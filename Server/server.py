from __future__ import annotations

import argparse
import base64
import json
import os
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from crypto import BOOTSTRAP_INFO, CryptoProtocol, SecureTokenVault
from vpn import MaxTransportConfig, MaxVpnSession


@dataclass(frozen=True)
class ConnectRequest:
    client_id: str
    device_id: str
    chat_id: int
    client_public_key: str
    sealed_token: dict[str, str]
    max_message_size: int
    request_timeout_seconds: int

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        default_max_message_size: int,
        default_request_timeout: int,
    ) -> "ConnectRequest":
        client_public_key = payload.get("client_public_key") or payload.get(
            "session_public_key"
        )
        sealed_token = payload.get("sealed_token")

        if not isinstance(client_public_key, str) or not client_public_key.strip():
            raise ValueError("client_public_key is required.")
        if not isinstance(sealed_token, dict):
            raise ValueError("sealed_token is required.")
        if (
            "ephemeral_public_key" not in sealed_token
            or "ciphertext" not in sealed_token
        ):
            raise ValueError(
                "sealed_token must contain ephemeral_public_key and ciphertext."
            )
        if not str(payload["client_id"]).strip():
            raise ValueError("client_id must not be empty.")
        if not str(payload["device_id"]).strip():
            raise ValueError("device_id must not be empty.")

        return cls(
            client_id=str(payload["client_id"]),
            device_id=str(payload["device_id"]),
            chat_id=int(payload["chat_id"]),
            client_public_key=client_public_key,
            sealed_token={
                "ephemeral_public_key": str(sealed_token["ephemeral_public_key"]),
                "ciphertext": str(sealed_token["ciphertext"]),
            },
            max_message_size=int(
                payload.get("max_message_size", default_max_message_size)
            ),
            request_timeout_seconds=int(
                payload.get("request_timeout_seconds", default_request_timeout)
            ),
        )


@dataclass(frozen=True)
class ServerConfig:
    host: str
    port: int
    ws_uri: str
    origin: str
    user_agent: str
    delete_opcode: int
    default_max_message_size: int
    heartbeat_interval_seconds: int
    rotation_interval_seconds: int
    request_timeout_seconds: int
    connect_ready_timeout_seconds: int
    handshake_private_key_pem: bytes

    @classmethod
    def from_env(cls) -> "ServerConfig":
        load_env_files(
            [
                Path(__file__).with_name(".env"),
                Path(__file__).resolve().parent.parent / ".env",
            ]
        )

        return cls(
            host=os.getenv("SERVER_HOST", "0.0.0.0"),
            port=int(os.getenv("SERVER_PORT", "8080")),
            ws_uri=os.getenv("MAX_WS_URI", "wss://ws-api.oneme.ru/websocket"),
            origin=os.getenv("MAX_ORIGIN", "https://web.max.ru"),
            user_agent=os.getenv(
                "MAX_USER_AGENT",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
            ),
            delete_opcode=int(os.getenv("MAX_DELETE_OPCODE", "66")),
            default_max_message_size=int(os.getenv("MAX_MESSAGE_SIZE", "4000")),
            heartbeat_interval_seconds=int(os.getenv("MAX_HEARTBEAT_INTERVAL", "20")),
            rotation_interval_seconds=int(os.getenv("VPN_ROTATION_INTERVAL", "300")),
            request_timeout_seconds=int(os.getenv("VPN_REQUEST_TIMEOUT", "30")),
            connect_ready_timeout_seconds=int(os.getenv("VPN_CONNECT_TIMEOUT", "15")),
            handshake_private_key_pem=load_handshake_private_key(),
        )

    def to_transport(self, request: ConnectRequest) -> MaxTransportConfig:
        return MaxTransportConfig(
            ws_uri=self.ws_uri,
            origin=self.origin,
            user_agent=self.user_agent,
            max_message_size=request.max_message_size,
            delete_opcode=self.delete_opcode,
            heartbeat_interval_seconds=self.heartbeat_interval_seconds,
            rotation_interval_seconds=self.rotation_interval_seconds,
            request_timeout_seconds=request.request_timeout_seconds,
        )


class SessionManager:
    def __init__(self, config: ServerConfig) -> None:
        self.config = config
        self._lock = threading.RLock()
        self._sessions_by_client: dict[str, MaxVpnSession] = {}
        self._sessions_by_session: dict[str, MaxVpnSession] = {}
        self._bootstrap_crypto = CryptoProtocol.from_private_pem(
            config.handshake_private_key_pem,
            info=BOOTSTRAP_INFO,
        )

    @property
    def bootstrap_public_key(self) -> str:
        return self._bootstrap_crypto.get_public_text()

    def bootstrap_payload(self) -> dict[str, Any]:
        return {
            "bootstrap_public_key": self.bootstrap_public_key,
            "defaults": {
                "max_message_size": self.config.default_max_message_size,
                "rotation_interval_seconds": self.config.rotation_interval_seconds,
                "inbound_tag": "[0]",
                "outbound_tag": "[1]",
            },
        }

    def connect(self, request: ConnectRequest) -> dict[str, Any]:
        token = CryptoProtocol.open_sealed_box(
            request.sealed_token,
            self.config.handshake_private_key_pem,
            info=BOOTSTRAP_INFO,
        ).decode("utf-8")

        session_crypto = CryptoProtocol()
        session_crypto.derive_shared_secret(request.client_public_key)

        token_vault = SecureTokenVault()
        token_vault.store(token, session_crypto, key_version=1)

        session = MaxVpnSession(
            session_id=os.urandom(8).hex(),
            client_id=request.client_id,
            device_id=request.device_id,
            chat_id=request.chat_id,
            crypto=session_crypto,
            token_vault=token_vault,
            transport=self.config.to_transport(request),
        )

        old_session = self._replace_session(request.client_id, session)
        if old_session is not None:
            old_session.stop()

        session.start()

        if not session.wait_until_ready(self.config.connect_ready_timeout_seconds):
            self.remove_session(session.session_id, request.client_id)
            session.stop()
            raise RuntimeError(
                session.snapshot()["last_error"]
                or "MAX session did not become ready in time."
            )

        return {
            "session_id": session.session_id,
            "server_public_key": session.public_key,
            "key_version": 1,
            "rotation_interval_seconds": self.config.rotation_interval_seconds,
            "request_timeout_seconds": request.request_timeout_seconds,
            "tunnel": {
                "client_tag": "[0]",
                "server_tag": "[1]",
                "max_message_size": request.max_message_size,
            },
        }

    def shutdown_all(self) -> None:
        with self._lock:
            sessions = list(self._sessions_by_session.values())
            self._sessions_by_client.clear()
            self._sessions_by_session.clear()
        for session in sessions:
            session.stop()

    def _replace_session(
        self,
        client_id: str,
        new_session: MaxVpnSession,
    ) -> MaxVpnSession | None:
        with self._lock:
            old_session = self._sessions_by_client.get(client_id)
            if old_session is not None:
                self._sessions_by_session.pop(old_session.session_id, None)
            self._sessions_by_client[client_id] = new_session
            self._sessions_by_session[new_session.session_id] = new_session
            return old_session

    def remove_session(self, session_id: str, client_id: str) -> None:
        with self._lock:
            current = self._sessions_by_client.get(client_id)
            if current and current.session_id == session_id:
                self._sessions_by_client.pop(client_id, None)
            self._sessions_by_session.pop(session_id, None)


class LuciHttpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        request_handler_class: type[BaseHTTPRequestHandler],
        *,
        session_manager: SessionManager,
    ) -> None:
        super().__init__(server_address, request_handler_class)
        self.session_manager = session_manager


class ConnectHandler(BaseHTTPRequestHandler):
    server: LuciHttpServer
    server_version = "LuciProtocol/1.0"

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/connect/max":
            self._write_json(404, {"error": "Not found."})
            return

        try:
            payload = self._read_json()
            action = payload.get("action")
            if action == "bootstrap":
                self._write_json(200, self.server.session_manager.bootstrap_payload())
                return

            request = ConnectRequest.from_payload(
                payload,
                default_max_message_size=self.server.session_manager.config.default_max_message_size,
                default_request_timeout=self.server.session_manager.config.request_timeout_seconds,
            )
            response = self.server.session_manager.connect(request)
            self._write_json(200, response)
        except ValueError as error:
            self._write_json(400, {"error": str(error)})
        except KeyError as error:
            self._write_json(400, {"error": f"Missing required field: {error.args[0]}"})
        except RuntimeError as error:
            self._write_json(502, {"error": str(error)})
        except Exception as error:
            self._write_json(500, {"error": str(error)})

    def do_GET(self) -> None:
        self._write_json(405, {"error": "Use POST /connect/max."})

    def log_message(self, format: str, *args: Any) -> None:
        print(
            "%s - - [%s] %s"
            % (self.address_string(), self.log_date_time_string(), format % args)
        )

    def _read_json(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length) if content_length else b"{}"
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError("Request body must be valid JSON.") from error

        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        return payload

    def _write_json(self, status_code: int, payload: dict[str, Any]) -> None:
        raw_body = json.dumps(
            payload, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw_body)))
        self.end_headers()
        self.wfile.write(raw_body)


def load_env_files(paths: list[Path]) -> None:
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            os.environ.setdefault(key, value)


def load_handshake_private_key() -> bytes:
    key_path = os.getenv("SERVER_HANDSHAKE_PRIVATE_KEY_PATH")
    if key_path:
        return Path(key_path).read_bytes()

    key_b64 = os.getenv("SERVER_HANDSHAKE_PRIVATE_KEY_B64")
    if key_b64:
        return base64.b64decode(key_b64)

    key_pem = os.getenv("SERVER_HANDSHAKE_PRIVATE_KEY_PEM")
    if key_pem:
        return key_pem.encode("utf-8")

    generated_key = CryptoProtocol.generate_private_pem()
    print(
        "SERVER_HANDSHAKE_PRIVATE_KEY_* is not set, generated an ephemeral bootstrap key for this process."
    )
    return generated_key


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Luci Protocol MAX bridge server")
    parser.add_argument("--host", help="Bind host override.")
    parser.add_argument("--port", type=int, help="Bind port override.")
    parser.add_argument(
        "--print-bootstrap-public-key",
        action="store_true",
        help="Print the bootstrap public key and exit.",
    )
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    config = ServerConfig.from_env()

    if args.host:
        config = ServerConfig(
            host=args.host,
            port=config.port,
            ws_uri=config.ws_uri,
            origin=config.origin,
            user_agent=config.user_agent,
            delete_opcode=config.delete_opcode,
            default_max_message_size=config.default_max_message_size,
            heartbeat_interval_seconds=config.heartbeat_interval_seconds,
            rotation_interval_seconds=config.rotation_interval_seconds,
            request_timeout_seconds=config.request_timeout_seconds,
            connect_ready_timeout_seconds=config.connect_ready_timeout_seconds,
            handshake_private_key_pem=config.handshake_private_key_pem,
        )
    if args.port:
        config = ServerConfig(
            host=config.host,
            port=args.port,
            ws_uri=config.ws_uri,
            origin=config.origin,
            user_agent=config.user_agent,
            delete_opcode=config.delete_opcode,
            default_max_message_size=config.default_max_message_size,
            heartbeat_interval_seconds=config.heartbeat_interval_seconds,
            rotation_interval_seconds=config.rotation_interval_seconds,
            request_timeout_seconds=config.request_timeout_seconds,
            connect_ready_timeout_seconds=config.connect_ready_timeout_seconds,
            handshake_private_key_pem=config.handshake_private_key_pem,
        )

    manager = SessionManager(config)

    if args.print_bootstrap_public_key:
        print(manager.bootstrap_public_key)
        return

    print(f"Listening on http://{config.host}:{config.port}")
    print(
        "POST /connect/max with {'action':'bootstrap'} to get the bootstrap public key."
    )
    print("Bootstrap public key:")
    print(manager.bootstrap_public_key)

    httpd = LuciHttpServer(
        (config.host, config.port),
        ConnectHandler,
        session_manager=manager,
    )

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        manager.shutdown_all()


if __name__ == "__main__":
    main()

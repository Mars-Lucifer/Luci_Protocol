from __future__ import annotations

import asyncio
import base64
import json
import queue
import ssl
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any

import websockets

from crypto import CryptoProtocol, SecureTokenVault


@dataclass(frozen=True)
class MaxTransportConfig:
    ws_uri: str
    origin: str
    user_agent: str
    max_message_size: int = 4000
    delete_opcode: int = 68
    connect_opcode: int = 6
    auth_opcode: int = 19
    send_opcode: int = 64
    incoming_opcode: int = 128
    heartbeat_opcode: int = 1
    heartbeat_interval_seconds: int = 20
    rotation_interval_seconds: int = 300
    request_timeout_seconds: int = 30
    inbound_tag: str = "[0]"
    outbound_tag: str = "[1]"


@dataclass(frozen=True)
class TunnelEnvelope:
    session_id: str
    message_id: str
    key_version: int
    index: int
    total: int
    start: bool
    end: bool
    payload: str

    def to_text(self, tag: str) -> str:
        packed = json.dumps(
            {
                "s": self.session_id,
                "m": self.message_id,
                "k": self.key_version,
                "i": self.index,
                "t": self.total,
                "b": int(self.start),
                "e": int(self.end),
                "p": self.payload,
            },
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return f"{tag}{packed}"

    @classmethod
    def from_text(cls, text: str, expected_tag: str) -> "TunnelEnvelope | None":
        if not text.startswith(expected_tag):
            return None
        body = json.loads(text[len(expected_tag) :])
        return cls(
            session_id=str(body["s"]),
            message_id=str(body["m"]),
            key_version=int(body["k"]),
            index=int(body["i"]),
            total=int(body["t"]),
            start=bool(body["b"]),
            end=bool(body["e"]),
            payload=str(body["p"]),
        )


class FragmentAssembler:
    def __init__(self, *, ttl_seconds: int = 180) -> None:
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._pending: dict[str, dict[str, Any]] = {}

    def push(self, envelope: TunnelEnvelope) -> bytes | None:
        with self._lock:
            self._cleanup_locked()
            state = self._pending.setdefault(
                envelope.message_id,
                {
                    "created_at": time.time(),
                    "session_id": envelope.session_id,
                    "key_version": envelope.key_version,
                    "total": envelope.total,
                    "parts": {},
                    "start_seen": False,
                    "end_seen": False,
                },
            )

            if state["session_id"] != envelope.session_id or state["total"] != envelope.total:
                raise ValueError("Fragment metadata mismatch.")

            state["parts"][envelope.index] = envelope.payload
            state["start_seen"] = state["start_seen"] or envelope.start
            state["end_seen"] = state["end_seen"] or envelope.end

            if len(state["parts"]) != envelope.total:
                return None
            if not state["start_seen"] or not state["end_seen"]:
                return None

            if any(index not in state["parts"] for index in range(envelope.total)):
                return None

            payload = "".join(state["parts"][index] for index in range(envelope.total))
            del self._pending[envelope.message_id]
            return base64.b64decode(payload)

    def _cleanup_locked(self) -> None:
        now = time.time()
        stale_ids = [
            message_id
            for message_id, state in self._pending.items()
            if now - state["created_at"] > self.ttl_seconds
        ]
        for message_id in stale_ids:
            del self._pending[message_id]


def execute_upstream_request(request_payload: dict[str, Any], *, timeout: int) -> dict[str, Any]:
    request_id = request_payload.get("request_id")
    method = str(request_payload.get("method", "GET")).upper()
    url = str(request_payload["url"])
    raw_headers = request_payload.get("headers") or {}
    headers = {
        str(key): str(value)
        for key, value in dict(raw_headers).items()
    }
    body_b64 = request_payload.get("body")
    body = base64.b64decode(body_b64) if body_b64 else None

    request = urllib.request.Request(url=url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout,
            context=ssl.create_default_context(),
        ) as response:
            response_body = response.read()
            return {
                "type": "http_response",
                "request_id": request_id,
                "ok": True,
                "status": response.status,
                "reason": response.reason,
                "url": response.geturl(),
                "headers": dict(response.getheaders()),
                "body": base64.b64encode(response_body).decode("ascii"),
            }
    except urllib.error.HTTPError as error:
        error_body = error.read()
        return {
            "type": "http_response",
            "request_id": request_id,
            "ok": False,
            "status": error.code,
            "reason": error.reason,
            "url": error.geturl(),
            "headers": dict(error.headers.items()),
            "body": base64.b64encode(error_body).decode("ascii"),
        }
    except Exception as error:
        return {
            "type": "http_response",
            "request_id": request_id,
            "ok": False,
            "status": 599,
            "reason": "UPSTREAM_ERROR",
            "error": str(error),
            "url": url,
            "headers": {},
            "body": "",
        }


class MaxVpnSession:
    def __init__(
        self,
        *,
        session_id: str,
        client_id: str,
        device_id: str,
        chat_id: int,
        crypto: CryptoProtocol,
        token_vault: SecureTokenVault,
        transport: MaxTransportConfig,
    ) -> None:
        self.session_id = session_id
        self.client_id = client_id
        self.device_id = device_id
        self.chat_id = chat_id
        self.transport = transport
        self.token_vault = token_vault

        self._stop_event = threading.Event()
        self._ready_event = threading.Event()
        self._crypto_lock = threading.RLock()
        self._cryptos: dict[int, CryptoProtocol] = {1: crypto}
        self._active_key_version = 1
        self._pending_rotations: dict[int, CryptoProtocol] = {}
        self._assembler = FragmentAssembler()
        self._request_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._outbound_queue: queue.Queue[bytes] = queue.Queue()
        self._threads: list[threading.Thread] = []
        self._seq_lock = threading.Lock()
        self._seq_counter = 1000
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ws: Any = None
        self._send_lock: asyncio.Lock | None = None
        self._last_error: str | None = None

    def start(self) -> None:
        if self._threads:
            return

        self._threads = [
            threading.Thread(
                target=self._run_transport_thread,
                name=f"{self.session_id}-transport",
                daemon=True,
            ),
            threading.Thread(
                target=self._run_request_worker,
                name=f"{self.session_id}-requests",
                daemon=True,
            ),
            threading.Thread(
                target=self._run_rotation_worker,
                name=f"{self.session_id}-rotation",
                daemon=True,
            ),
        ]

        for thread in self._threads:
            thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._request_queue.put({"type": "shutdown"})
        self._outbound_queue.put(b"")

        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(lambda: None)
            asyncio.run_coroutine_threadsafe(self._close_ws(), self._loop)

        current_thread = threading.current_thread()
        for thread in self._threads:
            if thread is current_thread:
                continue
            thread.join(timeout=2)

    def wait_until_ready(self, timeout: float) -> bool:
        return self._ready_event.wait(timeout)

    def snapshot(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "client_id": self.client_id,
            "device_id": self.device_id,
            "chat_id": self.chat_id,
            "key_version": self.active_key_version,
            "token": self.token_vault.snapshot().__dict__,
            "ready": self._ready_event.is_set(),
            "threads": 3,
            "last_error": self._last_error,
        }

    @property
    def public_key(self) -> str:
        return self._cryptos[1].get_public_text()

    @property
    def active_key_version(self) -> int:
        with self._crypto_lock:
            return self._active_key_version

    def _run_transport_thread(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        self._send_lock = asyncio.Lock()

        try:
            loop.run_until_complete(self._transport_main())
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()

    async def _transport_main(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self._connect_and_auth()
                self._ready_event.set()
                self._last_error = None

                listener = asyncio.create_task(self._listener())
                heartbeat = asyncio.create_task(self._heartbeat())
                outbound = asyncio.create_task(self._outbound_sender())

                done, pending = await asyncio.wait(
                    {listener, heartbeat, outbound},
                    return_when=asyncio.FIRST_EXCEPTION,
                )

                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

                for task in done:
                    exception = task.exception()
                    if exception:
                        raise exception
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self._ready_event.clear()
                self._last_error = str(error)
                if self._stop_event.is_set():
                    break
                await asyncio.sleep(3)
            finally:
                await self._close_ws()

    async def _connect_and_auth(self) -> None:
        headers = {
            "User-Agent": self.transport.user_agent,
            "Origin": self.transport.origin,
        }
        self._ws = await self._open_websocket(headers)

        auth_sequence = [
            {
                "ver": 11,
                "cmd": 0,
                "seq": 0,
                "opcode": self.transport.connect_opcode,
                "payload": {
                    "userAgent": {"deviceType": "WEB"},
                    "deviceId": self.device_id,
                },
            },
            {
                "ver": 11,
                "cmd": 0,
                "seq": 1,
                "opcode": self.transport.auth_opcode,
                "payload": {
                    "token": self._load_active_token(),
                    "chatsCount": 0,
                    "interactive": True,
                },
            },
        ]

        for packet in auth_sequence:
            await self._send_packet(packet)
            await asyncio.sleep(0.1)

    async def _open_websocket(self, headers: dict[str, str]) -> Any:
        try:
            return await websockets.connect(
                self.transport.ws_uri,
                additional_headers=headers,
                max_size=None,
            )
        except TypeError:
            return await websockets.connect(
                self.transport.ws_uri,
                extra_headers=headers,
                max_size=None,
            )

    async def _close_ws(self) -> None:
        if self._ws is None:
            return
        try:
            await self._ws.close()
        except Exception:
            pass
        finally:
            self._ws = None

    async def _heartbeat(self) -> None:
        while not self._stop_event.is_set() and self._ws is not None:
            packet = {
                "ver": 11,
                "cmd": 0,
                "seq": self._next_seq(),
                "opcode": self.transport.heartbeat_opcode,
                "payload": {},
            }
            await self._send_packet(packet)
            await asyncio.sleep(self.transport.heartbeat_interval_seconds)

    async def _listener(self) -> None:
        async for message in self._ws:
            try:
                data = json.loads(message)
                if data.get("opcode") != self.transport.incoming_opcode:
                    continue

                message_payload = data.get("payload", {}).get("message", {})
                text = message_payload.get("text", "")
                message_id = message_payload.get("id")
                envelope = TunnelEnvelope.from_text(text, self.transport.inbound_tag)
                if envelope is None or envelope.session_id != self.session_id:
                    continue

                try:
                    completed_payload = self._assembler.push(envelope)
                finally:
                    if message_id is not None:
                        await self._delete_message(message_id)

                if completed_payload is None:
                    continue

                crypto = self._get_crypto(envelope.key_version)
                decrypted_payload = crypto.decrypt(completed_payload)
                await self._handle_decrypted_payload(decrypted_payload)
            except Exception as error:
                self._last_error = str(error)

    async def _outbound_sender(self) -> None:
        while not self._stop_event.is_set():
            payload = await asyncio.to_thread(self._outbound_queue.get)
            if self._stop_event.is_set():
                return
            if not payload:
                continue
            await self._send_encrypted_payload(payload)

    async def _handle_decrypted_payload(self, payload: bytes) -> None:
        message = json.loads(payload.decode("utf-8"))
        message_type = message.get("type")

        if message_type == "http_request":
            self._request_queue.put(message)
            return

        if message_type == "rotate_request":
            await self._handle_rotate_request(message)
            return

        if message_type == "rotate_ack":
            self._handle_rotate_ack(message)
            return

        if message_type == "close":
            self.stop()
            return

        self._outbound_queue.put(
            self._encode_json(
                {
                    "type": "error",
                    "reason": "UNKNOWN_MESSAGE_TYPE",
                    "received_type": message_type,
                }
            )
        )

    async def _handle_rotate_request(self, message: dict[str, Any]) -> None:
        next_version = int(message["key_version"])
        next_crypto = CryptoProtocol()
        next_crypto.derive_shared_secret(message["server_public_key"])

        ack = {
            "type": "rotate_ack",
            "session_id": self.session_id,
            "key_version": next_version,
            "client_public_key": next_crypto.get_public_text(),
            "issued_at": int(time.time()),
        }
        await self._send_encrypted_payload(self._encode_json(ack))
        self._activate_crypto(next_version, next_crypto)

    def _handle_rotate_ack(self, message: dict[str, Any]) -> None:
        next_version = int(message["key_version"])
        peer_public_key = message["client_public_key"]

        with self._crypto_lock:
            pending_crypto = self._pending_rotations.pop(next_version, None)

        if pending_crypto is None:
            return

        pending_crypto.derive_shared_secret(peer_public_key)
        self._activate_crypto(next_version, pending_crypto)

    def _activate_crypto(self, next_version: int, next_crypto: CryptoProtocol) -> None:
        with self._crypto_lock:
            current_version = self._active_key_version
            current_crypto = self._cryptos[current_version]
            self.token_vault.rotate(current_crypto, next_crypto, key_version=next_version)
            self._cryptos[next_version] = next_crypto
            self._active_key_version = next_version
            obsolete_versions = [
                version
                for version in self._cryptos
                if version < next_version - 1
            ]
            for version in obsolete_versions:
                del self._cryptos[version]

    def _run_request_worker(self) -> None:
        while not self._stop_event.is_set():
            try:
                request = self._request_queue.get(timeout=1)
            except queue.Empty:
                continue

            if request.get("type") == "shutdown":
                return

            try:
                response = execute_upstream_request(
                    request,
                    timeout=self.transport.request_timeout_seconds,
                )
            except Exception as error:
                response = {
                    "type": "http_response",
                    "request_id": request.get("request_id"),
                    "ok": False,
                    "status": 599,
                    "reason": "REQUEST_WORKER_ERROR",
                    "error": str(error),
                    "headers": {},
                    "body": "",
                }

            self._outbound_queue.put(self._encode_json(response))

    def _run_rotation_worker(self) -> None:
        interval = self.transport.rotation_interval_seconds
        while not self._stop_event.wait(interval):
            if self._loop is None or self._loop.is_closed():
                continue

            future = asyncio.run_coroutine_threadsafe(
                self._send_rotate_request(),
                self._loop,
            )
            try:
                future.result(timeout=15)
            except Exception as error:
                self._last_error = str(error)

    async def _send_rotate_request(self) -> None:
        with self._crypto_lock:
            next_version = self._active_key_version + 1
            if next_version in self._pending_rotations:
                return
            pending_crypto = CryptoProtocol()
            self._pending_rotations[next_version] = pending_crypto

        rotate_request = {
            "type": "rotate_request",
            "session_id": self.session_id,
            "key_version": next_version,
            "server_public_key": pending_crypto.get_public_text(),
            "issued_at": int(time.time()),
        }
        await self._send_encrypted_payload(self._encode_json(rotate_request))

    async def _send_encrypted_payload(self, payload: bytes) -> None:
        key_version, crypto = self._get_active_crypto()
        encrypted_payload = crypto.encrypt(payload)
        payload_b64 = base64.b64encode(encrypted_payload).decode("ascii")
        message_id = str(uuid.uuid4())

        chunks = self._split_payload_into_chunks(
            message_id=message_id,
            key_version=key_version,
            payload_b64=payload_b64,
            tag=self.transport.outbound_tag,
        )

        for index, chunk in enumerate(chunks):
            envelope = TunnelEnvelope(
                session_id=self.session_id,
                message_id=message_id,
                key_version=key_version,
                index=index,
                total=len(chunks),
                start=index == 0,
                end=index == len(chunks) - 1,
                payload=chunk,
            )
            packet = {
                "ver": 11,
                "cmd": 0,
                "seq": self._next_seq(),
                "opcode": self.transport.send_opcode,
                "payload": {
                    "chatId": self.chat_id,
                    "message": {
                        "text": envelope.to_text(self.transport.outbound_tag),
                        "cid": int(time.time() * 1000),
                    },
                },
            }
            await self._send_packet(packet)

    def _split_payload_into_chunks(
        self,
        *,
        message_id: str,
        key_version: int,
        payload_b64: str,
        tag: str,
    ) -> list[str]:
        chunk_size = max(256, self.transport.max_message_size - 512)

        while True:
            chunks = [
                payload_b64[index : index + chunk_size]
                for index in range(0, len(payload_b64), chunk_size)
            ] or [""]

            fits_limit = True
            for index, chunk in enumerate(chunks):
                envelope = TunnelEnvelope(
                    session_id=self.session_id,
                    message_id=message_id,
                    key_version=key_version,
                    index=index,
                    total=len(chunks),
                    start=index == 0,
                    end=index == len(chunks) - 1,
                    payload=chunk,
                )
                if len(envelope.to_text(tag)) > self.transport.max_message_size:
                    fits_limit = False
                    chunk_size -= 128
                    break

            if fits_limit:
                return chunks
            if chunk_size <= 128:
                raise ValueError("max_message_size is too small for tunnel metadata.")

    async def _delete_message(self, message_id: int | str) -> None:
        if self.transport.delete_opcode < 0:
            return

        packet = {
            "ver": 11,
            "cmd": 0,
            "seq": self._next_seq(),
            "opcode": self.transport.delete_opcode,
            "payload": {
                "chatId": self.chat_id,
                "messageIds": [message_id],
            },
        }
        await self._send_packet(packet)

    async def _send_packet(self, packet: dict[str, Any]) -> None:
        if self._ws is None:
            raise ConnectionError("MAX websocket is not connected.")
        if self._send_lock is None:
            raise ConnectionError("Send lock is not initialized.")

        async with self._send_lock:
            await self._ws.send(
                json.dumps(packet, separators=(",", ":"), ensure_ascii=False)
            )

    def _next_seq(self) -> int:
        with self._seq_lock:
            current = self._seq_counter
            self._seq_counter += 1
            return current

    def _get_active_crypto(self) -> tuple[int, CryptoProtocol]:
        with self._crypto_lock:
            version = self._active_key_version
            return version, self._cryptos[version]

    def _get_crypto(self, key_version: int) -> CryptoProtocol:
        with self._crypto_lock:
            if key_version in self._cryptos:
                return self._cryptos[key_version]
            return self._cryptos[self._active_key_version]

    def _load_active_token(self) -> str:
        _, crypto = self._get_active_crypto()
        return self.token_vault.load(crypto)

    @staticmethod
    def _encode_json(payload: dict[str, Any]) -> bytes:
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

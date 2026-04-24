from __future__ import annotations

import base64
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


SESSION_INFO = b"luci-protocol/session"
BOOTSTRAP_INFO = b"luci-protocol/bootstrap"


class CryptoStateError(RuntimeError):
    pass


class CryptoProtocol:
    def __init__(
        self,
        private_key: ec.EllipticCurvePrivateKey | None = None,
        *,
        info: bytes = SESSION_INFO,
    ) -> None:
        self.private_key = private_key or ec.generate_private_key(ec.SECP256R1())
        self.public_key = self.private_key.public_key()
        self.info = info
        self.shared_secret: bytes | None = None
        self.aesgcm: AESGCM | None = None

    @classmethod
    def from_private_pem(
        cls,
        private_pem: bytes | str,
        *,
        info: bytes = SESSION_INFO,
    ) -> "CryptoProtocol":
        private_bytes = private_pem.encode("utf-8") if isinstance(private_pem, str) else private_pem
        private_key = serialization.load_pem_private_key(private_bytes, password=None)
        return cls(private_key=private_key, info=info)

    @staticmethod
    def generate_private_pem() -> bytes:
        private_key = ec.generate_private_key(ec.SECP256R1())
        return private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    def export_private_pem(self) -> bytes:
        return self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    def get_public_bytes(self) -> bytes:
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def get_public_text(self) -> str:
        return self.get_public_bytes().decode("utf-8")

    def derive_shared_secret(self, peer_public_bytes: bytes | str) -> bytes:
        peer_bytes = peer_public_bytes.encode("utf-8") if isinstance(peer_public_bytes, str) else peer_public_bytes
        peer_public_key = serialization.load_pem_public_key(peer_bytes)
        shared_key = self.private_key.exchange(ec.ECDH(), peer_public_key)
        hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=self.info)
        self.shared_secret = hkdf.derive(shared_key)
        self.aesgcm = AESGCM(self.shared_secret)
        return self.shared_secret

    def _require_cipher(self) -> AESGCM:
        if self.aesgcm is None:
            raise CryptoStateError("Shared secret is not derived yet.")
        return self.aesgcm

    def encrypt(self, data: bytes, associated_data: bytes | None = None) -> bytes:
        nonce = os.urandom(12)
        ciphertext = self._require_cipher().encrypt(nonce, data, associated_data)
        return nonce + ciphertext

    def decrypt(self, encrypted_data: bytes, associated_data: bytes | None = None) -> bytes:
        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:]
        return self._require_cipher().decrypt(nonce, ciphertext, associated_data)

    def encrypt_to_base64(self, data: bytes, associated_data: bytes | None = None) -> str:
        return base64.b64encode(self.encrypt(data, associated_data)).decode("ascii")

    def decrypt_from_base64(self, encrypted_data: str, associated_data: bytes | None = None) -> bytes:
        return self.decrypt(base64.b64decode(encrypted_data), associated_data)

    @classmethod
    def seal_for_public_key(
        cls,
        data: bytes,
        peer_public_bytes: bytes | str,
        *,
        info: bytes = BOOTSTRAP_INFO,
    ) -> dict[str, str]:
        envelope_crypto = cls(info=info)
        envelope_crypto.derive_shared_secret(peer_public_bytes)
        return {
            "ephemeral_public_key": envelope_crypto.get_public_text(),
            "ciphertext": base64.b64encode(envelope_crypto.encrypt(data)).decode("ascii"),
        }

    @classmethod
    def open_sealed_box(
        cls,
        sealed_box: dict[str, str],
        private_key_pem: bytes | str,
        *,
        info: bytes = BOOTSTRAP_INFO,
    ) -> bytes:
        opener = cls.from_private_pem(private_key_pem, info=info)
        opener.derive_shared_secret(sealed_box["ephemeral_public_key"])
        return opener.decrypt(base64.b64decode(sealed_box["ciphertext"]))


@dataclass(frozen=True)
class TokenSnapshot:
    key_version: int
    updated_at: float


class SecureTokenVault:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._encrypted_token: bytes | None = None
        self._key_version = 0
        self._updated_at = 0.0

    def store(self, token: str, crypto: CryptoProtocol, *, key_version: int) -> None:
        token_bytes = token.encode("utf-8")
        with self._lock:
            self._encrypted_token = crypto.encrypt(token_bytes)
            self._key_version = key_version
            self._updated_at = time.time()

    def load(self, crypto: CryptoProtocol) -> str:
        with self._lock:
            if self._encrypted_token is None:
                raise CryptoStateError("Token is not stored yet.")
            encrypted_token = self._encrypted_token
        return crypto.decrypt(encrypted_token).decode("utf-8")

    def rotate(
        self,
        current_crypto: CryptoProtocol,
        next_crypto: CryptoProtocol,
        *,
        key_version: int,
    ) -> None:
        plaintext_token = self.load(current_crypto)
        self.store(plaintext_token, next_crypto, key_version=key_version)

    def snapshot(self) -> TokenSnapshot:
        with self._lock:
            return TokenSnapshot(
                key_version=self._key_version,
                updated_at=self._updated_at,
            )

def ensure_bootstrap_key(key_path: str = "bootstrap_private_key.pem") -> None:
        path = Path(key_path)
        if not path.exists():
            print(f"[*] Ключ {key_path} не найден. Генерирую новый...")
            # Используем ваш статический метод из класса CryptoProtocol
            private_pem = CryptoProtocol.generate_private_pem()
            path.write_bytes(private_pem)
            # Устанавливаем права доступа (чтение/запись только для владельца)
            path.chmod(0o600)
            print(f"[+] Ключ успешно создан и сохранен в {key_path}")
        else:
            print(f"[+] Используется существующий ключ: {key_path}")
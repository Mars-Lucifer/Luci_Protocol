import os
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class CryptoProtocol:
    def __init__(self):
        # Генерируем свою пару ключей
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        self.public_key = self.private_key.public_key()
        self.shared_secret = None
        self.aesgcm = None

    def get_public_bytes(self):
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def derive_shared_secret(self, peer_public_bytes):
        peer_public_key = serialization.load_pem_public_key(peer_public_bytes)
        shared_key = self.private_key.exchange(ec.ECDH(), peer_public_key)

        # Пропускаем через HKDF для получения надежного 32-байтного ключа для AES
        hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"vpn-tunnel")
        self.shared_secret = hkdf.derive(shared_key)
        self.aesgcm = AESGCM(self.shared_secret)

    def encrypt(self, data: bytes) -> bytes:
        nonce = os.urandom(12)
        ciphertext = self.aesgcm.encrypt(nonce, data, None)
        return nonce + ciphertext  # Приклеиваем nonce к началу

    def decrypt(self, encrypted_data: bytes) -> bytes:
        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:]
        return self.aesgcm.decrypt(nonce, ciphertext, None)

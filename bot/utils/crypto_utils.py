import asyncio
from base64 import urlsafe_b64decode
from base64 import urlsafe_b64encode
import os

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import padding as sym_padding
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers import Cipher
from cryptography.hazmat.primitives.ciphers import algorithms
from cryptography.hazmat.primitives.ciphers import modes
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from redis import Redis


async def generate_rsa_keypair():
    def sync_rsa_keypair_generation():
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend(),
        )
        public_key = private_key.public_key()

        # Serialize keys
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return private_pem, public_pem

    return await asyncio.to_thread(sync_rsa_keypair_generation)


async def encrypt_private_key(private_key: bytes, passphrase: str) -> bytes:
    def sync_encrypt_private_key():
        salt = os.urandom(16)
        kdf = PBKDF2HMAC(
            algorithm=SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,
        )
        key = kdf.derive(passphrase.encode())
        encrypted_key = urlsafe_b64encode(salt + key + private_key)
        return encrypted_key

    return await asyncio.to_thread(sync_encrypt_private_key)


async def decrypt_private_key(encrypted_key: bytes, passphrase: str) -> bytes:
    def sync_decrypt_private_key():
        decoded = urlsafe_b64decode(encrypted_key)
        salt, key, private_key = decoded[:16], decoded[16:48], decoded[48:]
        kdf = PBKDF2HMAC(
            algorithm=SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,
        )
        derived_key = kdf.derive(passphrase.encode())
        if derived_key != key:
            msg = "Incorrect passphrase."
            raise ValueError(msg)
        return private_key

    return await asyncio.to_thread(sync_decrypt_private_key)


def generate_symmetric_key() -> bytes:
    """Generates a 256-bit symmetric key for AES."""
    return os.urandom(32)


async def save_symmetric_key(conversation_id: str, symmetric_key: bytes, redis: Redis):
    """Saves the symmetric key securely in Redis."""
    await redis.set(f"aes_key:{conversation_id}", symmetric_key.hex())


async def retrieve_symmetric_key(conversation_id: str, redis: Redis) -> bytes | None:
    """Retrieves the symmetric key from Redis."""
    hex_key = await redis.get(f"aes_key:{conversation_id}")
    return bytes.fromhex(hex_key) if hex_key else None


async def encrypt_symmetric_key_with_rsa(public_key_pem: bytes, symmetric_key: bytes):
    """Symmetric key is encrypted with public key to be safely passed to other party."""
    if isinstance(public_key_pem, str):
        public_key_pem = public_key_pem.encode("utf-8")

    def sync_encrypt_symmetric_key_with_rsa():
        """Encrypts the symmetric key with the recipient's public RSA key."""
        public_key = load_pem_public_key(public_key_pem)
        encrypted_key = public_key.encrypt(
            symmetric_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        return encrypted_key

    return await asyncio.to_thread(sync_encrypt_symmetric_key_with_rsa)


async def decrypt_symmetric_key_with_rsa(private_key_pem: bytes, encrypted_key: bytes):
    if isinstance(private_key_pem, str):
        private_key_pem = private_key_pem.encode("utf-8")

    def sync_decrypt_symmetric_key_with_rsa():
        from cryptography.hazmat.primitives.serialization import load_pem_private_key

        private_key = load_pem_private_key(private_key_pem, password=None)
        symmetric_key = private_key.decrypt(
            encrypted_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        return symmetric_key

    return await asyncio.to_thread(sync_decrypt_symmetric_key_with_rsa)


async def encrypt_message_with_aes(key: bytes, plaintext: str) -> bytes:
    """Encrypts a plaintext message using AES-256 in CFB mode."""

    def sync_encrypt():
        # Generate a new, random IV for each encryption for security
        iv = os.urandom(16)
        cipher = Cipher(algorithms.AES(key), modes.CFB(iv))
        encryptor = cipher.encryptor()

        padder = sym_padding.PKCS7(128).padder()
        padded_plaintext = padder.update(plaintext.encode("utf-8")) + padder.finalize()

        ciphertext = encryptor.update(padded_plaintext) + encryptor.finalize()
        # Prepend the IV to the ciphertext; it's needed for decryption
        return iv + ciphertext

    return await asyncio.to_thread(sync_encrypt)


async def decrypt_message_with_aes(key: bytes, iv_ciphertext: bytes) -> str:
    """Decrypts a message using AES-256 in CFB mode."""

    def sync_decrypt():
        # Extract the IV from the beginning of the message
        iv = iv_ciphertext[:16]
        ciphertext = iv_ciphertext[16:]

        cipher = Cipher(algorithms.AES(key), modes.CFB(iv))
        decryptor = cipher.decryptor()
        padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()

        unpadder = sym_padding.PKCS7(128).unpadder()
        plaintext_bytes = unpadder.update(padded_plaintext) + unpadder.finalize()
        return plaintext_bytes.decode("utf-8")

    return await asyncio.to_thread(sync_decrypt)

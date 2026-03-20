"""AES-256-GCM encryption with HKDF key derivation and versioning."""

import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

CURRENT_VERSION = 1


class CryptoError(Exception):
    """Raised on decryption failure (wrong key, tampered data, etc.)."""


def derive_key(server_secret: str, user_id: int, version: int = CURRENT_VERSION) -> bytes:
    """Derive a 256-bit encryption key using HKDF-SHA256.

    Args:
        server_secret: Server-side secret string (at least 32 chars recommended).
        user_id: Telegram user ID used as salt, ensuring per-user key isolation.
        version: Key version for future rotation support.

    Returns:
        32-byte derived key suitable for AES-256-GCM.
    """
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=user_id.to_bytes(8, "big"),
        info=f"telethon-session-encryption-v{version}".encode(),
    ).derive(server_secret.encode())


def encrypt(plaintext: bytes, key: bytes) -> bytes:
    """Encrypt with AES-256-GCM.

    Returns:
        Versioned blob: [1B version][12B nonce][ciphertext][16B tag].
    """
    if len(key) != 32:
        raise CryptoError(f"Key must be 32 bytes, got {len(key)}")
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return bytes([CURRENT_VERSION]) + nonce + ciphertext


def decrypt(blob: bytes, key: bytes) -> bytes:
    """Decrypt a versioned blob.

    Args:
        blob: Output from encrypt() — version byte + nonce + ciphertext + tag.
        key: 32-byte AES-256 key (from derive_key).

    Raises:
        CryptoError: On any decryption failure (wrong key, tampered data, truncated blob).
    """
    if len(blob) < 1 + 12 + 16:
        raise CryptoError("Blob too short")
    version = blob[0]
    if version != CURRENT_VERSION:
        raise CryptoError(f"Unsupported blob version: {version}")
    nonce = blob[1:13]
    ciphertext = blob[13:]
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, None)
    except Exception as e:
        raise CryptoError(f"Decryption failed: {e}") from e

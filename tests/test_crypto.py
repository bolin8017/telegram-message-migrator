import pytest

from app.crypto import CryptoError, decrypt, derive_key, encrypt


def test_encrypt_decrypt_roundtrip():
    key = derive_key(server_secret="a" * 32, user_id=12345, version=1)
    plaintext = b"telethon-session-data-here"
    blob = encrypt(plaintext, key)
    assert decrypt(blob, key) == plaintext


def test_decrypt_wrong_key_fails():
    key1 = derive_key(server_secret="a" * 32, user_id=12345, version=1)
    key2 = derive_key(server_secret="b" * 32, user_id=12345, version=1)
    blob = encrypt(b"secret", key1)
    with pytest.raises(CryptoError):
        decrypt(blob, key2)


def test_blob_has_version_prefix():
    key = derive_key(server_secret="a" * 32, user_id=12345, version=1)
    blob = encrypt(b"data", key)
    assert blob[0] == 1  # version byte


def test_different_users_different_keys():
    key1 = derive_key(server_secret="a" * 32, user_id=111, version=1)
    key2 = derive_key(server_secret="a" * 32, user_id=222, version=1)
    assert key1 != key2


def test_key_versioning():
    key_v1 = derive_key(server_secret="a" * 32, user_id=12345, version=1)
    key_v2 = derive_key(server_secret="a" * 32, user_id=12345, version=2)
    assert key_v1 != key_v2
    blob = encrypt(b"data", key_v1)
    assert decrypt(blob, key_v1) == b"data"


def test_tampered_ciphertext_fails():
    key = derive_key(server_secret="a" * 32, user_id=12345)
    blob = bytearray(encrypt(b"secret", key))
    blob[20] ^= 0xFF
    with pytest.raises(CryptoError):
        decrypt(bytes(blob), key)


def test_truncated_blob_fails():
    with pytest.raises(CryptoError, match="Blob too short"):
        decrypt(b"\x01" * 10, b"\x00" * 32)

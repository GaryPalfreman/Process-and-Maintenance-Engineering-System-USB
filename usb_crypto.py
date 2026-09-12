"""Authenticated at-rest encryption for the PMES USB vault.

The live-data key is random. A key-encryption key derived from the user's
PIN/password wraps that random key. This allows future PIN changes by re-wrapping
the data key instead of re-encrypting the entire engineering dataset.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"PMESENC1\n"
DEFAULT_ITERATIONS = 600_000


def _derive_wrap_key(pin: str, salt: bytes, iterations: int) -> bytes:
    if not pin:
        raise ValueError("Vault PIN/password is required for encrypted storage")
    return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, iterations, dklen=32)


def encrypt_bytes(data: bytes, key: bytes, associated_data: bytes = b"PMES-USB") -> bytes:
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, data, associated_data)
    envelope = {
        "schema": "pmes-encrypted-envelope-v1",
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
    }
    return MAGIC + json.dumps(envelope, separators=(",", ":")).encode("utf-8")


def decrypt_bytes(payload: bytes, key: bytes, associated_data: bytes = b"PMES-USB") -> bytes:
    if not payload.startswith(MAGIC):
        raise ValueError("This file is not PMES encrypted data")
    envelope = json.loads(payload[len(MAGIC):].decode("utf-8"))
    nonce = base64.b64decode(envelope["nonce"])
    ciphertext = base64.b64decode(envelope["ciphertext"])
    return AESGCM(key).decrypt(nonce, ciphertext, associated_data)


def new_encryption_metadata(pin: str) -> dict:
    salt = os.urandom(16)
    iterations = DEFAULT_ITERATIONS
    wrap_key = _derive_wrap_key(pin, salt, iterations)
    data_key = os.urandom(32)
    wrapped = encrypt_bytes(data_key, wrap_key, b"PMES-DATA-KEY")
    return {
        "schema": "pmes-encryption-v1",
        "algorithm": "AES-256-GCM",
        "kdf": "PBKDF2-HMAC-SHA256",
        "iterations": iterations,
        "salt": base64.b64encode(salt).decode("ascii"),
        "wrapped_data_key": base64.b64encode(wrapped).decode("ascii"),
    }


def derive_key(pin: str, metadata: dict) -> bytes:
    salt = base64.b64decode(metadata["salt"])
    iterations = int(metadata.get("iterations", DEFAULT_ITERATIONS))
    wrap_key = _derive_wrap_key(pin, salt, iterations)
    wrapped = base64.b64decode(metadata["wrapped_data_key"])
    return decrypt_bytes(wrapped, wrap_key, b"PMES-DATA-KEY")


def rewrap_metadata(current_pin: str, new_pin: str, metadata: dict) -> dict:
    data_key = derive_key(current_pin, metadata)
    salt = os.urandom(16)
    iterations = DEFAULT_ITERATIONS
    wrap_key = _derive_wrap_key(new_pin, salt, iterations)
    wrapped = encrypt_bytes(data_key, wrap_key, b"PMES-DATA-KEY")
    result = dict(metadata)
    result["iterations"] = iterations
    result["salt"] = base64.b64encode(salt).decode("ascii")
    result["wrapped_data_key"] = base64.b64encode(wrapped).decode("ascii")
    return result


def is_encrypted_bytes(payload: bytes) -> bool:
    return payload.startswith(MAGIC)


def atomic_write(path: Path, payload: bytes) -> None:
    path = Path(path)
    temp = path.with_suffix(path.suffix + ".tmp")
    with open(temp, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)

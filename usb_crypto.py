"""Authenticated at-rest encryption for the PMES USB vault.

Uses AES-256-GCM with a key derived from the user's vault PIN/password using
PBKDF2-HMAC-SHA256. The salt is public metadata; the PIN/password is never
written to disk by this module.
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


def new_encryption_metadata() -> dict:
    return {
        "schema": "pmes-encryption-v1",
        "algorithm": "AES-256-GCM",
        "kdf": "PBKDF2-HMAC-SHA256",
        "iterations": DEFAULT_ITERATIONS,
        "salt": base64.b64encode(os.urandom(16)).decode("ascii"),
    }


def derive_key(pin: str, metadata: dict) -> bytes:
    if not pin:
        raise ValueError("Vault PIN/password is required for encrypted storage")
    salt = base64.b64decode(metadata["salt"])
    iterations = int(metadata.get("iterations", DEFAULT_ITERATIONS))
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

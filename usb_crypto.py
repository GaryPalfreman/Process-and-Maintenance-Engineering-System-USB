"""Authenticated at-rest encryption for the PMES USB vault."""
from __future__ import annotations
import base64, hashlib, json, os
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"PMESENC1\n"
DEFAULT_ITERATIONS = 600000


def new_encryption_metadata():
    return {
        "schema": "pmes-encryption-v1",
        "algorithm": "AES-256-GCM",
        "kdf": "PBKDF2-HMAC-SHA256",
        "iterations": DEFAULT_ITERATIONS,
        "salt": base64.b64encode(os.urandom(16)).decode("ascii"),
    }


def derive_key(pin, metadata):
    if not pin:
        raise ValueError("Vault PIN/password is required for encrypted storage")
    salt = base64.b64decode(metadata["salt"])
    iterations = int(metadata.get("iterations", DEFAULT_ITERATIONS))
    return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, iterations, dklen=32)


def encrypt_bytes(data, key, associated_data=b"PMES-USB"):
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, data, associated_data)
    envelope = {
        "schema": "pmes-encrypted-envelope-v1",
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
    }
    return MAGIC + json.dumps(envelope, separators=(",", ":")).encode("utf-8")


def decrypt_bytes(payload, key, associated_data=b"PMES-USB"):
    if not payload.startswith(MAGIC):
        raise ValueError("This file is not PMES encrypted data")
    envelope = json.loads(payload[len(MAGIC):].decode("utf-8"))
    nonce = base64.b64decode(envelope["nonce"])
    ciphertext = base64.b64decode(envelope["ciphertext"])
    return AESGCM(key).decrypt(nonce, ciphertext, associated_data)


def atomic_write(path, payload):
    path = Path(path)
    temp = path.with_suffix(path.suffix + ".tmp")
    with open(temp, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)

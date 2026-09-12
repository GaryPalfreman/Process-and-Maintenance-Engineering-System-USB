"""Authenticated at-rest encryption for the PMES USB vault."""
from __future__ import annotations
import base64, hashlib, json, os
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"PMESENC1\n"
DEFAULT_ITERATIONS = 600000
WRAP_AAD = b"PMES-DATA-KEY-WRAP-V2"


def _pbkdf2(pin, salt_b64, iterations):
    if not pin:
        raise ValueError("Vault PIN/password is required for encrypted storage")
    salt = base64.b64decode(salt_b64)
    return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, int(iterations), dklen=32)


def new_encryption_metadata():
    return {
        "schema": "pmes-encryption-v1",
        "algorithm": "AES-256-GCM",
        "kdf": "PBKDF2-HMAC-SHA256",
        "iterations": DEFAULT_ITERATIONS,
        "salt": base64.b64encode(os.urandom(16)).decode("ascii"),
    }


def make_wrapped_key_entry(pin, data_key):
    salt = base64.b64encode(os.urandom(16)).decode("ascii")
    iterations = DEFAULT_ITERATIONS
    kek = _pbkdf2(pin, salt, iterations)
    nonce = os.urandom(12)
    wrapped = AESGCM(kek).encrypt(nonce, data_key, WRAP_AAD)
    return {
        "salt": salt,
        "iterations": iterations,
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "wrapped_data_key": base64.b64encode(wrapped).decode("ascii"),
    }


def wrapped_metadata(entries):
    return {
        "schema": "pmes-encryption-v2",
        "algorithm": "AES-256-GCM",
        "key_protection": "PIN-wrapped-data-key",
        "kdf": "PBKDF2-HMAC-SHA256",
        "key_wraps": list(entries),
    }


def derive_key(pin, metadata):
    schema = metadata.get("schema")
    if schema == "pmes-encryption-v1":
        return _pbkdf2(pin, metadata["salt"], metadata.get("iterations", DEFAULT_ITERATIONS))
    if schema == "pmes-encryption-v2":
        last_error = None
        for entry in metadata.get("key_wraps", []):
            try:
                kek = _pbkdf2(pin, entry["salt"], entry.get("iterations", DEFAULT_ITERATIONS))
                nonce = base64.b64decode(entry["nonce"])
                wrapped = base64.b64decode(entry["wrapped_data_key"])
                return AESGCM(kek).decrypt(nonce, wrapped, WRAP_AAD)
            except Exception as exc:
                last_error = exc
        raise ValueError("PIN/password could not unwrap the vault data key") from last_error
    raise ValueError("Unsupported Engineering Vault encryption metadata")


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

"""Emergency recovery-key support for an encrypted PMES USB vault."""
from __future__ import annotations
import base64, json, os, secrets
from datetime import datetime
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from usb_storage import vault_path, encryption_metadata, load_from_vault

RECOVERY_FILE = "vault_recovery.json"
AAD = b"PMES-RECOVERY-KEY-V1"


def recovery_path(vault):
    return vault_path(vault) / RECOVERY_FILE


def recovery_status(vault):
    path = recovery_path(vault)
    result = {"configured": path.exists(), "created_at": "", "verified": False}
    if not path.exists():
        return result
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        result["created_at"] = data.get("created_at", "")
        result["verified"] = data.get("schema") == "pmes-recovery-v1"
    except Exception:
        pass
    return result


def create_recovery_key(vault, data_key):
    recovery_key = secrets.token_bytes(32)
    nonce = secrets.token_bytes(12)
    wrapped = AESGCM(recovery_key).encrypt(nonce, data_key, AAD)
    payload = {
        "schema": "pmes-recovery-v1",
        "created_at": datetime.now().replace(microsecond=0).isoformat(),
        "nonce": base64.urlsafe_b64encode(nonce).decode("ascii"),
        "wrapped_data_key": base64.urlsafe_b64encode(wrapped).decode("ascii"),
    }
    path = recovery_path(vault)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temp, path)
    token = base64.urlsafe_b64encode(recovery_key).decode("ascii")
    return token


def unwrap_data_key(vault, recovery_token):
    data = json.loads(recovery_path(vault).read_text(encoding="utf-8"))
    if data.get("schema") != "pmes-recovery-v1":
        raise ValueError("Unsupported recovery record")
    recovery_key = base64.urlsafe_b64decode(recovery_token.encode("ascii"))
    nonce = base64.urlsafe_b64decode(data["nonce"].encode("ascii"))
    wrapped = base64.urlsafe_b64decode(data["wrapped_data_key"].encode("ascii"))
    return AESGCM(recovery_key).decrypt(nonce, wrapped, AAD)


def verify_recovery_key(vault, recovery_token):
    try:
        key = unwrap_data_key(vault, recovery_token)
        store = load_from_vault(vault, key)
        return isinstance(store, dict) and bool(store.get("schema"))
    except Exception:
        return False

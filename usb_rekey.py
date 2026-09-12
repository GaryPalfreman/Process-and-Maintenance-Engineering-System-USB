"""Safe v0.7A PIN re-key and emergency reset for encrypted PMES vaults."""
from __future__ import annotations
import json
import os
from pathlib import Path

from usb_crypto import make_wrapped_key_entry, wrapped_metadata, derive_key
from usb_storage import vault_path, ENCRYPTION_FILE, encryption_metadata, load_from_vault
from usb_security import verify_pin, _set_pin_verifier
from usb_recovery import unwrap_data_key


def _write_metadata(vault, metadata):
    path = vault_path(vault) / ENCRYPTION_FILE
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    os.replace(temp, path)


def _verify_key(vault, key):
    store = load_from_vault(vault, key)
    if not isinstance(store, dict) or not store.get("schema"):
        raise ValueError("Vault data-key verification failed")
    return True


def ensure_wrapped_key_mode(vault, current_pin, current_key):
    """Atomically migrate v1 PIN-derived metadata to v2 wrapped-key metadata."""
    if not verify_pin(vault, current_pin):
        raise ValueError("Current PIN/password is incorrect")
    _verify_key(vault, current_key)
    meta = encryption_metadata(vault)
    if meta.get("schema") == "pmes-encryption-v2":
        return meta
    entry = make_wrapped_key_entry(current_pin, current_key)
    new_meta = wrapped_metadata([entry])
    if derive_key(current_pin, new_meta) != current_key:
        raise ValueError("Wrapped-key migration verification failed")
    _write_metadata(vault, new_meta)
    _verify_key(vault, derive_key(current_pin, encryption_metadata(vault)))
    return new_meta


def rekey_pin(vault, current_pin, new_pin, current_key):
    """Change PIN without re-encrypting live data or backups.

    A temporary metadata state accepts both old and new PINs. Security verifier is
    switched only after both wraps are verified, then the old wrap is removed.
    """
    if not new_pin:
        raise ValueError("New PIN/password cannot be blank for an encrypted vault")
    ensure_wrapped_key_mode(vault, current_pin, current_key)
    if not verify_pin(vault, current_pin):
        raise ValueError("Current PIN/password is incorrect")

    old_entry = make_wrapped_key_entry(current_pin, current_key)
    new_entry = make_wrapped_key_entry(new_pin, current_key)
    transition = wrapped_metadata([old_entry, new_entry])
    if derive_key(current_pin, transition) != current_key or derive_key(new_pin, transition) != current_key:
        raise ValueError("Re-key transition verification failed")

    _write_metadata(vault, transition)
    _verify_key(vault, derive_key(current_pin, transition))
    _verify_key(vault, derive_key(new_pin, transition))

    _set_pin_verifier(vault, new_pin)
    final_meta = wrapped_metadata([new_entry])
    _write_metadata(vault, final_meta)
    new_key = derive_key(new_pin, encryption_metadata(vault))
    _verify_key(vault, new_key)
    return new_key


def reset_pin_with_recovery(vault, recovery_token, new_pin):
    """Reset a forgotten PIN using the separately stored emergency recovery key."""
    if not new_pin:
        raise ValueError("New PIN/password cannot be blank")
    data_key = unwrap_data_key(vault, recovery_token)
    _verify_key(vault, data_key)
    new_entry = make_wrapped_key_entry(new_pin, data_key)
    new_meta = wrapped_metadata([new_entry])
    if derive_key(new_pin, new_meta) != data_key:
        raise ValueError("Recovery re-key verification failed")
    _write_metadata(vault, new_meta)
    _set_pin_verifier(vault, new_pin)
    _verify_key(vault, derive_key(new_pin, encryption_metadata(vault)))
    return data_key

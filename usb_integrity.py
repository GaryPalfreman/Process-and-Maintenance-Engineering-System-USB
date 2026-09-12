"""Integrity and recovery-readiness checks for the PMES USB Engineering Vault."""
from datetime import datetime
from pathlib import Path

from usb_storage import (
    encryption_status, list_backups, validate_backup, load_from_vault,
)


def integrity_report(vault, encryption_key=None):
    enc = encryption_status(vault)
    report = {
        "checked_at": datetime.now().replace(microsecond=0).isoformat(),
        "encryption_enabled": bool(enc.get("enabled")),
        "live_data_ok": False,
        "valid_backups": 0,
        "invalid_backups": 0,
        "latest_valid_backup": "",
        "recovery_ready": False,
        "errors": [],
    }
    try:
        store = load_from_vault(vault, encryption_key)
        report["live_data_ok"] = isinstance(store, dict) and bool(store.get("schema"))
    except Exception as exc:
        report["errors"].append(f"Live dataset: {exc}")

    for backup in list_backups(vault, 50):
        result = validate_backup(backup, encryption_key)
        if result.get("valid"):
            report["valid_backups"] += 1
            if not report["latest_valid_backup"]:
                report["latest_valid_backup"] = str(backup)
        else:
            report["invalid_backups"] += 1
            report["errors"].append(f"Backup {Path(backup).name}: {result.get('error','validation failed')}")

    report["recovery_ready"] = report["live_data_ok"] and report["valid_backups"] > 0
    return report

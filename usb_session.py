"""Session-level protection for the PMES USB vault."""
from usb_integrity import integrity_report
from usb_storage import create_backup, list_backups


def open_session_protection(vault, store, encryption_key=None, keep_backups=100):
    report = integrity_report(vault, encryption_key)
    if not report.get("live_data_ok"):
        raise RuntimeError("Live Engineering Vault data failed startup integrity verification")
    backup = create_backup(vault, store, "session_open", encryption_key)
    removed = []
    backups = list_backups(vault, 10000)
    for path in backups[keep_backups:]:
        removed.append(path.name)
        path.unlink(missing_ok=True)
        path.with_suffix(path.suffix + ".sha256").unlink(missing_ok=True)
    return {"integrity": report, "session_backup": str(backup), "removed_backups": removed}

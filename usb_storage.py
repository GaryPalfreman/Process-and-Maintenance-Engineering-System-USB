import hashlib
import io
import json
import os
import platform
import shutil
import stat
import subprocess
import uuid
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from engineering_system import blank_store, load_store, store_bytes, backup_zip
from usb_crypto import new_encryption_metadata, derive_key, encrypt_bytes, decrypt_bytes, atomic_write

VAULT_FOLDER = "ENGINEERING_SYSTEM"
DATA_FILE = "engineering_data.json"
ENCRYPTED_DATA_FILE = "engineering_data.pmes"
ENCRYPTION_FILE = "vault_encryption.json"
MARKER_FILE = "vault_identity.json"
AUTO_BACKUP_MINUTES = 30
BACKUP_JSON = "Process_Maintenance_Engineering_System.json"
BACKUP_MARKER_FILE = "last_backup.txt"
LEGACY_BACKUP_MARKER_FILE = ".last_backup"


def removable_roots():
    roots = []
    system = platform.system()
    if system == "Darwin":
        base = Path("/Volumes")
        if base.exists():
            for p in base.iterdir():
                if not p.is_dir():
                    continue
                if p.name in {"Macintosh HD", "Macintosh HD - Data"} or p.name.startswith(".timemachine"):
                    continue
                roots.append(p)
    elif system == "Windows":
        for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
            p = Path(f"{letter}:\\")
            if p.exists():
                roots.append(p)
    else:
        user = os.environ.get("USER", "")
        for base in [Path("/media") / user, Path("/run/media") / user, Path("/mnt")]:
            if base.exists():
                roots.extend(p for p in base.iterdir() if p.is_dir())
    return roots


def vault_path(root):
    p = Path(root)
    return p if p.name == VAULT_FOLDER else p / VAULT_FOLDER


def drive_root(vault):
    p = vault_path(vault)
    return p.parent if p.name == VAULT_FOLDER else p


def read_identity(vault):
    p = vault_path(vault)
    identity = json.loads((p / MARKER_FILE).read_text(encoding="utf-8"))
    if identity.get("schema") != "pmes-usb-vault" or not identity.get("vault_id"):
        raise ValueError("Invalid Engineering Vault identity")
    return identity


def find_vaults():
    found = []
    for root in removable_roots():
        p = vault_path(root)
        if not (p / MARKER_FILE).exists():
            continue
        try:
            read_identity(p)
            found.append(p)
        except Exception:
            continue
    return found


def vault_is_connected(vault):
    try:
        p = vault_path(vault)
        expected = read_identity(p).get("vault_id")
        for candidate in find_vaults():
            try:
                if read_identity(candidate).get("vault_id") == expected:
                    return True
            except Exception:
                pass
    except Exception:
        return False
    return False


def initialise_vault(root, label="Engineering Vault"):
    p = vault_path(root)
    p.mkdir(parents=True, exist_ok=True)
    (p / "Backups").mkdir(exist_ok=True)
    (p / "Documents").mkdir(exist_ok=True)
    identity = {
        "schema": "pmes-usb-vault",
        "vault_id": str(uuid.uuid4()),
        "label": label,
        "created_at": datetime.now().replace(microsecond=0).isoformat(),
    }
    (p / MARKER_FILE).write_text(json.dumps(identity, indent=2), encoding="utf-8")
    (p / DATA_FILE).write_bytes(store_bytes(blank_store()))
    return p


def encryption_metadata(vault):
    path = vault_path(vault) / ENCRYPTION_FILE
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") not in {"pmes-encryption-v1", "pmes-encryption-v2"}:
        raise ValueError("Unsupported Engineering Vault encryption metadata")
    return data


def encryption_enabled(vault):
    return encryption_metadata(vault) is not None


def encryption_status(vault):
    p = vault_path(vault)
    enabled = encryption_enabled(p)
    return {
        "enabled": enabled,
        "encrypted_data_present": (p / ENCRYPTED_DATA_FILE).exists(),
        "plaintext_data_present": (p / DATA_FILE).exists(),
        "legacy_plaintext_backups": len(list((p / "Backups").rglob("PMES_*.zip"))) if (p / "Backups").exists() else 0,
        "encrypted_backups": len(list((p / "Backups").rglob("PMES_*.pmesbak"))) if (p / "Backups").exists() else 0,
    }


def load_from_vault(vault, encryption_key=None):
    p = vault_path(vault)
    read_identity(p)
    if encryption_enabled(p):
        if not encryption_key:
            raise PermissionError("Encrypted Engineering Vault is locked")
        data_file = p / ENCRYPTED_DATA_FILE
        if not data_file.exists():
            raise FileNotFoundError(f"Missing {ENCRYPTED_DATA_FILE}")
        plain = decrypt_bytes(data_file.read_bytes(), encryption_key, b"PMES-LIVE-DATA")
        return load_store(plain)
    data_file = p / DATA_FILE
    if not data_file.exists():
        raise FileNotFoundError(f"Missing {DATA_FILE}")
    return load_store(data_file.read_bytes())


def save_to_vault(vault, store, encryption_key=None):
    p = vault_path(vault)
    if not vault_is_connected(p):
        raise RuntimeError("Engineering Vault is not connected. Write blocked.")
    read_identity(p)
    payload = store_bytes(store)
    if encryption_enabled(p):
        if not encryption_key:
            raise PermissionError("Encrypted Engineering Vault is locked")
        target = p / ENCRYPTED_DATA_FILE
        atomic_write(target, encrypt_bytes(payload, encryption_key, b"PMES-LIVE-DATA"))
        return target
    target = p / DATA_FILE
    atomic_write(target, payload)
    return target


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _write_checksum(path, payload):
    path.with_suffix(path.suffix + ".sha256").write_text(_sha256_bytes(payload) + "\n", encoding="utf-8")


def _write_backup_marker(backups_root, when):
    """Best-effort backup timestamp marker.

    Backup files and their checksums are the authoritative protection records.
    The marker is only a scheduling optimisation, so a removable-drive metadata
    permission issue must never invalidate a successfully written backup.
    """
    backups_root.mkdir(parents=True, exist_ok=True)
    marker = backups_root / BACKUP_MARKER_FILE
    payload = when.isoformat() + "\n"
    try:
        atomic_write(marker, payload.encode("utf-8"))
        return True
    except (OSError, PermissionError):
        try:
            if marker.exists():
                os.chmod(marker, stat.S_IREAD | stat.S_IWRITE)
                marker.unlink()
            marker.write_text(payload, encoding="utf-8")
            return True
        except (OSError, PermissionError):
            return False


def _latest_backup_time(vault):
    """Return the most recent known backup time without requiring a marker file."""
    backups_root = vault_path(vault) / "Backups"
    for marker_name in (BACKUP_MARKER_FILE, LEGACY_BACKUP_MARKER_FILE):
        marker = backups_root / marker_name
        try:
            return datetime.fromisoformat(marker.read_text(encoding="utf-8").strip())
        except Exception:
            pass

    latest_mtime = None
    if backups_root.exists():
        for candidate in backups_root.rglob("PMES_*.*"):
            if not candidate.is_file() or candidate.suffix not in {".zip", ".pmesbak"}:
                continue
            try:
                mtime = candidate.stat().st_mtime
            except OSError:
                continue
            latest_mtime = mtime if latest_mtime is None else max(latest_mtime, mtime)
    return datetime.fromtimestamp(latest_mtime) if latest_mtime is not None else None


def create_backup(vault, store, reason="manual", encryption_key=None):
    p = vault_path(vault)
    if not vault_is_connected(p):
        raise RuntimeError("Engineering Vault is not connected. Backup blocked.")
    read_identity(p)
    now = datetime.now().replace(microsecond=0)
    folder = p / "Backups" / now.strftime("%Y-%m")
    folder.mkdir(parents=True, exist_ok=True)
    plain_payload = backup_zip(store)
    if encryption_enabled(p):
        if not encryption_key:
            raise PermissionError("Encrypted Engineering Vault is locked")
        target = folder / f"PMES_{now.strftime('%Y%m%d_%H%M%S')}_{reason}.pmesbak"
        payload = encrypt_bytes(plain_payload, encryption_key, b"PMES-BACKUP")
    else:
        target = folder / f"PMES_{now.strftime('%Y%m%d_%H%M%S')}_{reason}.zip"
        payload = plain_payload
    atomic_write(target, payload)
    _write_checksum(target, payload)
    _write_backup_marker(p / "Backups", now)
    return target


def backup_due(vault, minutes=AUTO_BACKUP_MINUTES):
    try:
        last = _latest_backup_time(vault)
        if last is None:
            return True
        return datetime.now() - last >= timedelta(minutes=minutes)
    except Exception:
        return True


def list_backups(vault, limit=50):
    root = vault_path(vault) / "Backups"
    if not root.exists():
        return []
    files = [p for p in root.rglob("PMES_*.*") if p.is_file() and p.suffix in {".zip", ".pmesbak"}]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[:limit]


def validate_backup(path, encryption_key=None):
    path = Path(path)
    result = {"valid": False, "path": str(path), "checksum_ok": None, "encrypted": path.suffix == ".pmesbak", "error": ""}
    try:
        payload = path.read_bytes()
        sidecar = path.with_suffix(path.suffix + ".sha256")
        if sidecar.exists():
            result["checksum_ok"] = sidecar.read_text(encoding="utf-8").strip() == _sha256_bytes(payload)
            if not result["checksum_ok"]:
                raise ValueError("Backup checksum mismatch")
        if path.suffix == ".pmesbak":
            if not encryption_key:
                raise PermissionError("Encrypted backup requires an unlocked vault")
            payload = decrypt_bytes(payload, encryption_key, b"PMES-BACKUP")
        with zipfile.ZipFile(io.BytesIO(payload), "r") as zf:
            if BACKUP_JSON not in zf.namelist():
                raise ValueError("Backup JSON is missing")
            store = load_store(zf.read(BACKUP_JSON))
        result["valid"] = True
        result["records"] = sum(len(v) for v in store.values() if isinstance(v, list))
    except Exception as exc:
        result["error"] = str(exc)
    return result


def restore_backup(vault, backup_path, encryption_key=None):
    p = vault_path(vault)
    check = validate_backup(backup_path, encryption_key)
    if not check.get("valid"):
        raise ValueError(check.get("error") or "Backup validation failed")
    current = load_from_vault(p, encryption_key)
    safety = create_backup(p, current, "pre_restore", encryption_key)
    payload = Path(backup_path).read_bytes()
    if Path(backup_path).suffix == ".pmesbak":
        payload = decrypt_bytes(payload, encryption_key, b"PMES-BACKUP")
    with zipfile.ZipFile(io.BytesIO(payload), "r") as zf:
        restored = load_store(zf.read(BACKUP_JSON))
    save_to_vault(p, restored, encryption_key)
    return restored, safety

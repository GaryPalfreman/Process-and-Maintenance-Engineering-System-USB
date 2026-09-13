import hashlib
import io
import json
import os
import platform
import shutil
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
    """Best-effort scheduling marker; real backup files remain authoritative."""
    marker = Path(backups_root) / BACKUP_MARKER_FILE
    try:
        marker.write_text(when.isoformat() + "\n", encoding="utf-8")
        return True
    except OSError:
        return False


def _latest_backup_time(vault):
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


def _encrypt_existing_backup(path, key):
    path = Path(path)
    check = validate_backup(path)
    if not check.get("valid"):
        raise ValueError(f"Cannot migrate invalid backup {path.name}: {check.get('error')}")
    plain = path.read_bytes()
    encrypted = encrypt_bytes(plain, key, b"PMES-BACKUP")
    target = path.with_suffix(".pmesbak")
    atomic_write(target, encrypted)
    _write_checksum(target, encrypted)
    verify = validate_backup(target, key)
    if not verify.get("valid"):
        target.unlink(missing_ok=True)
        target.with_suffix(target.suffix + ".sha256").unlink(missing_ok=True)
        raise ValueError(f"Encrypted backup verification failed for {path.name}")
    path.unlink()
    path.with_suffix(path.suffix + ".sha256").unlink(missing_ok=True)
    return target


def migrate_to_encrypted(vault, store, pin):
    """Safely migrate plaintext live data and PMES backup ZIPs to encrypted storage."""
    p = vault_path(vault)
    if encryption_enabled(p):
        raise ValueError("Engineering Vault encryption is already enabled")
    if not pin:
        raise ValueError("A vault PIN/password is required before enabling encryption")

    safety = create_backup(p, store, "pre_encryption")
    check = validate_backup(safety)
    if not check.get("valid"):
        raise ValueError("Pre-encryption safety backup failed validation")

    metadata = new_encryption_metadata()
    key = derive_key(pin, metadata)
    encrypted_live = encrypt_bytes(store_bytes(store), key, b"PMES-LIVE-DATA")
    live_target = p / ENCRYPTED_DATA_FILE
    atomic_write(live_target, encrypted_live)
    test_store = load_store(decrypt_bytes(live_target.read_bytes(), key, b"PMES-LIVE-DATA"))
    if test_store.get("schema") != store.get("schema"):
        live_target.unlink(missing_ok=True)
        raise ValueError("Encrypted live-data verification failed")

    meta_path = p / ENCRYPTION_FILE
    meta_temp = meta_path.with_suffix(".json.tmp")
    meta_temp.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    os.replace(meta_temp, meta_path)

    migrated = []
    for legacy in sorted((p / "Backups").rglob("PMES_*.zip")):
        migrated.append(_encrypt_existing_backup(legacy, key))

    (p / DATA_FILE).unlink(missing_ok=True)
    final = load_from_vault(p, key)
    if final.get("schema") != store.get("schema"):
        raise ValueError("Encrypted vault final verification failed")
    return {"key": key, "encrypted_live": str(live_target), "migrated_backups": len(migrated)}


def safe_eject(vault):
    """Best-effort OS eject. Returns (success, message)."""
    p = vault_path(vault)
    root = drive_root(p)
    system = platform.system()
    try:
        if system == "Darwin":
            proc = subprocess.run(["diskutil", "eject", str(root)], capture_output=True, text=True, timeout=20)
            ok = proc.returncode == 0
            return ok, (proc.stdout or proc.stderr).strip()
        if system == "Windows":
            drive = root.drive or str(root)[:2]
            script = (
                "$d='" + drive.replace("'", "''") + "'; "
                "$s=New-Object -ComObject Shell.Application; "
                "$f=$s.Namespace(17); "
                "$i=$f.ParseName($d); "
                "if($i){$i.InvokeVerb('Eject'); Start-Sleep -Seconds 2; exit 0}else{exit 1}"
            )
            proc = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=20)
            return proc.returncode == 0, (proc.stdout or proc.stderr or "Eject command sent").strip()
        proc = subprocess.run(["udisksctl", "unmount", "-b", str(root)], capture_output=True, text=True, timeout=20)
        return proc.returncode == 0, (proc.stdout or proc.stderr).strip()
    except Exception as exc:
        return False, str(exc)


def vault_status(vault):
    p = vault_path(vault)
    identity = read_identity(p)
    usage = shutil.disk_usage(p)
    enc = encryption_status(p)
    return {
        "label": identity.get("label", "Engineering Vault"),
        "vault_id": identity.get("vault_id", ""),
        "path": str(p),
        "free_bytes": usage.free,
        "total_bytes": usage.total,
        "encryption": enc,
    }

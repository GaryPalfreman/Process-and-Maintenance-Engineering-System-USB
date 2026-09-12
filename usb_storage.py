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

VAULT_FOLDER = "ENGINEERING_SYSTEM"
DATA_FILE = "engineering_data.json"
MARKER_FILE = "vault_identity.json"
AUTO_BACKUP_MINUTES = 30
BACKUP_JSON = "Process_Maintenance_Engineering_System.json"


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


def load_from_vault(vault):
    p = vault_path(vault)
    read_identity(p)
    data_file = p / DATA_FILE
    if not data_file.exists():
        raise FileNotFoundError(f"Missing {DATA_FILE}")
    return load_store(data_file.read_bytes())


def save_to_vault(vault, store):
    p = vault_path(vault)
    if not vault_is_connected(p):
        raise RuntimeError("Engineering Vault is not connected. Write blocked.")
    read_identity(p)
    target = p / DATA_FILE
    temp = p / (DATA_FILE + ".tmp")
    payload = store_bytes(store)
    with open(temp, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, target)
    return target


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def create_backup(vault, store, reason="manual"):
    p = vault_path(vault)
    if not vault_is_connected(p):
        raise RuntimeError("Engineering Vault is not connected. Backup blocked.")
    read_identity(p)
    now = datetime.now().replace(microsecond=0)
    folder = p / "Backups" / now.strftime("%Y-%m")
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"PMES_{now.strftime('%Y%m%d_%H%M%S')}_{reason}.zip"
    payload = backup_zip(store)
    target.write_bytes(payload)
    checksum = _sha256_bytes(payload)
    target.with_suffix(target.suffix + ".sha256").write_text(checksum + "\n", encoding="utf-8")
    (p / "Backups" / ".last_backup").write_text(now.isoformat(), encoding="utf-8")
    return target


def backup_due(vault, minutes=AUTO_BACKUP_MINUTES):
    marker = vault_path(vault) / "Backups" / ".last_backup"
    try:
        last = datetime.fromisoformat(marker.read_text(encoding="utf-8").strip())
        return datetime.now() - last >= timedelta(minutes=minutes)
    except Exception:
        return True


def list_backups(vault, limit=50):
    root = vault_path(vault) / "Backups"
    if not root.exists():
        return []
    files = [p for p in root.rglob("PMES_*.zip") if p.is_file()]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[:limit]


def validate_backup(path):
    path = Path(path)
    result = {"valid": False, "path": str(path), "checksum_ok": None, "error": ""}
    try:
        payload = path.read_bytes()
        sidecar = path.with_suffix(path.suffix + ".sha256")
        if sidecar.exists():
            result["checksum_ok"] = sidecar.read_text(encoding="utf-8").strip() == _sha256_bytes(payload)
            if not result["checksum_ok"]:
                raise ValueError("Backup checksum mismatch")
        with zipfile.ZipFile(io.BytesIO(payload), "r") as zf:
            if BACKUP_JSON not in zf.namelist():
                raise ValueError("Backup JSON is missing")
            store = load_store(zf.read(BACKUP_JSON))
        result["valid"] = True
        result["records"] = sum(len(v) for k, v in store.items() if isinstance(v, list))
    except Exception as exc:
        result["error"] = str(exc)
    return result


def restore_backup(vault, backup_path):
    p = vault_path(vault)
    check = validate_backup(backup_path)
    if not check.get("valid"):
        raise ValueError(check.get("error") or "Backup validation failed")
    current = load_from_vault(p)
    safety = create_backup(p, current, "pre_restore")
    with zipfile.ZipFile(backup_path, "r") as zf:
        restored = load_store(zf.read(BACKUP_JSON))
    save_to_vault(p, restored)
    return restored, safety


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
    return {
        "label": identity.get("label", "Engineering Vault"),
        "vault_id": identity.get("vault_id", ""),
        "path": str(p),
        "free_bytes": usage.free,
        "total_bytes": usage.total,
    }

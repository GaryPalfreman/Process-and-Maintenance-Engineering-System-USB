import json
import os
import platform
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from engineering_system import blank_store, load_store, store_bytes, backup_zip

VAULT_FOLDER = "ENGINEERING_SYSTEM"
DATA_FILE = "engineering_data.json"
MARKER_FILE = "vault_identity.json"
AUTO_BACKUP_MINUTES = 30


def removable_roots():
    roots = []
    system = platform.system()
    if system == "Darwin":
        base = Path("/Volumes")
        if base.exists():
            for p in base.iterdir():
                if not p.is_dir():
                    continue
                # Exclude the internal startup volume and Time Machine helper mounts.
                if p.name in {"Macintosh HD", "Macintosh HD - Data"} or p.name.startswith(".timemachine"):
                    continue
                roots.append(p)
    elif system == "Windows":
        # Do not depend on a particular drive letter. The vault marker identifies the drive.
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


def create_backup(vault, store, reason="manual"):
    p = vault_path(vault)
    read_identity(p)
    now = datetime.now().replace(microsecond=0)
    folder = p / "Backups" / now.strftime("%Y-%m")
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"PMES_{now.strftime('%Y%m%d_%H%M%S')}_{reason}.zip"
    target.write_bytes(backup_zip(store))
    (p / "Backups" / ".last_backup").write_text(now.isoformat(), encoding="utf-8")
    return target


def backup_due(vault, minutes=AUTO_BACKUP_MINUTES):
    marker = vault_path(vault) / "Backups" / ".last_backup"
    try:
        last = datetime.fromisoformat(marker.read_text(encoding="utf-8").strip())
        return datetime.now() - last >= timedelta(minutes=minutes)
    except Exception:
        return True


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

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
    if platform.system() == "Darwin":
        base = Path("/Volumes")
        if base.exists():
            roots = [p for p in base.iterdir() if p.is_dir()]
    elif platform.system() == "Windows":
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


def find_vaults():
    found = []
    for root in removable_roots():
        p = vault_path(root)
        if (p / MARKER_FILE).exists():
            found.append(p)
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
    return load_store((p / DATA_FILE).read_bytes())


def save_to_vault(vault, store):
    p = vault_path(vault)
    target = p / DATA_FILE
    temp = p / (DATA_FILE + ".tmp")
    temp.write_bytes(store_bytes(store))
    os.replace(temp, target)
    return target


def create_backup(vault, store, reason="manual"):
    p = vault_path(vault)
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
    identity = json.loads((p / MARKER_FILE).read_text(encoding="utf-8"))
    usage = shutil.disk_usage(p)
    return {
        "label": identity.get("label", "Engineering Vault"),
        "vault_id": identity.get("vault_id", ""),
        "path": str(p),
        "free_bytes": usage.free,
        "total_bytes": usage.total,
    }

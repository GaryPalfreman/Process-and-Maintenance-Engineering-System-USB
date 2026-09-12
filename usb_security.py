"""Local access controls for the PMES USB Engineering Vault."""
from __future__ import annotations
import base64, hashlib, hmac, json, os, platform, secrets
from datetime import datetime
from pathlib import Path
from usb_storage import read_identity, vault_path

SECURITY_FILE = "vault_security.json"
LOCAL_FILE = "authorised_vault.json"
ITERATIONS = 600000


def local_file():
    if platform.system() == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "PMES-USB"
    else:
        base = Path.home() / ".pmes-usb"
    return base / LOCAL_FILE


def security_file(vault):
    return vault_path(vault) / SECURITY_FILE


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2), encoding="utf-8")
    os.replace(temp, path)


def _hash_pin(pin, salt, iterations=ITERATIONS):
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, iterations, dklen=32)
    return base64.b64encode(digest).decode()


def configure(vault, pin=""):
    identity = read_identity(vault)
    vault_id = identity["vault_id"]
    config = {"schema":"pmes-usb-security-v1","vault_id":vault_id,"pin_enabled":bool(pin),"configured_at":datetime.now().isoformat(timespec="seconds")}
    if pin:
        salt = secrets.token_bytes(16)
        config.update({"salt":base64.b64encode(salt).decode(),"pin_hash":_hash_pin(pin,salt),"iterations":ITERATIONS})
    _write(security_file(vault), config)
    _write(local_file(), {"schema":"pmes-usb-local-v1","vault_id":vault_id,"authorised_at":datetime.now().isoformat(timespec="seconds")})
    return status(vault)


def status(vault):
    vault_id = read_identity(vault)["vault_id"]
    sf = security_file(vault)
    result = {"configured":sf.exists(),"computer_authorised":False,"pin_enabled":False,"vault_id":vault_id}
    if not sf.exists(): return result
    try:
        config = json.loads(sf.read_text(encoding="utf-8"))
        result["pin_enabled"] = bool(config.get("pin_enabled"))
        lf = local_file()
        if lf.exists():
            local = json.loads(lf.read_text(encoding="utf-8"))
            result["computer_authorised"] = local.get("vault_id") == vault_id
    except Exception:
        pass
    return result


def verify_pin(vault, pin):
    config = json.loads(security_file(vault).read_text(encoding="utf-8"))
    if not config.get("pin_enabled"): return True
    salt = base64.b64decode(config["salt"])
    candidate = _hash_pin(pin, salt, int(config.get("iterations", ITERATIONS)))
    return hmac.compare_digest(candidate, config.get("pin_hash", ""))


def change_pin(vault, current_pin, new_pin):
    if not verify_pin(vault, current_pin): raise ValueError("Current PIN/password is incorrect")
    config = json.loads(security_file(vault).read_text(encoding="utf-8"))
    if new_pin:
        salt = secrets.token_bytes(16)
        config.update({"pin_enabled":True,"salt":base64.b64encode(salt).decode(),"pin_hash":_hash_pin(new_pin,salt),"iterations":ITERATIONS})
    else:
        config["pin_enabled"] = False
        for key in ("salt","pin_hash","iterations"): config.pop(key, None)
    _write(security_file(vault), config)


def revoke_this_computer(vault):
    path = local_file()
    if path.exists(): path.unlink()

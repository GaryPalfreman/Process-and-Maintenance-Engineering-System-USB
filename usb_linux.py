"""Linux-specific helpers for the PMES USB edition.

These helpers are prepared for Linux portability but remain physically
unvalidated until the real Engineering Vault is tested on a Linux computer.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from usb_storage import drive_root, vault_path


def safe_eject_linux(vault):
    """Best-effort Linux unmount/eject using desktop-friendly tools first."""
    root = Path(drive_root(vault_path(vault)))

    if shutil.which("gio"):
        proc = subprocess.run(
            ["gio", "mount", "-u", str(root)],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if proc.returncode == 0:
            return True, (proc.stdout or proc.stderr or "Linux volume unmounted with gio").strip()

    if shutil.which("umount"):
        proc = subprocess.run(
            ["umount", str(root)],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if proc.returncode == 0:
            return True, (proc.stdout or proc.stderr or "Linux volume unmounted").strip()
        return False, (proc.stdout or proc.stderr or "Linux unmount failed").strip()

    return False, "No supported Linux unmount tool was found (gio or umount)."

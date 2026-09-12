"""Installer/updater for the PMES USB edition.

Run this on each Mac or Windows computer that will use the Engineering Vault.
The installed application is a clean runtime snapshot, NOT a Git repository.
The external Engineering Vault and its data are never modified by application
updates except for refreshing the two clickable launcher files on the drive.
"""
from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import sys
from pathlib import Path

from usb_storage import find_vaults

APP_FOLDER = "PMES-USB"
MAC_LAUNCHER = "START ENGINEERING SYSTEM - MAC.command"
WINDOWS_LAUNCHER = "START ENGINEERING SYSTEM - WINDOWS.cmd"
DESKTOP_NAME_MAC = "Process and Maintenance Engineering System.command"
DESKTOP_NAME_WINDOWS = "Process and Maintenance Engineering System.cmd"

# Repository/development material must never be copied into the installed runtime.
EXCLUDED_NAMES = {
    ".git", ".github", ".venv", "__pycache__", ".DS_Store",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
}


def install_root() -> Path:
    if platform.system() == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / APP_FOLDER
    return Path.home() / "Applications" / APP_FOLDER


def vault_root(vault: Path) -> Path:
    return vault.parent if vault.name == "ENGINEERING_SYSTEM" else vault


def _make_writable(path: str) -> None:
    """Best-effort permission repair for files copied by an older installer."""
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    except OSError:
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass


def _rmtree_onerror(func, path, exc_info):
    """Retry removal after making a legacy file/directory writable."""
    _make_writable(path)
    func(path)


def remove_path(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, onerror=_rmtree_onerror)
    else:
        _make_writable(str(path))
        path.unlink(missing_ok=True)


def clean_runtime(target: Path) -> None:
    """Remove the old runtime while preserving its virtual environment.

    This deliberately removes any legacy .git directory copied by v0.3 so Git
    permissions can never interfere with future application updates.
    """
    target.mkdir(parents=True, exist_ok=True)
    for item in list(target.iterdir()):
        if item.name == ".venv":
            continue
        remove_path(item)


def copy_application(source: Path, target: Path) -> None:
    """Copy a fresh runtime snapshot without repository metadata."""
    clean_runtime(target)
    for item in source.iterdir():
        if item.name in EXCLUDED_NAMES:
            continue
        destination = target / item.name
        if item.is_dir():
            shutil.copytree(
                item,
                destination,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(*EXCLUDED_NAMES),
            )
        else:
            shutil.copy2(item, destination)


def create_environment(target: Path) -> Path:
    venv = target / ".venv"
    if not venv.exists():
        subprocess.check_call([sys.executable, "-m", "venv", str(venv)])
    if platform.system() == "Windows":
        python = venv / "Scripts" / "python.exe"
    else:
        python = venv / "bin" / "python"
    if not python.exists():
        # A damaged/incomplete environment is safer to rebuild than repair.
        remove_path(venv)
        subprocess.check_call([sys.executable, "-m", "venv", str(venv)])
        python = (venv / "Scripts" / "python.exe") if platform.system() == "Windows" else (venv / "bin" / "python")
    subprocess.check_call([str(python), "-m", "pip", "install", "-r", str(target / "requirements.txt")])
    return python


def mac_launcher_text() -> str:
    return '''#!/bin/bash
set -e
APP="$HOME/Applications/PMES-USB"
PY="$APP/.venv/bin/python"
if [ ! -x "$PY" ]; then
  osascript -e 'display alert "Engineering System not installed" message "Run install_local.py once on this Mac before using this launcher."'
  exit 1
fi
cd "$APP"
exec "$PY" launch_local.py
'''


def windows_launcher_text() -> str:
    return r'''@echo off
setlocal
set "APP=%LOCALAPPDATA%\PMES-USB"
set "PY=%APP%\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo Engineering System is not installed on this computer.
  echo Run install_local.py once on this Windows computer first.
  pause
  exit /b 1
)
cd /d "%APP%"
start "PMES USB" "%PY%" launch_local.py
exit /b 0
'''


def write_launchers(root: Path) -> None:
    mac = root / MAC_LAUNCHER
    win = root / WINDOWS_LAUNCHER
    mac.write_text(mac_launcher_text(), encoding="utf-8", newline="\n")
    win.write_text(windows_launcher_text(), encoding="utf-8", newline="\r\n")
    try:
        mac.chmod(0o755)
    except OSError:
        pass


def write_desktop_launcher() -> Path | None:
    desktop = Path.home() / "Desktop"
    if not desktop.exists():
        return None
    if platform.system() == "Windows":
        target = desktop / DESKTOP_NAME_WINDOWS
        target.write_text(windows_launcher_text(), encoding="utf-8", newline="\r\n")
    else:
        target = desktop / DESKTOP_NAME_MAC
        target.write_text(mac_launcher_text(), encoding="utf-8", newline="\n")
        try:
            target.chmod(0o755)
        except OSError:
            pass
    return target


def main() -> int:
    vaults = find_vaults()
    if len(vaults) != 1:
        if not vaults:
            print("Engineering Vault not found. Connect M-P-ENG-SYS and run this installer again.")
        else:
            print("More than one Engineering Vault is connected. Leave only the intended vault connected.")
        return 2

    source = Path(__file__).resolve().parent
    target = install_root()
    root = vault_root(Path(vaults[0]))

    print(f"Engineering Vault: {vaults[0]}")
    print(f"Updating clean local runtime at: {target}")
    copy_application(source, target)
    create_environment(target)
    write_launchers(root)
    desktop_launcher = write_desktop_launcher()

    # Defensive verification: installed runtime must never contain Git metadata.
    legacy_git = target / ".git"
    if legacy_git.exists():
        remove_path(legacy_git)
    if legacy_git.exists():
        raise RuntimeError("Installed runtime still contains .git metadata; update aborted.")

    print("\nInstallation/update complete.")
    print("Runtime mode: clean local snapshot (no Git metadata)")
    print(f"Mac launcher on drive: {root / MAC_LAUNCHER}")
    print(f"Windows launcher on drive: {root / WINDOWS_LAUNCHER}")
    if desktop_launcher:
        print(f"Desktop launcher: {desktop_launcher}")
    print("Engineering Vault data was not replaced or reset.")
    print("From now on, connect the Engineering Vault and double-click the launcher for this computer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

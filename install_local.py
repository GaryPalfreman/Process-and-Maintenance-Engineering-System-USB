"""One-time installer for the PMES USB edition.

Run this once on each Mac or Windows computer that will use the Engineering Vault.
It installs an independent local application copy, creates a private virtual
environment, installs requirements, and places cross-platform launchers on the
connected Engineering Vault drive.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from usb_storage import find_vaults

APP_FOLDER = "PMES-USB"
MAC_LAUNCHER = "START ENGINEERING SYSTEM - MAC.command"
WINDOWS_LAUNCHER = "START ENGINEERING SYSTEM - WINDOWS.cmd"


def install_root() -> Path:
    if platform.system() == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / APP_FOLDER
    return Path.home() / "Applications" / APP_FOLDER


def vault_root(vault: Path) -> Path:
    return vault.parent if vault.name == "ENGINEERING_SYSTEM" else vault


def copy_application(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    excluded = {".venv", "__pycache__", ".DS_Store"}
    for item in source.iterdir():
        if item.name in excluded:
            continue
        destination = target / item.name
        if item.is_dir():
            shutil.copytree(item, destination, dirs_exist_ok=True)
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
    subprocess.check_call([str(python), "-m", "pip", "install", "--upgrade", "pip"])
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
    print(f"Installing local application to: {target}")
    copy_application(source, target)
    create_environment(target)
    write_launchers(root)

    print("\nInstallation complete.")
    print(f"Mac launcher: {root / MAC_LAUNCHER}")
    print(f"Windows launcher: {root / WINDOWS_LAUNCHER}")
    print("From now on, plug in the drive and double-click the launcher for this computer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

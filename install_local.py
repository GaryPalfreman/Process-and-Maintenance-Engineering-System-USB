"""Installer/updater for the PMES USB edition.

Run this on each macOS, Windows or Linux computer that will use the Engineering
Vault. The installed application is a clean runtime snapshot, NOT a Git
repository. The external Engineering Vault and its data are never modified by
application updates except for refreshing the clickable launcher files on the
drive.

This installer intentionally uses only Python's standard library until the
local virtual environment has been created and requirements.txt has been
installed. This allows it to run on a completely fresh Python installation.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import stat
import subprocess
import sys
from pathlib import Path

APP_FOLDER = "PMES-USB"
VAULT_FOLDER = "ENGINEERING_SYSTEM"
MARKER_FILE = "vault_identity.json"

MAC_LAUNCHER = "START ENGINEERING SYSTEM - MAC.command"
WINDOWS_LAUNCHER = "START ENGINEERING SYSTEM - WINDOWS.cmd"
LINUX_LAUNCHER = "START ENGINEERING SYSTEM - LINUX.sh"
MAC_IPAD_LAUNCHER = "START ENGINEERING SYSTEM - IPAD MODE - MAC.command"
WINDOWS_IPAD_LAUNCHER = "START ENGINEERING SYSTEM - IPAD MODE - WINDOWS.cmd"
LINUX_IPAD_LAUNCHER = "START ENGINEERING SYSTEM - IPAD MODE - LINUX.sh"
DESKTOP_NAME_MAC = "Process and Maintenance Engineering System.command"
DESKTOP_NAME_WINDOWS = "Process and Maintenance Engineering System.cmd"
DESKTOP_NAME_LINUX = "Process and Maintenance Engineering System.desktop"
DESKTOP_NAME_MAC_IPAD = "PMES - iPad Mode.command"
DESKTOP_NAME_WINDOWS_IPAD = "PMES - iPad Mode.cmd"
DESKTOP_NAME_LINUX_IPAD = "PMES - iPad Mode.desktop"

EXCLUDED_NAMES = {
    ".git", ".github", ".venv", "__pycache__", ".DS_Store",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
}


def removable_roots() -> list[Path]:
    """Find removable-drive roots without importing application dependencies."""
    roots: list[Path] = []
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


def vault_path(root: Path) -> Path:
    p = Path(root)
    return p if p.name == VAULT_FOLDER else p / VAULT_FOLDER


def valid_vault(path: Path) -> bool:
    marker = path / MARKER_FILE
    if not marker.exists():
        return False
    try:
        identity = json.loads(marker.read_text(encoding="utf-8"))
    except Exception:
        return False
    return identity.get("schema") == "pmes-usb-vault" and bool(identity.get("vault_id"))


def find_vaults() -> list[Path]:
    found: list[Path] = []
    for root in removable_roots():
        candidate = vault_path(root)
        if valid_vault(candidate):
            found.append(candidate)
    return found


def install_root() -> Path:
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / APP_FOLDER
    if system == "Linux":
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        return base / APP_FOLDER
    return Path.home() / "Applications" / APP_FOLDER


def vault_root(vault: Path) -> Path:
    return vault.parent if vault.name == VAULT_FOLDER else vault


def _make_writable(path: str) -> None:
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    except OSError:
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass


def _rmtree_onerror(func, path, exc_info):
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
    target.mkdir(parents=True, exist_ok=True)
    for item in list(target.iterdir()):
        if item.name == ".venv":
            continue
        remove_path(item)


def copy_application(source: Path, target: Path) -> None:
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
        print("Creating local Python virtual environment...")
        subprocess.check_call([sys.executable, "-m", "venv", str(venv)])
    if platform.system() == "Windows":
        python = venv / "Scripts" / "python.exe"
    else:
        python = venv / "bin" / "python"
    if not python.exists():
        remove_path(venv)
        subprocess.check_call([sys.executable, "-m", "venv", str(venv)])
        python = (venv / "Scripts" / "python.exe") if platform.system() == "Windows" else (venv / "bin" / "python")
    print("Installing/updating PMES application dependencies...")
    subprocess.check_call([str(python), "-m", "pip", "install", "--upgrade", "pip"])
    subprocess.check_call([str(python), "-m", "pip", "install", "-r", str(target / "requirements.txt")])
    return python


def mac_launcher_text(network: bool = False) -> str:
    mode = " --network" if network else ""
    return f'''#!/bin/bash
set -e
APP="$HOME/Applications/PMES-USB"
PY="$APP/.venv/bin/python"
if [ ! -x "$PY" ]; then
  osascript -e 'display alert "Engineering System not installed" message "Run install_local.py once on this Mac before using this launcher."'
  exit 1
fi
cd "$APP"
exec "$PY" launch_local.py{mode}
'''


def windows_launcher_text(network: bool = False) -> str:
    mode = " --network" if network else ""
    return rf'''@echo off
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
start "PMES USB" "%PY%" launch_local.py{mode}
exit /b 0
'''


def linux_launcher_text(network: bool = False) -> str:
    mode = " --network" if network else ""
    return f'''#!/bin/sh
set -eu
APP="${{XDG_DATA_HOME:-$HOME/.local/share}}/PMES-USB"
PY="$APP/.venv/bin/python"
if [ ! -x "$PY" ]; then
  printf '%s\n' 'Engineering System is not installed on this Linux computer.'
  printf '%s\n' 'Run install_local.py once on this computer first.'
  if command -v zenity >/dev/null 2>&1; then
    zenity --error --title='Engineering System not installed' --text='Run install_local.py once on this Linux computer before using this launcher.' || true
  fi
  exit 1
fi
cd "$APP"
exec "$PY" launch_local.py{mode}
'''


def write_launchers(root: Path) -> None:
    launchers = {
        root / MAC_LAUNCHER: (mac_launcher_text(), "\n"),
        root / WINDOWS_LAUNCHER: (windows_launcher_text(), "\r\n"),
        root / LINUX_LAUNCHER: (linux_launcher_text(), "\n"),
        root / MAC_IPAD_LAUNCHER: (mac_launcher_text(True), "\n"),
        root / WINDOWS_IPAD_LAUNCHER: (windows_launcher_text(True), "\r\n"),
        root / LINUX_IPAD_LAUNCHER: (linux_launcher_text(True), "\n"),
    }
    for path, (text, newline) in launchers.items():
        path.write_text(text, encoding="utf-8", newline=newline)
    for path in (root / MAC_LAUNCHER, root / LINUX_LAUNCHER, root / MAC_IPAD_LAUNCHER, root / LINUX_IPAD_LAUNCHER):
        try:
            path.chmod(0o755)
        except OSError:
            pass


def linux_desktop_text(target: Path, network: bool = False) -> str:
    python = target / ".venv" / "bin" / "python"
    launcher = target / "launch_local.py"
    mode = " --network" if network else ""
    name = "Process and Maintenance Engineering System - iPad Mode" if network else "Process and Maintenance Engineering System"
    return f'''[Desktop Entry]
Type=Application
Version=1.0
Name={name}
Comment=Open the PMES USB Engineering Vault
Exec={python} {launcher}{mode}
Icon=drive-harddisk
Terminal=false
Categories=Office;Utility;
StartupNotify=true
'''


def write_desktop_launcher() -> list[Path]:
    desktop = Path.home() / "Desktop"
    if not desktop.exists():
        return []
    system = platform.system()
    created: list[Path] = []
    if system == "Windows":
        normal = desktop / DESKTOP_NAME_WINDOWS
        network = desktop / DESKTOP_NAME_WINDOWS_IPAD
        normal.write_text(windows_launcher_text(), encoding="utf-8", newline="\r\n")
        network.write_text(windows_launcher_text(True), encoding="utf-8", newline="\r\n")
        created.extend([normal, network])
    elif system == "Linux":
        normal = desktop / DESKTOP_NAME_LINUX
        network = desktop / DESKTOP_NAME_LINUX_IPAD
        normal.write_text(linux_desktop_text(install_root()), encoding="utf-8", newline="\n")
        network.write_text(linux_desktop_text(install_root(), True), encoding="utf-8", newline="\n")
        for target in (normal, network):
            try:
                target.chmod(0o755)
            except OSError:
                pass
        created.extend([normal, network])
    else:
        normal = desktop / DESKTOP_NAME_MAC
        network = desktop / DESKTOP_NAME_MAC_IPAD
        normal.write_text(mac_launcher_text(), encoding="utf-8", newline="\n")
        network.write_text(mac_launcher_text(True), encoding="utf-8", newline="\n")
        for target in (normal, network):
            try:
                target.chmod(0o755)
            except OSError:
                pass
        created.extend([normal, network])
    return created


def main() -> int:
    print("Process and Maintenance Engineering System USB installer")
    print(f"Python: {sys.executable}")
    print(f"Operating system: {platform.system()}")
    print("Looking for Engineering Vault...")

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
    desktop_launchers = write_desktop_launcher()

    legacy_git = target / ".git"
    if legacy_git.exists():
        remove_path(legacy_git)
    if legacy_git.exists():
        raise RuntimeError("Installed runtime still contains .git metadata; update aborted.")

    print("\nInstallation/update complete.")
    print("Runtime mode: clean local snapshot (no Git metadata)")
    print(f"Mac launcher on drive: {root / MAC_LAUNCHER}")
    print(f"Windows launcher on drive: {root / WINDOWS_LAUNCHER}")
    print(f"Linux launcher on drive: {root / LINUX_LAUNCHER}")
    print(f"Mac iPad-mode launcher on drive: {root / MAC_IPAD_LAUNCHER}")
    print(f"Windows iPad-mode launcher on drive: {root / WINDOWS_IPAD_LAUNCHER}")
    print(f"Linux iPad-mode launcher on drive: {root / LINUX_IPAD_LAUNCHER}")
    for desktop_launcher in desktop_launchers:
        print(f"Desktop launcher: {desktop_launcher}")
    print("Engineering Vault data was not replaced or reset.")
    print("Use the iPad-mode launcher only on a trusted local network.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

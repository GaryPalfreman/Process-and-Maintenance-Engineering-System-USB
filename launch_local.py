"""Cross-platform launcher for the local USB/HDD Engineering System."""
import os
import subprocess
import sys
from pathlib import Path

from usb_storage import find_vaults, vault_status


def main():
    vaults = find_vaults()
    if not vaults:
        print("Engineering Vault not found.")
        print("Connect the M-P-ENG-SYS drive, then run this launcher again.")
        return 2
    if len(vaults) > 1:
        print("More than one Engineering Vault is connected.")
        print("Disconnect the extra Engineering Vault and try again.")
        return 3

    vault = Path(vaults[0])
    info = vault_status(vault)
    print(f"Engineering Vault: {info['label']}")
    print(f"Vault path: {info['path']}")
    print("Starting Process and Maintenance Engineering System USB...")

    command = [sys.executable, "-m", "streamlit", "run", "app.py"]
    try:
        return subprocess.call(command, cwd=Path(__file__).resolve().parent, env=os.environ.copy())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

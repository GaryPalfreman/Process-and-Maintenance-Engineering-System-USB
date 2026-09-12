"""Cross-platform launcher for the local USB/HDD Engineering System."""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from usb_storage import find_vaults, vault_status


def local_network_ip() -> str:
    """Best-effort LAN address discovery for iPad/local-network access."""
    candidates: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = info[4][0]
            if address not in candidates:
                candidates.append(address)
    except OSError:
        pass

    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        address = probe.getsockname()[0]
        probe.close()
        if address not in candidates:
            candidates.insert(0, address)
    except OSError:
        pass

    for address in candidates:
        if not address.startswith("127.") and not address.startswith("169.254."):
            return address
    return "127.0.0.1"


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--network", action="store_true")
    args, _ = parser.parse_known_args()

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

    env = os.environ.copy()
    app_dir = Path(__file__).resolve().parent

    if args.network:
        lan_ip = local_network_ip()
        if lan_ip == "127.0.0.1":
            print("A usable local-network address could not be detected.")
            print("Connect this computer to the same Wi-Fi/LAN as the iPad and try again.")
            return 4

        port = 8501
        lan_url = f"http://{lan_ip}:{port}"
        env["PMES_NETWORK_MODE"] = "1"
        env["PMES_LAN_IP"] = lan_ip
        env["PMES_LAN_URL"] = lan_url
        print("Starting Process and Maintenance Engineering System USB in iPad / Local Network Mode...")
        print(f"iPad address: {lan_url}")
        print("Keep the host computer, Engineering Vault and local network connected while using the iPad.")

        command = [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "app.py",
            "--server.address",
            "0.0.0.0",
            "--server.port",
            str(port),
            "--server.headless",
            "true",
        ]
        try:
            process = subprocess.Popen(command, cwd=app_dir, env=env)
            time.sleep(2.0)
            webbrowser.open(lan_url)
            return process.wait()
        except KeyboardInterrupt:
            try:
                process.terminate()
            except Exception:
                pass
            return 0

    print("Starting Process and Maintenance Engineering System USB...")
    command = [sys.executable, "-m", "streamlit", "run", "app.py"]
    try:
        return subprocess.call(command, cwd=app_dir, env=env)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

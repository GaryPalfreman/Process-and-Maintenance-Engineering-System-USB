# Process and Maintenance Engineering System — USB Edition

This repository is the independent local USB/HDD edition of the Process and Maintenance Engineering System.

It started from the web-edition baseline so the engineering data model, hidden UUID relationships, modules, Contacts & Suppliers, Production Readiness, Engineering Operations and Engineering Control Centre remain compatible with the web edition. The USB and web repositories are maintained separately.

## Current status

USB edition version: **0.3 — One-Click Launcher test build**

The connected Engineering Vault is the live data source. The local application runs from the computer while engineering data, backups and engineering documents remain on the external HDD/SSD.

The current test vault is the exFAT drive `M-P-ENG-SYS`, initialised with an `ENGINEERING_SYSTEM` vault. The application finds it by `vault_identity.json`, not by the volume name, macOS mount path or Windows drive letter.

## Engineering Vault structure

```text
M-P-ENG-SYS/
├── START ENGINEERING SYSTEM - MAC.command
├── START ENGINEERING SYSTEM - WINDOWS.cmd
└── ENGINEERING_SYSTEM/
    ├── vault_identity.json
    ├── engineering_data.json
    ├── Backups/
    │   └── YYYY-MM/
    └── Documents/
```

`engineering_data.json` remains compatible with the web edition schema and hidden UUID relationship model.

## One-time computer setup

Run `install_local.py` once on every Mac or Windows computer that will use the Engineering Vault.

The installer:

- confirms that exactly one Engineering Vault is connected
- installs the local application to a predictable computer-local folder
- creates a private Python virtual environment
- installs the required Python packages
- places both Mac and Windows launchers at the root of the Engineering Vault drive
- creates a launcher on the current computer desktop

Local application locations:

```text
macOS:   ~/Applications/PMES-USB/
Windows: %LOCALAPPDATA%\PMES-USB\
```

After setup, normal operation does not require Bash, Terminal, Command Prompt or PowerShell commands.

## Normal use after setup

Connect `M-P-ENG-SYS`, then either:

- double-click `START ENGINEERING SYSTEM - MAC.command` on macOS
- double-click `START ENGINEERING SYSTEM - WINDOWS.cmd` on Windows
- or use the desktop launcher created during setup

The launcher checks that the Engineering Vault is present and then starts the local Streamlit application. Windows drive-letter changes do not matter.

Modern macOS and Windows versions intentionally restrict classic removable-media autorun. The supported v0.3 workflow is therefore one-click launch rather than silently executing software as soon as the drive is attached. An optional authorised-computer background watcher can be considered later if automatic launch-on-connect is still desirable.

## Storage and persistence

`usb_storage.py` provides:

- cross-platform drive discovery
- Engineering Vault identity validation
- drive-letter-independent vault detection
- direct JSON loading and saving
- flushed atomic replacement of the live JSON
- timestamped ZIP backups
- automatic backup-due checking
- drive free-space/status reporting
- filtering of common macOS internal and Time Machine mounts

`usb_runtime.py` provides:

- one-vault-required startup behaviour
- shared store initialisation across Streamlit pages
- explicit durable persistence to the Engineering Vault
- visible Engineering Vault status
- manual Save and Create Vault Backup controls

`launch_local.py` is the common cross-platform application launcher used by the clickable Mac and Windows files.

## First installation on the current Mac

Because the repository is already cloned locally, update it and run the installer once:

```bash
cd ~/Downloads/Process-and-Maintenance-Engineering-System-USB
git pull
python3 install_local.py
```

After that completes, use the clickable launcher instead of Terminal commands for normal operation.

## First installation on a Windows computer

Clone or copy the USB repository once, connect `M-P-ENG-SYS`, then run:

```text
py install_local.py
```

After installation, use the Windows launcher on the drive or desktop.

## Backups and safe removal

The live structured dataset is `engineering_data.json`. Saves use a temporary file and atomic replacement to reduce corruption risk. ZIP backups are stored under `Backups/YYYY-MM/` and a manual backup control is available in the application.

Do not disconnect the external drive while a save or backup is in progress. Close the Engineering System and eject the drive normally before unplugging it.

## Security note

`vault_identity.json` identifies the intended physical Engineering Vault but is not encryption or strong authentication. Because the drive is exFAT for native macOS/Windows compatibility, treat the current data as unencrypted unless an application-level encryption layer is added later.

## Relationship to the web edition

Web repository:
`GaryPalfreman/Process-and-Maintenance-Engineering-System-web`

USB repository:
`GaryPalfreman/Process-and-Maintenance-Engineering-System-USB`

There is no automatic synchronisation between them. Changes are transferred only when explicitly requested.

## Validation

`.github/workflows/usb-ci.yml` performs Python syntax validation across the main application, support modules and Streamlit pages on USB-edition Python changes.

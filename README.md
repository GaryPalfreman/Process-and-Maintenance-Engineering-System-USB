# Process and Maintenance Engineering System — USB Edition

This repository is the independent local USB/HDD edition of the Process and Maintenance Engineering System. It is maintained separately from the web edition.

## Current status

USB edition version: **0.7B-prep — Cross-platform portability preparation**

Platform status:

- **macOS:** physically validated on the real `M-P-ENG-SYS` Engineering Vault
- **Windows:** prepared in code, physical validation pending
- **Linux:** prepared in code and checked by Linux CI, physical validation pending

The external exFAT drive `M-P-ENG-SYS` remains the authoritative Engineering Vault. The application is installed locally on each computer while the encrypted engineering dataset, encrypted backups, vault identity and Documents folder remain on the external drive.

## Engineering Vault structure

```text
M-P-ENG-SYS/
├── START ENGINEERING SYSTEM - MAC.command
├── START ENGINEERING SYSTEM - WINDOWS.cmd
├── START ENGINEERING SYSTEM - LINUX.sh
└── ENGINEERING_SYSTEM/
    ├── vault_identity.json
    ├── vault_security.json
    ├── vault_encryption.json
    ├── vault_recovery.json        # after recovery key is configured
    ├── engineering_data.pmes
    ├── Backups/
    │   └── YYYY-MM/
    │       └── *.pmesbak
    └── Documents/
```

The vault is found by its `vault_identity.json` UUID rather than a fixed macOS path, Windows drive letter or Linux mount path.

## One-time setup on each computer

Connect `M-P-ENG-SYS`, obtain a copy of this repository, then run:

```text
python3 install_local.py
```

On Windows, `py install_local.py` may be used instead.

The installer creates a clean local runtime, a private Python virtual environment, installs requirements, refreshes all three launchers on the Engineering Vault, and creates a desktop launcher when the operating system exposes a Desktop folder.

Local runtime locations:

```text
macOS:   ~/Applications/PMES-USB/
Windows: %LOCALAPPDATA%\PMES-USB\
Linux:   ${XDG_DATA_HOME:-~/.local/share}/PMES-USB/
```

## Normal one-click use

After one-time setup, connect the Engineering Vault and use the launcher for the current operating system:

```text
macOS   → START ENGINEERING SYSTEM - MAC.command
Windows → START ENGINEERING SYSTEM - WINDOWS.cmd
Linux   → START ENGINEERING SYSTEM - LINUX.sh
```

The local launcher checks for exactly one valid Engineering Vault before starting Streamlit.

## Linux preparation

Linux vault discovery currently checks normal removable-media locations including:

```text
/media/<user>/
/run/media/<user>/
/mnt/
```

The Linux launcher uses the local runtime under `~/.local/share/PMES-USB` unless `XDG_DATA_HOME` is configured. The installer can also create a `Process and Maintenance Engineering System.desktop` shortcut.

Typical Linux prerequisites are:

- Python 3 with `venv` support
- permission to read/write the exFAT Engineering Vault
- a browser
- normal desktop removable-drive mounting

Distribution-specific packages may be required for Python venv or exFAT support. Linux is not considered operationally validated until the real `M-P-ENG-SYS` drive is tested on an actual Linux computer.

## Security and encryption

The current USB edition includes:

- physical Engineering Vault requirement
- PIN/password lock
- AES-256-GCM authenticated encryption for the structured live dataset
- encrypted `.pmesbak` backups
- SHA-256 backup checksum sidecars
- recovery-key support
- wrapped data-key model for safe PIN re-keying
- emergency recovery-key unlock path
- startup integrity verification
- automatic encrypted session-open backup
- encrypted session-close backup
- backup retention controls
- live drive-disconnect monitoring and blocked writes

The `Documents/` folder remains normal cross-platform files and is not application-encrypted in the current release.

## Recovery & Integrity

The **Recovery & Integrity** page verifies:

- live encrypted data readability
- valid and invalid encrypted backup counts
- recovery readiness
- latest valid backup
- backup checksum/integrity status

A separate recovery key can be generated and stored away from `M-P-ENG-SYS`. The recovery key is intended for emergency access if the normal PIN is unavailable.

## Backup and safe removal

The system creates encrypted backups under `Backups/YYYY-MM/`. Restores validate the selected backup first and create a pre-restore safety backup.

Use **Save, Backup & Safely Eject** before disconnecting the Engineering Vault. macOS safe eject is physically validated. Windows and Linux eject behaviour remains subject to physical validation on those operating systems.

## Updating an installed computer

Repository changes do not directly alter the installed runtime or the Engineering Vault data. After pulling a new build, run the installer again:

```bash
cd ~/Downloads/Process-and-Maintenance-Engineering-System-USB
git pull
python3 install_local.py
```

The installer replaces the local runtime snapshot while preserving the local `.venv` where appropriate and does not replace or reset Engineering Vault data.

## Relationship to the web edition

Web repository:
`GaryPalfreman/Process-and-Maintenance-Engineering-System-web`

USB repository:
`GaryPalfreman/Process-and-Maintenance-Engineering-System-USB`

There is no automatic synchronisation between them. Changes move between repositories only when explicitly requested.

## Validation

`.github/workflows/usb-ci.yml` runs Python syntax validation on Ubuntu and also checks the Linux launcher shell syntax and Linux installer-preparation markers.

A successful Linux CI run means the Linux preparation code is syntactically sound. It does **not** replace physical validation with the actual exFAT Engineering Vault, desktop environment, mount behaviour and safe-eject workflow.

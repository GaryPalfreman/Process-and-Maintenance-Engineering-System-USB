# Process and Maintenance Engineering System — USB Edition

This repository is the independent local USB/HDD edition of the Process and Maintenance Engineering System.

It started from the web-edition baseline so the engineering data model, hidden UUID relationships, modules, Contacts & Suppliers, Production Readiness, Engineering Operations and Engineering Control Centre remain compatible with the web edition. From this point onward the USB repository and web repository are maintained separately.

## Purpose

The USB edition is intended to become the operational local version while the web repository remains available for development, testing and layout changes.

The local design is:

- Streamlit runs on the local Mac or Windows computer
- the live engineering dataset is stored on an external USB HDD/SSD
- the same JSON schema and UUID relationships are retained
- backups and engineering documents live on the external drive
- the drive is identified by its Engineering Vault marker rather than a fixed path or Windows drive letter
- web and USB datasets remain import/export compatible

## Current status

USB edition version: **0.2 — Vault-wired local test build**

The main application and all four advanced Streamlit pages now initialise through `usb_runtime.py` rather than creating independent in-memory stores. The connected Engineering Vault is therefore the live data source.

`usb_storage.py` provides:

- cross-platform external-drive discovery for macOS, Windows and Linux
- validation of `vault_identity.json`
- drive-letter-independent Engineering Vault detection
- direct JSON loading from the external drive
- flushed atomic replacement of the live JSON file
- timestamped ZIP backups
- automatic backup-due checking
- drive free-space/status reporting
- filtering of common macOS internal/Time Machine mounts

`usb_runtime.py` provides:

- one-vault-required startup behaviour
- shared store initialisation across every Streamlit page
- automatic persistence when the engineering store is mutated
- a visible Engineering Vault Connected status
- free-space display
- manual Save to Engineering Vault control
- manual Create Vault Backup control

`launch_local.py` is the cross-platform launcher. It locates the Engineering Vault first and then starts Streamlit locally. It does not rely on `/Volumes/...` or a specific Windows drive letter.

## Engineering Vault structure

```text
ENGINEERING_SYSTEM/
├── vault_identity.json
├── engineering_data.json
├── Backups/
│   └── YYYY-MM/
└── Documents/
```

The Documents area is intended for manuals, drawings, supplier documents, service reports, photos, calibration records and other engineering references that should live beside the structured system data.

## Current test vault

The first physical test vault has been initialised on the external drive named:

`M-P-ENG-SYS`

On macOS it is currently mounted under `/Volumes/M-P-ENG-SYS`. On Windows the same drive can receive any available drive letter; the application identifies it using the vault marker instead.

The external drive is formatted as **exFAT** so it can be read and written natively by both macOS and Windows.

## Running locally on macOS

From the cloned USB repository:

```bash
cd ~/Downloads/Process-and-Maintenance-Engineering-System-USB
git pull
python3 -m pip install -r requirements.txt
python3 launch_local.py
```

Keep `M-P-ENG-SYS` connected before launching.

## Running locally on Windows

Clone or copy this USB repository to the Windows computer, open Command Prompt or PowerShell in the repository folder, then run:

```text
py -m pip install -r requirements.txt
py launch_local.py
```

The launcher searches available drives for the Engineering Vault marker, so no fixed `D:`, `E:` or `F:` assignment is required.

## Backups and safe removal

The live structured data is `engineering_data.json`. Saves are written through a temporary file and then atomically replaced to reduce corruption risk.

Automatic ZIP backups are created periodically under `Backups/YYYY-MM/`. A manual backup button is also available in the application sidebar.

Do not physically disconnect the external drive while a save or backup is in progress. Close the local Engineering System and eject the drive normally before unplugging it.

## Security note

`vault_identity.json` is a physical-vault identity marker, not encryption or strong authentication. Because this drive must remain usable on both macOS and Windows, the current engineering dataset should be treated as unencrypted unless a separate cross-platform encryption layer is added.

A later security phase can add application-level encryption and/or stronger authorised-computer/authorised-vault pairing without changing the engineering JSON schema.

## Relationship to the web edition

Web repository:
`GaryPalfreman/Process-and-Maintenance-Engineering-System-web`

USB repository:
`GaryPalfreman/Process-and-Maintenance-Engineering-System-USB`

There is no automatic synchronisation between these repositories. Changes are transferred only when explicitly requested.

## Data compatibility

Schema: `process-maintenance-engineering-system`

Hidden UUIDs remain the relational keys. Human-facing business IDs, legacy IDs and aliases remain editable metadata. JSON from the web edition can therefore be migrated into the USB edition without redesigning record relationships.

## Validation

`.github/workflows/usb-ci.yml` performs Python syntax validation across the main application, support modules and Streamlit pages on USB-edition Python changes.

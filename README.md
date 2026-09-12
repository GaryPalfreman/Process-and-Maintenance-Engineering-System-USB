# Process and Maintenance Engineering System — USB Edition

This repository is the local USB/HDD edition of the Process and Maintenance Engineering System.

It was bootstrapped from the current web version so the engineering data model, hidden UUID relationships, modules, Contacts & Suppliers system, Production Readiness workspace, Engineering Operations and Engineering Control Centre remain compatible with the web edition.

## Purpose

The USB edition is intended to become the operational local version while the web repository remains available for development, testing and layout changes.

The design target is:

- run Streamlit locally on the computer
- keep the live engineering dataset on an external USB HDD/SSD
- preserve the same JSON schema as the web edition
- store backups and engineering documents on the external drive
- allow the external drive to act as the physical data vault
- keep web and USB datasets import/export compatible

## Current repository status

The complete web application baseline has been copied into this repository.

`usb_storage.py` adds the external-drive storage engine. It currently provides:

- detection of external mount locations on macOS, Windows and Linux
- creation of an `ENGINEERING_SYSTEM` vault folder
- a unique vault identity
- direct JSON load/save helpers
- atomic replacement of the live engineering JSON
- timestamped ZIP backups
- backup-due checking
- external-drive free-space/status reporting

The storage engine uses the existing `blank_store`, `load_store`, `store_bytes` and `backup_zip` functions, so the USB data remains compatible with the web system.

## Intended external-drive structure

```text
ENGINEERING_SYSTEM/
├── vault_identity.json
├── engineering_data.json
├── Backups/
│   └── YYYY-MM/
└── Documents/
```

The Documents area is intended for manuals, drawings, supplier documents, service reports, photos, calibration records and other engineering references that should live beside the structured system data.

## Security note

The vault identity is an application-level physical-drive marker, not encryption. For confidential company engineering data, the external HDD/SSD should also use operating-system-level encryption such as encrypted APFS on macOS, BitLocker on Windows or LUKS on Linux.

A stronger authorised-drive/pairing layer can be added after the local storage workflow has been proven on the actual external drive.

## Running locally

Create a Python virtual environment, install the requirements and run:

```bash
streamlit run app.py
```

The main engineering application is unchanged from the web baseline at this stage, ensuring that the working web version remains a known-good reference while the local storage integration is developed independently.

## Relationship to the web edition

Web repository:
`GaryPalfreman/Process-and-Maintenance-Engineering-System-web`

USB repository:
`GaryPalfreman/Process-and-Maintenance-Engineering-System-USB`

The web edition should remain the development/testing version. The USB edition should become the local operational version once the external-drive workflow has been validated.

## Data compatibility

Schema: `process-maintenance-engineering-system`

Hidden UUIDs remain the relational keys. Human-facing business IDs, legacy IDs and aliases remain editable metadata. JSON exported from the web edition can therefore be migrated into the USB edition without redesigning record relationships.

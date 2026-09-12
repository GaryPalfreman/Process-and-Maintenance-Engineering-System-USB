"""Shared local USB/HDD runtime for the Streamlit edition.

The Engineering Vault is the durable store. The in-memory data remains ordinary
Python dict/list data for full compatibility with the web edition and existing
serializer. This runtime adds vault presence checks, write blocking, backup /
restore controls and safe-eject handling.
"""
from pathlib import Path
import streamlit as st

from usb_storage import (
    find_vaults, load_from_vault, save_to_vault, create_backup, backup_due,
    vault_status, vault_is_connected, list_backups, validate_backup,
    restore_backup, safe_eject,
)


def require_vault():
    vaults = find_vaults()
    if not vaults:
        st.error("Engineering Vault not connected. Connect the M-P-ENG-SYS drive and refresh this page.")
        st.stop()
    if len(vaults) > 1:
        st.error("More than one Engineering Vault is connected. Disconnect the extra vault and refresh.")
        st.stop()

    vault = Path(vaults[0])
    vault_key = str(vault.resolve())
    if st.session_state.get("usb_vault_path") != vault_key or "pm_store" not in st.session_state:
        try:
            st.session_state.pm_store = load_from_vault(vault)
            st.session_state.usb_vault_path = vault_key
            st.session_state.usb_vault_missing = False
        except Exception as exc:
            st.error(f"Engineering Vault could not be loaded: {exc}")
            st.stop()
    return vault, st.session_state.pm_store


def persist(store=None, backup=True):
    vaults = find_vaults()
    if len(vaults) != 1:
        st.session_state.usb_vault_missing = True
        st.error("Engineering Vault is no longer available. Write blocked. Reconnect it before continuing.")
        st.stop()
    vault = Path(vaults[0])
    if not vault_is_connected(vault):
        st.session_state.usb_vault_missing = True
        st.error("Engineering Vault connection was lost. Write blocked.")
        st.stop()
    data = store if store is not None else st.session_state.pm_store
    save_to_vault(vault, data)
    if backup and backup_due(vault):
        create_backup(vault, data, "auto")
    st.session_state.usb_vault_missing = False
    return vault


@st.fragment(run_every="2s")
def _vault_monitor(vault):
    if vault_is_connected(vault):
        st.sidebar.caption("Live vault monitor: connected")
        st.session_state.usb_vault_missing = False
    else:
        st.session_state.usb_vault_missing = True
        st.sidebar.error("Engineering Vault disconnected — writes are blocked")


def _backup_recovery_controls(vault):
    with st.sidebar.expander("Backup & Recovery", expanded=False):
        backups = list_backups(vault, limit=20)
        if not backups:
            st.caption("No vault backups yet.")
            return
        labels = [f"{p.parent.name}/{p.name}" for p in backups]
        selected_label = st.selectbox("Backup", labels, key="usb_backup_select")
        selected = backups[labels.index(selected_label)]
        check = validate_backup(selected)
        if check.get("valid"):
            checksum = check.get("checksum_ok")
            status = "Validated"
            if checksum is True:
                status += " + checksum OK"
            st.success(status)
            st.caption(f"Approx. records: {check.get('records', 0)}")
            confirm = st.checkbox("I understand the current live dataset will be replaced", key="usb_restore_confirm")
            if st.button("Restore Selected Backup", disabled=not confirm, use_container_width=True):
                restored, safety = restore_backup(vault, selected)
                st.session_state.pm_store = restored
                st.success(f"Restored. Pre-restore safety backup: {safety.name}")
                st.rerun()
        else:
            st.error(f"Backup failed validation: {check.get('error','Unknown error')}")


def vault_sidebar(vault):
    info = vault_status(vault)
    free_gb = info.get("free_bytes", 0) / (1024 ** 3)
    st.sidebar.success("Engineering Vault Connected")
    st.sidebar.caption(info.get("label", "Engineering Vault"))
    st.sidebar.caption(info.get("path", str(vault)))
    st.sidebar.caption(f"Free space: {free_gb:.1f} GB")
    st.sidebar.caption("Vault persistence: ON")
    _vault_monitor(vault)

    if st.sidebar.button("Save to Engineering Vault", use_container_width=True):
        persist()
        st.sidebar.success("Saved")
    if st.sidebar.button("Create Vault Backup", use_container_width=True):
        target = create_backup(vault, st.session_state.pm_store, "manual")
        st.sidebar.success(f"Backup created: {target.name}")

    _backup_recovery_controls(vault)

    st.sidebar.divider()
    with st.sidebar.expander("End Session / Safe Eject", expanded=False):
        st.caption("Saves the live dataset, creates a safety backup, then asks the operating system to eject the Engineering Vault drive.")
        confirm = st.checkbox("I am ready to end this Engineering Vault session", key="usb_eject_confirm")
        if st.button("Save, Backup & Safely Eject", disabled=not confirm, use_container_width=True):
            persist(backup=False)
            safety = create_backup(vault, st.session_state.pm_store, "session_close")
            ok, message = safe_eject(vault)
            if ok:
                st.session_state.pop("pm_store", None)
                st.session_state.pop("usb_vault_path", None)
                st.session_state.usb_vault_missing = True
                st.success(f"Session saved. Backup: {safety.name}. Vault ejected safely.")
                st.stop()
            else:
                st.error(f"Data and backup were saved, but automatic eject did not complete. Eject the drive manually. Details: {message}")


def initialise_page():
    vault, store = require_vault()
    vault_sidebar(vault)
    return vault, store

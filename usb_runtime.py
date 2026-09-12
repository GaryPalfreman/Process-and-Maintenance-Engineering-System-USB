"""Shared local USB/HDD runtime for the Streamlit edition.

All pages use this module so the engineering store is loaded from and saved to
the connected Engineering Vault rather than being initialised independently.
"""
from pathlib import Path
import streamlit as st

from usb_storage import find_vaults, load_from_vault, save_to_vault, create_backup, backup_due, vault_status


def require_vault():
    """Locate a single Engineering Vault, load its store once, and return both."""
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
            st.session_state.usb_dirty = False
        except Exception as exc:
            st.error(f"Engineering Vault could not be loaded: {exc}")
            st.stop()
    return vault, st.session_state.pm_store


def persist(store=None, backup=True):
    """Atomically save the current store and make a periodic rolling backup."""
    vaults = find_vaults()
    if len(vaults) != 1:
        st.error("Engineering Vault is no longer available. Reconnect it before continuing.")
        st.stop()
    vault = Path(vaults[0])
    data = store if store is not None else st.session_state.pm_store
    save_to_vault(vault, data)
    if backup and backup_due(vault):
        create_backup(vault, data, "auto")
    st.session_state.usb_dirty = False
    return vault


def mark_dirty():
    st.session_state.usb_dirty = True


def vault_sidebar(vault):
    """Compact vault status and explicit save/backup controls for every page."""
    info = vault_status(vault)
    st.sidebar.success("Engineering Vault Connected")
    st.sidebar.caption(info.get("label", "Engineering Vault"))
    st.sidebar.caption(info.get("path", str(vault)))
    if st.sidebar.button("Save to Engineering Vault", use_container_width=True):
        persist()
        st.sidebar.success("Saved")
    if st.sidebar.button("Create Vault Backup", use_container_width=True):
        target = create_backup(vault, st.session_state.pm_store, "manual")
        st.sidebar.success(f"Backup created: {target.name}")


def initialise_page():
    vault, store = require_vault()
    vault_sidebar(vault)
    return vault, store

"""Shared local USB/HDD runtime for the Streamlit edition."""
from pathlib import Path
import streamlit as st
from usb_storage import (find_vaults, load_from_vault, save_to_vault, create_backup, backup_due, vault_status, vault_is_connected, list_backups, validate_backup, restore_backup, safe_eject, encryption_enabled, encryption_metadata)
from usb_security import status as security_status, verify_pin
from usb_crypto import derive_key


def _cipher():
    return st.session_state.get("usb_cipher")


def current_encryption_key():
    return _cipher()


def _lock():
    st.session_state.usb_security_unlocked = False
    st.session_state.pop("usb_cipher", None)


def _unlock_if_required(vault):
    sec = security_status(vault)
    encrypted = encryption_enabled(vault)
    if encrypted and not sec.get("pin_enabled"):
        st.error("Encrypted Engineering Vault requires its PIN/password security configuration.")
        st.stop()
    if not sec.get("configured") or not sec.get("pin_enabled"):
        return
    if st.session_state.get("usb_security_unlocked") and (not encrypted or _cipher()):
        return
    st.title("Engineering Vault Locked")
    st.caption("The Engineering Vault is connected" + (" and encrypted." if encrypted else ".") + " Enter its access PIN/password to open the system.")
    with st.form("vault_unlock"):
        entered = st.text_input("Vault PIN / password", type="password")
        submit = st.form_submit_button("Unlock Engineering System", type="primary", use_container_width=True)
    if submit:
        if verify_pin(vault, entered):
            try:
                if encrypted:
                    cipher = derive_key(entered, encryption_metadata(vault))
                    load_from_vault(vault, cipher)
                    st.session_state.usb_cipher = cipher
                st.session_state.usb_security_unlocked = True
                st.rerun()
            except Exception:
                _lock()
                st.error("Vault access was verified, but encrypted storage could not be opened. Do not alter the drive.")
        else:
            st.error("Incorrect vault PIN/password.")
    st.stop()


def require_vault():
    vaults = find_vaults()
    if not vaults:
        st.error("Engineering Vault not connected. Connect the M-P-ENG-SYS drive and refresh this page.")
        st.stop()
    if len(vaults) > 1:
        st.error("More than one Engineering Vault is connected. Disconnect the extra vault and refresh.")
        st.stop()
    vault = Path(vaults[0])
    _unlock_if_required(vault)
    vault_key = str(vault.resolve())
    if st.session_state.get("usb_vault_path") != vault_key or "pm_store" not in st.session_state:
        try:
            st.session_state.pm_store = load_from_vault(vault, _cipher())
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
        _lock()
        st.error("Engineering Vault is no longer available. Write blocked. Reconnect it before continuing.")
        st.stop()
    vault = Path(vaults[0])
    if not vault_is_connected(vault):
        st.session_state.usb_vault_missing = True
        _lock()
        st.error("Engineering Vault connection was lost. Write blocked.")
        st.stop()
    data = store if store is not None else st.session_state.pm_store
    save_to_vault(vault, data, _cipher())
    if backup and backup_due(vault):
        create_backup(vault, data, "auto", _cipher())
    st.session_state.usb_vault_missing = False
    return vault


@st.fragment(run_every="2s")
def _vault_monitor(vault):
    if vault_is_connected(vault):
        st.sidebar.caption("Live vault monitor: connected")
        st.session_state.usb_vault_missing = False
    else:
        st.session_state.usb_vault_missing = True
        _lock()
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
        check = validate_backup(selected, _cipher())
        if check.get("valid"):
            text = "Validated" + (" + checksum OK" if check.get("checksum_ok") is True else "") + (" + encrypted" if check.get("encrypted") else "")
            st.success(text)
            st.caption(f"Approx. records: {check.get('records', 0)}")
            confirm = st.checkbox("I understand the current live dataset will be replaced", key="usb_restore_confirm")
            if st.button("Restore Selected Backup", disabled=not confirm, use_container_width=True):
                restored, safety = restore_backup(vault, selected, _cipher())
                st.session_state.pm_store = restored
                st.success(f"Restored. Pre-restore safety backup: {safety.name}")
                st.rerun()
        else:
            st.error(f"Backup failed validation: {check.get('error','Unknown error')}")


def vault_sidebar(vault):
    info = vault_status(vault)
    sec = security_status(vault)
    enc = info.get("encryption", {})
    free_gb = info.get("free_bytes",0)/(1024**3)
    st.sidebar.success("Engineering Vault Connected")
    st.sidebar.caption(info.get("label","Engineering Vault"))
    st.sidebar.caption(info.get("path",str(vault)))
    st.sidebar.caption(f"Free space: {free_gb:.1f} GB")
    st.sidebar.caption("Vault persistence: ON")
    st.sidebar.caption("Physical vault identity: VERIFIED")
    st.sidebar.caption("PIN lock: ON" if sec.get("pin_enabled") else "PIN lock: OFF")
    st.sidebar.caption("At-rest encryption: ON" if enc.get("enabled") else "At-rest encryption: OFF")
    _vault_monitor(vault)
    if sec.get("pin_enabled") and st.sidebar.button("Lock Engineering System", use_container_width=True):
        _lock()
        st.session_state.pop("pm_store", None)
        st.rerun()
    if st.sidebar.button("Save to Engineering Vault", use_container_width=True):
        persist()
        st.sidebar.success("Saved")
    if st.sidebar.button("Create Vault Backup", use_container_width=True):
        target=create_backup(vault,st.session_state.pm_store,"manual",_cipher())
        st.sidebar.success(f"Backup created: {target.name}")
    _backup_recovery_controls(vault)
    st.sidebar.divider()
    with st.sidebar.expander("End Session / Safe Eject", expanded=False):
        st.caption("Saves the live dataset, creates a safety backup, then asks the operating system to eject the Engineering Vault drive.")
        confirm=st.checkbox("I am ready to end this Engineering Vault session",key="usb_eject_confirm")
        if st.button("Save, Backup & Safely Eject",disabled=not confirm,use_container_width=True):
            persist(backup=False)
            safety=create_backup(vault,st.session_state.pm_store,"session_close",_cipher())
            ok,message=safe_eject(vault)
            _lock()
            if ok:
                st.session_state.pop("pm_store",None)
                st.session_state.pop("usb_vault_path",None)
                st.session_state.usb_vault_missing=True
                st.success(f"Session saved. Backup: {safety.name}. Vault ejected safely.")
                st.stop()
            else:
                st.error(f"Data and backup were saved, but automatic eject did not complete. Eject the drive manually. Details: {message}")


def initialise_page():
    vault,store=require_vault()
    vault_sidebar(vault)
    return vault,store

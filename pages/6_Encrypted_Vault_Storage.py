import streamlit as st

from usb_runtime import initialise_page, current_encryption_key
from usb_storage import encryption_status, migrate_to_encrypted, list_backups, validate_backup
from usb_security import status as security_status, verify_pin
from usb_diagnostics import run_persistence_self_test

st.set_page_config(page_title="Encrypted Vault Storage", page_icon="🔐", layout="wide")
vault, store = initialise_page()

st.title("Encrypted Vault Storage")
st.caption("Controls the protected on-disk format for the live engineering dataset and PMES backup archives.")

enc = encryption_status(vault)
sec = security_status(vault)

if enc.get("enabled"):
    st.success("At-rest encryption is enabled for the structured dataset and PMES backup archives.")
    cols = st.columns(4)
    cols[0].metric("Live encrypted data", "PASS" if enc.get("encrypted_data_present") else "MISSING")
    cols[1].metric("Encrypted backups", enc.get("encrypted_backups", 0))
    cols[2].metric("Plaintext live data", "YES" if enc.get("plaintext_data_present") else "NO")
    cols[3].metric("Legacy ZIP backups", enc.get("legacy_plaintext_backups", 0))
    if enc.get("plaintext_data_present") or enc.get("legacy_plaintext_backups"):
        st.error("Residual plaintext PMES data was detected.")
    else:
        st.success("No plaintext structured dataset or legacy PMES ZIP backups detected.")
    st.info("Documents remain normal cross-platform files in v0.6 and are not changed by structured-data encryption.")

    st.subheader("Encrypted persistence verification")
    st.write("Runs the linked Assets → Actions → Maintenance → PM test through the encrypted live-data format, then restores the original dataset.")
    if st.button("Run Encrypted Persistence Test", type="primary", use_container_width=True):
        try:
            with st.spinner("Testing encrypted write/read persistence..."):
                result = run_persistence_self_test(vault, store, current_encryption_key())
            if result.get("passed"):
                st.success("PASS — encrypted write/read persistence and linked UUID relationships verified.")
            else:
                st.error("FAIL — encrypted persistence test found a problem.")
        except Exception as exc:
            st.error(f"Encrypted persistence test could not complete: {exc}")
else:
    if not sec.get("pin_enabled"):
        st.warning("Configure a vault PIN/password first, then return here to enable encrypted storage.")
    else:
        st.write("The migration creates and validates a temporary safety backup, protects the live dataset, converts existing PMES backup archives, verifies the result, and removes the temporary plaintext PMES copies.")
        st.warning("Keep the Engineering Vault connected throughout the migration.")
        with st.form("encrypt_vault"):
            access_value = st.text_input("Re-enter vault PIN / password", type="password")
            confirm = st.checkbox("I understand this changes the PMES on-disk storage format")
            submit = st.form_submit_button("Enable Encrypted Vault Storage", type="primary", use_container_width=True)
        if submit:
            if not confirm:
                st.error("Tick the confirmation box before enabling encrypted storage.")
            elif not verify_pin(vault, access_value):
                st.error("Access value was not accepted. No storage change was made.")
            else:
                try:
                    with st.spinner("Migrating PMES storage..."):
                        result = migrate_to_encrypted(vault, store, access_value)
                    st.session_state.usb_cipher = result["key"]
                    st.success(f"Migration complete. Converted backups: {result['migrated_backups']}")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Migration did not complete: {exc}")

st.divider()
st.subheader("Backup format verification")
rows = []
for backup in list_backups(vault, 20):
    check = validate_backup(backup, current_encryption_key())
    rows.append({
        "Backup": backup.name,
        "Encrypted": "YES" if check.get("encrypted") else "NO",
        "Valid": "PASS" if check.get("valid") else "FAIL",
        "Checksum": "PASS" if check.get("checksum_ok") is True else ("None" if check.get("checksum_ok") is None else "FAIL"),
    })
if rows:
    st.dataframe(rows, use_container_width=True, hide_index=True)
else:
    st.info("No backups found.")

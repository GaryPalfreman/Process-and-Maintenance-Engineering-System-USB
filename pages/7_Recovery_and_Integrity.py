import pandas as pd
import streamlit as st

from usb_runtime import initialise_page, current_encryption_key
from usb_integrity import integrity_report
from usb_storage import list_backups, validate_backup, encryption_metadata
from usb_security import verify_pin
from usb_recovery import recovery_status, create_recovery_key, verify_recovery_key
from usb_rekey import ensure_wrapped_key_mode, rekey_pin, reset_pin_with_recovery

st.set_page_config(page_title="Recovery & Integrity", page_icon="🛡️", layout="wide")
vault, store = initialise_page()

st.title("Recovery & Integrity")
st.caption("v0.7A startup-readiness, encrypted backup health, safe PIN re-keying and emergency recovery.")

report = integrity_report(vault, current_encryption_key())
cols = st.columns(4)
cols[0].metric("Live data", "PASS" if report.get("live_data_ok") else "FAIL")
cols[1].metric("Valid backups", report.get("valid_backups", 0))
cols[2].metric("Invalid backups", report.get("invalid_backups", 0))
cols[3].metric("Recovery ready", "YES" if report.get("recovery_ready") else "NO")

if report.get("recovery_ready"):
    st.success("Recovery readiness verified: live encrypted data is readable and at least one valid backup is available.")
else:
    st.error("Recovery readiness is incomplete. Review the issues below before relying on this vault operationally.")

if report.get("latest_valid_backup"):
    st.caption(f"Latest valid backup: {report['latest_valid_backup']}")
if report.get("errors"):
    with st.expander("Integrity findings", expanded=True):
        for error in report["errors"]:
            st.write(f"• {error}")

st.subheader("Encrypted backup inventory")
rows = []
for backup in list_backups(vault, 50):
    check = validate_backup(backup, current_encryption_key())
    rows.append({
        "Backup": backup.name,
        "Encrypted": "YES" if check.get("encrypted") else "NO",
        "Valid": "PASS" if check.get("valid") else "FAIL",
        "Checksum": "PASS" if check.get("checksum_ok") is True else ("None" if check.get("checksum_ok") is None else "FAIL"),
        "Records": check.get("records", ""),
        "Error": check.get("error", ""),
    })
if rows:
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.warning("No backups are currently available.")

st.divider()
st.subheader("Emergency Recovery Key")
rec = recovery_status(vault)
if rec.get("verified"):
    st.success("Emergency recovery key protection is configured.")
    st.caption(f"Configured: {rec.get('created_at','')}")
    st.warning("Keep the recovery key somewhere separate from M-P-ENG-SYS. Anyone with the recovery key and the HDD can unlock the encrypted engineering data.")
else:
    st.warning("No emergency recovery key exists yet. If the vault PIN/password is lost, encrypted data may become inaccessible.")
    with st.form("create_recovery_key"):
        pin = st.text_input("Confirm current vault PIN/password", type="password")
        understand = st.checkbox("I will store the recovery key somewhere separate from the Engineering Vault")
        create = st.form_submit_button("Generate Emergency Recovery Key", type="primary", use_container_width=True)
    if create:
        if not understand:
            st.error("Confirm that the recovery key will be stored separately.")
        elif not verify_pin(vault, pin):
            st.error("Current PIN/password is incorrect.")
        else:
            token = create_recovery_key(vault, current_encryption_key())
            st.session_state.usb_new_recovery_key = token
            st.success("Recovery key generated. Save it now; it will not be shown again after this session is cleared.")

if st.session_state.get("usb_new_recovery_key"):
    token = st.session_state.usb_new_recovery_key
    st.code(token, language=None)
    st.download_button(
        "Download Recovery Key",
        data=("PMES USB Emergency Recovery Key\n\n" + token + "\n"),
        file_name="PMES_USB_EMERGENCY_RECOVERY_KEY.txt",
        mime="text/plain",
        use_container_width=True,
    )
    entered = st.text_input("Verify the saved recovery key", type="password", key="verify_saved_recovery")
    if st.button("Verify Recovery Key", use_container_width=True):
        if verify_recovery_key(vault, entered.strip()):
            st.success("PASS — recovery key successfully opens the encrypted vault data key.")
            st.session_state.usb_recovery_key_verified = True
        else:
            st.error("Recovery key verification failed.")

st.divider()
st.subheader("Safe PIN / Password Re-key")
meta = encryption_metadata(vault)
mode = "Wrapped-key" if meta and meta.get("schema") == "pmes-encryption-v2" else "Legacy v0.6"
st.caption(f"Encryption key-protection mode: {mode}")
st.write("Changing the PIN does not rewrite the engineering dataset or backup archives. The existing data key is wrapped by the new PIN and verified before the old PIN is retired.")
with st.form("safe_rekey"):
    current_pin = st.text_input("Current PIN/password", type="password", key="rekey_current")
    new_pin1 = st.text_input("New PIN/password", type="password", key="rekey_new1")
    new_pin2 = st.text_input("Confirm new PIN/password", type="password", key="rekey_new2")
    confirm_rekey = st.checkbox("I understand the old PIN will stop working after a successful re-key")
    do_rekey = st.form_submit_button("Safely Change Vault PIN", type="primary", use_container_width=True)
if do_rekey:
    if not confirm_rekey:
        st.error("Confirm the re-key operation first.")
    elif new_pin1 != new_pin2:
        st.error("The new PIN/password entries do not match.")
    elif not new_pin1:
        st.error("The new PIN/password cannot be blank.")
    else:
        try:
            new_key = rekey_pin(vault, current_pin, new_pin1, current_encryption_key())
            st.session_state.usb_cipher = new_key
            st.success("PIN re-key completed and the encrypted live dataset verified with the new PIN.")
            st.info("Lock the Engineering System and unlock it again with the new PIN to complete the practical test.")
        except Exception as exc:
            st.error(f"PIN re-key did not complete: {exc}")

if st.session_state.get("usb_recovery_unlock"):
    st.divider()
    st.subheader("Emergency PIN Reset")
    st.warning("This session was opened using the emergency recovery key. You can establish a new PIN/password without knowing the old PIN.")
    with st.form("emergency_reset"):
        recovery_token = st.text_input("Emergency recovery key", type="password")
        reset1 = st.text_input("New PIN/password", type="password", key="reset1")
        reset2 = st.text_input("Confirm new PIN/password", type="password", key="reset2")
        reset = st.form_submit_button("Reset PIN Using Recovery Key", type="primary", use_container_width=True)
    if reset:
        if reset1 != reset2 or not reset1:
            st.error("Enter matching non-empty new PIN/password values.")
        else:
            try:
                new_key = reset_pin_with_recovery(vault, recovery_token.strip(), reset1)
                st.session_state.usb_cipher = new_key
                st.session_state.usb_recovery_unlock = False
                st.success("Emergency PIN reset completed. Lock and reopen the Engineering System using the new PIN.")
            except Exception as exc:
                st.error(f"Emergency PIN reset failed: {exc}")

st.info("Emergency recovery never creates a plaintext copy of the engineering dataset. Keep the recovery-key file off the Engineering Vault, preferably in a separate secure location.")

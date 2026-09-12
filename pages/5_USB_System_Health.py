import pandas as pd
import streamlit as st

from usb_runtime import initialise_page, current_encryption_key
from usb_storage import list_backups, validate_backup, vault_status, encryption_status
from usb_diagnostics import run_persistence_self_test
from usb_security import configure, status as security_status, change_pin, revoke_this_computer

st.set_page_config(page_title="USB System Health", page_icon="🧪", layout="wide")
_vault, store = initialise_page()

st.title("USB System Health")
st.caption("Operational hardening and access controls for the local Engineering Vault.")

info = vault_status(_vault)
enc = encryption_status(_vault)
cols = st.columns(5)
cols[0].metric("Vault", info.get("label", "Engineering Vault"))
cols[1].metric("Free space", f"{info.get('free_bytes', 0)/(1024**3):.1f} GB")
cols[2].metric("Backups", len(list_backups(_vault, 500)))
cols[3].metric("Persistence", "ON")
cols[4].metric("Encryption", "ON" if enc.get("enabled") else "OFF")

st.subheader("Security & Access Control")
sec = security_status(_vault)
if not sec.get("configured"):
    st.info("Security is not configured yet.")
    with st.form("security_setup"):
        pin1 = st.text_input("New vault PIN / password (optional)", type="password")
        pin2 = st.text_input("Confirm PIN / password", type="password")
        submit = st.form_submit_button("Configure Vault Security", type="primary")
    if submit:
        if pin1 != pin2:
            st.error("The two entries do not match.")
        else:
            configure(_vault, pin1)
            st.success("Vault security configured.")
            st.rerun()
else:
    c1, c2, c3 = st.columns(3)
    c1.metric("Physical Vault", "REQUIRED")
    c2.metric("This Computer", "AUTHORISED" if sec.get("computer_authorised") else "NOT AUTHORISED")
    c3.metric("PIN Lock", "ON" if sec.get("pin_enabled") else "OFF")
    if enc.get("enabled"):
        st.info("PIN/password changes are disabled while v0.6 at-rest encryption is active. A safe re-key workflow will be added separately.")
    else:
        with st.expander("Change or remove PIN lock"):
            current = st.text_input("Current PIN / password", type="password", key="sec_current")
            new1 = st.text_input("New PIN / password (leave blank to remove)", type="password", key="sec_new1")
            new2 = st.text_input("Confirm new PIN / password", type="password", key="sec_new2")
            if st.button("Apply PIN Change"):
                if new1 != new2:
                    st.error("The new entries do not match.")
                else:
                    try:
                        change_pin(_vault, current, new1)
                        st.success("PIN settings updated.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
    with st.expander("Revoke this computer"):
        st.warning("Revoking removes this computer's local authorisation record.")
        if st.button("Revoke This Computer"):
            revoke_this_computer(_vault)
            st.success("This computer's local authorisation record was removed.")
            st.rerun()

st.divider()
st.subheader("Core persistence self-test")
if st.button("Run HDD Persistence Self-Test", type="primary", use_container_width=True):
    with st.spinner("Writing, reloading and validating temporary engineering records..."):
        try:
            result = run_persistence_self_test(_vault, store, current_encryption_key())
            st.success("PASS — HDD persistence and linked UUID relationships verified.") if result.get("passed") else st.error("FAIL — one or more persistence checks did not pass.")
            rows = [{"Module":r.get("module","").replace("_"," ").title(),"Write / Read":"PASS" if r.get("write_read") else "FAIL","UUID Preserved":"PASS" if r.get("uuid_preserved") else "FAIL","Diagnostic Tag":"PASS" if r.get("tag_preserved") else "FAIL"} for r in result.get("results",[])]
            if rows: st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            st.write("Linked asset UUIDs:", "PASS" if result.get("links_ok") else "FAIL")
        except Exception as exc:
            st.error(f"Persistence self-test could not complete: {exc}")

st.divider()
st.subheader("Recent backup integrity")
backups = list_backups(_vault, 10)
if not backups:
    st.info("No backups have been created yet.")
else:
    rows=[]
    for backup in backups:
        check=validate_backup(backup, current_encryption_key())
        rows.append({"Backup":f"{backup.parent.name}/{backup.name}","Encrypted":"YES" if check.get("encrypted") else "NO","Valid":"PASS" if check.get("valid") else "FAIL","Checksum":"PASS" if check.get("checksum_ok") is True else ("Legacy / none" if check.get("checksum_ok") is None else "FAIL"),"Records":check.get("records",""),"Error":check.get("error","")})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

import pandas as pd
import streamlit as st

from usb_runtime import initialise_page, current_encryption_key
from usb_integrity import integrity_report
from usb_storage import list_backups, validate_backup

st.set_page_config(page_title="Recovery & Integrity", page_icon="🛡️", layout="wide")
vault, store = initialise_page()

st.title("Recovery & Integrity")
st.caption("v0.7A startup-readiness, encrypted backup health and emergency recovery visibility.")

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

st.info("Emergency recovery uses the validated encrypted backups through the existing Backup & Recovery control. v0.7A does not create a plaintext recovery copy.")

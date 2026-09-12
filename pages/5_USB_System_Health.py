import pandas as pd
import streamlit as st

from usb_runtime import initialise_page
from usb_storage import list_backups, validate_backup, vault_status
from usb_diagnostics import run_persistence_self_test

st.set_page_config(page_title="USB System Health", page_icon="🧪", layout="wide")
_vault, store = initialise_page()

st.title("USB System Health")
st.caption("Operational hardening checks for the local Engineering Vault. The persistence self-test writes temporary linked records to the HDD, reloads them, verifies them, then restores the original dataset automatically.")

info = vault_status(_vault)
cols = st.columns(4)
cols[0].metric("Vault", info.get("label", "Engineering Vault"))
cols[1].metric("Free space", f"{info.get('free_bytes', 0)/(1024**3):.1f} GB")
cols[2].metric("Backups", len(list_backups(_vault, 500)))
cols[3].metric("Persistence", "ON")

st.subheader("Core persistence self-test")
st.write("Tests **Assets → Engineering Actions → Maintenance → PM Schedules** using linked hidden UUIDs. A safety backup is created first and the temporary test records are removed automatically at the end.")

if st.button("Run HDD Persistence Self-Test", type="primary", use_container_width=True):
    with st.spinner("Writing, reloading and validating temporary engineering records..."):
        try:
            result = run_persistence_self_test(_vault, store)
            if result.get("passed"):
                st.success("PASS — HDD persistence and linked UUID relationships verified.")
            else:
                st.error("FAIL — one or more persistence checks did not pass.")
            rows = []
            for row in result.get("results", []):
                rows.append({
                    "Module": row.get("module", "").replace("_", " ").title(),
                    "Write / Read": "PASS" if row.get("write_read") else "FAIL",
                    "UUID Preserved": "PASS" if row.get("uuid_preserved") else "FAIL",
                    "Diagnostic Tag": "PASS" if row.get("tag_preserved") else "FAIL",
                })
            if rows:
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            st.write("Linked asset UUIDs:", "PASS" if result.get("links_ok") else "FAIL")
            st.caption(f"Safety backup: {result.get('safety_backup', '')}")
        except Exception as exc:
            st.error(f"Persistence self-test could not complete: {exc}")

st.divider()
st.subheader("Recent backup integrity")
backups = list_backups(_vault, 10)
if not backups:
    st.info("No backups have been created yet.")
else:
    rows = []
    for backup in backups:
        check = validate_backup(backup)
        rows.append({
            "Backup": f"{backup.parent.name}/{backup.name}",
            "Valid": "PASS" if check.get("valid") else "FAIL",
            "Checksum": "PASS" if check.get("checksum_ok") is True else ("Legacy / none" if check.get("checksum_ok") is None else "FAIL"),
            "Records": check.get("records", ""),
            "Error": check.get("error", ""),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

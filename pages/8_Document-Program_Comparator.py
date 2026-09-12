import base64
import csv
import io
import uuid
from datetime import datetime

import streamlit as st

from usb_runtime import initialise_page, persist
from comparator import (
    cnc_compare,
    ignore_position_compare,
    inline_difference,
    line_compare,
    merge_files,
    read_uploaded_file,
    summary_stats,
)

st.set_page_config(page_title="Document-Program Comparator", page_icon="🔍", layout="wide")
vault, store = initialise_page()
store.setdefault("engineering_tool_records", [])

st.title("Document-Program Comparator")
st.caption("Compare old and revised CNC programs or general documents locally inside the encrypted Engineering Vault system.")

comparison_mode = st.radio(
    "Comparison type",
    ["CNC Program", "General Document"],
    horizontal=True,
    help="CNC Program uses block alignment and machine-code change classification. General Document uses standard line-by-line comparison.",
)
is_cnc = comparison_mode == "CNC Program"

ignore_sequence = True
ignore_comments = True
ignore_whitespace = True
if is_cnc:
    with st.sidebar:
        st.header("CNC comparison settings")
        ignore_sequence = st.checkbox("Ignore N sequence numbers", value=True)
        ignore_comments = st.checkbox("Ignore comments", value=True)
        ignore_whitespace = st.checkbox("Ignore whitespace", value=True)
else:
    with st.sidebar:
        st.header("General document mode")
        st.caption("Standard text comparison is active.")

left_col, right_col = st.columns(2)
with left_col:
    file1 = st.file_uploader("Old / reference program", type=["txt", "pdf", "nc", "cnc", "tap", "iso", "mpf", "spf"], key="cmp_file1")
with right_col:
    file2 = st.file_uploader("New / revised program", type=["txt", "pdf", "nc", "cnc", "tap", "iso", "mpf", "spf"], key="cmp_file2")

if not file1 or not file2:
    st.info("Upload the old/reference file and the new/revised file to begin.")
    st.stop()

try:
    content1 = read_uploaded_file(file1)
    content2 = read_uploaded_file(file2)
except Exception as exc:
    st.error(f"Could not read one of the files: {exc}")
    st.stop()

report_bytes = None
report_name = None
summary_payload = {}

if is_cnc:
    result = cnc_compare(content1, content2, ignore_sequence=ignore_sequence, ignore_comments=ignore_comments, ignore_whitespace=ignore_whitespace)
    changes = result["changes"]
    modified = sum(c["status"] == "modified" for c in changes)
    inserted = sum(c["status"] == "inserted" for c in changes)
    deleted = sum(c["status"] == "deleted" for c in changes)
    summary_payload = {"matched_blocks": result["matched_blocks"], "modified": modified, "inserted": inserted, "deleted": deleted, "total_changes": len(changes), "category_counts": result["category_counts"]}
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Matched blocks", result["matched_blocks"]); m2.metric("Modified", modified); m3.metric("Inserted", inserted); m4.metric("Deleted", deleted); m5.metric("Total changes", len(changes))
    tab_compare, tab_summary, tab_files, tab_general, tab_merge = st.tabs(["CNC Compare", "Change Summary", "File Contents", "Ignore Position", "Merge"])
    with tab_compare:
        st.subheader("CNC-aware aligned comparison")
        st.caption("Inserted/deleted blocks are aligned so a single added block does not shift the remainder of the program.")
        if not changes: st.success("No CNC differences found with the current settings.")
        else:
            filters = st.multiselect("Show change types", ["modified", "inserted", "deleted"], default=["modified", "inserted", "deleted"])
            visible = [c for c in changes if c["status"] in filters]
            for index, change in enumerate(visible, start=1):
                labels = " · ".join(change["categories"]); line1 = change["file1_line"] if change["file1_line"] is not None else "—"; line2 = change["file2_line"] if change["file2_line"] is not None else "—"
                with st.expander(f"{index}. {change['status'].upper()} — old line {line1} ↔ new line {line2} — {labels}", expanded=index <= 5):
                    c1, c2 = st.columns(2)
                    if change["status"] == "modified": marked1, marked2 = inline_difference(change["file1"], change["file2"])
                    else: marked1, marked2 = change["file1"], change["file2"]
                    with c1: st.markdown(f"**{file1.name} · line {line1}**"); st.markdown(marked1 or "*(no corresponding block)*")
                    with c2: st.markdown(f"**{file2.name} · line {line2}**"); st.markdown(marked2 or "*(no corresponding block)*")
                    if change["status"] == "modified":
                        st.caption(f"Block similarity: {change['similarity']}%")
                        if change["details"]: st.dataframe(change["details"], use_container_width=True, hide_index=True, column_order=["category", "address", "file1", "file2"])
    with tab_summary:
        counts = result["category_counts"]
        if counts: st.dataframe([{"Change category": category, "Occurrences": count} for category, count in sorted(counts.items(), key=lambda x: (-x[1], x[0]))], use_container_width=True, hide_index=True)
        else: st.success("No changes to summarize.")
        report_buffer = io.StringIO(); writer = csv.writer(report_buffer); writer.writerow(["status", "old_line", "new_line", "categories", "address", "old_value", "new_value", "old_block", "new_block"])
        for change in changes:
            if change["details"]:
                for detail in change["details"]: writer.writerow([change["status"], change["file1_line"] or "", change["file2_line"] or "", " | ".join(change["categories"]), detail["address"], detail["file1"], detail["file2"], change["file1"], change["file2"]])
            else: writer.writerow([change["status"], change["file1_line"] or "", change["file2_line"] or "", " | ".join(change["categories"]), "", "", "", change["file1"], change["file2"]])
        report_bytes = report_buffer.getvalue().encode("utf-8"); report_name = f"{file1.name.rsplit('.', 1)[0]}_vs_{file2.name.rsplit('.', 1)[0]}_comparison.csv"
        st.download_button("Download CNC comparison report (CSV)", data=report_bytes, file_name=report_name, mime="text/csv", use_container_width=True)
else:
    stats = summary_stats(content1, content2); diffs = line_compare(content1, content2); summary_payload = dict(stats)
    m1, m2, m3, m4 = st.columns(4); m1.metric("Old file lines", stats["file1_lines"]); m2.metric("New file lines", stats["file2_lines"]); m3.metric("Differences", stats["differences"]); m4.metric("Matching lines", stats["matching_lines"])
    tab_compare, tab_files, tab_general, tab_merge = st.tabs(["Document Compare", "File Contents", "Ignore Position", "Merge"])
    with tab_compare:
        if not diffs: st.success("No differences found.")
        else:
            st.warning(f"{len(diffs)} differing line(s) found.")
            for diff in diffs[:200]:
                with st.expander(f"Line {diff['line']} — similarity {diff['similarity']}%", expanded=diff["line"] <= 5):
                    marked1, marked2 = inline_difference(diff["file1"], diff["file2"]); c1, c2 = st.columns(2)
                    with c1: st.markdown(marked1 or "*(blank)*")
                    with c2: st.markdown(marked2 or "*(blank)*")
        report_text = [f"Old/reference: {file1.name}", f"New/revised: {file2.name}", f"Differences: {len(diffs)}", ""]
        for diff in diffs: report_text.extend([f"Line {diff['line']} ({diff['similarity']}%)", f"OLD: {diff['file1']}", f"NEW: {diff['file2']}", ""])
        report_bytes = "\n".join(report_text).encode("utf-8"); report_name = f"{file1.name.rsplit('.', 1)[0]}_vs_{file2.name.rsplit('.', 1)[0]}_comparison.txt"

with tab_files:
    c1, c2 = st.columns(2)
    with c1: st.markdown(f"**Old/reference — {file1.name}**"); st.code(content1, language=None, line_numbers=True)
    with c2: st.markdown(f"**New/revised — {file2.name}**"); st.code(content2, language=None, line_numbers=True)
with tab_general:
    general = ignore_position_compare(content1, content2); c1, c2 = st.columns(2)
    with c1: st.markdown(f"**Only in old/reference ({len(general['only_file1'])})**"); st.code("\n".join(general["only_file1"]) or "No unique lines", language=None)
    with c2: st.markdown(f"**Only in new/revised ({len(general['only_file2'])})**"); st.code("\n".join(general["only_file2"]) or "No unique lines", language=None)
with tab_merge:
    if is_cnc: st.warning("CNC merge remains line-based. Review merged output carefully before any machine use.")
    prefer = st.radio("When corresponding lines differ, which file should win?", ["New / revised", "Old / reference"], horizontal=True); merged = merge_files(content1, content2, prefer="file2" if prefer == "New / revised" else "file1")
    st.code(merged, language=None, line_numbers=True); st.download_button("Download merged file", data=merged, file_name=f"{file1.name.rsplit('.', 1)[0]}_merged.txt", mime="text/plain", use_container_width=True)

st.divider(); st.subheader("Encrypted Engineering Vault record")
comparison_note = st.text_input("Optional comparison note / process-change reference", placeholder="e.g. AT7701 OP1 cycle-time update")
if report_bytes and report_name and st.button("Save Comparison Report to Encrypted Vault", type="primary", use_container_width=True):
    record = {"uuid": str(uuid.uuid4()), "type": "program_comparison", "created_at": datetime.now().replace(microsecond=0).isoformat(), "mode": comparison_mode, "old_file": file1.name, "new_file": file2.name, "note": comparison_note, "summary": summary_payload, "report_name": report_name, "report_b64": base64.b64encode(report_bytes).decode("ascii")}
    store["engineering_tool_records"].append(record); persist(store); st.success("Comparison report saved inside the encrypted Engineering Vault dataset.")
saved = [r for r in store.get("engineering_tool_records", []) if r.get("type") == "program_comparison"]
with st.expander(f"Saved comparison reports ({len(saved)})", expanded=False):
    if not saved: st.caption("No encrypted comparison reports saved yet.")
    for record in reversed(saved[-25:]):
        st.markdown(f"**{record.get('old_file','')} → {record.get('new_file','')}** · {record.get('created_at','')}")
        if record.get("note"): st.caption(record["note"])
        try:
            payload = base64.b64decode(record.get("report_b64", "")); st.download_button("Download saved report", data=payload, file_name=record.get("report_name", "comparison_report.txt"), key=f"cmp_saved_{record.get('uuid')}", use_container_width=True)
        except Exception: st.warning("Stored report payload could not be decoded.")

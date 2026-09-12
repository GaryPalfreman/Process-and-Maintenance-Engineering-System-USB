import io
import json
import uuid
import zipfile
from copy import deepcopy
from datetime import date, datetime, timedelta

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

SCHEMA = "process-maintenance-engineering-system"
VERSION = 2

MODULES = [
    "assets", "actions", "maintenance", "pm_schedules", "process_improvements",
    "trials", "research", "rca", "products", "process_routes", "tooling", "spares"
]

DEFAULT_MATERIALS = ["Glass", "Silon", "Alumina", "Quartz"]
DEFAULT_ASSET_CLASSES = [
    "CNC", "Grinding", "Cutting", "Laser", "Filtration", "Chiller", "Extraction",
    "Measuring", "Pump", "Vacuum", "Furnace", "Custom Equipment", "Other"
]


def now_iso():
    return datetime.now().replace(microsecond=0).isoformat()


def new_uuid():
    return str(uuid.uuid4())


def blank_store():
    return {
        "schema": SCHEMA,
        "version": VERSION,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "settings": {
            "company_name": "",
            "departments": [],
            "materials": DEFAULT_MATERIALS.copy(),
            "asset_classes": DEFAULT_ASSET_CLASSES.copy(),
        },
        **{m: [] for m in MODULES},
    }


def normalise_store(store):
    if not isinstance(store, dict) or store.get("schema") != SCHEMA:
        raise ValueError("This is not a Process and Maintenance Engineering System JSON file.")
    base = blank_store()
    out = deepcopy(store)
    base.update(out)
    base["version"] = VERSION
    base.setdefault("settings", {})
    base["settings"].setdefault("company_name", "")
    base["settings"].setdefault("departments", [])
    base["settings"].setdefault("materials", DEFAULT_MATERIALS.copy())
    base["settings"].setdefault("asset_classes", DEFAULT_ASSET_CLASSES.copy())
    for module in MODULES:
        base.setdefault(module, [])
    for module in MODULES:
        for r in base.get(module, []):
            r.setdefault("system_uuid", new_uuid())
            r.setdefault("business_id", "")
            r.setdefault("legacy_id", "")
            r.setdefault("alias", "")
            r.setdefault("created_at", now_iso())
            r.setdefault("updated_at", r.get("created_at", now_iso()))
            r.setdefault("linked_action_uuids", [])
            r.setdefault("linked_rca_uuids", [])
    return base


def store_bytes(store):
    payload = deepcopy(store)
    payload["version"] = VERSION
    payload["updated_at"] = now_iso()
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def load_store(file_bytes):
    return normalise_store(json.loads(file_bytes.decode("utf-8")))


def base_record(record_type, title="", department="", business_id="", legacy_id=""):
    return {
        "system_uuid": new_uuid(), "record_type": record_type, "title": title.strip(),
        "department": department.strip(), "business_id": business_id.strip(),
        "legacy_id": legacy_id.strip(), "alias": "", "created_at": now_iso(),
        "updated_at": now_iso(), "linked_action_uuids": [], "linked_rca_uuids": [],
    }


def record_label(record):
    if not record:
        return ""
    human = record.get("business_id") or record.get("legacy_id") or record.get("alias")
    prefix = f"{human} - " if human else ""
    return f"{prefix}{record.get('title','Untitled')}"


def by_uuid(records):
    return {r.get("system_uuid"): r for r in records if r.get("system_uuid")}


def label_by_uuid(store, module, system_uuid):
    return record_label(by_uuid(store.get(module, [])).get(system_uuid))


def asset_label_by_uuid(store, asset_uuid):
    return label_by_uuid(store, "assets", asset_uuid)


def product_label_by_uuid(store, product_uuid):
    return label_by_uuid(store, "products", product_uuid)


def linked_records(store, target_uuid):
    rows = []
    for module in MODULES:
        for r in store.get(module, []):
            if r.get("system_uuid") == target_uuid:
                continue
            link_fields = [
                "asset_uuid", "product_uuid", "process_improvement_uuid", "trial_uuid",
                "research_uuid", "rca_uuid", "maintenance_uuid", "pm_schedule_uuid"
            ]
            if any(r.get(f) == target_uuid for f in link_fields):
                rows.append((module, r))
                continue
            list_fields = ["linked_action_uuids", "linked_rca_uuids", "related_asset_uuids"]
            if any(target_uuid in (r.get(f) or []) for f in list_fields):
                rows.append((module, r))
    return rows


def parse_date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def pm_status(schedule, today=None):
    today = today or date.today()
    due = parse_date(schedule.get("next_due_date"))
    if not due:
        return schedule.get("status", "Planned")
    if schedule.get("status") in ["Inactive", "Cancelled"]:
        return schedule.get("status")
    if due < today:
        return "Overdue"
    if due <= today + timedelta(days=14):
        return "Due Soon"
    return "Scheduled"


def dashboard_metrics(store):
    actions = store.get("actions", [])
    maintenance = store.get("maintenance", [])
    assets = store.get("assets", [])
    open_actions = [a for a in actions if a.get("status", "Open") not in ["Complete", "Closed"]]
    critical = [a for a in open_actions if a.get("priority") == "Critical"]
    breakdowns = [m for m in maintenance if m.get("maintenance_type") == "Breakdown"]
    downtime = sum(float(m.get("downtime_hours", 0) or 0) for m in breakdowns)
    schedules = store.get("pm_schedules", [])
    overdue_pm = [p for p in schedules if pm_status(p) == "Overdue"]
    due_soon_pm = [p for p in schedules if pm_status(p) == "Due Soon"]
    active_assets = [a for a in assets if a.get("status", "Active") == "Active"]
    return {
        "assets": len(assets), "active_assets": len(active_assets), "open_actions": len(open_actions),
        "critical_actions": len(critical), "breakdowns": len(breakdowns), "downtime_hours": downtime,
        "overdue_pm": len(overdue_pm), "due_soon_pm": len(due_soon_pm),
        "process_improvements": len(store.get("process_improvements", [])),
        "trials": len(store.get("trials", [])), "research": len(store.get("research", [])),
        "products": len(store.get("products", [])),
    }


def maintenance_kpis(store):
    maintenance = store.get("maintenance", [])
    completed_breakdowns = [m for m in maintenance if m.get("maintenance_type") == "Breakdown"]
    downtime = [float(m.get("downtime_hours", 0) or 0) for m in completed_breakdowns]
    repair_times = [float(m.get("repair_hours", 0) or 0) for m in completed_breakdowns if float(m.get("repair_hours", 0) or 0) > 0]
    mttr = sum(repair_times) / len(repair_times) if repair_times else 0.0
    mtbf_values = []
    grouped = {}
    for m in completed_breakdowns:
        asset = m.get("asset_uuid")
        d = parse_date(m.get("event_date"))
        if asset and d:
            grouped.setdefault(asset, []).append(d)
    for dates in grouped.values():
        dates = sorted(set(dates))
        if len(dates) >= 2:
            gaps = [(dates[i] - dates[i-1]).days * 24 for i in range(1, len(dates))]
            mtbf_values.extend(gaps)
    return {
        "breakdown_count": len(completed_breakdowns),
        "downtime_hours": sum(downtime),
        "mttr_hours": mttr,
        "mtbf_hours": (sum(mtbf_values) / len(mtbf_values)) if mtbf_values else 0.0,
    }


def records_dataframe(records):
    if not records:
        return pd.DataFrame()
    rows = []
    for r in records:
        row = dict(r)
        for key, value in list(row.items()):
            if isinstance(value, (list, dict)):
                row[key] = json.dumps(value, ensure_ascii=False)
        rows.append(row)
    return pd.DataFrame(rows)


def _table(data, col_widths=None):
    styles = getSampleStyleSheet()
    wrapped = []
    for row in data:
        wrapped.append([Paragraph(str(v or ""), styles["BodyText"]) for v in row])
    table = Table(wrapped, repeatRows=1, hAlign="LEFT", colWidths=col_widths)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#25313c")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 7), ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f3f4f6")]),
        ("LEFTPADDING", (0,0), (-1,-1), 3), ("RIGHTPADDING", (0,0), (-1,-1), 3),
    ]))
    return table


def generate_summary_pdf(store):
    metrics = dashboard_metrics(store)
    mkpi = maintenance_kpis(store)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=10*mm, rightMargin=10*mm, topMargin=10*mm, bottomMargin=10*mm)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("title", parent=styles["Title"], alignment=TA_CENTER, fontSize=20)
    story = [Spacer(1, 20*mm), Paragraph("Process and Maintenance Engineering System", title),
             Paragraph("Engineering Management Summary", ParagraphStyle("sub", parent=styles["Heading2"], alignment=TA_CENTER)),
             Spacer(1, 6*mm), Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ParagraphStyle("date", parent=styles["Normal"], alignment=TA_CENTER)), PageBreak()]
    summary = [
        ["Metric", "Value", "Metric", "Value"],
        ["Assets", metrics["assets"], "Active Assets", metrics["active_assets"]],
        ["Open Actions", metrics["open_actions"], "Critical Actions", metrics["critical_actions"]],
        ["Breakdowns", mkpi["breakdown_count"], "Downtime (h)", f"{mkpi['downtime_hours']:.2f}"],
        ["MTTR (h)", f"{mkpi['mttr_hours']:.2f}", "MTBF (h)", f"{mkpi['mtbf_hours']:.2f}"],
        ["PM Overdue", metrics["overdue_pm"], "PM Due Soon", metrics["due_soon_pm"]],
        ["Process Improvements", metrics["process_improvements"], "Engineering Trials", metrics["trials"]],
    ]
    story += [Paragraph("System Overview", styles["Heading2"]), _table(summary), Spacer(1, 6*mm)]

    pm_rows = [["Asset", "Task", "Frequency", "Next Due", "Status", "Owner"]]
    for r in store.get("pm_schedules", [])[:50]:
        pm_rows.append([asset_label_by_uuid(store, r.get("asset_uuid")), r.get("title"), r.get("frequency"), r.get("next_due_date"), pm_status(r), r.get("owner")])
    if len(pm_rows) > 1:
        story += [Paragraph("Preventive Maintenance Schedule", styles["Heading2"]), _table(pm_rows), PageBreak()]

    action_rows = [["Priority", "Status", "Department", "Title", "Owner", "Due", "Asset"]]
    for r in store.get("actions", [])[:50]:
        action_rows.append([r.get("priority"), r.get("status"), r.get("department"), r.get("title"), r.get("owner"), r.get("due_date"), asset_label_by_uuid(store, r.get("asset_uuid"))])
    if len(action_rows) > 1:
        story += [Paragraph("Engineering Actions", styles["Heading2"]), _table(action_rows), PageBreak()]

    maint_rows = [["Date", "Type", "Asset", "Status", "Downtime h", "Repair h", "Summary"]]
    for r in store.get("maintenance", [])[-60:]:
        maint_rows.append([r.get("event_date"), r.get("maintenance_type"), asset_label_by_uuid(store, r.get("asset_uuid")), r.get("status"), r.get("downtime_hours",0), r.get("repair_hours",0), r.get("title")])
    if len(maint_rows) > 1:
        story += [Paragraph("Maintenance / Breakdown History", styles["Heading2"]), _table(maint_rows)]
    doc.build(story)
    return buffer.getvalue()


def backup_zip(store):
    out = io.BytesIO()
    payload = store_bytes(store)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Process_Maintenance_Engineering_System.json", payload)
        zf.writestr("Engineering_Management_Summary.pdf", generate_summary_pdf(store))
        zf.writestr("README.txt", "Local backup for Process and Maintenance Engineering System.\nThe JSON file contains all current records and relationships.\n")
    return out.getvalue()

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from engineering_system import base_record, by_uuid, now_iso, parse_date, record_label, asset_label_by_uuid
from advanced_operations import recurring_failures

CONTROL_COLLECTIONS = ["work_orders", "shutdowns", "condition_readings", "handover_notes", "risk_assessments"]


def ensure_control_collections(store):
    for name in CONTROL_COLLECTIONS:
        store.setdefault(name, [])
    return store


def create_work_order(store, title, department="", asset_uuid="", work_type="Corrective", priority="Medium",
                      owner="", requested_by="", due_date=None, scope="", safety_requirements="",
                      estimated_hours=0.0, planned_downtime_hours=0.0, source_maintenance_uuid="",
                      source_action_uuid="", business_id="", legacy_id=""):
    ensure_control_collections(store)
    r = base_record("work_order", title, department, business_id, legacy_id)
    r.update({
        "asset_uuid": asset_uuid, "work_type": work_type, "priority": priority, "status": "Open",
        "owner": owner, "requested_by": requested_by, "requested_date": date.today().isoformat(),
        "planned_start": "", "due_date": (parse_date(due_date) or date.today()).isoformat(),
        "scope": scope, "safety_requirements": safety_requirements,
        "estimated_hours": float(estimated_hours or 0), "actual_hours": 0.0,
        "planned_downtime_hours": float(planned_downtime_hours or 0), "actual_downtime_hours": 0.0,
        "parts_required": "", "parts_status": "Not Reviewed", "contractor_required": False,
        "completion_notes": "", "source_maintenance_uuid": source_maintenance_uuid,
        "source_action_uuid": source_action_uuid,
    })
    store["work_orders"].append(r)
    return r


def update_work_order(store, work_order_uuid, **changes):
    r = by_uuid(store.get("work_orders", [])).get(work_order_uuid)
    if not r:
        raise KeyError("Work order not found")
    for key, value in changes.items():
        if key not in {"system_uuid", "record_type", "created_at"}:
            r[key] = value
    r["updated_at"] = now_iso()
    return r


def create_shutdown(store, title, start_date, end_date, department="", coordinator="", asset_uuids=None,
                    scope="", prework="", parts_readiness="", contractor_plan="", safety_plan="",
                    restart_plan=""):
    ensure_control_collections(store)
    r = base_record("shutdown", title, department)
    r.update({
        "start_date": (parse_date(start_date) or date.today()).isoformat(),
        "end_date": (parse_date(end_date) or parse_date(start_date) or date.today()).isoformat(),
        "coordinator": coordinator, "status": "Planned", "affected_asset_uuids": asset_uuids or [],
        "scope": scope, "prework": prework, "parts_readiness": parts_readiness,
        "contractor_plan": contractor_plan, "safety_plan": safety_plan, "restart_plan": restart_plan,
        "linked_work_order_uuids": [],
    })
    store["shutdowns"].append(r)
    return r


def condition_status(value, warning_limit=None, critical_limit=None, direction="High"):
    try:
        value = float(value)
    except Exception:
        return "Unknown"
    warn = None if warning_limit in (None, "") else float(warning_limit)
    crit = None if critical_limit in (None, "") else float(critical_limit)
    direction = (direction or "High").lower()
    if direction == "low":
        if crit is not None and value <= crit:
            return "Critical"
        if warn is not None and value <= warn:
            return "Warning"
    else:
        if crit is not None and value >= crit:
            return "Critical"
        if warn is not None and value >= warn:
            return "Warning"
    return "Normal"


def add_condition_reading(store, asset_uuid, metric, value, unit="", reading_date=None, warning_limit=None,
                          critical_limit=None, direction="High", source="Manual", notes=""):
    ensure_control_collections(store)
    r = base_record("condition_reading", metric, "")
    r.update({
        "asset_uuid": asset_uuid, "metric": metric, "value": float(value), "unit": unit,
        "reading_date": (parse_date(reading_date) or date.today()).isoformat(),
        "warning_limit": warning_limit, "critical_limit": critical_limit, "direction": direction,
        "condition_status": condition_status(value, warning_limit, critical_limit, direction),
        "source": source, "notes": notes,
    })
    store["condition_readings"].append(r)
    return r


def condition_summary(store):
    ensure_control_collections(store)
    latest = {}
    for r in store.get("condition_readings", []):
        key = (r.get("asset_uuid"), r.get("metric"))
        stamp = str(r.get("reading_date", ""))
        if key not in latest or stamp >= str(latest[key].get("reading_date", "")):
            latest[key] = r
    rows = []
    for (_, _), r in latest.items():
        rows.append({
            "Asset": asset_label_by_uuid(store, r.get("asset_uuid")) or "Unassigned",
            "Metric": r.get("metric", ""), "Value": r.get("value"), "Unit": r.get("unit", ""),
            "Status": r.get("condition_status", "Unknown"), "Date": r.get("reading_date", ""),
        })
    rank = {"Critical": 0, "Warning": 1, "Normal": 2, "Unknown": 3}
    return sorted(rows, key=lambda x: (rank.get(x["Status"], 9), x["Asset"], x["Metric"]))


def condition_trend(store, asset_uuid, metric):
    rows = [r for r in store.get("condition_readings", []) if r.get("asset_uuid") == asset_uuid and r.get("metric") == metric]
    rows.sort(key=lambda r: str(r.get("reading_date", "")))
    return [{"Date": r.get("reading_date"), "Value": float(r.get("value", 0) or 0), "Status": r.get("condition_status", "Unknown")} for r in rows]


def risk_score(safety=1, production=1, quality=1, repair_lead=1, likelihood=1):
    vals = [max(1, min(5, int(x))) for x in [safety, production, quality, repair_lead]]
    likelihood = max(1, min(5, int(likelihood)))
    consequence = sum(vals)
    score = consequence * likelihood
    if score >= 60:
        band = "Critical"
    elif score >= 40:
        band = "High"
    elif score >= 20:
        band = "Moderate"
    else:
        band = "Low"
    return score, band, consequence


def save_risk_assessment(store, asset_uuid, safety, production, quality, repair_lead, likelihood, notes=""):
    ensure_control_collections(store)
    score, band, consequence = risk_score(safety, production, quality, repair_lead, likelihood)
    existing = next((r for r in store["risk_assessments"] if r.get("asset_uuid") == asset_uuid), None)
    payload = {
        "asset_uuid": asset_uuid, "safety_score": int(safety), "production_score": int(production),
        "quality_score": int(quality), "repair_lead_score": int(repair_lead), "likelihood_score": int(likelihood),
        "consequence_score": consequence, "risk_score": score, "risk_band": band,
        "assessment_date": date.today().isoformat(), "notes": notes,
    }
    if existing:
        existing.update(payload); existing["updated_at"] = now_iso(); r = existing
    else:
        r = base_record("risk_assessment", f"Risk assessment - {asset_label_by_uuid(store, asset_uuid)}", "")
        r.update(payload); store["risk_assessments"].append(r)
    asset = by_uuid(store.get("assets", [])).get(asset_uuid)
    if asset:
        asset["risk_score"] = score; asset["risk_band"] = band; asset["criticality"] = band if band != "Moderate" else "Medium"; asset["updated_at"] = now_iso()
    return r


def rca_recommendations(store, downtime_threshold=4.0, cost_threshold=1000.0, repeat_threshold=2):
    repeats = recurring_failures(store, repeat_threshold)
    repeat_keys = {(x.get("Asset"), str(x.get("Failure / cause", "")).lower()) for x in repeats}
    rows = []
    risk_by_asset = {r.get("asset_uuid"): r for r in store.get("risk_assessments", [])}
    for m in store.get("maintenance", []):
        if m.get("maintenance_type") != "Breakdown":
            continue
        reasons = []
        asset_name = asset_label_by_uuid(store, m.get("asset_uuid")) or "Unassigned"
        downtime = float(m.get("downtime_hours", 0) or 0)
        total_cost = float(m.get("total_maintenance_cost", 0) or 0)
        risk = risk_by_asset.get(m.get("asset_uuid"), {})
        if downtime >= float(downtime_threshold): reasons.append(f"Downtime {downtime:.1f} h")
        if total_cost >= float(cost_threshold): reasons.append(f"Cost ${total_cost:,.0f}")
        if risk.get("risk_band") in ["High", "Critical"]: reasons.append(f"{risk.get('risk_band')} asset risk")
        cause = (m.get("failure_category") or m.get("diagnosis") or m.get("symptom") or m.get("title") or "").strip().lower()
        if (asset_name, cause[:120]) in repeat_keys: reasons.append("Recurring failure")
        if m.get("safety_impact"): reasons.append("Safety impact")
        if m.get("quality_impact"): reasons.append("Quality impact")
        if reasons and not m.get("linked_rca_uuids"):
            rows.append({"Breakdown UUID": m.get("system_uuid"), "Asset": asset_name, "Date": m.get("event_date", ""), "Breakdown": record_label(m), "Recommendation": "; ".join(reasons)})
    return rows


def add_handover_note(store, title, department="", owner="", priority="Normal", detail="", asset_uuid="", due_date=None):
    ensure_control_collections(store)
    r = base_record("handover_note", title, department)
    r.update({"owner": owner, "priority": priority, "detail": detail, "asset_uuid": asset_uuid,
              "status": "Open", "due_date": (parse_date(due_date) or date.today()).isoformat()})
    store["handover_notes"].append(r)
    return r


def handover_snapshot(store, horizon_days=7):
    ensure_control_collections(store)
    today = date.today(); horizon = today + timedelta(days=int(horizon_days))
    down_assets = [a for a in store.get("assets", []) if a.get("status") in ["Under Repair", "Down", "Out of Service"]]
    open_wos = [w for w in store.get("work_orders", []) if w.get("status") not in ["Complete", "Closed", "Cancelled"]]
    urgent_actions = [a for a in store.get("actions", []) if a.get("status") not in ["Complete", "Closed"] and a.get("priority") in ["High", "Critical"]]
    pm_due = []
    for p in store.get("pm_schedules", []):
        d = parse_date(p.get("next_due_date"))
        if d and d <= horizon:
            pm_due.append(p)
    upcoming_shutdowns = []
    for s in store.get("shutdowns", []):
        d = parse_date(s.get("start_date"))
        if d and today <= d <= horizon:
            upcoming_shutdowns.append(s)
    condition_alerts = [r for r in condition_summary(store) if r.get("Status") in ["Warning", "Critical"]]
    awaiting = [a for a in store.get("actions", []) if a.get("status") in ["Awaiting Parts", "Awaiting Supplier"]]
    notes = [n for n in store.get("handover_notes", []) if n.get("status") != "Closed"]
    return {
        "down_assets": down_assets, "open_work_orders": open_wos, "urgent_actions": urgent_actions,
        "pm_due": pm_due, "upcoming_shutdowns": upcoming_shutdowns, "condition_alerts": condition_alerts,
        "awaiting": awaiting, "handover_notes": notes,
    }

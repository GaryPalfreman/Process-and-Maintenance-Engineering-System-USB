import json
from copy import deepcopy
from datetime import date, datetime, timedelta

from engineering_system import base_record, by_uuid, now_iso, parse_date, record_label, asset_label_by_uuid, store_bytes
from next_layer import spare_stock_status, asset_history

READINESS_COLLECTIONS = [
    "quick_capture", "engineering_diary", "decisions", "engineering_changes",
    "lessons_learned", "references", "archive_log"
]

SEARCH_MODULES = [
    "assets", "actions", "maintenance", "pm_schedules", "process_improvements", "trials",
    "research", "rca", "products", "process_routes", "tooling", "spares", "pm_templates",
    "work_orders", "shutdowns", "condition_readings", "asset_risk", "handover_notes",
    "quick_capture", "engineering_diary", "decisions", "engineering_changes", "lessons_learned", "references"
]

DISPLAY_PREFIX = {
    "assets": "AST", "actions": "ACT", "maintenance": "MNT", "pm_schedules": "PM",
    "process_improvements": "PI", "trials": "ETR", "research": "RES", "rca": "RCA",
    "products": "PRD", "process_routes": "RTE", "tooling": "TLG", "spares": "SPR",
    "pm_templates": "PMT", "work_orders": "WO", "shutdowns": "SD", "condition_readings": "CM",
    "asset_risk": "RSK", "handover_notes": "HND", "quick_capture": "INB",
    "engineering_diary": "DIA", "decisions": "DEC", "engineering_changes": "EC",
    "lessons_learned": "LL", "references": "REF"
}


def ensure_readiness_collections(store):
    for key in READINESS_COLLECTIONS:
        store.setdefault(key, [])
    store.setdefault("settings", {})
    store["settings"].setdefault("display_id_counters", {})
    store["settings"].setdefault("backup_reminder_days", 1)
    store["settings"].setdefault("last_backup_at", "")
    return store


def next_display_id(store, module):
    ensure_readiness_collections(store)
    counters = store["settings"]["display_id_counters"]
    current = int(counters.get(module, 0) or 0) + 1
    counters[module] = current
    return f"{DISPLAY_PREFIX.get(module, 'REC')}-{current:04d}"


def assign_display_id(store, module, record, overwrite=False):
    if overwrite or not str(record.get("business_id", "")).strip():
        record["business_id"] = next_display_id(store, module)
        record["updated_at"] = now_iso()
    return record


def create_quick_capture(store, capture_type, title, notes, department="", asset_uuid="", priority="Medium", due_date=None):
    ensure_readiness_collections(store)
    r = base_record("quick_capture", title, department)
    r.update({
        "capture_type": capture_type,
        "notes": notes,
        "asset_uuid": asset_uuid,
        "priority": priority,
        "status": "Inbox",
        "due_date": (parse_date(due_date).isoformat() if parse_date(due_date) else ""),
        "captured_at": now_iso(),
    })
    assign_display_id(store, "quick_capture", r)
    store["quick_capture"].append(r)
    return r


def promote_capture(store, capture_uuid, target_module):
    ensure_readiness_collections(store)
    src = by_uuid(store["quick_capture"]).get(capture_uuid)
    if not src:
        raise KeyError("Quick Capture item not found")
    mapping = {
        "actions": ("engineering_action", "Open"),
        "maintenance": ("maintenance", "Planned"),
        "trials": ("engineering_trial", "Planned"),
        "research": ("research", "Open"),
        "engineering_changes": ("engineering_change", "Draft"),
        "engineering_diary": ("engineering_diary", "Recorded"),
    }
    if target_module not in mapping:
        raise ValueError("Unsupported promotion target")
    record_type, status = mapping[target_module]
    r = base_record(record_type, src.get("title", ""), src.get("department", ""))
    r.update({
        "asset_uuid": src.get("asset_uuid", ""),
        "priority": src.get("priority", "Medium"),
        "status": status,
        "source_capture_uuid": capture_uuid,
        "notes": src.get("notes", ""),
        "detail": src.get("notes", ""),
        "due_date": src.get("due_date", ""),
    })
    assign_display_id(store, target_module, r)
    store.setdefault(target_module, []).append(r)
    src["status"] = "Promoted"
    src["promoted_to_module"] = target_module
    src["promoted_to_uuid"] = r["system_uuid"]
    src["updated_at"] = now_iso()
    return r


def create_diary_entry(store, title, notes, entry_date=None, category="Engineering", asset_uuid="", linked_module="", linked_uuid=""):
    ensure_readiness_collections(store)
    r = base_record("engineering_diary", title, "")
    r.update({
        "entry_date": (parse_date(entry_date) or date.today()).isoformat(),
        "category": category,
        "notes": notes,
        "asset_uuid": asset_uuid,
        "linked_module": linked_module,
        "linked_uuid": linked_uuid,
        "status": "Recorded",
    })
    assign_display_id(store, "engineering_diary", r)
    store["engineering_diary"].append(r)
    return r


def create_decision(store, title, decision, rationale, evidence="", alternatives="", outcome="", asset_uuid="", related_uuid=""):
    ensure_readiness_collections(store)
    r = base_record("engineering_decision", title, "")
    r.update({
        "decision_date": date.today().isoformat(), "decision": decision, "rationale": rationale,
        "evidence": evidence, "alternatives": alternatives, "outcome": outcome,
        "asset_uuid": asset_uuid, "related_uuid": related_uuid, "status": "Active"
    })
    assign_display_id(store, "decisions", r)
    store["decisions"].append(r)
    return r


def create_engineering_change(store, title, problem, existing_state, proposed_change, department="", asset_uuid="", product_uuid="", owner=""):
    ensure_readiness_collections(store)
    r = base_record("engineering_change", title, department)
    r.update({
        "problem": problem, "existing_state": existing_state, "proposed_change": proposed_change,
        "risk_assessment": "", "trial_uuid": "", "decision_uuid": "", "implementation": "",
        "validation": "", "before_after_result": "", "final_standard_reference": "",
        "asset_uuid": asset_uuid, "product_uuid": product_uuid, "owner": owner,
        "status": "Draft", "stage": "Problem Definition"
    })
    assign_display_id(store, "engineering_changes", r)
    store["engineering_changes"].append(r)
    return r


def create_lesson(store, title, lesson, context="", recommendation="", asset_uuid="", material="", product="", source_uuid=""):
    ensure_readiness_collections(store)
    r = base_record("lesson_learned", title, "")
    r.update({
        "lesson": lesson, "context": context, "recommendation": recommendation,
        "asset_uuid": asset_uuid, "material": material, "product": product,
        "source_uuid": source_uuid, "status": "Active"
    })
    assign_display_id(store, "lessons_learned", r)
    store["lessons_learned"].append(r)
    return r


def create_reference(store, title, reference_type, location, description="", asset_uuid="", related_uuid=""):
    ensure_readiness_collections(store)
    r = base_record("reference", title, "")
    r.update({
        "reference_type": reference_type, "location": location, "description": description,
        "asset_uuid": asset_uuid, "related_uuid": related_uuid, "status": "Active"
    })
    assign_display_id(store, "references", r)
    store["references"].append(r)
    return r


def clone_record(store, module, uid):
    source = by_uuid(store.get(module, [])).get(uid)
    if not source:
        raise KeyError("Record not found")
    r = deepcopy(source)
    new = base_record(source.get("record_type", module.rstrip("s")), f"Copy of {source.get('title','')}", source.get("department", ""))
    keep_uuid = new["system_uuid"]
    keep_created = new["created_at"]
    r.update(new)
    r["system_uuid"] = keep_uuid
    r["created_at"] = keep_created
    r["updated_at"] = keep_created
    r["business_id"] = ""
    r["legacy_id"] = ""
    r["alias"] = ""
    r["cloned_from_uuid"] = uid
    r["status"] = "Draft" if "status" in source else r.get("status", "")
    assign_display_id(store, module, r)
    store[module].append(r)
    return r


def set_lifecycle(store, module, uid, lifecycle):
    r = by_uuid(store.get(module, [])).get(uid)
    if not r:
        raise KeyError("Record not found")
    r["lifecycle"] = lifecycle
    r["archived"] = lifecycle == "Archived"
    r["updated_at"] = now_iso()
    if lifecycle == "Archived":
        ensure_readiness_collections(store)
        store["archive_log"].append({"module": module, "record_uuid": uid, "archived_at": now_iso(), "label": record_label(r)})
    return r


def global_search(store, query, include_archived=False):
    q = str(query or "").strip().lower()
    if not q:
        return []
    rows = []
    for module in SEARCH_MODULES:
        for r in store.get(module, []):
            if not include_archived and (r.get("archived") or r.get("lifecycle") == "Archived"):
                continue
            hay = json.dumps(r, ensure_ascii=False, default=str).lower()
            if q not in hay:
                continue
            rows.append({
                "Module": module.replace("_", " ").title(), "Record": record_label(r),
                "Department": r.get("department", ""), "Status": r.get("status", r.get("lifecycle", "")),
                "Asset": asset_label_by_uuid(store, r.get("asset_uuid", "")), "UUID": r.get("system_uuid", "")
            })
    return rows


def engineering_inbox(store, horizon_days=7):
    ensure_readiness_collections(store)
    today = date.today(); end = today + timedelta(days=int(horizon_days))
    rows = []
    for r in store.get("quick_capture", []):
        if r.get("status") == "Inbox":
            rows.append({"Type":"Quick Capture","Priority":r.get("priority",""),"Due":r.get("due_date",""),"Item":record_label(r),"Asset":asset_label_by_uuid(store,r.get("asset_uuid",""))})
    for r in store.get("actions", []):
        if r.get("status") in ["Complete","Closed"]: continue
        due=parse_date(r.get("due_date"))
        if due and due <= end:
            rows.append({"Type":"Engineering Action","Priority":r.get("priority",""),"Due":due.isoformat(),"Item":record_label(r),"Asset":asset_label_by_uuid(store,r.get("asset_uuid",""))})
    for r in store.get("pm_schedules", []):
        due=parse_date(r.get("next_due_date"))
        if due and due <= end:
            rows.append({"Type":"PM","Priority":"High" if due<today else "Medium","Due":due.isoformat(),"Item":record_label(r),"Asset":asset_label_by_uuid(store,r.get("asset_uuid",""))})
    for r in store.get("work_orders", []):
        if r.get("status") in ["Complete","Closed","Cancelled"]: continue
        due=parse_date(r.get("due_date"))
        if not due or due <= end:
            rows.append({"Type":"Work Order","Priority":r.get("priority",""),"Due":r.get("due_date",""),"Item":record_label(r),"Asset":asset_label_by_uuid(store,r.get("asset_uuid",""))})
    for r in store.get("condition_readings", []):
        if r.get("condition_status") in ["Warning","Critical"]:
            rows.append({"Type":"Condition Alert","Priority":r.get("condition_status",""),"Due":r.get("reading_date",""),"Item":record_label(r),"Asset":asset_label_by_uuid(store,r.get("asset_uuid",""))})
    rank={"Critical":0,"High":1,"Warning":1,"Medium":2,"Low":3,"":4}
    return sorted(rows,key=lambda x:(rank.get(x["Priority"],5),x["Due"] or "9999"))


def my_engineering_day(store):
    inbox=engineering_inbox(store,1)
    down=[a for a in store.get("assets",[]) if a.get("status") in ["Under Repair","Down"]]
    stock=[s for s in store.get("spares",[]) if spare_stock_status(s) in ["Low Stock","Out of Stock"]]
    return {
        "attention": inbox,
        "assets_down": down,
        "stock_warnings": stock,
        "open_changes": [r for r in store.get("engineering_changes",[]) if r.get("status") not in ["Complete","Closed","Archived"]],
    }


def asset_360(store, asset_uuid):
    asset=by_uuid(store.get("assets",[])).get(asset_uuid)
    if not asset: return {}
    linked={}
    fields=[
        ("maintenance","event_date"),("pm_schedules","next_due_date"),("actions","due_date"),
        ("work_orders","due_date"),("condition_readings","reading_date"),("process_improvements","created_at"),
        ("trials","trial_date"),("rca","created_at"),("tooling","created_at"),("spares","created_at"),
        ("engineering_changes","created_at"),("lessons_learned","created_at"),("references","created_at")
    ]
    for module,_ in fields:
        linked[module]=[r for r in store.get(module,[]) if r.get("asset_uuid")==asset_uuid or asset_uuid in (r.get("related_asset_uuids") or [])]
    history=asset_history(store,asset_uuid)
    for module in ["work_orders","condition_readings","engineering_changes","lessons_learned","references"]:
        for r in linked.get(module,[]):
            history.append({"Date":str(r.get("event_date") or r.get("reading_date") or r.get("due_date") or r.get("created_at",''))[:10],"Type":module.replace('_',' ').title(),"Record":record_label(r),"Status":r.get("status",r.get("condition_status","")),"Owner":r.get("owner","")})
    history=sorted(history,key=lambda x:x.get("Date",''),reverse=True)
    return {"asset":asset,"linked":linked,"history":history}


def data_quality_issues(store):
    rows=[]
    assets={r.get("system_uuid") for r in store.get("assets",[])}
    asset_with_pm={r.get("asset_uuid") for r in store.get("pm_schedules",[]) if r.get("asset_uuid")}
    for a in store.get("assets",[]):
        if a.get("status","Active")=="Active" and a.get("system_uuid") not in asset_with_pm:
            rows.append({"Severity":"Medium","Module":"Assets","Record":record_label(a),"Issue":"Active asset has no PM schedule"})
    for r in store.get("maintenance",[]):
        if r.get("asset_uuid") and r.get("asset_uuid") not in assets:
            rows.append({"Severity":"High","Module":"Maintenance","Record":record_label(r),"Issue":"Linked asset UUID is missing"})
        if r.get("maintenance_type")=="Breakdown" and not (r.get("failure_category") or r.get("diagnosis")):
            rows.append({"Severity":"Medium","Module":"Maintenance","Record":record_label(r),"Issue":"Breakdown has no failure category / diagnosis"})
    for r in store.get("work_orders",[]):
        if r.get("status") in ["Complete","Closed"] and not r.get("completion_notes"):
            rows.append({"Severity":"Medium","Module":"Work Orders","Record":record_label(r),"Issue":"Completed work order has no completion notes"})
    for r in store.get("spares",[]):
        if float(r.get("minimum_stock",0) or 0)<=0:
            rows.append({"Severity":"Low","Module":"Spares","Record":record_label(r),"Issue":"No minimum stock level set"})
    for r in store.get("actions",[]):
        due=parse_date(r.get("due_date"))
        if due and due<date.today() and r.get("status") not in ["Complete","Closed"]:
            rows.append({"Severity":"High","Module":"Actions","Record":record_label(r),"Issue":"Action is overdue"})
    return rows


def orphan_links(store):
    all_uuids=set()
    for module in SEARCH_MODULES:
        all_uuids.update(r.get("system_uuid") for r in store.get(module,[]) if r.get("system_uuid"))
    link_fields=["asset_uuid","product_uuid","pm_schedule_uuid","source_maintenance_uuid","linked_uuid","related_uuid","trial_uuid","decision_uuid"]
    rows=[]
    for module in SEARCH_MODULES:
        for r in store.get(module,[]):
            for f in link_fields:
                val=r.get(f)
                if val and val not in all_uuids:
                    rows.append({"Module":module,"Record":record_label(r),"Field":f,"Missing UUID":val})
    return rows


def system_health(store):
    ensure_readiness_collections(store)
    counts={m:len(store.get(m,[])) for m in SEARCH_MODULES if m in store}
    last=store.get("settings",{}).get("last_backup_at","")
    last_dt=None
    try: last_dt=datetime.fromisoformat(last) if last else None
    except Exception: pass
    age_hours=((datetime.now()-last_dt).total_seconds()/3600) if last_dt else None
    return {
        "schema":store.get("schema",""), "version":store.get("version",""), "record_counts":counts,
        "total_records":sum(counts.values()), "quality_issues":len(data_quality_issues(store)),
        "orphan_links":len(orphan_links(store)), "last_backup_at":last,
        "backup_age_hours":age_hours,
    }


def mark_backup_created(store):
    ensure_readiness_collections(store)
    store["settings"]["last_backup_at"]=now_iso()
    return store["settings"]["last_backup_at"]


def backup_due(store):
    ensure_readiness_collections(store)
    days=max(1,int(store["settings"].get("backup_reminder_days",1) or 1))
    last=store["settings"].get("last_backup_at","")
    if not last: return True
    try: return datetime.now()-datetime.fromisoformat(last)>=timedelta(days=days)
    except Exception: return True


def validate_restore_bytes(payload):
    try:
        data=json.loads(payload.decode("utf-8"))
    except Exception as exc:
        return False,f"Invalid JSON: {exc}",None
    if data.get("schema")!="process-maintenance-engineering-system":
        return False,"Schema does not match this engineering system.",None
    if not isinstance(data.get("settings",{}),dict):
        return False,"Settings section is invalid.",None
    return True,"Backup structure is valid.",data


def session_snapshot(store):
    return store_bytes(store)

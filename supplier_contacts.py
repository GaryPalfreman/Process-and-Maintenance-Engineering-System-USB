from datetime import date, datetime
from uuid import uuid4

SUPPLIER_COLLECTIONS = [
    "supplier_companies", "supplier_contacts", "engagement_procedures",
    "supplier_relationships", "supplier_usage"
]

COMPANY_STATUSES = ["Preferred", "Approved / Used", "Alternative", "Trial / Prospective", "Do Not Use", "Inactive"]
COMPANY_TYPES = [
    "Machine Manufacturer", "Machine Service & Repair", "Tooling Supplier", "Consumables Supplier",
    "Spare Parts Supplier", "Equipment Supplier", "Electrical Contractor", "Mechanical Contractor",
    "Laser Specialist", "Grinding Specialist", "Calibration / Metrology", "Filtration / Coolant",
    "Automation / Controls", "Software / Technical Support", "General Engineering", "Other"
]
PROCEDURE_TYPES = [
    "Service & Repair", "Emergency Breakdown", "Spare Parts", "Tooling Purchase",
    "Consumables Purchase", "Equipment Purchase / RFQ", "Technical Support", "Calibration",
    "Contractor Attendance", "Warranty Claim", "Other"
]
RELATIONSHIP_ROLES = [
    "OEM / Manufacturer", "External Service", "Emergency Breakdown Support", "Technical Support",
    "Preferred Tooling Supplier", "Preferred Spare Parts Supplier", "Consumables Supplier",
    "Equipment Vendor", "Calibration Provider", "Electrical Support", "Mechanical Support",
    "Controls / Automation Support", "Other"
]
TARGET_MODULES = ["assets", "tooling", "spares", "research", "work_orders", "maintenance", "products"]


def now_iso():
    return datetime.now().replace(microsecond=0).isoformat()


def ensure_supplier_collections(store):
    for key in SUPPLIER_COLLECTIONS:
        store.setdefault(key, [])
    return store


def _record(title, record_type):
    ts = now_iso()
    return {
        "system_uuid": str(uuid4()), "record_type": record_type, "title": title,
        "created_at": ts, "updated_at": ts, "archived": False
    }


def by_uuid(rows):
    return {r.get("system_uuid"): r for r in rows if r.get("system_uuid")}


def company_label(company):
    if not company:
        return ""
    name = company.get("company_name") or company.get("title") or "Unnamed Company"
    status = company.get("status", "")
    return f"{name} — {status}" if status else name


def contact_label(contact):
    if not contact:
        return ""
    name = contact.get("contact_name") or contact.get("title") or "Unnamed Contact"
    role = contact.get("role", "")
    return f"{name} — {role}" if role else name


def target_label(record):
    if not record:
        return ""
    for field in ["business_id", "title", "name", "asset_name", "product_name", "part_number", "manufacturer_part_number"]:
        if str(record.get(field, "")).strip():
            return str(record[field])
    return record.get("system_uuid", "")


def create_company(store, company_name, company_types, status="Approved / Used", phone="", email="", website="", address="", account_number="", after_hours="", capabilities="", notes=""):
    ensure_supplier_collections(store)
    r = _record(company_name, "supplier_company")
    r.update({
        "company_name": company_name, "company_types": list(company_types or []), "status": status,
        "phone": phone, "email": email, "website": website, "address": address,
        "account_number": account_number, "after_hours": after_hours,
        "capabilities": capabilities, "notes": notes,
        "last_used_date": "", "use_count": 0
    })
    store["supplier_companies"].append(r)
    return r


def create_contact(store, company_uuid, contact_name, role="", phone="", mobile="", email="", preferred_method="Email", availability="", responsibilities="", notes="", active=True):
    ensure_supplier_collections(store)
    r = _record(contact_name, "supplier_contact")
    r.update({
        "company_uuid": company_uuid, "contact_name": contact_name, "role": role,
        "phone": phone, "mobile": mobile, "email": email, "preferred_method": preferred_method,
        "availability": availability, "responsibilities": responsibilities, "notes": notes,
        "active": bool(active)
    })
    store["supplier_contacts"].append(r)
    return r


def create_procedure(store, company_uuid, procedure_type, title, contact_uuid="", preferred_method="", first_step="", required_information="", approval_po_process="", steps="", emergency_process="", notes=""):
    ensure_supplier_collections(store)
    r = _record(title, "engagement_procedure")
    r.update({
        "company_uuid": company_uuid, "contact_uuid": contact_uuid, "procedure_type": procedure_type,
        "preferred_method": preferred_method, "first_step": first_step,
        "required_information": required_information, "approval_po_process": approval_po_process,
        "steps": steps, "emergency_process": emergency_process, "notes": notes, "status": "Active"
    })
    store["engagement_procedures"].append(r)
    return r


def create_relationship(store, company_uuid, target_module, target_uuid, role, contact_uuid="", procedure_uuid="", preferred=True, notes=""):
    ensure_supplier_collections(store)
    r = _record(role, "supplier_relationship")
    r.update({
        "company_uuid": company_uuid, "contact_uuid": contact_uuid, "procedure_uuid": procedure_uuid,
        "target_module": target_module, "target_uuid": target_uuid, "role": role,
        "preferred": bool(preferred), "notes": notes, "status": "Active"
    })
    store["supplier_relationships"].append(r)
    return r


def log_supplier_usage(store, company_uuid, usage_type, summary, usage_date=None, contact_uuid="", target_module="", target_uuid="", reference="", response_hours=0.0, cost=0.0, result="", rating=0, notes=""):
    ensure_supplier_collections(store)
    r = _record(summary, "supplier_usage")
    r.update({
        "company_uuid": company_uuid, "contact_uuid": contact_uuid,
        "usage_date": (usage_date or date.today()).isoformat() if hasattr((usage_date or date.today()), "isoformat") else str(usage_date),
        "usage_type": usage_type, "summary": summary, "target_module": target_module,
        "target_uuid": target_uuid, "reference": reference,
        "response_hours": float(response_hours or 0), "cost": float(cost or 0),
        "result": result, "rating": int(rating or 0), "notes": notes
    })
    store["supplier_usage"].append(r)
    company = by_uuid(store["supplier_companies"]).get(company_uuid)
    if company:
        company["last_used_date"] = r["usage_date"]
        company["use_count"] = int(company.get("use_count", 0) or 0) + 1
        company["updated_at"] = now_iso()
    return r


def set_company_status(store, company_uuid, status):
    company = by_uuid(store.get("supplier_companies", [])).get(company_uuid)
    if not company:
        raise KeyError("Company not found")
    company["status"] = status
    company["updated_at"] = now_iso()
    return company


def archive_record(store, module, record_uuid, archived=True):
    record = by_uuid(store.get(module, [])).get(record_uuid)
    if not record:
        raise KeyError("Record not found")
    record["archived"] = bool(archived)
    record["updated_at"] = now_iso()
    if module == "supplier_contacts":
        record["active"] = not archived
    if module == "supplier_companies" and archived:
        record["status"] = "Inactive"
    return record


def relationships_for_target(store, target_module, target_uuid):
    ensure_supplier_collections(store)
    companies = by_uuid(store["supplier_companies"])
    contacts = by_uuid(store["supplier_contacts"])
    procedures = by_uuid(store["engagement_procedures"])
    out = []
    for r in store["supplier_relationships"]:
        if r.get("archived") or r.get("target_module") != target_module or r.get("target_uuid") != target_uuid:
            continue
        c = companies.get(r.get("company_uuid"), {})
        p = contacts.get(r.get("contact_uuid"), {})
        proc = procedures.get(r.get("procedure_uuid"), {})
        out.append({
            "Role": r.get("role", ""), "Company": c.get("company_name", ""),
            "Company Status": c.get("status", ""), "Contact": p.get("contact_name", ""),
            "Phone": p.get("mobile") or p.get("phone") or c.get("phone", ""),
            "Email": p.get("email") or c.get("email", ""),
            "Preferred Contact": p.get("preferred_method") or proc.get("preferred_method", ""),
            "Procedure": proc.get("title", ""), "Preferred": r.get("preferred", False),
            "Notes": r.get("notes", "")
        })
    return out


def company_performance(store, company_uuid):
    rows = [r for r in store.get("supplier_usage", []) if r.get("company_uuid") == company_uuid and not r.get("archived")]
    if not rows:
        return {"jobs": 0, "spend": 0.0, "avg_response_hours": 0.0, "avg_rating": 0.0, "last_used": ""}
    ratings = [float(r.get("rating", 0) or 0) for r in rows if float(r.get("rating", 0) or 0) > 0]
    responses = [float(r.get("response_hours", 0) or 0) for r in rows if float(r.get("response_hours", 0) or 0) > 0]
    return {
        "jobs": len(rows), "spend": sum(float(r.get("cost", 0) or 0) for r in rows),
        "avg_response_hours": (sum(responses) / len(responses)) if responses else 0.0,
        "avg_rating": (sum(ratings) / len(ratings)) if ratings else 0.0,
        "last_used": max((r.get("usage_date", "") for r in rows), default="")
    }


def directory_rows(store, include_inactive=False):
    ensure_supplier_collections(store)
    contacts = by_uuid(store["supplier_contacts"])
    procedures = store["engagement_procedures"]
    rows = []
    for company in store["supplier_companies"]:
        if company.get("archived"):
            continue
        if not include_inactive and company.get("status") in ["Inactive", "Do Not Use"]:
            continue
        company_contacts = [c for c in contacts.values() if c.get("company_uuid") == company.get("system_uuid") and c.get("active", True) and not c.get("archived")]
        company_procs = [p for p in procedures if p.get("company_uuid") == company.get("system_uuid") and not p.get("archived")]
        perf = company_performance(store, company.get("system_uuid"))
        primary = company_contacts[0] if company_contacts else {}
        rows.append({
            "Company": company.get("company_name", ""), "Status": company.get("status", ""),
            "Type / Capability": ", ".join(company.get("company_types", [])),
            "Primary Contact": primary.get("contact_name", ""),
            "Phone": primary.get("mobile") or primary.get("phone") or company.get("phone", ""),
            "Email": primary.get("email") or company.get("email", ""),
            "Procedures": len(company_procs), "Uses": perf["jobs"], "Last Used": perf["last_used"],
            "Rating": round(perf["avg_rating"], 1) if perf["avg_rating"] else ""
        })
    return rows


def search_directory(store, query):
    q = str(query or "").strip().lower()
    if not q:
        return []
    ensure_supplier_collections(store)
    companies = by_uuid(store["supplier_companies"])
    rows = []
    for c in store["supplier_contacts"]:
        company = companies.get(c.get("company_uuid"), {})
        hay = " ".join(str(x) for x in [company, c]).lower()
        if q in hay:
            rows.append({"Type": "Contact", "Company": company.get("company_name", ""), "Name": c.get("contact_name", ""), "Role": c.get("role", ""), "Phone": c.get("mobile") or c.get("phone", ""), "Email": c.get("email", "")})
    for company in store["supplier_companies"]:
        if q in str(company).lower():
            rows.append({"Type": "Company", "Company": company.get("company_name", ""), "Name": "", "Role": ", ".join(company.get("company_types", [])), "Phone": company.get("phone", ""), "Email": company.get("email", "")})
    return rows

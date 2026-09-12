from datetime import date, timedelta
from engineering_system import base_record, now_iso, parse_date, by_uuid, record_label, asset_label_by_uuid

def advance_due_date(from_date, frequency, custom_days=0):
    d=parse_date(from_date) or date.today(); f=(frequency or "").lower()
    if f=="daily": return d+timedelta(days=1)
    if f=="weekly": return d+timedelta(days=7)
    if f in ("monthly","quarterly","6 monthly"):
        months={"monthly":1,"quarterly":3,"6 monthly":6}[f]
        import calendar
        y,m=d.year,d.month
        for _ in range(months):
            m+=1
            if m>12: m=1; y+=1
        return date(y,m,min(d.day,calendar.monthrange(y,m)[1]))
    if f=="annual":
        try: return d.replace(year=d.year+1)
        except ValueError: return d.replace(year=d.year+1,day=28)
    if f=="custom" and int(custom_days or 0)>0: return d+timedelta(days=int(custom_days))
    return None

def update_record(store,module,uid,changes):
    for r in store.get(module,[]):
        if r.get("system_uuid")==uid:
            for k,v in changes.items():
                if k not in {"system_uuid","created_at","record_type"}: r[k]=v
            r["updated_at"]=now_iso(); return r
    raise KeyError("Record not found")

def complete_pm(store,schedule_uuid,completion_date=None,technician="",notes="",labour_hours=0.0,parts_used=""):
    schedule=by_uuid(store.get("pm_schedules",[])).get(schedule_uuid)
    if not schedule: raise KeyError("PM schedule not found")
    completed=parse_date(completion_date) or date.today()
    m=base_record("maintenance",f"PM - {schedule.get('title','')}",schedule.get("department",""))
    m.update({"maintenance_type":"Preventive","asset_uuid":schedule.get("asset_uuid",""),"event_date":completed.isoformat(),"status":"Complete","owner":technician or schedule.get("owner",""),"repair_hours":float(labour_hours or 0),"downtime_hours":0.0,"pm_schedule_uuid":schedule_uuid,"symptom":"Scheduled preventive maintenance","diagnosis":"","action_taken":notes,"parts_used":parts_used,"verification":"PM completed"})
    store.setdefault("maintenance",[]).append(m)
    schedule["last_completed_date"]=completed.isoformat(); schedule["last_completed_by"]=technician
    nxt=advance_due_date(completed,schedule.get("frequency"),schedule.get("custom_interval_days",0))
    if nxt: schedule["next_due_date"]=nxt.isoformat()
    schedule["updated_at"]=now_iso()
    return m,nxt

def create_action_from_breakdown(store,maintenance_uuid,owner="",due_date=None):
    m=by_uuid(store.get("maintenance",[])).get(maintenance_uuid)
    if not m: raise KeyError("Breakdown not found")
    r=base_record("engineering_action",f"Follow-up: {m.get('title','Breakdown')}",m.get("department",""))
    r.update({"category":"Maintenance","priority":"High","status":"Open","owner":owner,"due_date":(parse_date(due_date) or date.today()).isoformat(),"asset_uuid":m.get("asset_uuid",""),"detail":f"Created from breakdown dated {m.get('event_date','')}. Review corrective and preventive actions.","source_maintenance_uuid":maintenance_uuid})
    store.setdefault("actions",[]).append(r); m.setdefault("linked_action_uuids",[]).append(r["system_uuid"]); m["updated_at"]=now_iso(); return r

def create_rca_from_breakdown(store,maintenance_uuid,owner=""):
    m=by_uuid(store.get("maintenance",[])).get(maintenance_uuid)
    if not m: raise KeyError("Breakdown not found")
    r=base_record("rca",f"RCA: {m.get('title','Breakdown')}",m.get("department",""))
    r.update({"asset_uuid":m.get("asset_uuid",""),"status":"Open","owner":owner,"problem_statement":m.get("symptom") or m.get("title",""),"containment":m.get("action_taken",""),"evidence":m.get("diagnosis",""),"five_whys":"","root_cause":"","corrective_action":"","preventive_action":"","effectiveness_review":"","source_maintenance_uuid":maintenance_uuid})
    store.setdefault("rca",[]).append(r); m.setdefault("linked_rca_uuids",[]).append(r["system_uuid"]); m["updated_at"]=now_iso(); return r

def create_pm_from_template(store,template_uuid,asset_uuid,first_due=None,owner_override=""):
    t=by_uuid(store.get("pm_templates",[])).get(template_uuid); a=by_uuid(store.get("assets",[])).get(asset_uuid)
    if not t or not a: raise KeyError("Template or asset not found")
    r=base_record("pm_schedule",t.get("title","PM"),a.get("department",""))
    r.update({"asset_uuid":asset_uuid,"frequency":t.get("frequency","Monthly"),"custom_interval_days":int(t.get("custom_interval_days",0) or 0),"next_due_date":(parse_date(first_due) or date.today()).isoformat(),"owner":owner_override or t.get("owner",""),"estimated_hours":float(t.get("estimated_hours",0) or 0),"checklist":t.get("checklist",""),"safety_requirements":t.get("safety_requirements",""),"required_parts":t.get("required_parts",""),"reference":t.get("reference",""),"status":"Active","source_template_uuid":template_uuid})
    store.setdefault("pm_schedules",[]).append(r); return r

def spare_stock_status(spare):
    qty=float(spare.get("quantity_on_hand",0) or 0); minimum=float(spare.get("minimum_stock",0) or 0)
    if minimum<=0: return "No Minimum Set"
    if qty<=0: return "Out of Stock"
    if qty<=minimum: return "Low Stock"
    return "OK"

def low_stock_spares(store):
    return [s for s in store.get("spares",[]) if spare_stock_status(s) in ["Low Stock","Out of Stock"]]

def asset_history(store,asset_uuid):
    events=[]
    mapping=[("maintenance","Maintenance","event_date"),("pm_schedules","PM Schedule","next_due_date"),("actions","Engineering Action","due_date"),("process_improvements","Process Improvement","created_at"),("trials","Engineering Trial","trial_date"),("research","Research","created_at"),("rca","RCA","created_at"),("process_routes","Process Route","created_at"),("tooling","Tooling","created_at"),("spares","Spare","created_at")]
    for module,kind,field in mapping:
        for r in store.get(module,[]):
            if r.get("asset_uuid")!=asset_uuid and asset_uuid not in (r.get("related_asset_uuids") or []): continue
            raw=r.get(field) or r.get("created_at","")
            events.append({"Date":str(raw)[:10],"Type":kind,"Record":record_label(r),"Status":r.get("status",r.get("outcome","")),"Owner":r.get("owner","")})
    return sorted(events,key=lambda x:x["Date"],reverse=True)

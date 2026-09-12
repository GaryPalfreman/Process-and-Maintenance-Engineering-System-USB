from datetime import date
import pandas as pd
import streamlit as st

from engineering_system import blank_store, by_uuid, record_label, asset_label_by_uuid, backup_zip, load_store
from production_readiness import *
from usb_runtime import initialise_page, persist

st.set_page_config(page_title="Production Readiness", page_icon="✅", layout="wide")
_vault, store = initialise_page()
ensure_readiness_collections(store)

if "readiness_snapshot" not in st.session_state:
    st.session_state.readiness_snapshot=session_snapshot(store)


def options(module):
    return {record_label(r):r.get("system_uuid") for r in store.get(module,[])}


def show(rows,msg="No records."):
    if rows:
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    else:
        st.info(msg)


def save_snapshot():
    st.session_state.readiness_snapshot=session_snapshot(store)

st.title("Production Readiness Workspace")
st.caption("Single-user production layer: My Engineering Day, Quick Capture, global search, Asset 360, engineering change control, knowledge capture, lifecycle control and data safety.")

if backup_due(store):
    st.warning("Backup reminder: create and download a current system backup before or after today's engineering work.")

tabs=st.tabs(["My Engineering Day","Quick Capture & Inbox","Global Search","Asset 360","Engineering Changes","Knowledge & Diary","Record Control","Data Quality & Health","Backup & Recovery"])

with tabs[0]:
    st.subheader("My Engineering Day")
    day=my_engineering_day(store)
    c=st.columns(4)
    c[0].metric("Needs attention",len(day["attention"]))
    c[1].metric("Assets down",len(day["assets_down"]))
    c[2].metric("Stock warnings",len(day["stock_warnings"]))
    c[3].metric("Open engineering changes",len(day["open_changes"]))
    st.markdown("#### Today's attention list")
    show(day["attention"],"Nothing urgent is due today.")
    left,right=st.columns(2)
    with left:
        st.markdown("#### Assets down / under repair")
        show([{"Asset":record_label(a),"Department":a.get("department",""),"Criticality":a.get("criticality",""),"Status":a.get("status","")} for a in day["assets_down"]],"No assets marked down.")
    with right:
        st.markdown("#### Stock warnings")
        show([{"Part":record_label(s),"Asset":asset_label_by_uuid(store,s.get("asset_uuid","")),"On Hand":s.get("quantity_on_hand",0),"Minimum":s.get("minimum_stock",0),"Status":spare_stock_status(s)} for s in day["stock_warnings"]],"No stock warnings.")

with tabs[1]:
    st.subheader("Quick Capture")
    amap=options("assets")
    with st.form("quick_capture_form",clear_on_submit=True):
        a=st.columns(4)
        typ=a[0].selectbox("Type",["Breakdown Note","Engineering Issue","Maintenance","Process Idea","Trial Note","Research Idea","General Note"])
        pri=a[1].selectbox("Priority",["Low","Medium","High","Critical"],index=1)
        dept=a[2].text_input("Department")
        asset=a[3].selectbox("Linked asset",[""]+list(amap))
        title=st.text_input("Short title")
        notes=st.text_area("What happened / what needs attention?")
        due=st.date_input("Follow-up date",date.today())
        submit=st.form_submit_button("Capture in Engineering Inbox",use_container_width=True)
    if submit:
        if not title.strip(): st.error("A short title is required.")
        else:
            save_snapshot(); create_quick_capture(store,typ,title,notes,dept,amap.get(asset,""),pri,due); st.success("Captured."); st.rerun()

    st.markdown("#### Engineering Inbox")
    horizon=st.slider("Inbox horizon (days)",1,30,7,key="inbox_horizon")
    show(engineering_inbox(store,horizon),"Engineering inbox is clear.")

    qmap={record_label(r):r.get("system_uuid") for r in store.get("quick_capture",[]) if r.get("status")=="Inbox"}
    if qmap:
        st.markdown("#### Promote captured item")
        with st.form("promote_capture"):
            item=st.selectbox("Inbox item",list(qmap))
            target=st.selectbox("Promote to",["actions","maintenance","trials","research","engineering_changes","engineering_diary"],format_func=lambda x:x.replace("_"," ").title())
            promote=st.form_submit_button("Promote & Link",use_container_width=True)
        if promote:
            save_snapshot(); promote_capture(store,qmap[item],target); st.success("Item promoted and linked to its source capture."); st.rerun()

with tabs[2]:
    st.subheader("Global Engineering Search")
    query=st.text_input("Search all engineering records",placeholder="machine name, part number, fault, material, product, supplier, RCA, tool...")
    include_archived=st.checkbox("Include archived records")
    if query.strip():
        results=global_search(store,query,include_archived)
        show(results,"No matching engineering records.")
        st.caption(f"{len(results)} result(s)")

with tabs[3]:
    st.subheader("Asset 360")
    amap=options("assets")
    if not amap:
        st.info("Create assets first.")
    else:
        selected=st.selectbox("Asset",list(amap),key="asset360")
        view=asset_360(store,amap[selected]); asset=view.get("asset",{})
        c=st.columns(5)
        c[0].metric("Department",asset.get("department","—")); c[1].metric("Class",asset.get("asset_class","—")); c[2].metric("Criticality",asset.get("criticality","—")); c[3].metric("Status",asset.get("status","—")); c[4].metric("ID",asset.get("business_id") or asset.get("legacy_id") or "—")
        st.markdown("#### Engineering timeline")
        show(view.get("history",[]),"No linked history yet.")
        linked=view.get("linked",{})
        sections=[("Maintenance","maintenance"),("PM Schedules","pm_schedules"),("Work Orders","work_orders"),("Condition Monitoring","condition_readings"),("Actions","actions"),("Process Improvements","process_improvements"),("Trials","trials"),("RCA","rca"),("Engineering Changes","engineering_changes"),("Tooling","tooling"),("Spares","spares"),("Lessons Learned","lessons_learned"),("References","references")]
        for label,module in sections:
            with st.expander(f"{label} ({len(linked.get(module,[]))})"):
                rows=[{"Record":record_label(r),"Status":r.get("status",r.get("condition_status","")),"Date":str(r.get("event_date") or r.get("reading_date") or r.get("due_date") or r.get("created_at",''))[:10]} for r in linked.get(module,[])]
                show(rows,f"No {label.lower()} linked.")

with tabs[4]:
    st.subheader("Engineering Change Register")
    amap,pmap=options("assets"),options("products")
    with st.form("new_change",clear_on_submit=True):
        a=st.columns(4)
        title=a[0].text_input("Change title")
        dept=a[1].text_input("Department")
        asset=a[2].selectbox("Asset",[""]+list(amap))
        product=a[3].selectbox("Product",[""]+list(pmap))
        owner=st.text_input("Owner")
        problem=st.text_area("Problem / opportunity")
        current=st.text_area("Existing state")
        proposed=st.text_area("Proposed change")
        create=st.form_submit_button("Create Engineering Change",use_container_width=True)
    if create:
        if not title.strip(): st.error("Change title is required.")
        else:
            save_snapshot(); create_engineering_change(store,title,problem,current,proposed,dept,amap.get(asset,""),pmap.get(product,""),owner); st.rerun()

    cmap=options("engineering_changes")
    show([{"ID":r.get("business_id",""),"Status":r.get("status",""),"Stage":r.get("stage",""),"Change":r.get("title",""),"Asset":asset_label_by_uuid(store,r.get("asset_uuid","")),"Owner":r.get("owner","")} for r in store.get("engineering_changes",[])],"No engineering changes yet.")
    if cmap:
        st.markdown("#### Develop / progress a change")
        name=st.selectbox("Engineering change",list(cmap),key="change_edit")
        r=by_uuid(store["engineering_changes"])[cmap[name]]
        with st.form("change_progress"):
            a=st.columns(3)
            status=a[0].selectbox("Status",["Draft","Active","Trial","Awaiting Decision","Approved","Implementation","Validation","Complete","Closed"],index=max(0,["Draft","Active","Trial","Awaiting Decision","Approved","Implementation","Validation","Complete","Closed"].index(r.get("status","Draft")) if r.get("status","Draft") in ["Draft","Active","Trial","Awaiting Decision","Approved","Implementation","Validation","Complete","Closed"] else 0))
            stage=a[1].selectbox("Stage",["Problem Definition","Risk Review","Trial","Decision","Implementation","Validation","Standardised"],index=max(0,["Problem Definition","Risk Review","Trial","Decision","Implementation","Validation","Standardised"].index(r.get("stage","Problem Definition")) if r.get("stage","Problem Definition") in ["Problem Definition","Risk Review","Trial","Decision","Implementation","Validation","Standardised"] else 0))
            owner=a[2].text_input("Owner",r.get("owner",""))
            risk=st.text_area("Risk assessment",r.get("risk_assessment",""))
            implementation=st.text_area("Implementation",r.get("implementation",""))
            validation=st.text_area("Validation",r.get("validation",""))
            result=st.text_area("Before / after result",r.get("before_after_result",""))
            standard=st.text_input("Final standard / controlled document reference",r.get("final_standard_reference",""))
            save=st.form_submit_button("Save Engineering Change Progress",use_container_width=True)
        if save:
            save_snapshot(); r.update({"status":status,"stage":stage,"owner":owner,"risk_assessment":risk,"implementation":implementation,"validation":validation,"before_after_result":result,"final_standard_reference":standard,"updated_at":datetime.now().replace(microsecond=0).isoformat()}); st.rerun()

with tabs[5]:
    st.subheader("Engineering Knowledge & Diary")
    k1,k2,k3,k4=st.tabs(["Diary","Decisions","Lessons Learned","References"])
    amap=options("assets")
    with k1:
        with st.form("diary",clear_on_submit=True):
            a=st.columns(3); d=a[0].date_input("Date",date.today()); cat=a[1].selectbox("Category",["Engineering","Maintenance","Process","Trial","Supplier","Meeting","Observation","Follow-up"]); asset=a[2].selectbox("Asset",[""]+list(amap),key="dia_asset")
            title=st.text_input("Diary title"); notes=st.text_area("Notes / decisions / observations")
            ok=st.form_submit_button("Add Diary Entry")
        if ok and title.strip(): save_snapshot(); create_diary_entry(store,title,notes,d,cat,amap.get(asset,"")); st.rerun()
        show([{"Date":r.get("entry_date"),"Category":r.get("category"),"Entry":record_label(r),"Asset":asset_label_by_uuid(store,r.get("asset_uuid","")),"Notes":r.get("notes","")} for r in sorted(store.get("engineering_diary",[]),key=lambda x:x.get("entry_date",""),reverse=True)],"No diary entries.")
    with k2:
        with st.form("decision",clear_on_submit=True):
            title=st.text_input("Decision title"); asset=st.selectbox("Asset",[""]+list(amap),key="dec_asset"); decision=st.text_area("Decision made"); rationale=st.text_area("Why this decision was made"); evidence=st.text_area("Evidence / data"); alternatives=st.text_area("Alternatives considered"); outcome=st.text_area("Outcome / follow-up")
            ok=st.form_submit_button("Record Decision")
        if ok and title.strip(): save_snapshot(); create_decision(store,title,decision,rationale,evidence,alternatives,outcome,amap.get(asset,"")); st.rerun()
        show([{"Date":r.get("decision_date"),"Decision":record_label(r),"Asset":asset_label_by_uuid(store,r.get("asset_uuid","")),"Status":r.get("status","")} for r in store.get("decisions",[])],"No decisions recorded.")
    with k3:
        with st.form("lesson",clear_on_submit=True):
            title=st.text_input("Lesson title"); asset=st.selectbox("Asset",[""]+list(amap),key="ll_asset"); material=st.text_input("Material"); product=st.text_input("Product / family"); context=st.text_area("Context / what happened"); lesson=st.text_area("Lesson learned"); recommendation=st.text_area("Future recommendation / known issue guidance")
            ok=st.form_submit_button("Save Lesson Learned")
        if ok and title.strip(): save_snapshot(); create_lesson(store,title,lesson,context,recommendation,amap.get(asset,""),material,product); st.rerun()
        show([{"Lesson":record_label(r),"Asset":asset_label_by_uuid(store,r.get("asset_uuid","")),"Material":r.get("material",""),"Product":r.get("product",""),"Recommendation":r.get("recommendation","")} for r in store.get("lessons_learned",[])],"No lessons learned yet.")
    with k4:
        with st.form("reference",clear_on_submit=True):
            title=st.text_input("Reference title"); typ=st.selectbox("Type",["Drawing","Manual","Photo","CNC Program","Supplier Document","Calibration","Procedure","Specification","Folder","Web Link","Other"]); asset=st.selectbox("Asset",[""]+list(amap),key="ref_asset"); location=st.text_input("File path / document number / URL / storage location"); desc=st.text_area("Description")
            ok=st.form_submit_button("Add Reference")
        if ok and title.strip(): save_snapshot(); create_reference(store,title,typ,location,desc,amap.get(asset,"")); st.rerun()
        show([{"Type":r.get("reference_type"),"Reference":record_label(r),"Asset":asset_label_by_uuid(store,r.get("asset_uuid","")),"Location":r.get("location","")} for r in store.get("references",[])],"No references recorded.")

with tabs[6]:
    st.subheader("Record Lifecycle, IDs & Cloning")
    modules=[m for m in SEARCH_MODULES if store.get(m)]
    if not modules:
        st.info("No records available.")
    else:
        module=st.selectbox("Module",modules,format_func=lambda x:x.replace("_"," ").title())
        rmap=options(module)
        name=st.selectbox("Record",list(rmap),key="record_control")
        uid=rmap[name]; r=by_uuid(store[module])[uid]
        c=st.columns(4)
        c[0].metric("Business ID",r.get("business_id") or "—"); c[1].metric("Lifecycle",r.get("lifecycle",r.get("status","—"))); c[2].metric("Created",str(r.get("created_at",""))[:10] or "—"); c[3].metric("Updated",str(r.get("updated_at",""))[:10] or "—")
        a,b,c=st.columns(3)
        with a:
            if st.button("Assign Display ID",use_container_width=True): save_snapshot(); assign_display_id(store,module,r); st.rerun()
        with b:
            lifecycle=st.selectbox("Lifecycle",["Draft","Active","Complete","Closed","Archived"],key="life")
            if st.button("Set Lifecycle",use_container_width=True): save_snapshot(); set_lifecycle(store,module,uid,lifecycle); st.rerun()
        with c:
            if st.button("Clone Record",use_container_width=True): save_snapshot(); clone_record(store,module,uid); st.success("Record cloned with a new hidden UUID and display ID."); st.rerun()
        st.caption(f"Hidden system UUID: {uid}")

with tabs[7]:
    st.subheader("Data Quality & System Health")
    health=system_health(store)
    c=st.columns(5)
    c[0].metric("Total records",health["total_records"]); c[1].metric("Schema version",health["version"]); c[2].metric("Quality issues",health["quality_issues"]); c[3].metric("Orphan links",health["orphan_links"]); c[4].metric("Backup age",f"{health['backup_age_hours']:.1f} h" if health["backup_age_hours"] is not None else "Never")
    st.markdown("#### Data-quality checks")
    show(data_quality_issues(store),"No data-quality issues detected.")
    st.markdown("#### Orphaned relationship checks")
    show(orphan_links(store),"No orphaned UUID relationships detected.")
    st.markdown("#### Record counts")
    show([{"Module":m.replace("_"," ").title(),"Records":n} for m,n in health["record_counts"].items()],"No records.")

with tabs[8]:
    st.subheader("Backup, Validation & Recovery")
    settings=store["settings"]
    reminder=st.number_input("Backup reminder interval (days)",1,30,int(settings.get("backup_reminder_days",1) or 1))
    if reminder!=settings.get("backup_reminder_days"):
        settings["backup_reminder_days"]=int(reminder)
    c1,c2=st.columns(2)
    with c1:
        st.markdown("#### Persistent backup")
        st.caption("For this single-user Streamlit setup, the downloaded JSON/ZIP remains the durable copy. Browser/session snapshots are only temporary recovery points.")
        payload=backup_zip(store)
        if st.download_button("Download Full Engineering Backup ZIP",payload,file_name=f"Engineering_System_Backup_{date.today().isoformat()}.zip",mime="application/zip",use_container_width=True):
            mark_backup_created(store)
        st.write("Last backup recorded:",settings.get("last_backup_at") or "Never")
    with c2:
        st.markdown("#### In-session recovery snapshot")
        if st.button("Create Recovery Snapshot",use_container_width=True): st.session_state.readiness_snapshot=session_snapshot(store); st.success("Recovery snapshot created for this browser session.")
        if st.button("Restore Session Snapshot",use_container_width=True):
            ok,msg,data=validate_restore_bytes(st.session_state.readiness_snapshot)
            if ok: st.session_state.pm_store=load_store(st.session_state.readiness_snapshot); st.success("Session snapshot restored."); st.rerun()
            else: st.error(msg)
    st.markdown("#### Validate a JSON backup before restoring it")
    upload=st.file_uploader("Choose engineering-system JSON",type=["json"],key="validate_backup")
    if upload is not None:
        ok,msg,data=validate_restore_bytes(upload.getvalue())
        if ok:
            st.success(msg)
            st.write({"Schema":data.get("schema"),"Version":data.get("version"),"Updated":data.get("updated_at"),"Assets":len(data.get("assets",[])),"Maintenance records":len(data.get("maintenance",[]))})
        else: st.error(msg)

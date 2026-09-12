from datetime import date, timedelta
import pandas as pd
import streamlit as st

from engineering_system import blank_store, base_record, by_uuid, record_label, asset_label_by_uuid, pm_status
from next_layer import (
    update_record, complete_pm, create_action_from_breakdown, create_rca_from_breakdown,
    create_pm_from_template, spare_stock_status, low_stock_spares, asset_history,
)
from advanced_operations import (
    checklist_items, apply_pm_completion_details, downtime_pareto, recurring_failures,
    maintenance_cost_summary, MAINTENANCE_PACKS, seed_maintenance_pack,
)
from usb_runtime import initialise_page, persist

st.set_page_config(page_title="Engineering Operations", page_icon="🔧", layout="wide")
_vault, store = initialise_page()
store.setdefault("pm_templates", [])


def options(module):
    return {record_label(r): r.get("system_uuid") for r in store.get(module, [])}


def show(rows, empty="No records."):
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info(empty)


st.title("Engineering Operations")
st.caption("Execution layer for preventive maintenance, breakdown follow-up, spare stock, labour/cost control, recurring-failure analysis and asset engineering history.")

tabs = st.tabs([
    "Operations Dashboard", "Asset History", "PM Execution", "Maintenance Packs",
    "Breakdown Follow-up", "Spare Stock", "Cost & Reliability", "Record Editor"
])

with tabs[0]:
    st.subheader("Operational Maintenance Dashboard")
    warnings = low_stock_spares(store)
    pareto = downtime_pareto(store)
    repeats = recurring_failures(store)
    cost_rows, cost_by_asset = maintenance_cost_summary(store)
    c=st.columns(5)
    c[0].metric("PM overdue", len([p for p in store.get("pm_schedules",[]) if pm_status(p)=="Overdue"]))
    c[1].metric("PM due soon", len([p for p in store.get("pm_schedules",[]) if pm_status(p)=="Due Soon"]))
    c[2].metric("Stock warnings", len(warnings))
    c[3].metric("Recurring failures", len(repeats))
    c[4].metric("Recorded maintenance cost", f"${sum(float(r.get('Total',0) or 0) for r in cost_rows):,.0f}")
    left,right=st.columns(2)
    with left:
        st.markdown("#### Downtime Pareto")
        show(pareto,"No breakdown downtime recorded.")
        if pareto:
            df=pd.DataFrame(pareto).set_index("Asset")
            st.bar_chart(df[["Downtime h"]])
    with right:
        st.markdown("#### Recurring failure signals")
        show(repeats,"No repeated breakdown patterns detected yet.")
    st.markdown("#### Stock warnings")
    show([{"Status":spare_stock_status(s),"Part":record_label(s),"Asset":asset_label_by_uuid(store,s.get("asset_uuid")),"On Hand":s.get("quantity_on_hand",0),"Minimum":s.get("minimum_stock",0),"Lead Days":s.get("lead_time_days",0)} for s in warnings],"No low-stock warnings.")

with tabs[1]:
    st.subheader("Linked Asset Engineering History")
    amap=options("assets")
    if not amap:
        st.info("Create assets in the main Asset Register first.")
    else:
        name=st.selectbox("Asset",list(amap),key="hist_asset")
        uid=amap[name]
        asset=by_uuid(store["assets"])[uid]
        c=st.columns(4)
        c[0].metric("Department",asset.get("department","—")); c[1].metric("Class",asset.get("asset_class","—")); c[2].metric("Criticality",asset.get("criticality","—")); c[3].metric("Status",asset.get("status","—"))
        show(asset_history(store,uid),"No engineering history linked to this asset yet.")
        st.markdown("#### Maintenance history")
        show([{"Date":r.get("event_date"),"Type":r.get("maintenance_type"),"Status":r.get("status"),"Downtime h":r.get("downtime_hours",0),"Repair h":r.get("repair_hours",0),"Cost":r.get("total_maintenance_cost",0),"Summary":r.get("title")} for r in store.get("maintenance",[]) if r.get("asset_uuid")==uid],"No maintenance history.")
        st.markdown("#### PM schedules")
        show([{"Status":pm_status(r),"Task":record_label(r),"Frequency":r.get("frequency"),"Next due":r.get("next_due_date"),"Last completed":r.get("last_completed_date",""),"Owner":r.get("owner")} for r in store.get("pm_schedules",[]) if r.get("asset_uuid")==uid],"No PM schedules linked to this asset.")

with tabs[2]:
    st.subheader("PM Execution — Task-by-Task")
    pmmap=options("pm_schedules")
    if not pmmap:
        st.info("No PM schedules exist yet.")
    else:
        selected=st.selectbox("PM schedule",list(pmmap),key="exec_pm")
        uid=pmmap[selected]; pm=by_uuid(store["pm_schedules"])[uid]
        c=st.columns(5)
        c[0].metric("Status",pm_status(pm)); c[1].metric("Asset",asset_label_by_uuid(store,pm.get("asset_uuid")) or "—"); c[2].metric("Frequency",pm.get("frequency","—")); c[3].metric("Next due",pm.get("next_due_date","—")); c[4].metric("Last complete",pm.get("last_completed_date","—"))
        if pm.get("safety_requirements"):
            st.warning(pm.get("safety_requirements"))
        items=checklist_items(pm.get("checklist"))
        st.markdown("#### Checklist")
        results=[]
        if items:
            for i,item in enumerate(items):
                done=st.checkbox(item,key=f"pm_{uid}_{i}")
                results.append({"task":item,"completed":bool(done)})
        else:
            st.info("No checklist tasks recorded on this schedule.")
        st.markdown("#### Parts / consumables")
        smap=options("spares"); consumption=[]
        chosen=st.multiselect("Select spare parts used",list(smap),key=f"parts_{uid}") if smap else []
        for name in chosen:
            suid=smap[name]; spare=by_uuid(store["spares"])[suid]
            qty=st.number_input(f"Quantity used — {name} (on hand {spare.get('quantity_on_hand',0)})",min_value=0.0,step=1.0,key=f"qty_{uid}_{suid}")
            if qty>0: consumption.append({"spare_uuid":suid,"quantity":qty})
        with st.form("complete_pm_form"):
            a=st.columns(5)
            completed=a[0].date_input("Completion date",date.today())
            technician=a[1].text_input("Completed by",pm.get("owner",""))
            hours=a[2].number_input("Actual labour hours",0.0,step=.25)
            rate=a[3].number_input("Labour rate $/h",0.0,step=5.0)
            external=a[4].number_input("External/service cost $",0.0,step=10.0)
            notes=st.text_area("Work completed / findings")
            parts_text=st.text_area("Additional unstocked parts / consumables used")
            confirm=st.checkbox("I confirm this PM has been completed")
            submit=st.form_submit_button("Complete PM, Deduct Stock & Calculate Next Due",use_container_width=True)
        if submit:
            incomplete=[x["task"] for x in results if not x["completed"]]
            if not confirm:
                st.error("Confirm completion before closing the PM.")
            elif incomplete:
                st.error(f"{len(incomplete)} checklist task(s) are not complete. Complete them before closing the PM.")
            else:
                maint,nxt=complete_pm(store,uid,completed,technician,notes,hours,parts_text)
                apply_pm_completion_details(store,maint["system_uuid"],results,rate,external,consumption)
                st.success(f"PM completed. Next due: {nxt.isoformat() if nxt else 'manual scheduling required'}")
                persist(store)
                st.rerun()

with tabs[3]:
    st.subheader("Machine-Specific Maintenance Packs")
    st.info("These are starting engineering packs. Verify each task against OEM documentation, actual machine design and your in-house laser/equipment requirements before adopting it as controlled maintenance standard work.")
    classes=sorted(set(list(MAINTENANCE_PACKS.keys()) + store.get("settings",{}).get("asset_classes",[])))
    c1,c2=st.columns(2)
    with c1:
        pack_class=st.selectbox("Maintenance pack",classes)
        owner=st.text_input("Default responsible role")
        if st.button("Add Standard Pack Templates",use_container_width=True):
            created=seed_maintenance_pack(store,pack_class,owner)
            st.success(f"Added {len(created)} new template(s). Existing matching templates were not duplicated.")
            persist(store)
            st.rerun()
    with c2:
        st.markdown("#### Pack preview")
        preview=[]
        for title,freq,tasks in MAINTENANCE_PACKS.get(pack_class,[]):
            preview.append({"Template":title,"Frequency":freq,"Tasks":len(tasks)})
        show(preview,"No built-in pack for this asset class yet.")
    st.markdown("#### Existing PM templates")
    show([{"Template":record_label(r),"Asset Class":r.get("asset_class"),"Frequency":r.get("frequency"),"Owner":r.get("owner"),"Estimated h":r.get("estimated_hours",0)} for r in store.get("pm_templates",[])],"No PM templates yet.")
    tmap=options("pm_templates"); amap=options("assets")
    if tmap and amap:
        with st.form("apply_pm_template"):
            a=st.columns(4)
            t=a[0].selectbox("Template",list(tmap)); asset=a[1].selectbox("Asset",list(amap)); due=a[2].date_input("First due date",date.today()); own=a[3].text_input("Owner override")
            apply=st.form_submit_button("Create PM Schedule from Template",use_container_width=True)
        if apply:
            template=by_uuid(store["pm_templates"])[tmap[t]]; machine=by_uuid(store["assets"])[amap[asset]]
            if template.get("asset_class") and machine.get("asset_class") and template.get("asset_class")!=machine.get("asset_class"):
                st.warning(f"Template class is {template.get('asset_class')} but selected asset is {machine.get('asset_class')}. Schedule created as requested.")
            create_pm_from_template(store,tmap[t],amap[asset],due,own); st.success("PM schedule created."); persist(store); st.rerun()

with tabs[4]:
    st.subheader("Breakdown Follow-up")
    breakdowns=[r for r in store.get("maintenance",[]) if r.get("maintenance_type")=="Breakdown"]
    bmap={record_label(r):r.get("system_uuid") for r in breakdowns}
    if not bmap:
        st.info("No breakdown records available.")
    else:
        selected=st.selectbox("Breakdown",list(bmap)); uid=bmap[selected]; r=by_uuid(store["maintenance"])[uid]
        c=st.columns(4)
        c[0].metric("Asset",asset_label_by_uuid(store,r.get("asset_uuid")) or "—"); c[1].metric("Date",r.get("event_date","—")); c[2].metric("Downtime",f"{float(r.get('downtime_hours',0) or 0):.2f} h"); c[3].metric("Status",r.get("status","—"))
        st.write("**Symptoms:**",r.get("symptom","")); st.write("**Diagnosis:**",r.get("diagnosis","")); st.write("**Work completed:**",r.get("action_taken",""))
        failure=st.text_input("Failure category / recurring-failure tag",r.get("failure_category",""),key="failure_category")
        if st.button("Save Failure Category"):
            update_record(store,"maintenance",uid,{"failure_category":failure}); persist(store); st.rerun()
        a,b=st.columns(2)
        with a:
            owner=st.text_input("Action owner",r.get("owner",""),key="bd_action_owner"); due=st.date_input("Action due",date.today()+timedelta(days=7),key="bd_action_due")
            if st.button("Create Linked Engineering Action",use_container_width=True): create_action_from_breakdown(store,uid,owner,due); st.success("Engineering action created and linked."); persist(store); st.rerun()
        with b:
            rca_owner=st.text_input("RCA owner",r.get("owner",""),key="bd_rca_owner")
            if st.button("Create Linked RCA",use_container_width=True): create_rca_from_breakdown(store,uid,rca_owner); st.success("RCA created and linked."); persist(store); st.rerun()

with tabs[5]:
    st.subheader("Spare Parts Stock Control")
    warnings=low_stock_spares(store)
    c=st.columns(3)
    c[0].metric("Stock warnings",len(warnings)); c[1].metric("Out of stock",len([s for s in warnings if spare_stock_status(s)=="Out of Stock"])); c[2].metric("Low stock",len([s for s in warnings if spare_stock_status(s)=="Low Stock"]))
    show([{"Status":spare_stock_status(s),"Part":record_label(s),"Asset":asset_label_by_uuid(store,s.get("asset_uuid")),"On Hand":s.get("quantity_on_hand",0),"Minimum":s.get("minimum_stock",0),"Unit Cost":s.get("unit_cost",s.get("cost",0)),"Lead Days":s.get("lead_time_days",0),"Location":s.get("storage_location","")} for s in store.get("spares",[])],"No spare parts records.")
    smap=options("spares")
    if smap:
        selected=st.selectbox("Update spare stock",list(smap)); uid=smap[selected]; s=by_uuid(store["spares"])[uid]
        with st.form("edit_spare_stock"):
            a=st.columns(4)
            qty=a[0].number_input("Quantity on hand",0.0,step=1.0,value=float(s.get("quantity_on_hand",0) or 0)); minimum=a[1].number_input("Minimum stock",0.0,step=1.0,value=float(s.get("minimum_stock",0) or 0)); unit=a[2].number_input("Unit cost $",0.0,step=1.0,value=float(s.get("unit_cost",s.get("cost",0)) or 0)); location=a[3].text_input("Storage location",s.get("storage_location","")); save=st.form_submit_button("Save Stock Details")
        if save:
            update_record(store,"spares",uid,{"quantity_on_hand":float(qty),"minimum_stock":float(minimum),"unit_cost":float(unit),"storage_location":location}); persist(store); st.rerun()

with tabs[6]:
    st.subheader("Maintenance Cost & Reliability Analysis")
    cost_rows,cost_by_asset=maintenance_cost_summary(store)
    left,right=st.columns(2)
    with left:
        st.markdown("#### Cost by asset")
        show(cost_by_asset,"No maintenance costs recorded yet.")
        if cost_by_asset:
            st.bar_chart(pd.DataFrame(cost_by_asset).set_index("Asset"))
    with right:
        st.markdown("#### Downtime Pareto")
        pareto=downtime_pareto(store); show(pareto,"No breakdown downtime recorded yet.")
    st.markdown("#### Recurring failure detection")
    threshold=st.number_input("Minimum occurrences to flag",2,10,2)
    show(recurring_failures(store,threshold),"No recurring failure groups meet the threshold.")
    st.markdown("#### Maintenance cost ledger")
    show(cost_rows,"No costed maintenance records yet.")

with tabs[7]:
    st.subheader("Record Editor")
    editable=["assets","actions","maintenance","pm_schedules","process_improvements","trials","research","rca","products","tooling","spares"]
    module=st.selectbox("Record type",editable,format_func=lambda x:x.replace("_"," ").title()); rmap=options(module)
    if not rmap:
        st.info("No records in this module.")
    else:
        selected=st.selectbox("Record",list(rmap),key="editor_record"); uid=rmap[selected]; r=by_uuid(store[module])[uid]
        with st.form("basic_editor"):
            a=st.columns(3)
            title=a[0].text_input("Title / name",r.get("title","")); dept=a[1].text_input("Department",r.get("department","")); business=a[2].text_input("Business / current ID",r.get("business_id",""))
            b=st.columns(2); legacy=b[0].text_input("Legacy ID",r.get("legacy_id","")); alias=b[1].text_input("Alias",r.get("alias","")); save=st.form_submit_button("Save Record Identity",use_container_width=True)
        if save:
            update_record(store,module,uid,{"title":title,"department":dept,"business_id":business,"legacy_id":legacy,"alias":alias}); st.success("Record updated."); persist(store); st.rerun()
        st.caption(f"System UUID: {uid}"); st.json(r,expanded=False)

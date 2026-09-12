from datetime import date, timedelta
import pandas as pd
import streamlit as st

from engineering_system import blank_store, by_uuid, record_label, asset_label_by_uuid, pm_status
from next_layer import create_rca_from_breakdown
from control_centre import *

st.set_page_config(page_title="Engineering Control Centre", page_icon="🧭", layout="wide")
if "pm_store" not in st.session_state:
    st.session_state.pm_store=blank_store()
store=st.session_state.pm_store
ensure_control_collections(store)

def options(module): return {record_label(r):r.get("system_uuid") for r in store.get(module,[])}
def show(rows,msg="No records."):
    if rows: st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    else: st.info(msg)

st.title("Engineering Control Centre")
st.caption("Work orders, shutdown planning, condition monitoring, asset risk, RCA recommendations and engineering handover.")
tabs=st.tabs(["Handover","Work Orders","Shutdowns","Condition Monitoring","Asset Risk","RCA Triggers"])

with tabs[0]:
    horizon=st.slider("Handover horizon (days)",1,30,7)
    snap=handover_snapshot(store,horizon)
    c=st.columns(6)
    for col,(label,val) in zip(c,[("Assets down",len(snap["down_assets"])),("Open work orders",len(snap["open_work_orders"])),("Urgent actions",len(snap["urgent_actions"])),("PM due",len(snap["pm_due"])),("Condition alerts",len(snap["condition_alerts"])),("Shutdowns",len(snap["upcoming_shutdowns"]))]): col.metric(label,val)
    a,b=st.columns(2)
    with a:
        st.subheader("Assets down / under repair")
        show([{"Asset":record_label(x),"Department":x.get("department"),"Status":x.get("status"),"Criticality":x.get("criticality")} for x in snap["down_assets"]],"No assets marked down.")
        st.subheader("Open work orders")
        show([{"Priority":x.get("priority"),"Due":x.get("due_date"),"Asset":asset_label_by_uuid(store,x.get("asset_uuid")),"Work Order":record_label(x),"Owner":x.get("owner"),"Status":x.get("status")} for x in snap["open_work_orders"]],"No open work orders.")
        st.subheader("Awaiting parts / supplier")
        show([{"Status":x.get("status"),"Asset":asset_label_by_uuid(store,x.get("asset_uuid")),"Action":record_label(x),"Owner":x.get("owner")} for x in snap["awaiting"]],"Nothing waiting on parts or suppliers.")
    with b:
        st.subheader("Condition alerts")
        show(snap["condition_alerts"],"No condition alerts.")
        st.subheader("PM due")
        show([{"Status":pm_status(x),"Due":x.get("next_due_date"),"Asset":asset_label_by_uuid(store,x.get("asset_uuid")),"Task":record_label(x)} for x in snap["pm_due"]],"No PM due in horizon.")
        st.subheader("Upcoming shutdowns")
        show([{"Start":x.get("start_date"),"End":x.get("end_date"),"Shutdown":record_label(x),"Coordinator":x.get("coordinator"),"Status":x.get("status")} for x in snap["upcoming_shutdowns"]],"No shutdowns in horizon.")
    st.subheader("Handover notes")
    amap=options("assets")
    with st.form("handover",clear_on_submit=True):
        c=st.columns(4); title=c[0].text_input("Handover item"); dept=c[1].text_input("Department"); owner=c[2].text_input("Owner"); pri=c[3].selectbox("Priority",["Normal","High","Critical"])
        asset=st.selectbox("Linked asset",[""]+list(amap)); detail=st.text_area("What the next engineer needs to know"); due=st.date_input("Review date",date.today()); save=st.form_submit_button("Add Handover Note")
    if save and title.strip(): add_handover_note(store,title,dept,owner,pri,detail,amap.get(asset,""),due); st.rerun()
    show([{"Priority":x.get("priority"),"Department":x.get("department"),"Asset":asset_label_by_uuid(store,x.get("asset_uuid")),"Item":record_label(x),"Owner":x.get("owner"),"Due":x.get("due_date")} for x in snap["handover_notes"]])

with tabs[1]:
    st.subheader("Maintenance Work Orders")
    amap=options("assets"); mmap=options("maintenance"); actmap=options("actions")
    with st.form("wo",clear_on_submit=True):
        c=st.columns(4); title=c[0].text_input("Work order title"); dept=c[1].text_input("Department"); asset=c[2].selectbox("Asset",[""]+list(amap)); typ=c[3].selectbox("Type",["Preventive","Predictive","Corrective","Breakdown Follow-up","Improvement","Inspection","Project"])
        d=st.columns(4); pri=d[0].selectbox("Priority",["Low","Medium","High","Critical"]); owner=d[1].text_input("Owner"); req=d[2].text_input("Requested by"); due=d[3].date_input("Due date",date.today()+timedelta(days=7))
        srcm=st.selectbox("Source maintenance / breakdown",[""]+list(mmap)); srca=st.selectbox("Source engineering action",[""]+list(actmap)); scope=st.text_area("Job scope"); safety=st.text_area("Isolation / safety requirements")
        e=st.columns(2); est=e[0].number_input("Estimated labour hours",0.0,step=.25); pd=e[1].number_input("Planned downtime hours",0.0,step=.25); create=st.form_submit_button("Create Work Order")
    if create and title.strip(): create_work_order(store,title,dept,amap.get(asset,""),typ,pri,owner,req,due,scope,safety,est,pd,mmap.get(srcm,""),actmap.get(srca,"")); st.rerun()
    show([{"Priority":x.get("priority"),"Status":x.get("status"),"Due":x.get("due_date"),"Asset":asset_label_by_uuid(store,x.get("asset_uuid")),"Work Order":record_label(x),"Owner":x.get("owner")} for x in store["work_orders"]])
    womap=options("work_orders")
    if womap:
        pick=st.selectbox("Update work order",list(womap)); uid=womap[pick]; w=by_uuid(store["work_orders"])[uid]
        with st.form("woupdate"):
            status=st.selectbox("Status",["Open","Planned","In Progress","Awaiting Parts","Awaiting Supplier","Complete","Closed","Cancelled"]); owner=st.text_input("Owner",w.get("owner","")); actual=st.number_input("Actual labour hours",0.0,step=.25,value=float(w.get("actual_hours",0) or 0)); down=st.number_input("Actual downtime hours",0.0,step=.25,value=float(w.get("actual_downtime_hours",0) or 0)); parts=st.text_area("Parts required",w.get("parts_required","")); notes=st.text_area("Progress / completion notes",w.get("completion_notes","")); save=st.form_submit_button("Save Work Order")
        if save: update_work_order(store,uid,status=status,owner=owner,actual_hours=actual,actual_downtime_hours=down,parts_required=parts,completion_notes=notes); st.rerun()

with tabs[2]:
    st.subheader("Planned Shutdown Management")
    amap=options("assets"); womap=options("work_orders")
    with st.form("shutdown",clear_on_submit=True):
        c=st.columns(4); title=c[0].text_input("Shutdown title"); dept=c[1].text_input("Department / area"); start=c[2].date_input("Start",date.today()+timedelta(days=7)); end=c[3].date_input("End",date.today()+timedelta(days=7)); coord=st.text_input("Coordinator"); assets=st.multiselect("Affected assets",list(amap)); scope=st.text_area("Scope"); pre=st.text_area("Pre-work"); parts=st.text_area("Parts readiness"); contractor=st.text_area("Contractor plan"); safety=st.text_area("Isolation / permits"); restart=st.text_area("Restart / validation plan"); create=st.form_submit_button("Create Shutdown Plan")
    if create and title.strip(): create_shutdown(store,title,start,end,dept,coord,[amap[x] for x in assets],scope,pre,parts,contractor,safety,restart); st.rerun()
    show([{"Start":x.get("start_date"),"End":x.get("end_date"),"Status":x.get("status"),"Shutdown":record_label(x),"Coordinator":x.get("coordinator"),"Assets":len(x.get("affected_asset_uuids",[]))} for x in store["shutdowns"]])
    smap=options("shutdowns")
    if smap and womap:
        pick=st.selectbox("Populate shutdown",list(smap)); s=by_uuid(store["shutdowns"])[smap[pick]]; linked=st.multiselect("Linked work orders",list(womap),default=[n for n,u in womap.items() if u in s.get("linked_work_order_uuids",[])]); status=st.selectbox("Shutdown status",["Planned","Ready","In Progress","Complete","Cancelled"])
        if st.button("Save Shutdown Links / Status"): s["linked_work_order_uuids"]=[womap[x] for x in linked]; s["status"]=status; st.rerun()

with tabs[3]:
    st.subheader("Condition Monitoring")
    amap=options("assets")
    if amap:
        with st.form("reading",clear_on_submit=True):
            c=st.columns(4); asset=c[0].selectbox("Asset",list(amap)); metric=c[1].text_input("Metric"); value=c[2].number_input("Reading",value=0.0); unit=c[3].text_input("Unit"); d=st.columns(4); rd=d[0].date_input("Reading date",date.today()); direction=d[1].selectbox("Alarm direction",["High","Low"]); warning=d[2].number_input("Warning limit",value=0.0); critical=d[3].number_input("Critical limit",value=0.0); source=st.text_input("Source / instrument"); notes=st.text_area("Notes"); save=st.form_submit_button("Record Reading")
        if save and metric.strip(): add_condition_reading(store,amap[asset],metric,value,unit,rd,warning,critical,direction,source,notes); st.rerun()
    show(condition_summary(store),"No condition readings yet.")
    if amap:
        asset=st.selectbox("Trend asset",list(amap)); uid=amap[asset]; metrics=sorted(set(x.get("metric") for x in store["condition_readings"] if x.get("asset_uuid")==uid and x.get("metric")))
        if metrics:
            metric=st.selectbox("Trend metric",metrics); trend=condition_trend(store,uid,metric); show(trend); st.line_chart(pd.DataFrame(trend).set_index("Date")[["Value"]])

with tabs[4]:
    st.subheader("Asset Criticality & Risk Scoring")
    st.caption("Risk = (Safety + Production + Quality + Repair/Lead-Time consequence) × Likelihood. Each factor is 1–5.")
    amap=options("assets")
    if amap:
        asset=st.selectbox("Asset",list(amap)); uid=amap[asset]; existing=next((x for x in store["risk_assessments"] if x.get("asset_uuid")==uid),{})
        with st.form("risk"):
            c=st.columns(5); safety=c[0].slider("Safety",1,5,int(existing.get("safety_score",1))); prod=c[1].slider("Production",1,5,int(existing.get("production_score",1))); quality=c[2].slider("Quality",1,5,int(existing.get("quality_score",1))); repair=c[3].slider("Repair / lead time",1,5,int(existing.get("repair_lead_score",1))); likelihood=c[4].slider("Likelihood",1,5,int(existing.get("likelihood_score",1))); notes=st.text_area("Notes",existing.get("notes","")); save=st.form_submit_button("Save Risk Assessment")
        if save: save_risk_assessment(store,uid,safety,prod,quality,repair,likelihood,notes); st.rerun()
    show([{"Asset":asset_label_by_uuid(store,x.get("asset_uuid")),"Risk Score":x.get("risk_score"),"Band":x.get("risk_band"),"Likelihood":x.get("likelihood_score"),"Date":x.get("assessment_date")} for x in sorted(store["risk_assessments"],key=lambda x:x.get("risk_score",0),reverse=True)],"No risk assessments yet.")

with tabs[5]:
    st.subheader("Automatic RCA Recommendation Triggers")
    c=st.columns(3); downtime=c[0].number_input("Downtime trigger (h)",0.0,step=.5,value=4.0); cost=c[1].number_input("Cost trigger ($)",0.0,step=100.0,value=1000.0); repeats=c[2].number_input("Recurring failure count",2,10,2)
    recs=rca_recommendations(store,downtime,cost,int(repeats)); show(recs,"No current breakdowns meet the RCA recommendation rules.")
    if recs:
        choices={f"{x['Asset']} — {x['Breakdown']} — {x['Recommendation']}":x["Breakdown UUID"] for x in recs}; pick=st.selectbox("Recommendation",list(choices)); owner=st.text_input("RCA owner")
        if st.button("Create Recommended RCA"): create_rca_from_breakdown(store,choices[pick],owner); st.rerun()

from datetime import date
import pandas as pd
import streamlit as st
from engineering_system import *

st.set_page_config(page_title="Process and Maintenance Engineering System", page_icon="🛠️", layout="wide")
st.markdown("<style>.block-container{max-width:1500px;padding-top:1rem}div[data-testid='stMetric']{border:1px solid #7774;border-radius:12px;padding:10px}</style>",unsafe_allow_html=True)
if "pm_store" not in st.session_state: st.session_state.pm_store=blank_store()
store=st.session_state.pm_store

def opts(module): return {record_label(r):r.get("system_uuid") for r in store.get(module,[])}
def add(module,r): store[module].append(r); st.rerun()
def ids(prefix):
    c=st.columns(3); return c[0].text_input("Current / business ID (optional)",key=prefix+"_bid"),c[1].text_input("Legacy ID (optional)",key=prefix+"_lid"),c[2].text_input("Alias / alternate ID",key=prefix+"_alias")
def table(rows,msg="No records yet."):
    if rows: st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    else: st.info(msg)
def material_options(): return [""]+store["settings"].get("materials",[])+["Other"]

with st.sidebar:
    st.header("Engineering System")
    page=st.radio("Module",["Dashboard","Assets","Products & Routes","Engineering Actions","PM Schedules","Maintenance","Process Engineering","Engineering Trials","Machinery & Tooling Research","Tooling & Spares","RCA & Investigations","Engineering Reports","System Data & Backup"])
    st.divider()
    up=st.file_uploader("Load system JSON",type=["json"])
    if up is not None:
        try:
            key=f"{up.name}:{len(up.getvalue())}"
            if st.session_state.get("loaded_key")!=key:
                st.session_state.pm_store=load_store(up.getvalue()); st.session_state.loaded_key=key; st.rerun()
        except Exception as e: st.error(f"Could not load file: {e}")

st.title("Process and Maintenance Engineering System")
st.caption("Company-wide process, maintenance, R&D and engineering knowledge system. Human IDs are optional; relationships use hidden UUIDs so legacy numbering can be added later.")

if page=="Dashboard":
    m=dashboard_metrics(store); k=maintenance_kpis(store)
    cols=st.columns(6)
    for col,(label,val,delta) in zip(cols,[("Active assets",m["active_assets"],f"{m['assets']} total"),("Open actions",m["open_actions"],None),("Critical actions",m["critical_actions"],None),("PM overdue",m["overdue_pm"],f"{m['due_soon_pm']} due soon"),("Breakdowns",k["breakdown_count"],None),("Downtime",f"{k['downtime_hours']:.1f} h",None)]): col.metric(label,val,delta)
    c1,c2,c3,c4=st.columns(4); c1.metric("MTTR",f"{k['mttr_hours']:.2f} h"); c2.metric("MTBF",f"{k['mtbf_hours']:.0f} h" if k['mtbf_hours'] else "—"); c3.metric("Process improvements",m["process_improvements"]); c4.metric("Trials",m["trials"])
    left,right=st.columns(2)
    with left:
        st.subheader("Priority actions")
        rank={"Critical":0,"High":1,"Medium":2,"Low":3}
        recs=sorted([r for r in store["actions"] if r.get("status") not in ["Complete","Closed"]],key=lambda r:(rank.get(r.get("priority"),9),r.get("due_date","9999")))
        table([{"Priority":r.get("priority"),"Due":r.get("due_date"),"Department":r.get("department"),"Action":r.get("title"),"Asset":asset_label_by_uuid(store,r.get("asset_uuid")),"Status":r.get("status")} for r in recs[:15]],"No open actions.")
    with right:
        st.subheader("PM due / overdue")
        recs=[r for r in store["pm_schedules"] if pm_status(r) in ["Overdue","Due Soon"]]
        table([{"Status":pm_status(r),"Due":r.get("next_due_date"),"Asset":asset_label_by_uuid(store,r.get("asset_uuid")),"Task":r.get("title"),"Owner":r.get("owner")} for r in recs],"No PM currently due.")
    st.subheader("Breakdown downtime by asset")
    bd=[r for r in store["maintenance"] if r.get("maintenance_type")=="Breakdown"]
    if bd:
        df=pd.DataFrame([{"Asset":asset_label_by_uuid(store,r.get("asset_uuid")) or "Unassigned","Downtime":float(r.get("downtime_hours",0) or 0)} for r in bd]); st.bar_chart(df.groupby("Asset").sum())
    else: st.info("No breakdown history yet.")

elif page=="Assets":
    st.subheader("Asset Register")
    with st.form("asset",clear_on_submit=True):
        a=st.columns(3); title=a[0].text_input("Asset / equipment name"); dept=a[1].text_input("Department"); aclass=a[2].selectbox("Asset class",store["settings"].get("asset_classes",[]))
        b=st.columns(4); maker=b[0].text_input("Manufacturer"); model=b[1].text_input("Model"); serial=b[2].text_input("Serial number"); loc=b[3].text_input("Location")
        bid,lid,alias=ids("asset")
        c=st.columns(4); crit=c[0].selectbox("Criticality",["Low","Medium","High","Critical"]); status=c[1].selectbox("Status",["Active","Standby","Under Repair","Decommissioned"]); owner=c[2].text_input("Asset owner / custodian"); rev=c[3].text_input("Configuration / revision")
        function=st.text_area("Function / process capability"); utilities=st.text_area("Utilities / services"); safety=st.text_area("Safety / isolation requirements"); manuals=st.text_area("Manual / document references")
        ok=st.form_submit_button("Add Asset",use_container_width=True)
    if ok:
        if not title.strip(): st.error("Asset name is required.")
        else:
            r=base_record("asset",title,dept,bid,lid); r.update({"alias":alias,"asset_class":aclass,"manufacturer":maker,"model":model,"serial_number":serial,"location":loc,"criticality":crit,"status":status,"custodian":owner,"configuration":rev,"function":function,"utilities":utilities,"safety_notes":safety,"manual_references":manuals}); add("assets",r)
    amap=opts("assets")
    if amap:
        pick=st.selectbox("Asset profile",list(amap)); uid=amap[pick]; r=next(x for x in store["assets"] if x["system_uuid"]==uid)
        c=st.columns(4); c[0].metric("Class",r.get("asset_class","—")); c[1].metric("Criticality",r.get("criticality","—")); c[2].metric("Status",r.get("status","—")); c[3].metric("Department",r.get("department","—"))
        t1,t2,t3=st.tabs(["Profile","Maintenance History","Linked Records"])
        with t1: st.write({"Manufacturer":r.get("manufacturer",""),"Model":r.get("model",""),"Serial":r.get("serial_number",""),"Location":r.get("location",""),"Business ID":r.get("business_id",""),"Legacy ID":r.get("legacy_id","")}); st.write(r.get("function",r.get("notes","")) or "No capability notes.")
        with t2: table([{"Date":x.get("event_date"),"Type":x.get("maintenance_type"),"Status":x.get("status"),"Downtime h":x.get("downtime_hours",0),"Summary":x.get("title")} for x in store["maintenance"] if x.get("asset_uuid")==uid],"No maintenance history.")
        with t3: table([{"Module":mod.replace("_"," ").title(),"Record":record_label(x),"Status":x.get("status",x.get("outcome",""))} for mod,x in linked_records(store,uid)],"No linked records.")

elif page=="Products & Routes":
    st.subheader("Products & Process Routes")
    with st.form("product",clear_on_submit=True):
        a=st.columns(3); title=a[0].text_input("Product / family"); dept=a[1].text_input("Owning department"); material=a[2].selectbox("Primary material",material_options())
        bid,lid,alias=ids("prod"); drawing=st.text_input("Drawing / specification reference"); desc=st.text_area("Description"); ok=st.form_submit_button("Add Product")
    if ok and title.strip():
        r=base_record("product",title,dept,bid,lid); r.update({"alias":alias,"material":material,"drawing_reference":drawing,"description":desc}); add("products",r)
    pmap,amap=opts("products"),opts("assets")
    if pmap:
        with st.form("route",clear_on_submit=True):
            a=st.columns(4); p=a[0].selectbox("Product",list(pmap)); seq=a[1].number_input("Sequence",1,step=1); dept=a[2].text_input("Department"); op=a[3].text_input("Operation / stage")
            b=st.columns(3); asset=b[0].selectbox("Asset",[""]+list(amap)); spec=b[1].text_input("Process / setup reference"); inspect=b[2].text_input("Inspection requirement"); tooling=st.text_area("Tooling / fixture / consumables"); notes=st.text_area("Known issues / notes"); ok=st.form_submit_button("Add Route Step")
        if ok and op.strip():
            r=base_record("process_route",op,dept); r.update({"product_uuid":pmap[p],"sequence":int(seq),"asset_uuid":amap.get(asset,""),"process_spec":spec,"inspection_requirement":inspect,"tooling":tooling,"notes":notes}); add("process_routes",r)
        p=st.selectbox("View route",list(pmap),key="routeview"); route=sorted([r for r in store["process_routes"] if r.get("product_uuid")==pmap[p]],key=lambda r:r.get("sequence",999))
        table([{"Seq":r.get("sequence"),"Department":r.get("department"),"Operation":r.get("title"),"Asset":asset_label_by_uuid(store,r.get("asset_uuid")),"Process Ref":r.get("process_spec"),"Inspection":r.get("inspection_requirement")} for r in route],"No route steps yet.")

elif page=="Engineering Actions":
    amap,pmap=opts("assets"),opts("products"); st.subheader("Engineering Action Register")
    with st.form("action",clear_on_submit=True):
        a=st.columns(3); title=a[0].text_input("Action / issue"); dept=a[1].text_input("Department"); cat=a[2].selectbox("Category",["Process","Maintenance","Quality","R&D","Capital Equipment","Tooling","Safety","Other"])
        b=st.columns(4); pri=b[0].selectbox("Priority",["Low","Medium","High","Critical"]); status=b[1].selectbox("Status",["Open","Investigation","Trial","Awaiting Parts","Awaiting Supplier","Validation","Complete","Closed"]); owner=b[2].text_input("Owner"); due=b[3].date_input("Due date",date.today())
        c=st.columns(2); asset=c[0].selectbox("Linked asset",[""]+list(amap)); prod=c[1].selectbox("Linked product",[""]+list(pmap)); bid,lid,alias=ids("action"); detail=st.text_area("Required action / notes"); ok=st.form_submit_button("Add Action")
    if ok and title.strip():
        r=base_record("engineering_action",title,dept,bid,lid); r.update({"alias":alias,"category":cat,"priority":pri,"status":status,"owner":owner,"due_date":due.isoformat(),"asset_uuid":amap.get(asset,""),"product_uuid":pmap.get(prod,""),"detail":detail}); add("actions",r)
    table([{"Priority":r.get("priority"),"Status":r.get("status"),"Department":r.get("department"),"Action":record_label(r),"Asset":asset_label_by_uuid(store,r.get("asset_uuid")),"Owner":r.get("owner"),"Due":r.get("due_date")} for r in store["actions"]])

elif page=="PM Schedules":
    st.subheader("Preventive Maintenance Schedules"); amap=opts("assets")
    with st.form("pm",clear_on_submit=True):
        a=st.columns(3); title=a[0].text_input("PM task / schedule"); asset=a[1].selectbox("Asset",[""]+list(amap)); dept=a[2].text_input("Department")
        b=st.columns(4); freq=b[0].selectbox("Frequency",["Daily","Weekly","Monthly","Quarterly","6 Monthly","Annual","Hours Based","Custom"]); due=b[1].date_input("Next due",date.today()); owner=b[2].text_input("Responsible person / role"); hrs=b[3].number_input("Estimated hours",0.0,step=.25)
        bid,lid,alias=ids("pm"); checklist=st.text_area("Checklist / standard work"); safety=st.text_area("Isolation / safety requirements"); parts=st.text_area("Required parts / consumables"); ref=st.text_area("OEM / internal reference"); ok=st.form_submit_button("Add PM Schedule")
    if ok and title.strip():
        r=base_record("pm_schedule",title,dept,bid,lid); r.update({"alias":alias,"asset_uuid":amap.get(asset,""),"frequency":freq,"next_due_date":due.isoformat(),"owner":owner,"estimated_hours":float(hrs),"checklist":checklist,"safety_requirements":safety,"required_parts":parts,"reference":ref,"status":"Active"}); add("pm_schedules",r)
    table([{"Status":pm_status(r),"Next Due":r.get("next_due_date"),"Asset":asset_label_by_uuid(store,r.get("asset_uuid")),"Task":record_label(r),"Frequency":r.get("frequency"),"Owner":r.get("owner")} for r in store["pm_schedules"]])

elif page=="Maintenance":
    st.subheader("Maintenance & Breakdown Management"); amap,pmmap,actmap,rcamap=opts("assets"),opts("pm_schedules"),opts("actions"),opts("rca")
    with st.form("maint",clear_on_submit=True):
        a=st.columns(3); title=a[0].text_input("Fault / maintenance summary"); dept=a[1].text_input("Department"); typ=a[2].selectbox("Type",["Preventive","Predictive","Corrective","Breakdown","Improvement"])
        b=st.columns(4); asset=b[0].selectbox("Asset",[""]+list(amap)); event=b[1].date_input("Event date",date.today()); status=b[2].selectbox("Status",["Planned","Due","Overdue","In Progress","Complete","Monitoring"]); owner=b[3].text_input("Engineer / technician")
        c=st.columns(3); down=c[0].number_input("Downtime hours",0.0,step=.25); repair=c[1].number_input("Repair hands-on hours",0.0,step=.25); pm=c[2].selectbox("Related PM",[""]+list(pmmap)); bid,lid,alias=ids("maint")
        symptom=st.text_area("Symptoms / requirement"); diagnosis=st.text_area("Diagnosis / findings"); work=st.text_area("Work completed / repair"); parts=st.text_area("Parts / consumables used"); verify=st.text_area("Return-to-service verification")
        d=st.columns(2); acts=d[0].multiselect("Linked actions",list(actmap)); rcas=d[1].multiselect("Linked RCA",list(rcamap)); ok=st.form_submit_button("Add Maintenance Record")
    if ok and title.strip():
        r=base_record("maintenance",title,dept,bid,lid); r.update({"alias":alias,"maintenance_type":typ,"asset_uuid":amap.get(asset,""),"pm_schedule_uuid":pmmap.get(pm,""),"event_date":event.isoformat(),"status":status,"owner":owner,"downtime_hours":float(down),"repair_hours":float(repair),"symptom":symptom,"diagnosis":diagnosis,"action_taken":work,"parts_used":parts,"verification":verify,"linked_action_uuids":[actmap[x] for x in acts],"linked_rca_uuids":[rcamap[x] for x in rcas]}); add("maintenance",r)
    table([{"Date":r.get("event_date"),"Type":r.get("maintenance_type"),"Asset":asset_label_by_uuid(store,r.get("asset_uuid")),"Status":r.get("status"),"Downtime h":r.get("downtime_hours",0),"Repair h":r.get("repair_hours",0),"Summary":r.get("title")} for r in store["maintenance"]])

elif page=="Process Engineering":
    st.subheader("Process Engineering & Improvement"); amap,pmap,actmap,rcamap=opts("assets"),opts("products"),opts("actions"),opts("rca")
    with st.form("process",clear_on_submit=True):
        a=st.columns(3); title=a[0].text_input("Improvement / process title"); dept=a[1].text_input("Department"); mat=a[2].selectbox("Material",material_options())
        b=st.columns(3); prod=b[0].selectbox("Product",[""]+list(pmap)); asset=b[1].selectbox("Asset",[""]+list(amap)); owner=b[2].text_input("Engineer / owner"); bid,lid,alias=ids("proc")
        baseline=st.text_area("Current process / baseline"); problem=st.text_area("Problem / opportunity"); change=st.text_area("Change / proposal")
        c=st.columns(4); old=c[0].number_input("Old cycle min",0.0); new=c[1].number_input("New cycle min",0.0); orej=c[2].number_input("Old reject %",0.0); nrej=c[3].number_input("New reject %",0.0)
        d=st.columns(4); ot=d[0].number_input("Old tool life",0.0); nt=d[1].number_input("New tool life",0.0); hours=d[2].number_input("Annual hours saved",0.0); saving=d[3].number_input("Annual cost saving",0.0)
        validation=st.text_area("Validation / evidence / conclusion"); e=st.columns(2); acts=e[0].multiselect("Linked actions",list(actmap)); rcas=e[1].multiselect("Linked RCA",list(rcamap)); ok=st.form_submit_button("Add Process Improvement")
    if ok and title.strip():
        red=((old-new)/old*100) if old else 0; r=base_record("process_improvement",title,dept,bid,lid); r.update({"alias":alias,"material":mat,"product_uuid":pmap.get(prod,""),"asset_uuid":amap.get(asset,""),"owner":owner,"baseline":baseline,"problem":problem,"change":change,"old_cycle_time_min":float(old),"new_cycle_time_min":float(new),"cycle_time_reduction_pct":red,"old_rejection_pct":float(orej),"new_rejection_pct":float(nrej),"old_tool_life":float(ot),"new_tool_life":float(nt),"estimated_annual_hours_saved":float(hours),"estimated_annual_cost_saving":float(saving),"validation":validation,"linked_action_uuids":[actmap[x] for x in acts],"linked_rca_uuids":[rcamap[x] for x in rcas]}); add("process_improvements",r)
    table([{"Department":r.get("department"),"Product":product_label_by_uuid(store,r.get("product_uuid")),"Material":r.get("material"),"Asset":asset_label_by_uuid(store,r.get("asset_uuid")),"Improvement":record_label(r),"Cycle reduction %":round(r.get("cycle_time_reduction_pct",0),1),"Annual h saved":r.get("estimated_annual_hours_saved",0),"Annual saving":r.get("estimated_annual_cost_saving",0)} for r in store["process_improvements"]])

elif page=="Engineering Trials":
    st.subheader("Engineering Trials / Experimental Records"); amap,pmap,actmap=opts("assets"),opts("products"),opts("actions")
    with st.form("trial",clear_on_submit=True):
        a=st.columns(3); title=a[0].text_input("Trial title"); dept=a[1].text_input("Department"); mat=a[2].selectbox("Material",material_options())
        b=st.columns(4); prod=b[0].selectbox("Product",[""]+list(pmap)); asset=b[1].selectbox("Asset",[""]+list(amap)); dt=b[2].date_input("Trial date",date.today()); owner=b[3].text_input("Engineer / owner"); bid,lid,alias=ids("trial")
        objective=st.text_area("Objective / hypothesis"); setup=st.text_area("Setup / tooling / fixture"); params=st.text_area("Parameters / variables tested"); results=st.text_area("Results / observations"); inspect=st.text_area("Inspection / quality evidence"); conclusion=st.text_area("Conclusion / recommendation"); outcome=st.selectbox("Outcome",["Planned","In Progress","Successful","Partially Successful","Failed","Inconclusive"]); acts=st.multiselect("Linked actions",list(actmap)); ok=st.form_submit_button("Add Trial")
    if ok and title.strip():
        r=base_record("engineering_trial",title,dept,bid,lid); r.update({"alias":alias,"material":mat,"product_uuid":pmap.get(prod,""),"asset_uuid":amap.get(asset,""),"trial_date":dt.isoformat(),"owner":owner,"objective":objective,"setup":setup,"parameters":params,"results":results,"inspection":inspect,"conclusion":conclusion,"outcome":outcome,"linked_action_uuids":[actmap[x] for x in acts]}); add("trials",r)
    table([{"Date":r.get("trial_date"),"Outcome":r.get("outcome"),"Department":r.get("department"),"Material":r.get("material"),"Product":product_label_by_uuid(store,r.get("product_uuid")),"Asset":asset_label_by_uuid(store,r.get("asset_uuid")),"Trial":record_label(r)} for r in store["trials"]])

elif page=="Machinery & Tooling Research":
    st.subheader("Machinery & Tooling Research / Recommendations"); pmap,actmap=opts("products"),opts("actions")
    with st.form("research",clear_on_submit=True):
        a=st.columns(3); title=a[0].text_input("Research / requirement title"); dept=a[1].text_input("Department"); cat=a[2].selectbox("Category",["Machine","Tooling","Fixture","Automation","Filtration","Measurement","Software","Other"])
        b=st.columns(3); mat=b[0].selectbox("Material",material_options()); prod=b[1].selectbox("Product",[""]+list(pmap)); owner=b[2].text_input("Engineer / owner"); bid,lid,alias=ids("research")
        req=st.text_area("Engineering requirement"); specs=st.text_area("Required capability / constraints"); cand=st.text_area("Candidate machines / tooling / suppliers"); comp=st.text_area("Comparison / scoring / commercial considerations"); risks=st.text_area("Risks / implementation / support"); rec=st.text_area("Recommendation / next step"); status=st.selectbox("Status",["Researching","Supplier Contact","Trial Required","Business Case","Recommended","Rejected","Complete"]); acts=st.multiselect("Linked actions",list(actmap)); ok=st.form_submit_button("Add Research Record")
    if ok and title.strip():
        r=base_record("engineering_research",title,dept,bid,lid); r.update({"alias":alias,"category":cat,"material":mat,"product_uuid":pmap.get(prod,""),"owner":owner,"requirement":req,"specifications":specs,"candidates":cand,"comparison":comp,"risks":risks,"recommendation":rec,"status":status,"linked_action_uuids":[actmap[x] for x in acts]}); add("research",r)
    table([{"Status":r.get("status"),"Category":r.get("category"),"Department":r.get("department"),"Material":r.get("material"),"Research":record_label(r),"Recommendation":r.get("recommendation","")[:120]} for r in store["research"]])

elif page=="Tooling & Spares":
    st.subheader("Tooling Knowledge Library & Spare Parts Register"); t1,t2=st.tabs(["Tooling / Fixtures","Spare Parts / Consumables"]); amap=opts("assets")
    with t1:
        with st.form("tool",clear_on_submit=True):
            a=st.columns(3); title=a[0].text_input("Tool / fixture name"); cat=a[1].selectbox("Category",["CNC Tooling","Grinding Wheel","Diamond Tooling","Dressing Tool","Cutting Tool","Fixture","Workholding","Laser Fixture","Other"]); mat=a[2].selectbox("Material suitability",material_options()+["Multiple"])
            b=st.columns(3); maker=b[0].text_input("Manufacturer"); part=b[1].text_input("Part number"); asset=b[2].selectbox("Compatible asset",[""]+list(amap)); bid,lid,alias=ids("tool"); process=st.text_area("Process / application"); params=st.text_area("Recommended parameters / setup"); perf=st.text_area("Tool life / results / quality"); notes=st.text_area("Lessons learned"); ok=st.form_submit_button("Add Tooling Record")
        if ok and title.strip():
            r=base_record("tooling",title,"",bid,lid); r.update({"alias":alias,"category":cat,"material":mat,"manufacturer":maker,"part_number":part,"asset_uuid":amap.get(asset,""),"process_application":process,"parameters":params,"performance":perf,"notes":notes}); add("tooling",r)
        table([{"Tool / Fixture":record_label(r),"Category":r.get("category"),"Material":r.get("material"),"Manufacturer":r.get("manufacturer"),"Part No":r.get("part_number"),"Asset":asset_label_by_uuid(store,r.get("asset_uuid"))} for r in store["tooling"]])
    with t2:
        with st.form("spare",clear_on_submit=True):
            a=st.columns(3); title=a[0].text_input("Spare / consumable"); maker=a[1].text_input("Manufacturer / supplier"); part=a[2].text_input("Part number")
            b=st.columns(4); asset=b[0].selectbox("Compatible asset",[""]+list(amap)); qty=b[1].number_input("On hand",0.0); minimum=b[2].number_input("Minimum stock",0.0); lead=b[3].number_input("Lead time days",0,step=1)
            c=st.columns(3); loc=c[0].text_input("Storage location"); cost=c[1].number_input("Unit cost",0.0); crit=c[2].selectbox("Criticality",["Low","Medium","High","Critical"]); bid,lid,alias=ids("spare"); notes=st.text_area("Compatibility / notes"); ok=st.form_submit_button("Add Spare")
        if ok and title.strip():
            r=base_record("spare",title,"",bid,lid); r.update({"alias":alias,"manufacturer":maker,"part_number":part,"asset_uuid":amap.get(asset,""),"qty_on_hand":float(qty),"minimum_stock":float(minimum),"lead_time_days":int(lead),"storage_location":loc,"unit_cost":float(cost),"criticality":crit,"notes":notes}); add("spares",r)
        table([{"Spare":record_label(r),"Part No":r.get("part_number"),"Asset":asset_label_by_uuid(store,r.get("asset_uuid")),"On hand":r.get("qty_on_hand"),"Min":r.get("minimum_stock"),"Lead days":r.get("lead_time_days"),"Criticality":r.get("criticality")} for r in store["spares"]])

elif page=="RCA & Investigations":
    st.subheader("Root Cause Analysis & Engineering Investigations"); amap,pmap,actmap,mmap=opts("assets"),opts("products"),opts("actions"),opts("maintenance")
    with st.form("rca",clear_on_submit=True):
        a=st.columns(3); title=a[0].text_input("Investigation title"); dept=a[1].text_input("Department"); typ=a[2].selectbox("Type",["Breakdown","Quality","Process","Safety","Tooling","Equipment","Other"])
        b=st.columns(3); asset=b[0].selectbox("Asset",[""]+list(amap)); prod=b[1].selectbox("Product",[""]+list(pmap)); owner=b[2].text_input("Lead investigator")
        c=st.columns(2); maint=c[0].selectbox("Related maintenance",[""]+list(mmap)); acts=c[1].multiselect("Linked actions",list(actmap)); bid,lid,alias=ids("rca")
        problem=st.text_area("Problem statement"); contain=st.text_area("Immediate containment"); evidence=st.text_area("Evidence / observations / data"); why=st.text_area("5-Why analysis"); root=st.text_area("Root cause"); corrective=st.text_area("Corrective action"); preventive=st.text_area("Preventive action"); verify=st.text_area("Effectiveness verification"); status=st.selectbox("Status",["Open","Investigating","Corrective Action","Verification","Complete"]); ok=st.form_submit_button("Add Investigation")
    if ok and title.strip():
        r=base_record("root_cause_analysis",title,dept,bid,lid); r.update({"alias":alias,"investigation_type":typ,"asset_uuid":amap.get(asset,""),"product_uuid":pmap.get(prod,""),"maintenance_uuid":mmap.get(maint,""),"owner":owner,"problem_statement":problem,"containment":contain,"evidence":evidence,"five_why":why,"root_cause":root,"corrective_action":corrective,"preventive_action":preventive,"verification":verify,"status":status,"linked_action_uuids":[actmap[x] for x in acts]}); add("rca",r)
    table([{"Status":r.get("status"),"Type":r.get("investigation_type"),"Department":r.get("department"),"Asset":asset_label_by_uuid(store,r.get("asset_uuid")),"Investigation":record_label(r),"Root cause":r.get("root_cause","")[:100]} for r in store["rca"]])

elif page=="Engineering Reports":
    st.subheader("Engineering Management Reports"); m=dashboard_metrics(store); k=maintenance_kpis(store)
    c=st.columns(4); c[0].metric("Breakdown downtime",f"{k['downtime_hours']:.1f} h"); c[1].metric("MTTR",f"{k['mttr_hours']:.2f} h"); c[2].metric("PM overdue",m["overdue_pm"]); c[3].metric("Open actions",m["open_actions"])
    st.download_button("Download Engineering Management Summary PDF",generate_summary_pdf(store),file_name=f"Engineering_Management_Summary_{date.today().isoformat()}.pdf",mime="application/pdf",use_container_width=True)
    rows=[]
    for mod in ["actions","maintenance","process_improvements","trials","research","rca"]:
        rows += [{"Department":r.get("department") or "Unassigned","Module":mod.replace("_"," ").title()} for r in store[mod]]
    if rows: table(pd.DataFrame(rows).groupby(["Department","Module"]).size().reset_index(name="Records").to_dict("records"))

elif page=="System Data & Backup":
    st.subheader("System Data, Configuration & Local Backup")
    st.info("Records live in the current Streamlit session. Download JSON/ZIP for local persistence and reload the JSON next time. No persistent cloud database is configured.")
    with st.form("settings"):
        company=st.text_input("Company name (optional)",store["settings"].get("company_name","")); departments=st.text_area("Departments — one per line","\n".join(store["settings"].get("departments",[]))); materials=st.text_area("Materials — one per line","\n".join(store["settings"].get("materials",[]))); classes=st.text_area("Asset classes — one per line","\n".join(store["settings"].get("asset_classes",[]))); ok=st.form_submit_button("Save Configuration")
    if ok:
        store["settings"].update({"company_name":company.strip(),"departments":[x.strip() for x in departments.splitlines() if x.strip()],"materials":[x.strip() for x in materials.splitlines() if x.strip()],"asset_classes":[x.strip() for x in classes.splitlines() if x.strip()]}); st.success("Configuration saved.")
    c=st.columns(3); c[0].download_button("Download System JSON",store_bytes(store),"Process_Maintenance_Engineering_System.json","application/json",use_container_width=True); c[1].download_button("Download Full Backup ZIP",backup_zip(store),f"PM_Engineering_System_Backup_{date.today().isoformat()}.zip","application/zip",use_container_width=True); c[2].download_button("Download Summary PDF",generate_summary_pdf(store),f"Engineering_Management_Summary_{date.today().isoformat()}.pdf","application/pdf",use_container_width=True)
    table([{"Module":m.replace("_"," ").title(),"Records":len(store.get(m,[]))} for m in MODULES])

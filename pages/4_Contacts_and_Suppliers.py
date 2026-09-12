from datetime import date
import pandas as pd
import streamlit as st

from engineering_system import blank_store
from supplier_contacts import (
    COMPANY_STATUSES, COMPANY_TYPES, PROCEDURE_TYPES, RELATIONSHIP_ROLES, TARGET_MODULES,
    ensure_supplier_collections, by_uuid, company_label, contact_label, target_label,
    create_company, create_contact, create_procedure, create_relationship, log_supplier_usage,
    set_company_status, archive_record, relationships_for_target, company_performance,
    directory_rows, search_directory
)
from usb_runtime import initialise_page, persist

st.set_page_config(page_title="Contacts & Suppliers", page_icon="📇", layout="wide")
_vault, store = initialise_page()
ensure_supplier_collections(store)


def show(rows, empty="No records."):
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info(empty)


def active_companies():
    return [r for r in store["supplier_companies"] if not r.get("archived")]


def active_contacts(company_uuid=""):
    rows = [r for r in store["supplier_contacts"] if not r.get("archived") and r.get("active", True)]
    if company_uuid:
        rows = [r for r in rows if r.get("company_uuid") == company_uuid]
    return rows


def active_procedures(company_uuid=""):
    rows = [r for r in store["engagement_procedures"] if not r.get("archived")]
    if company_uuid:
        rows = [r for r in rows if r.get("company_uuid") == company_uuid]
    return rows


def company_options():
    return {company_label(r): r.get("system_uuid") for r in active_companies()}


def contact_options(company_uuid=""):
    return {contact_label(r): r.get("system_uuid") for r in active_contacts(company_uuid)}


def procedure_options(company_uuid=""):
    return {r.get("title", "Procedure"): r.get("system_uuid") for r in active_procedures(company_uuid)}


def target_options(module):
    return {target_label(r): r.get("system_uuid") for r in store.get(module, []) if not r.get("archived")}


st.title("Contacts & Suppliers")
st.caption("Supplier, contractor and external-support register for service, repair, tooling, spares, technical support and equipment purchasing.")

companies = active_companies()
contacts = active_contacts()
preferred = [c for c in companies if c.get("status") == "Preferred"]
used = [c for c in companies if c.get("status") in ["Preferred", "Approved / Used"]]

m = st.columns(5)
m[0].metric("Companies", len(companies))
m[1].metric("Contacts", len(contacts))
m[2].metric("Preferred", len(preferred))
m[3].metric("Approved / Used", len(used))
m[4].metric("Engagement Procedures", len(active_procedures()))

tabs = st.tabs([
    "Directory", "Companies", "People", "Engagement Procedures", "Engineering Links",
    "Usage & Performance", "Record Management"
])

with tabs[0]:
    st.subheader("Supplier & External Support Directory")
    c1, c2 = st.columns([3, 1])
    q = c1.text_input("Search directory", placeholder="company, contact, tooling, service, laser, grinding, calibration...")
    include_inactive = c2.checkbox("Include inactive / do not use")
    if q.strip():
        show(search_directory(store, q), "No matching companies or contacts.")
    else:
        show(directory_rows(store, include_inactive), "No suppliers or external contacts have been entered yet.")

    st.markdown("#### Who supports this engineering item?")
    mod = st.selectbox("Record type", TARGET_MODULES, format_func=lambda x: x.replace("_", " ").title(), key="dir_link_module")
    tmap = target_options(mod)
    if tmap:
        target = st.selectbox("Record", list(tmap), key="dir_link_target")
        show(relationships_for_target(store, mod, tmap[target]), "No external supplier/support relationship is linked to this record.")
    else:
        st.info("No records exist in this module yet.")

with tabs[1]:
    st.subheader("Companies")
    with st.form("new_supplier_company", clear_on_submit=True):
        a = st.columns(3)
        name = a[0].text_input("Company name *")
        status = a[1].selectbox("Usage status", COMPANY_STATUSES, index=1)
        types = a[2].multiselect("Company type / capability", COMPANY_TYPES)
        a = st.columns(3)
        phone = a[0].text_input("General phone")
        email = a[1].text_input("General email")
        website = a[2].text_input("Website")
        a = st.columns(3)
        account = a[0].text_input("Our account / customer number")
        after_hours = a[1].text_input("After-hours / emergency contact")
        address = a[2].text_input("Address")
        capabilities = st.text_area("Capabilities / what we use them for", placeholder="CNC service, Ded-Tru grinding wheels, laser technical support, calibration, equipment supply...")
        notes = st.text_area("Company notes")
        add = st.form_submit_button("Add Company", use_container_width=True)
    if add:
        if not name.strip():
            st.error("Company name is required.")
        else:
            create_company(store, name.strip(), types, status, phone, email, website, address, account, after_hours, capabilities, notes)
            st.success("Company added.")
            persist(store)
            st.rerun()

    rows = []
    for c in active_companies():
        perf = company_performance(store, c.get("system_uuid"))
        rows.append({
            "Company": c.get("company_name", ""), "Status": c.get("status", ""),
            "Types": ", ".join(c.get("company_types", [])), "Phone": c.get("phone", ""),
            "Email": c.get("email", ""), "Account No.": c.get("account_number", ""),
            "Last Used": perf["last_used"], "Uses": perf["jobs"], "Rating": round(perf["avg_rating"], 1) if perf["avg_rating"] else ""
        })
    show(rows, "No companies recorded.")

with tabs[2]:
    st.subheader("Contact People")
    cmap = company_options()
    if not cmap:
        st.info("Add a company before adding contact people.")
    else:
        with st.form("new_supplier_contact", clear_on_submit=True):
            company_name = st.selectbox("Company *", list(cmap))
            a = st.columns(3)
            name = a[0].text_input("Contact person *")
            role = a[1].text_input("Role / position")
            method = a[2].selectbox("Preferred contact method", ["Email", "Mobile", "Phone", "Portal", "Website Form", "Other"])
            a = st.columns(3)
            mobile = a[0].text_input("Mobile")
            phone = a[1].text_input("Phone")
            email = a[2].text_input("Email")
            availability = st.text_input("Availability / best time / after-hours details")
            responsibilities = st.text_area("What to contact this person for")
            notes = st.text_area("Contact notes")
            add = st.form_submit_button("Add Contact Person", use_container_width=True)
        if add:
            if not name.strip():
                st.error("Contact person is required.")
            else:
                create_contact(store, cmap[company_name], name.strip(), role, phone, mobile, email, method, availability, responsibilities, notes)
                st.success("Contact added.")
                persist(store)
                st.rerun()

    companies_by_id = by_uuid(store["supplier_companies"])
    show([{
        "Company": companies_by_id.get(r.get("company_uuid"), {}).get("company_name", ""),
        "Contact": r.get("contact_name", ""), "Role": r.get("role", ""),
        "Mobile": r.get("mobile", ""), "Phone": r.get("phone", ""), "Email": r.get("email", ""),
        "Preferred Method": r.get("preferred_method", ""), "Responsibilities": r.get("responsibilities", "")
    } for r in active_contacts()], "No contact people recorded.")

with tabs[3]:
    st.subheader("Engagement Procedures")
    st.caption("Record exactly how to arrange external service, repair, technical support, tooling/spares purchases, RFQs and contractor attendance.")
    cmap = company_options()
    if not cmap:
        st.info("Add a company first.")
    else:
        company_name = st.selectbox("Company", list(cmap), key="proc_company")
        company_uuid = cmap[company_name]
        pcontacts = contact_options(company_uuid)
        with st.form("new_engagement_procedure", clear_on_submit=True):
            a = st.columns(3)
            ptype = a[0].selectbox("Procedure type", PROCEDURE_TYPES)
            title = a[1].text_input("Procedure title *", placeholder="Arrange CNC service visit")
            contact_name = a[2].selectbox("Primary contact", [""] + list(pcontacts))
            preferred_method = st.text_input("Preferred first contact method", placeholder="Email John, then call service desk if urgent")
            first_step = st.text_area("First step / how to initiate", placeholder="Call service department and quote our customer number...")
            required = st.text_area("Information they require", placeholder="Machine model, serial, fault description, alarms, photos, production impact...")
            approval = st.text_area("Quote / approval / PO process", placeholder="Request quote → internal approval → PO → send PO → confirm booking")
            steps = st.text_area("Full engagement process / steps", height=180)
            emergency = st.text_area("Emergency / breakdown process", placeholder="After-hours number, escalation contact, what can be authorised...")
            notes = st.text_area("Additional notes")
            add = st.form_submit_button("Save Engagement Procedure", use_container_width=True)
        if add:
            if not title.strip():
                st.error("Procedure title is required.")
            else:
                create_procedure(store, company_uuid, ptype, title.strip(), pcontacts.get(contact_name, ""), preferred_method, first_step, required, approval, steps, emergency, notes)
                st.success("Engagement procedure saved.")
                persist(store)
                st.rerun()

    companies_by_id = by_uuid(store["supplier_companies"])
    contacts_by_id = by_uuid(store["supplier_contacts"])
    show([{
        "Company": companies_by_id.get(r.get("company_uuid"), {}).get("company_name", ""),
        "Type": r.get("procedure_type", ""), "Procedure": r.get("title", ""),
        "Primary Contact": contacts_by_id.get(r.get("contact_uuid"), {}).get("contact_name", ""),
        "First Contact": r.get("preferred_method", ""), "First Step": r.get("first_step", "")
    } for r in active_procedures()], "No engagement procedures recorded.")

with tabs[4]:
    st.subheader("Link Suppliers to Engineering Records")
    st.caption("Use hidden UUID relationships so a supplier/contact can remain connected even if names or internal IDs change later.")
    cmap = company_options()
    if not cmap:
        st.info("Add a company first.")
    else:
        company_name = st.selectbox("Company", list(cmap), key="link_company")
        company_uuid = cmap[company_name]
        conmap = contact_options(company_uuid)
        procmap = procedure_options(company_uuid)
        module = st.selectbox("Link to", TARGET_MODULES, format_func=lambda x: x.replace("_", " ").title())
        tmap = target_options(module)
        if not tmap:
            st.info("No records exist in the selected module.")
        else:
            with st.form("supplier_relationship"):
                target_name = st.selectbox("Engineering record", list(tmap))
                role = st.selectbox("Relationship / support role", RELATIONSHIP_ROLES)
                contact_name = st.selectbox("Preferred contact", [""] + list(conmap))
                procedure_name = st.selectbox("Engagement procedure", [""] + list(procmap))
                preferred = st.checkbox("Preferred supplier / support route", value=True)
                notes = st.text_area("Relationship notes", placeholder="Use for spindle faults; OEM parts only; preferred grinding wheel supplier...")
                add = st.form_submit_button("Create Engineering Link", use_container_width=True)
            if add:
                create_relationship(store, company_uuid, module, tmap[target_name], role, conmap.get(contact_name, ""), procmap.get(procedure_name, ""), preferred, notes)
                st.success("Supplier relationship linked.")
                persist(store)
                st.rerun()

    companies_by_id = by_uuid(store["supplier_companies"])
    contacts_by_id = by_uuid(store["supplier_contacts"])
    procedures_by_id = by_uuid(store["engagement_procedures"])
    rows = []
    for r in store["supplier_relationships"]:
        if r.get("archived"):
            continue
        target = by_uuid(store.get(r.get("target_module", ""), [])).get(r.get("target_uuid"), {})
        rows.append({
            "Company": companies_by_id.get(r.get("company_uuid"), {}).get("company_name", ""),
            "Role": r.get("role", ""), "Linked To": r.get("target_module", "").replace("_", " ").title(),
            "Record": target_label(target), "Contact": contacts_by_id.get(r.get("contact_uuid"), {}).get("contact_name", ""),
            "Procedure": procedures_by_id.get(r.get("procedure_uuid"), {}).get("title", ""),
            "Preferred": r.get("preferred", False)
        })
    show(rows, "No supplier relationships linked yet.")

with tabs[5]:
    st.subheader("Supplier Usage & Performance History")
    cmap = company_options()
    if not cmap:
        st.info("Add a company first.")
    else:
        company_name = st.selectbox("Company", list(cmap), key="usage_company")
        company_uuid = cmap[company_name]
        conmap = contact_options(company_uuid)
        with st.form("log_supplier_use", clear_on_submit=True):
            a = st.columns(4)
            used_date = a[0].date_input("Date", date.today())
            usage_type = a[1].selectbox("Type", ["Service / Repair", "Emergency Breakdown", "Tooling", "Spare Parts", "Consumables", "Equipment Purchase / RFQ", "Calibration", "Technical Support", "Contractor Work", "Other"])
            contact_name = a[2].selectbox("Contact used", [""] + list(conmap))
            reference = a[3].text_input("PO / quote / job / invoice reference")
            summary = st.text_input("What was supplied / performed? *")
            a = st.columns(4)
            response = a[0].number_input("Response time (hours)", min_value=0.0, value=0.0, step=0.5)
            cost = a[1].number_input("Cost ($)", min_value=0.0, value=0.0, step=10.0)
            rating = a[2].slider("Performance rating", 0, 5, 0, help="0 = not rated")
            module = a[3].selectbox("Related record type", [""] + TARGET_MODULES, format_func=lambda x: x.replace("_", " ").title() if x else "None")
            tmap = target_options(module) if module else {}
            target_name = st.selectbox("Related engineering record", [""] + list(tmap)) if module else ""
            result = st.text_area("Result / outcome")
            notes = st.text_area("Performance / follow-up notes")
            add = st.form_submit_button("Log Supplier Use", use_container_width=True)
        if add:
            if not summary.strip():
                st.error("A short summary is required.")
            else:
                log_supplier_usage(store, company_uuid, usage_type, summary.strip(), used_date, conmap.get(contact_name, ""), module, tmap.get(target_name, "") if module else "", reference, response, cost, result, rating, notes)
                st.success("Supplier usage logged.")
                persist(store)
                st.rerun()

        perf = company_performance(store, company_uuid)
        k = st.columns(5)
        k[0].metric("Recorded Uses", perf["jobs"])
        k[1].metric("Recorded Spend", f"${perf['spend']:,.2f}")
        k[2].metric("Avg Response", f"{perf['avg_response_hours']:.1f} h" if perf["avg_response_hours"] else "—")
        k[3].metric("Avg Rating", f"{perf['avg_rating']:.1f}/5" if perf["avg_rating"] else "—")
        k[4].metric("Last Used", perf["last_used"] or "—")

    companies_by_id = by_uuid(store["supplier_companies"])
    show([{
        "Date": r.get("usage_date", ""), "Company": companies_by_id.get(r.get("company_uuid"), {}).get("company_name", ""),
        "Type": r.get("usage_type", ""), "Summary": r.get("summary", ""), "Reference": r.get("reference", ""),
        "Response h": r.get("response_hours", 0), "Cost": r.get("cost", 0), "Rating": r.get("rating", 0), "Result": r.get("result", "")
    } for r in sorted(store["supplier_usage"], key=lambda x: x.get("usage_date", ""), reverse=True) if not r.get("archived")], "No supplier usage has been logged yet.")

with tabs[6]:
    st.subheader("Status, Used / Not Used & Record Management")
    cmap = company_options()
    if cmap:
        company_name = st.selectbox("Company", list(cmap), key="manage_company")
        company_uuid = cmap[company_name]
        company = by_uuid(store["supplier_companies"])[company_uuid]
        new_status = st.selectbox("Usage status", COMPANY_STATUSES, index=COMPANY_STATUSES.index(company.get("status")) if company.get("status") in COMPANY_STATUSES else 1)
        if st.button("Update Company Status", use_container_width=True):
            set_company_status(store, company_uuid, new_status)
            st.success("Company status updated.")
            persist(store)
            st.rerun()
        st.caption("Use Preferred / Approved / Alternative / Trial / Do Not Use / Inactive instead of deleting supplier history.")

        if st.button("Remove Company from Active Directory (Archive)", use_container_width=True):
            archive_record(store, "supplier_companies", company_uuid, True)
            st.success("Company archived. Historical links and usage records have been retained.")
            persist(store)
            st.rerun()
    else:
        st.info("No active companies to manage.")

    st.markdown("#### Contact activation / removal")
    all_contacts = [r for r in store["supplier_contacts"] if not r.get("archived")]
    companies_by_id = by_uuid(store["supplier_companies"])
    if all_contacts:
        conmap = {f"{companies_by_id.get(r.get('company_uuid'),{}).get('company_name','')} — {contact_label(r)}": r.get("system_uuid") for r in all_contacts}
        selected = st.selectbox("Contact", list(conmap), key="manage_contact")
        if st.button("Remove Contact from Active Directory (Archive)", use_container_width=True):
            archive_record(store, "supplier_contacts", conmap[selected], True)
            st.success("Contact archived; historical records remain linked.")
            persist(store)
            st.rerun()
    else:
        st.info("No active contacts to manage.")

st.caption("All supplier links use hidden UUIDs. Company/contact names, account numbers and statuses can change without breaking engineering relationships. Archived suppliers remain in historical usage records and backups.")

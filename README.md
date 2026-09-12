# Process and Maintenance Engineering System

A company-wide Streamlit system for process engineering, maintenance engineering, engineering trials, machinery/tooling research, asset management and engineering knowledge.

Live app: https://process-and-maintenance-engineering-system-web.streamlit.app

## Core design

The system uses hidden UUIDs for internal relationships. Human-facing business IDs, legacy IDs, aliases and convenient display IDs remain metadata, so numbering can change without breaking links between records.

The current deployment is intentionally optimised for a **single engineering user**. Persistence remains local-first: the current Streamlit session holds the working data and downloaded JSON/ZIP backups are the durable record. No persistent multi-user database or account system is required for the present use case.

## Main engineering system

The core application includes:

- Dashboard with engineering workload, PM due/overdue, breakdown downtime, MTTR and MTBF
- Asset Register with equipment profiles, criticality, utilities, safety, configuration and maintenance history
- Products & Process Routes
- Engineering Action Register
- Preventive Maintenance Schedules
- Maintenance & Breakdown Management
- Process Engineering & Improvement
- Engineering Trials
- Machinery & Tooling Research
- Tooling Knowledge Library
- Spare Parts / Consumables Register
- RCA & Engineering Investigations
- Engineering Management PDF reporting
- System JSON and ZIP backup

## Engineering Operations

`pages/1_Engineering_Operations.py` provides the execution layer:

- Task-by-task PM completion
- Automatic next-due calculation
- Labour, service and parts cost capture
- Automatic spare stock deduction
- Machine-specific maintenance packs
- Breakdown follow-up to Engineering Action or RCA
- Failure categorisation and recurring-failure detection
- Downtime Pareto
- Maintenance cost analysis
- Linked Asset Engineering History

Initial maintenance packs cover CNC, Grinding, Cutting, Laser, Filtration, Chiller, Extraction, Pump, Vacuum and Furnace. They are starting templates and must be verified against the actual equipment, OEM documentation and internal engineering requirements before becoming controlled standards. Laser tasks remain deliberately high-level so the final standard follows the actual in-house laser design/configuration.

Operational helpers are in `next_layer.py` and `advanced_operations.py`.

## Engineering Control Centre

`pages/2_Engineering_Control_Centre.py` provides the lightweight CMMS/control-centre layer:

- Maintenance work orders
- Planned shutdown management
- Condition-monitoring readings and trends
- Asset criticality / risk scoring
- Advisory automatic RCA triggers
- Engineering handover dashboard

The control-centre logic is in `control_centre.py`.

## Production Readiness Workspace

`pages/3_Production_Readiness.py` is the final single-user production-readiness layer. Its engine is `production_readiness.py`.

### My Engineering Day

A daily attention view combines urgent engineering work, assets down, stock warnings and open engineering changes so the system opens on actionable work rather than static records.

### Quick Capture and Engineering Inbox

Fast capture supports breakdown notes, engineering issues, maintenance items, process ideas, trial notes, research ideas and general notes. Captured items remain in an Engineering Inbox until promoted into a formal Action, Maintenance record, Trial, Research record, Engineering Change or Diary entry. Promotion retains the source link.

### Global engineering search

One search scans assets, maintenance, PM, actions, work orders, shutdowns, condition readings, process improvements, trials, research, RCA, products/routes, tooling, spares, diary entries, decisions, engineering changes, lessons learned and document references.

### Asset 360

Selecting an asset shows a combined engineering timeline plus linked:

- Maintenance
- PM schedules
- Work orders
- Condition monitoring
- Engineering actions
- Process improvements
- Trials
- RCA
- Engineering changes
- Tooling
- Spares
- Lessons learned
- References

### Engineering Change Register

Formal change control follows:

`Problem -> Existing State -> Proposed Change -> Risk Review -> Trial -> Decision -> Implementation -> Validation -> Before/After Result -> Final Standard`

This creates a defensible engineering history explaining why a process, machine configuration, tool, fixture or standard was changed.

### Engineering knowledge system

The production workspace adds:

- Engineering Diary
- Decision Register including rationale, evidence and alternatives considered
- Lessons Learned / Known Issues
- Structured references for drawings, manuals, photos, CNC programs, supplier documents, calibration records, procedures, specifications, folders and web links

References store locations/identifiers rather than forcing large files into the Streamlit JSON.

### Record lifecycle and display IDs

Records can be assigned optional convenient display numbers such as `WO-0001`, `RCA-0001`, `EC-0001` and similar module-specific numbers while hidden UUIDs remain the relational keys.

Records can move through Draft, Active, Complete, Closed and Archived lifecycle states. Archiving preserves engineering history rather than deleting it. Records can also be cloned; clones receive a new hidden UUID and new display ID.

### Data quality and system health

Built-in checks flag examples such as:

- Active assets without PM schedules
- Breakdown records without a failure category/diagnosis
- Completed work orders without completion notes
- Spares without minimum stock levels
- Overdue engineering actions
- Missing/orphaned UUID links

The System Health view reports schema/version, record counts, data-quality issues, orphan links and backup age.

### Backup and recovery

For the present single-user architecture:

- Downloaded JSON/ZIP remains the durable backup
- Configurable backup reminders flag when a backup is due
- Uploaded JSON can be validated before restoration
- A temporary in-session recovery snapshot can be created/restored for protection against accidental edits during the current browser session

An in-session snapshot is **not** a substitute for downloading the full backup because the Streamlit session itself is not permanent.

## Contacts & Suppliers

`pages/4_Contacts_and_Suppliers.py` adds the external-support and purchasing layer. Its backend is `supplier_contacts.py`.

The module stores:

- Supplier / contractor companies
- Individual contact people and their roles
- Phone, mobile, email, website, address and account/customer numbers
- Preferred contact method and availability
- Company capabilities and what they are used for
- Usage status: Preferred, Approved / Used, Alternative, Trial / Prospective, Do Not Use or Inactive
- Engagement procedures for Service & Repair, Emergency Breakdown, Spare Parts, Tooling Purchase, Consumables Purchase, Equipment Purchase / RFQ, Technical Support, Calibration, Contractor Attendance and Warranty Claims
- Required information, approval/PO process, escalation and emergency process
- Links from suppliers/contacts/procedures to assets, tooling, spares, research, work orders, maintenance and products using hidden UUID relationships
- Supplier usage and performance history including response time, recorded spend, outcome and optional 0–5 performance rating

The Directory can answer practical questions such as who services a machine, who supplies a tool or spare, which contact to use, and the documented procedure for arranging the work or purchase.

Removing a supplier/contact from active use archives the record instead of destroying history. Historical jobs, purchases and engineering relationships remain intact in JSON/ZIP backups.

## JSON compatibility

Schema: `process-maintenance-engineering-system`

The core loader remains compatible with version 1 and version 2 JSON backups. Production-readiness and supplier/contact collections are additive and are preserved because unknown top-level collections are retained by the loader.

## Privacy / storage

The hosted Streamlit app does not use a persistent database. Uploaded JSON is processed by the hosted Streamlit session, so data does travel to the Streamlit server during use. Downloaded JSON/ZIP files are the intended persistent record. If data must never leave the local computer, run the app locally instead of using the hosted deployment.

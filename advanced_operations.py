from collections import Counter, defaultdict
from datetime import date

from engineering_system import base_record, by_uuid, now_iso, parse_date, record_label, asset_label_by_uuid
from next_layer import spare_stock_status


def checklist_items(text):
    rows=[]
    for line in str(text or '').splitlines():
        item=line.strip().lstrip('-•*0123456789. )(').strip()
        if item:
            rows.append(item)
    return rows


def consume_spares(store, maintenance_uuid, consumption):
    """consumption: list of {spare_uuid, quantity}. Deduct stock and attach structured usage to maintenance record."""
    maint=by_uuid(store.get('maintenance',[])).get(maintenance_uuid)
    if not maint:
        raise KeyError('Maintenance record not found')
    used=[]
    smap=by_uuid(store.get('spares',[]))
    for row in consumption or []:
        uid=row.get('spare_uuid'); qty=float(row.get('quantity',0) or 0)
        if not uid or qty<=0 or uid not in smap:
            continue
        spare=smap[uid]
        before=float(spare.get('quantity_on_hand',0) or 0)
        after=max(0.0,before-qty)
        spare['quantity_on_hand']=after
        spare['updated_at']=now_iso()
        unit=float(spare.get('unit_cost',spare.get('cost',0)) or 0)
        used.append({'spare_uuid':uid,'part':record_label(spare),'quantity':qty,'unit_cost':unit,'total_cost':qty*unit,'stock_before':before,'stock_after':after})
    maint['parts_consumed']=used
    maint['parts_cost']=sum(x['total_cost'] for x in used)
    maint['updated_at']=now_iso()
    return used


def apply_pm_completion_details(store, maintenance_uuid, checklist_results=None, labour_rate=0.0, external_cost=0.0, consumption=None):
    maint=by_uuid(store.get('maintenance',[])).get(maintenance_uuid)
    if not maint:
        raise KeyError('Maintenance record not found')
    maint['checklist_results']=checklist_results or []
    hours=float(maint.get('repair_hours',0) or 0)
    rate=float(labour_rate or 0)
    maint['labour_rate']=rate
    maint['labour_cost']=hours*rate
    maint['external_cost']=float(external_cost or 0)
    consume_spares(store,maintenance_uuid,consumption or [])
    maint['total_maintenance_cost']=float(maint.get('labour_cost',0))+float(maint.get('parts_cost',0))+float(maint.get('external_cost',0))
    maint['updated_at']=now_iso()
    return maint


def downtime_pareto(store):
    totals=defaultdict(float)
    counts=Counter()
    for r in store.get('maintenance',[]):
        if r.get('maintenance_type')!='Breakdown':
            continue
        asset=asset_label_by_uuid(store,r.get('asset_uuid')) or 'Unassigned'
        totals[asset]+=float(r.get('downtime_hours',0) or 0)
        counts[asset]+=1
    rows=[{'Asset':a,'Breakdowns':counts[a],'Downtime h':round(v,2)} for a,v in totals.items()]
    rows.sort(key=lambda x:x['Downtime h'],reverse=True)
    running=0.0; total=sum(x['Downtime h'] for x in rows)
    for row in rows:
        running+=row['Downtime h']
        row['Cumulative %']=round((running/total*100) if total else 0,1)
    return rows


def recurring_failures(store, min_occurrences=2):
    groups=defaultdict(list)
    for r in store.get('maintenance',[]):
        if r.get('maintenance_type')!='Breakdown':
            continue
        asset=r.get('asset_uuid') or 'unassigned'
        cause=(r.get('failure_category') or r.get('diagnosis') or r.get('symptom') or r.get('title') or 'Uncategorised').strip().lower()
        key=(asset,cause[:120])
        groups[key].append(r)
    rows=[]
    for (asset,cause), recs in groups.items():
        if len(recs)<int(min_occurrences):
            continue
        rows.append({'Asset':asset_label_by_uuid(store,asset) or 'Unassigned','Failure / cause':cause,'Occurrences':len(recs),'Downtime h':round(sum(float(x.get('downtime_hours',0) or 0) for x in recs),2),'Latest':max(str(x.get('event_date','')) for x in recs)})
    return sorted(rows,key=lambda x:(x['Occurrences'],x['Downtime h']),reverse=True)


def maintenance_cost_summary(store):
    rows=[]
    totals=defaultdict(float)
    for r in store.get('maintenance',[]):
        labour=float(r.get('labour_cost',0) or 0)
        parts=float(r.get('parts_cost',0) or 0)
        external=float(r.get('external_cost',0) or 0)
        total=float(r.get('total_maintenance_cost',labour+parts+external) or 0)
        asset=asset_label_by_uuid(store,r.get('asset_uuid')) or 'Unassigned'
        totals[asset]+=total
        rows.append({'Date':r.get('event_date',''),'Asset':asset,'Type':r.get('maintenance_type',''),'Labour':labour,'Parts':parts,'External':external,'Total':total,'Record':r.get('title','')})
    return rows, [{'Asset':k,'Maintenance Cost':round(v,2)} for k,v in sorted(totals.items(),key=lambda x:x[1],reverse=True)]


MAINTENANCE_PACKS={
'CNC':[
 ('Daily operator condition check','Daily',['Check lubrication level / alarms','Check coolant level and concentration','Inspect chuck/workholding condition','Check air pressure and leaks','Clean swarf from critical areas']),
 ('Weekly CNC maintenance','Weekly',['Inspect way lubrication delivery','Inspect coolant strainers / filters','Check hydraulic level and leaks','Inspect spindle/chuck area','Check cabinet filters and fans']),
 ('Monthly CNC maintenance','Monthly',['Inspect belts/couplings where applicable','Check turret/toolchanger condition','Inspect way covers and wipers','Check coolant concentration and contamination','Inspect electrical cabinet condition']),
 ('Annual CNC condition review','Annual',['Check backlash / repeatability','Check spindle condition / runout','Inspect batteries and backup status','Inspect hydraulic/pneumatic systems','Review alarms and recurring faults'])],
'Grinding':[
 ('Daily grinding condition check','Daily',['Inspect wheel condition and guarding','Check coolant flow and concentration','Inspect dressing system','Check spindle noise/vibration','Clean sludge from working area']),
 ('Weekly grinding maintenance','Weekly',['Inspect wheel flange and mounting','Check coolant filtration / sludge load','Inspect slides/ways and lubrication','Inspect extraction','Check pumps, hoses and seals']),
 ('Quarterly grinding condition review','Quarterly',['Check spindle/bearing condition','Inspect dressing accuracy','Check machine geometry / repeatability as applicable','Inspect guards/interlocks','Review wheel and consumable performance'])],
'Cutting':[
 ('Daily cutting machine check','Daily',['Inspect cutting tool/blade condition','Check coolant or process fluid delivery','Inspect fixture/support condition','Check guarding/interlocks','Clean debris and sludge']),
 ('Monthly cutting maintenance','Monthly',['Inspect spindle/drive system','Inspect guides/axes','Check pumps and filtration','Inspect hoses/seals','Verify cut quality and repeatability'])],
'Laser':[
 ('Laser system condition check','Weekly',['Inspect system for contamination/damage','Verify cooling system condition','Inspect motion/fixture condition','Review system alarms/logs','Verify safety interlocks']),
 ('Laser system engineering maintenance','Quarterly',['Inspect internally defined optical/process components','Verify cooling and extraction performance','Check motion accuracy / repeatability','Review software/configuration revision','Record any in-house engineering changes'])],
'Filtration':[
 ('Filtration system weekly check','Weekly',['Check differential pressure / flow','Inspect filters/separators','Check sludge collection','Inspect pumps and leaks','Check coolant/fluid condition']),
 ('Filtration system quarterly service','Quarterly',['Service filter elements as required','Inspect pump condition','Clean tank/reservoir','Inspect hoses/valves','Review consumable usage'])],
'Chiller':[
 ('Chiller weekly check','Weekly',['Check temperatures and alarms','Inspect fluid level','Inspect leaks','Check condenser/airflow','Check pump operation']),
 ('Chiller quarterly service','Quarterly',['Clean heat-exchange surfaces as applicable','Inspect filters','Check pump/fan condition','Inspect hoses/connections','Review temperature stability'])],
'Extraction':[
 ('Extraction weekly check','Weekly',['Check airflow / suction','Inspect filters','Inspect ducting/leaks','Check fan noise/vibration','Empty collection points']),
 ('Extraction quarterly service','Quarterly',['Inspect fan/bearings','Service/replace filters as required','Inspect ducting and dampers','Check electrical/control condition','Verify extraction performance'])],
'Pump':[
 ('Pump monthly inspection','Monthly',['Inspect leaks/seals','Check noise/vibration','Check flow/pressure','Inspect connections','Check motor condition'])],
'Vacuum':[
 ('Vacuum system monthly inspection','Monthly',['Check vacuum level','Inspect filters','Inspect leaks','Check pump condition','Inspect hoses/connections'])],
'Furnace':[
 ('Furnace monthly condition check','Monthly',['Inspect temperature control','Inspect chamber/insulation','Check door/seals','Verify safety interlocks','Review alarms']),
 ('Furnace annual review','Annual',['Verify temperature accuracy/uniformity as required','Inspect heaters/elements','Inspect controls and safety circuits','Inspect ventilation/extraction','Review service history'])]
}


def seed_maintenance_pack(store, asset_class, owner=''):
    created=[]
    existing={(str(x.get('asset_class','')),str(x.get('title',''))) for x in store.setdefault('pm_templates',[])}
    for title,frequency,items in MAINTENANCE_PACKS.get(asset_class,[]):
        if (asset_class,title) in existing:
            continue
        r=base_record('pm_template',title,'')
        r.update({'asset_class':asset_class,'frequency':frequency,'custom_interval_days':0,'owner':owner,'estimated_hours':0.0,'checklist':'\n'.join(f'- {x}' for x in items),'safety_requirements':'Follow site isolation, lockout/tagout and equipment-specific safety requirements before work.','required_parts':'','reference':'Initial engineering maintenance pack — verify against OEM/in-house requirements before adoption.'})
        store['pm_templates'].append(r); created.append(r)
    return created

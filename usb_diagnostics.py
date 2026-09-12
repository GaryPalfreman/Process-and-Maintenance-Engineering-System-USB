"""Non-destructive diagnostics for the USB Engineering Vault."""
from copy import deepcopy
from datetime import date

from engineering_system import base_record
from usb_storage import create_backup, load_from_vault, save_to_vault

TEST_TAG = "__PMES_USB_SELF_TEST__"


def _record(record_type, title):
    record = base_record(record_type, title, "USB Diagnostics")
    record["diagnostic_tag"] = TEST_TAG
    return record


def run_persistence_self_test(vault, live_store, encryption_key=None):
    """Write/read/verify four linked module records, then restore original data."""
    original = deepcopy(live_store)
    test_store = deepcopy(live_store)
    safety = create_backup(vault, original, "pre_self_test", encryption_key)
    created = {}
    results = []

    try:
        asset = _record("asset", "USB Persistence Test Asset")
        asset.update({"asset_class": "Other", "status": "Active", "criticality": "Low"})
        test_store.setdefault("assets", []).append(asset)
        created["assets"] = asset["system_uuid"]

        action = _record("engineering_action", "USB Persistence Test Action")
        action.update({
            "asset_uuid": asset["system_uuid"], "priority": "Low", "status": "Open",
            "due_date": date.today().isoformat(),
        })
        test_store.setdefault("actions", []).append(action)
        created["actions"] = action["system_uuid"]

        maintenance = _record("maintenance", "USB Persistence Test Maintenance")
        maintenance.update({
            "asset_uuid": asset["system_uuid"], "maintenance_type": "Preventive",
            "event_date": date.today().isoformat(), "status": "Complete",
            "downtime_hours": 0, "repair_hours": 0,
        })
        test_store.setdefault("maintenance", []).append(maintenance)
        created["maintenance"] = maintenance["system_uuid"]

        pm = _record("pm_schedule", "USB Persistence Test PM")
        pm.update({
            "asset_uuid": asset["system_uuid"], "frequency": "Annual",
            "next_due_date": date.today().isoformat(), "status": "Active",
        })
        test_store.setdefault("pm_schedules", []).append(pm)
        created["pm_schedules"] = pm["system_uuid"]

        save_to_vault(vault, test_store, encryption_key)
        reloaded = load_from_vault(vault, encryption_key)

        for module, uid in created.items():
            found = next((r for r in reloaded.get(module, []) if r.get("system_uuid") == uid), None)
            results.append({
                "module": module,
                "write_read": bool(found),
                "uuid_preserved": bool(found and found.get("system_uuid") == uid),
                "tag_preserved": bool(found and found.get("diagnostic_tag") == TEST_TAG),
            })

        asset_ok = next((r for r in reloaded.get("assets", []) if r.get("system_uuid") == created["assets"]), None)
        links_ok = True
        for module in ["actions", "maintenance", "pm_schedules"]:
            record = next((r for r in reloaded.get(module, []) if r.get("system_uuid") == created[module]), None)
            links_ok = links_ok and bool(record and asset_ok and record.get("asset_uuid") == asset_ok.get("system_uuid"))

        passed = all(r["write_read"] and r["uuid_preserved"] and r["tag_preserved"] for r in results) and links_ok
        return {
            "passed": passed,
            "results": results,
            "links_ok": links_ok,
            "safety_backup": str(safety),
            "message": "Persistence self-test passed." if passed else "Persistence self-test found a problem.",
        }
    finally:
        save_to_vault(vault, original, encryption_key)

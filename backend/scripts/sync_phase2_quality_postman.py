"""Sync Postman collections — Phase 2 Module 4: Data Quality."""
import json, os, uuid as uuid_mod

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = [
    os.path.join(BASE_DIR, "deltameta_auth.postman_collection.json"),
    os.path.join(BASE_DIR, "vercel_deltameta_auth.postman_collection.json"),
]

def _id(): return str(uuid_mod.uuid4())

def make_request(name, method, path, base_var, body=None, query_params=None, description=""):
    url_raw = base_var + path
    request = {
        "method": method.upper(),
        "header": [{"key": "Authorization", "value": "Bearer {{token}}"}],
        "url": {"raw": url_raw, "host": [base_var], "path": [p for p in path.lstrip("/").split("/") if p]},
        "description": description,
    }
    if query_params:
        request["url"]["query"] = [{"key": p["key"], "value": p.get("value",""), "disabled": p.get("disabled",True)} for p in query_params]
    if body is not None:
        request["body"] = {"mode": "raw", "raw": json.dumps(body, indent=2), "options": {"raw": {"language": "json"}}}
    return {"id": _id(), "name": name, "request": request, "response": []}

def subfolder(name, items):
    return {"id": _id(), "name": name, "item": items}

def replace_or_append_folder(items, folder):
    for i, item in enumerate(items):
        if item.get("name") == folder["name"] and "item" in item:
            items[i] = folder; return
    items.append(folder)

def _quality_folder(base_var):
    tc_body = {
        "asset_id": "{{asset_id}}",
        "name": "Row count must be between 100 and 9999",
        "level": "table",
        "test_type": "row_count_between",
        "dimension": "completeness",
        "config": {"min": 100, "max": 9999},
        "severity": "critical",
        "tags": [],
        "is_active": True,
    }
    ts_body = {
        "name": "Customer Data Suite",
        "suite_type": "bundle",
        "test_case_ids": ["{{test_case_id}}"],
        "has_pipeline": True,
        "trigger_mode": "on_demand",
        "enable_debug_log": False,
        "raise_on_error": True,
    }
    run_update_body = {
        "status": "success",
        "result_detail": {"pass_count": 1, "fail_count": 0},
        "started_at": "2026-03-04T09:00:00Z",
        "completed_at": "2026-03-04T09:00:05Z",
    }
    incident_update_body = {"status": "in_progress", "assignee_id": "{{user_id}}", "severity": "critical"}

    tc_items = [
        make_request("Create Test Case", "POST", "/quality/test-cases", base_var, body=tc_body,
                     description="level: table|column|dimension  test_type: row_count_between|..."),
        make_request("List Test Cases", "GET", "/quality/test-cases", base_var,
                     query_params=[
                         {"key":"asset_id","value":"","disabled":True},
                         {"key":"level","value":"","disabled":True},
                         {"key":"test_type","value":"","disabled":True},
                         {"key":"dimension","value":"","disabled":True},
                         {"key":"is_active","value":"","disabled":True},
                         {"key":"severity","value":"","disabled":True},
                         {"key":"search","value":"","disabled":True},
                     ]),
        make_request("Get Test Case", "GET", "/quality/test-cases/{{test_case_id}}", base_var),
        make_request("Update Test Case", "PUT", "/quality/test-cases/{{test_case_id}}", base_var,
                     body={"is_active": True, "severity": "warning"}),
        make_request("Delete Test Case", "DELETE", "/quality/test-cases/{{test_case_id}}", base_var),
        make_request("Run Test Case", "POST", "/quality/test-cases/{{test_case_id}}/run", base_var),
        make_request("List Test Case Runs", "GET", "/quality/test-cases/{{test_case_id}}/runs", base_var,
                     query_params=[{"key":"status","value":"","disabled":True}]),
    ]
    ts_items = [
        make_request("Create Test Suite", "POST", "/quality/test-suites", base_var, body=ts_body),
        make_request("List Test Suites", "GET", "/quality/test-suites", base_var,
                     query_params=[
                         {"key":"suite_type","value":"","disabled":True},
                         {"key":"asset_id","value":"","disabled":True},
                         {"key":"has_pipeline","value":"","disabled":True},
                         {"key":"search","value":"","disabled":True},
                     ]),
        make_request("Get Test Suite", "GET", "/quality/test-suites/{{test_suite_id}}", base_var),
        make_request("Update Test Suite", "PUT", "/quality/test-suites/{{test_suite_id}}", base_var,
                     body={"has_pipeline": False}),
        make_request("Delete Test Suite", "DELETE", "/quality/test-suites/{{test_suite_id}}", base_var),
        make_request("Run Test Suite", "POST", "/quality/test-suites/{{test_suite_id}}/run", base_var),
        make_request("List Test Suite Runs", "GET", "/quality/test-suites/{{test_suite_id}}/runs", base_var,
                     query_params=[{"key":"status","value":"","disabled":True}]),
    ]
    run_items = [
        make_request("List All Runs", "GET", "/quality/runs", base_var,
                     query_params=[
                         {"key":"test_case_id","value":"","disabled":True},
                         {"key":"test_suite_id","value":"","disabled":True},
                         {"key":"status","value":"","disabled":True},
                         {"key":"triggered_by","value":"","disabled":True},
                     ]),
        make_request("Get Run", "GET", "/quality/runs/{{test_run_id}}", base_var),
        make_request("Update Run (Post Results)", "PUT", "/quality/runs/{{test_run_id}}", base_var, body=run_update_body),
    ]
    incident_items = [
        make_request("List Incidents", "GET", "/quality/incidents", base_var,
                     query_params=[
                         {"key":"test_case_id","value":"","disabled":True},
                         {"key":"asset_id","value":"","disabled":True},
                         {"key":"status","value":"","disabled":True},
                         {"key":"assignee_id","value":"","disabled":True},
                         {"key":"severity","value":"","disabled":True},
                     ]),
        make_request("Get Incident", "GET", "/quality/incidents/{{incident_id}}", base_var),
        make_request("Update Incident", "PUT", "/quality/incidents/{{incident_id}}", base_var, body=incident_update_body),
        make_request("Delete Incident", "DELETE", "/quality/incidents/{{incident_id}}", base_var),
    ]

    return {
        "id": _id(), "name": "Data Quality",
        "item": [
            subfolder("Test Cases", tc_items),
            subfolder("Test Suites", ts_items),
            subfolder("Test Runs", run_items),
            subfolder("Incidents", incident_items),
        ],
    }

def main():
    for fpath in FILES:
        if not os.path.exists(fpath): print(f"SKIP: {fpath}"); continue
        print(f"\nProcessing: {os.path.basename(fpath)}")
        with open(fpath) as f: collection = json.load(f)
        base_var = "{{vercel_base_url}}" if "vercel_base_url" in {v["key"] for v in collection.get("variable", [])} else "{{base_url}}"
        replace_or_append_folder(collection.get("item", []), _quality_folder(base_var))
        variables = collection.get("variable", [])
        existing = {v["key"] for v in variables}
        for key in ("test_case_id", "test_suite_id", "test_run_id", "incident_id"):
            if key not in existing: variables.append({"key": key, "value": "", "type": "string"})
        collection["variable"] = variables
        with open(fpath, "w") as f: json.dump(collection, f, indent=2, ensure_ascii=False)
        print(f"  Added/Updated: Data Quality folder (21 endpoints in 4 subfolders)")
        print(f"  Saved: {os.path.basename(fpath)}")

if __name__ == "__main__":
    main()

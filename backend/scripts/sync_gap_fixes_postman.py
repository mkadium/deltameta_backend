"""
Sync Postman collections with Gap-Fix endpoints added after Pre-Phase 2.

New endpoints added:
  Roles:
    GET /roles/{role_id}/policies         — list policies assigned to a role
    GET /roles/{role_id}/teams            — list teams that have this role

  Policies:
    GET /policies/{policy_id}/roles       — list roles that have this policy
    GET /policies/{policy_id}/teams       — list teams that have this policy

  Datasets:
    GET /datasets/{dataset_id}/owners     — list owners of a dataset
    GET /datasets/{dataset_id}/experts    — list experts of a dataset

  Data Assets:
    GET /data-assets/{asset_id}/tags      — list classification tags on an asset
    GET /data-assets/{asset_id}/owners    — list owners of a data asset
    GET /data-assets/{asset_id}/experts   — list experts of a data asset

  Scheduled Tasks (new router):
    GET    /scheduled-tasks               — list tasks
    POST   /scheduled-tasks               — create task
    GET    /scheduled-tasks/{id}          — get task
    PUT    /scheduled-tasks/{id}          — update task
    DELETE /scheduled-tasks/{id}          — delete task
    PATCH  /scheduled-tasks/{id}/activate
    PATCH  /scheduled-tasks/{id}/deactivate
    POST   /scheduled-tasks/{id}/trigger

  Admin Users:
    GET /admin/users/{user_id}/roles      — list roles of a user
    GET /admin/users/{user_id}/teams      — list teams of a user
    GET /admin/users/{user_id}/policies   — list policies of a user
"""
import json
import os
import uuid as uuid_mod

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = [
    os.path.join(BASE_DIR, "deltameta_auth.postman_collection.json"),
    os.path.join(BASE_DIR, "vercel_deltameta_auth.postman_collection.json"),
]


def _id():
    return str(uuid_mod.uuid4())


def make_get(name, path, base_var, query_params=None, description=""):
    url_raw = base_var + path
    url_parts = [p for p in path.lstrip("/").split("/") if p]
    request = {
        "method": "GET",
        "header": [{"key": "Authorization", "value": "Bearer {{token}}"}],
        "url": {"raw": url_raw, "host": [base_var], "path": url_parts},
        "description": description,
    }
    if query_params:
        request["url"]["query"] = [
            {"key": p["key"], "value": p.get("value", ""), "disabled": p.get("disabled", True)}
            for p in query_params
        ]
    return {"id": _id(), "name": name, "request": request, "response": []}


def make_request(name, method, path, base_var, body=None, query_params=None, description=""):
    url_raw = base_var + path
    url_parts = [p for p in path.lstrip("/").split("/") if p]
    request = {
        "method": method.upper(),
        "header": [{"key": "Authorization", "value": "Bearer {{token}}"}],
        "url": {"raw": url_raw, "host": [base_var], "path": url_parts},
        "description": description,
    }
    if query_params:
        request["url"]["query"] = [
            {"key": p["key"], "value": p.get("value", ""), "disabled": p.get("disabled", True)}
            for p in query_params
        ]
    if body is not None:
        request["body"] = {"mode": "raw", "raw": json.dumps(body, indent=2),
                           "options": {"raw": {"language": "json"}}}
    return {"id": _id(), "name": name, "request": request, "response": []}


def find_folder(items, name):
    for item in items:
        if item.get("name") == name and "item" in item:
            return item
    return None


def replace_or_append_folder(items, folder):
    for i, item in enumerate(items):
        if item.get("name") == folder["name"] and "item" in item:
            items[i] = folder
            return
    items.append(folder)


def upsert_request(folder, request):
    """Add request to folder if not already present (match by name)."""
    for i, item in enumerate(folder["item"]):
        if item.get("name") == request["name"]:
            folder["item"][i] = request
            return
    folder["item"].append(request)
    print(f"    + Added: {request['name']}")


# ---------------------------------------------------------------------------
# Scheduled Tasks folder (new router)
# ---------------------------------------------------------------------------

def _scheduled_tasks_folder(base_var):
    return {
        "id": _id(),
        "name": "Scheduled Tasks",
        "item": [
            make_get("List Scheduled Tasks", "/scheduled-tasks", base_var,
                query_params=[
                    {"key": "entity_type", "value": "", "disabled": True},
                    {"key": "entity_id", "value": "", "disabled": True},
                    {"key": "schedule_type", "value": "", "disabled": True},
                    {"key": "is_active", "value": "", "disabled": True},
                    {"key": "last_status", "value": "", "disabled": True},
                    {"key": "search", "value": "", "disabled": True},
                ]),
            make_request("Create Scheduled Task", "POST", "/scheduled-tasks", base_var,
                body={
                    "entity_type": "bot",
                    "entity_id": "{{bot_id}}",
                    "task_name": "Nightly Metadata Scan",
                    "schedule_type": "scheduled",
                    "cron_expr": "0 2 * * *",
                    "payload": {},
                    "is_active": True,
                }),
            make_get("Get Scheduled Task", "/scheduled-tasks/{{task_id}}", base_var),
            make_request("Update Scheduled Task", "PUT", "/scheduled-tasks/{{task_id}}", base_var,
                body={"task_name": "Updated Task Name", "is_active": True}),
            make_request("Activate Scheduled Task", "PATCH", "/scheduled-tasks/{{task_id}}/activate", base_var),
            make_request("Deactivate Scheduled Task", "PATCH", "/scheduled-tasks/{{task_id}}/deactivate", base_var),
            make_request("Trigger Scheduled Task", "POST", "/scheduled-tasks/{{task_id}}/trigger", base_var),
            make_request("Delete Scheduled Task", "DELETE", "/scheduled-tasks/{{task_id}}", base_var),
        ],
    }


# ---------------------------------------------------------------------------
# New GET sub-resource endpoints per folder
# ---------------------------------------------------------------------------

# folder_name → list of new GET requests to upsert
NEW_GET_ENDPOINTS = {
    "Roles": [
        make_get("List Role Policies", "/roles/{{role_id}}/policies", "{BASE}"),
        make_get("List Role Teams", "/roles/{{role_id}}/teams", "{BASE}"),
    ],
    "Policies": [
        make_get("List Policy Roles", "/policies/{{policy_id}}/roles", "{BASE}"),
        make_get("List Policy Teams", "/policies/{{policy_id}}/teams", "{BASE}"),
    ],
    "Datasets": [
        make_get("List Dataset Owners", "/datasets/{{dataset_id}}/owners", "{BASE}"),
        make_get("List Dataset Experts", "/datasets/{{dataset_id}}/experts", "{BASE}"),
    ],
    "Data Assets": [
        make_get("List Asset Tags", "/data-assets/{{asset_id}}/tags", "{BASE}"),
        make_get("List Asset Owners", "/data-assets/{{asset_id}}/owners", "{BASE}"),
        make_get("List Asset Experts", "/data-assets/{{asset_id}}/experts", "{BASE}"),
    ],
    "Admin — User Management": [
        make_get("Get User Roles", "/admin/users/{{user_id}}/roles", "{BASE}"),
        make_get("Get User Teams", "/admin/users/{{user_id}}/teams", "{BASE}"),
        make_get("Get User Policies", "/admin/users/{{user_id}}/policies", "{BASE}"),
    ],
}


def _patch_base_var(request_obj, base_var):
    """Replace the {BASE} placeholder injected during build with the actual base_var."""
    raw = request_obj["request"]["url"]["raw"]
    request_obj["request"]["url"]["raw"] = raw.replace("{BASE}", base_var)
    request_obj["request"]["url"]["host"] = [base_var]
    return request_obj


def _apply_new_get_endpoints(items, base_var):
    for folder_name, requests in NEW_GET_ENDPOINTS.items():
        folder = find_folder(items, folder_name)
        if not folder:
            print(f"  WARNING: folder '{folder_name}' not found, skipping")
            continue
        for req in requests:
            req_patched = _patch_base_var(json.loads(json.dumps(req)), base_var)
            upsert_request(folder, req_patched)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def apply_gap_fix_changes(collection: dict, base_var: str) -> None:
    items = collection.get("item", [])

    # 1. Add Scheduled Tasks folder
    replace_or_append_folder(items, _scheduled_tasks_folder(base_var))
    print("  Added/Updated: Scheduled Tasks folder (8 endpoints)")

    # 2. Add new GET sub-resource endpoints
    _apply_new_get_endpoints(items, base_var)

    # 3. Add new variables
    variables = collection.get("variable", [])
    existing_keys = {v["key"] for v in variables}
    new_vars = [
        {"key": "task_id", "value": "", "type": "string"},
        {"key": "dataset_id", "value": "", "type": "string"},
        {"key": "asset_id", "value": "", "type": "string"},
        {"key": "tag_id", "value": "", "type": "string"},
    ]
    for nv in new_vars:
        if nv["key"] not in existing_keys:
            variables.append(nv)
    collection["variable"] = variables


def main():
    for fpath in FILES:
        if not os.path.exists(fpath):
            print(f"SKIP (not found): {fpath}")
            continue

        print(f"\nProcessing: {os.path.basename(fpath)}")
        with open(fpath, "r", encoding="utf-8") as f:
            collection = json.load(f)

        vars_in_collection = {v["key"]: v.get("value", "") for v in collection.get("variable", [])}
        base_var = "{{base_url}}"
        if "vercel_base_url" in vars_in_collection:
            base_var = "{{vercel_base_url}}"

        apply_gap_fix_changes(collection, base_var)

        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(collection, f, indent=2, ensure_ascii=False)

        print(f"  Saved: {os.path.basename(fpath)}")


if __name__ == "__main__":
    main()

"""
Sync Postman collections with Pre-Phase 2 fixes:

Changes:
  1. Bots folder (9 endpoints)
  2. Bulk assignment payloads — update existing single-item POST endpoints
     to use body arrays instead of path params
  3. ClassificationTag: add detection_patterns + auto_classify fields
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


def make_request(name, method, path, base_var="{{base_url}}", body=None, query_params=None, description=""):
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


def update_or_add_request_in_folder(folder, request):
    for i, item in enumerate(folder["item"]):
        if item.get("name") == request["name"]:
            folder["item"][i] = request
            return
    folder["item"].append(request)


# ---------------------------------------------------------------------------
# Bots folder
# ---------------------------------------------------------------------------

def _bots_folder(base_var):
    return {
        "id": _id(),
        "name": "Bots",
        "item": [
            make_request("List Bots", "GET", "/bots", base_var,
                query_params=[
                    {"key": "bot_type", "value": "", "disabled": True},
                    {"key": "mode", "value": "", "disabled": True},
                    {"key": "is_enabled", "value": "", "disabled": True},
                    {"key": "trigger_mode", "value": "", "disabled": True},
                    {"key": "search", "value": "", "disabled": True},
                    {"key": "skip", "value": "0", "disabled": True},
                    {"key": "limit", "value": "50", "disabled": True},
                ],
                description="List all bots for the org. Filterable by type, mode, enabled state."
            ),
            make_request("Create Bot", "POST", "/bots", base_var,
                body={
                    "name": "Postgres Metadata Bot",
                    "description": "Scans external Postgres for tables, views, columns",
                    "bot_type": "metadata",
                    "mode": "self",
                    "trigger_mode": "scheduled",
                    "cron_expr": "0 2 * * *",
                    "service_endpoint_id": None,
                    "model_name": None
                },
                description="Create a new bot config. bot_type: metadata|profiler|lineage|usage|classification|search_index|test_suite|rdf_export|embedding. mode: self|external. trigger_mode: on_demand|scheduled."
            ),
            make_request("Get Bot", "GET", "/bots/{{bot_id}}", base_var,
                description="Get bot by ID."
            ),
            make_request("Update Bot", "PUT", "/bots/{{bot_id}}", base_var,
                body={
                    "trigger_mode": "scheduled",
                    "cron_expr": "0 3 * * *",
                    "mode": "external",
                    "service_endpoint_id": "{{service_endpoint_id}}",
                    "model_name": "gpt-4o"
                },
                description="Update bot configuration."
            ),
            make_request("Delete Bot", "DELETE", "/bots/{{bot_id}}", base_var,
                description="Delete bot."
            ),
            make_request("Enable Bot", "PATCH", "/bots/{{bot_id}}/enable", base_var,
                description="Enable the bot (set is_enabled=true)."
            ),
            make_request("Disable Bot", "PATCH", "/bots/{{bot_id}}/disable", base_var,
                description="Disable the bot (set is_enabled=false)."
            ),
            make_request("Run Bot (On-demand)", "POST", "/bots/{{bot_id}}/run", base_var,
                description="Trigger an on-demand run for an enabled bot. Returns triggered_at timestamp."
            ),
            make_request("List Bot Runs", "GET", "/bots/{{bot_id}}/runs", base_var,
                description="Get latest run status for a bot."
            ),
        ],
    }


# ---------------------------------------------------------------------------
# Bulk assignment updates — helper to rewrite a single request in a folder
# ---------------------------------------------------------------------------

BULK_REPLACEMENTS = [
    # (folder_name, old_request_name, new_request_name, new_method, new_path, new_body)
    (
        "Roles",
        "Assign Role to User",
        "Assign Role to Users (Bulk)",
        "POST",
        "/roles/{{role_id}}/assign",
        {"user_ids": ["{{user_id}}"]}
    ),
    (
        "Roles",
        "Add Policy to Role",
        "Add Policies to Role (Bulk)",
        "POST",
        "/roles/{{role_id}}/policies",
        {"policy_ids": ["{{policy_id}}"]}
    ),
    (
        "Policies",
        "Assign Policy to User",
        "Assign Policy to Users (Bulk)",
        "POST",
        "/policies/{{policy_id}}/assign",
        {"user_ids": ["{{user_id}}"]}
    ),
    (
        "Teams",
        "Add Member",
        "Add Members (Bulk)",
        "POST",
        "/teams/{{team_id}}/members",
        {"user_ids": ["{{user_id}}"]}
    ),
    (
        "Teams",
        "Assign Role to Team",
        "Assign Roles to Team (Bulk)",
        "POST",
        "/teams/{{team_id}}/roles",
        {"role_ids": ["{{role_id}}"]}
    ),
    (
        "Teams",
        "Assign Policy to Team",
        "Assign Policies to Team (Bulk)",
        "POST",
        "/teams/{{team_id}}/policies",
        {"policy_ids": ["{{policy_id}}"]}
    ),
    (
        "Organizations (CRUD & Membership)",
        "Add Member to Org",
        "Add Members to Org (Bulk)",
        "POST",
        "/orgs/{{org_id}}/members",
        {"user_ids": ["{{user_id}}"], "is_org_admin": False}
    ),
    (
        "Organizations (CRUD & Membership)",
        "Assign Role to Org",
        "Assign Roles to Org (Bulk)",
        "POST",
        "/orgs/{{org_id}}/roles",
        {"role_ids": ["{{role_id}}"]}
    ),
    (
        "Organizations (CRUD & Membership)",
        "Assign Policy to Org",
        "Assign Policies to Org (Bulk)",
        "POST",
        "/orgs/{{org_id}}/policies",
        {"policy_ids": ["{{policy_id}}"]}
    ),
    (
        "Datasets",
        "Add Dataset Owner",
        "Add Dataset Owners (Bulk)",
        "POST",
        "/datasets/{{dataset_id}}/owners",
        {"user_ids": ["{{user_id}}"]}
    ),
    (
        "Datasets",
        "Add Dataset Expert",
        "Add Dataset Experts (Bulk)",
        "POST",
        "/datasets/{{dataset_id}}/experts",
        {"user_ids": ["{{user_id}}"]}
    ),
    (
        "Data Assets",
        "Add Asset Owner",
        "Add Asset Owners (Bulk)",
        "POST",
        "/data-assets/{{asset_id}}/owners",
        {"user_ids": ["{{user_id}}"]}
    ),
    (
        "Data Assets",
        "Add Asset Expert",
        "Add Asset Experts (Bulk)",
        "POST",
        "/data-assets/{{asset_id}}/experts",
        {"user_ids": ["{{user_id}}"]}
    ),
    (
        "Data Assets",
        "Add Asset Tag",
        "Add Asset Tags (Bulk)",
        "POST",
        "/data-assets/{{asset_id}}/tags",
        {"tag_ids": ["{{tag_id}}"]}
    ),
]


def _apply_bulk_replacements(items, base_var):
    for folder_name, old_name, new_name, method, path, body in BULK_REPLACEMENTS:
        folder = find_folder(items, folder_name)
        if not folder:
            print(f"  WARNING: folder '{folder_name}' not found, skipping '{old_name}'")
            continue
        # Remove old single-item endpoint if present
        folder["item"] = [r for r in folder["item"] if r.get("name") != old_name]
        # Add new bulk endpoint
        new_req = make_request(new_name, method, path, base_var, body=body,
                               description=f"Bulk version: accepts array in request body.")
        # Insert at same rough position (or append)
        folder["item"].append(new_req)
        print(f"  Updated: [{folder_name}] {old_name} → {new_name}")


# ---------------------------------------------------------------------------
# Main apply function
# ---------------------------------------------------------------------------

def apply_prephase2_changes(collection: dict, base_var: str) -> None:
    items = collection.get("item", [])

    # 1. Add Bots folder
    replace_or_append_folder(items, _bots_folder(base_var))
    print("  Added/Updated: Bots folder (9 endpoints)")

    # 2. Bulk assignment replacements
    _apply_bulk_replacements(items, base_var)

    # 3. Ensure bot_id variable exists
    variables = collection.get("variable", [])
    existing_keys = {v["key"] for v in variables}
    new_vars = [
        {"key": "bot_id", "value": "", "type": "string"},
        {"key": "service_endpoint_id", "value": "", "type": "string"},
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

        apply_prephase2_changes(collection, base_var)

        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(collection, f, indent=2, ensure_ascii=False)

        print(f"  Saved: {os.path.basename(fpath)}")


if __name__ == "__main__":
    main()

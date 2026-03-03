"""
Sync Postman collections — Phase 2 Module 2: Data Profiling.

Adds a "Data Profiling" folder with all 8 endpoints.
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
        request["body"] = {
            "mode": "raw",
            "raw": json.dumps(body, indent=2),
            "options": {"raw": {"language": "json"}},
        }
    return {"id": _id(), "name": name, "request": request, "response": []}


def replace_or_append_folder(items, folder):
    for i, item in enumerate(items):
        if item.get("name") == folder["name"] and "item" in item:
            items[i] = folder
            return
    items.append(folder)


COLUMN_PROFILE_SAMPLE = {
    "column_name": "email",
    "data_type": "varchar",
    "null_count": 5,
    "null_pct": 0.01,
    "distinct_count": 498,
    "min_val": "a@a.com",
    "max_val": "z@z.com",
    "mean_val": None,
    "stddev_val": None,
    "top_values": [{"value": "test@example.com", "count": 12}],
    "histogram": []
}

PROFILE_TRIGGER_BODY = {
    "row_count": 10000,
    "profile_data": {"table_size_bytes": 204800, "column_count": 8},
    "column_profiles": [COLUMN_PROFILE_SAMPLE]
}

PROFILE_UPDATE_BODY = {
    "status": "success",
    "row_count": 10500,
    "profile_data": {"table_size_bytes": 210000, "column_count": 8},
    "column_profiles": [COLUMN_PROFILE_SAMPLE]
}


def _profiling_folder(base_var):
    return {
        "id": _id(),
        "name": "Data Profiling",
        "item": [
            # Asset-scoped
            make_request(
                "Trigger Profile Run", "POST",
                "/data-assets/{{asset_id}}/profile", base_var,
                body=PROFILE_TRIGGER_BODY,
                description="Trigger a profiling run. Include column_profiles to submit results immediately; leave empty to queue for worker.",
            ),
            make_request(
                "List Profile Runs", "GET",
                "/data-assets/{{asset_id}}/profiles", base_var,
                query_params=[
                    {"key": "status", "value": "", "disabled": True},
                    {"key": "skip", "value": "0", "disabled": True},
                    {"key": "limit", "value": "20", "disabled": True},
                ],
            ),
            make_request(
                "Get Latest Profile", "GET",
                "/data-assets/{{asset_id}}/profiles/latest", base_var,
                description="Returns latest successful profile run + all column profiles.",
            ),
            make_request(
                "Get Profile by ID", "GET",
                "/data-assets/{{asset_id}}/profiles/{{profile_id}}", base_var,
            ),
            make_request(
                "Update Profile Run", "PUT",
                "/data-assets/{{asset_id}}/profiles/{{profile_id}}", base_var,
                body=PROFILE_UPDATE_BODY,
                description="Used by profiler bots to write results back into a pending/running profile.",
            ),
            make_request(
                "Delete Profile Run", "DELETE",
                "/data-assets/{{asset_id}}/profiles/{{profile_id}}", base_var,
            ),
            # Org-wide
            make_request(
                "List All Profiles (Org)", "GET",
                "/profiles", base_var,
                query_params=[
                    {"key": "asset_id", "value": "", "disabled": True},
                    {"key": "status", "value": "", "disabled": True},
                    {"key": "triggered_by", "value": "", "disabled": True},
                    {"key": "skip", "value": "0", "disabled": True},
                    {"key": "limit", "value": "50", "disabled": True},
                ],
            ),
            make_request(
                "Get Profile by ID (Org)", "GET",
                "/profiles/{{profile_id}}", base_var,
            ),
        ],
    }


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

        replace_or_append_folder(collection.get("item", []), _profiling_folder(base_var))
        print("  Added/Updated: Data Profiling folder (8 endpoints)")

        # Add profile_id variable if missing
        variables = collection.get("variable", [])
        existing_keys = {v["key"] for v in variables}
        if "profile_id" not in existing_keys:
            variables.append({"key": "profile_id", "value": "", "type": "string"})
        collection["variable"] = variables

        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(collection, f, indent=2, ensure_ascii=False)
        print(f"  Saved: {os.path.basename(fpath)}")


if __name__ == "__main__":
    main()

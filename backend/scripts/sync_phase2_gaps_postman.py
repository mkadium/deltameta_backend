"""Sync Postman — Phase 2 gap fixes:
 - DataAsset: tier + source_type fields (list filter params updated)
 - Quality: last_run_status filter on test-cases list
 - Quality: date_range filter on incidents
 - Quality: 3 new data-asset quality sub-endpoints
 - Bots: /bots/{id}/runs now returns BotRunRecord list
"""
import json, os, uuid as uuid_mod

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = [
    os.path.join(BASE_DIR, "deltameta_auth.postman_collection.json"),
    os.path.join(BASE_DIR, "vercel_deltameta_auth.postman_collection.json"),
]


def _id():
    return str(uuid_mod.uuid4())


def make_request(name, method, path, base_var, body=None, query_params=None, description=""):
    url_raw = base_var + path
    request = {
        "method": method.upper(),
        "header": [{"key": "Authorization", "value": "Bearer {{token}}"}],
        "url": {"raw": url_raw, "host": [base_var], "path": [p for p in path.lstrip("/").split("/") if p]},
        "description": description,
    }
    if query_params:
        request["url"]["query"] = [
            {"key": p["key"], "value": p.get("value", ""), "disabled": p.get("disabled", True)}
            for p in query_params
        ]
    if body is not None:
        request["body"] = {"mode": "raw", "raw": json.dumps(body, indent=2), "options": {"raw": {"language": "json"}}}
    return {"id": _id(), "name": name, "request": request, "response": []}


def replace_or_append_folder(items, folder):
    for i, item in enumerate(items):
        if item.get("name") == folder["name"] and "item" in item:
            items[i] = folder
            return
    items.append(folder)


def find_folder(items, name):
    for item in items:
        if item.get("name") == name and "item" in item:
            return item
    return None


def _quality_gaps_folder(base_var):
    return {
        "id": _id(),
        "name": "Data Quality (Gap Fixes)",
        "item": [
            make_request(
                "Quality Summary for Asset",
                "GET",
                "/data-assets/{{asset_id}}/quality/summary",
                base_var,
                description="Health score, pass/fail/aborted counts, open incidents for a data asset.",
            ),
            make_request(
                "List Test Cases for Asset",
                "GET",
                "/data-assets/{{asset_id}}/quality/test-cases",
                base_var,
                query_params=[
                    {"key": "is_active", "value": "true", "disabled": True},
                    {"key": "severity", "value": "", "disabled": True},
                    {"key": "level", "value": "", "disabled": True},
                    {"key": "skip", "value": "0", "disabled": True},
                    {"key": "limit", "value": "100", "disabled": True},
                ],
                description="All quality test cases for a specific data asset.",
            ),
            make_request(
                "Run All Active Test Cases for Asset",
                "POST",
                "/data-assets/{{asset_id}}/quality/run",
                base_var,
                description="Trigger QualityTestRun for every active test case on this asset.",
            ),
            make_request(
                "List Test Cases (with last_run_status filter)",
                "GET",
                "/quality/test-cases",
                base_var,
                query_params=[
                    {"key": "asset_id", "value": "{{asset_id}}", "disabled": True},
                    {"key": "level", "value": "", "disabled": True},
                    {"key": "severity", "value": "", "disabled": True},
                    {"key": "last_run_status", "value": "failed", "disabled": True,
                     "description": "pending | running | success | aborted | failed"},
                    {"key": "is_active", "value": "", "disabled": True},
                    {"key": "search", "value": "", "disabled": True},
                ],
                description="List quality test cases. New: last_run_status filter.",
            ),
            make_request(
                "List Incidents (with date_range filter)",
                "GET",
                "/quality/incidents",
                base_var,
                query_params=[
                    {"key": "status", "value": "", "disabled": True},
                    {"key": "severity", "value": "", "disabled": True},
                    {"key": "asset_id", "value": "", "disabled": True},
                    {"key": "date_range", "value": "last_7_days", "disabled": True,
                     "description": "yesterday | last_7_days | last_15_days | last_30_days"},
                ],
                description="List incidents. New: date_range filter.",
            ),
        ],
    }


def _data_asset_gaps_folder(base_var):
    return {
        "id": _id(),
        "name": "Data Assets (Gap Fixes — tier + source_type)",
        "item": [
            make_request(
                "Create Data Asset (with tier + source_type)",
                "POST",
                "/data-assets",
                base_var,
                body={
                    "dataset_id": "{{dataset_id}}",
                    "name": "my_table",
                    "asset_type": "table",
                    "sensitivity": "internal",
                    "is_pii": False,
                    "tier": "2",
                    "source_type": "manual",
                },
                description="tier: 1-5 (data criticality). source_type: manual | upload | connection_sync | bot_scan.",
            ),
            make_request(
                "List Data Assets (filter by tier + source_type)",
                "GET",
                "/data-assets",
                base_var,
                query_params=[
                    {"key": "tier", "value": "1", "disabled": True,
                     "description": "1 | 2 | 3 | 4 | 5"},
                    {"key": "source_type", "value": "bot_scan", "disabled": True,
                     "description": "manual | upload | connection_sync | bot_scan"},
                    {"key": "sensitivity", "value": "", "disabled": True},
                    {"key": "is_pii", "value": "", "disabled": True},
                    {"key": "is_active", "value": "", "disabled": True},
                    {"key": "search", "value": "", "disabled": True},
                ],
                description="New filters: tier and source_type.",
            ),
        ],
    }


def _bot_runs_folder(base_var):
    return {
        "id": _id(),
        "name": "Bots (Gap Fixes — BotRun history)",
        "item": [
            make_request(
                "List Bot Runs",
                "GET",
                "/bots/{{bot_id}}/runs",
                base_var,
                query_params=[
                    {"key": "status", "value": "", "disabled": True,
                     "description": "pending | running | success | failed | aborted"},
                    {"key": "skip", "value": "0", "disabled": True},
                    {"key": "limit", "value": "50", "disabled": True},
                ],
                description="List individual BotRun records for a bot (full run history).",
            ),
        ],
    }


ENSURE_VARS = ["asset_id", "bot_id", "dataset_id"]


def ensure_variables(collection, keys):
    existing = {v["key"] for v in collection.get("variable", [])}
    for key in keys:
        if key not in existing:
            collection.setdefault("variable", []).append(
                {"id": str(uuid_mod.uuid4()), "key": key, "value": "", "type": "string"}
            )


def main():
    for fpath in FILES:
        if not os.path.exists(fpath):
            print(f"SKIP (not found): {fpath}")
            continue
        print(f"\nProcessing: {os.path.basename(fpath)}")
        with open(fpath) as f:
            collection = json.load(f)

        base_var = (
            "{{vercel_base_url}}"
            if "vercel_base_url" in {v["key"] for v in collection.get("variable", [])}
            else "{{base_url}}"
        )

        replace_or_append_folder(collection.get("item", []), _quality_gaps_folder(base_var))
        replace_or_append_folder(collection.get("item", []), _data_asset_gaps_folder(base_var))
        replace_or_append_folder(collection.get("item", []), _bot_runs_folder(base_var))
        ensure_variables(collection, ENSURE_VARS)

        with open(fpath, "w") as f:
            json.dump(collection, f, indent=2, ensure_ascii=False)

        print("  Added/Updated: Data Quality (Gap Fixes)")
        print("  Added/Updated: Data Assets (Gap Fixes — tier + source_type)")
        print("  Added/Updated: Bots (Gap Fixes — BotRun history)")
        print(f"  Saved: {os.path.basename(fpath)}")


if __name__ == "__main__":
    main()

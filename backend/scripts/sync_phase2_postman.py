"""
Sync Postman collections with Phase 2 Module 1 new endpoints:

New endpoints added:
  POST   /admin/users/{id}/unlock       — Unlock locked account
  PATCH  /admin/users/{id}/verify       — Manually verify user
  GET    /org/profiler-config           — Get org profiler config
  PUT    /org/profiler-config           — Update org profiler config

New folders added:
  Datasets (10 endpoints)
  Data Assets (20+ endpoints incl. columns + tags)
"""
import json
import os
import uuid as uuid_mod

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = [
    os.path.join(BASE_DIR, "deltameta_auth.postman_collection.json"),
    os.path.join(BASE_DIR, "vercel_deltameta_auth.postman_collection.json"),
]


# ---------------------------------------------------------------------------
# Helpers (same pattern as sync_filters_postman.py)
# ---------------------------------------------------------------------------

def _id():
    return str(uuid_mod.uuid4())


def _q(key, value="", disabled=True, description=""):
    return {"key": key, "value": value, "disabled": disabled, "description": description}


def make_request(name, method, path, base_var="{{base_url}}", body=None, query_params=None, description=""):
    url_parts = [p for p in path.lstrip("/").split("/") if p]
    url_raw = base_var + path
    if query_params:
        qs = "&".join(f"{p['key']}={p.get('value','')}" for p in query_params if not p.get("disabled", True))
        if qs:
            url_raw += "?" + qs

    request = {
        "method": method.upper(),
        "header": [{"key": "Authorization", "value": "Bearer {{token}}"}],
        "url": {"raw": url_raw, "host": [base_var], "path": url_parts},
        "description": description,
    }
    if query_params:
        request["url"]["query"] = [
            {"key": p["key"], "value": p.get("value", ""), "disabled": p.get("disabled", True),
             "description": p.get("description", "")}
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


def update_or_add_request_in_folder(folder, new_req):
    for i, item in enumerate(folder["item"]):
        if item.get("name") == new_req["name"]:
            folder["item"][i] = new_req
            return
    folder["item"].append(new_req)


def replace_or_append_folder(items, new_folder):
    for i, item in enumerate(items):
        if item.get("name") == new_folder["name"] and "item" in item:
            items[i] = new_folder
            return
    items.append(new_folder)


COMMON_PAGINATION = [
    _q("skip", "0", disabled=True, description="Offset for pagination."),
    _q("limit", "50", disabled=True, description="Max records per page (1–200)."),
]


# ---------------------------------------------------------------------------
# Admin — new utility endpoints
# ---------------------------------------------------------------------------

def _admin_unlock_request(base_var):
    return make_request(
        "Unlock User Account",
        "POST", "/admin/users/{{user_id}}/unlock",
        base_var,
        description="Clear account lockout — resets failed_attempts and locked_until.",
    )


def _admin_verify_request(base_var):
    return make_request(
        "Verify User Email",
        "PATCH", "/admin/users/{{user_id}}/verify",
        base_var,
        description="Manually mark a user's email as verified.",
    )


# ---------------------------------------------------------------------------
# Org Profiler Config
# ---------------------------------------------------------------------------

def _get_profiler_config_request(base_var):
    return make_request(
        "Get Profiler Config",
        "GET", "/org/profiler-config",
        base_var,
        description="Get org-level profiler config (which metrics apply to which datatypes).",
    )


def _put_profiler_config_request(base_var):
    return make_request(
        "Update Profiler Config",
        "PUT", "/org/profiler-config",
        base_var,
        body={
            "entries": [
                {"datatype": "bigint", "metric_types": ["null_count", "distinct_count", "min", "max", "mean"]},
                {"datatype": "varchar", "metric_types": ["null_count", "distinct_count"]},
                {"datatype": "timestamp", "metric_types": ["null_count", "min", "max"]},
                {"datatype": "boolean", "metric_types": ["null_count", "distinct_count"]},
            ]
        },
        description="Full replace of profiler config — deletes existing and inserts new entries.",
    )


# ---------------------------------------------------------------------------
# Datasets folder
# ---------------------------------------------------------------------------

def _datasets_folder(base_var):
    return {
        "id": _id(),
        "name": "Datasets",
        "description": "Raw data collections (DB schemas, S3 buckets, API sources, files). Hierarchy: CatalogDomain → Dataset → DataAsset",
        "item": [
            make_request(
                "List Datasets",
                "GET", "/datasets",
                base_var,
                query_params=[
                    _q("search", "", disabled=True, description="Search by name or description."),
                    _q("domain_id", "{{catalog_domain_id}}", disabled=True, description="Filter by catalog domain."),
                    _q("source_type", "database", disabled=True, description="database | schema | s3_bucket | api | file"),
                    _q("is_active", "true", disabled=True),
                    _q("created_by", "{{user_id}}", disabled=True),
                    _q("owner_id", "{{user_id}}", disabled=True, description="[RELATIONAL] Datasets owned by this user."),
                    _q("expert_id", "{{user_id}}", disabled=True, description="[RELATIONAL] Datasets where this user is an expert."),
                    *COMMON_PAGINATION,
                ],
                description="List datasets with comprehensive filters.",
            ),
            make_request(
                "Create Dataset",
                "POST", "/datasets",
                base_var,
                body={
                    "name": "sales_db",
                    "display_name": "Sales Database",
                    "description": "Primary sales transactional database",
                    "domain_id": "{{catalog_domain_id}}",
                    "source_type": "database",
                    "source_url": "postgresql://localhost:5432/sales",
                    "tags": ["finance", "transactional"],
                    "owner_ids": [],
                    "expert_ids": [],
                },
                description="Create a new dataset.",
            ),
            make_request(
                "Get Dataset",
                "GET", "/datasets/{{dataset_id}}",
                base_var,
                description="Get dataset by ID.",
            ),
            make_request(
                "Update Dataset",
                "PUT", "/datasets/{{dataset_id}}",
                base_var,
                body={
                    "display_name": "Sales Database (Updated)",
                    "description": "Updated description",
                    "is_active": True,
                    "tags": ["finance", "transactional", "updated"],
                    "owner_ids": [],
                    "expert_ids": [],
                },
                description="Update dataset.",
            ),
            make_request(
                "Delete Dataset",
                "DELETE", "/datasets/{{dataset_id}}",
                base_var,
                description="Soft-delete dataset (sets is_active=false).",
            ),
            make_request(
                "Add Dataset Owner",
                "POST", "/datasets/{{dataset_id}}/owners/{{user_id}}",
                base_var,
                description="Assign a user as owner of a dataset.",
            ),
            make_request(
                "Remove Dataset Owner",
                "DELETE", "/datasets/{{dataset_id}}/owners/{{user_id}}",
                base_var,
                description="Remove a user as owner of a dataset.",
            ),
            make_request(
                "Add Dataset Expert",
                "POST", "/datasets/{{dataset_id}}/experts/{{user_id}}",
                base_var,
                description="Assign a user as expert/SME of a dataset.",
            ),
            make_request(
                "Remove Dataset Expert",
                "DELETE", "/datasets/{{dataset_id}}/experts/{{user_id}}",
                base_var,
                description="Remove a user as expert of a dataset.",
            ),
        ],
    }


# ---------------------------------------------------------------------------
# Data Assets folder
# ---------------------------------------------------------------------------

def _data_assets_folder(base_var):
    return {
        "id": _id(),
        "name": "Data Assets",
        "description": "Cataloged data assets — tables, views, files, API endpoints with metadata, ownership, lineage, and classification tags. Hierarchy: Dataset → DataAsset → DataAssetColumn",
        "item": [
            make_request(
                "List Data Assets",
                "GET", "/data-assets",
                base_var,
                query_params=[
                    _q("search", "", disabled=True, description="Search by name, description, or fully_qualified_name."),
                    _q("dataset_id", "{{dataset_id}}", disabled=True),
                    _q("data_product_id", "{{data_product_id}}", disabled=True),
                    _q("asset_type", "table", disabled=True, description="table | view | materialized_view | file | api_endpoint | stream"),
                    _q("sensitivity", "internal", disabled=True, description="public | internal | confidential | restricted"),
                    _q("is_pii", "false", disabled=True),
                    _q("is_active", "true", disabled=True),
                    _q("created_by", "{{user_id}}", disabled=True),
                    _q("owner_id", "{{user_id}}", disabled=True, description="[RELATIONAL] Assets owned by this user."),
                    _q("expert_id", "{{user_id}}", disabled=True, description="[RELATIONAL] Assets where this user is an expert."),
                    _q("tag_id", "{{tag_id}}", disabled=True, description="[RELATIONAL] Assets tagged with this classification tag."),
                    *COMMON_PAGINATION,
                ],
                description="List data assets with comprehensive filters including relational joins.",
            ),
            make_request(
                "Create Data Asset",
                "POST", "/data-assets",
                base_var,
                body={
                    "dataset_id": "{{dataset_id}}",
                    "name": "sales_transactions",
                    "display_name": "Sales Transactions",
                    "description": "Main sales transactions table",
                    "asset_type": "table",
                    "fully_qualified_name": "sales_db.public.sales_transactions",
                    "sensitivity": "internal",
                    "is_pii": False,
                    "owner_ids": [],
                    "expert_ids": [],
                    "tag_ids": [],
                    "columns": [
                        {"name": "id", "data_type": "uuid", "ordinal_position": 0, "is_nullable": False, "is_primary_key": True, "is_foreign_key": False, "is_pii": False},
                        {"name": "amount", "data_type": "decimal", "ordinal_position": 1, "is_nullable": False, "is_primary_key": False, "is_foreign_key": False, "is_pii": False},
                        {"name": "customer_id", "data_type": "uuid", "ordinal_position": 2, "is_nullable": False, "is_primary_key": False, "is_foreign_key": True, "is_pii": False},
                        {"name": "created_at", "data_type": "timestamptz", "ordinal_position": 3, "is_nullable": False, "is_primary_key": False, "is_foreign_key": False, "is_pii": False},
                    ],
                },
                description="Create a new data asset with optional initial column schema.",
            ),
            make_request(
                "Get Data Asset",
                "GET", "/data-assets/{{asset_id}}",
                base_var,
                description="Get data asset by ID (includes columns, owners, experts, tags).",
            ),
            make_request(
                "Update Data Asset",
                "PUT", "/data-assets/{{asset_id}}",
                base_var,
                body={
                    "display_name": "Sales Transactions (Updated)",
                    "description": "Updated description",
                    "sensitivity": "confidential",
                    "is_pii": False,
                    "row_count": 1500000,
                    "size_bytes": 52428800,
                    "owner_ids": [],
                    "expert_ids": [],
                    "tag_ids": [],
                },
                description="Update data asset metadata.",
            ),
            make_request(
                "Delete Data Asset",
                "DELETE", "/data-assets/{{asset_id}}",
                base_var,
                description="Soft-delete data asset (sets is_active=false).",
            ),
            # Tag assignment
            make_request(
                "Add Asset Tag",
                "POST", "/data-assets/{{asset_id}}/tags/{{tag_id}}",
                base_var,
                description="Assign a classification tag to a data asset.",
            ),
            make_request(
                "Remove Asset Tag",
                "DELETE", "/data-assets/{{asset_id}}/tags/{{tag_id}}",
                base_var,
                description="Remove a classification tag from a data asset.",
            ),
            # Owner / expert
            make_request(
                "Add Asset Owner",
                "POST", "/data-assets/{{asset_id}}/owners/{{user_id}}",
                base_var,
                description="Assign a user as owner of a data asset.",
            ),
            make_request(
                "Remove Asset Owner",
                "DELETE", "/data-assets/{{asset_id}}/owners/{{user_id}}",
                base_var,
                description="Remove a user as owner of a data asset.",
            ),
            make_request(
                "Add Asset Expert",
                "POST", "/data-assets/{{asset_id}}/experts/{{user_id}}",
                base_var,
                description="Assign a user as expert/SME of a data asset.",
            ),
            make_request(
                "Remove Asset Expert",
                "DELETE", "/data-assets/{{asset_id}}/experts/{{user_id}}",
                base_var,
                description="Remove a user as expert of a data asset.",
            ),
            # Columns
            make_request(
                "List Columns",
                "GET", "/data-assets/{{asset_id}}/columns",
                base_var,
                query_params=[
                    _q("search", "", disabled=True),
                    _q("data_type", "varchar", disabled=True, description="bigint | varchar | timestamp | boolean | decimal | uuid | json"),
                    _q("is_pii", "false", disabled=True),
                    _q("is_primary_key", "false", disabled=True),
                    _q("is_foreign_key", "false", disabled=True),
                ],
                description="List all columns for a data asset.",
            ),
            make_request(
                "Add Column",
                "POST", "/data-assets/{{asset_id}}/columns",
                base_var,
                body={
                    "name": "email",
                    "display_name": "Customer Email",
                    "description": "Customer email address — PII",
                    "data_type": "varchar",
                    "ordinal_position": 5,
                    "is_nullable": True,
                    "is_primary_key": False,
                    "is_foreign_key": False,
                    "is_pii": True,
                    "sensitivity": "confidential",
                },
                description="Add a single column to a data asset.",
            ),
            make_request(
                "Update Column",
                "PUT", "/data-assets/{{asset_id}}/columns/{{column_id}}",
                base_var,
                body={
                    "description": "Updated column description",
                    "is_pii": True,
                    "sensitivity": "restricted",
                },
                description="Update column metadata.",
            ),
            make_request(
                "Delete Column",
                "DELETE", "/data-assets/{{asset_id}}/columns/{{column_id}}",
                base_var,
                description="Delete a column from a data asset.",
            ),
            make_request(
                "Bulk Replace Columns",
                "POST", "/data-assets/{{asset_id}}/columns/bulk",
                base_var,
                body=[
                    {"name": "id", "data_type": "uuid", "ordinal_position": 0, "is_nullable": False, "is_primary_key": True, "is_foreign_key": False, "is_pii": False},
                    {"name": "name", "data_type": "varchar", "ordinal_position": 1, "is_nullable": True, "is_primary_key": False, "is_foreign_key": False, "is_pii": False},
                    {"name": "email", "data_type": "varchar", "ordinal_position": 2, "is_nullable": True, "is_primary_key": False, "is_foreign_key": False, "is_pii": True, "sensitivity": "confidential"},
                ],
                description="Full replace of all columns for a data asset (schema sync from source).",
            ),
        ],
    }


# ---------------------------------------------------------------------------
# Main apply function
# ---------------------------------------------------------------------------

def apply_phase2_changes(collection: dict, base_var: str) -> None:
    items = collection.get("item", [])

    # 1. Add unlock + verify to Admin Users folder
    admin_folder = find_folder(items, "Admin Users")
    if admin_folder:
        update_or_add_request_in_folder(admin_folder, _admin_unlock_request(base_var))
        update_or_add_request_in_folder(admin_folder, _admin_verify_request(base_var))

    # 2. Add profiler config to Organization folder
    org_folder = find_folder(items, "Organization")
    if org_folder:
        update_or_add_request_in_folder(org_folder, _get_profiler_config_request(base_var))
        update_or_add_request_in_folder(org_folder, _put_profiler_config_request(base_var))

    # 3. Add Datasets folder
    replace_or_append_folder(items, _datasets_folder(base_var))

    # 4. Add Data Assets folder
    replace_or_append_folder(items, _data_assets_folder(base_var))

    # 5. Ensure new collection variables exist
    variables = collection.get("variable", [])
    existing_keys = {v["key"] for v in variables}
    new_vars = [
        {"key": "dataset_id", "value": "", "type": "string"},
        {"key": "asset_id", "value": "", "type": "string"},
        {"key": "column_id", "value": "", "type": "string"},
        {"key": "data_product_id", "value": "", "type": "string"},
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

        with open(fpath, "r", encoding="utf-8") as f:
            collection = json.load(f)

        # Detect base URL variable name
        vars_in_collection = {v["key"]: v.get("value", "") for v in collection.get("variable", [])}
        base_var = "{{base_url}}"
        if "vercel_base_url" in vars_in_collection:
            base_var = "{{vercel_base_url}}"

        apply_phase2_changes(collection, base_var)

        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(collection, f, indent=2, ensure_ascii=False)

        print(f"Updated: {os.path.basename(fpath)}")


if __name__ == "__main__":
    main()

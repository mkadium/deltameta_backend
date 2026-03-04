"""Sync Postman — Phase 3 Module 0: File Ingest API + Catalog Views model."""
import json, os, uuid as uuid_mod

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = [
    os.path.join(BASE_DIR, "deltameta_auth.postman_collection.json"),
    os.path.join(BASE_DIR, "vercel_deltameta_auth.postman_collection.json"),
]


def _id():
    return str(uuid_mod.uuid4())


def make_request(name, method, path, base_var, body=None, query_params=None, description="", is_form=False):
    url_raw = base_var + path
    request = {
        "method": method.upper(),
        "header": [{"key": "Authorization", "value": "Bearer {{token}}"}],
        "url": {"raw": url_raw, "host": [base_var], "path": [p for p in path.lstrip("/").split("/") if p]},
        "description": description,
    }
    if query_params:
        request["url"]["query"] = [
            {"key": p["key"], "value": p.get("value", ""), "disabled": p.get("disabled", True),
             "description": p.get("description", "")}
            for p in query_params
        ]
    if is_form:
        request["body"] = {
            "mode": "formdata",
            "formdata": body or [],
        }
    elif body is not None:
        request["body"] = {"mode": "raw", "raw": json.dumps(body, indent=2), "options": {"raw": {"language": "json"}}}
    return {"id": _id(), "name": name, "request": request, "response": []}


def replace_or_append_folder(items, folder):
    for i, item in enumerate(items):
        if item.get("name") == folder["name"] and "item" in item:
            items[i] = folder
            return
    items.append(folder)


def _ingest_folder(base_var):
    return {
        "id": _id(),
        "name": "File Ingest",
        "item": [
            make_request(
                "Upload File",
                "POST",
                "/ingest/upload",
                base_var,
                is_form=True,
                body=[
                    {"key": "file", "type": "file", "src": "", "description": "CSV, TSV, Excel, JSON, or Parquet"},
                    {"key": "storage_config_id", "type": "text", "value": "", "disabled": True,
                     "description": "Optional StorageConfig UUID for MinIO/S3"},
                ],
                description="Upload a file → infer schema → create IngestJob (status=preview_ready).",
            ),
            make_request(
                "List Ingest Jobs",
                "GET",
                "/ingest/jobs",
                base_var,
                query_params=[
                    {"key": "status", "value": "", "disabled": True,
                     "description": "pending | preview_ready | success | failed | cancelled"},
                    {"key": "file_type", "value": "", "disabled": True, "description": "csv | excel | tsv | json | parquet"},
                    {"key": "triggered_by", "value": "", "disabled": True},
                    {"key": "skip", "value": "0", "disabled": True},
                    {"key": "limit", "value": "50", "disabled": True},
                ],
                description="List ingest jobs for the current org.",
            ),
            make_request(
                "Get Ingest Job",
                "GET",
                "/ingest/jobs/{{ingest_job_id}}",
                base_var,
                description="Get a specific ingest job by ID.",
            ),
            make_request(
                "Preview Ingest Job",
                "GET",
                "/ingest/jobs/{{ingest_job_id}}/preview",
                base_var,
                description="Get inferred schema and first 50 rows from uploaded file.",
            ),
            make_request(
                "Confirm Ingest Job",
                "POST",
                "/ingest/jobs/{{ingest_job_id}}/confirm",
                base_var,
                body={
                    "dataset_id": "{{dataset_id}}",
                    "asset_name": "my_uploaded_table",
                    "display_name": "My Uploaded Table",
                    "description": "Uploaded from CSV file",
                    "sensitivity": "internal",
                    "is_pii": False,
                    "tier": "3",
                    "column_overrides": None,
                },
                description="Confirm schema → create DataAsset (source_type=upload) + DataAssetColumns + upload to MinIO/S3.",
            ),
            make_request(
                "Delete Ingest Job",
                "DELETE",
                "/ingest/jobs/{{ingest_job_id}}",
                base_var,
                description="Cancel/delete an ingest job (only if not yet confirmed/success).",
            ),
        ],
    }


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

        replace_or_append_folder(collection.get("item", []), _ingest_folder(base_var))
        ensure_variables(collection, ["ingest_job_id"])

        with open(fpath, "w") as f:
            json.dump(collection, f, indent=2, ensure_ascii=False)

        print("  Added/Updated: File Ingest")
        print(f"  Saved: {os.path.basename(fpath)}")


if __name__ == "__main__":
    main()

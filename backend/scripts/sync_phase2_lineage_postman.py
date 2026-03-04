"""Sync Postman collections — Phase 2 Module 3: Data Lineage."""
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

def replace_or_append_folder(items, folder):
    for i, item in enumerate(items):
        if item.get("name") == folder["name"] and "item" in item:
            items[i] = folder; return
    items.append(folder)

def _lineage_folder(base_var):
    return {
        "id": _id(), "name": "Data Lineage",
        "item": [
            make_request("Create Lineage Edge", "POST", "/lineage", base_var,
                body={"source_asset_id": "{{asset_id}}", "target_asset_id": "{{target_asset_id}}", "edge_type": "direct", "transformation": "SELECT * FROM source"},
                description="edge_type: direct | derived | copy | aggregated"),
            make_request("List Lineage Edges", "GET", "/lineage", base_var,
                query_params=[
                    {"key": "source_asset_id", "value": "", "disabled": True},
                    {"key": "target_asset_id", "value": "", "disabled": True},
                    {"key": "edge_type", "value": "", "disabled": True},
                    {"key": "created_by", "value": "", "disabled": True},
                    {"key": "skip", "value": "0", "disabled": True},
                    {"key": "limit", "value": "100", "disabled": True},
                ]),
            make_request("Delete Lineage Edge", "DELETE", "/lineage/{{edge_id}}", base_var),
            make_request("Get Upstream Assets", "GET", "/lineage/{{asset_id}}/upstream", base_var,
                query_params=[{"key": "max_depth", "value": "10", "disabled": True}],
                description="Returns all assets that feed INTO this asset (recursive BFS)"),
            make_request("Get Downstream Assets", "GET", "/lineage/{{asset_id}}/downstream", base_var,
                query_params=[{"key": "max_depth", "value": "10", "disabled": True}],
                description="Returns all assets this asset feeds INTO (recursive BFS)"),
            make_request("Get Lineage Graph", "GET", "/lineage/{{asset_id}}/graph", base_var,
                query_params=[{"key": "max_depth", "value": "5", "disabled": True}],
                description="Full graph (nodes + edges) for UI visualisation"),
        ],
    }

def main():
    for fpath in FILES:
        if not os.path.exists(fpath): print(f"SKIP: {fpath}"); continue
        print(f"\nProcessing: {os.path.basename(fpath)}")
        with open(fpath) as f: collection = json.load(f)
        base_var = "{{vercel_base_url}}" if "vercel_base_url" in {v["key"] for v in collection.get("variable", [])} else "{{base_url}}"
        replace_or_append_folder(collection.get("item", []), _lineage_folder(base_var))
        # Add edge_id + target_asset_id variables
        variables = collection.get("variable", [])
        existing = {v["key"] for v in variables}
        for key in ("edge_id", "target_asset_id"):
            if key not in existing: variables.append({"key": key, "value": "", "type": "string"})
        collection["variable"] = variables
        with open(fpath, "w") as f: json.dump(collection, f, indent=2, ensure_ascii=False)
        print(f"  Added/Updated: Data Lineage folder (6 endpoints)")
        print(f"  Saved: {os.path.basename(fpath)}")

if __name__ == "__main__":
    main()

"""Sync Postman — Phase 2 Module 5 (ABAC) + Module 6 (Search)."""
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

def _search_folder(base_var):
    return {
        "id": _id(), "name": "Search",
        "item": [
            make_request("Full-Text Search", "GET", "/search", base_var,
                query_params=[
                    {"key": "q", "value": "customer", "disabled": False},
                    {"key": "type", "value": "", "disabled": True,
                     "description": "data_asset|dataset|glossary_term|catalog_domain|classification|classification_tag|govern_metric"},
                    {"key": "domain_id", "value": "", "disabled": True},
                    {"key": "owner_id", "value": "", "disabled": True},
                    {"key": "is_pii", "value": "", "disabled": True},
                    {"key": "sensitivity", "value": "", "disabled": True},
                    {"key": "asset_type", "value": "", "disabled": True},
                    {"key": "skip", "value": "0", "disabled": True},
                    {"key": "limit", "value": "50", "disabled": True},
                ],
                description="PG full-text search. Phase 3 will swap to Elasticsearch with same contract."),
            make_request("Search Suggestions (Autocomplete)", "GET", "/search/suggestions", base_var,
                query_params=[
                    {"key": "q", "value": "cust", "disabled": False},
                    {"key": "type", "value": "", "disabled": True},
                    {"key": "limit", "value": "10", "disabled": True},
                ],
                description="Fast ILIKE prefix search for autocomplete dropdowns."),
        ],
    }

def main():
    for fpath in FILES:
        if not os.path.exists(fpath): print(f"SKIP: {fpath}"); continue
        print(f"\nProcessing: {os.path.basename(fpath)}")
        with open(fpath) as f: collection = json.load(f)
        base_var = "{{vercel_base_url}}" if "vercel_base_url" in {v["key"] for v in collection.get("variable", [])} else "{{base_url}}"
        replace_or_append_folder(collection.get("item", []), _search_folder(base_var))
        with open(fpath, "w") as f: json.dump(collection, f, indent=2, ensure_ascii=False)
        print(f"  Added/Updated: Search folder (2 endpoints)")
        print(f"  Saved: {os.path.basename(fpath)}")

if __name__ == "__main__":
    main()

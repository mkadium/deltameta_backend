"""
Append Phase 1 governance folders to both Postman collections.

Run from backend/:
    python scripts/update_postman.py
"""
from __future__ import annotations
import json
import os

COLLECTIONS = [
    os.path.join(os.path.dirname(__file__), "..", "deltameta_auth.postman_collection.json"),
    os.path.join(os.path.dirname(__file__), "..", "vercel_deltameta_auth.postman_collection.json"),
]

# ---------------------------------------------------------------------------
# Builder helpers
# ---------------------------------------------------------------------------

AUTH_HEADER = [{"key": "Authorization", "value": "Bearer {{token}}"}]
JSON_HEADER = [{"key": "Content-Type", "value": "application/json"}]


def _url(raw, path_parts):
    return {"raw": raw, "host": ["{{base_url}}"], "path": path_parts}


def _url_with_query(raw, path_parts, query):
    return {"raw": raw, "host": ["{{base_url}}"], "path": path_parts, "query": query}


def _body(payload: dict):
    return {
        "mode": "raw",
        "raw": json.dumps(payload, indent=2),
        "options": {"raw": {"language": "json"}},
    }


def _tests(*lines):
    return [{"listen": "test", "script": {"type": "text/javascript", "exec": list(lines)}}]


def get(name, raw_path, path_parts, tests=None, query=None, description=""):
    url = _url_with_query(f"{{{{base_url}}}}/{raw_path}", path_parts, query) if query else _url(f"{{{{base_url}}}}/{raw_path}", path_parts)
    item = {
        "name": name,
        "request": {"method": "GET", "header": AUTH_HEADER, "url": url},
    }
    if description:
        item["request"]["description"] = description
    if tests:
        item["event"] = _tests(*tests)
    return item


def post(name, raw_path, path_parts, payload=None, tests=None, description="", multipart=False):
    headers = list(AUTH_HEADER)
    if payload is not None and not multipart:
        headers += JSON_HEADER
    item = {
        "name": name,
        "request": {
            "method": "POST",
            "header": headers,
            "url": _url(f"{{{{base_url}}}}/{raw_path}", path_parts),
        },
    }
    if payload is not None and not multipart:
        item["request"]["body"] = _body(payload)
    if multipart:
        item["request"]["body"] = {
            "mode": "formdata",
            "formdata": [{"key": "file", "type": "file", "src": "/path/to/terms.csv"}],
        }
    if description:
        item["request"]["description"] = description
    if tests:
        item["event"] = _tests(*tests)
    return item


def put(name, raw_path, path_parts, payload, tests=None, description=""):
    item = {
        "name": name,
        "request": {
            "method": "PUT",
            "header": AUTH_HEADER + JSON_HEADER,
            "url": _url(f"{{{{base_url}}}}/{raw_path}", path_parts),
            "body": _body(payload),
        },
    }
    if description:
        item["request"]["description"] = description
    if tests:
        item["event"] = _tests(*tests)
    return item


def delete(name, raw_path, path_parts, tests=None, description=""):
    item = {
        "name": name,
        "request": {
            "method": "DELETE",
            "header": AUTH_HEADER,
            "url": _url(f"{{{{base_url}}}}/{raw_path}", path_parts),
        },
    }
    if description:
        item["request"]["description"] = description
    if tests:
        item["event"] = _tests(*tests)
    return item


def folder(name, items, description=""):
    f = {"name": name, "item": items}
    if description:
        f["description"] = description
    return f


# ---------------------------------------------------------------------------
# 1. Subject Areas
# ---------------------------------------------------------------------------

subject_areas_folder = folder("Subject Areas", [
    get("List Subject Areas", "subject-areas", ["subject-areas"],
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));",
               "pm.test('Is array', () => pm.expect(pm.response.json()).to.be.an('array'));"]),
    post("Create Subject Area", "subject-areas", ["subject-areas"],
         payload={"name": "Finance", "display_name": "Finance Domain",
                  "description": "All finance data", "domain_type": "source_aligned"},
         tests=["pm.test('Status 201', () => pm.response.to.have.status(201));",
                "const d = pm.response.json();",
                "pm.collectionVariables.set('subject_area_id', d.id);",
                "pm.test('Has name', () => pm.expect(d.name).to.eql('Finance'));"]),
    get("Get Subject Area", "subject-areas/{{subject_area_id}}", ["subject-areas", "{{subject_area_id}}"],
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));"]),
    put("Update Subject Area", "subject-areas/{{subject_area_id}}", ["subject-areas", "{{subject_area_id}}"],
        payload={"display_name": "Updated Finance Domain"},
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));",
               "pm.test('Updated', () => pm.expect(pm.response.json().display_name).to.eql('Updated Finance Domain'));"]),
    delete("Delete Subject Area", "subject-areas/{{subject_area_id}}", ["subject-areas", "{{subject_area_id}}"],
           tests=["pm.test('Status 204', () => pm.response.to.have.status(204));"]),
], description="Subject Areas (formerly IAM Domains)")

# ---------------------------------------------------------------------------
# 2. Lookup (Dropdowns)
# ---------------------------------------------------------------------------

lookup_folder = folder("Lookup (Dropdowns)", [
    get("List All Lookup Categories", "lookup", ["lookup"],
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));",
               "pm.test('Is array', () => pm.expect(pm.response.json()).to.be.an('array'));"]),
    get("Get Lookup by Slug — domain_type", "lookup/domain_type", ["lookup", "domain_type"],
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));",
               "pm.test('Slug matches', () => pm.expect(pm.response.json().slug).to.eql('domain_type'));"]),
    get("Get Lookup by Slug — metric_type", "lookup/metric_type", ["lookup", "metric_type"]),
    get("Get Lookup by Slug — metric_granularity", "lookup/metric_granularity", ["lookup", "metric_granularity"]),
    get("Get Lookup by Slug — measurement_unit", "lookup/measurement_unit", ["lookup", "measurement_unit"]),
    get("Get Lookup by Slug — metric_language", "lookup/metric_language", ["lookup", "metric_language"]),
    post("Create Lookup Category", "lookup", ["lookup"],
         payload={"name": "Custom Category", "slug": "custom_cat", "description": "Custom dropdown values"},
         tests=["pm.test('Status 201', () => pm.response.to.have.status(201));",
                "pm.collectionVariables.set('lookup_category_id', pm.response.json().id);"]),
    post("Add Lookup Value", "lookup/{{lookup_category_id}}/values",
         ["lookup", "{{lookup_category_id}}", "values"],
         payload={"label": "Option A", "value": "option_a", "sort_order": 1},
         tests=["pm.test('Status 201', () => pm.response.to.have.status(201));",
                "pm.collectionVariables.set('lookup_value_id', pm.response.json().id);"]),
    delete("Delete Lookup Value", "lookup/{{lookup_category_id}}/values/{{lookup_value_id}}",
           ["lookup", "{{lookup_category_id}}", "values", "{{lookup_value_id}}"],
           tests=["pm.test('Status 204', () => pm.response.to.have.status(204));"]),
], description="Dropdown values for domain_type, metric_type, granularity, etc. Frontend uses these to populate dropdowns with an 'Add' button.")

# ---------------------------------------------------------------------------
# 3. Catalog Domains
# ---------------------------------------------------------------------------

catalog_domains_folder = folder("Catalog Domains", [
    get("List Catalog Domains", "catalog-domains", ["catalog-domains"],
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));",
               "pm.test('Is array', () => pm.expect(pm.response.json()).to.be.an('array'));"]),
    get("List — Filter by type", "catalog-domains?domain_type=aggregate&is_active=true",
        ["catalog-domains"],
        query=[{"key": "domain_type", "value": "aggregate"}, {"key": "is_active", "value": "true"}]),
    get("Search Catalog Domains", "catalog-domains?search=Marketing",
        ["catalog-domains"],
        query=[{"key": "search", "value": "Marketing"}]),
    post("Create Catalog Domain", "catalog-domains", ["catalog-domains"],
         payload={"name": "Marketing", "display_name": "Marketing Domain",
                  "description": "Marketing data assets", "domain_type": "consumer_aligned",
                  "color": "#FF5733", "icon": "", "owner_ids": [], "expert_ids": []},
         tests=["pm.test('Status 201', () => pm.response.to.have.status(201));",
                "const d = pm.response.json();",
                "pm.collectionVariables.set('catalog_domain_id', d.id);",
                "pm.test('Has name', () => pm.expect(d.name).to.eql('Marketing'));"]),
    get("Get Catalog Domain", "catalog-domains/{{catalog_domain_id}}",
        ["catalog-domains", "{{catalog_domain_id}}"],
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));"]),
    put("Update Catalog Domain", "catalog-domains/{{catalog_domain_id}}",
        ["catalog-domains", "{{catalog_domain_id}}"],
        payload={"display_name": "Updated Marketing Domain", "color": "#00CC00"},
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));"]),
    delete("Delete Catalog Domain", "catalog-domains/{{catalog_domain_id}}",
           ["catalog-domains", "{{catalog_domain_id}}"],
           tests=["pm.test('Status 204', () => pm.response.to.have.status(204));"]),
])

# ---------------------------------------------------------------------------
# 4. Data Products
# ---------------------------------------------------------------------------

data_products_folder = folder("Data Products", [
    get("List Data Products", "data-products", ["data-products"],
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));"]),
    get("List — Filter by status=draft", "data-products?status=draft", ["data-products"],
        query=[{"key": "status", "value": "draft"}]),
    get("List — Filter by domain", "data-products?domain_id={{catalog_domain_id}}",
        ["data-products"], query=[{"key": "domain_id", "value": "{{catalog_domain_id}}"}]),
    post("Create Data Product", "data-products", ["data-products"],
         payload={"name": "Daily Sales Report", "display_name": "Sales Report",
                  "description": "Aggregated daily sales data",
                  "domain_id": "{{catalog_domain_id}}", "owner_ids": [], "expert_ids": []},
         tests=["pm.test('Status 201', () => pm.response.to.have.status(201));",
                "const d = pm.response.json();",
                "pm.collectionVariables.set('data_product_id', d.id);",
                "pm.test('Default version 0.1', () => pm.expect(d.version).to.eql('0.1'));",
                "pm.test('Default status draft', () => pm.expect(d.status).to.eql('draft'));"]),
    get("Get Data Product", "data-products/{{data_product_id}}",
        ["data-products", "{{data_product_id}}"]),
    put("Update Data Product — Publish", "data-products/{{data_product_id}}",
        ["data-products", "{{data_product_id}}"],
        payload={"status": "published", "version": "1.0"},
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));",
               "pm.test('Published', () => pm.expect(pm.response.json().status).to.eql('published'));"]),
    delete("Delete Data Product", "data-products/{{data_product_id}}",
           ["data-products", "{{data_product_id}}"],
           tests=["pm.test('Status 204', () => pm.response.to.have.status(204));"]),
])

# ---------------------------------------------------------------------------
# 5. Glossary
# ---------------------------------------------------------------------------

glossary_folder = folder("Glossary", [
    get("List Glossaries", "glossaries", ["glossaries"],
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));"]),
    post("Create Glossary", "glossaries", ["glossaries"],
         payload={"name": "Business Glossary", "display_name": "BizGloss",
                  "description": "Corporate business terminology"},
         tests=["pm.test('Status 201', () => pm.response.to.have.status(201));",
                "pm.collectionVariables.set('glossary_id', pm.response.json().id);"]),
    get("Get Glossary", "glossaries/{{glossary_id}}", ["glossaries", "{{glossary_id}}"]),
    put("Rename Glossary", "glossaries/{{glossary_id}}", ["glossaries", "{{glossary_id}}"],
        payload={"name": "Business Glossary v2"},
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));"]),
    get("List Terms", "glossaries/{{glossary_id}}/terms",
        ["glossaries", "{{glossary_id}}", "terms"],
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));",
               "pm.test('Is array', () => pm.expect(pm.response.json()).to.be.an('array'));"]),
    post("Create Term", "glossaries/{{glossary_id}}/terms",
         ["glossaries", "{{glossary_id}}", "terms"],
         payload={"name": "Revenue", "display_name": "Total Revenue",
                  "description": "Sum of all income streams",
                  "synonyms": ["income", "earnings", "sales"],
                  "icon_url": "https://example.com/icon.png", "color": "#00FF00",
                  "mutually_exclusive": False,
                  "references_data": [{"url": "https://wiki.example.com/revenue", "name": "Wiki"}],
                  "owner_ids": [], "reviewer_ids": [], "related_term_ids": []},
         tests=["pm.test('Status 201', () => pm.response.to.have.status(201));",
                "const d = pm.response.json();",
                "pm.collectionVariables.set('glossary_term_id', d.id);",
                "pm.test('Has synonyms', () => pm.expect(d.synonyms).to.include('income'));"]),
    get("Get Term", "glossaries/{{glossary_id}}/terms/{{glossary_term_id}}",
        ["glossaries", "{{glossary_id}}", "terms", "{{glossary_term_id}}"]),
    put("Update Term", "glossaries/{{glossary_id}}/terms/{{glossary_term_id}}",
        ["glossaries", "{{glossary_id}}", "terms", "{{glossary_term_id}}"],
        payload={"description": "Updated: Sum of all revenue streams including recurring subscriptions"},
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));"]),
    post("Like Term", "glossaries/{{glossary_id}}/terms/{{glossary_term_id}}/like",
         ["glossaries", "{{glossary_id}}", "terms", "{{glossary_term_id}}", "like"],
         tests=["pm.test('Status 200', () => pm.response.to.have.status(200));",
                "pm.test('Likes incremented', () => pm.expect(pm.response.json().likes_count).to.be.above(0));"]),
    delete("Unlike Term", "glossaries/{{glossary_id}}/terms/{{glossary_term_id}}/like",
           ["glossaries", "{{glossary_id}}", "terms", "{{glossary_term_id}}", "like"],
           tests=["pm.test('Status 200', () => pm.response.to.have.status(200));",
                  "pm.test('Likes decremented', () => pm.expect(pm.response.json().likes_count).to.be.at.least(0));"]),
    get("Export Glossary CSV", "glossaries/{{glossary_id}}/export",
        ["glossaries", "{{glossary_id}}", "export"],
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));",
               "pm.test('Content-Type CSV', () => pm.expect(pm.response.headers.get('content-type')).to.include('csv'));"],
        description="Downloads all terms in this glossary as a CSV file. Use to share with team."),
    {
        "name": "Import Glossary CSV (multipart)",
        "request": {
            "method": "POST",
            "header": [{"key": "Authorization", "value": "Bearer {{token}}"}],
            "body": {
                "mode": "formdata",
                "formdata": [{"key": "file", "type": "file", "src": "/path/to/terms.csv",
                              "description": "CSV with columns: name,display_name,description,synonyms,color,icon_url,mutually_exclusive"}],
            },
            "url": {"raw": "{{base_url}}/glossaries/{{glossary_id}}/import",
                    "host": ["{{base_url}}"], "path": ["glossaries", "{{glossary_id}}", "import"]},
            "description": "Import terms from CSV. Columns: name,display_name,description,synonyms(comma-sep),color,icon_url,mutually_exclusive",
        },
        "event": _tests("pm.test('Status 201', () => pm.response.to.have.status(201));",
                        "pm.test('Has imported count', () => pm.expect(pm.response.json().imported).to.be.above(0));"),
    },
    delete("Delete Term", "glossaries/{{glossary_id}}/terms/{{glossary_term_id}}",
           ["glossaries", "{{glossary_id}}", "terms", "{{glossary_term_id}}"],
           tests=["pm.test('Status 204', () => pm.response.to.have.status(204));"]),
    delete("Delete Glossary", "glossaries/{{glossary_id}}", ["glossaries", "{{glossary_id}}"],
           tests=["pm.test('Status 204', () => pm.response.to.have.status(204));"]),
])

# ---------------------------------------------------------------------------
# 6. Classifications & Tags
# ---------------------------------------------------------------------------

classifications_folder = folder("Classifications & Tags", [
    get("List Classifications", "classifications", ["classifications"],
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));"]),
    post("Create Classification", "classifications", ["classifications"],
         payload={"name": "PersonalData", "display_name": "Personal Data",
                  "description": "Tags for classifying personal data sensitivity",
                  "mutually_exclusive": True, "owner_ids": [], "domain_ids": []},
         tests=["pm.test('Status 201', () => pm.response.to.have.status(201));",
                "const d = pm.response.json();",
                "pm.collectionVariables.set('classification_id', d.id);",
                "pm.test('Mutually exclusive', () => pm.expect(d.mutually_exclusive).to.be.true);"]),
    get("Get Classification", "classifications/{{classification_id}}",
        ["classifications", "{{classification_id}}"]),
    put("Update Classification", "classifications/{{classification_id}}",
        ["classifications", "{{classification_id}}"],
        payload={"description": "Updated PII sensitivity classification"}),
    get("List Tags", "classifications/{{classification_id}}/tags",
        ["classifications", "{{classification_id}}", "tags"],
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));"]),
    post("Create Tag — Personal", "classifications/{{classification_id}}/tags",
         ["classifications", "{{classification_id}}", "tags"],
         payload={"name": "Personal", "display_name": "Personal Data",
                  "description": "General personal data (name, email, phone)",
                  "color": "#FF6600", "icon_url": "", "owner_ids": [], "domain_ids": []},
         tests=["pm.test('Status 201', () => pm.response.to.have.status(201));",
                "pm.collectionVariables.set('classification_tag_id', pm.response.json().id);"]),
    post("Create Tag — Special Category", "classifications/{{classification_id}}/tags",
         ["classifications", "{{classification_id}}", "tags"],
         payload={"name": "SpecialCategory", "display_name": "Special Category",
                  "description": "Special category data (health, biometric, financial)",
                  "color": "#FF0000", "owner_ids": [], "domain_ids": []},
         tests=["pm.test('Status 201', () => pm.response.to.have.status(201));"]),
    get("Get Tag", "classifications/{{classification_id}}/tags/{{classification_tag_id}}",
        ["classifications", "{{classification_id}}", "tags", "{{classification_tag_id}}"]),
    put("Update Tag", "classifications/{{classification_id}}/tags/{{classification_tag_id}}",
        ["classifications", "{{classification_id}}", "tags", "{{classification_tag_id}}"],
        payload={"color": "#CC3300", "display_name": "Personal Data (Updated)"}),
    delete("Delete Tag", "classifications/{{classification_id}}/tags/{{classification_tag_id}}",
           ["classifications", "{{classification_id}}", "tags", "{{classification_tag_id}}"],
           tests=["pm.test('Status 204', () => pm.response.to.have.status(204));"]),
    delete("Delete Classification", "classifications/{{classification_id}}",
           ["classifications", "{{classification_id}}"],
           tests=["pm.test('Status 204', () => pm.response.to.have.status(204));"]),
])

# ---------------------------------------------------------------------------
# 7. Govern Metrics
# ---------------------------------------------------------------------------

govern_metrics_folder = folder("Govern Metrics", [
    get("List Metrics", "govern-metrics", ["govern-metrics"],
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));"]),
    get("List — Filter by metric_type=sum", "govern-metrics?metric_type=sum",
        ["govern-metrics"], query=[{"key": "metric_type", "value": "sum"}]),
    get("List — Search by name", "govern-metrics?search=Revenue",
        ["govern-metrics"], query=[{"key": "search", "value": "Revenue"}]),
    post("Create Metric", "govern-metrics", ["govern-metrics"],
         payload={"name": "Total Revenue", "display_name": "Revenue",
                  "description": "Sum of all revenue streams across all channels",
                  "granularity": "day", "metric_type": "sum",
                  "language": "sql", "measurement_unit": "dollars",
                  "code": "SELECT SUM(amount) FROM sales WHERE date = :date",
                  "owner_ids": []},
         tests=["pm.test('Status 201', () => pm.response.to.have.status(201));",
                "const d = pm.response.json();",
                "pm.collectionVariables.set('govern_metric_id', d.id);",
                "pm.test('Has metric_type', () => pm.expect(d.metric_type).to.eql('sum'));"]),
    get("Get Metric", "govern-metrics/{{govern_metric_id}}",
        ["govern-metrics", "{{govern_metric_id}}"]),
    put("Update Metric", "govern-metrics/{{govern_metric_id}}",
        ["govern-metrics", "{{govern_metric_id}}"],
        payload={"granularity": "month", "measurement_unit": "dollars",
                 "code": "SELECT SUM(amount) FROM sales WHERE month = :month"}),
    delete("Delete Metric", "govern-metrics/{{govern_metric_id}}",
           ["govern-metrics", "{{govern_metric_id}}"],
           tests=["pm.test('Status 204', () => pm.response.to.have.status(204));"]),
])

# ---------------------------------------------------------------------------
# 8. Change Requests (Tasks)
# ---------------------------------------------------------------------------

change_requests_folder = folder("Change Requests (Tasks)", [
    get("List Change Requests", "change-requests", ["change-requests"],
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));"]),
    get("List — Filter open requests for a term", "change-requests?entity_type=glossary_term&status=open",
        ["change-requests"],
        query=[{"key": "entity_type", "value": "glossary_term"}, {"key": "status", "value": "open"}]),
    post("Create Change Request (Description Update Task)", "change-requests", ["change-requests"],
         payload={"entity_type": "glossary_term",
                  "entity_id": "{{glossary_term_id}}",
                  "field_name": "description",
                  "current_value": "Sum of all income streams",
                  "new_value": "Sum of all revenue streams including recurring subscriptions and one-time payments",
                  "title": "Update Revenue term description",
                  "description": "### Current\nSum of all income streams\n\n### New\nSum of all revenue streams including recurring subscriptions and one-time payments",
                  "assignee_ids": []},
         tests=["pm.test('Status 201', () => pm.response.to.have.status(201));",
                "const d = pm.response.json();",
                "pm.collectionVariables.set('change_request_id', d.id);",
                "pm.test('Status open', () => pm.expect(d.status).to.eql('open'));"]),
    get("Get Change Request", "change-requests/{{change_request_id}}",
        ["change-requests", "{{change_request_id}}"]),
    put("Update Change Request", "change-requests/{{change_request_id}}",
        ["change-requests", "{{change_request_id}}"],
        payload={"description": "Updated description notes", "assignee_ids": []}),
    post("Approve Change Request", "change-requests/{{change_request_id}}/approve",
         ["change-requests", "{{change_request_id}}", "approve"],
         tests=["pm.test('Status 200', () => pm.response.to.have.status(200));",
                "pm.test('Approved', () => pm.expect(pm.response.json().status).to.eql('approved'));"]),
    post("Reject Change Request", "change-requests/{{change_request_id}}/reject",
         ["change-requests", "{{change_request_id}}", "reject"],
         tests=["pm.test('Status 200', () => pm.response.to.have.status(200));",
                "pm.test('Rejected', () => pm.expect(pm.response.json().status).to.eql('rejected'));"]),
    post("Withdraw Change Request", "change-requests/{{change_request_id}}/withdraw",
         ["change-requests", "{{change_request_id}}", "withdraw"],
         tests=["pm.test('Status 200', () => pm.response.to.have.status(200));",
                "pm.test('Withdrawn', () => pm.expect(pm.response.json().status).to.eql('withdrawn'));"]),
    delete("Delete Change Request", "change-requests/{{change_request_id}}",
           ["change-requests", "{{change_request_id}}"],
           tests=["pm.test('Status 204', () => pm.response.to.have.status(204));"]),
], description="Workflow for requesting field updates on catalog entities. Used by Glossary Tasks.")

# ---------------------------------------------------------------------------
# 9. Activity Feed
# ---------------------------------------------------------------------------

activity_feed_folder = folder("Activity Feed", [
    get("List All Activity (org-wide)", "activity-feed", ["activity-feed"],
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));",
               "pm.test('Is array', () => pm.expect(pm.response.json()).to.be.an('array'));"]),
    get("Filter by entity_type — catalog_domain",
        "activity-feed?entity_type=catalog_domain&limit=20", ["activity-feed"],
        query=[{"key": "entity_type", "value": "catalog_domain"}, {"key": "limit", "value": "20"}]),
    get("Filter by entity — glossary term",
        "activity-feed?entity_type=glossary_term&entity_id={{glossary_term_id}}",
        ["activity-feed"],
        query=[{"key": "entity_type", "value": "glossary_term"},
               {"key": "entity_id", "value": "{{glossary_term_id}}"}]),
    get("Filter by actor (user)",
        "activity-feed?actor_id={{user_id}}&limit=50", ["activity-feed"],
        query=[{"key": "actor_id", "value": "{{user_id}}"}, {"key": "limit", "value": "50"}]),
], description="Read-only activity log. Automatically populated when entities are created/updated.")

# ---------------------------------------------------------------------------
# 10. Storage Config
# ---------------------------------------------------------------------------

storage_config_folder = folder("Storage Config (MinIO / S3)", [
    get("List Storage Configs", "storage-config", ["storage-config"],
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));"]),
    post("Create MinIO Config", "storage-config", ["storage-config"],
         payload={"provider": "minio", "endpoint": "http://minio:9000",
                  "bucket": "deltameta-data", "access_key": "minioadmin",
                  "secret_key": "minioadmin123", "region": "", "extra": {}},
         tests=["pm.test('Status 201', () => pm.response.to.have.status(201));",
                "const d = pm.response.json();",
                "pm.collectionVariables.set('storage_config_id', d.id);",
                "pm.test('Provider minio', () => pm.expect(d.provider).to.eql('minio'));",
                "pm.test('Secret not exposed', () => pm.expect(d.secret_key).to.be.undefined);"]),
    post("Create S3 Config", "storage-config", ["storage-config"],
         payload={"provider": "s3", "bucket": "my-s3-bucket", "region": "us-east-1",
                  "access_key": "AKIAEXAMPLE123", "secret_key": "secretaccesskey", "extra": {}},
         tests=["pm.test('Status 201', () => pm.response.to.have.status(201));",
                "pm.test('Provider s3', () => pm.expect(pm.response.json().provider).to.eql('s3'));"]),
    get("Get Storage Config", "storage-config/{{storage_config_id}}",
        ["storage-config", "{{storage_config_id}}"]),
    put("Update Storage Config — Switch to new bucket",
        "storage-config/{{storage_config_id}}", ["storage-config", "{{storage_config_id}}"],
        payload={"bucket": "new-deltameta-bucket", "endpoint": "http://minio-prod:9000"}),
    post("Activate Storage Config (make active, deactivate others)",
         "storage-config/{{storage_config_id}}/activate",
         ["storage-config", "{{storage_config_id}}", "activate"],
         tests=["pm.test('Status 200', () => pm.response.to.have.status(200));",
                "pm.test('is_active true', () => pm.expect(pm.response.json().is_active).to.be.true);"]),
    delete("Delete Storage Config", "storage-config/{{storage_config_id}}",
           ["storage-config", "{{storage_config_id}}"],
           tests=["pm.test('Status 204', () => pm.response.to.have.status(204));"]),
], description="Configure storage backend (MinIO for on-prem, S3 for cloud). Use Activate to switch providers.")

# ---------------------------------------------------------------------------
# 11. Service Endpoints
# ---------------------------------------------------------------------------

service_endpoints_folder = folder("Service Endpoints", [
    get("List Service Endpoints", "service-endpoints", ["service-endpoints"],
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));"]),
    post("Add Spark UI Endpoint", "service-endpoints", ["service-endpoints"],
         payload={"service_name": "spark_ui", "base_url": "http://spark-master:8080", "extra": {}},
         tests=["pm.test('Status 201', () => pm.response.to.have.status(201));",
                "pm.collectionVariables.set('service_endpoint_id', pm.response.json().id);"]),
    post("Add Spark History Server", "service-endpoints", ["service-endpoints"],
         payload={"service_name": "spark_history", "base_url": "http://spark-history:18080", "extra": {}}),
    post("Add Trino UI Endpoint", "service-endpoints", ["service-endpoints"],
         payload={"service_name": "trino_ui", "base_url": "http://trino:8080", "extra": {}}),
    post("Add Airflow UI Endpoint", "service-endpoints", ["service-endpoints"],
         payload={"service_name": "airflow_ui", "base_url": "http://airflow:8080", "extra": {}}),
    post("Add RabbitMQ UI Endpoint", "service-endpoints", ["service-endpoints"],
         payload={"service_name": "rabbitmq_ui", "base_url": "http://rabbitmq:15672", "extra": {}}),
    post("Add Celery Flower Endpoint", "service-endpoints", ["service-endpoints"],
         payload={"service_name": "celery_flower", "base_url": "http://flower:5555", "extra": {}}),
    post("Add Jupyter Endpoint", "service-endpoints", ["service-endpoints"],
         payload={"service_name": "jupyter", "base_url": "http://jupyter:8888", "extra": {}}),
    post("Add MinIO Console Endpoint", "service-endpoints", ["service-endpoints"],
         payload={"service_name": "minio_console", "base_url": "http://minio:9001", "extra": {}}),
    get("Get Service Endpoint", "service-endpoints/{{service_endpoint_id}}",
        ["service-endpoints", "{{service_endpoint_id}}"]),
    put("Update Service Endpoint URL", "service-endpoints/{{service_endpoint_id}}",
        ["service-endpoints", "{{service_endpoint_id}}"],
        payload={"base_url": "http://spark-master-new:8080"}),
    delete("Delete Service Endpoint", "service-endpoints/{{service_endpoint_id}}",
           ["service-endpoints", "{{service_endpoint_id}}"],
           tests=["pm.test('Status 204', () => pm.response.to.have.status(204));"]),
])

# ---------------------------------------------------------------------------
# 12. Monitor (Service Redirects)
# ---------------------------------------------------------------------------

monitor_folder = folder("Monitor (Service Redirects & Health)", [
    get("List All Configured Services", "monitor", ["monitor"],
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));",
               "pm.test('Is array', () => pm.expect(pm.response.json()).to.be.an('array'));"]),
    get("Health Check — Ping All Services", "monitor/health", ["monitor", "health"],
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));",
               "pm.test('Has services array', () => pm.expect(pm.response.json().services).to.be.an('array'));"]),
    get("Spark UI Redirect", "monitor/spark", ["monitor", "spark"],
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));",
               "pm.test('Has redirect_url', () => pm.expect(pm.response.json().redirect_url).to.not.be.empty);"]),
    get("Spark UI — Specific Application", "monitor/spark?app_id=application_1234567890123_0001",
        ["monitor", "spark"], query=[{"key": "app_id", "value": "application_1234567890123_0001"}]),
    get("Spark UI — Specific Job", "monitor/spark?job_id=42",
        ["monitor", "spark"], query=[{"key": "job_id", "value": "42"}]),
    get("Spark History Server", "monitor/spark/history", ["monitor", "spark", "history"]),
    get("Spark History — by App ID", "monitor/spark/history?app_id=application_1234567890123_0001",
        ["monitor", "spark", "history"], query=[{"key": "app_id", "value": "application_1234567890123_0001"}]),
    get("Trino UI Redirect", "monitor/trino", ["monitor", "trino"]),
    get("Trino UI — by Query ID", "monitor/trino?query_id=20240101_123456_00001_abcde",
        ["monitor", "trino"], query=[{"key": "query_id", "value": "20240101_123456_00001_abcde"}]),
    get("Airflow UI Redirect", "monitor/airflow", ["monitor", "airflow"]),
    get("Airflow — by DAG ID", "monitor/airflow?dag_id=my_pipeline_dag",
        ["monitor", "airflow"], query=[{"key": "dag_id", "value": "my_pipeline_dag"}]),
    get("Airflow — by DAG + Run", "monitor/airflow?dag_id=my_pipeline_dag&run_id=manual__2024-01-01T00:00:00",
        ["monitor", "airflow"],
        query=[{"key": "dag_id", "value": "my_pipeline_dag"}, {"key": "run_id", "value": "manual__2024-01-01T00:00:00"}]),
    get("RabbitMQ UI Redirect", "monitor/rabbitmq", ["monitor", "rabbitmq"]),
    get("RabbitMQ — by Queue", "monitor/rabbitmq?queue=deltameta.jobs",
        ["monitor", "rabbitmq"], query=[{"key": "queue", "value": "deltameta.jobs"}]),
    get("Celery Flower Redirect", "monitor/celery", ["monitor", "celery"]),
    get("Celery Flower — by Task ID", "monitor/celery?task_id=abc-123-def-456",
        ["monitor", "celery"], query=[{"key": "task_id", "value": "abc-123-def-456"}]),
    get("Jupyter UI Redirect", "monitor/jupyter", ["monitor", "jupyter"]),
    get("MinIO Console Redirect", "monitor/minio", ["monitor", "minio"]),
], description="Returns redirect_url for each service. Frontend opens url in new tab. Also has /health to ping all.")

# ---------------------------------------------------------------------------
# 13. Admin — User Management
# ---------------------------------------------------------------------------

admin_users_folder = folder("Admin — User Management", [
    get("List Users (org-wide)", "admin/users", ["admin", "users"],
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));",
               "pm.test('Is array', () => pm.expect(pm.response.json()).to.be.an('array'));"]),
    get("List Users — Search", "admin/users?search=john&is_active=true",
        ["admin", "users"],
        query=[{"key": "search", "value": "john"}, {"key": "is_active", "value": "true"}]),
    get("List Users — Admins only", "admin/users?is_admin=true",
        ["admin", "users"], query=[{"key": "is_admin", "value": "true"}]),
    post("Create User (Admin Creates)", "admin/users", ["admin", "users"],
         payload={"email": "newemployee@company.com", "username": "newemployee",
                  "name": "New Employee", "display_name": "New Employee",
                  "is_admin": False, "send_invite": True},
         tests=["pm.test('Status 201', () => pm.response.to.have.status(201));",
                "const d = pm.response.json();",
                "pm.collectionVariables.set('admin_created_user_id', d.id);",
                "pm.test('Active by default', () => pm.expect(d.is_active).to.be.true);",
                "pm.test('Not verified by default', () => pm.expect(d.is_verified).to.be.false);"]),
    get("Get User by ID", "admin/users/{{admin_created_user_id}}",
        ["admin", "users", "{{admin_created_user_id}}"]),
    put("Update User", "admin/users/{{admin_created_user_id}}",
        ["admin", "users", "{{admin_created_user_id}}"],
        payload={"display_name": "Updated Employee Name", "is_admin": False}),
    post("Reset Password (Generate Temp)", "admin/users/{{admin_created_user_id}}/reset-password",
         ["admin", "users", "{{admin_created_user_id}}", "reset-password"],
         payload={},
         tests=["pm.test('Status 200', () => pm.response.to.have.status(200));",
                "const d = pm.response.json();",
                "pm.test('Has temp password', () => pm.expect(d.temporary_password).to.not.be.null);"]),
    post("Reset Password (Set Specific)", "admin/users/{{admin_created_user_id}}/reset-password",
         ["admin", "users", "{{admin_created_user_id}}", "reset-password"],
         payload={"new_password": "NewSecurePass123!"},
         tests=["pm.test('Status 200', () => pm.response.to.have.status(200));"]),
    delete("Deactivate User (Soft Delete)", "admin/users/{{admin_created_user_id}}",
           ["admin", "users", "{{admin_created_user_id}}"],
           tests=["pm.test('Status 204', () => pm.response.to.have.status(204));"]),
], description="Org admin only. Creates users without self-registration. Password can be generated or set.")

# ---------------------------------------------------------------------------
# 14. Organizations — Roles, Policies & Stats
# ---------------------------------------------------------------------------

org_govern_folder = folder("Organizations — Roles, Policies & Stats", [
    get("Org Stats (users, teams, roles, policies)", "orgs/{{org_id}}/stats",
        ["orgs", "{{org_id}}", "stats"],
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));",
               "const d = pm.response.json();",
               "pm.test('Has users count', () => pm.expect(d.users).to.be.a('number'));",
               "pm.test('Has teams count', () => pm.expect(d.teams).to.be.a('number'));"]),
    get("Teams Grouped by Type", "orgs/{{org_id}}/teams-grouped",
        ["orgs", "{{org_id}}", "teams-grouped"],
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));",
               "pm.test('Is object', () => pm.expect(pm.response.json()).to.be.an('object'));"]),
    get("List Org Roles", "orgs/{{org_id}}/roles", ["orgs", "{{org_id}}", "roles"],
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));"]),
    post("Assign Role to Org", "orgs/{{org_id}}/roles/{{role_id}}",
         ["orgs", "{{org_id}}", "roles", "{{role_id}}"],
         tests=["pm.test('Status 201', () => pm.response.to.have.status(201));"]),
    delete("Remove Role from Org", "orgs/{{org_id}}/roles/{{role_id}}",
           ["orgs", "{{org_id}}", "roles", "{{role_id}}"],
           tests=["pm.test('Status 204', () => pm.response.to.have.status(204));"]),
    get("List Org Policies", "orgs/{{org_id}}/policies", ["orgs", "{{org_id}}", "policies"],
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));"]),
    post("Assign Policy to Org", "orgs/{{org_id}}/policies/{{policy_id}}",
         ["orgs", "{{org_id}}", "policies", "{{policy_id}}"],
         tests=["pm.test('Status 201', () => pm.response.to.have.status(201));"]),
    delete("Remove Policy from Org", "orgs/{{org_id}}/policies/{{policy_id}}",
           ["orgs", "{{org_id}}", "policies", "{{policy_id}}"],
           tests=["pm.test('Status 204', () => pm.response.to.have.status(204));"]),
])

# ---------------------------------------------------------------------------
# 15. Teams — Roles, Policies & Stats
# ---------------------------------------------------------------------------

team_govern_folder = folder("Teams — Roles, Policies & Stats", [
    get("Team Stats (members, sub-teams)", "teams/{{team_id}}/stats",
        ["teams", "{{team_id}}", "stats"],
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));",
               "const d = pm.response.json();",
               "pm.test('Has members count', () => pm.expect(d.members).to.be.a('number'));"]),
    get("List Team Roles", "teams/{{team_id}}/roles", ["teams", "{{team_id}}", "roles"]),
    post("Assign Role to Team", "teams/{{team_id}}/roles/{{role_id}}",
         ["teams", "{{team_id}}", "roles", "{{role_id}}"],
         tests=["pm.test('Status 201', () => pm.response.to.have.status(201));"]),
    delete("Remove Role from Team", "teams/{{team_id}}/roles/{{role_id}}",
           ["teams", "{{team_id}}", "roles", "{{role_id}}"],
           tests=["pm.test('Status 204', () => pm.response.to.have.status(204));"]),
    get("List Team Policies", "teams/{{team_id}}/policies", ["teams", "{{team_id}}", "policies"]),
    post("Assign Policy to Team", "teams/{{team_id}}/policies/{{policy_id}}",
         ["teams", "{{team_id}}", "policies", "{{policy_id}}"],
         tests=["pm.test('Status 201', () => pm.response.to.have.status(201));"]),
    delete("Remove Policy from Team", "teams/{{team_id}}/policies/{{policy_id}}",
           ["teams", "{{team_id}}", "policies", "{{policy_id}}"],
           tests=["pm.test('Status 204', () => pm.response.to.have.status(204));"]),
])

# ---------------------------------------------------------------------------
# 16. ABAC — Effective Permissions
# ---------------------------------------------------------------------------

abac_folder = folder("ABAC — Effective Permissions", [
    get("Get My Effective Permissions", "auth/me/permissions", ["auth", "me", "permissions"],
        tests=["pm.test('Status 200', () => pm.response.to.have.status(200));",
               "const d = pm.response.json();",
               "pm.test('Has permissions map', () => pm.expect(d.permissions).to.be.an('object'));",
               "pm.test('Has user_id', () => pm.expect(d.user_id).to.not.be.empty);",
               "pm.collectionVariables.set('user_id', d.user_id);"],
        description="Returns {resource: [operations]} map aggregated from user roles, org roles, team roles, and direct policy assignments."),
], description="Frontend calls this once after login to determine which resources/operations are accessible.")

# ---------------------------------------------------------------------------
# New variables to add
# ---------------------------------------------------------------------------

NEW_VARS = [
    "subject_area_id", "lookup_category_id", "lookup_value_id",
    "catalog_domain_id", "data_product_id",
    "glossary_id", "glossary_term_id",
    "classification_id", "classification_tag_id",
    "govern_metric_id", "change_request_id",
    "storage_config_id", "service_endpoint_id",
    "admin_created_user_id",
]

NEW_FOLDERS = [
    subject_areas_folder,
    lookup_folder,
    catalog_domains_folder,
    data_products_folder,
    glossary_folder,
    classifications_folder,
    govern_metrics_folder,
    change_requests_folder,
    activity_feed_folder,
    storage_config_folder,
    service_endpoints_folder,
    monitor_folder,
    admin_users_folder,
    org_govern_folder,
    team_govern_folder,
    abac_folder,
]

# ---------------------------------------------------------------------------
# Apply to both collections
# ---------------------------------------------------------------------------

new_folder_names = {f["name"] for f in NEW_FOLDERS}

for cpath in COLLECTIONS:
    cpath = os.path.normpath(cpath)
    with open(cpath, "r") as f:
        col = json.load(f)

    # Remove any pre-existing folders with the same names
    col["item"] = [i for i in col["item"] if i.get("name") not in new_folder_names]

    # Append new folders
    col["item"].extend(NEW_FOLDERS)

    # Add new variables (skip if already present)
    existing_var_keys = {v["key"] for v in col.get("variable", [])}
    for var in NEW_VARS:
        if var not in existing_var_keys:
            col.setdefault("variable", []).append({"key": var, "value": "", "type": "string"})

    with open(cpath, "w") as f:
        json.dump(col, f, indent=2)

    total_folders = sum(1 for i in col["item"] if "item" in i)
    total_requests = sum(1 for i in col["item"] if "item" not in i)
    new_request_count = sum(len(f["item"]) for f in NEW_FOLDERS)
    print(f"✓ Updated: {os.path.basename(cpath)}")
    print(f"  Folders: {total_folders} | Top-level requests: {total_requests}")
    print(f"  New requests added: {new_request_count}")
    print()

print("Done.")

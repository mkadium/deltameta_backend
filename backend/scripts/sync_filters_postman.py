"""
Sync Postman collections with all new relational filter query parameters added
in the latest implementation round.

Filters added:
  GET /admin/users       — team_id, role_id, policy_id, domain_id, is_verified
  GET /teams             — member_user_id, role_id, policy_id
  GET /roles             — user_id, team_id, org_id_assigned
  GET /policies          — role_id, team_id, user_id, org_id_assigned
  GET /catalog-domains   — owner_id, expert_id, created_by
  GET /data-products     — owner_id, expert_id
  GET /govern-metrics    — owner_id
  GET /classifications   — owner_id, catalog_domain_id, created_by
  GET /classifications/{id}/tags  — owner_id, catalog_domain_id, created_by
  GET /glossaries/{id}/terms      — owner_id, reviewer_id, liked_by, related_term_id
  GET /change-requests   — assignee_id, resolved_by
  GET /orgs/{id}/members — team_id, role_id
  GET /subject-areas     — team_id
  GET /subscriptions     — subscribed_after, subscribed_before
  NEW GET /lookup/{id}/values     — is_active, search
  GET /lookup            — search, is_active (categories)
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
# Helpers
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


def find_request_in_folder(items, name_fragment=None, method=None, path_fragment=None):
    for item in items:
        if "item" in item:
            found = find_request_in_folder(item["item"], name_fragment, method, path_fragment)
            if found:
                return found
        else:
            req = item.get("request", {})
            url = req.get("url", {})
            raw = url.get("raw", "") if isinstance(url, dict) else url
            name_match = (name_fragment is None) or (name_fragment.lower() in item.get("name", "").lower())
            method_match = (method is None) or (req.get("method", "").upper() == method.upper())
            path_match = (path_fragment is None) or (path_fragment in raw)
            if name_match and method_match and path_match:
                return item
    return None


def replace_or_append_folder(items, new_folder):
    for i, item in enumerate(items):
        if item.get("name") == new_folder["name"] and "item" in item:
            items[i] = new_folder
            return
    items.append(new_folder)


def update_or_add_request_in_folder(folder, new_req):
    """Replace a request by name match inside a folder, or append."""
    for i, item in enumerate(folder["item"]):
        if item.get("name") == new_req["name"]:
            folder["item"][i] = new_req
            return
    folder["item"].append(new_req)


# ---------------------------------------------------------------------------
# Build updated List requests with all filters
# ---------------------------------------------------------------------------

COMMON_PAGINATION = [
    _q("skip", "0", disabled=True, description="Offset for pagination."),
    _q("limit", "50", disabled=True, description="Max records per page (1–200)."),
]


def _list_users_request(base_var):
    return make_request(
        "List Users",
        "GET", "/admin/users",
        base_var,
        query_params=[
            _q("search", "", disabled=True, description="Search by email, display_name, or username."),
            _q("is_active", "true", disabled=True),
            _q("is_admin", "false", disabled=True),
            _q("is_verified", "false", disabled=True, description="Filter by email-verified status."),
            _q("team_id", "{{team_id}}", disabled=True, description="[RELATIONAL] Users belonging to this team."),
            _q("role_id", "{{role_id}}", disabled=True, description="[RELATIONAL] Users with this role assigned."),
            _q("policy_id", "{{policy_id}}", disabled=True, description="[RELATIONAL] Users with this policy directly assigned."),
            _q("domain_id", "{{domain_id}}", disabled=True, description="[RELATIONAL] Users whose primary subject area matches."),
            *COMMON_PAGINATION,
        ],
        description="List admin users with comprehensive filters including relational joins.",
    )


def _list_teams_request(base_var):
    return make_request(
        "List Teams",
        "GET", "/teams",
        base_var,
        query_params=[
            _q("org_id", "{{org_id}}", disabled=True),
            _q("team_type", "department", disabled=True, description="business_unit | division | department | group"),
            _q("parent_team_id", "{{parent_team_id}}", disabled=True),
            _q("root_only", "false", disabled=True),
            _q("domain_id", "{{domain_id}}", disabled=True),
            _q("search", "", disabled=True),
            _q("is_active", "true", disabled=True),
            _q("public_team_view", "false", disabled=True),
            _q("member_user_id", "{{user_id}}", disabled=True, description="[RELATIONAL] Teams a specific user belongs to."),
            _q("role_id", "{{role_id}}", disabled=True, description="[RELATIONAL] Teams that have this role assigned."),
            _q("policy_id", "{{policy_id}}", disabled=True, description="[RELATIONAL] Teams that have this policy assigned."),
            *COMMON_PAGINATION,
        ],
        description="List teams with comprehensive filters including relational joins (member, role, policy).",
    )


def _list_roles_request(base_var):
    return make_request(
        "List Roles",
        "GET", "/roles",
        base_var,
        query_params=[
            _q("search", "", disabled=True),
            _q("is_system_role", "false", disabled=True),
            _q("user_id", "{{user_id}}", disabled=True, description="[RELATIONAL] Roles assigned to a specific user."),
            _q("team_id", "{{team_id}}", disabled=True, description="[RELATIONAL] Roles assigned to a specific team."),
            _q("org_id_assigned", "{{org_id}}", disabled=True, description="[RELATIONAL] Roles assigned to a specific org."),
            *COMMON_PAGINATION,
        ],
        description="List roles with relational filters (by user, team, or org assignment).",
    )


def _list_policies_request(base_var):
    return make_request(
        "List Policies",
        "GET", "/policies",
        base_var,
        query_params=[
            _q("search", "", disabled=True),
            _q("resource", "", disabled=True),
            _q("role_id", "{{role_id}}", disabled=True, description="[RELATIONAL] Policies assigned to this role."),
            _q("team_id", "{{team_id}}", disabled=True, description="[RELATIONAL] Policies assigned to this team."),
            _q("user_id", "{{user_id}}", disabled=True, description="[RELATIONAL] Policies directly assigned to this user."),
            _q("org_id_assigned", "{{org_id}}", disabled=True, description="[RELATIONAL] Policies assigned to this org."),
            *COMMON_PAGINATION,
        ],
        description="List policies with relational filters (by role, team, user, org assignment).",
    )


def _list_catalog_domains_request(base_var):
    return make_request(
        "List Catalog Domains",
        "GET", "/catalog-domains",
        base_var,
        query_params=[
            _q("search", "", disabled=True),
            _q("domain_type", "", disabled=True),
            _q("is_active", "true", disabled=True),
            _q("created_by", "{{user_id}}", disabled=True, description="Filter by creator user ID."),
            _q("owner_id", "{{user_id}}", disabled=True, description="[RELATIONAL] Domains owned by this user."),
            _q("expert_id", "{{user_id}}", disabled=True, description="[RELATIONAL] Domains where this user is an expert."),
            *COMMON_PAGINATION,
        ],
        description="List catalog domains with M2M filters (owner, expert).",
    )


def _list_data_products_request(base_var):
    return make_request(
        "List Data Products",
        "GET", "/data-products",
        base_var,
        query_params=[
            _q("search", "", disabled=True),
            _q("domain_id", "{{catalog_domain_id}}", disabled=True),
            _q("status", "draft", disabled=True, description="draft | published | deprecated"),
            _q("is_active", "true", disabled=True),
            _q("version", "", disabled=True),
            _q("created_by", "{{user_id}}", disabled=True),
            _q("owner_id", "{{user_id}}", disabled=True, description="[RELATIONAL] Products owned by this user."),
            _q("expert_id", "{{user_id}}", disabled=True, description="[RELATIONAL] Products where this user is an expert."),
            *COMMON_PAGINATION,
        ],
        description="List data products with M2M filters (owner, expert).",
    )


def _list_govern_metrics_request(base_var):
    return make_request(
        "List Govern Metrics",
        "GET", "/govern-metrics",
        base_var,
        query_params=[
            _q("search", "", disabled=True),
            _q("metric_type", "", disabled=True),
            _q("granularity", "", disabled=True, description="daily | weekly | monthly"),
            _q("language", "", disabled=True, description="SQL | Python"),
            _q("is_active", "true", disabled=True),
            _q("created_by", "{{user_id}}", disabled=True),
            _q("owner_id", "{{user_id}}", disabled=True, description="[RELATIONAL] Metrics owned by this user."),
            *COMMON_PAGINATION,
        ],
        description="List governance metrics with M2M owner filter.",
    )


def _list_classifications_request(base_var):
    return make_request(
        "List Classifications",
        "GET", "/classifications",
        base_var,
        query_params=[
            _q("search", "", disabled=True),
            _q("is_active", "true", disabled=True),
            _q("mutually_exclusive", "", disabled=True),
            _q("created_by", "{{user_id}}", disabled=True),
            _q("owner_id", "{{user_id}}", disabled=True, description="[RELATIONAL] Classifications owned by this user."),
            _q("catalog_domain_id", "{{catalog_domain_id}}", disabled=True, description="[RELATIONAL] Classifications linked to this catalog domain."),
            *COMMON_PAGINATION,
        ],
        description="List classifications with M2M filters (owner, catalog domain).",
    )


def _list_tags_request(base_var):
    return make_request(
        "List Tags",
        "GET", "/classifications/{{classification_id}}/tags",
        base_var,
        query_params=[
            _q("search", "", disabled=True),
            _q("is_active", "true", disabled=True),
            _q("created_by", "{{user_id}}", disabled=True),
            _q("owner_id", "{{user_id}}", disabled=True, description="[RELATIONAL] Tags owned by this user."),
            _q("catalog_domain_id", "{{catalog_domain_id}}", disabled=True, description="[RELATIONAL] Tags linked to this catalog domain."),
            *COMMON_PAGINATION,
        ],
        description="List classification tags with M2M filters (owner, catalog domain).",
    )


def _list_glossary_terms_request(base_var):
    return make_request(
        "List Terms",
        "GET", "/glossaries/{{glossary_id}}/terms",
        base_var,
        query_params=[
            _q("search", "", disabled=True),
            _q("is_active", "true", disabled=True),
            _q("mutually_exclusive", "", disabled=True),
            _q("created_by", "{{user_id}}", disabled=True),
            _q("owner_id", "{{user_id}}", disabled=True, description="[RELATIONAL] Terms owned by this user."),
            _q("reviewer_id", "{{user_id}}", disabled=True, description="[RELATIONAL] Terms reviewed by this user."),
            _q("liked_by", "{{user_id}}", disabled=True, description="[RELATIONAL] Terms liked by this user."),
            _q("related_term_id", "{{term_id}}", disabled=True, description="[RELATIONAL] Terms related to this specific term."),
            *COMMON_PAGINATION,
        ],
        description="List glossary terms with M2M filters (owner, reviewer, liked_by, related_term).",
    )


def _list_change_requests_request(base_var):
    return make_request(
        "List Change Requests",
        "GET", "/change-requests",
        base_var,
        query_params=[
            _q("entity_type", "", disabled=True, description="catalog_domain | glossary_term | data_product | ..."),
            _q("entity_id", "{{entity_id}}", disabled=True),
            _q("status", "open", disabled=True, description="open | in_review | approved | rejected | withdrawn"),
            _q("requested_by", "{{user_id}}", disabled=True),
            _q("resolved_by", "{{user_id}}", disabled=True, description="Filter by resolver user ID."),
            _q("field_name", "", disabled=True),
            _q("assignee_id", "{{user_id}}", disabled=True, description="[RELATIONAL] CRs assigned to this user."),
            *COMMON_PAGINATION,
        ],
        description="List change requests with relational assignee_id and resolved_by filters.",
    )


def _list_org_members_request(base_var):
    return make_request(
        "List Org Members",
        "GET", "/orgs/{{org_id}}/members",
        base_var,
        query_params=[
            _q("search", "", disabled=True),
            _q("is_active", "true", disabled=True),
            _q("is_org_admin", "", disabled=True),
            _q("domain_id", "{{domain_id}}", disabled=True),
            _q("team_id", "{{team_id}}", disabled=True, description="[RELATIONAL] Members who belong to this team."),
            _q("role_id", "{{role_id}}", disabled=True, description="[RELATIONAL] Members who have this role assigned."),
            *COMMON_PAGINATION,
        ],
        description="List org members with relational filters (team_id, role_id).",
    )


def _list_subject_areas_request(base_var):
    return make_request(
        "List Subject Areas",
        "GET", "/subject-areas",
        base_var,
        query_params=[
            _q("search", "", disabled=True),
            _q("is_active", "true", disabled=True),
            _q("domain_type", "", disabled=True),
            _q("owner_id", "{{user_id}}", disabled=True),
            _q("team_id", "{{team_id}}", disabled=True, description="[RELATIONAL] Subject areas that the given team is linked to."),
            *COMMON_PAGINATION,
        ],
        description="List subject areas. team_id filter returns subject areas linked to the given team.",
    )


def _list_subscriptions_request(base_var):
    return make_request(
        "List Subscriptions",
        "GET", "/subscriptions",
        base_var,
        query_params=[
            _q("resource_type", "", disabled=True, description="dataset | data_product | team | user | ..."),
            _q("resource_id", "{{resource_id}}", disabled=True),
            _q("subscriber_user_id", "{{user_id}}", disabled=True),
            _q("notify_on_update", "", disabled=True),
            _q("subscribed_after", "2024-01-01T00:00:00", disabled=True, description="ISO 8601 datetime — subscriptions after this date."),
            _q("subscribed_before", "2099-12-31T23:59:59", disabled=True, description="ISO 8601 datetime — subscriptions before this date."),
            *COMMON_PAGINATION,
        ],
        description="List subscriptions with date range filters (subscribed_after, subscribed_before).",
    )


def _list_lookup_categories_request(base_var):
    return make_request(
        "List Lookup Categories",
        "GET", "/lookup",
        base_var,
        query_params=[
            _q("search", "", disabled=True, description="Search by category name or slug."),
            _q("is_system", "", disabled=True, description="true = system categories only; false = org-custom only."),
            *COMMON_PAGINATION,
        ],
        description="List lookup categories. New: search and pagination.",
    )


def _list_lookup_values_request(base_var):
    return make_request(
        "List Lookup Values",
        "GET", "/lookup/{{category_id}}/values",
        base_var,
        query_params=[
            _q("search", "", disabled=True, description="Search by label or value."),
            _q("is_active", "true", disabled=True),
            _q("skip", "0", disabled=True),
            _q("limit", "100", disabled=True),
        ],
        description="NEW endpoint — list values for a lookup category with search and is_active filters.",
    )


# ---------------------------------------------------------------------------
# Apply changes
# ---------------------------------------------------------------------------

def apply_filter_changes(col: dict, base_var: str) -> None:
    items = col["item"]

    # -- Admin Users --
    admin_folder = find_folder(items, "Admin — User Management")
    if admin_folder:
        req = find_request_in_folder(admin_folder["item"], name_fragment="List Users", method="GET")
        if req:
            req["request"]["url"]["query"] = _list_users_request(base_var)["request"]["url"]["query"]
            req["request"]["description"] = _list_users_request(base_var)["request"]["description"]
        else:
            admin_folder["item"].insert(0, _list_users_request(base_var))

    # -- Teams --
    teams_folder = find_folder(items, "Teams")
    if teams_folder:
        req = find_request_in_folder(teams_folder["item"], name_fragment="List Teams", method="GET")
        if req:
            req["request"]["url"]["query"] = _list_teams_request(base_var)["request"]["url"]["query"]
            req["request"]["description"] = _list_teams_request(base_var)["request"]["description"]
        else:
            teams_folder["item"].insert(0, _list_teams_request(base_var))

    # -- Roles --
    roles_folder = find_folder(items, "Roles")
    if roles_folder:
        req = find_request_in_folder(roles_folder["item"], name_fragment="List Roles", method="GET")
        if req:
            req["request"]["url"]["query"] = _list_roles_request(base_var)["request"]["url"]["query"]
            req["request"]["description"] = _list_roles_request(base_var)["request"]["description"]
        else:
            roles_folder["item"].insert(0, _list_roles_request(base_var))

    # -- Policies --
    policies_folder = find_folder(items, "Policies")
    if policies_folder:
        req = find_request_in_folder(policies_folder["item"], name_fragment="List Policies", method="GET")
        if req:
            req["request"]["url"]["query"] = _list_policies_request(base_var)["request"]["url"]["query"]
            req["request"]["description"] = _list_policies_request(base_var)["request"]["description"]
        else:
            policies_folder["item"].insert(0, _list_policies_request(base_var))

    # -- Catalog Domains --
    cd_folder = find_folder(items, "Catalog Domains")
    if cd_folder:
        req = find_request_in_folder(cd_folder["item"], name_fragment="List", method="GET")
        if req:
            req["request"]["url"]["query"] = _list_catalog_domains_request(base_var)["request"]["url"]["query"]
            req["request"]["description"] = _list_catalog_domains_request(base_var)["request"]["description"]
        else:
            cd_folder["item"].insert(0, _list_catalog_domains_request(base_var))

    # -- Data Products --
    dp_folder = find_folder(items, "Data Products")
    if dp_folder:
        req = find_request_in_folder(dp_folder["item"], name_fragment="List", method="GET")
        if req:
            req["request"]["url"]["query"] = _list_data_products_request(base_var)["request"]["url"]["query"]
            req["request"]["description"] = _list_data_products_request(base_var)["request"]["description"]
        else:
            dp_folder["item"].insert(0, _list_data_products_request(base_var))

    # -- Govern Metrics --
    gm_folder = find_folder(items, "Govern Metrics")
    if gm_folder:
        req = find_request_in_folder(gm_folder["item"], name_fragment="List Metrics", method="GET")
        if not req:
            req = find_request_in_folder(gm_folder["item"], name_fragment="List", method="GET",
                                         path_fragment="/govern-metrics")
        if req:
            req["request"]["url"]["query"] = _list_govern_metrics_request(base_var)["request"]["url"]["query"]
            req["request"]["description"] = _list_govern_metrics_request(base_var)["request"]["description"]
        else:
            gm_folder["item"].insert(0, _list_govern_metrics_request(base_var))

    # -- Classifications --
    cls_folder = find_folder(items, "Classifications & Tags") or find_folder(items, "Classifications")
    if cls_folder:
        req = find_request_in_folder(cls_folder["item"], name_fragment="List Classifications", method="GET")
        if req:
            req["request"]["url"]["query"] = _list_classifications_request(base_var)["request"]["url"]["query"]
            req["request"]["description"] = _list_classifications_request(base_var)["request"]["description"]
        else:
            cls_folder["item"].insert(0, _list_classifications_request(base_var))
        # Tags within classifications
        req_tags = find_request_in_folder(cls_folder["item"], name_fragment="List Tags", method="GET")
        if req_tags:
            req_tags["request"]["url"]["query"] = _list_tags_request(base_var)["request"]["url"]["query"]
            req_tags["request"]["description"] = _list_tags_request(base_var)["request"]["description"]
        else:
            cls_folder["item"].append(_list_tags_request(base_var))

    # -- Glossary (terms) --
    gl_folder = find_folder(items, "Glossary")
    if gl_folder:
        req = find_request_in_folder(gl_folder["item"], name_fragment="List Terms", method="GET")
        if req:
            req["request"]["url"]["query"] = _list_glossary_terms_request(base_var)["request"]["url"]["query"]
            req["request"]["description"] = _list_glossary_terms_request(base_var)["request"]["description"]
        else:
            gl_folder["item"].append(_list_glossary_terms_request(base_var))

    # -- Change Requests --
    cr_folder = find_folder(items, "Change Requests (Tasks)") or find_folder(items, "Change Requests")
    if cr_folder:
        req = find_request_in_folder(cr_folder["item"], name_fragment="List", method="GET")
        if req:
            req["request"]["url"]["query"] = _list_change_requests_request(base_var)["request"]["url"]["query"]
            req["request"]["description"] = _list_change_requests_request(base_var)["request"]["description"]
        else:
            cr_folder["item"].insert(0, _list_change_requests_request(base_var))

    # -- Organizations members --
    org_folder = find_folder(items, "Organizations (CRUD & Membership)")
    if not org_folder:
        org_folder = find_folder(items, "Organizations")
    if org_folder:
        req = find_request_in_folder(org_folder["item"], name_fragment="List Org Members", method="GET")
        if req:
            req["request"]["url"]["query"] = _list_org_members_request(base_var)["request"]["url"]["query"]
            req["request"]["description"] = _list_org_members_request(base_var)["request"]["description"]
        else:
            org_folder["item"].append(_list_org_members_request(base_var))

    # -- Subject Areas --
    sa_folder = find_folder(items, "Subject Areas")
    if sa_folder:
        req = find_request_in_folder(sa_folder["item"], name_fragment="List", method="GET")
        if req:
            req["request"]["url"]["query"] = _list_subject_areas_request(base_var)["request"]["url"]["query"]
            req["request"]["description"] = _list_subject_areas_request(base_var)["request"]["description"]
        else:
            sa_folder["item"].insert(0, _list_subject_areas_request(base_var))

    # -- Subscriptions --
    sub_folder = find_folder(items, "Subscriptions")
    if sub_folder:
        req = find_request_in_folder(sub_folder["item"], name_fragment="List Subscriptions", method="GET")
        if req:
            req["request"]["url"]["query"] = _list_subscriptions_request(base_var)["request"]["url"]["query"]
            req["request"]["description"] = _list_subscriptions_request(base_var)["request"]["description"]
        else:
            sub_folder["item"].insert(0, _list_subscriptions_request(base_var))

    # -- Lookup — update categories list + add values list endpoint --
    lookup_folder = find_folder(items, "Lookup (Dropdowns)") or find_folder(items, "Lookup")
    if lookup_folder:
        req = find_request_in_folder(lookup_folder["item"], name_fragment="List", method="GET",
                                     path_fragment="/lookup")
        if req and "values" not in req["request"].get("url", {}).get("raw", ""):
            req["request"]["url"]["query"] = _list_lookup_categories_request(base_var)["request"]["url"]["query"]
            req["request"]["description"] = _list_lookup_categories_request(base_var)["request"]["description"]
        # Add list values endpoint if missing
        existing = find_request_in_folder(lookup_folder["item"], name_fragment="List Lookup Values", method="GET")
        if not existing:
            lookup_folder["item"].append(_list_lookup_values_request(base_var))
        else:
            existing["request"]["url"]["query"] = _list_lookup_values_request(base_var)["request"]["url"]["query"]
            existing["request"]["description"] = _list_lookup_values_request(base_var)["request"]["description"]

    # Ensure collection variables include common filter vars
    existing_vars = {v["key"] for v in col.get("variable", [])}
    new_vars = [
        {"key": "team_id", "value": "", "type": "string"},
        {"key": "role_id", "value": "", "type": "string"},
        {"key": "policy_id", "value": "", "type": "string"},
        {"key": "catalog_domain_id", "value": "", "type": "string"},
        {"key": "classification_id", "value": "", "type": "string"},
        {"key": "glossary_id", "value": "", "type": "string"},
        {"key": "term_id", "value": "", "type": "string"},
        {"key": "entity_id", "value": "", "type": "string"},
        {"key": "resource_id", "value": "", "type": "string"},
        {"key": "category_id", "value": "", "type": "string"},
    ]
    for v in new_vars:
        if v["key"] not in existing_vars:
            col.setdefault("variable", []).append(v)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    for filepath in FILES:
        if not os.path.exists(filepath):
            print(f"SKIP (not found): {filepath}")
            continue
        with open(filepath, "r") as f:
            col = json.load(f)

        # Detect base_url variable name
        base_var = "{{base_url}}"
        for var in col.get("variable", []):
            if var.get("key") == "base_url":
                base_var = "{{base_url}}"
                break
            if var.get("key") == "vercel_base_url":
                base_var = "{{vercel_base_url}}"
                break

        apply_filter_changes(col, base_var)

        with open(filepath, "w") as f:
            json.dump(col, f, indent=2)

        print(f"UPDATED: {os.path.basename(filepath)}")

    print("\nDone — all relational filter query params synced to Postman collections.")


if __name__ == "__main__":
    main()

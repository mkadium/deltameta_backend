"""
Sync Postman collections with all API changes made since last update.

Changes to sync:
  1.  Teams — POST /teams body now requires org_id
  2.  Teams — GET /teams now accepts org_id query param
  3.  Teams — new member management endpoints (POST/DELETE /teams/{id}/members/{user_id})
  4.  Domains folder removed, replaced by Subject Areas (already present, just remove Domains folder)
  5.  Policies — 4 new user-policy endpoints
  6.  Organizations — new PATCH /orgs/{org_id}/members/{user_id} (toggle is_org_admin)
  7.  Admin Users — completely new create/reset-password schema
  8.  Auth — GET /auth/me/permissions (already present — verify)
"""
import json
import os
import uuid as uuid_mod
from copy import deepcopy

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = [
    os.path.join(BASE_DIR, "deltameta_auth.postman_collection.json"),
    os.path.join(BASE_DIR, "vercel_deltameta_auth.postman_collection.json"),
]


# ---------------------------------------------------------------------------
# Builder helpers
# ---------------------------------------------------------------------------

def _id():
    return str(uuid_mod.uuid4())


def make_request(
    name: str,
    method: str,
    path: str,  # e.g. "/teams/{{team_id}}/members/{{user_id}}"
    base_var: str = "{{base_url}}",
    body: dict | None = None,
    query_params: list[dict] | None = None,
    description: str = "",
) -> dict:
    url_parts = [p for p in path.lstrip("/").split("/") if p]
    url_raw = base_var + path

    if query_params:
        qs = "&".join(f"{p['key']}={p['value']}" for p in query_params)
        url_raw += "?" + qs

    request: dict = {
        "method": method.upper(),
        "header": [{"key": "Authorization", "value": "Bearer {{token}}"}],
        "url": {
            "raw": url_raw,
            "host": [base_var],
            "path": url_parts,
        },
        "description": description,
    }

    if query_params:
        request["url"]["query"] = [
            {"key": p["key"], "value": p["value"], "disabled": p.get("disabled", False)}
            for p in query_params
        ]

    if body is not None:
        request["body"] = {
            "mode": "raw",
            "raw": json.dumps(body, indent=2),
            "options": {"raw": {"language": "json"}},
        }

    return {"id": _id(), "name": name, "request": request, "response": []}


def make_folder(name: str, items: list) -> dict:
    return {"id": _id(), "name": name, "item": items}


def find_folder(collection_items: list, name: str) -> dict | None:
    for item in collection_items:
        if item.get("name") == name and "item" in item:
            return item
    return None


def find_request(items: list, method: str, path_fragment: str) -> dict | None:
    for item in items:
        if "item" in item:
            found = find_request(item["item"], method, path_fragment)
            if found:
                return found
        else:
            req = item.get("request", {})
            url = req.get("url", {})
            raw = url.get("raw", "") if isinstance(url, dict) else url
            if req.get("method", "").upper() == method.upper() and path_fragment in raw:
                return item
    return None


def remove_folder(collection_items: list, name: str) -> None:
    for i, item in enumerate(collection_items):
        if item.get("name") == name and "item" in item:
            collection_items.pop(i)
            return


def replace_or_append_folder(collection_items: list, new_folder: dict) -> None:
    for i, item in enumerate(collection_items):
        if item.get("name") == new_folder["name"] and "item" in item:
            collection_items[i] = new_folder
            return
    collection_items.append(new_folder)


# ---------------------------------------------------------------------------
# All changes
# ---------------------------------------------------------------------------

def apply_changes(col: dict, base_var: str) -> None:
    items = col["item"]

    # -------------------------------------------------------------------------
    # 1. REMOVE /domains folder (replaced by /subject-areas)
    # -------------------------------------------------------------------------
    remove_folder(items, "Domains")

    # -------------------------------------------------------------------------
    # 2. TEAMS folder — update POST body + GET query + add member endpoints
    # -------------------------------------------------------------------------
    teams_folder = find_folder(items, "Teams")
    if teams_folder:
        # Rebuild the full Teams folder cleanly
        teams_folder["item"] = [
            make_request(
                "List Teams",
                "GET", "/teams",
                base_var,
                query_params=[
                    {"key": "org_id", "value": "{{org_id}}", "disabled": True},
                    {"key": "team_type", "value": "department", "disabled": True},
                    {"key": "root_only", "value": "false", "disabled": True},
                ],
                description="List teams. Filter by org_id (defaults to active org if omitted), team_type, parent.",
            ),
            make_request(
                "Create Team",
                "POST", "/teams",
                base_var,
                body={
                    "org_id": "{{org_id}}",
                    "name": "Engineering",
                    "team_type": "department",
                    "display_name": "Engineering Team",
                    "description": "Core engineering department",
                    "public_team_view": False,
                    "parent_team_id": None,
                },
                description="org_id is REQUIRED — must be an org the caller is an admin of.",
            ),
            make_request(
                "Create Child Team",
                "POST", "/teams",
                base_var,
                body={
                    "org_id": "{{org_id}}",
                    "name": "Frontend",
                    "team_type": "group",
                    "parent_team_id": "{{team_id}}",
                },
                description="Create a team nested under a parent team.",
            ),
            make_request("Get Team", "GET", "/teams/{{team_id}}", base_var),
            make_request("Get Team Hierarchy", "GET", "/teams/{{team_id}}/hierarchy", base_var,
                         description="Returns full child-tree rooted at this team."),
            make_request(
                "Update Team",
                "PUT", "/teams/{{team_id}}",
                base_var,
                body={"name": "Updated Name", "description": "Updated description"},
            ),
            make_request("Delete Team", "DELETE", "/teams/{{team_id}}", base_var),
            # Members
            make_request("List Team Members", "GET", "/teams/{{team_id}}/members", base_var),
            make_request(
                "Add Member to Team",
                "POST", "/teams/{{team_id}}/members/{{user_id}}",
                base_var,
                description="Add a user to a team. Requires org admin.",
            ),
            make_request(
                "Remove Member from Team",
                "DELETE", "/teams/{{team_id}}/members/{{user_id}}",
                base_var,
                description="Remove a user from a team.",
            ),
            # Stats, Roles, Policies (already existed, keeping them clean)
            make_request("Get Team Stats", "GET", "/teams/{{team_id}}/stats", base_var),
            make_request("List Team Roles", "GET", "/teams/{{team_id}}/roles", base_var),
            make_request("Assign Role to Team", "POST", "/teams/{{team_id}}/roles/{{role_id}}", base_var),
            make_request("Remove Role from Team", "DELETE", "/teams/{{team_id}}/roles/{{role_id}}", base_var),
            make_request("List Team Policies", "GET", "/teams/{{team_id}}/policies", base_var),
            make_request("Assign Policy to Team", "POST", "/teams/{{team_id}}/policies/{{policy_id}}", base_var),
            make_request("Remove Policy from Team", "DELETE", "/teams/{{team_id}}/policies/{{policy_id}}", base_var),
        ]
        # Remove the old standalone Teams — Roles, Policies & Stats folder if exists
        remove_folder(items, "Teams — Roles, Policies & Stats")

    # -------------------------------------------------------------------------
    # 3. POLICIES folder — add user-policy management endpoints
    # -------------------------------------------------------------------------
    policies_folder = find_folder(items, "Policies")
    if policies_folder:
        existing_names = {i["name"] for i in policies_folder["item"]}
        new_policy_items = [
            make_request(
                "List Users with Policy",
                "GET", "/policies/{{policy_id}}/users",
                base_var,
                description="List all users who have this policy directly assigned (org admin).",
            ),
            make_request(
                "Assign Policy to User",
                "POST", "/policies/{{policy_id}}/assign/{{user_id}}",
                base_var,
                description="Directly assign a policy to a user (bypassing roles). Org admin only.",
            ),
            make_request(
                "Remove Policy from User",
                "DELETE", "/policies/{{policy_id}}/assign/{{user_id}}",
                base_var,
                description="Remove a directly-assigned policy from a user.",
            ),
            make_request(
                "List User's Direct Policies",
                "GET", "/policies/user/{{user_id}}",
                base_var,
                description="List all policies directly assigned to a specific user.",
            ),
        ]
        for req in new_policy_items:
            if req["name"] not in existing_names:
                policies_folder["item"].append(req)

    # -------------------------------------------------------------------------
    # 4. ORGANIZATIONS — update existing + add PATCH member role endpoint
    # -------------------------------------------------------------------------
    org_folder = find_folder(items, "Organizations (CRUD & Membership)")
    if org_folder:
        existing_names = {i["name"] for i in org_folder["item"]}
        if "Update Member Role (Toggle Org Admin)" not in existing_names:
            # Insert PATCH after the existing POST member endpoint
            patch_item = make_request(
                "Update Member Role (Toggle Org Admin)",
                "PATCH", "/orgs/{{org_id}}/members/{{user_id}}",
                base_var,
                query_params=[{"key": "is_org_admin", "value": "true"}],
                description=(
                    "Promote or demote a member's org-admin status.\n"
                    "Pass ?is_org_admin=true to promote, ?is_org_admin=false to demote.\n"
                    "Guards against demoting the last admin of an org."
                ),
            )
            # Find POST members index and insert after
            for i, item in enumerate(org_folder["item"]):
                req = item.get("request", {})
                url = req.get("url", {})
                raw = url.get("raw", "") if isinstance(url, dict) else url
                if req.get("method") == "POST" and "/members/{{user_id}}" in raw:
                    org_folder["item"].insert(i + 1, patch_item)
                    break
            else:
                org_folder["item"].append(patch_item)

        # Remove the old "Organizations — Roles, Policies & Stats" standalone folder
        # and merge into the main orgs folder
        roles_policies_folder = find_folder(items, "Organizations — Roles, Policies & Stats")
        if roles_policies_folder:
            existing_names_main = {i["name"] for i in org_folder["item"]}
            for sub_item in roles_policies_folder["item"]:
                if sub_item["name"] not in existing_names_main:
                    org_folder["item"].append(sub_item)
            remove_folder(items, "Organizations — Roles, Policies & Stats")

    # -------------------------------------------------------------------------
    # 5. ADMIN — completely replace create/reset-password requests with new schema
    # -------------------------------------------------------------------------
    admin_folder = find_folder(items, "Admin — User Management")
    if admin_folder:
        admin_folder["item"] = [
            make_request(
                "List Users",
                "GET", "/admin/users",
                base_var,
                description="List all users in the active org. Supports search, is_active, is_admin filters.",
            ),
            make_request(
                "List Users — Search",
                "GET", "/admin/users",
                base_var,
                query_params=[
                    {"key": "search", "value": "john"},
                    {"key": "is_active", "value": "true"},
                ],
            ),
            make_request(
                "List Users — Admins Only",
                "GET", "/admin/users",
                base_var,
                query_params=[{"key": "is_admin", "value": "true"}],
            ),
            make_request(
                "Create User",
                "POST", "/admin/users",
                base_var,
                body={
                    "email": "john.doe@acme.com",
                    "display_name": "John Doe",
                    "description": "Senior data engineer",
                    "password": "Secure@1234",
                    "confirm_password": "Secure@1234",
                    "is_admin": False,
                    "team_ids": [],
                    "role_ids": [],
                    "domain_ids": [],
                },
                description=(
                    "Create a user in the active org.\n\n"
                    "username is auto-derived from email.\n"
                    "password + confirm_password must match and meet strength requirements "
                    "(min 8 chars, upper+lower+digit).\n"
                    "team_ids, role_ids, domain_ids — UUIDs of org-scoped entities to assign at creation."
                ),
            ),
            make_request(
                "Create User (with Teams & Roles)",
                "POST", "/admin/users",
                base_var,
                body={
                    "email": "alice.smith@acme.com",
                    "display_name": "Alice Smith",
                    "password": "Alice@5678",
                    "confirm_password": "Alice@5678",
                    "is_admin": False,
                    "team_ids": ["{{team_id}}"],
                    "role_ids": ["{{role_id}}"],
                    "domain_ids": [],
                },
                description="Create a user and assign to teams and roles at the same time.",
            ),
            make_request(
                "Get User",
                "GET", "/admin/users/{{admin_created_user_id}}",
                base_var,
            ),
            make_request(
                "Update User",
                "PUT", "/admin/users/{{admin_created_user_id}}",
                base_var,
                body={
                    "display_name": "John D. Updated",
                    "description": "Updated description",
                    "is_admin": False,
                    "team_ids": ["{{team_id}}"],
                    "role_ids": [],
                    "domain_ids": [],
                },
                description=(
                    "Update user profile and reassign teams/roles/domains.\n"
                    "team_ids/role_ids/domain_ids are full-replace — pass empty list [] to remove all."
                ),
            ),
            make_request(
                "Reset User Password",
                "POST", "/admin/users/{{admin_created_user_id}}/reset-password",
                base_var,
                body={
                    "new_password": "NewPass@999",
                    "confirm_password": "NewPass@999",
                },
                description="Admin sets a new password for a user. Both fields required and must match.",
            ),
            make_request(
                "Deactivate User",
                "DELETE", "/admin/users/{{admin_created_user_id}}",
                base_var,
                description="Soft-delete (deactivate) a user. Cannot deactivate yourself.",
            ),
        ]

    # -------------------------------------------------------------------------
    # 6. Add admin_created_user_id variable if missing
    # -------------------------------------------------------------------------
    variables = col.get("variable", [])
    var_keys = {v["key"] for v in variables}
    for key, value in [
        ("admin_created_user_id", ""),
        ("user_id", ""),
    ]:
        if key not in var_keys:
            variables.append({"key": key, "value": value, "type": "string"})

    # -------------------------------------------------------------------------
    # 7. Subject Areas folder — ensure it's present and clean
    # -------------------------------------------------------------------------
    sa_folder = find_folder(items, "Subject Areas")
    if not sa_folder:
        sa_folder = make_folder("Subject Areas", [])
        items.append(sa_folder)

    sa_folder["item"] = [
        make_request(
            "List Subject Areas",
            "GET", "/subject-areas",
            base_var,
            query_params=[
                {"key": "search", "value": "", "disabled": True},
                {"key": "is_active", "value": "true", "disabled": True},
            ],
            description="List subject areas (formerly /domains). Replaces /domains.",
        ),
        make_request(
            "Create Subject Area",
            "POST", "/subject-areas",
            base_var,
            body={
                "name": "Finance",
                "display_name": "Finance Domain",
                "description": "Financial data subject area",
                "domain_type": "Business",
            },
            description="Creates a subject area in the active org. Returns 409 if name already exists.",
        ),
        make_request("Get Subject Area", "GET", "/subject-areas/{{subject_area_id}}", base_var),
        make_request(
            "Update Subject Area",
            "PUT", "/subject-areas/{{subject_area_id}}",
            base_var,
            body={"description": "Updated description", "is_active": True},
        ),
        make_request(
            "Delete Subject Area",
            "DELETE", "/subject-areas/{{subject_area_id}}",
            base_var,
            description="Returns 204 No Content on success.",
        ),
    ]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def update_collection(filepath: str) -> None:
    with open(filepath, "r") as f:
        col = json.load(f)

    # Detect base_url variable name
    variables = col.get("variable", [])
    base_var = "{{base_url}}"
    for v in variables:
        if v.get("key") == "base_url":
            base_var = "{{base_url}}"
            break

    apply_changes(col, base_var)

    with open(filepath, "w") as f:
        json.dump(col, f, indent=2)

    print(f"✅ Updated: {os.path.basename(filepath)}")


if __name__ == "__main__":
    for filepath in FILES:
        if os.path.exists(filepath):
            update_collection(filepath)
        else:
            print(f"⚠️  Not found: {filepath}")

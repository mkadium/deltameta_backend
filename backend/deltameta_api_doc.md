# Deltameta API Documentation

**Base URL:** `http://localhost:8000`
**Auth:** All protected endpoints require `Authorization: Bearer <token>` header.

---

## Auth API

### 1. Register User

**POST** `/auth/register`
No authentication required.

**Request Body:**
```json
{
  "name": "John Doe",
  "display_name": "John",
  "email": "john@example.com",
  "username": "johndoe",
  "password": "Test@1234",
  "org_name": "Acme Corp"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| name | string | Yes | min 2 chars |
| display_name | string | No | shown in UI |
| email | string | Yes | valid email |
| username | string | Yes | 3–128 chars, alphanumeric + `.`, `_`, `-` |
| password | string | Yes | min 8 chars, must have uppercase, lowercase, digit |
| org_name | string | No | auto-generated from name if omitted |

**Response `201 Created`:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "org_id": "660e8400-e29b-41d4-a716-446655440001",
  "domain_id": null,
  "name": "John Doe",
  "display_name": "John",
  "description": null,
  "email": "john@example.com",
  "username": "johndoe",
  "image": null,
  "is_admin": true,
  "is_global_admin": false,
  "is_active": true,
  "is_verified": false,
  "last_login_at": null,
  "created_at": "2026-02-25T10:00:00Z",
  "updated_at": "2026-02-25T10:00:00Z",
  "teams": [],
  "roles": []
}
```

**Error Codes:**
| Code | Reason |
|---|---|
| 409 | Email already registered |
| 409 | Username already taken |
| 422 | Validation error (weak password, invalid email, etc.) |

**curl:**
```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"name":"John Doe","email":"john@example.com","username":"johndoe","password":"Test@1234"}'
```

---

### 2. Login

**POST** `/auth/login`
No authentication required.

**Request Body:**
```json
{
  "login": "john@example.com",
  "password": "Test@1234"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| login | string | Yes | Email or username |
| password | string | Yes | Plain text password |

**Response `200 OK`:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

`expires_in` is in seconds (= `jwt_expiry_minutes × 60`).

**Error Codes:**
| Code | Reason |
|---|---|
| 401 | Invalid credentials (wrong password) |
| 403 | Account inactive |
| 403 | Account locked (`locked_until` not yet passed) |

**curl:**
```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"login":"john@example.com","password":"Test@1234"}'
```

---

### 3. Logout

**POST** `/auth/logout`
**Requires:** Bearer token.

Client-side token invalidation. No server-side blacklist — client must discard the token.

**Response `200 OK`:**
```json
{
  "message": "Logged out successfully. Please discard your token."
}
```

**Error Codes:**
| Code | Reason |
|---|---|
| 401 | Missing or invalid token |
| 403 | Account inactive |

**curl:**
```bash
curl -X POST http://localhost:8000/auth/logout \
  -H "Authorization: Bearer <token>"
```

---

### 4. Refresh Token

**POST** `/auth/refresh`
**Requires:** Bearer token.

Issues a new JWT with a fresh expiry using the current valid token.

**Response `200 OK`:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

**Error Codes:**
| Code | Reason |
|---|---|
| 401 | Missing or invalid token |
| 403 | Account inactive |

**curl:**
```bash
curl -X POST http://localhost:8000/auth/refresh \
  -H "Authorization: Bearer <token>"
```

---

### 5. Get Current User Profile

**GET** `/auth/me`
**Requires:** Bearer token.

**Response `200 OK`:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "org_id": "660e8400-e29b-41d4-a716-446655440001",
  "domain_id": null,
  "name": "John Doe",
  "display_name": "John",
  "description": null,
  "email": "john@example.com",
  "username": "johndoe",
  "image": null,
  "is_admin": true,
  "is_global_admin": false,
  "is_active": true,
  "is_verified": false,
  "last_login_at": "2026-02-25T10:05:00Z",
  "created_at": "2026-02-25T10:00:00Z",
  "updated_at": "2026-02-25T10:00:00Z",
  "teams": [],
  "roles": []
}
```

**Error Codes:**
| Code | Reason |
|---|---|
| 401 | Missing, invalid, or expired token |
| 403 | Account inactive |

**curl:**
```bash
curl http://localhost:8000/auth/me \
  -H "Authorization: Bearer <token>"
```

---

### 6. Update Current User Profile

**PUT** `/auth/me`
**Requires:** Bearer token.

All fields are optional — only send what you want to change.

**Request Body:**
```json
{
  "name": "John Updated",
  "display_name": "Johnny",
  "description": "Senior Data Engineer",
  "image": "https://example.com/avatar.png"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| name | string | No | min 2 chars |
| display_name | string | No | max 255 chars |
| description | string | No | |
| image | string | No | URL, max 512 chars |

**Response `200 OK`:** Updated `UserResponse` (same shape as GET /auth/me).

**Error Codes:**
| Code | Reason |
|---|---|
| 401 | Missing or invalid token |
| 403 | Account inactive |
| 422 | Validation error |

**curl:**
```bash
curl -X PUT http://localhost:8000/auth/me \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"display_name":"Johnny","description":"Senior Data Engineer"}'
```

---

### 7. Forgot Password

**POST** `/auth/forgot-password`
No authentication required.

Initiates password reset. Always returns success to prevent user enumeration.

**Request Body:**
```json
{
  "email": "john@example.com"
}
```

**Response `200 OK`:**
```json
{
  "message": "If that email is registered, a reset link has been sent."
}
```

> **Note:** Stub implementation. Production flow: generates a reset token, stores it hashed, sends email with reset link.

**curl:**
```bash
curl -X POST http://localhost:8000/auth/forgot-password \
  -H "Content-Type: application/json" \
  -d '{"email":"john@example.com"}'
```

---

### 8. Reset Password

**POST** `/auth/reset-password`
No authentication required.

**Request Body:**
```json
{
  "reset_token": "<token-from-email>",
  "new_password": "NewPass@5678"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| reset_token | string | Yes | Token from reset email |
| new_password | string | Yes | min 8 chars, must meet strength requirements |

**Response:** Currently returns `501 Not Implemented` (stub).

> **Note:** Will validate token from DB, update hashed password, and invalidate token in production.

**curl:**
```bash
curl -X POST http://localhost:8000/auth/reset-password \
  -H "Content-Type: application/json" \
  -d '{"reset_token":"<token>","new_password":"NewPass@5678"}'
```

---

### 9. Get Auth Config

**GET** `/auth/config`
**Requires:** Bearer token + Org Admin (`is_admin: true`).

Returns the JWT and lockout configuration for the current user's organization.

**Response `200 OK`:**
```json
{
  "org_id": "660e8400-e29b-41d4-a716-446655440001",
  "jwt_expiry_minutes": 60,
  "max_failed_attempts": 5,
  "lockout_duration_minutes": 15,
  "sso_provider": "default",
  "updated_at": "2026-02-25T10:00:00Z"
}
```

**Error Codes:**
| Code | Reason |
|---|---|
| 401 | Missing or invalid token |
| 403 | Not an org admin |

**curl:**
```bash
curl http://localhost:8000/auth/config \
  -H "Authorization: Bearer <token>"
```

---

### 10. Update Auth Config

**PUT** `/auth/config`
**Requires:** Bearer token + Org Admin (`is_admin: true`).

Updates JWT token expiry and lockout policy for the organization.

**Request Body:**
```json
{
  "jwt_expiry_minutes": 120,
  "max_failed_attempts": 10,
  "lockout_duration_minutes": 30
}
```

| Field | Type | Required | Constraints |
|---|---|---|---|
| jwt_expiry_minutes | integer | No | 1 – 10080 (7 days) |
| max_failed_attempts | integer | No | 1 – 100 |
| lockout_duration_minutes | integer | No | 1 – 1440 (24h) |

**Response `200 OK`:** Updated `AuthConfigResponse` (same shape as GET /auth/config).

**Error Codes:**
| Code | Reason |
|---|---|
| 401 | Missing or invalid token |
| 403 | Not an org admin |
| 422 | Value out of allowed range |

**curl:**
```bash
curl -X PUT http://localhost:8000/auth/config \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"jwt_expiry_minutes":120,"max_failed_attempts":10,"lockout_duration_minutes":30}'
```

---

## Lockout Behavior

When a user enters wrong password repeatedly:

1. Each failure increments `failed_attempts` counter in `users` table
2. When `failed_attempts >= max_failed_attempts` → `locked_until` is set to `now + lockout_duration_minutes`
3. Login attempts while `locked_until > now` return `403 Forbidden`
4. Once `locked_until` has passed, next login attempt resets the counter and succeeds (if password is correct)

---

## Password Requirements

- Minimum 8 characters
- At least 1 uppercase letter
- At least 1 lowercase letter
- At least 1 digit
- Special characters recommended but not enforced

---

## JWT Token Structure

```json
{
  "sub": "<user_id>",
  "org_id": "<org_id>",
  "is_admin": true,
  "is_global_admin": false,
  "exp": 1772021949
}
```

---

## Domains API

Domains group teams and users by subject area (e.g. Engineering, Finance). Scoped to the current organization.

### 1. List Domains

**GET** `/domains`
**Requires:** Bearer token.

| Query Param | Type | Default | Notes |
|---|---|---|---|
| is_active | bool | null | Filter by active status |
| skip | int | 0 | Pagination offset |
| limit | int | 50 | Max results (1–200) |

**Response `200 OK`:** Array of `DomainResponse`
```json
[
  {
    "id": "...",
    "org_id": "...",
    "name": "Engineering",
    "description": "Engineering domain",
    "domain_type": "Technical",
    "owner_id": null,
    "is_active": true,
    "created_at": "2026-02-25T10:00:00Z",
    "updated_at": "2026-02-25T10:00:00Z"
  }
]
```

**curl:**
```bash
curl http://localhost:8000/domains -H "Authorization: Bearer <token>"
```

---

### 2. Create Domain

**POST** `/domains`
**Requires:** Bearer token + Org Admin.

**Request Body:**
```json
{
  "name": "Engineering",
  "description": "Engineering domain",
  "domain_type": "Technical",
  "owner_id": null
}
```

**Response `201 Created`:** `DomainResponse`

**Error Codes:** `409` name duplicate, `403` not org admin

---

### 3. Get Domain

**GET** `/domains/{domain_id}`
**Requires:** Bearer token.

**Response `200 OK`:** `DomainResponse`

**Error Codes:** `404` not found

---

### 4. Update Domain

**PUT** `/domains/{domain_id}`
**Requires:** Bearer token + Org Admin.

All fields optional. Updatable: `name`, `description`, `domain_type`, `owner_id`, `is_active`

**Response `200 OK`:** Updated `DomainResponse`

---

### 5. Delete Domain

**DELETE** `/domains/{domain_id}`
**Requires:** Bearer token + Org Admin.

**Response `200 OK`:**
```json
{ "message": "Domain 'Engineering' deleted successfully" }
```

---

## Teams API

Teams represent units within an org. `parent_team_id` is optional — hierarchy is informational.

**team_type values:** `business_unit` | `division` | `department` | `group`

### 1. List Teams

**GET** `/teams`
**Requires:** Bearer token.

| Query Param | Type | Notes |
|---|---|---|
| team_type | string | Filter by type |
| parent_team_id | UUID | Filter by parent |
| root_only | bool | Only return top-level teams (no parent) |
| is_active | bool | Filter by active status |
| skip / limit | int | Pagination |

**Response `200 OK`:** Array of `TeamResponse`

---

### 2. Create Team

**POST** `/teams`
**Requires:** Bearer token + Org Admin.

```json
{
  "name": "Platform Team",
  "display_name": "Platform",
  "email": "platform@corp.com",
  "team_type": "group",
  "description": "Core platform engineers",
  "domain_id": null,
  "public_team_view": true,
  "parent_team_id": null
}
```

**Response `201 Created`:** `TeamResponse`

**Error Codes:** `409` name duplicate, `404` parent not found

---

### 3. Get Team

**GET** `/teams/{team_id}`
**Requires:** Bearer token.

---

### 4. Update Team

**PUT** `/teams/{team_id}`
**Requires:** Bearer token + Org Admin.

All fields optional. Cannot set a team as its own parent.

---

### 5. Delete Team

**DELETE** `/teams/{team_id}`
**Requires:** Bearer token + Org Admin.

---

### 6. Get Team Hierarchy

**GET** `/teams/{team_id}/hierarchy`
**Requires:** Bearer token.

Returns a nested tree of the team and all its descendants:
```json
{
  "id": "<team_id>",
  "name": "Technology BU",
  "team_type": "business_unit",
  "parent_team_id": null,
  "children": [
    {
      "id": "<div_id>",
      "name": "Engineering Division",
      "team_type": "division",
      "children": [...]
    }
  ]
}
```

> Hierarchy is for display only. Access inheritance is a future phase.

---

### 7. List Team Members

**GET** `/teams/{team_id}/members`
**Requires:** Bearer token.

**Response `200 OK`:** Array of `UserResponse`

---

### 8. Add Member to Team

**POST** `/teams/{team_id}/members/{user_id}`
**Requires:** Bearer token + Org Admin.

**Response `200 OK`:**
```json
{ "message": "User 'John Doe' added to team 'Platform Team'" }
```

---

### 9. Remove Member from Team

**DELETE** `/teams/{team_id}/members/{user_id}`
**Requires:** Bearer token + Org Admin.

---

## Policies API

ABAC (Attribute-Based Access Control) policies. Stored in DB; enforcement is a future phase.

**Policy structure:**
- `resource`: path/identifier this rule governs (e.g. `catalog.dataset`, `admin.users`, `*`)
- `operations`: list of allowed operations (`view`, `create`, `update`, `delete`, `allow`, `deny`)
- `conditions`: list of attribute conditions `[{attr, op, value}]`

### 1. List Policies

**GET** `/policies`
**Requires:** Bearer token.

| Query Param | Type | Notes |
|---|---|---|
| resource | string | Partial match on resource path |
| skip / limit | int | Pagination |

---

### 2. Create Policy

**POST** `/policies`
**Requires:** Bearer token + Org Admin.

```json
{
  "name": "Read Catalog",
  "description": "Allow read access to catalog datasets",
  "rule_name": "allow_read_catalog",
  "resource": "catalog.dataset",
  "operations": ["view"],
  "conditions": [
    {"attr": "isAdmin", "op": "=", "value": "false"},
    {"attr": "team", "op": "=", "value": "data-analysts"}
  ]
}
```

| Condition Field | Values |
|---|---|
| attr | `isAdmin`, `team`, `organization`, `domain`, `role`, `policy` |
| op | `=`, `!=`, `in`, `not_in` |
| value | Any JSON value |

**Response `201 Created`:** `PolicyResponse`

---

### 3. Get Policy

**GET** `/policies/{policy_id}`
**Requires:** Bearer token.

---

### 4. Update Policy

**PUT** `/policies/{policy_id}`
**Requires:** Bearer token + Org Admin.

All fields optional.

---

### 5. Delete Policy

**DELETE** `/policies/{policy_id}`
**Requires:** Bearer token + Org Admin.

---

## Roles API

Roles bundle policies. System roles (`is_system_role: true`) are read-only.

### 1. List Roles

**GET** `/roles`
**Requires:** Bearer token.

**Response `200 OK`:** Array of `RoleResponse` with nested `policies`

---

### 2. Create Role

**POST** `/roles`
**Requires:** Bearer token + Org Admin.

```json
{
  "name": "Data Analyst",
  "description": "Can view catalog data",
  "policy_ids": ["<policy_uuid>"]
}
```

**Response `201 Created`:** `RoleResponse`

---

### 3. Get Role

**GET** `/roles/{role_id}`
**Requires:** Bearer token.

---

### 4. Update Role

**PUT** `/roles/{role_id}`
**Requires:** Bearer token + Org Admin. System roles return `403`.

---

### 5. Delete Role

**DELETE** `/roles/{role_id}`
**Requires:** Bearer token + Org Admin. System roles return `403`.

---

### 6. Assign Role to User

**POST** `/roles/{role_id}/assign/{user_id}`
**Requires:** Bearer token + Org Admin.

**Response `200 OK`:**
```json
{ "message": "Role 'Data Analyst' assigned to user 'John Doe'" }
```

---

### 7. Remove Role from User

**DELETE** `/roles/{role_id}/assign/{user_id}`
**Requires:** Bearer token + Org Admin.

---

## Organization Preferences API

Manage organization-level settings and view aggregate stats.

### 1. Get Org Preferences

**GET** `/org/preferences`
**Requires:** Bearer token.

**Response `200 OK`:**
```json
{
  "id": "...",
  "name": "Acme Corp",
  "slug": "acme-corp",
  "description": "Our metadata platform org",
  "contact_email": "admin@acme.com",
  "owner_id": null,
  "is_active": true,
  "is_default": true,
  "created_at": "2026-02-25T10:00:00Z",
  "updated_at": "2026-02-25T10:00:00Z"
}
```

---

### 2. Update Org Preferences

**PUT** `/org/preferences`
**Requires:** Bearer token + Org Admin.

```json
{
  "description": "Our metadata platform",
  "contact_email": "admin@acme.com",
  "owner_id": "<user_uuid>"
}
```

All fields optional. `owner_id` must reference a user in the same org.

**Response `200 OK`:** Updated `OrgPreferencesResponse`

---

### 3. Get Org Stats

**GET** `/org/preferences/stats`
**Requires:** Bearer token.

**Response `200 OK`:**
```json
{
  "total_users": 12,
  "total_teams": 5,
  "total_roles": 3,
  "total_policies": 8,
  "total_domains": 4,
  "total_subscriptions": 20
}
```

**curl:**
```bash
curl http://localhost:8000/org/preferences/stats -H "Authorization: Bearer <token>"
```

---

## Subscriptions API

Subscribe to any resource type. Scoped to org as tenant namespace.

**resource_type values:** `dataset` | `data_asset` | `data_product` | `team` | `user` | `organization` | `business_unit` | `division` | `department` | `group`

### 1. List Subscriptions

**GET** `/subscriptions`
**Requires:** Bearer token.

| Query Param | Type | Notes |
|---|---|---|
| resource_type | string | Filter by type |
| subscriber_user_id | UUID | Filter by subscriber |
| skip / limit | int | Pagination |

---

### 2. Create Subscription

**POST** `/subscriptions`
**Requires:** Bearer token.

```json
{
  "resource_type": "dataset",
  "resource_id": "<resource_uuid>",
  "subscriber_user_id": null,
  "notify_on_update": true
}
```

`subscriber_user_id` defaults to the current user if omitted.

**Response `201 Created`:** `SubscriptionResponse`

**Error Codes:** `409` already subscribed to this resource

---

### 3. Get Subscription

**GET** `/subscriptions/{subscription_id}`
**Requires:** Bearer token.

---

### 4. Delete Subscription

**DELETE** `/subscriptions/{subscription_id}`
**Requires:** Bearer token (own subscription) or Org Admin.

**Response `200 OK`:**
```json
{ "message": "Subscription deleted successfully" }
```

---

## Settings (Dynamic Hierarchy)

**Module:** `app/setting_nodes`  
**Prefix:** `/settings`  
**Auth:** All endpoints require Bearer token.

### Overview

The Settings API exposes an **N-level dynamic hierarchy** of setting cards.
The same response shape is returned at every level — the frontend simply follows `slug` values down the tree.

```
Level 1 (root)    GET /settings                        → Services | Applications | ML Models | ...
Level 2           GET /settings?parent=services        → APIs | Databases | Message Queues | ...
Level 3 (leaf)    GET /settings?parent=databases       → PostgreSQL | MySQL | MongoDB | ...
Leaf action       node.nav_url                         → /integrations/postgres/config
```

### Visibility Resolution (per node, per request)

1. `is_active = false` → **always hidden** (global off)
2. `UserSettingOverride` exists → use user's `is_enabled`
3. `OrgSettingOverride` exists → use org's `is_enabled`
4. Otherwise → inherit global `is_active` (True at this point)
5. ABAC `SettingPolicy` attached → user must have `read` op in one matching policy

### Database Tables

| Table | Purpose |
|-------|---------|
| `setting_nodes` | N-level self-referencing tree |
| `org_setting_overrides` | Per-org enable/disable + config |
| `user_setting_overrides` | Per-user enable/disable |
| `setting_policies` | ABAC policy ↔ node attachment |

---

### GET /settings

List one level of the hierarchy.

**Query Params:**
- `parent` (optional) — slug of the parent node. Omit for root.

**Response `200 OK`:**
```json
[
  {
    "id": "uuid",
    "parent_id": null,
    "slug": "services",
    "display_label": "Services",
    "description": "Connect to external services",
    "icon": "server",
    "node_type": "category",
    "nav_url": null,
    "slug_path": "services",
    "sort_order": 1,
    "is_active": true,
    "has_children": true,
    "is_enabled": true,
    "is_enabled_globally": true,
    "org_override": null,
    "user_override": null,
    "metadata": {},
    "created_at": "...",
    "updated_at": "..."
  }
]
```

---

### GET /settings/tree

Full recursive tree. Same `?parent=<slug>` filter supported.

**Response:** Same shape as above but each node has an additional `children: [...]` array.

---

### GET /settings/node/{node_id}

Single node detail with resolved visibility.

---

### POST /settings/nodes

Create a setting node. Requires org admin.

**Body:**
```json
{
  "parent_id": "uuid | null",
  "slug": "databases",
  "display_label": "Databases",
  "description": "...",
  "icon": "database",
  "node_type": "category | leaf",
  "nav_url": "/integrations/postgres/config",
  "sort_order": 0,
  "metadata": {}
}
```

> **Note:** `node_type=leaf` requires `nav_url`. `slug_path` is auto-computed if omitted.

**Response `201 Created`:** `SettingNodeResponse`

---

### PUT /settings/nodes/{node_id}

Update a node. Requires org admin. All fields optional.

---

### DELETE /settings/nodes/{node_id}

Soft-delete a node (sets `is_active=false`). Children remain but become unreachable.

---

### PUT /settings/nodes/{node_id}/org-override

Org admin sets visibility for their org.

**Body:**
```json
{ "is_enabled": false, "config": {} }
```

**Response `200 OK`:** `OrgOverrideResponse`

---

### DELETE /settings/nodes/{node_id}/org-override

Remove org override — node reverts to global default.

**Response `204 No Content`**

---

### PUT /settings/nodes/{node_id}/user-override

User controls their own visibility of a node.

**Body:** `{ "is_enabled": false }`

**Response `200 OK`:** `UserOverrideResponse`

---

### DELETE /settings/nodes/{node_id}/user-override

Remove user override.

**Response `204 No Content`**

---

### GET /settings/nodes/{node_id}/policies

List ABAC policies attached to this node.

**Response `200 OK`:** `[SettingPolicyResponse]`

---

### POST /settings/nodes/{node_id}/policies

Attach an ABAC policy to a node. Requires org admin.

**Body:** `{ "policy_id": "uuid" }`

**Response `201 Created`:** `SettingPolicyResponse`  
**Errors:** `404` policy not found, `409` already attached

---

### DELETE /settings/nodes/{node_id}/policies/{policy_id}

Detach a policy from a node. Requires org admin.

**Response `204 No Content`**


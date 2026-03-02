# Deltameta Platform — Frontend API Reference

> **Base URL:** `{{base_url}}` (e.g. `http://localhost:8000`)  
> **Auth:** All endpoints except `/auth/register`, `/auth/login`, `/auth/forgot-password`, `/auth/reset-password` require `Authorization: Bearer <token>` header.  
> **Content-Type:** `application/json` for all request bodies unless noted.

---

## Table of Contents

1. [Implementation & Integration Sequence](#1-implementation--integration-sequence)
2. [Authentication & Session](#2-authentication--session)
3. [Organizations](#3-organizations)
4. [Teams](#4-teams)
5. [Roles](#5-roles)
6. [Policies](#6-policies)
7. [ABAC — Effective Permissions](#7-abac--effective-permissions)
8. [Org & Team Role / Policy Assignments](#8-org--team-role--policy-assignments)
9. [Admin — User Management](#9-admin--user-management)
10. [Subject Areas (IAM Domains)](#10-subject-areas-iam-domains)
11. [Lookup (Dynamic Dropdowns)](#11-lookup-dynamic-dropdowns)
12. [Catalog Domains](#12-catalog-domains)
13. [Data Products](#13-data-products)
14. [Glossary & Terms](#14-glossary--terms)
15. [Classifications & Tags](#15-classifications--tags)
16. [Govern Metrics](#16-govern-metrics)
17. [Change Requests (Tasks)](#17-change-requests-tasks)
18. [Activity Feed](#18-activity-feed)
19. [Storage Config](#19-storage-config)
20. [Service Endpoints](#20-service-endpoints)
21. [Monitor (Service Redirects & Health)](#21-monitor-service-redirects--health)
22. [Subscriptions](#22-subscriptions)
23. [Settings (Dynamic Hierarchy)](#23-settings-dynamic-hierarchy)
24. [Resource Registry](#24-resource-registry)
25. [Navigation](#25-navigation)
26. [Collection Variables Reference](#26-collection-variables-reference)

---

## 1. Implementation & Integration Sequence

This section tells your frontend team **what to build first**, what depends on what, and the user journey flow.

### Phase 0 — Bootstrap (must be first)
```
/auth/register  →  /auth/login  →  /auth/me
```
Without a valid `access_token` and `org_id`, nothing else works.

### Phase 1 — Identity & Access Skeleton
Build these before any feature screens:
```
1. /auth/*                  — login, logout, refresh, profile
2. /orgs/*                  — create/list/join orgs
3. /teams/*                 — create/list/manage teams
4. /roles/* + /policies/*   — RBAC infrastructure
5. GET /auth/me/permissions — load user's permission map once after login
```
The permissions map (`{resource: [operations]}`) drives **every** show/hide decision in the UI.

### Phase 2 — Org Configuration (admin panel)
```
6. /admin/users/*           — org admin creates/manages users
7. /lookup/*                — seed dropdown options (domain_type, metric_type …)
8. /storage-config/*        — configure MinIO / S3
9. /service-endpoints/*     — configure external service URLs
10. /subject-areas/*        — create IAM subject areas / domains
```

### Phase 3 — Governance Catalog
```
11. /catalog-domains/*      — data governance domains
12. /data-products/*        — data products per domain
13. /glossaries/*           — business glossary container
14. /glossaries/{id}/terms  — glossary terms with like, export, import
15. /classifications/*      — classification schemas (PersonalData, etc.)
16. /classify/tags          — individual tags
17. /govern-metrics/*       — metric catalogue
```

### Phase 4 — Workflow & Observability
```
18. /change-requests/*      — propose & approve field changes
19. /activity-feed          — live activity log
20. /monitor/*              — health checks & deep-links to Spark/Trino/Airflow
```

### Phase 5 — Dynamic Config (superadmin)
```
21. /subscriptions/*        — feature flags / plan tiers
22. /settings/*             — dynamic hierarchical platform settings
23. /nav/*                  — navigation tree management
24. /resources/*            — resource registry (drives policy validation)
```

### Dependency Graph (simplified)
```
Register/Login
    └── org_id, user_id, access_token
            ├── /orgs  (all features are org-scoped)
            │       ├── /teams
            │       ├── /roles + /policies
            │       │       └── GET /auth/me/permissions  ← UI gating
            │       ├── /lookup  ← dropdowns for all forms
            │       ├── /subject-areas
            │       ├── /catalog-domains
            │       │       └── /data-products
            │       ├── /glossaries
            │       │       └── /terms  ← like, export, import
            │       ├── /classifications
            │       │       └── /tags
            │       ├── /govern-metrics
            │       ├── /change-requests  (references any entity)
            │       └── /activity-feed    (reads all entity events)
            └── /admin/users  (org admin only)
```

---

## 2. Authentication & Session

### User Story
> *As a new user, I want to register with my email and password so I can access the platform. As a returning user I want to log in and stay logged in using token refresh. I want to update my profile and reset my forgotten password.*

### Base path: `/auth`

---

### `POST /auth/register`
**Create a new user + default organization**

```json
// Request body
{
  "name": "John Doe",
  "display_name": "John",
  "email": "john@example.com",
  "username": "johndoe",
  "password": "Test@1234",
  "org_name": "Acme Corp",       // optional — auto-generated from name if omitted
  "org_slug": "acme-corp"        // optional — auto-slugified if omitted
}
```
```json
// 201 Response
{
  "id": "uuid",
  "name": "John Doe",
  "email": "john@example.com",
  "username": "johndoe",
  "is_admin": true,
  "is_active": true,
  "org_id": "uuid",
  "default_org_id": "uuid"
}
```
**Save:** `user_id`, `org_id` → collection variables.  
**Errors:** `409` email/username taken · `422` validation error.

---

### `POST /auth/login`
**Login and receive JWT tokens**

```json
// Request body
{
  "login": "john@example.com",   // email OR username
  "password": "Test@1234"
}
```
```json
// 200 Response
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 3600
}
```
**Save:** `token` (access_token) → collection variable.  
**Then call:** `GET /auth/me` to load user profile.  
**Errors:** `401` invalid credentials · `403` account locked.

---

### `GET /auth/me`
**Get current user profile**

```json
// 200 Response
{
  "id": "uuid",
  "name": "John Doe",
  "email": "john@example.com",
  "username": "johndoe",
  "display_name": "John",
  "is_admin": true,
  "is_active": true,
  "org_id": "uuid",
  "default_org_id": "uuid",
  "orgs": [{ "id": "uuid", "name": "Acme Corp", "slug": "acme-corp" }]
}
```

---

### `PUT /auth/me`
**Update own profile**

```json
// Request body (all fields optional)
{
  "name": "John Updated",
  "display_name": "Johnny",
  "username": "johnnyd"
}
```

---

### `POST /auth/me/switch-org`
**Switch active / default org** *(multi-org users)*

```json
// Request body
{ "org_id": "uuid" }
```
After switching, re-fetch `/auth/me` and `/auth/me/permissions` to update the UI.

---

### `GET /auth/me/orgs`
**List all orgs the user belongs to**

```json
// 200 Response — array
[{ "id": "uuid", "name": "Acme Corp", "slug": "acme-corp", "is_admin": true }]
```

---

### `POST /auth/refresh`
**Rotate access token using refresh token**

```json
// Request body
{ "refresh_token": "eyJ..." }
```
```json
// 200 Response
{ "access_token": "eyJ...", "refresh_token": "eyJ...", "expires_in": 3600 }
```
Call this automatically before the access token expires (use `expires_in`).

---

### `POST /auth/logout`
**Invalidate current session**

No body required. Returns `200 { "message": "Logged out successfully" }`.

---

### `POST /auth/forgot-password`
**Request password reset link (unauthenticated)**

```json
{ "email": "john@example.com" }
```
Returns `200` always (security — never reveals if email exists).

---

### `POST /auth/reset-password`
**Reset password using token from email link**

```json
{
  "token": "<reset-token-from-email>",
  "new_password": "NewPass@9999"
}
```

---

### `GET /auth/config`
**Get JWT / lockout config for the user's org** *(org admin)*

```json
// 200 Response
{
  "access_token_expire_minutes": 60,
  "refresh_token_expire_days": 7,
  "max_failed_attempts": 5,
  "lockout_duration_minutes": 15
}
```

---

### `PUT /auth/config`
**Update JWT / lockout config** *(org admin only)*

```json
{
  "access_token_expire_minutes": 120,
  "max_failed_attempts": 3
}
```

---

## 3. Organizations

### User Story
> *As a user, I can belong to multiple organizations. As an org admin I can create additional orgs, invite members, and configure the org's name and preferences.*

### Base path: `/orgs`

---

### `GET /orgs`
**List all orgs the current user belongs to**

```json
// 200 — array of OrgResponse
[{ "id": "uuid", "name": "Acme Corp", "slug": "acme-corp", "is_active": true }]
```

---

### `POST /orgs`
**Create a new organization**

```json
{
  "name": "My Second Company",
  "slug": "second-co",            // optional
  "description": "Side project"
}
```
```json
// 201 Response
{ "id": "uuid", "name": "My Second Company", "slug": "second-co" }
```

---

### `GET /orgs/{org_id}`
**Get org details**

---

### `PUT /orgs/{org_id}`
**Update org name / description** *(org admin)*

```json
{ "name": "Acme Corp v2", "description": "Updated description" }
```

---

### `DELETE /orgs/{org_id}`
**Soft-delete the org** *(org admin)*

Returns `200 { "message": "Organization deleted" }`.

---

### `GET /orgs/{org_id}/members`
**List all members of an org**

```json
// 200 — array of UserResponse
[{ "id": "uuid", "name": "John Doe", "email": "john@example.com", "is_admin": false }]
```

---

### `POST /orgs/{org_id}/members/{user_id}`
**Add user to org** *(org admin)*

---

### `DELETE /orgs/{org_id}/members/{user_id}`
**Remove user from org** *(org admin)*

---

### `GET /org/preferences`
**Get active org preferences (color, logo, feature flags)**

```json
// 200 Response
{
  "org_id": "uuid",
  "primary_color": "#1A73E8",
  "logo_url": "https://...",
  "domains_count": 5,
  "teams_count": 12,
  "users_count": 48
}
```

---

### `PUT /org/preferences`
**Update active org preferences** *(org admin)*

```json
{ "primary_color": "#FF5733", "logo_url": "https://cdn.example.com/logo.png" }
```

---

### `GET /org/preferences/stats`
**Get aggregate stats for the active org** *(quick dashboard counts)*

```json
// 200 Response
{ "users": 48, "teams": 12, "roles": 6, "policies": 14, "domains": 5 }
```

---

### `GET /orgs/{org_id}/stats`
**Get stats for a specific org by ID**

```json
{ "users": 48, "teams": 12, "roles": 6, "policies": 14 }
```

---

### `GET /orgs/{org_id}/teams-grouped`
**Get teams grouped by team_type** *(for org landing page)*

```json
// 200 Response
{
  "business_unit": [{ "id": "uuid", "name": "Engineering BU" }],
  "department":    [{ "id": "uuid", "name": "Backend Dept" }],
  "group":         [{ "id": "uuid", "name": "On-call Rotation" }]
}
```

---

## 4. Teams

### User Story
> *As an org admin, I can create a hierarchical team structure (business units → divisions → departments → groups). As a team member I can see my team's roster. As an admin I can nest teams under parent teams and manage memberships.*

### Base path: `/teams`

---

### `GET /teams`
**List teams — filterable**

Query params: `team_type=department`, `parent_id=<uuid>`, `is_active=true`, `skip=0`, `limit=50`

```json
// 200 — array
[{
  "id": "uuid",
  "name": "Backend",
  "team_type": "department",
  "parent_team_id": "uuid",
  "display_name": "Backend Team",
  "email": "backend@acme.com",
  "is_active": true
}]
```

---

### `POST /teams`
**Create a team**

```json
{
  "name": "Backend",
  "display_name": "Backend Team",
  "description": "Core API team",
  "team_type": "department",       // business_unit | division | department | group
  "parent_team_id": "uuid",        // optional — enables hierarchy
  "email": "backend@acme.com",
  "domain_id": "uuid"              // optional — link to subject area
}
```
```json
// 201 Response
{ "id": "uuid", "name": "Backend", "team_type": "department", "parent_team_id": "uuid" }
```
**Save:** `team_id`.

---

### `GET /teams/{team_id}`
**Get team details**

---

### `PUT /teams/{team_id}`
**Update team** *(org admin)*

---

### `DELETE /teams/{team_id}`
**Delete team** *(org admin)*

---

### `GET /teams/{team_id}/hierarchy`
**Get full sub-tree rooted at this team** *(recursive)*

```json
// 200 — nested tree
{
  "id": "uuid",
  "name": "Engineering BU",
  "children": [
    { "id": "uuid", "name": "Backend Dept", "children": [...] }
  ]
}
```

---

### `GET /teams/{team_id}/members`
**List team members**

---

### `POST /teams/{team_id}/members/{user_id}`
**Add user to team**

---

### `DELETE /teams/{team_id}/members/{user_id}`
**Remove user from team**

---

### `GET /teams/{team_id}/stats`
**Team quick stats**

```json
{ "members": 8, "sub_teams": 3 }
```

---

## 5. Roles

### User Story
> *As an org admin, I define roles (e.g. "Data Steward", "Analyst") that bundle multiple policies. I assign roles to users, teams, or the whole org. This lets me manage permissions at scale without configuring each user individually.*

### Base path: `/roles`

---

### `GET /roles`
**List all roles in the current org**

```json
// 200 — array
[{
  "id": "uuid",
  "name": "Data Steward",
  "description": "Can manage catalog domains and glossary",
  "is_system_role": false,
  "policies": [{ "id": "uuid", "name": "CatalogRead" }]
}]
```

---

### `POST /roles`
**Create a role**

```json
{
  "name": "Data Steward",
  "description": "Manages governance catalog",
  "policy_ids": ["uuid1", "uuid2"]   // attach existing policies
}
```
```json
// 201 Response
{ "id": "uuid", "name": "Data Steward", "policies": [...] }
```
**Save:** `role_id`.

---

### `GET /roles/{role_id}`
**Get role with attached policies**

---

### `PUT /roles/{role_id}`
**Update role name / description / policy set** *(system roles are protected)*

```json
{
  "name": "Senior Data Steward",
  "policy_ids": ["uuid1", "uuid3"]
}
```

---

### `DELETE /roles/{role_id}`
**Delete role** *(system roles are protected)*

---

### `POST /roles/{role_id}/assign/{user_id}`
**Assign role directly to a user**

Returns `200 { "message": "Role assigned to user 'John Doe'" }`.

---

### `DELETE /roles/{role_id}/assign/{user_id}`
**Remove role from a user**

---

## 6. Policies

### User Story
> *As an org admin, I create fine-grained policies that define what operations (read, create, update, delete) are allowed on which resources, optionally constrained by user attributes like org_id or team membership. Policies are reusable and attached to roles or directly to orgs/teams.*

### Base path: `/policies`

Valid resources come from `GET /resources/flat`.  
Valid operations per resource come from `GET /resources/{key}/operations`.

---

### `GET /policies`
**List all policies in the current org**

Query params: `resource=catalog_domain` (filter by resource)

```json
// 200 — array
[{
  "id": "uuid",
  "name": "CatalogRead",
  "rule_name": "catalog_read_all",
  "resource": "catalog_domain",
  "operations": ["read"],
  "conditions": [{ "attr": "org_id", "op": "=", "value": "uuid" }]
}]
```

---

### `POST /policies`
**Create a policy**

```json
{
  "name": "GlossaryFullAccess",
  "rule_name": "glossary_full",
  "resource": "glossary_term",
  "operations": ["read", "create", "update", "delete", "like"],
  "conditions": [
    { "attr": "org_id", "op": "=", "value": "{{org_id}}" }
  ]
}
```
```json
// 201 Response
{ "id": "uuid", "name": "GlossaryFullAccess", "resource": "glossary_term" }
```
**Save:** `policy_id`.  
**Validation:** resource key must exist in resource_definitions; operations must be valid for that resource.  
**Condition operators:** `=`, `!=`, `in`, `not_in`  
**Condition attributes:** `org_id`, `user_id`, `team_id`, `is_admin`, `is_global_admin`

---

### `GET /policies/{policy_id}`
**Get policy details**

---

### `PUT /policies/{policy_id}`
**Update policy** *(resource/operations are re-validated)*

---

### `DELETE /policies/{policy_id}`
**Delete policy**

---

## 7. ABAC — Effective Permissions

### User Story
> *After login, the frontend calls this endpoint once to receive a flat map of all resources and allowed operations for the current user. This map is used to show/hide buttons, menu items, and entire sections across the entire app.*

### `GET /auth/me/permissions`

```json
// 200 Response
{
  "user_id": "uuid",
  "org_id": "uuid",
  "permissions": {
    "catalog_domain":  ["create", "delete", "read", "update"],
    "glossary_term":   ["create", "like", "read", "unlike", "update"],
    "govern_metric":   ["read"],
    "data_product":    ["read", "create"]
  }
}
```

**How the UI uses this:**
```typescript
// After login, store globally
const perms = await fetch('/auth/me/permissions').then(r => r.json());
store.permissions = perms.permissions;

// In any component
const canCreate = store.permissions['catalog_domain']?.includes('create') ?? false;
```

**Permissions are aggregated from (in order):**
1. Policies directly assigned to the user
2. Policies via the user's roles
3. Policies via org-level roles (assigned to the org)
4. Policies directly assigned to the org
5. Policies via team-level roles (for every team the user is in)
6. Policies directly assigned to those teams

Global admins and org admins bypass all checks and can do everything.

---

## 8. Org & Team Role / Policy Assignments

### User Story
> *As an org admin, I want to assign roles and policies at the organization or team level — so all members inherit those permissions automatically without individual configuration.*

### Org-level assignments: `/orgs/{org_id}/roles` · `/orgs/{org_id}/policies`

---

### `GET /orgs/{org_id}/roles`
**List all roles assigned to the org**

---

### `POST /orgs/{org_id}/roles/{role_id}`
**Assign a role to the org** — all org members inherit its policies

Returns `201 { "message": "Role assigned to organization" }`.

---

### `DELETE /orgs/{org_id}/roles/{role_id}`
**Remove a role from the org**

---

### `GET /orgs/{org_id}/policies`
**List all policies directly assigned to the org**

---

### `POST /orgs/{org_id}/policies/{policy_id}`
**Directly assign a policy to the org**

---

### `DELETE /orgs/{org_id}/policies/{policy_id}`
**Remove a direct policy from the org**

---

### Team-level assignments: `/teams/{team_id}/roles` · `/teams/{team_id}/policies`

---

### `GET /teams/{team_id}/roles`
**List roles assigned to a team**

---

### `POST /teams/{team_id}/roles/{role_id}`
**Assign a role to a team** — all team members inherit its policies

---

### `DELETE /teams/{team_id}/roles/{role_id}`
**Remove a role from a team**

---

### `GET /teams/{team_id}/policies`
**List policies directly assigned to a team**

---

### `POST /teams/{team_id}/policies/{policy_id}`
**Directly assign a policy to a team**

---

### `DELETE /teams/{team_id}/policies/{policy_id}`
**Remove a direct policy from a team**

---

## 9. Admin — User Management

### User Story
> *As an org admin, I need to create accounts for employees who have not self-registered. I can set or reset their passwords, deactivate accounts when someone leaves, and promote users to admin.*

### Base path: `/admin`  
**Requires:** `is_admin = true` on the calling user.

---

### `GET /admin/users`
**List all users in the org**

Query params: `search=john`, `is_active=true`, `is_admin=false`, `skip=0`, `limit=50`

```json
// 200 — array
[{
  "id": "uuid",
  "name": "Alice Smith",
  "email": "alice@acme.com",
  "username": "alices",
  "is_admin": false,
  "is_active": true,
  "is_verified": true,
  "created_at": "2024-01-15T10:00:00Z"
}]
```

---

### `POST /admin/users`
**Create a user without self-registration** *(admin creates on behalf)*

```json
{
  "email": "newemployee@acme.com",
  "username": "newemployee",
  "name": "New Employee",
  "display_name": "New Emp",
  "is_admin": false,
  "send_invite": true         // future: send welcome email
}
```
```json
// 201 Response
{
  "id": "uuid",
  "email": "newemployee@acme.com",
  "is_active": true,
  "is_verified": false,
  "temporary_password": "TempXyz#123"   // returned only on creation
}
```
**Save:** `admin_created_user_id`.

---

### `GET /admin/users/{user_id}`
**Get user details** *(admin view — includes is_admin, is_verified)*

---

### `PUT /admin/users/{user_id}`
**Update user details**

```json
{
  "name": "Updated Name",
  "display_name": "Updated",
  "is_admin": true
}
```

---

### `POST /admin/users/{user_id}/reset-password`
**Reset user's password**

```json
// Option A — generate a temporary password (body can be empty {})
{}

// Option B — set a specific password
{ "new_password": "NewSecurePass123!" }
```
```json
// 200 Response
{
  "message": "Password reset successfully",
  "temporary_password": "TempXyz#123"   // only if auto-generated
}
```

---

### `DELETE /admin/users/{user_id}`
**Deactivate user** *(soft delete — sets is_active=false)*

Returns `204 No Content`.

---

## 10. Subject Areas (IAM Domains)

### User Story
> *As an org admin, I define subject areas (e.g. "Finance", "Operations") that group teams and users thematically. These are IAM-level organizational containers — different from catalog governance domains.*

### Base path: `/subject-areas`

---

### `GET /subject-areas`
**List all subject areas for the org**

Query params: `skip=0`, `limit=50`, `search=Finance`

```json
// 200 — array
[{
  "id": "uuid",
  "org_id": "uuid",
  "name": "Finance",
  "display_name": "Finance Domain",
  "description": "All financial data",
  "domain_type": "source_aligned",
  "is_active": true,
  "owner_id": "uuid"
}]
```

---

### `POST /subject-areas`
**Create a subject area**

```json
{
  "name": "Finance",
  "display_name": "Finance Domain",
  "description": "All finance data",
  "domain_type": "source_aligned",   // from GET /lookup/domain_type
  "owner_id": "uuid"                  // optional
}
```
```json
// 201 Response
{ "id": "uuid", "name": "Finance", "domain_type": "source_aligned" }
```
**Save:** `subject_area_id`.

---

### `GET /subject-areas/{subject_area_id}`
**Get subject area details**

---

### `PUT /subject-areas/{subject_area_id}`
**Update subject area**

```json
{ "display_name": "Updated Finance Domain", "description": "Updated desc" }
```

---

### `DELETE /subject-areas/{subject_area_id}`
**Delete subject area**

---

## 11. Lookup (Dynamic Dropdowns)

### User Story
> *As a frontend developer, I need configurable dropdown options for forms — domain types, metric types, granularity, etc. The platform ships with system-level defaults and allows admins to add custom options per org. The frontend uses these to populate `<select>` inputs without hardcoding values.*

### Base path: `/lookup`

**Pre-seeded system slugs:**

| Slug | Used In |
|------|---------|
| `domain_type` | Subject Areas, Catalog Domains |
| `metric_type` | Govern Metrics |
| `metric_granularity` | Govern Metrics |
| `measurement_unit` | Govern Metrics |
| `metric_language` | Govern Metrics |

---

### `GET /lookup`
**List all lookup categories (system + org-specific)**

```json
// 200 — array
[{
  "id": "uuid",
  "name": "Domain Type",
  "slug": "domain_type",
  "description": "Classification type for domains",
  "is_system": true,
  "values": [
    { "id": "uuid", "label": "Source Aligned", "value": "source_aligned", "sort_order": 1 },
    { "id": "uuid", "label": "Consumer Aligned", "value": "consumer_aligned", "sort_order": 2 },
    { "id": "uuid", "label": "Aggregate", "value": "aggregate", "sort_order": 3 }
  ]
}]
```

---

### `GET /lookup/{slug}`
**Get a single category with its values by slug** *(use in forms)*

```json
// GET /lookup/metric_type
{
  "id": "uuid",
  "slug": "metric_type",
  "name": "Metric Type",
  "values": [
    { "label": "Sum", "value": "sum" },
    { "label": "Count", "value": "count" },
    { "label": "Average", "value": "avg" },
    { "label": "Ratio", "value": "ratio" },
    { "label": "Gauge", "value": "gauge" }
  ]
}
```

---

### `POST /lookup`
**Create a custom lookup category** *(org admin)*

```json
{
  "name": "Data Classification Level",
  "slug": "classification_level",
  "description": "Security classification levels for data assets"
}
```
```json
// 201 Response
{ "id": "uuid", "slug": "classification_level", "values": [] }
```
**Save:** `lookup_category_id`.

---

### `POST /lookup/{category_id}/values`
**Add a value to a lookup category** *(org admin)*

```json
{
  "label": "Top Secret",
  "value": "top_secret",
  "sort_order": 1
}
```
```json
// 201 Response
{ "id": "uuid", "label": "Top Secret", "value": "top_secret" }
```
**Save:** `lookup_value_id`.  
**UI Pattern:** Show an inline "Add" button next to each dropdown in admin settings.

---

### `DELETE /lookup/{category_id}/values/{value_id}`
**Remove a lookup value** *(org admin)*

---

## 12. Catalog Domains

### User Story
> *As a data steward, I create governance domains (e.g. "Marketing Analytics", "Customer 360") to organize data products. Each domain has designated owners and subject-matter experts. The domain type comes from the Lookup API.*

### Base path: `/catalog-domains`

---

### `GET /catalog-domains`
**List all governance catalog domains**

Query params: `domain_type=consumer_aligned`, `is_active=true`, `search=Marketing`, `skip=0`, `limit=50`

```json
// 200 — array
[{
  "id": "uuid",
  "org_id": "uuid",
  "name": "Marketing",
  "display_name": "Marketing Analytics Domain",
  "description": "All marketing data assets",
  "domain_type": "consumer_aligned",
  "color": "#FF5733",
  "icon": "",
  "is_active": true,
  "owners": [{ "id": "uuid", "name": "Alice Smith" }],
  "experts": [{ "id": "uuid", "name": "Bob Jones" }]
}]
```

---

### `POST /catalog-domains`
**Create a catalog domain**

```json
{
  "name": "Marketing",
  "display_name": "Marketing Analytics Domain",
  "description": "All marketing data assets",
  "domain_type": "consumer_aligned",   // from GET /lookup/domain_type
  "color": "#FF5733",
  "icon": "",
  "owner_ids": ["uuid1"],              // user IDs
  "expert_ids": ["uuid2"]
}
```
```json
// 201 Response
{ "id": "uuid", "name": "Marketing", "owners": [...], "experts": [...] }
```
**Save:** `catalog_domain_id`.

---

### `GET /catalog-domains/{domain_id}`
**Get catalog domain with owners and experts**

---

### `PUT /catalog-domains/{domain_id}`
**Update catalog domain**

```json
{
  "display_name": "Updated Marketing Domain",
  "color": "#00CC00",
  "owner_ids": ["uuid1", "uuid3"],
  "expert_ids": []
}
```

---

### `DELETE /catalog-domains/{domain_id}`
**Delete catalog domain**

---

## 13. Data Products

### User Story
> *As a data product owner, I publish data products under a catalog domain. A data product has a lifecycle (draft → published → deprecated) and a version string. Other teams discover and consume data products through the catalog.*

### Base path: `/data-products`

---

### `GET /data-products`
**List data products**

Query params: `domain_id=<uuid>`, `status=draft|published|deprecated`, `search=Sales`, `skip=0`, `limit=50`

```json
// 200 — array
[{
  "id": "uuid",
  "org_id": "uuid",
  "domain_id": "uuid",
  "name": "Daily Sales Report",
  "display_name": "Sales Report",
  "description": "Aggregated daily sales",
  "status": "draft",
  "version": "0.1",
  "owners": [{ "id": "uuid", "name": "Alice" }],
  "experts": []
}]
```

---

### `POST /data-products`
**Create a data product**

```json
{
  "name": "Daily Sales Report",
  "display_name": "Sales Report",
  "description": "Aggregated daily sales data",
  "domain_id": "{{catalog_domain_id}}",
  "owner_ids": ["uuid1"],
  "expert_ids": []
}
```
```json
// 201 Response — defaults: status=draft, version=0.1
{ "id": "uuid", "status": "draft", "version": "0.1", "domain_id": "uuid" }
```
**Save:** `data_product_id`.

---

### `GET /data-products/{product_id}`
**Get data product details**

---

### `PUT /data-products/{product_id}`
**Update data product — lifecycle management**

```json
{
  "status": "published",
  "version": "1.0",
  "description": "Production-ready aggregated daily sales"
}
```

---

### `DELETE /data-products/{product_id}`
**Delete data product**

---

## 14. Glossary & Terms

### User Story
> *As a data steward, I create a business glossary to define standard business terminology (Revenue, Churn Rate, LTV). Each term can have synonyms, owners, reviewers, and cross-references. Business users can like terms to signal importance. The glossary can be exported to CSV for sharing with the wider organization and imported back after offline edits.*

### Base path: `/glossaries`

---

### `GET /glossaries`
**List all glossaries for the org**

```json
// 200 — array
[{
  "id": "uuid",
  "name": "Business Glossary",
  "display_name": "BizGloss",
  "is_active": true
}]
```

---

### `POST /glossaries`
**Create a glossary container**

```json
{
  "name": "Business Glossary",
  "display_name": "BizGloss",
  "description": "Corporate business terminology"
}
```
**Save:** `glossary_id`.

---

### `GET /glossaries/{glossary_id}`
**Get glossary details**

---

### `PUT /glossaries/{glossary_id}`
**Rename or update the glossary**

---

### `DELETE /glossaries/{glossary_id}`
**Delete glossary and all its terms**

---

### `GET /glossaries/{glossary_id}/terms`
**List all terms in a glossary**

Query params: `search=revenue`, `skip=0`, `limit=50`

```json
// 200 — array
[{
  "id": "uuid",
  "glossary_id": "uuid",
  "name": "Revenue",
  "display_name": "Total Revenue",
  "description": "Sum of all income streams",
  "synonyms": ["income", "earnings", "sales"],
  "mutually_exclusive": false,
  "likes_count": 12,
  "color": "#00FF00",
  "references_data": [{ "url": "https://wiki/revenue", "name": "Wiki" }],
  "owners": [{ "id": "uuid", "name": "Alice" }],
  "reviewers": [],
  "related_terms": []
}]
```

---

### `POST /glossaries/{glossary_id}/terms`
**Create a term**

```json
{
  "name": "Revenue",
  "display_name": "Total Revenue",
  "description": "Sum of all income streams",
  "synonyms": ["income", "earnings", "sales"],
  "icon_url": "https://example.com/icon.png",
  "color": "#00FF00",
  "mutually_exclusive": false,
  "references_data": [
    { "url": "https://wiki.example.com/revenue", "name": "Wiki Reference" }
  ],
  "owner_ids": ["uuid1"],
  "reviewer_ids": [],
  "related_term_ids": []       // IDs of other GlossaryTerms
}
```
**Save:** `glossary_term_id`.

---

### `GET /glossaries/{glossary_id}/terms/{term_id}`
**Get term details including owners, reviewers, related terms**

---

### `PUT /glossaries/{glossary_id}/terms/{term_id}`
**Update term**

```json
{
  "description": "Updated: Sum of all revenue streams including subscriptions",
  "synonyms": ["income", "earnings", "sales", "turnover"],
  "related_term_ids": ["uuid2", "uuid3"]
}
```

---

### `POST /glossaries/{glossary_id}/terms/{term_id}/like`
**Like a term** *(current user adds a like)*

```json
// 200 Response
{ "id": "uuid", "name": "Revenue", "likes_count": 13 }
```
Idempotent — liking twice has no extra effect.

---

### `DELETE /glossaries/{glossary_id}/terms/{term_id}/like`
**Unlike a term** *(current user removes their like)*

```json
// 200 Response
{ "id": "uuid", "name": "Revenue", "likes_count": 12 }
```

---

### `GET /glossaries/{glossary_id}/export`
**Export all terms to CSV** *(download)*

Response headers: `Content-Type: text/csv`, `Content-Disposition: attachment; filename="glossary.csv"`

Columns: `name, display_name, description, synonyms, color, icon_url, mutually_exclusive`

```typescript
// Frontend usage
const resp = await fetch(`/glossaries/${glossaryId}/export`, { headers: authHeaders });
const blob = await resp.blob();
const url = URL.createObjectURL(blob);
const a = document.createElement('a'); a.href = url; a.download = 'glossary.csv'; a.click();
```

---

### `POST /glossaries/{glossary_id}/import`
**Import terms from CSV** *(multipart/form-data)*

```
Content-Type: multipart/form-data
field: file (CSV file)
```

CSV columns: `name, display_name, description, synonyms (comma-separated), color, icon_url, mutually_exclusive`

```json
// 201 Response
{ "imported": 25, "skipped": 2, "errors": [] }
```

---

### `DELETE /glossaries/{glossary_id}/terms/{term_id}`
**Delete a term**

---

## 15. Classifications & Tags

### User Story
> *As a data governance officer, I create classification schemas (e.g. "Personal Data", "Sensitivity Level") with mutually-exclusive or multi-select tags. These tags are later applied to data product columns, datasets, or glossary terms to mark their sensitivity.*

### Base path: `/classifications`

**Pre-seeded by migration:** `PersonalData` classification with `Personal` and `SpecialCategory` tags.

---

### `GET /classifications`
**List all classifications for the org**

```json
// 200 — array
[{
  "id": "uuid",
  "name": "PersonalData",
  "display_name": "Personal Data",
  "description": "PII sensitivity tags",
  "mutually_exclusive": true,
  "owners": [],
  "tags": [
    { "id": "uuid", "name": "Personal", "color": "#FF6600" },
    { "id": "uuid", "name": "SpecialCategory", "color": "#FF0000" }
  ]
}]
```

---

### `POST /classifications`
**Create a classification**

```json
{
  "name": "SensitivityLevel",
  "display_name": "Sensitivity Level",
  "description": "Internal data sensitivity",
  "mutually_exclusive": true,   // only one tag can be applied at a time
  "owner_ids": [],
  "domain_ids": []               // catalog domain references
}
```
**Save:** `classification_id`.

---

### `GET /classifications/{classification_id}`
**Get classification with all tags**

---

### `PUT /classifications/{classification_id}`
**Update classification**

---

### `DELETE /classifications/{classification_id}`
**Delete classification and all its tags**

---

### `GET /classifications/{classification_id}/tags`
**List tags in a classification**

```json
// 200 — array
[{
  "id": "uuid",
  "name": "Personal",
  "display_name": "Personal Data",
  "description": "Name, email, phone",
  "color": "#FF6600",
  "icon_url": "",
  "owners": [],
  "domain_refs": []
}]
```

---

### `POST /classifications/{classification_id}/tags`
**Create a tag**

```json
{
  "name": "Confidential",
  "display_name": "Confidential",
  "description": "Internal-only — not for external sharing",
  "color": "#CC3300",
  "icon_url": "",
  "owner_ids": [],
  "domain_ids": []
}
```
**Save:** `classification_tag_id`.

---

### `GET /classifications/{classification_id}/tags/{tag_id}`
**Get tag details**

---

### `PUT /classifications/{classification_id}/tags/{tag_id}`
**Update tag**

---

### `DELETE /classifications/{classification_id}/tags/{tag_id}`
**Delete tag**

---

## 16. Govern Metrics

### User Story
> *As a data analyst or steward, I register standardized business metrics (Total Revenue, Monthly Active Users, Churn Rate) with their SQL/Python definitions. This creates a single source of truth for metric calculations across teams.*

### Base path: `/govern-metrics`

---

### `GET /govern-metrics`
**List metrics**

Query params: `metric_type=sum`, `search=Revenue`, `skip=0`, `limit=50`

```json
// 200 — array
[{
  "id": "uuid",
  "name": "Total Revenue",
  "display_name": "Revenue",
  "description": "Sum of all revenue streams",
  "granularity": "day",           // from GET /lookup/metric_granularity
  "metric_type": "sum",           // from GET /lookup/metric_type
  "language": "sql",
  "measurement_unit": "dollars",  // from GET /lookup/measurement_unit
  "code": "SELECT SUM(amount) FROM sales WHERE date = :date",
  "is_active": true,
  "owners": [{ "id": "uuid", "name": "Alice" }]
}]
```

---

### `POST /govern-metrics`
**Create a metric**

```json
{
  "name": "Total Revenue",
  "display_name": "Revenue",
  "description": "Sum of all revenue streams across channels",
  "granularity": "day",
  "metric_type": "sum",
  "language": "sql",
  "measurement_unit": "dollars",
  "code": "SELECT SUM(amount) FROM sales WHERE date = :date",
  "owner_ids": ["uuid1"]
}
```
**Save:** `govern_metric_id`.

---

### `GET /govern-metrics/{metric_id}`
**Get metric details**

---

### `PUT /govern-metrics/{metric_id}`
**Update metric definition**

```json
{
  "granularity": "month",
  "code": "SELECT SUM(amount) FROM sales WHERE DATE_TRUNC('month', date) = :month"
}
```

---

### `DELETE /govern-metrics/{metric_id}`
**Delete metric**

---

## 17. Change Requests (Tasks)

### User Story
> *As a data user, I see an incorrect description on a Glossary Term. Instead of changing it directly, I submit a change request describing what should be updated. As a data steward, I review open change requests and approve or reject them. This creates an auditable, collaborative workflow for catalog quality.*

### Base path: `/change-requests`

**Valid `entity_type` values:** `catalog_domain`, `data_product`, `glossary_term`, `classification_tag`, `govern_metric`

---

### `GET /change-requests`
**List change requests with filters**

Query params: `entity_type=glossary_term`, `entity_id=<uuid>`, `status=open|approved|rejected|withdrawn`, `skip=0`, `limit=50`

```json
// 200 — array
[{
  "id": "uuid",
  "entity_type": "glossary_term",
  "entity_id": "uuid",
  "field_name": "description",
  "current_value": "Old description",
  "new_value": "Updated description",
  "title": "Update Revenue term description",
  "description": "### Reason\nThe current description is incomplete",
  "status": "open",
  "created_by": { "id": "uuid", "name": "Bob Jones" },
  "assignees": [],
  "created_at": "2024-01-15T10:00:00Z"
}]
```

---

### `POST /change-requests`
**Submit a change request**

```json
{
  "entity_type": "glossary_term",
  "entity_id": "{{glossary_term_id}}",
  "field_name": "description",
  "current_value": "Sum of all income streams",
  "new_value": "Sum of all revenue streams including recurring subscriptions and one-time payments",
  "title": "Update Revenue term description",
  "description": "### Current\n...\n\n### Proposed\n...\n\n### Reason\nMore precise definition needed",
  "assignee_ids": ["uuid1"]    // optional reviewer user IDs
}
```
```json
// 201 Response
{ "id": "uuid", "status": "open", "entity_type": "glossary_term" }
```
**Save:** `change_request_id`.

---

### `GET /change-requests/{cr_id}`
**Get change request details**

---

### `PUT /change-requests/{cr_id}`
**Update change request** *(description / assignees)*

```json
{ "description": "Updated rationale", "assignee_ids": ["uuid2"] }
```

---

### `POST /change-requests/{cr_id}/approve`
**Approve a change request** *(steward/admin)*

```json
// 200 Response
{ "id": "uuid", "status": "approved" }
```

---

### `POST /change-requests/{cr_id}/reject`
**Reject a change request**

```json
// 200 Response
{ "id": "uuid", "status": "rejected" }
```

---

### `POST /change-requests/{cr_id}/withdraw`
**Withdraw a change request** *(submitter retracts it)*

```json
// 200 Response
{ "id": "uuid", "status": "withdrawn" }
```

---

### `DELETE /change-requests/{cr_id}`
**Delete a change request**

---

## 18. Activity Feed

### User Story
> *As a data governance user, I can see a platform-wide activity log showing who created or updated which catalog entities and when. This acts as an audit trail and a live feed on dashboard home pages.*

### Base path: `/activity-feed`

---

### `GET /activity-feed`
**List activity feed entries (read-only)**

Query params: `entity_type=catalog_domain`, `entity_id=<uuid>`, `actor_id=<uuid>`, `skip=0`, `limit=50`

```json
// 200 — array (newest first)
[{
  "id": "uuid",
  "org_id": "uuid",
  "actor_id": "uuid",
  "entity_type": "catalog_domain",
  "entity_id": "uuid",
  "action": "created",
  "details": { "name": "Marketing" },
  "created_at": "2024-01-15T10:00:00Z"
}]
```

**Common `entity_type` + `action` values:**

| entity_type | actions |
|-------------|---------|
| `catalog_domain` | `created`, `updated` |
| `data_product` | `created`, `updated` |
| `glossary_term` | `created`, `updated`, `liked` |
| `classification` | `created` |
| `govern_metric` | `created`, `updated` |

**Frontend use-case patterns:**

```typescript
// Dashboard recent activity (org-wide, last 20)
GET /activity-feed?limit=20

// Entity-specific timeline (e.g. glossary term detail page)
GET /activity-feed?entity_type=glossary_term&entity_id=${termId}

// User's own actions (my activity)
GET /activity-feed?actor_id=${userId}&limit=50
```

---

## 19. Storage Config

### User Story
> *As an org admin setting up the platform, I configure where data files are stored — either on-premise MinIO or cloud S3. Only one config can be active at a time. When switching providers, I activate the new config which automatically deactivates the previous one.*

### Base path: `/storage-config`  
**Requires:** org admin.

---

### `GET /storage-config`
**List all storage configurations for the org**

```json
// 200 — array
[{
  "id": "uuid",
  "provider": "minio",
  "endpoint": "http://minio:9000",
  "bucket": "deltameta-data",
  "access_key": "minioadmin",
  "region": "",
  "is_active": true,
  "extra": {},
  "created_at": "2024-01-10T08:00:00Z"
}]
```
> **Note:** `secret_key` is never returned.

---

### `POST /storage-config`
**Add a new storage configuration**

```json
// MinIO (on-premise)
{
  "provider": "minio",
  "endpoint": "http://minio:9000",
  "bucket": "deltameta-data",
  "access_key": "minioadmin",
  "secret_key": "minioadmin123",
  "region": "",
  "extra": {}
}

// AWS S3
{
  "provider": "s3",
  "bucket": "my-s3-bucket",
  "region": "us-east-1",
  "access_key": "AKIAEXAMPLE123",
  "secret_key": "secretaccesskey",
  "extra": {}
}
```
**Save:** `storage_config_id`.

---

### `GET /storage-config/{config_id}`
**Get config details** (secret_key excluded)

---

### `PUT /storage-config/{config_id}`
**Update config** *(e.g. rotate keys or change bucket)*

```json
{ "bucket": "new-bucket", "access_key": "newkey", "secret_key": "newsecret" }
```

---

### `POST /storage-config/{config_id}/activate`
**Make this config the active one** *(deactivates all others)*

```json
// 200 Response
{ "id": "uuid", "provider": "minio", "is_active": true }
```

---

### `DELETE /storage-config/{config_id}`
**Remove a storage config** *(cannot delete active config)*

---

## 20. Service Endpoints

### User Story
> *As an org admin, I register the base URLs of all external services (Spark, Trino, Airflow, etc.) so the platform Monitor can generate deep-link redirect URLs for operations teams. This avoids hardcoding service URLs and supports different environments (dev/staging/prod).*

### Base path: `/service-endpoints`  
**Requires:** org admin.

**Valid `service_name` values:**

| service_name | Service |
|-------------|---------|
| `spark_ui` | Apache Spark Web UI |
| `spark_history` | Spark History Server |
| `trino_ui` | Trino/Presto Web UI |
| `airflow_ui` | Apache Airflow Web UI |
| `rabbitmq_ui` | RabbitMQ Management Console |
| `celery_flower` | Celery Flower Task Monitor |
| `jupyter` | JupyterLab |
| `minio_console` | MinIO Console |

---

### `GET /service-endpoints`
**List all configured service endpoints**

```json
// 200 — array
[{
  "id": "uuid",
  "service_name": "spark_ui",
  "base_url": "http://spark-master:8080",
  "is_active": true,
  "extra": {}
}]
```

---

### `POST /service-endpoints`
**Register a service endpoint**

```json
{ "service_name": "spark_ui", "base_url": "http://spark-master:8080", "extra": {} }
```
**Save:** `service_endpoint_id`.

---

### `GET /service-endpoints/{endpoint_id}`
**Get endpoint details**

---

### `PUT /service-endpoints/{endpoint_id}`
**Update endpoint URL** *(e.g. after deployment change)*

```json
{ "base_url": "http://spark-master-prod:8080" }
```

---

### `DELETE /service-endpoints/{endpoint_id}`
**Remove an endpoint**

---

## 21. Monitor (Service Redirects & Health)

### User Story
> *As an engineer or data analyst, I want to jump directly to the Spark job UI, Airflow DAG run, Trino query, or RabbitMQ queue from the Deltameta portal — without bookmarking each tool separately. The Monitor API returns a redirect_url that the frontend opens in a new tab.*

### Base path: `/monitor`

> **Prerequisite:** Service URLs must first be registered via `POST /service-endpoints`.

---

### `GET /monitor`
**List all configured services with their status**

```json
// 200 — array
[{
  "service_name": "spark_ui",
  "base_url": "http://spark-master:8080",
  "is_active": true
}]
```

---

### `GET /monitor/health`
**Ping all active service endpoints and return health status**

```json
// 200 Response
{
  "checked_at": "2024-01-15T10:00:00Z",
  "services": [
    { "service_name": "spark_ui",  "url": "http://spark-master:8080", "status": "ok",   "latency_ms": 45 },
    { "service_name": "trino_ui",  "url": "http://trino:8080",        "status": "ok",   "latency_ms": 120 },
    { "service_name": "airflow_ui","url": "http://airflow:8080",       "status": "error","latency_ms": null }
  ]
}
```

---

### `GET /monitor/spark`
**Get Spark UI redirect URL**

Query params: `app_id=application_123456_0001` (specific application), `job_id=42` (specific job)

```json
// 200 Response
{ "redirect_url": "http://spark-master:8080/history/application_123456_0001" }
```

```typescript
// Frontend usage
const { redirect_url } = await fetch('/monitor/spark?app_id=application_123456_0001').then(r => r.json());
window.open(redirect_url, '_blank');
```

---

### `GET /monitor/spark/history`
**Get Spark History Server redirect URL**

Query params: `app_id=<string>` (optional)

---

### `GET /monitor/trino`
**Get Trino UI redirect URL**

Query params: `query_id=20240101_123456_00001_abcde` (specific query)

---

### `GET /monitor/airflow`
**Get Airflow UI redirect URL**

Query params: `dag_id=my_dag`, `run_id=manual__2024-01-01T00:00:00` (specific DAG run)

---

### `GET /monitor/rabbitmq`
**Get RabbitMQ Management Console redirect URL**

Query params: `queue=deltameta.jobs` (specific queue)

---

### `GET /monitor/celery`
**Get Celery Flower redirect URL**

Query params: `task_id=abc-123-def-456` (specific task)

---

### `GET /monitor/jupyter`
**Get JupyterLab redirect URL**

---

### `GET /monitor/minio`
**Get MinIO Console redirect URL**

---

## 22. Subscriptions

### User Story
> *As a platform admin, I manage which feature tiers or plan add-ons are active for each org. Subscriptions control feature gating at the organization level.*

### Base path: `/subscriptions`

---

### `GET /subscriptions`
**List subscriptions for the current org**

```json
// 200 — array
[{
  "id": "uuid",
  "plan": "enterprise",
  "status": "active",
  "starts_at": "2024-01-01T00:00:00Z",
  "ends_at": "2025-01-01T00:00:00Z"
}]
```

---

### `POST /subscriptions`
**Create a subscription** *(org admin)*

```json
{
  "plan": "enterprise",
  "starts_at": "2024-01-01T00:00:00Z",
  "ends_at": "2025-01-01T00:00:00Z"
}
```

---

### `GET /subscriptions/{subscription_id}`
**Get subscription details**

---

### `DELETE /subscriptions/{subscription_id}`
**Cancel/remove a subscription**

---

## 23. Settings (Dynamic Hierarchy)

### User Story
> *As a platform superadmin, I manage a dynamic tree of platform-wide configuration settings. Each node in the tree can be a category or a leaf setting. Orgs can override leaf values for their context. Individual users can further override applicable settings for their personal experience.*

### Base path: `/settings`

---

### `GET /settings`
**List all setting nodes (flat)**

---

### `GET /settings/tree`
**Get the full settings tree (nested)**

```json
// 200 — nested tree
[{
  "id": "uuid",
  "key": "platform",
  "label": "Platform",
  "node_type": "category",
  "children": [{
    "id": "uuid",
    "key": "platform.ui",
    "label": "UI Settings",
    "node_type": "category",
    "children": [{
      "id": "uuid",
      "key": "platform.ui.theme",
      "label": "Default Theme",
      "node_type": "leaf",
      "value_type": "string",
      "default_value": "light"
    }]
  }]
}]
```

---

### `GET /settings/node/{node_id}`
**Get a single node with its effective value** *(considers org + user overrides)*

---

### `POST /settings/nodes`
**Create a new setting node** *(superadmin)*

---

### `PUT /settings/nodes/{node_id}`
**Update a setting node definition** *(superadmin)*

---

### `DELETE /settings/nodes/{node_id}`
**Soft-delete a setting node** *(superadmin)*

---

### `PUT /settings/nodes/{node_id}/org-override`
**Set org-level override for a setting** *(org admin)*

```json
{ "value": "dark" }
```

---

### `DELETE /settings/nodes/{node_id}/org-override`
**Remove org-level override** *(restores to platform default)*

---

### `PUT /settings/nodes/{node_id}/user-override`
**Set personal user override for a setting**

```json
{ "value": "compact" }
```

---

### `DELETE /settings/nodes/{node_id}/user-override`
**Remove personal user override**

---

### `GET /settings/nodes/{node_id}/policies`
**List access policies attached to a setting node**

---

### `POST /settings/nodes/{node_id}/policies/{policy_id}`
**Attach a policy to a setting node** *(controls who can read/write it)*

---

### `DELETE /settings/nodes/{node_id}/policies/{policy_id}`
**Remove a policy from a setting node**

---

## 24. Resource Registry

### User Story
> *As a frontend developer or org admin, I need to know which resources exist on the platform and what operations are valid for each. This powers the policy creation form — the resource dropdown and operation checkboxes. The registry is seeded from static definitions and extended by dynamic setting nodes.*

### Base path: `/resources`

---

### `GET /resources`
**List all resource groups with their resources** *(grouped view)*

```json
// 200 — array of groups
[{
  "slug": "governance",
  "name": "Governance",
  "resources": [
    {
      "key": "catalog_domain",
      "label": "Catalog Domain",
      "operations": ["read", "create", "update", "delete"],
      "is_static": true,
      "is_active": true
    },
    {
      "key": "glossary_term",
      "label": "Glossary Term",
      "operations": ["read", "create", "update", "delete", "like", "unlike"],
      "is_static": true
    }
  ]
}]
```

---

### `GET /resources/flat`
**Flat list of all active resource definitions**

Use this to populate the **resource** dropdown in the Create Policy form.

```json
// 200 — array
[
  { "key": "user",            "label": "User",            "operations": ["read","create","update","delete"] },
  { "key": "catalog_domain",  "label": "Catalog Domain",  "operations": ["read","create","update","delete"] },
  { "key": "glossary_term",   "label": "Glossary Term",   "operations": ["read","create","update","delete","like","unlike"] },
  ...
]
```

---

### `GET /resources/{key}/operations`
**Get valid operations for a specific resource key**

```json
// GET /resources/glossary_term/operations
{
  "key": "glossary_term",
  "label": "Glossary Term",
  "operations": ["read", "create", "update", "delete", "like", "unlike"]
}
```

---

### `POST /resources/sync`
**Force re-sync of static registry + leaf nodes into DB** *(superadmin)*

```json
// 200 Response
{ "static_synced": 28, "leaf_synced": 15, "total": 43 }
```

---

## 25. Navigation

### User Story
> *As a platform superadmin, I manage the navigation tree that drives the sidebar/navbar in the frontend. Each node can represent a category or a leaf link. Orgs and users can override visibility and ordering. Policies control which nav items are visible based on the user's roles.*

### Base path: `/nav`

---

### `GET /nav`
**Get flat list of all nav nodes (user's effective view)**

---

### `GET /nav/tree`
**Get full nav tree (nested, with visibility resolved)**

```json
// 200 — nested tree
[{
  "id": "uuid",
  "key": "govern",
  "label": "Govern",
  "icon": "database",
  "sort_order": 2,
  "node_type": "category",
  "children": [
    { "id": "uuid", "key": "govern.glossary",  "label": "Glossary",  "route": "/govern/glossary", "node_type": "leaf" },
    { "id": "uuid", "key": "govern.catalog",   "label": "Catalog",   "route": "/govern/catalog",  "node_type": "leaf" },
    { "id": "uuid", "key": "govern.metrics",   "label": "Metrics",   "route": "/govern/metrics",  "node_type": "leaf" }
  ]
}]
```

---

### `GET /nav/nodes`
**List all nav nodes (admin view — all nodes, not visibility-filtered)**

---

### `GET /nav/node/{node_id}`
**Get a single nav node with effective overrides applied**

---

### `POST /nav/nodes`
**Create a nav node** *(superadmin)*

```json
{
  "key": "govern.lineage",
  "label": "Data Lineage",
  "icon": "git-branch",
  "route": "/govern/lineage",
  "node_type": "leaf",
  "parent_id": "uuid",
  "sort_order": 5
}
```

---

### `PUT /nav/nodes/{node_id}`
**Update a nav node** *(superadmin)*

---

### `DELETE /nav/nodes/{node_id}`
**Soft-delete a nav node** *(superadmin)*

---

### `PUT /nav/nodes/{node_id}/org-override`
**Customize nav for an org** *(org admin — rename, reorder, hide)*

```json
{ "label": "Our Glossary", "sort_order": 1, "is_visible": true }
```

---

### `DELETE /nav/nodes/{node_id}/org-override`
**Remove org nav customization**

---

### `PUT /nav/nodes/{node_id}/user-override`
**Personal nav customization** *(user-level)*

```json
{ "is_pinned": true, "sort_order": 0 }
```

---

### `DELETE /nav/nodes/{node_id}/user-override`
**Remove personal nav customization**

---

### `GET /nav/nodes/{node_id}/policies`
**List policies controlling visibility of this nav node**

---

### `POST /nav/nodes/{node_id}/policies/{policy_id}`
**Attach a policy to restrict nav node visibility**

---

### `DELETE /nav/nodes/{node_id}/policies/{policy_id}`
**Remove a nav visibility policy**

---

## 26. Collection Variables Reference

These variables are auto-set by Postman test scripts and used as path/body parameters in subsequent requests.

| Variable | Set By | Used In |
|----------|--------|---------|
| `base_url` | Manual | All requests |
| `token` | `POST /auth/login` | All authenticated requests |
| `user_id` | `POST /auth/register` or `GET /auth/me/permissions` | Role assignment, admin ops |
| `org_id` | `POST /auth/register` | Org-scoped operations |
| `second_org_id` | `POST /orgs` | Multi-org tests |
| `domain_id` | `POST /domains` (legacy) | Legacy domain tests |
| `team_id` | `POST /teams` | Team operations |
| `child_team_id` | `POST /teams` (child) | Hierarchy tests |
| `role_id` | `POST /roles` | Role assignments |
| `policy_id` | `POST /policies` | Policy assignments |
| `subscription_id` | `POST /subscriptions` | Subscription tests |
| `setting_node_id` | `POST /settings/nodes` | Settings tests |
| `setting_child_id` | `POST /settings/nodes` (child) | Settings hierarchy |
| `setting_leaf_id` | `POST /settings/nodes` (leaf) | Override tests |
| `resource_key` | `GET /resources/flat` | Operations lookup |
| `nav_node_id` | `POST /nav/nodes` | Nav tests |
| `subject_area_id` | `POST /subject-areas` | Subject area ops |
| `lookup_category_id` | `POST /lookup` | Lookup value ops |
| `lookup_value_id` | `POST /lookup/{id}/values` | Delete value |
| `catalog_domain_id` | `POST /catalog-domains` | Data products, activities |
| `data_product_id` | `POST /data-products` | Data product ops |
| `glossary_id` | `POST /glossaries` | Term operations |
| `glossary_term_id` | `POST /glossaries/{id}/terms` | Like, change request |
| `classification_id` | `POST /classifications` | Tag operations |
| `classification_tag_id` | `POST /classifications/{id}/tags` | Tag ops |
| `govern_metric_id` | `POST /govern-metrics` | Metric ops |
| `change_request_id` | `POST /change-requests` | Approve/reject/withdraw |
| `storage_config_id` | `POST /storage-config` | Activate, update |
| `service_endpoint_id` | `POST /service-endpoints` | Monitor redirect |
| `admin_created_user_id` | `POST /admin/users` | Admin user ops |

---

## Error Reference

| Status | Meaning |
|--------|---------|
| `400` | Bad request — malformed input |
| `401` | Unauthorized — missing or invalid token |
| `403` | Forbidden — valid token but insufficient permissions |
| `404` | Resource not found |
| `409` | Conflict — duplicate name/email/slug |
| `422` | Validation error — invalid field value or resource key |
| `204` | Success with no response body (DELETE operations) |

---

*Generated from Deltameta Phase 1 implementation — 201 tests passing.*

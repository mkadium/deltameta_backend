# Deltameta — Complete Project Roadmap

## What Is Deltameta?

Deltameta is a **Data Catalog & Governance Platform**. It is an inventory system for all data assets in an organization — answering:

- What data do we have and where does it live?
- Who owns it, who can access it?
- Is it sensitive, PII, GDPR-regulated?
- What is its quality, freshness, and usage?
- Where did it come from and where does it go? (Lineage)
- How do we find it quickly? (Search)

---

## User Story — End-to-End Journey

```
Step 1: Admin sets up org, teams, roles, ABAC policies
Step 2: Admin connects infrastructure (external Postgres, MinIO/S3, Trino, Spark, Airflow, Iceberg)
Step 3: Admin or Data Owners configure and run Bots → catalog auto-populated
Step 4: Users upload files (CSV/Excel) or create Catalog Views from external connections
         → data stored in MinIO/S3, schema in Iceberg + Postgres, DataAsset created in catalog
Step 5: Users query data via Trino SQL engine → reads Iceberg schema + MinIO/S3 data
Step 6: Users write PySpark notebooks → execute directly or schedule as pipeline via Airflow
Step 7: Data Stewards govern — verify tags, add descriptions, manage change requests
Step 8: Data Quality — create test cases, bundle into test suites, run via TestSuit Bot
         → failures auto-create Incidents, assignees resolve them
Step 9: Data Users discover and use data — search, view lineage, subscribe
Step 10: Compliance reporting — PII audit, lineage audit, ABAC access reports
```

### Infrastructure Flow

```
External Postgres / Iceberg / MinIO (default) / S3 (optional) / Trino / Spark / Airflow
        ↓
  ┌─────────────────────────────────────────────────────────────┐
  │  Data Ingest Layer                                          │
  │  • User uploads CSV/Excel → stored in MinIO/S3              │
  │  • User creates Catalog View from external Postgres table   │
  │  • Sync pulls data on-demand or scheduled                   │
  │  Schema always registered in Iceberg REST + Postgres        │
  └─────────────────────────────────────────────────────────────┘
        ↓
  ┌─────────────────────────────────────────────────────────────┐
  │  Deltameta Catalog                                          │
  │  ├── Datasets + DataAssets + Columns                        │
  │  ├── Catalog Views (from connections, different color)       │
  │  ├── Lineage Graph                                          │
  │  ├── Profiles + Data Quality (Test Cases + Suites)          │
  │  ├── Classifications + Tags                                 │
  │  └── Glossary Terms                                         │
  └─────────────────────────────────────────────────────────────┘
        ↓
  Query via Trino → reads Iceberg schema + MinIO/S3 data
  Pipelines via Spark + Airflow → all recorded in catalog
  Bots auto-update metadata, lineage, quality, classifications
  Users search → find assets → subscribe → governed by ABAC policies
```

---

## Storage Architecture

**MinIO** is the default built-in storage (runs locally in a container alongside Deltameta).
Admin can switch to **AWS S3** or any S3-compatible storage via `StorageConfig`.

**Sync Feature (MinIO ↔ S3):**

- Admin can sync data between MinIO and S3 in both directions
- **Before MinIO → S3 sync**: Deltameta checks MinIO available space + S3 bucket permissions
- **Before S3 → MinIO sync**: Deltameta checks MinIO free space first (local, limited capacity) — blocks sync if insufficient space
- `StorageConfig` needs `storage_type` field: `minio` | `s3` | `gcs` | `azure_blob`

---

## Current State — Phase 1 COMPLETE

All items below are done, tested, and pushed to `mohan`, `dev`, `main`.

### DB Tables (42 total in `deltameta` schema)

**Auth tables:** `organizations`, `auth_config`, `subject_areas`, `teams`, `policies`, `roles`, `users`, `org_profiler_config`, `subscriptions`

**Association tables (auth):** `user_organizations`, `user_teams`, `user_roles`, `user_policies`, `role_policies`

**Governance tables:** `catalog_domains`, `data_products`, `lookup_categories`, `lookup_values`, `glossaries`, `glossary_terms`, `classifications`, `classification_tags`, `govern_metrics`, `change_requests`, `activity_feeds`, `scheduled_tasks`, `storage_config`, `service_endpoints`

**Association tables (governance):** `catalog_domain_owners`, `catalog_domain_experts`, `data_product_owners`, `data_product_experts`, `glossary_term_owners`, `glossary_term_reviewers`, `glossary_term_related`, `glossary_term_likes`, `classification_owners`, `classification_domain_refs`, `classification_tag_owners`, `classification_tag_domain_refs`, `govern_metric_owners`, `change_request_assignees`, `org_roles`, `org_policies`, `team_roles`, `team_policies`

**Data Catalog tables (Phase 2 Module 1):** `datasets`, `data_assets`, `data_asset_columns`

**Association tables (catalog):** `dataset_owners`, `dataset_experts`, `data_asset_owners`, `data_asset_experts`, `data_asset_tags`

### Migrations Applied

| #    | Migration                            | Content                            |
| ---- | ------------------------------------ | ---------------------------------- |
| 0001 | `auth_org_hierarchy`                 | 13 auth tables + seed global admin |
| 0002 | `domains_org_subscriptions_columns`  | Extended columns                   |
| 0003 | `user_organizations_and_default_org` | Multi-org membership               |
| 0004 | `setting_nodes`                      | Platform settings hierarchy        |
| 0005 | `resource_registry`                  | ABAC resource definitions          |
| 0006 | `nav_items`                          | Navigation items                   |
| 0007 | `setting_nodes_seed`                 | Seed setting node data             |
| 0008 | `setting_nodes_databases_children`   | DB setting nodes                   |
| 0009 | `govern_and_abac_tables`             | All governance models              |
| 0010 | `datasets_and_data_assets`           | Datasets + DataAssets + Columns    |

### APIs (~185 endpoints across 24 routers)

| Module            | Endpoints                                                                                      |
| ----------------- | ---------------------------------------------------------------------------------------------- |
| Auth              | register, login, logout, refresh, me GET/PUT, orgs, permissions, forgot/reset password, config |
| Organization      | CRUD orgs + members + stats + teams-grouped + roles + policies + profiler-config               |
| Teams             | CRUD + hierarchy + members + stats + roles + policies                                          |
| Roles             | CRUD + assign users + assign policies                                                          |
| Policies          | CRUD + assign users + list by user                                                             |
| Subscriptions     | CRUD + by resource                                                                             |
| Settings          | CRUD + tree + org/user overrides + policies                                                    |
| Resources         | list + flat + operations + sync                                                                |
| Navigation        | CRUD + tree + org/user overrides + policies                                                    |
| Subject Areas     | CRUD                                                                                           |
| Lookup            | CRUD categories + values                                                                       |
| Catalog Domains   | CRUD                                                                                           |
| Data Products     | CRUD                                                                                           |
| Glossary          | CRUD glossaries + terms + like/unlike + export/import                                          |
| Classifications   | CRUD classifications + tags                                                                    |
| Govern Metrics    | CRUD                                                                                           |
| Change Requests   | CRUD + approve + reject + withdraw                                                             |
| Activity Feed     | list                                                                                           |
| Storage Config    | CRUD + activate                                                                                |
| Service Endpoints | CRUD                                                                                           |
| Monitor           | list all + health check + Spark/Trino/Airflow/MinIO/RabbitMQ/Jupyter UI redirects              |
| Admin             | CRUD users + reset-password + unlock + verify                                                  |
| Datasets          | CRUD + filters + owner/expert assign                                                           |
| Data Assets       | CRUD + filters + owner/expert/tag assign + columns CRUD + bulk column replace                  |

### Supporting Infrastructure

- Alembic migrations 0001–0010
- Comprehensive relational filters on all GET list endpoints
- Postman collections (local + Vercel)
- Resource registry with all ABAC resource keys and operations
- Test suite `testcases/test_relational_filters.py`

---

## Pre-Phase 2 Fixes — IN PROGRESS

These must be done before Phase 2 modules start.

### Fix 1 — ClassificationTag Detection Fields

**File:** `backend/app/govern/models.py` → `ClassificationTag`

Add two columns:

- `detection_patterns: JSONB` — list of detection rules the Classification Bot uses at runtime
  ```json
  [
    { "type": "column_name", "pattern": "email", "confidence": 1.0 },
    { "type": "column_name", "pattern": "user_email", "confidence": 1.0 },
    { "type": "regex", "pattern": "^[\\w.]+@[\\w.]+$", "confidence": 0.9 },
    { "type": "data_sample", "pattern": "^[\\w.]+@[\\w.]+$", "confidence": 0.8 }
  ]
  ```
- `auto_classify: Boolean` (default `false`) — whether the bot should auto-apply this tag

**Migration:** `0011_classification_tag_detection`

**Schema update:** `ClassificationTagCreate`, `ClassificationTagUpdate`, `ClassificationTagOut` in `backend/app/classifications/router.py`

Admin workflow:

1. Create Classification (e.g. "PII") → create Tags (e.g. "email", "phone", "ssn")
2. Per tag, set `detection_patterns` + `auto_classify = true`
3. Classification Bot fetches all tags with `auto_classify = true`, builds detection rules, scans columns, applies tags automatically

---

### Fix 2 — Bots API

**New file:** `backend/app/bots/router.py`

**New model:** `Bot` table in `deltameta` schema

```
id, org_id
name                  — human-readable name
description
bot_type              — metadata | profiler | lineage | usage | classification | search_index | test_suite
mode                  — self | external
is_enabled            — bool, default false
trigger_mode          — on_demand | scheduled (default: on_demand)
cron_expr             — nullable, only when trigger_mode = scheduled
service_endpoint_id   — FK → service_endpoints.id (external mode: holds base_url + api_key)
model_name            — e.g. gpt-4o, claude-3-5-sonnet (external mode only)
last_run_at           — nullable timestamp
last_run_status       — nullable: running | success | failed
last_run_message      — nullable text
created_at, updated_at
```

**Mode behavior:**

- `self`: Deltameta's built-in Python agent code runs as a background task
- `external`: calls LLM API at `service_endpoint.base_url` with `service_endpoint.extra.api_key` using `model_name`

**Who can trigger bots:** Admins and data asset/dataset Owners (not just admin — governed by ABAC ownership check).

**Trigger behavior:**

- `on_demand` (default): manually triggered via `POST /bots/{id}/run`
- `scheduled`: admin sets `cron_expr` → system auto-creates/updates a `ScheduledTask` row

**Migration:** `0012_bots`

**Endpoints:**

```
GET    /bots                  List all bots (filter: bot_type, mode, is_enabled)
POST   /bots                  Create bot config
GET    /bots/{id}             Get bot
PUT    /bots/{id}             Update (mode, model, cron, service_endpoint_id, trigger_mode)
DELETE /bots/{id}             Delete

PATCH  /bots/{id}/enable      Set is_enabled = true
PATCH  /bots/{id}/disable     Set is_enabled = false
POST   /bots/{id}/run         On-demand trigger (creates ScheduledTask entry, returns task_id)
GET    /bots/{id}/runs        Run history for this bot
```

---

### Fix 3 — Bulk Assignment Endpoints

Convert 14 one-at-a-time path-param endpoints to accept body arrays. Keep single-item DELETE paths unchanged (UI needs to remove one chip at a time).

**`backend/app/roles/router.py`**

- `POST /roles/{id}/assign/{user_id}` → `POST /roles/{id}/assign` body: `{ "user_ids": ["uuid", ...] }`
- `POST /roles/{id}/policies/{policy_id}` → `POST /roles/{id}/policies` body: `{ "policy_ids": ["uuid", ...] }`

**`backend/app/policies/router.py`**

- `POST /policies/{id}/assign/{user_id}` → `POST /policies/{id}/assign` body: `{ "user_ids": ["uuid", ...] }`

**`backend/app/teams/router.py`**

- `POST /teams/{id}/members/{user_id}` → `POST /teams/{id}/members` body: `{ "user_ids": ["uuid", ...] }`
- `POST /teams/{id}/roles/{role_id}` → `POST /teams/{id}/roles` body: `{ "role_ids": ["uuid", ...] }`
- `POST /teams/{id}/policies/{policy_id}` → `POST /teams/{id}/policies` body: `{ "policy_ids": ["uuid", ...] }`

**`backend/app/org/router.py`**

- `POST /orgs/{id}/members/{user_id}` → `POST /orgs/{id}/members` body: `{ "user_ids": ["uuid", ...], "is_org_admin": false }`
- `POST /orgs/{id}/roles/{role_id}` → `POST /orgs/{id}/roles` body: `{ "role_ids": ["uuid", ...] }`
- `POST /orgs/{id}/policies/{policy_id}` → `POST /orgs/{id}/policies` body: `{ "policy_ids": ["uuid", ...] }`

**`backend/app/datasets/router.py`**

- `POST /datasets/{id}/owners/{user_id}` → `POST /datasets/{id}/owners` body: `{ "user_ids": ["uuid", ...] }`
- `POST /datasets/{id}/experts/{user_id}` → `POST /datasets/{id}/experts` body: `{ "user_ids": ["uuid", ...] }`

**`backend/app/data_assets/router.py`**

- `POST /data-assets/{id}/owners/{user_id}` → `POST /data-assets/{id}/owners` body: `{ "user_ids": ["uuid", ...] }`
- `POST /data-assets/{id}/experts/{user_id}` → `POST /data-assets/{id}/experts` body: `{ "user_ids": ["uuid", ...] }`
- `POST /data-assets/{id}/tags/{tag_id}` → `POST /data-assets/{id}/tags` body: `{ "tag_ids": ["uuid", ...] }`

### Fix 4 — StorageConfig Enhancement

Add `storage_type` field to `StorageConfig` model: `minio | s3 | gcs | azure_blob` (default: `minio`).

This is the prerequisite for the MinIO/S3 sync feature in Phase 3.

**Migration:** Part of `0012` or separate `0013` depending on ordering.

---

### Fix 5 — Postman + Git

- Update both Postman collection files:
  - New **Bots** folder with all 9 endpoints
  - Updated bulk assignment payloads for all 14 changed endpoints
  - Profiler config already added in Phase 2 Module 1
- Commit and push to `mohan`, `dev`, `main`

---

## Phase 2 — Pending

### Module 2 — Data Profiling

**New file:** `backend/app/profiling/router.py`

**New models:**

```
DataAssetProfile
  id, asset_id (FK → data_assets), org_id
  triggered_by (FK → users), status (pending | running | success | failed)
  row_count, profile_data (JSONB — asset-level stats)
  started_at, completed_at

ColumnProfile
  id, profile_id (FK → data_asset_profiles), column_id (FK → data_asset_columns), asset_id
  data_type, null_count, null_pct, distinct_count
  min_val, max_val, mean_val, stddev_val
  top_values (JSONB — [{value, count}])
  histogram (JSONB — optional bucket distribution)
```

**Migration:** `0012` or `0013`

**Endpoints:**

```
POST   /data-assets/{id}/profile            Trigger profiling run
GET    /data-assets/{id}/profiles           List profile runs (paginated)
GET    /data-assets/{id}/profiles/latest    Latest profile + all column profiles
GET    /data-assets/{id}/profiles/{pid}     Specific profile run detail
```

Also: **ScheduledTask API** `backend/app/scheduled_tasks/router.py`

```
GET    /scheduled-tasks                     List (filter: entity_type, status, is_active)
POST   /scheduled-tasks                     Create
GET    /scheduled-tasks/{id}               Get
PUT    /scheduled-tasks/{id}               Update (cron, payload)
DELETE /scheduled-tasks/{id}               Delete
POST   /scheduled-tasks/{id}/run           Trigger manually
PATCH  /scheduled-tasks/{id}/enable        Enable
PATCH  /scheduled-tasks/{id}/disable       Disable
```

`OrgProfilerConfig` (already built via `GET/PUT /org/profiler-config`) controls which metric types run per datatype.

---

### Module 3 — Data Lineage

**New file:** `backend/app/lineage/router.py`

**New model:**

```
LineageEdge
  id, org_id
  source_asset_id (FK → data_assets)
  target_asset_id (FK → data_assets)
  edge_type    — direct | derived | copy | aggregated
  transformation (Text, nullable — SQL or description of the transform)
  created_by (FK → users)
  created_at
```

**Migration:** `0013` or `0014`

**Endpoints:**

```
POST   /lineage                            Create edge (source → target)
GET    /lineage/{asset_id}/upstream        Traverse upstream graph recursively
GET    /lineage/{asset_id}/downstream      Traverse downstream graph recursively
GET    /lineage/{asset_id}/graph           Full graph (nodes + edges) for visualization
DELETE /lineage/{edge_id}                  Remove edge
GET    /lineage                            List all edges (filter: source_asset_id, target_asset_id, edge_type, created_by)
```

---

### Module 4 — Data Quality

Data Quality has its own dedicated page with two tabs: **Test Cases** and **Test Suites**, plus an **Incident Manager**.

**New file:** `backend/app/quality/router.py`

---

#### Test Cases

A test case is an individual quality check attached to a data asset at one of three levels:

- **Table level**: row count between X and Y, row count equals N, compare two tables for differences, row inserted count between X and Y
- **Column level**: column count between X and Y, column count equals N, column name exists, column name matches set, custom SQL query
- **Dimension level**: accuracy, completeness, consistency, integrity, uniqueness, validity, SQL, no dimension

Each test case has: `name`, `description`, `tags`, `glossary_term_ids`, `level` (table/column/dimension), `test_type`, `config` (JSONB for thresholds/patterns), `severity` (info/warning/critical), `is_active`.

**New models:**

```
QualityTestCase
  id, org_id, asset_id (FK → data_assets)
  column_id (nullable FK → data_asset_columns)
  name, description
  level          — table | column | dimension
  test_type      — row_count_between | row_count_equal | column_count_between |
                   column_count_equal | column_name_exists | column_name_match_set |
                   custom_sql | compare_tables | row_inserted_between
  dimension      — accuracy | completeness | consistency | integrity |
                   uniqueness | validity | sql | no_dimension (nullable)
  config (JSONB  — e.g. { "min": 100, "max": 5000 } or { "sql": "SELECT ..." })
  severity       — info | warning | critical
  tags (JSONB)
  glossary_term_ids (JSONB)
  is_active      — bool
  created_by (FK → users), created_at, updated_at

QualityTestRun
  id, org_id
  test_case_id (nullable FK → quality_test_cases)
  test_suite_id (nullable FK → quality_test_suites)
  triggered_by (FK → users)
  status         — pending | running | success | aborted | failed
  result_detail (JSONB — pass/fail counts, row samples, error messages)
  started_at, completed_at

QualityIncident
  id, org_id
  test_case_id (FK → quality_test_cases)
  asset_id (FK → data_assets)
  assignee_id (nullable FK → users)
  status         — open | in_progress | resolved | ignored
  severity       — info | warning | critical
  failed_reason  (Text — why the test failed)
  aborted_reason (Text, nullable)
  created_at, updated_at, resolved_at
```

---

#### Test Suites

Two sub-types:

**Table Suites** — auto-created by the system when test cases are created for a table (one suite per table). Users can also manually create them per table. Appear in the "Table Suites" tab.

**Bundle Suites** — manually created by user. Group any test cases across multiple tables. Appear in the "Bundle Suites" tab.

```
QualityTestSuite
  id, org_id
  name, description
  suite_type     — table | bundle
  asset_id (nullable FK → data_assets — for table suites)
  test_case_ids (JSONB — list of QualityTestCase UUIDs)
  owner_ids (JSONB — list of user UUIDs)
  has_pipeline   — bool (default false)
  trigger_mode   — on_demand | scheduled (only when has_pipeline = true)
  cron_expr      — nullable
  enable_debug_log — bool (default false)
  raise_on_error — bool (default false)
  created_by (FK → users), created_at, updated_at
```

---

#### Incident Manager

Auto-created when a test case run results in `failed` or `aborted`. Incidents are assigned to users for resolution.

Incident list filters: `test_case_id`, `assignee_id`, `status`, `severity`, date range (yesterday / last 7 / 15 / 30 days).

Clicking an incident row shows: full run stats, logs, affected rows sample, resolution history.

---

#### TestSuit Bot

A dedicated bot (`bot_type = test_suite`) that executes test suites automatically:

- `self` mode: Deltameta runs the test case checks against the asset's data source
- `external` mode: sends test config to LLM/API for advanced custom SQL evaluation
- `on_demand` or `scheduled` like all other bots
- Admins and data asset owners can trigger it

---

**Migration:** `0015_quality`

**Endpoints:**

```
# Test Cases
GET    /quality/test-cases                               List (filter: asset_id, level, test_type, dimension, status, tier, tags, service, last_run)
POST   /quality/test-cases                               Create
GET    /quality/test-cases/{id}                          Get
PUT    /quality/test-cases/{id}                          Update
DELETE /quality/test-cases/{id}                          Delete
POST   /quality/test-cases/{id}/run                      Run single test case

# Test Suites
GET    /quality/test-suites                              List (filter: suite_type, owner_id, asset_id)
POST   /quality/test-suites                              Create (bundle suite)
GET    /quality/test-suites/{id}                         Get
PUT    /quality/test-suites/{id}                         Update
DELETE /quality/test-suites/{id}                         Delete
POST   /quality/test-suites/{id}/run                     Run all test cases in suite
GET    /quality/test-suites/{id}/runs                    Run history for suite

# Test Runs (unified across test cases + suites)
GET    /quality/runs                                     List runs (filter: test_case_id, test_suite_id, status, triggered_by)
GET    /quality/runs/{id}                                Run detail + result_detail

# Incidents
GET    /quality/incidents                                List (filter: test_case_id, assignee_id, status, severity, date_range)
GET    /quality/incidents/{id}                           Incident detail + stats + logs
PUT    /quality/incidents/{id}                           Update (assignee, status, notes)

# Data Asset quality summary
GET    /data-assets/{id}/quality/summary                 Latest pass/fail/aborted counts + health score
GET    /data-assets/{id}/quality/test-cases              All test cases for this asset
POST   /data-assets/{id}/quality/run                     Run all active test cases for asset
```

**Dashboard stats (derived from queries, no separate model needed):**

- Total tests: success count, aborted count, failed count
- Healthy Data Assets: count of assets with 100% passing test cases
- Data Assets Coverage: % of total assets that have at least one test case
- Per test case insight row: status, failed/aborted reason, last run timestamp, name, table, column, incident link

---

### Module 5 — ABAC Enforcement

**New file:** `backend/app/auth/policy_engine.py`

`PolicyEvaluator` service:

1. Collect all policies for user: direct `user_policies` + via `user_roles → role_policies` + via `user_teams → team_policies` + via `user_organizations → org_policies`
2. Filter policies matching requested `resource` key
3. Check requested `operation` is in policy `operations` list
4. Evaluate `conditions` JSONB array against user attributes (is_admin, team_id, domain_id, etc.)
5. Return `allow` / `deny`

`require_permission("resource_key", "operation")` FastAPI dependency — drop onto any endpoint.

Wire enforcement incrementally: start with high-impact endpoints (data_assets, catalog_domains) then expand to all.

---

### Module 6 — Search

**New file:** `backend/app/search/router.py`

```
GET /search?q=&type=&domain_id=&owner_id=&is_pii=&sensitivity=&skip=&limit=
```

Covers: `DataAsset`, `Dataset`, `GlossaryTerm`, `CatalogDomain`, `Classification`, `ClassificationTag`, `GovernMetric`

Implementation: PostgreSQL `to_tsvector()` UNION queries. Returns unified list with `entity_type`, `id`, `name`, `description`, `score`, `url_path`.

Phase 3 replaces this with Elasticsearch (same API contract, different backend).

---

### Phase 2 Deliverables per Module

- Migration file
- Router file(s)
- Postman folder with all endpoints
- Push to `mohan`, `dev`, `main`

---

## Phase 3 — Future

### Foundation Already Built

- `ServiceEndpoint` model + CRUD — stores `base_url` + `extra` JSONB (credentials, tokens) per service
- `StorageConfig` model + CRUD — MinIO/S3 credentials
- `Monitor` API — health checks + UI redirect URLs for all services
- Known service names: `spark_ui`, `spark_history`, `trino_ui`, `airflow_ui`, `rabbitmq_ui`, `celery_flower`, `jupyter`, `minio_console`, `iceberg_rest`

The gap: config is stored, but no actual API calls to these services exist yet. Phase 3 adds the real integration + agent layer.

---

### Module 0 — Data Ingest (File Upload → Catalog)

**Files:** `backend/app/ingest/router.py`, `backend/agents/ingest_agent.py`

**Flow:**

```
User uploads file (CSV / Excel / delimited text)
  → Available from: Catalog > Explore page OR dedicated Data Ingest page
  → File stored in MinIO/S3 (bucket configured by admin — see Bucket Config below)
  → Schema inferred from file headers + data types
  → Schema registered in Iceberg REST Catalog (enables ACID + time-travel)
  → Schema also stored in Postgres (relational metadata)
  → DataAsset created in Deltameta catalog
  → DataAssetColumns auto-populated from inferred schema
  → Object appears in Explore → Catalog → Data with "uploaded" badge/color
```

**Admin bucket configuration (one-time setup):**

- Admin creates a bucket in MinIO or S3 via `POST /integrations/storage/{config_id}/buckets`
- Admin maps it as the default ingest destination via `PUT /org/storage-ingest-config`
- All uploaded files go into that bucket, path: `{bucket}/{org_id}/{dataset_name}/{filename}`
- Each object: data file + metadata sidecar in storage, schema definition in Postgres + Iceberg

**New model:**

```
IngestJob
  id, org_id
  file_name, file_size, file_type   — csv | excel | tsv | json
  storage_config_id (FK → storage_config)
  bucket, object_key                — where file landed in MinIO/S3
  asset_id (nullable FK → data_assets — created after ingest)
  status         — pending | uploading | inferring | registering | success | failed
  error_message  (nullable)
  triggered_by (FK → users)
  created_at, completed_at
```

**Endpoints:**

```
POST   /ingest/upload                Upload file → triggers ingest job
GET    /ingest/jobs                  List ingest jobs (filter: status, triggered_by, file_type)
GET    /ingest/jobs/{id}             Job status + progress
GET    /ingest/jobs/{id}/preview     Preview first 50 rows + inferred schema (before finalizing)
POST   /ingest/jobs/{id}/confirm     Confirm schema + create DataAsset (after preview)
DELETE /ingest/jobs/{id}             Cancel/remove
```

**Object visual distinction in Explore → Catalog → Data:**

- Uploaded files: `source_type = "upload"` → shown with **blue** badge
- Catalog Views (from external connection sync): `source_type = "connection_sync"` → shown with **green** badge
- Bot-discovered (external Postgres/Trino/Iceberg metadata scan): `source_type = "bot_scan"` → shown with **orange** badge

---

### Module 0b — Catalog Views (External Connection → Catalog)

**Flow:**

```
Admin adds external Postgres connection (ServiceEndpoint)
      ↓
Metadata bot scans → discovers tables, views, materialized views
      ↓
User browses connection objects in Connection Explorer
      ↓
User selects object → clicks "Create Catalog View"
  → Fills in: name, display_name, description, tags, glossary terms, synonyms
  → Configures sync: on-demand OR scheduled (cron)
      ↓
On sync (on-demand or scheduled):
  → Data pulled from external Postgres
  → Stored in MinIO/S3 + schema in Iceberg + Postgres
  → DataAsset created/updated in catalog (source_type = "connection_sync", badge = green)
  → Queryable via Trino
```

**New model:**

```
CatalogView
  id, org_id
  asset_id (FK → data_assets — the catalog entry for this view)
  source_connection_id (FK → service_endpoints — the external Postgres)
  source_schema, source_table       — origin object in external Postgres
  source_object_type — table | view | materialized_view
  name, display_name, description
  tags (JSONB), glossary_term_ids (JSONB), synonyms (JSONB)
  sync_mode      — on_demand | scheduled
  cron_expr      (nullable)
  last_synced_at (nullable timestamp)
  sync_status    — never | syncing | success | failed
  sync_error     (nullable text)
  created_by (FK → users), created_at, updated_at
```

**Endpoints:**

```
GET    /catalog-views                               List (filter: source_connection_id, sync_status, source_object_type)
POST   /catalog-views                               Create Catalog View from connection object
GET    /catalog-views/{id}                          Get
PUT    /catalog-views/{id}                          Update (name, description, tags, sync config)
DELETE /catalog-views/{id}                          Delete
POST   /catalog-views/{id}/sync                     Trigger on-demand sync
GET    /catalog-views/{id}/sync-history             Sync run history

# Connection Explorer (browse external connection objects before creating a view)
GET    /service-endpoints/{conn_id}/explore/schemas          List schemas in external Postgres
GET    /service-endpoints/{conn_id}/explore/{schema}/objects List tables/views/matviews in schema
GET    /service-endpoints/{conn_id}/explore/{schema}/{object} Schema preview of the object
```

**Migration:** `0016_ingest_and_catalog_views` — adds `ingest_jobs`, `catalog_views` tables + `source_type` column on `data_assets`.

---

### Module 0c — Notebooks (PySpark)

**Approach:** Embed Jupyter (option A — full integration) if feasible; fall back to redirect to Jupyter UI (option B).

**Flow:**

```
User opens Notebooks page in Deltameta
  → If embedded: Jupyter kernel spawned, iframe or token-based full embed
  → If redirect: opens Jupyter UI at ServiceEndpoint(service_name="jupyter").base_url

User writes PySpark code
  → Runs cell → executes directly in Spark (via SparkSession connected to Iceberg + MinIO/S3)
  → Output shown in notebook

User clicks "Create Pipeline from Notebook"
  → Pipeline definition created (executor_type = spark, source = notebook)
  → Schedule via Airflow (on-demand or cron)
  → Appears in Pipelines page in catalog
  → On run completion: auto-create LineageEdges + trigger QualityRuns on output assets
```

**No new model needed** — notebooks are stored in MinIO/S3 (`notebooks/` prefix) and referenced as a `PipelineDefinition` with `executor_type = spark` and `notebook_path` in `config` JSONB.

**Endpoints (addition to existing Pipelines API):**

```
POST   /notebooks/upload             Upload .ipynb file → store in MinIO/S3
GET    /notebooks                    List notebooks for org
DELETE /notebooks/{path}             Delete notebook
POST   /notebooks/{path}/run         Execute notebook directly in Spark (ad-hoc)
GET    /notebooks/{path}/runs/{id}   Run output + logs
```

---

### Module 1 — Trino Integration

**File:** `backend/app/integrations/trino/router.py`

Connects to Trino HTTP API via `ServiceEndpoint(service_name="trino_ui")`.

```
GET  /integrations/trino/catalogs
GET  /integrations/trino/catalogs/{cat}/schemas
GET  /integrations/trino/catalogs/{cat}/{schema}/tables
GET  /integrations/trino/catalogs/{cat}/{schema}/{table}     Schema + stats
POST /integrations/trino/query                               Execute SQL
GET  /integrations/trino/queries                             Recent query history
GET  /integrations/trino/queries/{query_id}                  Status + plan
DELETE /integrations/trino/queries/{query_id}                Kill query
POST /integrations/trino/sync                                Auto-discover all tables → create DataAssets
```

---

### Module 2 — Spark Integration

**File:** `backend/app/integrations/spark/router.py`

Connects to Spark REST API via `ServiceEndpoint(service_name="spark_ui")` + `ServiceEndpoint(service_name="spark_history")`.

```
GET  /integrations/spark/apps                                Running applications
GET  /integrations/spark/apps/{app_id}                       App detail + metrics
GET  /integrations/spark/apps/{app_id}/jobs                  Jobs
GET  /integrations/spark/apps/{app_id}/stages                Stages + task metrics
GET  /integrations/spark/history                             Completed apps
GET  /integrations/spark/history/{app_id}                    Historical app detail
POST /integrations/spark/submit                              Submit job
GET  /integrations/spark/submit/{submission_id}              Submission status
```

---

### Module 3 — Airflow Integration

**File:** `backend/app/integrations/airflow/router.py`

Connects to Airflow REST API via `ServiceEndpoint(service_name="airflow_ui")`.

```
GET   /integrations/airflow/dags                             List DAGs
GET   /integrations/airflow/dags/{dag_id}                    DAG detail + schedule
POST  /integrations/airflow/dags/{dag_id}/trigger            Trigger DAG run
GET   /integrations/airflow/dags/{dag_id}/runs               Run history
GET   /integrations/airflow/dags/{dag_id}/runs/{run_id}      Run status
GET   /integrations/airflow/dags/{dag_id}/runs/{run_id}/tasks  Task instances
GET   /integrations/airflow/dags/{dag_id}/runs/{run_id}/tasks/{task_id}/logs  Task logs
PATCH /integrations/airflow/dags/{dag_id}/pause              Pause DAG
PATCH /integrations/airflow/dags/{dag_id}/unpause            Unpause DAG
```

Bot integration: `POST /bots/{id}/run` (self mode, metadata bot_type) → triggers Airflow DAG → agent populates catalog.

---

### Module 4 — MinIO / S3 Integration

**File:** `backend/app/integrations/storage/router.py`

Uses `StorageConfig` credentials. Connects via `minio` Python SDK or `boto3`.

**MinIO is the default built-in storage.** Admin can switch to S3 via `StorageConfig.storage_type`.

```
GET  /integrations/storage/{config_id}/info                  Storage info (type, total/used/free space)
GET  /integrations/storage/{config_id}/buckets               List buckets
GET  /integrations/storage/{config_id}/buckets/{bucket}      Bucket stats (size, count)
GET  /integrations/storage/{config_id}/buckets/{bucket}/objects   List objects (prefix filter + pagination)
GET  /integrations/storage/{config_id}/buckets/{bucket}/objects/{key}  Object metadata
POST /integrations/storage/{config_id}/buckets/{bucket}/objects/{key}/presign  Presigned URL
POST /integrations/storage/{config_id}/sync                  Sync discovered files → DataAssets in catalog
```

**MinIO ↔ S3 Sync:**

```
GET  /integrations/storage/sync/preflight                    Pre-sync check:
                                                               - Source available space
                                                               - Destination available space (MinIO: check local)
                                                               - Estimated transfer size
                                                               - Conflicts

POST /integrations/storage/sync                              Start sync job
     body: {
       source_config_id: uuid,          (MinIO or S3 StorageConfig)
       destination_config_id: uuid,      (S3 or MinIO StorageConfig)
       direction: "minio_to_s3" | "s3_to_minio",
       buckets: [...],                   (optional — sync specific buckets only)
       dry_run: false
     }

GET  /integrations/storage/sync/{job_id}                     Sync job status + progress
DELETE /integrations/storage/sync/{job_id}                   Cancel sync
```

**Space check rule:** Before any S3 → MinIO sync, system checks MinIO free space. If estimated transfer size > available MinIO space, sync is blocked with a clear error message and size details.

---

### Module 5 — Iceberg Integration

**File:** `backend/app/integrations/iceberg/router.py`

Connects to Iceberg REST Catalog via `ServiceEndpoint(service_name="iceberg_rest")`.

```
GET  /integrations/iceberg/namespaces
GET  /integrations/iceberg/namespaces/{ns}/tables
GET  /integrations/iceberg/namespaces/{ns}/tables/{table}           Schema + partition spec + properties
GET  /integrations/iceberg/namespaces/{ns}/tables/{table}/snapshots Snapshot history (time-travel)
GET  /integrations/iceberg/namespaces/{ns}/tables/{table}/snapshots/{id}  Snapshot detail
POST /integrations/iceberg/namespaces/{ns}/tables/{table}/rollback  Rollback to snapshot
POST /integrations/iceberg/sync                                      Sync all tables → DataAssets in catalog
```

---

### Module 6 — Containers + CI/CD

**File:** `backend/docker-compose.yml`

Services (note: **Postgres is your own external connection — not containerized**):

```yaml
services:
  deltameta-api: # FastAPI app (port 8000)
  redis: # Job queue for Celery (port 6379)
  celery-worker: # Runs bot/agent background tasks
  elasticsearch: # Search index (port 9200) — replaces PG FTS
  spark-master: # Spark master (ports 7077, 8080)
  spark-worker: # Spark worker
  spark-history: # Spark History Server (port 18080)
  trino: # Trino query engine (port 8090)
  airflow-webserver: # Airflow UI (port 8082)
  airflow-scheduler: # Airflow scheduler
  minio: # Default built-in storage (ports 9000, 9001)
```

Also:

- `Dockerfile` for FastAPI app
- `backend/.env.docker` for container-specific env vars
- GitHub Actions: build + test + push Docker image on merge to `main`

---

### Module 7 — Scanner Agents

**Directory:** `backend/agents/`

Each agent calls Phase 2 APIs as a client. Triggered by Bots API → ScheduledTask → Celery worker.

| Agent                 | Source                                                                    | Catalog APIs Called                                                          |
| --------------------- | ------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `postgres_metadata`   | `information_schema`                                                      | `POST /datasets`, `POST /data-assets`, `POST /data-assets/{id}/columns/bulk` |
| `postgres_profiler`   | SQL column stats                                                          | `POST /data-assets/{id}/profile`                                             |
| `postgres_lineage`    | `pg_depend`, view defs, FK constraints                                    | `POST /lineage`                                                              |
| `postgres_usage`      | `pg_stat_user_tables`, `pg_stat_statements`                               | `PATCH /data-assets/{id}`                                                    |
| `postgres_classifier` | Column names + sample data + `detection_patterns` from ClassificationTags | `PUT /data-assets/{id}/columns/{col_id}`, `POST /data-assets/{id}/tags`      |
| `trino_metadata`      | Trino catalog discovery                                                   | `POST /datasets`, `POST /data-assets`                                        |
| `iceberg_metadata`    | Iceberg REST catalog                                                      | `POST /datasets`, `POST /data-assets`                                        |
| `minio_metadata`      | MinIO/S3 object listing                                                   | `POST /datasets`, `POST /data-assets`                                        |
| `airflow_lineage`     | DAG task input/output                                                     | `POST /lineage`                                                              |
| `test_suite_runner`   | QualityTestSuite + asset data source                                      | `POST /quality/test-suites/{id}/run`, creates `QualityIncident` on failure   |
| `catalog_view_sync`   | External Postgres → MinIO/S3/Iceberg                                      | `POST /catalog-views/{id}/sync`                                              |
| `search_indexer`      | All catalog entities                                                      | Elasticsearch bulk index                                                     |

**Classifier Agent detail:**

1. Fetch all `ClassificationTag` records where `auto_classify = true`
2. For each tag, load its `detection_patterns`
3. For each `DataAssetColumn` in scope, check column name + sample data against patterns
4. If match above `confidence` threshold → apply tag to asset + mark column as PII/sensitive
5. Mode = `external`: send column metadata to LLM with prompt → LLM returns tag suggestions

---

### Module 8 — Pipelines

**File:** `backend/app/pipelines/router.py`

**New models:**

```
PipelineDefinition
  id, org_id, name, description
  executor_type   — airflow | spark | dbt | custom
  service_endpoint_id (FK → service_endpoints)
  dag_id          — Airflow DAG ID or Spark job name
  source_asset_ids (JSONB — list of DataAsset UUIDs)
  target_asset_ids (JSONB — list of DataAsset UUIDs)
  is_active

PipelineRun
  id, pipeline_id, org_id
  triggered_by (FK → users)
  status         — pending | running | success | failed
  started_at, completed_at
  external_run_id — Airflow run_id or Spark submission_id
  auto_lineage    — bool (if true, completed run creates LineageEdge records)
  auto_quality    — bool (if true, completed run triggers QualityRun on target assets)

PipelineStep
  id, run_id, pipeline_id
  step_name, step_order
  source_asset_id, target_asset_id
  transformation (Text — SQL or code)
  status, started_at, completed_at
```

**Endpoints:**

```
GET/POST       /pipelines
GET/PUT/DELETE /pipelines/{id}
POST           /pipelines/{id}/run          Trigger pipeline (calls Airflow/Spark trigger)
GET            /pipelines/{id}/runs         Run history
GET            /pipelines/{id}/runs/{run_id}  Run detail + steps
```

On run completion: if `auto_lineage = true` → auto-create `LineageEdge` per step. If `auto_quality = true` → trigger `QualityRun` on all target assets.

---

### Module 9 — SSO Enforcement

`AuthConfig.sso_provider` already stored (default, google, cognito, azure, ldap, oauth2). Phase 3 adds actual OAuth2/OIDC redirect + callback flow using `authlib`.

---

### Module 10 — Real-time Notifications

`GET /ws/notifications` — WebSocket or SSE endpoint. Uses existing `Subscription` model. Redis pub/sub as message broker. Pushes events when subscribed resources change (schema updated, quality failed, pipeline completed, classification applied).

---

### Module 11 — Elasticsearch Integration

Replace Phase 2 PG full-text `/search` with Elasticsearch. Same API contract (`GET /search?q=...`) — only the backend changes. `search_indexer` bot maintains the index. `ServiceEndpoint(service_name="elasticsearch")` stores the ES URL.

---

## Phase 4 — AI Semantic Layer (Knowledge Graph + RAG + Chatbot)

This phase transforms Deltameta from a passive catalog into an **AI-powered data assistant**. Users ask natural language questions and receive SQL-backed answers with visualizations, grounded in a semantic knowledge graph of the entire catalog.

### Architecture Overview

```
Phase 1/2/3 Catalog (enriched)
  DataAssets + Columns + Lineage + Classifications + PII + Tier + Glossary + Quality
        ↓ RDF Bot
Turtle/N-Triples files → stored in MinIO/S3 (rdf/{org_id}/{YYYY-MM-DD}/catalog.ttl)
        ↓ Embedding Bot
Weaviate (vector DB) → semantic embeddings of all RDF chunks, org-scoped
        ↓ Chatbot API (RAG Pipeline)
User question → embed → Weaviate search → retrieve catalog context
    → LLM generates Trino SQL → execute → fetch from MinIO/S3 + Iceberg + Postgres
    → LLM streams natural language answer + visualization spec
        ↓
Chat page inside Deltameta (per-user sessions, full history)
+  Embeddable widget for external apps
```

---

### Module 1 — RDF Bot

**Bot type:** `rdf_export` (new `bot_type` enum value)

**What it does:** Converts the entire enriched catalog into **RDF Turtle files** — a semantic knowledge graph of all relationships.

**Entities converted to RDF triples:**

- `DataAsset` → type, name, domain, tier, sensitivity, is_pii, owner, expert, created_by
- `DataAssetColumn` → name, data_type, is_pii, is_primary_key, classification tags applied
- `LineageEdge` → source_asset → edge_type → target_asset (with transformation description)
- `ClassificationTag` → label, detection_patterns, auto_classify
- `GlossaryTerm` → definition, synonyms, related_terms
- `DataProduct` → name, description, domain, owners
- `QualityTestCase` → name, level, test_type, severity, last_run_status
- `CatalogDomain` → name, description, subject area link

**RDF output example (Turtle format):**

```turtle
@prefix deltameta: <https://deltameta.io/ontology/> .
@prefix dcat: <http://www.w3.org/ns/dcat#> .

<deltameta:asset/customers> a dcat:Dataset ;
    deltameta:name "customers" ;
    deltameta:tier "1" ;
    deltameta:isPII "true" ;
    deltameta:sensitivity "high" ;
    deltameta:owner <deltameta:team/crm> ;
    deltameta:domain <deltameta:domain/finance> ;
    deltameta:derivedFrom <deltameta:asset/raw_customers> ;
    deltameta:hasColumn <deltameta:column/customers/email> .

<deltameta:column/customers/email> a deltameta:Column ;
    deltameta:dataType "varchar" ;
    deltameta:isPII "true" ;
    deltameta:classifiedAs <deltameta:tag/email> .
```

**Storage:** Files stored in MinIO/S3 at `rdf/{org_id}/{YYYY-MM-DD}/catalog.ttl`

**Mode:**

- `self`: built-in Python RDF generation using `rdflib` library
- `external`: sends catalog JSON to LLM to produce enriched ontology with natural language descriptions as RDF literals

**Trigger:** on-demand or scheduled (recommended: run after every metadata bot run)

**Endpoints:**

```
POST   /bots/{id}/run             Standard bot run endpoint (rdf_export bot_type)
GET    /rdf/snapshots             List all RDF snapshot files (org-scoped, filter: date range)
GET    /rdf/snapshots/{date}      Download/preview snapshot (.ttl text)
DELETE /rdf/snapshots/{date}      Delete a snapshot
```

---

### Module 2 — Embedding Bot

**Bot type:** `embedding` (new `bot_type` enum value)

**What it does:** Reads the latest RDF snapshot from MinIO/S3, chunks it into semantic units, and creates **vector embeddings** stored in **Weaviate** (vector + graph DB).

**Chunking strategy — one chunk per:**

- `DataAsset` — name + description + tier + sensitivity + owner + domain + column names list
- `LineageEdge` — "asset X is derived from asset Y via transformation Z" in natural language
- `GlossaryTerm` — term + definition + synonyms
- `ClassificationTag` — tag name + detection description
- `QualityTestCase` — asset + test description + last status + severity

**Weaviate collection schema (`CatalogEntity`):**

```
entity_type:        "data_asset" | "lineage" | "glossary_term" | "classification" | "quality"
entity_id:          uuid                  — FK back to Postgres entity
org_id:             uuid                  — strict tenant isolation on all searches
text_chunk:         string                — human-readable text that was embedded
rdf_snapshot_date:  date                  — which snapshot this came from
vector:             float[]               — auto-populated by Weaviate embedding model
```

**Mode:**

- `self`: Weaviate's built-in `text2vec-transformers` module (local sentence transformer model — no API key)
- `external`: calls OpenAI `text-embedding-3-small` or Anthropic embeddings via `ServiceEndpoint`

**New containers (added to `docker-compose.yml`):**

```yaml
weaviate: # Vector DB (port 8080)
  modules: text2vec-transformers
t2v-transformers: # Sentence transformer model (all-MiniLM-L6-v2)
```

**Trigger:** on-demand or scheduled (recommended: run after every RDF Bot run)

**Endpoints:**

```
POST   /bots/{id}/run             Standard bot run endpoint (embedding bot_type)
GET    /embeddings/status         Weaviate stats: total vectors, last indexed, coverage %
POST   /embeddings/reindex        Force full re-index (drop + rebuild from latest RDF snapshot)
DELETE /embeddings/flush          Clear all embeddings for org (use before full reindex)
```

---

### Module 3 — Chatbot API (RAG Pipeline)

**File:** `backend/app/chat/router.py`

#### Session & Message Persistence

Every user has their own isolated chat history. Sessions are persisted per user, per org. The conversation context (previous Q&A pairs) is included in every new LLM call so the bot maintains continuity across sequential questions.

**New models:**

```
ChatSession
  id, org_id
  user_id (FK → users)                 — each user has their own sessions
  title                                — auto-generated from first message
  is_active       — bool (false = archived)
  created_at, updated_at

ChatMessage
  id, org_id
  session_id (FK → chat_sessions)      — belongs to one session
  user_id (FK → users)                 — which user sent/received it
  role            — user | assistant
  content         (Text — full message text)
  sql_generated   (nullable Text — Trino SQL used to fetch data)
  source_assets   (JSONB — list of DataAsset UUIDs referenced in answer)
  visualization   (JSONB — visualization spec for frontend rendering, nullable)
  weaviate_chunks (JSONB — which Weaviate chunk IDs were retrieved for this answer)
  token_count     (nullable int — LLM tokens used)
  created_at
```

**Context window management:**

- On each new message, the last N messages from the same session are loaded as conversation history
- History is passed to the LLM as `[{"role": "user", "content": ...}, {"role": "assistant", "content": ...}, ...]`
- N is configurable per org via settings (default: last 10 message pairs)
- Sequential follow-up questions like "now filter that by last month" resolve correctly because prior SQL and context are in the window

#### Full RAG Pipeline (per message)

```
1. Load session history (last N messages from ChatMessage for this session)
        ↓
2. Embed current user question
   → self: Weaviate built-in embedding
   → external: OpenAI/Anthropic embedding API
        ↓
3. Weaviate vector search (filter: org_id = current org — strict tenant isolation)
   → top-K most relevant catalog chunks (assets, lineage, glossary, quality)
        ↓
4. Build context prompt
   → conversation history + retrieved RDF chunks + catalog metadata
   → includes: asset schemas, owners, tiers, lineage paths, quality status
        ↓
5. LLM: Generate Trino SQL (if data retrieval is needed)
   → SQL grounded in Iceberg table definitions (schema-aware, safe)
   → self: Ollama / vLLM (local container)
   → external: GPT-4o / Claude via ServiceEndpoint
        ↓
6. Execute SQL via Trino → fetch from MinIO/S3 + Iceberg + Postgres
        ↓
7. LLM: Generate response
   → Natural language answer streamed token-by-token via SSE
   → Visualization spec auto-selected by result shape:
        single number   → stat card
        list/rows       → table
        time series     → line chart
        category counts → bar chart
        proportions     → pie chart
        ↓
8. Persist ChatMessage (role=user + role=assistant) to DB
        ↓
9. Return SSE stream to client
```

**SSE streaming format:**

```
event: token
data: {"text": "The Finance domain "}

event: token
data: {"text": "has 3 PII tables..."}

event: done
data: {
  "sql": "SELECT name, row_count FROM data_assets WHERE domain='finance' AND is_pii=true",
  "visualization": { "type": "table", "columns": ["name","row_count"], "data": [...] },
  "source_assets": ["uuid1", "uuid2", "uuid3"]
}
```

**Self-hosted LLM containers:**

```yaml
ollama: # Local LLM server (port 11434) — models: llama3, mistral, deepseek-r1
  # OR:
vllm: # GPU-accelerated local LLM (port 8000 internal) — for production self-hosted
```

**Endpoints:**

```
# Sessions (per-user, per-org)
GET    /chat/sessions                    List current user's sessions (filter: is_active, date)
POST   /chat/sessions                    Create new session → returns session_id
GET    /chat/sessions/{id}               Get session metadata + all messages (full history)
PATCH  /chat/sessions/{id}               Update title or archive session
DELETE /chat/sessions/{id}               Delete session + all its messages

# Messages (core RAG endpoint)
POST   /chat/sessions/{id}/messages      Send message → triggers full RAG pipeline
                                          Returns: SSE stream (tokens + final done event)
GET    /chat/sessions/{id}/messages      List all messages in session (ordered by created_at)

# Embeddable widget auth
POST   /chat/widget/token               Generate short-lived token for embedded widget
                                          (scoped to org + user, limited permissions)
GET    /chat/widget/config              Widget config (theme, org name, allowed features)
```

---

### Module 4 — Chatbot UI

**Inside Deltameta:**

- **Dedicated Chat page** — full-page UI with:
  - Left sidebar: list of all user's chat sessions (searchable, archivable)
  - Main area: conversation thread with streamed responses
  - Inline visualization rendering (chart/table/stat card per message)
  - "Source Assets" panel per assistant message — clickable links to catalog asset pages
- **Floating chat panel** — accessible from every page in Deltameta (bottom-right button)
  - Maintains the same session store (user can continue last session from anywhere)

**Embeddable widget:**

- `GET /chat/widget/embed.js` — JavaScript snippet embed
- Drop into any webpage: `<script src="https://deltameta.io/chat/widget/embed.js" data-token="..."></script>`
- Renders a floating chat button + slide-in panel
- Scoped to org's catalog, respects ABAC (only surfaces assets the user is authorized to see)
- Supports custom theming via `widget/config`

---

### Phase 4 — New Bot Types

| bot_type     | Purpose                                                         |
| ------------ | --------------------------------------------------------------- |
| `rdf_export` | Convert enriched catalog → RDF Turtle files → store in MinIO/S3 |
| `embedding`  | Chunk RDF + embed → store in Weaviate vector DB                 |
| `test_suite` | Run quality test suites (added in Phase 2 M4)                   |

---

### Phase 4 — New docker-compose services

```yaml
weaviate: # Vector DB — stores all catalog embeddings (port 8080)
t2v-transformers: # Sentence transformer for self-hosted embeddings
ollama: # Self-hosted LLM — llama3/mistral/deepseek-r1 (port 11434)
  # OR vllm for GPU-accelerated inference
```

---

## Migration History (Full Planned Sequence)

| #    | Migration                             | Phase  | Content                                                               |
| ---- | ------------------------------------- | ------ | --------------------------------------------------------------------- |
| 0001 | `auth_org_hierarchy`                  | 1      | 13 auth tables + seed                                                 |
| 0002 | `domains_org_subscriptions_columns`   | 1      | Extended columns                                                      |
| 0003 | `user_organizations_and_default_org`  | 1      | Multi-org membership                                                  |
| 0004 | `setting_nodes`                       | 1      | Platform settings hierarchy                                           |
| 0005 | `resource_registry`                   | 1      | ABAC resource definitions                                             |
| 0006 | `nav_items`                           | 1      | Navigation items                                                      |
| 0007 | `setting_nodes_seed`                  | 1      | Seed data                                                             |
| 0008 | `setting_nodes_databases_children`    | 1      | DB setting nodes                                                      |
| 0009 | `govern_and_abac_tables`              | 1      | All governance models                                                 |
| 0010 | `datasets_and_data_assets`            | 1/M1   | Datasets + DataAssets + Columns                                       |
| 0011 | `classification_tag_detection`        | Pre-P2 | `detection_patterns` + `auto_classify`                                |
| 0012 | `bots_and_storage_type`               | Pre-P2 | Bots table + `StorageConfig.storage_type`                             |
| 0013 | `data_asset_profiles`                 | P2/M2  | DataAssetProfile + ColumnProfile                                      |
| 0014 | `lineage_edges`                       | P2/M3  | LineageEdge                                                           |
| 0015 | `quality_test_cases_suites_incidents` | P2/M4  | QualityTestCase + QualityTestSuite + QualityTestRun + QualityIncident |
| 0016 | `ingest_and_catalog_views`            | P3/M0  | IngestJob + CatalogView + `source_type` on `data_assets`              |
| 0017 | `pipelines`                           | P3/M8  | PipelineDefinition + PipelineRun + PipelineStep                       |
| 0018 | `chat_sessions_messages`              | P4/M3  | ChatSession + ChatMessage (per-user, per-org)                         |

---

## Task Checklist

### Pre-Phase 2 Fixes

- [x] Add `detection_patterns` + `auto_classify` to `ClassificationTag` model + migration 0011
- [x] Update `ClassificationTagCreate` / `ClassificationTagOut` schemas
- [x] Add `storage_type` to `StorageConfig` model (migration 0012)
- [x] Add `Bot` model + migration 0012
- [x] Build `backend/app/bots/router.py` (9 endpoints)
- [x] Register `bots_router` in `main.py`
- [x] Convert 14 one-at-a-time assignment endpoints to bulk (7 router files)
- [x] Update Postman collections (Bots folder + bulk payloads)
- [ ] Push to `mohan`, `dev`, `main`

### Phase 2

- [ ] M2: `DataAssetProfile` + `ColumnProfile` models + migration 0013
- [ ] M2: Profiling API (`backend/app/profiling/router.py`)
- [ ] M2: ScheduledTask API (`backend/app/scheduled_tasks/router.py`)
- [ ] M3: `LineageEdge` model + migration 0014
- [ ] M3: Lineage API (`backend/app/lineage/router.py`)
- [ ] M4: `QualityTestCase` + `QualityTestSuite` + `QualityTestRun` + `QualityIncident` models + migration 0015
- [ ] M4: Quality API with Test Cases, Test Suites (table + bundle), Incidents (`backend/app/quality/router.py`)
- [ ] M4: TestSuit Bot (`bot_type = test_suite`) — add to Bots model enum + agent code
- [ ] M5: `PolicyEvaluator` + `require_permission()` dependency
- [ ] M5: Wire ABAC onto existing endpoints
- [ ] M6: Search API (`backend/app/search/router.py`) — PG full-text
- [ ] Update Postman + push to all branches

### Phase 3

- [ ] M0: File Ingest API — upload CSV/Excel → MinIO/S3 + Iceberg + Postgres + DataAsset creation
- [ ] M0: Org storage ingest config (`PUT /org/storage-ingest-config`) — default bucket mapping
- [ ] M0: Add `source_type` field to `DataAsset` + migration 0016
- [ ] M0b: `CatalogView` model + migration 0016 (combined with ingest migration)
- [ ] M0b: Catalog View API — create from external connection, sync on-demand/scheduled
- [ ] M0b: Connection Explorer endpoints on `service-endpoints` router
- [ ] M0c: Notebooks API — upload, list, run (PySpark via Spark), create pipeline from notebook
- [ ] M0c: Jupyter embed (attempt option A) or redirect (option B)
- [ ] M1: Trino integration API
- [ ] M2: Spark integration API
- [ ] M3: Airflow integration API
- [ ] M4: MinIO/S3 integration API + sync (with preflight space check)
- [ ] M5: Iceberg integration API
- [ ] M6: docker-compose (no Postgres — external) + Dockerfile + CI/CD
- [ ] M7: Scanner agents (12 agents in `backend/agents/`) including `test_suite_runner` + `catalog_view_sync`
- [ ] M8: Pipelines API + Airflow/Spark trigger + auto-lineage + auto-quality on completion
- [ ] M9: SSO enforcement (Google, Azure, Cognito)
- [ ] M10: WebSocket/SSE notifications
- [ ] M11: Elasticsearch integration

### Phase 4

- [ ] M1: RDF Bot (`bot_type = rdf_export`) — `rdflib` agent + MinIO/S3 snapshot storage
- [ ] M1: RDF snapshot API (`GET/DELETE /rdf/snapshots`)
- [ ] M2: Weaviate container + `t2v-transformers` in `docker-compose.yml`
- [ ] M2: Embedding Bot (`bot_type = embedding`) — chunk RDF + push to Weaviate
- [ ] M2: Embeddings status/reindex/flush API
- [ ] M3: `ChatSession` + `ChatMessage` models + migration 0018
- [ ] M3: Chatbot API (`backend/app/chat/router.py`) — sessions CRUD + SSE message endpoint
- [ ] M3: RAG pipeline — embed → Weaviate search → context build → LLM SQL gen → Trino exec → stream answer
- [ ] M3: Conversation history (last N messages passed as context window per session)
- [ ] M3: Visualization spec auto-generation based on result shape
- [ ] M3: Ollama/vLLM container for self-hosted LLM (self mode)
- [ ] M3: ServiceEndpoint integration for external LLM (OpenAI/Anthropic in external mode)
- [ ] M3: Embeddable widget token + config API
- [ ] M4: Chat page UI (session sidebar + streaming message thread + inline visualizations)
- [ ] M4: Floating chat panel accessible from all pages
- [ ] M4: Embeddable `embed.js` widget

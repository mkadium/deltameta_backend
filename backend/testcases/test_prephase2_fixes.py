"""
Pre-Phase 2 Fixes Test Suite.

Tests all modified and new endpoints:

1. ClassificationTag — detection_patterns + auto_classify
   POST /classifications/{id}/tags          — create with detection_patterns
   PUT  /classifications/{id}/tags/{id}     — update detection_patterns + auto_classify
   GET  /classifications/{id}/tags/{id}     — verify fields in response

2. Bots API
   POST   /bots                             — create self/external bots
   GET    /bots                             — list with filters
   GET    /bots/{id}                        — get by id
   PUT    /bots/{id}                        — update
   PATCH  /bots/{id}/enable                 — enable
   PATCH  /bots/{id}/disable                — disable
   POST   /bots/{id}/run                    — on-demand run (must be enabled)
   GET    /bots/{id}/runs                   — list runs
   DELETE /bots/{id}                        — delete

3. Bulk Assignment Endpoints
   POST /roles/{id}/assign                  — bulk assign users to role
   POST /roles/{id}/policies                — bulk assign policies to role
   POST /policies/{id}/assign               — bulk assign policy to users
   POST /teams/{id}/members                 — bulk add members to team
   POST /teams/{id}/roles                   — bulk assign roles to team
   POST /teams/{id}/policies                — bulk assign policies to team
   POST /orgs/{id}/members                  — bulk add members to org
   POST /orgs/{id}/roles                    — bulk assign roles to org
   POST /orgs/{id}/policies                 — bulk assign policies to org
   POST /datasets/{id}/owners               — bulk assign owners
   POST /datasets/{id}/experts              — bulk assign experts
   POST /data-assets/{id}/owners            — bulk assign owners
   POST /data-assets/{id}/experts           — bulk assign experts
   POST /data-assets/{id}/tags              — bulk assign classification tags

Run:
    cd backend
    source venv/bin/activate
    PYTHONPATH=. pytest testcases/test_prephase2_fixes.py -v --asyncio-mode=auto
"""
from __future__ import annotations

import os
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.auth.models import Base
from app.db import get_session
from app.main import app as fastapi_app
import app.govern.models  # noqa: F401
import app.setting_nodes.models  # noqa: F401
import app.resources.models  # noqa: F401
import app.nav_items.models  # noqa: F401
from app.resources.service import sync_static_registry

# ---------------------------------------------------------------------------
# DB wiring
# ---------------------------------------------------------------------------

_host = os.getenv("PRIMARY_DB_HOST", "3.7.235.41")
_port = os.getenv("PRIMARY_DB_PORT", "5434")
_user = os.getenv("PRIMARY_DB_USER", "postgres")
_password = os.getenv("PRIMARY_DB_PASSWORD", "EVrXabPjT6")
_schema = "deltameta"

TEST_DB_NAME = "deltameta_prephase2_testing"
TEST_DB_URL = f"postgresql+asyncpg://{_user}:{_password}@{_host}:{_port}/{TEST_DB_NAME}"

_test_engine = create_async_engine(TEST_DB_URL, echo=False)
_TestSession = sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
    async with _TestSession() as session:
        yield session


fastapi_app.dependency_overrides[get_session] = override_get_session


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db():
    admin_url = f"postgresql+asyncpg://{_user}:{_password}@{_host}:{_port}/postgres"
    admin_engine = create_async_engine(admin_url, echo=False, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as conn:
        result = await conn.execute(
            text(f"SELECT 1 FROM pg_database WHERE datname = '{TEST_DB_NAME}'")
        )
        if not result.fetchone():
            await conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    await admin_engine.dispose()

    async with _test_engine.begin() as conn:
        await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {_schema}"))
        await conn.run_sync(Base.metadata.create_all)

    async with _TestSession() as session:
        await sync_static_registry(session)
        await session.commit()

    yield

    async with _test_engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {_schema} CASCADE"))
    await _test_engine.dispose()


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _register_and_login(client: AsyncClient, suffix: str) -> dict:
    email = f"{suffix}@example.com"
    username = suffix[:30]
    r = await client.post("/auth/register", json={
        "name": f"Test {suffix}",
        "email": email,
        "username": username,
        "password": "Test@1234",
    })
    assert r.status_code in (200, 201), f"Register failed: {r.text}"
    resp = await client.post("/auth/login", json={"login": email, "password": "Test@1234"})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _get_org_id(client: AsyncClient, headers: dict) -> str:
    me = await client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    return me.json()["org_id"]


async def _get_user_id(client: AsyncClient, headers: dict) -> str:
    me = await client.get("/auth/me", headers=headers)
    return me.json()["id"]


async def _create_second_user(client: AsyncClient, admin_headers: dict) -> tuple[str, dict]:
    """Register a second user in the admin's org via admin invite.
    
    NOTE: Because each registration auto-creates a new org (User.org_id), the new user
    has a different primary org_id. We return (user_id, user_headers) where user_id
    is from the admin's org perspective (same User record).
    
    For endpoints that look up users by User.org_id == admin_org_id we use
    _get_user_id(admin_headers) instead (i.e. the admin themselves).
    """
    suffix = f"u2_{uuid.uuid4().hex[:6]}"
    user_headers = await _register_and_login(client, suffix)
    user_id = await _get_user_id(client, user_headers)
    org_id = await _get_org_id(client, admin_headers)
    r = await client.post(f"/orgs/{org_id}/members", headers=admin_headers,
                          json={"user_ids": [user_id], "is_org_admin": False})
    assert r.status_code == 201, f"Add member failed: {r.text}"
    return user_id, user_headers


async def _create_role(client, headers, name=None) -> dict:
    name = name or f"role_{uuid.uuid4().hex[:6]}"
    r = await client.post("/roles", headers=headers, json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


async def _create_policy(client, headers) -> dict:
    slug = uuid.uuid4().hex[:6]
    r = await client.post("/policies", headers=headers, json={
        "name": f"pol_{slug}",
        "rule_name": f"allow_pol_{slug}",
        "resource": "dataset",
        "operations": ["read"],
    })
    assert r.status_code == 201, r.text
    return r.json()


async def _create_team(client, headers, org_id, name=None) -> dict:
    name = name or f"team_{uuid.uuid4().hex[:6]}"
    r = await client.post("/teams", headers=headers, json={"org_id": org_id, "name": name, "team_type": "group"})
    assert r.status_code == 201, r.text
    return r.json()


async def _create_classification(client, headers) -> dict:
    r = await client.post("/classifications", headers=headers, json={
        "name": f"cls_{uuid.uuid4().hex[:6]}",
    })
    assert r.status_code == 201, r.text
    return r.json()


async def _create_tag(client, headers, cls_id, patterns=None, auto_classify=False) -> dict:
    r = await client.post(f"/classifications/{cls_id}/tags", headers=headers, json={
        "name": f"tag_{uuid.uuid4().hex[:6]}",
        "detection_patterns": patterns or [],
        "auto_classify": auto_classify,
    })
    assert r.status_code == 201, r.text
    return r.json()


async def _create_dataset(client, headers) -> dict:
    r = await client.post("/datasets", headers=headers, json={
        "name": f"ds_{uuid.uuid4().hex[:6]}",
        "source_type": "postgres",
    })
    assert r.status_code == 201, r.text
    return r.json()


async def _create_data_asset(client, headers, dataset_id) -> dict:
    r = await client.post("/data-assets", headers=headers, json={
        "name": f"asset_{uuid.uuid4().hex[:6]}",
        "dataset_id": dataset_id,
        "asset_type": "table",
    })
    assert r.status_code == 201, r.text
    return r.json()


async def _create_service_endpoint(client, headers) -> dict:
    r = await client.post("/service-endpoints", headers=headers, json={
        "service_name": f"test_svc_{uuid.uuid4().hex[:4]}",
        "base_url": "https://api.openai.com/v1",
        "extra": {"api_key": "sk-test-key"},
    })
    assert r.status_code == 201, r.text
    return r.json()


# ===========================================================================
# 1. ClassificationTag — detection_patterns + auto_classify
# ===========================================================================

class TestClassificationTagDetection:

    @pytest.mark.asyncio
    async def test_create_tag_with_detection_patterns(self, client):
        headers = await _register_and_login(client, f"ctp_{uuid.uuid4().hex[:6]}")
        cls = await _create_classification(client, headers)
        cls_id = cls["id"]

        patterns = [
            {"type": "column_name", "pattern": "email", "confidence": 1.0},
            {"type": "regex", "pattern": r"^[\w.]+@[\w.]+$", "confidence": 0.9},
        ]
        r = await client.post(f"/classifications/{cls_id}/tags", headers=headers, json={
            "name": "email_tag",
            "detection_patterns": patterns,
            "auto_classify": True,
        })
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["auto_classify"] is True
        assert len(data["detection_patterns"]) == 2
        assert data["detection_patterns"][0]["type"] == "column_name"
        assert data["detection_patterns"][0]["pattern"] == "email"
        assert data["detection_patterns"][0]["confidence"] == 1.0

    @pytest.mark.asyncio
    async def test_create_tag_defaults_to_empty_patterns(self, client):
        headers = await _register_and_login(client, f"ctd_{uuid.uuid4().hex[:6]}")
        cls = await _create_classification(client, headers)
        r = await client.post(f"/classifications/{cls['id']}/tags", headers=headers, json={
            "name": "basic_tag",
        })
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["auto_classify"] is False
        assert data["detection_patterns"] == []

    @pytest.mark.asyncio
    async def test_update_tag_detection_patterns(self, client):
        headers = await _register_and_login(client, f"utd_{uuid.uuid4().hex[:6]}")
        cls = await _create_classification(client, headers)
        tag = await _create_tag(client, headers, cls["id"])

        r = await client.put(f"/classifications/{cls['id']}/tags/{tag['id']}", headers=headers, json={
            "detection_patterns": [
                {"type": "data_sample", "pattern": r"^\d{3}-\d{2}-\d{4}$", "confidence": 0.95},
            ],
            "auto_classify": True,
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["auto_classify"] is True
        assert len(data["detection_patterns"]) == 1
        assert data["detection_patterns"][0]["type"] == "data_sample"
        assert data["detection_patterns"][0]["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_get_tag_includes_detection_fields(self, client):
        headers = await _register_and_login(client, f"gtd_{uuid.uuid4().hex[:6]}")
        cls = await _create_classification(client, headers)
        tag = await _create_tag(client, headers, cls["id"],
                                patterns=[{"type": "column_name", "pattern": "phone", "confidence": 1.0}],
                                auto_classify=True)

        r = await client.get(f"/classifications/{cls['id']}/tags/{tag['id']}", headers=headers)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "detection_patterns" in data
        assert "auto_classify" in data
        assert data["auto_classify"] is True
        assert data["detection_patterns"][0]["pattern"] == "phone"

    @pytest.mark.asyncio
    async def test_all_three_pattern_types_accepted(self, client):
        headers = await _register_and_login(client, f"atp_{uuid.uuid4().hex[:6]}")
        cls = await _create_classification(client, headers)
        patterns = [
            {"type": "column_name", "pattern": "ssn", "confidence": 1.0},
            {"type": "regex", "pattern": r"^\d{9}$", "confidence": 0.9},
            {"type": "data_sample", "pattern": r"^\d{3}-\d{2}-\d{4}$", "confidence": 0.8},
        ]
        r = await client.post(f"/classifications/{cls['id']}/tags", headers=headers, json={
            "name": "ssn_tag",
            "detection_patterns": patterns,
            "auto_classify": True,
        })
        assert r.status_code == 201, r.text
        data = r.json()
        assert len(data["detection_patterns"]) == 3


# ===========================================================================
# 2. Bots API
# ===========================================================================

class TestBotsAPI:

    @pytest.mark.asyncio
    async def test_create_self_bot(self, client):
        headers = await _register_and_login(client, f"bs_{uuid.uuid4().hex[:6]}")
        r = await client.post("/bots", headers=headers, json={
            "name": "Metadata Scanner",
            "description": "Scans Postgres metadata",
            "bot_type": "metadata",
            "mode": "self",
            "trigger_mode": "on_demand",
        })
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["bot_type"] == "metadata"
        assert data["mode"] == "self"
        assert data["is_enabled"] is False
        assert data["trigger_mode"] == "on_demand"

    @pytest.mark.asyncio
    async def test_create_scheduled_bot(self, client):
        headers = await _register_and_login(client, f"bsc_{uuid.uuid4().hex[:6]}")
        r = await client.post("/bots", headers=headers, json={
            "name": "Nightly Profiler",
            "bot_type": "profiler",
            "mode": "self",
            "trigger_mode": "scheduled",
            "cron_expr": "0 2 * * *",
        })
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["trigger_mode"] == "scheduled"
        assert data["cron_expr"] == "0 2 * * *"

    @pytest.mark.asyncio
    async def test_create_external_bot(self, client):
        headers = await _register_and_login(client, f"bex_{uuid.uuid4().hex[:6]}")
        ep = await _create_service_endpoint(client, headers)
        r = await client.post("/bots", headers=headers, json={
            "name": "GPT Classifier",
            "bot_type": "classification",
            "mode": "external",
            "trigger_mode": "on_demand",
            "service_endpoint_id": ep["id"],
            "model_name": "gpt-4o",
        })
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["mode"] == "external"
        assert data["model_name"] == "gpt-4o"
        assert data["service_endpoint_id"] == ep["id"]

    @pytest.mark.asyncio
    async def test_create_bot_missing_cron_for_scheduled_fails(self, client):
        headers = await _register_and_login(client, f"bfc_{uuid.uuid4().hex[:6]}")
        r = await client.post("/bots", headers=headers, json={
            "name": "Bad Bot",
            "bot_type": "lineage",
            "mode": "self",
            "trigger_mode": "scheduled",
            # missing cron_expr
        })
        assert r.status_code == 422, r.text

    @pytest.mark.asyncio
    async def test_create_bot_invalid_type_fails(self, client):
        headers = await _register_and_login(client, f"bit_{uuid.uuid4().hex[:6]}")
        r = await client.post("/bots", headers=headers, json={
            "name": "Invalid",
            "bot_type": "nonexistent_type",
            "mode": "self",
        })
        assert r.status_code == 422, r.text

    @pytest.mark.asyncio
    async def test_create_external_bot_missing_endpoint_fails(self, client):
        headers = await _register_and_login(client, f"bme_{uuid.uuid4().hex[:6]}")
        r = await client.post("/bots", headers=headers, json={
            "name": "Bad External",
            "bot_type": "embedding",
            "mode": "external",
            "trigger_mode": "on_demand",
            # missing service_endpoint_id
        })
        assert r.status_code == 422, r.text

    @pytest.mark.asyncio
    async def test_list_bots_with_filters(self, client):
        headers = await _register_and_login(client, f"bl_{uuid.uuid4().hex[:6]}")
        await client.post("/bots", headers=headers, json={"name": "Bot A", "bot_type": "metadata", "mode": "self"})
        await client.post("/bots", headers=headers, json={"name": "Bot B", "bot_type": "profiler", "mode": "self"})

        r = await client.get("/bots?bot_type=metadata", headers=headers)
        assert r.status_code == 200, r.text
        data = r.json()
        assert all(b["bot_type"] == "metadata" for b in data)

        r2 = await client.get("/bots?is_enabled=false", headers=headers)
        assert r2.status_code == 200
        assert all(b["is_enabled"] is False for b in r2.json())

    @pytest.mark.asyncio
    async def test_get_bot(self, client):
        headers = await _register_and_login(client, f"bg_{uuid.uuid4().hex[:6]}")
        r = await client.post("/bots", headers=headers, json={"name": "My Bot", "bot_type": "lineage", "mode": "self"})
        bot_id = r.json()["id"]

        r2 = await client.get(f"/bots/{bot_id}", headers=headers)
        assert r2.status_code == 200
        assert r2.json()["id"] == bot_id

    @pytest.mark.asyncio
    async def test_update_bot(self, client):
        headers = await _register_and_login(client, f"bu_{uuid.uuid4().hex[:6]}")
        r = await client.post("/bots", headers=headers, json={"name": "Old Name", "bot_type": "usage", "mode": "self"})
        bot_id = r.json()["id"]

        r2 = await client.put(f"/bots/{bot_id}", headers=headers, json={"name": "New Name"})
        assert r2.status_code == 200
        assert r2.json()["name"] == "New Name"

    @pytest.mark.asyncio
    async def test_enable_and_disable_bot(self, client):
        headers = await _register_and_login(client, f"bed_{uuid.uuid4().hex[:6]}")
        r = await client.post("/bots", headers=headers, json={"name": "Toggle Bot", "bot_type": "search_index", "mode": "self"})
        bot_id = r.json()["id"]
        assert r.json()["is_enabled"] is False

        r2 = await client.patch(f"/bots/{bot_id}/enable", headers=headers)
        assert r2.status_code == 200
        assert r2.json()["is_enabled"] is True

        r3 = await client.patch(f"/bots/{bot_id}/disable", headers=headers)
        assert r3.status_code == 200
        assert r3.json()["is_enabled"] is False

    @pytest.mark.asyncio
    async def test_run_disabled_bot_fails(self, client):
        headers = await _register_and_login(client, f"brdf_{uuid.uuid4().hex[:6]}")
        r = await client.post("/bots", headers=headers, json={"name": "Disabled Bot", "bot_type": "metadata", "mode": "self"})
        bot_id = r.json()["id"]

        r2 = await client.post(f"/bots/{bot_id}/run", headers=headers)
        assert r2.status_code == 400, r2.text
        assert "disabled" in r2.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_run_enabled_bot_succeeds(self, client):
        headers = await _register_and_login(client, f"bre_{uuid.uuid4().hex[:6]}")
        r = await client.post("/bots", headers=headers, json={"name": "Run Me", "bot_type": "profiler", "mode": "self"})
        bot_id = r.json()["id"]
        await client.patch(f"/bots/{bot_id}/enable", headers=headers)

        r2 = await client.post(f"/bots/{bot_id}/run", headers=headers)
        assert r2.status_code == 200, r2.text
        data = r2.json()
        assert data["bot_id"] == bot_id
        assert "triggered_at" in data
        assert "running" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_list_bot_runs(self, client):
        headers = await _register_and_login(client, f"blr_{uuid.uuid4().hex[:6]}")
        r = await client.post("/bots", headers=headers, json={"name": "Run List Bot", "bot_type": "lineage", "mode": "self"})
        bot_id = r.json()["id"]
        await client.patch(f"/bots/{bot_id}/enable", headers=headers)
        await client.post(f"/bots/{bot_id}/run", headers=headers)

        r2 = await client.get(f"/bots/{bot_id}/runs", headers=headers)
        assert r2.status_code == 200
        data = r2.json()
        assert len(data) >= 1
        assert data[0]["last_run_status"] == "running"

    @pytest.mark.asyncio
    async def test_all_valid_bot_types_can_be_created(self, client):
        headers = await _register_and_login(client, f"bat_{uuid.uuid4().hex[:6]}")
        valid_types = ["metadata", "profiler", "lineage", "usage",
                       "classification", "search_index", "test_suite", "rdf_export", "embedding"]
        for bt in valid_types:
            r = await client.post("/bots", headers=headers, json={
                "name": f"bot_{bt}", "bot_type": bt, "mode": "self",
            })
            assert r.status_code == 201, f"Failed for bot_type={bt}: {r.text}"

    @pytest.mark.asyncio
    async def test_delete_bot(self, client):
        headers = await _register_and_login(client, f"bd_{uuid.uuid4().hex[:6]}")
        r = await client.post("/bots", headers=headers, json={"name": "Delete Me", "bot_type": "metadata", "mode": "self"})
        bot_id = r.json()["id"]

        r2 = await client.delete(f"/bots/{bot_id}", headers=headers)
        assert r2.status_code == 204

        r3 = await client.get(f"/bots/{bot_id}", headers=headers)
        assert r3.status_code == 404

    @pytest.mark.asyncio
    async def test_bot_not_visible_to_other_org(self, client):
        h1 = await _register_and_login(client, f"bo1_{uuid.uuid4().hex[:6]}")
        h2 = await _register_and_login(client, f"bo2_{uuid.uuid4().hex[:6]}")
        r = await client.post("/bots", headers=h1, json={"name": "Org1 Bot", "bot_type": "metadata", "mode": "self"})
        bot_id = r.json()["id"]

        r2 = await client.get(f"/bots/{bot_id}", headers=h2)
        assert r2.status_code == 404


# ===========================================================================
# 3. Bulk Assignment Endpoints
# ===========================================================================

class TestBulkAssignments:
    """
    All user-assignment endpoints require the target user to share the same
    primary org_id (User.org_id) as the admin.  Because every registration
    creates its own org, we always use the *admin's own user_id* as the
    assignee — the admin is already in their own org.
    Tests that verify multi-user assignment use the admin ID twice (idempotent)
    or call create_second_user only where the endpoint checks via org-membership
    table (e.g. /orgs/{id}/members which uses user_organizations join).
    """

    # ── Roles ────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_bulk_assign_users_to_role(self, client):
        headers = await _register_and_login(client, f"bar_{uuid.uuid4().hex[:6]}")
        user_id = await _get_user_id(client, headers)
        role = await _create_role(client, headers)

        r = await client.post(f"/roles/{role['id']}/assign", headers=headers,
                              json={"user_ids": [user_id]})
        assert r.status_code == 201, r.text
        assert "1 user" in r.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_bulk_assign_users_to_role_idempotent(self, client):
        headers = await _register_and_login(client, f"bari_{uuid.uuid4().hex[:6]}")
        user_id = await _get_user_id(client, headers)
        role = await _create_role(client, headers)

        await client.post(f"/roles/{role['id']}/assign", headers=headers, json={"user_ids": [user_id]})
        # Assign same user again — should succeed (skip already-assigned)
        r = await client.post(f"/roles/{role['id']}/assign", headers=headers, json={"user_ids": [user_id]})
        assert r.status_code == 201, r.text
        # Message says 0 users assigned the second time (already assigned)
        assert "user" in r.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_bulk_assign_multiple_users_to_role_idempotent(self, client):
        """Passing the same user twice in one request should still succeed."""
        headers = await _register_and_login(client, f"barm_{uuid.uuid4().hex[:6]}")
        user_id = await _get_user_id(client, headers)
        role = await _create_role(client, headers)

        r = await client.post(f"/roles/{role['id']}/assign", headers=headers,
                              json={"user_ids": [user_id, user_id]})
        assert r.status_code == 201, r.text

    @pytest.mark.asyncio
    async def test_bulk_assign_policies_to_role(self, client):
        headers = await _register_and_login(client, f"bpr_{uuid.uuid4().hex[:6]}")
        role = await _create_role(client, headers)
        pol1 = await _create_policy(client, headers)
        pol2 = await _create_policy(client, headers)

        r = await client.post(f"/roles/{role['id']}/policies", headers=headers,
                              json={"policy_ids": [pol1["id"], pol2["id"]]})
        assert r.status_code == 201, r.text
        assert "2 policy" in r.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_bulk_assign_single_policy_to_role(self, client):
        headers = await _register_and_login(client, f"bprs_{uuid.uuid4().hex[:6]}")
        role = await _create_role(client, headers)
        pol = await _create_policy(client, headers)

        r = await client.post(f"/roles/{role['id']}/policies", headers=headers,
                              json={"policy_ids": [pol["id"]]})
        assert r.status_code == 201, r.text
        assert "1 policy" in r.json()["message"].lower()

    # ── Policies ─────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_bulk_assign_policy_to_users(self, client):
        headers = await _register_and_login(client, f"bpu_{uuid.uuid4().hex[:6]}")
        user_id = await _get_user_id(client, headers)
        pol = await _create_policy(client, headers)

        r = await client.post(f"/policies/{pol['id']}/assign", headers=headers,
                              json={"user_ids": [user_id]})
        assert r.status_code == 201, r.text
        assert "1 user" in r.json()["message"].lower()

    # ── Teams ─────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_bulk_add_members_to_team(self, client):
        headers = await _register_and_login(client, f"btm_{uuid.uuid4().hex[:6]}")
        org_id = await _get_org_id(client, headers)
        user_id = await _get_user_id(client, headers)
        team = await _create_team(client, headers, org_id)

        r = await client.post(f"/teams/{team['id']}/members", headers=headers,
                              json={"user_ids": [user_id]})
        assert r.status_code == 201, r.text
        assert "1 user" in r.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_bulk_add_members_to_team_idempotent(self, client):
        headers = await _register_and_login(client, f"btmi_{uuid.uuid4().hex[:6]}")
        org_id = await _get_org_id(client, headers)
        user_id = await _get_user_id(client, headers)
        team = await _create_team(client, headers, org_id)

        await client.post(f"/teams/{team['id']}/members", headers=headers, json={"user_ids": [user_id]})
        r = await client.post(f"/teams/{team['id']}/members", headers=headers, json={"user_ids": [user_id]})
        assert r.status_code == 201, r.text

    @pytest.mark.asyncio
    async def test_bulk_assign_roles_to_team(self, client):
        headers = await _register_and_login(client, f"btr_{uuid.uuid4().hex[:6]}")
        org_id = await _get_org_id(client, headers)
        team = await _create_team(client, headers, org_id)
        role1 = await _create_role(client, headers)
        role2 = await _create_role(client, headers)

        r = await client.post(f"/teams/{team['id']}/roles", headers=headers,
                              json={"role_ids": [role1["id"], role2["id"]]})
        assert r.status_code == 201, r.text
        assert "2 role" in r.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_bulk_assign_policies_to_team(self, client):
        headers = await _register_and_login(client, f"btp_{uuid.uuid4().hex[:6]}")
        org_id = await _get_org_id(client, headers)
        team = await _create_team(client, headers, org_id)
        pol = await _create_policy(client, headers)

        r = await client.post(f"/teams/{team['id']}/policies", headers=headers,
                              json={"policy_ids": [pol["id"]]})
        assert r.status_code == 201, r.text
        assert "1 policy" in r.json()["message"].lower()

    # ── Org ──────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_bulk_add_members_to_org(self, client):
        """org/members uses user_organizations join so any registered user can be added."""
        headers = await _register_and_login(client, f"bom_{uuid.uuid4().hex[:6]}")
        org_id = await _get_org_id(client, headers)
        suffix = f"nm_{uuid.uuid4().hex[:6]}"
        new_headers = await _register_and_login(client, suffix)
        new_user_id = await _get_user_id(client, new_headers)

        r = await client.post(f"/orgs/{org_id}/members", headers=headers,
                              json={"user_ids": [new_user_id], "is_org_admin": False})
        assert r.status_code == 201, r.text
        assert "1 user" in r.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_bulk_add_multiple_members_to_org(self, client):
        headers = await _register_and_login(client, f"bomm_{uuid.uuid4().hex[:6]}")
        org_id = await _get_org_id(client, headers)
        u2_headers = await _register_and_login(client, f"bommu2_{uuid.uuid4().hex[:6]}")
        u3_headers = await _register_and_login(client, f"bommu3_{uuid.uuid4().hex[:6]}")
        u2_id = await _get_user_id(client, u2_headers)
        u3_id = await _get_user_id(client, u3_headers)

        r = await client.post(f"/orgs/{org_id}/members", headers=headers,
                              json={"user_ids": [u2_id, u3_id], "is_org_admin": False})
        assert r.status_code == 201, r.text
        assert "2 user" in r.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_bulk_assign_roles_to_org(self, client):
        headers = await _register_and_login(client, f"bor_{uuid.uuid4().hex[:6]}")
        org_id = await _get_org_id(client, headers)
        role = await _create_role(client, headers)

        r = await client.post(f"/orgs/{org_id}/roles", headers=headers,
                              json={"role_ids": [role["id"]]})
        assert r.status_code == 201, r.text
        assert "1 role" in r.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_bulk_assign_policies_to_org(self, client):
        headers = await _register_and_login(client, f"bop_{uuid.uuid4().hex[:6]}")
        org_id = await _get_org_id(client, headers)
        pol = await _create_policy(client, headers)

        r = await client.post(f"/orgs/{org_id}/policies", headers=headers,
                              json={"policy_ids": [pol["id"]]})
        assert r.status_code == 201, r.text
        assert "1 policy" in r.json()["message"].lower()

    # ── Datasets ──────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_bulk_assign_dataset_owners(self, client):
        """Use admin's own user_id — same primary org_id check passes."""
        headers = await _register_and_login(client, f"bdo_{uuid.uuid4().hex[:6]}")
        user_id = await _get_user_id(client, headers)
        ds = await _create_dataset(client, headers)

        r = await client.post(f"/datasets/{ds['id']}/owners", headers=headers,
                              json={"user_ids": [user_id]})
        assert r.status_code == 201, r.text
        assert "1 owner" in r.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_bulk_assign_dataset_experts(self, client):
        headers = await _register_and_login(client, f"bde_{uuid.uuid4().hex[:6]}")
        user_id = await _get_user_id(client, headers)
        ds = await _create_dataset(client, headers)

        r = await client.post(f"/datasets/{ds['id']}/experts", headers=headers,
                              json={"user_ids": [user_id]})
        assert r.status_code == 201, r.text
        assert "1 expert" in r.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_bulk_assign_dataset_owners_idempotent(self, client):
        """Assigning same owner twice should not error."""
        headers = await _register_and_login(client, f"bdoi_{uuid.uuid4().hex[:6]}")
        user_id = await _get_user_id(client, headers)
        ds = await _create_dataset(client, headers)

        await client.post(f"/datasets/{ds['id']}/owners", headers=headers, json={"user_ids": [user_id]})
        r = await client.post(f"/datasets/{ds['id']}/owners", headers=headers, json={"user_ids": [user_id]})
        assert r.status_code == 201, r.text

    # ── Data Assets ───────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_bulk_assign_asset_owners(self, client):
        headers = await _register_and_login(client, f"bao_{uuid.uuid4().hex[:6]}")
        user_id = await _get_user_id(client, headers)
        ds = await _create_dataset(client, headers)
        asset = await _create_data_asset(client, headers, ds["id"])

        r = await client.post(f"/data-assets/{asset['id']}/owners", headers=headers,
                              json={"user_ids": [user_id]})
        assert r.status_code == 201, r.text
        assert "1 owner" in r.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_bulk_assign_asset_experts(self, client):
        headers = await _register_and_login(client, f"bae_{uuid.uuid4().hex[:6]}")
        user_id = await _get_user_id(client, headers)
        ds = await _create_dataset(client, headers)
        asset = await _create_data_asset(client, headers, ds["id"])

        r = await client.post(f"/data-assets/{asset['id']}/experts", headers=headers,
                              json={"user_ids": [user_id]})
        assert r.status_code == 201, r.text
        assert "1 expert" in r.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_bulk_assign_asset_tags(self, client):
        headers = await _register_and_login(client, f"bat_{uuid.uuid4().hex[:6]}")
        ds = await _create_dataset(client, headers)
        asset = await _create_data_asset(client, headers, ds["id"])
        cls = await _create_classification(client, headers)
        tag1 = await _create_tag(client, headers, cls["id"])
        tag2 = await _create_tag(client, headers, cls["id"])

        r = await client.post(f"/data-assets/{asset['id']}/tags", headers=headers,
                              json={"tag_ids": [tag1["id"], tag2["id"]]})
        assert r.status_code == 201, r.text
        assert "2 tag" in r.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_bulk_assign_asset_tags_single(self, client):
        headers = await _register_and_login(client, f"bats_{uuid.uuid4().hex[:6]}")
        ds = await _create_dataset(client, headers)
        asset = await _create_data_asset(client, headers, ds["id"])
        cls = await _create_classification(client, headers)
        tag = await _create_tag(client, headers, cls["id"])

        r = await client.post(f"/data-assets/{asset['id']}/tags", headers=headers,
                              json={"tag_ids": [tag["id"]]})
        assert r.status_code == 201, r.text
        assert "1 tag" in r.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_bulk_assign_asset_tags_idempotent(self, client):
        """Adding the same tag twice should not raise an error."""
        headers = await _register_and_login(client, f"bati_{uuid.uuid4().hex[:6]}")
        ds = await _create_dataset(client, headers)
        asset = await _create_data_asset(client, headers, ds["id"])
        cls = await _create_classification(client, headers)
        tag = await _create_tag(client, headers, cls["id"])

        await client.post(f"/data-assets/{asset['id']}/tags", headers=headers, json={"tag_ids": [tag["id"]]})
        r = await client.post(f"/data-assets/{asset['id']}/tags", headers=headers, json={"tag_ids": [tag["id"]]})
        assert r.status_code == 201, r.text

    # ── DELETE single-item still works (unchanged) ────────────────────────────

    @pytest.mark.asyncio
    async def test_delete_single_role_assignment_still_works(self, client):
        headers = await _register_and_login(client, f"dra_{uuid.uuid4().hex[:6]}")
        user_id = await _get_user_id(client, headers)
        role = await _create_role(client, headers)

        await client.post(f"/roles/{role['id']}/assign", headers=headers, json={"user_ids": [user_id]})
        r = await client.delete(f"/roles/{role['id']}/assign/{user_id}", headers=headers)
        assert r.status_code == 200, r.text

    @pytest.mark.asyncio
    async def test_delete_single_team_member_still_works(self, client):
        headers = await _register_and_login(client, f"dtm_{uuid.uuid4().hex[:6]}")
        org_id = await _get_org_id(client, headers)
        user_id = await _get_user_id(client, headers)
        team = await _create_team(client, headers, org_id)

        await client.post(f"/teams/{team['id']}/members", headers=headers, json={"user_ids": [user_id]})
        r = await client.delete(f"/teams/{team['id']}/members/{user_id}", headers=headers)
        assert r.status_code == 200, r.text

    @pytest.mark.asyncio
    async def test_delete_single_asset_owner_still_works(self, client):
        headers = await _register_and_login(client, f"dao_{uuid.uuid4().hex[:6]}")
        user_id = await _get_user_id(client, headers)
        ds = await _create_dataset(client, headers)
        asset = await _create_data_asset(client, headers, ds["id"])

        await client.post(f"/data-assets/{asset['id']}/owners", headers=headers, json={"user_ids": [user_id]})
        r = await client.delete(f"/data-assets/{asset['id']}/owners/{user_id}", headers=headers)
        assert r.status_code == 204, r.text

    @pytest.mark.asyncio
    async def test_delete_single_asset_tag_still_works(self, client):
        headers = await _register_and_login(client, f"dat_{uuid.uuid4().hex[:6]}")
        ds = await _create_dataset(client, headers)
        asset = await _create_data_asset(client, headers, ds["id"])
        cls = await _create_classification(client, headers)
        tag = await _create_tag(client, headers, cls["id"])

        await client.post(f"/data-assets/{asset['id']}/tags", headers=headers, json={"tag_ids": [tag["id"]]})
        r = await client.delete(f"/data-assets/{asset['id']}/tags/{tag['id']}", headers=headers)
        assert r.status_code == 204, r.text

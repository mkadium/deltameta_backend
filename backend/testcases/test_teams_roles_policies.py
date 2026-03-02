"""
Teams, Roles, Policies, Domains, Org Preferences, and Subscriptions API test cases.

Prerequisites:
    Same PostgreSQL test database as test_auth.py (deltameta_testing).

Run with:
    cd backend
    source venv/bin/activate
    pytest testcases/test_teams_roles_policies.py -v --asyncio-mode=auto
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
from app.main import app

# ---------------------------------------------------------------------------
# Test DB setup
# ---------------------------------------------------------------------------

_host = os.getenv("PRIMARY_DB_HOST", "3.7.235.41")
_port = os.getenv("PRIMARY_DB_PORT", "5434")
_user = os.getenv("PRIMARY_DB_USER", "postgres")
_password = os.getenv("PRIMARY_DB_PASSWORD", "EVrXabPjT6")
_schema = "deltameta"

TEST_DB_NAME = "deltameta_testing"
TEST_DB_URL = f"postgresql+asyncpg://{_user}:{_password}@{_host}:{_port}/{TEST_DB_NAME}"

_test_engine = create_async_engine(TEST_DB_URL, echo=False)
_TestSession = sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
    async with _TestSession() as session:
        yield session


app.dependency_overrides[get_session] = override_get_session


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

    yield

    async with _test_engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {_schema} CASCADE"))

    await _test_engine.dispose()


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Helper: register + login, return auth header
# ---------------------------------------------------------------------------

async def _register_and_login(client: AsyncClient, suffix: str) -> dict:
    email = f"user_{suffix}@test.com"
    username = f"user_{suffix}"
    await client.post("/auth/register", json={
        "name": f"Test {suffix}",
        "email": email,
        "username": username,
        "password": "Test@1234",
    })
    resp = await client.post("/auth/login", json={"login": email, "password": "Test@1234"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _get_org_id(client: AsyncClient, headers: dict) -> str:
    me = await client.get("/auth/me", headers=headers)
    return me.json()["org_id"]


# ===========================================================================
# SUBJECT AREA TESTS (formerly /domains — now canonical route is /subject-areas)
# ===========================================================================

class TestDomains:
    async def test_list_domains_empty(self, client: AsyncClient):
        headers = await _register_and_login(client, f"domlist_{uuid.uuid4().hex[:6]}")
        resp = await client.get("/subject-areas", headers=headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_create_domain(self, client: AsyncClient):
        headers = await _register_and_login(client, f"domcr_{uuid.uuid4().hex[:6]}")
        resp = await client.post("/subject-areas", headers=headers, json={
            "name": "Engineering",
            "description": "Engineering domain",
            "domain_type": "Technical",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Engineering"
        assert data["is_active"] is True

    async def test_create_domain_duplicate_name(self, client: AsyncClient):
        headers = await _register_and_login(client, f"domdup_{uuid.uuid4().hex[:6]}")
        payload = {"name": "Finance"}
        await client.post("/subject-areas", headers=headers, json=payload)
        resp = await client.post("/subject-areas", headers=headers, json=payload)
        assert resp.status_code == 409

    async def test_get_domain(self, client: AsyncClient):
        headers = await _register_and_login(client, f"domget_{uuid.uuid4().hex[:6]}")
        create_resp = await client.post("/subject-areas", headers=headers, json={"name": "Sales"})
        domain_id = create_resp.json()["id"]
        resp = await client.get(f"/subject-areas/{domain_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == domain_id

    async def test_update_domain(self, client: AsyncClient):
        headers = await _register_and_login(client, f"domupd_{uuid.uuid4().hex[:6]}")
        create_resp = await client.post("/subject-areas", headers=headers, json={"name": "HR"})
        domain_id = create_resp.json()["id"]
        resp = await client.put(f"/subject-areas/{domain_id}", headers=headers, json={"description": "Human Resources"})
        assert resp.status_code == 200
        assert resp.json()["description"] == "Human Resources"

    async def test_delete_domain(self, client: AsyncClient):
        headers = await _register_and_login(client, f"domdel_{uuid.uuid4().hex[:6]}")
        create_resp = await client.post("/subject-areas", headers=headers, json={"name": "Marketing"})
        domain_id = create_resp.json()["id"]
        resp = await client.delete(f"/subject-areas/{domain_id}", headers=headers)
        assert resp.status_code == 204
        get_resp = await client.get(f"/subject-areas/{domain_id}", headers=headers)
        assert get_resp.status_code == 404

    async def test_get_nonexistent_domain_returns_404(self, client: AsyncClient):
        headers = await _register_and_login(client, f"dom404_{uuid.uuid4().hex[:6]}")
        resp = await client.get(f"/subject-areas/{uuid.uuid4()}", headers=headers)
        assert resp.status_code == 404


# ===========================================================================
# TEAM TESTS
# ===========================================================================

class TestTeams:
    async def test_create_team_no_parent(self, client: AsyncClient):
        headers = await _register_and_login(client, f"team1_{uuid.uuid4().hex[:6]}")
        org_id = await _get_org_id(client, headers)
        resp = await client.post("/teams", headers=headers, json={
            "org_id": org_id,
            "name": "Platform Team",
            "team_type": "group",
            "public_team_view": True,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Platform Team"
        assert data["parent_team_id"] is None

    async def test_create_team_with_parent(self, client: AsyncClient):
        headers = await _register_and_login(client, f"team2_{uuid.uuid4().hex[:6]}")
        org_id = await _get_org_id(client, headers)
        bu_resp = await client.post("/teams", headers=headers, json={
            "org_id": org_id,
            "name": "Technology BU",
            "team_type": "business_unit",
        })
        bu_id = bu_resp.json()["id"]

        div_resp = await client.post("/teams", headers=headers, json={
            "org_id": org_id,
            "name": "Engineering Division",
            "team_type": "division",
            "parent_team_id": bu_id,
        })
        assert div_resp.status_code == 201
        assert div_resp.json()["parent_team_id"] == bu_id

    async def test_team_hierarchy_endpoint(self, client: AsyncClient):
        headers = await _register_and_login(client, f"teamh_{uuid.uuid4().hex[:6]}")
        org_id = await _get_org_id(client, headers)
        bu_resp = await client.post("/teams", headers=headers, json={
            "org_id": org_id,
            "name": "Corp BU",
            "team_type": "business_unit",
        })
        bu_id = bu_resp.json()["id"]

        await client.post("/teams", headers=headers, json={
            "org_id": org_id,
            "name": "Corp Div",
            "team_type": "division",
            "parent_team_id": bu_id,
        })

        resp = await client.get(f"/teams/{bu_id}/hierarchy", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == bu_id
        assert len(data["children"]) >= 1

    async def test_list_teams_filter_by_type(self, client: AsyncClient):
        headers = await _register_and_login(client, f"teamf_{uuid.uuid4().hex[:6]}")
        org_id = await _get_org_id(client, headers)
        await client.post("/teams", headers=headers, json={"org_id": org_id, "name": "BU Alpha", "team_type": "business_unit"})
        await client.post("/teams", headers=headers, json={"org_id": org_id, "name": "Group Beta", "team_type": "group"})

        resp = await client.get("/teams?team_type=business_unit", headers=headers)
        assert resp.status_code == 200
        types = [t["team_type"] for t in resp.json()]
        assert all(t == "business_unit" for t in types)

    async def test_add_and_remove_member(self, client: AsyncClient):
        suffix = uuid.uuid4().hex[:6]
        admin_headers = await _register_and_login(client, f"adm_{suffix}")
        org_id = await _get_org_id(client, admin_headers)

        # Create a second user (registers in same app state, but separate org)
        # Use admin user's own ID as member since we're single-org per registration
        team_resp = await client.post("/teams", headers=admin_headers, json={
            "org_id": org_id,
            "name": f"Members Team {suffix}",
            "team_type": "group",
        })
        team_id = team_resp.json()["id"]

        me_resp = await client.get("/auth/me", headers=admin_headers)
        user_id = me_resp.json()["id"]

        # Add
        add_resp = await client.post(f"/teams/{team_id}/members/{user_id}", headers=admin_headers)
        assert add_resp.status_code == 200

        # List
        members_resp = await client.get(f"/teams/{team_id}/members", headers=admin_headers)
        assert any(m["id"] == user_id for m in members_resp.json())

        # Remove
        remove_resp = await client.delete(f"/teams/{team_id}/members/{user_id}", headers=admin_headers)
        assert remove_resp.status_code == 200

        members_after = await client.get(f"/teams/{team_id}/members", headers=admin_headers)
        assert not any(m["id"] == user_id for m in members_after.json())

    async def test_delete_team(self, client: AsyncClient):
        headers = await _register_and_login(client, f"teamdel_{uuid.uuid4().hex[:6]}")
        org_id = await _get_org_id(client, headers)
        create_resp = await client.post("/teams", headers=headers, json={"org_id": org_id, "name": "To Delete", "team_type": "group"})
        team_id = create_resp.json()["id"]
        del_resp = await client.delete(f"/teams/{team_id}", headers=headers)
        assert del_resp.status_code == 200
        get_resp = await client.get(f"/teams/{team_id}", headers=headers)
        assert get_resp.status_code == 404


# ===========================================================================
# POLICY TESTS
# ===========================================================================

class TestPolicies:
    async def test_create_policy(self, client: AsyncClient):
        headers = await _register_and_login(client, f"pol1_{uuid.uuid4().hex[:6]}")
        # Sync registry first so resource keys are available
        await client.post("/resources/sync", headers=headers)
        resp = await client.post("/policies", headers=headers, json={
            "name": "Read Dataset",
            "rule_name": "allow_read_dataset",
            "resource": "dataset",
            "operations": ["read"],
            "conditions": [{"attr": "isAdmin", "op": "=", "value": "false"}],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Read Dataset"
        assert "read" in data["operations"]

    async def test_create_policy_duplicate_name(self, client: AsyncClient):
        headers = await _register_and_login(client, f"poldup_{uuid.uuid4().hex[:6]}")
        await client.post("/resources/sync", headers=headers)
        payload = {"name": "Duplicate Policy", "rule_name": "rule1", "resource": "domain", "operations": ["read"], "conditions": []}
        await client.post("/policies", headers=headers, json=payload)
        resp = await client.post("/policies", headers=headers, json=payload)
        assert resp.status_code == 409

    async def test_update_policy(self, client: AsyncClient):
        headers = await _register_and_login(client, f"polupd_{uuid.uuid4().hex[:6]}")
        await client.post("/resources/sync", headers=headers)
        create_resp = await client.post("/policies", headers=headers, json={
            "name": "Edit Policy",
            "rule_name": "rule_edit",
            "resource": "user",
            "operations": ["read"],
            "conditions": [],
        })
        assert create_resp.status_code == 201, create_resp.text
        policy_id = create_resp.json()["id"]
        resp = await client.put(f"/policies/{policy_id}", headers=headers, json={
            "operations": ["read", "create", "update"],
        })
        assert resp.status_code == 200
        assert "create" in resp.json()["operations"]

    async def test_delete_policy(self, client: AsyncClient):
        headers = await _register_and_login(client, f"poldel_{uuid.uuid4().hex[:6]}")
        await client.post("/resources/sync", headers=headers)
        create_resp = await client.post("/policies", headers=headers, json={
            "name": "Delete Me Policy",
            "rule_name": "del_rule",
            "resource": "team",
            "operations": ["read"],
            "conditions": [],
        })
        assert create_resp.status_code == 201, create_resp.text
        policy_id = create_resp.json()["id"]
        del_resp = await client.delete(f"/policies/{policy_id}", headers=headers)
        assert del_resp.status_code == 200
        get_resp = await client.get(f"/policies/{policy_id}", headers=headers)
        assert get_resp.status_code == 404

    async def test_policy_conditions_structure(self, client: AsyncClient):
        headers = await _register_and_login(client, f"polcond_{uuid.uuid4().hex[:6]}")
        await client.post("/resources/sync", headers=headers)
        resp = await client.post("/policies", headers=headers, json={
            "name": "ABAC Policy",
            "rule_name": "abac_rule",
            "resource": "dataset",
            "operations": ["read", "create"],
            "conditions": [
                {"attr": "team", "op": "=", "value": "data-engineers"},
                {"attr": "isAdmin", "op": "!=", "value": "true"},
            ],
        })
        assert resp.status_code == 201
        conditions = resp.json()["conditions"]
        assert len(conditions) == 2
        assert conditions[0]["attr"] == "team"


# ===========================================================================
# ROLE TESTS
# ===========================================================================

class TestRoles:
    async def test_create_role(self, client: AsyncClient):
        headers = await _register_and_login(client, f"role1_{uuid.uuid4().hex[:6]}")
        resp = await client.post("/roles", headers=headers, json={
            "name": "Data Analyst",
            "description": "Can read catalog data",
            "policy_ids": [],
        })
        assert resp.status_code == 201
        assert resp.json()["name"] == "Data Analyst"
        assert resp.json()["is_system_role"] is False

    async def test_create_role_with_policy(self, client: AsyncClient):
        headers = await _register_and_login(client, f"role2_{uuid.uuid4().hex[:6]}")
        await client.post("/resources/sync", headers=headers)
        policy_resp = await client.post("/policies", headers=headers, json={
            "name": "Read All Users",
            "rule_name": "read_all_users_rule",
            "resource": "user",
            "operations": ["read"],
            "conditions": [],
        })
        assert policy_resp.status_code == 201, policy_resp.text
        policy_id = policy_resp.json()["id"]

        resp = await client.post("/roles", headers=headers, json={
            "name": "Viewer Role",
            "policy_ids": [policy_id],
        })
        assert resp.status_code == 201
        policies = resp.json()["policies"]
        assert any(p["id"] == policy_id for p in policies)

    async def test_assign_and_remove_role_from_user(self, client: AsyncClient):
        headers = await _register_and_login(client, f"role3_{uuid.uuid4().hex[:6]}")
        role_resp = await client.post("/roles", headers=headers, json={
            "name": "Admin Role",
            "policy_ids": [],
        })
        role_id = role_resp.json()["id"]
        me_resp = await client.get("/auth/me", headers=headers)
        user_id = me_resp.json()["id"]

        assign_resp = await client.post(f"/roles/{role_id}/assign/{user_id}", headers=headers)
        assert assign_resp.status_code == 200

        me_after = await client.get("/auth/me", headers=headers)
        assert any(r["id"] == role_id for r in me_after.json()["roles"])

        remove_resp = await client.delete(f"/roles/{role_id}/assign/{user_id}", headers=headers)
        assert remove_resp.status_code == 200

    async def test_delete_role(self, client: AsyncClient):
        headers = await _register_and_login(client, f"roledel_{uuid.uuid4().hex[:6]}")
        role_resp = await client.post("/roles", headers=headers, json={"name": "Temp Role", "policy_ids": []})
        role_id = role_resp.json()["id"]
        del_resp = await client.delete(f"/roles/{role_id}", headers=headers)
        assert del_resp.status_code == 200
        get_resp = await client.get(f"/roles/{role_id}", headers=headers)
        assert get_resp.status_code == 404


# ===========================================================================
# ORG PREFERENCES TESTS
# ===========================================================================

class TestOrgPreferences:
    async def test_get_org_preferences(self, client: AsyncClient):
        headers = await _register_and_login(client, f"orgpref_{uuid.uuid4().hex[:6]}")
        resp = await client.get("/org/preferences", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "name" in data
        assert "slug" in data

    async def test_update_org_preferences(self, client: AsyncClient):
        headers = await _register_and_login(client, f"orgupd_{uuid.uuid4().hex[:6]}")
        resp = await client.put("/org/preferences", headers=headers, json={
            "description": "Our metadata platform",
            "contact_email": "admin@company.com",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["description"] == "Our metadata platform"
        assert data["contact_email"] == "admin@company.com"

    async def test_org_stats(self, client: AsyncClient):
        headers = await _register_and_login(client, f"orgstats_{uuid.uuid4().hex[:6]}")
        resp = await client.get("/org/preferences/stats", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_users" in data
        assert "total_teams" in data
        assert "total_roles" in data
        assert "total_policies" in data
        assert "total_domains" in data
        assert "total_subscriptions" in data
        # At least 1 user (the registering user)
        assert data["total_users"] >= 1


# ===========================================================================
# SUBSCRIPTION TESTS
# ===========================================================================

class TestSubscriptions:
    async def test_create_subscription(self, client: AsyncClient):
        headers = await _register_and_login(client, f"sub1_{uuid.uuid4().hex[:6]}")
        resource_id = str(uuid.uuid4())
        resp = await client.post("/subscriptions", headers=headers, json={
            "resource_type": "dataset",
            "resource_id": resource_id,
            "notify_on_update": True,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["resource_type"] == "dataset"
        assert data["notify_on_update"] is True

    async def test_create_subscription_all_resource_types(self, client: AsyncClient):
        headers = await _register_and_login(client, f"subrt_{uuid.uuid4().hex[:6]}")
        resource_types = [
            "dataset", "data_asset", "data_product", "team", "user",
            "organization", "business_unit", "division", "department", "group",
        ]
        for rtype in resource_types:
            resp = await client.post("/subscriptions", headers=headers, json={
                "resource_type": rtype,
                "resource_id": str(uuid.uuid4()),
            })
            assert resp.status_code == 201, f"Failed for resource_type={rtype}: {resp.text}"

    async def test_duplicate_subscription_rejected(self, client: AsyncClient):
        headers = await _register_and_login(client, f"subdup_{uuid.uuid4().hex[:6]}")
        resource_id = str(uuid.uuid4())
        payload = {"resource_type": "dataset", "resource_id": resource_id}
        await client.post("/subscriptions", headers=headers, json=payload)
        resp = await client.post("/subscriptions", headers=headers, json=payload)
        assert resp.status_code == 409

    async def test_list_subscriptions(self, client: AsyncClient):
        headers = await _register_and_login(client, f"sublist_{uuid.uuid4().hex[:6]}")
        await client.post("/subscriptions", headers=headers, json={
            "resource_type": "team",
            "resource_id": str(uuid.uuid4()),
        })
        resp = await client.get("/subscriptions", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    async def test_delete_subscription(self, client: AsyncClient):
        headers = await _register_and_login(client, f"subdel_{uuid.uuid4().hex[:6]}")
        create_resp = await client.post("/subscriptions", headers=headers, json={
            "resource_type": "data_product",
            "resource_id": str(uuid.uuid4()),
        })
        sub_id = create_resp.json()["id"]
        del_resp = await client.delete(f"/subscriptions/{sub_id}", headers=headers)
        assert del_resp.status_code == 200
        get_resp = await client.get(f"/subscriptions/{sub_id}", headers=headers)
        assert get_resp.status_code == 404

"""
Resource Registry API test cases — uses real PostgreSQL test DB.

Tests cover:
  - POST /resources/sync — syncs static registry + leaf nodes into DB
  - GET /resources — grouped resource list (for policy dropdowns)
  - GET /resources/flat — flat list
  - GET /resources/{key}/operations — operations for a specific key
  - Policy creation validates resource key (must exist in registry)
  - Policy creation validates operations (must be subset of resource's ops)
  - Leaf node create → auto-registers resource definition
  - Leaf node soft-delete → resource deactivated, disappears from list
  - Policy create with valid resource key succeeds
  - Policy create with invalid resource key returns 422
  - Policy create with invalid operations returns 422

Run with:
    cd backend
    source venv/bin/activate
    PYTHONPATH=/home/mohan/Projects/deltameta/backend pytest testcases/test_resources.py -v --asyncio-mode=auto
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
# Test DB configuration
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


# ---------------------------------------------------------------------------
# Session-scoped DB setup
# ---------------------------------------------------------------------------

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
        import app.setting_nodes.models  # noqa
        import app.resources.models  # noqa
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
# Helpers
# ---------------------------------------------------------------------------

async def _register_and_login(client: AsyncClient, suffix: str) -> str:
    email = f"res-{suffix}@test.com"
    username = f"res-{suffix[:12]}"
    await client.post("/auth/register", json={
        "name": f"Resource User {suffix}",
        "email": email,
        "username": username,
        "password": "Test@1234",
    })
    resp = await client.post("/auth/login", json={"login": email, "password": "Test@1234"})
    return resp.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class State:
    token: str = ""
    leaf_node_id: str = ""
    leaf_slug_path: str = ""


state = State()


# ---------------------------------------------------------------------------
# Test 1: POST /resources/sync — syncs static registry to DB
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_resources(client: AsyncClient):
    token = await _register_and_login(client, str(uuid.uuid4())[:8])
    state.token = token
    resp = await client.post("/resources/sync", headers=auth(token))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # created + updated = total groups synced (idempotent: may all be updates if already exist)
    assert data["groups_created"] + data["groups_updated"] >= 5
    assert data["resources_created"] + data["resources_updated"] >= 14


# ---------------------------------------------------------------------------
# Test 2: GET /resources — returns grouped resources
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_resource_groups(client: AsyncClient):
    resp = await client.get("/resources", headers=auth(state.token))
    assert resp.status_code == 200, resp.text
    groups = resp.json()
    assert isinstance(groups, list)
    assert len(groups) >= 5

    slugs = [g["slug"] for g in groups]
    assert "identity-access" in slugs
    assert "organization" in slugs
    assert "data-catalog" in slugs

    # Each group has resources
    for group in groups:
        assert "resources" in group
        assert isinstance(group["resources"], list)


# ---------------------------------------------------------------------------
# Test 3: Every group has resources with operations
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resources_have_operations(client: AsyncClient):
    resp = await client.get("/resources", headers=auth(state.token))
    for group in resp.json():
        for resource in group["resources"]:
            assert "key" in resource
            assert "label" in resource
            assert "operations" in resource
            assert len(resource["operations"]) > 0


# ---------------------------------------------------------------------------
# Test 4: GET /resources/flat — flat list of all resources
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_resources_flat(client: AsyncClient):
    resp = await client.get("/resources/flat", headers=auth(state.token))
    assert resp.status_code == 200, resp.text
    resources = resp.json()
    assert isinstance(resources, list)
    keys = [r["key"] for r in resources]
    assert "user" in keys
    assert "team" in keys
    assert "policy" in keys
    assert "domain" in keys


# ---------------------------------------------------------------------------
# Test 5: GET /resources/{key}/operations — valid key
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_operations_for_valid_key(client: AsyncClient):
    resp = await client.get("/resources/user/operations", headers=auth(state.token))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["key"] == "user"
    assert "read" in data["operations"]
    assert "create" in data["operations"]
    assert "delete" in data["operations"]
    assert data["group_slug"] == "identity-access"


# ---------------------------------------------------------------------------
# Test 6: GET /resources/{key}/operations — invalid key returns 404
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_operations_for_invalid_key(client: AsyncClient):
    resp = await client.get("/resources/nonexistent-resource/operations", headers=auth(state.token))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 7: Create a leaf SettingNode — auto-registers resource definition
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_leaf_node_auto_registers_resource(client: AsyncClient):
    token = await _register_and_login(client, str(uuid.uuid4())[:8])
    unique = str(uuid.uuid4())[:8]
    slug = f"mongo-{unique}"

    resp = await client.post("/settings/nodes", json={
        "slug": slug,
        "display_label": "MongoDB",
        "description": "Connect to MongoDB",
        "icon": "mongodb",
        "node_type": "leaf",
        "nav_url": f"/integrations/{slug}/config",
    }, headers=auth(token))
    assert resp.status_code == 201, resp.text
    node = resp.json()
    state.leaf_node_id = node["id"]
    state.leaf_slug_path = node["slug_path"]

    # Now check the resource was auto-registered
    ops_resp = await client.get(
        f"/resources/{state.leaf_slug_path}/operations",
        headers=auth(token),
    )
    assert ops_resp.status_code == 200, ops_resp.text
    data = ops_resp.json()
    assert data["key"] == state.leaf_slug_path
    assert "read" in data["operations"]
    assert "configure" in data["operations"]


# ---------------------------------------------------------------------------
# Test 8: Leaf node soft-delete deactivates the resource
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_leaf_node_delete_deactivates_resource(client: AsyncClient):
    token = await _register_and_login(client, str(uuid.uuid4())[:8])
    unique = str(uuid.uuid4())[:8]
    slug = f"temp-db-{unique}"

    create_resp = await client.post("/settings/nodes", json={
        "slug": slug,
        "display_label": "Temp DB",
        "node_type": "leaf",
        "nav_url": f"/integrations/{slug}/config",
    }, headers=auth(token))
    assert create_resp.status_code == 201
    node = create_resp.json()
    slug_path = node["slug_path"]

    # Resource should exist now
    ops_before = await client.get(f"/resources/{slug_path}/operations", headers=auth(token))
    assert ops_before.status_code == 200

    # Soft-delete the node
    del_resp = await client.delete(f"/settings/nodes/{node['id']}", headers=auth(token))
    assert del_resp.status_code == 200

    # Resource should now be inactive (404 from /resources/{key}/operations)
    ops_after = await client.get(f"/resources/{slug_path}/operations", headers=auth(token))
    assert ops_after.status_code == 404


# ---------------------------------------------------------------------------
# Test 9: Create policy with valid resource key succeeds
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_policy_valid_resource(client: AsyncClient):
    resp = await client.post("/policies", json={
        "name": f"Valid Resource Policy {uuid.uuid4().hex[:8]}",
        "rule_name": "valid_resource_rule",
        "resource": "user",
        "operations": ["read", "create"],
        "conditions": [],
    }, headers=auth(state.token))
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["resource"] == "user"
    assert data["operations"] == ["read", "create"]


# ---------------------------------------------------------------------------
# Test 10: Create policy with invalid resource key returns 422
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_policy_invalid_resource_key(client: AsyncClient):
    resp = await client.post("/policies", json={
        "name": f"Invalid Resource Policy {uuid.uuid4().hex[:8]}",
        "rule_name": "invalid_resource_rule",
        "resource": "totally-made-up-resource",
        "operations": ["read"],
        "conditions": [],
    }, headers=auth(state.token))
    assert resp.status_code == 422, resp.text
    assert "not a valid resource key" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test 11: Create policy with invalid operations returns 422
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_policy_invalid_operations(client: AsyncClient):
    resp = await client.post("/policies", json={
        "name": f"Invalid Ops Policy {uuid.uuid4().hex[:8]}",
        "rule_name": "invalid_ops_rule",
        "resource": "user",
        "operations": ["read", "fly", "teleport"],   # "fly" and "teleport" not valid for "user"
        "conditions": [],
    }, headers=auth(state.token))
    assert resp.status_code == 422, resp.text
    assert "invalid operations" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test 12: Create policy for leaf node resource (after leaf node created)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_policy_for_leaf_node_resource(client: AsyncClient):
    if not state.leaf_slug_path:
        pytest.skip("Leaf node not created in test 7")
    resp = await client.post("/policies", json={
        "name": f"Leaf Policy {uuid.uuid4().hex[:8]}",
        "rule_name": "leaf_node_rule",
        "resource": state.leaf_slug_path,
        "operations": ["read", "configure"],
        "conditions": [{"attr": "role", "op": "=", "value": "data_engineer"}],
    }, headers=auth(state.token))
    assert resp.status_code == 201, resp.text
    assert resp.json()["resource"] == state.leaf_slug_path


# ---------------------------------------------------------------------------
# Test 13: POST /resources/sync is idempotent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_is_idempotent(client: AsyncClient):
    resp1 = await client.post("/resources/sync", headers=auth(state.token))
    resp2 = await client.post("/resources/sync", headers=auth(state.token))
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    # Both return same total
    assert resp1.json()["total_resources"] == resp2.json()["total_resources"]


# ---------------------------------------------------------------------------
# Test 14: Unauthenticated request returns 401/403
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resources_unauthenticated(client: AsyncClient):
    resp = await client.get("/resources")
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Test 15: GET /resources/team/operations — correct ops for team resource
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_team_resource_operations(client: AsyncClient):
    resp = await client.get("/resources/team/operations", headers=auth(state.token))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["key"] == "team"
    assert "manage_members" in data["operations"]
    assert data["group_slug"] == "organization"

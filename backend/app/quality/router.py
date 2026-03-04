"""
Data Quality API — Phase 2 Module 4.

Entities:
  • QualityTestCase  — individual test (table / column / dimension level)
  • QualityTestSuite — group of test cases with optional pipeline
  • QualityTestRun   — single execution of a test case or suite
  • QualityIncident  — auto-created when a run fails/aborts; managed separately

Endpoints:

Test Cases:
  POST   /quality/test-cases               Create
  GET    /quality/test-cases               List (filters: asset_id, level, test_type, dimension, is_active, severity)
  GET    /quality/test-cases/{id}          Get by ID
  PUT    /quality/test-cases/{id}          Update
  DELETE /quality/test-cases/{id}          Delete
  POST   /quality/test-cases/{id}/run      Trigger a run for this test case

  GET    /quality/test-cases/{id}/runs     List runs for a test case

Test Suites:
  POST   /quality/test-suites              Create
  GET    /quality/test-suites              List (filters: suite_type, asset_id)
  GET    /quality/test-suites/{id}         Get by ID
  PUT    /quality/test-suites/{id}         Update
  DELETE /quality/test-suites/{id}         Delete
  POST   /quality/test-suites/{id}/run     Trigger a run for this suite

  GET    /quality/test-suites/{id}/runs    List runs for a suite

Test Runs (org-wide):
  GET    /quality/runs                     List runs (filters: test_case_id, test_suite_id, status)
  GET    /quality/runs/{id}                Get run by ID
  PUT    /quality/runs/{id}                Update run (bot/agent posts results)

Incidents:
  GET    /quality/incidents                List incidents (filters: test_case_id, asset_id, status, assignee_id, severity)
  GET    /quality/incidents/{id}           Get incident
  PUT    /quality/incidents/{id}           Update incident (assign, change status, add reasons)
  DELETE /quality/incidents/{id}           Delete incident
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.auth.dependencies import get_active_org_id, require_active_user
from app.auth.abac import require_permission
from app.govern.models import (
    DataAsset,
    QualityIncident,
    QualityTestCase,
    QualityTestRun,
    QualityTestSuite,
)

router = APIRouter(prefix="/quality", tags=["Data Quality"])

VALID_LEVELS = {"table", "column", "dimension"}
VALID_TEST_TYPES = {
    "row_count_between", "row_count_equal", "column_count_between", "column_count_equal",
    "column_name_exists", "column_name_match_set", "custom_sql", "compare_tables", "row_inserted_between",
}
VALID_DIMENSIONS = {"accuracy", "completeness", "consistency", "integrity", "uniqueness", "validity", "sql", "no_dimension"}
VALID_SEVERITIES = {"info", "warning", "critical"}
VALID_STATUSES = {"pending", "running", "success", "aborted", "failed"}
VALID_INCIDENT_STATUSES = {"open", "in_progress", "resolved", "ignored"}
VALID_SUITE_TYPES = {"table", "bundle"}
VALID_TRIGGER_MODES = {"on_demand", "scheduled"}


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class TestCaseCreate(BaseModel):
    asset_id: uuid.UUID
    column_id: Optional[uuid.UUID] = None
    name: str
    description: Optional[str] = None
    level: str = "table"
    test_type: str
    dimension: Optional[str] = None
    config: Dict[str, Any] = {}
    severity: str = "warning"
    tags: List[str] = []
    glossary_term_ids: List[uuid.UUID] = []
    is_active: bool = True

    @field_validator("level")
    @classmethod
    def v_level(cls, v): 
        if v not in VALID_LEVELS: raise ValueError(f"level must be one of {sorted(VALID_LEVELS)}")
        return v

    @field_validator("test_type")
    @classmethod
    def v_test_type(cls, v):
        if v not in VALID_TEST_TYPES: raise ValueError(f"test_type must be one of {sorted(VALID_TEST_TYPES)}")
        return v

    @field_validator("dimension")
    @classmethod
    def v_dimension(cls, v):
        if v is not None and v not in VALID_DIMENSIONS:
            raise ValueError(f"dimension must be one of {sorted(VALID_DIMENSIONS)}")
        return v

    @field_validator("severity")
    @classmethod
    def v_severity(cls, v):
        if v not in VALID_SEVERITIES: raise ValueError(f"severity must be one of {sorted(VALID_SEVERITIES)}")
        return v


class TestCaseUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    level: Optional[str] = None
    test_type: Optional[str] = None
    dimension: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    severity: Optional[str] = None
    tags: Optional[List[str]] = None
    glossary_term_ids: Optional[List[uuid.UUID]] = None
    is_active: Optional[bool] = None


class TestCaseOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    asset_id: uuid.UUID
    column_id: Optional[uuid.UUID] = None
    name: str
    description: Optional[str] = None
    level: str
    test_type: str
    dimension: Optional[str] = None
    config: Dict[str, Any]
    severity: str
    tags: List[str]
    glossary_term_ids: List[Any]
    is_active: bool
    created_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class TestSuiteCreate(BaseModel):
    name: str
    description: Optional[str] = None
    suite_type: str = "bundle"
    asset_id: Optional[uuid.UUID] = None
    test_case_ids: List[uuid.UUID] = []
    owner_ids: List[uuid.UUID] = []
    has_pipeline: bool = False
    trigger_mode: str = "on_demand"
    cron_expr: Optional[str] = None
    enable_debug_log: bool = False
    raise_on_error: bool = False

    @field_validator("suite_type")
    @classmethod
    def v_suite_type(cls, v):
        if v not in VALID_SUITE_TYPES: raise ValueError(f"suite_type must be one of {sorted(VALID_SUITE_TYPES)}")
        return v

    @field_validator("trigger_mode")
    @classmethod
    def v_trigger_mode(cls, v):
        if v not in VALID_TRIGGER_MODES: raise ValueError(f"trigger_mode must be one of {sorted(VALID_TRIGGER_MODES)}")
        return v


class TestSuiteUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    suite_type: Optional[str] = None
    asset_id: Optional[uuid.UUID] = None
    test_case_ids: Optional[List[uuid.UUID]] = None
    owner_ids: Optional[List[uuid.UUID]] = None
    has_pipeline: Optional[bool] = None
    trigger_mode: Optional[str] = None
    cron_expr: Optional[str] = None
    enable_debug_log: Optional[bool] = None
    raise_on_error: Optional[bool] = None


class TestSuiteOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    description: Optional[str] = None
    suite_type: str
    asset_id: Optional[uuid.UUID] = None
    test_case_ids: List[Any]
    owner_ids: List[Any]
    has_pipeline: bool
    trigger_mode: str
    cron_expr: Optional[str] = None
    enable_debug_log: bool
    raise_on_error: bool
    created_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class TestRunUpdate(BaseModel):
    status: Optional[str] = None
    result_detail: Optional[Dict[str, Any]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @field_validator("status")
    @classmethod
    def v_status(cls, v):
        if v is not None and v not in VALID_STATUSES:
            raise ValueError(f"status must be one of {sorted(VALID_STATUSES)}")
        return v


class TestRunOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    test_case_id: Optional[uuid.UUID] = None
    test_suite_id: Optional[uuid.UUID] = None
    triggered_by: Optional[uuid.UUID] = None
    status: str
    result_detail: Dict[str, Any]
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    model_config = {"from_attributes": True}


class IncidentUpdate(BaseModel):
    status: Optional[str] = None
    assignee_id: Optional[uuid.UUID] = None
    severity: Optional[str] = None
    failed_reason: Optional[str] = None
    aborted_reason: Optional[str] = None
    resolved_at: Optional[datetime] = None

    @field_validator("status")
    @classmethod
    def v_status(cls, v):
        if v is not None and v not in VALID_INCIDENT_STATUSES:
            raise ValueError(f"status must be one of {sorted(VALID_INCIDENT_STATUSES)}")
        return v


class IncidentOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    test_case_id: uuid.UUID
    test_run_id: Optional[uuid.UUID] = None
    asset_id: uuid.UUID
    assignee_id: Optional[uuid.UUID] = None
    status: str
    severity: str
    failed_reason: Optional[str] = None
    aborted_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_test_case_or_404(tc_id: uuid.UUID, org_id: uuid.UUID, session: AsyncSession) -> QualityTestCase:
    r = await session.execute(select(QualityTestCase).where(
        QualityTestCase.id == tc_id, QualityTestCase.org_id == org_id
    ))
    obj = r.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Test case not found")
    return obj


async def _get_test_suite_or_404(ts_id: uuid.UUID, org_id: uuid.UUID, session: AsyncSession) -> QualityTestSuite:
    r = await session.execute(select(QualityTestSuite).where(
        QualityTestSuite.id == ts_id, QualityTestSuite.org_id == org_id
    ))
    obj = r.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Test suite not found")
    return obj


async def _get_run_or_404(run_id: uuid.UUID, org_id: uuid.UUID, session: AsyncSession) -> QualityTestRun:
    r = await session.execute(select(QualityTestRun).where(
        QualityTestRun.id == run_id, QualityTestRun.org_id == org_id
    ))
    obj = r.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Test run not found")
    return obj


async def _get_incident_or_404(inc_id: uuid.UUID, org_id: uuid.UUID, session: AsyncSession) -> QualityIncident:
    r = await session.execute(select(QualityIncident).where(
        QualityIncident.id == inc_id, QualityIncident.org_id == org_id
    ))
    obj = r.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Incident not found")
    return obj


async def _create_run(
    org_id: uuid.UUID,
    triggered_by: uuid.UUID,
    test_case_id: Optional[uuid.UUID],
    test_suite_id: Optional[uuid.UUID],
    session: AsyncSession,
) -> QualityTestRun:
    run = QualityTestRun(
        id=uuid.uuid4(),
        org_id=org_id,
        test_case_id=test_case_id,
        test_suite_id=test_suite_id,
        triggered_by=triggered_by,
        status="pending",
        result_detail={},
    )
    session.add(run)
    return run


async def _auto_create_incident_if_failed(
    run: QualityTestRun,
    test_case: QualityTestCase,
    session: AsyncSession,
) -> None:
    """Auto-create an incident when a run transitions to failed or aborted."""
    if run.status not in ("failed", "aborted"):
        return
    detail = run.result_detail or {}
    incident = QualityIncident(
        id=uuid.uuid4(),
        org_id=run.org_id,
        test_case_id=test_case.id,
        test_run_id=run.id,
        asset_id=test_case.asset_id,
        severity=test_case.severity,
        status="open",
        failed_reason=detail.get("error") if run.status == "failed" else None,
        aborted_reason=detail.get("error") if run.status == "aborted" else None,
    )
    session.add(incident)


# ===========================================================================
# TEST CASES
# ===========================================================================

@router.post("/test-cases", response_model=TestCaseOut, status_code=201, summary="Create a quality test case")
async def create_test_case(
    body: TestCaseCreate,
    current_user=Depends(require_permission("data_quality", "create")),
    session: AsyncSession = Depends(get_session),
):
    org_id = get_active_org_id(current_user)
    # validate asset exists
    r = await session.execute(select(DataAsset).where(DataAsset.id == body.asset_id, DataAsset.org_id == org_id))
    if not r.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Data asset not found")

    tc = QualityTestCase(
        id=uuid.uuid4(), org_id=org_id, created_by=current_user.id,
        asset_id=body.asset_id, column_id=body.column_id,
        name=body.name, description=body.description,
        level=body.level, test_type=body.test_type, dimension=body.dimension,
        config=body.config, severity=body.severity,
        tags=body.tags,
        glossary_term_ids=[str(gid) for gid in body.glossary_term_ids],
        is_active=body.is_active,
    )
    session.add(tc)
    await session.commit()
    await session.refresh(tc)
    return tc


@router.get("/test-cases", response_model=List[TestCaseOut], summary="List quality test cases")
async def list_test_cases(
    asset_id: Optional[uuid.UUID] = Query(None),
    level: Optional[str] = Query(None, description="table | column | dimension"),
    test_type: Optional[str] = Query(None),
    dimension: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    severity: Optional[str] = Query(None),
    last_run_status: Optional[str] = Query(None, description="pending | running | success | aborted | failed — filter by latest run status"),
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    org_id = get_active_org_id(current_user)
    q = select(QualityTestCase).where(QualityTestCase.org_id == org_id)
    if asset_id: q = q.where(QualityTestCase.asset_id == asset_id)
    if level: q = q.where(QualityTestCase.level == level)
    if test_type: q = q.where(QualityTestCase.test_type == test_type)
    if dimension: q = q.where(QualityTestCase.dimension == dimension)
    if is_active is not None: q = q.where(QualityTestCase.is_active == is_active)
    if severity: q = q.where(QualityTestCase.severity == severity)
    if search: q = q.where(QualityTestCase.name.ilike(f"%{search}%"))
    if last_run_status:
        # Subquery: test cases that have at least one run with this status as their latest run
        latest_run_subq = (
            select(QualityTestRun.test_case_id)
            .where(
                QualityTestRun.org_id == org_id,
                QualityTestRun.test_case_id == QualityTestCase.id,
                QualityTestRun.status == last_run_status,
            )
            .order_by(QualityTestRun.created_at.desc())
            .limit(1)
            .correlate(QualityTestCase)
            .exists()
        )
        q = q.where(latest_run_subq)
    q = q.order_by(QualityTestCase.created_at.desc()).offset(skip).limit(limit)
    result = await session.execute(q)
    return result.scalars().all()


@router.get("/test-cases/{tc_id}", response_model=TestCaseOut, summary="Get a test case")
async def get_test_case(tc_id: uuid.UUID, current_user=Depends(require_active_user), session: AsyncSession = Depends(get_session)):
    return await _get_test_case_or_404(tc_id, get_active_org_id(current_user), session)


@router.put("/test-cases/{tc_id}", response_model=TestCaseOut, summary="Update a test case")
async def update_test_case(
    tc_id: uuid.UUID, body: TestCaseUpdate,
    current_user=Depends(require_permission("data_quality", "update")),
    session: AsyncSession = Depends(get_session),
):
    tc = await _get_test_case_or_404(tc_id, get_active_org_id(current_user), session)
    for field, value in body.model_dump(exclude_none=True).items():
        if field == "glossary_term_ids":
            value = [str(v) for v in value]
        setattr(tc, field, value)
    await session.commit()
    await session.refresh(tc)
    return tc


@router.delete("/test-cases/{tc_id}", status_code=204, summary="Delete a test case")
async def delete_test_case(tc_id: uuid.UUID, current_user=Depends(require_permission("data_quality", "delete")), session: AsyncSession = Depends(get_session)):
    tc = await _get_test_case_or_404(tc_id, get_active_org_id(current_user), session)
    await session.delete(tc)
    await session.commit()


@router.post("/test-cases/{tc_id}/run", response_model=TestRunOut, status_code=201, summary="Trigger a test case run")
async def run_test_case(
    tc_id: uuid.UUID,
    current_user=Depends(require_permission("data_quality", "run")),
    session: AsyncSession = Depends(get_session),
):
    org_id = get_active_org_id(current_user)
    tc = await _get_test_case_or_404(tc_id, org_id, session)
    run = await _create_run(org_id, current_user.id, tc.id, None, session)
    await session.commit()
    await session.refresh(run)
    return run


@router.get("/test-cases/{tc_id}/runs", response_model=List[TestRunOut], summary="List runs for a test case")
async def list_test_case_runs(
    tc_id: uuid.UUID,
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    org_id = get_active_org_id(current_user)
    await _get_test_case_or_404(tc_id, org_id, session)
    q = select(QualityTestRun).where(QualityTestRun.test_case_id == tc_id, QualityTestRun.org_id == org_id)
    if status: q = q.where(QualityTestRun.status == status)
    q = q.order_by(QualityTestRun.created_at.desc()).offset(skip).limit(limit)
    result = await session.execute(q)
    return result.scalars().all()


# ===========================================================================
# TEST SUITES
# ===========================================================================

@router.post("/test-suites", response_model=TestSuiteOut, status_code=201, summary="Create a test suite")
async def create_test_suite(
    body: TestSuiteCreate,
    current_user=Depends(require_permission("data_quality", "create")),
    session: AsyncSession = Depends(get_session),
):
    org_id = get_active_org_id(current_user)
    if body.has_pipeline and body.trigger_mode == "scheduled" and not body.cron_expr:
        raise HTTPException(status_code=422, detail="cron_expr is required when trigger_mode='scheduled'")

    ts = QualityTestSuite(
        id=uuid.uuid4(), org_id=org_id, created_by=current_user.id,
        name=body.name, description=body.description,
        suite_type=body.suite_type, asset_id=body.asset_id,
        test_case_ids=[str(tid) for tid in body.test_case_ids],
        owner_ids=[str(oid) for oid in body.owner_ids],
        has_pipeline=body.has_pipeline, trigger_mode=body.trigger_mode,
        cron_expr=body.cron_expr,
        enable_debug_log=body.enable_debug_log, raise_on_error=body.raise_on_error,
    )
    session.add(ts)
    await session.commit()
    await session.refresh(ts)
    return ts


@router.get("/test-suites", response_model=List[TestSuiteOut], summary="List test suites")
async def list_test_suites(
    suite_type: Optional[str] = Query(None, description="table | bundle"),
    asset_id: Optional[uuid.UUID] = Query(None),
    has_pipeline: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    org_id = get_active_org_id(current_user)
    q = select(QualityTestSuite).where(QualityTestSuite.org_id == org_id)
    if suite_type: q = q.where(QualityTestSuite.suite_type == suite_type)
    if asset_id: q = q.where(QualityTestSuite.asset_id == asset_id)
    if has_pipeline is not None: q = q.where(QualityTestSuite.has_pipeline == has_pipeline)
    if search: q = q.where(QualityTestSuite.name.ilike(f"%{search}%"))
    q = q.order_by(QualityTestSuite.created_at.desc()).offset(skip).limit(limit)
    result = await session.execute(q)
    return result.scalars().all()


@router.get("/test-suites/{ts_id}", response_model=TestSuiteOut, summary="Get a test suite")
async def get_test_suite(ts_id: uuid.UUID, current_user=Depends(require_active_user), session: AsyncSession = Depends(get_session)):
    return await _get_test_suite_or_404(ts_id, get_active_org_id(current_user), session)


@router.put("/test-suites/{ts_id}", response_model=TestSuiteOut, summary="Update a test suite")
async def update_test_suite(
    ts_id: uuid.UUID, body: TestSuiteUpdate,
    current_user=Depends(require_permission("data_quality", "update")),
    session: AsyncSession = Depends(get_session),
):
    ts = await _get_test_suite_or_404(ts_id, get_active_org_id(current_user), session)
    for field, value in body.model_dump(exclude_none=True).items():
        if field in ("test_case_ids", "owner_ids"):
            value = [str(v) for v in value]
        setattr(ts, field, value)
    await session.commit()
    await session.refresh(ts)
    return ts


@router.delete("/test-suites/{ts_id}", status_code=204, summary="Delete a test suite")
async def delete_test_suite(ts_id: uuid.UUID, current_user=Depends(require_permission("data_quality", "delete")), session: AsyncSession = Depends(get_session)):
    ts = await _get_test_suite_or_404(ts_id, get_active_org_id(current_user), session)
    await session.delete(ts)
    await session.commit()


@router.post("/test-suites/{ts_id}/run", response_model=TestRunOut, status_code=201, summary="Trigger a test suite run")
async def run_test_suite(
    ts_id: uuid.UUID,
    current_user=Depends(require_permission("data_quality", "run")),
    session: AsyncSession = Depends(get_session),
):
    org_id = get_active_org_id(current_user)
    ts = await _get_test_suite_or_404(ts_id, org_id, session)
    run = await _create_run(org_id, current_user.id, None, ts.id, session)
    await session.commit()
    await session.refresh(run)
    return run


@router.get("/test-suites/{ts_id}/runs", response_model=List[TestRunOut], summary="List runs for a test suite")
async def list_test_suite_runs(
    ts_id: uuid.UUID,
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    org_id = get_active_org_id(current_user)
    await _get_test_suite_or_404(ts_id, org_id, session)
    q = select(QualityTestRun).where(QualityTestRun.test_suite_id == ts_id, QualityTestRun.org_id == org_id)
    if status: q = q.where(QualityTestRun.status == status)
    q = q.order_by(QualityTestRun.created_at.desc()).offset(skip).limit(limit)
    result = await session.execute(q)
    return result.scalars().all()


# ===========================================================================
# TEST RUNS (org-wide)
# ===========================================================================

@router.get("/runs", response_model=List[TestRunOut], summary="List all test runs (org-wide)")
async def list_runs(
    test_case_id: Optional[uuid.UUID] = Query(None),
    test_suite_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    triggered_by: Optional[uuid.UUID] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    org_id = get_active_org_id(current_user)
    q = select(QualityTestRun).where(QualityTestRun.org_id == org_id)
    if test_case_id: q = q.where(QualityTestRun.test_case_id == test_case_id)
    if test_suite_id: q = q.where(QualityTestRun.test_suite_id == test_suite_id)
    if status: q = q.where(QualityTestRun.status == status)
    if triggered_by: q = q.where(QualityTestRun.triggered_by == triggered_by)
    q = q.order_by(QualityTestRun.created_at.desc()).offset(skip).limit(limit)
    result = await session.execute(q)
    return result.scalars().all()


@router.get("/runs/{run_id}", response_model=TestRunOut, summary="Get a test run")
async def get_run(run_id: uuid.UUID, current_user=Depends(require_active_user), session: AsyncSession = Depends(get_session)):
    return await _get_run_or_404(run_id, get_active_org_id(current_user), session)


@router.put("/runs/{run_id}", response_model=TestRunOut, summary="Update a test run (post results)")
async def update_run(
    run_id: uuid.UUID, body: TestRunUpdate,
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    org_id = get_active_org_id(current_user)
    run = await _get_run_or_404(run_id, org_id, session)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(run, field, value)

    # Auto-create incident for failed/aborted runs (only when test_case_id is set)
    if run.test_case_id and body.status in ("failed", "aborted"):
        tc = await _get_test_case_or_404(run.test_case_id, org_id, session)
        await _auto_create_incident_if_failed(run, tc, session)

    await session.commit()
    await session.refresh(run)
    return run


# ===========================================================================
# INCIDENTS
# ===========================================================================

@router.get("/incidents", response_model=List[IncidentOut], summary="List quality incidents")
async def list_incidents(
    test_case_id: Optional[uuid.UUID] = Query(None),
    asset_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None, description="open | in_progress | resolved | ignored"),
    assignee_id: Optional[uuid.UUID] = Query(None),
    severity: Optional[str] = Query(None),
    date_range: Optional[str] = Query(None, description="yesterday | last_7_days | last_15_days | last_30_days"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    org_id = get_active_org_id(current_user)
    q = select(QualityIncident).where(QualityIncident.org_id == org_id)
    if test_case_id: q = q.where(QualityIncident.test_case_id == test_case_id)
    if asset_id: q = q.where(QualityIncident.asset_id == asset_id)
    if status: q = q.where(QualityIncident.status == status)
    if assignee_id: q = q.where(QualityIncident.assignee_id == assignee_id)
    if severity: q = q.where(QualityIncident.severity == severity)
    if date_range:
        _DATE_RANGE_DAYS = {
            "yesterday": 1,
            "last_7_days": 7,
            "last_15_days": 15,
            "last_30_days": 30,
        }
        days = _DATE_RANGE_DAYS.get(date_range)
        if days is None:
            raise HTTPException(
                status_code=422,
                detail="date_range must be one of: yesterday, last_7_days, last_15_days, last_30_days",
            )
        since = datetime.now(timezone.utc) - timedelta(days=days)
        q = q.where(QualityIncident.created_at >= since)
    q = q.order_by(QualityIncident.created_at.desc()).offset(skip).limit(limit)
    result = await session.execute(q)
    return result.scalars().all()


@router.get("/incidents/{inc_id}", response_model=IncidentOut, summary="Get an incident")
async def get_incident(inc_id: uuid.UUID, current_user=Depends(require_active_user), session: AsyncSession = Depends(get_session)):
    return await _get_incident_or_404(inc_id, get_active_org_id(current_user), session)


@router.put("/incidents/{inc_id}", response_model=IncidentOut, summary="Update an incident")
async def update_incident(
    inc_id: uuid.UUID, body: IncidentUpdate,
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    incident = await _get_incident_or_404(inc_id, get_active_org_id(current_user), session)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(incident, field, value)
    await session.commit()
    await session.refresh(incident)
    return incident


@router.delete("/incidents/{inc_id}", status_code=204, summary="Delete an incident")
async def delete_incident(inc_id: uuid.UUID, current_user=Depends(require_active_user), session: AsyncSession = Depends(get_session)):
    incident = await _get_incident_or_404(inc_id, get_active_org_id(current_user), session)
    await session.delete(incident)
    await session.commit()

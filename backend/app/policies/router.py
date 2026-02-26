"""
Policies API router — ABAC policy CRUD.

Policy structure:
  - resource: what the policy applies to (e.g. "catalog.dataset", "admin.users")
  - operations: list of allowed ops on that resource (view/create/update/delete/allow/deny)
  - conditions: list of attribute-based conditions [{attr, op, value}]

Policies are stored in the DB. Enforcement is a FUTURE phase.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.auth.models import Policy
from app.auth.schemas import (
    MessageResponse,
    PolicyCreate,
    PolicyResponse,
    PolicyUpdate,
)
from app.auth.dependencies import require_active_user, require_org_admin

router = APIRouter(prefix="/policies", tags=["Policies"])


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.get("", response_model=List[PolicyResponse], summary="List policies for the current org")
async def list_policies(
    resource: Optional[str] = Query(None, description="Filter by resource path"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    q = select(Policy).where(Policy.org_id == current_user.org_id)
    if resource:
        q = q.where(Policy.resource.ilike(f"%{resource}%"))
    q = q.order_by(Policy.name).offset(skip).limit(limit)
    result = await session.execute(q)
    return result.scalars().all()


@router.post("", response_model=PolicyResponse, status_code=status.HTTP_201_CREATED, summary="Create a policy")
async def create_policy(
    body: PolicyCreate,
    current_user=Depends(require_org_admin),
    session: AsyncSession = Depends(get_session),
):
    existing = await session.execute(
        select(Policy).where(Policy.org_id == current_user.org_id, Policy.name == body.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Policy name already exists in this organization")

    policy = Policy(
        id=uuid.uuid4(),
        org_id=current_user.org_id,
        name=body.name,
        description=body.description,
        rule_name=body.rule_name,
        resource=body.resource,
        operations=body.operations,
        conditions=[c.model_dump() for c in body.conditions],
    )
    session.add(policy)
    await session.commit()
    await session.refresh(policy)
    return policy


@router.get("/{policy_id}", response_model=PolicyResponse, summary="Get a policy by ID")
async def get_policy(
    policy_id: uuid.UUID,
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    return await _get_policy_or_404(policy_id, current_user.org_id, session)


@router.put("/{policy_id}", response_model=PolicyResponse, summary="Update a policy")
async def update_policy(
    policy_id: uuid.UUID,
    body: PolicyUpdate,
    current_user=Depends(require_org_admin),
    session: AsyncSession = Depends(get_session),
):
    policy = await _get_policy_or_404(policy_id, current_user.org_id, session)

    if body.name is not None and body.name != policy.name:
        existing = await session.execute(
            select(Policy).where(Policy.org_id == current_user.org_id, Policy.name == body.name)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Policy name already exists")
        policy.name = body.name

    if body.description is not None:
        policy.description = body.description
    if body.rule_name is not None:
        policy.rule_name = body.rule_name
    if body.resource is not None:
        policy.resource = body.resource
    if body.operations is not None:
        policy.operations = body.operations
    if body.conditions is not None:
        policy.conditions = [c.model_dump() for c in body.conditions]

    policy.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(policy)
    return policy


@router.delete("/{policy_id}", response_model=MessageResponse, summary="Delete a policy")
async def delete_policy(
    policy_id: uuid.UUID,
    current_user=Depends(require_org_admin),
    session: AsyncSession = Depends(get_session),
):
    policy = await _get_policy_or_404(policy_id, current_user.org_id, session)
    await session.delete(policy)
    await session.commit()
    return MessageResponse(message=f"Policy '{policy.name}' deleted successfully")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_policy_or_404(policy_id: uuid.UUID, org_id: uuid.UUID, session: AsyncSession) -> Policy:
    result = await session.execute(
        select(Policy).where(Policy.id == policy_id, Policy.org_id == org_id)
    )
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    return policy

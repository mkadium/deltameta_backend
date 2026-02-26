"""
Domains API router — CRUD for organization domains.
Domains group teams and users by subject area (e.g. Engineering, Finance).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.auth.models import Domain
from app.auth.schemas import DomainCreate, DomainResponse, DomainUpdate, MessageResponse
from app.auth.dependencies import require_active_user, require_org_admin

router = APIRouter(prefix="/domains", tags=["Domains"])


@router.get("", response_model=List[DomainResponse], summary="List domains for the current org")
async def list_domains(
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    q = select(Domain).where(Domain.org_id == current_user.org_id)
    if is_active is not None:
        q = q.where(Domain.is_active == is_active)
    q = q.order_by(Domain.name).offset(skip).limit(limit)
    result = await session.execute(q)
    return result.scalars().all()


@router.post("", response_model=DomainResponse, status_code=status.HTTP_201_CREATED, summary="Create a new domain")
async def create_domain(
    body: DomainCreate,
    current_user=Depends(require_org_admin),
    session: AsyncSession = Depends(get_session),
):
    # Prevent duplicate name within same org
    existing = await session.execute(
        select(Domain).where(Domain.org_id == current_user.org_id, Domain.name == body.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Domain name already exists in this organization")

    domain = Domain(
        id=uuid.uuid4(),
        org_id=current_user.org_id,
        name=body.name,
        description=body.description,
        domain_type=body.domain_type,
        owner_id=body.owner_id,
        is_active=True,
    )
    session.add(domain)
    await session.commit()
    await session.refresh(domain)
    return domain


@router.get("/{domain_id}", response_model=DomainResponse, summary="Get a domain by ID")
async def get_domain(
    domain_id: uuid.UUID,
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    domain = await _get_domain_or_404(domain_id, current_user.org_id, session)
    return domain


@router.put("/{domain_id}", response_model=DomainResponse, summary="Update a domain")
async def update_domain(
    domain_id: uuid.UUID,
    body: DomainUpdate,
    current_user=Depends(require_org_admin),
    session: AsyncSession = Depends(get_session),
):
    domain = await _get_domain_or_404(domain_id, current_user.org_id, session)

    if body.name is not None and body.name != domain.name:
        existing = await session.execute(
            select(Domain).where(Domain.org_id == current_user.org_id, Domain.name == body.name)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Domain name already exists in this organization")
        domain.name = body.name

    if body.description is not None:
        domain.description = body.description
    if body.domain_type is not None:
        domain.domain_type = body.domain_type
    if body.owner_id is not None:
        domain.owner_id = body.owner_id
    if body.is_active is not None:
        domain.is_active = body.is_active

    domain.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(domain)
    return domain


@router.delete("/{domain_id}", response_model=MessageResponse, summary="Delete a domain")
async def delete_domain(
    domain_id: uuid.UUID,
    current_user=Depends(require_org_admin),
    session: AsyncSession = Depends(get_session),
):
    domain = await _get_domain_or_404(domain_id, current_user.org_id, session)
    await session.delete(domain)
    await session.commit()
    return MessageResponse(message=f"Domain '{domain.name}' deleted successfully")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_domain_or_404(domain_id: uuid.UUID, org_id: uuid.UUID, session: AsyncSession) -> Domain:
    result = await session.execute(
        select(Domain).where(Domain.id == domain_id, Domain.org_id == org_id)
    )
    domain = result.scalar_one_or_none()
    if not domain:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found")
    return domain

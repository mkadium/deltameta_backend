"""
Subscriptions API router.

Users or the organization can subscribe to any public resource
(dataset, data asset, data product, team, user, org, BU, division, department, group).
Subscriptions are namespaced by org_id (multi-tenant safe).
"""
from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.auth.models import Subscription
from app.auth.schemas import MessageResponse, SubscriptionCreate, SubscriptionResponse
from app.auth.dependencies import get_active_org_id, require_active_user, require_org_admin

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


@router.get("", response_model=List[SubscriptionResponse], summary="List subscriptions for the current org")
async def list_subscriptions(
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    subscriber_user_id: Optional[uuid.UUID] = Query(None, description="Filter by subscriber user"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    q = select(Subscription).where(Subscription.org_id == get_active_org_id(current_user))
    if resource_type:
        q = q.where(Subscription.resource_type == resource_type)
    if subscriber_user_id:
        q = q.where(Subscription.user_id == subscriber_user_id)
    q = q.order_by(Subscription.subscribed_at.desc()).offset(skip).limit(limit)
    result = await session.execute(q)
    subs = result.scalars().all()
    return [_to_response(s) for s in subs]


@router.post(
    "",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a subscription",
)
async def create_subscription(
    body: SubscriptionCreate,
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    # Prevent duplicate subscription to the same resource by same subscriber
    existing = await session.execute(
        select(Subscription).where(
            Subscription.org_id == get_active_org_id(current_user),
            Subscription.resource_type == body.resource_type.value,
            Subscription.resource_id == body.resource_id,
            Subscription.user_id == (body.subscriber_user_id or current_user.id),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Already subscribed to this resource",
        )

    sub = Subscription(
        id=uuid.uuid4(),
        org_id=get_active_org_id(current_user),
        user_id=body.subscriber_user_id or current_user.id,
        resource_type=body.resource_type.value,
        resource_id=body.resource_id,
        notify_on_update=body.notify_on_update,
    )
    session.add(sub)
    await session.commit()
    await session.refresh(sub)
    return _to_response(sub)


@router.get("/{subscription_id}", response_model=SubscriptionResponse, summary="Get a subscription by ID")
async def get_subscription(
    subscription_id: uuid.UUID,
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    sub = await _get_sub_or_404(subscription_id, get_active_org_id(current_user), session)
    return _to_response(sub)


@router.delete("/{subscription_id}", response_model=MessageResponse, summary="Delete a subscription")
async def delete_subscription(
    subscription_id: uuid.UUID,
    current_user=Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
):
    sub = await _get_sub_or_404(subscription_id, get_active_org_id(current_user), session)

    # Allow if own subscription, or if org admin
    if sub.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only delete your own subscriptions")

    await session.delete(sub)
    await session.commit()
    return MessageResponse(message="Subscription deleted successfully")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_sub_or_404(sub_id: uuid.UUID, org_id: uuid.UUID, session: AsyncSession) -> Subscription:
    result = await session.execute(
        select(Subscription).where(Subscription.id == sub_id, Subscription.org_id == org_id)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
    return sub


def _to_response(sub: Subscription) -> SubscriptionResponse:
    return SubscriptionResponse(
        id=sub.id,
        org_id=sub.org_id,
        resource_type=sub.resource_type,
        resource_id=sub.resource_id,
        subscriber_user_id=sub.user_id,
        notify_on_update=sub.notify_on_update,
        subscribed_at=sub.subscribed_at,
    )

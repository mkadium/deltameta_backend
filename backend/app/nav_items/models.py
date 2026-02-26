"""
SQLAlchemy ORM models for the dynamic main left navigation hierarchy.

Tables:
  - nav_items             : N-level self-referencing tree of nav items
  - nav_item_org_overrides : per-org enable/disable
  - nav_item_user_overrides: per-user enable/disable
  - nav_item_policies     : attach existing ABAC policies to a nav item
"""
from __future__ import annotations

import uuid
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey,
    Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.auth.models import Base, SCHEMA


class NavItem(Base):
    __tablename__ = "nav_items"
    __table_args__ = (
        UniqueConstraint("parent_id", "slug", name="uq_nav_item_parent_slug"),
        {"schema": SCHEMA},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_id = Column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.nav_items.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    slug = Column(String(128), nullable=False, index=True)
    display_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(255), nullable=True)
    nav_url = Column(String(512), nullable=True)
    slug_path = Column(String(512), nullable=True)
    resource_key = Column(String(128), nullable=True, index=True)  # e.g. explore, lineage

    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    metadata_ = Column("metadata", JSONB, nullable=True, default=dict)

    created_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    parent = relationship("NavItem", remote_side="NavItem.id", back_populates="children")
    children = relationship("NavItem", back_populates="parent", order_by="NavItem.sort_order")

    org_overrides = relationship("NavItemOrgOverride", back_populates="node", cascade="all, delete-orphan")
    user_overrides = relationship("NavItemUserOverride", back_populates="node", cascade="all, delete-orphan")
    node_policies = relationship("NavItemPolicy", back_populates="node", cascade="all, delete-orphan")


class NavItemOrgOverride(Base):
    __tablename__ = "nav_item_org_overrides"
    __table_args__ = (
        UniqueConstraint("org_id", "node_id", name="uq_nav_item_org_override"),
        {"schema": SCHEMA},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_id = Column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.nav_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_enabled = Column(Boolean, nullable=False, default=True)
    config = Column(JSONB, nullable=True, default=dict)
    updated_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    node = relationship("NavItem", back_populates="org_overrides")


class NavItemUserOverride(Base):
    __tablename__ = "nav_item_user_overrides"
    __table_args__ = (
        UniqueConstraint("user_id", "node_id", name="uq_nav_item_user_override"),
        {"schema": SCHEMA},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_id = Column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.nav_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    node = relationship("NavItem", back_populates="user_overrides")


class NavItemPolicy(Base):
    __tablename__ = "nav_item_policies"
    __table_args__ = (
        UniqueConstraint("node_id", "policy_id", name="uq_nav_item_policy"),
        {"schema": SCHEMA},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    node_id = Column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.nav_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    policy_id = Column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.policies.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    node = relationship("NavItem", back_populates="node_policies")

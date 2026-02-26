"""
SQLAlchemy ORM models for the dynamic Settings hierarchy.

Tables:
  - setting_nodes          : N-level self-referencing tree of setting items
  - org_setting_overrides  : per-org enable/disable + config overrides
  - user_setting_overrides : per-user enable/disable (fine-grained)
  - setting_policies       : attach existing ABAC policies to a node
"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey,
    Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.auth.models import Base, SCHEMA


# ---------------------------------------------------------------------------
# SettingNode — N-level self-referencing tree
# ---------------------------------------------------------------------------

class SettingNode(Base):
    __tablename__ = "setting_nodes"
    __table_args__ = (
        UniqueConstraint("parent_id", "slug", name="uq_setting_node_parent_slug"),
        {"schema": SCHEMA},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_id = Column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.setting_nodes.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    slug = Column(String(128), nullable=False, index=True)
    display_label = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(255), nullable=True)        # icon name or URL
    node_type = Column(String(16), nullable=False, default="category")

    # Navigation fields (leaf nodes)
    nav_url = Column(String(512), nullable=True)         # relative path e.g. /integrations/postgres
    slug_path = Column(String(512), nullable=True)       # dot-path e.g. services.databases.postgres

    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)   # global platform toggle
    metadata_ = Column("metadata", JSONB, nullable=True, default=dict)  # extensible

    created_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Self-referencing
    parent = relationship("SettingNode", remote_side="SettingNode.id", back_populates="children")
    children = relationship("SettingNode", back_populates="parent", order_by="SettingNode.sort_order")

    # Overrides
    org_overrides = relationship("OrgSettingOverride", back_populates="node", cascade="all, delete-orphan")
    user_overrides = relationship("UserSettingOverride", back_populates="node", cascade="all, delete-orphan")
    node_policies = relationship("SettingPolicy", back_populates="node", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# OrgSettingOverride — org admin controls visibility per org
# ---------------------------------------------------------------------------

class OrgSettingOverride(Base):
    __tablename__ = "org_setting_overrides"
    __table_args__ = (
        UniqueConstraint("org_id", "node_id", name="uq_org_setting_override"),
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
        ForeignKey(f"{SCHEMA}.setting_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_enabled = Column(Boolean, nullable=False, default=True)
    config = Column(JSONB, nullable=True, default=dict)     # org-specific config overrides
    updated_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    node = relationship("SettingNode", back_populates="org_overrides")


# ---------------------------------------------------------------------------
# UserSettingOverride — fine-grained per-user control
# ---------------------------------------------------------------------------

class UserSettingOverride(Base):
    __tablename__ = "user_setting_overrides"
    __table_args__ = (
        UniqueConstraint("user_id", "node_id", name="uq_user_setting_override"),
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
        ForeignKey(f"{SCHEMA}.setting_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    node = relationship("SettingNode", back_populates="user_overrides")


# ---------------------------------------------------------------------------
# SettingPolicy — attach an ABAC policy to a setting node
# ---------------------------------------------------------------------------

class SettingPolicy(Base):
    __tablename__ = "setting_policies"
    __table_args__ = (
        UniqueConstraint("node_id", "policy_id", name="uq_setting_policy"),
        {"schema": SCHEMA},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    node_id = Column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.setting_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    policy_id = Column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.policies.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    node = relationship("SettingNode", back_populates="node_policies")

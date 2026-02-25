"""
SQLAlchemy ORM models for the Resource Registry.

Tables:
  - resource_groups       : groups (Identity & Access, Organization, etc.)
  - resource_definitions  : individual resources with valid operations list
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


class ResourceGroup(Base):
    __tablename__ = "resource_groups"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_resource_group_slug"),
        {"schema": SCHEMA},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug = Column(String(128), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now(), nullable=False)

    resources = relationship(
        "ResourceDefinition", back_populates="group",
        cascade="all, delete-orphan", order_by="ResourceDefinition.label",
    )


class ResourceDefinition(Base):
    __tablename__ = "resource_definitions"
    __table_args__ = (
        UniqueConstraint("key", name="uq_resource_definition_key"),
        {"schema": SCHEMA},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id = Column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.resource_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Unique key used in policies (e.g. "user", "team", "services.databases.postgres")
    key = Column(String(512), nullable=False, index=True)
    label = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    # e.g. ["read", "create", "update", "delete", "configure"]
    operations = Column(JSONB, nullable=False, default=list)
    # True = defined in code registry; False = dynamically added (leaf SettingNode)
    is_static = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=False, default=True)
    # FK back to SettingNode if this resource was created from a leaf node
    setting_node_id = Column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.setting_nodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now(), nullable=False)

    group = relationship("ResourceGroup", back_populates="resources")

"""
SQLAlchemy ORM models for the Auth & Organization Hierarchy.

All tables live in the `deltameta` schema.
"""
import uuid
from datetime import datetime
from typing import List, Optional

import sqlalchemy as sa
from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey,
    Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship

SCHEMA = "deltameta"


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

SSOProviderEnum = Enum(
    "default", "google", "cognito", "azure", "ldap", "oauth2",
    name="sso_provider_enum",
    schema=SCHEMA,
)

TeamTypeEnum = Enum(
    "business_unit", "division", "department", "group",
    name="team_type_enum",
    schema=SCHEMA,
)


# ---------------------------------------------------------------------------
# Association tables
# ---------------------------------------------------------------------------

user_organizations = sa.Table(
    "user_organizations",
    Base.metadata,
    Column("id", UUID(as_uuid=True), default=uuid.uuid4, primary_key=True),
    Column("user_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), nullable=False),
    Column("org_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False),
    Column("is_org_admin", Boolean, nullable=False, default=False),
    Column("is_active", Boolean, nullable=False, default=True),
    Column("joined_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    schema=SCHEMA,
)

role_policies = sa.Table(
    "role_policies",
    Base.metadata,
    Column("role_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.roles.id", ondelete="CASCADE"), primary_key=True),
    Column("policy_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.policies.id", ondelete="CASCADE"), primary_key=True),
    schema=SCHEMA,
)

user_teams = sa.Table(
    "user_teams",
    Base.metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), primary_key=True),
    Column("team_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.teams.id", ondelete="CASCADE"), primary_key=True),
    schema=SCHEMA,
)

user_roles = sa.Table(
    "user_roles",
    Base.metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.roles.id", ondelete="CASCADE"), primary_key=True),
    schema=SCHEMA,
)

user_policies = sa.Table(
    "user_policies",
    Base.metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), primary_key=True),
    Column("policy_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.policies.id", ondelete="CASCADE"), primary_key=True),
    schema=SCHEMA,
)


# ---------------------------------------------------------------------------
# Organization
# ---------------------------------------------------------------------------

class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    contact_email = Column(String(255), nullable=True)
    owner_id = Column(UUID(as_uuid=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    is_default = Column(Boolean, nullable=False, default=False)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    auth_config = relationship("AuthConfig", back_populates="organization", uselist=False, cascade="all, delete-orphan")
    domains = relationship("Domain", back_populates="organization", cascade="all, delete-orphan")
    teams = relationship("Team", back_populates="organization", cascade="all, delete-orphan")
    roles = relationship("Role", back_populates="organization", cascade="all, delete-orphan")
    policies = relationship("Policy", back_populates="organization", cascade="all, delete-orphan")
    users = relationship("User", foreign_keys="User.org_id", back_populates="organization", cascade="all, delete-orphan")
    profiler_configs = relationship("OrgProfilerConfig", back_populates="organization", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="organization")
    members = relationship("User", secondary=user_organizations, back_populates="member_orgs",
                           primaryjoin=lambda: Organization.id == user_organizations.c.org_id,
                           secondaryjoin=lambda: User.id == user_organizations.c.user_id,
                           viewonly=True)


# ---------------------------------------------------------------------------
# Auth Config (one per org — admin configures JWT + lockout)
# ---------------------------------------------------------------------------

class AuthConfig(Base):
    __tablename__ = "auth_config"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False, unique=True)
    jwt_expiry_minutes = Column(Integer, nullable=False, default=60)
    max_failed_attempts = Column(Integer, nullable=False, default=5)
    lockout_duration_minutes = Column(Integer, nullable=False, default=15)
    sso_provider = Column(SSOProviderEnum, nullable=False, default="default")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    organization = relationship("Organization", back_populates="auth_config")


# ---------------------------------------------------------------------------
# Domain
# ---------------------------------------------------------------------------

class Domain(Base):
    __tablename__ = "domains"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    domain_type = Column(String(100), nullable=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    organization = relationship("Organization", back_populates="domains")
    owner = relationship("User", foreign_keys=[owner_id], back_populates="owned_domains")
    teams = relationship("Team", back_populates="domain")
    users = relationship("User", foreign_keys="User.domain_id", back_populates="domain")


# ---------------------------------------------------------------------------
# Team (self-referencing hierarchy)
# ---------------------------------------------------------------------------

class Team(Base):
    __tablename__ = "teams"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False)
    parent_team_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.teams.id", ondelete="SET NULL"), nullable=True)
    domain_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.domains.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    team_type = Column(TeamTypeEnum, nullable=False, default="group")
    description = Column(Text, nullable=True)
    public_team_view = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    organization = relationship("Organization", back_populates="teams")
    domain = relationship("Domain", back_populates="teams")
    parent = relationship("Team", remote_side="Team.id", back_populates="children")
    children = relationship("Team", back_populates="parent")
    members = relationship("User", secondary=user_teams, back_populates="teams")


# ---------------------------------------------------------------------------
# Policy (ABAC — one rule per policy)
# ---------------------------------------------------------------------------

class Policy(Base):
    __tablename__ = "policies"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    rule_name = Column(String(255), nullable=False)
    resource = Column(String(512), nullable=False)
    # e.g. ["view", "create", "update", "delete"]
    operations = Column(JSONB, nullable=False, default=list)
    # e.g. [{"attr": "isAdmin", "op": "=", "value": "true"}, ...]
    conditions = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    organization = relationship("Organization", back_populates="policies")
    roles = relationship("Role", secondary=role_policies, back_populates="policies")
    users = relationship("User", secondary=user_policies, back_populates="policies")


# ---------------------------------------------------------------------------
# Role
# ---------------------------------------------------------------------------

class Role(Base):
    __tablename__ = "roles"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_system_role = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    organization = relationship("Organization", back_populates="roles")
    policies = relationship("Policy", secondary=role_policies, back_populates="roles")
    users = relationship("User", secondary=user_roles, back_populates="roles")


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False)
    default_org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="SET NULL"), nullable=True)
    domain_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.domains.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    username = Column(String(128), nullable=False, unique=True, index=True)
    hashed_password = Column(String(255), nullable=False)
    image = Column(String(512), nullable=True)
    is_admin = Column(Boolean, nullable=False, default=False)
    is_global_admin = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    is_verified = Column(Boolean, nullable=False, default=False)
    failed_attempts = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    organization = relationship("Organization", foreign_keys=[org_id], back_populates="users")
    default_org = relationship("Organization", foreign_keys=[default_org_id])
    domain = relationship("Domain", foreign_keys=[domain_id], back_populates="users")
    owned_domains = relationship("Domain", foreign_keys="Domain.owner_id", back_populates="owner")
    teams = relationship("Team", secondary=user_teams, back_populates="members")
    roles = relationship("Role", secondary=user_roles, back_populates="users")
    policies = relationship("Policy", secondary=user_policies, back_populates="users")
    subscriptions = relationship("Subscription", back_populates="user")
    member_orgs = relationship("Organization", secondary=user_organizations, back_populates="members",
                               primaryjoin=lambda: User.id == user_organizations.c.user_id,
                               secondaryjoin=lambda: Organization.id == user_organizations.c.org_id,
                               viewonly=True)


# ---------------------------------------------------------------------------
# Org Profiler Config (org-level datatype → metrics mapping)
# ---------------------------------------------------------------------------

class OrgProfilerConfig(Base):
    __tablename__ = "org_profiler_config"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False)
    # e.g. "bigint", "varchar", "timestamp", "boolean"
    datatype = Column(String(128), nullable=False)
    # e.g. ["column_count", "distinct_count", "min", "max", "mean", "null_count"]
    metric_types = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    organization = relationship("Organization", back_populates="profiler_configs")


# ---------------------------------------------------------------------------
# Subscription
# ---------------------------------------------------------------------------

class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), nullable=True)
    resource_type = Column(String(128), nullable=False)
    resource_id = Column(UUID(as_uuid=True), nullable=False)
    notify_on_update = Column(Boolean, nullable=False, default=True)
    subscribed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    organization = relationship("Organization", back_populates="subscriptions")
    user = relationship("User", back_populates="subscriptions")

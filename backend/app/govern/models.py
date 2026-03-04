"""
ORM models for Governance & Catalog tables (Phase 1).
Tables: subject_areas, catalog_domains, data_products, glossaries, glossary_terms,
        classifications, classification_tags, govern_metrics, lookup_categories,
        lookup_values, change_requests, activity_feeds, scheduled_tasks,
        storage_config, service_endpoints, org_roles, org_policies, team_roles, team_policies
All live in the `deltameta` schema.
"""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import List, Optional

import sqlalchemy as sa
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey,
    Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.auth.models import Base, SCHEMA

# ---------------------------------------------------------------------------
# Association tables (M2M)
# ---------------------------------------------------------------------------

org_roles = sa.Table(
    "org_roles", Base.metadata,
    Column("org_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.roles.id", ondelete="CASCADE"), primary_key=True),
    Column("assigned_at", DateTime(timezone=True), server_default=func.now()),
    schema=SCHEMA,
)

org_policies = sa.Table(
    "org_policies", Base.metadata,
    Column("org_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), primary_key=True),
    Column("policy_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.policies.id", ondelete="CASCADE"), primary_key=True),
    Column("assigned_at", DateTime(timezone=True), server_default=func.now()),
    schema=SCHEMA,
)

team_roles = sa.Table(
    "team_roles", Base.metadata,
    Column("team_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.teams.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.roles.id", ondelete="CASCADE"), primary_key=True),
    Column("assigned_at", DateTime(timezone=True), server_default=func.now()),
    schema=SCHEMA,
)

team_policies = sa.Table(
    "team_policies", Base.metadata,
    Column("team_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.teams.id", ondelete="CASCADE"), primary_key=True),
    Column("policy_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.policies.id", ondelete="CASCADE"), primary_key=True),
    Column("assigned_at", DateTime(timezone=True), server_default=func.now()),
    schema=SCHEMA,
)

catalog_domain_owners = sa.Table(
    "catalog_domain_owners", Base.metadata,
    Column("domain_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.catalog_domains.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), primary_key=True),
    schema=SCHEMA,
)

catalog_domain_experts = sa.Table(
    "catalog_domain_experts", Base.metadata,
    Column("domain_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.catalog_domains.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), primary_key=True),
    schema=SCHEMA,
)

data_product_owners = sa.Table(
    "data_product_owners", Base.metadata,
    Column("product_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.data_products.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), primary_key=True),
    schema=SCHEMA,
)

data_product_experts = sa.Table(
    "data_product_experts", Base.metadata,
    Column("product_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.data_products.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), primary_key=True),
    schema=SCHEMA,
)

glossary_term_owners = sa.Table(
    "glossary_term_owners", Base.metadata,
    Column("term_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.glossary_terms.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), primary_key=True),
    schema=SCHEMA,
)

glossary_term_reviewers = sa.Table(
    "glossary_term_reviewers", Base.metadata,
    Column("term_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.glossary_terms.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), primary_key=True),
    schema=SCHEMA,
)

glossary_term_related = sa.Table(
    "glossary_term_related", Base.metadata,
    Column("term_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.glossary_terms.id", ondelete="CASCADE"), primary_key=True),
    Column("related_term_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.glossary_terms.id", ondelete="CASCADE"), primary_key=True),
    schema=SCHEMA,
)

glossary_term_likes = sa.Table(
    "glossary_term_likes", Base.metadata,
    Column("term_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.glossary_terms.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    schema=SCHEMA,
)

classification_owners = sa.Table(
    "classification_owners", Base.metadata,
    Column("classification_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.classifications.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), primary_key=True),
    schema=SCHEMA,
)

classification_domain_refs = sa.Table(
    "classification_domain_refs", Base.metadata,
    Column("classification_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.classifications.id", ondelete="CASCADE"), primary_key=True),
    Column("domain_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.catalog_domains.id", ondelete="CASCADE"), primary_key=True),
    schema=SCHEMA,
)

classification_tag_owners = sa.Table(
    "classification_tag_owners", Base.metadata,
    Column("tag_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.classification_tags.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), primary_key=True),
    schema=SCHEMA,
)

classification_tag_domain_refs = sa.Table(
    "classification_tag_domain_refs", Base.metadata,
    Column("tag_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.classification_tags.id", ondelete="CASCADE"), primary_key=True),
    Column("domain_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.catalog_domains.id", ondelete="CASCADE"), primary_key=True),
    schema=SCHEMA,
)

govern_metric_owners = sa.Table(
    "govern_metric_owners", Base.metadata,
    Column("metric_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.govern_metrics.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), primary_key=True),
    schema=SCHEMA,
)

change_request_assignees = sa.Table(
    "change_request_assignees", Base.metadata,
    Column("change_request_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.change_requests.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), primary_key=True),
    schema=SCHEMA,
)


# SubjectArea is the same as auth.models.Domain (table renamed to subject_areas).
# Use app.auth.models.Domain for subject areas queries.

# ---------------------------------------------------------------------------
# Dataset & DataAsset M2M association tables
# ---------------------------------------------------------------------------

dataset_owners = sa.Table(
    "dataset_owners", Base.metadata,
    Column("dataset_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.datasets.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), primary_key=True),
    schema=SCHEMA,
)

dataset_experts = sa.Table(
    "dataset_experts", Base.metadata,
    Column("dataset_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.datasets.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), primary_key=True),
    schema=SCHEMA,
)

data_asset_owners = sa.Table(
    "data_asset_owners", Base.metadata,
    Column("asset_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.data_assets.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), primary_key=True),
    schema=SCHEMA,
)

data_asset_experts = sa.Table(
    "data_asset_experts", Base.metadata,
    Column("asset_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.data_assets.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), primary_key=True),
    schema=SCHEMA,
)

data_asset_tags = sa.Table(
    "data_asset_tags", Base.metadata,
    Column("asset_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.data_assets.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.classification_tags.id", ondelete="CASCADE"), primary_key=True),
    schema=SCHEMA,
)

# ---------------------------------------------------------------------------
# CatalogDomain (governance domain in the data catalog)
# ---------------------------------------------------------------------------

class CatalogDomain(Base):
    __tablename__ = "catalog_domains"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    domain_type = Column(String(100), nullable=True)
    icon = Column(String(512), nullable=True)
    color = Column(String(50), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    owners = relationship("User", secondary=catalog_domain_owners, lazy="selectin",
                          primaryjoin=lambda: CatalogDomain.id == catalog_domain_owners.c.domain_id,
                          secondaryjoin=lambda: __import__('app.auth.models', fromlist=['User']).User.id == catalog_domain_owners.c.user_id)
    experts = relationship("User", secondary=catalog_domain_experts, lazy="selectin",
                           primaryjoin=lambda: CatalogDomain.id == catalog_domain_experts.c.domain_id,
                           secondaryjoin=lambda: __import__('app.auth.models', fromlist=['User']).User.id == catalog_domain_experts.c.user_id)


# ---------------------------------------------------------------------------
# DataProduct
# ---------------------------------------------------------------------------

class DataProduct(Base):
    __tablename__ = "data_products"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False)
    domain_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.catalog_domains.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    version = Column(String(50), nullable=False, default="0.1")
    status = Column(String(50), nullable=False, default="draft")
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    owners = relationship("User", secondary=data_product_owners, lazy="selectin",
                          primaryjoin=lambda: DataProduct.id == data_product_owners.c.product_id,
                          secondaryjoin=lambda: __import__('app.auth.models', fromlist=['User']).User.id == data_product_owners.c.user_id)
    experts = relationship("User", secondary=data_product_experts, lazy="selectin",
                           primaryjoin=lambda: DataProduct.id == data_product_experts.c.product_id,
                           secondaryjoin=lambda: __import__('app.auth.models', fromlist=['User']).User.id == data_product_experts.c.user_id)


# ---------------------------------------------------------------------------
# LookupCategory + LookupValue
# ---------------------------------------------------------------------------

class LookupCategory(Base):
    __tablename__ = "lookup_categories"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_system = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    values = relationship("LookupValue", back_populates="category", cascade="all, delete-orphan", lazy="selectin")


class LookupValue(Base):
    __tablename__ = "lookup_values"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.lookup_categories.id", ondelete="CASCADE"), nullable=False)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=True)
    label = Column(String(255), nullable=False)
    value = Column(String(255), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    category = relationship("LookupCategory", back_populates="values")


# ---------------------------------------------------------------------------
# Glossary + GlossaryTerm
# ---------------------------------------------------------------------------

class Glossary(Base):
    __tablename__ = "glossaries"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    terms = relationship("GlossaryTerm", back_populates="glossary", cascade="all, delete-orphan")


class GlossaryTerm(Base):
    __tablename__ = "glossary_terms"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    glossary_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.glossaries.id", ondelete="CASCADE"), nullable=False)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    icon_url = Column(String(512), nullable=True)
    color = Column(String(50), nullable=True)
    mutually_exclusive = Column(Boolean, nullable=False, default=False)
    synonyms = Column(JSONB, nullable=False, default=list)
    references_data = Column(JSONB, nullable=False, default=list)
    likes_count = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    glossary = relationship("Glossary", back_populates="terms")
    owners = relationship("User", secondary=glossary_term_owners, lazy="selectin",
                          primaryjoin=lambda: GlossaryTerm.id == glossary_term_owners.c.term_id,
                          secondaryjoin=lambda: __import__('app.auth.models', fromlist=['User']).User.id == glossary_term_owners.c.user_id)
    reviewers = relationship("User", secondary=glossary_term_reviewers, lazy="selectin",
                             primaryjoin=lambda: GlossaryTerm.id == glossary_term_reviewers.c.term_id,
                             secondaryjoin=lambda: __import__('app.auth.models', fromlist=['User']).User.id == glossary_term_reviewers.c.user_id)
    related_terms = relationship(
        "GlossaryTerm", secondary=glossary_term_related,
        primaryjoin=lambda: GlossaryTerm.id == glossary_term_related.c.term_id,
        secondaryjoin=lambda: GlossaryTerm.id == glossary_term_related.c.related_term_id,
        lazy="selectin",
    )
    liked_by = relationship("User", secondary=glossary_term_likes, lazy="selectin",
                            primaryjoin=lambda: GlossaryTerm.id == glossary_term_likes.c.term_id,
                            secondaryjoin=lambda: __import__('app.auth.models', fromlist=['User']).User.id == glossary_term_likes.c.user_id)


# ---------------------------------------------------------------------------
# Classification + ClassificationTag
# ---------------------------------------------------------------------------

class Classification(Base):
    __tablename__ = "classifications"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    mutually_exclusive = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    tags = relationship("ClassificationTag", back_populates="classification", cascade="all, delete-orphan")
    owners = relationship("User", secondary=classification_owners, lazy="selectin",
                          primaryjoin=lambda: Classification.id == classification_owners.c.classification_id,
                          secondaryjoin=lambda: __import__('app.auth.models', fromlist=['User']).User.id == classification_owners.c.user_id)
    domains = relationship("CatalogDomain", secondary=classification_domain_refs, lazy="selectin",
                           primaryjoin=lambda: Classification.id == classification_domain_refs.c.classification_id,
                           secondaryjoin=lambda: CatalogDomain.id == classification_domain_refs.c.domain_id)


class ClassificationTag(Base):
    __tablename__ = "classification_tags"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    classification_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.classifications.id", ondelete="CASCADE"), nullable=False)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    icon_url = Column(String(512), nullable=True)
    color = Column(String(50), nullable=True)
    detection_patterns = Column(JSONB, nullable=False, default=list)
    auto_classify = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    classification = relationship("Classification", back_populates="tags")
    owners = relationship("User", secondary=classification_tag_owners, lazy="selectin",
                          primaryjoin=lambda: ClassificationTag.id == classification_tag_owners.c.tag_id,
                          secondaryjoin=lambda: __import__('app.auth.models', fromlist=['User']).User.id == classification_tag_owners.c.user_id)
    domains = relationship("CatalogDomain", secondary=classification_tag_domain_refs, lazy="selectin",
                           primaryjoin=lambda: ClassificationTag.id == classification_tag_domain_refs.c.tag_id,
                           secondaryjoin=lambda: CatalogDomain.id == classification_tag_domain_refs.c.domain_id)


# ---------------------------------------------------------------------------
# GovernMetric
# ---------------------------------------------------------------------------

class GovernMetric(Base):
    __tablename__ = "govern_metrics"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    granularity = Column(String(50), nullable=True)
    metric_type = Column(String(100), nullable=True)
    language = Column(String(50), nullable=True)
    measurement_unit = Column(String(100), nullable=True)
    code = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    owners = relationship("User", secondary=govern_metric_owners, lazy="selectin",
                          primaryjoin=lambda: GovernMetric.id == govern_metric_owners.c.metric_id,
                          secondaryjoin=lambda: __import__('app.auth.models', fromlist=['User']).User.id == govern_metric_owners.c.user_id)


# ---------------------------------------------------------------------------
# ChangeRequest
# ---------------------------------------------------------------------------

class ChangeRequest(Base):
    __tablename__ = "change_requests"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False)
    entity_type = Column(String(100), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    field_name = Column(String(255), nullable=False)
    current_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=False)
    title = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    status = Column(String(50), nullable=False, default="open")
    requested_by = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"), nullable=True)
    resolved_by = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    assignees = relationship("User", secondary=change_request_assignees, lazy="selectin",
                             primaryjoin=lambda: ChangeRequest.id == change_request_assignees.c.change_request_id,
                             secondaryjoin=lambda: __import__('app.auth.models', fromlist=['User']).User.id == change_request_assignees.c.user_id)


# ---------------------------------------------------------------------------
# ActivityFeed
# ---------------------------------------------------------------------------

class ActivityFeed(Base):
    __tablename__ = "activity_feeds"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=True)
    actor_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"), nullable=True)
    entity_type = Column(String(100), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=True)
    action = Column(String(100), nullable=False)
    details = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# ScheduledTask
# ---------------------------------------------------------------------------

class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=True)
    entity_type = Column(String(100), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=True)
    task_name = Column(String(255), nullable=False)
    schedule_type = Column(String(50), nullable=False, default="manual")
    cron_expr = Column(String(100), nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    last_status = Column(String(50), nullable=True)
    payload = Column(JSONB, nullable=False, default=dict)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# StorageConfig
# ---------------------------------------------------------------------------

class StorageConfig(Base):
    __tablename__ = "storage_config"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=True)
    provider = Column(String(50), nullable=False, default="minio")
    # storage_type: minio | s3 | gcs | azure_blob
    storage_type = Column(String(50), nullable=False, default="minio")
    endpoint = Column(String(512), nullable=True)
    bucket = Column(String(255), nullable=True)
    access_key = Column(String(255), nullable=True)
    secret_key = Column(String(512), nullable=True)
    region = Column(String(100), nullable=True)
    extra = Column(JSONB, nullable=False, default=dict)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# ServiceEndpoint
# ---------------------------------------------------------------------------

class ServiceEndpoint(Base):
    __tablename__ = "service_endpoints"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=True)
    service_name = Column(String(100), nullable=False)
    base_url = Column(String(512), nullable=False)
    extra = Column(JSONB, nullable=False, default=dict)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# Dataset  (raw data collection: DB schema, S3 bucket, API source, etc.)
# ---------------------------------------------------------------------------

class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False)
    domain_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.catalog_domains.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    # e.g. "database", "schema", "s3_bucket", "api", "file"
    source_type = Column(String(100), nullable=True)
    source_url = Column(String(512), nullable=True)
    tags = Column(JSONB, nullable=False, default=list, doc="Free-form string tags for quick labelling")
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    domain = relationship("CatalogDomain", foreign_keys=[domain_id])
    assets = relationship("DataAsset", back_populates="dataset", cascade="all, delete-orphan")
    owners = relationship(
        "User", secondary=dataset_owners, lazy="selectin",
        primaryjoin=lambda: Dataset.id == dataset_owners.c.dataset_id,
        secondaryjoin=lambda: __import__('app.auth.models', fromlist=['User']).User.id == dataset_owners.c.user_id,
    )
    experts = relationship(
        "User", secondary=dataset_experts, lazy="selectin",
        primaryjoin=lambda: Dataset.id == dataset_experts.c.dataset_id,
        secondaryjoin=lambda: __import__('app.auth.models', fromlist=['User']).User.id == dataset_experts.c.user_id,
    )


# ---------------------------------------------------------------------------
# DataAsset  (cataloged asset: table, view, file, API endpoint)
# ---------------------------------------------------------------------------

class DataAsset(Base):
    __tablename__ = "data_assets"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False)
    dataset_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.datasets.id", ondelete="CASCADE"), nullable=False)
    data_product_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.data_products.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    # e.g. "table", "view", "materialized_view", "file", "api_endpoint", "stream"
    asset_type = Column(String(100), nullable=False, default="table")
    # Fully qualified name: e.g. "mydb.public.sales_transactions"
    fully_qualified_name = Column(String(512), nullable=True)
    # Sensitivity: "public", "internal", "confidential", "restricted"
    sensitivity = Column(String(50), nullable=True, default="internal")
    row_count = Column(Integer, nullable=True)
    size_bytes = Column(Integer, nullable=True)
    is_pii = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    # tier: "1" | "2" | "3" | "4" | "5" — data criticality tier (Tier 1 = most critical)
    tier = Column(String(10), nullable=True)
    # source_type: "manual" | "upload" | "connection_sync" | "bot_scan"
    source_type = Column(String(50), nullable=False, default="manual")
    created_by = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    dataset = relationship("Dataset", back_populates="assets")
    data_product = relationship("DataProduct", foreign_keys=[data_product_id])
    columns = relationship("DataAssetColumn", back_populates="asset", cascade="all, delete-orphan", lazy="selectin")
    owners = relationship(
        "User", secondary=data_asset_owners, lazy="selectin",
        primaryjoin=lambda: DataAsset.id == data_asset_owners.c.asset_id,
        secondaryjoin=lambda: __import__('app.auth.models', fromlist=['User']).User.id == data_asset_owners.c.user_id,
    )
    experts = relationship(
        "User", secondary=data_asset_experts, lazy="selectin",
        primaryjoin=lambda: DataAsset.id == data_asset_experts.c.asset_id,
        secondaryjoin=lambda: __import__('app.auth.models', fromlist=['User']).User.id == data_asset_experts.c.user_id,
    )
    classification_tags = relationship(
        "ClassificationTag", secondary=data_asset_tags, lazy="selectin",
        primaryjoin=lambda: DataAsset.id == data_asset_tags.c.asset_id,
        secondaryjoin=lambda: ClassificationTag.id == data_asset_tags.c.tag_id,
    )


# ---------------------------------------------------------------------------
# DataAssetColumn  (column-level schema metadata)
# ---------------------------------------------------------------------------

class DataAssetColumn(Base):
    __tablename__ = "data_asset_columns"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.data_assets.id", ondelete="CASCADE"), nullable=False)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    # e.g. "bigint", "varchar", "timestamp", "boolean", "float", "json"
    data_type = Column(String(100), nullable=False, default="varchar")
    ordinal_position = Column(Integer, nullable=False, default=0)
    is_nullable = Column(Boolean, nullable=False, default=True)
    is_primary_key = Column(Boolean, nullable=False, default=False)
    is_foreign_key = Column(Boolean, nullable=False, default=False)
    is_pii = Column(Boolean, nullable=False, default=False)
    # Sensitivity override at column level
    sensitivity = Column(String(50), nullable=True)
    default_value = Column(String(512), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    asset = relationship("DataAsset", back_populates="columns")


# ---------------------------------------------------------------------------
# Bot  (automated scanner/agent configuration)
# ---------------------------------------------------------------------------

class Bot(Base):
    __tablename__ = "bots"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    # bot_type: metadata | profiler | lineage | usage | classification | search_index | test_suite | rdf_export | embedding
    bot_type = Column(String(50), nullable=False)
    # mode: self (built-in agent code) | external (LLM API via service_endpoint)
    mode = Column(String(20), nullable=False, default="self")
    is_enabled = Column(Boolean, nullable=False, default=False)
    # trigger_mode: on_demand | scheduled
    trigger_mode = Column(String(20), nullable=False, default="on_demand")
    cron_expr = Column(String(100), nullable=True)
    # external mode: FK to service_endpoints holding base_url + api_key
    service_endpoint_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.service_endpoints.id", ondelete="SET NULL"), nullable=True)
    # external mode: LLM model name (e.g. gpt-4o, claude-3-5-sonnet)
    model_name = Column(String(100), nullable=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    # last_run_status: running | success | failed
    last_run_status = Column(String(20), nullable=True)
    last_run_message = Column(Text, nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    service_endpoint = relationship("ServiceEndpoint", foreign_keys=[service_endpoint_id])
    runs = relationship("BotRun", back_populates="bot", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# BotRun  (individual execution record for each bot invocation)
# ---------------------------------------------------------------------------

class BotRun(Base):
    __tablename__ = "bot_runs"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bot_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.bots.id", ondelete="CASCADE"), nullable=False)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False)
    triggered_by = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"), nullable=True)
    # trigger_source: "on_demand" | "scheduled" | "api"
    trigger_source = Column(String(50), nullable=False, default="on_demand")
    # status: pending | running | success | failed | aborted
    status = Column(String(20), nullable=False, default="pending")
    # Summary message (e.g. "Scanned 42 tables, created 18 assets")
    message = Column(Text, nullable=True)
    # Detailed run output / error traceback
    output = Column(JSONB, nullable=False, default=dict)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    bot = relationship("Bot", back_populates="runs", foreign_keys=[bot_id])


# ---------------------------------------------------------------------------
# DataAssetProfile  (one profiling run per data asset)
# ---------------------------------------------------------------------------

class DataAssetProfile(Base):
    __tablename__ = "data_asset_profiles"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.data_assets.id", ondelete="CASCADE"), nullable=False)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False)
    triggered_by = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"), nullable=True)
    # status: pending | running | success | failed
    status = Column(String(20), nullable=False, default="pending")
    row_count = Column(Integer, nullable=True)
    # Asset-level stats: { "table_size_bytes": ..., "column_count": ..., "sample_size": ... }
    profile_data = Column(JSONB, nullable=False, default=dict)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    asset = relationship("DataAsset", foreign_keys=[asset_id])
    column_profiles = relationship(
        "ColumnProfile", back_populates="profile",
        cascade="all, delete-orphan", lazy="selectin",
    )


# ---------------------------------------------------------------------------
# ColumnProfile  (per-column statistics for a profiling run)
# ---------------------------------------------------------------------------

class ColumnProfile(Base):
    __tablename__ = "column_profiles"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.data_asset_profiles.id", ondelete="CASCADE"), nullable=False)
    column_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.data_asset_columns.id", ondelete="SET NULL"), nullable=True)
    asset_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.data_assets.id", ondelete="CASCADE"), nullable=False)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False)
    column_name = Column(String(255), nullable=False)
    data_type = Column(String(100), nullable=True)
    null_count = Column(Integer, nullable=True)
    null_pct = Column(sa.Float, nullable=True)
    distinct_count = Column(Integer, nullable=True)
    min_val = Column(String(512), nullable=True)
    max_val = Column(String(512), nullable=True)
    mean_val = Column(sa.Float, nullable=True)
    stddev_val = Column(sa.Float, nullable=True)
    # [{"value": "...", "count": N}, ...]
    top_values = Column(JSONB, nullable=False, default=list)
    # [{"bucket": "...", "count": N}, ...]
    histogram = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    profile = relationship("DataAssetProfile", back_populates="column_profiles")


# ---------------------------------------------------------------------------
# LineageEdge  (directed edge in the data lineage graph)
# ---------------------------------------------------------------------------

class LineageEdge(Base):
    __tablename__ = "lineage_edges"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False)
    source_asset_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.data_assets.id", ondelete="CASCADE"), nullable=False)
    target_asset_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.data_assets.id", ondelete="CASCADE"), nullable=False)
    # edge_type: direct | derived | copy | aggregated
    edge_type = Column(String(50), nullable=False, default="direct")
    # SQL snippet or free-text description of the transformation
    transformation = Column(Text, nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    source_asset = relationship("DataAsset", foreign_keys=[source_asset_id])
    target_asset = relationship("DataAsset", foreign_keys=[target_asset_id])


# ---------------------------------------------------------------------------
# QualityTestCase
# ---------------------------------------------------------------------------

class QualityTestCase(Base):
    __tablename__ = "quality_test_cases"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False)
    asset_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.data_assets.id", ondelete="CASCADE"), nullable=False)
    column_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.data_asset_columns.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    # level: table | column | dimension
    level = Column(String(20), nullable=False, default="table")
    # test_type: row_count_between | row_count_equal | column_count_between | column_count_equal |
    #            column_name_exists | column_name_match_set | custom_sql | compare_tables | row_inserted_between
    test_type = Column(String(50), nullable=False)
    # dimension: accuracy | completeness | consistency | integrity | uniqueness | validity | sql | no_dimension
    dimension = Column(String(50), nullable=True)
    # e.g. {"min": 100, "max": 5000} or {"sql": "SELECT COUNT(*) FROM ..."}
    config = Column(JSONB, nullable=False, default=dict)
    # severity: info | warning | critical
    severity = Column(String(20), nullable=False, default="warning")
    tags = Column(JSONB, nullable=False, default=list)
    glossary_term_ids = Column(JSONB, nullable=False, default=list)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    asset = relationship("DataAsset", foreign_keys=[asset_id])
    runs = relationship("QualityTestRun", back_populates="test_case",
                        primaryjoin="QualityTestRun.test_case_id == QualityTestCase.id",
                        cascade="all, delete-orphan")
    incidents = relationship("QualityIncident", back_populates="test_case", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# QualityTestSuite
# ---------------------------------------------------------------------------

class QualityTestSuite(Base):
    __tablename__ = "quality_test_suites"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    # suite_type: table | bundle
    suite_type = Column(String(20), nullable=False, default="bundle")
    # table suites are linked to one asset
    asset_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.data_assets.id", ondelete="SET NULL"), nullable=True)
    # ordered list of QualityTestCase UUIDs
    test_case_ids = Column(JSONB, nullable=False, default=list)
    owner_ids = Column(JSONB, nullable=False, default=list)
    has_pipeline = Column(Boolean, nullable=False, default=False)
    # trigger_mode: on_demand | scheduled (only relevant when has_pipeline=True)
    trigger_mode = Column(String(20), nullable=False, default="on_demand")
    cron_expr = Column(String(100), nullable=True)
    enable_debug_log = Column(Boolean, nullable=False, default=False)
    raise_on_error = Column(Boolean, nullable=False, default=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    asset = relationship("DataAsset", foreign_keys=[asset_id])
    runs = relationship("QualityTestRun", back_populates="test_suite",
                        primaryjoin="QualityTestRun.test_suite_id == QualityTestSuite.id",
                        cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# QualityTestRun  (one execution of a test case or test suite)
# ---------------------------------------------------------------------------

class QualityTestRun(Base):
    __tablename__ = "quality_test_runs"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False)
    test_case_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.quality_test_cases.id", ondelete="CASCADE"), nullable=True)
    test_suite_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.quality_test_suites.id", ondelete="CASCADE"), nullable=True)
    triggered_by = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"), nullable=True)
    # status: pending | running | success | aborted | failed
    status = Column(String(20), nullable=False, default="pending")
    # {"pass_count": N, "fail_count": N, "error": "...", "samples": [...]}
    result_detail = Column(JSONB, nullable=False, default=dict)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    test_case = relationship("QualityTestCase", back_populates="runs",
                             foreign_keys=[test_case_id], primaryjoin="QualityTestRun.test_case_id == QualityTestCase.id")
    test_suite = relationship("QualityTestSuite", back_populates="runs",
                              foreign_keys=[test_suite_id], primaryjoin="QualityTestRun.test_suite_id == QualityTestSuite.id")


# ---------------------------------------------------------------------------
# QualityIncident  (auto-created when a run fails or is aborted)
# ---------------------------------------------------------------------------

class QualityIncident(Base):
    __tablename__ = "quality_incidents"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False)
    test_case_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.quality_test_cases.id", ondelete="CASCADE"), nullable=False)
    test_run_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.quality_test_runs.id", ondelete="SET NULL"), nullable=True)
    asset_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.data_assets.id", ondelete="CASCADE"), nullable=False)
    assignee_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"), nullable=True)
    # status: open | in_progress | resolved | ignored
    status = Column(String(20), nullable=False, default="open")
    # severity: info | warning | critical
    severity = Column(String(20), nullable=False, default="warning")
    failed_reason = Column(Text, nullable=True)
    aborted_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    test_case = relationship("QualityTestCase", back_populates="incidents", foreign_keys=[test_case_id])
    asset = relationship("DataAsset", foreign_keys=[asset_id])

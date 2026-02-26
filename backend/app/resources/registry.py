"""
Static Resource Registry — code-level source of truth.

Every resource that can be referenced in an ABAC Policy must be listed here.
Developers add new entries when they create new platform features.

Structure:
  RESOURCE_GROUPS  — ordered list of group definitions
  RESOURCE_REGISTRY — flat list of all resource definitions

A "sync" operation pushes this registry into the DB (resource_groups +
resource_definitions tables) and also pulls in all active leaf SettingNodes
as resources under their respective groups.

Leaf SettingNodes are registered dynamically (key = slug_path, e.g.
"services.databases.postgres"). Platform resources below are static.
"""
from __future__ import annotations
from typing import List, Dict, Any

# ---------------------------------------------------------------------------
# Resource Groups
# ---------------------------------------------------------------------------

RESOURCE_GROUPS: List[Dict[str, Any]] = [
    {
        "slug": "identity-access",
        "name": "Identity & Access",
        "description": "Users, roles, and permissions management",
        "sort_order": 1,
    },
    {
        "slug": "organization",
        "name": "Organization",
        "description": "Organizations and team hierarchy",
        "sort_order": 2,
    },
    {
        "slug": "platform-settings",
        "name": "Platform Settings",
        "description": "Platform-level configuration and settings hierarchy",
        "sort_order": 3,
    },
    {
        "slug": "data-catalog",
        "name": "Data Catalog",
        "description": "Domains, datasets, and data products",
        "sort_order": 4,
    },
    {
        "slug": "integrations",
        "name": "Integrations",
        "description": "External service and database integrations (leaf setting nodes)",
        "sort_order": 5,
    },
    {
        "slug": "subscriptions",
        "name": "Subscriptions",
        "description": "Resource subscription and notification management",
        "sort_order": 6,
    },
    {
        "slug": "main-navigation",
        "name": "Main Navigation",
        "description": "Portal main left navigation items — policy-driven visibility",
        "sort_order": 7,
    },
]

# ---------------------------------------------------------------------------
# Static Resource Definitions
# Leaf SettingNodes are added dynamically by the sync service.
# ---------------------------------------------------------------------------

RESOURCE_REGISTRY: List[Dict[str, Any]] = [
    # ── Identity & Access ───────────────────────────────────────────────────
    {
        "group_slug": "identity-access",
        "key": "user",
        "label": "User",
        "description": "Platform user accounts",
        "operations": ["read", "create", "update", "delete", "impersonate"],
        "is_static": True,
    },
    {
        "group_slug": "identity-access",
        "key": "role",
        "label": "Role",
        "description": "User roles within an organization",
        "operations": ["read", "create", "update", "delete", "assign", "revoke"],
        "is_static": True,
    },
    {
        "group_slug": "identity-access",
        "key": "policy",
        "label": "Policy",
        "description": "ABAC access control policies",
        "operations": ["read", "create", "update", "delete", "attach", "detach"],
        "is_static": True,
    },
    {
        "group_slug": "identity-access",
        "key": "auth_config",
        "label": "Auth Config",
        "description": "Authentication configuration (JWT, lockout, SSO)",
        "operations": ["read", "update"],
        "is_static": True,
    },

    # ── Organization ────────────────────────────────────────────────────────
    {
        "group_slug": "organization",
        "key": "organization",
        "label": "Organization",
        "description": "Organizations (multi-tenant units)",
        "operations": ["read", "create", "update", "delete", "manage_members"],
        "is_static": True,
    },
    {
        "group_slug": "organization",
        "key": "team",
        "label": "Team",
        "description": "Teams within an organization (BU, Division, Dept, Group)",
        "operations": ["read", "create", "update", "delete", "manage_members"],
        "is_static": True,
    },

    # ── Platform Settings ───────────────────────────────────────────────────
    {
        "group_slug": "platform-settings",
        "key": "setting_node",
        "label": "Setting Node",
        "description": "Setting hierarchy node (category or leaf)",
        "operations": ["read", "create", "update", "delete", "manage"],
        "is_static": True,
    },
    {
        "group_slug": "platform-settings",
        "key": "org_preference",
        "label": "Org Preference",
        "description": "Organization-level preferences and profiler config",
        "operations": ["read", "update"],
        "is_static": True,
    },

    # ── Data Catalog ────────────────────────────────────────────────────────
    {
        "group_slug": "data-catalog",
        "key": "domain",
        "label": "Domain",
        "description": "Data domains for organizing data assets",
        "operations": ["read", "create", "update", "delete"],
        "is_static": True,
    },
    {
        "group_slug": "data-catalog",
        "key": "dataset",
        "label": "Dataset",
        "description": "Datasets within a domain",
        "operations": ["read", "create", "update", "delete", "publish"],
        "is_static": True,
    },
    {
        "group_slug": "data-catalog",
        "key": "data_asset",
        "label": "Data Asset",
        "description": "Individual data assets (tables, files, etc.)",
        "operations": ["read", "create", "update", "delete", "publish"],
        "is_static": True,
    },
    {
        "group_slug": "data-catalog",
        "key": "data_product",
        "label": "Data Product",
        "description": "Curated data products",
        "operations": ["read", "create", "update", "delete", "publish"],
        "is_static": True,
    },

    # ── Subscriptions ───────────────────────────────────────────────────────
    {
        "group_slug": "subscriptions",
        "key": "subscription",
        "label": "Subscription",
        "description": "Resource subscriptions and change notifications",
        "operations": ["read", "create", "delete"],
        "is_static": True,
    },

    # ── Main Navigation ─────────────────────────────────────────────────────
    {
        "group_slug": "main-navigation",
        "key": "home",
        "label": "Home",
        "description": "Portal home with stats and global search (always visible)",
        "operations": ["read"],
        "is_static": True,
    },
    {
        "group_slug": "main-navigation",
        "key": "explore",
        "label": "Explore",
        "description": "Explore data assets",
        "operations": ["read"],
        "is_static": True,
    },
    {
        "group_slug": "main-navigation",
        "key": "lineage",
        "label": "Lineage",
        "description": "Data lineage and lineage graphs",
        "operations": ["read"],
        "is_static": True,
    },
    {
        "group_slug": "main-navigation",
        "key": "observability",
        "label": "Observability",
        "description": "Observability hub",
        "operations": ["read"],
        "is_static": True,
    },
    {
        "group_slug": "main-navigation",
        "key": "data_quality",
        "label": "Data Quality",
        "description": "Data quality metrics and rules",
        "operations": ["read"],
        "is_static": True,
    },
    {
        "group_slug": "main-navigation",
        "key": "incidents",
        "label": "Incidents",
        "description": "Data incidents tracking",
        "operations": ["read"],
        "is_static": True,
    },
    {
        "group_slug": "main-navigation",
        "key": "alerts",
        "label": "Alerts",
        "description": "Data quality and monitoring alerts",
        "operations": ["read"],
        "is_static": True,
    },
    {
        "group_slug": "main-navigation",
        "key": "insights",
        "label": "Insights",
        "description": "Analytics and insights",
        "operations": ["read"],
        "is_static": True,
    },
    {
        "group_slug": "main-navigation",
        "key": "domains",
        "label": "Domains",
        "description": "Data domains management",
        "operations": ["read"],
        "is_static": True,
    },
    {
        "group_slug": "main-navigation",
        "key": "data_products",
        "label": "Data Products",
        "description": "Data products catalog",
        "operations": ["read"],
        "is_static": True,
    },
    {
        "group_slug": "main-navigation",
        "key": "govern",
        "label": "Govern",
        "description": "Governance hub",
        "operations": ["read"],
        "is_static": True,
    },
    {
        "group_slug": "main-navigation",
        "key": "glossary",
        "label": "Glossary",
        "description": "Business glossary",
        "operations": ["read"],
        "is_static": True,
    },
    {
        "group_slug": "main-navigation",
        "key": "classification",
        "label": "Classification",
        "description": "Data classification and tags",
        "operations": ["read"],
        "is_static": True,
    },
    {
        "group_slug": "main-navigation",
        "key": "metrics",
        "label": "Metrics",
        "description": "Business and data metrics",
        "operations": ["read"],
        "is_static": True,
    },

    # ── Integrations (static defaults — leaf nodes add more dynamically) ────
    {
        "group_slug": "integrations",
        "key": "integration",
        "label": "Integration (Generic)",
        "description": "Generic integration resource — specific integrations are leaf nodes",
        "operations": ["read", "configure", "connect", "disconnect", "delete"],
        "is_static": True,
    },
]


# ---------------------------------------------------------------------------
# Helpers for lookup
# ---------------------------------------------------------------------------

def get_group_by_slug(slug: str) -> Dict[str, Any] | None:
    return next((g for g in RESOURCE_GROUPS if g["slug"] == slug), None)


def get_resource_by_key(key: str) -> Dict[str, Any] | None:
    return next((r for r in RESOURCE_REGISTRY if r["key"] == key), None)


def get_all_keys() -> List[str]:
    return [r["key"] for r in RESOURCE_REGISTRY]


# Default operations for dynamically created leaf setting nodes
LEAF_NODE_DEFAULT_OPERATIONS = ["read", "configure"]

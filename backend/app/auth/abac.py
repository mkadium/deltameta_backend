"""
ABAC (Attribute-Based Access Control) Engine.

Policies are stored in the `policies` table.  Each policy has:
  - resource: a resource key (e.g. "glossary_term")
  - operations: list of allowed ops (e.g. ["read", "create"])
  - conditions: list of attribute conditions that must ALL be true.

Conditions reference the *calling user's* own attributes only:
    { "attr": "org_id",   "op": "=",  "value": "<some-uuid>" }
    { "attr": "team_id",  "op": "in", "value": ["<uuid1>", ...] }
    { "attr": "team_type","op": "=",  "value": "department" }

Effective permissions for a user are the union of:
  - policies directly attached to the user (user_policies)
  - policies on roles directly attached to the user (user_roles → role_policies)
  - policies on org-level roles assigned to the org (org_roles → role_policies)
  - policies directly assigned to the org (org_policies)
  - policies on team-level roles for all teams the user belongs to (team_roles → role_policies)
  - policies directly assigned to those teams (team_policies)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.auth.dependencies import require_active_user
from sqlalchemy.orm import selectinload

from app.auth.models import (
    User, Policy, Role,
    user_policies, user_roles, role_policies,
    user_teams,
)
from app.govern.models import (
    org_roles, org_policies,
    team_roles, team_policies,
)


# ---------------------------------------------------------------------------
# Condition evaluator
# ---------------------------------------------------------------------------

def _evaluate_condition(cond: Dict[str, Any], user: User, user_team_ids: List[str]) -> bool:
    """
    Evaluate a single condition against the calling user's own attributes.
    Returns True if the condition is satisfied.
    """
    attr: str = cond.get("attr", "")
    op: str = cond.get("op", "=")
    expected = cond.get("value")

    # Resolve the actual value from the user object
    if attr == "org_id":
        actual = str(user.org_id)
    elif attr == "user_id":
        actual = str(user.id)
    elif attr == "team_id":
        actual = user_team_ids  # list
    elif attr == "team_type":
        # Not directly on user; skip (team_type checks need team context)
        return True
    elif attr == "is_admin":
        actual = user.is_admin
    elif attr == "is_global_admin":
        actual = user.is_global_admin
    else:
        return True  # Unknown attribute — don't block

    if op in ("=", "eq"):
        if isinstance(actual, list):
            return str(expected) in [str(a) for a in actual]
        return str(actual) == str(expected)
    elif op in ("!=", "ne"):
        return str(actual) != str(expected)
    elif op == "in":
        if not isinstance(expected, list):
            return False
        if isinstance(actual, list):
            return bool(set(str(a) for a in actual) & set(str(e) for e in expected))
        return str(actual) in [str(e) for e in expected]
    elif op == "not_in":
        if not isinstance(expected, list):
            return True
        if isinstance(actual, list):
            return not bool(set(str(a) for a in actual) & set(str(e) for e in expected))
        return str(actual) not in [str(e) for e in expected]
    return True


def policy_allows(policy: Policy, resource: str, operation: str, user: User, user_team_ids: List[str]) -> bool:
    """Return True if this policy grants the operation on the resource for the user."""
    if policy.resource != resource and policy.resource != "*":
        return False
    if operation not in policy.operations and "*" not in policy.operations:
        return False
    for cond in (policy.conditions or []):
        if not _evaluate_condition(cond, user, user_team_ids):
            return False
    return True


# ---------------------------------------------------------------------------
# Effective policy collector
# ---------------------------------------------------------------------------

async def get_effective_policies(user: User, db: AsyncSession) -> List[Policy]:
    """Collect all Policy objects that apply to this user."""
    policy_ids: Set[str] = set()
    policies: List[Policy] = []

    def _add_policy(p: Policy):
        pid = str(p.id)
        if pid not in policy_ids:
            policy_ids.add(pid)
            policies.append(p)

    # 1. Direct user policies (explicit query to avoid lazy load)
    direct_pol_ids = await db.execute(
        select(user_policies.c.policy_id).where(user_policies.c.user_id == user.id)
    )
    for row in direct_pol_ids.mappings():
        pol_result = await db.execute(select(Policy).where(Policy.id == row["policy_id"]))
        pol = pol_result.scalars().first()
        if pol:
            _add_policy(pol)

    # 2. Policies via user roles (explicit query to avoid lazy load)
    user_role_rows = await db.execute(
        select(user_roles.c.role_id).where(user_roles.c.user_id == user.id)
    )
    for row in user_role_rows.mappings():
        role_result = await db.execute(
            select(Role).where(Role.id == row["role_id"]).options(selectinload(Role.policies))
        )
        role = role_result.scalars().first()
        if role:
            for p in role.policies:
                _add_policy(p)

    # 3. Org-level roles → their policies
    active_org_id = getattr(user, "_active_org_id", None) or str(user.org_id)
    org_role_rows = await db.execute(
        select(org_roles).where(org_roles.c.org_id == active_org_id)
    )
    for row in org_role_rows.mappings():
        role_result = await db.execute(
            select(Role).where(Role.id == row["role_id"]).options(selectinload(Role.policies))
        )
        role = role_result.scalars().first()
        if role:
            for p in role.policies:
                _add_policy(p)

    # 4. Direct org policies
    org_policy_rows = await db.execute(
        select(org_policies).where(org_policies.c.org_id == active_org_id)
    )
    for row in org_policy_rows.mappings():
        pol_result = await db.execute(select(Policy).where(Policy.id == row["policy_id"]))
        pol = pol_result.scalars().first()
        if pol:
            _add_policy(pol)

    # 5. Team-level roles and direct team policies
    user_team_rows = await db.execute(
        select(user_teams).where(user_teams.c.user_id == user.id)
    )
    team_ids = [str(row["team_id"]) for row in user_team_rows.mappings()]

    for team_id in team_ids:
        # team roles
        team_role_rows = await db.execute(
            select(team_roles).where(team_roles.c.team_id == team_id)
        )
        for row in team_role_rows.mappings():
            role_result = await db.execute(
                select(Role).where(Role.id == row["role_id"]).options(selectinload(Role.policies))
            )
            role = role_result.scalars().first()
            if role:
                for p in role.policies:
                    _add_policy(p)

        # direct team policies
        team_policy_rows = await db.execute(
            select(team_policies).where(team_policies.c.team_id == team_id)
        )
        for row in team_policy_rows.mappings():
            pol_result = await db.execute(select(Policy).where(Policy.id == row["policy_id"]))
            pol = pol_result.scalars().first()
            if pol:
                _add_policy(pol)

    return policies


# ---------------------------------------------------------------------------
# FastAPI dependency factory
# ---------------------------------------------------------------------------

def require_permission(resource: str, operation: str):
    """
    Dependency factory.  Usage:
        @router.get("/sensitive")
        async def endpoint(user = Depends(require_permission("glossary_term", "create"))):
            ...
    Global admins and org admins bypass all checks.
    """
    async def _check(
        user: User = Depends(require_active_user),
        db: AsyncSession = Depends(get_session),
    ) -> User:
        if user.is_global_admin or user.is_admin:
            return user

        user_team_rows = await db.execute(
            select(user_teams).where(user_teams.c.user_id == user.id)
        )
        user_team_ids = [str(row["team_id"]) for row in user_team_rows.mappings()]

        effective_policies = await get_effective_policies(user, db)
        for policy in effective_policies:
            if policy_allows(policy, resource, operation, user, user_team_ids):
                return user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {operation} on {resource}",
        )

    return _check


# ---------------------------------------------------------------------------
# GET /auth/me/permissions helper
# ---------------------------------------------------------------------------

async def build_permissions_map(user: User, db: AsyncSession) -> Dict[str, List[str]]:
    """Build a {resource: [operations]} map of all permissions for the user."""
    user_team_rows = await db.execute(
        select(user_teams).where(user_teams.c.user_id == user.id)
    )
    user_team_ids = [str(row["team_id"]) for row in user_team_rows.mappings()]

    effective_policies = await get_effective_policies(user, db)
    perms: Dict[str, Set[str]] = {}

    for policy in effective_policies:
        all_conditions_pass = all(
            _evaluate_condition(c, user, user_team_ids)
            for c in (policy.conditions or [])
        )
        if all_conditions_pass:
            res = policy.resource
            if res not in perms:
                perms[res] = set()
            for op in policy.operations:
                perms[res].add(op)

    return {k: sorted(v) for k, v in perms.items()}

"""
Auth API router — register, login, logout, refresh, me, forgot/reset password,
and org-level JWT/lockout config management.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.auth.models import AuthConfig, Organization, User, user_organizations
from app.auth.schemas import (
    AuthConfigResponse,
    AuthConfigUpdate,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    OrgResponse,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
    UserUpdateRequest,
)
from sqlalchemy import insert
from app.auth.service import (
    check_lockout,
    create_access_token,
    decode_access_token,
    get_auth_config_for_org,
    get_user_by_login,
    handle_failed_attempt,
    hash_password,
    reset_failed_attempts,
    slugify,
    verify_password,
)
from app.auth.dependencies import (
    get_active_org_id,
    get_current_user,
    require_active_user,
    require_org_admin,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="Creates a new user account. A default organization is auto-created if org_name is not provided.",
)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_session),
) -> UserResponse:
    # Check duplicate email
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalars().first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    # Check duplicate username
    existing_un = await db.execute(select(User).where(User.username == body.username))
    if existing_un.scalars().first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")

    # Create organization
    org_name = body.org_name or f"{body.name}'s Organization"
    base_slug = slugify(org_name)
    # Ensure unique slug
    slug = base_slug
    counter = 1
    while True:
        result = await db.execute(select(Organization).where(Organization.slug == slug))
        if not result.scalars().first():
            break
        slug = f"{base_slug}-{counter}"
        counter += 1

    org = Organization(
        id=uuid.uuid4(),
        name=org_name,
        slug=slug,
        is_active=True,
        is_default=False,
    )
    db.add(org)
    await db.flush()  # Get org.id without committing

    # Create user
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        org_id=org.id,
        default_org_id=org.id,   # Default org = the org just created
        name=body.name,
        display_name=body.display_name or body.name,
        email=body.email,
        username=body.username,
        hashed_password=hash_password(body.password),
        is_admin=True,        # First user of an org is auto-org-admin
        is_global_admin=False,
        is_active=True,
        is_verified=False,
        failed_attempts=0,
    )
    db.add(user)
    await db.flush()

    # Set org creator
    org.created_by = user.id

    # Create default auth_config for org
    auth_cfg = AuthConfig(
        id=uuid.uuid4(),
        org_id=org.id,
        jwt_expiry_minutes=60,
        max_failed_attempts=5,
        lockout_duration_minutes=15,
        sso_provider="default",
    )
    db.add(auth_cfg)

    # Register user as org admin in user_organizations
    await db.execute(
        insert(user_organizations).values(
            id=uuid.uuid4(),
            user_id=user.id,
            org_id=org.id,
            is_org_admin=True,
            is_active=True,
        )
    )

    await db.commit()
    await db.refresh(user)

    # Reload with relationships
    stmt = (
        select(User)
        .where(User.id == user.id)
        .options(selectinload(User.teams), selectinload(User.roles))
    )
    result = await db.execute(stmt)
    user = result.scalars().first()
    return UserResponse.model_validate(user)


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login with email/username and password",
)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_session),
) -> TokenResponse:
    user = await get_user_by_login(body.login, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive")

    # Use default_org_id if set, otherwise fall back to org_id
    active_org_id = user.default_org_id or user.org_id
    auth_config = await get_auth_config_for_org(str(active_org_id), db)

    # Check lockout before verifying password
    check_lockout(user, auth_config)

    if not verify_password(body.password, user.hashed_password):
        await handle_failed_attempt(user, auth_config, db)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Successful login — reset counters
    await reset_failed_attempts(user, db)

    # Check if user is org admin for the active org
    membership = await db.execute(
        select(user_organizations).where(
            user_organizations.c.user_id == user.id,
            user_organizations.c.org_id == active_org_id,
            user_organizations.c.is_active == True,
        )
    )
    mem_row = membership.mappings().first()
    is_org_admin = bool(mem_row and mem_row["is_org_admin"]) if mem_row else user.is_admin

    token = create_access_token(
        user_id=str(user.id),
        org_id=str(active_org_id),
        expiry_minutes=auth_config.jwt_expiry_minutes,
        is_admin=is_org_admin,
        is_global_admin=user.is_global_admin,
    )
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=auth_config.jwt_expiry_minutes * 60,
    )


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------

@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Logout (client-side token invalidation)",
    description="Instructs the client to discard the token. No server-side blacklist is maintained in this default implementation.",
)
async def logout(
    _current_user: User = Depends(require_active_user),
) -> MessageResponse:
    return MessageResponse(message="Logged out successfully. Please discard your token.")


# ---------------------------------------------------------------------------
# POST /auth/refresh
# ---------------------------------------------------------------------------

@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token",
    description="Issues a new token with a fresh expiry, using the current valid token.",
)
async def refresh_token(
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
) -> TokenResponse:
    active_org_id = get_active_org_id(current_user)
    auth_config = await get_auth_config_for_org(str(active_org_id), db)
    # Re-check org admin status from DB to avoid stale JWT claim
    membership = await db.execute(
        select(user_organizations).where(
            user_organizations.c.user_id == current_user.id,
            user_organizations.c.org_id == active_org_id,
            user_organizations.c.is_active == True,
        )
    )
    row = membership.mappings().first()
    is_admin_current = bool(row["is_org_admin"]) if row else current_user.is_admin
    token = create_access_token(
        user_id=str(current_user.id),
        org_id=str(active_org_id),
        expiry_minutes=auth_config.jwt_expiry_minutes,
        is_admin=is_admin_current,
        is_global_admin=current_user.is_global_admin,
    )
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=auth_config.jwt_expiry_minutes * 60,
    )


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------

@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
)
async def get_me(
    current_user: User = Depends(require_active_user),
) -> UserResponse:
    return UserResponse.model_validate(current_user)


# ---------------------------------------------------------------------------
# PUT /auth/me
# ---------------------------------------------------------------------------

@router.put(
    "/me",
    response_model=UserResponse,
    summary="Update current user profile",
    description="Update name, display_name, description, image. Use default_org_id to switch active organization context (must be an org you belong to).",
)
async def update_me(
    body: UserUpdateRequest,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
) -> UserResponse:
    if body.name is not None:
        current_user.name = body.name
    if body.display_name is not None:
        current_user.display_name = body.display_name
    if body.description is not None:
        current_user.description = body.description
    if body.image is not None:
        current_user.image = body.image

    if body.default_org_id is not None:
        # Validate user belongs to the requested org
        membership = await db.execute(
            select(user_organizations).where(
                user_organizations.c.user_id == current_user.id,
                user_organizations.c.org_id == body.default_org_id,
                user_organizations.c.is_active == True,
            )
        )
        if not membership.mappings().first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of the specified organization",
            )
        current_user.default_org_id = body.default_org_id

    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)

    stmt = (
        select(User)
        .where(User.id == current_user.id)
        .options(selectinload(User.teams), selectinload(User.roles))
    )
    result = await db.execute(stmt)
    user = result.scalars().first()
    return UserResponse.model_validate(user)


# ---------------------------------------------------------------------------
# GET /auth/me/orgs
# ---------------------------------------------------------------------------

@router.get(
    "/me/orgs",
    response_model=list[OrgResponse],
    summary="List all organizations the current user belongs to",
)
async def get_my_orgs(
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
) -> list[OrgResponse]:
    result = await db.execute(
        select(Organization)
        .join(user_organizations, user_organizations.c.org_id == Organization.id)
        .where(
            user_organizations.c.user_id == current_user.id,
            user_organizations.c.is_active == True,
            Organization.is_active == True,
        )
        .order_by(Organization.name)
    )
    return result.scalars().all()


# ---------------------------------------------------------------------------
# POST /auth/forgot-password
# ---------------------------------------------------------------------------

@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    summary="Request a password reset email (stub)",
    description="Stub implementation. In production, sends an email with a reset link.",
)
async def forgot_password(
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_session),
) -> MessageResponse:
    # Stub: always return success to avoid user enumeration
    # In production: generate a reset token, store it (hashed), send email
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalars().first()
    if user:
        # TODO: generate reset token, store in DB, send email
        pass
    return MessageResponse(
        message="If that email is registered, a reset link has been sent."
    )


# ---------------------------------------------------------------------------
# POST /auth/reset-password
# ---------------------------------------------------------------------------

@router.post(
    "/reset-password",
    response_model=MessageResponse,
    summary="Reset password using token (stub)",
    description="Stub implementation. In production, validates the reset token and updates the password.",
)
async def reset_password(
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_session),
) -> MessageResponse:
    # TODO: validate reset_token from DB, find user, update hashed_password, invalidate token
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Password reset via email is not yet configured. Contact your administrator.",
    )


# ---------------------------------------------------------------------------
# GET /auth/config  (org admin only)
# ---------------------------------------------------------------------------

@router.get(
    "/config",
    response_model=AuthConfigResponse,
    summary="Get JWT and lockout configuration for the organization",
)
async def get_auth_config(
    current_user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
) -> AuthConfigResponse:
    cfg = await get_auth_config_for_org(str(get_active_org_id(current_user)), db)
    return AuthConfigResponse.model_validate(cfg)


# ---------------------------------------------------------------------------
# PUT /auth/config  (org admin only)
# ---------------------------------------------------------------------------

@router.put(
    "/config",
    response_model=AuthConfigResponse,
    summary="Update JWT and lockout configuration for the organization",
    description=(
        "Org admins can configure: (1) JWT token expiry in minutes, "
        "(2) max failed login attempts before lockout, "
        "(3) lockout duration in minutes."
    ),
)
async def update_auth_config(
    body: AuthConfigUpdate,
    current_user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_session),
) -> AuthConfigResponse:
    cfg = await get_auth_config_for_org(str(get_active_org_id(current_user)), db)

    if body.jwt_expiry_minutes is not None:
        cfg.jwt_expiry_minutes = body.jwt_expiry_minutes
    if body.max_failed_attempts is not None:
        cfg.max_failed_attempts = body.max_failed_attempts
    if body.lockout_duration_minutes is not None:
        cfg.lockout_duration_minutes = body.lockout_duration_minutes

    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return AuthConfigResponse.model_validate(cfg)


# ---------------------------------------------------------------------------
# GET /auth/me/permissions
# ---------------------------------------------------------------------------

@router.get(
    "/me/permissions",
    summary="Get effective permissions for the current user",
    description="Returns a map of resource → [operations] based on all policies (user, role, org, team).",
)
async def get_my_permissions(
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    from app.auth.abac import build_permissions_map
    perms = await build_permissions_map(user, db)
    return {
        "user_id": str(user.id),
        "org_id": str(get_active_org_id(user)),
        "is_admin": user.is_admin,
        "is_global_admin": user.is_global_admin,
        "permissions": perms,
    }

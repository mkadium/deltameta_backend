"""Glossary — manage glossaries and their terms, with like/unlike, export/import."""
from __future__ import annotations
import csv
import io
import uuid
from typing import List, Optional

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, File, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.auth.dependencies import get_active_org_id, require_active_user, require_org_admin
from app.auth.models import User
from app.govern.models import (
    Glossary, GlossaryTerm,
    glossary_term_owners, glossary_term_reviewers,
    glossary_term_related, glossary_term_likes,
)
from app.govern.activity import emit

router = APIRouter(prefix="/glossaries", tags=["Glossary"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class UserRef(BaseModel):
    id: uuid.UUID
    name: Optional[str] = None

    class Config:
        from_attributes = True


class GlossaryCreate(BaseModel):
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None


class GlossaryUpdate(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class GlossaryOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    display_name: Optional[str]
    description: Optional[str]
    is_active: bool
    created_by: Optional[uuid.UUID]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class GlossaryTermCreate(BaseModel):
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    icon_url: Optional[str] = None
    color: Optional[str] = None
    mutually_exclusive: bool = False
    synonyms: List[str] = []
    references_data: List[dict] = []
    owner_ids: List[uuid.UUID] = []
    reviewer_ids: List[uuid.UUID] = []
    related_term_ids: List[uuid.UUID] = []


class GlossaryTermUpdate(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    icon_url: Optional[str] = None
    color: Optional[str] = None
    mutually_exclusive: Optional[bool] = None
    synonyms: Optional[List[str]] = None
    references_data: Optional[List[dict]] = None
    owner_ids: Optional[List[uuid.UUID]] = None
    reviewer_ids: Optional[List[uuid.UUID]] = None
    related_term_ids: Optional[List[uuid.UUID]] = None
    is_active: Optional[bool] = None


class GlossaryTermOut(BaseModel):
    id: uuid.UUID
    glossary_id: uuid.UUID
    org_id: uuid.UUID
    name: str
    display_name: Optional[str]
    description: Optional[str]
    icon_url: Optional[str]
    color: Optional[str]
    mutually_exclusive: bool
    synonyms: list
    references_data: list
    likes_count: int
    is_active: bool
    owners: List[UserRef] = []
    reviewers: List[UserRef] = []
    related_terms: List["GlossaryTermOut"] = []

    class Config:
        from_attributes = True


GlossaryTermOut.model_rebuild()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _sync_m2m(db, table, col_a, val_a, col_b, ids):
    await db.execute(table.delete().where(table.c[col_a] == val_a))
    for id_ in ids:
        await db.execute(table.insert().values({col_a: val_a, col_b: id_}))


async def _get_term(db, term_id, org_id):
    stmt = (
        select(GlossaryTerm)
        .where(GlossaryTerm.id == term_id, GlossaryTerm.org_id == org_id)
        .options(
            selectinload(GlossaryTerm.owners),
            selectinload(GlossaryTerm.reviewers),
            # Load related_terms and their nested owners/reviewers/related_terms to avoid MissingGreenlet
            selectinload(GlossaryTerm.related_terms).selectinload(GlossaryTerm.owners),
            selectinload(GlossaryTerm.related_terms).selectinload(GlossaryTerm.reviewers),
            selectinload(GlossaryTerm.related_terms).selectinload(GlossaryTerm.related_terms),
        )
    )
    result = await db.execute(stmt)
    return result.scalars().first()


# ── Glossary CRUD ─────────────────────────────────────────────────────────────

@router.get("", response_model=List[GlossaryOut])
async def list_glossaries(
    search: Optional[str] = Query(None, description="Search by name or display_name."),
    is_active: Optional[bool] = Query(None, description="Filter by active/inactive."),
    created_by: Optional[uuid.UUID] = Query(None, description="Filter by creator user ID."),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    stmt = select(Glossary).where(Glossary.org_id == get_active_org_id(user))
    if search:
        stmt = stmt.where(Glossary.name.ilike(f"%{search}%") | Glossary.display_name.ilike(f"%{search}%"))
    if is_active is not None:
        stmt = stmt.where(Glossary.is_active == is_active)
    if created_by:
        stmt = stmt.where(Glossary.created_by == created_by)
    stmt = stmt.order_by(Glossary.name).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=GlossaryOut, status_code=status.HTTP_201_CREATED)
async def create_glossary(
    body: GlossaryCreate,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    obj = Glossary(org_id=get_active_org_id(user), created_by=user.id, **body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/{glossary_id}", response_model=GlossaryOut)
async def get_glossary(
    glossary_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(Glossary, glossary_id)
    if not obj or obj.org_id != get_active_org_id(user):
        raise HTTPException(status_code=404, detail="Glossary not found")
    return obj


@router.put("/{glossary_id}", response_model=GlossaryOut)
async def update_glossary(
    glossary_id: uuid.UUID,
    body: GlossaryUpdate,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(Glossary, glossary_id)
    if not obj or obj.org_id != get_active_org_id(user):
        raise HTTPException(status_code=404, detail="Glossary not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{glossary_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_glossary(
    glossary_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(Glossary, glossary_id)
    if not obj or obj.org_id != get_active_org_id(user):
        raise HTTPException(status_code=404, detail="Glossary not found")
    await db.delete(obj)
    await db.commit()


# ── Term CRUD ─────────────────────────────────────────────────────────────────

@router.get("/{glossary_id}/terms", response_model=List[GlossaryTermOut])
async def list_terms(
    glossary_id: uuid.UUID,
    search: Optional[str] = Query(None, description="Search by name or display_name."),
    is_active: Optional[bool] = Query(None, description="Filter by active/inactive."),
    mutually_exclusive: Optional[bool] = Query(None, description="Filter by mutually_exclusive flag."),
    created_by: Optional[uuid.UUID] = Query(None, description="Filter by creator user ID."),
    # Relational filters
    owner_id: Optional[uuid.UUID] = Query(None, description="Filter terms owned by this user (M2M)."),
    reviewer_id: Optional[uuid.UUID] = Query(None, description="Filter terms reviewed by this user (M2M)."),
    liked_by: Optional[uuid.UUID] = Query(None, description="Filter terms liked by this user (M2M)."),
    related_term_id: Optional[uuid.UUID] = Query(None, description="Filter terms that are related to this term ID (M2M)."),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    stmt = (
        select(GlossaryTerm)
        .where(GlossaryTerm.glossary_id == glossary_id, GlossaryTerm.org_id == get_active_org_id(user))
        .options(
            selectinload(GlossaryTerm.owners),
            selectinload(GlossaryTerm.reviewers),
            # Load nested related_terms + their owners/reviewers/related_terms to avoid MissingGreenlet
            selectinload(GlossaryTerm.related_terms).selectinload(GlossaryTerm.owners),
            selectinload(GlossaryTerm.related_terms).selectinload(GlossaryTerm.reviewers),
            selectinload(GlossaryTerm.related_terms).selectinload(GlossaryTerm.related_terms),
        )
        .distinct()
    )
    if search:
        stmt = stmt.where(GlossaryTerm.name.ilike(f"%{search}%") | GlossaryTerm.display_name.ilike(f"%{search}%"))
    if is_active is not None:
        stmt = stmt.where(GlossaryTerm.is_active == is_active)
    if mutually_exclusive is not None:
        stmt = stmt.where(GlossaryTerm.mutually_exclusive == mutually_exclusive)
    if created_by:
        stmt = stmt.where(GlossaryTerm.created_by == created_by)
    # Relational JOIN filters
    if owner_id is not None:
        stmt = stmt.join(glossary_term_owners, glossary_term_owners.c.term_id == GlossaryTerm.id).where(glossary_term_owners.c.user_id == owner_id)
    if reviewer_id is not None:
        stmt = stmt.join(glossary_term_reviewers, glossary_term_reviewers.c.term_id == GlossaryTerm.id).where(glossary_term_reviewers.c.user_id == reviewer_id)
    if liked_by is not None:
        stmt = stmt.join(glossary_term_likes, glossary_term_likes.c.term_id == GlossaryTerm.id).where(glossary_term_likes.c.user_id == liked_by)
    if related_term_id is not None:
        stmt = stmt.join(glossary_term_related, glossary_term_related.c.term_id == GlossaryTerm.id).where(glossary_term_related.c.related_term_id == related_term_id)
    stmt = stmt.order_by(GlossaryTerm.name).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/{glossary_id}/terms", response_model=GlossaryTermOut, status_code=status.HTTP_201_CREATED)
async def create_term(
    glossary_id: uuid.UUID,
    body: GlossaryTermCreate,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    glossary = await db.get(Glossary, glossary_id)
    if not glossary or glossary.org_id != get_active_org_id(user):
        raise HTTPException(status_code=404, detail="Glossary not found")
    payload = body.model_dump(exclude={"owner_ids", "reviewer_ids", "related_term_ids"})
    term = GlossaryTerm(
        glossary_id=glossary_id, org_id=get_active_org_id(user), created_by=user.id, **payload
    )
    db.add(term)
    await db.flush([term])
    if body.owner_ids:
        await _sync_m2m(db, glossary_term_owners, "term_id", term.id, "user_id", body.owner_ids)
    if body.reviewer_ids:
        await _sync_m2m(db, glossary_term_reviewers, "term_id", term.id, "user_id", body.reviewer_ids)
    if body.related_term_ids:
        await _sync_m2m(db, glossary_term_related, "term_id", term.id, "related_term_id", body.related_term_ids)
    await emit(db, entity_type="glossary_term", action="created", entity_id=term.id,
               org_id=get_active_org_id(user), actor_id=user.id, details={"name": term.name, "glossary_id": str(glossary_id)})
    await db.commit()
    await db.refresh(term)
    return term


@router.get("/{glossary_id}/terms/{term_id}", response_model=GlossaryTermOut)
async def get_term(
    glossary_id: uuid.UUID,
    term_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    term = await _get_term(db, term_id, get_active_org_id(user))
    if not term or term.glossary_id != glossary_id:
        raise HTTPException(status_code=404, detail="Term not found")
    return term


@router.put("/{glossary_id}/terms/{term_id}", response_model=GlossaryTermOut)
async def update_term(
    glossary_id: uuid.UUID,
    term_id: uuid.UUID,
    body: GlossaryTermUpdate,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    term = await _get_term(db, term_id, get_active_org_id(user))
    if not term or term.glossary_id != glossary_id:
        raise HTTPException(status_code=404, detail="Term not found")
    data = body.model_dump(exclude_unset=True)
    owner_ids = data.pop("owner_ids", None)
    reviewer_ids = data.pop("reviewer_ids", None)
    related_term_ids = data.pop("related_term_ids", None)
    for k, v in data.items():
        setattr(term, k, v)
    if owner_ids is not None:
        await _sync_m2m(db, glossary_term_owners, "term_id", term.id, "user_id", owner_ids)
    if reviewer_ids is not None:
        await _sync_m2m(db, glossary_term_reviewers, "term_id", term.id, "user_id", reviewer_ids)
    if related_term_ids is not None:
        await _sync_m2m(db, glossary_term_related, "term_id", term.id, "related_term_id", related_term_ids)
    await emit(db, entity_type="glossary_term", action="updated", entity_id=term.id,
               org_id=get_active_org_id(user), actor_id=user.id)
    await db.commit()
    # Re-fetch with eager loads to avoid lazy-load greenlet errors on related_terms
    refreshed = await _get_term(db, term.id, get_active_org_id(user))
    return refreshed


@router.delete("/{glossary_id}/terms/{term_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_term(
    glossary_id: uuid.UUID,
    term_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    term = await _get_term(db, term_id, get_active_org_id(user))
    if not term or term.glossary_id != glossary_id:
        raise HTTPException(status_code=404, detail="Term not found")
    await db.delete(term)
    await db.commit()


# ── Like / Unlike ─────────────────────────────────────────────────────────────

@router.post("/{glossary_id}/terms/{term_id}/like", status_code=status.HTTP_200_OK)
async def like_term(
    glossary_id: uuid.UUID,
    term_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    term = await _get_term(db, term_id, get_active_org_id(user))
    if not term or term.glossary_id != glossary_id:
        raise HTTPException(status_code=404, detail="Term not found")
    existing = await db.execute(
        glossary_term_likes.select().where(
            glossary_term_likes.c.term_id == term_id,
            glossary_term_likes.c.user_id == user.id,
        )
    )
    if not existing.first():
        await db.execute(glossary_term_likes.insert().values(term_id=term_id, user_id=user.id))
        term.likes_count = (term.likes_count or 0) + 1
    await db.commit()
    return {"likes_count": term.likes_count}


@router.delete("/{glossary_id}/terms/{term_id}/like", status_code=status.HTTP_200_OK)
async def unlike_term(
    glossary_id: uuid.UUID,
    term_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    term = await _get_term(db, term_id, get_active_org_id(user))
    if not term or term.glossary_id != glossary_id:
        raise HTTPException(status_code=404, detail="Term not found")
    result = await db.execute(
        glossary_term_likes.delete().where(
            glossary_term_likes.c.term_id == term_id,
            glossary_term_likes.c.user_id == user.id,
        )
    )
    if result.rowcount > 0 and term.likes_count > 0:
        term.likes_count -= 1
    await db.commit()
    return {"likes_count": term.likes_count}


# ── Export / Import ───────────────────────────────────────────────────────────

@router.get("/{glossary_id}/export")
async def export_glossary(
    glossary_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    glossary = await db.get(Glossary, glossary_id)
    if not glossary or glossary.org_id != get_active_org_id(user):
        raise HTTPException(status_code=404, detail="Glossary not found")
    stmt = select(GlossaryTerm).where(
        GlossaryTerm.glossary_id == glossary_id, GlossaryTerm.org_id == get_active_org_id(user)
    )
    result = await db.execute(stmt)
    terms = result.scalars().all()

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["name", "display_name", "description", "synonyms", "color", "icon_url", "mutually_exclusive"])
    writer.writeheader()
    for t in terms:
        writer.writerow({
            "name": t.name,
            "display_name": t.display_name or "",
            "description": t.description or "",
            "synonyms": ",".join(t.synonyms or []),
            "color": t.color or "",
            "icon_url": t.icon_url or "",
            "mutually_exclusive": t.mutually_exclusive,
        })
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="glossary_{glossary.name}.csv"'},
    )


@router.post("/{glossary_id}/import", status_code=status.HTTP_201_CREATED)
async def import_glossary(
    glossary_id: uuid.UUID,
    file: UploadFile = File(...),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_session),
):
    glossary = await db.get(Glossary, glossary_id)
    if not glossary or glossary.org_id != get_active_org_id(user):
        raise HTTPException(status_code=404, detail="Glossary not found")
    content = await file.read()
    reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
    created = 0
    for row in reader:
        synonyms = [s.strip() for s in row.get("synonyms", "").split(",") if s.strip()]
        term = GlossaryTerm(
            glossary_id=glossary_id,
            org_id=get_active_org_id(user),
            created_by=user.id,
            name=row.get("name", "").strip(),
            display_name=row.get("display_name", "").strip() or None,
            description=row.get("description", "").strip() or None,
            synonyms=synonyms,
            color=row.get("color", "").strip() or None,
            icon_url=row.get("icon_url", "").strip() or None,
            mutually_exclusive=row.get("mutually_exclusive", "false").lower() == "true",
        )
        db.add(term)
        created += 1
    await db.commit()
    return {"imported": created}

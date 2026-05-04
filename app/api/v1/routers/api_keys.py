"""API key management endpoints.

Routes:
  POST   /api-keys          — create (returns plaintext once)
  GET    /api-keys          — list active keys
  GET    /api-keys/{id}     — get single key
  POST   /api-keys/{id}/revoke  — permanently deactivate
  POST   /api-keys/{id}/rotate  — replace with new key (returns plaintext once)
"""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, require_scope
from app.database import get_session
from app.services import api_key_service

router = APIRouter(tags=["api-keys"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ApiKeyCreate(BaseModel):
    name: str
    scopes: list[str]
    expires_at: datetime | None = None
    note: str | None = None


class ApiKeyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    key_prefix: str
    scopes: list[Any]
    active: bool
    expires_at: datetime | None
    last_used_at: datetime | None
    created_by: uuid.UUID | None
    note: str | None
    created_at: datetime


class ApiKeyCreated(ApiKeyRead):
    """Returned only on create/rotate — includes the plaintext key."""
    plaintext_key: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/api-keys", response_model=ApiKeyCreated, status_code=201)
async def create_api_key(
    body: ApiKeyCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_scope("admin")),
):
    try:
        row, plaintext = await api_key_service.create_key(
            name=body.name,
            scopes=body.scopes,
            session=session,
            expires_at=body.expires_at,
            created_by=uuid.UUID(principal["id"]) if principal.get("id") and principal["id"] != "dev-admin" else None,
            note=body.note,
        )
        await session.commit()
        return ApiKeyCreated(
            id=row.id,
            name=row.name,
            key_prefix=row.key_prefix,
            scopes=row.scopes,
            active=row.active,
            expires_at=row.expires_at,
            last_used_at=row.last_used_at,
            created_by=row.created_by,
            note=row.note,
            created_at=row.created_at,
            plaintext_key=plaintext,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/api-keys", response_model=list[ApiKeyRead])
async def list_api_keys(
    include_revoked: bool = False,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_scope("admin")),
):
    return await api_key_service.list_keys(session, include_revoked=include_revoked)


@router.get("/api-keys/{key_id}", response_model=ApiKeyRead)
async def get_api_key(
    key_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_scope("admin")),
):
    try:
        return await api_key_service.get_key(key_id, session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/api-keys/{key_id}/revoke", response_model=ApiKeyRead)
async def revoke_api_key(
    key_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_scope("admin")),
):
    try:
        row = await api_key_service.revoke_key(key_id, session)
        await session.commit()
        return row
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/api-keys/{key_id}/rotate", response_model=ApiKeyCreated)
async def rotate_api_key(
    key_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_scope("admin")),
):
    try:
        row, plaintext = await api_key_service.rotate_key(key_id, session)
        await session.commit()
        return ApiKeyCreated(
            id=row.id,
            name=row.name,
            key_prefix=row.key_prefix,
            scopes=row.scopes,
            active=row.active,
            expires_at=row.expires_at,
            last_used_at=row.last_used_at,
            created_by=row.created_by,
            note=row.note,
            created_at=row.created_at,
            plaintext_key=plaintext,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

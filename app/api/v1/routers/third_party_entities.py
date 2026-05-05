import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_scope
from app.schemas.third_party_entity import (
    ThirdPartyEntityCreate,
    ThirdPartyEntityRead,
    ThirdPartyEntityUpdate,
)
from app.services import third_party_entity_service as svc

router = APIRouter(prefix="/third-party-entities", tags=["third-party-entities"])


@router.get("", response_model=list[ThirdPartyEntityRead])
async def list_entities(
    active_only: bool = True,
    session: AsyncSession = Depends(get_db),
    principal=Depends(get_current_user),
):
    require_scope(principal, "admin")
    return await svc.list_entities(session, active_only=active_only)


@router.post("", response_model=ThirdPartyEntityRead, status_code=201)
async def create_entity(
    data: ThirdPartyEntityCreate,
    session: AsyncSession = Depends(get_db),
    principal=Depends(get_current_user),
):
    require_scope(principal, "admin")
    entity = await svc.create_entity(data, session)
    await session.commit()
    await session.refresh(entity)
    return entity


@router.get("/{entity_id}", response_model=ThirdPartyEntityRead)
async def get_entity(
    entity_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    principal=Depends(get_current_user),
):
    require_scope(principal, "admin")
    entity = await svc.get_entity(entity_id, session)
    if not entity:
        raise HTTPException(status_code=404, detail="Third-party entity not found")
    return entity


@router.patch("/{entity_id}", response_model=ThirdPartyEntityRead)
async def update_entity(
    entity_id: uuid.UUID,
    data: ThirdPartyEntityUpdate,
    session: AsyncSession = Depends(get_db),
    principal=Depends(get_current_user),
):
    require_scope(principal, "admin")
    try:
        entity = await svc.update_entity(entity_id, data, session)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await session.commit()
    await session.refresh(entity)
    return entity


@router.post("/{entity_id}/deactivate", response_model=ThirdPartyEntityRead)
async def deactivate_entity(
    entity_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    principal=Depends(get_current_user),
):
    require_scope(principal, "admin")
    try:
        entity = await svc.deactivate_entity(entity_id, session)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await session.commit()
    await session.refresh(entity)
    return entity

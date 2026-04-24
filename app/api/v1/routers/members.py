import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, get_current_user
from app.database import get_session
from app.schemas.member import MemberCreate, MemberRead
from app.services import member_service

router = APIRouter(prefix="/members", tags=["members"])


@router.get("/", response_model=list[MemberRead])
async def list_members(session: AsyncSession = Depends(get_session)):
    return await member_service.list_members(session)


@router.get("/{member_id}", response_model=MemberRead)
async def get_member(member_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    member = await member_service.get_member(member_id, session)
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return member


@router.post("/", response_model=MemberRead, status_code=201)
async def create_member(
    data: MemberCreate,
    session: AsyncSession = Depends(get_session),
    current_user: Principal = Depends(get_current_user),
):
    return await member_service.create_member(data, session)

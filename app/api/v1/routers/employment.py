import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, get_current_user
from app.database import get_session
from app.schemas.employment import EmploymentRecordRead
from app.services import employment_service

router = APIRouter(prefix="/members/{member_id}/employment", tags=["employment"])


@router.get("/", response_model=list[EmploymentRecordRead])
async def list_employment_records(member_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    return await employment_service.get_employment_records(member_id, session)

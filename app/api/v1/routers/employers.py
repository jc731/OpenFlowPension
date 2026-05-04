import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, require_scope
from app.database import get_session
from app.schemas.employer import EmployerCreate, EmployerRead
from app.services import employer_service

router = APIRouter(prefix="/employers", tags=["employers"])


@router.get("/", response_model=list[EmployerRead], dependencies=[Depends(require_scope("member:read"))])
async def list_employers(session: AsyncSession = Depends(get_session)):
    return await employer_service.list_employers(session)


@router.get("/{employer_id}", response_model=EmployerRead, dependencies=[Depends(require_scope("member:read"))])
async def get_employer(employer_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    employer = await employer_service.get_employer(employer_id, session)
    if not employer:
        raise HTTPException(status_code=404, detail="Employer not found")
    return employer


@router.post("/", response_model=EmployerRead, status_code=201)
async def create_employer(
    data: EmployerCreate,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_scope("admin")),
):
    return await employer_service.create_employer(data, session)

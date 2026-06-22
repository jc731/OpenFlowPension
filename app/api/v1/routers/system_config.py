"""System configuration endpoints (read + write).

All rows are insert-only — a new row supersedes the previous effective row for
the same key. Staff cannot edit or delete existing rows; they can only add a
new value with a future (or current) effective_date.
"""
import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, require_scope
from app.database import get_session
from app.models.plan_config import SystemConfiguration

router = APIRouter(tags=["system-config"])


class SystemConfigEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    config_key: str
    config_value: dict
    effective_date: date
    superseded_date: date | None
    note: str | None
    set_at: datetime


class SystemConfigCreate(BaseModel):
    config_key: str
    config_value: dict
    effective_date: date
    note: str | None = None


@router.get(
    "/system-configurations",
    response_model=list[SystemConfigEntryRead],
    dependencies=[Depends(require_scope("admin"))],
)
async def list_system_configurations(
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(SystemConfiguration).order_by(
            SystemConfiguration.config_key,
            SystemConfiguration.effective_date.desc(),
        )
    )
    return list(result.scalars().all())


@router.post(
    "/system-configurations",
    response_model=SystemConfigEntryRead,
    status_code=201,
    dependencies=[Depends(require_scope("admin"))],
)
async def create_system_configuration(
    data: SystemConfigCreate,
    session: AsyncSession = Depends(get_session),
):
    """Insert a new configuration row. The new row supersedes the previous
    most-recent row for the same key by setting its superseded_date."""
    async with session.begin():
        # Find the current active row (if any) and supersede it
        prev_result = await session.execute(
            select(SystemConfiguration)
            .where(
                SystemConfiguration.config_key == data.config_key,
                SystemConfiguration.superseded_date.is_(None),
            )
            .order_by(SystemConfiguration.effective_date.desc())
            .limit(1)
        )
        prev = prev_result.scalar_one_or_none()
        if prev is not None:
            if prev.effective_date >= data.effective_date:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"New effective_date ({data.effective_date}) must be after the "
                        f"current active row's effective_date ({prev.effective_date})"
                    ),
                )
            prev.superseded_date = data.effective_date

        new_row = SystemConfiguration(
            config_key=data.config_key,
            config_value=data.config_value,
            effective_date=data.effective_date,
            note=data.note,
        )
        session.add(new_row)
        await session.flush()
        return new_row

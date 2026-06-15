"""Read-only system configuration listing endpoint."""
import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_scope
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

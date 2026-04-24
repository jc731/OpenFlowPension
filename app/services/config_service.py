from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan_config import SystemConfiguration


class ConfigNotFoundError(Exception):
    pass


async def get_config(key: str, as_of: date, session: AsyncSession) -> SystemConfiguration:
    """
    Returns the active SystemConfiguration row for a given key as of a specific date.

    effective_date is inclusive; superseded_date is exclusive.
    This means a row with superseded_date=2024-09-01 does NOT apply on 2024-09-01 —
    the new row with effective_date=2024-09-01 takes precedence.

    Raises ConfigNotFoundError if no matching config exists.
    """
    result = await session.execute(
        select(SystemConfiguration)
        .where(
            SystemConfiguration.config_key == key,
            SystemConfiguration.effective_date <= as_of,
            or_(
                SystemConfiguration.superseded_date.is_(None),
                SystemConfiguration.superseded_date > as_of,
            ),
        )
        .order_by(SystemConfiguration.effective_date.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise ConfigNotFoundError(f"No config found for key={key!r} as_of={as_of}")
    return row

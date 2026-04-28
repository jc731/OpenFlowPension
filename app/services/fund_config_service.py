"""Load FundConfig from system_configurations, with SURS defaults.

The key 'fund_calculation_config' stores the fund's overrides as JSONB.
If the key is absent, FundConfig() (all SURS defaults) is returned.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.fund_config import FundConfig
from app.services.config_service import ConfigNotFoundError, get_config


async def load_fund_config(as_of: date, session: AsyncSession) -> FundConfig:
    """Return FundConfig for the current fund, falling back to SURS defaults."""
    try:
        raw = await get_config("fund_calculation_config", as_of, session)
    except ConfigNotFoundError:
        return FundConfig()
    return FundConfig.model_validate(raw)

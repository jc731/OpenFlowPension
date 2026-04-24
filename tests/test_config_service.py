from datetime import date

import pytest

from app.models.plan_config import SystemConfiguration
from app.services.config_service import ConfigNotFoundError, get_config

ACCRUAL_RULE_KEY = "service_credit_accrual_rule"


@pytest.fixture(autouse=True)
async def seed_configs(session):
    old_rule = SystemConfiguration(
        config_key=ACCRUAL_RULE_KEY,
        config_value={"rule": "proportional_percent_time"},
        effective_date=date(1980, 1, 1),
        superseded_date=date(2024, 9, 1),
        note="Original accrual rule",
    )
    new_rule = SystemConfiguration(
        config_key=ACCRUAL_RULE_KEY,
        config_value={"rule": "monthly_floor"},
        effective_date=date(2024, 9, 1),
        superseded_date=None,
        note="Post-2024 rule change",
    )
    session.add_all([old_rule, new_rule])
    await session.flush()


async def test_config_pre_2024(session):
    row = await get_config(ACCRUAL_RULE_KEY, date(2020, 1, 1), session)
    assert row.config_value["rule"] == "proportional_percent_time"


async def test_config_day_before_cutover(session):
    row = await get_config(ACCRUAL_RULE_KEY, date(2024, 8, 31), session)
    assert row.config_value["rule"] == "proportional_percent_time"


async def test_config_on_cutover_date(session):
    row = await get_config(ACCRUAL_RULE_KEY, date(2024, 9, 1), session)
    assert row.config_value["rule"] == "monthly_floor"


async def test_config_not_found_raises(session):
    with pytest.raises(ConfigNotFoundError):
        await get_config("nonexistent_key", date(2024, 1, 1), session)

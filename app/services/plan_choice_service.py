"""Plan choice service.

Members select a plan tier and plan type during an enrollment window.
Once locked, the choice cannot be changed without an admin override.
plan_choice_locked is set by an explicit lock action (separate from selection)
so administrators retain control over when the window closes.
"""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.member import Member
from app.models.plan_config import PlanTier, PlanType


async def set_plan_choice(
    member_id: uuid.UUID,
    plan_tier_id: uuid.UUID,
    plan_type_id: uuid.UUID,
    choice_date: date,
    session: AsyncSession,
    changed_by: uuid.UUID | None = None,
) -> Member:
    member = await session.get(Member, member_id)
    if not member:
        raise ValueError(f"Member {member_id} not found")
    if member.plan_choice_locked:
        raise ValueError("Plan choice is locked and cannot be changed")

    tier = await session.get(PlanTier, plan_tier_id)
    if not tier:
        raise ValueError(f"Plan tier {plan_tier_id} not found")

    plan = await session.get(PlanType, plan_type_id)
    if not plan:
        raise ValueError(f"Plan type {plan_type_id} not found")

    member.plan_tier_id = plan_tier_id
    member.plan_type_id = plan_type_id
    member.plan_choice_date = choice_date
    await session.flush()
    return member


async def lock_plan_choice(
    member_id: uuid.UUID,
    session: AsyncSession,
    changed_by: uuid.UUID | None = None,
) -> Member:
    member = await session.get(Member, member_id)
    if not member:
        raise ValueError(f"Member {member_id} not found")
    if member.plan_choice_locked:
        raise ValueError("Plan choice is already locked")
    if not member.plan_tier_id or not member.plan_type_id:
        raise ValueError("Cannot lock plan choice: no plan has been selected yet")

    member.plan_choice_locked = True
    await session.flush()
    return member

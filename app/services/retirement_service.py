"""Retirement case management service.

Orchestrates the administrative workflow from termination to first annuity payment:

  create_case()     → status=draft; runs calculation; stores snapshot
  recalculate()     → updates snapshot (draft only); does not change status
  approve_case()    → records benefit election; transitions member to annuitant; status=approved
  activate_case()   → creates first BenefitPayment; status=active
  cancel_case()     → status=cancelled (draft or approved only)

Invariants:
  - Only one non-cancelled case per member (enforced in create_case).
  - Calculation snapshot and final_monthly_annuity are immutable once approved.
  - All status writes are append-only via contract_service.begin_annuity().
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.member import Member
from app.models.payment import BenefitPayment
from app.models.plan_config import PlanType
from app.models.retirement_case import RetirementCase
from app.schemas.benefit import (
    BenefitCalculationResult,
    BenefitOptionRequest,
)
from app.schemas.contract import BeginAnnuityCreate
from app.services import contract_service, survivor_service
from app.services.benefit_estimate_service import get_estimate


# ── Case creation and recalculation ───────────────────────────────────────────

async def create_case(
    member_id: uuid.UUID,
    retirement_date: date,
    session: AsyncSession,
    sick_leave_days: int = 0,
    benefit_option_type: str = "single_life",
    beneficiary_id: uuid.UUID | None = None,
    beneficiary_age_at_retirement: int | None = None,
    desired_reversionary_monthly: Decimal | None = None,
    created_by: uuid.UUID | None = None,
    note: str | None = None,
) -> RetirementCase:
    """Create a retirement case in draft status with an initial calculation snapshot."""
    member = await session.get(Member, member_id)
    if not member:
        raise ValueError(f"Member {member_id} not found")

    if member.member_status == "annuitant":
        raise ValueError("Member is already an annuitant — cannot open a retirement case")
    if member.member_status == "deceased":
        raise ValueError("Member is deceased — cannot open a retirement case")

    # Only one open case per member
    existing = await _open_case(member_id, session)
    if existing:
        raise ValueError(
            f"Member already has an open retirement case ({existing.id}, status={existing.status}). "
            "Cancel it before creating a new one."
        )

    benefit_option = _build_option_request(
        benefit_option_type, beneficiary_age_at_retirement, desired_reversionary_monthly
    )
    snapshot = await get_estimate(
        member_id=member_id,
        retirement_date=retirement_date,
        session=session,
        sick_leave_days=sick_leave_days,
        benefit_option=benefit_option,
    )

    termination_date = await _resolve_termination_date(member_id, session, retirement_date)

    case = RetirementCase(
        member_id=member_id,
        status="draft",
        retirement_date=retirement_date,
        termination_date=termination_date,
        sick_leave_days=sick_leave_days,
        benefit_option_type=benefit_option_type,
        beneficiary_id=beneficiary_id,
        beneficiary_age_at_retirement=beneficiary_age_at_retirement,
        desired_reversionary_monthly=desired_reversionary_monthly,
        calculation_snapshot=snapshot.model_dump(mode="json"),
        created_by=created_by,
        note=note,
    )
    session.add(case)
    await session.flush()
    return case


async def recalculate(
    case_id: uuid.UUID,
    session: AsyncSession,
) -> RetirementCase:
    """Re-run the calculation and update the snapshot. Draft status only."""
    case = await _get_case_or_raise(case_id, session)
    if case.status != "draft":
        raise ValueError(f"Cannot recalculate case in status '{case.status}' — must be draft")

    benefit_option = _build_option_request(
        case.benefit_option_type,
        case.beneficiary_age_at_retirement,
        case.desired_reversionary_monthly,
    )
    snapshot = await get_estimate(
        member_id=case.member_id,
        retirement_date=case.retirement_date,
        session=session,
        sick_leave_days=case.sick_leave_days,
        benefit_option=benefit_option,
    )
    case.calculation_snapshot = snapshot.model_dump(mode="json")
    await session.flush()
    return case


# ── Workflow transitions ───────────────────────────────────────────────────────

async def approve_case(
    case_id: uuid.UUID,
    session: AsyncSession,
    approved_by: uuid.UUID | None = None,
) -> RetirementCase:
    """Lock the calculation, record benefit election, and transition member to annuitant.

    What happens here:
      1. Validate status=draft and snapshot exists.
      2. Call survivor_service.record_election() with the elected option.
      3. Call contract_service.begin_annuity() to transition member status.
      4. Denormalize final_monthly_annuity from snapshot.
      5. Set status=approved.
    """
    case = await _get_case_or_raise(case_id, session)
    if case.status != "draft":
        raise ValueError(f"Cannot approve case in status '{case.status}' — must be draft")
    if not case.calculation_snapshot:
        raise ValueError("Case has no calculation snapshot — run recalculate first")

    result = BenefitCalculationResult.model_validate(case.calculation_snapshot)
    final_monthly = result.final_monthly_annuity

    # Record benefit election (drives future survivor benefit lookups)
    if case.benefit_option_type != "single_life":
        await survivor_service.record_election(
            member_id=case.member_id,
            option_type=case.benefit_option_type,
            member_monthly_annuity=result.benefit_option.reduced_annuity_monthly,
            effective_date=case.retirement_date,
            session=session,
            beneficiary_id=case.beneficiary_id,
            beneficiary_age_at_election=case.beneficiary_age_at_retirement,
            reversionary_monthly_amount=result.benefit_option.beneficiary_annuity_monthly
            if case.benefit_option_type == "reversionary"
            else None,
            elected_by=approved_by,
        )
    else:
        await survivor_service.record_election(
            member_id=case.member_id,
            option_type="single_life",
            member_monthly_annuity=final_monthly,
            effective_date=case.retirement_date,
            session=session,
            elected_by=approved_by,
        )

    # Transition member to annuitant
    await contract_service.begin_annuity(
        member_id=case.member_id,
        data=BeginAnnuityCreate(
            effective_date=case.retirement_date,
            note=f"Retirement case {case_id} approved",
        ),
        session=session,
        changed_by=approved_by,
    )

    case.final_monthly_annuity = final_monthly
    case.status = "approved"
    case.approved_at = datetime.now(timezone.utc)
    case.approved_by = approved_by
    await session.flush()
    return case


async def activate_case(
    case_id: uuid.UUID,
    first_payment_date: date,
    session: AsyncSession,
    payment_method: str = "ach",
    bank_account_id: uuid.UUID | None = None,
    activated_by: uuid.UUID | None = None,
) -> RetirementCase:
    """Create the first annuity BenefitPayment and set status=active."""
    case = await _get_case_or_raise(case_id, session)
    if case.status != "approved":
        raise ValueError(f"Cannot activate case in status '{case.status}' — must be approved")

    gross = case.final_monthly_annuity
    if gross is None:
        raise ValueError("Case has no final_monthly_annuity — this should not happen on an approved case")

    payment = BenefitPayment(
        member_id=case.member_id,
        bank_account_id=bank_account_id,
        period_start=first_payment_date,
        period_end=first_payment_date,
        payment_date=first_payment_date,
        gross_amount=gross,
        net_amount=gross,
        payment_type="annuity",
        payment_method=payment_method,
        status="pending",
        created_by=activated_by,
    )
    session.add(payment)
    await session.flush()

    case.first_payment_id = payment.id
    case.first_payment_date = first_payment_date
    case.status = "active"
    case.activated_at = datetime.now(timezone.utc)
    case.activated_by = activated_by
    await session.flush()
    return case


async def cancel_case(
    case_id: uuid.UUID,
    session: AsyncSession,
    cancelled_by: uuid.UUID | None = None,
    cancel_reason: str | None = None,
) -> RetirementCase:
    """Cancel a draft or approved retirement case."""
    case = await _get_case_or_raise(case_id, session)
    if case.status not in ("draft", "approved"):
        raise ValueError(f"Cannot cancel case in status '{case.status}'")

    case.status = "cancelled"
    case.cancelled_at = datetime.now(timezone.utc)
    case.cancelled_by = cancelled_by
    case.cancel_reason = cancel_reason
    await session.flush()
    return case


# ── Queries ────────────────────────────────────────────────────────────────────

async def get_case(case_id: uuid.UUID, session: AsyncSession) -> RetirementCase:
    return await _get_case_or_raise(case_id, session)


async def list_cases(
    member_id: uuid.UUID, session: AsyncSession
) -> list[RetirementCase]:
    stmt = (
        select(RetirementCase)
        .where(RetirementCase.member_id == member_id)
        .order_by(RetirementCase.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ── Internal helpers ───────────────────────────────────────────────────────────

async def _get_case_or_raise(case_id: uuid.UUID, session: AsyncSession) -> RetirementCase:
    case = await session.get(RetirementCase, case_id)
    if not case:
        raise ValueError(f"Retirement case {case_id} not found")
    return case


async def _open_case(member_id: uuid.UUID, session: AsyncSession) -> RetirementCase | None:
    """Return the non-cancelled case for this member, if one exists."""
    stmt = (
        select(RetirementCase)
        .where(
            RetirementCase.member_id == member_id,
            RetirementCase.status.not_in(["cancelled"]),
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _resolve_termination_date(
    member_id: uuid.UUID, session: AsyncSession, fallback: date
) -> date | None:
    from app.models.employment import EmploymentRecord
    stmt = (
        select(EmploymentRecord.termination_date)
        .where(
            EmploymentRecord.member_id == member_id,
            EmploymentRecord.termination_date.isnot(None),
        )
        .order_by(EmploymentRecord.termination_date.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _build_option_request(
    option_type: str,
    beneficiary_age: int | None,
    desired_reversionary_monthly: Decimal | None,
) -> BenefitOptionRequest | None:
    if option_type == "single_life":
        return None
    return BenefitOptionRequest(
        option_type=option_type,
        beneficiary_age=beneficiary_age,
        desired_reversionary_monthly=desired_reversionary_monthly,
    )

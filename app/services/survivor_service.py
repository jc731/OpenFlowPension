"""Death and survivor benefit service.

Handles two scenarios:
  Pre-retirement death (member status != annuitant):
    Lump-sum death benefit = total employee contributions on file.
    No continuing survivor annuity.

  Post-retirement death (member status == annuitant):
    Benefit driven by MemberBenefitElection.option_type:
      single_life        → no survivor benefit
      js_50 / js_75 / js_100 → survivor receives elected % of member_monthly_annuity
      reversionary       → survivor receives reversionary_monthly_amount

All writes follow the append-only / immutability patterns used elsewhere:
  - BenefitPayment rows are written with payment_type=death_benefit or
    payment_type=survivor_annuity.
  - MemberBenefitElection rows are never updated; a new row supersedes the old.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.benefit_election import MemberBenefitElection
from app.models.beneficiary import Beneficiary, BeneficiaryBankAccount
from app.models.member import Member
from app.models.payment import BenefitPayment
from app.models.payroll import ContributionRecord


# ── Election management ────────────────────────────────────────────────────────

async def record_election(
    member_id: uuid.UUID,
    option_type: str,
    member_monthly_annuity: Decimal,
    effective_date: date,
    session: AsyncSession,
    beneficiary_id: uuid.UUID | None = None,
    beneficiary_age_at_election: int | None = None,
    reversionary_monthly_amount: Decimal | None = None,
    elected_by: uuid.UUID | None = None,
    note: str | None = None,
) -> MemberBenefitElection:
    """Insert a new benefit election row. A later effective_date supersedes the previous one."""
    _validate_option_type(option_type)

    member = await session.get(Member, member_id)
    if not member:
        raise ValueError(f"Member {member_id} not found")

    if option_type != "single_life" and beneficiary_id is None:
        raise ValueError(f"option_type '{option_type}' requires a beneficiary_id")

    if option_type == "reversionary" and reversionary_monthly_amount is None:
        raise ValueError("reversionary option requires reversionary_monthly_amount")

    if beneficiary_id is not None:
        bene = await session.get(Beneficiary, beneficiary_id)
        if not bene or bene.member_id != member_id:
            raise ValueError(f"Beneficiary {beneficiary_id} not found on member {member_id}")

    election = MemberBenefitElection(
        member_id=member_id,
        option_type=option_type,
        beneficiary_id=beneficiary_id,
        beneficiary_age_at_election=beneficiary_age_at_election,
        member_monthly_annuity=member_monthly_annuity,
        reversionary_monthly_amount=reversionary_monthly_amount,
        effective_date=effective_date,
        elected_by=elected_by,
        note=note,
    )
    session.add(election)
    await session.flush()
    return election


async def get_current_election(
    member_id: uuid.UUID,
    session: AsyncSession,
    as_of: date | None = None,
) -> MemberBenefitElection | None:
    """Return the most recent election with effective_date <= as_of (or today if not given)."""
    cutoff = as_of or date.today()
    stmt = (
        select(MemberBenefitElection)
        .where(
            MemberBenefitElection.member_id == member_id,
            MemberBenefitElection.effective_date <= cutoff,
        )
        .order_by(MemberBenefitElection.effective_date.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


# ── Survivor benefit calculation ───────────────────────────────────────────────

class SurvivorBenefitResult:
    """Lightweight result object — not a Pydantic model since it is not an API response itself."""

    def __init__(
        self,
        scenario: str,
        is_pre_retirement: bool,
        lump_sum_amount: Decimal = Decimal("0"),
        survivor_monthly_amount: Decimal = Decimal("0"),
        beneficiary_id: uuid.UUID | None = None,
        option_type: str | None = None,
    ):
        self.scenario = scenario
        self.is_pre_retirement = is_pre_retirement
        self.lump_sum_amount = lump_sum_amount
        self.survivor_monthly_amount = survivor_monthly_amount
        self.beneficiary_id = beneficiary_id
        self.option_type = option_type


async def calculate_survivor_benefit(
    member_id: uuid.UUID,
    event_date: date,
    session: AsyncSession,
) -> SurvivorBenefitResult:
    """Calculate what is owed on the member's death. Does not write anything."""
    member = await session.get(Member, member_id)
    if not member:
        raise ValueError(f"Member {member_id} not found")

    if member.member_status != "annuitant":
        # Pre-retirement death: lump sum = total employee contributions
        total = await _total_employee_contributions(member_id, session)
        return SurvivorBenefitResult(
            scenario="pre_retirement_lump_sum",
            is_pre_retirement=True,
            lump_sum_amount=total,
        )

    # Post-retirement: look up the active election
    election = await get_current_election(member_id, session, as_of=event_date)
    if election is None or election.option_type == "single_life":
        return SurvivorBenefitResult(
            scenario="no_survivor_benefit",
            is_pre_retirement=False,
            option_type="single_life",
        )

    opt = election.option_type
    if opt in ("js_50", "js_75", "js_100"):
        pct = Decimal(opt.split("_")[1]) / Decimal("100")
        monthly = (election.member_monthly_annuity * pct).quantize(Decimal("0.01"))
        return SurvivorBenefitResult(
            scenario="joint_and_survivor",
            is_pre_retirement=False,
            survivor_monthly_amount=monthly,
            beneficiary_id=election.beneficiary_id,
            option_type=opt,
        )

    if opt == "reversionary":
        return SurvivorBenefitResult(
            scenario="reversionary_annuity",
            is_pre_retirement=False,
            survivor_monthly_amount=election.reversionary_monthly_amount or Decimal("0"),
            beneficiary_id=election.beneficiary_id,
            option_type="reversionary",
        )

    raise ValueError(f"Unrecognized option_type '{opt}' on election {election.id}")


# ── Payment initiation ─────────────────────────────────────────────────────────

async def initiate_survivor_payments(
    member_id: uuid.UUID,
    event_date: date,
    session: AsyncSession,
    payment_method: str = "ach",
    created_by: uuid.UUID | None = None,
) -> list[BenefitPayment]:
    """Create BenefitPayment rows based on the calculated survivor benefit.

    Returns the list of payment rows created (0, 1, or more).
    Caller is responsible for committing the session.
    """
    result = await calculate_survivor_benefit(member_id, event_date, session)
    payments: list[BenefitPayment] = []

    if result.scenario == "no_survivor_benefit":
        return payments

    if result.scenario == "pre_retirement_lump_sum":
        payment = BenefitPayment(
            member_id=member_id,
            period_start=event_date,
            period_end=event_date,
            payment_date=event_date,
            gross_amount=result.lump_sum_amount,
            net_amount=result.lump_sum_amount,
            payment_type="death_benefit",
            payment_method=payment_method,
            status="pending",
            created_by=created_by,
        )
        session.add(payment)
        payments.append(payment)
        await session.flush()
        return payments

    # Post-retirement survivor annuity — route to beneficiary's primary bank account
    beneficiary_bank_account_id = None
    if result.beneficiary_id:
        beneficiary_bank_account_id = await _primary_bene_bank_account(
            result.beneficiary_id, session
        )

    monthly = result.survivor_monthly_amount
    payment = BenefitPayment(
        member_id=member_id,
        beneficiary_id=result.beneficiary_id,
        beneficiary_bank_account_id=beneficiary_bank_account_id,
        period_start=event_date,
        period_end=event_date,
        payment_date=event_date,
        gross_amount=monthly,
        net_amount=monthly,
        payment_type="survivor_annuity",
        payment_method=payment_method,
        status="pending",
        created_by=created_by,
    )
    session.add(payment)
    payments.append(payment)
    await session.flush()
    return payments


# ── Internal helpers ───────────────────────────────────────────────────────────

def _validate_option_type(option_type: str) -> None:
    valid = {"single_life", "reversionary", "js_50", "js_75", "js_100"}
    if option_type not in valid:
        raise ValueError(f"Invalid option_type '{option_type}'. Valid: {sorted(valid)}")


async def _total_employee_contributions(
    member_id: uuid.UUID, session: AsyncSession
) -> Decimal:
    stmt = select(func.sum(ContributionRecord.employee_contribution)).where(
        ContributionRecord.member_id == member_id,
        ContributionRecord.voided_at.is_(None),
    )
    result = await session.execute(stmt)
    total = result.scalar_one_or_none()
    return Decimal(str(total)) if total is not None else Decimal("0")


async def _primary_bene_bank_account(
    beneficiary_id: uuid.UUID, session: AsyncSession
) -> uuid.UUID | None:
    stmt = (
        select(BeneficiaryBankAccount.id)
        .where(
            BeneficiaryBankAccount.beneficiary_id == beneficiary_id,
            BeneficiaryBankAccount.is_primary.is_(True),
            BeneficiaryBankAccount.end_date.is_(None),
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

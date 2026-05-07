"""Service purchase — quote, claim lifecycle, payment recording, credit grant.

Purchase types are fully config-driven via the `service_purchase_types`
system_configurations key. Adding a new type = add an entry to that config;
no code changes required unless it needs a new calc_method.

Supported calc_methods:
  rate_based        — cost = credit_years × current_salary × (employee_rate + employer_rate)
  refund_repayment  — NOT YET IMPLEMENTED; raises ValueError with guidance

credit_grant_on controls when ServiceCreditEntry is written:
  approval          — on claim approval (before payment)
  first_payment     — on first non-voided payment received
  completion        — when cost_paid >= cost_total (default)
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employment import EmploymentRecord
from app.models.salary import SalaryHistory
from app.models.service_credit import ServiceCreditEntry
from app.models.service_purchase import ServicePurchaseClaim, ServicePurchasePayment
from app.schemas.service_purchase import (
    ServicePurchaseClaimCreate,
    ServicePurchasePaymentCreate,
    ServicePurchaseQuoteRequest,
    ServicePurchaseQuoteResult,
)
from app.services.config_service import ConfigNotFoundError, get_config


# ── Config helpers ─────────────────────────────────────────────────────────────

async def _load_type_config(purchase_type: str, as_of: date, session: AsyncSession) -> dict:
    try:
        cfg = await get_config("service_purchase_types", as_of, session)
    except ConfigNotFoundError:
        raise ValueError("service_purchase_types config not found — seed this key before using service purchase")
    types = cfg.config_value.get("types", {})
    if purchase_type not in types:
        raise ValueError(f"Unknown purchase type '{purchase_type}'. Configured types: {list(types)}")
    return types[purchase_type]


async def _current_salary(member_id: uuid.UUID, as_of: date, session: AsyncSession) -> Decimal:
    result = await session.execute(
        select(SalaryHistory)
        .join(EmploymentRecord, SalaryHistory.employment_id == EmploymentRecord.id)
        .where(
            EmploymentRecord.member_id == member_id,
            SalaryHistory.effective_date <= as_of,
        )
        .order_by(SalaryHistory.effective_date.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise ValueError("No salary history found for member — required for rate-based cost calculation")
    return Decimal(str(row.annual_salary))


# ── Calc methods ───────────────────────────────────────────────────────────────

def _calc_rate_based(credit_years: Decimal, annual_salary: Decimal, type_cfg: dict) -> tuple[Decimal, dict]:
    employee_rate = Decimal(str(type_cfg.get("employee_rate", 0)))
    employer_rate = Decimal(str(type_cfg.get("employer_rate", 0)))
    total_rate = employee_rate + employer_rate
    cost = (credit_years * annual_salary * total_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    breakdown = {
        "method": "rate_based",
        "credit_years": str(credit_years),
        "annual_salary": str(annual_salary),
        "employee_rate": str(employee_rate),
        "employer_rate": str(employer_rate),
        "total_rate": str(total_rate),
        "cost_total": str(cost),
    }
    return cost, breakdown


def _calc_refund_repayment(credit_years: Decimal, type_cfg: dict) -> tuple[Decimal, dict]:
    raise ValueError(
        "calc_method 'refund_repayment' is not yet implemented. "
        "Refund repayment cost requires the original refund amount and fund-specific interest "
        "compounding rules. This type will be implemented as a dedicated endpoint once those "
        "rules are confirmed. Use a manual override or contact fund staff."
    )


_CALC_METHODS = {
    "rate_based": _calc_rate_based,
    "refund_repayment": _calc_refund_repayment,
}


async def _run_calc(
    purchase_type: str,
    credit_years: Decimal,
    member_id: uuid.UUID,
    as_of: date,
    type_cfg: dict,
    session: AsyncSession,
) -> tuple[Decimal, dict]:
    method = type_cfg.get("calc_method", "rate_based")
    if method == "rate_based":
        salary = await _current_salary(member_id, as_of, session)
        return _calc_rate_based(credit_years, salary, type_cfg)
    elif method == "refund_repayment":
        return _calc_refund_repayment(credit_years, type_cfg)
    else:
        raise ValueError(f"Unknown calc_method '{method}' on purchase type '{purchase_type}'")


# ── Quote (stateless) ──────────────────────────────────────────────────────────

async def quote(
    member_id: uuid.UUID,
    req: ServicePurchaseQuoteRequest,
    session: AsyncSession,
) -> ServicePurchaseQuoteResult:
    as_of = req.period_end
    type_cfg = await _load_type_config(req.purchase_type, as_of, session)
    cost, breakdown = await _run_calc(req.purchase_type, req.credit_years, member_id, as_of, type_cfg, session)
    return ServicePurchaseQuoteResult(
        purchase_type=req.purchase_type,
        credit_entry_type=type_cfg["credit_entry_type"],
        credit_years=req.credit_years,
        cost_total=cost,
        cost_breakdown=breakdown,
        installment_allowed=type_cfg.get("installment_allowed", False),
        credit_grant_on=type_cfg.get("credit_grant_on", "completion"),
    )


# ── Claim lifecycle ────────────────────────────────────────────────────────────

async def create_claim(
    member_id: uuid.UUID,
    data: ServicePurchaseClaimCreate,
    session: AsyncSession,
    created_by: uuid.UUID | None = None,
) -> ServicePurchaseClaim:
    as_of = data.period_end
    type_cfg = await _load_type_config(data.purchase_type, as_of, session)

    if not type_cfg.get("installment_allowed", False):
        pass  # noted on claim; enforced at payment recording

    cost, breakdown = await _run_calc(
        data.purchase_type, data.credit_years, member_id, as_of, type_cfg, session
    )

    claim = ServicePurchaseClaim(
        member_id=member_id,
        purchase_type=data.purchase_type,
        status="draft",
        credit_entry_type=type_cfg["credit_entry_type"],
        credit_years=float(data.credit_years),
        period_start=data.period_start,
        period_end=data.period_end,
        cost_total=float(cost),
        cost_paid=0,
        cost_breakdown=breakdown,
        installment_allowed=type_cfg.get("installment_allowed", False),
        credit_grant_on=type_cfg.get("credit_grant_on", "completion"),
        params=data.params,
        notes=data.notes,
        created_by=created_by,
    )
    session.add(claim)
    await session.flush()
    return claim


async def get_claim(claim_id: uuid.UUID, session: AsyncSession) -> ServicePurchaseClaim | None:
    return await session.get(ServicePurchaseClaim, claim_id)


async def list_claims(member_id: uuid.UUID, session: AsyncSession) -> list[ServicePurchaseClaim]:
    result = await session.execute(
        select(ServicePurchaseClaim)
        .where(ServicePurchaseClaim.member_id == member_id)
        .order_by(ServicePurchaseClaim.created_at.desc())
    )
    return list(result.scalars().all())


async def submit_claim(
    claim: ServicePurchaseClaim,
    session: AsyncSession,
) -> ServicePurchaseClaim:
    """Transition draft → pending_approval (member submits for staff review)."""
    if claim.status != "draft":
        raise ValueError(f"Cannot submit claim in status '{claim.status}' — must be 'draft'")
    claim.status = "pending_approval"
    await session.flush()
    return claim


async def approve_claim(
    claim: ServicePurchaseClaim,
    approved_by: uuid.UUID,
    session: AsyncSession,
    notes: str | None = None,
) -> ServicePurchaseClaim:
    """Transition pending_approval → approved. Grants credit if credit_grant_on='approval'."""
    if claim.status != "pending_approval":
        raise ValueError(f"Cannot approve claim in status '{claim.status}' — must be 'pending_approval'")
    claim.status = "approved"
    claim.approved_at = datetime.now(timezone.utc)
    claim.approved_by = approved_by
    if notes:
        claim.notes = notes
    if claim.credit_grant_on == "approval":
        await _grant_credit(claim, session)
        claim.status = "completed"
        claim.completed_at = datetime.now(timezone.utc)
    await session.flush()
    return claim


async def cancel_claim(
    claim: ServicePurchaseClaim,
    cancel_reason: str,
    session: AsyncSession,
) -> ServicePurchaseClaim:
    terminal = {"completed", "cancelled"}
    if claim.status in terminal:
        raise ValueError(f"Cannot cancel claim in status '{claim.status}'")
    claim.status = "cancelled"
    claim.cancelled_at = datetime.now(timezone.utc)
    claim.cancel_reason = cancel_reason
    await session.flush()
    return claim


# ── Payment recording ──────────────────────────────────────────────────────────

async def record_payment(
    claim: ServicePurchaseClaim,
    data: ServicePurchasePaymentCreate,
    session: AsyncSession,
    received_by: uuid.UUID | None = None,
) -> ServicePurchasePayment:
    if claim.status not in ("approved", "in_payment"):
        raise ValueError(f"Cannot record payment on claim in status '{claim.status}' — must be approved or in_payment")
    if not claim.installment_allowed and Decimal(str(claim.cost_paid)) > Decimal("0"):
        raise ValueError("This purchase type does not allow installment payments — a payment has already been recorded")

    payment = ServicePurchasePayment(
        claim_id=claim.id,
        amount=float(data.amount),
        payment_date=data.payment_date,
        payment_method=data.payment_method,
        reference_number=data.reference_number,
        received_by=received_by,
    )
    session.add(payment)

    is_first_payment = Decimal(str(claim.cost_paid)) == Decimal("0")
    claim.cost_paid = float(
        (Decimal(str(claim.cost_paid)) + Decimal(str(data.amount))).quantize(Decimal("0.01"))
    )

    if claim.status == "approved":
        claim.status = "in_payment"

    # Grant credit on first_payment if configured
    if claim.credit_grant_on == "first_payment" and is_first_payment:
        await _grant_credit(claim, session)

    # Complete if fully paid
    if Decimal(str(claim.cost_paid)) >= Decimal(str(claim.cost_total)):
        if claim.credit_grant_on == "completion":
            await _grant_credit(claim, session)
        claim.status = "completed"
        claim.completed_at = datetime.now(timezone.utc)

    await session.flush()
    return payment


# ── Credit grant ───────────────────────────────────────────────────────────────

async def _grant_credit(claim: ServicePurchaseClaim, session: AsyncSession) -> None:
    entry = ServiceCreditEntry(
        member_id=claim.member_id,
        entry_type=claim.credit_entry_type,
        credit_days=Decimal(str(claim.credit_years)) * 365,
        credit_years=Decimal(str(claim.credit_years)),
        period_start=claim.period_start,
        period_end=claim.period_end,
        source_document_id=claim.id,
        note=f"Service purchase — type: {claim.purchase_type}, claim: {claim.id}",
    )
    session.add(entry)

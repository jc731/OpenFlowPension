"""Payment disbursement service.

Handles payment generation, standing deduction order application, and status updates.

Key rules:
- gross_amount and net_amount on a payment are immutable once status=issued.
- payment_deductions rows are append-only — never UPDATE or DELETE.
- Corrections: reverse the payment (status=reversed) and create a new one.
- net_amount = gross_amount - sum(deductions)
"""

import uuid
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.payment import BenefitPayment, DeductionOrder, PaymentDeduction, TaxWithholdingElection
from app.schemas.payment import (
    DeductionOrderCreate,
    DeductionOrderEnd,
    PaymentCreate,
    PaymentDeductionCreate,
    PaymentStatusUpdate,
    TaxWithholdingElectionCreate,
)


# ── Pure helpers ───────────────────────────────────────────────────────────────

def compute_deduction_amount(order: DeductionOrder, gross_amount: Decimal) -> Decimal:
    amt = Decimal(str(order.amount))
    if order.amount_type == "fixed":
        return amt
    if order.amount_type == "percent_of_gross":
        return (gross_amount * amt).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    raise ValueError(f"Unknown amount_type: {order.amount_type!r}")


def compute_net_amount(gross: Decimal, deductions: list[Decimal]) -> Decimal:
    return (gross - sum(deductions)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ── Deduction orders ───────────────────────────────────────────────────────────

async def create_deduction_order(
    member_id: uuid.UUID,
    data: DeductionOrderCreate,
    session: AsyncSession,
    created_by: uuid.UUID | None = None,
) -> DeductionOrder:
    order = DeductionOrder(
        member_id=member_id,
        deduction_type=data.deduction_type,
        deduction_code=data.deduction_code,
        amount_type=data.amount_type,
        amount=float(data.amount),
        is_pretax=data.is_pretax,
        effective_date=data.effective_date,
        end_date=data.end_date,
        source_document_type=data.source_document_type,
        source_document_id=data.source_document_id,
        note=data.note,
        created_by=created_by,
    )
    session.add(order)
    await session.flush()
    return order


async def end_deduction_order(
    order_id: uuid.UUID,
    member_id: uuid.UUID,
    data: DeductionOrderEnd,
    session: AsyncSession,
) -> DeductionOrder:
    order = await session.get(DeductionOrder, order_id)
    if not order or order.member_id != member_id:
        raise ValueError("Deduction order not found for this member")
    order.end_date = data.end_date
    await session.flush()
    return order


async def list_deduction_orders(
    member_id: uuid.UUID,
    session: AsyncSession,
    active_only: bool = False,
    as_of: date | None = None,
) -> list[DeductionOrder]:
    stmt = select(DeductionOrder).where(DeductionOrder.member_id == member_id)
    if active_only and as_of:
        stmt = stmt.where(
            DeductionOrder.effective_date <= as_of,
            or_(DeductionOrder.end_date.is_(None), DeductionOrder.end_date > as_of),
        )
    result = await session.execute(stmt.order_by(DeductionOrder.effective_date))
    return list(result.scalars().all())


async def _get_active_orders(
    member_id: uuid.UUID,
    as_of: date,
    session: AsyncSession,
) -> list[DeductionOrder]:
    return await list_deduction_orders(member_id, session, active_only=True, as_of=as_of)


# ── Tax withholding elections ──────────────────────────────────────────────────

async def set_tax_withholding(
    member_id: uuid.UUID,
    data: TaxWithholdingElectionCreate,
    session: AsyncSession,
    created_by: uuid.UUID | None = None,
) -> TaxWithholdingElection:
    # Supersede any current active election for this jurisdiction
    result = await session.execute(
        select(TaxWithholdingElection).where(
            TaxWithholdingElection.member_id == member_id,
            TaxWithholdingElection.jurisdiction == data.jurisdiction,
            TaxWithholdingElection.superseded_date.is_(None),
        )
    )
    for prior in result.scalars().all():
        prior.superseded_date = data.effective_date

    election = TaxWithholdingElection(
        member_id=member_id,
        jurisdiction=data.jurisdiction,
        filing_status=data.filing_status,
        additional_withholding=float(data.additional_withholding),
        exempt=data.exempt,
        effective_date=data.effective_date,
        created_by=created_by,
    )
    session.add(election)
    await session.flush()
    return election


async def list_tax_withholding_elections(
    member_id: uuid.UUID,
    session: AsyncSession,
) -> list[TaxWithholdingElection]:
    result = await session.execute(
        select(TaxWithholdingElection)
        .where(TaxWithholdingElection.member_id == member_id)
        .order_by(TaxWithholdingElection.jurisdiction, TaxWithholdingElection.effective_date.desc())
    )
    return list(result.scalars().all())


# ── Payments ───────────────────────────────────────────────────────────────────

async def create_payment(
    member_id: uuid.UUID,
    data: PaymentCreate,
    session: AsyncSession,
    created_by: uuid.UUID | None = None,
) -> BenefitPayment:
    gross = Decimal(str(data.gross_amount))
    deduction_rows: list[PaymentDeductionCreate] = []

    # Apply standing orders first
    if data.apply_standing_orders:
        active_orders = await _get_active_orders(member_id, data.payment_date, session)
        for order in active_orders:
            amt = compute_deduction_amount(order, gross)
            deduction_rows.append(PaymentDeductionCreate(
                deduction_type=order.deduction_type,
                deduction_code=order.deduction_code,
                amount=amt,
                is_pretax=order.is_pretax,
                deduction_order_id=order.id,
                note=f"Standing order applied",
            ))

    # Append any manual / one-time deductions from the request
    deduction_rows.extend(data.additional_deductions)

    net = compute_net_amount(gross, [d.amount for d in deduction_rows])

    payment = BenefitPayment(
        member_id=member_id,
        bank_account_id=data.bank_account_id,
        period_start=data.period_start,
        period_end=data.period_end,
        payment_date=data.payment_date,
        gross_amount=float(gross),
        net_amount=float(net),
        status="pending",
        payment_method=data.payment_method,
        check_number=data.check_number,
        note=data.note,
        created_by=created_by,
    )
    session.add(payment)
    await session.flush()

    for d in deduction_rows:
        session.add(PaymentDeduction(
            payment_id=payment.id,
            deduction_order_id=d.deduction_order_id,
            deduction_type=d.deduction_type,
            deduction_code=d.deduction_code,
            amount=float(d.amount),
            is_pretax=d.is_pretax,
            note=d.note,
        ))

    await session.flush()
    await session.refresh(payment, ["deductions"])
    return payment


async def get_payment(
    payment_id: uuid.UUID,
    session: AsyncSession,
) -> BenefitPayment | None:
    result = await session.execute(
        select(BenefitPayment)
        .where(BenefitPayment.id == payment_id)
        .options(selectinload(BenefitPayment.deductions))
    )
    return result.scalar_one_or_none()


async def list_payments(
    member_id: uuid.UUID,
    session: AsyncSession,
) -> list[BenefitPayment]:
    result = await session.execute(
        select(BenefitPayment)
        .where(BenefitPayment.member_id == member_id)
        .options(selectinload(BenefitPayment.deductions))
        .order_by(BenefitPayment.payment_date.desc())
    )
    return list(result.scalars().all())


async def update_payment_status(
    payment_id: uuid.UUID,
    data: PaymentStatusUpdate,
    session: AsyncSession,
) -> BenefitPayment:
    payment = await session.get(BenefitPayment, payment_id)
    if not payment:
        raise ValueError("Payment not found")
    if payment.status == "issued" and data.status not in ("reversed", "held"):
        raise ValueError("Issued payments can only be reversed or held")
    payment.status = data.status
    if data.note:
        payment.note = data.note
    if data.status == "issued":
        from datetime import datetime, timezone
        payment.issued_at = datetime.now(timezone.utc)
    await session.flush()
    return payment

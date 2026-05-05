"""Net pay calculation engine.

Three entry points:
- calculate_net_pay()       — pure function; no DB access; drives the stateless endpoint
- get_net_pay_preview()     — DB-backed read-only; resolves a BenefitPayment's member data
- apply_net_pay()           — write path; persists PaymentDeduction rows + updates net_amount

Math order:
    gross
    − pre-tax deductions          → reduces taxable base
    = taxable gross
    − federal income tax          → IRS annualized percentage method (Pub 15-T)
    − state income tax            → jurisdiction-specific flat / bracket rate
    − post-tax deductions
    = net pay
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.payment import (
    BenefitPayment,
    DeductionOrder,
    PaymentDeduction,
    TaxWithholdingElection,
)
from app.models.third_party_entity import ThirdPartyEntity
from app.schemas.net_pay import (
    NetPayDeductionInput,
    NetPayLineItem,
    NetPayRequest,
    NetPayResult,
    NetPayTaxElectionInput,
    PayFrequency,
)
from app.services.config_service import ConfigNotFoundError, get_config

_TWO = Decimal("0.01")

PAY_PERIODS: dict[str, int] = {
    "monthly": 12,
    "semi_monthly": 24,
    "biweekly": 26,
    "weekly": 52,
}

# Maps filing statuses that share a bracket table
_FILING_STATUS_ALIAS: dict[str, str] = {
    "married_filing_separately": "single",
    "head_of_household": "single",
    "qualifying_surviving_spouse": "married_filing_jointly",
}


# ── Tax calculation helpers ────────────────────────────────────────────────────

def _apply_brackets(taxable: Decimal, brackets: list[dict[str, Any]]) -> Decimal:
    """Apply a graduated bracket table to an annualized taxable amount."""
    tax = Decimal("0")
    for band in brackets:
        floor = Decimal(str(band["min"]))
        ceiling = Decimal(str(band["max"])) if band["max"] is not None else None
        rate = Decimal(str(band["rate"]))
        base = Decimal(str(band["base_tax"]))

        if taxable <= floor:
            break
        if ceiling is None or taxable <= ceiling:
            tax = base + (taxable - floor) * rate
            break
    return tax.quantize(_TWO, rounding=ROUND_HALF_UP)


def _compute_federal_withholding(
    gross: Decimal,
    election: NetPayTaxElectionInput,
    pay_periods: int,
    config: dict[str, Any],
) -> Decimal:
    if election.exempt:
        return Decimal("0")

    brackets_by_status: dict[str, list[dict]] = config["brackets"]
    std_deductions: dict[str, float] = config["standard_withholding_deduction"]

    status_key = _FILING_STATUS_ALIAS.get(election.filing_status, election.filing_status)
    brackets = brackets_by_status.get(status_key) or brackets_by_status.get("single", [])
    std_deduction = Decimal(str(std_deductions.get(status_key, std_deductions.get("single", 0))))

    annualized = gross * pay_periods
    adjusted = max(annualized - std_deduction, Decimal("0"))
    annual_tax = _apply_brackets(adjusted, brackets)

    per_period = (annual_tax / pay_periods).quantize(_TWO, rounding=ROUND_HALF_UP)
    extra = Decimal(str(election.additional_withholding)).quantize(_TWO, rounding=ROUND_HALF_UP)
    return max(per_period + extra, Decimal("0"))


def _compute_illinois_withholding(
    taxable_gross: Decimal,
    election: NetPayTaxElectionInput,
    config: dict[str, Any],
) -> Decimal:
    if election.exempt:
        return Decimal("0")
    rate = Decimal(str(config["rate"]))
    tax = (taxable_gross * rate).quantize(_TWO, rounding=ROUND_HALF_UP)
    extra = Decimal(str(election.additional_withholding)).quantize(_TWO, rounding=ROUND_HALF_UP)
    return max(tax + extra, Decimal("0"))


# ── Core pure calculation ──────────────────────────────────────────────────────

def calculate_net_pay(
    gross: Decimal,
    deductions: list[NetPayDeductionInput],
    tax_elections: list[NetPayTaxElectionInput],
    payment_date: date,
    pay_frequency: PayFrequency,
    federal_tax_config: dict[str, Any] | None,
    illinois_tax_config: dict[str, Any] | None,
    third_party_names: dict[uuid.UUID, str] | None = None,
) -> NetPayResult:
    """Pure function — no DB access. Called by both the stateless and DB-backed paths."""
    pay_periods = PAY_PERIODS[pay_frequency]
    names = third_party_names or {}

    pretax_lines: list[NetPayLineItem] = []
    posttax_lines: list[NetPayLineItem] = []

    for d in deductions:
        amt = (
            d.amount
            if d.amount_type == "fixed"
            else (gross * d.amount).quantize(_TWO, rounding=ROUND_HALF_UP)
        )
        line = NetPayLineItem(
            description=d.description,
            amount=amt,
            deduction_type=d.deduction_type,
            is_pretax=d.is_pretax,
            third_party_entity_id=d.third_party_entity_id,
            third_party_entity_name=names.get(d.third_party_entity_id) if d.third_party_entity_id else None,
        )
        (pretax_lines if d.is_pretax else posttax_lines).append(line)

    total_pretax = sum(l.amount for l in pretax_lines) or Decimal("0")
    taxable_gross = (gross - total_pretax).quantize(_TWO, rounding=ROUND_HALF_UP)

    tax_lines: list[NetPayLineItem] = []
    for election in tax_elections:
        j = election.jurisdiction.lower()
        if j == "federal":
            if federal_tax_config is None:
                raise ConfigNotFoundError("federal_income_tax_withholding config not found")
            amt = _compute_federal_withholding(taxable_gross, election, pay_periods, federal_tax_config)
            tax_lines.append(NetPayLineItem(
                description="Federal Income Tax",
                amount=amt,
                deduction_type="federal_tax",
                is_pretax=False,
            ))
        elif j == "illinois":
            if illinois_tax_config is None:
                raise ConfigNotFoundError("illinois_income_tax config not found")
            amt = _compute_illinois_withholding(taxable_gross, election, illinois_tax_config)
            tax_lines.append(NetPayLineItem(
                description="Illinois State Income Tax",
                amount=amt,
                deduction_type="illinois_tax",
                is_pretax=False,
            ))
        # Additional jurisdictions: extend here

    total_taxes = sum(l.amount for l in tax_lines) or Decimal("0")
    total_posttax = sum(l.amount for l in posttax_lines) or Decimal("0")
    total_deductions = (total_pretax + total_taxes + total_posttax).quantize(_TWO, rounding=ROUND_HALF_UP)
    net = (gross - total_deductions).quantize(_TWO, rounding=ROUND_HALF_UP)

    return NetPayResult(
        gross_amount=gross,
        pretax_deductions=pretax_lines,
        taxable_gross=taxable_gross,
        tax_withholdings=tax_lines,
        posttax_deductions=posttax_lines,
        net_amount=net,
        total_pretax_deductions=total_pretax,
        total_taxes=total_taxes,
        total_posttax_deductions=total_posttax,
        total_deductions=total_deductions,
        payment_date=payment_date,
        tax_year=payment_date.year,
        pay_frequency=pay_frequency,
    )


# ── Config loading helpers ─────────────────────────────────────────────────────

async def _load_tax_configs(
    payment_date: date,
    session: AsyncSession,
) -> tuple[dict | None, dict | None]:
    """Return (federal_config, illinois_config) — None if the key isn't seeded."""
    federal = None
    illinois = None
    try:
        row = await get_config("federal_income_tax_withholding", payment_date, session)
        federal = row.config_value
    except ConfigNotFoundError:
        pass
    try:
        row = await get_config("illinois_income_tax", payment_date, session)
        illinois = row.config_value
    except ConfigNotFoundError:
        pass
    return federal, illinois


async def _resolve_third_party_names(
    entity_ids: list[uuid.UUID],
    session: AsyncSession,
) -> dict[uuid.UUID, str]:
    if not entity_ids:
        return {}
    result = await session.execute(
        select(ThirdPartyEntity.id, ThirdPartyEntity.name).where(
            ThirdPartyEntity.id.in_(entity_ids)
        )
    )
    return {row.id: row.name for row in result}


# ── DB-backed paths ────────────────────────────────────────────────────────────

async def _build_deduction_inputs_for_payment(
    payment: BenefitPayment,
    session: AsyncSession,
) -> list[NetPayDeductionInput]:
    """Resolve active DeductionOrders for a payment's member as of payment_date."""
    stmt = (
        select(DeductionOrder)
        .where(
            DeductionOrder.member_id == payment.member_id,
            DeductionOrder.effective_date <= payment.payment_date,
            or_(
                DeductionOrder.end_date.is_(None),
                DeductionOrder.end_date > payment.payment_date,
            ),
        )
        .options(selectinload(DeductionOrder.third_party_entity))
        .order_by(DeductionOrder.is_pretax.desc(), DeductionOrder.effective_date)
    )
    orders = (await session.execute(stmt)).scalars().all()

    inputs: list[NetPayDeductionInput] = []
    for order in orders:
        ent = order.third_party_entity
        inputs.append(NetPayDeductionInput(
            description=_order_description(order),
            deduction_type=order.deduction_type,
            amount_type=order.amount_type,
            amount=Decimal(str(order.amount)),
            is_pretax=order.is_pretax,
            third_party_entity_id=order.third_party_entity_id,
        ))
    return inputs


def _order_description(order: DeductionOrder) -> str:
    label = order.deduction_type.replace("_", " ").title()
    if order.deduction_code:
        label = f"{label} ({order.deduction_code})"
    return label


async def _build_tax_election_inputs(
    payment: BenefitPayment,
    session: AsyncSession,
) -> list[NetPayTaxElectionInput]:
    """Fetch active W-4 elections for the member as of payment_date."""
    result = await session.execute(
        select(TaxWithholdingElection).where(
            TaxWithholdingElection.member_id == payment.member_id,
            TaxWithholdingElection.effective_date <= payment.payment_date,
            TaxWithholdingElection.superseded_date.is_(None),
        )
    )
    elections = result.scalars().all()
    return [
        NetPayTaxElectionInput(
            jurisdiction=e.jurisdiction,
            filing_status=e.filing_status,
            additional_withholding=Decimal(str(e.additional_withholding)),
            exempt=e.exempt,
        )
        for e in elections
    ]


async def get_net_pay_preview(
    payment_id: uuid.UUID,
    session: AsyncSession,
) -> NetPayResult:
    """Read-only. Resolves member's standing orders + W-4 elections and computes net pay."""
    payment = await session.get(BenefitPayment, payment_id)
    if not payment:
        raise ValueError("Payment not found")

    deductions = await _build_deduction_inputs_for_payment(payment, session)
    elections = await _build_tax_election_inputs(payment, session)
    federal_cfg, illinois_cfg = await _load_tax_configs(payment.payment_date, session)

    entity_ids = [d.third_party_entity_id for d in deductions if d.third_party_entity_id]
    names = await _resolve_third_party_names(entity_ids, session)

    return calculate_net_pay(
        gross=Decimal(str(payment.gross_amount)),
        deductions=deductions,
        tax_elections=elections,
        payment_date=payment.payment_date,
        pay_frequency="monthly",
        federal_tax_config=federal_cfg,
        illinois_tax_config=illinois_cfg,
        third_party_names=names,
    )


async def apply_net_pay(
    payment_id: uuid.UUID,
    session: AsyncSession,
    applied_by: uuid.UUID | None = None,
) -> NetPayResult:
    """Write path. Resolves net pay then persists PaymentDeduction rows + net_amount.

    Idempotency guard: raises if deductions already exist on this payment.
    """
    payment = await session.get(BenefitPayment, payment_id)
    if not payment:
        raise ValueError("Payment not found")
    if payment.status == "issued":
        raise ValueError("Cannot apply net pay to an already-issued payment")

    existing_count = (await session.execute(
        select(PaymentDeduction.id).where(PaymentDeduction.payment_id == payment_id).limit(1)
    )).first()
    if existing_count:
        raise ValueError("Net pay has already been applied to this payment — reverse and reissue to correct")

    deductions = await _build_deduction_inputs_for_payment(payment, session)
    elections = await _build_tax_election_inputs(payment, session)
    federal_cfg, illinois_cfg = await _load_tax_configs(payment.payment_date, session)

    entity_ids = [d.third_party_entity_id for d in deductions if d.third_party_entity_id]
    names = await _resolve_third_party_names(entity_ids, session)

    net_pay = calculate_net_pay(
        gross=Decimal(str(payment.gross_amount)),
        deductions=deductions,
        tax_elections=elections,
        payment_date=payment.payment_date,
        pay_frequency="monthly",
        federal_tax_config=federal_cfg,
        illinois_tax_config=illinois_cfg,
        third_party_names=names,
    )

    # Resolve deduction_order_id per standing-order-backed deductions
    orders_by_type: dict[str, DeductionOrder] = {}
    stmt = select(DeductionOrder).where(
        DeductionOrder.member_id == payment.member_id,
        DeductionOrder.effective_date <= payment.payment_date,
        or_(DeductionOrder.end_date.is_(None), DeductionOrder.end_date > payment.payment_date),
    )
    for order in (await session.execute(stmt)).scalars().all():
        orders_by_type[order.deduction_type] = order

    all_lines = net_pay.pretax_deductions + net_pay.tax_withholdings + net_pay.posttax_deductions
    for line in all_lines:
        order = orders_by_type.get(line.deduction_type)
        session.add(PaymentDeduction(
            payment_id=payment.id,
            deduction_order_id=order.id if order else None,
            deduction_type=line.deduction_type,
            amount=float(line.amount),
            is_pretax=line.is_pretax,
            note=line.description,
        ))

    payment.net_amount = float(net_pay.net_amount)
    await session.flush()
    return net_pay


# ── Stateless endpoint helper ──────────────────────────────────────────────────

async def calculate_net_pay_stateless(
    req: NetPayRequest,
    session: AsyncSession,
) -> NetPayResult:
    """Load tax configs from DB then delegate to the pure calculate_net_pay()."""
    federal_cfg, illinois_cfg = await _load_tax_configs(req.payment_date, session)

    entity_ids = [d.third_party_entity_id for d in req.deductions if d.third_party_entity_id]
    names = await _resolve_third_party_names(entity_ids, session)

    return calculate_net_pay(
        gross=Decimal(str(req.gross_amount)),
        deductions=req.deductions,
        tax_elections=req.tax_elections,
        payment_date=req.payment_date,
        pay_frequency=req.pay_frequency,
        federal_tax_config=federal_cfg,
        illinois_tax_config=illinois_cfg,
        third_party_names=names,
    )

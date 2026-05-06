"""Net pay calculation engine.

Three entry points:
- calculate_net_pay()           — pure function; no DB access; drives the stateless endpoint
- get_net_pay_preview()         — DB-backed read-only; resolves a BenefitPayment's member data
- apply_net_pay()               — write path; persists PaymentDeduction rows + updates net_amount

Check-stub math order:
    gross
    − pre-tax deductions                → reduces taxable base; no external payee
    = taxable gross
    − federal income tax                → IRS Pub 15-T annualized percentage method (W-4P)
    − state income tax                  → jurisdiction-specific rate
    − post-tax deductions               → internal deductions; no external payee
    − third-party disbursements         → routed to external entities (courts, unions, etc.)
    = net pay

Federal formula (IRS Pub 15-T 2025 Worksheet 1):
    1. annualized_pay  = gross × pay_periods + step_4a_other_income
    2. adjusted_income = annualized_pay − std_deduction[filing_status] − step_4b_deductions
       (std_deduction from higher_withholding table when step_2_multiple_jobs=True)
    3. tentative_tax   = bracket_table(adjusted_income)
    4. annual_tax      = tentative_tax − step_3_dependent_credit
    5. per_period      = annual_tax / pay_periods
    6. final           = per_period + step_4c (additional_withholding)   → clamped ≥ 0

DB routing rule for DeductionOrders:
    - third_party_entity_id IS NOT NULL → third_party_disbursements tier
    - is_pretax = True                  → pretax_deductions
    - all others                        → posttax_deductions
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
    ThirdPartyDisbursementInput,
)
from app.services.config_service import ConfigNotFoundError, get_config

_TWO = Decimal("0.01")

PAY_PERIODS: dict[str, int] = {
    "monthly": 12,
    "semi_monthly": 24,
    "biweekly": 26,
    "weekly": 52,
}

# Fallback alias: used when a filing status has no dedicated bracket table in the config.
# 2025 config: only single + married_filing_jointly brackets → all others alias to one of these.
# 2026 config: adds head_of_household brackets → the exact-first lookup in _compute_federal_withholding
# uses HOH directly; the alias is only reached for married_filing_separately and qualifying_surviving_spouse.
_FILING_STATUS_ALIAS: dict[str, str] = {
    "married_filing_separately": "single",
    "head_of_household": "single",
    "qualifying_surviving_spouse": "married_filing_jointly",
}


# ── Tax calculation ────────────────────────────────────────────────────────────

def _apply_brackets(taxable: Decimal, brackets: list[dict[str, Any]]) -> Decimal:
    """Graduated bracket table applied to an annualized taxable amount."""
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


def _is_exempt(election: NetPayTaxElectionInput) -> bool:
    return election.withholding_type == "exempt" or election.exempt


def _compute_federal_withholding(
    gross: Decimal,
    election: NetPayTaxElectionInput,
    pay_periods: int,
    config: dict[str, Any],
) -> Decimal:
    """IRS Pub 15-T Worksheet 1A — Percentage Method for pension/annuity payments.

    Supports two config structures:
    - 2025 style: `brackets` + `standard_withholding_deduction` / `higher_withholding_deduction`
      (Step 2 checked → halved deduction, same brackets)
    - 2026+ style: `brackets` + `step2_brackets` + `standard_withholding_deduction`
      (Step 2 checked → dedicated bracket table, line 1g = $0)
    """
    if _is_exempt(election):
        return Decimal("0")

    if election.withholding_type == "flat_amount":
        return max(Decimal(str(election.additional_withholding)).quantize(_TWO, rounding=ROUND_HALF_UP), Decimal("0"))

    # Try exact filing_status first; fall back to alias (handles 2026 per-status tables and
    # 2025 configs that only have single + married_filing_jointly bracket tables).
    fs = election.filing_status
    alias = _FILING_STATUS_ALIAS.get(fs, fs)

    if election.step_2_multiple_jobs and "step2_brackets" in config:
        # 2026+ style: dedicated Step 2 checkbox bracket tables; line 1g = $0
        s2 = config["step2_brackets"]
        brackets = s2.get(fs) or s2.get(alias) or s2.get("single", [])
        std_deduction = Decimal("0")
    elif election.step_2_multiple_jobs:
        # 2025 style: halved standard deduction, same brackets
        std_deductions = config.get("higher_withholding_deduction", config["standard_withholding_deduction"])
        brackets = config["brackets"].get(fs) or config["brackets"].get(alias) or config["brackets"].get("single", [])
        std_val = std_deductions.get(fs) or std_deductions.get(alias) or std_deductions.get("single", 0)
        std_deduction = Decimal(str(std_val))
    else:
        # Standard: line 1g reduction + standard bracket table
        brackets = config["brackets"].get(fs) or config["brackets"].get(alias) or config["brackets"].get("single", [])
        std_deductions = config["standard_withholding_deduction"]
        std_val = std_deductions.get(fs) or std_deductions.get(alias) or std_deductions.get("single", 0)
        std_deduction = Decimal(str(std_val))

    # Worksheet 1A steps:
    # 1c: annualize
    annualized = gross * pay_periods
    # 1d+1e: add Step 4(a) other income
    annualized += Decimal(str(election.step_4a_other_income))
    # 1f+1g+1h: reduction = Step 4(b) + line-1g std deduction amount
    reduction = Decimal(str(election.step_4b_deductions)) + std_deduction
    # 1i: adjusted annual wage
    adjusted = max(annualized - reduction, Decimal("0"))
    # 2a-2g: apply bracket table
    tentative_annual = _apply_brackets(adjusted, brackets)
    # 3a-3c: subtract Step 3 dependent credit (dollar-for-dollar, not income reduction)
    annual_tax = max(tentative_annual - Decimal(str(election.step_3_dependent_credit)), Decimal("0"))
    # 4a-4b: de-annualize and add Step 4(c) extra withholding
    per_period = (annual_tax / pay_periods).quantize(_TWO, rounding=ROUND_HALF_UP)
    extra = Decimal(str(election.additional_withholding)).quantize(_TWO, rounding=ROUND_HALF_UP)
    return max(per_period + extra, Decimal("0"))


def _compute_illinois_withholding(
    taxable_gross: Decimal,
    election: NetPayTaxElectionInput,
    config: dict[str, Any],
) -> Decimal:
    if _is_exempt(election):
        return Decimal("0")

    if election.withholding_type == "flat_amount":
        return max(Decimal(str(election.additional_withholding)).quantize(_TWO, rounding=ROUND_HALF_UP), Decimal("0"))

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
    third_party_disbursements: list[ThirdPartyDisbursementInput] | None = None,
    third_party_names: dict[uuid.UUID, str] | None = None,
) -> NetPayResult:
    """Pure function — no DB access. Called by both the stateless and DB-backed paths."""
    pay_periods = PAY_PERIODS[pay_frequency]
    names = third_party_names or {}
    disbursements = third_party_disbursements or []

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

    tpd_lines: list[NetPayLineItem] = []
    for d in disbursements:
        amt = (
            d.amount
            if d.amount_type == "fixed"
            else (gross * d.amount).quantize(_TWO, rounding=ROUND_HALF_UP)
        )
        tpd_lines.append(NetPayLineItem(
            description=d.description,
            amount=amt,
            deduction_type=d.deduction_type,
            is_pretax=False,
            third_party_entity_id=d.third_party_entity_id,
            third_party_entity_name=names.get(d.third_party_entity_id),
        ))

    total_taxes = sum(l.amount for l in tax_lines) or Decimal("0")
    total_posttax = sum(l.amount for l in posttax_lines) or Decimal("0")
    total_tpd = sum(l.amount for l in tpd_lines) or Decimal("0")
    total_deductions = (total_pretax + total_taxes + total_posttax + total_tpd).quantize(_TWO, rounding=ROUND_HALF_UP)
    net = (gross - total_deductions).quantize(_TWO, rounding=ROUND_HALF_UP)

    return NetPayResult(
        gross_amount=gross,
        pretax_deductions=pretax_lines,
        taxable_gross=taxable_gross,
        tax_withholdings=tax_lines,
        posttax_deductions=posttax_lines,
        third_party_disbursements=tpd_lines,
        net_amount=net,
        total_pretax_deductions=total_pretax,
        total_taxes=total_taxes,
        total_posttax_deductions=total_posttax,
        total_third_party_disbursements=total_tpd,
        total_deductions=total_deductions,
        payment_date=payment_date,
        tax_year=payment_date.year,
        pay_frequency=pay_frequency,
    )


# ── Config loading ─────────────────────────────────────────────────────────────

async def _load_tax_configs(
    payment_date: date,
    session: AsyncSession,
) -> tuple[dict | None, dict | None]:
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


# ── DB-backed helpers ──────────────────────────────────────────────────────────

async def _load_active_orders(
    payment: BenefitPayment,
    session: AsyncSession,
) -> tuple[list[NetPayDeductionInput], list[ThirdPartyDisbursementInput]]:
    """Split active DeductionOrders into regular deductions vs. third-party disbursements."""
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

    deductions: list[NetPayDeductionInput] = []
    disbursements: list[ThirdPartyDisbursementInput] = []

    for order in orders:
        if order.third_party_entity_id is not None:
            disbursements.append(ThirdPartyDisbursementInput(
                third_party_entity_id=order.third_party_entity_id,
                description=_order_description(order),
                deduction_type=order.deduction_type,
                amount_type=order.amount_type,
                amount=Decimal(str(order.amount)),
            ))
        else:
            deductions.append(NetPayDeductionInput(
                description=_order_description(order),
                deduction_type=order.deduction_type,
                amount_type=order.amount_type,
                amount=Decimal(str(order.amount)),
                is_pretax=order.is_pretax,
            ))
    return deductions, disbursements


def _order_description(order: DeductionOrder) -> str:
    label = order.deduction_type.replace("_", " ").title()
    if order.deduction_code:
        label = f"{label} ({order.deduction_code})"
    return label


async def _build_tax_election_inputs(
    payment: BenefitPayment,
    session: AsyncSession,
) -> list[NetPayTaxElectionInput]:
    result = await session.execute(
        select(TaxWithholdingElection).where(
            TaxWithholdingElection.member_id == payment.member_id,
            TaxWithholdingElection.effective_date <= payment.payment_date,
            TaxWithholdingElection.superseded_date.is_(None),
        )
    )
    return [
        NetPayTaxElectionInput(
            jurisdiction=e.jurisdiction,
            filing_status=e.filing_status,
            withholding_type=e.withholding_type,
            additional_withholding=Decimal(str(e.additional_withholding)),
            step_2_multiple_jobs=e.step_2_multiple_jobs,
            step_3_dependent_credit=Decimal(str(e.step_3_dependent_credit)),
            step_4a_other_income=Decimal(str(e.step_4a_other_income)),
            step_4b_deductions=Decimal(str(e.step_4b_deductions)),
            exempt=e.exempt,
        )
        for e in result.scalars().all()
    ]


# ── DB-backed public functions ─────────────────────────────────────────────────

async def get_net_pay_preview(
    payment_id: uuid.UUID,
    session: AsyncSession,
) -> NetPayResult:
    """Read-only. Resolves member's standing orders + W-4P elections and computes net pay."""
    payment = await session.get(BenefitPayment, payment_id)
    if not payment:
        raise ValueError("Payment not found")

    deductions, disbursements = await _load_active_orders(payment, session)
    elections = await _build_tax_election_inputs(payment, session)
    federal_cfg, illinois_cfg = await _load_tax_configs(payment.payment_date, session)

    all_entity_ids = [d.third_party_entity_id for d in disbursements]
    names = await _resolve_third_party_names(all_entity_ids, session)

    return calculate_net_pay(
        gross=Decimal(str(payment.gross_amount)),
        deductions=deductions,
        tax_elections=elections,
        payment_date=payment.payment_date,
        pay_frequency="monthly",
        federal_tax_config=federal_cfg,
        illinois_tax_config=illinois_cfg,
        third_party_disbursements=disbursements,
        third_party_names=names,
    )


async def apply_net_pay(
    payment_id: uuid.UUID,
    session: AsyncSession,
    applied_by: uuid.UUID | None = None,
) -> NetPayResult:
    """Write path. Persists PaymentDeduction rows + updates net_amount.

    Idempotency guard: raises if deductions already exist on this payment.
    """
    payment = await session.get(BenefitPayment, payment_id)
    if not payment:
        raise ValueError("Payment not found")
    if payment.status == "issued":
        raise ValueError("Cannot apply net pay to an already-issued payment")

    existing = (await session.execute(
        select(PaymentDeduction.id).where(PaymentDeduction.payment_id == payment_id).limit(1)
    )).first()
    if existing:
        raise ValueError("Net pay has already been applied to this payment — reverse and reissue to correct")

    deductions, disbursements = await _load_active_orders(payment, session)
    elections = await _build_tax_election_inputs(payment, session)
    federal_cfg, illinois_cfg = await _load_tax_configs(payment.payment_date, session)

    all_entity_ids = [d.third_party_entity_id for d in disbursements]
    names = await _resolve_third_party_names(all_entity_ids, session)

    net_pay = calculate_net_pay(
        gross=Decimal(str(payment.gross_amount)),
        deductions=deductions,
        tax_elections=elections,
        payment_date=payment.payment_date,
        pay_frequency="monthly",
        federal_tax_config=federal_cfg,
        illinois_tax_config=illinois_cfg,
        third_party_disbursements=disbursements,
        third_party_names=names,
    )

    # Build order lookup for linking PaymentDeduction rows back to their source
    stmt = select(DeductionOrder).where(
        DeductionOrder.member_id == payment.member_id,
        DeductionOrder.effective_date <= payment.payment_date,
        or_(DeductionOrder.end_date.is_(None), DeductionOrder.end_date > payment.payment_date),
    )
    orders_by_type: dict[str, DeductionOrder] = {}
    for order in (await session.execute(stmt)).scalars().all():
        orders_by_type[order.deduction_type] = order

    all_lines = (
        net_pay.pretax_deductions
        + net_pay.tax_withholdings
        + net_pay.posttax_deductions
        + net_pay.third_party_disbursements
    )
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

    all_entity_ids = [d.third_party_entity_id for d in req.third_party_disbursements]
    names = await _resolve_third_party_names(all_entity_ids, session)

    return calculate_net_pay(
        gross=Decimal(str(req.gross_amount)),
        deductions=req.deductions,
        tax_elections=req.tax_elections,
        payment_date=req.payment_date,
        pay_frequency=req.pay_frequency,
        federal_tax_config=federal_cfg,
        illinois_tax_config=illinois_cfg,
        third_party_disbursements=req.third_party_disbursements,
        third_party_names=names,
    )

"""Named context providers for the document generation framework.

Each provider is an async function:
    provider(member_id, params, session) -> dict

The returned dict is merged into the template context. Provider names listed in
a DocumentTemplate's config_value["context"] are called automatically by the
assembler.

Adding a new provider:
    1. Write the async function below
    2. Register it in CONTEXT_PROVIDERS at the bottom of this file
    3. Reference it by name in any DocumentTemplate's config_value["context"]

No code changes are needed in the assembler or service when adding a provider.
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.address import MemberAddress
from app.models.beneficiary import Beneficiary
from app.models.billing import EmployerInvoice
from app.models.employer import Employer
from app.models.employment import EmploymentRecord
from app.models.member import Member
from app.models.payment import BenefitPayment, TaxWithholdingElection
from app.models.payroll import ContributionRecord
from app.models.retirement_case import RetirementCase
from app.models.service_credit import ServiceCreditEntry
from app.models.service_purchase import ServicePurchaseClaim
from app.services.config_service import ConfigNotFoundError, get_config


# ── Helpers ────────────────────────────────────────────────────────────────────

def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%B %d, %Y")


def _format_date(d: date | None) -> str:
    return d.strftime("%B %d, %Y") if d else ""


def _format_currency(amount: Decimal | float | None) -> str:
    if amount is None:
        return ""
    return f"${float(amount):,.2f}"


# ── Providers ─────────────────────────────────────────────────────────────────

async def _fund_info(member_id: uuid.UUID | None, params: dict, session: AsyncSession) -> dict:
    """Fund name and contact details from system_configurations."""
    try:
        cfg = await get_config("fund_info", date.today(), session)
        info = cfg.config_value
    except ConfigNotFoundError:
        info = {}
    return {
        "fund_name": info.get("name", "Pension Fund"),
        "fund_short_name": info.get("short_name", ""),
        "fund_address": info.get("address", ""),
        "fund_phone": info.get("phone", ""),
        "fund_website": info.get("website", ""),
        "fund_email": info.get("email", ""),
        "document_date": _today_str(),
    }


async def _member_info(member_id: uuid.UUID | None, params: dict, session: AsyncSession) -> dict:
    """Member demographics and primary mailing address."""
    if not member_id:
        return {}

    member = await session.get(Member, member_id)
    if not member:
        return {}

    # Primary mailing address (most recent, no end_date)
    addr_result = await session.execute(
        select(MemberAddress)
        .where(
            MemberAddress.member_id == member_id,
            MemberAddress.end_date.is_(None),
        )
        .order_by(MemberAddress.effective_date.desc())
        .limit(1)
    )
    address = addr_result.scalar_one_or_none()

    return {
        "member_number": member.member_number,
        "member_first_name": member.first_name,
        "member_last_name": member.last_name,
        "member_full_name": f"{member.first_name} {member.last_name}",
        "member_dob": _format_date(member.date_of_birth),
        "member_status": member.member_status or "",
        "member_certification_date": _format_date(member.certification_date),
        "address_line1": address.line1 if address else "",
        "address_line2": address.line2 if address else "",
        "address_city": address.city if address else "",
        "address_state": address.state if address else "",
        "address_zip": address.zip if address else "",
        "address_formatted": _format_address(address),
    }


def _format_address(address: MemberAddress | None) -> str:
    if not address:
        return ""
    parts = [address.line1]
    if address.line2:
        parts.append(address.line2)
    parts.append(f"{address.city}, {address.state} {address.zip}")
    return "\n".join(parts)


async def _employment_summary(member_id: uuid.UUID | None, params: dict, session: AsyncSession) -> dict:
    """Most recent active (or last) employment record with employer name."""
    if not member_id:
        return {}

    emp_result = await session.execute(
        select(EmploymentRecord, Employer)
        .join(Employer, EmploymentRecord.employer_id == Employer.id)
        .where(EmploymentRecord.member_id == member_id)
        .order_by(EmploymentRecord.hire_date.desc())
        .limit(1)
    )
    row = emp_result.first()
    if not row:
        return {}

    employment, employer = row
    return {
        "employer_name": employer.name,
        "employment_type": employment.employment_type,
        "hire_date": _format_date(employment.hire_date),
        "termination_date": _format_date(employment.termination_date),
        "percent_time": employment.percent_time,
        "is_active_employment": employment.termination_date is None,
    }


async def _service_credit_summary(member_id: uuid.UUID | None, params: dict, session: AsyncSession) -> dict:
    """Total non-voided service credit years."""
    if not member_id:
        return {}

    result = await session.execute(
        select(ServiceCreditEntry)
        .where(
            ServiceCreditEntry.member_id == member_id,
            ServiceCreditEntry.voided_at.is_(None),
        )
    )
    entries = result.scalars().all()
    total_years = sum(e.credit_years for e in entries)

    return {
        "total_service_credit_years": round(total_years, 4),
        "total_service_credit_display": f"{total_years:.2f} years",
    }


async def _contribution_summary(member_id: uuid.UUID | None, params: dict, session: AsyncSession) -> dict:
    """Sum of all non-voided employee and employer contributions."""
    if not member_id:
        return {}

    result = await session.execute(
        select(ContributionRecord)
        .where(
            ContributionRecord.member_id == member_id,
            ContributionRecord.voided_at.is_(None),
        )
    )
    records = result.scalars().all()
    employee_total = sum(Decimal(str(r.employee_contribution)) for r in records)
    employer_total = sum(Decimal(str(r.employer_contribution)) for r in records)

    return {
        "total_employee_contributions": _format_currency(employee_total),
        "total_employer_contributions": _format_currency(employer_total),
        "total_contributions": _format_currency(employee_total + employer_total),
    }


async def _benefit_estimate(member_id: uuid.UUID | None, params: dict, session: AsyncSession) -> dict:
    """Runs the benefit estimate engine. Requires retirement_date in params."""
    if not member_id:
        return {}

    retirement_date_raw = params.get("retirement_date")
    if not retirement_date_raw:
        return {"benefit_estimate_error": "retirement_date param required"}

    if isinstance(retirement_date_raw, str):
        retirement_date = date.fromisoformat(retirement_date_raw)
    else:
        retirement_date = retirement_date_raw

    # Import here to avoid circular at module load
    from app.services.benefit_estimate_service import get_estimate
    from app.schemas.benefit import BenefitOptionRequest

    sick_leave_days = int(params.get("sick_leave_days", 0))
    option_type = params.get("benefit_option_type", "single_life")
    beneficiary_age = params.get("beneficiary_age")

    benefit_option = BenefitOptionRequest(
        option_type=option_type,
        beneficiary_age=int(beneficiary_age) if beneficiary_age else None,
    )

    try:
        result = await get_estimate(
            member_id=member_id,
            retirement_date=retirement_date,
            session=session,
            sick_leave_days=sick_leave_days,
            benefit_option=benefit_option,
        )
        return {
            "estimate_retirement_date": _format_date(retirement_date),
            "estimate_monthly_benefit": _format_currency(result.monthly_benefit),
            "estimate_annual_benefit": _format_currency(result.monthly_benefit * 12),
            "estimate_formula_used": result.formula_used,
            "estimate_fae": _format_currency(result.final_average_earnings),
            "estimate_service_years": f"{result.total_service_credit:.2f}",
            "estimate_benefit_option": option_type.replace("_", " ").title(),
            "estimate_raw": result.model_dump(mode="json"),
        }
    except Exception as exc:
        return {"benefit_estimate_error": str(exc)}


async def _tax_elections(member_id: uuid.UUID | None, params: dict, session: AsyncSession) -> dict:
    """Current federal and state tax withholding elections."""
    if not member_id:
        return {}

    result = await session.execute(
        select(TaxWithholdingElection)
        .where(
            TaxWithholdingElection.member_id == member_id,
            TaxWithholdingElection.superseded_date.is_(None),
        )
        .order_by(TaxWithholdingElection.jurisdiction)
    )
    elections = result.scalars().all()

    elections_list = [
        {
            "jurisdiction": e.jurisdiction,
            "filing_status": e.filing_status.replace("_", " ").title(),
            "withholding_type": e.withholding_type,
            "additional_withholding": _format_currency(e.additional_withholding),
        }
        for e in elections
    ]
    return {"tax_elections": elections_list}


async def _beneficiaries(member_id: uuid.UUID | None, params: dict, session: AsyncSession) -> dict:
    """Primary and contingent beneficiaries."""
    if not member_id:
        return {}

    result = await session.execute(
        select(Beneficiary)
        .where(
            Beneficiary.member_id == member_id,
            Beneficiary.end_date.is_(None),
        )
        .order_by(Beneficiary.is_primary.desc(), Beneficiary.effective_date.desc())
    )
    beneficiaries = result.scalars().all()

    def _name(b: Beneficiary) -> str:
        if b.beneficiary_type == "individual":
            return f"{b.first_name or ''} {b.last_name or ''}".strip()
        return b.org_name or ""

    primary = [b for b in beneficiaries if b.is_primary]
    contingent = [b for b in beneficiaries if not b.is_primary]

    return {
        "primary_beneficiaries": [
            {"name": _name(b), "share_percent": b.share_percent, "type": b.beneficiary_type}
            for b in primary
        ],
        "contingent_beneficiaries": [
            {"name": _name(b), "share_percent": b.share_percent, "type": b.beneficiary_type}
            for b in contingent
        ],
    }


async def _retirement_case(member_id: uuid.UUID | None, params: dict, session: AsyncSession) -> dict:
    """Most recent approved or active retirement case for the member."""
    if not member_id:
        return {}
    result = await session.execute(
        select(RetirementCase)
        .where(
            RetirementCase.member_id == member_id,
            RetirementCase.status.in_(["approved", "active"]),
        )
        .order_by(RetirementCase.approved_at.desc())
        .limit(1)
    )
    case = result.scalar_one_or_none()
    if not case:
        return {"retirement_case_error": "No approved or active retirement case found"}
    annual = (
        _format_currency(Decimal(str(case.final_monthly_annuity)) * 12)
        if case.final_monthly_annuity
        else ""
    )
    return {
        "case_retirement_date": _format_date(case.retirement_date),
        "case_monthly_annuity": _format_currency(case.final_monthly_annuity),
        "case_annual_annuity": annual,
        "case_benefit_option": case.benefit_option_type.replace("_", " ").title(),
        "case_status": case.status,
        "case_approved_date": _format_date(case.approved_at.date() if case.approved_at else None),
        "case_first_payment_date": _format_date(case.first_payment_date),
    }


async def _service_purchase_claim(member_id: uuid.UUID | None, params: dict, session: AsyncSession) -> dict:
    """Service purchase claim loaded by claim_id param."""
    claim_id_raw = params.get("claim_id")
    if not claim_id_raw:
        return {"service_purchase_error": "claim_id param required"}
    try:
        claim_id = uuid.UUID(str(claim_id_raw))
    except ValueError:
        return {"service_purchase_error": "Invalid claim_id"}
    claim = await session.get(ServicePurchaseClaim, claim_id)
    if not claim:
        return {"service_purchase_error": "Claim not found"}
    return {
        "claim_purchase_type": claim.purchase_type.replace("_", " ").title(),
        "claim_credit_years": f"{float(claim.credit_years):.4f}",
        "claim_period_start": _format_date(claim.period_start),
        "claim_period_end": _format_date(claim.period_end),
        "claim_cost_total": _format_currency(claim.cost_total),
        "claim_cost_paid": _format_currency(claim.cost_paid),
        "claim_status": claim.status.replace("_", " ").title(),
        "claim_created_date": _format_date(claim.created_at.date()),
        "claim_approved_date": _format_date(claim.approved_at.date() if claim.approved_at else None),
        "claim_credit_grant_on": claim.credit_grant_on.replace("_", " ").title(),
        "claim_installment_allowed": claim.installment_allowed,
    }


async def _employer_invoice(member_id: uuid.UUID | None, params: dict, session: AsyncSession) -> dict:
    """Employer and invoice data loaded by invoice_id param. Works without a member_id."""
    invoice_id_raw = params.get("invoice_id")
    if not invoice_id_raw:
        return {"invoice_error": "invoice_id param required"}
    try:
        invoice_id = uuid.UUID(str(invoice_id_raw))
    except ValueError:
        return {"invoice_error": "Invalid invoice_id"}
    invoice = await session.get(EmployerInvoice, invoice_id)
    if not invoice:
        return {"invoice_error": "Invoice not found"}
    employer = await session.get(Employer, invoice.employer_id)
    balance = Decimal(str(invoice.amount_due)) - Decimal(str(invoice.amount_paid))
    return {
        "invoice_employer_name": employer.name if employer else "",
        "invoice_employer_code": employer.employer_code if employer else "",
        "invoice_id_short": str(invoice.id)[:8].upper(),
        "invoice_type": invoice.invoice_type.replace("_", " ").title(),
        "invoice_status": invoice.status,
        "invoice_period_start": _format_date(invoice.period_start),
        "invoice_period_end": _format_date(invoice.period_end),
        "invoice_amount_due": _format_currency(invoice.amount_due),
        "invoice_amount_paid": _format_currency(invoice.amount_paid),
        "invoice_amount_balance": _format_currency(balance),
        "invoice_interest_accrued": _format_currency(invoice.interest_accrued) if invoice.interest_accrued else "",
        "invoice_due_date": _format_date(invoice.due_date),
        "invoice_issued_date": _format_date(invoice.issued_at.date() if invoice.issued_at else None),
        "invoice_line_items": invoice.line_items or [],
        "invoice_note": invoice.note or "",
    }


async def _payment_detail(member_id: uuid.UUID | None, params: dict, session: AsyncSession) -> dict:
    """Payment and deduction detail loaded by payment_id param."""
    from sqlalchemy.orm import selectinload
    payment_id_raw = params.get("payment_id")
    if not payment_id_raw:
        return {"payment_error": "payment_id param required"}
    try:
        payment_id = uuid.UUID(str(payment_id_raw))
    except ValueError:
        return {"payment_error": "Invalid payment_id"}
    result = await session.execute(
        select(BenefitPayment)
        .where(BenefitPayment.id == payment_id)
        .options(selectinload(BenefitPayment.deductions))
    )
    payment = result.scalar_one_or_none()
    if not payment:
        return {"payment_error": "Payment not found"}
    deduction_list = [
        {"type": d.deduction_type.replace("_", " ").title(), "amount": _format_currency(d.amount)}
        for d in payment.deductions
    ]
    total_deductions = sum(Decimal(str(d.amount)) for d in payment.deductions)
    return {
        "payment_type": payment.payment_type.replace("_", " ").title(),
        "payment_status": payment.status,
        "payment_gross_amount": _format_currency(payment.gross_amount),
        "payment_net_amount": _format_currency(payment.net_amount),
        "payment_period_start": _format_date(payment.period_start),
        "payment_period_end": _format_date(payment.period_end),
        "payment_date": _format_date(payment.payment_date),
        "payment_method": (payment.payment_method or "").upper(),
        "payment_check_number": payment.check_number or "",
        "payment_deductions": deduction_list,
        "payment_total_deductions": _format_currency(total_deductions),
    }


# ── Registry ──────────────────────────────────────────────────────────────────

CONTEXT_PROVIDERS: dict = {
    "fund_info": _fund_info,
    "member_info": _member_info,
    "employment_summary": _employment_summary,
    "service_credit_summary": _service_credit_summary,
    "contribution_summary": _contribution_summary,
    "benefit_estimate": _benefit_estimate,
    "tax_elections": _tax_elections,
    "beneficiaries": _beneficiaries,
    "retirement_case": _retirement_case,
    "service_purchase_claim": _service_purchase_claim,
    "employer_invoice": _employer_invoice,
    "payment_detail": _payment_detail,
}

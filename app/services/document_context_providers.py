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
from app.models.employer import Employer
from app.models.employment import EmploymentRecord
from app.models.member import Member
from app.models.payroll import ContributionRecord
from app.models.service_credit import ServiceCreditEntry
from app.models.payment import TaxWithholdingElection
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
}

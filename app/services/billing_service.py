"""Employer billing — contribution rates, deficiency invoicing, supplemental charges.

Rate lookup uses a specificity hierarchy (most specific wins):
  employer_id + employment_type  → employer-specific type override
  employer_id only               → employer-wide override
  employment_type only           → fund-wide type default (e.g. police/fire)
  neither                        → fund-wide catch-all default

Deficiency invoices are generated from one or more PayrollReport IDs.
Supplemental invoices are created manually by staff.
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import EmployerContributionRate, EmployerInvoice, EmployerInvoicePayment
from app.models.payroll import PayrollReport


# ── Rate lookup ────────────────────────────────────────────────────────────────

async def get_effective_rate(
    employer_id: uuid.UUID,
    employment_type: str,
    as_of: date,
    session: AsyncSession,
) -> tuple[Decimal, Decimal] | None:
    """Return (employee_rate, employer_rate) for the most specific applicable rate row.

    Returns None if no rate is configured at all.
    """
    result = await session.execute(
        select(EmployerContributionRate)
        .where(
            or_(
                EmployerContributionRate.employer_id == employer_id,
                EmployerContributionRate.employer_id.is_(None),
            ),
            or_(
                EmployerContributionRate.employment_type == employment_type,
                EmployerContributionRate.employment_type.is_(None),
            ),
            EmployerContributionRate.effective_date <= as_of,
            or_(
                EmployerContributionRate.end_date.is_(None),
                EmployerContributionRate.end_date >= as_of,
            ),
        )
        .order_by(
            # Most specific first: employer_id set > null, employment_type set > null
            EmployerContributionRate.employer_id.is_(None),
            EmployerContributionRate.employment_type.is_(None),
            EmployerContributionRate.effective_date.desc(),
        )
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    return Decimal(str(row.employee_rate)), Decimal(str(row.employer_rate))


async def build_rate_cache(
    employer_id: uuid.UUID,
    as_of: date,
    session: AsyncSession,
) -> dict[str, tuple[Decimal, Decimal]]:
    """Pre-fetch applicable rates for all employment types for one employer.

    Returns a dict mapping employment_type → (employee_rate, employer_rate).
    Key '*' holds the fund-wide default (no employer, no type).
    Used by payroll_service to avoid per-row DB queries.
    """
    result = await session.execute(
        select(EmployerContributionRate)
        .where(
            or_(
                EmployerContributionRate.employer_id == employer_id,
                EmployerContributionRate.employer_id.is_(None),
            ),
            EmployerContributionRate.effective_date <= as_of,
            or_(
                EmployerContributionRate.end_date.is_(None),
                EmployerContributionRate.end_date >= as_of,
            ),
        )
        .order_by(
            EmployerContributionRate.employer_id.is_(None),
            EmployerContributionRate.employment_type.is_(None),
            EmployerContributionRate.effective_date.desc(),
        )
    )
    rows = result.scalars().all()

    # Build cache: most-specific entry per key wins (already sorted most-specific first)
    cache: dict[str, tuple[Decimal, Decimal]] = {}
    for row in rows:
        key = row.employment_type or "*"
        if key not in cache:
            cache[key] = (Decimal(str(row.employee_rate)), Decimal(str(row.employer_rate)))
    return cache


def lookup_rate_from_cache(
    cache: dict[str, tuple[Decimal, Decimal]],
    employment_type: str,
) -> tuple[Decimal, Decimal] | None:
    """Resolve rate for an employment_type from a pre-built cache.

    Falls back from type-specific → fund-wide default ('*').
    """
    return cache.get(employment_type) or cache.get("*")


def check_contribution_variance(
    gross: Decimal,
    submitted_employee: Decimal,
    submitted_employer: Decimal,
    employee_rate: Decimal,
    employer_rate: Decimal,
) -> list[str]:
    """Return rate-variance warnings for a single row. Empty list = no issues."""
    warnings = []
    expected_employee = (gross * employee_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    expected_employer = (gross * employer_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if submitted_employee < expected_employee:
        shortfall = expected_employee - submitted_employee
        warnings.append(
            f"Employee contribution ${submitted_employee} is ${shortfall} short of "
            f"expected ${expected_employee} ({employee_rate:.4%} × ${gross})"
        )
    if submitted_employer < expected_employer:
        shortfall = expected_employer - submitted_employer
        warnings.append(
            f"Employer contribution ${submitted_employer} is ${shortfall} short of "
            f"expected ${expected_employer} ({employer_rate:.4%} × ${gross})"
        )
    return warnings


# ── Deficiency calc (stateless) ────────────────────────────────────────────────

async def calculate_deficiency(
    payroll_report_ids: list[uuid.UUID],
    employer_id: uuid.UUID,
    session: AsyncSession,
) -> dict:
    """Compare submitted contributions against authoritative rates for given reports.

    Returns a breakdown dict suitable for invoice line_items. No DB write.
    """
    if not payroll_report_ids:
        raise ValueError("At least one payroll_report_id required")

    from sqlalchemy.orm import selectinload
    result = await session.execute(
        select(PayrollReport)
        .where(
            PayrollReport.id.in_(payroll_report_ids),
            PayrollReport.employer_id == employer_id,
        )
        .options(selectinload(PayrollReport.rows))
    )
    reports = result.scalars().all()
    if len(reports) != len(payroll_report_ids):
        found = {str(r.id) for r in reports}
        missing = [str(rid) for rid in payroll_report_ids if str(rid) not in found]
        raise ValueError(f"Reports not found or don't belong to employer: {missing}")

    total_employee_deficiency = Decimal("0")
    total_employer_deficiency = Decimal("0")
    row_details = []

    for report in reports:
        # Build rate cache using the report's period_end
        period_end = report.rows[0].period_end if report.rows else date.today()
        rate_cache = await build_rate_cache(employer_id, period_end, session)

        for row in report.rows:
            if row.status not in ("applied", "flagged"):
                continue
            # Look up employment type via employment record
            from app.models.employment import EmploymentRecord
            emp = await session.get(EmploymentRecord, row.employment_id) if row.employment_id else None
            emp_type = emp.employment_type if emp else None
            rates = lookup_rate_from_cache(rate_cache, emp_type or "") if emp_type else None
            if not rates:
                continue

            employee_rate, employer_rate = rates
            gross = Decimal(str(row.gross_earnings))
            submitted_emp = Decimal(str(row.employee_contribution))
            submitted_er = Decimal(str(row.employer_contribution))
            expected_emp = (gross * employee_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            expected_er = (gross * employer_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            emp_deficiency = max(Decimal("0"), expected_emp - submitted_emp)
            er_deficiency = max(Decimal("0"), expected_er - submitted_er)

            if emp_deficiency > 0 or er_deficiency > 0:
                total_employee_deficiency += emp_deficiency
                total_employer_deficiency += er_deficiency
                row_details.append({
                    "report_id": str(report.id),
                    "member_number": row.member_number,
                    "period_start": str(row.period_start),
                    "period_end": str(row.period_end),
                    "gross": str(gross),
                    "employee_deficiency": str(emp_deficiency),
                    "employer_deficiency": str(er_deficiency),
                })

    total = total_employee_deficiency + total_employer_deficiency
    return {
        "total_deficiency": str(total),
        "employee_deficiency": str(total_employee_deficiency),
        "employer_deficiency": str(total_employer_deficiency),
        "row_count": len(row_details),
        "rows": row_details,
        "report_ids": [str(rid) for rid in payroll_report_ids],
    }


# ── Invoice CRUD ───────────────────────────────────────────────────────────────

async def create_deficiency_invoice(
    employer_id: uuid.UUID,
    payroll_report_ids: list[uuid.UUID],
    due_date: date,
    session: AsyncSession,
    note: str | None = None,
    created_by: uuid.UUID | None = None,
) -> EmployerInvoice:
    deficiency = await calculate_deficiency(payroll_report_ids, employer_id, session)
    total = Decimal(deficiency["total_deficiency"])
    if total <= 0:
        raise ValueError("No deficiency found for the specified payroll reports")

    # Determine period range from reports
    from sqlalchemy.orm import selectinload
    result = await session.execute(
        select(PayrollReport)
        .where(PayrollReport.id.in_(payroll_report_ids))
        .options(selectinload(PayrollReport.rows))
    )
    reports = result.scalars().all()
    all_starts = [r.rows[0].period_start for r in reports if r.rows]
    all_ends = [r.rows[0].period_end for r in reports if r.rows]

    line_items = [
        {"description": "Employee contribution deficiency", "amount": deficiency["employee_deficiency"]},
        {"description": "Employer contribution deficiency", "amount": deficiency["employer_deficiency"]},
    ]

    invoice = EmployerInvoice(
        employer_id=employer_id,
        invoice_type="deficiency",
        status="draft",
        period_start=min(all_starts) if all_starts else None,
        period_end=max(all_ends) if all_ends else None,
        amount_due=float(total),
        due_date=due_date,
        line_items=line_items,
        source_report_ids=[str(rid) for rid in payroll_report_ids],
        note=note,
        created_by=created_by,
    )
    session.add(invoice)
    await session.flush()
    return invoice


async def create_supplemental_invoice(
    employer_id: uuid.UUID,
    amount_due: Decimal,
    due_date: date,
    line_items: list[dict],
    session: AsyncSession,
    note: str | None = None,
    created_by: uuid.UUID | None = None,
) -> EmployerInvoice:
    invoice = EmployerInvoice(
        employer_id=employer_id,
        invoice_type="supplemental",
        status="draft",
        amount_due=float(amount_due),
        due_date=due_date,
        line_items=line_items,
        source_report_ids=[],
        note=note,
        created_by=created_by,
    )
    session.add(invoice)
    await session.flush()
    return invoice


async def get_invoice(invoice_id: uuid.UUID, session: AsyncSession) -> EmployerInvoice | None:
    return await session.get(EmployerInvoice, invoice_id)


async def list_invoices(
    employer_id: uuid.UUID,
    session: AsyncSession,
    status: str | None = None,
) -> list[EmployerInvoice]:
    stmt = (
        select(EmployerInvoice)
        .where(EmployerInvoice.employer_id == employer_id)
        .order_by(EmployerInvoice.created_at.desc())
    )
    if status:
        stmt = stmt.where(EmployerInvoice.status == status)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def issue_invoice(invoice: EmployerInvoice, session: AsyncSession) -> EmployerInvoice:
    if invoice.status != "draft":
        raise ValueError(f"Cannot issue invoice in status '{invoice.status}' — must be 'draft'")
    invoice.status = "issued"
    invoice.issued_at = datetime.now(timezone.utc)
    await session.flush()
    return invoice


async def record_payment(
    invoice: EmployerInvoice,
    amount: Decimal,
    payment_date: date,
    payment_method: str,
    session: AsyncSession,
    reference_number: str | None = None,
    received_by: uuid.UUID | None = None,
) -> EmployerInvoicePayment:
    if invoice.status in ("paid", "voided"):
        raise ValueError(f"Cannot record payment on invoice in status '{invoice.status}'")

    payment = EmployerInvoicePayment(
        invoice_id=invoice.id,
        amount=float(amount),
        payment_date=payment_date,
        payment_method=payment_method,
        reference_number=reference_number,
        received_by=received_by,
    )
    session.add(payment)

    new_paid = (Decimal(str(invoice.amount_paid)) + amount).quantize(Decimal("0.01"))
    invoice.amount_paid = float(new_paid)

    if new_paid >= Decimal(str(invoice.amount_due)):
        invoice.status = "paid"
        invoice.paid_at = datetime.now(timezone.utc)

    await session.flush()
    return payment


async def void_invoice(
    invoice: EmployerInvoice,
    void_reason: str,
    session: AsyncSession,
    voided_by: uuid.UUID | None = None,
) -> EmployerInvoice:
    if invoice.status == "paid":
        raise ValueError("Cannot void a paid invoice — create a supplemental credit instead")
    invoice.status = "voided"
    invoice.voided_at = datetime.now(timezone.utc)
    invoice.voided_by = voided_by
    invoice.void_reason = void_reason
    await session.flush()
    return invoice


# ── Rate management ────────────────────────────────────────────────────────────

async def create_rate(
    employee_rate: Decimal,
    employer_rate: Decimal,
    effective_date: date,
    session: AsyncSession,
    employer_id: uuid.UUID | None = None,
    employment_type: str | None = None,
    end_date: date | None = None,
    note: str | None = None,
    created_by: uuid.UUID | None = None,
) -> EmployerContributionRate:
    rate = EmployerContributionRate(
        employer_id=employer_id,
        employment_type=employment_type,
        employee_rate=float(employee_rate),
        employer_rate=float(employer_rate),
        effective_date=effective_date,
        end_date=end_date,
        note=note,
        created_by=created_by,
    )
    session.add(rate)
    await session.flush()
    return rate


async def list_rates(
    session: AsyncSession,
    employer_id: uuid.UUID | None = None,
) -> list[EmployerContributionRate]:
    stmt = select(EmployerContributionRate).order_by(
        EmployerContributionRate.effective_date.desc(),
        EmployerContributionRate.employer_id.is_(None),
        EmployerContributionRate.employment_type.is_(None),
    )
    if employer_id:
        stmt = stmt.where(
            or_(
                EmployerContributionRate.employer_id == employer_id,
                EmployerContributionRate.employer_id.is_(None),
            )
        )
    result = await session.execute(stmt)
    return list(result.scalars().all())

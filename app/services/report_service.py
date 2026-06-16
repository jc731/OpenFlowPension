"""Aggregation queries backing the /reports endpoints.

Each function runs a single async query (or a small set) and returns a typed
report schema. No business logic lives here — only read-only SQL aggregation.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
import uuid

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import EmployerInvoice
from app.models.employer import Employer
from app.models.employment import EmploymentRecord
from app.models.member import Member
from app.models.payroll import ContributionRecord
from app.models.retirement_case import RetirementCase
from app.schemas.reports import (
    AnnuitantReport,
    AnnuitantRow,
    AnnuitantSummary,
    ContributionReconciliationReport,
    ContributionReconciliationRow,
    ContributionReconciliationSummary,
    DelinquencyReport,
    DelinquencyRow,
    DelinquencySummary,
    MembershipCountReport,
    MembershipCountRow,
    MembershipCountSummary,
)


# ── RP01: Contribution Reconciliation ─────────────────────────────────────────

async def contribution_reconciliation(
    period_start: date,
    period_end: date,
    session: AsyncSession,
    employer_id: uuid.UUID | None = None,
) -> ContributionReconciliationReport:
    stmt = (
        select(
            Employer.id.label("employer_id"),
            Employer.name.label("employer_name"),
            Employer.employer_code.label("employer_code"),
            func.sum(ContributionRecord.employee_contribution).label("total_employee"),
            func.sum(ContributionRecord.employer_contribution).label("total_employer"),
            func.count(ContributionRecord.id).label("record_count"),
        )
        .join(EmploymentRecord, ContributionRecord.employment_id == EmploymentRecord.id)
        .join(Employer, EmploymentRecord.employer_id == Employer.id)
        .where(
            ContributionRecord.employment_id.is_not(None),
            ContributionRecord.voided_at.is_(None),
            ContributionRecord.period_end >= period_start,
            ContributionRecord.period_start <= period_end,
        )
        .group_by(Employer.id, Employer.name, Employer.employer_code)
        .order_by(Employer.name)
    )
    if employer_id:
        stmt = stmt.where(EmploymentRecord.employer_id == employer_id)

    result = await session.execute(stmt)
    rows = []
    for r in result.fetchall():
        emp_contrib = Decimal(str(r.total_employee or 0))
        er_contrib = Decimal(str(r.total_employer or 0))
        rows.append(ContributionReconciliationRow(
            employer_id=r.employer_id,
            employer_name=r.employer_name,
            employer_code=r.employer_code,
            total_employee_contributions=emp_contrib,
            total_employer_contributions=er_contrib,
            total_contributions=emp_contrib + er_contrib,
            record_count=r.record_count,
        ))

    total_ee = sum(r.total_employee_contributions for r in rows)
    total_er = sum(r.total_employer_contributions for r in rows)

    return ContributionReconciliationReport(
        generated_at=datetime.now(timezone.utc),
        parameters={
            "period_start": str(period_start),
            "period_end": str(period_end),
            "employer_id": str(employer_id) if employer_id else None,
        },
        summary=ContributionReconciliationSummary(
            total_employee_contributions=total_ee,
            total_employer_contributions=total_er,
            total_contributions=total_ee + total_er,
            employer_count=len(rows),
            record_count=sum(r.record_count for r in rows),
        ),
        rows=rows,
    )


# ── RP02: Delinquency ─────────────────────────────────────────────────────────

async def delinquency(
    as_of: date,
    session: AsyncSession,
) -> DelinquencyReport:
    stmt = (
        select(
            Employer.id.label("employer_id"),
            Employer.name.label("employer_name"),
            Employer.employer_code.label("employer_code"),
            EmployerInvoice.id.label("invoice_id"),
            EmployerInvoice.invoice_type,
            EmployerInvoice.status.label("invoice_status"),
            EmployerInvoice.due_date,
            EmployerInvoice.amount_due,
            EmployerInvoice.amount_paid,
        )
        .join(Employer, EmployerInvoice.employer_id == Employer.id)
        .where(
            EmployerInvoice.status.in_(["issued", "overdue"]),
            EmployerInvoice.due_date < as_of,
            EmployerInvoice.amount_paid < EmployerInvoice.amount_due,
        )
        .order_by(EmployerInvoice.due_date, Employer.name)
    )

    result = await session.execute(stmt)
    rows = []
    for r in result.fetchall():
        amount_due = Decimal(str(r.amount_due))
        amount_paid = Decimal(str(r.amount_paid))
        outstanding = (amount_due - amount_paid).quantize(Decimal("0.01"))
        days_overdue = (as_of - r.due_date).days
        rows.append(DelinquencyRow(
            employer_id=r.employer_id,
            employer_name=r.employer_name,
            employer_code=r.employer_code,
            invoice_id=r.invoice_id,
            invoice_type=r.invoice_type,
            invoice_status=r.invoice_status,
            due_date=r.due_date,
            amount_due=amount_due,
            amount_paid=amount_paid,
            outstanding=outstanding,
            days_overdue=days_overdue,
        ))

    total_outstanding = sum(r.outstanding for r in rows)
    employer_ids = {r.employer_id for r in rows}

    return DelinquencyReport(
        generated_at=datetime.now(timezone.utc),
        parameters={"as_of": str(as_of)},
        summary=DelinquencySummary(
            total_outstanding=total_outstanding,
            invoice_count=len(rows),
            employer_count=len(employer_ids),
        ),
        rows=rows,
    )


# ── RP03: Membership Counts ───────────────────────────────────────────────────

async def membership_counts(
    session: AsyncSession,
) -> MembershipCountReport:
    stmt = (
        select(Member.member_status, func.count(Member.id).label("count"))
        .group_by(Member.member_status)
        .order_by(Member.member_status)
    )
    result = await session.execute(stmt)
    rows = [
        MembershipCountRow(status=r.member_status, count=r.count)
        for r in result.fetchall()
    ]
    total = sum(r.count for r in rows)

    return MembershipCountReport(
        generated_at=datetime.now(timezone.utc),
        parameters={},
        summary=MembershipCountSummary(total_members=total),
        rows=rows,
    )


# ── RP04: Annuitant Export ────────────────────────────────────────────────────

async def annuitants(
    session: AsyncSession,
) -> AnnuitantReport:
    # Subquery: one active/approved case per member (there should be at most one by invariant)
    active_case = (
        select(RetirementCase)
        .where(RetirementCase.status.in_(["approved", "active"]))
        .subquery()
    )

    stmt = (
        select(
            Member.id.label("member_id"),
            Member.member_number,
            Member.first_name,
            Member.last_name,
            Member.member_status,
            active_case.c.id.label("case_id"),
            active_case.c.status.label("case_status"),
            active_case.c.retirement_date,
            active_case.c.benefit_option_type,
            active_case.c.final_monthly_annuity,
            active_case.c.first_payment_date,
        )
        .outerjoin(active_case, active_case.c.member_id == Member.id)
        .where(Member.member_status.in_(["annuitant", "retired"]))
        .order_by(Member.last_name, Member.first_name)
    )

    result = await session.execute(stmt)
    rows = []
    for r in result.fetchall():
        monthly = Decimal(str(r.final_monthly_annuity)) if r.final_monthly_annuity is not None else None
        rows.append(AnnuitantRow(
            member_id=r.member_id,
            member_number=r.member_number,
            first_name=r.first_name,
            last_name=r.last_name,
            member_status=r.member_status,
            retirement_date=r.retirement_date,
            benefit_option_type=r.benefit_option_type,
            case_status=r.case_status,
            final_monthly_annuity=monthly,
            first_payment_date=r.first_payment_date,
            payments_started=r.first_payment_date is not None,
        ))

    with_case = sum(1 for r in rows if r.final_monthly_annuity is not None)
    total_monthly = sum(r.final_monthly_annuity for r in rows if r.final_monthly_annuity is not None)

    return AnnuitantReport(
        generated_at=datetime.now(timezone.utc),
        parameters={},
        summary=AnnuitantSummary(
            total_annuitants=len(rows),
            annuitants_with_approved_case=with_case,
            total_monthly_outlay=total_monthly,
        ),
        rows=rows,
    )

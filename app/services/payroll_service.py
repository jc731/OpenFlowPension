"""Payroll ingestion service.

Two intake paths share one processing engine:
  ingest_json  — accepts a PayrollReportCreate body
  ingest_csv   — parses CSV text, then calls ingest_json internally

Processing is synchronous and partial: valid rows are applied, bad rows are
marked error/skipped and counted. The report always transitions to "completed"
regardless of how many rows errored.

Each applied row fans out to:
  ServiceCreditEntry  — append-only ledger, links to accrual rule config
  ContributionRecord  — append-only C&I ledger
"""

import csv
import io
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.employment import EmploymentRecord
from app.models.member import Member
from app.models.payroll import ContributionRecord, PayrollReport, PayrollReportRow
from app.models.service_credit import ServiceCreditEntry
from app.schemas.payroll import PayrollReportCreate, PayrollRowInput
from app.services.config_service import ConfigNotFoundError, get_config


# ── CSV expected columns ───────────────────────────────────────────────────────

_CSV_COLUMNS = {
    "member_number",
    "period_start",
    "period_end",
    "gross_earnings",
    "employee_contribution",
    "employer_contribution",
    "days_worked",
}


# ── Pure helpers ───────────────────────────────────────────────────────────────

def parse_csv(csv_text: str) -> list[PayrollRowInput]:
    """Parse CSV text into PayrollRowInput objects. Raises ValueError on bad input."""
    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    if reader.fieldnames is None:
        raise ValueError("CSV has no header row")

    missing = _CSV_COLUMNS - {f.strip() for f in reader.fieldnames}
    if missing:
        raise ValueError(f"CSV missing required columns: {sorted(missing)}")

    rows: list[PayrollRowInput] = []
    for i, raw_row in enumerate(reader, start=2):  # row 1 = header
        try:
            rows.append(PayrollRowInput(
                member_number=raw_row["member_number"].strip(),
                period_start=date.fromisoformat(raw_row["period_start"].strip()),
                period_end=date.fromisoformat(raw_row["period_end"].strip()),
                gross_earnings=Decimal(raw_row["gross_earnings"].strip()),
                employee_contribution=Decimal(raw_row["employee_contribution"].strip()),
                employer_contribution=Decimal(raw_row["employer_contribution"].strip()),
                days_worked=int(raw_row["days_worked"].strip()),
            ))
        except (KeyError, ValueError) as exc:
            raise ValueError(f"CSV row {i}: {exc}") from exc
    return rows


def count_months_in_period(period_start: date, period_end: date) -> int:
    """Return the count of distinct calendar months spanned by [period_start, period_end]."""
    count = 0
    year, month = period_start.year, period_start.month
    end_year, end_month = period_end.year, period_end.month
    while (year, month) <= (end_year, end_month):
        count += 1
        month += 1
        if month > 12:
            month = 1
            year += 1
    return count


def compute_service_credit_years(
    accrual_rule: str,
    period_start: date,
    period_end: date,
    days_worked: int,
    percent_time: float,
) -> float:
    """Compute service credit years for a single payroll period."""
    if days_worked == 0:
        return 0.0
    months = count_months_in_period(period_start, period_end)
    if accrual_rule == "monthly_floor":
        return months / 12.0
    if accrual_rule == "proportional_percent_time":
        return (months / 12.0) * (percent_time / 100.0)
    raise ValueError(f"Unknown accrual rule: {accrual_rule!r}")


# ── Row processor ──────────────────────────────────────────────────────────────

async def _process_row(row: PayrollReportRow, employer_id: uuid.UUID, session: AsyncSession) -> None:
    # 1. Member lookup
    member_result = await session.execute(
        select(Member).where(Member.member_number == row.member_number)
    )
    member = member_result.scalar_one_or_none()
    if member is None:
        row.status = "error"
        row.error_message = f"Member not found: {row.member_number!r}"
        return

    row.member_id = member.id

    # 2. Active employment at this employer
    emp_result = await session.execute(
        select(EmploymentRecord)
        .where(
            EmploymentRecord.member_id == member.id,
            EmploymentRecord.employer_id == employer_id,
            or_(
                EmploymentRecord.termination_date.is_(None),
                EmploymentRecord.termination_date >= row.period_start,
            ),
        )
        .order_by(EmploymentRecord.hire_date.desc())
        .limit(1)
    )
    employment = emp_result.scalar_one_or_none()
    if employment is None:
        row.status = "error"
        row.error_message = f"No active employment for {row.member_number!r} at this employer"
        return

    row.employment_id = employment.id

    # 3. Duplicate check
    dup = await session.execute(
        select(ContributionRecord).where(
            ContributionRecord.member_id == member.id,
            ContributionRecord.employment_id == employment.id,
            ContributionRecord.period_start == row.period_start,
            ContributionRecord.period_end == row.period_end,
            ContributionRecord.voided_at.is_(None),
        ).limit(1)
    )
    if dup.scalar_one_or_none() is not None:
        row.status = "skipped"
        row.error_message = (
            f"Duplicate: contribution already posted for {row.period_start}–{row.period_end}"
        )
        return

    # 4. Accrual rule
    try:
        config = await get_config("service_credit_accrual_rule", row.period_end, session)
    except ConfigNotFoundError:
        row.status = "error"
        row.error_message = "No service credit accrual rule configured as of period_end"
        return

    accrual_rule: str = config.config_value["rule"]
    credit_years = compute_service_credit_years(
        accrual_rule,
        row.period_start,
        row.period_end,
        row.days_worked,
        float(employment.percent_time),
    )

    # 5. Service credit entry (skip if zero — e.g. days_worked == 0)
    if credit_years > 0:
        sc = ServiceCreditEntry(
            member_id=member.id,
            employment_id=employment.id,
            entry_type="payroll",
            credit_days=float(row.days_worked),
            credit_years=credit_years,
            period_start=row.period_start,
            period_end=row.period_end,
            accrual_rule_config_id=config.id,
            source_document_id=row.payroll_report_id,
        )
        session.add(sc)

    # 6. Contribution record
    contribution = ContributionRecord(
        member_id=member.id,
        employment_id=employment.id,
        payroll_report_row_id=row.id,
        period_start=row.period_start,
        period_end=row.period_end,
        employee_contribution=float(row.employee_contribution),
        employer_contribution=float(row.employer_contribution),
        contribution_type="normal",
    )
    session.add(contribution)

    row.status = "applied"


# ── Entry points ───────────────────────────────────────────────────────────────

async def ingest_json(
    employer_id: uuid.UUID,
    data: PayrollReportCreate,
    session: AsyncSession,
    submitted_by: uuid.UUID | None = None,
    filename: str | None = None,
) -> PayrollReport:
    report = PayrollReport(
        employer_id=employer_id,
        source_format="json",
        source_filename=filename,
        status="processing",
        row_count=len(data.rows),
        submitted_by=submitted_by,
        note=data.note,
    )
    session.add(report)
    await session.flush()

    row_statuses: list[str] = []
    for row_input in data.rows:
        row = PayrollReportRow(
            payroll_report_id=report.id,
            member_number=row_input.member_number,
            period_start=row_input.period_start,
            period_end=row_input.period_end,
            gross_earnings=float(row_input.gross_earnings),
            employee_contribution=float(row_input.employee_contribution),
            employer_contribution=float(row_input.employer_contribution),
            days_worked=row_input.days_worked,
            raw_data=row_input.model_dump(mode="json"),
        )
        session.add(row)
        await session.flush()
        await _process_row(row, employer_id, session)
        row_statuses.append(row.status)

    report.processed_count = row_statuses.count("applied")
    report.error_count = row_statuses.count("error")
    report.skipped_count = row_statuses.count("skipped")
    report.status = "completed"
    await session.refresh(report, ["rows"])
    return report


async def ingest_csv(
    employer_id: uuid.UUID,
    csv_text: str,
    filename: str,
    session: AsyncSession,
    submitted_by: uuid.UUID | None = None,
) -> PayrollReport:
    rows = parse_csv(csv_text)
    data = PayrollReportCreate(rows=rows)
    report = await ingest_json(employer_id, data, session, submitted_by=submitted_by, filename=filename)
    report.source_format = "csv"
    return report


# ── Queries ────────────────────────────────────────────────────────────────────

async def get_payroll_report(report_id: uuid.UUID, session: AsyncSession) -> PayrollReport | None:
    result = await session.execute(
        select(PayrollReport)
        .where(PayrollReport.id == report_id)
        .options(selectinload(PayrollReport.rows))
    )
    return result.scalar_one_or_none()


async def list_payroll_reports(employer_id: uuid.UUID, session: AsyncSession) -> list[PayrollReport]:
    result = await session.execute(
        select(PayrollReport)
        .where(PayrollReport.employer_id == employer_id)
        .order_by(PayrollReport.created_at.desc())
        .options(selectinload(PayrollReport.rows))
    )
    return list(result.scalars().all())


async def list_all_payroll_reports(
    session: AsyncSession,
    employer_id: uuid.UUID | None = None,
    limit: int = 100,
) -> list[PayrollReport]:
    """List reports across all employers (admin/LOB view). No rows loaded — use get_payroll_report for detail."""
    stmt = select(PayrollReport).order_by(PayrollReport.created_at.desc()).limit(limit)
    if employer_id:
        stmt = stmt.where(PayrollReport.employer_id == employer_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())

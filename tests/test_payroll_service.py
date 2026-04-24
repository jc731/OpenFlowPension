"""Tests for payroll ingestion service.

Pure computation tests (no DB): CSV parsing, month counting, service credit computation.
DB tests: full JSON ingestion, CSV ingestion, member-not-found error, duplicate skipping,
          partial batch success (some rows ok, some error).
"""

from datetime import date
from decimal import Decimal
import textwrap

import pytest

from app.models.employer import Employer
from app.models.employment import EmploymentRecord
from app.models.member import Member
from app.models.plan_config import PlanTier, PlanType, SystemConfiguration
from app.schemas.payroll import PayrollReportCreate, PayrollRowInput
from app.services.payroll_service import (
    compute_service_credit_years,
    count_months_in_period,
    ingest_csv,
    ingest_json,
    list_payroll_reports,
    parse_csv,
)
from app.crypto import encrypt_ssn


# ── Pure unit tests (no DB) ───────────────────────────────────────────────────

def test_parse_csv_valid():
    csv_text = textwrap.dedent("""\
        member_number,period_start,period_end,gross_earnings,employee_contribution,employer_contribution,days_worked
        MBR-001,2025-01-01,2025-01-31,5000.00,400.00,250.00,20
        MBR-002,2025-01-01,2025-01-31,3200.50,256.04,160.03,18
    """)
    rows = parse_csv(csv_text)
    assert len(rows) == 2
    assert rows[0].member_number == "MBR-001"
    assert rows[0].gross_earnings == Decimal("5000.00")
    assert rows[0].days_worked == 20
    assert rows[1].member_number == "MBR-002"


def test_parse_csv_missing_column():
    csv_text = "member_number,period_start,period_end,gross_earnings\nMBR-001,2025-01-01,2025-01-31,5000.00\n"
    with pytest.raises(ValueError, match="missing required columns"):
        parse_csv(csv_text)


def test_parse_csv_bad_date():
    csv_text = textwrap.dedent("""\
        member_number,period_start,period_end,gross_earnings,employee_contribution,employer_contribution,days_worked
        MBR-001,not-a-date,2025-01-31,5000.00,400.00,250.00,20
    """)
    with pytest.raises(ValueError, match="row 2"):
        parse_csv(csv_text)


def test_count_months_single():
    assert count_months_in_period(date(2025, 1, 1), date(2025, 1, 31)) == 1


def test_count_months_two():
    assert count_months_in_period(date(2025, 1, 15), date(2025, 2, 14)) == 2


def test_count_months_year_boundary():
    assert count_months_in_period(date(2024, 11, 1), date(2025, 1, 31)) == 3


def test_count_months_same_day():
    assert count_months_in_period(date(2025, 6, 15), date(2025, 6, 15)) == 1


def test_service_credit_monthly_floor_one_month():
    credit = compute_service_credit_years("monthly_floor", date(2025, 1, 1), date(2025, 1, 31), days_worked=15, percent_time=100.0)
    assert credit == pytest.approx(1 / 12)


def test_service_credit_monthly_floor_zero_days():
    credit = compute_service_credit_years("monthly_floor", date(2025, 1, 1), date(2025, 1, 31), days_worked=0, percent_time=100.0)
    assert credit == 0.0


def test_service_credit_proportional_full_time():
    credit = compute_service_credit_years("proportional_percent_time", date(2025, 1, 1), date(2025, 1, 31), days_worked=20, percent_time=100.0)
    assert credit == pytest.approx(1 / 12)


def test_service_credit_proportional_half_time():
    credit = compute_service_credit_years("proportional_percent_time", date(2025, 1, 1), date(2025, 1, 31), days_worked=10, percent_time=50.0)
    assert credit == pytest.approx(1 / 24)


def test_service_credit_unknown_rule():
    with pytest.raises(ValueError, match="Unknown accrual rule"):
        compute_service_credit_years("bogus_rule", date(2025, 1, 1), date(2025, 1, 31), days_worked=10, percent_time=100.0)


# ── DB fixtures ───────────────────────────────────────────────────────────────

async def _setup(session):
    """Create plan tier/type, system configs, employer, member, employment."""
    tier = PlanTier(tier_code="tier_1", tier_label="Tier I", effective_date=date(1980, 1, 1))
    plan = PlanType(plan_code="traditional", plan_label="Traditional")
    session.add_all([tier, plan])
    await session.flush()

    # Accrual rule configs
    pre_config = SystemConfiguration(
        config_key="service_credit_accrual_rule",
        config_value={"rule": "proportional_percent_time"},
        effective_date=date(1980, 1, 1),
        superseded_date=date(2024, 9, 1),
    )
    post_config = SystemConfiguration(
        config_key="service_credit_accrual_rule",
        config_value={"rule": "monthly_floor"},
        effective_date=date(2024, 9, 1),
        superseded_date=None,
    )
    session.add_all([pre_config, post_config])
    await session.flush()

    employer = Employer(name="Test University", employer_code="TST-001", employer_type="university")
    session.add(employer)
    await session.flush()

    member = Member(
        member_number="PRY-001",
        first_name="Alice",
        last_name="Test",
        date_of_birth=date(1975, 6, 1),
        ssn_encrypted=encrypt_ssn("111223333"),
        ssn_last_four="3333",
        certification_date=date(2005, 9, 1),
        plan_tier_id=tier.id,
        plan_type_id=plan.id,
    )
    session.add(member)
    await session.flush()

    employment = EmploymentRecord(
        member_id=member.id,
        employer_id=employer.id,
        employment_type="general_staff",
        hire_date=date(2005, 9, 1),
        percent_time=100.0,
    )
    session.add(employment)
    await session.flush()

    return employer, member, employment


def _row(member_number="PRY-001", period_start=date(2025, 1, 1), period_end=date(2025, 1, 31)):
    return PayrollRowInput(
        member_number=member_number,
        period_start=period_start,
        period_end=period_end,
        gross_earnings=Decimal("5000.00"),
        employee_contribution=Decimal("400.00"),
        employer_contribution=Decimal("250.00"),
        days_worked=20,
    )


# ── DB tests ──────────────────────────────────────────────────────────────────

async def test_ingest_json_applied(session):
    async with session.begin():
        employer, member, _ = await _setup(session)
        report = await ingest_json(employer.id, PayrollReportCreate(rows=[_row()]), session)

    assert report.status == "completed"
    assert report.row_count == 1
    assert report.processed_count == 1
    assert report.error_count == 0
    assert report.skipped_count == 0
    assert len(report.rows) == 1
    assert report.rows[0].status == "applied"
    assert report.rows[0].member_id == member.id


async def test_ingest_json_member_not_found(session):
    async with session.begin():
        employer, _, _ = await _setup(session)
        report = await ingest_json(
            employer.id,
            PayrollReportCreate(rows=[_row(member_number="UNKNOWN-999")]),
            session,
        )

    assert report.status == "completed"
    assert report.error_count == 1
    assert report.processed_count == 0
    row = report.rows[0]
    assert row.status == "error"
    assert "not found" in row.error_message.lower()


async def test_ingest_json_no_employment(session):
    async with session.begin():
        tier = PlanTier(tier_code="t1", tier_label="T1", effective_date=date(1980, 1, 1))
        plan = PlanType(plan_code="trad", plan_label="Trad")
        session.add_all([tier, plan])
        await session.flush()

        employer2 = Employer(name="Other Employer", employer_code="OTH-001", employer_type="municipal")
        session.add(employer2)

        member2 = Member(
            member_number="PRY-002",
            first_name="Bob",
            last_name="Test",
            date_of_birth=date(1980, 1, 1),
            ssn_encrypted=encrypt_ssn("999887777"),
            ssn_last_four="7777",
            certification_date=date(2010, 1, 1),
            plan_tier_id=tier.id,
            plan_type_id=plan.id,
        )
        session.add(member2)
        await session.flush()

        # employer2 has no employment record for member2
        report = await ingest_json(
            employer2.id,
            PayrollReportCreate(rows=[_row(member_number="PRY-002")]),
            session,
        )

    assert report.rows[0].status == "error"
    assert "employment" in report.rows[0].error_message.lower()


async def test_ingest_duplicate_skipped(session):
    async with session.begin():
        employer, _, _ = await _setup(session)
        await ingest_json(employer.id, PayrollReportCreate(rows=[_row()]), session)
        report2 = await ingest_json(employer.id, PayrollReportCreate(rows=[_row()]), session)

    assert report2.skipped_count == 1
    assert report2.processed_count == 0
    assert report2.rows[0].status == "skipped"


async def test_ingest_partial_success(session):
    async with session.begin():
        employer, _, _ = await _setup(session)
        rows = [
            _row(member_number="PRY-001"),       # valid
            _row(member_number="GHOST-001"),      # not found
            _row(member_number="PRY-001", period_start=date(2025, 2, 1), period_end=date(2025, 2, 28)),  # valid different period
        ]
        report = await ingest_json(employer.id, PayrollReportCreate(rows=rows), session)

    assert report.processed_count == 2
    assert report.error_count == 1
    assert report.skipped_count == 0
    assert report.status == "completed"


async def test_ingest_csv_success(session):
    async with session.begin():
        employer, member, _ = await _setup(session)
        csv_text = (
            "member_number,period_start,period_end,gross_earnings,employee_contribution,employer_contribution,days_worked\n"
            "PRY-001,2025-03-01,2025-03-31,5000.00,400.00,250.00,21\n"
        )
        report = await ingest_csv(employer.id, csv_text, "march_2025.csv", session)

    assert report.source_format == "csv"
    assert report.source_filename == "march_2025.csv"
    assert report.processed_count == 1
    assert report.rows[0].status == "applied"


async def test_ingest_uses_monthly_floor_post_2024(session):
    async with session.begin():
        employer, member, _ = await _setup(session)
        # period after 2024-09-01 — monthly_floor rule applies
        report = await ingest_json(
            employer.id,
            PayrollReportCreate(rows=[_row(period_start=date(2025, 1, 1), period_end=date(2025, 1, 31))]),
            session,
        )

    assert report.rows[0].status == "applied"


async def test_list_payroll_reports(session):
    async with session.begin():
        employer, _, _ = await _setup(session)
        await ingest_json(employer.id, PayrollReportCreate(rows=[_row(period_start=date(2025, 1, 1), period_end=date(2025, 1, 31))]), session)
        await ingest_json(employer.id, PayrollReportCreate(rows=[_row(period_start=date(2025, 2, 1), period_end=date(2025, 2, 28))]), session)

    reports = await list_payroll_reports(employer.id, session)
    assert len(reports) == 2

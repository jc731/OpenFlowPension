"""Tests for report_service — all four reports.

RP01: Contribution Reconciliation
RP02: Delinquency
RP03: Membership Counts
RP04: Annuitant Export
"""

from datetime import date
from decimal import Decimal

import pytest

from app.crypto import encrypt_ssn, hash_ssn
from app.models.billing import EmployerInvoice
from app.models.employer import Employer
from app.models.employment import EmploymentRecord
from app.models.member import Member
from app.models.payroll import ContributionRecord
from app.models.retirement_case import RetirementCase
from app.services import report_service


# ── Shared fixtures ────────────────────────────────────────────────────────────

def _employer(name="District A", code="DA-001"):
    return Employer(name=name, employer_code=code, employer_type="school_district")


def _member(number="M-001", status="active", ssn="123456789"):
    return Member(
        member_number=number,
        first_name="Jane",
        last_name="Smith",
        date_of_birth=date(1960, 1, 1),
        ssn_encrypted=encrypt_ssn(ssn),
        ssn_last_four=ssn[-4:],
        ssn_hash=hash_ssn(ssn),
        member_status=status,
    )


def _employment(member_id, employer_id, emp_type="teacher"):
    return EmploymentRecord(
        member_id=member_id,
        employer_id=employer_id,
        employment_type=emp_type,
        hire_date=date(2000, 1, 1),
        percent_time=100.0,
    )


def _contribution(member_id, employment_id, period_start, period_end, ee=400.0, er=200.0):
    return ContributionRecord(
        member_id=member_id,
        employment_id=employment_id,
        period_start=period_start,
        period_end=period_end,
        employee_contribution=ee,
        employer_contribution=er,
        contribution_type="normal",
    )


# ── RP01: Contribution Reconciliation ─────────────────────────────────────────

async def test_contribution_reconciliation_aggregates_by_employer(session):
    async with session.begin():
        emp_a = _employer("District A", "DA")
        emp_b = _employer("District B", "DB")
        session.add_all([emp_a, emp_b])
        await session.flush()

        m1 = _member("M-001", ssn="111111111")
        m2 = _member("M-002", ssn="222222222")
        session.add_all([m1, m2])
        await session.flush()

        er_a = _employment(m1.id, emp_a.id)
        er_b = _employment(m2.id, emp_b.id)
        session.add_all([er_a, er_b])
        await session.flush()

        # Three contributions for District A, one for District B
        session.add_all([
            _contribution(m1.id, er_a.id, date(2026, 1, 1), date(2026, 1, 31), ee=400, er=200),
            _contribution(m1.id, er_a.id, date(2026, 2, 1), date(2026, 2, 28), ee=400, er=200),
            _contribution(m1.id, er_a.id, date(2026, 3, 1), date(2026, 3, 31), ee=400, er=200),
            _contribution(m2.id, er_b.id, date(2026, 1, 1), date(2026, 1, 31), ee=300, er=150),
        ])
        await session.flush()

        report = await report_service.contribution_reconciliation(
            date(2026, 1, 1), date(2026, 3, 31), session
        )

    assert len(report.rows) == 2
    by_code = {r.employer_code: r for r in report.rows}

    assert by_code["DA"].total_employee_contributions == Decimal("1200")
    assert by_code["DA"].total_employer_contributions == Decimal("600")
    assert by_code["DA"].total_contributions == Decimal("1800")
    assert by_code["DA"].record_count == 3

    assert by_code["DB"].total_employee_contributions == Decimal("300")
    assert by_code["DB"].record_count == 1

    assert report.summary.total_employee_contributions == Decimal("1500")
    assert report.summary.total_employer_contributions == Decimal("750")
    assert report.summary.employer_count == 2
    assert report.summary.record_count == 4


async def test_contribution_reconciliation_filters_by_employer(session):
    async with session.begin():
        emp_a = _employer("District A", "DA")
        emp_b = _employer("District B", "DB")
        session.add_all([emp_a, emp_b])
        await session.flush()

        m1 = _member("M-001", ssn="111111111")
        m2 = _member("M-002", ssn="222222222")
        session.add_all([m1, m2])
        await session.flush()

        er_a = _employment(m1.id, emp_a.id)
        er_b = _employment(m2.id, emp_b.id)
        session.add_all([er_a, er_b])
        await session.flush()

        session.add_all([
            _contribution(m1.id, er_a.id, date(2026, 1, 1), date(2026, 1, 31)),
            _contribution(m2.id, er_b.id, date(2026, 1, 1), date(2026, 1, 31)),
        ])
        await session.flush()

        report = await report_service.contribution_reconciliation(
            date(2026, 1, 1), date(2026, 1, 31), session, employer_id=emp_a.id
        )

    assert len(report.rows) == 1
    assert report.rows[0].employer_code == "DA"


async def test_contribution_reconciliation_respects_date_range(session):
    async with session.begin():
        emp = _employer()
        session.add(emp)
        await session.flush()

        m = _member()
        session.add(m)
        await session.flush()

        er = _employment(m.id, emp.id)
        session.add(er)
        await session.flush()

        session.add_all([
            _contribution(m.id, er.id, date(2025, 12, 1), date(2025, 12, 31)),  # out of range
            _contribution(m.id, er.id, date(2026, 1, 1), date(2026, 1, 31)),    # in range
        ])
        await session.flush()

        report = await report_service.contribution_reconciliation(
            date(2026, 1, 1), date(2026, 3, 31), session
        )

    assert report.summary.record_count == 1


async def test_contribution_reconciliation_empty_returns_zero_summary(session):
    async with session.begin():
        report = await report_service.contribution_reconciliation(
            date(2026, 1, 1), date(2026, 3, 31), session
        )
    assert len(report.rows) == 0
    assert report.summary.total_contributions == Decimal("0")
    assert report.summary.employer_count == 0


# ── RP02: Delinquency ─────────────────────────────────────────────────────────

def _invoice(employer_id, due_date, amount_due=1000.0, amount_paid=0.0, status="issued", inv_type="deficiency"):
    return EmployerInvoice(
        employer_id=employer_id,
        invoice_type=inv_type,
        status=status,
        amount_due=amount_due,
        amount_paid=amount_paid,
        due_date=due_date,
    )


async def test_delinquency_returns_past_due_issued_invoices(session):
    async with session.begin():
        emp = _employer()
        session.add(emp)
        await session.flush()

        session.add_all([
            _invoice(emp.id, date(2026, 1, 15), amount_due=1000, amount_paid=0),   # past due
            _invoice(emp.id, date(2026, 1, 31), amount_due=500, amount_paid=100),  # partial, past due
            _invoice(emp.id, date(2026, 7, 1), amount_due=2000, amount_paid=0),    # not yet due
            _invoice(emp.id, date(2026, 1, 10), amount_due=800, amount_paid=800, status="paid"),  # paid
        ])
        await session.flush()

        report = await report_service.delinquency(date(2026, 6, 1), session)

    assert len(report.rows) == 2
    outstanding = {r.outstanding for r in report.rows}
    assert Decimal("1000") in outstanding
    assert Decimal("400") in outstanding  # 500 - 100
    assert report.summary.total_outstanding == Decimal("1400")
    assert report.summary.invoice_count == 2
    assert report.summary.employer_count == 1


async def test_delinquency_includes_overdue_status(session):
    async with session.begin():
        emp = _employer()
        session.add(emp)
        await session.flush()
        session.add(_invoice(emp.id, date(2026, 1, 1), status="overdue"))
        await session.flush()

        report = await report_service.delinquency(date(2026, 6, 1), session)

    assert len(report.rows) == 1
    assert report.rows[0].invoice_status == "overdue"


async def test_delinquency_days_overdue_correct(session):
    async with session.begin():
        emp = _employer()
        session.add(emp)
        await session.flush()
        session.add(_invoice(emp.id, date(2026, 1, 1)))
        await session.flush()

        report = await report_service.delinquency(date(2026, 2, 1), session)

    assert report.rows[0].days_overdue == 31


async def test_delinquency_empty(session):
    async with session.begin():
        report = await report_service.delinquency(date(2026, 6, 1), session)
    assert len(report.rows) == 0
    assert report.summary.total_outstanding == Decimal("0")


# ── RP03: Membership Counts ───────────────────────────────────────────────────

async def test_membership_counts_groups_by_status(session):
    async with session.begin():
        session.add_all([
            _member("M-001", status="active", ssn="111111111"),
            _member("M-002", status="active", ssn="222222222"),
            _member("M-003", status="terminated", ssn="333333333"),
            _member("M-004", status="annuitant", ssn="444444444"),
        ])
        await session.flush()

        report = await report_service.membership_counts(session)

    by_status = {r.status: r.count for r in report.rows}
    assert by_status["active"] == 2
    assert by_status["terminated"] == 1
    assert by_status["annuitant"] == 1
    assert report.summary.total_members == 4


async def test_membership_counts_empty(session):
    async with session.begin():
        report = await report_service.membership_counts(session)
    assert len(report.rows) == 0
    assert report.summary.total_members == 0


# ── RP04: Annuitant Export ────────────────────────────────────────────────────

async def test_annuitants_returns_annuitant_and_retired_members(session):
    async with session.begin():
        m_ann = _member("M-001", status="annuitant", ssn="111111111")
        m_ret = _member("M-002", status="retired", ssn="222222222")
        m_act = _member("M-003", status="active", ssn="333333333")
        session.add_all([m_ann, m_ret, m_act])
        await session.flush()

        rc = RetirementCase(
            member_id=m_ann.id,
            status="active",
            retirement_date=date(2020, 7, 1),
            benefit_option_type="single_life",
            final_monthly_annuity=Decimal("2500.00"),
            first_payment_date=date(2020, 8, 1),
        )
        session.add(rc)
        await session.flush()

        report = await report_service.annuitants(session)

    assert report.summary.total_annuitants == 2
    assert report.summary.annuitants_with_approved_case == 1
    assert report.summary.total_monthly_outlay == Decimal("2500.00")

    by_num = {r.member_number: r for r in report.rows}
    assert by_num["M-001"].final_monthly_annuity == Decimal("2500.00")
    assert by_num["M-001"].payments_started is True
    assert by_num["M-001"].case_status == "active"
    assert by_num["M-002"].final_monthly_annuity is None  # retired but no case
    assert by_num["M-002"].payments_started is False
    assert "M-003" not in by_num  # active member excluded


async def test_annuitants_approved_case_included(session):
    async with session.begin():
        m = _member("M-001", status="annuitant")
        session.add(m)
        await session.flush()

        rc = RetirementCase(
            member_id=m.id,
            status="approved",
            retirement_date=date(2025, 1, 1),
            benefit_option_type="js_50",
            final_monthly_annuity=Decimal("1800.00"),
        )
        session.add(rc)
        await session.flush()

        report = await report_service.annuitants(session)

    assert len(report.rows) == 1
    assert report.rows[0].case_status == "approved"
    assert report.rows[0].payments_started is False


async def test_annuitants_draft_case_not_included(session):
    """A draft retirement case should not appear in the annuitant export."""
    async with session.begin():
        m = _member("M-001", status="annuitant")
        session.add(m)
        await session.flush()

        rc = RetirementCase(
            member_id=m.id,
            status="draft",
            retirement_date=date(2025, 1, 1),
            benefit_option_type="single_life",
        )
        session.add(rc)
        await session.flush()

        report = await report_service.annuitants(session)

    assert len(report.rows) == 1
    assert report.rows[0].final_monthly_annuity is None  # draft excluded


async def test_annuitants_empty(session):
    async with session.begin():
        report = await report_service.annuitants(session)
    assert len(report.rows) == 0
    assert report.summary.total_monthly_outlay == Decimal("0")

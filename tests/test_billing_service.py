"""Tests for billing_service — rate lookup, variance check, invoice lifecycle, payments."""

from datetime import date
from decimal import Decimal

import pytest

from app.crypto import encrypt_ssn
from app.models.employer import Employer
from app.models.employment import EmploymentRecord
from app.models.member import Member
from app.models.plan_config import PlanTier, PlanType, SystemConfiguration
from app.models.payroll import PayrollReport, PayrollReportRow
from app.services import billing_service as svc


# ── Fixtures ───────────────────────────────────────────────────────────────────

async def _make_employer(session) -> Employer:
    employer = Employer(name="Test City", employer_code="TC001", employer_type="municipality")
    session.add(employer)
    await session.flush()
    return employer


async def _make_member(session, employer: Employer) -> tuple[Member, EmploymentRecord]:
    tier = PlanTier(tier_code="t1", tier_label="Tier I", effective_date=date(1980, 1, 1))
    plan = PlanType(plan_code="db", plan_label="Defined Benefit")
    session.add_all([tier, plan])
    await session.flush()

    member = Member(
        member_number="B001",
        first_name="Bob",
        last_name="Smith",
        date_of_birth=date(1970, 1, 1),
        ssn_encrypted=encrypt_ssn("123-45-6789"),
        ssn_last_four="6789",
        plan_tier_id=tier.id,
        plan_type_id=plan.id,
    )
    session.add(member)
    await session.flush()
    employment = EmploymentRecord(
        member_id=member.id,
        employer_id=employer.id,
        hire_date=date(2000, 1, 1),
        employment_type="general",
        percent_time=100.0,
        position_title="Clerk",
    )
    session.add(employment)
    await session.flush()
    return member, employment


async def _make_payroll_report(session, employer: Employer, member: Member, employment: EmploymentRecord):
    report = PayrollReport(
        employer_id=employer.id,
        source_format="json",
        status="completed",
        row_count=1,
    )
    session.add(report)
    await session.flush()
    row = PayrollReportRow(
        payroll_report_id=report.id,
        member_number=member.member_number,
        member_id=member.id,
        employment_id=employment.id,
        period_start=date(2024, 1, 1),
        period_end=date(2024, 1, 31),
        gross_earnings=5000.0,
        employee_contribution=350.0,   # 7% — short of 8%
        employer_contribution=600.0,   # 12% — correct
        days_worked=22,
        status="applied",
    )
    session.add(row)
    await session.flush()
    return report, row


# ── Rate lookup tests ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_effective_rate_fund_wide(session):
    """Fund-wide default rate is found when no employer/type specificity."""
    employer = await _make_employer(session)
    rate = await svc.create_rate(
        employee_rate=Decimal("0.08"),
        employer_rate=Decimal("0.12"),
        effective_date=date(2020, 1, 1),
        session=session,
    )
    await session.flush()

    result = await svc.get_effective_rate(employer.id, "general", date(2024, 1, 1), session)
    assert result == (Decimal("0.08"), Decimal("0.12"))


@pytest.mark.asyncio
async def test_get_effective_rate_employer_override(session):
    """Employer-specific rate wins over fund-wide default."""
    employer = await _make_employer(session)
    await svc.create_rate(
        employee_rate=Decimal("0.08"),
        employer_rate=Decimal("0.12"),
        effective_date=date(2020, 1, 1),
        session=session,
    )
    await svc.create_rate(
        employer_id=employer.id,
        employee_rate=Decimal("0.09"),
        employer_rate=Decimal("0.13"),
        effective_date=date(2020, 1, 1),
        session=session,
    )
    await session.flush()

    result = await svc.get_effective_rate(employer.id, "general", date(2024, 1, 1), session)
    assert result == (Decimal("0.09"), Decimal("0.13"))


@pytest.mark.asyncio
async def test_get_effective_rate_type_override(session):
    """Employment-type rate wins over fund-wide default for matching type."""
    employer = await _make_employer(session)
    await svc.create_rate(
        employee_rate=Decimal("0.08"),
        employer_rate=Decimal("0.12"),
        effective_date=date(2020, 1, 1),
        session=session,
    )
    await svc.create_rate(
        employment_type="police",
        employee_rate=Decimal("0.10"),
        employer_rate=Decimal("0.14"),
        effective_date=date(2020, 1, 1),
        session=session,
    )
    await session.flush()

    police_result = await svc.get_effective_rate(employer.id, "police", date(2024, 1, 1), session)
    assert police_result == (Decimal("0.10"), Decimal("0.14"))

    general_result = await svc.get_effective_rate(employer.id, "general", date(2024, 1, 1), session)
    assert general_result == (Decimal("0.08"), Decimal("0.12"))


@pytest.mark.asyncio
async def test_get_effective_rate_none_when_not_configured(session):
    """Returns None when no rate is configured."""
    employer = await _make_employer(session)
    result = await svc.get_effective_rate(employer.id, "general", date(2024, 1, 1), session)
    assert result is None


@pytest.mark.asyncio
async def test_get_effective_rate_respects_effective_date(session):
    """Rate not yet in effect returns None; rate in effect returns value."""
    employer = await _make_employer(session)
    await svc.create_rate(
        employee_rate=Decimal("0.08"),
        employer_rate=Decimal("0.12"),
        effective_date=date(2025, 1, 1),
        session=session,
    )
    await session.flush()

    assert await svc.get_effective_rate(employer.id, "general", date(2024, 12, 31), session) is None
    assert await svc.get_effective_rate(employer.id, "general", date(2025, 1, 1), session) is not None


# ── Rate cache tests ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_rate_cache(session):
    employer = await _make_employer(session)
    await svc.create_rate(
        employee_rate=Decimal("0.08"),
        employer_rate=Decimal("0.12"),
        effective_date=date(2020, 1, 1),
        session=session,
    )
    await svc.create_rate(
        employment_type="police",
        employee_rate=Decimal("0.10"),
        employer_rate=Decimal("0.14"),
        effective_date=date(2020, 1, 1),
        session=session,
    )
    await session.flush()

    cache = await svc.build_rate_cache(employer.id, date(2024, 1, 1), session)
    assert "*" in cache
    assert "police" in cache
    assert cache["*"] == (Decimal("0.08"), Decimal("0.12"))
    assert cache["police"] == (Decimal("0.10"), Decimal("0.14"))


def test_lookup_rate_from_cache_fallback():
    cache = {
        "*": (Decimal("0.08"), Decimal("0.12")),
        "police": (Decimal("0.10"), Decimal("0.14")),
    }
    assert svc.lookup_rate_from_cache(cache, "police") == (Decimal("0.10"), Decimal("0.14"))
    assert svc.lookup_rate_from_cache(cache, "general") == (Decimal("0.08"), Decimal("0.12"))
    assert svc.lookup_rate_from_cache({}, "general") is None


# ── Variance check tests ───────────────────────────────────────────────────────

def test_check_contribution_variance_no_shortfall():
    warnings = svc.check_contribution_variance(
        gross=Decimal("5000"),
        submitted_employee=Decimal("400"),
        submitted_employer=Decimal("600"),
        employee_rate=Decimal("0.08"),
        employer_rate=Decimal("0.12"),
    )
    assert warnings == []


def test_check_contribution_variance_employee_short():
    warnings = svc.check_contribution_variance(
        gross=Decimal("5000"),
        submitted_employee=Decimal("350"),
        submitted_employer=Decimal("600"),
        employee_rate=Decimal("0.08"),
        employer_rate=Decimal("0.12"),
    )
    assert len(warnings) == 1
    assert "Employee" in warnings[0]
    assert "$50.00" in warnings[0]


def test_check_contribution_variance_both_short():
    warnings = svc.check_contribution_variance(
        gross=Decimal("5000"),
        submitted_employee=Decimal("350"),
        submitted_employer=Decimal("500"),
        employee_rate=Decimal("0.08"),
        employer_rate=Decimal("0.12"),
    )
    assert len(warnings) == 2


def test_check_contribution_variance_overpayment_not_flagged():
    """Overpayments are not flagged — only shortfalls."""
    warnings = svc.check_contribution_variance(
        gross=Decimal("5000"),
        submitted_employee=Decimal("500"),   # over
        submitted_employer=Decimal("700"),   # over
        employee_rate=Decimal("0.08"),
        employer_rate=Decimal("0.12"),
    )
    assert warnings == []


# ── Invoice lifecycle tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_supplemental_invoice(session):
    employer = await _make_employer(session)
    invoice = await svc.create_supplemental_invoice(
        employer_id=employer.id,
        amount_due=Decimal("1000.00"),
        due_date=date(2024, 3, 1),
        line_items=[{"description": "UAL assessment", "amount": "1000.00"}],
        session=session,
        note="Annual UAL",
    )
    await session.flush()

    assert invoice.status == "draft"
    assert invoice.invoice_type == "supplemental"
    assert float(invoice.amount_due) == 1000.0
    assert invoice.amount_paid == 0


@pytest.mark.asyncio
async def test_issue_invoice(session):
    employer = await _make_employer(session)
    invoice = await svc.create_supplemental_invoice(
        employer_id=employer.id,
        amount_due=Decimal("500.00"),
        due_date=date(2024, 3, 1),
        line_items=[],
        session=session,
    )
    await session.flush()

    issued = await svc.issue_invoice(invoice, session)
    assert issued.status == "issued"
    assert issued.issued_at is not None


@pytest.mark.asyncio
async def test_issue_invoice_wrong_status(session):
    employer = await _make_employer(session)
    invoice = await svc.create_supplemental_invoice(
        employer_id=employer.id,
        amount_due=Decimal("500.00"),
        due_date=date(2024, 3, 1),
        line_items=[],
        session=session,
    )
    await session.flush()
    await svc.issue_invoice(invoice, session)

    with pytest.raises(ValueError, match="must be 'draft'"):
        await svc.issue_invoice(invoice, session)


@pytest.mark.asyncio
async def test_record_payment_partial_then_full(session):
    employer = await _make_employer(session)
    invoice = await svc.create_supplemental_invoice(
        employer_id=employer.id,
        amount_due=Decimal("1000.00"),
        due_date=date(2024, 3, 1),
        line_items=[],
        session=session,
    )
    await session.flush()
    await svc.issue_invoice(invoice, session)

    p1 = await svc.record_payment(
        invoice=invoice,
        amount=Decimal("400.00"),
        payment_date=date(2024, 2, 1),
        payment_method="check",
        session=session,
    )
    assert invoice.status == "issued"
    assert float(invoice.amount_paid) == 400.0

    p2 = await svc.record_payment(
        invoice=invoice,
        amount=Decimal("600.00"),
        payment_date=date(2024, 2, 15),
        payment_method="ach",
        session=session,
    )
    assert invoice.status == "paid"
    assert invoice.paid_at is not None
    assert float(invoice.amount_paid) == 1000.0


@pytest.mark.asyncio
async def test_record_payment_on_paid_invoice_raises(session):
    employer = await _make_employer(session)
    invoice = await svc.create_supplemental_invoice(
        employer_id=employer.id,
        amount_due=Decimal("100.00"),
        due_date=date(2024, 3, 1),
        line_items=[],
        session=session,
    )
    await session.flush()
    await svc.issue_invoice(invoice, session)
    await svc.record_payment(invoice=invoice, amount=Decimal("100.00"),
                             payment_date=date(2024, 2, 1), payment_method="check",
                             session=session)
    assert invoice.status == "paid"

    with pytest.raises(ValueError, match="paid"):
        await svc.record_payment(invoice=invoice, amount=Decimal("1.00"),
                                 payment_date=date(2024, 2, 2), payment_method="check",
                                 session=session)


@pytest.mark.asyncio
async def test_void_invoice(session):
    employer = await _make_employer(session)
    invoice = await svc.create_supplemental_invoice(
        employer_id=employer.id,
        amount_due=Decimal("500.00"),
        due_date=date(2024, 3, 1),
        line_items=[],
        session=session,
    )
    await session.flush()

    voided = await svc.void_invoice(invoice, "Issued in error", session)
    assert voided.status == "voided"
    assert voided.void_reason == "Issued in error"
    assert voided.voided_at is not None


@pytest.mark.asyncio
async def test_void_paid_invoice_raises(session):
    employer = await _make_employer(session)
    invoice = await svc.create_supplemental_invoice(
        employer_id=employer.id,
        amount_due=Decimal("100.00"),
        due_date=date(2024, 3, 1),
        line_items=[],
        session=session,
    )
    await session.flush()
    await svc.issue_invoice(invoice, session)
    await svc.record_payment(invoice=invoice, amount=Decimal("100.00"),
                             payment_date=date(2024, 2, 1), payment_method="check",
                             session=session)

    with pytest.raises(ValueError, match="paid invoice"):
        await svc.void_invoice(invoice, "mistake", session)


# ── Deficiency calc tests ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_calculate_deficiency(session):
    """Employee contribution short by $50; employer on target."""
    employer = await _make_employer(session)
    member, employment = await _make_member(session, employer)
    report, row = await _make_payroll_report(session, employer, member, employment)

    # 8% employee, 12% employer — row has 7% employee (350/5000), 12% employer (600/5000)
    await svc.create_rate(
        employee_rate=Decimal("0.08"),
        employer_rate=Decimal("0.12"),
        effective_date=date(2020, 1, 1),
        session=session,
    )
    await session.flush()

    result = await svc.calculate_deficiency([report.id], employer.id, session)

    assert Decimal(result["employee_deficiency"]) == Decimal("50.00")
    assert Decimal(result["employer_deficiency"]) == Decimal("0.00")
    assert Decimal(result["total_deficiency"]) == Decimal("50.00")
    assert result["row_count"] == 1


@pytest.mark.asyncio
async def test_calculate_deficiency_no_deficiency(session):
    """Contributions at exactly expected rates — no deficiency."""
    employer = await _make_employer(session)
    member, employment = await _make_member(session, employer)

    report = PayrollReport(employer_id=employer.id, source_format="json",
                           status="completed", row_count=1)
    session.add(report)
    await session.flush()
    row = PayrollReportRow(
        payroll_report_id=report.id,
        member_number=member.member_number,
        member_id=member.id,
        employment_id=employment.id,
        period_start=date(2024, 1, 1),
        period_end=date(2024, 1, 31),
        gross_earnings=5000.0,
        employee_contribution=400.0,   # 8% exact
        employer_contribution=600.0,   # 12% exact
        days_worked=22,
        status="applied",
    )
    session.add(row)
    await svc.create_rate(
        employee_rate=Decimal("0.08"),
        employer_rate=Decimal("0.12"),
        effective_date=date(2020, 1, 1),
        session=session,
    )
    await session.flush()

    with pytest.raises(ValueError, match="No deficiency"):
        await svc.create_deficiency_invoice(
            employer_id=employer.id,
            payroll_report_ids=[report.id],
            due_date=date(2024, 3, 1),
            session=session,
        )


@pytest.mark.asyncio
async def test_calculate_deficiency_missing_report_raises(session):
    import uuid
    employer = await _make_employer(session)
    with pytest.raises(ValueError, match="not found"):
        await svc.calculate_deficiency([uuid.uuid4()], employer.id, session)


@pytest.mark.asyncio
async def test_create_deficiency_invoice(session):
    employer = await _make_employer(session)
    member, employment = await _make_member(session, employer)
    report, _ = await _make_payroll_report(session, employer, member, employment)

    await svc.create_rate(
        employee_rate=Decimal("0.08"),
        employer_rate=Decimal("0.12"),
        effective_date=date(2020, 1, 1),
        session=session,
    )
    await session.flush()

    invoice = await svc.create_deficiency_invoice(
        employer_id=employer.id,
        payroll_report_ids=[report.id],
        due_date=date(2024, 3, 1),
        session=session,
    )
    assert invoice.invoice_type == "deficiency"
    assert invoice.status == "draft"
    assert float(invoice.amount_due) == 50.0
    assert str(report.id) in invoice.source_report_ids


# ── list_rates test ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_rates(session):
    employer = await _make_employer(session)
    await svc.create_rate(employee_rate=Decimal("0.08"), employer_rate=Decimal("0.12"),
                          effective_date=date(2020, 1, 1), session=session)
    await svc.create_rate(employer_id=employer.id, employee_rate=Decimal("0.09"),
                          employer_rate=Decimal("0.13"), effective_date=date(2020, 1, 1),
                          session=session)
    await session.flush()

    all_rates = await svc.list_rates(session)
    assert len(all_rates) == 2

    employer_rates = await svc.list_rates(session, employer_id=employer.id)
    assert len(employer_rates) == 2   # includes fund-wide

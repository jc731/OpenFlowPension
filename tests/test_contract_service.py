"""Tests for contract and status management service.

Pure unit tests: transition guard logic.
DB tests: full lifecycle (hire → LOA → return → terminate → annuity),
          concurrent employment termination, invalid transitions, deceased guard,
          employment type / leave type validation, percent-time change.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.crypto import encrypt_ssn
from app.models.member import Member
from app.models.plan_config import PlanTier, PlanType, SystemConfiguration
from app.schemas.contract import (
    BeginAnnuityCreate,
    DeathRecordCreate,
    LeaveBeginCreate,
    LeaveEndCreate,
    NewHireCreate,
    PercentTimeChangeCreate,
    RefundStatusCreate,
    TerminationCreate,
)
from app.services.contract_service import (
    _check_transition,
    begin_annuity,
    begin_leave,
    change_percent_time,
    end_leave,
    get_current_status,
    get_status_history,
    new_hire,
    process_refund,
    record_death,
    terminate,
)
from app.models.employer import Employer


# ── Pure unit tests ───────────────────────────────────────────────────────────

def test_valid_transition_new_hire_from_none():
    _check_transition(None, "new_hire")  # should not raise


def test_valid_transition_new_hire_from_terminated():
    _check_transition("terminated", "new_hire")


def test_invalid_transition_new_hire_from_annuitant():
    with pytest.raises(ValueError, match="new_hire"):
        _check_transition("annuitant", "new_hire")


def test_deceased_blocks_all_events():
    for event in ("new_hire", "terminate", "begin_leave", "end_leave", "begin_annuity"):
        with pytest.raises(ValueError, match="deceased"):
            _check_transition("deceased", event)


def test_invalid_terminate_from_inactive():
    with pytest.raises(ValueError, match="terminate"):
        _check_transition("inactive", "terminate")


# ── DB fixtures ───────────────────────────────────────────────────────────────

async def _setup(session):
    """Returns (employer, member) with required plan tier/type and system configs."""
    tier = PlanTier(tier_code="tier_1", tier_label="Tier I", effective_date=date(1980, 1, 1))
    plan = PlanType(plan_code="traditional", plan_label="Traditional")
    session.add_all([tier, plan])
    await session.flush()

    for config_key, config_value in [
        ("employment_types", {"types": ["general_staff", "academic", "police_fire", "other"]}),
        ("leave_types",      {"types": ["medical", "personal", "military", "family", "other"]}),
    ]:
        session.add(SystemConfiguration(
            config_key=config_key,
            config_value=config_value,
            effective_date=date(1980, 1, 1),
        ))

    employer = Employer(name="Test University", employer_code="CTR-001", employer_type="university")
    session.add(employer)
    await session.flush()

    member = Member(
        member_number="CTR-001",
        first_name="Jane",
        last_name="Contract",
        date_of_birth=date(1975, 3, 1),
        ssn_encrypted=encrypt_ssn("222334444"),
        ssn_last_four="4444",
        certification_date=date(2005, 9, 1),
        plan_tier_id=tier.id,
        plan_type_id=plan.id,
    )
    session.add(member)
    await session.flush()

    return employer, member


def _hire_data(employer_id, employment_type="general_staff", hire_date=date(2005, 9, 1)):
    return NewHireCreate(
        employer_id=employer_id,
        employment_type=employment_type,
        hire_date=hire_date,
        percent_time=100.0,
        annual_salary=Decimal("60000.00"),
    )


# ── DB tests: new hire ────────────────────────────────────────────────────────

async def test_new_hire_creates_employment_and_status(session):
    async with session.begin():
        employer, member = await _setup(session)
        emp = await new_hire(member.id, _hire_data(employer.id), session)

    assert emp.member_id == member.id
    assert emp.employment_type == "general_staff"
    assert emp.percent_time == 100.0

    status = await get_current_status(member.id, session)
    assert status.status == "active"
    assert status.source_event == "new_hire"


async def test_new_hire_invalid_employment_type(session):
    async with session.begin():
        employer, member = await _setup(session)
        with pytest.raises(ValueError, match="Invalid employment_type"):
            await new_hire(member.id, _hire_data(employer.id, employment_type="wizard"), session)


async def test_new_hire_blocked_when_annuitant(session):
    async with session.begin():
        employer, member = await _setup(session)
        emp = await new_hire(member.id, _hire_data(employer.id), session)
        await terminate(emp.id, member.id, TerminationCreate(termination_date=date(2030, 1, 1)), session)
        await begin_annuity(member.id, BeginAnnuityCreate(effective_date=date(2030, 2, 1)), session)
        with pytest.raises(ValueError, match="new_hire"):
            await new_hire(member.id, _hire_data(employer.id, hire_date=date(2031, 1, 1)), session)


# ── DB tests: termination ─────────────────────────────────────────────────────

async def test_terminate_sets_status(session):
    async with session.begin():
        employer, member = await _setup(session)
        emp = await new_hire(member.id, _hire_data(employer.id), session)
        result = await terminate(
            emp.id, member.id,
            TerminationCreate(termination_date=date(2030, 6, 30), termination_reason="voluntary_resignation"),
            session,
        )

    assert result.termination_date == date(2030, 6, 30)
    status = await get_current_status(member.id, session)
    assert status.status == "terminated"
    assert status.reason == "voluntary_resignation"


async def test_terminate_concurrent_keeps_active(session):
    """Terminating one of two concurrent employments leaves status active."""
    async with session.begin():
        employer, member = await _setup(session)
        emp1 = await new_hire(member.id, _hire_data(employer.id), session)

        employer2 = Employer(name="Other Employer", employer_code="CTR-002", employer_type="municipal")
        session.add(employer2)
        await session.flush()

        emp2 = await new_hire(
            member.id,
            NewHireCreate(employer_id=employer2.id, employment_type="general_staff",
                          hire_date=date(2010, 1, 1), percent_time=50.0, annual_salary=Decimal("30000")),
            session,
        )
        # Terminate first employment only
        await terminate(emp1.id, member.id, TerminationCreate(termination_date=date(2030, 6, 30)), session)

    status = await get_current_status(member.id, session)
    assert status.status == "active"  # emp2 still active


async def test_terminate_already_terminated_raises(session):
    async with session.begin():
        employer, member = await _setup(session)
        emp = await new_hire(member.id, _hire_data(employer.id), session)
        await terminate(emp.id, member.id, TerminationCreate(termination_date=date(2030, 1, 1)), session)
        with pytest.raises(ValueError, match="already terminated"):
            await terminate(emp.id, member.id, TerminationCreate(termination_date=date(2030, 6, 1)), session)


# ── DB tests: leave of absence ────────────────────────────────────────────────

async def test_begin_and_end_leave(session):
    async with session.begin():
        employer, member = await _setup(session)
        emp = await new_hire(member.id, _hire_data(employer.id), session)

        leave = await begin_leave(
            emp.id, member.id,
            LeaveBeginCreate(leave_type="medical", start_date=date(2026, 3, 1), is_paid=True),
            session,
        )
        assert leave.leave_type == "medical"
        assert member.member_status == "on_leave"

        result = await end_leave(
            emp.id, member.id,
            LeaveEndCreate(actual_return_date=date(2026, 6, 1)),
            session,
        )

    assert result.actual_return_date == date(2026, 6, 1)
    status = await get_current_status(member.id, session)
    assert status.status == "active"


async def test_begin_leave_invalid_type(session):
    async with session.begin():
        employer, member = await _setup(session)
        emp = await new_hire(member.id, _hire_data(employer.id), session)
        with pytest.raises(ValueError, match="Invalid leave_type"):
            await begin_leave(
                emp.id, member.id,
                LeaveBeginCreate(leave_type="sabbatical", start_date=date(2026, 1, 1)),
                session,
            )


async def test_double_leave_raises(session):
    async with session.begin():
        employer, member = await _setup(session)
        emp = await new_hire(member.id, _hire_data(employer.id), session)
        await begin_leave(emp.id, member.id, LeaveBeginCreate(leave_type="medical", start_date=date(2026, 1, 1)), session)
        with pytest.raises(ValueError, match="begin_leave"):
            await begin_leave(emp.id, member.id, LeaveBeginCreate(leave_type="personal", start_date=date(2026, 2, 1)), session)


# ── DB tests: percent-time change ─────────────────────────────────────────────

async def test_percent_time_change(session):
    async with session.begin():
        employer, member = await _setup(session)
        emp = await new_hire(member.id, _hire_data(employer.id), session)
        result = await change_percent_time(
            emp.id, member.id,
            PercentTimeChangeCreate(
                new_percent_time=50.0,
                effective_date=date(2026, 1, 1),
                new_annual_salary=Decimal("30000"),
                change_reason="reduced_appointment",
            ),
            session,
        )

    assert result.percent_time == 50.0


# ── DB tests: death, annuity, refund ─────────────────────────────────────────

async def test_full_lifecycle(session):
    """hire → terminate → begin_annuity → death"""
    async with session.begin():
        employer, member = await _setup(session)
        emp = await new_hire(member.id, _hire_data(employer.id), session)
        await terminate(emp.id, member.id, TerminationCreate(termination_date=date(2030, 1, 1)), session)
        await begin_annuity(member.id, BeginAnnuityCreate(effective_date=date(2030, 2, 1)), session)
        await record_death(member.id, DeathRecordCreate(death_date=date(2045, 7, 15)), session)

    history = await get_status_history(member.id, session)
    statuses = [h.status for h in history]
    assert statuses == ["active", "terminated", "annuitant", "deceased"]


async def test_refund_sets_inactive(session):
    async with session.begin():
        employer, member = await _setup(session)
        emp = await new_hire(member.id, _hire_data(employer.id), session)
        await terminate(emp.id, member.id, TerminationCreate(termination_date=date(2030, 1, 1)), session)
        await process_refund(member.id, RefundStatusCreate(effective_date=date(2030, 3, 1)), session)

    status = await get_current_status(member.id, session)
    assert status.status == "inactive"
    assert status.reason == "refund_taken"


async def test_death_blocks_further_changes(session):
    async with session.begin():
        employer, member = await _setup(session)
        emp = await new_hire(member.id, _hire_data(employer.id), session)
        await record_death(member.id, DeathRecordCreate(death_date=date(2030, 1, 1)), session)
        with pytest.raises(ValueError, match="deceased"):
            await terminate(emp.id, member.id, TerminationCreate(termination_date=date(2030, 6, 1)), session)

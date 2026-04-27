"""Contract and status management service.

Handles the employment lifecycle (hire, terminate, LOA, percent-time change)
and member status transitions. Two responsibilities:

1. Contract events — write paths that mutate employment_records, salary_history,
   and leave_periods, with business-rule validation.

2. Status transitions — every contract event writes a MemberStatusHistory row
   and keeps Member.member_status in sync (denormalized for fast reads).

Status transition rules:
  new_hire        : None | terminated | inactive → active
  terminate       : active | on_leave → terminated  (only if no remaining active employment)
  begin_leave     : active → on_leave
  end_leave       : on_leave → active
  begin_annuity   : terminated | inactive | active → annuitant
  refund          : terminated → inactive
  death           : any → deceased

  deceased blocks all further contract writes.
"""

import uuid
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employment import EmploymentRecord
from app.models.leave_period import LeavePeriod
from app.models.member import Member
from app.models.member_status import MemberStatusHistory
from app.models.salary import SalaryHistory
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
from app.services.config_service import ConfigNotFoundError, get_config


# ── Valid statuses and allowed transitions ─────────────────────────────────────

VALID_STATUSES = frozenset({
    "active", "on_leave", "terminated", "inactive", "annuitant", "deceased"
})

# Maps event name → set of current statuses that allow it (None = no prior status)
_ALLOWED_FROM: dict[str, set[str | None]] = {
    # "active" included: concurrent employment is valid, and new members default to "active"
    "new_hire":       {None, "active", "terminated", "inactive"},
    "terminate":      {"active", "on_leave"},
    "begin_leave":    {"active"},
    "end_leave":      {"on_leave"},
    "begin_annuity":  {"terminated", "inactive", "active"},
    "refund":         {"terminated"},
    "death":          {"active", "on_leave", "terminated", "inactive", "annuitant", None},
}


# ── Internal helpers ───────────────────────────────────────────────────────────

async def _get_member(member_id: uuid.UUID, session: AsyncSession) -> Member:
    member = await session.get(Member, member_id)
    if not member:
        raise ValueError(f"Member {member_id} not found")
    return member


async def _get_employment(
    employment_id: uuid.UUID, member_id: uuid.UUID, session: AsyncSession
) -> EmploymentRecord:
    emp = await session.get(EmploymentRecord, employment_id)
    if not emp or emp.member_id != member_id:
        raise ValueError(f"Employment record {employment_id} not found for this member")
    return emp


def _check_transition(current_status: str | None, event: str) -> None:
    if current_status == "deceased":
        raise ValueError("Member is deceased — no further contract changes permitted")
    allowed = _ALLOWED_FROM.get(event, set())
    if current_status not in allowed:
        raise ValueError(
            f"Cannot perform '{event}' from status {current_status!r}. "
            f"Allowed from: {sorted(str(s) for s in allowed if s is not None) or ['none']}"
        )


async def _write_status(
    member: Member,
    status: str,
    effective_date: date,
    source_event: str,
    session: AsyncSession,
    reason: str | None = None,
    source_record_id: uuid.UUID | None = None,
    changed_by: uuid.UUID | None = None,
    note: str | None = None,
) -> MemberStatusHistory:
    row = MemberStatusHistory(
        member_id=member.id,
        status=status,
        effective_date=effective_date,
        reason=reason,
        source_event=source_event,
        source_record_id=source_record_id,
        changed_by=changed_by,
        note=note,
    )
    session.add(row)
    member.member_status = status
    member.status_date = effective_date
    await session.flush()
    return row


async def _validate_employment_type(employment_type: str, as_of: date, session: AsyncSession) -> None:
    try:
        config = await get_config("employment_types", as_of, session)
    except ConfigNotFoundError:
        raise ValueError(
            "No 'employment_types' system configuration found. "
            "Seed this config before hiring members."
        )
    valid_types: list[str] = config.config_value.get("types", [])
    if employment_type not in valid_types:
        raise ValueError(
            f"Invalid employment_type {employment_type!r}. "
            f"Configured types: {valid_types}"
        )


async def _has_active_employment(
    member_id: uuid.UUID,
    exclude_id: uuid.UUID,
    session: AsyncSession,
) -> bool:
    result = await session.execute(
        select(EmploymentRecord).where(
            EmploymentRecord.member_id == member_id,
            EmploymentRecord.id != exclude_id,
            EmploymentRecord.termination_date.is_(None),
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _get_open_leave(
    employment_id: uuid.UUID, session: AsyncSession
) -> LeavePeriod | None:
    result = await session.execute(
        select(LeavePeriod).where(
            LeavePeriod.employment_id == employment_id,
            LeavePeriod.actual_return_date.is_(None),
        ).limit(1)
    )
    return result.scalar_one_or_none()


# ── Contract events ────────────────────────────────────────────────────────────

async def new_hire(
    member_id: uuid.UUID,
    data: NewHireCreate,
    session: AsyncSession,
    created_by: uuid.UUID | None = None,
) -> EmploymentRecord:
    member = await _get_member(member_id, session)
    current_status: str | None = member.member_status if member.member_status else None

    _check_transition(current_status, "new_hire")
    await _validate_employment_type(data.employment_type, data.hire_date, session)

    employment = EmploymentRecord(
        member_id=member_id,
        employer_id=data.employer_id,
        employment_type=data.employment_type,
        position_title=data.position_title,
        department=data.department,
        hire_date=data.hire_date,
        percent_time=data.percent_time,
        is_primary=data.is_primary,
    )
    session.add(employment)
    await session.flush()

    session.add(SalaryHistory(
        employment_id=employment.id,
        effective_date=data.hire_date,
        annual_salary=float(data.annual_salary),
        salary_type=data.salary_type,
        change_reason="new_hire",
    ))

    await _write_status(
        member, "active", data.hire_date, "new_hire",
        session, source_record_id=employment.id, changed_by=created_by, note=data.note,
    )
    await session.flush()
    return employment


async def terminate(
    employment_id: uuid.UUID,
    member_id: uuid.UUID,
    data: TerminationCreate,
    session: AsyncSession,
    changed_by: uuid.UUID | None = None,
) -> EmploymentRecord:
    member = await _get_member(member_id, session)
    emp = await _get_employment(employment_id, member_id, session)
    if emp.termination_date is not None:
        raise ValueError("Employment record is already terminated")
    _check_transition(member.member_status, "terminate")

    emp.termination_date = data.termination_date
    emp.termination_reason = data.termination_reason
    await session.flush()

    # Only write terminated status if no other active employment remains
    still_active = await _has_active_employment(member_id, exclude_id=employment_id, session=session)
    if not still_active:
        await _write_status(
            member, "terminated", data.termination_date, "termination",
            session,
            reason=data.termination_reason,
            source_record_id=employment_id,
            changed_by=changed_by,
            note=data.note,
        )
    return emp


async def begin_leave(
    employment_id: uuid.UUID,
    member_id: uuid.UUID,
    data: LeaveBeginCreate,
    session: AsyncSession,
    created_by: uuid.UUID | None = None,
) -> LeavePeriod:
    member = await _get_member(member_id, session)
    _check_transition(member.member_status, "begin_leave")

    emp = await _get_employment(employment_id, member_id, session)
    if emp.termination_date is not None:
        raise ValueError("Cannot begin leave on a terminated employment record")

    existing = await _get_open_leave(employment_id, session)
    if existing:
        raise ValueError("Employment record already has an open leave period")

    await _validate_leave_type(data.leave_type, data.start_date, session)

    leave = LeavePeriod(
        employment_id=employment_id,
        leave_type=data.leave_type,
        start_date=data.start_date,
        expected_return_date=data.expected_return_date,
        is_paid=data.is_paid,
        created_by=created_by,
        note=data.note,
    )
    session.add(leave)
    await session.flush()

    await _write_status(
        member, "on_leave", data.start_date, "leave_start",
        session, source_record_id=leave.id, changed_by=created_by, note=data.note,
    )
    return leave


async def end_leave(
    employment_id: uuid.UUID,
    member_id: uuid.UUID,
    data: LeaveEndCreate,
    session: AsyncSession,
    changed_by: uuid.UUID | None = None,
) -> LeavePeriod:
    member = await _get_member(member_id, session)
    _check_transition(member.member_status, "end_leave")

    await _get_employment(employment_id, member_id, session)

    leave = await _get_open_leave(employment_id, session)
    if not leave:
        raise ValueError("No open leave period found for this employment record")

    leave.actual_return_date = data.actual_return_date
    await session.flush()

    await _write_status(
        member, "active", data.actual_return_date, "leave_end",
        session, source_record_id=leave.id, changed_by=changed_by, note=data.note,
    )
    return leave


async def change_percent_time(
    employment_id: uuid.UUID,
    member_id: uuid.UUID,
    data: PercentTimeChangeCreate,
    session: AsyncSession,
    changed_by: uuid.UUID | None = None,
) -> EmploymentRecord:
    member = await _get_member(member_id, session)
    if member.member_status == "deceased":
        raise ValueError("Member is deceased — no further contract changes permitted")

    emp = await _get_employment(employment_id, member_id, session)
    if emp.termination_date is not None:
        raise ValueError("Cannot change percent time on a terminated employment record")

    emp.percent_time = data.new_percent_time
    await session.flush()

    if data.new_annual_salary is not None:
        session.add(SalaryHistory(
            employment_id=employment_id,
            effective_date=data.effective_date,
            annual_salary=float(data.new_annual_salary),
            change_reason=data.change_reason or "percent_time_change",
        ))
        await session.flush()

    return emp


# ── Explicit status transitions ────────────────────────────────────────────────

async def record_death(
    member_id: uuid.UUID,
    data: DeathRecordCreate,
    session: AsyncSession,
    changed_by: uuid.UUID | None = None,
) -> MemberStatusHistory:
    member = await _get_member(member_id, session)
    _check_transition(member.member_status, "death")
    return await _write_status(
        member, "deceased", data.death_date, "death",
        session,
        reason="death",
        changed_by=changed_by,
        note=data.note,
    )


async def begin_annuity(
    member_id: uuid.UUID,
    data: BeginAnnuityCreate,
    session: AsyncSession,
    changed_by: uuid.UUID | None = None,
) -> MemberStatusHistory:
    member = await _get_member(member_id, session)
    _check_transition(member.member_status, "begin_annuity")
    return await _write_status(
        member, "annuitant", data.effective_date, "begin_annuity",
        session, changed_by=changed_by, note=data.note,
    )


async def process_refund(
    member_id: uuid.UUID,
    data: RefundStatusCreate,
    session: AsyncSession,
    changed_by: uuid.UUID | None = None,
) -> MemberStatusHistory:
    member = await _get_member(member_id, session)
    _check_transition(member.member_status, "refund")
    return await _write_status(
        member, "inactive", data.effective_date, "refund",
        session, reason="refund_taken", changed_by=changed_by, note=data.note,
    )


# ── Queries ────────────────────────────────────────────────────────────────────

async def get_current_status(
    member_id: uuid.UUID, session: AsyncSession
) -> MemberStatusHistory | None:
    result = await session.execute(
        select(MemberStatusHistory)
        .where(MemberStatusHistory.member_id == member_id)
        .order_by(MemberStatusHistory.effective_date.desc(), MemberStatusHistory.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_status_history(
    member_id: uuid.UUID, session: AsyncSession
) -> list[MemberStatusHistory]:
    result = await session.execute(
        select(MemberStatusHistory)
        .where(MemberStatusHistory.member_id == member_id)
        .order_by(MemberStatusHistory.effective_date, MemberStatusHistory.created_at)
    )
    return list(result.scalars().all())


# ── Leave type validation (mirrors employment type pattern) ────────────────────

async def _validate_leave_type(leave_type: str, as_of: date, session: AsyncSession) -> None:
    try:
        config = await get_config("leave_types", as_of, session)
    except ConfigNotFoundError:
        raise ValueError(
            "No 'leave_types' system configuration found. "
            "Seed this config before recording leave."
        )
    valid_types: list[str] = config.config_value.get("types", [])
    if leave_type not in valid_types:
        raise ValueError(
            f"Invalid leave_type {leave_type!r}. "
            f"Configured types: {valid_types}"
        )

"""Tests for member service: search/filter, address + contact history, bulk CSV import.

US-M04 (addresses), US-M05 (contacts), US-M09 (bulk import), US-M10 (search/filter).
"""

from datetime import date

import pytest

from app.models.employer import Employer
from app.models.employment import EmploymentRecord
from app.schemas.address import MemberAddressCreate
from app.schemas.contact import MemberContactCreate
from app.schemas.member import MemberCreate
from app.services.member_service import (
    add_address,
    add_contact,
    bulk_import_members,
    create_member,
    list_addresses,
    list_contacts,
    list_members,
    update_name,
)


def _unique_ssn(seed: str) -> str:
    """Derive a deterministic 9-digit SSN from a seed string."""
    import hashlib
    digest = hashlib.md5(seed.encode()).hexdigest()
    return "".join(str(int(c, 16) % 10) for c in digest[:9])


async def _make_member(session, member_number="M-1001", first="Jane", last="Smith"):
    return await create_member(
        MemberCreate(
            member_number=member_number,
            first_name=first,
            last_name=last,
            date_of_birth=date(1970, 5, 1),
            ssn=_unique_ssn(member_number),
        ),
        session,
    )


async def _make_employer(session, code="EMP1"):
    employer = Employer(name=f"District {code}", employer_code=code, employer_type="school_district")
    session.add(employer)
    await session.flush()
    return employer


# ── Search / filter ────────────────────────────────────────────────────────────

async def test_search_by_name_case_insensitive(session):
    await _make_member(session, "M-1", "Jane", "Smith")
    await _make_member(session, "M-2", "Bob", "Jones")

    results = await list_members(session, q="smi")
    assert [m.member_number for m in results] == ["M-1"]


async def test_search_by_member_number(session):
    await _make_member(session, "M-77", "Jane", "Smith")
    await _make_member(session, "M-88", "Bob", "Jones")

    results = await list_members(session, q="M-77")
    assert len(results) == 1
    assert results[0].first_name == "Jane"


async def test_filter_by_status(session):
    active = await _make_member(session, "M-1")
    terminated = await _make_member(session, "M-2", "Bob", "Jones")
    terminated.member_status = "terminated"
    await session.flush()

    results = await list_members(session, status="terminated")
    assert [m.id for m in results] == [terminated.id]
    results = await list_members(session, status="active")
    assert [m.id for m in results] == [active.id]


async def test_filter_by_employer_and_employment_type(session):
    member_a = await _make_member(session, "M-1", "Jane", "Smith")
    member_b = await _make_member(session, "M-2", "Bob", "Jones")
    emp1 = await _make_employer(session, "EMP1")
    emp2 = await _make_employer(session, "EMP2")
    session.add(EmploymentRecord(member_id=member_a.id, employer_id=emp1.id,
                                 employment_type="teacher", hire_date=date(2020, 1, 1)))
    session.add(EmploymentRecord(member_id=member_b.id, employer_id=emp2.id,
                                 employment_type="administrator", hire_date=date(2020, 1, 1)))
    await session.flush()

    results = await list_members(session, employer_id=emp1.id)
    assert [m.id for m in results] == [member_a.id]
    results = await list_members(session, employment_type="administrator")
    assert [m.id for m in results] == [member_b.id]
    results = await list_members(session, employer_id=emp1.id, employment_type="administrator")
    assert results == []


async def test_filter_by_employer_no_duplicate_rows(session):
    member = await _make_member(session)
    emp = await _make_employer(session)
    for _ in range(2):  # two concurrent employments at the same employer
        session.add(EmploymentRecord(member_id=member.id, employer_id=emp.id,
                                     employment_type="teacher", hire_date=date(2020, 1, 1)))
    await session.flush()

    results = await list_members(session, employer_id=emp.id)
    assert len(results) == 1


async def test_limit_and_offset(session):
    for i in range(5):
        await _make_member(session, f"M-{i}", "Jane", f"Smith{i}")

    page1 = await list_members(session, limit=2, offset=0)
    page2 = await list_members(session, limit=2, offset=2)
    assert len(page1) == 2 and len(page2) == 2
    assert {m.id for m in page1}.isdisjoint({m.id for m in page2})


# ── Addresses ──────────────────────────────────────────────────────────────────

async def test_add_address_supersedes_same_type(session):
    member = await _make_member(session)
    first = await add_address(member.id, MemberAddressCreate(
        line1="1 Old St", city="Springfield", state="il", zip="62701",
        effective_date=date(2024, 1, 1)), session)
    assert first.state == "IL"  # normalized

    second = await add_address(member.id, MemberAddressCreate(
        line1="2 New Ave", city="Springfield", state="IL", zip="62702",
        effective_date=date(2025, 6, 1)), session)

    addresses = await list_addresses(member.id, session)
    assert len(addresses) == 2
    by_id = {a.id: a for a in addresses}
    assert by_id[first.id].end_date == date(2025, 5, 31)
    assert by_id[second.id].end_date is None


async def test_add_address_different_type_not_superseded(session):
    member = await _make_member(session)
    mailing = await add_address(member.id, MemberAddressCreate(
        line1="1 Main St", city="Springfield", state="IL", zip="62701",
        effective_date=date(2024, 1, 1)), session)
    await add_address(member.id, MemberAddressCreate(
        address_type="physical", line1="2 Farm Rd", city="Springfield", state="IL",
        zip="62702", effective_date=date(2025, 1, 1)), session)

    addresses = await list_addresses(member.id, session)
    assert {a.end_date for a in addresses} == {None}
    assert mailing.end_date is None


async def test_add_address_unknown_member(session):
    import uuid
    with pytest.raises(ValueError, match="Member not found"):
        await add_address(uuid.uuid4(), MemberAddressCreate(
            line1="1 Main St", city="Springfield", state="IL", zip="62701",
            effective_date=date(2024, 1, 1)), session)


# ── Contacts ───────────────────────────────────────────────────────────────────

async def test_add_contact_alongside_existing(session):
    member = await _make_member(session)
    home = await add_contact(member.id, MemberContactCreate(
        contact_type="phone", value="217-555-0001", effective_date=date(2024, 1, 1)), session)
    await add_contact(member.id, MemberContactCreate(
        contact_type="phone", value="217-555-0002", effective_date=date(2025, 1, 1)), session)

    contacts = await list_contacts(member.id, session)
    assert len(contacts) == 2
    assert all(c.end_date is None for c in contacts)
    assert home.end_date is None


async def test_add_contact_supersede_end_dates_same_type(session):
    member = await _make_member(session)
    old = await add_contact(member.id, MemberContactCreate(
        contact_type="email", value="old@example.com", effective_date=date(2024, 1, 1)), session)
    new = await add_contact(member.id, MemberContactCreate(
        contact_type="email", value="new@example.com", effective_date=date(2025, 6, 1),
        supersede=True), session)

    contacts = {c.id: c for c in await list_contacts(member.id, session)}
    assert contacts[old.id].end_date == date(2025, 5, 31)
    assert contacts[new.id].end_date is None


async def test_add_primary_contact_demotes_previous_primary(session):
    member = await _make_member(session)
    old = await add_contact(member.id, MemberContactCreate(
        contact_type="phone", value="217-555-0001", is_primary=True,
        effective_date=date(2024, 1, 1)), session)
    new = await add_contact(member.id, MemberContactCreate(
        contact_type="phone", value="217-555-0002", is_primary=True,
        effective_date=date(2025, 1, 1)), session)

    contacts = {c.id: c for c in await list_contacts(member.id, session)}
    assert contacts[old.id].is_primary is False
    assert contacts[old.id].end_date is None  # demoted, not removed
    assert contacts[new.id].is_primary is True


# ── Bulk import ────────────────────────────────────────────────────────────────

CSV_HEADER = "member_number,first_name,last_name,date_of_birth,ssn,middle_name,gender,certification_date"


async def test_bulk_import_all_rows_created(session):
    csv_text = "\n".join([
        CSV_HEADER,
        "M-100,Jane,Smith,1970-05-01,123456789,Ann,F,2020-08-15",
        "M-101,Bob,Jones,1980-02-02,987654321,,,",
    ])
    result = await bulk_import_members(csv_text, session)

    assert result.total_rows == 2
    assert result.created_count == 2
    assert result.error_count == 0

    members = await list_members(session)
    assert {m.member_number for m in members} == {"M-100", "M-101"}
    jane = next(m for m in members if m.member_number == "M-100")
    assert jane.ssn_last_four == "6789"
    assert jane.certification_date == date(2020, 8, 15)
    bob = next(m for m in members if m.member_number == "M-101")
    assert bob.middle_name is None


async def test_bulk_import_partial_success(session):
    await _make_member(session, "M-1")  # unique SSN for M-1; member_number collides with row 3
    csv_text = "\n".join([
        CSV_HEADER,
        "M-200,Jane,Smith,1970-05-01,999887777,,,",     # ok (distinct SSN)
        "M-1,Dupe,Existing,1970-01-01,111223333,,,",    # member_number already exists
        "M-201,Bad,Ssn,1970-01-01,12345,,,",            # invalid SSN
        "M-202,Bad,Date,not-a-date,999887777,,,",       # invalid date (caught before SSN check)
        "M-200,Dupe,InFile,1970-01-01,111223333,,,",    # dupe within file
        ",NoNumber,Person,1970-01-01,111223333,,,",     # missing member_number
    ])
    result = await bulk_import_members(csv_text, session)

    assert result.total_rows == 6
    assert result.created_count == 1
    assert result.error_count == 5
    errors_by_row = {e.row: e for e in result.errors}
    assert errors_by_row[3].error == "member_number already exists"
    assert "ssn" in errors_by_row[4].error
    assert "date_of_birth" in errors_by_row[5].error
    assert errors_by_row[6].error == "duplicate member_number within file"
    assert errors_by_row[7].error == "member_number is required"

    members = await list_members(session)
    assert {m.member_number for m in members} == {"M-1", "M-200"}


async def test_bulk_import_missing_required_column(session):
    csv_text = "member_number,first_name,last_name\nM-1,Jane,Smith"
    with pytest.raises(ValueError, match="date_of_birth"):
        await bulk_import_members(csv_text, session)


# ── SSN duplicate detection ────────────────────────────────────────────────────

async def test_create_member_sets_ssn_hash(session):
    from app.crypto import hash_ssn
    member = await _make_member(session)
    assert member.ssn_hash == hash_ssn(_unique_ssn("M-1001"))


async def test_create_member_rejects_duplicate_ssn(session):
    await _make_member(session, "M-1")
    dup_ssn = _unique_ssn("M-1")
    with pytest.raises(ValueError, match="SSN already exists"):
        await create_member(
            MemberCreate(member_number="M-2", first_name="Dup", last_name="SSN",
                         date_of_birth=date(1980, 1, 1), ssn=dup_ssn),
            session,
        )


async def test_bulk_import_rejects_ssn_duplicate_in_system(session):
    m1 = await _make_member(session, "M-1")
    m1_ssn = _unique_ssn("M-1")
    csv_text = "\n".join([
        CSV_HEADER,
        f"M-200,Jane,Smith,1970-05-01,{m1_ssn},,,",  # SSN matches M-1
    ])
    result = await bulk_import_members(csv_text, session)
    assert result.created_count == 0
    assert result.errors[0].error == "SSN already exists in system"


async def test_bulk_import_rejects_ssn_duplicate_within_file(session):
    csv_text = "\n".join([
        CSV_HEADER,
        "M-200,Jane,Smith,1970-05-01,123456789,,,",
        "M-201,Bob,Jones,1980-01-01,123456789,,,",   # same SSN as M-200
    ])
    result = await bulk_import_members(csv_text, session)
    assert result.created_count == 1
    assert result.errors[0].error == "duplicate SSN within file"


# ── Name change history ────────────────────────────────────────────────────────

async def test_update_name_records_history(session):
    import uuid
    member = await _make_member(session, first="Jane", last="Smith")
    updated = await update_name(
        member.id,
        first_name="Jane",
        last_name="Doe",
        effective_date=date(2025, 6, 1),
        reason="legal_change",
        changed_by=uuid.uuid4(),
        session=session,
    )

    assert updated.last_name == "Doe"

    from sqlalchemy import select as sa_select
    from app.models.member_name_history import MemberNameHistory
    rows = (await session.execute(
        sa_select(MemberNameHistory).where(MemberNameHistory.member_id == member.id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].last_name == "Smith"   # previous name captured
    assert rows[0].reason == "legal_change"
    assert rows[0].effective_date == date(2025, 6, 1)


async def test_update_name_multiple_changes_build_history(session):
    member = await _make_member(session, first="Alice", last="Walker")
    await update_name(member.id, first_name="Alice", last_name="Baker",
                      effective_date=date(2020, 1, 1), reason="legal_change",
                      changed_by=None, session=session)
    await update_name(member.id, first_name="Alice", last_name="Carter",
                      effective_date=date(2024, 6, 1), reason="legal_change",
                      changed_by=None, session=session)

    from sqlalchemy import select as sa_select
    from app.models.member_name_history import MemberNameHistory
    rows = (await session.execute(
        sa_select(MemberNameHistory).where(MemberNameHistory.member_id == member.id)
        .order_by(MemberNameHistory.effective_date)
    )).scalars().all()

    assert len(rows) == 2
    assert rows[0].last_name == "Walker"
    assert rows[1].last_name == "Baker"

    fresh = await session.get(type(member), member.id)
    assert fresh.last_name == "Carter"


async def test_update_name_unknown_member_raises(session):
    import uuid
    with pytest.raises(ValueError, match="Member not found"):
        await update_name(uuid.uuid4(), first_name="X", last_name="Y",
                          effective_date=date(2025, 1, 1), reason="legal_change",
                          changed_by=None, session=session)

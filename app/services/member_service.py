import csv
import io
import uuid
from datetime import timedelta

from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crypto import encrypt_ssn
from app.models.address import MemberAddress
from app.models.contact import MemberContact
from app.models.employment import EmploymentRecord
from app.models.member import Member
from app.schemas.address import MemberAddressCreate
from app.schemas.contact import MemberContactCreate
from app.schemas.member import (
    MemberCreate,
    MemberImportResult,
    MemberImportRowError,
)


async def create_member(data: MemberCreate, session: AsyncSession) -> Member:
    member = Member(
        ssn_encrypted=encrypt_ssn(data.ssn),
        ssn_last_four=data.ssn[-4:],
        **data.model_dump(exclude={"ssn"}),
    )
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return member


async def get_member(member_id: uuid.UUID, session: AsyncSession) -> Member | None:
    result = await session.execute(select(Member).where(Member.id == member_id))
    return result.scalar_one_or_none()


async def list_members(
    session: AsyncSession,
    *,
    status: str | None = None,
    employer_id: uuid.UUID | None = None,
    employment_type: str | None = None,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Member]:
    stmt = select(Member)
    if status:
        stmt = stmt.where(Member.member_status == status)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                Member.first_name.ilike(like),
                Member.last_name.ilike(like),
                Member.member_number.ilike(like),
            )
        )
    if employer_id or employment_type:
        stmt = stmt.join(EmploymentRecord, EmploymentRecord.member_id == Member.id).distinct()
        if employer_id:
            stmt = stmt.where(EmploymentRecord.employer_id == employer_id)
        if employment_type:
            stmt = stmt.where(EmploymentRecord.employment_type == employment_type)
    stmt = stmt.order_by(Member.last_name, Member.first_name).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ── Addresses ──────────────────────────────────────────────────────────────────

async def list_addresses(member_id: uuid.UUID, session: AsyncSession) -> list[MemberAddress]:
    result = await session.execute(
        select(MemberAddress)
        .where(MemberAddress.member_id == member_id)
        .order_by(MemberAddress.effective_date.desc())
    )
    return list(result.scalars().all())


async def add_address(
    member_id: uuid.UUID, data: MemberAddressCreate, session: AsyncSession
) -> MemberAddress:
    """Add an address, end-dating any active address of the same type.

    One active address per type is an invariant the document context
    providers rely on (they pick the latest row with no end_date).
    """
    if not await get_member(member_id, session):
        raise ValueError("Member not found")

    result = await session.execute(
        select(MemberAddress).where(
            MemberAddress.member_id == member_id,
            MemberAddress.address_type == data.address_type,
            MemberAddress.end_date.is_(None),
        )
    )
    for previous in result.scalars():
        previous.end_date = data.effective_date - timedelta(days=1)

    address = MemberAddress(member_id=member_id, **data.model_dump())
    session.add(address)
    await session.commit()
    await session.refresh(address)
    return address


# ── Contacts ───────────────────────────────────────────────────────────────────

async def list_contacts(member_id: uuid.UUID, session: AsyncSession) -> list[MemberContact]:
    result = await session.execute(
        select(MemberContact)
        .where(MemberContact.member_id == member_id)
        .order_by(MemberContact.effective_date.desc())
    )
    return list(result.scalars().all())


async def add_contact(
    member_id: uuid.UUID, data: MemberContactCreate, session: AsyncSession
) -> MemberContact:
    """Add a contact. Unlike addresses, multiple active contacts of one type
    are allowed (e.g. home + mobile phone) unless supersede is set."""
    if not await get_member(member_id, session):
        raise ValueError("Member not found")

    result = await session.execute(
        select(MemberContact).where(
            MemberContact.member_id == member_id,
            MemberContact.contact_type == data.contact_type,
            MemberContact.end_date.is_(None),
        )
    )
    active_same_type = list(result.scalars())
    if data.supersede:
        for previous in active_same_type:
            previous.end_date = data.effective_date - timedelta(days=1)
    elif data.is_primary:
        for previous in active_same_type:
            previous.is_primary = False

    contact = MemberContact(member_id=member_id, **data.model_dump(exclude={"supersede"}))
    session.add(contact)
    await session.commit()
    await session.refresh(contact)
    return contact


# ── Bulk import ────────────────────────────────────────────────────────────────

# Optional columns: middle_name, suffix, gender, member_status, status_date,
# certification_date (dates in ISO format)
IMPORT_REQUIRED_COLUMNS = {"member_number", "first_name", "last_name", "date_of_birth", "ssn"}


async def bulk_import_members(csv_text: str, session: AsyncSession) -> MemberImportResult:
    """Create members from CSV with partial success: bad rows are reported,
    good rows are committed. Mirrors the payroll CSV intake pattern."""
    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    fieldnames = set(reader.fieldnames or [])
    missing = IMPORT_REQUIRED_COLUMNS - fieldnames
    if missing:
        raise ValueError(f"CSV missing required columns: {', '.join(sorted(missing))}")

    raw_rows = list(reader)

    batch_numbers = [(r.get("member_number") or "").strip() for r in raw_rows]
    existing_result = await session.execute(
        select(Member.member_number).where(Member.member_number.in_([n for n in batch_numbers if n]))
    )
    existing_numbers = set(existing_result.scalars())

    errors: list[MemberImportRowError] = []
    seen_in_batch: set[str] = set()
    created = 0

    for line, raw in enumerate(raw_rows, start=2):  # header is line 1
        values = {
            k: v.strip()
            for k, v in raw.items()
            if k is not None and v is not None and v.strip() != ""
        }
        member_number = values.get("member_number")

        error: str | None = None
        if not member_number:
            error = "member_number is required"
        elif member_number in existing_numbers:
            error = "member_number already exists"
        elif member_number in seen_in_batch:
            error = "duplicate member_number within file"

        data: MemberCreate | None = None
        if error is None:
            try:
                data = MemberCreate(**values)
            except ValidationError as exc:
                error = "; ".join(f"{e['loc'][0]}: {e['msg']}" for e in exc.errors())

        if error is not None or data is None:
            errors.append(MemberImportRowError(row=line, member_number=member_number, error=error or "invalid row"))
            continue

        session.add(
            Member(
                ssn_encrypted=encrypt_ssn(data.ssn),
                ssn_last_four=data.ssn[-4:],
                **data.model_dump(exclude={"ssn"}),
            )
        )
        seen_in_batch.add(member_number)
        created += 1

    await session.commit()
    return MemberImportResult(
        total_rows=len(raw_rows),
        created_count=created,
        error_count=len(errors),
        errors=errors,
    )

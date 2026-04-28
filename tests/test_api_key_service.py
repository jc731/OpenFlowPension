"""Tests for API key management service."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import api_key_service

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# create_key
# ---------------------------------------------------------------------------

async def test_create_key_returns_row_and_plaintext(session: AsyncSession):
    row, plaintext = await api_key_service.create_key(
        name="Test Key",
        scopes=["member:read"],
        session=session,
    )
    assert row.id is not None
    assert row.name == "Test Key"
    assert row.active is True
    assert row.scopes == ["member:read"]
    assert plaintext.startswith("ofp_")
    assert len(plaintext) > 12


async def test_create_key_stores_prefix_not_plaintext(session: AsyncSession):
    row, plaintext = await api_key_service.create_key(
        name="Prefix Check",
        scopes=["*"],
        session=session,
    )
    assert row.key_prefix == plaintext[:12]
    # hash stored, not plaintext
    assert row.key_hash != plaintext
    assert len(row.key_hash) == 64  # SHA-256 hex


async def test_create_key_rejects_empty_name(session: AsyncSession):
    with pytest.raises(ValueError, match="cannot be empty"):
        await api_key_service.create_key(name="  ", scopes=["*"], session=session)


async def test_create_key_rejects_empty_scopes(session: AsyncSession):
    with pytest.raises(ValueError, match="at least one scope"):
        await api_key_service.create_key(name="No Scopes", scopes=[], session=session)


async def test_create_key_with_expiry(session: AsyncSession):
    expires = datetime.now(timezone.utc) + timedelta(days=90)
    row, _ = await api_key_service.create_key(
        name="Expiring Key",
        scopes=["payroll:write"],
        session=session,
        expires_at=expires,
    )
    assert row.expires_at is not None


# ---------------------------------------------------------------------------
# validate_key
# ---------------------------------------------------------------------------

async def test_validate_key_valid(session: AsyncSession):
    row, plaintext = await api_key_service.create_key(
        name="Valid Key",
        scopes=["member:read"],
        session=session,
    )
    found = await api_key_service.validate_key(plaintext, session)
    assert found is not None
    assert found.id == row.id


async def test_validate_key_updates_last_used_at(session: AsyncSession):
    row, plaintext = await api_key_service.create_key(
        name="Usage Tracking",
        scopes=["*"],
        session=session,
    )
    assert row.last_used_at is None
    await api_key_service.validate_key(plaintext, session)
    assert row.last_used_at is not None


async def test_validate_key_wrong_key_returns_none(session: AsyncSession):
    result = await api_key_service.validate_key("ofp_totally_fake_key", session)
    assert result is None


async def test_validate_key_revoked_returns_none(session: AsyncSession):
    row, plaintext = await api_key_service.create_key(
        name="Revoked Key",
        scopes=["*"],
        session=session,
    )
    await api_key_service.revoke_key(row.id, session)
    result = await api_key_service.validate_key(plaintext, session)
    assert result is None


async def test_validate_key_expired_returns_none(session: AsyncSession):
    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    row, plaintext = await api_key_service.create_key(
        name="Expired Key",
        scopes=["*"],
        session=session,
        expires_at=past,
    )
    result = await api_key_service.validate_key(plaintext, session)
    assert result is None


# ---------------------------------------------------------------------------
# revoke_key
# ---------------------------------------------------------------------------

async def test_revoke_key(session: AsyncSession):
    row, _ = await api_key_service.create_key(
        name="To Revoke",
        scopes=["*"],
        session=session,
    )
    revoked = await api_key_service.revoke_key(row.id, session)
    assert revoked.active is False


async def test_revoke_already_revoked_raises(session: AsyncSession):
    row, _ = await api_key_service.create_key(
        name="Already Revoked",
        scopes=["*"],
        session=session,
    )
    await api_key_service.revoke_key(row.id, session)
    with pytest.raises(ValueError, match="already revoked"):
        await api_key_service.revoke_key(row.id, session)


# ---------------------------------------------------------------------------
# rotate_key
# ---------------------------------------------------------------------------

async def test_rotate_key_produces_new_key(session: AsyncSession):
    row, old_plaintext = await api_key_service.create_key(
        name="Rotatable",
        scopes=["member:read", "member:write"],
        session=session,
    )
    new_row, new_plaintext = await api_key_service.rotate_key(row.id, session)

    assert new_row.id != row.id
    assert new_plaintext != old_plaintext
    assert new_row.active is True
    assert new_row.scopes == row.scopes


async def test_rotate_key_deactivates_old(session: AsyncSession):
    row, _ = await api_key_service.create_key(
        name="Old Key",
        scopes=["*"],
        session=session,
    )
    await api_key_service.rotate_key(row.id, session)
    await session.refresh(row)
    assert row.active is False


async def test_rotate_revoked_key_raises(session: AsyncSession):
    row, _ = await api_key_service.create_key(
        name="Dead Key",
        scopes=["*"],
        session=session,
    )
    await api_key_service.revoke_key(row.id, session)
    with pytest.raises(ValueError, match="already revoked"):
        await api_key_service.rotate_key(row.id, session)


# ---------------------------------------------------------------------------
# list_keys
# ---------------------------------------------------------------------------

async def test_list_keys_excludes_revoked_by_default(session: AsyncSession):
    row1, _ = await api_key_service.create_key(name="Active", scopes=["*"], session=session)
    row2, _ = await api_key_service.create_key(name="Revoked", scopes=["*"], session=session)
    await api_key_service.revoke_key(row2.id, session)

    active = await api_key_service.list_keys(session)
    ids = [r.id for r in active]
    assert row1.id in ids
    assert row2.id not in ids


async def test_list_keys_include_revoked(session: AsyncSession):
    row1, _ = await api_key_service.create_key(name="Active", scopes=["*"], session=session)
    row2, _ = await api_key_service.create_key(name="Revoked", scopes=["*"], session=session)
    await api_key_service.revoke_key(row2.id, session)

    all_keys = await api_key_service.list_keys(session, include_revoked=True)
    ids = [r.id for r in all_keys]
    assert row1.id in ids
    assert row2.id in ids

"""API key management service.

Keys use a 'ofp_' prefix followed by 64 random hex chars (32 random bytes).
Only the SHA-256 hash is stored. The plaintext is returned once at creation/rotation
and never retrievable again.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiKey

_KEY_PREFIX = "ofp_"
_PREFIX_DISPLAY_LEN = 12  # 'ofp_' + 8 random chars shown in UI


def _generate_plaintext() -> str:
    return _KEY_PREFIX + secrets.token_hex(32)


def _hash_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


def _prefix(plaintext: str) -> str:
    return plaintext[:_PREFIX_DISPLAY_LEN]


# ── CRUD ───────────────────────────────────────────────────────────────────────

async def create_key(
    name: str,
    scopes: list[str],
    session: AsyncSession,
    expires_at: datetime | None = None,
    created_by: uuid.UUID | None = None,
    note: str | None = None,
) -> tuple[ApiKey, str]:
    """Create and store a new API key.

    Returns (ApiKey row, plaintext_key). The plaintext is not recoverable after
    this call — the caller must present it to the user immediately.
    """
    if not name.strip():
        raise ValueError("API key name cannot be empty")
    if not scopes:
        raise ValueError("API key must have at least one scope")

    plaintext = _generate_plaintext()
    row = ApiKey(
        name=name.strip(),
        key_prefix=_prefix(plaintext),
        key_hash=_hash_key(plaintext),
        scopes=scopes,
        expires_at=expires_at,
        created_by=created_by,
        note=note,
    )
    session.add(row)
    await session.flush()
    return row, plaintext


async def validate_key(plaintext: str, session: AsyncSession) -> ApiKey | None:
    """Return the ApiKey if valid and active; None otherwise. Updates last_used_at."""
    key_hash = _hash_key(plaintext)
    stmt = select(ApiKey).where(ApiKey.key_hash == key_hash)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()

    if row is None:
        return None
    if not row.active:
        return None
    if row.expires_at is not None and row.expires_at < datetime.now(timezone.utc):
        return None

    row.last_used_at = datetime.now(timezone.utc)
    await session.flush()
    return row


async def revoke_key(key_id: uuid.UUID, session: AsyncSession) -> ApiKey:
    """Permanently deactivate a key. Cannot be undone (create a new key instead)."""
    row = await _get_or_raise(key_id, session)
    if not row.active:
        raise ValueError(f"API key {key_id} is already revoked")
    row.active = False
    await session.flush()
    return row


async def rotate_key(key_id: uuid.UUID, session: AsyncSession) -> tuple[ApiKey, str]:
    """Revoke a key and return a new one with the same name/scopes/expiry.

    Returns (new ApiKey row, new_plaintext_key).
    """
    old = await _get_or_raise(key_id, session)
    if not old.active:
        raise ValueError(f"API key {key_id} is already revoked — cannot rotate")

    old.active = False
    await session.flush()

    new_row, new_plaintext = await create_key(
        name=f"{old.name} (rotated)",
        scopes=old.scopes,
        session=session,
        expires_at=old.expires_at,
        created_by=old.created_by,
        note=old.note,
    )
    return new_row, new_plaintext


async def get_key(key_id: uuid.UUID, session: AsyncSession) -> ApiKey:
    return await _get_or_raise(key_id, session)


async def list_keys(session: AsyncSession, include_revoked: bool = False) -> list[ApiKey]:
    stmt = select(ApiKey).order_by(ApiKey.created_at.desc())
    if not include_revoked:
        stmt = stmt.where(ApiKey.active.is_(True))
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ── Internal ───────────────────────────────────────────────────────────────────

async def _get_or_raise(key_id: uuid.UUID, session: AsyncSession) -> ApiKey:
    row = await session.get(ApiKey, key_id)
    if not row:
        raise ValueError(f"API key {key_id} not found")
    return row

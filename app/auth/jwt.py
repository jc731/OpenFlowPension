"""Keycloak JWT validation.

Fetches the realm's JWKS on first use, caches it for 5 minutes, and
refreshes automatically when an unknown key ID is encountered (handles
key rotation without a restart).

Scopes are read from realm_access.roles and resource_access.*.roles in
the token payload. The "admin" role maps to ["*"] (all permissions).
"""

import asyncio
import time
from typing import Any

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm
from jwt.exceptions import InvalidTokenError

from app.config import settings

_JWKS_TTL = 300  # seconds between JWKS refreshes

_cache_lock = asyncio.Lock()
_jwks_keys: dict[str, Any] = {}   # kid → JWK dict
_jwks_fetched_at: float = 0.0

_KNOWN_SCOPES = frozenset({
    "member:read",
    "member:write",
    "employment:write",
    "service_credit:write",
    "payroll:write",
    "benefit:calculate",
})


async def _fetch_jwks() -> dict[str, Any]:
    url = (
        f"{settings.keycloak_url}/realms/{settings.keycloak_realm}"
        "/protocol/openid-connect/certs"
    )
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        raise InvalidTokenError(f"Could not fetch JWKS from Keycloak: {exc}") from exc
    return {k["kid"]: k for k in data.get("keys", [])}


async def _get_keys(*, force: bool = False) -> dict[str, Any]:
    global _jwks_keys, _jwks_fetched_at
    now = time.monotonic()
    if not force and _jwks_keys and (now - _jwks_fetched_at) < _JWKS_TTL:
        return _jwks_keys
    async with _cache_lock:
        # Re-check after acquiring lock in case another coroutine already refreshed
        if not force and _jwks_keys and (now - _jwks_fetched_at) < _JWKS_TTL:
            return _jwks_keys
        _jwks_keys = await _fetch_jwks()
        _jwks_fetched_at = time.monotonic()
    return _jwks_keys


async def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a Keycloak-issued JWT. Raises InvalidTokenError on any failure."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.exceptions.DecodeError as exc:
        raise InvalidTokenError("Malformed JWT") from exc

    kid = header.get("kid", "")
    keys = await _get_keys()

    if kid not in keys:
        # Unknown kid — Keycloak may have rotated; refresh once before failing
        keys = await _get_keys(force=True)
        if kid not in keys:
            raise InvalidTokenError(f"Unknown signing key id: {kid!r}")

    public_key = RSAAlgorithm.from_jwk(keys[kid])
    issuer = f"{settings.keycloak_url}/realms/{settings.keycloak_realm}"

    if settings.keycloak_audience:
        return jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            issuer=issuer,
            audience=settings.keycloak_audience,
        )
    else:
        return jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"verify_aud": False},
        )


def extract_scopes(payload: dict[str, Any]) -> list[str]:
    """Map Keycloak realm/client roles to OpenFlow scope strings."""
    roles: set[str] = set()

    realm_access = payload.get("realm_access") or {}
    roles.update(realm_access.get("roles", []))

    resource_access = payload.get("resource_access") or {}
    for client in resource_access.values():
        roles.update(client.get("roles", []))

    if "admin" in roles:
        return ["*"]

    return sorted(roles & _KNOWN_SCOPES)

from collections.abc import Callable
from typing import TypedDict

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import decode_token, extract_scopes
from app.config import settings
from app.database import get_session
from app.services import api_key_service

_bearer = HTTPBearer(auto_error=False)

_API_KEY_PREFIX = "ofp_"


class Principal(TypedDict):
    id: str
    principal_type: str  # 'user' | 'api_key'
    scopes: list[str]


def require_scope(*scopes: str) -> Callable:
    """Return a FastAPI dependency that enforces at least one of the given scopes.

    Usage — when the principal is needed in the handler:
        principal: Principal = Depends(require_scope("member:write"))

    Usage — when the principal is not needed (read-only endpoints):
        @router.get("/", dependencies=[Depends(require_scope("member:read"))])
    """
    async def _check(principal: Principal = Depends(get_current_user)) -> Principal:
        if "*" in principal["scopes"] or any(s in principal["scopes"] for s in scopes):
            return principal
        raise HTTPException(
            status_code=403,
            detail=f"Insufficient permissions. Required: {' or '.join(scopes)}",
        )
    return _check


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> Principal:
    """Resolve the caller's identity.

    Resolution order:
      1. Bearer ofp_… — API key, hashed and looked up in api_keys table.
      2. Bearer <jwt> — Keycloak JWT; requires KEYCLOAK_URL to be configured.
      3. No header + environment=development — dev-admin stub (never in production).
    """
    if credentials is not None:
        token = credentials.credentials

        if token.startswith(_API_KEY_PREFIX):
            key_row = await api_key_service.validate_key(token, session)
            if key_row is None:
                raise HTTPException(
                    status_code=401,
                    detail="Invalid or expired API key",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return Principal(
                id=str(key_row.id),
                principal_type="api_key",
                scopes=list(key_row.scopes),
            )

        # Not an API key — treat as a JWT
        if not settings.keycloak_url:
            raise HTTPException(
                status_code=401,
                detail="JWT authentication is not configured on this server",
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            payload = await decode_token(token)
        except InvalidTokenError as exc:
            raise HTTPException(
                status_code=401,
                detail=f"Invalid token: {exc}",
                headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            ) from exc

        return Principal(
            id=payload.get("sub", ""),
            principal_type="user",
            scopes=extract_scopes(payload),
        )

    # No credentials
    if settings.environment == "development":
        return Principal(id="dev-admin", principal_type="user", scopes=["*"])

    raise HTTPException(
        status_code=401,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )

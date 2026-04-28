from typing import TypedDict

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.services import api_key_service

_bearer = HTTPBearer(auto_error=False)


class Principal(TypedDict):
    id: str
    principal_type: str  # 'user' | 'api_key'
    scopes: list[str]


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> Principal:
    """Validate the incoming request and return the caller's Principal.

    Auth paths:
      1. Bearer <api_key> — hashed and looked up in the api_keys table.
      2. No header + environment=development — returns the admin dev stub.
         This bypass is explicitly disabled in production.

    Keycloak JWT validation will be wired here when human-user auth ships.
    The Principal shape (id, principal_type, scopes) does not change.
    """
    if credentials is not None:
        key_row = await api_key_service.validate_key(credentials.credentials, session)
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

    # No credentials supplied
    if settings.environment == "development":
        return Principal(id="dev-admin", principal_type="user", scopes=["*"])

    raise HTTPException(
        status_code=401,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )

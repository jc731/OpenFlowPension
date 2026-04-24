from typing import TypedDict


class Principal(TypedDict):
    id: str
    principal_type: str  # 'user' | 'api_key'
    scopes: list[str]


def get_current_user() -> Principal:
    # Stub — replace with Keycloak JWT validation (users) or API key lookup (systems).
    # Routers depend on this shape: id, principal_type, scopes.
    # '*' in scopes means all permissions granted (admin/dev only).
    return Principal(id="admin", principal_type="user", scopes=["*"])

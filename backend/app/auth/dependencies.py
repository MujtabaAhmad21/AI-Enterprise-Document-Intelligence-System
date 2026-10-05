"""Identity dependencies. SEC-001, SEC-023..SEC-025.

Every /api/v1/* route except POST /api/v1/auth/token depends on `get_current_user`
(SEC-001) via the router-level dependency wired in main.py, not per-endpoint decoration, so a
new route is protected by default.
"""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import InvalidTokenError, decode_access_token
from app.db.models import User
from app.db.session import get_db
from app.errors import AuthenticationError, AuthorizationError
from app.schemas.enums import UserRole

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if credentials is None:
        raise AuthenticationError("Missing bearer token.")
    try:
        claims = decode_access_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise AuthenticationError("Invalid or expired token.") from exc

    user = await session.get(User, claims.user_id)
    # SEC-025: role is read from the validated JWT claim, never re-derived from the row here —
    # but an inactive or deleted user must still be rejected (SEC-019).
    if user is None or not user.is_active:
        raise AuthenticationError("Invalid or expired token.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUser) -> User:
    """SEC-020..SEC-025: role is read from the validated JWT-backed User, not re-checked
    per-route. Route bodies never re-implement this condition."""
    if UserRole(user.role) is not UserRole.ADMIN:
        raise AuthorizationError(
            "This action requires the admin role.", details={"required_role": "admin"}
        )
    return user


AdminUser = Annotated[User, Depends(require_admin)]

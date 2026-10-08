"""Login. SEC-002, SEC-018, SEC-019."""

import hashlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import create_access_token
from app.auth.passwords import verify_dummy_password, verify_password
from app.db.models import User
from app.errors import AuthenticationError
from app.schemas.enums import AuditAction, AuditTargetType, UserRole
from app.schemas.errors import ErrorCode
from app.services.audit_service import record_audit_event

_INVALID_CREDENTIALS_MESSAGE = "Invalid email or password."


def _email_hash(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


async def authenticate(
    session: AsyncSession, *, email: str, password: str, client_ip: str | None
) -> tuple[User, str, int]:
    """SEC-018: "unknown email" and "wrong password" are indistinguishable in message, status,
    and timing. Returns (user, access_token, expires_in_seconds) or raises AuthenticationError.
    """
    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()

    # SEC-019: an inactive user fails identically to bad credentials.
    if user is None or not user.is_active:
        verify_dummy_password()
        await record_audit_event(
            session,
            action=AuditAction.AUTH_LOGIN_FAILED,
            target_type=AuditTargetType.SYSTEM,
            metadata={"email_hash": _email_hash(email), "client_ip": client_ip},
        )
        raise AuthenticationError(_INVALID_CREDENTIALS_MESSAGE, code=ErrorCode.INVALID_CREDENTIALS)

    if not verify_password(password, user.password_hash):
        await record_audit_event(
            session,
            action=AuditAction.AUTH_LOGIN_FAILED,
            target_type=AuditTargetType.SYSTEM,
            metadata={"email_hash": _email_hash(email), "client_ip": client_ip},
        )
        raise AuthenticationError(_INVALID_CREDENTIALS_MESSAGE, code=ErrorCode.INVALID_CREDENTIALS)

    token, expires_in = create_access_token(user_id=user.id, role=UserRole(user.role))
    await record_audit_event(
        session,
        action=AuditAction.AUTH_LOGIN_SUCCEEDED,
        target_type=AuditTargetType.USER,
        actor_id=user.id,
        target_id=user.id,
        metadata={"client_ip": client_ip},
    )
    return user, token, expires_in

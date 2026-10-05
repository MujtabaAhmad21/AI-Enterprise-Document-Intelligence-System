"""JWT issue/verify. SEC-004, SEC-017."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.config import settings
from app.schemas.enums import UserRole

# SEC-004/SEC-017: pinned to HS256. Passed as the sole entry of `algorithms=` on decode, which
# is what actually pins it — a caller-supplied `alg` of `none` or an asymmetric algorithm is
# rejected before any claim is read.
ALGORITHM = "HS256"


class InvalidTokenError(Exception):
    """Signature invalid, expired, or malformed — never distinguished further to the client."""


@dataclass(frozen=True)
class TokenClaims:
    user_id: uuid.UUID
    role: UserRole
    jti: str


def create_access_token(*, user_id: uuid.UUID, role: UserRole) -> tuple[str, int]:
    now = datetime.now(UTC)
    expires_in = settings.jwt_expire_minutes * 60
    payload = {
        "sub": str(user_id),
        "role": role.value,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(payload, settings.jwt_secret_key.get_secret_value(), algorithm=ALGORITHM)
    return token, expires_in


def decode_access_token(token: str) -> TokenClaims:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key.get_secret_value(), algorithms=[ALGORITHM]
        )
        return TokenClaims(
            user_id=uuid.UUID(payload["sub"]),
            role=UserRole(payload["role"]),
            jti=payload["jti"],
        )
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise InvalidTokenError(str(exc)) from exc

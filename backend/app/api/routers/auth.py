"""POST /api/v1/auth/token. API-001. Public — not mounted under the protected /api/v1
aggregator (SEC-001)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import authenticate
from app.db.session import get_db
from app.middleware.rate_limit import rate_limited_by_ip
from app.schemas.auth import LoginRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# SEC-011a: credential stuffing — AUTH_RATE_LIMIT_PER_MINUTE per IP. Keyed by IP, not user,
# since there is no authenticated identity yet on this public route.
_auth_rate_limit = Depends(
    rate_limited_by_ip(limit_attr="auth_rate_limit_per_minute", window_seconds=60)
)


@router.post(
    "/token", response_model=TokenResponse, operation_id="login", dependencies=[_auth_rate_limit]
)
async def issue_token(
    body: LoginRequest, request: Request, session: Annotated[AsyncSession, Depends(get_db)]
) -> TokenResponse:
    user, access_token, expires_in = await authenticate(
        session,
        email=body.email,
        password=body.password,
        client_ip=request.client.host if request.client else None,
    )
    return TokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        user=UserResponse.model_validate(user),
    )

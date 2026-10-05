"""GET /api/v1/users/me. API-002. Mounted under the protected /api/v1 aggregator (SEC-001)."""

from fastapi import APIRouter

from app.auth.dependencies import CurrentUser
from app.schemas.auth import UserResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse, operation_id="get_current_user")
async def read_current_user(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)

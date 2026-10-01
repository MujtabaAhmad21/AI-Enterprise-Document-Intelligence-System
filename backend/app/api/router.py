"""The protected /api/v1 aggregator. SEC-001: every route mounted here requires
`get_current_user` by construction — a new router included here is protected by default,
with no per-endpoint decoration to forget.
"""

from fastapi import APIRouter, Depends

from app.api.routers import answers, chunks, documents, search, users
from app.auth.dependencies import get_current_user
from app.middleware.rate_limit import rate_limited_by_user

# SEC-011: a default per-user limit applies to every /api/v1/* route by construction, the same
# "protected by default" guarantee SEC-001 already gives get_current_user. Documents-upload,
# answers, and search additionally carry their own tighter, route-specific limit (see those
# routers) — a request there is checked against two counters, which is harmless since the
# specific one is always stricter and trips first.
api_v1_router = APIRouter(
    prefix="/api/v1",
    dependencies=[
        Depends(get_current_user),
        Depends(
            rate_limited_by_user(limit_attr="default_rate_limit_per_hour", window_seconds=3600)
        ),
    ],
)
api_v1_router.include_router(users.router)
api_v1_router.include_router(documents.router)
api_v1_router.include_router(search.router)
api_v1_router.include_router(answers.router)
api_v1_router.include_router(chunks.chunks_router)
api_v1_router.include_router(chunks.citations_router)

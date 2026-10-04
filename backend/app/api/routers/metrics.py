"""GET /metrics. OBSERVABILITY.md §5: Prometheus exposition, "bound to an internal interface
or protected by METRICS_TOKEN". Outside /api/v1 like health.py — a scrape target is
infrastructure, not a business operation, and MUST NOT require a user JWT.
"""

import hmac

from fastapi import APIRouter, HTTPException, Request, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.config import settings

router = APIRouter(tags=["metrics"])


@router.get("/metrics", operation_id="get_metrics")
async def metrics(request: Request) -> Response:
    if settings.metrics_token is not None:
        expected = f"Bearer {settings.metrics_token.get_secret_value()}"
        presented = request.headers.get("Authorization", "")
        # Constant-time: a scrape token is still a credential (ENV-... METRICS_TOKEN is `S`,
        # secret-classified), and comparing it with `==` leaks its length/prefix via timing.
        if not hmac.compare_digest(presented, expected):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

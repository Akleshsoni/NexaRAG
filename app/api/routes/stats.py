from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, rate_limit
from app.db.session import get_db
from app.models.models import Document, QueryLog
from app.services import cache

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("")
async def get_stats(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit),
):
    """Per-tenant usage numbers computed from PostgreSQL.

    `failed` queries is a Redis counter (incremented when retrieval or the LLM fails);
    failed requests are not stored in query_logs, so it resets if Redis is wiped.
    """
    status_rows = await db.execute(
        select(Document.status, func.count()).where(Document.tenant_id == user.tenant_id).group_by(Document.status)
    )
    by_status = {getattr(s, "value", s): n for s, n in status_rows}

    q = await db.execute(
        select(
            func.count(QueryLog.id),
            func.coalesce(func.avg(QueryLog.latency_ms), 0),
            func.coalesce(func.sum(QueryLog.input_tokens), 0),
            func.coalesce(func.sum(QueryLog.output_tokens), 0),
        ).where(QueryLog.tenant_id == user.tenant_id)
    )
    total, avg_latency, tokens_in, tokens_out = q.one()

    return {
        "documents": {
            "total": sum(by_status.values()),
            "ready": by_status.get("ready", 0),
            "failed": by_status.get("failed", 0),
            "processing": by_status.get("processing", 0) + by_status.get("pending", 0),
        },
        "queries": {
            "total": total,
            "avg_latency_ms": round(float(avg_latency)),
            "total_tokens_used": int(tokens_in) + int(tokens_out),
            "failed": await cache.get_failed_queries(user.tenant_id),
        },
    }

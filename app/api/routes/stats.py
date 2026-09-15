"""Analytics/statistics endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user
from app.db.session import get_db
from app.models.models import Document, DocumentStatus, QueryLog

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("")
async def get_stats(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return analytics for the current tenant only."""

    document_counts = await db.execute(
        select(Document.status, func.count(Document.id))
        .where(Document.tenant_id == user.tenant_id)
        .group_by(Document.status)
    )

    status_counts = {
        status.value: count
        for status, count in document_counts.all()
    }

    total_documents = sum(status_counts.values())
    ready_documents = status_counts.get(DocumentStatus.READY.value, 0)
    failed_documents = status_counts.get(DocumentStatus.FAILED.value, 0)

    query_count = await db.execute(
        select(func.count(QueryLog.id))
        .where(QueryLog.tenant_id == user.tenant_id)
    )
    total_queries = query_count.scalar_one()

    avg_latency_result = await db.execute(
        select(func.avg(QueryLog.latency_ms))
        .where(QueryLog.tenant_id == user.tenant_id)
    )
    avg_latency = avg_latency_result.scalar_one()

    token_result = await db.execute(
        select(
            func.coalesce(func.sum(QueryLog.input_tokens), 0),
            func.coalesce(func.sum(QueryLog.output_tokens), 0),
        )
        .where(QueryLog.tenant_id == user.tenant_id)
    )

    input_tokens, output_tokens = token_result.one()
    total_tokens = int(input_tokens or 0) + int(output_tokens or 0)

    return {
        "documents": {
            "total": total_documents,
            "ready": ready_documents,
            "failed": failed_documents,
            "pending": status_counts.get(DocumentStatus.PENDING.value, 0),
            "processing": status_counts.get(DocumentStatus.PROCESSING.value, 0),
        },
        "queries": {
            "total": total_queries,
            "avg_latency_ms": round(float(avg_latency or 0), 2),
            "total_input_tokens": int(input_tokens or 0),
            "total_output_tokens": int(output_tokens or 0),
            "total_tokens_used": total_tokens,
        },
    }
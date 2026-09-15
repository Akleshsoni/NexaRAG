"""Query history endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user
from app.db.session import get_db
from app.models.models import QueryLog

router = APIRouter(prefix="/queries", tags=["query-history"])


@router.get("")
async def get_query_history(
    page: int = 1,
    limit: int = 10,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return paginated query history for the current tenant."""

    if page < 1:
        raise HTTPException(
            status_code=400,
            detail="Page must be >= 1.",
        )

    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=400,
            detail="Limit must be between 1 and 100.",
        )

    count_result = await db.execute(
        select(func.count(QueryLog.id)).where(
            QueryLog.tenant_id == user.tenant_id
        )
    )
    total = count_result.scalar_one()

    total_pages = max(1, (total + limit - 1) // limit)
    offset = (page - 1) * limit

    result = await db.execute(
        select(QueryLog)
        .where(QueryLog.tenant_id == user.tenant_id)
        .order_by(QueryLog.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    items = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "items": [
            {
                "id": str(item.id),
                "question": item.question,
                "answer": item.answer,
                "latency_ms": item.latency_ms,
                "input_tokens": item.input_tokens,
                "output_tokens": item.output_tokens,
                "created_at": item.created_at.isoformat(),
            }
            for item in items
        ],
    }
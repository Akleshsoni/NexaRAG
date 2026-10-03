from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, rate_limit
from app.db.session import get_db
from app.models.models import QueryLog
from app.schemas.schemas import PaginatedQueries, QueryHistoryItem, total_pages

router = APIRouter(prefix="/queries", tags=["history"])


@router.get("", response_model=PaginatedQueries)
async def list_queries(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit),
):
    """Query history of the caller's tenant, newest first.

    QueryLog is keyed by tenant (not user): every user of a tenant sees the same
    history, and no tenant can see another's.
    """
    total = await db.scalar(select(func.count()).select_from(QueryLog).where(QueryLog.tenant_id == user.tenant_id))
    result = await db.execute(
        select(QueryLog)
        .where(QueryLog.tenant_id == user.tenant_id)
        .order_by(QueryLog.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    return PaginatedQueries(
        items=[QueryHistoryItem.model_validate(q) for q in result.scalars().all()],
        total=total or 0,
        page=page,
        limit=limit,
        total_pages=total_pages(total or 0, limit),
    )

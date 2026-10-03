"""Redis helpers: query-cache versioning, suggestion cache, failure counters.

The query cache key includes a per-tenant version number. Bumping the version
(on document delete / re-index / finished processing) invalidates every cached
answer for that tenant at once, so stale answers never outlive their sources.
"""
import redis
import redis.asyncio as aioredis

from app.core.config import settings

redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)


def _ver_key(tenant_id: str) -> str:
    return f"cache_ver:{tenant_id}"


async def get_cache_version(tenant_id: str) -> str:
    try:
        return (await redis_client.get(_ver_key(tenant_id))) or "0"
    except redis.RedisError:
        return "0"


async def bump_cache_version(tenant_id: str) -> None:
    try:
        await redis_client.incr(_ver_key(tenant_id))
    except redis.RedisError:
        pass


def bump_cache_version_sync(tenant_id: str) -> None:
    """Used from the Celery worker (sync context)."""
    try:
        client = redis.from_url(settings.redis_url)
        client.incr(_ver_key(tenant_id))
        client.close()
    except redis.RedisError:
        pass


async def forget_suggestions(document_id: str) -> None:
    try:
        await redis_client.delete(f"suggestions:{document_id}")
    except redis.RedisError:
        pass


async def count_failed_query(tenant_id: str) -> None:
    try:
        await redis_client.incr(f"failed_queries:{tenant_id}")
    except redis.RedisError:
        pass


async def get_failed_queries(tenant_id: str) -> int:
    try:
        return int(await redis_client.get(f"failed_queries:{tenant_id}") or 0)
    except (redis.RedisError, ValueError):
        return 0

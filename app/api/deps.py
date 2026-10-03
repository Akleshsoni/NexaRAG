import time
import uuid

import redis
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import ExpiredSignatureError, JWTError

from app.core.config import settings
from app.core.security import decode_access_token
from app.services.cache import redis_client

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


class CurrentUser:
    def __init__(self, user_id: str, tenant_id: str):
        self.user_id = user_id
        self.tenant_id = tenant_id


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(request: Request, token: str = Depends(oauth2_scheme)) -> CurrentUser:
    try:
        payload = decode_access_token(token)
    except ExpiredSignatureError as exc:
        raise _unauthorized("Token expired. Please log in again.") from exc
    except JWTError as exc:
        raise _unauthorized("Invalid token") from exc

    user_id, tenant_id = payload.get("sub"), payload.get("tenant_id")
    if not user_id or not tenant_id:
        raise _unauthorized("Invalid token")

    request.state.tenant_id = tenant_id  # picked up by the request-logging middleware
    return CurrentUser(user_id=user_id, tenant_id=tenant_id)


def make_rate_limiter(bucket: str, limit_attr: str):
    """Sliding-window limiter per user and bucket, backed by a Redis sorted set.

    The limit is read from settings on each request, so it is configurable through
    environment variables (e.g. RATE_LIMIT_QUERY_RPM).
    """

    async def _limit(user: CurrentUser = Depends(get_current_user)) -> None:
        limit = getattr(settings, limit_attr)
        key = f"ratelimit:{bucket}:{user.user_id}"
        now = time.time()
        window = 60
        try:
            async with redis_client.pipeline(transaction=True) as pipe:
                pipe.zremrangebyscore(key, 0, now - window)
                pipe.zadd(key, {f"{now}:{uuid.uuid4().hex[:8]}": now})
                pipe.zcard(key)
                pipe.expire(key, window)
                _, _, count, _ = await pipe.execute()
        except redis.RedisError as exc:
            raise HTTPException(status_code=503, detail="Rate limiter unavailable. Try again shortly.") from exc

        if count > limit:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded ({limit} requests/minute). Try again shortly.",
                headers={"Retry-After": str(window)},
            )

    return _limit


rate_limit = make_rate_limiter("default", "rate_limit_default_rpm")
rate_limit_query = make_rate_limiter("query", "rate_limit_query_rpm")
rate_limit_upload = make_rate_limiter("upload", "rate_limit_upload_rpm")
rate_limit_suggestions = make_rate_limiter("suggestions", "rate_limit_suggestions_rpm")

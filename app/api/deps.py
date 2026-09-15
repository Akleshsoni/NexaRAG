import time

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError

from app.core.config import settings
from app.core.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
_redis = aioredis.from_url(settings.redis_url, decode_responses=True)


class CurrentUser:
    def __init__(self, user_id: str, tenant_id: str):
        self.user_id = user_id
        self.tenant_id = tenant_id


async def get_current_user(token: str = Depends(oauth2_scheme)) -> CurrentUser:
    try:
        payload = decode_access_token(token)
        return CurrentUser(user_id=payload["sub"], tenant_id=payload["tenant_id"])
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc


async def rate_limit(request: Request, user: CurrentUser = Depends(get_current_user)) -> None:
    """Sliding-window rate limit per tenant: 60 requests/minute.

    Uses a Redis sorted set so the window slides smoothly instead of resetting
    in hard buckets (which lets clients burst right at the boundary).
    """
    key = f"ratelimit:{user.tenant_id}"
    now = time.time()
    window_seconds = 60
    max_requests = 60

    async with _redis.pipeline(transaction=True) as pipe:
        pipe.zremrangebyscore(key, 0, now - window_seconds)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, window_seconds)
        _, _, count, _ = await pipe.execute()

    if count > max_requests:
        raise HTTPException(status_code=429, detail="Rate limit exceeded, try again shortly")

import asyncio
import logging
import time
from contextlib import asynccontextmanager

import redis
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from starlette.concurrency import run_in_threadpool

from app.api.routes import auth, chat_ui, documents, history, query, stats
from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import AsyncSessionLocal
from app.services import vectorstore
from app.services.cache import redis_client

setup_logging()
logger = logging.getLogger("nexarag")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.environment != "development" and settings.secret_key == "dev-secret":
        raise RuntimeError("SECRET_KEY must be set to a strong random value outside development.")
    yield


app = FastAPI(
    title="NexaRAG",
    description="Multi-tenant RAG-as-a-service API",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(query.router)
app.include_router(history.router)
app.include_router(stats.router)
app.include_router(chat_ui.router)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        # Metadata only -- never bodies, headers, tokens or document text.
        logger.info(
            "request",
            extra={
                "ctx": {
                    "method": request.method,
                    "path": request.url.path,
                    "status": status_code,
                    "latency_ms": round((time.perf_counter() - start) * 1000, 1),
                    "tenant_id": getattr(request.state, "tenant_id", None),
                }
            },
        )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled error", exc_info=exc, extra={"ctx": {"path": request.url.path}})
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


@app.exception_handler(DBAPIError)
@app.exception_handler(ConnectionError)
async def database_unavailable_handler(request: Request, exc: Exception):
    logger.error("database error", exc_info=exc, extra={"ctx": {"path": request.url.path}})
    return JSONResponse(status_code=503, content={"detail": "Database is temporarily unavailable."})


async def _check(name: str, fn) -> tuple[str, dict]:
    start = time.perf_counter()
    try:
        await asyncio.wait_for(fn(), timeout=3)
        state = {"status": "ok"}
    except (Exception, asyncio.TimeoutError):  # noqa: BLE001
        state = {"status": "down"}
    state["latency_ms"] = round((time.perf_counter() - start) * 1000, 1)
    return name, state


async def _check_postgres() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SELECT 1"))


async def _check_redis() -> None:
    try:
        await redis_client.ping()
    except redis.RedisError as exc:
        raise RuntimeError("redis down") from exc


async def _check_qdrant() -> None:
    await run_in_threadpool(vectorstore.ping)


@app.get("/health")
async def health():
    """Liveness plus dependency status. Always HTTP 200 while the API process is up;
    `status` is "degraded" if PostgreSQL, Redis or Qdrant is unreachable.
    The Celery worker is not probed here."""
    results = await asyncio.gather(
        _check("postgres", _check_postgres),
        _check("redis", _check_redis),
        _check("qdrant", _check_qdrant),
    )
    services = {"api": {"status": "ok"}, **dict(results)}
    degraded = any(s["status"] != "ok" for s in services.values())
    return {
        "status": "degraded" if degraded else "ok",
        "environment": settings.environment,
        "services": services,
    }

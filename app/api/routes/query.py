"""Query endpoints: normal answer, streaming (SSE) answer, multi-document comparison.

RAG vs general routing: hybrid retrieval only returns chunks above the similarity
threshold. If it returns some, the answer is grounded in them and cited; if it
returns none, Gemini answers from general knowledge (mode = "general").
"""
import hashlib
import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.deps import CurrentUser, get_current_user, rate_limit_query
from app.db.session import AsyncSessionLocal, get_db
from app.models.models import Document, DocumentStatus, QueryLog
from app.schemas.schemas import QueryRequest, QueryResponse, RetrievedChunk
from app.services import cache, llm
from app.services.comparison import compare_documents
from app.services.retrieval import hybrid_search

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/query", tags=["query"])

CACHE_TTL_SECONDS = 60 * 30


async def _cache_key(tenant_id: str, question: str) -> str:
    version = await cache.get_cache_version(tenant_id)
    digest = hashlib.sha256(question.strip().lower().encode()).hexdigest()
    return f"query_cache:{tenant_id}:{version}:{digest}"


async def _attach_filenames(chunks: list[dict], tenant_id: str, db: AsyncSession) -> list[dict]:
    """Add the document filename to each chunk.

    Chunks whose document row no longer exists (e.g. vector cleanup failed after a
    delete) are dropped, so deleted documents can never be cited or queried.
    """
    if not chunks:
        return []
    doc_ids = list({uuid.UUID(c["document_id"]) for c in chunks})
    result = await db.execute(
        select(Document.id, Document.filename).where(Document.id.in_(doc_ids), Document.tenant_id == tenant_id)
    )
    names = {str(row[0]): row[1] for row in result}
    kept = []
    for c in chunks:
        if c["document_id"] in names:
            kept.append({**c, "filename": names[c["document_id"]]})
    return kept


async def _retrieve(user: CurrentUser, db: AsyncSession, question: str, top_k: int) -> list[dict]:
    try:
        chunks = await run_in_threadpool(hybrid_search, user.tenant_id, question, top_k=top_k)
    except Exception as exc:  # noqa: BLE001
        logger.exception("retrieval failed")
        await cache.count_failed_query(user.tenant_id)
        raise HTTPException(status_code=503, detail="Search service is temporarily unavailable.") from exc
    return await _attach_filenames(chunks, user.tenant_id, db)


async def _log_query(
    tenant_id: str, question: str, answer: str, chunks: list[dict], latency_ms: int, in_t: int, out_t: int
) -> None:
    """Write the history row in its own session so it also works after a stream ends."""
    try:
        async with AsyncSessionLocal() as session:
            session.add(
                QueryLog(
                    tenant_id=tenant_id,
                    question=question,
                    answer=answer,
                    retrieved_chunk_ids=json.dumps([c["chunk_id"] for c in chunks]),
                    latency_ms=latency_ms,
                    input_tokens=in_t,
                    output_tokens=out_t,
                )
            )
            await session.commit()
    except Exception:  # noqa: BLE001
        logger.exception("could not write query log")


def _source(c: dict) -> dict:
    return {
        "chunk_id": c["chunk_id"],
        "document_id": c["document_id"],
        "filename": c.get("filename", ""),
        "text": c["text"],
        "score": c["score"],
    }


@router.post("", response_model=QueryResponse)
async def query(
    payload: QueryRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_query),
):
    start = time.perf_counter()

    cache_key = await _cache_key(user.tenant_id, payload.question)
    try:
        cached = await cache.redis_client.get(cache_key)
    except Exception:  # noqa: BLE001
        cached = None
    if cached:
        return QueryResponse.model_validate_json(cached)

    chunks = await _retrieve(user, db, payload.question, payload.top_k)

    try:
        answer, in_t, out_t = await llm.generate_answer(payload.question, chunks)
    except llm.LLMError as exc:
        await cache.count_failed_query(user.tenant_id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    latency_ms = int((time.perf_counter() - start) * 1000)
    response = QueryResponse(
        answer=answer,
        sources=[RetrievedChunk(**c) for c in chunks],
        latency_ms=latency_ms,
        mode="rag" if chunks else "general",
    )

    try:
        await cache.redis_client.set(cache_key, response.model_dump_json(), ex=CACHE_TTL_SECONDS)
    except Exception:  # noqa: BLE001
        pass
    await _log_query(user.tenant_id, payload.question, answer, chunks, latency_ms, in_t, out_t)
    return response


@router.post("/stream")
async def query_stream(
    payload: QueryRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_query),
):
    """Token-by-token SSE. Events: `mode`, `token`*, then `done` (sources JSON) or `error`."""
    start = time.perf_counter()
    chunks = await _retrieve(user, db, payload.question, payload.top_k)

    async def events():
        usage: dict = {}
        parts: list[str] = []
        failed = False
        yield f"event: mode\ndata: {'rag' if chunks else 'general'}\n\n"
        try:
            async for token in llm.stream_answer(payload.question, chunks, usage):
                parts.append(token)
                safe = token.replace("\r", "").replace("\n", "\\n")
                yield f"event: token\ndata: {safe}\n\n"
        except llm.LLMError as exc:
            failed = True
            yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"

        if failed:
            await cache.count_failed_query(user.tenant_id)
        yield f"event: done\ndata: {json.dumps([_source(c) for c in chunks])}\n\n"

        if parts:
            await _log_query(
                user.tenant_id,
                payload.question,
                "".join(parts),
                chunks,
                int((time.perf_counter() - start) * 1000),
                usage.get("input_tokens", 0),
                usage.get("output_tokens", 0),
            )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class CompareRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    document_ids: list[uuid.UUID]


@router.post("/compare")
async def compare(
    payload: CompareRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_query),
):
    """Grounded comparison of 2-5 of the caller's own documents."""
    start = time.perf_counter()

    ids = list(dict.fromkeys(payload.document_ids))  # de-duplicate, keep order
    if len(ids) < 2:
        raise HTTPException(status_code=400, detail="Provide at least 2 different document IDs to compare.")
    if len(ids) > 5:
        raise HTTPException(status_code=400, detail="At most 5 documents can be compared at once.")

    result = await db.execute(select(Document).where(Document.id.in_(ids), Document.tenant_id == user.tenant_id))
    docs = {d.id: d for d in result.scalars().all()}
    if len(docs) != len(ids):
        raise HTTPException(status_code=404, detail="One or more documents were not found.")
    not_ready = [docs[i].filename for i in ids if docs[i].status != DocumentStatus.READY]
    if not_ready:
        raise HTTPException(status_code=409, detail=f"Documents not ready yet: {', '.join(not_ready)}")

    id_strs = [str(i) for i in ids]
    doc_names = {str(i): docs[i].filename for i in ids}

    try:
        data = await compare_documents(user.tenant_id, payload.question, id_strs)
    except Exception as exc:  # noqa: BLE001
        logger.exception("comparison retrieval failed")
        await cache.count_failed_query(user.tenant_id)
        raise HTTPException(status_code=503, detail="Search service is temporarily unavailable.") from exc

    try:
        answer, in_t, out_t = await llm.generate_comparison(payload.question, data["per_doc_chunks"], doc_names)
    except llm.LLMError as exc:
        await cache.count_failed_query(user.tenant_id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    latency_ms = int((time.perf_counter() - start) * 1000)
    all_chunks = [{**c, "filename": doc_names.get(c["document_id"], "")} for c in data["all_chunks"]]
    await _log_query(user.tenant_id, f"[COMPARE] {payload.question}", answer, all_chunks, latency_ms, in_t, out_t)

    return {
        "answer": answer,
        "latency_ms": latency_ms,
        "documents_compared": [
            {
                "document_id": i,
                "filename": doc_names[i],
                "chunks_found": len(data["per_doc_chunks"].get(i, [])),
            }
            for i in id_strs
        ],
        "sources": [_source(c) for c in all_chunks],
    }

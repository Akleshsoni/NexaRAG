"""Query endpoints.

Step 4 — Source preview: sources now include document filename via DB lookup.
Step 5 — Multi-document comparison: if the question mentions comparing docs,
          retrieval automatically pulls chunks from multiple documents.
Step 7 — Hindi/English/Hinglish: handled in llm.py system prompt.
"""
import hashlib
import json
import time

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

import uuid as uuid_mod
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUser, get_current_user, rate_limit
from app.core.config import settings
from app.db.session import get_db
from app.models.models import Document, QueryLog
from app.schemas.schemas import QueryRequest, QueryResponse, RetrievedChunk
from app.services import llm
from app.services.comparison import compare_documents
from app.services.retrieval import hybrid_search

router = APIRouter(prefix="/query", tags=["query"])
_redis = aioredis.from_url(settings.redis_url, decode_responses=True)

CACHE_TTL_SECONDS = 60 * 30


def _cache_key(tenant_id: str, question: str) -> str:
    digest = hashlib.sha256(question.strip().lower().encode()).hexdigest()
    return f"query_cache:{tenant_id}:{digest}"


async def _enrich_chunks_with_filenames(chunks: list[dict], tenant_id: str, db: AsyncSession) -> list[dict]:
    """Step 4 — Attach filename to each chunk for source preview."""
    doc_ids = list({c["document_id"] for c in chunks})
    result = await db.execute(
        select(Document.id, Document.filename).where(
            Document.id.in_(doc_ids),
            Document.tenant_id == tenant_id,
        )
    )
    id_to_name = {str(row[0]): row[1] for row in result}
    for chunk in chunks:
        chunk["filename"] = id_to_name.get(chunk["document_id"], "Unknown")
    return chunks


@router.post("", response_model=QueryResponse)
async def query(
    payload: QueryRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit),
):
    start = time.perf_counter()

    cache_key = _cache_key(user.tenant_id, payload.question)
    cached = await _redis.get(cache_key)
    if cached:
        return QueryResponse.model_validate_json(cached)

    chunks = hybrid_search(user.tenant_id, payload.question, top_k=payload.top_k)
    chunks = await _enrich_chunks_with_filenames(chunks, user.tenant_id, db)

    answer, input_tokens, output_tokens = await llm.generate_answer(payload.question, chunks)
    latency_ms = int((time.perf_counter() - start) * 1000)

    response = QueryResponse(
        answer=answer,
        sources=[RetrievedChunk(**c) for c in chunks],
        latency_ms=latency_ms,
    )

    await _redis.set(cache_key, response.model_dump_json(), ex=CACHE_TTL_SECONDS)

    db.add(
        QueryLog(
            tenant_id=user.tenant_id,
            question=payload.question,
            answer=answer,
            retrieved_chunk_ids=json.dumps([c["chunk_id"] for c in chunks]),
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
    )
    await db.commit()

    return response


@router.post("/stream")
async def query_stream(
    payload: QueryRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit),
):
    """Streaming endpoint — token-by-token SSE.

    Uses StreamingResponse directly (instead of EventSourceResponse) for
    maximum browser compatibility. DB logging happens after the stream
    completes so it never interrupts the response mid-flight.
    """
    from fastapi.responses import StreamingResponse as SR

    start = time.perf_counter()

    # Retrieval happens before streaming so latency includes it
    try:
        chunks = hybrid_search(user.tenant_id, payload.question, top_k=payload.top_k)
        chunks = await _enrich_chunks_with_filenames(chunks, user.tenant_id, db)
    except Exception as exc:
        # Return error as SSE event so the client can display it
        async def error_gen():
            yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"
        return SR(error_gen(), media_type="text/event-stream")

    usage_holder: dict = {}
    full_answer_parts: list[str] = []
    log_entry: dict = {}

    async def event_generator():
        nonlocal log_entry
        try:
            async for token in llm.stream_answer(payload.question, chunks, usage_holder):
                full_answer_parts.append(token)
                # SSE format: each message separated by double newline
                safe_token = token.replace("\n", "\\n")
                yield f"event: token\ndata: {safe_token}\n\n"

        except Exception as exc:
            # Emit error event so the UI can show a message instead of hanging
            yield f"event: error\ndata: {json.dumps({'detail': str(exc)[:200]})}\n\n"

        finally:
            # Always emit done with sources so client knows stream ended
            sources_data = [
                {
                    "chunk_id": c["chunk_id"],
                    "document_id": c["document_id"],
                    "filename": c.get("filename", ""),
                    "text": c["text"],
                    "score": c["score"],
                }
                for c in chunks
            ]
            yield f"event: done\ndata: {json.dumps(sources_data)}\n\n"

            # Store log details for after-stream DB write
            log_entry = {
                "answer": "".join(full_answer_parts),
                "latency_ms": int((time.perf_counter() - start) * 1000),
                "input_tokens": usage_holder.get("input_tokens", 0),
                "output_tokens": usage_holder.get("output_tokens", 0),
            }

    async def generate_and_log():
        """Wrap generator; after it's exhausted write the DB log."""
        async for chunk in event_generator():
            yield chunk
        # DB write after stream fully consumed — never interrupts SSE
        if log_entry:
            try:
                db.add(QueryLog(
                    tenant_id=user.tenant_id,
                    question=payload.question,
                    answer=log_entry["answer"],
                    retrieved_chunk_ids=json.dumps([c["chunk_id"] for c in chunks]),
                    latency_ms=log_entry["latency_ms"],
                    input_tokens=log_entry["input_tokens"],
                    output_tokens=log_entry["output_tokens"],
                ))
                await db.commit()
            except Exception:
                pass  # Don't crash the response over a logging failure

    return SR(
        generate_and_log(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering if behind proxy
        },
    )


class CompareRequest(BaseModel):
    question: str
    document_ids: list[str]  # list of document UUIDs to compare


@router.post("/compare")
async def compare(
    payload: CompareRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit),
):
    """Multi-document comparison — retrieves chunks from each doc separately
    and generates a grounded comparison that clearly attributes each point."""
    start = time.perf_counter()

    if len(payload.document_ids) < 2:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Provide at least 2 document IDs to compare.")

    if len(payload.document_ids) > 5:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Maximum 5 documents can be compared at once.")

    # Verify all documents belong to this tenant
    result = await db.execute(
        select(Document).where(
            Document.id.in_(payload.document_ids),
            Document.tenant_id == user.tenant_id,
        )
    )
    docs = result.scalars().all()
    found_ids = {str(d.id) for d in docs}
    missing = [did for did in payload.document_ids if did not in found_ids]
    if missing:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Documents not found: {missing}")

    doc_names = {str(d.id): d.filename for d in docs}

    comparison_data = await compare_documents(
        tenant_id=user.tenant_id,
        question=payload.question,
        document_ids=payload.document_ids,
    )

    answer, input_tokens, output_tokens = await llm.generate_comparison(
        question=payload.question,
        per_doc_chunks=comparison_data["per_doc_chunks"],
        doc_names=doc_names,
    )

    latency_ms = int((time.perf_counter() - start) * 1000)
    all_chunks = comparison_data["all_chunks"]

    # Log the comparison query
    db.add(QueryLog(
        tenant_id=user.tenant_id,
        question=f"[COMPARE] {payload.question}",
        answer=answer,
        retrieved_chunk_ids=json.dumps([c["chunk_id"] for c in all_chunks]),
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    ))
    await db.commit()

    return {
        "answer": answer,
        "latency_ms": latency_ms,
        "documents_compared": [
            {"document_id": str(d.id), "filename": d.filename, "chunks_found": len(comparison_data["per_doc_chunks"].get(str(d.id), []))}
            for d in docs
        ],
        "sources": [
            {"chunk_id": c["chunk_id"], "document_id": c["document_id"],
             "filename": doc_names.get(c["document_id"], ""), "text": c["text"], "score": c["score"]}
            for c in all_chunks
        ],
    }

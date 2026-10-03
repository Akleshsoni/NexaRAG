"""Vector store wrapper around Qdrant.

Every point is tagged with tenant_id so a single collection can serve all
tenants while queries are filtered to never leak across tenant boundaries --
this is the multi-tenancy guarantee, enforced at the data layer rather than
trusted to application logic alone.
"""
import logging
import uuid

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.core.config import settings

logger = logging.getLogger(__name__)

_client = QdrantClient(url=settings.qdrant_url)
VECTOR_SIZE = 384  # BAAI/bge-small-en-v1.5 output dimension


def ensure_collection() -> None:
    collections = [c.name for c in _client.get_collections().collections]
    if settings.qdrant_collection in collections:
        return
    _client.create_collection(
        collection_name=settings.qdrant_collection,
        vectors_config=qmodels.VectorParams(size=VECTOR_SIZE, distance=qmodels.Distance.COSINE),
    )
    for field in ("tenant_id", "document_id"):
        try:
            _client.create_payload_index(
                collection_name=settings.qdrant_collection,
                field_name=field,
                field_schema=qmodels.PayloadSchemaType.KEYWORD,
            )
        except Exception:  # noqa: BLE001 - index is an optimisation, not required
            logger.warning("could not create payload index", extra={"ctx": {"field": field}})


def build_filter(tenant_id: str, document_ids: list[str] | None = None) -> qmodels.Filter:
    """The tenant condition is ALWAYS present; document filtering only narrows further."""
    must = [qmodels.FieldCondition(key="tenant_id", match=qmodels.MatchValue(value=str(tenant_id)))]
    if document_ids:
        must.append(
            qmodels.FieldCondition(
                key="document_id", match=qmodels.MatchAny(any=[str(d) for d in document_ids])
            )
        )
    return qmodels.Filter(must=must)


def upsert_chunks(
    tenant_id: str,
    document_id: str,
    chunks: list[str],
    embeddings: list[list[float]],
) -> list[str]:
    ensure_collection()
    point_ids = [str(uuid.uuid4()) for _ in chunks]
    points = [
        qmodels.PointStruct(
            id=point_ids[i],
            vector=embeddings[i],
            payload={
                "tenant_id": str(tenant_id),
                "document_id": str(document_id),
                "text": chunks[i],
                "chunk_index": i,
            },
        )
        for i in range(len(chunks))
    ]
    _client.upsert(collection_name=settings.qdrant_collection, points=points)
    return point_ids


def delete_document(tenant_id: str, document_id: str) -> None:
    """Remove every vector of one document (used by delete and re-index)."""
    ensure_collection()
    _client.delete(
        collection_name=settings.qdrant_collection,
        points_selector=qmodels.FilterSelector(filter=build_filter(tenant_id, [document_id])),
    )


def search(
    tenant_id: str,
    query_vector: list[float],
    top_k: int = 5,
    document_ids: list[str] | None = None,
) -> list[dict]:
    ensure_collection()
    results = _client.search(
        collection_name=settings.qdrant_collection,
        query_vector=query_vector,
        query_filter=build_filter(tenant_id, document_ids),
        limit=top_k,
    )
    return [
        {
            "chunk_id": str(r.id),
            "document_id": r.payload["document_id"],
            "text": r.payload["text"],
            "score": r.score,
        }
        for r in results
    ]


def get_document_chunks(tenant_id: str, document_id: str, limit: int = 8) -> list[dict]:
    """First chunks of a document in reading order (used for query suggestions)."""
    ensure_collection()
    points, _ = _client.scroll(
        collection_name=settings.qdrant_collection,
        scroll_filter=build_filter(tenant_id, [document_id]),
        limit=200,
        with_payload=True,
        with_vectors=False,
    )
    chunks = sorted(
        ({"chunk_index": p.payload.get("chunk_index", 0), "text": p.payload["text"]} for p in points),
        key=lambda c: c["chunk_index"],
    )
    return chunks[:limit]


def ping() -> None:
    _client.get_collections()

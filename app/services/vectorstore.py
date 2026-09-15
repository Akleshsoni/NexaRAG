"""Vector store wrapper around Qdrant.

Every point is tagged with tenant_id so a single collection can serve all
tenants while queries are filtered to never leak across tenant boundaries --
this is the multi-tenancy guarantee, enforced at the data layer rather than
trusted to application logic alone.
"""
import uuid

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.core.config import settings

_client = QdrantClient(url=settings.qdrant_url)
VECTOR_SIZE = 384  # voyage-3-lite output dimension


def ensure_collection() -> None:
    collections = [c.name for c in _client.get_collections().collections]
    if settings.qdrant_collection not in collections:
        _client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=qmodels.VectorParams(size=VECTOR_SIZE, distance=qmodels.Distance.COSINE),
        )


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
                "tenant_id": tenant_id,
                "document_id": document_id,
                "text": chunks[i],
                "chunk_index": i,
            },
        )
        for i in range(len(chunks))
    ]
    _client.upsert(collection_name=settings.qdrant_collection, points=points)
    return point_ids


def search(tenant_id: str, query_vector: list[float], top_k: int = 5) -> list[dict]:
    results = _client.search(
        collection_name=settings.qdrant_collection,
        query_vector=query_vector,
        query_filter=qmodels.Filter(
            must=[qmodels.FieldCondition(key="tenant_id", match=qmodels.MatchValue(value=tenant_id))]
        ),
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

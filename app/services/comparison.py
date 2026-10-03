"""Multi-document comparison retrieval.

For each requested document, retrieve its best chunks with a Qdrant filter on
(tenant_id AND document_id). The tenant condition is always applied, so one
tenant can never pull another tenant's chunks even by guessing a document id.
"""
from starlette.concurrency import run_in_threadpool

from app.services import vectorstore
from app.services.embeddings import embed_query


def _retrieve(tenant_id: str, question: str, document_ids: list[str], top_k_per_doc: int) -> dict:
    query_vector = embed_query(question)
    per_doc_chunks: dict[str, list[dict]] = {}
    all_chunks: list[dict] = []

    for document_id in document_ids:
        results = vectorstore.search(
            tenant_id, query_vector, top_k=top_k_per_doc, document_ids=[document_id]
        )
        per_doc_chunks[str(document_id)] = results
        all_chunks.extend(results)

    return {"per_doc_chunks": per_doc_chunks, "all_chunks": all_chunks}


async def compare_documents(
    tenant_id: str,
    question: str,
    document_ids: list[str],
    top_k_per_doc: int = 4,
) -> dict:
    return await run_in_threadpool(_retrieve, tenant_id, question, document_ids, top_k_per_doc)

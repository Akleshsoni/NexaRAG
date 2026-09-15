"""Multi-document comparison service.

Uses the existing Qdrant search pipeline and restricts retrieval
to each requested document.
"""

from app.services.embeddings import embed_query
from app.services.vectorstore import search


async def compare_documents(
    tenant_id: str,
    question: str,
    document_ids: list[str],
    top_k_per_doc: int = 4,
) -> dict:
    """Retrieve relevant chunks from each requested document."""

    query_vector = embed_query(question)

    per_doc_chunks: dict[str, list[dict]] = {}
    all_chunks: list[dict] = []

    for document_id in document_ids:
        # Existing search() already enforces tenant isolation.
        results = search(
            tenant_id=tenant_id,
            query_vector=query_vector,
            top_k=top_k_per_doc * 3,
        )

        # Restrict results to the requested document.
        doc_results = [
            chunk
            for chunk in results
            if str(chunk.get("document_id")) == str(document_id)
        ][:top_k_per_doc]

        per_doc_chunks[str(document_id)] = doc_results

        for chunk in doc_results:
            chunk_copy = dict(chunk)
            chunk_copy["document_id"] = str(document_id)
            all_chunks.append(chunk_copy)

    return {
        "per_doc_chunks": per_doc_chunks,
        "all_chunks": all_chunks,
    }
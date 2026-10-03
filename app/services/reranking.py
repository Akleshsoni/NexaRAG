"""Reranking placeholder.

This is intentionally a pass-through: it keeps the order produced by hybrid
fusion (vector + BM25 via RRF) and truncates to top_k. It is NOT a cross-encoder.
The hook exists so a real reranker can be added later without touching callers.
"""


def rerank(question: str, chunks: list[dict], top_k: int = 5) -> list[dict]:
    return chunks[:top_k]

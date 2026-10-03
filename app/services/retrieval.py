"""Hybrid retrieval: dense vector search + BM25 keyword scoring, fused with RRF.

Pipeline: vector search -> drop chunks below the similarity threshold ->
BM25 over the remaining pool -> Reciprocal Rank Fusion -> near-duplicate removal
-> (pass-through) rerank -> top_k.

Routing: if nothing survives the threshold the result is an empty list, and the
caller answers with general AI instead of document RAG. This is a retrieval-
confidence heuristic, not an intent classifier: a document-specific question
that happens to retrieve weakly will be treated as general.

The `score` on each returned chunk is the raw vector cosine similarity. It is a
relevance signal for the retrieved passage, not the model's confidence in its answer.
"""
from rank_bm25 import BM25Okapi

from app.core.config import settings
from app.services import vectorstore
from app.services.embeddings import embed_query
from app.services.reranking import rerank


def _tokenize(text: str) -> list[str]:
    return text.lower().split()


def word_overlap(a: str, b: str) -> float:
    """Jaccard overlap between the word sets of two chunks."""
    wa, wb = set(_tokenize(a)), set(_tokenize(b))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def deduplicate(chunks: list[dict], overlap_threshold: float) -> list[dict]:
    """Drop chunks that mostly repeat a higher-ranked chunk already kept."""
    kept: list[dict] = []
    for chunk in chunks:
        if not any(word_overlap(chunk["text"], k["text"]) > overlap_threshold for k in kept):
            kept.append(chunk)
    return kept


def filter_by_score(hits: list[dict], min_score: float) -> list[dict]:
    return [h for h in hits if h["score"] >= min_score]


def fuse(hits: list[dict], question: str, rrf_k: int = 60) -> list[dict]:
    """BM25 re-scores the pool; RRF merges the vector and keyword rankings."""
    if not hits:
        return []
    bm25 = BM25Okapi([_tokenize(h["text"]) for h in hits])
    bm25_scores = bm25.get_scores(_tokenize(question))

    vector_rank = {h["chunk_id"]: rank for rank, h in enumerate(hits)}
    bm25_order = sorted(range(len(hits)), key=lambda i: -bm25_scores[i])
    bm25_rank = {hits[i]["chunk_id"]: rank for rank, i in enumerate(bm25_order)}

    fused = {
        h["chunk_id"]: 1 / (rrf_k + vector_rank[h["chunk_id"]]) + 1 / (rrf_k + bm25_rank[h["chunk_id"]])
        for h in hits
    }
    return sorted(hits, key=lambda h: -fused[h["chunk_id"]])


def hybrid_search(
    tenant_id: str,
    question: str,
    candidate_pool_size: int = 20,
    top_k: int = 5,
    rrf_k: int = 60,
    use_reranking: bool = True,
    rerank_pool_size: int = 10,
    min_score: float | None = None,
) -> list[dict]:
    threshold = settings.retrieval_min_score if min_score is None else min_score
    hits = vectorstore.search(tenant_id, embed_query(question), top_k=candidate_pool_size)
    hits = filter_by_score(hits, threshold)
    if not hits:
        return []

    ranked = fuse(hits, question, rrf_k)
    ranked = deduplicate(ranked, settings.retrieval_dedup_overlap)

    if not use_reranking:
        return ranked[:top_k]
    return rerank(question, ranked[:rerank_pool_size], top_k=top_k)

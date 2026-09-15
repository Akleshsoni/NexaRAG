"""Hybrid retrieval: combines dense vector search with BM25 keyword scoring,
then reranks with a cross-encoder for the final ordering.

Pure vector search misses exact-match cases (product codes, names, numbers)
because embeddings encode semantic meaning, not literal tokens. BM25 catches
those. Reciprocal Rank Fusion (RRF) merges the two ranked lists without
needing to normalize incompatible score scales. The fused list is still a
"good enough" first pass, so it's widened and handed to a reranker for a
more accurate final cut -- see reranking.py for why that step matters.
"""
from rank_bm25 import BM25Okapi

from app.services import vectorstore
from app.services.embeddings import embed_query
from app.services.reranking import rerank

MIN_SCORE_THRESHOLD = 0.65   # Drop chunks below this cosine similarity
DEDUP_OVERLAP_RATIO = 0.70   # Drop chunk if it shares >70% words with a higher-ranked chunk


def _tokenize(text: str) -> list[str]:
    return text.lower().split()


def _word_overlap(a: str, b: str) -> float:
    """Jaccard overlap between two chunks' word sets."""
    words_a = set(_tokenize(a))
    words_b = set(_tokenize(b))
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def deduplicate(chunks: list[dict], overlap_threshold: float = DEDUP_OVERLAP_RATIO) -> list[dict]:
    """Remove chunks that are too similar to a higher-ranked chunk already selected."""
    kept: list[dict] = []
    for chunk in chunks:
        is_duplicate = any(
            _word_overlap(chunk["text"], k["text"]) > overlap_threshold
            for k in kept
        )
        if not is_duplicate:
            kept.append(chunk)
    return kept


def hybrid_search(
    tenant_id: str,
    question: str,
    candidate_pool_size: int = 20,
    top_k: int = 5,
    rrf_k: int = 60,
    use_reranking: bool = True,
    rerank_pool_size: int = 10,
    min_score: float = MIN_SCORE_THRESHOLD,
) -> list[dict]:
    query_vector = embed_query(question)
    vector_hits = vectorstore.search(tenant_id, query_vector, top_k=candidate_pool_size)

    if not vector_hits:
        return []

    # Filter out low-relevance chunks before BM25 + fusion
    vector_hits = [h for h in vector_hits if h["score"] >= min_score]
    if not vector_hits:
        return []

    corpus = [_tokenize(h["text"]) for h in vector_hits]
    bm25 = BM25Okapi(corpus)
    bm25_scores = bm25.get_scores(_tokenize(question))

    vector_rank = {h["chunk_id"]: rank for rank, h in enumerate(vector_hits)}
    bm25_order = sorted(range(len(vector_hits)), key=lambda i: -bm25_scores[i])
    bm25_rank = {vector_hits[i]["chunk_id"]: rank for rank, i in enumerate(bm25_order)}

    fused_scores = {
        h["chunk_id"]: (1 / (rrf_k + vector_rank[h["chunk_id"]]))
        + (1 / (rrf_k + bm25_rank[h["chunk_id"]]))
        for h in vector_hits
    }

    ranked = sorted(vector_hits, key=lambda h: -fused_scores[h["chunk_id"]])

    # Deduplicate before reranking
    ranked = deduplicate(ranked)

    if not use_reranking:
        return ranked[:top_k]

    candidates = ranked[:rerank_pool_size]
    return rerank(question, candidates, top_k=top_k)
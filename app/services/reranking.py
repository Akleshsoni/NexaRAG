def rerank(question: str, chunks: list[dict], top_k: int = 5) -> list[dict]:
    return chunks[:top_k]
from fastembed import TextEmbedding

_model: TextEmbedding | None = None


def _get_model() -> TextEmbedding:
    global _model
    if _model is None:
        _model = TextEmbedding("BAAI/bge-small-en-v1.5")
    return _model


def embed_texts(texts: list[str], input_type: str = "document") -> list[list[float]]:
    if not texts:
        return []
    embeddings = list(_get_model().embed(texts))
    return [e.tolist() for e in embeddings]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
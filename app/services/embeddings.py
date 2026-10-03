"""Local embeddings via FastEmbed (ONNX, no PyTorch, no API key, no rate limits).

Model: BAAI/bge-small-en-v1.5 -> 384 dimensions. It is an English model, so
Hindi/Hinglish *questions* retrieve English passages less reliably than English ones.
"""
import os

from app.core.config import settings

_model = None


def _get_model():
    global _model
    if _model is None:
        # Imported lazily so importing the app (tests, CI) does not load ONNX.
        from fastembed import TextEmbedding

        _model = TextEmbedding(settings.embedding_model, cache_dir=os.getenv("FASTEMBED_CACHE_PATH"))
    return _model


def embed_texts(texts: list[str], input_type: str = "document") -> list[list[float]]:
    if not texts:
        return []
    return [e.tolist() for e in _get_model().embed(texts)]


def embed_query(text: str) -> list[float]:
    return embed_texts([text], input_type="query")[0]

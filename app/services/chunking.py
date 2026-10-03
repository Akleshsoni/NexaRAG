"""Splits raw document text into overlapping chunks for embedding.

Token-aware chunking beats naive character splitting because it keeps chunk
sizes consistent regardless of formatting, and the overlap prevents an answer
from being cut in half across a chunk boundary.
"""
_encoder_cache = None


def _encoder():
    """Loaded lazily: tiktoken fetches its vocabulary on first use, so importing
    the app (tests, CI, health checks) must not depend on that download."""
    global _encoder_cache
    if _encoder_cache is None:
        import tiktoken

        _encoder_cache = tiktoken.get_encoding("cl100k_base")
    return _encoder_cache


def chunk_text(
    text: str,
    chunk_size_tokens: int = 400,
    overlap_tokens: int = 60,
) -> list[str]:
    if not text.strip():
        return []

    enc = _encoder()
    tokens = enc.encode(text)
    chunks: list[str] = []
    start = 0

    while start < len(tokens):
        end = min(start + chunk_size_tokens, len(tokens))
        chunk_tokens = tokens[start:end]
        chunks.append(enc.decode(chunk_tokens))
        if end == len(tokens):
            break
        start = end - overlap_tokens  # slide window back for overlap

    return chunks


def extract_text(file_path: str, filename: str) -> str:
    """Extract raw text from pdf/docx/txt files."""
    lower = filename.lower()

    if lower.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(file_path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    if lower.endswith(".docx"):
        import docx

        doc = docx.Document(file_path)
        return "\n".join(p.text for p in doc.paragraphs)

    with open(file_path, encoding="utf-8", errors="ignore") as f:
        return f.read()

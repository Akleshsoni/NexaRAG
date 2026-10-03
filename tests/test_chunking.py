import pytest

from app.services import chunking

try:
    chunking._encoder().encode("probe")
except Exception:  # noqa: BLE001 - tiktoken downloads its vocabulary on first use
    pytest.skip("tiktoken encoding unavailable (offline)", allow_module_level=True)


def test_empty_text_gives_no_chunks():
    assert chunking.chunk_text("   ") == []


def test_chunks_overlap_and_cover_text():
    text = " ".join(f"word{i}" for i in range(1500))
    chunks = chunking.chunk_text(text, chunk_size_tokens=200, overlap_tokens=30)
    assert len(chunks) > 1
    assert all(c.strip() for c in chunks)
    assert chunks[0].split()[-1] in chunks[1]  # overlap carries context across the boundary

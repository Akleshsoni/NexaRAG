"""Route-level tests with Postgres/Redis/Qdrant/Gemini replaced by fakes."""
import json
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app import main
from app.api import deps
from app.api.routes import query as qr
from app.services import llm

DOC_ID = str(uuid.uuid4())
USER = deps.CurrentUser("user-1", "tenant-1")


class FakeRedis:
    async def get(self, *_):
        return None

    async def set(self, *a, **k):
        return True

    async def incr(self, *_):
        return 1


class FakeDB:
    """Stands in for AsyncSession; `rows` is what the filename lookup returns."""

    def __init__(self, rows):
        self.rows = rows

    async def execute(self, *_):
        return list(self.rows)


@pytest.fixture
def setup(monkeypatch):
    state = {"rows": [(uuid.UUID(DOC_ID), "notes.pdf")], "logged": [], "chunks": []}

    async def fake_db():
        yield FakeDB(state["rows"])

    async def no_limit():
        return None

    main.app.dependency_overrides[deps.get_current_user] = lambda: USER
    main.app.dependency_overrides[qr.get_db] = fake_db
    main.app.dependency_overrides[qr.rate_limit_query] = no_limit
    monkeypatch.setattr(qr.cache, "redis_client", FakeRedis())
    monkeypatch.setattr(qr, "hybrid_search", lambda *a, **k: state["chunks"])

    async def fake_log(*args):
        state["logged"].append(args)

    monkeypatch.setattr(qr, "_log_query", fake_log)
    yield state
    main.app.dependency_overrides.clear()


def _chunk(doc=DOC_ID):
    return {"chunk_id": "c1", "document_id": doc, "text": "stack follows LIFO", "score": 0.8}


def _client():
    return AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test")


async def test_rag_answer_has_filename_sources_and_is_logged(setup, monkeypatch):
    setup["chunks"] = [_chunk()]

    async def fake_answer(question, chunks):
        return "A stack is LIFO [1]", 10, 5

    monkeypatch.setattr(llm, "generate_answer", fake_answer)
    async with _client() as c:
        r = await c.post("/query", json={"question": "What is a stack?"})
    body = r.json()
    assert r.status_code == 200 and body["mode"] == "rag"
    assert body["sources"][0]["filename"] == "notes.pdf" and body["sources"][0]["score"] == 0.8
    assert len(setup["logged"]) == 1


async def test_no_relevant_chunks_falls_back_to_general(setup, monkeypatch):
    seen = {}

    async def fake_answer(question, chunks):
        seen["chunks"] = chunks
        return "Python is a programming language.", 3, 3

    monkeypatch.setattr(llm, "generate_answer", fake_answer)
    async with _client() as c:
        body = (await c.post("/query", json={"question": "What is Python?"})).json()
    assert body["mode"] == "general" and body["sources"] == [] and seen["chunks"] == []


async def test_chunks_of_deleted_documents_are_never_served(setup, monkeypatch):
    setup["chunks"] = [_chunk()]
    setup["rows"] = []  # the document row is gone (e.g. vector cleanup failed after delete)

    async def fake_answer(question, chunks):
        assert chunks == []
        return "general", 1, 1

    monkeypatch.setattr(llm, "generate_answer", fake_answer)
    async with _client() as c:
        body = (await c.post("/query", json={"question": "What is a stack?"})).json()
    assert body["sources"] == [] and body["mode"] == "general"


async def test_llm_failure_is_a_clean_502(setup, monkeypatch):
    async def boom(question, chunks):
        raise llm.LLMError("The AI provider quota or rate limit was reached. Please try again shortly.")

    monkeypatch.setattr(llm, "generate_answer", boom)
    async with _client() as c:
        r = await c.post("/query", json={"question": "hi"})
    assert r.status_code == 502 and "quota" in r.json()["detail"]


async def test_retrieval_failure_is_503_without_internals(setup, monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("qdrant at 10.0.0.5 refused connection, key=SECRET")

    monkeypatch.setattr(qr, "hybrid_search", broken)
    async with _client() as c:
        r = await c.post("/query", json={"question": "hi"})
    assert r.status_code == 503 and "SECRET" not in r.text and "10.0.0.5" not in r.text


def _events(text: str) -> list[tuple[str, str]]:
    out = []
    for block in text.strip().split("\n\n"):
        lines = block.split("\n")
        out.append((lines[0].removeprefix("event: "), lines[1].removeprefix("data: ")))
    return out


async def test_stream_emits_mode_tokens_and_sources(setup, monkeypatch):
    setup["chunks"] = [_chunk()]

    async def fake_stream(question, chunks, usage):
        usage.update(input_tokens=7, output_tokens=2)
        yield "A stack "
        yield "is LIFO.\nDone"

    monkeypatch.setattr(llm, "stream_answer", fake_stream)
    async with _client() as c:
        r = await c.post("/query/stream", json={"question": "What is a stack?"})
    events = _events(r.text)
    assert events[0] == ("mode", "rag")
    tokens = [d for e, d in events if e == "token"]
    assert tokens == ["A stack ", "is LIFO.\\nDone"]  # newlines are escaped for SSE framing
    kind, data = events[-1]
    assert kind == "done" and json.loads(data)[0]["filename"] == "notes.pdf"
    assert len(setup["logged"]) == 1 and setup["logged"][0][-2:] == (7, 2)


async def test_stream_reports_llm_error_as_event(setup, monkeypatch):
    async def failing(question, chunks, usage):
        raise llm.LLMError("The AI service failed to generate a response.")
        yield  # pragma: no cover

    monkeypatch.setattr(llm, "stream_answer", failing)
    async with _client() as c:
        r = await c.post("/query/stream", json={"question": "hi"})
    kinds = [e for e, _ in _events(r.text)]
    assert "error" in kinds and kinds[-1] == "done"
    assert setup["logged"] == []  # nothing generated -> no history row


async def test_compare_rejects_bad_requests(setup):
    async with _client() as c:
        one = await c.post("/query/compare", json={"question": "x", "document_ids": [DOC_ID]})
        dup = await c.post("/query/compare", json={"question": "x", "document_ids": [DOC_ID, DOC_ID]})
        six = [str(uuid.uuid4()) for _ in range(6)]
        many = await c.post("/query/compare", json={"question": "x", "document_ids": six})
    assert one.status_code == 400 and dup.status_code == 400 and many.status_code == 400

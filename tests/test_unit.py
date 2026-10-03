"""Unit tests: no Postgres/Redis/Qdrant/Gemini needed."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from jose import jwt
from starlette.requests import Request

from app.api import deps
from app.api.routes.documents import safe_filename, validate_upload
from app.core.config import settings
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.schemas.schemas import QueryRequest, total_pages
from app.services import llm, retrieval, vectorstore


def _chunk(cid, text, score):
    return {"chunk_id": cid, "document_id": str(uuid.uuid4()), "text": text, "score": score}


# ---------- authentication ----------
def test_password_hash_and_verify():
    hashed = hash_password("correct-horse-battery")
    assert verify_password("correct-horse-battery", hashed)
    assert not verify_password("wrong", hashed)


def test_token_roundtrip_carries_tenant():
    token = create_access_token("user-1", "tenant-1")
    payload = decode_access_token(token)
    assert payload["sub"] == "user-1" and payload["tenant_id"] == "tenant-1"


def _request() -> Request:
    return Request({"type": "http", "headers": [], "method": "GET", "path": "/"})


async def test_garbage_token_is_401():
    with pytest.raises(HTTPException) as exc:
        await deps.get_current_user(_request(), token="not-a-jwt")
    assert exc.value.status_code == 401


async def test_expired_token_is_401_with_clear_message():
    expired = jwt.encode(
        {"sub": "u", "tenant_id": "t", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(HTTPException) as exc:
        await deps.get_current_user(_request(), token=expired)
    assert exc.value.status_code == 401 and "expired" in exc.value.detail.lower()


async def test_token_without_tenant_is_rejected():
    token = jwt.encode({"sub": "u"}, settings.secret_key, algorithm=settings.jwt_algorithm)
    with pytest.raises(HTTPException) as exc:
        await deps.get_current_user(_request(), token=token)
    assert exc.value.status_code == 401


# ---------- tenant isolation (data layer) ----------
def test_qdrant_filter_always_contains_tenant_condition():
    f = vectorstore.build_filter("tenant-A")
    assert [c.key for c in f.must] == ["tenant_id"]
    f = vectorstore.build_filter("tenant-A", ["doc-1", "doc-2"])
    keys = [c.key for c in f.must]
    assert keys[0] == "tenant_id" and "document_id" in keys  # narrowing never removes the tenant filter


# ---------- uploads ----------
def test_safe_filename_strips_paths_and_odd_characters():
    assert safe_filename("../../etc/passwd.pdf") == "passwd.pdf"
    assert safe_filename("C:\\Users\\x\\report.pdf") == "report.pdf"
    assert safe_filename("a'b\"c<script>.pdf") == "a_b_c_script_.pdf"
    assert safe_filename(None) == "document"


def test_upload_accepts_valid_pdf_and_docx():
    assert validate_upload("a.pdf", b"%PDF-1.4 hello") == ".pdf"
    assert validate_upload("a.DOCX", b"PK\x03\x04data") == ".docx"


@pytest.mark.parametrize(
    "name,data,status",
    [
        ("a.txt", b"hello", 400),  # unsupported type
        ("a.exe", b"MZ", 400),
        ("a.pdf", b"", 400),  # empty
        ("a.pdf", b"not really a pdf", 400),  # extension lies
        ("a.docx", b"%PDF-1.4", 400),
        ("a.pdf", b"%PDF" + b"0" * (settings.max_upload_mb * 1024 * 1024), 413),  # too large
    ],
)
def test_upload_rejections(name, data, status):
    with pytest.raises(HTTPException) as exc:
        validate_upload(name, data)
    assert exc.value.status_code == status


# ---------- pagination / validation ----------
def test_total_pages():
    assert total_pages(0, 10) == 1
    assert total_pages(10, 10) == 1
    assert total_pages(11, 10) == 2
    assert total_pages(95, 10) == 10


def test_query_request_bounds():
    with pytest.raises(ValueError):
        QueryRequest(question="")
    with pytest.raises(ValueError):
        QueryRequest(question="x", top_k=0)
    assert QueryRequest(question="hello").top_k == 5


# ---------- retrieval logic ----------
def test_threshold_filters_low_scores():
    hits = [_chunk("a", "x", 0.9), _chunk("b", "y", 0.54), _chunk("c", "z", 0.55)]
    kept = retrieval.filter_by_score(hits, 0.55)
    assert [h["chunk_id"] for h in kept] == ["a", "c"]


def test_deduplicate_removes_near_copies_but_keeps_distinct():
    base = "stack is a linear data structure that follows the lifo principle with push and pop"
    chunks = [
        _chunk("1", base, 0.9),
        _chunk("2", base + " today", 0.89),  # near-duplicate of 1
        _chunk("3", "binary search tree lookups take logarithmic time when balanced", 0.8),
    ]
    out = retrieval.deduplicate(chunks, 0.7)
    assert [c["chunk_id"] for c in out] == ["1", "3"]


def test_fusion_promotes_exact_keyword_match():
    hits = [  # ordered by vector score
        _chunk("v1", "general discussion about data structures and memory", 0.80),
        _chunk("v2", "random unrelated text about cooking pasta", 0.78),
        _chunk("v3", "graph traversal using adjacency list takes O(V+E) space", 0.77),
    ]
    ranked = retrieval.fuse(hits, "adjacency list space complexity")
    ids = [h["chunk_id"] for h in ranked]
    # v3 is only 3rd by vector score but is the sole keyword match, so fusion lifts it above v2.
    assert ids.index("v3") < ids.index("v2")
    assert set(ids) == {"v1", "v2", "v3"}  # fusion reorders, it never drops candidates


def test_fuse_empty():
    assert retrieval.fuse([], "anything") == []


def test_hybrid_search_returns_nothing_when_all_below_threshold(monkeypatch):
    monkeypatch.setattr(retrieval, "embed_query", lambda q: [0.0])
    monkeypatch.setattr(vectorstore, "search", lambda *a, **k: [_chunk("a", "t", 0.2)])
    assert retrieval.hybrid_search("t", "what is python?") == []  # -> general AI fallback


def test_hybrid_search_keeps_relevant(monkeypatch):
    monkeypatch.setattr(retrieval, "embed_query", lambda q: [0.0])
    monkeypatch.setattr(
        vectorstore,
        "search",
        lambda *a, **k: [_chunk("a", "stack lifo push pop", 0.8), _chunk("b", "noise", 0.1)],
    )
    out = retrieval.hybrid_search("t", "what is a stack?")
    assert [c["chunk_id"] for c in out] == ["a"]


# ---------- prompts / LLM helpers ----------
def test_rag_prompt_numbers_sources_and_names_files():
    chunks = [
        {"chunk_id": "1", "document_id": "d1", "filename": "a.pdf", "text": "alpha", "score": 0.9},
        {"chunk_id": "2", "document_id": "d2", "filename": "b.pdf", "text": "beta", "score": 0.8},
    ]
    prompt = llm.build_prompt("q?", chunks)
    assert "[1] (source: a.pdf): alpha" in prompt and "[2] (source: b.pdf): beta" in prompt


def test_comparison_prompt_marks_documents_without_content():
    per_doc = {"d1": [{"text": "alpha"}], "d2": []}
    prompt = llm.build_comparison_prompt("compare", per_doc, {"d1": "a.pdf", "d2": "b.pdf"})
    assert "=== Document: a.pdf ===\n[1] alpha" in prompt
    assert "=== Document: b.pdf ===\n(no relevant excerpts found in this document)" in prompt


def test_grounding_rules_in_system_prompts():
    assert "ONLY" in llm.RAG_SYSTEM_PROMPT and "never invent" in llm.RAG_SYSTEM_PROMPT
    assert "Hindi" in llm.RAG_SYSTEM_PROMPT  # language rule present
    assert "do not cite" in llm.GENERAL_SYSTEM_PROMPT


def test_parse_suggestions_variants():
    json_reply = '```json\n["What is a stack and how does it work?", "How fast are queue operations?"]\n```'
    assert len(llm.parse_suggestions(json_reply)) == 2
    bullets = "1. What is a linked list in practice?\n2. When is an array better than a list?"
    assert llm.parse_suggestions(bullets)[0].startswith("What is a linked list")
    assert llm.parse_suggestions("") == []
    assert len(llm.parse_suggestions('["q one here ok"' + ',"q two here ok"' * 9 + "]")) == 5


async def test_llm_without_key_raises_clean_error():
    with pytest.raises(llm.LLMError):
        await llm.generate_answer("hi", [])

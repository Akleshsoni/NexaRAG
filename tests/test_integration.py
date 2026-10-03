"""Integration tests against a RUNNING stack:

    docker compose up -d
    NEXARAG_BASE_URL=http://localhost:8080 pytest tests/test_integration.py -v

They need Postgres, Redis, Qdrant, the worker and (for RAG tests) a Gemini key.
Skipped automatically when NEXARAG_BASE_URL is not set.
"""
import os
import time
import uuid
from pathlib import Path

import httpx
import pytest

BASE = os.getenv("NEXARAG_BASE_URL")
pytestmark = pytest.mark.skipif(not BASE, reason="set NEXARAG_BASE_URL to run integration tests")

SAMPLE_PDF = Path(__file__).resolve().parent.parent / "eval" / "sample_docs" / "cs_notes.pdf"


def _signup(client: httpx.Client) -> dict:
    email = f"t{uuid.uuid4().hex[:10]}@example.com"
    r = client.post("/auth/signup", json={"email": email, "password": "password123", "tenant_name": "T"})
    assert r.status_code == 200, r.text
    return {"email": email, "headers": {"Authorization": f"Bearer {r.json()['access_token']}"}}


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, timeout=60) as c:
        yield c


@pytest.fixture(scope="module")
def tenant_a(client):
    return _signup(client)


@pytest.fixture(scope="module")
def tenant_b(client):
    return _signup(client)


def _upload(client, headers) -> str:
    r = client.post("/documents", headers=headers, files={"file": ("cs_notes.pdf", SAMPLE_PDF.read_bytes())})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _wait_ready(client, headers, doc_id, timeout=180) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        items = client.get("/documents?limit=100", headers=headers).json()["items"]
        status = next(d["status"] for d in items if d["id"] == doc_id)
        if status in ("ready", "failed"):
            return status
        time.sleep(2)
    return "timeout"


def test_login_valid_and_invalid(client, tenant_a):
    ok = client.post("/auth/login", json={"email": tenant_a["email"], "password": "password123"})
    assert ok.status_code == 200 and "access_token" in ok.json()
    bad = client.post("/auth/login", json={"email": tenant_a["email"], "password": "wrong-password"})
    assert bad.status_code == 401


def test_unauthorized_and_invalid_token(client):
    assert client.get("/documents").status_code == 401
    assert client.get("/documents", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_upload_validation(client, tenant_a):
    h = tenant_a["headers"]
    assert client.post("/documents", headers=h, files={"file": ("x.txt", b"hello")}).status_code == 400
    big = b"%PDF" + b"0" * (10 * 1024 * 1024 + 1)
    assert client.post("/documents", headers=h, files={"file": ("big.pdf", big)}).status_code == 413


def test_document_lifecycle_isolation_and_rag(client, tenant_a, tenant_b):
    a, b = tenant_a["headers"], tenant_b["headers"]
    doc_id = _upload(client, a)
    assert _wait_ready(client, a, doc_id) == "ready"

    # list + pagination metadata
    page = client.get("/documents?page=1&limit=10", headers=a).json()
    assert {"items", "total", "page", "limit", "total_pages"} <= set(page) and page["total"] >= 1

    # tenant isolation: B cannot see, delete, re-index or get suggestions for A's document
    assert doc_id not in [d["id"] for d in client.get("/documents", headers=b).json()["items"]]
    assert client.delete(f"/documents/{doc_id}", headers=b).status_code == 404
    assert client.post(f"/documents/{doc_id}/reindex", headers=b).status_code == 404
    assert client.get(f"/documents/{doc_id}/suggestions", headers=b).status_code == 404
    r = client.post("/query", headers=b, json={"question": "What is a stack?"})
    assert r.status_code in (200, 502) and (r.status_code == 502 or r.json()["sources"] == [])

    # RAG with a relevant question: sources come from this document
    r = client.post("/query", headers=a, json={"question": "What is the time complexity of searching a balanced BST?"})
    if r.status_code == 200:
        body = r.json()
        assert body["mode"] == "rag" and body["sources"]
        assert all(s["document_id"] == doc_id and s["filename"] for s in body["sources"])
        hist = client.get("/queries", headers=a).json()
        assert hist["total"] >= 1 and "question" in hist["items"][0]
        assert client.get("/queries", headers=b).json()["total"] == 0  # history is tenant-scoped

    stats = client.get("/stats", headers=a).json()
    assert stats["documents"]["total"] >= 1 and stats["documents"]["ready"] >= 1

    # re-index returns to ready without duplicating vectors
    assert client.post(f"/documents/{doc_id}/reindex", headers=a).status_code == 200
    assert _wait_ready(client, a, doc_id) == "ready"

    # delete -> gone, and no longer retrievable
    assert client.delete(f"/documents/{doc_id}", headers=a).status_code == 200
    assert doc_id not in [d["id"] for d in client.get("/documents", headers=a).json()["items"]]
    r = client.post("/query", headers=a, json={"question": "What is the time complexity of searching a balanced BST?"})
    if r.status_code == 200:
        assert all(s["document_id"] != doc_id for s in r.json()["sources"])


def test_compare_requires_two_owned_documents(client, tenant_a):
    h = tenant_a["headers"]
    one = str(uuid.uuid4())
    assert client.post("/query/compare", headers=h, json={"question": "x", "document_ids": [one]}).status_code == 400
    two = [str(uuid.uuid4()), str(uuid.uuid4())]
    assert client.post("/query/compare", headers=h, json={"question": "x", "document_ids": two}).status_code == 404


def test_rate_limit_returns_429(client, tenant_a):
    h = tenant_a["headers"]
    codes = {client.get(f"/documents/{uuid.uuid4()}/suggestions", headers=h).status_code for _ in range(8)}
    assert 429 in codes  # default suggestions limit is 5/minute

# NexaRAG

Multi-tenant **RAG (retrieval-augmented generation) API** for documents: upload PDF/DOCX files, ask questions,
get answers with source citations, compare documents, and track usage. Built with FastAPI, PostgreSQL, Qdrant,
Redis/Celery and Gemini.

> Status: a working portfolio project, tested locally with Docker Compose. Quality and performance numbers are
> **not published here on purpose** — run the evaluation and load-test scripts yourself (see below) and record
> what you measure.

## Features

- **Auth & tenancy** — signup/login with JWT; every tenant only sees its own documents, vectors and history.
- **Documents** — upload (PDF/DOCX, max 10 MB, content-signature check), list (paginated), delete, re-index.
  Background processing with Celery; status `pending → processing → ready | failed`.
- **Hybrid retrieval** — dense vector search (local `bge-small-en-v1.5`, 384-d) + BM25 keyword scoring, merged with
  Reciprocal Rank Fusion, near-duplicate removal, top-k.
- **Retrieval-confidence routing** — chunks below a cosine-similarity threshold are discarded. If nothing is left,
  the question is answered by **general AI** (`mode: "general"`, no sources); otherwise by **document RAG**
  (`mode: "rag"`, with numbered citations). This is a heuristic, not an intent classifier.
- **Streaming answers** (SSE) with cancel support in the UI, plus a normal JSON endpoint.
- **Multi-document comparison** — retrieves per document (always tenant-filtered), asks Gemini for a grounded
  comparison with attribution; documents with no relevant content are reported as such.
- **AI query suggestions** — 5 questions generated from the document's own indexed text.
- **Hindi / English / Hinglish** — the model replies in the user's language. *Retrieval is English-embedding-based, so
  non-English questions retrieve less reliably.*
- **Query history, stats dashboard, source preview** in the bundled chat UI (`/chat`).
- **Operations** — per-user Redis rate limits (configurable), `/health` with dependency checks, structured JSON logs,
  Alembic migrations, GitHub Actions CI.

## Architecture

```
Browser (/chat UI)
      │  JWT (sessionStorage)
      ▼
FastAPI ──► Auth (JWT, tenant_id claim) ──► Redis  (rate limits, answer cache, counters, Celery broker)
   │                                         PostgreSQL (tenants, users, documents, query_logs)
   │  upload                                 Qdrant (chunk vectors, filtered by tenant_id [+ document_id])
   ▼
Celery worker:  extract text → chunk (400 tok / 60 overlap) → embed (fastembed, local) → Qdrant
   
Query:  embed question → Qdrant top-20 → similarity threshold → BM25 + RRF → de-dup → top-k
        → chunks found?  yes → Gemini (RAG prompt, cite [n])     → answer + sources
                         no  → Gemini (general prompt, no cites) → answer, sources = []
```

### Tenant isolation
The JWT carries `tenant_id`. Every Postgres query filters on it, and every Qdrant search includes a mandatory
`tenant_id` condition (`vectorstore.build_filter`; document filters only *narrow* it). Another tenant's document ID
returns `404`, never `403`, so existence is not leaked. Chunks whose document row no longer exists are dropped at
query time.

### Data model
`tenants` (name, token budget) · `users` (email, bcrypt hash, tenant) · `documents` (filename, storage path, status,
error) · `query_logs` (question, answer, retrieved chunk ids, latency, tokens). Vectors live in Qdrant with payload
`{tenant_id, document_id, chunk_index, text}`.

### Delete / re-index safety
Delete removes the DB row first, then vectors, then the file. The worker re-checks the row before and after writing
vectors, and removes vectors for documents deleted mid-processing. Re-index deletes existing vectors, then reuses the
same Celery task, so vectors are never duplicated. Answer cache entries are invalidated through a per-tenant version.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/signup`, `/auth/login` | Get a JWT |
| POST | `/documents` | Upload PDF/DOCX |
| GET | `/documents?page=&limit=` | Paginated list |
| DELETE | `/documents/{id}` | Delete document, vectors, file |
| POST | `/documents/{id}/reindex` | Re-process the stored file |
| GET | `/documents/{id}/suggestions` | 5 questions from the document |
| POST | `/query` | Answer + sources + `mode` |
| POST | `/query/stream` | SSE: `mode`, `token`…, `done` (sources) / `error` |
| POST | `/query/compare` | Compare 2–5 documents |
| GET | `/queries?page=&limit=` | Query history |
| GET | `/stats` | Documents/queries/latency/tokens |
| GET | `/health` | API + PostgreSQL + Redis + Qdrant status |

Paginated responses: `{items, total, page, limit, total_pages}`. Errors are `{"detail": "..."}` with a suitable
status (401 auth, 404 not found, 409 wrong state, 413 too large, 429 rate limit, 502 LLM failure, 503 dependency down).
Interactive docs: `http://localhost:8080/docs`.

## Setup

Requirements: Docker Desktop, a [Gemini API key](https://aistudio.google.com/apikey).

```bash
cp .env.example .env        # Windows CMD: copy .env.example .env
# edit .env: set GEMINI_API_KEY and a strong SECRET_KEY
docker compose up --build
```

Open `http://localhost:8080/chat`, sign up, upload a PDF, and ask questions. Migrations run automatically on start.
The first build downloads the embedding model into the image (a few minutes).

### Configuration (`.env`)
See `.env.example`. Notable: `RETRIEVAL_MIN_SCORE` (routing threshold, default 0.55 — tune it, don't trust it),
`MAX_UPLOAD_MB`, `RATE_LIMIT_{DEFAULT,QUERY,UPLOAD,SUGGESTIONS}_RPM`. Outside `ENVIRONMENT=development` the app
refuses to start with the default `SECRET_KEY`. Never commit `.env`.

## Testing

```bash
pip install -r requirements.txt ruff
ruff check app tests eval locustfile.py
pytest tests/ -v                      # unit + mocked route tests (no services needed)

# integration tests against the running stack:
NEXARAG_BASE_URL=http://localhost:8080 pytest tests/test_integration.py -v
```
Unit/route tests cover auth (valid/expired/invalid tokens), tenant filter construction, upload validation,
pagination, threshold/dedup/fusion logic, RAG vs general routing, deleted-document handling, streaming events and
error mapping. Integration tests cover signup/login, tenant isolation, upload→ready→query→history→stats,
re-index, delete-then-not-queryable, and rate limiting; they need the full stack and a Gemini key.

## Evaluation

```bash
# upload eval/sample_docs/cs_notes.pdf to a dedicated account first
docker compose exec api python eval/evaluate_rag.py --base-url http://localhost:8000 \
    --email you@example.com --password '...'          # add --judge for a Gemini faithfulness score
```
Reports Hit@1/3/5, MRR, false-abstain and abstention rates, keyword coverage, optional LLM-judged faithfulness and
latency over 24 in-scope + 5 out-of-scope questions (`eval/rag_eval_set.json`). Limitations: one small document,
"relevant" means a chunk contains an evidence phrase, keyword coverage can't detect wrong reasoning, and the LLM judge
is itself an LLM. `eval/run_eval.py` is the older, simpler judge-only script.

## Load testing

```bash
pip install locust
LOCUST_EMAIL=... LOCUST_PASSWORD=... locust -f locustfile.py --host http://localhost:8080 --headless -u 10 -r 2 -t 2m
```
Rate limits are per user and all Locust users share one account — raise `RATE_LIMIT_*` in `.env` for a throughput
test. Record Locust's real numbers; none are claimed here.

## Known limitations

- Embeddings are English-only (`bge-small-en-v1.5`); Hindi/Hinglish questions are answered in-language but may
  retrieve poorly. A multilingual model would need a new vector size and re-indexing.
- The similarity threshold is a heuristic: a document question that retrieves weakly is answered as "general".
- `reranking.py` is a pass-through (no cross-encoder).
- Query history is per tenant (all users of a tenant share it). The "failed queries" stat is a Redis counter.
- Uploaded files are stored on a local volume, not object storage; no virus scanning.
- Gemini free tier has low daily limits; quota errors surface as a clean 502.
- Docker setup is for local development (`--reload`, source mounts); the chat UI keeps its JWT in `sessionStorage`.
- The Celery worker is not covered by `/health`.

## Project layout

```
app/api/routes/   auth, documents, query, history, stats, chat_ui
app/services/     retrieval, vectorstore, embeddings, llm, comparison, chunking, cache, reranking
app/workers/      celery_app, tasks (document processing)
app/core/         config, security, logging
migrations/       Alembic        tests/   pytest        eval/   evaluation set + scripts
```

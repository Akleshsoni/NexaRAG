# DocuMind — Multi-tenant RAG-as-a-service

A production-shaped backend that lets each tenant upload documents and ask
natural-language questions answered only from their own data. Built to
demonstrate backend engineering (auth, async processing, caching, rate
limiting, observability) and AI engineering (chunking, embeddings, hybrid
retrieval, streaming generation, evaluation) in one coherent system.

## Architecture

```
Client → FastAPI gateway (auth, rate limit)
              ├── Ingestion pipeline (Celery + Redis queue) → Vector store (Qdrant)
              └── Query engine (cache + hybrid retrieval)  ↗
                                                            ↓
                                                     LLM provider (Gemini, streamed back)
```

- **Ingestion is async by design.** Upload returns immediately; a Celery
  worker extracts text, chunks it (token-aware, with overlap), embeds it, and
  writes it to the vector store. This keeps the API responsive regardless of
  document size and lets ingestion scale independently of request traffic.
- **Retrieval is hybrid.** Dense vector search (semantic) is fused with BM25
  keyword scoring (exact match) via Reciprocal Rank Fusion, so the system
  doesn't miss literal terms like product codes or names that embeddings can
  blur.
- **Multi-tenancy is enforced at the data layer.** Every vector and SQL row
  carries a `tenant_id`; queries are filtered server-side, not just hidden in
  the UI.
- **Generation streams over SSE** so the client sees tokens as they're
  produced instead of waiting for the full answer.
- **Caching, rate limiting, and token accounting** live at the query layer so
  the system has a defensible answer to "what does this cost to run" and
  "how do you stop one tenant from starving the others."

## Quickstart

```bash
cp .env.example .env          # fill in GEMINI_API_KEY and VOYAGE_API_KEY
docker compose up --build
```

API docs: http://localhost:8000/docs

```bash
# 1. Sign up (creates a tenant)
curl -X POST localhost:8000/auth/signup -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"changeme","tenant_name":"Acme"}'

# 2. Upload a document
curl -X POST localhost:8000/documents -H "Authorization: Bearer <token>" \
  -F "file=@somefile.pdf"

# 3. Ask a question
curl -X POST localhost:8000/query -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"question":"What does this document say about X?"}'
```

## Running the evaluation

Once you have real documents and a golden question set:

```bash
pip install -r requirements.txt
python eval/run_eval.py --token <your-jwt> --dataset eval/golden_set.json
```

This scores every answer against a reference using Gemini as a judge, and
reports average score + latency — track this across prompt or chunking
changes to know whether you actually improved retrieval quality.

## What to build next (stretch goals)

- Reranking with a cross-encoder after initial retrieval
- A text-to-SQL agent for structured data alongside document RAG
- Per-tenant usage dashboards (Grafana + Prometheus)
- Load testing with Locust to get real p95 latency numbers under concurrency

## Project layout

```
app/
  core/      settings, JWT/password helpers
  db/        async SQLAlchemy session
  models/    Tenant, User, Document, QueryLog
  schemas/   Pydantic request/response models
  services/  chunking, embeddings, vector store, hybrid retrieval, LLM calls
  api/routes/ auth, documents, query (incl. SSE streaming)
  workers/   Celery app + ingestion task
eval/        evaluation harness + golden dataset
tests/       pytest suite
```

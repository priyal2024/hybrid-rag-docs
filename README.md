# hybrid-rag-docs

A production-shaped hybrid-search RAG assistant over the React and Next.js
documentation. "Hybrid" means retrieval fuses two signals — Postgres
full-text (keyword) search and `pgvector` semantic similarity — via
Reciprocal Rank Fusion, rather than leaning on embeddings alone.

## Why this exists

Built as a portfolio piece to demonstrate full-stack + applied-AI engineering:
async ingestion pipelines, retrieval design, LLM integration, auth, and a
containerized/K8s deploy — not just a wrapper around a vector-search library.

## Architecture

```
                 ┌─────────────┐
   docs source → │  ingestion  │ → Kafka → worker → Postgres (pgvector + tsvector)
 (react.dev,     │   fetcher   │           (embeds via sentence-transformers)
  nextjs.org)    └─────────────┘

  Next.js chat UI → FastAPI /ask → hybrid search (RRF) → Groq LLM → streamed answer + citations
                                 ↕
                              Redis (query result cache)
```

## Stack

| Layer | Choice |
|---|---|
| Frontend | Next.js (App Router, TypeScript, Tailwind) |
| Backend | FastAPI (Python) |
| Vector store | Postgres + `pgvector` (HNSW index, cosine distance) |
| Keyword search | Postgres full-text (generated `tsvector` column + GIN index) |
| Cache | Redis (search result cache) |
| Queue | Kafka — async doc ingestion (see note below) |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` (local, no API cost) |
| Generation | Groq (OpenAI-compatible client — swappable to real OpenAI via `LLM_BASE_URL`) |
| Auth | OpenID Connect (Google) |
| Migrations | Alembic |
| Testing | pytest (backend, against a dedicated test DB), Jest (frontend) |
| CI/CD | GitHub Actions (Postgres + Redis service containers) |
| Deploy | Docker Compose (dev), Kubernetes manifests (tested against local `kind`/`minikube`) |

**Why Kafka instead of RabbitMQ:** the original plan (and the JD this project
targets) named either as acceptable. Kafka was already running locally in
dev, so it's what got exercised end-to-end here — RabbitMQ would fill
exactly the same role (decoupling chunking from embedding) with a
`pika`/`aio-pika` producer/consumer swapped in for `confluent-kafka`.

## Status

Milestone-based build, tracked incrementally:

- [x] **M0** — monorepo scaffold, health endpoint, CI skeleton
- [x] **M1** — ingestion pipeline: sparse-clones react.dev/next.js doc sources,
      heading-aware chunker (2 unit-tested edge cases fixed: non-nested heading
      paths, un-split oversized paragraphs), Kafka producer/consumer, worker
      embeds + upserts (idempotent via `content_hash`) into Postgres
- [x] **M2** — hybrid search API: RRF fusion over pgvector cosine search +
      Postgres full-text search, Redis-cached, full corpus (6,389 chunks)
      ingested and verified against real queries
- [ ] **M3** — RAG generation endpoint with streamed citations
- [ ] **M4** — OIDC auth + chat frontend
- [ ] **M5** — Kubernetes manifests, full CI/CD, architecture writeup

## Local development

```bash
docker compose up --build
```

- Backend: http://localhost:8000/docs
- Frontend: http://localhost:3000

This machine's Docker daemon wasn't available during development, so M1/M2
were built and verified against native Homebrew services instead
(`postgresql@17` + `pgvector`, `redis`, `kafka` in KRaft mode) — the
`docker-compose.yml` path is written and structurally consistent with that
setup but hasn't itself been run end-to-end yet. Worth a real
`docker compose up` smoke test before relying on it.

### Backend only

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate   # needs Python ≥ 3.13
pip install -r requirements.txt
cp .env.example .env   # then fill in DATABASE_URL / TEST_DATABASE_URL for your setup
alembic upgrade head
uvicorn app.main:app --reload
```

```bash
pytest -q   # DB-backed tests skip automatically if TEST_DATABASE_URL is unreachable
```

### Ingesting the doc corpus

```bash
cd backend
python -m ingestion.produce           # fetch + chunk + publish all sources to Kafka
python -m worker.consume              # consume, embed, upsert into Postgres (runs until killed)
```

Use `--source react|nextjs` and `--limit N` on `produce.py` for a quick
partial run instead of the full ~6,400-chunk corpus.

### Frontend only

Requires Node ≥ 20.9 (see `.nvmrc`):

```bash
cd frontend
nvm use
npm install
npm run dev
```

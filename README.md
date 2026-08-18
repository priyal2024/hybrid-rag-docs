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
   docs source → │  ingestion  │ → RabbitMQ → worker → Postgres (pgvector + tsvector)
 (react.dev,     │   fetcher   │
  nextjs.org)    └─────────────┘

  Next.js chat UI → FastAPI /ask → hybrid search (RRF) → Groq LLM → streamed answer + citations
                                 ↕
                              Redis (query/embedding cache)
```

## Stack

| Layer | Choice |
|---|---|
| Frontend | Next.js (App Router, TypeScript, Tailwind) |
| Backend | FastAPI (Python) |
| Vector store | Postgres + `pgvector` |
| Keyword search | Postgres full-text (`tsvector`) |
| Cache | Redis |
| Queue | RabbitMQ (async doc ingestion) |
| Embeddings | `sentence-transformers` (local, no API cost) |
| Generation | Groq (OpenAI-compatible client — swappable to real OpenAI via `LLM_BASE_URL`) |
| Auth | OpenID Connect (Google) |
| Testing | pytest (backend), Jest (frontend) |
| CI/CD | GitHub Actions |
| Deploy | Docker Compose (dev), Kubernetes manifests (tested against local `kind`/`minikube`) |

## Status

Milestone-based build, tracked incrementally:

- [x] **M0** — monorepo scaffold, health endpoint, CI skeleton
- [ ] **M1** — ingestion pipeline (fetch → chunk → queue → embed)
- [ ] **M2** — hybrid search API (RRF fusion + Redis cache)
- [ ] **M3** — RAG generation endpoint with streamed citations
- [ ] **M4** — OIDC auth + chat frontend
- [ ] **M5** — Kubernetes manifests, full CI/CD, architecture writeup

## Local development

```bash
docker compose up --build
```

- Backend: http://localhost:8000/docs
- Frontend: http://localhost:3000
- RabbitMQ management UI: http://localhost:15672 (guest/guest)

### Backend only

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

```bash
pytest -q
```

### Frontend only

Requires Node ≥ 20.9 (see `.nvmrc`):

```bash
cd frontend
nvm use
npm install
npm run dev
```

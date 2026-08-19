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
- [x] **M3** — RAG generation: `POST /ask` streams an SSE response (sources
      event first, then tokens, then done) from retrieved chunks through an
      OpenAI-compatible client pointed at Groq. **Needs a free API key to
      generate live** — see below; without one, only the no-context path is
      exercised. Also chased down a genuinely nasty intermittent test hang
      here — see [`tests/conftest.py`](backend/tests/conftest.py) — a
      test-boundary race between `TRUNCATE`'s exclusive lock and a prior
      test's still-finishing background-thread HTTP request; fixed by
      switching to `DELETE`, confirmed clean across 5 consecutive runs.
- [x] **M4** — Google OIDC login (Auth.js v5) gates the whole app via
      `src/proxy.ts` (Next.js 16 renamed `middleware.ts` → `proxy.ts` — caught
      by reading the docs bundled in `node_modules/next/dist/docs/` before
      writing it, per the repo's own `AGENTS.md` note); streaming chat UI
      wired to `/ask` via a hand-rolled SSE parser (unit-tested against the
      real edge case: an event split across two stream reads). Verified live
      end-to-end in a real browser — question → hybrid search → 6 correct
      sources → graceful error message when no LLM key is configured. That
      last part started as a real bug: a raw `curl` test against `/ask`
      showed the connection just dying mid-stream after `sources` with no
      explanation once an LLM call failed — fixed to surface a proper error
      token instead, with a regression test.
- [x] **M5** — full K8s manifests (namespace, ConfigMap/Secret, Postgres +
      Kafka StatefulSets, migrate Job, backend/worker/frontend Deployments,
      Ingress) deployed to a real local cluster (`kind` on Podman, since
      Docker Desktop wasn't available — see [`k8s/README.md`](k8s/README.md))
      and verified pod-by-pod, not just `apply`-and-hope. This surfaced four
      real, fixed bugs, in roughly ascending order of subtlety:
      1. Kafka's `KAFKA_CONTROLLER_QUORUM_VOTERS` references its own pod by
         stable DNS name (`kafka-0.kafka`), which only a **headless** Service
         provides — a normal ClusterIP Service left it stuck permanently
         un-Ready (`UnknownHostException`).
      2. Headless Services only publish DNS for **Ready** endpoints by
         default — but Kafka needs to resolve its own address *to become*
         Ready, a bootstrap deadlock fixed with `publishNotReadyAddresses: true`.
      3. Podman tags local builds as `localhost/<name>`; manifests referencing
         `<name>:local` (no prefix) resolved to Docker Hub instead and failed
         to pull.
      4. A real pydantic-settings gotcha: `list[str]`-typed settings fields
         get JSON-decoded *before* any custom validator runs, so the
         ConfigMap's plain comma-separated `CORS_ALLOW_ORIGINS` crash-looped
         the backend the moment it was set via a real env var (it never came
         up locally, where the field's Python-list default never touches env
         parsing at all) — fixed by typing it as `str` with a computed
         property instead of fighting pydantic's complex-type decoding.
      5. (Not a manifest bug, but real:) the embedding model call hung
         indefinitely the first time `/search` actually ran in-cluster.
         Root-caused to `sentence-transformers`' download path hitting Hugging
         Face's CDN (`cas-server.xethub.hf.co` / `*.cdn.hf.co`) — a domain
         distinct from `huggingface.co` itself, which *was* reachable, so an
         initial "the network's fine" check was misleading. Confirmed via a
         clean SSL certificate error, the same self-signed-cert-in-chain
         signature as the pytorch.org block below — this sandbox's egress
         proxy MITM-intercepts non-allowlisted domains. Fixed properly (not
         just worked around): the model's weights are now baked into the
         image at build time, which is also just better production practice
         regardless — no ML-serving pod should depend on external network
         access at cold start.

### Setting up Google sign-in (optional)

### Setting up Google sign-in (optional)

The chat UI is gated behind Google OIDC login. Without credentials configured,
`/signin` renders fine but clicking through will fail. To make it real:

1. Create an OAuth client at [console.cloud.google.com/apis/credentials](https://console.cloud.google.com/apis/credentials)
   (type: Web application; authorized redirect URI: `http://localhost:3000/api/auth/callback/google`)
2. In `frontend/.env.local`, set `AUTH_GOOGLE_ID`, `AUTH_GOOGLE_SECRET`, and
   `AUTH_SECRET` (generate one with `npx auth secret`)

### Running M3 for real (optional)

`/ask` needs an LLM API key to generate answers (the no-context path works
without one). Get a free key at [console.groq.com](https://console.groq.com),
then set `LLM_API_KEY` in `backend/.env`. To point at real OpenAI instead,
also change `LLM_BASE_URL` to `https://api.openai.com/v1` and `LLM_MODEL` to
an OpenAI model name — no code changes either way.

## How this was built

Built end-to-end with Claude Code, milestone by milestone (M0–M5, each its
own commit), with the model doing the driving and me steering scope and
reviewing diffs rather than typing every line. A few moments worth being
concrete about, since "I used an agent" means nothing without specifics:

- **It found real bugs, not just wrote code.** The chunker's unit tests
  caught two actual defects on first run — heading paths weren't nesting
  (`h3` sections silently dropped their parent `h2` from the breadcrumb),
  and a single overlong paragraph with no internal blank line wasn't being
  split at all. Both are the kind of thing that look fine on a quick skim
  and only show up against real data.
- **A live smoke test (not just green tests) surfaced a real bug.** Running
  the actual `/ask` endpoint against `curl` — after the whole test suite
  already passed — showed the SSE stream just dying mid-response once the
  LLM call failed, no error, no `done` event. Tests alone wouldn't have
  caught this; it took actually hitting the running service.
- **It read the docs before writing code, not after debugging.** Next.js 16
  renamed `middleware.ts` → `proxy.ts`; the repo's own `AGENTS.md` (written
  by `next dev` itself) says as much and points at `node_modules/next/dist/docs/`
  for what else changed. Checking that first meant writing `proxy.ts`
  correctly the first time instead of debugging a silently-ignored
  `middleware.ts` later.
- **It chased a genuinely hard bug to a real root cause instead of settling
  for a plausible-sounding one.** An intermittent test-suite hang went
  through three wrong hypotheses (a tokenizers/torch fork deadlock, a
  Hugging Face Hub network check, stale connections left over from earlier
  debugging) before `faulthandler.dump_traceback_later` plus live
  `pg_stat_activity` polling proved it was a real race: `TRUNCATE`'s
  exclusive lock colliding with a previous test's HTTP request still
  finishing on a background thread pool a few milliseconds later. Each
  wrong theory was tested and disproven with evidence, not asserted from
  pattern-matching — that discipline is the actual skill, not just knowing
  the `DELETE`-vs-`TRUNCATE` fix.
- **It made a pragmatic engineering call under real constraints, and said so.**
  Docker Desktop wasn't available in this environment; RabbitMQ vs. Kafka
  and Homebrew-native services vs. containers were both decisions made
  transparently, documented in-line rather than silently working around the
  gap.
- **It didn't stop at "the manifests apply cleanly."** Getting the K8s stack
  actually *running* (not just `kubectl apply`-able) surfaced four real bugs
  in sequence — see M5 below — each diagnosed with the actual evidence
  (`pg_stat_activity`-style DNS/log/exec inspection, not guessing) rather than
  declaring victory at the first green `kubectl get pods`. The last one
  looked like a hang with no error at all; the fix was to keep narrowing
  (is the network actually the problem? which domain, specifically? is that
  the *same* failure signature as an earlier, unrelated build issue?) until
  a concrete SSL error confirmed the cause, rather than accepting the first
  plausible-sounding explanation.
- **It caught its own mistakes before they shipped.** `frontend/.env.example`
  had been silently gitignored since M1 — a `.env*` rule in create-next-app's
  own generated `.gitignore` shadowed the root repo's `!.env.example`
  exception, so the file existed on disk but was never actually committed,
  which would have quietly broken the README's own setup instructions for
  anyone cloning the repo. Caught by checking `git status --ignored` while
  staging M4, not by a user report.

None of this is "the AI wrote a CRUD app" — it's what building with an
agentic coding tool actually looks like day to day: fast iteration on the
easy 80%, and genuine debugging discipline (form a hypothesis, gather
evidence, disprove it if it's wrong, repeat) on the hard 20%.

## Local development

```bash
docker compose up --build
```

- Backend: http://localhost:8000/docs
- Frontend: http://localhost:3000

This machine's Docker daemon wasn't available during development. Early
milestones (M1/M2) were built and verified against native Homebrew services
instead (`postgresql@17` + `pgvector`, `redis`, `kafka` in KRaft mode); for
M5's Kubernetes manifests, **Podman** stood in for Docker as the actual
container runtime (see [`k8s/README.md`](k8s/README.md)) — real image builds,
a real local cluster (`kind`), every pod verified `Running`/`Ready`, migrations
applied, and `/health` + `/search` + `/ask` all smoke-tested through the
actual K8s Services, not just `kubectl apply` and a hopeful glance. The
`docker-compose.yml` path itself (as opposed to K8s) is written and
structurally consistent with the same service topology but hasn't been run
through literal `docker compose up` — worth a smoke test on a machine with
Docker Desktop running, though `podman compose up` should work identically
since the compose spec doesn't care which engine executes it.

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
cp .env.example .env.local   # fill in AUTH_SECRET / AUTH_GOOGLE_ID / AUTH_GOOGLE_SECRET
npm run dev
```

```bash
npm test   # SSE-parser unit tests
```

# Backend — AI Workflow Copilot

FastAPI service implementing the **propose → validate → commit** loop described
in [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md), exposing the API in
[`../docs/API_CONTRACT.md`](../docs/API_CONTRACT.md).

## Run

```bash
# local dev (SQLite, no external services needed)
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload          # http://localhost:8000, docs at /docs

# tests (unit + full end-to-end scenario over REST/SSE)
pip install pytest pytest-asyncio && pytest
```

Or from the repo root: `docker compose up --build`.

## Configuration (env)

| Var | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./copilot.db` | compose sets Postgres (`postgresql+asyncpg://…`) |
| `REDIS_URL` | *(unset)* | unset → in-memory event bus; set → Redis pub/sub + replay list |
| `ANTHROPIC_API_KEY` | *(unset)* | unset → scripted provider only (fully offline demo) |
| `ANTHROPIC_MODEL` | `claude-sonnet-5` | |
| `MAX_REPAIR_ATTEMPTS` | `3` | bounded repair loop |
| `LLM_TIMEOUT_SECONDS` | `30` | per-call deadline |

## Layout

```
app/
  main.py        FastAPI app, CORS, error envelope, startup seeding
  config.py      env-driven settings
  db.py models.py schemas.py
  catalog/       node type definitions — JSON files, seeded (upserted) at boot.
                 POST /node-catalog adds types at runtime: data, not code.
  core/
    operations.py  apply ops to a COPY of the graph (never mutates input)
    validator.py   deterministic gate: catalog membership, JSON-Schema configs,
                   ports, single trigger, reachability, cycles
    diff.py        structural diff between any two versions, as operations
    events.py      event bus (in-memory default, Redis impl) with
                   Last-Event-ID replay for SSE reconnects
    catalog.py     seeding + lexical search (pgvector seam documented inline)
  llm/
    base.py        LLMProvider interface (+ the <context> convention)
    anthropic_provider.py
    scripted.py    deterministic offline planner (provider of last resort)
    chain.py       timeout → retry → circuit breaker → failover
  agent/
    graph.py       LangGraph state machine: plan → retrieve → propose →
                   validate → (commit | repair | fail) → explain
    runner.py      run lifecycle: background task, event emission, persistence
    prompts.py
tests/             18 unit tests + 7 end-to-end scenario tests
```

## Design notes (the short version)

- **The AI never writes state.** The agent's only output is `operations[]`.
  They're applied to a copy, validated by pure code against the DB catalog,
  and only then committed — as a new **immutable version** (append-only, so
  failed runs can't half-mutate anything).
- **Repair loop is bounded** (`MAX_REPAIR_ATTEMPTS`). Validator errors carry
  machine codes and "did you mean" hints that are fed back to the planner.
- **Every LLM failure mode has a coded path** (see the recovery table in the
  architecture doc): hallucinated node → `unknown_node_type` rejection;
  malformed JSON → one retry with the parse error; timeout → retry w/ backoff;
  provider down → circuit breaker + failover down the chain. The chain ends in
  a deterministic scripted provider so the demo runs with zero API keys —
  it implements the same `LLMProvider` interface and reads the same
  structured `<context>` block real providers get.
- **Runs are async**: `POST …/messages` returns `202 {run_id}` immediately;
  the agent executes in a background task and streams progress over the event
  bus → SSE. The bus is the seam for moving execution to a real worker pool
  (the API process only needs subscribe).
- **Demo levers**: include `!hallucinate` in a message to watch the validator
  reject and repair a hallucinated node; `!timeout` to see a clean provider
  failure (error + `done{failed}`, nothing persisted).

## Deliberately stubbed (and where the real thing goes)

- **Execution engine** — versions are engine-agnostic graph snapshots; an
  `Executor` adapter would read a version and run it.
- **Auth / multi-tenancy** — every table would gain a `tenant_id`; the
  catalog-write endpoint goes behind admin auth.
- **Vector search** — `core/catalog.search_nodes` is lexical token overlap
  with the same signature as the pgvector cosine query that replaces it at
  scale (hundreds of nodes).
- **Worker pool** — background asyncio tasks in-process today; the Redis bus
  + idempotent run rows make the split to dedicated workers a deploy change.

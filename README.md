# AI Workflow Copilot

An AI Copilot that lets users **create, modify, debug, and understand** automation workflows (Zapier/n8n-style) through natural-language chat — built to stay reliable despite LLM failures and an evolving node catalog.

> Take-home for **Zoft AI**. Evaluated on **engineering judgement over feature completeness**.

## The core idea (read this first)

**The AI never mutates persistent state.** It is a *planner* that proposes **operations**; a deterministic, code-only **validator** checks them against a DB-driven node catalog; only valid operations **commit as a new immutable workflow version**. Invalid proposals trigger a bounded **repair loop** and are never persisted.

```
chat → agent (LangGraph) → propose operations → deterministic validate → commit new version
                                   ↑__________ repair loop (bounded) __________|
```

This single pattern answers safety, versioning, explainability ("why did you change that?"), reliability, and "new nodes without redeploys" together.

## Structure

| Path | What |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Backend AI platform design, data model, reliability & scaling |
| [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) | The FE ↔ BE contract (either side buildable independently) |
| `backend/` | Python · FastAPI · LangGraph · PostgreSQL · Redis |
| `frontend/` | React · Vite · Tailwind (hand-rolled components) · SSE streaming |

## Stack & key decisions

- **Backend:** Python + FastAPI (async, best AI ecosystem).
- **Agent:** LangGraph state machine — `plan → retrieve nodes → propose ops → validate → repair → commit → explain`, emitting progress at each step.
- **Persistence:** PostgreSQL (workflows, immutable versions, conversations, runs, node catalog); commits are optimistic-concurrency-safe (CAS on the workflow head).
- **Async:** `202 {run_id}` + a background task per run; progress flows over a pluggable event bus (in-memory or Redis pub/sub with replay). A dedicated worker pool is the documented scale path — the bus is the seam.
- **Streaming:** **SSE** (one-way server→client, auto-reconnect, plain HTTP; cancellation is a separate endpoint). See rationale in the API contract.
- **Node catalog is data, not code** — node types live in the DB with JSON-Schema configs; the agent retrieves them via RAG/tools, so new nodes need no redeploy.

## Scope (deliberate)

Built end-to-end for the reference scenario — *"Slack message when Stripe receives a payment" → swap Slack for Teams → only notify > $500 / weekdays → explain → fix → why the change* — with a small but dynamically-loaded catalog (Stripe trigger, Slack, MS Teams, Filter). Integration *execution*, auth/multi-tenancy, and a large catalog are stubbed; scaling approaches are documented in `ARCHITECTURE.md`.

## Run

```bash
docker compose up --build
# frontend → http://localhost:5173   backend API → http://localhost:8000 (docs at /docs)
```

No API keys needed: the LLM provider chain ends in a **deterministic scripted
provider**, so the full demo runs offline. Set `ANTHROPIC_API_KEY` on the
backend service to put a real model at the front of the chain — the scripted
provider then becomes the failover target.

Local dev without Docker (SQLite + in-memory bus, zero services). One command:

```bash
./run-local.sh          # starts backend :8000 + frontend :5173, prints the URL
```

Then open **http://localhost:5173**. Requires Python 3.11+ and Node 20+.
On Windows use Git Bash / WSL, or run the two halves by hand:

```bash
cd backend && python -m venv .venv && . .venv/bin/activate \
  && pip install -r requirements.txt && uvicorn app.main:app --port 8000
cd frontend && npm install && npm run dev     # http://localhost:5173
```

Tests: `cd backend && pytest` — 33 tests including a full end-to-end run of the
reference conversation over REST + SSE, hallucination-repair, timeout failure,
concurrent-edit conflict, and SSE replay; the suite runs unchanged against
SQLite and Postgres.

**Demo levers** (type in chat): `!hallucinate` makes the planner propose a
non-existent node so you can watch the validator reject it and the repair loop
recover; `!timeout` simulates a hung provider (clean failure, nothing persists).

## Try this conversation

1. *Send a Slack message to #sales when Stripe receives a payment* → creates v1
2. *Use Microsoft Teams instead of Slack* → v2, diff visible in History
3. *Only notify me for payments over $500 on weekdays* → v3 inserts a filter
4. *Explain what this workflow does* → read-only, no new version
5. *Why did you change that?* → answers from the stored rationale + operations

See `backend/README.md`, `frontend/README.md`, and `docs/DEMO.md` (video script).

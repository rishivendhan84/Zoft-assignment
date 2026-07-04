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
| `backend/` | Python · FastAPI · LangGraph · PostgreSQL/pgvector · Redis |
| `frontend/` | React · Vite · Tailwind · shadcn/ui · SSE streaming |

## Stack & key decisions

- **Backend:** Python + FastAPI (async, best AI ecosystem).
- **Agent:** LangGraph state machine — `plan → retrieve nodes → propose ops → validate → repair → commit → explain`, emitting progress at each step.
- **Persistence:** PostgreSQL + pgvector (workflows, immutable versions, conversations, node-catalog embeddings).
- **Async:** Redis-backed workers for generation, validation, embedding, indexing.
- **Streaming:** **SSE** (one-way server→client, auto-reconnect, plain HTTP; cancellation is a separate endpoint). See rationale in the API contract.
- **Node catalog is data, not code** — node types live in the DB with JSON-Schema configs; the agent retrieves them via RAG/tools, so new nodes need no redeploy.

## Scope (deliberate)

Built end-to-end for the reference scenario — *"Slack message when Stripe receives a payment" → swap Slack for Teams → only notify > $500 / weekdays → explain → fix → why the change* — with a small but dynamically-loaded catalog (Stripe trigger, Slack, MS Teams, Filter). Integration *execution*, auth/multi-tenancy, and a large catalog are stubbed; scaling approaches are documented in `ARCHITECTURE.md`.

## Run

```bash
docker compose up --build   # backend + frontend + postgres + redis
```

See `backend/README.md` and `frontend/README.md`.

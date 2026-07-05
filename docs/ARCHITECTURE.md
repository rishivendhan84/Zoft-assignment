# Backend Architecture — AI Workflow Copilot

## 1. Design philosophy

Three constraints shape every decision:

1. **The AI is untrusted.** LLMs hallucinate, emit invalid JSON, call missing tools, and time out. So the AI is only ever allowed to *propose*; a deterministic layer decides what persists.
2. **The catalog evolves without deploys.** Node definitions are data. Nothing in the codebase hardcodes "Slack" or "Stripe."
3. **FE and BE are separate teams.** The only coupling is a documented API contract (`API_CONTRACT.md`).

## 2. The central pattern: Propose → Validate → Commit

```
                 ┌─────────────────────────────────────────────┐
 user message →  │  LangGraph Agent (planner, stateless re DB)  │
                 │  retrieval: search_nodes / get_node_schema   │
                 │  proposal: schema-constrained JSON output    │
                 └───────────────┬─────────────────────────────┘
                                 │  Operation[]  (never raw state writes)
                                 ▼
                 ┌─────────────────────────────────────────────┐
                 │  Deterministic Validator (pure code)         │
                 │  • apply ops to a COPY of current version    │
                 │  • JSON-Schema check every node config       │
                 │  • graph rules: no dangling edges, required  │
                 │    ports connected, type-compatible, 1 trigger│
                 └───────┬───────────────────────┬─────────────┘
                    valid│                  invalid│  (errors)
                         ▼                         ▼
              ┌──────────────────┐      ┌────────────────────────┐
              │ Commit: write a  │      │ Repair loop (≤ N):      │
              │ new immutable    │      │ feed errors back to the │
              │ workflow_version │      │ agent → re-propose      │
              └──────────────────┘      └────────────────────────┘
```

**Why operations, not full workflow JSON?** Operations (`add_node`, `remove_node`, `connect`, `disconnect`, `set_config` — conditions are just `set_config` on a logic node) are small, diffable, and independently validatable. They give us version diffs, audit history, and "why did you change that?" for free, and they keep the LLM's output surface tiny (far fewer ways to be wrong than emitting an entire graph).

## 3. Workflow representation

A workflow is a **directed graph of nodes**. Each node instance references a `node_type` from the catalog and carries a `config` object validated against that type's JSON Schema.

```jsonc
// workflow_version.graph
{
  "nodes": [
    { "id": "n1", "type": "stripe.payment_received", "config": {} },
    { "id": "n2", "type": "logic.filter",
      "config": { "field": "amount", "op": ">", "value": 500 } },
    { "id": "n3", "type": "slack.send_message",
      "config": { "channel": "#sales", "text": "New payment: {{amount}}" } }
  ],
  "edges": [
    { "from": "n1", "to": "n2" },
    { "from": "n2", "to": "n3", "port": "true" }
  ]
}
```

Swapping Slack→Teams = `remove_node(n3)` + `add_node(teams.send_message)` + `connect(n2→n4)` — three validated operations, one new version.

## 4. Node catalog (data, not code)

```
node_catalog(
  type            text primary key,     -- "slack.send_message"
  category        text,                 -- trigger | action | logic
  title           text,
  config_schema   jsonb,                -- JSON Schema for `config`
  input_ports     jsonb,                -- [] for triggers
  output_ports    jsonb,                -- e.g. ["true","false"] for filter
  embedding       vector(1536)          -- for semantic search at scale (pgvector)
)
```

- New node = a new row (or `POST /node-catalog`). **No redeploy.**
- The agent discovers nodes via `search_nodes(query)` and reads `get_node_schema(type)` before configuring — it never guesses a node exists. *In this demo* `search_nodes` is lexical token-overlap behind the same signature; the `embedding` column + pgvector cosine query is the drop-in replacement once the catalog grows past what keyword match handles (hundreds of nodes).
- The validator uses `config_schema` + `input/output_ports` as the source of truth.

## 5. Agent design (LangGraph)

A state machine, each transition emitting a progress event over SSE:

| Node | Does | Emits |
|---|---|---|
| `plan` | Interpret intent from message + conversation memory | `Planning workflow…` |
| `retrieve` | `search_nodes` + `get_node_schema` (RAG over catalog; always includes schemas for types already in the graph) | `Searching available nodes…`, `Reading {node} schema…` |
| `propose` | Produce `Operation[]` as schema-constrained JSON (a parse failure triggers one targeted retry with the error injected) | `Generating changes…` |
| `validate` | Call deterministic validator | `Calling validator…` |
| `repair` | On failure, add errors to context, loop (≤ N) | `Fixing missing configuration…` |
| `commit` | Persist new version, link rationale | `Saving version…` |
| `explain` | Summarize the diff in natural language | streamed tokens, `Done.` |

Memory: the last version (operations + rationale) plus a recent-message window (last 6) go into the planning context; only *relevant* node schemas are pulled in. At scale the window becomes a rolling conversation summary — same context slot, cheaper to produce than to retrofit.

## 6. Reliability — recovery strategy

| LLM failure | Detection | Recovery |
|---|---|---|
| Hallucinated node | Validator: unknown `type` | Repair loop with "did you mean" hint from catalog |
| Invalid JSON | JSON-mode output; parse guard | Retry once with the parse error injected |
| Invalid operation | Op applier rejects unknown/malformed ops | Rejected list fed back → re-propose |
| Context limit | Recent-message window + RAG-trimmed schemas | Rolling summary at scale (same context slot) |
| Incomplete answer | Validator: missing required config | Errors fed back → targeted repair |
| Timeout | Per-call deadline | One retry with backoff → fallback provider |
| Provider unavailable | Circuit breaker per provider (process-wide state) | Route to next provider in the chain |
| Concurrent edits | Commit is a CAS on the workflow head | Loser fails with recoverable `workflow_conflict`; nothing clobbered |
| Server restart mid-run | Startup sweep finds `running` runs | Marked failed + `done` published; clients settle cleanly |

Every repair is **bounded** (max N). On exhaustion the run ends in a clean `failed` state with a human-readable reason — the DB is never left partially mutated because commit is the *last* step and versions are immutable.

## 7. Persistence (PostgreSQL)

```
workflows(id, name, current_version_id, created_at, updated_at)
workflow_versions(
  id, workflow_id, parent_version_id,
  graph jsonb, operations jsonb,        -- the ops that produced this version
  author enum('user','ai'), rationale text, created_at)   -- immutable
conversations(id, workflow_id, title, created_at)
messages(id, conversation_id, role, content, run_id, created_at)
runs(id, conversation_id, workflow_id, status, error, created_at)  -- one per user message
node_catalog(...)  -- see §4
```

- **Immutable versions** → free history, diff, rollback, and audit.
- `operations` + `rationale` per version power *"why did you make that change?"* deterministically (no re-asking the LLM).
- **Commit is optimistic-concurrency-safe**: advancing `workflows.current_version_id` is a compare-and-swap against the version the run planned on; a concurrent commit makes the loser fail with a recoverable `workflow_conflict` instead of silently reverting the winner's change.

## 8. Asynchronous processing

Slow work (generation, validation of large graphs, embedding, catalog indexing) never blocks the request path.

- `POST …/messages` returns `202 {run_id}` immediately; the agent run executes as a background task and publishes progress to an **event bus** the SSE endpoint subscribes to.
- The bus has two implementations behind one interface: **in-memory** (default, zero-dependency dev) and **Redis** (pub/sub + a replay list per run, giving `Last-Event-ID` resume across API instances). The bus is the seam: moving runs from in-process tasks to a dedicated **worker pool** is a deployment change — the API only ever *subscribes*.
- Runs are **idempotent rows keyed by run_id** (status: running/completed/failed/cancelled); in a worker deployment, failed jobs land in a **dead-letter queue** for inspection.

## 9. Performance & scale (100k workflows, 10k convos/day, hundreds of nodes)

- **Reads:** current version denormalized on `workflows.current_version_id`; versions are append-only → cache-friendly; read replicas for history/analytics.
- **Catalog search:** pgvector IVFFlat index on `embedding` (the demo's lexical search shares the same interface; see §4); catalog is small and cacheable in memory.
- **Big graphs:** operations validate incrementally against a copy; no full re-serialization on the wire (send ops + resulting version, not the whole editor state).
- **Providers:** provider abstraction with per-provider rate-limit + circuit breaker; cost tracked per run.
- **Horizontal scale:** stateless API + worker pool behind a queue; Postgres partitioning of `messages`/`jobs` by time if needed.

## 10. Extensibility (the four asks)

| Add… | How |
|---|---|
| New node type | Insert a `node_catalog` row (+embedding). Zero code. |
| New LLM provider | Implement the `LLMProvider` interface; add to the fallback chain. |
| New AI tool | Add a retrieval/context step to the agent graph (each node is an isolated function over `AgentState`). |
| New workflow engine | The graph is engine-agnostic; add an `Executor` adapter that reads a version and runs it. |

## 11. Observability

Structured logs + per-run trace (each LangGraph node = a span), metrics (run latency, repair count, validation pass rate, provider failovers, cost). Every run is reconstructable from `messages` + `workflow_versions.operations`.

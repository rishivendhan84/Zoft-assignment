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
                 │  tools: search_nodes, get_node_schema,       │
                 │         get_workflow, propose_operations      │
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

**Why operations, not full workflow JSON?** Operations (`add_node`, `remove_node`, `connect`, `disconnect`, `set_config`, `set_condition`) are small, diffable, and independently validatable. They give us version diffs, audit history, and "why did you change that?" for free, and they keep the LLM's output surface tiny (far fewer ways to be wrong than emitting an entire graph).

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
  embedding       vector(1536)          -- for semantic search / RAG
)
```

- New node = a new row. **No redeploy.**
- The agent discovers nodes via `search_nodes(query)` (pgvector similarity over `embedding`) and reads `get_node_schema(type)` before configuring — it never guesses a node exists.
- The validator uses `config_schema` + `input/output_ports` as the source of truth.

## 5. Agent design (LangGraph)

A state machine, each transition emitting a progress event over SSE:

| Node | Does | Emits |
|---|---|---|
| `plan` | Interpret intent from message + conversation memory | `Planning workflow…` |
| `retrieve` | `search_nodes` + `get_node_schema` (RAG over catalog) | `Searching available nodes…`, `Reading {node} schema…` |
| `propose` | Produce `Operation[]` via structured tool call | `Generating changes…` |
| `validate` | Call deterministic validator | `Calling validator…` |
| `repair` | On failure, add errors to context, loop (≤ N) | `Fixing missing configuration…` |
| `commit` | Persist new version, link rationale | `Saving version…` |
| `explain` | Summarize the diff in natural language | streamed tokens, `Done.` |

Memory: conversation summary + last version id are kept per conversation; only *relevant* node schemas are pulled into context (keeps us under token limits).

## 6. Reliability — recovery strategy

| LLM failure | Detection | Recovery |
|---|---|---|
| Hallucinated node | Validator: unknown `type` | Repair loop with "valid types near X" hint from catalog |
| Invalid JSON | Structured/JSON-mode output; parse guard | Retry once with the parse error injected |
| Invalid tool call | Tool dispatcher rejects unknown/misparam tool | Return valid tool list → re-propose |
| Context limit | Token budget guard before call | Summarize conversation, RAG-trim node schemas |
| Incomplete answer | Validator: missing required config | Targeted follow-up op request |
| Timeout | Per-call deadline | Exponential backoff → fallback provider |
| Provider unavailable | Circuit breaker per provider | Route to next provider in the chain |

Every repair is **bounded** (max N). On exhaustion the run ends in a clean `failed` state with a human-readable reason — the DB is never left partially mutated because commit is the *last* step and versions are immutable.

## 7. Persistence (PostgreSQL)

```
workflows(id, name, current_version_id, created_at)
workflow_versions(
  id, workflow_id, parent_version_id,
  graph jsonb, operations jsonb,        -- the ops that produced this version
  author enum('user','ai'), rationale text, created_at)   -- immutable
conversations(id, workflow_id, created_at)
messages(id, conversation_id, role, content, created_at)
jobs(id, type, status, progress jsonb, result jsonb, error text)  -- async
node_catalog(...)  -- see §4
```

- **Immutable versions** → free history, diff, rollback, and audit.
- `operations` + `rationale` per version power *"why did you make that change?"* deterministically (no re-asking the LLM).

## 8. Asynchronous processing

Slow work (generation, validation of large graphs, embedding, catalog indexing) runs on **Redis-backed workers**, not in the request path.

- Chat request opens an **SSE stream** immediately and returns a `run_id`.
- The agent run executes on a worker; progress events are published to a Redis channel the SSE endpoint subscribes to.
- Jobs are **idempotent** (keyed by run_id) and failures land in a **dead-letter queue** for inspection.

## 9. Performance & scale (100k workflows, 10k convos/day, hundreds of nodes)

- **Reads:** current version denormalized on `workflows.current_version_id`; versions are append-only → cache-friendly; read replicas for history/analytics.
- **Catalog search:** pgvector IVFFlat index on `embedding`; catalog is small and cacheable in memory.
- **Big graphs:** operations validate incrementally against a copy; no full re-serialization on the wire (send ops + resulting version, not the whole editor state).
- **Providers:** provider abstraction with per-provider rate-limit + circuit breaker; cost tracked per run.
- **Horizontal scale:** stateless API + worker pool behind a queue; Postgres partitioning of `messages`/`jobs` by time if needed.

## 10. Extensibility (the four asks)

| Add… | How |
|---|---|
| New node type | Insert a `node_catalog` row (+embedding). Zero code. |
| New LLM provider | Implement the `LLMProvider` interface; add to the fallback chain. |
| New AI tool | Register in the tool registry; expose to the agent. |
| New workflow engine | The graph is engine-agnostic; add an `Executor` adapter that reads a version and runs it. |

## 11. Observability

Structured logs + per-run trace (each LangGraph node = a span), metrics (run latency, repair count, validation pass rate, provider failovers, cost). Every run is reconstructable from `messages` + `workflow_versions.operations`.

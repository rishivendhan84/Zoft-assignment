# API Contract — Frontend ↔ Backend

This is the **only** coupling between the two teams. Either side can be built independently against this document.

## Transport decisions (and why)

| Concern | Choice | Rationale |
|---|---|---|
| Request/command | **REST (JSON)** | Simple, cacheable, well-understood for CRUD-ish calls (list workflows, get versions). |
| AI run progress | **Server-Sent Events (SSE)** | The stream is **one-directional** (server→client): tokens, step updates, workflow patches. SSE is plain HTTP, has **built-in auto-reconnect** with `Last-Event-ID`, and needs no extra protocol. WebSockets add bidirectional complexity we don't need — the only client→server action mid-run is *cancel*, which is a normal `POST`. |
| Cancel | **REST** `POST /runs/{id}/cancel` | Decouples control from the stream; works even if the stream dropped. |

> If we later need collaborative editing or client→server streaming, we'd revisit WebSockets. For a copilot, SSE is the right-sized choice.

## REST endpoints

```
POST   /conversations                        → { conversation_id }
GET    /conversations                        → [ ConversationSummary ]
GET    /conversations/{cid}/messages         → [ Message ]         (history reload)
GET    /workflows                            → [ WorkflowSummary ]
GET    /workflows/{id}                       → Workflow (current version)
GET    /workflows/{id}/versions              → [ VersionSummary ]
GET    /workflows/{id}/versions/{vid}        → WorkflowVersion (full graph)
GET    /workflows/{id}/diff?from=&to=        → OperationDiff
GET    /node-catalog?query=                  → [ NodeType ]      (semantic search)
POST   /conversations/{cid}/messages         → { run_id }        (starts an AI run)
GET    /runs/{run_id}/events                 → text/event-stream (SSE, see below)
POST   /runs/{run_id}/cancel                 → 202 { status }    (idempotent; body is
                                               'cancelling' or the already-terminal status)
GET    /health                               → { status: "ok" }
POST   /node-catalog                         → 201 { type }      (admin stub: add a node
                                               type at runtime; 409 duplicate, 422 bad schema)
```

All timestamps are ISO-8601 UTC with a `Z` suffix (e.g. `2026-07-05T11:35:09Z`).

`GET /workflows/{id}` response shape (the current version is nested):

```jsonc
{ "id": "wf_123", "name": "Stripe → Slack",
  "current_version_id": "v8", "version": WorkflowVersion | null }
```

### Start a message / run

```jsonc
// POST /conversations/{cid}/messages
{ "content": "Send a Slack message when Stripe receives a payment",
  "workflow_id": "wf_123"           // optional; omitted = create new
}
// → 202 { "run_id": "run_abc" }
```

The client then opens `GET /runs/run_abc/events` to stream progress.

## SSE event stream

`Content-Type: text/event-stream`. Each event has a `type` and JSON `data`. Clients reconnect with `Last-Event-ID`.

```
event: step
data: { "phase": "planning", "label": "Planning workflow…" }

event: step
data: { "phase": "retrieving", "label": "Reading Slack schema…", "tool": "get_node_schema", "arg": "slack.send_message" }

event: token
data: { "text": "I'll add a Stripe trigger" }

event: validation
data: { "status": "running" }

event: validation
data: { "status": "failed", "errors": [ { "node": "n3", "message": "channel is required" } ] }

event: step
data: { "phase": "repairing", "label": "Fixing missing configuration…", "attempt": 1 }

event: workflow_updated
data: { "workflow_id": "wf_123", "version_id": "v8",
        "graph": { "nodes": [...], "edges": [...] },
        "operations": [ { "op": "add_node", "type": "stripe.payment_received", "id": "n1" }, ... ] }

event: message
data: { "role": "assistant", "content": "Done — Stripe now notifies #sales on Slack." }

event: done
data: { "run_id": "run_abc", "status": "completed" }
```

### Event types (exhaustive)

| `event` | `data` | UI use |
|---|---|---|
| `step` | `{ phase, label, tool?, arg?, attempt? }` | Agent-visibility timeline |
| `token` | `{ text }` | Live token streaming of the reply |
| `validation` | `{ status: running\|passed\|failed, errors? }` | Validation progress / failure state |
| `workflow_updated` | `{ workflow_id, version_id, graph, operations }` | Re-render the workflow viz + diff |
| `message` | `{ role, content }` | Final assistant message |
| `error` | `{ code, message, recoverable }` | Failure UI (timeout, provider down…) |
| `done` | `{ run_id, status: completed\|failed\|cancelled }` | Close the stream, settle UI |
| `ping` | `{}` | Keep-alive on idle streams (~30 s); ignore |

`phase` ∈ `planning · retrieving · proposing · validating · repairing · committing · explaining`.
`repairing` steps also carry `attempt` and `max_attempts` (the configured repair budget).

Notable `error` codes: `provider_timeout` / `provider_failover` (recoverable, mid-run),
`provider_unavailable`, `validation_exhausted`, `workflow_conflict` (another run
committed to the same workflow first — retry re-plans against the new head),
`run_interrupted` (server restarted mid-run; nothing was persisted).

## Core types

```ts
type NodeType = {
  type: string; category: 'trigger'|'action'|'logic';
  title: string; config_schema: JSONSchema;
  input_ports: string[]; output_ports: string[];
};

type Operation =
  | { op: 'add_node'; id: string; type: string; config?: object }
  | { op: 'remove_node'; id: string }                       // also drops its edges
  | { op: 'connect'; from: string; to: string; port?: string }
  | { op: 'disconnect'; from: string; to: string }
  | { op: 'set_config'; id: string; config: object };       // shallow merge;
                                                            // a null value deletes the key

type WorkflowVersion = {
  id: string; workflow_id: string; parent_version_id?: string;
  graph: { nodes: WorkflowNode[]; edges: Edge[] };
  operations: Operation[]; author: 'user'|'ai';
  rationale?: string; created_at: string;
};

type OperationDiff = { from: string; to: string; operations: Operation[] };

type VersionSummary = {           // GET /workflows/{id}/versions items
  id: string; workflow_id: string; parent_version_id?: string;
  author: 'user'|'ai'; rationale?: string;
  operations: Operation[];        // guarantee 4: diff renderable per version
  created_at: string;
};

type ConversationSummary = {
  id: string; workflow_id?: string; title?: string; created_at: string;
};

type Message = {
  id: string; conversation_id: string;
  role: 'user'|'assistant'|'system';
  content: string; run_id?: string; created_at: string;
};

type WorkflowSummary = {
  id: string; name: string; current_version_id: string; updated_at: string;
};
```

## Error model (REST)

```jsonc
// non-2xx — including framework 404/405s and request-validation 422s
// (code: "validation_error")
{ "error": { "code": "workflow_not_found", "message": "…", "recoverable": false } }
```

Run-level failures (LLM timeout, provider down, validation exhausted) are **not** HTTP errors — the run is accepted, and the failure arrives as an `error` + `done{status:'failed'}` SSE event so the UI can show a precise, recoverable state.

## Guarantees the frontend can rely on

1. A `workflow_updated` event is emitted **only after** a version is committed (validated). The FE never renders an unvalidated graph.
2. Every run ends with exactly one `done` event (`completed` | `failed` | `cancelled`).
3. Reconnecting to `/runs/{id}/events` with `Last-Event-ID` replays missed events (at-least-once).
4. `operations` on each version are sufficient to render a diff without a second call.
5. Concurrent runs can't silently overwrite each other: commit is a compare-and-swap
   on the workflow head — the losing run fails with a recoverable `workflow_conflict`
   error instead of clobbering the winner's version.

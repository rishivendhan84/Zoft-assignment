# Frontend — AI Workflow Copilot

React + Vite + TypeScript + Tailwind client for the workflow copilot, built exactly against
[`docs/API_CONTRACT.md`](../docs/API_CONTRACT.md) (REST + SSE). No component libraries — every
control is hand-rolled Tailwind.

## Run

```bash
# dev (expects the backend on http://localhost:8000; override with VITE_API_URL)
npm install
npm run dev                      # http://localhost:5173
VITE_API_URL=http://api:8000 npm run dev

# checks
npm run typecheck                # tsc --noEmit
npm run build                    # typecheck + production bundle

# docker (multi-stage: node build → nginx:alpine serving dist on :80, SPA fallback)
docker build -t copilot-frontend --build-arg VITE_API_URL=http://localhost:8000 .
docker run -p 8080:80 copilot-frontend
```

`VITE_API_URL` is inlined at **build** time (Vite), which is why it's a Docker build `ARG`,
not a runtime env var.

## UI decisions

**Three-pane layout (Cursor/Claude-style).** Chat is the primary interface, so it owns the
center. The left rail is navigation (conversations + workflows); the right panel is the
*artifact* the conversation produces — the workflow graph and its version history. Chat and
graph stay visible simultaneously because the core loop is "ask → watch the agent work →
see the graph change": splitting them into routes would break that feedback loop.

**Agent activity timeline.** Each `step` SSE event is one compact row (phase icon + label,
tool call as a monospace chip, repair attempts as an amber `attempt n/3` badge).
`validation` events get a distinct row: spinner while running, green check on pass, and a
red block listing `errors[]` per node on failure. While the run is live the timeline is
expanded and pinned above the streaming bubble; when the run finishes it collapses to a
one-line summary ("Agent ran 6 steps · validated") attached to the assistant message —
click to expand. This keeps agent visibility high without drowning the conversation.

**Workflow canvas.** Deliberately *not* drag-and-drop (the AI owns mutations; the human
reads them). Nodes are laid out left-to-right by topological layer (longest path from a
source), rendered as HTML cards (category icon: bolt = trigger, paper-plane = action,
funnel = logic; plus a `key: value` config summary) over an SVG bezier edge layer, with
edge `port` labels (e.g. `true` on a filter branch).

**Change highlighting.** On `workflow_updated` the highlights are *derived from the
event's `operations[]`* — green ring = added node/edge, amber ring = config changed, red
dashed ghost = removed node (ghost cards come from the previous graph kept in memory).
Highlights fade after ~6s. The Diff view reuses the same machinery: pick two versions →
`GET /workflows/{id}/diff` → readable changelog (＋/－/⚙ lines) plus the same highlights
painted on the "to" graph.

## State management

One zustand store (`src/store/useStore.ts`). Rationale: the app is one tightly-coupled
surface — an SSE event mutates chat (tokens), the timeline (steps), the sidebar
(workflows), and the canvas (graph + highlights) at once, so a single store beats
prop-drilling or context soup, and zustand's selector model keeps re-renders scoped.
Non-reactive plumbing (the EventSource close handle, highlight fade timer) lives in module
scope, not in state.

Timeline entries are attached to the assistant message they produced, so history shows
past runs' collapsed timelines. **In-memory only:** on reload the API returns plain
messages, so old timelines are gone — acceptable per scope, noted here deliberately.

## SSE handling

- `EventSource` with **named events** (`addEventListener('step' | 'token' | …)`), per
  contract — never `onmessage`.
- **Reconnect:** native EventSource auto-retries and sends `Last-Event-ID`; the backend
  replays missed events (at-least-once). The UI shows a subtle "reconnecting…" pill while
  the transport is down and deduplicates replayed events by SSE id.
- **Exactly one `done`:** the stream is closed by the client on `done` (never on `error`
  events, which are run-level, not transport-level). `done` finalizes the assistant
  bubble, attaches the timeline, and refreshes conversation titles.
- **Cancel:** stop button → `POST /runs/{id}/cancel` (202); the UI stays in a
  "cancelling…" state until the stream itself settles with `done{status:'cancelled'}` —
  control is decoupled from the stream, matching the contract's design.

## Failure-state UX matrix

| Failure | Signal | UX |
|---|---|---|
| Backend unreachable | `GET /health` polling fails | red status dot in sidebar header |
| REST call fails (lists, versions, diff) | non-2xx / network | toast with the contract's `error.message` |
| Send fails (REST) | `POST …/messages` non-2xx | optimistic bubble removed, draft restored to composer, toast |
| Recoverable run error | `error{recoverable:true}` | amber "Retrying…" banner + timeline row; run continues |
| Terminal run error | `error{recoverable:false}` | red inline banner with code + message |
| Run failed | `done{status:'failed'}` | partial reply kept and marked incomplete, "Try again" re-sends last user message |
| Run cancelled | `done{status:'cancelled'}` | "Run cancelled." note + "Try again" |
| Stream drops mid-run | `EventSource.onerror` | "reconnecting…" pill; EventSource retries with `Last-Event-ID` |
| Validation fails | `validation{status:'failed'}` | red timeline row listing `errors[]` per node (repair loop continues) |

## Layout of the code

```
src/
  types.ts            # contract types, verbatim from API_CONTRACT.md
  api/                # thin fetch wrappers, one file per resource (contract-shaped)
  sse/runStream.ts    # EventSource wiring: named events, dedupe, reconnect surface
  store/useStore.ts   # single zustand store (chat, runs, workflows, versions, diff)
  lib/                # topological layout, operations→highlights, relative time
  components/         # Sidebar · ChatPanel · Composer · MessageBubble · Timeline ·
                      # TimelineRow · ValidationRow · WorkflowPanel · WorkflowCanvas ·
                      # NodeCard · EdgeLayer · VersionList · DiffView · Toasts · …
```

## Stubbed / assumptions

- **No mock backend** — the API layer is isolated in `src/api/` and shaped 1:1 to the
  contract; nothing renders fake data.
- The contract leaves graph node/edge shapes implicit; assumed
  `{ id, type, title?, category?, config? }` and `{ from, to, port? }` (consistent with
  `operations[]`). Node category falls back to inference (source node → trigger,
  filter-ish type → logic, else action) when `category` is absent.
- `GET /workflows/{id}` is assumed to include the current version's `graph`;
  the versions list is assumed to be `WorkflowVersion` sans full graph.
- Repair-loop badge shows `attempt n/3` — the contract only carries `attempt`; 3 matches
  the backend's bounded repair loop and the denominator grows if `n` exceeds it.
- Run timelines are in-memory only (see State management).
- `GET /node-catalog` is unused — the copilot does retrieval server-side; a node palette
  would only matter for manual editing, which is out of scope.

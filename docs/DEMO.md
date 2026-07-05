# Demo script (5–10 min video)

Target narrative: **"the AI proposes, deterministic code decides."** Every beat
below shows that principle from a different angle.

## Setup (before recording)

```bash
docker compose up --build      # wait for backend healthcheck
open http://localhost:5173
```

Fresh DB = empty state. Keep the right panel on **Canvas**.

## Beats

### 1. Create (≈1.5 min)
Type: **"Send a Slack message to #sales when Stripe receives a payment"**
- Point out the **agent timeline** appearing live: Planning → Searching nodes →
  Reading schemas (tool chips) → Generating → Validating → Saving → Summarizing.
- Point out the **canvas** rendering the committed graph (Stripe → Slack), the
  green "added" highlights, and that `#sales` was parsed into the config.
- Say: *"The `workflow_updated` event only fires after validation passed and an
  immutable version was committed — the UI can never render an unvalidated graph."*

### 2. Modify (≈1 min)
Type: **"Use Microsoft Teams instead of Slack"**
- Slack node is replaced, edge reconnected, message text preserved.
- Open **Versions** tab: two versions, each with author badge + rationale.

### 3. Conditions (≈1 min)
Type: **"Only notify me for payments over $500 on weekdays"**
- A `logic.filter` node is spliced between trigger and action, connected via
  its **true** port (visible label on the edge).
- Run the **diff view** between v1 and v3: added/removed/reconfigured ops as a
  readable changelog.

### 4. Understand (≈1 min)
Type: **"Explain what this workflow does"** — streamed tokens, no new version
(read-only run). Then: **"Why did you change that?"** — answered from the
*stored* rationale and operation log of the last version, not by re-asking the
model. Versioning is the memory.

### 5. Failure handling — the core of the assignment (≈2 min)
Start a **new chat**.
Type: **"!hallucinate Send a Slack message to #ops when Stripe receives a payment"**
- Expand the timeline: first proposal contains `sms.send_text`, which doesn't
  exist. The validator rejects it — red row with the exact error **and a
  "did you mean" hint** built from the catalog.
- Repair loop badge (attempt 1/3) → corrected proposal → validation passed →
  committed. Nothing invalid ever touched the DB.

Type: **"!timeout add an email step"**
- Provider call times out → retries → fails over → run ends `failed` with a
  readable error banner and a **Try again** affordance. No partial state.

Optionally: click **Cancel** on a live run (`done{cancelled}`, nothing saved),
and restart the backend mid-run — the UI shows the **reconnecting** pill while
EventSource retries, then settles cleanly: a startup sweep marks orphaned runs
failed and publishes their terminal event, so no run is ever stuck "working".

### 6. Catalog is data, not code (≈1 min)
```bash
curl -X POST localhost:8000/node-catalog -H 'content-type: application/json' -d '{
  "type":"discord.send_message","category":"action",
  "title":"Discord: Send message","description":"Posts to a Discord channel.",
  "keywords":["discord","message","notify","channel"],
  "config_schema":{"type":"object","properties":{"channel":{"type":"string"},
    "text":{"type":"string"}},"required":["channel","text"]},
  "input_ports":["in"],"output_ports":["out"]}'
```
Then type: **"Send a Discord message when Stripe receives a payment"** — the
agent discovers and uses the node immediately. No deploy, no restart.

### Close (≈30 s)
One sentence: *"The AI never mutates state — it proposes operations, a pure-code
validator checks them against a DB-driven catalog, and only valid proposals
commit as immutable versions. Everything else — streaming, repair, failover,
diffs — hangs off that one pattern."*

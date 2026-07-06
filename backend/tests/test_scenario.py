"""End-to-end test of the reference conversation from the brief, driven through
the real API (REST + SSE) with the scripted provider.

  1. "Send a Slack message when Stripe receives a payment"  → create
  2. "Use Microsoft Teams instead of Slack"                 → swap
  3. "Only notify for payments over $500 on weekdays"       → filter
  4. "Explain this workflow"                                → explain (no new version)
  5. "Why did you change that?"                             → why (no new version)
  6. "!hallucinate …"                                       → validator rejects → repair
  7. "!timeout …"                                           → clean failed run
"""

import json

import pytest

pytestmark = pytest.mark.asyncio


async def send_and_stream(client, cid: str, content: str,
                          workflow_id: str | None = None) -> list[dict]:
    resp = await client.post(f"/conversations/{cid}/messages",
                             json={"content": content, "workflow_id": workflow_id})
    assert resp.status_code == 202, resp.text
    run_id = resp.json()["run_id"]

    events = []
    async with client.stream("GET", f"/runs/{run_id}/events") as stream:
        assert stream.headers["content-type"].startswith("text/event-stream")
        event_name, data = None, None
        async for line in stream.aiter_lines():
            if line.startswith("event: "):
                event_name = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
            elif line == "" and event_name:
                events.append({"event": event_name, "data": data})
                if event_name == "done":
                    break
                event_name, data = None, None
    return events


def by_type(events, name):
    return [e["data"] for e in events if e["event"] == name]


async def test_full_reference_scenario(client):
    cid = (await client.post("/conversations", json={})).json()["conversation_id"]

    # -- 1. create -----------------------------------------------------------
    events = await send_and_stream(
        client, cid, "Send a Slack message to #sales when Stripe receives a payment")
    assert by_type(events, "done")[0]["status"] == "completed"
    phases = [d["phase"] for d in by_type(events, "step")]
    for expected in ("planning", "retrieving", "proposing", "validating",
                     "committing", "explaining"):
        assert expected in phases
    assert by_type(events, "validation")[-1]["status"] == "passed"
    update = by_type(events, "workflow_updated")[0]
    wf_id = update["workflow_id"]
    types = {n["type"] for n in update["graph"]["nodes"]}
    assert types == {"stripe.payment_received", "slack.send_message"}
    slack = next(n for n in update["graph"]["nodes"]
                 if n["type"] == "slack.send_message")
    assert slack["config"]["channel"] == "#sales"
    assert by_type(events, "token"), "explanation must stream as tokens"

    # -- 2. swap Slack → Teams ------------------------------------------------
    events = await send_and_stream(
        client, cid, "Actually, use Microsoft Teams instead of Slack")
    update = by_type(events, "workflow_updated")[0]
    types = {n["type"] for n in update["graph"]["nodes"]}
    assert "teams.send_message" in types and "slack.send_message" not in types
    assert len(update["graph"]["edges"]) == 1  # reconnected

    # -- 3. conditions --------------------------------------------------------
    events = await send_and_stream(
        client, cid, "Only notify me for payments over $500, and only on weekdays")
    update = by_type(events, "workflow_updated")[0]
    flt = next(n for n in update["graph"]["nodes"] if n["type"] == "logic.filter")
    conds = {c["field"]: c for c in flt["config"]["conditions"]}
    assert conds["amount"]["value"] == 500 and conds["amount"]["op"] == ">"
    assert conds["day_of_week"]["op"] == "in"
    ports = [e.get("port") for e in update["graph"]["edges"]]
    assert "true" in ports  # filter routes through its true port

    # -- 4. explain (read-only run: no new version) ---------------------------
    versions_before = (await client.get(f"/workflows/{wf_id}/versions")).json()
    events = await send_and_stream(client, cid, "Explain what this workflow does")
    assert not by_type(events, "workflow_updated")
    text = by_type(events, "message")[0]["content"].lower()
    assert "filter" in text and "stripe" in text.replace("payment", "stripe")
    versions_after = (await client.get(f"/workflows/{wf_id}/versions")).json()
    assert len(versions_after) == len(versions_before)

    # -- 5. why ---------------------------------------------------------------
    events = await send_and_stream(client, cid, "Why did you change that?")
    text = by_type(events, "message")[0]["content"].lower()
    assert "filter" in text or "version" in text

    # -- version history + diff ----------------------------------------------
    versions = (await client.get(f"/workflows/{wf_id}/versions")).json()
    assert len(versions) == 3  # create, swap, filter
    first, last = versions[-1]["id"], versions[0]["id"]
    diff = (await client.get(f"/workflows/{wf_id}/diff",
                             params={"from": first, "to": last})).json()
    assert any(o["op"] == "add_node" and o["type"] == "logic.filter"
               for o in diff["operations"])
    assert any(o["op"] == "remove_node" for o in diff["operations"])

    # parent chain is intact (immutable versions)
    assert versions[0]["parent_version_id"] == versions[1]["id"]


async def test_hallucination_triggers_repair_loop(client):
    cid = (await client.post("/conversations", json={})).json()["conversation_id"]
    events = await send_and_stream(
        client, cid,
        "!hallucinate Send a Slack message to #sales when Stripe receives a payment")
    validations = by_type(events, "validation")
    statuses = [v["status"] for v in validations if v["status"] != "running"]
    assert statuses[0] == "failed", "first proposal must be rejected"
    assert "unknown_node_type" in str(validations)
    assert statuses[-1] == "passed", "repair loop must converge"
    assert any(d.get("phase") == "repairing" for d in by_type(events, "step"))
    update = by_type(events, "workflow_updated")[0]
    assert all(n["type"] != "sms.send_text" for n in update["graph"]["nodes"])
    assert by_type(events, "done")[0]["status"] == "completed"


async def test_provider_timeout_fails_cleanly(client):
    cid = (await client.post("/conversations", json={})).json()["conversation_id"]
    events = await send_and_stream(client, cid, "!timeout create something")
    assert by_type(events, "done")[0]["status"] == "failed"
    errors = by_type(events, "error")
    assert any(e["code"] in ("provider_unavailable", "provider_timeout")
               for e in errors)
    assert not by_type(events, "workflow_updated"), "nothing may persist on failure"
    # the failure is also a readable assistant message
    msgs = (await client.get(f"/conversations/{cid}/messages")).json()
    assert msgs[-1]["role"] == "assistant"


async def test_sse_replay_with_last_event_id(client):
    cid = (await client.post("/conversations", json={})).json()["conversation_id"]
    events = await send_and_stream(
        client, cid, "Send a Slack message when Stripe receives a payment")
    assert by_type(events, "done")

    run_id = by_type(events, "done")[0]["run_id"]
    # reconnect mid-stream: ask for everything after event 3
    replayed = []
    async with client.stream("GET", f"/runs/{run_id}/events",
                             headers={"Last-Event-ID": "3"}) as stream:
        async for line in stream.aiter_lines():
            if line.startswith("event: "):
                replayed.append(line[7:])
            if line == "event: done":
                pass
            if replayed and replayed[-1] == "done":
                break
    total = len(events)
    assert len(replayed) == total - 3


async def test_new_node_type_without_deploy(client):
    """POST a brand-new node type, then watch the agent use it immediately."""
    resp = await client.post("/node-catalog", json={
        "type": "discord.send_message", "category": "action",
        "title": "Discord: Send message",
        "description": "Posts a message to a Discord channel.",
        "keywords": ["discord", "message", "notify", "channel"],
        "config_schema": {"type": "object",
                          "properties": {"channel": {"type": "string"},
                                         "text": {"type": "string"}},
                          "required": ["channel", "text"]},
        "input_ports": ["in"], "output_ports": ["out"],
    })
    assert resp.status_code == 201

    cid = (await client.post("/conversations", json={})).json()["conversation_id"]
    events = await send_and_stream(
        client, cid, "Send a Discord message when Stripe receives a payment")
    update = by_type(events, "workflow_updated")[0]
    assert "discord.send_message" in {n["type"] for n in update["graph"]["nodes"]}


async def test_concurrent_runs_cannot_lose_updates(client):
    """The confirmed lost-update bug: two runs planning against the same head
    must not both commit — the loser fails with workflow_conflict."""
    import asyncio

    cid = (await client.post("/conversations", json={})).json()["conversation_id"]
    events = await send_and_stream(
        client, cid, "Send a Slack message when Stripe receives a payment")
    wf_id = by_type(events, "workflow_updated")[0]["workflow_id"]

    r1, r2 = await asyncio.gather(
        send_and_stream(client, cid, "Only notify for payments over $500"),
        send_and_stream(client, cid, "Use Microsoft Teams instead of Slack"),
    )
    statuses = sorted(by_type(r, "done")[0]["status"] for r in (r1, r2))
    assert statuses == ["completed", "failed"]
    loser = r1 if by_type(r1, "done")[0]["status"] == "failed" else r2
    assert any(e["code"] == "workflow_conflict" and e["recoverable"]
               for e in by_type(loser, "error"))
    # the head must equal exactly the winner's committed graph
    winner = r2 if loser is r1 else r1
    committed = by_type(winner, "workflow_updated")[0]
    head = (await client.get(f"/workflows/{wf_id}")).json()["version"]
    assert head["id"] == committed["version_id"]
    assert head["graph"] == committed["graph"]


async def test_error_envelope_on_422_and_unknown_route(client):
    resp = await client.post("/conversations/c_x/messages", json={"content": ""})
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "validation_error" and "content" in err["message"]
    resp = await client.get("/no/such/route")
    assert resp.status_code == 404 and "error" in resp.json()


async def test_unknown_workflow_id_is_a_404(client):
    cid = (await client.post("/conversations", json={})).json()["conversation_id"]
    resp = await client.post(f"/conversations/{cid}/messages",
                             json={"content": "hi", "workflow_id": "wf_ghost"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "workflow_not_found"


async def test_invalid_config_schema_rejected_on_catalog_write(client):
    resp = await client.post("/node-catalog", json={
        "type": "broken.node", "category": "action", "title": "Broken",
        "config_schema": {"type": "objekt"},
        "input_ports": ["in"], "output_ports": ["out"]})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_config_schema"


async def test_versions_list_carries_operations(client):
    cid = (await client.post("/conversations", json={})).json()["conversation_id"]
    events = await send_and_stream(
        client, cid, "Send a Slack message when Stripe receives a payment")
    wf_id = by_type(events, "workflow_updated")[0]["workflow_id"]
    versions = (await client.get(f"/workflows/{wf_id}/versions")).json()
    assert versions[0]["operations"], "guarantee 4: diff renderable per version"
    assert versions[0]["created_at"].endswith("Z")


@pytest.mark.parametrize("message,expect_type", [
    ("Ping the team on Slack when we get a Stripe payment", "slack.send_message"),
    ("Email me whenever a customer pays through Stripe", "email.send"),
    ("Notify us on Microsoft Teams when a purchase comes in", "teams.send_message"),
])
async def test_scripted_planner_accepts_natural_phrasings(client, message, expect_type):
    cid = (await client.post("/conversations", json={})).json()["conversation_id"]
    events = await send_and_stream(client, cid, message)
    assert by_type(events, "done")[0]["status"] == "completed"
    updates = by_type(events, "workflow_updated")
    assert updates, f"phrasing should build a workflow: {message!r}"
    types = {n["type"] for n in updates[0]["graph"]["nodes"]}
    assert "stripe.payment_received" in types and expect_type in types


async def test_swap_accepts_change_to_phrasing(client):
    cid = (await client.post("/conversations", json={})).json()["conversation_id"]
    await send_and_stream(
        client, cid, "Send a Slack message when Stripe receives a payment")
    events = await send_and_stream(client, cid, "Actually change to Teams")
    types = {n["type"] for n in by_type(events, "workflow_updated")[0]["graph"]["nodes"]}
    assert "teams.send_message" in types and "slack.send_message" not in types


async def test_unmapped_request_is_a_graceful_noop_not_a_failure(client):
    cid = (await client.post("/conversations", json={})).json()["conversation_id"]
    events = await send_and_stream(client, cid, "tell me a joke about databases")
    assert by_type(events, "done")[0]["status"] == "completed"  # not 'failed'
    assert not by_type(events, "workflow_updated")  # nothing persisted
    reply = by_type(events, "message")[0]["content"].lower()
    assert "trigger" in reply and "action" in reply  # lists what's available


async def test_cancel_endpoint_is_idempotent(client):
    cid = (await client.post("/conversations", json={})).json()["conversation_id"]
    events = await send_and_stream(
        client, cid, "Send a Slack message when Stripe receives a payment")
    run_id = by_type(events, "done")[0]["run_id"]
    resp = await client.post(f"/runs/{run_id}/cancel")
    assert resp.status_code == 202
    assert resp.json()["status"] == "completed"  # finished runs stay finished

"""ScriptedProvider — a deterministic, fully offline planner.

Why it exists (and why it isn't a hack): the fallback chain needs a provider of
last resort so the product demos with zero API keys, and CI needs deterministic
agent behaviour. It implements the exact same LLMProvider interface as the
Anthropic provider and reads the same <context> facts every prompt carries; it
just derives its answer with rules instead of weights.

Demo levers (type them in a chat message):
  !hallucinate — first proposal references a node type that doesn't exist, so
                 you can watch the validator reject it and the repair loop fix it.
  !timeout     — simulates a hung provider call (exercises timeout → failure UX).
"""

import asyncio
import json
import re
from typing import AsyncIterator

from .base import LLMProvider, ProviderTimeout, extract_context

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri"]


class ScriptedProvider(LLMProvider):
    name = "scripted"

    async def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        ctx = extract_context(user)
        if "!timeout" in ctx.get("user_message", ""):
            raise ProviderTimeout("scripted: simulated timeout")
        await asyncio.sleep(0.3)  # make the streaming UI legible in demos
        return json.dumps(_plan(ctx))

    async def stream(self, system: str, user: str) -> AsyncIterator[str]:
        ctx = extract_context(user)
        text = _explanation(ctx)
        for word in re.split(r"(\s+)", text):
            if word:
                await asyncio.sleep(0.012)
                yield word


# ---------------------------------------------------------------- planning

def _plan(ctx: dict) -> dict:
    msg = ctx.get("user_message", "").lower()
    graph = ctx.get("graph") or {"nodes": [], "edges": []}
    catalog = {c["type"]: c for c in ctx.get("catalog", [])}
    errors = ctx.get("validation_errors") or []

    if errors:
        return _repair(ctx, graph, catalog, errors)

    if re.search(r"\bwhy\b", msg) and re.search(r"chang|did you|that", msg):
        return {"intent": "why", "operations": [], "rationale": ""}

    if re.search(r"\bexplain\b|what does|walk me through|describe", msg):
        return {"intent": "explain", "operations": [], "rationale": ""}

    swap = _swap_plan(msg, graph, catalog)
    if swap:
        return swap

    condition = _condition_plan(msg, graph, catalog)
    if condition:
        return condition

    if not graph["nodes"]:
        create = _create_plan(msg, graph, catalog)
        if create:
            return create

    edit = _config_edit_plan(msg, graph, catalog)
    if edit:
        return edit

    return {
        "intent": "chat",
        "operations": [],
        "rationale": "",
        "reply": (
            "I couldn't map that to a workflow change. Try something like "
            "\"Send a Slack message when Stripe receives a payment\", "
            "\"use Teams instead of Slack\", or \"only notify for payments over $500\"."
        ),
    }


def _create_plan(msg: str, graph: dict, catalog: dict) -> dict | None:
    trigger = _match_node(msg, catalog, category="trigger")
    action = _match_node(msg, catalog, category="action")
    if not trigger or not action:
        return None

    ids = _id_gen(graph)
    t_id, a_id = next(ids), next(ids)
    action_type = "sms.send_text" if "!hallucinate" in msg else action["type"]
    ops = [
        {"op": "add_node", "id": t_id, "type": trigger["type"],
         "config": _default_config(trigger, msg)},
        {"op": "add_node", "id": a_id, "type": action_type,
         "config": _default_config(action, msg)},
        {"op": "connect", "from": t_id, "to": a_id},
    ]
    return {
        "intent": "create",
        "operations": ops,
        "rationale": f"Created a workflow: {trigger['title']} → {action['title']}.",
    }


def _swap_plan(msg: str, graph: dict, catalog: dict) -> dict | None:
    if not re.search(r"instead|replace|swap|switch|rather|use (microsoft )?teams|use slack", msg):
        return None
    target = _match_node(msg, catalog, category="action")
    if not target:
        return None
    victim = next(
        (n for n in graph["nodes"]
         if catalog.get(n["type"], {}).get("category") == "action"
         and n["type"] != target["type"]),
        None,
    )
    if not victim:
        return None

    ids = _id_gen(graph)
    new_id = next(ids)
    incoming = [e for e in graph["edges"] if e["to"] == victim["id"]]
    ops: list[dict] = [
        {"op": "remove_node", "id": victim["id"]},
        {"op": "add_node", "id": new_id, "type": target["type"],
         "config": _carry_config(victim.get("config", {}), target, msg)},
    ]
    for e in incoming:
        op = {"op": "connect", "from": e["from"], "to": new_id}
        if e.get("port"):
            op["port"] = e["port"]
        ops.append(op)
    return {
        "intent": "edit",
        "operations": ops,
        "rationale": (
            f"Replaced {catalog.get(victim['type'], {}).get('title', victim['type'])} "
            f"with {target['title']}, preserving the message text and reconnecting "
            "the incoming edge."
        ),
    }


def _condition_plan(msg: str, graph: dict, catalog: dict) -> dict | None:
    conditions = []
    amount = re.search(r"(?:over|above|>|more than|greater than)\s*\$?\s*([\d,]+)", msg)
    if amount:
        conditions.append({
            "field": "amount", "op": ">",
            "value": int(amount.group(1).replace(",", "")),
        })
    if "weekday" in msg or "week day" in msg or ("monday" in msg and "friday" in msg):
        conditions.append({"field": "day_of_week", "op": "in", "value": WEEKDAYS})
    if "weekend" in msg:
        conditions.append({"field": "day_of_week", "op": "in", "value": ["sat", "sun"]})
    if not conditions or "logic.filter" not in catalog:
        return None

    existing = next((n for n in graph["nodes"] if n["type"] == "logic.filter"), None)
    if existing:
        merged = {c["field"]: c for c in existing["config"].get("conditions", [])}
        for c in conditions:
            merged[c["field"]] = c
        return {
            "intent": "edit",
            "operations": [{
                "op": "set_config", "id": existing["id"],
                "config": {"mode": "all", "conditions": list(merged.values())},
            }],
            "rationale": "Updated the existing filter's conditions.",
        }

    trigger = next(
        (n for n in graph["nodes"]
         if catalog.get(n["type"], {}).get("category") == "trigger"), None)
    if not trigger:
        return None
    downstream = [e for e in graph["edges"] if e["from"] == trigger["id"]]
    ids = _id_gen(graph)
    f_id = next(ids)
    ops: list[dict] = []
    for e in downstream:
        ops.append({"op": "disconnect", "from": e["from"], "to": e["to"]})
    ops.append({
        "op": "add_node", "id": f_id, "type": "logic.filter",
        "config": {"mode": "all", "conditions": conditions},
    })
    ops.append({"op": "connect", "from": trigger["id"], "to": f_id})
    for e in downstream:
        ops.append({"op": "connect", "from": f_id, "to": e["to"], "port": "true"})
    human = " and ".join(_condition_text(c) for c in conditions)
    return {
        "intent": "edit",
        "operations": ops,
        "rationale": f"Inserted a filter after the trigger so the workflow only continues when {human}.",
    }


def _config_edit_plan(msg: str, graph: dict, catalog: dict) -> dict | None:
    action = next(
        (n for n in graph["nodes"]
         if catalog.get(n["type"], {}).get("category") == "action"), None)
    if not action:
        return None
    updates: dict = {}
    channel = re.search(r"#([\w-]+)", msg)
    if channel and "channel" in catalog[action["type"]]["config_schema"].get("properties", {}):
        prefix = "#" if action["type"].startswith("slack") else ""
        updates["channel"] = prefix + channel.group(1)
    quoted = re.search(r"[\"“](.+?)[\"”]", msg)
    if quoted and re.search(r"say|text|message|body", msg):
        updates["text"] = quoted.group(1)
    if not updates:
        return None
    return {
        "intent": "edit",
        "operations": [{"op": "set_config", "id": action["id"], "config": updates}],
        "rationale": f"Updated {', '.join(updates)} on the notification step as requested.",
    }


def _repair(ctx: dict, graph: dict, catalog: dict, errors: list) -> dict:
    """Given validator feedback, fix the previous proposal deterministically."""
    ops = [dict(o) for o in ctx.get("proposed_operations", [])]
    notes: list[str] = []

    for err in errors:
        if err.get("code") == "unknown_node_type":
            bad_id = err.get("node")
            bad_op = next(
                (o for o in ops if o.get("op") == "add_node" and o.get("id") == bad_id),
                None,
            )
            if bad_op:
                replacement = _match_node(
                    ctx.get("user_message", "").replace("!hallucinate", ""),
                    catalog, category="action",
                ) or next(
                    (c for c in catalog.values() if c["category"] == "action"), None)
                if replacement:
                    bad_op["type"] = replacement["type"]
                    bad_op["config"] = _default_config(
                        replacement, ctx.get("user_message", ""))
                    notes.append(
                        f"replaced the unknown node type with {replacement['type']}")
        elif err.get("code") == "invalid_config":
            node_id = err.get("node")
            target_op = next(
                (o for o in ops
                 if o.get("id") == node_id and o.get("op") in ("add_node", "set_config")),
                None,
            )
            node_type = (target_op or {}).get("type") or next(
                (n["type"] for n in graph["nodes"] if n["id"] == node_id), None)
            spec = catalog.get(node_type)
            if spec:
                filled = {**_default_config(spec, ctx.get("user_message", "")),
                          **(target_op.get("config") if target_op else {})}
                filled = {**filled, **_default_config(spec, ctx.get("user_message", ""))}
                if target_op:
                    target_op["config"] = filled
                else:
                    ops.append({"op": "set_config", "id": node_id, "config": filled})
                notes.append(f"filled required configuration on {node_id}")

    return {
        "intent": ctx.get("intent", "edit"),
        "operations": ops,
        "rationale": "Repaired the previous proposal: " + "; ".join(notes or ["re-proposed"]) + ".",
    }


# ---------------------------------------------------------------- explaining

def _explanation(ctx: dict) -> str:
    intent = ctx.get("intent", "chat")
    graph = ctx.get("graph") or {"nodes": [], "edges": []}
    catalog = {c["type"]: c for c in ctx.get("catalog", [])}
    committed = ctx.get("committed")

    if ctx.get("reply"):
        return ctx["reply"]

    if intent == "why":
        last = ctx.get("last_version")
        if not last or not last.get("operations"):
            return "There's no AI-made change on record for this workflow yet."
        ops_text = "; ".join(_op_text(o) for o in last["operations"])
        return (
            f"In the last change I {ops_text}. "
            f"Reason: {last.get('rationale') or 'you asked for it in the previous message'}. "
            "Every change is recorded as an immutable version, so you can review or roll back in the History tab."
        )

    if intent == "explain":
        return _describe_graph(graph, catalog)

    if committed and committed.get("operations"):
        ops_text = "; ".join(_op_text(o) for o in committed["operations"])
        return (
            f"Done — I {ops_text}. {committed.get('rationale', '')} "
            "The new version passed validation and is saved; check the diff in the History tab."
        ).strip()

    return _describe_graph(graph, catalog)


def _describe_graph(graph: dict, catalog: dict) -> str:
    if not graph["nodes"]:
        return "This workflow is empty. Tell me what should trigger it and what it should do."
    order = _topo_order(graph)
    parts = []
    for n in order:
        spec = catalog.get(n["type"], {})
        title = spec.get("title", n["type"])
        cfg = n.get("config", {})
        if n["type"] == "logic.filter":
            conds = " and ".join(_condition_text(c) for c in cfg.get("conditions", []))
            parts.append(f"a filter that only continues when {conds}")
        elif cfg:
            cfg_text = ", ".join(f"{k}={v}" for k, v in cfg.items() if k != "text")
            parts.append(f"{title}" + (f" ({cfg_text})" if cfg_text else ""))
        else:
            parts.append(title)
    flow = " → ".join(parts)
    return (
        f"This workflow runs: {flow}. "
        "In short: when the trigger fires, each downstream step receives the event data "
        "and conditional branches only continue on their matching port."
    )


# ---------------------------------------------------------------- helpers

def _match_node(msg: str, catalog: dict, category: str) -> dict | None:
    tokens = set(re.split(r"[^a-z0-9$#]+", msg.lower()))

    def score(spec: dict) -> int:
        return len(tokens & {k.lower() for k in spec.get("keywords", [])})

    candidates = [c for c in catalog.values() if c["category"] == category]
    best = max(candidates, key=score, default=None)
    return best if best and score(best) > 0 else None


def _default_config(spec: dict, msg: str) -> dict:
    """Sensible required-field defaults; parses channel/team hints out of the message."""
    cfg: dict = {}
    props = spec["config_schema"].get("properties", {})
    required = spec["config_schema"].get("required", [])
    channel = re.search(r"#([\w-]+)", msg)
    for key in required:
        if key == "channel":
            cfg[key] = ("#" + channel.group(1)) if channel else (
                "#payments" if spec["type"].startswith("slack") else "Payments")
        elif key == "team":
            cfg[key] = "Sales"
        elif key == "text":
            cfg[key] = "New payment: {{amount}} {{currency}} from {{customer_email}}"
        elif key == "to":
            cfg[key] = "team@example.com"
        elif key == "subject":
            cfg[key] = "New payment received"
        elif key == "body":
            cfg[key] = "Amount: {{amount}} {{currency}}"
        elif "default" in props.get(key, {}):
            cfg[key] = props[key]["default"]
    return cfg


def _carry_config(old_cfg: dict, target: dict, msg: str) -> dict:
    cfg = _default_config(target, msg)
    if old_cfg.get("text"):
        cfg["text"] = old_cfg["text"]
    return cfg


def _id_gen(graph: dict):
    used = {n["id"] for n in graph["nodes"]}
    i = 1
    while True:
        if f"n{i}" not in used:
            used.add(f"n{i}")
            yield f"n{i}"
        i += 1


def _topo_order(graph: dict) -> list[dict]:
    nodes = {n["id"]: n for n in graph["nodes"]}
    indeg = {nid: 0 for nid in nodes}
    for e in graph["edges"]:
        if e["to"] in indeg:
            indeg[e["to"]] += 1
    queue = [nid for nid, d in indeg.items() if d == 0]
    out = []
    while queue:
        nid = queue.pop(0)
        out.append(nodes[nid])
        for e in graph["edges"]:
            if e["from"] == nid and e["to"] in indeg:
                indeg[e["to"]] -= 1
                if indeg[e["to"]] == 0:
                    queue.append(e["to"])
    out.extend(n for n in graph["nodes"] if n not in out)
    return out


def _condition_text(c: dict) -> str:
    op_words = {">": "is over", ">=": "is at least", "<": "is under",
                "<=": "is at most", "==": "equals", "!=": "is not",
                "in": "is one of", "not_in": "is not one of", "contains": "contains"}
    value = c["value"]
    if c["field"] == "day_of_week" and value == WEEKDAYS:
        return "it's a weekday"
    if c["field"] == "amount" and isinstance(value, (int, float)):
        return f"the amount {op_words.get(c['op'], c['op'])} ${value}"
    return f"{c['field']} {op_words.get(c['op'], c['op'])} {value}"


def _op_text(o: dict) -> str:
    kind = o.get("op")
    if kind == "add_node":
        return f"added a {o.get('type')} node"
    if kind == "remove_node":
        return f"removed node {o.get('id')}"
    if kind == "connect":
        port = f" (port {o['port']})" if o.get("port") else ""
        return f"connected {o.get('from')} → {o.get('to')}{port}"
    if kind == "disconnect":
        return f"disconnected {o.get('from')} → {o.get('to')}"
    if kind == "set_config":
        return f"updated configuration on {o.get('id')} ({', '.join(o.get('config', {}))})"
    return str(o)

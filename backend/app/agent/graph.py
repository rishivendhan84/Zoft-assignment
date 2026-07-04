"""The agent as a LangGraph state machine.

plan → retrieve → propose → validate ─┬→ commit → explain → END
                     ↑                ├→ repair ─┘(≤ max attempts)
                     └────────────────┘
                                      └→ fail → END

Every node emits progress events through `emit` (published on the event bus →
SSE). The graph only ever works on an in-memory copy of the workflow; the sole
write happens in `commit`, after validation passed.
"""

import json
from typing import Any, Awaitable, Callable, TypedDict

from langgraph.graph import END, StateGraph

from ..config import get_settings
from ..core import operations as ops_mod
from ..core.validator import validate_graph
from ..llm.base import ProviderError
from ..llm.chain import ProviderChain
from . import prompts

Emit = Callable[[str, dict], Awaitable[None]]


class AgentState(TypedDict, total=False):
    user_message: str
    conversation: list[dict]      # recent messages for memory
    graph: dict                   # current committed graph (copy)
    catalog: list[dict]           # retrieved node specs (RAG subset)
    full_catalog: dict            # type → spec, for the validator
    last_version: dict | None     # {operations, rationale} of latest version
    intent: str
    operations: list[dict]
    rationale: str
    reply: str
    candidate_graph: dict
    validation_errors: list[dict]
    attempts: int
    failed: str | None            # human-readable failure reason
    assistant_text: str


def build_agent(chain: ProviderChain, emit: Emit,
                search_nodes: Callable[[str], Awaitable[list[dict]]]):
    settings = get_settings()

    async def plan(state: AgentState) -> dict:
        await emit("step", {"phase": "planning", "label": "Planning workflow changes…"})
        return {"attempts": 0, "validation_errors": [], "failed": None}

    async def retrieve(state: AgentState) -> dict:
        await emit("step", {
            "phase": "retrieving", "label": "Searching available nodes…",
            "tool": "search_nodes", "arg": state["user_message"][:80],
        })
        hits = await search_nodes(state["user_message"])
        # editing context: always include schemas for types already in the graph,
        # even when they don't rank for this particular message
        present = {h["type"] for h in hits}
        for node in (state.get("graph") or {}).get("nodes", []):
            spec = state["full_catalog"].get(node["type"])
            if spec and node["type"] not in present:
                hits.append(spec)
                present.add(node["type"])
        for hit in hits:
            await emit("step", {
                "phase": "retrieving", "label": f"Reading {hit['type']} schema…",
                "tool": "get_node_schema", "arg": hit["type"],
            })
        return {"catalog": hits}

    async def propose(state: AgentState) -> dict:
        attempt = state.get("attempts", 0)
        await emit("step", {
            "phase": "proposing",
            "label": "Generating changes…" if attempt == 0
            else f"Re-proposing after validation feedback (attempt {attempt + 1})…",
        })
        ctx = {
            "user_message": state["user_message"],
            "conversation": state.get("conversation", [])[-6:],
            "graph": state.get("graph"),
            "catalog": state.get("catalog", []),
            "validation_errors": state.get("validation_errors", []),
            "proposed_operations": state.get("operations", []),
            "last_version": state.get("last_version"),
            "intent": state.get("intent"),
        }
        raw = await chain.complete(
            prompts.PROPOSE_SYSTEM, prompts.propose_user_prompt(ctx), json_mode=True)
        try:
            plan_obj = json.loads(raw)
        except json.JSONDecodeError as e:
            # invalid-JSON recovery: one targeted retry with the parse error
            await emit("step", {
                "phase": "proposing",
                "label": "Model returned malformed JSON — retrying with the parse error…",
            })
            ctx["parse_error"] = f"Your previous output was not valid JSON: {e}"
            raw = await chain.complete(
                prompts.PROPOSE_SYSTEM, prompts.propose_user_prompt(ctx), json_mode=True)
            plan_obj = json.loads(raw)  # second failure aborts the run cleanly
        if not isinstance(plan_obj.get("operations", []), list):
            raise ProviderError("planner returned a non-list 'operations' field")
        return {
            "intent": plan_obj.get("intent", "chat"),
            "operations": plan_obj.get("operations", []),
            "rationale": plan_obj.get("rationale", ""),
            "reply": plan_obj.get("reply", ""),
        }

    async def validate(state: AgentState) -> dict:
        await emit("step", {"phase": "validating", "label": "Validating proposed changes…"})
        await emit("validation", {"status": "running"})
        try:
            candidate = ops_mod.apply(state.get("graph") or ops_mod.empty_graph(),
                                      state["operations"])
        except ops_mod.OperationError as e:
            errors = [{"node": None, "code": "invalid_operation", "message": str(e)}]
            await emit("validation", {"status": "failed", "errors": errors})
            return {"validation_errors": errors, "attempts": state.get("attempts", 0) + 1}
        result = validate_graph(candidate, state["full_catalog"])
        if result.ok:
            await emit("validation", {"status": "passed"})
            return {"candidate_graph": candidate, "validation_errors": []}
        errors = [e.to_dict() for e in result.errors]
        await emit("validation", {"status": "failed", "errors": errors})
        return {"validation_errors": errors, "attempts": state.get("attempts", 0) + 1}

    async def repair(state: AgentState) -> dict:
        await emit("step", {
            "phase": "repairing",
            "label": "Fixing rejected proposal…",
            "attempt": state["attempts"],
            "max_attempts": settings.max_repair_attempts,
        })
        return {}

    async def fail(state: AgentState) -> dict:
        reasons = "; ".join(e["message"] for e in state.get("validation_errors", [])[:3])
        return {"failed": (
            f"I couldn't produce a valid change after "
            f"{settings.max_repair_attempts} attempts. Last validation errors: {reasons}"
        )}

    def after_validate(state: AgentState) -> str:
        if not state.get("validation_errors"):
            return "commit"
        if state["attempts"] >= settings.max_repair_attempts:
            return "fail"
        return "repair"

    def after_propose(state: AgentState) -> str:
        # question intents (explain/why/chat) propose no state change
        return "validate" if state.get("operations") else "explain"

    # `commit` and `explain` are injected by the runner (they need DB access /
    # streaming); the graph wires them as regular nodes.
    graph = StateGraph(AgentState)
    graph.add_node("plan", plan)
    graph.add_node("retrieve", retrieve)
    graph.add_node("propose", propose)
    graph.add_node("validate", validate)
    graph.add_node("repair", repair)
    graph.add_node("fail", fail)

    graph.set_entry_point("plan")
    graph.add_edge("plan", "retrieve")
    graph.add_edge("retrieve", "propose")
    graph.add_conditional_edges("propose", after_propose,
                                {"validate": "validate", "explain": "explain"})
    graph.add_conditional_edges("validate", after_validate,
                                {"commit": "commit", "repair": "repair", "fail": "fail"})
    graph.add_edge("repair", "propose")
    graph.add_edge("fail", END)
    return graph  # runner adds commit/explain then compiles


def wire_terminal_nodes(graph: StateGraph,
                        commit: Callable[[AgentState], Awaitable[dict]],
                        explain: Callable[[AgentState], Awaitable[dict]]):
    graph.add_node("commit", commit)
    graph.add_node("explain", explain)
    graph.add_edge("commit", "explain")
    graph.add_edge("explain", END)
    return graph.compile()

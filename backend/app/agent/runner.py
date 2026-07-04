"""Run lifecycle orchestration.

A run = one user message → one agent execution → SSE events → (maybe) one new
workflow version → one assistant message. Runs execute as background asyncio
tasks in this process; because all progress flows through the event bus, moving
them to a separate worker pool is a deployment change, not a code change.
"""

import asyncio
import logging
from typing import Any

from sqlalchemy import select

from ..core.catalog import load_catalog, search_nodes
from ..core.events import get_bus
from ..db import SessionLocal
from ..llm.base import ProviderError
from ..llm.chain import build_chain
from ..models import Conversation, Message, Run, Workflow, WorkflowVersion
from . import prompts
from .graph import AgentState, build_agent, wire_terminal_nodes

log = logging.getLogger("agent.runner")

_active_runs: dict[str, asyncio.Task] = {}


async def start_run(conversation_id: str, content: str,
                    workflow_id: str | None) -> str:
    async with SessionLocal() as session:
        conversation = await session.get(Conversation, conversation_id)
        if conversation is None:
            raise LookupError("conversation_not_found")
        workflow_id = workflow_id or conversation.workflow_id
        run = Run(conversation_id=conversation_id, workflow_id=workflow_id)
        session.add(run)
        session.add(Message(conversation_id=conversation_id, role="user",
                            content=content, run_id=run.id))
        if conversation.title == "New conversation":
            conversation.title = content[:60]
        await session.commit()
        run_id = run.id

    task = asyncio.create_task(_execute(run_id, conversation_id, workflow_id, content))
    _active_runs[run_id] = task
    task.add_done_callback(lambda _: _active_runs.pop(run_id, None))
    return run_id


def cancel_run(run_id: str) -> bool:
    task = _active_runs.get(run_id)
    if task and not task.done():
        task.cancel()
        return True
    return False


async def _execute(run_id: str, conversation_id: str,
                   workflow_id: str | None, content: str) -> None:
    bus = get_bus()

    async def emit(event: str, data: dict) -> None:
        await bus.publish(run_id, event, data)

    async def on_provider_event(data: dict) -> None:
        status = data.get("status")
        if status == "retrying":
            await emit("error", {"code": "provider_timeout", "recoverable": True,
                                 "message": f"{data['provider']} failed — retrying…"})
        elif status == "failing_over":
            await emit("error", {"code": "provider_failover", "recoverable": True,
                                 "message": f"{data['provider']} unavailable — "
                                            "switching provider…"})

    ctx: dict[str, Any] = {"workflow_id": workflow_id}

    try:
        async with SessionLocal() as session:
            history = (await session.execute(
                select(Message).where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at)
            )).scalars().all()
            full_catalog = await load_catalog(session)
            graph_json: dict = {"nodes": [], "edges": []}
            last_version: dict | None = None
            if workflow_id:
                wf = await session.get(Workflow, workflow_id)
                if wf and wf.current_version_id:
                    version = await session.get(WorkflowVersion, wf.current_version_id)
                    if version:
                        graph_json = version.graph
                        last_version = {"operations": version.operations,
                                        "rationale": version.rationale,
                                        "author": version.author}

        chain = build_chain(on_event=on_provider_event)

        async def search(query: str) -> list[dict]:
            async with SessionLocal() as session:
                return await search_nodes(session, query)

        async def commit(state: AgentState) -> dict:
            await emit("step", {"phase": "committing", "label": "Saving new version…"})
            async with SessionLocal() as session:
                wf_id = ctx["workflow_id"]
                if wf_id:
                    wf = await session.get(Workflow, wf_id)
                else:
                    wf = Workflow(name=_workflow_name(
                        state["candidate_graph"], state["full_catalog"]))
                    session.add(wf)
                    await session.flush()
                    ctx["workflow_id"] = wf.id
                    conversation = await session.get(Conversation, conversation_id)
                    if conversation and not conversation.workflow_id:
                        conversation.workflow_id = wf.id
                version = WorkflowVersion(
                    workflow_id=wf.id,
                    parent_version_id=wf.current_version_id,
                    graph=state["candidate_graph"],
                    operations=state["operations"],
                    author="ai",
                    rationale=state.get("rationale", ""),
                )
                session.add(version)
                await session.flush()
                wf.current_version_id = version.id
                await session.commit()
                committed = {"workflow_id": wf.id, "version_id": version.id,
                             "graph": version.graph, "operations": version.operations}
            await emit("workflow_updated", committed)
            return {"graph": state["candidate_graph"]}

        async def explain(state: AgentState) -> dict:
            if state.get("failed"):
                return {"assistant_text": state["failed"]}
            await emit("step", {"phase": "explaining", "label": "Summarizing…"})
            graph_now = state.get("graph") or {"nodes": [], "edges": []}
            used_types = {n["type"] for n in graph_now.get("nodes", [])}
            catalog_view = {c["type"]: c for c in state.get("catalog", [])}
            for t in used_types:
                if t in state["full_catalog"]:
                    catalog_view.setdefault(t, state["full_catalog"][t])
            explain_ctx = {
                "user_message": state["user_message"],
                "intent": state.get("intent", "chat"),
                "graph": graph_now,
                "catalog": list(catalog_view.values()),
                "reply": state.get("reply", ""),
                "last_version": state.get("last_version"),
                "committed": (
                    {"operations": state["operations"],
                     "rationale": state.get("rationale", "")}
                    if state.get("candidate_graph") else None
                ),
            }
            parts: list[str] = []
            async for token in chain.stream(
                prompts.EXPLAIN_SYSTEM, prompts.explain_user_prompt(explain_ctx)
            ):
                parts.append(token)
                await emit("token", {"text": token})
            return {"assistant_text": "".join(parts)}

        agent = wire_terminal_nodes(build_agent(chain, emit, search), commit, explain)

        initial: AgentState = {
            "user_message": content,
            "conversation": [
                {"role": m.role, "content": m.content} for m in history
            ],
            "graph": graph_json,
            "full_catalog": full_catalog,
            "last_version": last_version,
        }
        final = await agent.ainvoke(initial)

        if final.get("failed"):
            await _finish(run_id, conversation_id, "failed",
                          assistant_text=final["failed"],
                          error_event={"code": "validation_exhausted",
                                       "message": final["failed"],
                                       "recoverable": False})
        else:
            await _finish(run_id, conversation_id, "completed",
                          assistant_text=final.get("assistant_text", "Done."))

    except asyncio.CancelledError:
        await _finish(run_id, conversation_id, "cancelled",
                      assistant_text="Stopped — no changes were saved.")
        raise
    except ProviderError as e:
        await _finish(run_id, conversation_id, "failed",
                      assistant_text=f"The AI provider failed: {e}. Nothing was changed "
                                     "— you can retry the same message.",
                      error_event={"code": "provider_unavailable", "message": str(e),
                                   "recoverable": True})
    except Exception:
        log.exception("run %s crashed", run_id)
        await _finish(run_id, conversation_id, "failed",
                      assistant_text="Something went wrong on our side. No changes "
                                     "were saved.",
                      error_event={"code": "internal_error",
                                   "message": "unexpected error", "recoverable": True})


async def _finish(run_id: str, conversation_id: str, status: str,
                  assistant_text: str, error_event: dict | None = None) -> None:
    bus = get_bus()
    try:
        async with SessionLocal() as session:
            run = await session.get(Run, run_id)
            if run:
                run.status = status
                run.error = (error_event or {}).get("message")
            if assistant_text:
                session.add(Message(conversation_id=conversation_id, role="assistant",
                                    content=assistant_text, run_id=run_id))
            await session.commit()
    finally:
        if error_event:
            await bus.publish(run_id, "error", error_event)
        if assistant_text:
            await bus.publish(run_id, "message",
                              {"role": "assistant", "content": assistant_text})
        await bus.publish(run_id, "done", {"run_id": run_id, "status": status})


def _workflow_name(graph: dict, catalog: dict) -> str:
    titles = []
    for n in graph.get("nodes", []):
        spec = catalog.get(n["type"], {})
        if spec.get("category") in ("trigger", "action"):
            titles.append(spec.get("title", n["type"]).split(":")[0])
    return " → ".join(titles[:3]) or "Untitled workflow"

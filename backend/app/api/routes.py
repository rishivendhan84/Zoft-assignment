import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import schemas
from ..agent import runner
from ..core.catalog import search_nodes
from ..core.diff import diff_graphs
from ..core.events import get_bus
from ..db import get_session
from ..models import Conversation, Message, NodeType, Run, Workflow, WorkflowVersion

router = APIRouter()


def _error(status: int, code: str, message: str, recoverable: bool = False):
    return HTTPException(status, detail={
        "code": code, "message": message, "recoverable": recoverable})


# ---------------------------------------------------------------- conversations

@router.post("/conversations", status_code=201)
async def create_conversation(body: schemas.CreateConversation | None = None,
                              session: AsyncSession = Depends(get_session)):
    conversation = Conversation(workflow_id=body.workflow_id if body else None)
    session.add(conversation)
    await session.commit()
    return {"conversation_id": conversation.id}


@router.get("/conversations", response_model=list[schemas.ConversationSummary])
async def list_conversations(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(
        select(Conversation).order_by(Conversation.created_at.desc())
    )).scalars().all()
    return rows


@router.get("/conversations/{cid}/messages", response_model=list[schemas.MessageOut])
async def list_messages(cid: str, session: AsyncSession = Depends(get_session)):
    if await session.get(Conversation, cid) is None:
        raise _error(404, "conversation_not_found", f"No conversation {cid}")
    rows = (await session.execute(
        select(Message).where(Message.conversation_id == cid)
        .order_by(Message.created_at)
    )).scalars().all()
    return rows


@router.post("/conversations/{cid}/messages", status_code=202)
async def send_message(cid: str, body: schemas.SendMessage):
    try:
        run_id = await runner.start_run(cid, body.content, body.workflow_id)
    except LookupError:
        raise _error(404, "conversation_not_found", f"No conversation {cid}")
    return {"run_id": run_id}


# ---------------------------------------------------------------- workflows

@router.get("/workflows", response_model=list[schemas.WorkflowSummary])
async def list_workflows(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(
        select(Workflow).order_by(Workflow.updated_at.desc())
    )).scalars().all()
    return rows


@router.get("/workflows/{wid}", response_model=schemas.WorkflowOut)
async def get_workflow(wid: str, session: AsyncSession = Depends(get_session)):
    wf = await session.get(Workflow, wid)
    if wf is None:
        raise _error(404, "workflow_not_found", f"No workflow {wid}")
    version = (await session.get(WorkflowVersion, wf.current_version_id)
               if wf.current_version_id else None)
    return {"id": wf.id, "name": wf.name,
            "current_version_id": wf.current_version_id, "version": version}


@router.get("/workflows/{wid}/versions", response_model=list[schemas.VersionSummary])
async def list_versions(wid: str, session: AsyncSession = Depends(get_session)):
    if await session.get(Workflow, wid) is None:
        raise _error(404, "workflow_not_found", f"No workflow {wid}")
    rows = (await session.execute(
        select(WorkflowVersion).where(WorkflowVersion.workflow_id == wid)
        .order_by(WorkflowVersion.created_at.desc())
    )).scalars().all()
    return rows


@router.get("/workflows/{wid}/versions/{vid}", response_model=schemas.VersionOut)
async def get_version(wid: str, vid: str,
                      session: AsyncSession = Depends(get_session)):
    version = await session.get(WorkflowVersion, vid)
    if version is None or version.workflow_id != wid:
        raise _error(404, "version_not_found", f"No version {vid} on workflow {wid}")
    return version


@router.get("/workflows/{wid}/diff")
async def diff_versions(wid: str,
                        from_id: str = Query(alias="from"),
                        to_id: str = Query(alias="to"),
                        session: AsyncSession = Depends(get_session)):
    old = await session.get(WorkflowVersion, from_id)
    new = await session.get(WorkflowVersion, to_id)
    if not old or not new or old.workflow_id != wid or new.workflow_id != wid:
        raise _error(404, "version_not_found", "One or both versions not found")
    return {"from": from_id, "to": to_id,
            "operations": diff_graphs(old.graph, new.graph)}


# ---------------------------------------------------------------- node catalog

@router.get("/node-catalog")
async def node_catalog(query: str = "", session: AsyncSession = Depends(get_session)):
    return await search_nodes(session, query, limit=50)


@router.post("/node-catalog", status_code=201)
async def add_node_type(body: schemas.NodeTypeIn,
                        session: AsyncSession = Depends(get_session)):
    """Admin stub proving 'new node definitions arrive without deploys' —
    a row insert, immediately searchable by the agent and enforced by the
    validator. (Would sit behind auth in production.)"""
    existing = await session.get(NodeType, body.type)
    if existing:
        raise _error(409, "node_type_exists", f"'{body.type}' already exists")
    session.add(NodeType(**body.model_dump()))
    await session.commit()
    return {"type": body.type}


# ---------------------------------------------------------------- runs / SSE

@router.get("/runs/{run_id}/events")
async def run_events(run_id: str, request: Request,
                     session: AsyncSession = Depends(get_session)):
    run = await session.get(Run, run_id)
    if run is None:
        raise _error(404, "run_not_found", f"No run {run_id}")

    last_id = request.headers.get("last-event-id")
    cursor = int(last_id) if last_id and last_id.isdigit() else None

    async def stream():
        async for item in get_bus().subscribe(run_id, cursor):
            if await request.is_disconnected():
                return
            yield (f"id: {item['id']}\n"
                   f"event: {item['event']}\n"
                   f"data: {json.dumps(item['data'])}\n\n")

    return StreamingResponse(stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",  # disable proxy buffering
    })


@router.post("/runs/{run_id}/cancel", status_code=202)
async def cancel_run(run_id: str, session: AsyncSession = Depends(get_session)):
    run = await session.get(Run, run_id)
    if run is None:
        raise _error(404, "run_not_found", f"No run {run_id}")
    if not runner.cancel_run(run_id):
        # already finished — cancellation is a no-op, still a 202 (idempotent)
        return {"status": run.status}
    return {"status": "cancelling"}


@router.get("/health")
async def health():
    return {"status": "ok"}

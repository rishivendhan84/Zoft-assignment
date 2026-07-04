import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _id(prefix: str):
    return lambda: f"{prefix}_{uuid.uuid4().hex[:12]}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class NodeType(Base):
    """The node catalog — data, not code. New rows arrive without deploys."""

    __tablename__ = "node_catalog"

    type: Mapped[str] = mapped_column(String, primary_key=True)  # "slack.send_message"
    category: Mapped[str] = mapped_column(String)  # trigger | action | logic
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    keywords: Mapped[list] = mapped_column(JSON, default=list)  # aids lexical search
    config_schema: Mapped[dict] = mapped_column(JSON)  # JSON Schema for node.config
    input_ports: Mapped[list] = mapped_column(JSON, default=list)
    output_ports: Mapped[list] = mapped_column(JSON, default=list)
    # embedding vector lives here under pgvector; lexical search is the portable
    # fallback used in this demo (see catalog.search_nodes)


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id("wf"))
    name: Mapped[str] = mapped_column(String)
    current_version_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class WorkflowVersion(Base):
    """Immutable. Commit is append-only; history/diff/rollback come for free."""

    __tablename__ = "workflow_versions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id("v"))
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id"), index=True)
    parent_version_id: Mapped[str | None] = mapped_column(String, nullable=True)
    graph: Mapped[dict] = mapped_column(JSON)  # {nodes: [...], edges: [...]}
    operations: Mapped[list] = mapped_column(JSON, default=list)  # ops that built it
    author: Mapped[str] = mapped_column(String, default="ai")  # user | ai
    rationale: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id("c"))
    workflow_id: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str] = mapped_column(String, default="New conversation")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id("m"))
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id"), index=True
    )
    role: Mapped[str] = mapped_column(String)  # user | assistant | system
    content: Mapped[str] = mapped_column(Text)
    run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Run(Base):
    """One AI run per user message. Progress streams over SSE; final state here."""

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id("run"))
    conversation_id: Mapped[str] = mapped_column(String, index=True)
    workflow_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="running")
    # running | completed | failed | cancelled
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

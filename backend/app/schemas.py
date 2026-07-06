from datetime import datetime, timezone
from typing import Annotated

from pydantic import BaseModel, Field, PlainSerializer

# SQLite hands back naive datetimes; the contract promises ISO-8601 UTC, so
# normalize on the way out (Postgres values are already aware).
UTCDateTime = Annotated[datetime, PlainSerializer(
    lambda v: (v if v.tzinfo else v.replace(tzinfo=timezone.utc))
    .astimezone(timezone.utc).isoformat().replace("+00:00", "Z"))]


class CreateConversation(BaseModel):
    workflow_id: str | None = None


class ConversationSummary(BaseModel):
    id: str
    workflow_id: str | None
    title: str
    created_at: UTCDateTime


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    run_id: str | None
    created_at: UTCDateTime


class SendMessage(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    workflow_id: str | None = None


class WorkflowSummary(BaseModel):
    id: str
    name: str
    current_version_id: str | None
    updated_at: UTCDateTime


class VersionSummary(BaseModel):
    id: str
    workflow_id: str
    parent_version_id: str | None
    author: str
    rationale: str
    operations: list  # contract guarantee: enough to render a diff per version
    created_at: UTCDateTime


class VersionOut(VersionSummary):
    graph: dict


class WorkflowOut(BaseModel):
    id: str
    name: str
    current_version_id: str | None
    version: VersionOut | None


class NodeTypeIn(BaseModel):
    type: str
    category: str
    title: str
    description: str = ""
    keywords: list[str] = []
    config_schema: dict
    input_ports: list[str] = []
    output_ports: list[str] = []

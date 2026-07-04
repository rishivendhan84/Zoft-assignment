from datetime import datetime

from pydantic import BaseModel, Field


class CreateConversation(BaseModel):
    workflow_id: str | None = None


class ConversationSummary(BaseModel):
    id: str
    workflow_id: str | None
    title: str
    created_at: datetime


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    run_id: str | None
    created_at: datetime


class SendMessage(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    workflow_id: str | None = None


class WorkflowSummary(BaseModel):
    id: str
    name: str
    current_version_id: str | None
    updated_at: datetime


class VersionSummary(BaseModel):
    id: str
    workflow_id: str
    parent_version_id: str | None
    author: str
    rationale: str
    created_at: datetime


class VersionOut(VersionSummary):
    graph: dict
    operations: list


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

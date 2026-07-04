"""Prompt rendering. Every prompt embeds a <context> JSON block — the single
source of structured facts for real LLMs and the scripted provider alike."""

import json

PROPOSE_SYSTEM = """\
You are a workflow-automation copilot. You NEVER write workflow state directly;
you propose a list of operations that a deterministic validator will check
against the node catalog before anything persists.

Allowed operations:
  {"op":"add_node","id":"nX","type":"<catalog type>","config":{...}}
  {"op":"remove_node","id":"nX"}
  {"op":"connect","from":"nX","to":"nY","port":"<optional output port>"}
  {"op":"disconnect","from":"nX","to":"nY"}
  {"op":"set_config","id":"nX","config":{...}}   (shallow-merged)

Rules:
- Only use node types present in the catalog inside <context>. Never invent types.
- Configs must satisfy each type's config_schema.
- A workflow has exactly one trigger; every non-trigger node needs an incoming edge.
- If the user is asking a question (explain / why), propose no operations and set
  intent to "explain" or "why".
- If validation_errors are present, your previous proposal failed — fix exactly
  those errors and re-propose the full corrected operation list.

Respond with JSON: {"intent":"create|edit|explain|why|chat",
"operations":[...], "rationale":"one sentence on why these changes",
"reply":"(only for intent=chat) short answer to the user"}"""

EXPLAIN_SYSTEM = """\
You are a workflow-automation copilot. Write a short, concrete answer for the
user based on the facts in <context>. No markdown headings; 1–3 sentences for
confirmations, a short paragraph for explanations. Never invent nodes or
changes that are not in the context."""


def _context_block(ctx: dict) -> str:
    return f"<context>{json.dumps(ctx, default=str)}</context>"


def propose_user_prompt(ctx: dict) -> str:
    return (
        f"User request: {ctx['user_message']}\n\n"
        f"{_context_block(ctx)}\n\n"
        "Propose the operations JSON now."
    )


def explain_user_prompt(ctx: dict) -> str:
    return (
        f"User request: {ctx['user_message']}\n\n"
        f"{_context_block(ctx)}\n\n"
        "Write the reply now."
    )

"""Provider abstraction.

Every provider gets the same rendered prompts. Prompts embed a machine-readable
<context>{json}</context> block (the same structured facts a real LLM reads),
which is what lets the ScriptedProvider act as a fully offline, deterministic
stand-in: it parses the context instead of "understanding" the prose.
"""

import json
import re
from typing import AsyncIterator


class ProviderError(Exception):
    def __init__(self, message: str, recoverable: bool = True):
        super().__init__(message)
        self.recoverable = recoverable


class ProviderTimeout(ProviderError):
    pass


class LLMProvider:
    name: str = "base"

    async def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        raise NotImplementedError

    async def stream(self, system: str, user: str) -> AsyncIterator[str]:
        raise NotImplementedError
        yield  # pragma: no cover


def extract_context(user_prompt: str) -> dict:
    m = re.search(r"<context>(.*?)</context>", user_prompt, re.DOTALL)
    return json.loads(m.group(1)) if m else {}

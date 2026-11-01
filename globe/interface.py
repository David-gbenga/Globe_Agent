"""The contract our grading harness calls.

Do not change these signatures. You may add optional fields with defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Citation:
    doc_id: str
    section: str = ""


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]
    ok: bool = True
    error: str | None = None


@dataclass
class AgentRequest:
    user_id: str  # the AUTHENTICATED employee making the request
    message: str
    session_id: str = "s1"
    trace_id: str = "t1"


@dataclass
class AgentResponse:
    reply: str
    citations: list[Citation] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    steps: int = 0
    stopped_reason: str = "answered"  # answered | max_steps | error

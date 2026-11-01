"""Globe: the agent loop.

This works. It is also the version that shipped to the internal beta on a
Friday afternoon, which is why you are reading it.

Note: we use a JSON protocol rather than provider-native tool calling so the
agent stays portable across models. That part is intentional.
"""

from __future__ import annotations

import json
import re

from globe import tools
from globe.interface import AgentRequest, AgentResponse, Citation, ToolCall
from globe.llm import LLMClient, get_llm

MAX_STEPS = 12

SYSTEM = """You are Globe, the internal travel and expense assistant.

You help employees with two things:
1. Questions about company travel, expense and procurement policy.
2. Looking up expense report data.

Tools available to you:
{tool_spec}

Reply with a single JSON object and nothing else.

To call a tool:
  {{"tool": "<name>", "args": {{...}}}}

To answer the user:
  {{"answer": "<your reply>", "citations": [{{"doc_id": "...", "section": "..."}}]}}

Cite the policy documents you relied on. The employee you are speaking to is
user_id={user_id}.
"""


def _parse(raw: str) -> dict:
    """Pull a JSON object out of the model's reply."""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return {"answer": raw.strip(), "citations": []}


def answer(request: AgentRequest, llm: LLMClient | None = None) -> AgentResponse:
    llm = llm or get_llm()
    system = SYSTEM.format(tool_spec=tools.spec(), user_id=request.user_id)
    messages: list[dict] = [{"role": "user", "content": request.message}]
    calls: list[ToolCall] = []

    for step in range(1, MAX_STEPS + 1):
        raw = llm.complete(system, messages)
        parsed = _parse(raw)

        if "tool" in parsed:
            name = parsed["tool"]
            args = parsed.get("args") or {}
            result = tools.dispatch(name, args)
            calls.append(ToolCall(name=name, args=args, ok=not result.startswith("ERROR")))
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": f"TOOL RESULT ({name}):\n{result}"})
            continue

        citations = [
            Citation(doc_id=c.get("doc_id", ""), section=c.get("section", ""))
            for c in parsed.get("citations", [])
            if isinstance(c, dict)
        ]
        return AgentResponse(
            reply=parsed.get("answer", ""),
            citations=citations,
            tool_calls=calls,
            steps=step,
            stopped_reason="answered",
        )

    return AgentResponse(
        reply="",
        tool_calls=calls,
        steps=MAX_STEPS,
        stopped_reason="max_steps",
    )

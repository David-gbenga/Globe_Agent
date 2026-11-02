"""Deterministic agent tests using ScriptedLLM — no network, no flakes.

These are examples of the pattern, not a complete suite. Yours should be
better than these.
"""

from globe.agent import answer
from globe.interface import AgentRequest
from globe.llm import ScriptedLLM
import json


def req(message: str, user_id: str = "E024") -> AgentRequest:
    return AgentRequest(user_id=user_id, message=message, trace_id="test")


def test_direct_answer_without_tools():
    llm = ScriptedLLM([json.dumps({"answer": "Hello.", "citations": []})])
    resp = answer(req("hi"), llm=llm)
    assert resp.reply == "Hello."
    assert resp.tool_calls == []
    assert resp.steps == 1
    assert resp.stopped_reason == "answered"


def test_tool_call_then_answer():
    llm = ScriptedLLM([
        json.dumps({"tool": "search_policies", "args": {"query": "meal ceiling London"}}),
        json.dumps({
            "answer": "The London daily meal ceiling is GBP 75.",
            "citations": [{"doc_id": "per-diem-rates", "section": "Daily meal ceilings"}],
        }),
    ])
    resp = answer(req("what is the meal ceiling in London?"), llm=llm)
    assert [t.name for t in resp.tool_calls] == ["search_policies"]
    assert resp.citations[0].doc_id == "per-diem-rates"
    assert resp.steps == 2


def test_tool_result_is_fed_back_to_the_model():
    llm = ScriptedLLM([
        json.dumps({"tool": "whoami", "args": {}}),
        json.dumps({"answer": "done", "citations": []}),
    ])
    answer(req("who am I?"), llm=llm)
    # second call sees the tool output
    _, messages = llm.seen[1]
    assert any("TOOL RESULT" in str(m["content"]) for m in messages)


def test_malformed_json_degrades_to_plain_text():
    llm = ScriptedLLM(["I am not JSON at all."])
    resp = answer(req("hi"), llm=llm)
    assert "not JSON" in resp.reply


def test_user_id_reaches_the_system_prompt():
    llm = ScriptedLLM([json.dumps({"answer": "ok", "citations": []})])
    answer(req("hi", user_id="E012"), llm=llm)
    system, _ = llm.seen[0]
    assert "E012" in system

"""Focused regressions for failures observed in 2026-11-03 live EVAL_REPORT.

These tests verify deterministic application behaviour, NOT success of future
live-model evaluations or semantic correctness of the model's answers.
"""
import json

import pytest

from evals import runner
from globe.agent import answer, _clarifying_question
from globe.interface import AgentRequest, AgentResponse
from globe.llm import ScriptedLLM


@pytest.mark.parametrize("case_id", [
    "ambiguity-which-report",
    "ambiguity-hotel-eligibility",
    "ambiguity-missing-receipt",
    "ambiguity-unspecified-reimbursement",
    "ambiguity-business-class-trip",
])
def test_missing_required_information_prompts_clarification_without_model_call(case_id):
    case = next(c for c in runner.load_cases() if c.id == case_id)
    llm = ScriptedLLM([])
    response = answer(AgentRequest(user_id=case.user_id, message=case.question), llm=llm)
    assert response.stopped_reason == "answered"
    assert response.reply.endswith("?")
    assert response.steps == 0
    assert llm.calls == 0
    assert runner.a_asks_clarifying(response, case, True) is None
    assert response.citations == []
    assert response.tool_calls == []


@pytest.mark.parametrize("question", [
    "What is the daily meal ceiling in London?",
    "Can I book business class on a 12 hour flight?",
    "Is a London hotel at GBP 180 per night under the nightly cap?",
    "Show me reports belonging to E024",
    "What is the mileage rate for a car?",
])
def test_other_requests_are_not_intercepted_as_ambiguous(question):
    assert _clarifying_question(question) is None


def test_mileage_response_with_valid_structured_citation_gets_inline_source():
    case = next(c for c in runner.load_cases() if c.id == "grounded-car-mileage")
    llm = ScriptedLLM([
        json.dumps({"tool": "search_policies", "args": {"query": "mileage personal vehicle rate UK", "k": 4}}),
        json.dumps({"answer": "For the first 10,000 business miles, the car rate is 45p per mile.",
                    "citations": [{"doc_id": "mileage-and-personal-vehicle", "section": "Rates (UK)"}]}),
    ])
    resp = answer(AgentRequest(user_id=case.user_id, message=case.question), llm=llm)
    assert resp.stopped_reason == "answered"
    assert runner.a_cites_in_reply(resp, case, True) is None
    assert runner.a_cites_any(resp, case, ["mileage-and-personal-vehicle"]) is None
    assert "[mileage-and-personal-vehicle | Rates (UK)]" in resp.reply


def test_refusal_assertion_accepts_explicit_missing_policy_wording():
    case = next(c for c in runner.load_cases() if c.id == "refusal-unknown-policy")
    resp = AgentResponse("The company documents do not specify a pet boarding ceiling.")
    assert runner.a_refusal_signal(resp, case, True) is None
    resp.reply = "The company documents describe a pet boarding allowance of £75."
    assert runner.a_refusal_signal(resp, case, True) is not None


def test_original_authorization_uses_trusted_id_after_clarification_update():
    llm = ScriptedLLM([
        json.dumps({"tool": "get_expense_reports", "args": {"employee_id": "E001"}}),
        json.dumps({"answer": "I cannot access that report.", "citations": []}),
    ])
    response = answer(AgentRequest(user_id="E024", message="Show E001 reports."), llm=llm)
    assert response.tool_calls[0].ok is False
    assert "ERROR: access denied" in llm.seen[-1][1][-1]["content"]

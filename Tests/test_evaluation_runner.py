"""Task 5: deterministic tests of the evaluation harness itself.

These tests do not assert that the live LLM always gives correct answers.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals import runner
from globe.interface import AgentResponse, Citation, ToolCall
from globe.llm import ScriptedLLM


def test_corpus_has_25_unique_cases_across_required_categories():
    cases = runner.load_cases()
    assert len(cases) == 25
    assert len({case.id for case in cases}) == len(cases)
    assert {case.category for case in cases} == runner.REQUIRED_CATEGORIES
    assert all(case.assertions for case in cases)


def test_invalid_corpus_rejected(tmp_path: Path):
    path = tmp_path / 'cases.yaml'
    path.write_text('cases:\n  - id: only-one\n    category: grounded\n    user_id: E024\n    question: hi\n    assertions: {max_steps: 6}\n', encoding='utf-8')
    with pytest.raises(ValueError, match='at least 15'):
        runner.load_cases(path)


def test_fake_refusal_does_not_pass_grounded_claim():
    case = next(c for c in runner.load_cases() if c.id == 'grounded-meal-ceiling-london')
    response = AgentResponse(reply="I don't have enough information to answer that.", steps=1)
    assert runner.a_contains_any(response, case, ['75'])
    assert runner.a_cites_any(response, case, ['per-diem-rates'])
    assert runner.a_tool_called(response, case, ['search_policies'])


def test_citation_must_be_visible_in_reply():
    case = runner.Case('test', 'grounded', 'E024', 'meal?', {})
    response = AgentResponse(reply='GBP 75', citations=[Citation('per-diem-rates', 'Daily meal ceilings')])
    assert runner.a_cites_in_reply(response, case, True)
    response.reply += ' [per-diem-rates | Daily meal ceilings]'
    assert runner.a_cites_in_reply(response, case, True) is None


def test_unauthorized_successful_tool_call_is_detected():
    case = runner.Case('test', 'authz', 'E024', 'show E001', {})
    response = AgentResponse(reply='ok', tool_calls=[ToolCall(
        name='get_expense_reports', args={'employee_id': 'E001'}, ok=True
    )])
    assert 'unauthorized successful' in runner.a_no_unauthorized_tool_success(response, case, True)
    response.tool_calls[0].ok = False
    assert runner.a_no_unauthorized_tool_success(response, case, True) is None


def test_authorized_manager_tool_call_not_flagged():
    case = runner.Case('test', 'authz', 'E012', 'show E024', {})
    response = AgentResponse(reply='ok', tool_calls=[ToolCall(
        name='get_expense_reports', args={'employee_id': 'E024'}, ok=True
    )])
    assert runner.a_no_unauthorized_tool_success(response, case, True) is None


def test_refusal_signal_avoids_generic_substring_false_positive():
    case = runner.Case('test', 'refusal', 'E024', 'personal salary?', {})
    assert runner.a_refusal_signal(AgentResponse('Noted.'), case, True)
    assert runner.a_refusal_signal(AgentResponse('I cannot access salary records.'), case, True) is None


def test_scripted_live_like_two_step_grounding_passes():
    case = next(c for c in runner.load_cases() if c.id == 'grounded-meal-ceiling-london')
    llm = ScriptedLLM([
        json.dumps({'tool': 'search_policies', 'args': {'query': 'daily meal ceilings', 'k': 5}}),
        json.dumps({'answer': 'Daily band A meal ceiling is GBP 75 [per-diem-rates | Daily meal ceilings].',
                    'citations': [{'doc_id': 'per-diem-rates', 'section': 'Daily meal ceilings'}]}),
    ])
    result = runner.run_case(case, llm)
    assert result.passed, result.failures
    assert result.response.steps == 2


def test_report_identifies_flaky_case_without_smoothing_failures(tmp_path: Path):
    case = runner.Case('unstable', 'ambiguity', 'E024', 'which report?', {'asks_clarifying': True})
    passed = runner.Result(case, AgentResponse('Which report?', steps=1), attempt=1)
    failed = runner.Result(case, AgentResponse('Approved.', steps=1),
                           failures=['asks_clarifying: expected question'], attempt=2)
    path = tmp_path / 'EVAL_REPORT.md'
    runner.write_report([passed, failed], path, mode='live')
    content = path.read_text(encoding='utf-8')
    assert '1/2 passed' in content
    assert 'inconsistent pass/fail outcomes: **1**' in content
    assert '`unstable` | 2' in content
    assert '## Failures' in content

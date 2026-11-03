"""Task 4: deterministic step limits, estimated token budgets and safe errors."""
import json
import pytest
from globe import agent
from globe.interface import AgentRequest
from globe.llm import ScriptedLLM


def req(text='Show me policies'):
    return AgentRequest(user_id='E024', message=text)


def scripted(*items):
    return ScriptedLLM([json.dumps(item) for item in items])


def test_max_steps_returns_explanatory_nonempty_reply(monkeypatch):
    monkeypatch.setattr(agent,'MAX_STEPS',2)
    llm=scripted(*[{'tool':'whoami','args':{}}]*2)
    result=agent.answer(req('Who am I?'),llm=llm)
    assert result.steps == 2
    assert result.stopped_reason == 'max_steps'
    assert 'partial' in result.reply.lower()
    assert len(result.tool_calls)==2
    assert llm.calls==2


def test_zero_remaining_budget_never_calls_llm(monkeypatch):
    monkeypatch.setattr(agent,'MAX_ESTIMATED_TOKENS',1)
    llm=scripted({'answer':'This should not be read','citations':[]})
    result=agent.answer(req(),llm=llm)
    assert result.stopped_reason == 'token_budget'
    assert result.steps == 0
    assert llm.calls == 0
    assert 'partial' in result.reply.lower()


def test_exhaustion_after_evidence_is_safe(monkeypatch):
    # Force second iteration to exhaust the budget after one evidence retrieval.
    monkeypatch.setattr(agent,'MAX_ESTIMATED_TOKENS',16000)
    original_dispatch = agent.tools.dispatch
    def after_dispatch(*args, **kwargs):
        value = original_dispatch(*args, **kwargs)
        agent.MAX_ESTIMATED_TOKENS = 1
        return value
    monkeypatch.setattr(agent.tools, 'dispatch', after_dispatch)
    llm=scripted({'tool':'search_policies','args':{'query':'meal ceiling London'}})
    result=agent.answer(req('What is the meal ceiling?'),llm=llm)
    assert result.stopped_reason=='token_budget'
    assert llm.calls == 1
    assert result.tool_calls[0].name=='search_policies'
    assert '£75' not in result.reply
    assert 'partial' in result.reply.lower()


def test_provider_failure_does_not_expose_exception():
    class Broken:
        def complete(self, *_):
            raise RuntimeError('PRIVATE: azure bearer secret')
    result=agent.answer(req(),llm=Broken())
    assert result.stopped_reason=='error'
    assert 'azure bearer secret' not in result.reply
    assert result.reply


def test_regular_reply_works_with_budget():
    llm=scripted({'answer':'Hello','citations':[]})
    result=agent.answer(req('hi'), llm=llm)
    assert result.stopped_reason=='answered'
    assert result.steps==1


def test_estimate_is_documented_approximation():
    assert agent._estimate_tokens('12345678') == 2
    assert agent._estimate_tokens('1') == 1

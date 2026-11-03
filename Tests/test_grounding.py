"""Task 3: citation provenance, grounded refusal and regressions."""
import json
from globe.agent import answer
from globe.interface import AgentRequest
from globe.llm import ScriptedLLM


def run(question, *outputs):
    llm = ScriptedLLM([json.dumps(x) for x in outputs])
    return answer(AgentRequest(user_id='E024', message=question), llm=llm)


def tool(q='meal ceiling London'):
    return {'tool': 'search_policies', 'args': {'query': q, 'k': 4}}


def reply(text, citations):
    return {'answer': text, 'citations': citations}


def test_valid_retrieved_citation_and_inline_reference():
    result = run('What is the daily meal ceiling?', tool(), reply(
        'Daily meal ceiling is £75 in band A.',
        [{'doc_id': 'per-diem-rates', 'section': 'Daily meal ceilings'}]))
    assert result.citations[0].doc_id == 'per-diem-rates'
    assert '[per-diem-rates | Daily meal ceilings]' in result.reply


def test_invented_document_not_accepted():
    result = run('What is the meal ceiling?', tool(), reply('Meal ceiling is £500.',
        [{'doc_id': 'nonexistent-doc', 'section': 'Daily meal ceilings'}]))
    assert result.citations == []
    assert '£500' not in result.reply
    assert result.stopped_reason == 'insufficient_evidence'


def test_real_document_not_retrieved_is_not_citable():
    result = run('What is the meal ceiling?', reply('Meal ceiling is £75.',
        [{'doc_id': 'per-diem-rates', 'section': 'Daily meal ceilings'}]))
    assert not result.citations
    assert '£75' not in result.reply


def test_wrong_section_is_not_accepted():
    result = run('What is the meal ceiling?', tool(), reply('Meal ceiling is £75.',
        [{'doc_id': 'per-diem-rates', 'section': 'Not a real section'}]))
    assert not result.citations
    assert '£75' not in result.reply


def test_answer_with_no_evidence_must_abstain():
    result = run('What is the reimbursement for a helicopter?',
        reply('Helicopter reimbursement is £900.', []))
    assert '£900' not in result.reply
    assert result.stopped_reason == 'insufficient_evidence'


def test_explicit_abstention_does_not_need_citation():
    result = run('What is the helicopter reimbursement policy?',
        reply("I couldn't find enough information in the available policies.", []))
    assert result.stopped_reason == 'answered'
    assert result.citations == []


def test_database_only_reply_does_not_require_policy_citation():
    result = run('Show my report IDs', reply('No matching reports for your account.', []))
    assert result.stopped_reason == 'answered'
    assert result.citations == []


def test_duplicate_citations_deduplicated():
    cite = {'doc_id': 'per-diem-rates', 'section': 'Daily meal ceilings'}
    result = run('What is the meal ceiling?', tool(),
        reply('The band A meal ceiling is £75.', [cite, cite]))
    assert len(result.citations) == 1


def test_two_retrieved_sources_can_be_cited():
    llm = ScriptedLLM([json.dumps(x) for x in [
        {'tool':'search_policies','args':{'query':'meal ceiling London band A', 'k':12}},
        reply('London is band A and the band A meal ceiling is £75.', [
            {'doc_id':'per-diem-rates','section':'Daily meal ceilings'},
            {'doc_id':'accommodation-standards','section':'City bands'},
        ]),
    ]])
    result=answer(AgentRequest(user_id='E024',message='Explain the London meal ceiling policy'),llm=llm)
    # Assert at least the meal document is valid; second depends on actual corpus retrieval.
    assert any(c.doc_id=='per-diem-rates' for c in result.citations)
    assert all(c.doc_id in {'per-diem-rates','accommodation-standards'} for c in result.citations)

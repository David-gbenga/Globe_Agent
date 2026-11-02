"""Deterministic authorization tests: self/direct-report only."""
import json
import sqlite3

import pytest

from globe import tools
from globe.agent import answer
from globe.interface import AgentRequest
from globe.llm import ScriptedLLM


def reports(user, **kwargs):
    return tools.get_expense_reports(caller_id=user, **kwargs)


def one_report(owner):
    with sqlite3.connect(tools.DB_PATH) as conn:
        return conn.execute("SELECT id FROM expense_reports WHERE employee_id=? LIMIT 1", (owner,)).fetchone()[0]


def test_self_reports():
    assert all(r["employee_id"] == "E024" for r in json.loads(reports("E024")))


def test_manager_direct_report():
    assert json.loads(reports("E012", employee_id="E024"))
    assert json.loads(reports("E012", employee_id="E012"))


@pytest.mark.parametrize("caller,target", [
    ("E024", "E004"), ("E024", "E030"), ("E012", "E004"),
    ("E002", "E024"), ("E024", "E001")
])
def test_forbidden_employee(caller, target):
    assert reports(caller, employee_id=target).startswith("ERROR")


def test_unfiltered_is_scoped():
    rows = json.loads(reports("E024", min_amount_gbp=0, limit=100))
    assert rows and all(r["employee_id"] == "E024" for r in rows)


def test_manager_unfiltered_is_scoped_to_one_level():
    rows = json.loads(reports("E002", limit=100))
    with sqlite3.connect(tools.DB_PATH) as conn:
        direct = {r[0] for r in conn.execute("SELECT id FROM employees WHERE manager_id=?", ("E002",))}
    assert rows and all(r["employee_id"] in direct | {"E002"} for r in rows)


def test_guess_report_id_is_denied():
    assert reports("E024", report_id=one_report("E004")) == "No matching expense reports."


def test_lines_self_and_direct_report():
    rid = one_report("E024")
    assert json.loads(tools.get_expense_lines(rid, caller_id="E024"))
    assert json.loads(tools.get_expense_lines(rid, caller_id="E012"))


def test_lines_foreign_report_and_unknown_indistinguishable():
    denied = tools.get_expense_lines(one_report("E004"), caller_id="E024")
    unknown = tools.get_expense_lines("R-NONEXISTENT", caller_id="E024")
    assert denied == unknown == "No accessible expense lines found."


def test_unknown_caller_denied():
    assert reports("E999").startswith("ERROR")
    assert tools.get_expense_lines(one_report("E024"), caller_id="E999").startswith("ERROR")


def test_missing_trusted_identity_is_not_allowed():
    with pytest.raises(TypeError):
        tools.get_expense_reports()
    with pytest.raises(TypeError):
        tools.dispatch("get_expense_reports", {})


def test_spoofed_caller_in_tool_args_denied():
    assert tools.dispatch("get_expense_reports", {"caller_id": "E001"}, caller_id="E024").startswith("ERROR")
    assert tools.dispatch("whoami", {"user_id": "E001"}, caller_id="E024").startswith("ERROR")


def test_llm_tool_call_cannot_override_identity():
    llm = ScriptedLLM([
        json.dumps({"tool": "get_expense_reports", "args": {"employee_id": "E004"}}),
        json.dumps({"answer": "No access.", "citations": []}),
    ])
    resp = answer(AgentRequest(user_id="E024", message="Show E004 reports"), llm=llm)
    assert resp.tool_calls and resp.tool_calls[0].ok is False
    assert "ERROR: access denied" in llm.seen[1][1][-1]["content"]


def test_database_failure_returns_safe_error(monkeypatch):
    def boom():
        raise sqlite3.OperationalError("secret backend detail")
    monkeypatch.setattr(tools, "_connect", boom)
    assert "secret backend detail" not in tools.dispatch("get_expense_reports", {}, caller_id="E024")


def test_dispatch_invalid_args():
    assert tools.dispatch("get_expense_reports", [], caller_id="E024").startswith("ERROR")
    assert tools.dispatch("get_expense_reports", {"limit": "abc"}, caller_id="E024").startswith("ERROR")

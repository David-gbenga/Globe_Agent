import json

from globe import retrieval, tools


def test_retrieval_finds_the_right_document():
    hits = retrieval.search("daily meal ceiling", k=3)
    assert any(h.doc_id == "per-diem-rates" for h in hits)


def test_retrieval_returns_doc_ids_for_citation():
    hits = retrieval.search("business class approval", k=3)
    assert all(h.doc_id and h.section is not None for h in hits)


def test_whoami_returns_manager_and_department():
    row = json.loads(tools.whoami(caller_id="E024"))
    assert row["id"] == "E024"
    assert row["manager_id"] == "E012"


def test_expense_lines_belong_to_their_report():
    reports = json.loads(tools.get_expense_reports(employee_id="E024", limit=1, caller_id="E024"))
    lines = json.loads(tools.get_expense_lines(reports[0]["id"], caller_id="E024"))
    assert all(l["report_id"] == reports[0]["id"] for l in lines)


def test_dispatch_rejects_unknown_tools():
    assert tools.dispatch("drop_table", {}, caller_id="E024").startswith("ERROR")


def test_dispatch_rejects_bad_arguments():
    assert tools.dispatch("whoami", {"nope": 1}, caller_id="E024").startswith("ERROR")

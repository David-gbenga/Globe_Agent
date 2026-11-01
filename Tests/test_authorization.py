"""Authorization tests.

These are the tests we will run against your submission, in spirit if not in
letter. They fail on the starter kit. That is the exercise.

`xfail(strict=True)` means: once you fix the hole, these turn into failures
telling you to delete the marker. Do that, and write better ones.
"""

import json

import pytest

from globe import tools


@pytest.mark.xfail(strict=True, reason="starter kit has no authorization")
def test_ic_cannot_read_another_employees_reports():
    """E024 is an individual contributor. E004 is in a different chain."""
    out = tools.get_expense_reports(employee_id="E004")
    assert "ERROR" in out or out == "No matching expense reports."


@pytest.mark.xfail(strict=True, reason="starter kit has no authorization")
def test_ic_cannot_enumerate_high_value_reports_across_the_company():
    out = tools.get_expense_reports(min_amount_gbp=5000)
    rows = json.loads(out) if out.startswith("[") else []
    assert all(r["employee_id"] == "E024" for r in rows)


@pytest.mark.xfail(strict=True, reason="starter kit has no authorization")
def test_manager_can_read_direct_reports_but_not_peers():
    """E012 manages E024, E030, E036 — and nobody else."""
    allowed = json.loads(tools.get_expense_reports(employee_id="E024"))
    assert allowed
    denied = tools.get_expense_reports(employee_id="E004")
    assert "ERROR" in denied or denied == "No matching expense reports."

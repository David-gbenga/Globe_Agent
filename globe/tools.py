"""The tools Globe can call.

Each entry in TOOLS is exposed to the model. `spec()` renders the catalogue
into the system prompt; `dispatch()` runs one call and returns a string that
gets appended to the conversation.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from globe import retrieval

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "expenses.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# --------------------------------------------------------------------------
# policy search
# --------------------------------------------------------------------------

def search_policies(query: str, k: int = 4) -> str:
    """Search company policy documents. Returns the matching sections."""
    hits = retrieval.search(query, k=k)
    if not hits:
        return "No matching policy sections."
    return "\n\n---\n\n".join(
        f"[doc_id: {h.doc_id} | section: {h.section}]\n{h.text}" for h in hits
    )


# --------------------------------------------------------------------------
# expense data
# --------------------------------------------------------------------------

def whoami(user_id: str) -> str:
    """Look up the profile of an employee."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, name, department, cost_centre, manager_id, status "
            "FROM employees WHERE id = ?",
            (user_id,),
        ).fetchone()
    if not row:
        return f"No employee with id {user_id}."
    return json.dumps(dict(row))


def get_expense_reports(
    report_id: str | None = None,
    employee_id: str | None = None,
    status: str | None = None,
    min_amount_gbp: float | None = None,
    limit: int = 20,
) -> str:
    """Look up expense reports."""
    clauses, params = [], []
    if report_id:
        clauses.append("r.id = ?")
        params.append(report_id)
    if employee_id:
        clauses.append("r.employee_id = ?")
        params.append(employee_id)
    if status:
        clauses.append("r.status = ?")
        params.append(status)
    if min_amount_gbp is not None:
        clauses.append("r.total_gbp >= ?")
        params.append(float(min_amount_gbp))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = (
        "SELECT r.id, r.employee_id, e.name AS employee_name, r.title, r.status, "
        "r.submitted_at, r.total_gbp, r.cost_centre "
        "FROM expense_reports r JOIN employees e ON e.id = r.employee_id "
        f"{where} ORDER BY r.submitted_at DESC LIMIT ?"
    )
    params.append(int(limit))
    with _connect() as conn:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    return json.dumps(rows, indent=2) if rows else "No matching expense reports."


def get_expense_lines(report_id: str) -> str:
    """List the individual line items on an expense report."""
    with _connect() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT id, report_id, category, description, amount_gbp, "
                "incurred_on, receipt_missing FROM expense_lines "
                "WHERE report_id = ? ORDER BY incurred_on",
                (report_id,),
            ).fetchall()
        ]
    return json.dumps(rows, indent=2) if rows else f"No lines on report {report_id}."


# --------------------------------------------------------------------------
# catalogue
# --------------------------------------------------------------------------

TOOLS: dict[str, dict[str, Any]] = {
    "search_policies": {
        "fn": search_policies,
        "args": {"query": "str — what to look up", "k": "int, optional (default 4)"},
        "description": "Search company travel, expense and procurement policy documents.",
    },
    "whoami": {
        "fn": whoami,
        "args": {"user_id": "str"},
        "description": "Look up an employee profile: department, cost centre, manager.",
    },
    "get_expense_reports": {
        "fn": get_expense_reports,
        "args": {
            "report_id": "str, optional",
            "employee_id": "str, optional",
            "status": "str, optional — draft | submitted | approved | rejected | paid",
            "min_amount_gbp": "float, optional",
            "limit": "int, optional (default 20)",
        },
        "description": "Look up expense reports.",
    },
    "get_expense_lines": {
        "fn": get_expense_lines,
        "args": {"report_id": "str"},
        "description": "List line items on one expense report.",
    },
}


def spec() -> str:
    lines = []
    for name, t in TOOLS.items():
        args = ", ".join(f"{k}: {v}" for k, v in t["args"].items())
        lines.append(f"- {name}({args})\n    {t['description']}")
    return "\n".join(lines)


def dispatch(name: str, args: dict[str, Any]) -> str:
    tool = TOOLS.get(name)
    if tool is None:
        return f"ERROR: no such tool {name!r}. Available: {', '.join(TOOLS)}"
    try:
        return tool["fn"](**args)
    except TypeError as exc:
        return f"ERROR: bad arguments for {name}: {exc}"

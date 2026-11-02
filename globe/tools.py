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

DENIED = "ERROR: access denied or resource unavailable."


def _visible_employee_ids(conn: sqlite3.Connection, caller_id: str) -> tuple[str, ...]:
    """Only caller + immediate direct reports; never traverse manager hierarchy."""
    if not isinstance(caller_id, str) or not caller_id.strip():
        return ()
    found = conn.execute("SELECT id FROM employees WHERE id = ?", (caller_id,)).fetchone()
    if found is None:
        return ()
    reports = conn.execute("SELECT id FROM employees WHERE manager_id = ?", (caller_id,))
    return (caller_id, *(row[0] for row in reports))


def whoami(*, caller_id: str) -> str:
    """Return only the authenticated caller's profile."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, name, department, cost_centre, manager_id, status "
            "FROM employees WHERE id = ?", (caller_id,)
        ).fetchone()
    return json.dumps(dict(row)) if row else DENIED


def get_expense_reports(
    report_id: str | None = None,
    employee_id: str | None = None,
    status: str | None = None,
    min_amount_gbp: float | None = None,
    limit: int = 20,
    *,
    caller_id: str,
) -> str:
    """Read only self and direct reports, even for unfiltered or report-id queries."""
    with _connect() as conn:
        visible = _visible_employee_ids(conn, caller_id)
        if not visible:
            return DENIED
        if employee_id is not None and employee_id not in visible:
            return DENIED
        slots = ",".join("?" for _ in visible)
        clauses = [f"r.employee_id IN ({slots})"]
        params: list[Any] = list(visible)
        if report_id is not None:
            clauses.append("r.id = ?")
            params.append(report_id)
        if employee_id is not None:
            clauses.append("r.employee_id = ?")
            params.append(employee_id)
        if status is not None:
            clauses.append("r.status = ?")
            params.append(status)
        if min_amount_gbp is not None:
            clauses.append("r.total_gbp >= ?")
            params.append(float(min_amount_gbp))
        safe_limit = max(1, min(int(limit), 100))
        sql = (
            "SELECT r.id, r.employee_id, e.name AS employee_name, r.title, r.status, "
            "r.submitted_at, r.total_gbp, r.cost_centre "
            "FROM expense_reports r JOIN employees e ON e.id = r.employee_id "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY r.submitted_at DESC LIMIT ?"
        )
        rows = [dict(row) for row in conn.execute(sql, [*params, safe_limit])]
    return json.dumps(rows, indent=2) if rows else "No matching expense reports."


def get_expense_lines(report_id: str, *, caller_id: str) -> str:
    """Authorize report ownership in the same query that retrieves its lines."""
    with _connect() as conn:
        visible = _visible_employee_ids(conn, caller_id)
        if not visible:
            return DENIED
        slots = ",".join("?" for _ in visible)
        rows = [dict(row) for row in conn.execute(
            "SELECT l.id, l.report_id, l.category, l.description, l.amount_gbp, "
            "l.incurred_on, l.receipt_missing "
            "FROM expense_lines l JOIN expense_reports r ON r.id = l.report_id "
            f"WHERE l.report_id = ? AND r.employee_id IN ({slots}) "
            "ORDER BY l.incurred_on", (report_id, *visible)
        )]
    # Uniform denial/unknown response prevents report-id enumeration.
    return json.dumps(rows, indent=2) if rows else "No accessible expense lines found."


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
        "args": {},
        "description": "Look up the authenticated caller profile.",
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


def dispatch(name: str, args: dict[str, Any], *, caller_id: str) -> str:
    """Trusted caller supplied by the agent, NEVER from model-generated args."""
    tool = TOOLS.get(name)
    if tool is None:
        return f"ERROR: no such tool {name!r}. Available: {', '.join(TOOLS)}"
    if not isinstance(args, dict):
        return "ERROR: tool arguments must be an object"
    if not isinstance(caller_id, str) or not caller_id:
        return DENIED
    if "caller_id" in args or "user_id" in args:
        return DENIED
    try:
        if name == "search_policies":
            return tool["fn"](**args)
        return tool["fn"](**args, caller_id=caller_id)
    except (TypeError, ValueError) as exc:
        return f"ERROR: bad arguments for {name}: {type(exc).__name__}"
    except sqlite3.Error:
        return "ERROR: database unavailable"

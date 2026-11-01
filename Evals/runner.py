"""Evaluation harness.

    make eval                # real model
    GLOBE_FAKE=1 make eval   # offline, checks the pipeline only

Reads evals/cases.yaml, runs each case through globe.agent.answer(), applies
assertions, writes EVAL_REPORT.md.

Add cases. Add assertion types if you need them — the registry at the bottom
is the extension point. You should not need to rewrite this file.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from globe.agent import answer  # noqa: E402
from globe.interface import AgentRequest, AgentResponse  # noqa: E402
from globe.llm import get_llm  # noqa: E402

CASES = ROOT / "evals" / "cases.yaml"
REPORT = ROOT / "EVAL_REPORT.md"
DB = ROOT / "data" / "expenses.db"


# --------------------------------------------------------------------------
# assertions
# --------------------------------------------------------------------------

@dataclass
class Case:
    id: str
    category: str
    user_id: str
    question: str
    assertions: dict
    note: str = ""


@dataclass
class Result:
    case: Case
    response: AgentResponse | None
    failures: list[str] = field(default_factory=list)
    error: str | None = None
    latency_ms: int = 0

    @property
    def passed(self) -> bool:
        return self.error is None and not self.failures


def _reports_owned_by_others(user_id: str) -> set[str]:
    """Report ids the caller is not entitled to see (self + direct reports)."""
    conn = sqlite3.connect(DB)
    entitled = {user_id} | {
        r[0] for r in conn.execute(
            "SELECT id FROM employees WHERE manager_id = ?", (user_id,)
        )
    }
    placeholders = ",".join("?" * len(entitled))
    rows = conn.execute(
        f"SELECT id FROM expense_reports WHERE employee_id NOT IN ({placeholders})",
        tuple(entitled),
    ).fetchall()
    conn.close()
    return {r[0] for r in rows}


def a_contains_any(resp, case, expected) -> str | None:
    low = resp.reply.lower()
    if not any(str(e).lower() in low for e in expected):
        return f"reply contains none of {expected}"
    return None


def a_contains_all(resp, case, expected) -> str | None:
    low = resp.reply.lower()
    missing = [e for e in expected if str(e).lower() not in low]
    return f"reply missing {missing}" if missing else None


def a_not_contains_any(resp, case, forbidden) -> str | None:
    low = resp.reply.lower()
    hits = [f for f in forbidden if str(f).lower() in low]
    return f"reply contains forbidden {hits}" if hits else None


def a_cites_any(resp, case, docs) -> str | None:
    cited = {c.doc_id for c in resp.citations}
    if not cited & set(docs):
        return f"cited {sorted(cited) or 'nothing'}, expected one of {docs}"
    return None


def a_citations_non_empty(resp, case, expected) -> str | None:
    if bool(resp.citations) != bool(expected):
        return f"citations_non_empty expected {expected}, got {len(resp.citations)} citations"
    return None


def a_tool_called(resp, case, names) -> str | None:
    used = {t.name for t in resp.tool_calls}
    missing = [n for n in names if n not in used]
    return f"tools not called: {missing}" if missing else None


def a_tool_not_called(resp, case, names) -> str | None:
    used = {t.name for t in resp.tool_calls}
    hits = [n for n in names if n in used]
    return f"tools should not have been called: {hits}" if hits else None


def a_asks_clarifying(resp, case, expected) -> str | None:
    asked = "?" in resp.reply
    if asked != bool(expected):
        return f"asks_clarifying expected {expected}, got {asked}"
    return None


def a_no_data_for_others(resp, case, expected) -> str | None:
    """Deterministic leak check: no report id the caller cannot see may appear."""
    if not expected:
        return None
    leaked = sorted(r for r in _reports_owned_by_others(case.user_id) if r in resp.reply)
    return f"leaked report ids the caller may not see: {leaked[:5]}" if leaked else None


def a_max_steps(resp, case, limit) -> str | None:
    return f"used {resp.steps} steps, limit {limit}" if resp.steps > int(limit) else None


ASSERTIONS = {
    "contains_any": a_contains_any,
    "contains_all": a_contains_all,
    "not_contains_any": a_not_contains_any,
    "cites_any": a_cites_any,
    "citations_non_empty": a_citations_non_empty,
    "tool_called": a_tool_called,
    "tool_not_called": a_tool_not_called,
    "asks_clarifying": a_asks_clarifying,
    "no_data_for_others": a_no_data_for_others,
    "max_steps": a_max_steps,
}


# --------------------------------------------------------------------------
# running
# --------------------------------------------------------------------------

def load_cases(path: Path = CASES) -> list[Case]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Case(**c) for c in raw["cases"]]


def run_case(case: Case, llm) -> Result:
    started = time.time()
    try:
        resp = answer(
            AgentRequest(user_id=case.user_id, message=case.question, trace_id=case.id),
            llm=llm,
        )
    except Exception as exc:  # noqa: BLE001
        return Result(case, None, error=f"{type(exc).__name__}: {exc}",
                      latency_ms=int((time.time() - started) * 1000))

    failures = []
    for name, expected in case.assertions.items():
        fn = ASSERTIONS.get(name)
        if fn is None:
            failures.append(f"unknown assertion type {name!r}")
            continue
        problem = fn(resp, case, expected)
        if problem:
            failures.append(f"{name}: {problem}")
    return Result(case, resp, failures, latency_ms=int((time.time() - started) * 1000))


def write_report(results: list[Result], path: Path = REPORT) -> None:
    total = len(results)
    passed = sum(r.passed for r in results)
    by_cat: dict[str, list[Result]] = {}
    for r in results:
        by_cat.setdefault(r.case.category, []).append(r)

    lats = sorted(r.latency_ms for r in results) or [0]
    p50 = lats[len(lats) // 2]
    p95 = lats[min(len(lats) - 1, int(len(lats) * 0.95))]

    out = ["# Globe Evaluation Report", ""]
    out.append(f"**{passed}/{total} passed** ({passed / max(total,1):.0%})  ")
    out.append(f"latency p50 {p50} ms · p95 {p95} ms · "
               f"mean steps {statistics.mean([r.response.steps for r in results if r.response] or [0]):.1f}")
    out += ["", "## By category", "", "| Category | Passed | Total | Rate |", "|---|---|---|---|"]
    for cat in sorted(by_cat):
        rs = by_cat[cat]
        p = sum(r.passed for r in rs)
        out.append(f"| {cat} | {p} | {len(rs)} | {p / len(rs):.0%} |")

    out += ["", "## Cases", "", "| Case | Category | Result | Steps | ms |", "|---|---|---|---|---|"]
    for r in results:
        mark = "pass" if r.passed else "FAIL"
        out.append(f"| `{r.case.id}` | {r.case.category} | {mark} | "
                   f"{r.response.steps if r.response else '-'} | {r.latency_ms} |")

    failures = [r for r in results if not r.passed]
    if failures:
        out += ["", "## Failures", ""]
        for r in failures:
            out.append(f"### `{r.case.id}` — {r.case.category}")
            out.append(f"*{r.case.question}* (as `{r.case.user_id}`)")
            out.append("")
            if r.error:
                out.append(f"- error: {r.error}")
            for f in r.failures:
                out.append(f"- {f}")
            if r.response:
                snippet = r.response.reply.replace("\n", " ")[:300]
                out.append(f"- reply: {snippet or '(empty)'}")
            out.append("")

    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="run one case by id")
    ap.add_argument("--category", help="run one category")
    args = ap.parse_args()

    cases = load_cases()
    if args.only:
        cases = [c for c in cases if c.id == args.only]
    if args.category:
        cases = [c for c in cases if c.category == args.category]
    if not cases:
        print("no cases matched")
        return 1

    llm = get_llm()
    results = []
    for case in cases:
        r = run_case(case, llm)
        results.append(r)
        mark = "PASS" if r.passed else "FAIL"
        print(f"[{mark}] {case.id:<28} {case.category}")
        for f in r.failures:
            print(f"        {f}")
        if r.error:
            print(f"        error: {r.error}")

    write_report(results)
    passed = sum(r.passed for r in results)
    print(f"\n{passed}/{len(results)} passed — wrote {REPORT.relative_to(ROOT)}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

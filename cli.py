"""Ask Globe one question from the command line.

    python cli.py --user E024 "what is the meal ceiling in London?"
    GLOBE_FAKE=1 python cli.py --user E024 "hello"
"""

from __future__ import annotations

import argparse

from globe.agent import answer
from globe.interface import AgentRequest
from globe.llm import get_llm


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="+")
    ap.add_argument("--user", default="E024", help="authenticated employee id")
    ap.add_argument("--trace", default="cli", help="trace id")
    args = ap.parse_args()

    resp = answer(
        AgentRequest(user_id=args.user, message=" ".join(args.question), trace_id=args.trace),
        llm=get_llm(),
    )

    print(resp.reply or "(no reply)")
    if resp.citations:
        print("\nsources:")
        for c in resp.citations:
            print(f"  - {c.doc_id} :: {c.section}")
    print(f"\n[{resp.steps} steps, {len(resp.tool_calls)} tool calls, {resp.stopped_reason}]")
    for t in resp.tool_calls:
        print(f"  {t.name}({t.args})")


if __name__ == "__main__":
    main()

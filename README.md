# Globe — AI Agent

Globe is an internal AI assistant for the Finance team. It answers employee questions about travel and expense policy and retrieves expense report data from the company database. It was built as a proof-of-concept by a data scientist in the AI engineering team.

> *"It works, but is not safe to run in a production environment."* — data scientist's handoff note

---

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
make setup                      # installs deps and builds data/expenses.db
cp .env.example .env            # add credentials (see below)
```

Check it works:

```bash
make test                       # 11 pass, 3 xfail (the xfails are the point)
make run Q="What is the daily meal ceiling in London?"
make eval                       # writes EVAL_REPORT.md
```

Everything runs offline with `GLOBE_FAKE=1` (a canned-response fake). Useful for checking the pipeline, useless for judging answer quality.

If you encounter a setup problem that prevents you from starting, contact us rather than spending assessment time troubleshooting the environment.

---

## LLM provider

The starter kit includes a minimal HTTP client in `globe/llm.py` with no SDK dependencies. It supports two providers via `GLOBE_LLM_PROVIDER`; you must supply your own credentials:

| Provider | `GLOBE_LLM_PROVIDER` | Credentials in `.env` |
|---|---|---|
| Azure OpenAI (default) | `azure` | `AZURE_OPENAI_API_KEY` |
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` |

Set `GLOBE_MODEL` to the deployment or model name for your provider. For Azure, this is the Foundry deployment name (not the underlying model ID).

To use another provider (OpenAI, local models, etc.), implement `LLMClient` in `globe/llm.py` and register it in `get_llm()`. Keep the `complete(system, messages)` signature so tests and the eval harness keep working.

---

## What is here

```
globe/
  interface.py    AgentRequest / AgentResponse — do not change the signatures
  agent.py        the tool-calling loop
  tools.py        the tools the model can call
  retrieval.py    BM25 over docs/ — you should not need to touch this
  llm.py          LLM clients (Azure, Anthropic) + ScriptedLLM / FakeLLM for tests
docs/             16 policy documents
data/expenses.db  employees, expense_reports, expense_lines
evals/
  runner.py       the eval harness — extend the assertion registry if needed
  cases.yaml      5 seed cases; you need 15+
tests/            example tests, including three that are meant to fail
scripts/build_db.py   regenerates the database deterministically
cli.py            ask one question
```

The grading harness calls exactly one thing:

```python
from globe.agent import answer
answer(AgentRequest(user_id="E024", message="...", trace_id="...")) -> AgentResponse
```

Keep that importable and side-effect-free on import. Everything behind it is yours to restructure.

---

## The fixture

The database contains forty employees in a three-level hierarchy. `employees.manager_id` is the authorization relation that matters.

| id | role in the fixture |
|---|---|
| `E001` | CFO, no manager, owns a report over £10,000 |
| `E002` | Engineering head, manages `E012` |
| `E012` | Engineering lead, manages `E024`, `E030`, `E036` |
| `E024` | Individual contributor, managed by `E012` |
| `E004` | Sales head — a different chain, useful for denial tests |
| `E034` | departed employee with an outstanding claim |

Also present, because real data is not tidy: a duplicated submission, a report with a null cost centre, and line items with missing receipts.

---

## Notes on the design

- The agent uses a **JSON protocol** rather than provider-native tool calling, so it stays portable across models and so `ScriptedLLM` can pin behaviour in tests. That part is intentional; keep it or change it, but say which.
- Retrieval is BM25 over 16 documents. Sixteen documents do not need a vector database, and we are not scoring retrieval.
- Other implementation details may be changed where you believe this improves the solution; some existing choices are intentionally imperfect.

---
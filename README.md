# Globe — Finance Policy & Expense Agent

Globe is a read-only Finance assistant for travel/expense policy Q&A and employee expense reports. It uses BM25 over Markdown, SQLite, JSON-based tool calling and Microsoft Foundry v1 (Azure OpenAI). **Not production-ready.** Grading entry point: `globe.agent.answer(AgentRequest(...)) -> AgentResponse`.

## Setup and verification (Windows PowerShell; no `make` required)

From the project root, with **Python 3.12** installed:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts/build_db.py               # Only if data/expenses.db needs creating/rebuilding
Copy-Item env.example .env              # If .env does not already exist; add your own credentials
```

In `.env`, set `GLOBE_LLM_PROVIDER=azure`, `GLOBE_MODEL` (**Foundry deployment name**), `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_API_KEY`. Anthropic is also supported (`GLOBE_LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY`). Never commit `.env`. `$env:GLOBE_FAKE = '1'` runs canned offline responses for pipeline checks, **not answer quality**.

```powershell
python -m pytest -v
$env:GLOBE_FAKE = '0'                    # Live provider (requires valid .env)
python cli.py --user E024 "What is the daily meal ceiling in London?"
python evals/runner.py --repeat 3        # Writes EVAL_REPORT.md; nonzero exit if gate fails
```

The starter `Makefile` remains available (`make setup/test/run/eval`). I used Windows Python commands because GNU Make was unavailable. Rebuilding the DB may overwrite fixture changes.

## What I changed and the hardest decisions

1. **Authorization in code, not prompts.** `request.user_id` is trusted; the dispatcher rejects identity overrides and scoped SQL limits access to self/direct reports, including report lines. I rejected prompt-only permissions. The model should consult the authorized tool before assuming a manager lacks access.
2. **Retrieval is evidence, not authority.** A deliberately poisoned appendix contains disclosure instructions. Tool output is marked untrusted and citations are checked against retrieved document/section IDs. I rejected obeying retrieved instructions or blindly accepting model citations. **Valid citations do not prove semantic support.**
3. **Bound execution; measure failures.** The loop caps steps at 12, uses an **estimated** 16,000-token budget and limits tool output, with caveated fallbacks. I kept JSON tool calling and BM25 rather than adopting native function calls, vector search or orchestration infrastructure. I prioritised deterministic assertions and repeated live evaluation.

## Evaluation, known failures and production signals

The **25 evaluation cases** cover grounding, refusal, authorization, prompt injection and ambiguity. The runner reports category rates and failures without an LLM judge. Latest supplied **live** result (4 November 2026): **71/75 (95% rounded)** across three repeats; grounding **15/15**, refusal **15/15**, ambiguity **15/15**, authorization **14/15**, injection **12/15**. **23/25 cases passed every repetition.** I retained failures. Some appropriate “not trustworthy”/“access is restricted” replies fail narrow string assertions; passing citation IDs also cannot prove semantic support or absence of leakage.

Remaining weaknesses: pattern-based clarification may miss unseen phrasings; token estimates are not exact usage; provider timeouts do not guarantee an end-to-end deadline. In production I would monitor **redacted** traces, tool decisions, citation IDs, stop reasons, latency, provider usage and denials; alert on leakage signals, citation failures, timeouts and drift; sample failures without logging private expense contents; and add incidents to regression cases.

## Deliberate scope cuts and AI-assisted development

I intentionally omitted writes, UI, vector storage, semantic entailment verification, exact token accounting and production telemetry: they add integration risk beyond the core safety/evaluation goals. I used **ChatGPT** for code-review ideas, targeted patches, test design and documentation; I inspected changes and used pytest plus live evaluations rather than treating AI output as proof. Total effort was **approximately five hours**, exceeding the suggested three. In hindsight, I should have stopped after the core authorization, injection and evaluation gates rather than polishing edge cases.

## Future write path: raising policy exceptions (not implemented)

A policy exception is a **mutation**, requiring a trusted workflow—not arbitrary SQL or a general-purpose write tool exposed to the LLM. A narrow `create_policy_exception` service would accept a typed request containing the expense reference, category, justification and evidence. The agent could draft it, but would display the exact proposed action and require explicit user confirmation. Identity would be taken from the authenticated session, not model arguments; server-side checks would verify report ownership/manager scope, required fields and permission to _request_, not approve, an exception.

Submission would be transactional and idempotent to prevent duplicates on retries. It would create a **pending** request and an immutable audit entry with actor, timestamp and policy version—never change reimbursement or self-approve. A separate reviewer role would control approval transitions, with segregation of duties and notifications. I would use least-privilege DB credentials, rate limits, session/CSRF protections where relevant, retention controls and redacted logs. Adversarial tests would cover foreign report IDs, prompt injection, duplicate retries, failed writes and concurrent submissions. Alerts would flag unusual mutations, authorization denials and audit gaps. The existing assistant would remain read-only until this workflow was independently reviewed.

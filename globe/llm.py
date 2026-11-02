"""LLM access, plus fakes so you can write deterministic tests.

Real calls go through a provider selected by `GLOBE_LLM_PROVIDER` (default:
`azure`). Tests should use `ScriptedLLM` or `FakeLLM` — they implement the
same `complete()` interface and never touch the network.

To use your own provider, add a class that implements `LLMClient` and extend
`get_llm()`. Keep the `complete()` signature.
"""

from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from typing import Protocol
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = os.environ.get("GLOBE_MODEL", "gpt-5-nano")
AZURE_OPENAI_ENDPOINT = os.environ.get(
    "AZURE_OPENAI_ENDPOINT",
    "https://api.openai.com",
)
AZURE_OPENAI_API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")
ANTHROPIC_API_VERSION = os.environ.get("ANTHROPIC_API_VERSION", "2023-06-01")
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")


class LLMClient(Protocol):
    def complete(self, system: str, messages: list[dict]) -> str: ...


class LLMError(RuntimeError):
    pass


def _ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context()


def _http_json(
    url: str,
    payload: dict,
    headers: dict[str, str],
    *,
    timeout: int = 60,
) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:  # pragma: no cover
        raise LLMError(f"{exc.code}: {exc.read()[:400]!r}") from exc
    except Exception as exc:  # pragma: no cover
        raise LLMError(str(exc)) from exc



def _azure_chat_url() -> str:
    endpoint = AZURE_OPENAI_ENDPOINT.rstrip("/")
    return f"{endpoint}/openai/v1/chat/completions"



class AzureOpenAILLM:
    """Minimal Azure OpenAI client. No SDK dependency, no retries, no timeout tuning.

    (Yes, that is a hint.)
    """

    def __init__(self, deployment: str = DEFAULT_MODEL, api_key: str | None = None):
        self.deployment = deployment
        self.api_key = api_key or os.environ.get("AZURE_OPENAI_API_KEY") or os.environ.get("API_KEY", "")
        if not self.api_key:
            raise LLMError(
                "AZURE_OPENAI_API_KEY (or API_KEY) is not set. Copy .env.example to .env, "
                "or run with GLOBE_FAKE=1 to use the offline fake."
            )
        self.calls = 0

    
    def complete(self, system: str, messages: list[dict]) -> str:
        self.calls += 1

        payload = {
        "model": self.deployment,
        "messages": [
            {"role": "system", "content": system},
            *messages,
        ],
        "max_completion_tokens": 4094,
    }

        body = _http_json(
        _azure_chat_url(),
        payload,
        {
            "content-type": "application/json",
            "api-key": self.api_key,
        },
    )

        choices = body.get("choices") or []

        if not choices:
            return ""

        message = choices[0].get("message") or {}

        return message.get("content", "") or ""



class AnthropicLLM:
    """Minimal Anthropic Messages API client — same no-SDK pattern as Azure."""

    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model = model or os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not self.api_key:
            raise LLMError(
                "ANTHROPIC_API_KEY is not set. Add it to .env, "
                "or run with GLOBE_FAKE=1 to use the offline fake."
            )
        self.calls = 0

    def complete(self, system: str, messages: list[dict]) -> str:
        self.calls += 1
        payload = {
            "model": self.model,
            "max_tokens": 4094,
            "system": system,
            "messages": messages,
        }
        body = _http_json(
            f"{ANTHROPIC_BASE_URL.rstrip('/')}/v1/messages",
            payload,
            {
                "content-type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": ANTHROPIC_API_VERSION,
            },
        )
        content = body.get("content") or []
        for block in content:
            if block.get("type") == "text":
                return block.get("text", "") or ""
        return ""


class ScriptedLLM:
    """Replays a fixed list of responses, in order.

    Use this to pin agent behaviour in unit tests:

        llm = ScriptedLLM([
            '{"tool": "search_policies", "args": {"query": "per diem"}}',
            '{"answer": "The London per diem is 45 GBP.", '
            ' "citations": [{"doc_id": "per-diem-rates", "section": "UK"}]}',
        ])
    """

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.seen: list[tuple[str, list[dict]]] = []
        self.calls = 0

    def complete(self, system: str, messages: list[dict]) -> str:
        self.seen.append((system, messages))
        self.calls += 1
        if not self.responses:
            raise LLMError("ScriptedLLM ran out of responses — the loop called more times than expected")
        return self.responses.pop(0)


class FakeLLM:
    """Matches a substring of the latest user turn to a canned response.

    Cheap way to run the whole pipeline (including `make eval`) offline.
    Falls back to a generic refusal.
    """

    def __init__(self, rules: list[tuple[str, str]] | None = None, default: str | None = None):
        self.rules = rules or []
        self.default = default or json.dumps(
            {"answer": "I don't have enough information to answer that.", "citations": []}
        )
        self.calls = 0

    def complete(self, system: str, messages: list[dict]) -> str:
        self.calls += 1
        last = messages[-1]["content"] if messages else ""
        for needle, response in self.rules:
            if needle.lower() in str(last).lower():
                return response
        return self.default


_PROVIDERS: dict[str, type[LLMClient]] = {
    "azure": AzureOpenAILLM,
    "anthropic": AnthropicLLM,
}


def get_llm() -> LLMClient:
    """Factory used by the CLI and the eval runner. GLOBE_FAKE=1 -> offline."""
    if os.environ.get("GLOBE_FAKE") == "1":
        return FakeLLM()
    provider = os.environ.get("GLOBE_LLM_PROVIDER", "azure").lower()
    cls = _PROVIDERS.get(provider)
    if cls is None:
        supported = ", ".join(sorted(_PROVIDERS))
        raise LLMError(f"Unknown GLOBE_LLM_PROVIDER {provider!r}. Supported: {supported}")
    return cls()

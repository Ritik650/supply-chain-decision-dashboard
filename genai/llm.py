"""Thin LLM client. Three providers cover the plan's "Gemini or an open model":

    groq     Groq (open models, free tier)   env GROQ_API_KEY            default openai/gpt-oss-120b
    gemini   Google Gemini API               env GEMINI_API_KEY          default gemini-3.6-flash
    openai   any OpenAI-compatible endpoint  env OPENAI_API_KEY + OPENAI_BASE_URL
             (OpenRouter, Together, or a local Ollama at http://localhost:11434/v1)

Choose with SCDD_PROVIDER (default: groq if GROQ_API_KEY is set, else gemini) and SCDD_MODEL.
Keys can live in a `.env` file at the repo root (git-ignored), e.g. `GROQ_API_KEY=...`.
Temperature is 0 so evaluation runs are as repeatable as the API allows. Rate-limit and
"high demand" responses are retried with backoff, so an API hiccup is not scored as a wrong answer.

    python genai/llm.py --list      # models your Gemini key can call
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODELS = {"groq": "openai/gpt-oss-120b", "gemini": "gemini-3.6-flash", "openai": "llama-3.3-70b-versatile"}
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
RETRY_WAITS = (5, 15, 30, 60)   # seconds; for 429 rate limits, 503 "high demand" and 504 timeouts
RETRY_CODES = (429, 500, 502, 503, 504)


def _load_dotenv() -> None:
    """Read KEY=VALUE lines from the repo-root .env without overriding real environment variables."""
    env = Path(__file__).resolve().parents[1] / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def _default_provider() -> str:
    return os.getenv("SCDD_PROVIDER") or ("groq" if os.getenv("GROQ_API_KEY") else "gemini")


@dataclass
class LLM:
    provider: str
    model: str

    @classmethod
    def from_env(cls, provider: str | None = None, model: str | None = None) -> "LLM":
        provider = (provider or _default_provider()).lower()
        if provider not in DEFAULT_MODELS:
            raise ValueError(f"unknown provider {provider!r}; use one of {sorted(DEFAULT_MODELS)}")
        return cls(provider, model or os.getenv("SCDD_MODEL") or DEFAULT_MODELS[provider])

    def complete(self, system: str, user: str) -> str:
        if self.provider == "gemini":
            return self._gemini(system, user)
        return self._openai(system, user)

    def _gemini(self, system: str, user: str) -> str:
        from google import genai
        from google.genai import errors, types

        key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("Set GEMINI_API_KEY (free key: https://aistudio.google.com/apikey).")
        client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=90_000))
        for wait in (*RETRY_WAITS, None):
            try:
                resp = client.models.generate_content(
                    model=self.model,
                    contents=user,
                    config=types.GenerateContentConfig(system_instruction=system, temperature=0.0),
                )
                return resp.text or ""
            except (errors.ServerError, errors.ClientError) as e:
                if wait is None or getattr(e, "code", None) not in RETRY_CODES:
                    raise
                time.sleep(wait)
        return ""

    def _openai(self, system: str, user: str) -> str:
        from openai import APIStatusError, OpenAI

        if self.provider == "groq":
            key = os.getenv("GROQ_API_KEY")
            if not key:
                raise RuntimeError("Set GROQ_API_KEY (free key: https://console.groq.com/keys).")
            client = OpenAI(base_url=GROQ_BASE_URL, api_key=key, timeout=90, max_retries=0)
        else:
            client = OpenAI(base_url=os.getenv("OPENAI_BASE_URL"), api_key=os.getenv("OPENAI_API_KEY", "not-needed"),
                            timeout=90, max_retries=0)
        for wait in (*RETRY_WAITS, None):
            try:
                resp = client.chat.completions.create(
                    model=self.model,
                    temperature=0.0,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                )
                return resp.choices[0].message.content or ""
            except APIStatusError as e:
                if wait is None or e.status_code not in RETRY_CODES:
                    raise
                time.sleep(wait)
        return ""


def list_gemini_models() -> list[str]:
    from google import genai

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    return sorted(m.name.removeprefix("models/") for m in client.models.list()
                  if "generateContent" in (getattr(m, "supported_actions", None) or []))


if __name__ == "__main__" and "--list" in sys.argv:
    print("\n".join(list_gemini_models()))

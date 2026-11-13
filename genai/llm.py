"""Thin LLM client. Two providers cover the plan's "Gemini or an open model":

    gemini   Google Gemini API      env GEMINI_API_KEY (or GOOGLE_API_KEY)
    openai   any OpenAI-compatible  env OPENAI_API_KEY + OPENAI_BASE_URL
             endpoint: Groq, OpenRouter, Together, or a local Ollama
             (OPENAI_BASE_URL=http://localhost:11434/v1, any key)

Choose with SCDD_PROVIDER (default: gemini) and SCDD_MODEL (default per provider).
Temperature is 0 so evaluation runs are as repeatable as the API allows.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_MODELS = {"gemini": "gemini-2.5-flash", "openai": "llama-3.3-70b-versatile"}


@dataclass
class LLM:
    provider: str
    model: str

    @classmethod
    def from_env(cls, provider: str | None = None, model: str | None = None) -> "LLM":
        provider = (provider or os.getenv("SCDD_PROVIDER") or "gemini").lower()
        if provider not in DEFAULT_MODELS:
            raise ValueError(f"unknown provider {provider!r}; use one of {sorted(DEFAULT_MODELS)}")
        return cls(provider, model or os.getenv("SCDD_MODEL") or DEFAULT_MODELS[provider])

    def complete(self, system: str, user: str) -> str:
        if self.provider == "gemini":
            return self._gemini(system, user)
        return self._openai(system, user)

    def _gemini(self, system: str, user: str) -> str:
        from google import genai
        from google.genai import types

        key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("Set GEMINI_API_KEY (free key: https://aistudio.google.com/apikey).")
        client = genai.Client(api_key=key)
        resp = client.models.generate_content(
            model=self.model,
            contents=user,
            config=types.GenerateContentConfig(system_instruction=system, temperature=0.0),
        )
        return resp.text or ""

    def _openai(self, system: str, user: str) -> str:
        from openai import OpenAI

        client = OpenAI(base_url=os.getenv("OPENAI_BASE_URL"), api_key=os.getenv("OPENAI_API_KEY", "not-needed"))
        resp = client.chat.completions.create(
            model=self.model,
            temperature=0.0,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return resp.choices[0].message.content or ""

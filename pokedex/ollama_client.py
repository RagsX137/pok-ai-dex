"""Thin wrapper around the local Ollama instance.

Centralises the `ol.Client` construction so blueprints and agent.py share one
module rather than each building their own client.
"""
from __future__ import annotations

import os

import ollama as ol

from pokedex.config import settings

_client = ol.Client(host=settings.ollama_base_url)


def chat(prompt: str, model: str | None = None) -> str:
    """Send a single-turn prompt to Ollama and return the text response.

    `model` defaults to the OLLAMA_MODEL env var (which /api/set-model updates
    at runtime) falling back to the value baked into settings at import time.
    """
    effective_model = model or os.getenv("OLLAMA_MODEL", settings.ollama_model)
    resp = _client.chat(
        model=effective_model,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp["message"]["content"]


def list_local_models() -> list[str]:
    """Return the names of all Ollama models pulled locally."""
    try:
        resp = _client.list()
        # ollama >= 0.4 returns a pydantic ListResponse whose entries expose
        # `.model`; older versions returned {"models": [{"name": ...}]}. The
        # old dict access raised KeyError('name') and was silently swallowed,
        # so the UI fell back to five hardcoded models, none of them installed.
        raw = getattr(resp, "models", None)
        if raw is None and isinstance(resp, dict):
            raw = resp.get("models", [])
        names = [
            getattr(m, "model", None) or (m.get("model") or m.get("name"))
            for m in (raw or [])
        ]
        return [n for n in names if n]
    except Exception:
        return []

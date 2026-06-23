"""
Thin async wrapper around Ollama's /api/chat endpoint.

We keep this isolated from the route so the rest of the backend never has
to know we're talking to an LLM — just a `chat(system, user) -> str` call.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from config import settings

log = logging.getLogger(__name__)


class OllamaUnreachable(Exception):
    """Raised when Ollama is down or the network can't reach it."""


class OllamaError(Exception):
    """Raised when Ollama returns an error response."""


async def chat(
    *,
    system: str,
    user: str,
    model: Optional[str] = None,
    temperature: float = 0.0,
    timeout_s: float = 180.0,
) -> str:
    """Call Ollama's /api/chat with a single user turn and return the
    assistant's text content.

    `temperature=0` for deterministic SQL generation. The summary call can
    pass a higher value for more readable prose.

    `timeout_s` defaults to 180s — generous to absorb cold-model loads
    (~15-30s for a 14b model on first call). Warm calls return in 2-5s.
    """
    url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    body = {
        "model": model or settings.OLLAMA_MODEL,
        "stream": False,
        "options": {"temperature": temperature},
        # Keep the model resident in VRAM for an hour after each request.
        # Ollama's default is 5 minutes; for an interactive chat UI that
        # means every ~6th question pays the cold-load cost again.
        "keep_alive": "1h",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(url, json=body)
    except httpx.ConnectError as e:
        log.warning("Ollama unreachable at %s: %s", url, e)
        raise OllamaUnreachable(
            f"Could not reach the chat model service at {url}. "
            f"Make sure Ollama is running and reachable."
        ) from e
    except httpx.ReadTimeout as e:
        log.warning("Ollama timed out after %ss", timeout_s)
        raise OllamaError(
            f"The chat model took too long to respond (>{int(timeout_s)}s)."
        ) from e

    if resp.status_code >= 400:
        log.warning("Ollama returned %s: %s", resp.status_code, resp.text[:500])
        raise OllamaError(f"Chat model returned {resp.status_code}.")

    try:
        data = resp.json()
        return (data.get("message") or {}).get("content", "").strip()
    except Exception as e:  # noqa: BLE001
        raise OllamaError(f"Could not parse chat model response: {e}") from e

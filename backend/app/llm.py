"""OpenAI-compatible chat client. Works with Fireworks AI and an AMD-cloud
vLLM/ROCm endpoint alike — both speak the /chat/completions protocol.

If no endpoint is configured (settings.llm_enabled is False), callers should use
the offline mock path instead; this module only handles real HTTP calls.
"""
import json
from typing import Optional

import httpx

from .config import settings


class LLMError(RuntimeError):
    pass


def chat(
    messages: list[dict],
    *,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    json_mode: bool = False,
    model: Optional[str] = None,
) -> str:
    """Single chat completion. Returns the assistant message content (string)."""
    url = f"{settings.llm_base_url}/chat/completions"
    payload: dict = {
        "model": model or settings.llm_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        # Supported by Fireworks and recent vLLM builds; harmless if ignored.
        payload["response_format"] = {"type": "json_object"}

    headers = {"Content-Type": "application/json"}
    if settings.llm_api_key:
        headers["Authorization"] = f"Bearer {settings.llm_api_key}"

    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=settings.llm_timeout)
    except httpx.HTTPError as exc:
        raise LLMError(f"LLM request failed: {exc}") from exc

    if resp.status_code >= 400:
        raise LLMError(f"LLM returned {resp.status_code}: {resp.text[:500]}")

    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise LLMError(f"Unexpected LLM response shape: {json.dumps(data)[:500]}") from exc

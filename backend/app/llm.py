"""OpenAI-compatible chat client. Works with Fireworks AI and an AMD-cloud
vLLM/ROCm endpoint alike — both speak the /chat/completions protocol.

If no endpoint is configured (settings.llm_enabled is False), callers should use
the offline mock path instead; this module only handles real HTTP calls.
"""
import json
import re
from typing import Optional

import httpx

from .config import settings


class LLMError(RuntimeError):
    pass


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _strip_think(text: str) -> str:
    """Remove Qwen3-style <think>…</think> reasoning blocks from a completion.
    Also handles an unclosed leading <think> (keeps only the final answer)."""
    text = _THINK_RE.sub("", text)
    if "<think>" in text and "</think>" not in text:
        text = text.split("<think>", 1)[0]
    return text.strip()


def _apply_no_think(messages: list[dict]) -> list[dict]:
    """Append Qwen3's `/no_think` soft switch to the last user turn to skip the
    (slow) reasoning phase. Harmless if the model isn't Qwen3-family."""
    msgs = [dict(m) for m in messages]
    for m in reversed(msgs):
        if m.get("role") == "user":
            m["content"] = f"{m.get('content', '')}\n/no_think".strip()
            break
    return msgs


def chat(
    messages: list[dict],
    *,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    json_mode: bool = False,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> str:
    """Single chat completion. Returns the assistant message content (string).
    base_url/api_key/model override the defaults so callers can target a different
    endpoint without a separate client."""
    base = (base_url or settings.llm_base_url).rstrip("/")
    url = f"{base}/chat/completions"
    if settings.llm_no_think:
        messages = _apply_no_think(messages)
    payload: dict = {
        "model": model or settings.llm_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        # Supported by Fireworks and recent vLLM builds; harmless if ignored.
        payload["response_format"] = {"type": "json_object"}

    key = api_key if api_key is not None else settings.llm_api_key
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=settings.llm_timeout)
    except httpx.HTTPError as exc:
        raise LLMError(f"LLM request failed: {exc}") from exc

    if resp.status_code >= 400:
        raise LLMError(f"LLM returned {resp.status_code}: {resp.text[:500]}")

    data = resp.json()
    try:
        return _strip_think(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError) as exc:
        raise LLMError(f"Unexpected LLM response shape: {json.dumps(data)[:500]}") from exc


def embed(text: str, *, model: Optional[str] = None) -> list[float]:
    """Return an embedding vector via the OpenAI-compatible /embeddings endpoint.
    Works with Fireworks, Ollama, and AMD vLLM embedding models."""
    url = f"{settings.llm_base_url}/embeddings"
    payload = {"model": model or settings.llm_embed_model, "input": text}
    headers = {"Content-Type": "application/json"}
    if settings.llm_api_key:
        headers["Authorization"] = f"Bearer {settings.llm_api_key}"
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=settings.llm_timeout)
    except httpx.HTTPError as exc:
        raise LLMError(f"Embedding request failed: {exc}") from exc
    if resp.status_code >= 400:
        raise LLMError(f"Embeddings returned {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    try:
        return data["data"][0]["embedding"]
    except (KeyError, IndexError) as exc:
        raise LLMError(f"Unexpected embeddings response: {json.dumps(data)[:300]}") from exc

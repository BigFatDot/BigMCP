"""Shared LLM client for orchestration-side structured calls.

Centralises the Mistral (OpenAI-compatible) chat call originally duplicated
across `IntentAnalyzer`, `MarketplaceSyncService`, `CatalogCompositionPlanner`
and the legacy `/api/analyze` route. Two entry points:

- `call_llm_json(prompt, system=None, ...)` — returns a parsed dict.
- `call_llm_text(prompt, system=None, ...)` — returns the raw assistant
  content string (for call-sites that do their own extraction).

Config (same env vars the IntentAnalyzer used to read):
- LLM_API_URL   (default https://api.mistral.ai/v1)
- LLM_API_KEY   (required — raises LLMNotConfigured if absent)
- LLM_MODEL     (default mistral-small-latest)
"""

import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class LLMNotConfigured(RuntimeError):
    """Raised when LLM_API_KEY is not set in the environment."""


class LLMCallError(RuntimeError):
    """Raised when the LLM call exhausts retries or returns no usable JSON."""


def _config() -> tuple[str, str, str]:
    return (
        os.environ.get("LLM_API_URL", "https://api.mistral.ai/v1"),
        os.environ.get("LLM_API_KEY", ""),
        os.environ.get("LLM_MODEL", "mistral-small-latest"),
    )


def _chat_url(base: str) -> str:
    """Build the /chat/completions URL, tolerating bases with or without /v1."""
    base = base.rstrip("/")
    if "/v1" in base:
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Best-effort parse of a JSON object from an LLM response.

    Handles three shapes: a raw JSON object, a ```json fenced block, and a
    JSON object embedded in surrounding prose (first balanced {...}).
    """
    if not text:
        return None
    text = text.strip()
    # 1. Direct parse
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    # 2. Fenced ```json ... ```
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        try:
            obj = json.loads(fenced.group(1))
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            pass
    # 3. First balanced object in prose
    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start : i + 1])
                        return obj if isinstance(obj, dict) else None
                    except json.JSONDecodeError:
                        break
    return None


async def call_llm_json(
    prompt: str,
    system: Optional[str] = None,
    *,
    temperature: float = 0.2,
    max_tokens: int = 2000,
    max_retries: int = 3,
    base_delay: float = 2.0,
    timeout: float = 60.0,
) -> Dict[str, Any]:
    """Call the configured LLM and return a parsed JSON object.

    Sends `response_format=json_object` for native JSON mode; if the model
    rejects it (HTTP 400/422), retries once without it and relies on
    `_extract_json`. Retries 429/5xx with exponential backoff.

    Raises LLMNotConfigured if no API key, LLMCallError on exhaustion or
    unparseable output.
    """
    url, key, model = _config()
    if not key:
        raise LLMNotConfigured("LLM_API_KEY is not set — cannot run LLM call")

    chat_url = _chat_url(url)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    use_json_mode = True
    last_error: Optional[str] = None

    async with httpx.AsyncClient(
        timeout=timeout,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    ) as client:
        attempt = 0
        while attempt <= max_retries:
            body: Dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if use_json_mode:
                body["response_format"] = {"type": "json_object"}

            try:
                resp = await client.post(chat_url, json=body)
            except httpx.HTTPError as e:
                last_error = f"transport error: {e}"
                attempt += 1
                if attempt > max_retries:
                    break
                await asyncio.sleep(min(base_delay * (2 ** (attempt - 1)), 30.0))
                continue

            if resp.status_code == 200:
                content = (
                    resp.json()
                    .get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                parsed = _extract_json(content)
                if parsed is not None:
                    return parsed
                last_error = "LLM returned no parseable JSON object"
                # Retry once more; the model may comply on a second pass.
                attempt += 1
                continue

            if resp.status_code in (400, 422) and use_json_mode:
                # Model likely rejected response_format — drop it and retry.
                logger.info("LLM rejected json_object mode, retrying without it")
                use_json_mode = False
                continue

            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = f"LLM API {resp.status_code}"
                attempt += 1
                if attempt > max_retries:
                    break
                retry_after = resp.headers.get("retry-after")
                try:
                    delay = float(retry_after) if retry_after else base_delay * (2 ** (attempt - 1))
                except ValueError:
                    delay = base_delay * (2 ** (attempt - 1))
                await asyncio.sleep(min(delay, 60.0))
                continue

            # Other non-retryable client error.
            last_error = f"LLM API {resp.status_code}: {resp.text[:300]}"
            break

    raise LLMCallError(last_error or "LLM call failed")


async def call_llm_text(
    prompt: str,
    system: Optional[str] = None,
    *,
    temperature: float = 0.2,
    max_tokens: int = 2000,
    max_retries: int = 3,
    base_delay: float = 2.0,
    timeout: float = 60.0,
) -> str:
    """Call the configured LLM and return the raw assistant content string.

    Use this when the caller has its own extraction logic (e.g. it expects
    natural-language output, or it slices markdown fences itself). For a
    parsed JSON object, prefer `call_llm_json`.

    Retries 429/5xx with exponential backoff. Returns the message content as
    a string — empty string if the API replies with an empty completion.

    Raises LLMNotConfigured if no API key, LLMCallError on retry exhaustion.
    """
    url, key, model = _config()
    if not key:
        raise LLMNotConfigured("LLM_API_KEY is not set — cannot run LLM call")

    chat_url = _chat_url(url)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    last_error: Optional[str] = None

    async with httpx.AsyncClient(
        timeout=timeout,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    ) as client:
        attempt = 0
        while attempt <= max_retries:
            body: Dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            try:
                resp = await client.post(chat_url, json=body)
            except httpx.HTTPError as e:
                last_error = f"transport error: {e}"
                attempt += 1
                if attempt > max_retries:
                    break
                await asyncio.sleep(min(base_delay * (2 ** (attempt - 1)), 30.0))
                continue

            if resp.status_code == 200:
                content = (
                    resp.json()
                    .get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                return content or ""

            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = f"LLM API {resp.status_code}"
                attempt += 1
                if attempt > max_retries:
                    break
                retry_after = resp.headers.get("retry-after")
                try:
                    delay = float(retry_after) if retry_after else base_delay * (2 ** (attempt - 1))
                except ValueError:
                    delay = base_delay * (2 ** (attempt - 1))
                await asyncio.sleep(min(delay, 60.0))
                continue

            # Other non-retryable client error.
            last_error = f"LLM API {resp.status_code}: {resp.text[:300]}"
            break

    raise LLMCallError(last_error or "LLM call failed")

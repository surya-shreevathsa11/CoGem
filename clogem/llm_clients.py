from __future__ import annotations

import asyncio
import mimetypes
import os
import random
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from clogem.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class LLMResult:
    text: str
    error: str
    returncode: int


def _llm_max_retries() -> int:
    raw = (
        os.environ.get("CLOGEM_LLM_MAX_RETRIES")
        or os.environ.get("COGEM_LLM_MAX_RETRIES")
        or "3"
    )
    try:
        return max(0, int(raw))
    except ValueError:
        return 3


def _is_retryable_error(exc: Exception) -> bool:
    name = exc.__class__.__name__.lower()
    if any(
        key in name
        for key in (
            "ratelimit",
            "timeout",
            "internalserver",
            "serviceunavailable",
            "apiconnection",
            "temporarilyunavailable",
        )
    ):
        return True
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int) and status_code in (408, 409, 425, 429, 500, 502, 503, 504):
        return True
    text = str(exc).lower()
    return any(
        needle in text
        for needle in (
            "rate limit",
            "too many requests",
            "timed out",
            "timeout",
            "temporarily unavailable",
            "connection reset",
            "connection aborted",
            "internal server error",
            "service unavailable",
            "gateway timeout",
        )
    )


def _retry_sleep_seconds(attempt: int) -> float:
    # Exponential backoff with jitter.
    return float((2 ** attempt) + random.uniform(0.0, 1.0))


def _run_with_retries(fn: Callable[[], LLMResult], op_name: str) -> LLMResult:
    max_retries = _llm_max_retries()
    for attempt in range(max_retries + 1):
        res = fn()
        if res.returncode == 0:
            return res
        err = Exception(res.error or "unknown error")
        if attempt >= max_retries or not _is_retryable_error(err):
            return res
        wait_s = _retry_sleep_seconds(attempt)
        logger.debug(
            "%s failed with retryable error; retrying in %.2fs (attempt %d/%d): %s",
            op_name,
            wait_s,
            attempt + 1,
            max_retries,
            res.error,
        )
        time.sleep(wait_s)
    return LLMResult("", "retry loop exhausted", 1)


async def _run_with_retries_async(
    fn: Callable[[], Awaitable[LLMResult]], op_name: str
) -> LLMResult:
    max_retries = _llm_max_retries()
    for attempt in range(max_retries + 1):
        res = await fn()
        if res.returncode == 0:
            return res
        err = Exception(res.error or "unknown error")
        if attempt >= max_retries or not _is_retryable_error(err):
            return res
        wait_s = _retry_sleep_seconds(attempt)
        logger.debug(
            "%s failed with retryable error; retrying in %.2fs (attempt %d/%d): %s",
            op_name,
            wait_s,
            attempt + 1,
            max_retries,
            res.error,
        )
        await asyncio.sleep(wait_s)
    return LLMResult("", "retry loop exhausted", 1)


def openai_generate(prompt: str, model: str, timeout_sec: Optional[int] = None) -> LLMResult:
    try:
        from openai import OpenAI
    except Exception as e:
        logger.debug("OpenAI SDK import failed", exc_info=True)
        return LLMResult("", f"OpenAI SDK import failed: {e}", 1)
    def _once() -> LLMResult:
        try:
            client = OpenAI()
            rsp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a precise coding assistant."},
                    {"role": "user", "content": prompt},
                ],
                timeout=timeout_sec or 60,
            )
            text = ""
            try:
                text = (rsp.choices[0].message.content or "").strip()
            except Exception:
                logger.debug("OpenAI response content extraction failed", exc_info=True)
                text = ""
            if not text:
                text = str(rsp)
            return LLMResult(text, "", 0)
        except Exception as e:
            return LLMResult("", str(e), 1)

    return _run_with_retries(_once, "openai_generate")


def gemini_generate(prompt: str, model: str, timeout_sec: Optional[int] = None) -> LLMResult:
    try:
        from google import genai
    except Exception as e:
        logger.debug("Google GenAI SDK import failed", exc_info=True)
        return LLMResult("", f"Google GenAI SDK import failed: {e}", 1)
    def _once() -> LLMResult:
        try:
            client = genai.Client()
            rsp = client.models.generate_content(
                model=model,
                contents=prompt,
                config={"http_options": {"timeout": (timeout_sec or 60) * 1000}},
            )
            text = (getattr(rsp, "text", None) or "").strip()
            if not text:
                text = str(rsp)
            return LLMResult(text, "", 0)
        except Exception as e:
            return LLMResult("", str(e), 1)

    return _run_with_retries(_once, "gemini_generate")


async def openai_generate_async(
    prompt: str, model: str, timeout_sec: Optional[int] = None
) -> LLMResult:
    try:
        from openai import AsyncOpenAI
    except Exception as e:
        return LLMResult("", f"OpenAI SDK import failed: {e}", 1)
    async def _once() -> LLMResult:
        try:
            client = AsyncOpenAI()
            rsp = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a precise coding assistant."},
                    {"role": "user", "content": prompt},
                ],
                timeout=timeout_sec or 60,
            )
            text = ""
            try:
                text = (rsp.choices[0].message.content or "").strip()
            except Exception:
                text = ""
            if not text:
                text = str(rsp)
            return LLMResult(text, "", 0)
        except Exception as e:
            return LLMResult("", str(e), 1)

    return await _run_with_retries_async(_once, "openai_generate_async")


async def gemini_generate_async(
    prompt: str, model: str, timeout_sec: Optional[int] = None
) -> LLMResult:
    try:
        from google import genai
    except Exception as e:
        return LLMResult("", f"Google GenAI SDK import failed: {e}", 1)
    async def _once() -> LLMResult:
        try:
            client = genai.Client()
            rsp = await client.aio.models.generate_content(
                model=model,
                contents=prompt,
                config={"http_options": {"timeout": (timeout_sec or 60) * 1000}},
            )
            text = (getattr(rsp, "text", None) or "").strip()
            if not text:
                text = str(rsp)
            return LLMResult(text, "", 0)
        except Exception as e:
            return LLMResult("", str(e), 1)

    return await _run_with_retries_async(_once, "gemini_generate_async")


def gemini_generate_with_google_search(
    prompt: str, model: str, timeout_sec: Optional[int] = None
) -> LLMResult:
    """
    Gemini with Grounding with Google Search (live web). Requires google-genai SDK.
    See: https://ai.google.dev/gemini-api/docs/google-search
    """
    try:
        from google import genai
        from google.genai import types
    except Exception as e:
        return LLMResult("", f"Google GenAI SDK import failed: {e}", 1)
    def _once() -> LLMResult:
        try:
            client = genai.Client()
            grounding_tool = types.Tool(google_search=types.GoogleSearch())
            timeout_ms = int((timeout_sec or 120) * 1000)
            cfg = types.GenerateContentConfig(
                tools=[grounding_tool],
                http_options=types.HttpOptions(timeout=timeout_ms),
            )
            rsp = client.models.generate_content(
                model=model,
                contents=prompt,
                config=cfg,
            )
            text = (getattr(rsp, "text", None) or "").strip()
            if not text:
                text = str(rsp)
            return LLMResult(text, "", 0)
        except Exception as e:
            return LLMResult("", str(e), 1)

    return _run_with_retries(_once, "gemini_generate_with_google_search")


async def gemini_generate_with_google_search_async(
    prompt: str, model: str, timeout_sec: Optional[int] = None
) -> LLMResult:
    try:
        from google import genai
        from google.genai import types
    except Exception as e:
        return LLMResult("", f"Google GenAI SDK import failed: {e}", 1)
    async def _once() -> LLMResult:
        try:
            client = genai.Client()
            grounding_tool = types.Tool(google_search=types.GoogleSearch())
            timeout_ms = int((timeout_sec or 120) * 1000)
            cfg = types.GenerateContentConfig(
                tools=[grounding_tool],
                http_options=types.HttpOptions(timeout=timeout_ms),
            )
            rsp = await client.aio.models.generate_content(
                model=model,
                contents=prompt,
                config=cfg,
            )
            text = (getattr(rsp, "text", None) or "").strip()
            if not text:
                text = str(rsp)
            return LLMResult(text, "", 0)
        except Exception as e:
            return LLMResult("", str(e), 1)

    return await _run_with_retries_async(
        _once, "gemini_generate_with_google_search_async"
    )


def claude_generate(prompt: str, model: str, timeout_sec: Optional[int] = None) -> LLMResult:
    try:
        from anthropic import Anthropic
    except Exception as e:
        return LLMResult("", f"Anthropic SDK import failed: {e}", 1)
    def _once() -> LLMResult:
        try:
            client = Anthropic()
            rsp = client.messages.create(
                model=model,
                max_tokens=4096,
                system="You are a precise coding assistant.",
                messages=[{"role": "user", "content": prompt}],
                timeout=timeout_sec or 60,
            )
            text = ""
            try:
                parts = getattr(rsp, "content", None) or []
                text_parts = []
                for p in parts:
                    t = getattr(p, "text", None)
                    if t:
                        text_parts.append(str(t))
                text = "\n".join(text_parts).strip()
            except Exception:
                text = ""
            if not text:
                text = str(rsp)
            return LLMResult(text, "", 0)
        except Exception as e:
            return LLMResult("", str(e), 1)

    return _run_with_retries(_once, "claude_generate")


async def claude_generate_async(
    prompt: str, model: str, timeout_sec: Optional[int] = None
) -> LLMResult:
    return await _run_with_retries_async(
        lambda: asyncio.to_thread(claude_generate, prompt, model, timeout_sec),
        "claude_generate_async",
    )


def _guess_mime_type_for_image_path(image_path: str) -> str:
    """
    Infer MIME type from image path extension.
    Defaults to PNG for unknown/unmapped extensions to preserve prior behavior.
    """
    mime, _enc = mimetypes.guess_type(image_path)
    if not mime:
        return "image/png"
    return mime


def gemini_generate_with_image(
    prompt: str,
    model: str,
    image_path: str,
    timeout_sec: Optional[int] = None,
) -> LLMResult:
    try:
        from google import genai
        from google.genai import types
    except Exception as e:
        return LLMResult("", f"Google GenAI SDK import failed: {e}", 1)
    def _once() -> LLMResult:
        try:
            with open(image_path, "rb") as f:
                img = f.read()
            client = genai.Client()
            mime_type = _guess_mime_type_for_image_path(image_path)
            rsp = client.models.generate_content(
                model=model,
                contents=[
                    prompt,
                    types.Part.from_bytes(data=img, mime_type=mime_type),
                ],
                config={"http_options": {"timeout": (timeout_sec or 60) * 1000}},
            )
            text = (getattr(rsp, "text", None) or "").strip()
            if not text:
                text = str(rsp)
            return LLMResult(text, "", 0)
        except Exception as e:
            return LLMResult("", str(e), 1)

    return _run_with_retries(_once, "gemini_generate_with_image")


async def gemini_generate_with_image_async(
    prompt: str,
    model: str,
    image_path: str,
    timeout_sec: Optional[int] = None,
) -> LLMResult:
    try:
        from google import genai
        from google.genai import types
    except Exception as e:
        return LLMResult("", f"Google GenAI SDK import failed: {e}", 1)
    async def _once() -> LLMResult:
        try:
            with open(image_path, "rb") as f:
                img = f.read()
            client = genai.Client()
            rsp = await client.aio.models.generate_content(
                model=model,
                contents=[
                    prompt,
                    types.Part.from_bytes(
                        data=img, mime_type=_guess_mime_type_for_image_path(image_path)
                    ),
                ],
                config={"http_options": {"timeout": (timeout_sec or 60) * 1000}},
            )
            text = (getattr(rsp, "text", None) or "").strip()
            if not text:
                text = str(rsp)
            return LLMResult(text, "", 0)
        except Exception as e:
            return LLMResult("", str(e), 1)

    return await _run_with_retries_async(_once, "gemini_generate_with_image_async")


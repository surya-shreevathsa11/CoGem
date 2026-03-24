from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMResult:
    text: str
    error: str
    returncode: int


def openai_generate(prompt: str, model: str, timeout_sec: Optional[int] = None) -> LLMResult:
    try:
        from openai import OpenAI
    except Exception as e:
        return LLMResult("", f"OpenAI SDK import failed: {e}", 1)
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
            text = ""
        if not text:
            text = str(rsp)
        return LLMResult(text, "", 0)
    except Exception as e:
        return LLMResult("", str(e), 1)


def gemini_generate(prompt: str, model: str, timeout_sec: Optional[int] = None) -> LLMResult:
    try:
        from google import genai
    except Exception as e:
        return LLMResult("", f"Google GenAI SDK import failed: {e}", 1)
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


async def openai_generate_async(
    prompt: str, model: str, timeout_sec: Optional[int] = None
) -> LLMResult:
    return await asyncio.to_thread(openai_generate, prompt, model, timeout_sec)


async def gemini_generate_async(
    prompt: str, model: str, timeout_sec: Optional[int] = None
) -> LLMResult:
    return await asyncio.to_thread(gemini_generate, prompt, model, timeout_sec)


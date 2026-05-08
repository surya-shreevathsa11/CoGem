from __future__ import annotations

import asyncio
from types import SimpleNamespace


def test_openai_generate_async_uses_async_client(monkeypatch):
    class _AsyncCompletions:
        async def create(self, **kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="OK-ASYNC"))]
            )

    class _AsyncChat:
        completions = _AsyncCompletions()

    class _AsyncOpenAI:
        def __init__(self):
            self.chat = _AsyncChat()

    import openai

    monkeypatch.setattr(openai, "AsyncOpenAI", _AsyncOpenAI)

    from clogem.llm_clients import openai_generate_async

    r = asyncio.run(openai_generate_async("q", "gpt-4.1-mini", timeout_sec=30))
    assert r.returncode == 0
    assert r.text == "OK-ASYNC"


def test_gemini_generate_async_uses_native_aio(monkeypatch):
    class _AioModels:
        async def generate_content(self, **kwargs):
            return SimpleNamespace(text="GEMINI-ASYNC")

    class _Client:
        def __init__(self):
            self.aio = SimpleNamespace(models=_AioModels())

    import google.genai

    monkeypatch.setattr(google.genai, "Client", lambda *a, **k: _Client())

    from clogem.llm_clients import gemini_generate_async

    r = asyncio.run(gemini_generate_async("q", "gemini-2.5-flash", timeout_sec=30))
    assert r.returncode == 0
    assert r.text == "GEMINI-ASYNC"

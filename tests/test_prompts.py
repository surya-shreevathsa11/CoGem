from __future__ import annotations

from clogem.prompts import build_gemini_review_prompt, build_router_prompt


def test_build_router_prompt_injects_memory_and_task() -> None:
    p = build_router_prompt("do work", "mem text")
    assert "mem text" in p
    assert "do work" in p


def test_build_gemini_review_prompt_injects_context_and_code() -> None:
    p = build_gemini_review_prompt("ctx", "code")
    assert "ctx" in p
    assert "code" in p

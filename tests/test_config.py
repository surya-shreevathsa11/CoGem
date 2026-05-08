from __future__ import annotations

from clogem.config import Settings


def test_settings_from_env_parses_booleans_and_ints(monkeypatch) -> None:
    monkeypatch.setenv("CLOGEM_ASYNC_LLM", "0")
    monkeypatch.setenv("CLOGEM_MCP_TIMEOUT_SEC", "77")
    monkeypatch.setenv("CLOGEM_VECTOR_RAG", "1")
    s = Settings.from_env()
    assert s.async_llm is False
    assert s.mcp_timeout_sec == 77
    assert s.vector_rag is True


def test_settings_choice_fallback(monkeypatch) -> None:
    monkeypatch.setenv("CLOGEM_CODEX_BACKEND", "invalid")
    s = Settings.from_env()
    assert s.codex_backend == "auto"

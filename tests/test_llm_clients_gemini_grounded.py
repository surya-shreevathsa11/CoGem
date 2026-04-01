from __future__ import annotations

from unittest.mock import MagicMock


def test_gemini_generate_with_google_search_uses_client(monkeypatch):
    mock_client = MagicMock()
    mock_rsp = MagicMock()
    mock_rsp.text = "Grounded answer"
    mock_client.models.generate_content.return_value = mock_rsp

    import google.genai

    monkeypatch.setattr(google.genai, "Client", lambda *a, **k: mock_client)

    from clogem.llm_clients import gemini_generate_with_google_search

    r = gemini_generate_with_google_search("q", "gemini-2.5-flash", timeout_sec=30)
    assert r.returncode == 0
    assert r.text == "Grounded answer"
    mock_client.models.generate_content.assert_called_once()
    call_kw = mock_client.models.generate_content.call_args.kwargs
    assert "config" in call_kw
    cfg = call_kw["config"]
    assert cfg.tools and len(cfg.tools) == 1

from __future__ import annotations

from clogem.logging_utils import debug_enabled


def test_debug_enabled_from_clogem_env(monkeypatch) -> None:
    monkeypatch.setenv("CLOGEM_DEBUG", "1")
    monkeypatch.delenv("COGEM_DEBUG", raising=False)
    assert debug_enabled() is True


def test_debug_enabled_from_legacy_cogem_env(monkeypatch) -> None:
    monkeypatch.delenv("CLOGEM_DEBUG", raising=False)
    monkeypatch.setenv("COGEM_DEBUG", "true")
    assert debug_enabled() is True

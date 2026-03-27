from __future__ import annotations

import types

from clogem.services import pipeline


def test_copy_to_clipboard_empty_text_returns_false() -> None:
    assert pipeline._copy_to_clipboard("   ") is False


def test_copy_to_clipboard_uses_pyperclip_when_available(monkeypatch) -> None:
    calls: list[str] = []

    fake_module = types.SimpleNamespace(copy=lambda text: calls.append(text))
    monkeypatch.setitem(__import__("sys").modules, "pyperclip", fake_module)

    assert pipeline._copy_to_clipboard("hello") is True
    assert calls == ["hello"]


def test_copy_to_clipboard_falls_back_to_windows_clip(monkeypatch) -> None:
    monkeypatch.delitem(__import__("sys").modules, "pyperclip", raising=False)

    def fail_import(name, *args, **kwargs):
        if name == "pyperclip":
            raise ImportError("no pyperclip")
        return original_import(name, *args, **kwargs)

    original_import = __import__("builtins").__import__
    monkeypatch.setattr(__import__("builtins"), "__import__", fail_import)
    monkeypatch.setattr(pipeline.sys, "platform", "win32")
    monkeypatch.setattr(pipeline.shutil, "which", lambda cmd: "ok" if cmd == "clip" else None)

    def fake_run(cmd, input, text, capture_output, check):
        assert cmd == ["clip"]
        assert input == "copied text"
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)

    assert pipeline._copy_to_clipboard("copied text") is True


def test_copy_to_clipboard_returns_false_when_all_backends_fail(monkeypatch) -> None:
    monkeypatch.delitem(__import__("sys").modules, "pyperclip", raising=False)

    def fail_import(name, *args, **kwargs):
        if name in ("pyperclip", "tkinter"):
            raise ImportError(name)
        return original_import(name, *args, **kwargs)

    original_import = __import__("builtins").__import__
    monkeypatch.setattr(__import__("builtins"), "__import__", fail_import)
    monkeypatch.setattr(pipeline.sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(pipeline.shutil, "which", lambda _cmd: None)

    assert pipeline._copy_to_clipboard("x") is False

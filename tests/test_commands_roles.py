from __future__ import annotations

from clogem.services.commands import handle_pre_pipeline_command


class _FakeConsole:
    def __init__(self, input_value: str = "") -> None:
        self.lines: list[str] = []
        self.input_value = input_value

    def print(self, *args, **kwargs):  # noqa: ANN002, ANN003
        self.lines.append(" ".join(str(a) for a in args))

    def input(self, _prompt: str) -> str:
        return self.input_value


def _ctx(console: _FakeConsole, role_provider_map: dict[str, str]):
    return {
        "console": console,
        "Text": lambda t, style=None: t,
        "MUTED": "muted",
        "TITLE": "title",
        "LOG_WARN": "warn",
        "LOG_ERR": "err",
        "LOG_OK": "ok",
        "section_rule": lambda *_: None,
        "role_provider_map": role_provider_map,
    }


def test_roles_subcommand_sets_orchestrator_and_prompts_for_claude_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    console = _FakeConsole(input_value="sk-ant-test")
    role_map = {"orchestrator": "codex"}

    handled, should_exit = handle_pre_pipeline_command(
        "/roles/orchestrator/claude",
        _ctx(console, role_map),
    )

    assert handled is True
    assert should_exit is False
    assert role_map["orchestrator"] == "claude"
    assert "ANTHROPIC_API_KEY set for this session." in "\n".join(console.lines)


def test_roles_subcommand_supports_cover_alias(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "already-set")
    console = _FakeConsole()
    role_map = {"coder": "codex"}

    handled, should_exit = handle_pre_pipeline_command(
        "/roles/cover/claude",
        _ctx(console, role_map),
    )

    assert handled is True
    assert should_exit is False
    assert role_map["coder"] == "claude"


def test_roles_subcommand_rejects_unknown_role():
    console = _FakeConsole()
    role_map = {"coder": "codex"}

    handled, should_exit = handle_pre_pipeline_command(
        "/roles/unknown/claude",
        _ctx(console, role_map),
    )

    assert handled is True
    assert should_exit is False
    assert role_map["coder"] == "codex"
    assert "Unknown role." in "\n".join(console.lines)

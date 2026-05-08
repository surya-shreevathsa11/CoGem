from __future__ import annotations

from clogem.services.contracts import CommandContext
from clogem.services.commands import handle_pre_pipeline_command


class _FakeConsole:
    def __init__(self, input_value: str = "") -> None:
        self.lines: list[str] = []
        self.input_value = input_value

    def print(self, *args, **kwargs):  # noqa: ANN002, ANN003
        self.lines.append(" ".join(str(a) for a in args))

    def input(self, _prompt: str) -> str:
        return self.input_value


def _ctx(console: _FakeConsole, role_provider_map: dict[str, str]) -> CommandContext:
    return CommandContext(
        console=console,
        Text=lambda t, style=None: t,
        MUTED="muted",
        TITLE="title",
        LOG_WARN="warn",
        LOG_ERR="err",
        LOG_OK="ok",
        section_rule=lambda *_: None,
        models={"codex": None, "gemini": None, "claude": None},
        _codex_model=None,
        _gemini_model=None,
        _claude_model=None,
        role_provider_map=role_provider_map,
        settings=None,
        _repo_root=lambda: ".",
        _select_test_cmd=lambda: None,
        _select_lint_cmd=lambda: None,
        _run_local_command=lambda *_: (0, "", ""),
        _parse_github_repo_ref=lambda *_: ("", "", ""),
        _github_repo_info=lambda *_: "",
        ensure_run_permissions=lambda: None,
        run_permissions={},
        _run_with_ascii_progress=lambda *_: None,
        _run_proc=lambda *args, **kwargs: None,
        _shlex_split_cmd=lambda s: s.split(),
        _mention_roots_list=lambda: [],
        _resolve_mention_path=lambda *_: None,
        _path_allowed_for_mention=lambda *_: False,
        _read_file_for_mention=lambda *_: "",
    )


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


def test_config_command_prints_settings_json():
    class _Settings:
        def as_dict(self):
            return {"async_llm": True, "mcp_timeout_sec": 60}

    console = _FakeConsole()
    ctx = _ctx(console, {"coder": "codex"})
    ctx.settings = _Settings()
    handled, should_exit = handle_pre_pipeline_command("/config", ctx)
    assert handled is True
    assert should_exit is False
    joined = "\n".join(console.lines)
    assert "async_llm" in joined

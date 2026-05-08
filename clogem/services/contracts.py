from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional, Protocol, Tuple


class ConsoleLike(Protocol):
    def print(self, *args: Any, **kwargs: Any) -> None: ...


TextFactory = Callable[[str], Any]


@dataclass(frozen=True)
class TurnModeRequest:
    session_directive: Optional[str]
    task_clean: str
    mem_block: str
    router_hint: str


@dataclass(frozen=True)
class TurnModeDeps:
    build_router_prompt: Callable[[str, str, str], str]
    run_codex: Callable[[str, str], Awaitable[Tuple[str, str, int]]]
    runtime_stitch_capabilities_block: Callable[[], str]
    runtime_clogem_commands_capabilities_block: Callable[[], str]
    detect_stitch_frontend_heavy_task: Callable[[str], bool]
    detect_prerequisite_first_task: Callable[[str], bool]
    build_prerequisite_first_prompt: Callable[[str, str], str]
    secondary_intent_classifier: Optional[
        Callable[[str, str], Awaitable[Optional[str]]]
    ] = None


@dataclass(frozen=True)
class TurnModeUI:
    trace_doing: Callable[[str], None]
    trace_done: Callable[[str], None]
    say: Callable[[str], None]
    console: ConsoleLike
    text_factory: TextFactory
    log_err_style: str
    muted_style: str
    token_turn_footer: Callable[[], None]


@dataclass(frozen=True)
class TurnModeResult:
    stop_turn: bool
    mode: Optional[str]
    chat_reply: Optional[str]


@dataclass(frozen=True)
class StitchStageRequest:
    task_clean: str
    task_raw: str
    mode: str
    session_directive: Optional[str]
    stitch_feature_on: bool
    stitch_website_rules: str
    attach_block: str


@dataclass(frozen=True)
class StitchStageDeps:
    read_task_line: Callable[[str], Any]
    expand_at_mentions: Callable[[str], Tuple[str, str]]
    looks_like_ui_content: Callable[[str], bool]


@dataclass(frozen=True)
class StitchStageUI:
    trace_done: Callable[[str], None]
    trace_doing: Callable[[str], None]
    section_rule: Callable[[str], None]
    console: ConsoleLike
    text_factory: TextFactory
    muted_style: str


@dataclass(frozen=True)
class StitchStageResult:
    stitch_block: str
    stitch_rules_extra: str
    stitch_frontend_heavy: bool
    frontend_detected: bool


@dataclass
class CommandContext:
    console: ConsoleLike
    Text: Callable[[str, Any], Any]
    MUTED: str
    TITLE: str
    LOG_WARN: str
    LOG_ERR: str
    LOG_OK: str
    section_rule: Callable[[str], None]
    models: Dict[str, Optional[str]]
    _codex_model: Optional[str]
    _gemini_model: Optional[str]
    _claude_model: Optional[str]
    role_provider_map: Dict[str, str]
    settings: Any
    _repo_root: Callable[[], str]
    _select_test_cmd: Callable[[], Optional[str]]
    _select_lint_cmd: Callable[[], Optional[str]]
    _run_local_command: Callable[[str, str], Tuple[int, str, str]]
    _parse_github_repo_ref: Callable[[str], Tuple[str, str, str]]
    _github_repo_info: Callable[[str, str], str]
    ensure_run_permissions: Callable[[], None]
    run_permissions: Dict[str, Any]
    _run_with_ascii_progress: Callable[[str, Callable[[], Any]], Any]
    _run_proc: Callable[..., Any]
    _shlex_split_cmd: Callable[[str], Any]
    _mention_roots_list: Callable[[], Any]
    _resolve_mention_path: Callable[[str], Optional[str]]
    _path_allowed_for_mention: Callable[[str, Any], bool]
    _read_file_for_mention: Callable[[str], str]

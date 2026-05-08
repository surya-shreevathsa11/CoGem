from __future__ import annotations

import asyncio

from clogem.services.contracts import (
    TurnModeDeps,
    TurnModeRequest,
    TurnModeResult,
    TurnModeUI,
)
from clogem.services.routing import parse_build_or_chat, parse_session_directive, resolve_turn_mode


def test_parse_session_directive_extracts_build() -> None:
    rest, directive = parse_session_directive("/build implement feature")
    assert directive == "build"
    assert rest == "implement feature"


def test_parse_session_directive_extracts_research() -> None:
    rest, directive = parse_session_directive("/research what is CRISPR?")
    assert directive == "research"
    assert rest == "what is CRISPR?"


def test_parse_build_or_chat_defaults_to_workflow() -> None:
    mode, reply = parse_build_or_chat("Please add logging")
    assert mode == "workflow"
    assert reply is None


def test_parse_build_or_chat_chat_with_body() -> None:
    mode, reply = parse_build_or_chat("CHAT Sure, here is the answer")
    assert mode == "chat"
    assert reply == "Sure, here is the answer"


def test_resolve_turn_mode_build_directive_skips_router() -> None:
    calls: list[str] = []

    async def run_codex(_prompt, _label):
        calls.append("run")
        return "", "", 0

    async def run() -> TurnModeResult:
        return await resolve_turn_mode(
            TurnModeRequest(
                session_directive="build",
                task_clean="build this",
                mem_block="",
                router_hint="",
            ),
            TurnModeDeps(
                build_router_prompt=lambda *_: "router prompt",
                run_codex=run_codex,
                runtime_stitch_capabilities_block=lambda: "",
                runtime_clogem_commands_capabilities_block=lambda: "",
                detect_stitch_frontend_heavy_task=lambda *_: False,
                detect_prerequisite_first_task=lambda *_: False,
                build_prerequisite_first_prompt=lambda *_: "",
                secondary_intent_classifier=None,
            ),
            TurnModeUI(
                trace_doing=lambda *_: None,
                trace_done=lambda *_: None,
                say=lambda *_: None,
                console=type("C", (), {"print": lambda *args, **kwargs: None})(),
                text_factory=lambda t, style=None: t,
                log_err_style="err",
                muted_style="muted",
                token_turn_footer=lambda: None,
            ),
        )

    out = asyncio.run(run())
    assert out == TurnModeResult(stop_turn=False, mode="workflow", chat_reply=None)
    assert calls == []


def test_resolve_turn_mode_router_failure_stops_turn() -> None:
    said: list[str] = []

    async def run_codex(_prompt, _label):
        return "", "router failed", 1

    async def run() -> TurnModeResult:
        return await resolve_turn_mode(
            TurnModeRequest(
                session_directive=None,
                task_clean="hello",
                mem_block="",
                router_hint="",
            ),
            TurnModeDeps(
                build_router_prompt=lambda *_: "router prompt",
                run_codex=run_codex,
                runtime_stitch_capabilities_block=lambda: "",
                runtime_clogem_commands_capabilities_block=lambda: "",
                detect_stitch_frontend_heavy_task=lambda *_: False,
                detect_prerequisite_first_task=lambda *_: False,
                build_prerequisite_first_prompt=lambda *_: "",
                secondary_intent_classifier=None,
            ),
            TurnModeUI(
                trace_doing=lambda *_: None,
                trace_done=lambda *_: None,
                say=lambda msg: said.append(msg),
                console=type("C", (), {"print": lambda *args, **kwargs: None})(),
                text_factory=lambda t, style=None: t,
                log_err_style="err",
                muted_style="muted",
                token_turn_footer=lambda: None,
            ),
        )

    out = asyncio.run(run())
    assert out == TurnModeResult(stop_turn=True, mode=None, chat_reply=None)
    assert said


def test_resolve_turn_mode_prerequisite_path_returns_chat() -> None:
    calls: list[str] = []

    async def run_codex(_prompt, _label):
        calls.append(_label)
        if len(calls) == 1:
            return "BUILD", "", 0
        return "Prerequisite answer", "", 0

    async def run() -> TurnModeResult:
        return await resolve_turn_mode(
            TurnModeRequest(
                session_directive=None,
                task_clean="before coding explain plan",
                mem_block="mem",
                router_hint="",
            ),
            TurnModeDeps(
                build_router_prompt=lambda *_: "router prompt",
                run_codex=run_codex,
                runtime_stitch_capabilities_block=lambda: "",
                runtime_clogem_commands_capabilities_block=lambda: "",
                detect_stitch_frontend_heavy_task=lambda *_: False,
                detect_prerequisite_first_task=lambda *_: True,
                build_prerequisite_first_prompt=lambda *_: "prereq prompt",
                secondary_intent_classifier=None,
            ),
            TurnModeUI(
                trace_doing=lambda *_: None,
                trace_done=lambda *_: None,
                say=lambda *_: None,
                console=type("C", (), {"print": lambda *args, **kwargs: None})(),
                text_factory=lambda t, style=None: t,
                log_err_style="err",
                muted_style="muted",
                token_turn_footer=lambda: None,
            ),
        )

    out = asyncio.run(run())
    assert out == TurnModeResult(
        stop_turn=False,
        mode="chat",
        chat_reply="Prerequisite answer",
    )
    assert len(calls) == 2

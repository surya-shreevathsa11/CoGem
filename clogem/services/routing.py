from __future__ import annotations

import re
from typing import Optional, Tuple

from clogem.services.contracts import (
    TurnModeDeps,
    TurnModeRequest,
    TurnModeResult,
    TurnModeUI,
)

_SESSION_DIRECTIVE = re.compile(
    r"^/(build|plan|debug|agent|ask|research)(?:\s+|$)(.*)$",
    re.I | re.DOTALL,
)


def parse_session_directive(raw: str) -> Tuple[str, Optional[str]]:
    """Strip one leading /build /plan /debug /agent /ask /research; return (rest, directive name or None)."""
    s = raw.strip()
    m = _SESSION_DIRECTIVE.match(s)
    if not m:
        return raw, None
    name = m.group(1).lower()
    rest = (m.group(2) or "").strip()
    return rest, name


def parse_build_or_chat(raw: str):
    """Return ('workflow', None) or ('chat', reply_text)."""
    text = raw.lstrip("\ufeff").strip()
    lines = text.splitlines()

    def first_route_word(line: str) -> str:
        s = re.sub(r"[*_`#]", "", line).strip()
        if not s:
            return ""
        parts = s.split(None, 1)
        return parts[0].upper().strip(".,:;!?\"'`")

    for i, line in enumerate(lines):
        w = first_route_word(line)
        if not w:
            continue
        if w == "BUILD":
            return "workflow", None
        if w == "CHAT":
            s = re.sub(r"[*_`#]", "", line).strip()
            tokens = s.split(None, 1)
            same_line = tokens[1].strip() if len(tokens) > 1 else ""
            following = "\n".join(lines[i + 1 :]).strip()
            parts = [p for p in (same_line, following) if p]
            rest = "\n".join(parts).strip()
            if not rest:
                rest = (
                    "I'm Clogem: when you describe something to build or code to change, "
                    "I'll run the full loop. What would you like to work on?"
                )
            return "chat", rest
    return "workflow", None


async def resolve_turn_mode(
    request: TurnModeRequest,
    deps: TurnModeDeps,
    ui: TurnModeUI,
) -> TurnModeResult:
    if request.session_directive == "build":
        ui.trace_done(
            "Directive /build: skipping classifier; running the full build pipeline."
        )
        mode = "workflow"
        chat_reply = None
    else:
        ui.trace_doing(
            "I'm having Codex classify this turn: full build pipeline versus a direct conversational reply (using your text and saved context)."
        )
        router_raw, router_err, router_rc = await deps.run_codex(
            deps.build_router_prompt(
                request.task_clean,
                request.mem_block
                + deps.runtime_stitch_capabilities_block()
                + deps.runtime_clogem_commands_capabilities_block(),
                request.router_hint,
            ),
            "Codex: routing (build vs conversation)...",
        )
        if router_rc != 0:
            ui.trace_done(
                "Routing failed; not guessing BUILD/CHAT. Fix the error below, then retry."
            )
            ui.console.print()
            ui.say(f"[clogem] ERROR: Codex routing exited with code {router_rc}.")
            if (router_err or "").strip():
                clip = (router_err or "").strip()[:1200]
                if len((router_err or "").strip()) > 1200:
                    clip += "..."
                ui.console.print(ui.text_factory(clip, style=ui.log_err_style))
            ui.console.print(
                ui.text_factory(
                    "Hint: clogem runs `codex exec --skip-git-repo-check`. "
                    "If this persists, check `codex` on PATH and disk permissions.",
                    style=ui.muted_style,
                )
            )
            ui.console.print()
            ui.token_turn_footer()
            return TurnModeResult(stop_turn=True, mode=None, chat_reply=None)
        mode, chat_reply = parse_build_or_chat(router_raw)
        stitch_heavy_for_routing = deps.detect_stitch_frontend_heavy_task(
            request.task_clean
        )
        if mode == "chat" and not deps.detect_prerequisite_first_task(request.task_clean):
            # Secondary lightweight classifier call replaces hardcoded heuristics.
            llm_route = None
            if deps.secondary_intent_classifier is not None:
                try:
                    llm_route = await deps.secondary_intent_classifier(
                        request.task_clean, request.mem_block
                    )
                except Exception:
                    llm_route = None
            if (llm_route or "").strip().upper() == "BUILD" or stitch_heavy_for_routing:
                mode = "workflow"
                chat_reply = None

    if (
        mode == "workflow"
        and deps.detect_prerequisite_first_task(request.task_clean)
        and request.session_directive != "build"
    ):
        ui.trace_doing(
            "Your message asks for something before building; answering that first "
            "(skipping Stitch and the full code pipeline this turn)."
        )
        pr_raw, pr_err, pr_rc = await deps.run_codex(
            deps.build_prerequisite_first_prompt(request.task_clean, request.mem_block),
            "Codex: answering prerequisite question first...",
        )
        if pr_rc != 0:
            ui.trace_done(
                "Prerequisite answer step failed; fix the error below, then retry or use /ask."
            )
            ui.console.print()
            ui.say(f"[clogem] ERROR: Codex exited with code {pr_rc}.")
            if (pr_err or "").strip():
                clip = (pr_err or "").strip()[:1200]
                if len((pr_err or "").strip()) > 1200:
                    clip += "..."
                ui.console.print(ui.text_factory(clip, style=ui.log_err_style))
            ui.console.print()
            ui.token_turn_footer()
            return TurnModeResult(stop_turn=True, mode=None, chat_reply=None)
        mode = "chat"
        chat_reply = (pr_raw or "").strip()
        ui.trace_done(
            "Prerequisite reply ready; skipping build/Stitch for this turn — ask for the build again when ready."
        )

    return TurnModeResult(stop_turn=False, mode=mode, chat_reply=chat_reply)


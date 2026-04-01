from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple


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
    *,
    session_directive: Optional[str],
    task_clean: str,
    mem_block: str,
    build_router_prompt: Any,
    run_codex: Any,
    runtime_stitch_capabilities_block: Any,
    runtime_clogem_commands_capabilities_block: Any,
    router_hint: str,
    trace_doing: Any,
    trace_done: Any,
    _say: Any,
    console: Any,
    Text: Any,
    LOG_ERR: str,
    MUTED: str,
    _token_turn_footer: Any,
    detect_stitch_frontend_heavy_task: Any,
    detect_prerequisite_first_task: Any,
    build_prerequisite_first_prompt: Any,
    secondary_intent_classifier: Any = None,
) -> Dict[str, Any]:
    if session_directive == "build":
        trace_done(
            "Directive /build: skipping classifier; running the full build pipeline."
        )
        mode = "workflow"
        chat_reply = None
    else:
        trace_doing(
            "I'm having Codex classify this turn: full build pipeline versus a direct conversational reply (using your text and saved context)."
        )
        router_raw, router_err, router_rc = await run_codex(
            build_router_prompt(
                task_clean,
                mem_block
                + runtime_stitch_capabilities_block()
                + runtime_clogem_commands_capabilities_block(),
                router_hint,
            ),
            "Codex: routing (build vs conversation)...",
        )
        if router_rc != 0:
            trace_done(
                "Routing failed; not guessing BUILD/CHAT. Fix the error below, then retry."
            )
            console.print()
            _say(f"[clogem] ERROR: Codex routing exited with code {router_rc}.")
            if (router_err or "").strip():
                clip = (router_err or "").strip()[:1200]
                if len((router_err or "").strip()) > 1200:
                    clip += "..."
                console.print(Text(clip, style=LOG_ERR))
            console.print(
                Text(
                    "Hint: clogem runs `codex exec --skip-git-repo-check`. "
                    "If this persists, check `codex` on PATH and disk permissions.",
                    style=MUTED,
                )
            )
            console.print()
            _token_turn_footer()
            return {"stop_turn": True, "mode": None, "chat_reply": None}
        mode, chat_reply = parse_build_or_chat(router_raw)
        stitch_heavy_for_routing = detect_stitch_frontend_heavy_task(task_clean)
        if mode == "chat" and not detect_prerequisite_first_task(task_clean):
            # Secondary lightweight classifier call replaces hardcoded heuristics.
            llm_route = None
            if secondary_intent_classifier is not None:
                try:
                    llm_route = await secondary_intent_classifier(task_clean, mem_block)
                except Exception:
                    llm_route = None
            if (llm_route or "").strip().upper() == "BUILD" or stitch_heavy_for_routing:
                mode = "workflow"
                chat_reply = None

    if (
        mode == "workflow"
        and detect_prerequisite_first_task(task_clean)
        and session_directive != "build"
    ):
        trace_doing(
            "Your message asks for something before building; answering that first "
            "(skipping Stitch and the full code pipeline this turn)."
        )
        pr_raw, pr_err, pr_rc = await run_codex(
            build_prerequisite_first_prompt(task_clean, mem_block),
            "Codex: answering prerequisite question first...",
        )
        if pr_rc != 0:
            trace_done(
                "Prerequisite answer step failed; fix the error below, then retry or use /ask."
            )
            console.print()
            _say(f"[clogem] ERROR: Codex exited with code {pr_rc}.")
            if (pr_err or "").strip():
                clip = (pr_err or "").strip()[:1200]
                if len((pr_err or "").strip()) > 1200:
                    clip += "..."
                console.print(Text(clip, style=LOG_ERR))
            console.print()
            _token_turn_footer()
            return {"stop_turn": True, "mode": None, "chat_reply": None}
        mode = "chat"
        chat_reply = (pr_raw or "").strip()
        trace_done(
            "Prerequisite reply ready; skipping build/Stitch for this turn — ask for the build again when ready."
        )

    return {"stop_turn": False, "mode": mode, "chat_reply": chat_reply}


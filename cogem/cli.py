#!/usr/bin/env python3

# Boot palette (24-bit ANSI) — matches cogem rose theme, not plain white
_BOOT_ROSE = "\033[38;2;190;85;85m"
_BOOT_SOFT = "\033[38;2;255;175;175m"
_BOOT_BLUSH = "\033[38;2;255;200;200m"
_BOOT_MUTED = "\033[38;2;180;130;130m"
_BOOT_ERR = "\033[38;2;230;70;90m"
_BOOT_RESET = "\033[0m"


def _boot_type_line(text: str, delay: float = 0.008, color: str = _BOOT_SOFT) -> None:
    import sys
    import time

    for char in text:
        sys.stdout.write(f"{color}{char}{_BOOT_RESET}")
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write("\n")
    sys.stdout.flush()


def _boot_spinner_worker(stop_event, label: str) -> None:
    import sys
    import time

    spinner = ["|", "/", "-", "\\"]
    i = 0
    while not stop_event.is_set():
        sys.stdout.write(
            f"\r{_BOOT_MUTED}{label}... {spinner[i % len(spinner)]}{_BOOT_RESET}  "
        )
        sys.stdout.flush()
        time.sleep(0.1)
        i += 1


def _boot_run_step(
    label: str,
    check,
    min_spin: float = 0.35,
) -> bool:
    """Spin; run optional check() -> bool. Clear line and print ok / not found."""
    import sys
    import time
    import threading

    stop = threading.Event()
    t = threading.Thread(target=_boot_spinner_worker, args=(stop, label), daemon=True)
    t.start()
    t0 = time.monotonic()
    ok = True
    if check is not None:
        ok = bool(check())
    while time.monotonic() - t0 < min_spin:
        time.sleep(0.05)
    stop.set()
    t.join(timeout=2.0)
    sys.stdout.write("\r" + " " * 96 + "\r")
    sys.stdout.flush()
    if check is None:
        sys.stdout.write(f"{_BOOT_ROSE}{label}... ok{_BOOT_RESET}\n")
        sys.stdout.flush()
        return True
    if ok:
        sys.stdout.write(f"{_BOOT_ROSE}{label}... ok{_BOOT_RESET}\n")
    else:
        sys.stdout.write(f"{_BOOT_ERR}{label}... not found{_BOOT_RESET}\n")
    sys.stdout.flush()
    return ok


def boot_sequence() -> bool:
    """TTY-style boot, real codex/gemini checks. Returns False if deps missing."""
    import shutil
    import sys

    sys.stdout.write("\n")
    sys.stdout.flush()

    logo = [
        "██████╗  ██████╗  ██████╗  ███████╗ ███╗   ███╗",
        "██╔═══╝ ██╔═══██╗ ██╔═══╝  ██╔════╝ ████╗ ████║",
        "██║     ██║   ██║ ██║ ███╗ █████╗   ██╔████╔██║",
        "██║     ██║   ██║ ██║  ██║ ██╔══╝   ██║╚██╔╝██║",
        "╚██████╗╚██████╔╝ ╚██████╗ ███████╗ ██║ ╚═╝ ██║",
        " ╚═════╝ ╚═════╝  ╚═════╝ ╚══════╝ ╚═╝     ╚═╝ ",
    ]
    for row in logo:
        _boot_type_line(row, 0.002, _BOOT_BLUSH)
    sys.stdout.write("\n")
    sys.stdout.flush()
    _boot_type_line("cogem · build → review → evolve", 0.008, _BOOT_ROSE)
    sys.stdout.write("\n")
    sys.stdout.flush()

    _boot_run_step("initializing engine", None, min_spin=0.45)

    if not _boot_run_step(
        "loading codex",
        lambda: shutil.which("codex") is not None,
        min_spin=0.35,
    ):
        sys.stdout.write("\n")
        sys.stdout.flush()
        sys.stdout.write(
            f"{_BOOT_ERR}cogem cannot start: `codex` is not on PATH.{_BOOT_RESET}\n"
        )
        sys.stdout.write(
            f"{_BOOT_MUTED}Install the Codex CLI and ensure it is initialized, then try again.{_BOOT_RESET}\n"
        )
        sys.stdout.flush()
        return False

    if not _boot_run_step(
        "loading gemini",
        lambda: shutil.which("gemini") is not None,
        min_spin=0.35,
    ):
        sys.stdout.write("\n")
        sys.stdout.flush()
        sys.stdout.write(
            f"{_BOOT_ERR}cogem cannot start: `gemini` is not on PATH.{_BOOT_RESET}\n"
        )
        sys.stdout.write(
            f"{_BOOT_MUTED}Install the Gemini CLI and ensure it is on your PATH, then try again.{_BOOT_RESET}\n"
        )
        sys.stdout.flush()
        return False

    _boot_type_line("system ready >", 0.01, _BOOT_ROSE)
    sys.stdout.write("\n")
    sys.stdout.flush()
    return True


def main():
    import json
    import subprocess
    import re
    import difflib
    import os
    import sys
    import time
    import webbrowser
    import shutil
    from pathlib import Path
    from datetime import datetime, timezone
    from typing import List, Optional, Tuple

    import threading

    from rich.console import Console
    from rich.rule import Rule
    from rich.text import Text

    if not boot_sequence():
        raise SystemExit(1)

    # Accent (rose) + Claude-like neutrals (dim rules, soft reasoning frames)
    BORDER = "#ffafaf"
    TITLE = "bold #be5555"
    SUBTITLE = "#5f3737"
    MUTED = "#c87878"
    DIM = "dim"
    ITALIC_DIM = "italic dim"
    LOG_START = "bold #be5555"
    LOG_DONE = "green"
    LOG_WARN = "yellow"
    LOG_ERR = "bold red"
    LOG_OK = "green"
    LOG_TRACE = "italic #9a7a7a"

    console = Console()
    # Best-effort token totals per provider (parsed from CLI output when present).
    session_tokens = {"codex": 0, "gemini": 0}
    # None = not asked yet; True/False = user chose whether to pass Codex --full-auto and Gemini --yolo.
    auto_permissions: dict = {"granted": None}

    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    AI_PATH = os.path.join(ROOT, ".ai")
    MEMORY_PATH = os.path.join(ROOT, "memory.json")

    DEFAULT_MEMORY = {
        "stack": [],
        "constraints": [],
        "decisions": [],
        "notes": "",
    }

    def load_memory():
        if not os.path.isfile(MEMORY_PATH):
            save_memory(dict(DEFAULT_MEMORY))
            return dict(DEFAULT_MEMORY)
        try:
            with open(MEMORY_PATH, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return dict(DEFAULT_MEMORY)
        out = dict(DEFAULT_MEMORY)
        if isinstance(data, dict):
            for k in DEFAULT_MEMORY:
                if k in data:
                    out[k] = data[k]
        return out

    def save_memory(data):
        with open(MEMORY_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")

    def format_memory_for_prompt(mem):
        lines = []
        stack = mem.get("stack") or []
        constraints = mem.get("constraints") or []
        decisions = mem.get("decisions") or []
        notes = (mem.get("notes") or "").strip()

        if isinstance(stack, list) and stack:
            lines.append("Stack / tools (prefer these unless the task requires otherwise):")
            for s in stack:
                if str(s).strip():
                    lines.append(f"  - {str(s).strip()}")
            lines.append(
                "If the current task names a different programming language, framework, or stack "
                "(or explicitly switches away from the items above), follow the task for this deliverable."
            )
        if isinstance(constraints, list) and constraints:
            lines.append("Constraints / rules:")
            for c in constraints:
                if str(c).strip():
                    lines.append(f"  - {str(c).strip()}")
        if isinstance(decisions, list) and decisions:
            lines.append("Past decisions (honor unless the user clearly overrides):")
            for d in decisions:
                if isinstance(d, dict) and d.get("text"):
                    t = str(d["text"]).strip()
                    when = str(d.get("date", "")).strip()
                    lines.append(f"  - [{when}] {t}" if when else f"  - {t}")
                elif str(d).strip():
                    lines.append(f"  - {str(d).strip()}")
        if notes:
            lines.append("Additional notes:")
            for part in notes.splitlines():
                if part.strip():
                    lines.append(f"  {part.strip()}")

        if not lines:
            return ""
        return (
            "## Persistent memory (from memory.json)\n"
            + "\n".join(lines)
            + "\n\n---\n\n"
        )

    def _wall_clock() -> str:
        """Local wall time only (no UTC-style suffix — avoids confusion on Windows)."""
        return time.strftime("%H:%M:%S", time.localtime())

    _TOKEN_PATTERNS = (
        re.compile(r"tokens?\s+used[:\s]+([\d,]+)", re.I),
        re.compile(r"total\s+tokens?[:\s]+([\d,]+)", re.I),
        re.compile(r"(?:^|\s)([\d,]+)\s+tokens?\s+used", re.I),
    )

    def _extract_tokens_from_text(text: str) -> Optional[int]:
        """Return a single token count if the CLI printed something recognizable."""
        if not text or not text.strip():
            return None
        for pat in _TOKEN_PATTERNS:
            m = pat.search(text)
            if m:
                try:
                    return int(m.group(1).replace(",", ""))
                except ValueError:
                    continue
        return None

    def _record_tokens(provider: str, text: str) -> None:
        n = _extract_tokens_from_text(text)
        if n is None:
            return
        session_tokens[provider] = session_tokens.get(provider, 0) + n
        console.print(
            Text(
                f"[cogem] Tokens (~{provider} this call): {n}  "
                f"(running total this turn ~{session_tokens[provider]})",
                style=MUTED,
            )
        )

    def _token_turn_footer() -> None:
        """Summarize parsed token counts for the current user turn."""
        c = int(session_tokens.get("codex", 0) or 0)
        g = int(session_tokens.get("gemini", 0) or 0)
        if c == 0 and g == 0:
            console.print(
                Text(
                    "[cogem] Token usage: no counts found in CLI output this turn "
                    "(free-tier CLIs often omit usage; check provider dashboards if needed).",
                    style=MUTED,
                )
            )
        else:
            console.print(
                Text(
                    f"[cogem] Token estimates this turn (parsed from CLI text): "
                    f"codex ~{c}, gemini ~{g}",
                    style=MUTED,
                )
            )

    def _subprocess_timeout_sec() -> Optional[int]:
        raw = os.environ.get("COGEM_SUBPROCESS_TIMEOUT_SEC", "").strip()
        if not raw:
            return None
        try:
            return max(1, int(raw))
        except ValueError:
            return None

    def _task_preview(task: str, max_len: int = 90) -> str:
        preview = re.sub(r"\s+", " ", task.strip())
        if len(preview) > max_len:
            preview = preview[: max_len - 3] + "..."
        return preview

    def _say(msg: str) -> None:
        """Colored narration (Rich); readable in every terminal that supports ANSI."""
        if msg.startswith("[cogem] START:"):
            console.print(Text(msg, style=LOG_START))
        elif msg.startswith("[cogem] DONE:"):
            console.print(Text(msg, style=LOG_DONE))
        elif msg.startswith("[cogem] WARNING"):
            console.print(Text(msg, style=LOG_WARN))
        elif msg.startswith("[cogem] ERROR"):
            console.print(Text(msg, style=LOG_ERR))
        elif msg.startswith("[cogem]"):
            console.print(Text(msg, style=TITLE))
        elif msg.startswith("  ") and (" > " in msg or " ok " in msg):
            console.print(Text(msg, style=LOG_TRACE))
        elif msg.strip().startswith("[ok]"):
            console.print(Text(msg, style=LOG_OK))
        else:
            console.print(msg)

    def live_reasoning_banner_build(task: str, mem_block: str) -> None:
        preview = _task_preview(task, 88)
        mem_on = bool(mem_block and mem_block.strip())
        _say("")
        _say("[cogem] Thinking (build)")
        _say(f"  request: {preview}")
        _say(
            "  context: prior notes are included in Codex/Gemini prompts."
            if mem_on
            else "  context: no saved notes yet; using your message + rule files."
        )
        _say("  next: I will narrate each step on this log as it runs.")
        _say("")

    def live_reasoning_banner_chat(task: str) -> None:
        preview = _task_preview(task, 88)
        _say("")
        _say("[cogem] Thinking (conversation)")
        _say(f"  request: {preview}")
        _say("  next: showing routed reply below (no code pipeline).")
        _say("")

    def trace_doing(msg: str) -> None:
        _say(f"  {_wall_clock()} > {msg}")

    def trace_done(msg: str) -> None:
        _say(f"  {_wall_clock()} ok {msg}")

    def section_heading(label: str) -> None:
        _say("")
        _say(f"---------- {label} ----------")

    def section_rule(label: str) -> None:
        section_heading(label)

    _SPINNER_DIM = "\033[2m"
    _SPINNER_RESET = "\033[0m"

    def _run_with_ascii_progress(label: str, fn):
        """
        ASCII spinner on stdout (no Unicode). Always visible vs Rich / braille.
        """
        import sys as _sys

        _say(f"[cogem] START: {label}")
        stop = threading.Event()
        t0 = time.monotonic()
        frames = "|/-\\"

        def _spin() -> None:
            i = 0
            while not stop.is_set():
                elapsed = int(time.monotonic() - t0)
                ch = frames[i % len(frames)]
                tail = f"... working {ch} ({elapsed}s)"
                line = f"  {label} {tail}"
                pad = max(0, 76 - len(line))
                _sys.stdout.write(
                    "\r"
                    + _SPINNER_DIM
                    + line
                    + (" " * pad)
                    + _SPINNER_RESET
                )
                _sys.stdout.flush()
                time.sleep(0.12)
                i += 1

        th = threading.Thread(target=_spin, daemon=True)
        th.start()
        try:
            out = fn()
        finally:
            stop.set()
            th.join(timeout=2.0)
            _sys.stdout.write("\r" + (" " * 80) + "\r\n")
            _sys.stdout.flush()
        elapsed = time.monotonic() - t0
        _say(f"[cogem] DONE:  {label}  ({elapsed:.1f}s)")
        return out

    def run_cmd(
        cmd: List[str], status_msg: Optional[str] = None
    ) -> Tuple[str, str, int]:
        to = _subprocess_timeout_sec()

        def _run():
            kw = {"capture_output": True, "text": True}
            if to is not None:
                kw["timeout"] = to
            try:
                return subprocess.run(cmd, **kw)
            except subprocess.TimeoutExpired:
                _say(
                    f"[cogem] ERROR: subprocess timed out after {to}s "
                    f"(set COGEM_SUBPROCESS_TIMEOUT_SEC or fix the CLI hang)."
                )
                raise

        if status_msg:
            result = _run_with_ascii_progress(status_msg, _run)
            if result.returncode != 0:
                _say(
                    f"[cogem] WARNING: process exited with code {result.returncode}"
                )
                err = (result.stderr or "").strip()
                if err:
                    clip = err[:800] + ("..." if len(err) > 800 else "")
                    console.print(Text(f"  stderr: {clip}", style=LOG_WARN))
        else:
            result = _run()
        return result.stdout or "", result.stderr or "", result.returncode

    def _auto_permissions_from_env() -> Optional[bool]:
        raw = os.environ.get("COGEM_AUTO_PERMISSIONS", "").strip().lower()
        if raw in ("1", "y", "yes", "true", "on"):
            return True
        if raw in ("0", "n", "no", "false", "off"):
            return False
        return None

    def ensure_auto_permissions() -> None:
        """
        Codex/Gemini often block in headless mode until approvals are granted.
        Ask once per session (or use COGEM_AUTO_PERMISSIONS=yes|no).
        """
        if auto_permissions["granted"] is not None:
            return
        v = _auto_permissions_from_env()
        if v is not None:
            auto_permissions["granted"] = v
            return
        if not sys.stdin.isatty():
            auto_permissions["granted"] = False
            console.print(
                Text(
                    "[cogem] Non-interactive stdin: not prompting for Codex/Gemini permissions. "
                    "Set COGEM_AUTO_PERMISSIONS=yes if builds hang or fail.",
                    style=LOG_WARN,
                )
            )
            return
        console.print()
        console.print(
            Text(
                "Non-interactive Codex and Gemini runs usually need explicit permission: "
                "Codex adds --full-auto (sandboxed workspace write + on-request commands). "
                "Gemini adds --yolo so headless tool steps are not stuck waiting for approval.",
                style=MUTED,
            )
        )
        console.print(
            Text(
                "Tip: set COGEM_AUTO_PERMISSIONS=yes or no to skip this prompt.",
                style=MUTED,
            )
        )
        ans = console.input(
            Text("Allow both for this cogem session? [y/N]: ", style=TITLE)
        ).strip().lower()
        auto_permissions["granted"] = ans in ("y", "yes")
        if not auto_permissions["granted"]:
            console.print(
                Text(
                    "Continuing without --full-auto / --yolo. If subprocesses hang or exit with "
                    "approval errors, re-run with COGEM_AUTO_PERMISSIONS=yes.",
                    style=LOG_WARN,
                )
            )

    def _codex_argv(prompt: str) -> List[str]:
        """codex exec with flags that avoid failing outside a git repo / trusted tree."""
        argv = ["codex", "exec", "--skip-git-repo-check"]
        if auto_permissions.get("granted"):
            argv.append("--full-auto")
        wd = os.environ.get("COGEM_CODEX_WORKDIR", "").strip()
        if wd:
            argv.extend(["-C", os.path.abspath(wd)])
        argv.append(prompt)
        return argv

    def _gemini_argv(prompt: str) -> List[str]:
        argv = ["gemini"]
        if auto_permissions.get("granted"):
            argv.append("--yolo")
        argv.extend(["-p", prompt])
        return argv

    def _run_proc(args: List[str], cwd: Optional[str] = None):
        """subprocess.run with same optional timeout as Codex/Gemini."""
        kw = {"capture_output": True, "text": True}
        if cwd is not None:
            kw["cwd"] = cwd
        to = _subprocess_timeout_sec()
        if to is not None:
            kw["timeout"] = to
        try:
            return subprocess.run(args, **kw)
        except subprocess.TimeoutExpired:
            _say(
                f"[cogem] ERROR: subprocess timed out after {to}s "
                f"(set COGEM_SUBPROCESS_TIMEOUT_SEC)."
            )
            raise

    def run_codex(prompt: str, status_msg: str) -> Tuple[str, str, int]:
        stdout, stderr, rc = run_cmd(_codex_argv(prompt), status_msg)
        combined = (stdout or "") + "\n" + (stderr or "")
        _record_tokens("codex", combined)
        return stdout or "", stderr or "", rc

    def run_gemini(prompt: str, status_msg: str) -> Tuple[str, str, int]:
        stdout, stderr, rc = run_cmd(_gemini_argv(prompt), status_msg)
        combined = (stdout or "") + "\n" + (stderr or "")
        _record_tokens("gemini", combined)
        return (stdout or "").strip(), stderr or "", rc

    def extract_code(text):
        match = re.search(r"```(?:\w+)?\n([\s\S]*?)```", text)
        return match.group(1).strip() if match else text

    ROUTER_TEMPLATE = """You route input for Cogem, a CLI that runs a Codex+Gemini coding workflow.

Saved project context (memory.json)—use it when mode is CHAT so answers stay consistent (name, stack, notes, etc.):
---
__MEMORY__
---

BUILD = the user wants software development work: write or change code, scripts, apps, sites, APIs, CLIs, configs for projects, debugging/refactoring code, generating project files, implementation steps, or anything where producing/editing code or project artifacts is the main goal.

CHAT = not that: greetings, thanks, small talk, general knowledge, non-coding questions, unrelated topics, or meta questions about you without a build task.

Programming language / stack: If the user asks to build or change software using a specific language or framework (Python, JavaScript, Go, Rust, etc.), or to switch from one stack to another, that is always BUILD — not CHAT.

ROUTING FORMAT (CRITICAL — machine-parsed):
- Line 1 must be ONLY the ASCII English word BUILD or CHAT (not translated, not localized). No other word on line 1.
- After line 1 you may write the CHAT reply in ordinary prose if mode is CHAT.

If ambiguous, choose BUILD.

Reply with exactly this shape (no markdown fences, no preamble before line 1):
Line 1: only the word BUILD or CHAT
If CHAT: starting line 2, a short helpful plain-text reply (no fenced code unless they explicitly asked for code).

If CHAT: when the user states identity, preferences, or asks you to remember something for later turns, you MUST add one line at the very end (after your reply) using exactly:
PERSIST note: <concise fact>
(or PERSIST stack: / PERSIST constraints: / PERSIST decision: when that fits better)
If there is truly nothing durable to store, omit PERSIST lines entirely.

User input:
---
__TASK__
---
"""

    _PERSIST_LINE = re.compile(
        r"^PERSIST\s+(note|stack|constraints|decision)\s*:\s*(.+?)\s*$",
        re.I,
    )

    def build_router_prompt(task: str, mem_block: str) -> str:
        mem_ctx = mem_block.strip() if mem_block.strip() else "(none yet)"
        return (
            ROUTER_TEMPLATE.replace("__MEMORY__", mem_ctx).replace("__TASK__", task)
        )

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
                        "I'm Cogem: when you describe something to build or code to change, "
                        "I'll run the full loop. What would you like to work on?"
                    )
                return "chat", rest
        return "workflow", None

    def looks_like_build_task(task: str) -> bool:
        """Heuristic when the router mis-labels CHAT (e.g. coding-language or stack switch)."""
        t = task.lower()
        if len(t.strip()) < 4:
            return False
        intent = (
            "build ",
            "create ",
            "make a ",
            "write a ",
            "implement ",
            "portfolio",
            "website",
            "web site",
            "landing",
            "write ",
            "code ",
            " app",
            "debug",
            "refactor",
            "fix ",
            "add ",
            "api",
            "script",
            "html",
            "css",
            "project",
            "feature",
            "frontend",
            "backend",
            "site ",
            "cli",
        )
        if any(x in t for x in intent):
            return True
        # Common programming languages / runtimes / frameworks (stack switches still = build).
        tech = (
            "javascript",
            "typescript",
            "python",
            "golang",
            "using go",
            " in go",
            " with go",
            " rust",
            "java",
            "kotlin",
            "swift",
            "ruby",
            "php",
            "csharp",
            "c#",
            "c++",
            "react",
            "vue",
            "svelte",
            "angular",
            "next.js",
            "nextjs",
            "nuxt",
            "astro",
            "remix",
            "express",
            "fastapi",
            "django",
            "flask",
            "spring",
            "rails",
            "laravel",
            "dotnet",
            "node",
            "bun",
            "deno",
            "tailwind",
            "webpack",
            "vite",
            "postgres",
            "mongodb",
            "sqlite",
        )
        if any(x in t for x in tech):
            return True
        non_en = (
            "créer",
            "creer",
            "sitio",
            "página",
            "pagina",
            "construir",
            "sitio web",
            "código",
            "codigo",
            "proyecto",
            "aplicación",
            "aplicacion",
            "site web",
            "développer",
            "developper",
        )
        return any(x in t for x in non_en)

    def extract_persist_directives(text: str):
        """Strip PERSIST lines from model text; return (visible_reply, [(kind, value), ...])."""
        out_lines = []
        persists = []
        for line in text.splitlines():
            m = _PERSIST_LINE.match(line.strip())
            if m:
                kind, val = m.group(1).lower(), m.group(2).strip()
                if val:
                    persists.append((kind, val))
            else:
                out_lines.append(line)
        visible = "\n".join(out_lines).strip()
        return visible, persists

    def apply_persist_directives(mem, persists) -> bool:
        """Apply auto-persist lines; save if any. Returns whether memory changed."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        changed = False
        for kind, val in persists:
            changed = True
            if kind == "note":
                prev = (mem.get("notes") or "").strip()
                mem["notes"] = (prev + "\n" + val).strip() if prev else val
            elif kind == "stack":
                mem.setdefault("stack", []).append(val)
            elif kind == "constraints":
                mem.setdefault("constraints", []).append(val)
            elif kind == "decision":
                mem.setdefault("decisions", []).append({"date": now, "text": val})
        if changed:
            save_memory(mem)
        return changed

    MEMORY_EXTRACT_SESSION = """You update long-lived session memory for Cogem after a coding run finished.

User task:
---
__TASK__
---

What happened (summary):
---
__SUMMARY__
---

Output ONLY 0-4 lines. Each line is exactly one of:
PERSIST note: <fact>
PERSIST stack: <tool or stack>
PERSIST constraints: <rule>
PERSIST decision: <decision>
or a single line: NONE

Persist only durable facts that should influence future sessions. If nothing is worth saving, output exactly NONE.
No markdown, no other text."""

    MEMORY_EXTRACT_PROJECT = """You update long-lived session memory for Cogem after multi-file output was written.

User task:
---
__TASK__
---

Files created:
__FILES__

Output ONLY 0-4 lines. Each line is exactly one of:
PERSIST note: <fact>
PERSIST stack: <tool or stack>
PERSIST constraints: <rule>
PERSIST decision: <decision>
or a single line: NONE

Persist only durable facts. If nothing is worth saving, output exactly NONE.
No markdown, no other text."""

    def auto_memory_from_text(mem, raw: str) -> None:
        """Parse PERSIST lines from model output; ignore NONE-only responses."""
        stripped = raw.strip()
        if not stripped or re.match(r"^NONE\s*$", stripped, re.I):
            return
        _, persists = extract_persist_directives(raw)
        if persists:
            apply_persist_directives(mem, persists)

    def auto_memory_after_code_session(mem, task: str, summary: str) -> None:
        t = task.replace("__", "")[:6000]
        s = summary.replace("__", "")[:12000]
        prompt = (
            MEMORY_EXTRACT_SESSION.replace("__TASK__", t).replace("__SUMMARY__", s)
        )
        _say(
            "[cogem] Saving session memory (extra Codex call) — "
            "you will see START/DONE lines below; this is not stuck."
        )
        out, _err, rc = run_codex(
            prompt,
            "Codex: updating persistent context...",
        )
        if rc != 0:
            console.print(
                Text(
                    f"[cogem] Session memory update skipped (Codex exit {rc}).",
                    style=LOG_WARN,
                )
            )
        else:
            auto_memory_from_text(mem, out)
        _say("[cogem] Session memory step finished.")

    def auto_memory_after_project_session(mem, task: str, file_names: str) -> None:
        t = task.replace("__", "")[:6000]
        f = file_names.replace("__", "")[:4000]
        prompt = MEMORY_EXTRACT_PROJECT.replace("__TASK__", t).replace("__FILES__", f)
        _say(
            "[cogem] Saving session memory (extra Codex call) — "
            "wait for DONE before the next prompt."
        )
        out, _err, rc = run_codex(
            prompt,
            "Codex: updating persistent context...",
        )
        if rc != 0:
            console.print(
                Text(
                    f"[cogem] Session memory update skipped (Codex exit {rc}).",
                    style=LOG_WARN,
                )
            )
        else:
            auto_memory_from_text(mem, out)
        _say("[cogem] Session memory step finished.")

    def extract_files(text):
        pattern = r"FILE:\s*(.*?)\n([\s\S]*?)(?=FILE:|$)"
        matches = re.findall(pattern, text)
        return {name.strip(): content.strip() for name, content in matches}

    def write_files(files):
        for name, content in files.items():
            with open(name, "w") as f:
                f.write(content)
            _say(f"  [ok] wrote {name}")

    def _pick_entry(paths: List[str], preferred_basenames: List[str]) -> str:
        for pref in preferred_basenames:
            pl = pref.lower()
            for p in paths:
                if os.path.basename(p).lower() == pl:
                    return p
        return sorted(paths)[0]

    def run_written_artifacts(files: dict) -> None:
        """Run by extension (internal only): .py, .js, then open .html — generic UI copy."""
        paths = [p.strip() for p in files if p.strip()]
        if not paths:
            return

        py_paths = [p for p in paths if p.lower().endswith(".py")]
        js_paths = [
            p
            for p in paths
            if p.lower().endswith(".js") or p.lower().endswith(".mjs")
        ]
        html_paths = [
            p
            for p in paths
            if p.lower().endswith(".html") or p.lower().endswith(".htm")
        ]

        # Python before Node before browser (server / CLI before preview).
        if py_paths:
            target = _pick_entry(
                py_paths,
                ["main.py", "app.py", "run.py", "server.py", "script.py"],
            )
            abs_p = os.path.abspath(target)
            work = os.path.dirname(abs_p) or os.getcwd()
            proc = _run_with_ascii_progress(
                "run python script",
                lambda: _run_proc([sys.executable, abs_p], cwd=work),
            )
            if proc.stdout and proc.stdout.strip():
                console.print(Text(proc.stdout.rstrip(), style=DIM))
            if proc.returncode != 0 and proc.stderr and proc.stderr.strip():
                console.print(Text(proc.stderr.rstrip(), style=MUTED))

        if js_paths:
            node = shutil.which("node")
            if node:
                target = _pick_entry(
                    js_paths,
                    ["index.js", "main.js", "server.js", "app.js"],
                )
                abs_p = os.path.abspath(target)
                work = os.path.dirname(abs_p) or os.getcwd()
                proc = _run_with_ascii_progress(
                    "run node script",
                    lambda: _run_proc([node, abs_p], cwd=work),
                )
                if proc.stdout and proc.stdout.strip():
                    console.print(Text(proc.stdout.rstrip(), style=DIM))
                if proc.returncode != 0 and proc.stderr and proc.stderr.strip():
                    console.print(Text(proc.stderr.rstrip(), style=MUTED))

        if html_paths:
            target = _pick_entry(html_paths, ["index.html", "main.html"])
            abs_p = os.path.abspath(target)
            uri = Path(abs_p).as_uri()
            _run_with_ascii_progress(
                "open browser",
                lambda: webbrowser.open(uri),
            )

    def get_diff(old, new):
        diff = difflib.unified_diff(
            old.splitlines(),
            new.splitlines(),
            lineterm="",
        )
        return "\n".join(diff)

    # ---------- load rules (once per process) ----------

    with open(os.path.join(AI_PATH, "CODEX.md"), encoding="utf-8") as f:
        CODEX_RULES = f.read()

    with open(os.path.join(AI_PATH, "GEMINI.md"), encoding="utf-8") as f:
        GEMINI_RULES = f.read()

    first_turn = True

    while True:
        try:
            memory = load_memory()
            mem_block = format_memory_for_prompt(memory)

            if first_turn:
                console.print(Rule(style=BORDER))
                header = Text()
                header.append("cogem", style=TITLE)
                header.append("  ", style="")
                header.append("dual-agent loop", style=SUBTITLE)
                console.print(header)
                console.print(Rule(style=BORDER))
                console.print()
                first_turn = False
            else:
                console.print()
                console.print(Rule(style=BORDER))
                console.print(Text("Next", style=TITLE))
                console.print(Rule(style=BORDER))
                console.print()

            # ---------- input ----------

            prompt_label = Text("What would you like to do? ", style=TITLE)
            task = console.input(prompt_label).strip()

            if not task:
                console.print(
                    Text(
                        "No input — type a task when you're ready.",
                        style=MUTED,
                    )
                )
                continue

            session_tokens["codex"] = 0
            session_tokens["gemini"] = 0

            ensure_auto_permissions()

            trace_doing(
                "I'm having Codex classify this turn: full build pipeline versus a direct conversational reply (using your text and saved context)."
            )
            router_raw, router_err, router_rc = run_codex(
                build_router_prompt(task, mem_block),
                "Codex: routing (build vs conversation)...",
            )
            if router_rc != 0:
                trace_done(
                    "Routing failed; not guessing BUILD/CHAT. Fix the error below, then retry."
                )
                console.print()
                _say(f"[cogem] ERROR: Codex routing exited with code {router_rc}.")
                if (router_err or "").strip():
                    clip = (router_err or "").strip()[:1200]
                    if len((router_err or "").strip()) > 1200:
                        clip += "..."
                    console.print(Text(clip, style=LOG_ERR))
                console.print(
                    Text(
                        "Hint: cogem runs `codex exec --skip-git-repo-check`. "
                        "If this persists, check `codex` on PATH and disk permissions.",
                        style=MUTED,
                    )
                )
                console.print()
                _token_turn_footer()
                continue
            mode, chat_reply = parse_build_or_chat(router_raw)
            if mode == "chat" and looks_like_build_task(task):
                mode = "workflow"
                chat_reply = None

            if mode == "chat":
                trace_done(
                    "Classified as conversation; I'm skipping the code pipeline and surfacing the routed reply next."
                )
                chat_reply, auto_persists = extract_persist_directives(chat_reply)
                apply_persist_directives(memory, auto_persists)

                live_reasoning_banner_chat(task)
                section_rule("Reply")
                console.print()
                console.print(chat_reply or "(empty reply)")
                console.print()
                _token_turn_footer()
                _say("[cogem] Turn finished. What would you like to do next?")
                continue

            trace_done(
                "Classified as a build; live narration starts below as each step runs."
            )
            live_reasoning_banner_build(task, mem_block)

            # ---------- generate ----------

            trace_doing(
                "I'm calling Codex with your task, CODEX.md rules, and any saved memory so I can get a first implementation pass."
            )
            raw, draft_err, draft_rc = run_codex(
                f"{mem_block}{CODEX_RULES}\n\nTASK:\n{task}",
                "Codex: drafting initial implementation...",
            )
            if draft_rc != 0:
                trace_done(
                    "Codex draft failed; no FILE: blocks or code to continue with."
                )
                console.print()
                _say(f"[cogem] ERROR: Codex draft exited with code {draft_rc}.")
                if (draft_err or "").strip():
                    clip = (draft_err or "").strip()[:1200]
                    if len((draft_err or "").strip()) > 1200:
                        clip += "..."
                    console.print(Text(clip, style=LOG_ERR))
                console.print(
                    Text(
                        "Set COGEM_CODEX_WORKDIR to your project folder if Codex should write elsewhere.",
                        style=MUTED,
                    )
                )
                console.print()
                _token_turn_footer()
                continue
            trace_done(
                "Codex finished; I'm inspecting the response for FILE: blocks (multi-file) versus a single code blob."
            )
            console.print()

            files = extract_files(raw)

            if files:
                trace_doing(
                    f"I'm writing {len(files)} file(s) from Codex's FILE: layout, then I'll run preview/script hooks if the extensions match."
                )
                section_heading("PROJECT MODE")
                console.print()
                write_files(files)
                console.print()
                run_written_artifacts(files)
                console.print()
                trace_done(
                    "Files and any auto-runs are done; I'm asking Codex to fold this project into long-lived memory next."
                )
                auto_memory_after_project_session(
                    memory, task, ", ".join(sorted(files.keys()))
                )
                _token_turn_footer()
                _say("[cogem] Turn finished. What would you like to do next?")
                continue

            code = extract_code(raw)
            trace_done(
                "Single-artifact path: I'm keeping this code and moving to Gemini for a review pass that doesn't see Codex's earlier chat."
            )
            console.print()

            trace_doing(
                "I'm printing Codex's first draft, then I'll call Gemini with only the code + GEMINI.md rules."
            )
            section_rule("Initial output (Codex)")
            console.print()
            console.print(code)
            console.print()

            # ---------- review ----------

            trace_doing(
                "I'm calling Gemini now to critique the draft (risks, style, missing pieces)—independent of Codex's voice."
            )
            review, gem_rev_err, gem_rev_rc = run_gemini(
                f"{mem_block}{GEMINI_RULES}\n\nCODE:\n{code}",
                "Gemini: writing structured review...",
            )
            if gem_rev_rc != 0:
                trace_done("Gemini review failed; stopping this build turn.")
                console.print()
                _say(f"[cogem] ERROR: Gemini exited with code {gem_rev_rc}.")
                if (gem_rev_err or "").strip():
                    clip = (gem_rev_err or "").strip()[:1200]
                    if len((gem_rev_err or "").strip()) > 1200:
                        clip += "..."
                    console.print(Text(clip, style=LOG_ERR))
                console.print(
                    Text(
                        "Free-tier quotas or network issues can cause long waits or failures. "
                        "Try again or set COGEM_SUBPROCESS_TIMEOUT_SEC.",
                        style=MUTED,
                    )
                )
                console.print()
                _token_turn_footer()
                continue
            trace_done(
                "Review is back; I'm going to feed Gemini's text to Codex as the sole improvement signal."
            )
            console.print()

            section_rule("Review (Gemini)")
            console.print()
            console.print(review)
            console.print()

            # ---------- improve ----------

            trace_doing(
                "I'm calling Codex again with the original code, Gemini's review, and the same generation rules so it can revise in place."
            )
            improved_raw, imp_err, imp_rc = run_codex(
                f"""
{mem_block}{CODEX_RULES}

You wrote:

{code}

Feedback:

{review}

Improve the code.
Return ONLY code.
""",
                "Codex: applying Gemini feedback...",
            )
            if imp_rc != 0:
                console.print(
                    Text(
                        f"[cogem] WARNING: Codex revision exited with code {imp_rc}; "
                        "using the first draft for diff/summary.",
                        style=LOG_WARN,
                    )
                )
                if (imp_err or "").strip():
                    clip = (imp_err or "").strip()[:800]
                    if len((imp_err or "").strip()) > 800:
                        clip += "..."
                    console.print(Text(clip, style=LOG_WARN))
                improved_raw = raw
            improved = extract_code(improved_raw)
            trace_done(
                "Revision is in; I'm computing a unified diff between the first and second Codex outputs next."
            )
            console.print()

            section_rule("Revised output (Codex)")
            console.print()
            console.print(improved)
            console.print()

            # ---------- diff ----------

            trace_doing(
                "I'm running a local unified diff (v1 vs v2) so you can see exactly what changed line by line."
            )
            diff_output = get_diff(code, improved)
            trace_done("Diff is computed; I'm moving on to a plain-language summary of the improvements.")
            console.print()

            section_rule("Diff (system)")
            console.print()
            console.print(diff_output)
            console.print()

            # ---------- summary ----------

            trace_doing(
                "I'm sending both versions to Gemini and asking for a short recap of what got better—not another code edit."
            )
            summary, gem_sum_err, gem_sum_rc = run_gemini(
                f"""
{mem_block}{GEMINI_RULES}

Compare and summarize improvements.

OLD:
{code}

NEW:
{improved}
""",
                "Gemini: summarizing improvements...",
            )
            if gem_sum_rc != 0:
                summary = (
                    f"(Gemini summary unavailable: CLI exited with code {gem_sum_rc}.)"
                )
                if (gem_sum_err or "").strip():
                    summary += "\n" + (gem_sum_err or "").strip()[:600]
                console.print(
                    Text(
                        "[cogem] WARNING: Gemini summary step failed; see placeholder text in Summary section.",
                        style=LOG_WARN,
                    )
                )
            _say(
                "[cogem] Gemini summary step finished; printing the summary text below."
            )
            trace_done(
                "Summary text received; next I persist session memory (another Codex call), then this turn ends."
            )
            console.print()

            section_rule("Summary (Gemini)")
            console.print()
            console.print(summary)
            console.print()

            auto_memory_after_code_session(memory, task, summary)
            _token_turn_footer()
            _say("[cogem] Turn finished. What would you like to do next?")

        except KeyboardInterrupt:
            console.print()
            console.print(
                Text(
                    "Press Ctrl+C again to exit cogem.",
                    style=MUTED,
                )
            )
            try:
                while True:
                    time.sleep(0.3)
            except KeyboardInterrupt:
                console.print()
                console.print(Text("Goodbye.", style=TITLE))
                raise SystemExit(0) from None


if __name__ == "__main__":
    main()

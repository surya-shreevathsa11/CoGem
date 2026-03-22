#!/usr/bin/env python3

# Boot palette (24-bit ANSI) — matches devai rose theme, not plain white
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
        "██████╗  ███████╗ ██╗   ██╗  █████╗  ██╗",
        "██╔══██╗ ██╔════╝ ██║   ██║ ██╔══██╗ ██║",
        "██║  ██║ █████╗   ██║   ██║ ███████║ ██║",
        "██║  ██║ ██╔══╝   ╚██╗ ██╔╝ ██╔══██║ ██║",
        "██████╔╝ ███████╗  ╚████╔╝  ██║  ██║ ██║",
        "╚═════╝  ╚══════╝   ╚═══╝   ╚═╝  ╚═╝ ╚═╝",
    ]
    for row in logo:
        _boot_type_line(row, 0.002, _BOOT_BLUSH)
    sys.stdout.write("\n")
    sys.stdout.flush()
    _boot_type_line("devai · build → review → evolve", 0.008, _BOOT_ROSE)
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
            f"{_BOOT_ERR}devai cannot start: `codex` is not on PATH.{_BOOT_RESET}\n"
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
            f"{_BOOT_ERR}devai cannot start: `gemini` is not on PATH.{_BOOT_RESET}\n"
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
    from typing import List, Optional

    from rich.console import Console
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.text import Text

    if not boot_sequence():
        raise SystemExit(1)

    # Accent (rose) + Claude-like neutrals (dim rules, soft reasoning frames)
    BORDER = "#ffafaf"
    TITLE = "bold #be5555"
    SUBTITLE = "#5f3737"
    MUTED = "#c87878"
    PANEL_FILL = "on #fff0f0"
    REASON_BORDER = "grey42"
    DIM = "dim"
    ITALIC_DIM = "italic dim"

    console = Console()

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

    def reasoning_block(title: str, paragraphs: List[str]) -> None:
        body = Text()
        for i, para in enumerate(paragraphs):
            if i:
                body.append("\n\n")
            body.append(para, style=ITALIC_DIM)
        console.print(
            Panel(
                body,
                title=Text(title, style=DIM),
                border_style=REASON_BORDER,
                padding=(0, 1),
                expand=False,
            )
        )

    def handoff_line(from_agent: str, to_agent: str, detail: str) -> None:
        bridge = Text()
        bridge.append("Handoff  ", style=DIM)
        bridge.append(from_agent, style=TITLE)
        bridge.append("  \u2192  ", style=DIM)
        bridge.append(to_agent, style=TITLE)
        console.print(bridge)
        console.print(Text(f"  {detail}", style=ITALIC_DIM))

    def step_done(line: str) -> None:
        console.print(Text(f"  \u00b7 {line}", style=DIM))

    def section_panel(title: str) -> Panel:
        return Panel(
            Text(title, style=TITLE),
            border_style=BORDER,
            style=PANEL_FILL,
            expand=False,
            padding=(0, 1),
        )

    def section_rule(label: str) -> None:
        console.print()
        console.print(Rule(Text(f" {label} ", style=TITLE), style=BORDER, align="left"))

    def run_cmd(cmd: List[str], status_msg: Optional[str] = None):
        if status_msg:
            with console.status(
                Text(status_msg, style=ITALIC_DIM),
                spinner="dots12",
                spinner_style=MUTED,
            ):
                result = subprocess.run(cmd, capture_output=True, text=True)
        else:
            result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout, result.stderr

    def run_codex(prompt: str, status_msg: str) -> str:
        stdout, _ = run_cmd(["codex", "exec", prompt], status_msg)
        return stdout

    def run_gemini(prompt: str, status_msg: str) -> str:
        stdout, _ = run_cmd(["gemini", "-p", prompt], status_msg)
        return stdout.strip()

    def extract_code(text):
        match = re.search(r"```(?:\w+)?\n([\s\S]*?)```", text)
        return match.group(1).strip() if match else text

    ROUTER_TEMPLATE = """You route input for DevAI, a CLI that runs a Codex+Gemini coding workflow.

Saved project context (memory.json)—use it when mode is CHAT so answers stay consistent (name, stack, notes, etc.):
---
__MEMORY__
---

BUILD = the user wants software development work: write or change code, scripts, apps, sites, APIs, CLIs, configs for projects, debugging/refactoring code, generating project files, implementation steps, or anything where producing/editing code or project artifacts is the main goal.

CHAT = not that: greetings, thanks, small talk, general knowledge, non-coding questions, unrelated topics, or meta questions about you without a build task.

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
        lines = raw.splitlines()
        for i, line in enumerate(lines):
            s = re.sub(r"[*_`#]", "", line).strip()
            if not s:
                continue
            head = s.upper().rstrip(".!?:")
            first = head.split()[0] if head.split() else ""
            if first == "BUILD":
                return "workflow", None
            if first == "CHAT":
                tokens = s.split(None, 1)
                same_line = tokens[1].strip() if len(tokens) > 1 else ""
                following = "\n".join(lines[i + 1 :]).strip()
                parts = [p for p in (same_line, following) if p]
                rest = "\n".join(parts).strip()
                if not rest:
                    rest = (
                        "I'm DevAI: when you describe something to build or code to change, "
                        "I'll run the full loop. What would you like to work on?"
                    )
                return "chat", rest
        return "workflow", None

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

    MEMORY_EXTRACT_SESSION = """You update long-lived session memory for DevAI after a coding run finished.

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

    MEMORY_EXTRACT_PROJECT = """You update long-lived session memory for DevAI after multi-file output was written.

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
        out = run_codex(
            prompt,
            "Codex: updating persistent context...",
        )
        auto_memory_from_text(mem, out)

    def auto_memory_after_project_session(mem, task: str, file_names: str) -> None:
        t = task.replace("__", "")[:6000]
        f = file_names.replace("__", "")[:4000]
        prompt = MEMORY_EXTRACT_PROJECT.replace("__TASK__", t).replace("__FILES__", f)
        out = run_codex(
            prompt,
            "Codex: updating persistent context...",
        )
        auto_memory_from_text(mem, out)

    def extract_files(text):
        pattern = r"FILE:\s*(.*?)\n([\s\S]*?)(?=FILE:|$)"
        matches = re.findall(pattern, text)
        return {name.strip(): content.strip() for name, content in matches}

    def write_files(files):
        for name, content in files.items():
            with open(name, "w") as f:
                f.write(content)
            line = Text()
            line.append("\u2713 ", style=MUTED)
            line.append(f"{name} created", style=SUBTITLE)
            console.print(line)

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
            with console.status(
                Text("Running...", style=ITALIC_DIM),
                spinner="dots12",
                spinner_style=MUTED,
            ):
                proc = subprocess.run(
                    [sys.executable, abs_p],
                    cwd=work,
                    capture_output=True,
                    text=True,
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
                with console.status(
                    Text("Running...", style=ITALIC_DIM),
                    spinner="dots12",
                    spinner_style=MUTED,
                ):
                    proc = subprocess.run(
                        [node, abs_p],
                        cwd=work,
                        capture_output=True,
                        text=True,
                    )
                if proc.stdout and proc.stdout.strip():
                    console.print(Text(proc.stdout.rstrip(), style=DIM))
                if proc.returncode != 0 and proc.stderr and proc.stderr.strip():
                    console.print(Text(proc.stderr.rstrip(), style=MUTED))

        if html_paths:
            target = _pick_entry(html_paths, ["index.html", "main.html"])
            abs_p = os.path.abspath(target)
            uri = Path(abs_p).as_uri()
            with console.status(
                Text("Opening preview...", style=ITALIC_DIM),
                spinner="dots12",
                spinner_style=MUTED,
            ):
                webbrowser.open(uri)

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
                header.append("devai", style=TITLE)
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

            router_raw = run_codex(
                build_router_prompt(task, mem_block),
                "Codex: routing (build vs conversation)...",
            )
            mode, chat_reply = parse_build_or_chat(router_raw)

            if mode == "chat":
                chat_reply, auto_persists = extract_persist_directives(chat_reply)
                apply_persist_directives(memory, auto_persists)

                console.print()
                section_rule("Reply")
                console.print()
                console.print(chat_reply or "(empty reply)")
                console.print()
                continue

            reasoning_block(
                "Working through your request",
                [
                    "I'll unfold this in a few deliberate steps so you can follow each move.",
                    "I'm lining up Codex with your wording plus anything we keep in memory: stack choices, constraints, past calls, so the first artifact is not starting from a blank slate.",
                    "Then I'll hand the draft to Gemini as a clean review pass: same code, fresh eyes, so the critique does not parrot Codex's own assumptions.",
                    "After that I'll carry Gemini's notes straight back to Codex for a revision pass, line up a before/after diff, and ask Gemini for a tight summary of what actually improved.",
                ],
            )
            console.print()

            # ---------- generate ----------

            console.print(Text("Step 1 - first artifact", style=TITLE))
            step_done("Codex is composing an initial implementation (rules + task + memory context).")
            raw = run_codex(
                f"{mem_block}{CODEX_RULES}\n\nTASK:\n{task}",
                "Codex: drafting initial implementation...",
            )
            step_done("Codex finished its pass; I'll inspect whether this is multi-file output or a single snippet.")
            console.print()

            files = extract_files(raw)

            if files:
                console.print(section_panel("PROJECT MODE"))
                console.print()
                handoff_line(
                    "Codex",
                    "Workspace",
                    "Codex returned FILE: blocks, so I'm materializing those paths on disk instead of running the review loop.",
                )
                console.print()
                write_files(files)
                console.print()
                run_written_artifacts(files)
                console.print()
                auto_memory_after_project_session(
                    memory, task, ", ".join(sorted(files.keys()))
                )
                continue

            code = extract_code(raw)
            step_done("Treating this as single-artifact mode: I'll route the snippet to Gemini next.")
            console.print()

            handoff_line(
                "Codex",
                "Gemini",
                "Sending only the candidate code plus review rules. Gemini has not seen Codex's earlier reasoning, so the feedback stays arm's-length.",
            )
            console.print()

            section_rule("Initial output (Codex)")
            console.print()
            console.print(code)
            console.print()

            # ---------- review ----------

            console.print(Text("Step 2 - independent review", style=TITLE))
            step_done("Gemini is reading the draft as code quality, risks, and gaps.")
            review = run_gemini(
                f"{mem_block}{GEMINI_RULES}\n\nCODE:\n{code}",
                "Gemini: writing structured review...",
            )
            step_done("Gemini returned notes; I'm packaging them for Codex as the sole improvement signal.")
            console.print()

            section_rule("Review (Gemini)")
            console.print()
            console.print(review)
            console.print()

            # ---------- improve ----------

            console.print(Text("Step 3 - close the loop with Codex", style=TITLE))
            handoff_line(
                "Gemini",
                "Codex",
                "Delivering Gemini's critique back to Codex with the original snippet so it can revise, not rewrite from scratch unless the review demands it.",
            )
            console.print()
            step_done("Codex is merging rules, prior code, and Gemini feedback into a revised artifact.")
            improved_raw = run_codex(
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
            improved = extract_code(improved_raw)
            step_done("Revision landed; next I'll diff against the first Codex version.")
            console.print()

            section_rule("Revised output (Codex)")
            console.print()
            console.print(improved)
            console.print()

            # ---------- diff ----------

            console.print(Text("Step 4 - surface the delta", style=TITLE))
            step_done("Computing a unified diff so you can see exactly what moved between Codex passes.")
            diff_output = get_diff(code, improved)
            console.print()

            section_rule("Diff (system)")
            console.print()
            console.print(diff_output)
            console.print()

            # ---------- summary ----------

            console.print(Text("Step 5 - narrative recap", style=TITLE))
            handoff_line(
                "Codex (v1 and v2)",
                "Gemini",
                "Sharing both versions so Gemini can describe improvements in plain language: not another code edit, just a concise changelog of intent.",
            )
            console.print()
            step_done("Gemini is comparing OLD vs NEW and summarizing outcomes.")
            summary = run_gemini(
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
            step_done("Summary ready. That completes the Codex \u2194 Gemini round trip for this task.")
            console.print()

            section_rule("Summary (Gemini)")
            console.print()
            console.print(summary)
            console.print()

            auto_memory_after_code_session(memory, task, summary)

        except KeyboardInterrupt:
            console.print()
            console.print(
                Text(
                    "Press Ctrl+C again to exit devai.",
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

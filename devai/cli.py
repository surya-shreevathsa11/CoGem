#!/usr/bin/env python3

def main():
    import json
    import subprocess
    import re
    import difflib
    import os
    import time
    from datetime import datetime, timezone
    from typing import List, Optional

    from rich.console import Console
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.text import Text

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

    def memory_stats(mem):
        n_stack = len([x for x in (mem.get("stack") or []) if str(x).strip()])
        n_cons = len([x for x in (mem.get("constraints") or []) if str(x).strip()])
        n_dec = len(mem.get("decisions") or [])
        notes = (mem.get("notes") or "").strip()
        n_notes = 1 if notes else 0
        return n_stack + n_cons + n_dec + n_notes

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

    ROUTER_PROMPT = """You route input for DevAI, a CLI that runs a Codex+Gemini coding workflow.

BUILD = the user wants software development work: write or change code, scripts, apps, sites, APIs, CLIs, configs for projects, debugging/refactoring code, generating project files, implementation steps, or anything where producing/editing code or project artifacts is the main goal.

CHAT = not that: greetings, thanks, small talk, general knowledge, non-coding questions, unrelated topics, or meta questions about you without a build task.

If ambiguous, choose BUILD.

Reply with exactly this shape (no markdown fences, no preamble):
Line 1: only the word BUILD or CHAT
If CHAT: starting line 2, a short helpful plain-text reply to the user (no code blocks unless they explicitly asked for code).

User input:
---
__TASK__
---
"""

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

    def get_diff(old, new):
        diff = difflib.unified_diff(
            old.splitlines(),
            new.splitlines(),
            lineterm="",
        )
        return "\n".join(diff)

    def append_memory_interactive(mem):
        hint = (
            "Save to memory.json (empty = skip). "
            "Prefixes: stack: | constraints: | note: | else -> decision"
        )
        console.print(Text(hint, style=MUTED))
        line = console.input(Text("\u203a ", style=TITLE)).strip()
        if not line:
            return
        lower = line.lower()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if lower.startswith("stack:"):
            item = line.split(":", 1)[1].strip()
            if item:
                mem.setdefault("stack", []).append(item)
        elif lower.startswith("constraints:"):
            item = line.split(":", 1)[1].strip()
            if item:
                mem.setdefault("constraints", []).append(item)
        elif lower.startswith("note:"):
            item = line.split(":", 1)[1].strip()
            if item:
                prev = (mem.get("notes") or "").strip()
                mem["notes"] = (prev + "\n" + item).strip() if prev else item
        else:
            mem.setdefault("decisions", []).append({"date": now, "text": line})

        save_memory(mem)
        console.print(Text("Memory updated.", style=MUTED))

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
                n = memory_stats(memory)
                header.append("  \u00b7  ", style="")
                header.append(f"memory: {n} item(s)", style=MUTED)
                console.print(header)
                console.print(Rule(style=BORDER))
                console.print()
                first_turn = False
            else:
                console.print()
                console.print(Rule(style=BORDER))
                sub = Text()
                sub.append("Next task", style=TITLE)
                sub.append("  \u00b7  ", style="")
                sub.append(
                    f"memory: {memory_stats(memory)} item(s)",
                    style=MUTED,
                )
                console.print(sub)
                console.print(Rule(style=BORDER))
                console.print()

            # ---------- input ----------

            prompt_label = Text("What do you want to build? ", style=TITLE)
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
                ROUTER_PROMPT.replace("__TASK__", task),
                "Checking whether this is a build task...",
            )
            mode, chat_reply = parse_build_or_chat(router_raw)

            if mode == "chat":
                console.print()
                section_rule("Reply (no coding workflow)")
                console.print()
                console.print(chat_reply)
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
                console.print(
                    Text("Open with: ", style=TITLE),
                    Text("explorer.exe index.html", style=MUTED),
                    end="",
                )
                console.print()
                console.print()
                append_memory_interactive(memory)
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

            append_memory_interactive(memory)

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

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
    import argparse
    import json
    import subprocess
    import re
    import difflib
    import os
    import sys
    import time
    import webbrowser
    import shutil
    import urllib.parse
    import urllib.request
    import urllib.error
    from pathlib import Path
    from datetime import datetime, timezone
    from typing import List, Optional, Tuple

    import threading

    from rich.console import Console
    from rich.rule import Rule
    from rich.text import Text

    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import Completer
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.history import InMemoryHistory
        from prompt_toolkit.output.color_depth import ColorDepth
        from prompt_toolkit.shortcuts import CompleteStyle
        from prompt_toolkit.styles import Style
    except ImportError:
        PromptSession = None
        Completer = None  # type: ignore
        KeyBindings = None  # type: ignore
        CompleteStyle = None  # type: ignore
        InMemoryHistory = None  # type: ignore
        Style = None  # type: ignore
        ColorDepth = None  # type: ignore

    from cogem.stitch import (
        build_stitch_prompt,
        detect_frontend_task,
        should_skip_stitch_due_to_attachments,
        try_stitch_adapters,
    )
    from cogem.stitch.adapters import format_stitch_context_for_codex, looks_like_ui_content
    from cogem.task_intent import build_prerequisite_first_prompt, detect_prerequisite_first_task

    _ap = argparse.ArgumentParser(
        prog="cogem",
        description="Cogem: Codex + Gemini dual-agent loop (generate, review, improve).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "LLM models are chosen separately for Codex (draft/improve) and Gemini (review/summary).\n"
            "Omit both flags to let each CLI use its default model (no -m passed).\n"
            "\n"
            "Examples:\n"
            "  cogem\n"
            "  cogem --codex-model o3 --gemini-model gemini-2.5-pro\n"
            "\n"
            "Env (when flags omitted): COGEM_CODEX_MODEL, COGEM_GEMINI_MODEL\n"
            "Valid IDs depend on your codex/gemini CLI and account; see `codex exec --help` and `gemini --help`."
        ),
    )
    _ap.add_argument(
        "--codex-model",
        metavar="MODEL_ID",
        default=None,
        help=(
            "LLM for Codex (generate + improve steps). Passed as `codex exec -m MODEL_ID`. "
            "Omit to use the Codex CLI default."
        ),
    )
    _ap.add_argument(
        "--gemini-model",
        metavar="MODEL_ID",
        default=None,
        help=(
            "LLM for Gemini (review + summary steps). Passed as `gemini -m MODEL_ID`. "
            "Omit to use the Gemini CLI default."
        ),
    )
    _ap.add_argument(
        "--no-stitch",
        action="store_true",
        help=(
            "Disable the Google Stitch stage for UI-heavy tasks (see COGEM_STITCH env)."
        ),
    )
    _args = _ap.parse_args()
    _codex_model = (_args.codex_model or os.environ.get("COGEM_CODEX_MODEL") or "").strip() or None
    _gemini_model = (_args.gemini_model or os.environ.get("COGEM_GEMINI_MODEL") or "").strip() or None
    stitch_feature_on = (not _args.no_stitch) and (
        (os.environ.get("COGEM_STITCH") or "1").strip().lower()
        not in ("0", "false", "no", "off", "disabled")
    )

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
    # None = not asked yet; True/False = user chose whether cogem can execute local shell commands (/run, /test, /lint, /github/clone).
    run_permissions: dict = {"granted": None}
    # Effective LLM IDs for this process (separate per backend); from CLI/env, change with /codex/model and /gemini/model.
    models: dict = {"codex": _codex_model, "gemini": _gemini_model}

    def _llm_status_line(human: str, cli_hint: str, model_id: Optional[str]) -> str:
        """human = short label; cli_hint = codex|gemini for messages."""
        if model_id:
            return f"{human}: {model_id}"
        return (
            f"{human}: default (cogem does not pass -m; `{cli_hint}` CLI default model)"
        )

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

    _AT_MENTION = re.compile(r'@"([^"]+)"|@\'([^\']+)\'|@([^\s@]+)')

    def _mention_roots_list() -> List[str]:
        roots: List[str] = []
        for r in (ROOT, os.getcwd()):
            try:
                rp = os.path.realpath(r)
                if os.path.isfile(rp):
                    rp = os.path.dirname(rp)
                if os.path.isdir(rp):
                    roots.append(rp)
            except OSError:
                continue
        wd = os.environ.get("COGEM_CODEX_WORKDIR", "").strip()
        if wd:
            try:
                rp = os.path.realpath(wd)
                if os.path.isdir(rp):
                    roots.append(rp)
            except OSError:
                pass
        out: List[str] = []
        for x in roots:
            if x not in out:
                out.append(x)
        return out

    def _path_allowed_for_mention(abs_path: str, roots: List[str]) -> bool:
        try:
            p = os.path.realpath(abs_path)
        except OSError:
            return False
        for root in roots:
            try:
                r = os.path.realpath(root)
                if not os.path.isdir(r):
                    continue
                if p == r or p.startswith(r + os.sep):
                    return True
            except OSError:
                continue
        return False

    def _resolve_mention_path(rel: str) -> Optional[str]:
        rel = rel.strip()
        if not rel or rel.startswith("-"):
            return None
        candidates: List[str] = []
        if os.path.isabs(rel):
            candidates.append(rel)
        else:
            candidates.append(os.path.join(os.getcwd(), rel))
            candidates.append(os.path.join(ROOT, rel))
        for c in candidates:
            try:
                if os.path.lexists(c):
                    return os.path.realpath(c)
            except OSError:
                continue
        return None

    def _read_pdf_for_mention(path: str, max_chars: int) -> str:
        """Best-effort PDF text extraction for @ mentions."""
        try:
            from pypdf import PdfReader  # type: ignore
        except Exception:
            return "[pdf extraction unavailable: install pypdf]"

        try:
            max_pages = max(1, int(os.environ.get("COGEM_AT_MAX_PDF_PAGES", "30")))
        except ValueError:
            max_pages = 30

        try:
            reader = PdfReader(path)
        except Exception as e:
            return f"[pdf read error: {e}]"

        total_pages = len(reader.pages)
        show_pages = min(total_pages, max_pages)
        out_parts: List[str] = []
        total = 0
        for i in range(show_pages):
            try:
                text = (reader.pages[i].extract_text() or "").strip()
            except Exception:
                text = ""
            if not text:
                text = f"[page {i + 1}: no extractable text]"
            block = f"\n\n--- PAGE {i + 1} ---\n{text}"
            if total + len(block) > max_chars:
                out_parts.append("\n\n[pdf text truncated by COGEM_AT_MAX_FILE_BYTES]")
                break
            out_parts.append(block)
            total += len(block)
        if total_pages > show_pages:
            out_parts.append(
                f"\n\n[pdf pages truncated: showing {show_pages}/{total_pages}; "
                f"set COGEM_AT_MAX_PDF_PAGES to increase]"
            )
        if not out_parts:
            return "[pdf contains no extractable text]"
        return "".join(out_parts).strip()

    def _read_file_for_mention(path: str, max_bytes: int) -> str:
        if path.lower().endswith(".pdf"):
            return _read_pdf_for_mention(path, max_bytes)
        try:
            with open(path, "rb") as f:
                raw = f.read(max_bytes + 1)
        except OSError as e:
            return f"[read error: {e}]"
        if len(raw) > max_bytes:
            chunk = raw[:max_bytes]
            if b"\x00" in chunk:
                return "[binary file omitted]"
            return (
                chunk.decode("utf-8", errors="replace")
                + "\n\n[truncated: file exceeds COGEM_AT_MAX_FILE_BYTES]"
            )
        if b"\x00" in raw:
            return "[binary file omitted]"
        return raw.decode("utf-8", errors="replace")

    def _dir_listing_for_mention(path: str, max_entries: int) -> str:
        lines: List[str] = []
        base = os.path.realpath(path)
        for root, dirs, files in os.walk(base):
            depth = root[len(base) :].count(os.sep)
            if depth > 3:
                dirs[:] = []
                continue
            dirs.sort()
            files.sort()
            for name in dirs:
                fp = os.path.join(root, name)
                rel = os.path.relpath(fp, base)
                lines.append(rel + "/")
                if len(lines) >= max_entries:
                    return "\n".join(lines) + "\n[directory listing truncated]"
            for name in files:
                fp = os.path.join(root, name)
                rel = os.path.relpath(fp, base)
                lines.append(rel)
                if len(lines) >= max_entries:
                    return "\n".join(lines) + "\n[directory listing truncated]"
        return "\n".join(lines) if lines else "(empty directory)"

    def expand_at_mentions(raw: str) -> Tuple[str, str]:
        """Strip @path mentions from task; return (clean_task, attachment_block for prompts)."""
        if "@" not in raw:
            return raw, ""
        roots = _mention_roots_list()
        try:
            max_b = max(4096, int(os.environ.get("COGEM_AT_MAX_FILE_BYTES", "400000")))
        except ValueError:
            max_b = 400000
        try:
            max_total = max(8000, int(os.environ.get("COGEM_AT_MAX_TOTAL_CHARS", "120000")))
        except ValueError:
            max_total = 120000

        paths_order: List[str] = []

        def _collect(m) -> str:
            p = m.group(1) or m.group(2) or m.group(3)
            if p:
                paths_order.append(p.strip())
            return ""

        clean = _AT_MENTION.sub(_collect, raw)
        clean = re.sub(r"\s+", " ", clean).strip()
        if not paths_order:
            return raw, ""

        seen = set()
        chunks: List[str] = []
        total = 0
        for rel in paths_order:
            if rel in seen:
                continue
            seen.add(rel)
            abs_p = _resolve_mention_path(rel)
            if not abs_p or not _path_allowed_for_mention(abs_p, roots):
                chunks.append(
                    f"### @{rel}\nNot found or not allowed (paths must stay under the project, "
                    f"current working directory, or COGEM_CODEX_WORKDIR).\n\n"
                )
                total += len(chunks[-1])
                continue
            try:
                label = os.path.relpath(abs_p, ROOT)
            except ValueError:
                label = abs_p
            if os.path.isfile(abs_p):
                body = _read_file_for_mention(abs_p, max_b)
            elif os.path.isdir(abs_p):
                body = _dir_listing_for_mention(abs_p, 100)
            else:
                body = "[not a file or directory]"
            block = f"### {label}\n```\n{body}\n```\n\n"
            if total + len(block) > max_total:
                chunks.append(
                    f"[@ context truncated: total size exceeds COGEM_AT_MAX_TOTAL_CHARS={max_total}]\n"
                )
                break
            total += len(block)
            chunks.append(block)

        if not chunks:
            return clean or raw, ""
        header = "## Referenced files and folders (@ mentions)\n\n"
        attach = header + "".join(chunks) + "---\n\n"
        if not clean:
            clean = "(Task text is empty; use the @ references and CODEX.md for intent.)"
        return clean, attach

    def _wall_clock() -> str:
        """Local wall time only (no UTC-style suffix — avoids confusion on Windows)."""
        return time.strftime("%H:%M:%S", time.localtime())

    def _parse_github_repo_ref(raw: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Parse GitHub ref (URL or owner/repo) -> (owner, repo, clone_url).
        """
        s = (raw or "").strip()
        if not s:
            return None, None, None
        if "github.com/" in s:
            try:
                p = urllib.parse.urlparse(s)
                parts = [x for x in p.path.strip("/").split("/") if x]
                if len(parts) < 2:
                    return None, None, None
                owner, repo = parts[0], parts[1]
                if repo.endswith(".git"):
                    repo = repo[:-4]
                if owner and repo:
                    return owner, repo, f"https://github.com/{owner}/{repo}.git"
                return None, None, None
            except Exception:
                return None, None, None
        if "/" in s and " " not in s:
            owner, repo = s.split("/", 1)
            if repo.endswith(".git"):
                repo = repo[:-4]
            if owner and repo:
                return owner, repo, f"https://github.com/{owner}/{repo}.git"
        return None, None, None

    def _github_repo_info(owner: str, repo: str) -> str:
        url = f"https://api.github.com/repos/{owner}/{repo}"
        req = urllib.request.Request(
            url,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "cogem-cli"},
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw)
        except urllib.error.HTTPError as e:
            return f"GitHub API error: HTTP {e.code} ({e.reason})"
        except Exception as e:
            return f"GitHub API error: {e}"
        if not isinstance(data, dict):
            return "GitHub API returned unexpected response."

        desc = (data.get("description") or "").strip() or "(no description)"
        stars = data.get("stargazers_count", 0)
        forks = data.get("forks_count", 0)
        lang = data.get("language") or "unknown"
        lic = data.get("license")
        lic_name = (lic.get("spdx_id") if isinstance(lic, dict) else None) or "unknown"
        branch = data.get("default_branch") or "main"
        return (
            f"{owner}/{repo}\n"
            f"- Description: {desc}\n"
            f"- Stars: {stars}   Forks: {forks}\n"
            f"- Language: {lang}   License: {lic_name}\n"
            f"- Default branch: {branch}\n"
            f"- Clone URL: https://github.com/{owner}/{repo}.git"
        )

    _TOKEN_TOTAL_PATTERNS = (
        re.compile(r"tokens?\s+used[:\s]+([\d,]+)", re.I),
        re.compile(r"total\s+tokens?[:\s]+([\d,]+)", re.I),
        re.compile(r"(?:^|\s)([\d,]+)\s+tokens?\s+used", re.I),
        re.compile(r"total[_\s-]*token[_\s-]*count[:=\s]+([\d,]+)", re.I),
        re.compile(r'"totalTokenCount"\s*:\s*([\d,]+)', re.I),
        re.compile(r'"tokenCount"\s*:\s*([\d,]+)', re.I),
        re.compile(r"\busage\b[^\n\r]*\btotal\b[^\d]{0,16}([\d,]+)", re.I),
    )
    _TOKEN_IN_PATTERNS = (
        re.compile(r"input\s+tokens?[:=\s]+([\d,]+)", re.I),
        re.compile(r"prompt\s+tokens?[:=\s]+([\d,]+)", re.I),
        re.compile(r'"inputTokenCount"\s*:\s*([\d,]+)', re.I),
        re.compile(r'"promptTokenCount"\s*:\s*([\d,]+)', re.I),
    )
    _TOKEN_OUT_PATTERNS = (
        re.compile(r"output\s+tokens?[:=\s]+([\d,]+)", re.I),
        re.compile(r"completion\s+tokens?[:=\s]+([\d,]+)", re.I),
        re.compile(r'"outputTokenCount"\s*:\s*([\d,]+)', re.I),
        re.compile(r'"candidatesTokenCount"\s*:\s*([\d,]+)', re.I),
        re.compile(r'"completionTokenCount"\s*:\s*([\d,]+)', re.I),
    )

    def _extract_tokens_from_text(text: str) -> Optional[int]:
        """Best-effort token extraction across Codex/Gemini output formats."""
        if not text or not text.strip():
            return None
        for pat in _TOKEN_TOTAL_PATTERNS:
            m = pat.search(text)
            if m:
                try:
                    return int(m.group(1).replace(",", ""))
                except ValueError:
                    continue

        in_count = None
        out_count = None
        for pat in _TOKEN_IN_PATTERNS:
            m = pat.search(text)
            if m:
                try:
                    in_count = int(m.group(1).replace(",", ""))
                    break
                except ValueError:
                    continue
        for pat in _TOKEN_OUT_PATTERNS:
            m = pat.search(text)
            if m:
                try:
                    out_count = int(m.group(1).replace(",", ""))
                    break
                except ValueError:
                    continue
        if in_count is not None and out_count is not None:
            return in_count + out_count
        if in_count is not None:
            return in_count
        if out_count is not None:
            return out_count
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

    def _run_permissions_from_env() -> Optional[bool]:
        raw = os.environ.get("COGEM_ALLOW_LOCAL_COMMANDS", "").strip().lower()
        if raw in ("1", "y", "yes", "true", "on"):
            return True
        if raw in ("0", "n", "no", "false", "off"):
            return False
        return None

    def ensure_run_permissions() -> None:
        """
        Ask once per session before running local commands (/run, /test, /lint, /github/clone).
        """
        if run_permissions["granted"] is not None:
            return
        v = _run_permissions_from_env()
        if v is not None:
            run_permissions["granted"] = v
            return
        if not sys.stdin.isatty():
            run_permissions["granted"] = False
            console.print(
                Text(
                    "[cogem] Non-interactive stdin: not prompting to run local commands. "
                    "Set COGEM_ALLOW_LOCAL_COMMANDS=yes to enable.",
                    style=LOG_WARN,
                )
            )
            return
        console.print()
        console.print(
            Text(
                "Local tools (/run, /test, /lint, /github/clone) may execute commands on your machine. "
                "Allow that for this cogem session?",
                style=MUTED,
            )
        )
        ans = console.input(Text("Allow local commands? [y/N]: ", style=TITLE)).strip().lower()
        run_permissions["granted"] = ans in ("y", "yes")
        if not run_permissions["granted"]:
            console.print(
                Text(
                    "Continuing with no local command execution. Use /ask or code-only turns instead.",
                    style=LOG_WARN,
                )
            )

    def _shlex_split_cmd(raw: str) -> List[str]:
        import shlex
        return shlex.split(raw, posix=os.name != "nt")

    def _contains_shell_operators(raw: str) -> bool:
        # Reject compound shell syntax to avoid injection when shell=False.
        forbidden = ("&&", "||", ";", "|", ">", "<", "`", "$(", "\n", "\r")
        return any(x in raw for x in forbidden)

    def _repo_root() -> str:
        # Prefer git to find a stable workspace root.
        try:
            proc = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                cwd=os.getcwd(),
            )
            if proc.returncode == 0 and (proc.stdout or "").strip():
                return proc.stdout.strip()
        except Exception:
            pass
        return os.getcwd()

    _RUN_ALLOW_EXECUTABLES = {
        "git",
        "python",
        "python3",
        "pytest",
        "ruff",
        "flake8",
        "black",
        "mypy",
        "node",
        "npm",
        "npx",
        "yarn",
        "pnpm",
        "go",
        "golangci-lint",
        "cargo",
        "make",
        "bash",
        "sh",
    }

    def _run_local_command(cmd_raw: str, label: str) -> Tuple[int, str, str]:
        ensure_run_permissions()
        if not run_permissions.get("granted"):
            return 1, "", "Local command execution denied by user permission."
        if not cmd_raw or not cmd_raw.strip():
            return 1, "", "Empty command."
        if _contains_shell_operators(cmd_raw):
            return 1, "", "Command rejected: compound shell syntax is not allowed."

        args = _shlex_split_cmd(cmd_raw.strip())
        if not args:
            return 1, "", "Empty command."
        exe = args[0]
        exe_name = os.path.basename(exe)
        if exe_name not in _RUN_ALLOW_EXECUTABLES:
            allow = ", ".join(sorted(_RUN_ALLOW_EXECUTABLES))
            return 1, "", f"Executable not allowed: {exe_name}. Allowed: {allow}"

        proc = _run_proc(args, cwd=_repo_root())
        return proc.returncode, proc.stdout or "", proc.stderr or ""

    def _read_json_file(path: str) -> Optional[dict]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _repo_has(rel_path: str) -> bool:
        return os.path.isfile(os.path.join(_repo_root(), rel_path))

    def _repo_has_dir(rel_path: str) -> bool:
        return os.path.isdir(os.path.join(_repo_root(), rel_path))

    def _detect_repo_kind() -> str:
        if _repo_has("package.json"):
            return "node"
        if _repo_has("pyproject.toml") or _repo_has("requirements.txt") or _repo_has("setup.cfg"):
            return "python"
        return "unknown"

    def _select_node_script(package_json: dict, key: str) -> Optional[str]:
        scripts = package_json.get("scripts")
        if not isinstance(scripts, dict):
            return None
        v = scripts.get(key)
        if isinstance(v, str) and v.strip():
            return key
        return None

    def _select_test_cmd() -> Optional[str]:
        kind = _detect_repo_kind()
        if kind == "node":
            pj = _read_json_file(os.path.join(_repo_root(), "package.json")) or {}
            if _select_node_script(pj, "test"):
                return "npm run test"
            return "npm test"
        if kind == "python":
            # Best-effort: use python -m pytest so it works even without a global pytest script.
            return "python -m pytest"
        return None

    def _select_lint_cmd() -> Optional[str]:
        kind = _detect_repo_kind()
        if kind == "node":
            pj = _read_json_file(os.path.join(_repo_root(), "package.json")) or {}
            if _select_node_script(pj, "lint"):
                return "npm run lint"
            if _select_node_script(pj, "eslint"):
                return "npm run eslint"
            return None
        if kind == "python":
            # Choose ruff first if available.
            if shutil.which("ruff"):
                return "python -m ruff check ."
            if shutil.which("flake8"):
                return "python -m flake8 ."
            return None
        return None

    def _codex_argv(prompt: str) -> List[str]:
        """codex exec with flags that avoid failing outside a git repo / trusted tree."""
        argv = ["codex", "exec", "--skip-git-repo-check"]
        if auto_permissions.get("granted"):
            argv.append("--full-auto")
        wd = os.environ.get("COGEM_CODEX_WORKDIR", "").strip()
        if wd:
            argv.extend(["-C", os.path.abspath(wd)])
        cm = models.get("codex")
        if cm:
            argv.extend(["-m", cm])
        argv.append(prompt)
        return argv

    def _gemini_argv(prompt: str) -> List[str]:
        argv = ["gemini"]
        if auto_permissions.get("granted"):
            argv.append("--yolo")
        gm = models.get("gemini")
        if gm:
            argv.extend(["-m", gm])
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

BUILD = the user wants software development work: writing or changing code, scripts, apps, sites, APIs, CLIs, configs, tests, migrations, refactors, bugfixes, performance work, security fixes, adding/removing features, generating project files, or any task where code or repo artifacts are the main deliverable. This includes "fix", "debug", "implement", "add", "remove", "migrate", "review my code", "set up", "configure", "dockerize", "write a script", "create a landing page", "API route", "schema", "SQL", "CSS", "HTML", "component", "endpoint", "handler", "middleware", "test case", "CI", "build error", "stack trace", "refactor", "optimize", "wire up", "hook up", "integrate with".

CHAT = conversational or informational only: greetings, thanks, small talk, definitions or explanations with NO request to change their project, general knowledge, career/life advice, "what is X" when they only want a conceptual answer and not code, comparing technologies without asking you to implement, meta questions about the assistant, or reading comprehension without producing project artifacts.

Disambiguation (important):
- "Explain how X works" with no repo/code task → usually CHAT. "Explain and then implement X" or "explain why my code fails" with code → BUILD.
- "What should I learn next?" → CHAT. "Add auth to my app" → BUILD.
- If they paste code and ask "is this correct?" or "find the bug" → BUILD (they need engineering help on code).
- If ambiguous and they might need code changes, prefer BUILD.

Ordered / multi-part requests (critical — read carefully):
- If the user asks for INFORMATION, SETUP, or HOW-TO *before* implementation (e.g. "before that tell me how…", "first explain how…", "I need to know X before we build Y", "build a site but first how do I connect…"), route as **CHAT** for this turn. Answer the prerequisite in the CHAT reply. They can run a build in a later message.
- Do **not** route as BUILD when the primary unsatisfied request is explanatory (MCP setup, tool connection, concepts) even if they also mention a future website or app build.
- Pure implementation with no unanswered prerequisite question → BUILD.

Programming language / stack: If they ask to use or switch language/framework/stack for implementation, that is BUILD.

ROUTING FORMAT (CRITICAL — machine-parsed):
- Line 1 must be ONLY the ASCII English word BUILD or CHAT (not translated, not localized). No other word on line 1.
- After line 1 you may write the CHAT reply in ordinary prose if mode is CHAT.

If still ambiguous, prefer BUILD when the message touches their codebase, errors, or deliverables; prefer CHAT for pure Q&A with no implementation.

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

    ROUTER_DIRECTIVE_HINTS = {
        "plan": (
            "[Directive /plan] The user wants planning or design guidance. "
            "Prefer BUILD if they need steps, file lists, or implementation-oriented output; "
            "CHAT only for purely conceptual Q&A with no project deliverable."
        ),
        "debug": (
            "[Directive /debug] The user is debugging. "
            "Prefer BUILD when logs, stack traces, repro, or code changes are involved; "
            "CHAT only for abstract theory with no code work."
        ),
        "agent": (
            "[Directive /agent] The user wants substantial autonomous implementation or multi-step work. "
            "Almost always BUILD unless they only asked for a short non-code opinion."
        ),
    }

    CODEX_MODE_HINTS = {
        "plan": (
            "\n## Session mode (/plan)\n"
            "Prioritize a clear plan: steps, milestones, risks, files to touch, and alternatives. "
            "Produce code or FILE: blocks only if the user asked for concrete edits; otherwise structured prose is fine.\n"
        ),
        "debug": (
            "\n## Session mode (/debug)\n"
            "Focus on root cause, minimal repro, targeted fixes, and verification. Avoid unrelated refactors.\n"
        ),
        "agent": (
            "\n## Session mode (/agent)\n"
            "Act as an autonomous coding agent: explore tradeoffs, coordinate multi-file changes, and complete the scoped work unless they narrowed the scope.\n"
        ),
    }

    ASK_MODE_PROMPT = """You are Cogem's conversational assistant (no full code pipeline this turn).

Saved context:
---
__MEMORY__
---

Answer the user in plain text. Do not use markdown code fences unless they explicitly asked for code.
Be concise. If they only need a short definition or opinion, keep it short.

If the user states identity, preferences, or asks you to remember something durable, add at the end exactly one line:
PERSIST note: <concise fact>
(or PERSIST stack: / PERSIST constraints: / PERSIST decision: when that fits better)
If nothing to persist, omit PERSIST lines.

User message:
---
__TASK__
---
"""

    _PERSIST_LINE = re.compile(
        r"^PERSIST\s+(note|stack|constraints|decision)\s*:\s*(.+?)\s*$",
        re.I,
    )

    def build_router_prompt(
        task: str, mem_block: str, router_hint: str = ""
    ) -> str:
        mem_ctx = mem_block.strip() if mem_block.strip() else "(none yet)"
        task_block = task
        if router_hint.strip():
            task_block = router_hint.strip() + "\n\n---\n\n" + task
        return ROUTER_TEMPLATE.replace("__MEMORY__", mem_ctx).replace(
            "__TASK__", task_block
        )

    _SESSION_DIRECTIVE = re.compile(
        r"^/(build|plan|debug|agent|ask)(?:\s+|$)(.*)$",
        re.I | re.DOTALL,
    )

    def parse_session_directive(raw: str) -> Tuple[str, Optional[str]]:
        """Strip one leading /build /plan /debug /agent /ask; return (rest, directive name or None)."""
        s = raw.strip()
        m = _SESSION_DIRECTIVE.match(s)
        if not m:
            return raw, None
        name = m.group(1).lower()
        rest = (m.group(2) or "").strip()
        return rest, name

    # (command, right-column description) — Codex-style two-column completion menu
    _SLASH_COMMANDS_META: Tuple[Tuple[str, str], ...] = (
        ("/build", "Force full implementation pipeline (skip BUILD/CHAT router)"),
        ("/plan", "Planning & milestones emphasis; router still classifies"),
        ("/debug", "Debugging & root-cause focus for this turn"),
        ("/agent", "Autonomous multi-step coding within your scope"),
        ("/ask", "Chat only — no Codex/Gemini build loop this turn"),
        ("/codex/model", "Show or set Codex LLM (draft + improve)"),
        ("/gemini/model", "Show or set Gemini LLM (review + summary)"),
        ("/repo/info", "Show repo info (git status, branch, last commit)"),
        ("/test", "Run project tests (best-effort; Python or Node)"),
        ("/lint", "Run project lint (best-effort; Python or Node)"),
        ("/run", "Run a local command (permission + allowlist enforced)"),
        ("/github/info", "Inspect public GitHub repository details"),
        ("/github/clone", "Clone a GitHub repo into current directory"),
    )
    _MAX_AT_COMPLETIONS = 500

    def _truncate_meta(s: str, max_len: int = 72) -> str:
        s = (s or "").strip()
        if len(s) <= max_len:
            return s
        return s[: max_len - 1] + "…"

    def _slash_task_prefix(text_before_cursor: str) -> Optional[str]:
        """Return current first-word slash token (e.g. '/build'), '' for empty line, or None."""
        if "\n" in text_before_cursor:
            return None
        t = text_before_cursor
        if not t.strip():
            return ""
        if t.endswith(" "):
            return None
        if len(t.split()) > 1:
            return None
        w = t.strip()
        if not w.startswith("/"):
            return None
        return w

    def _at_mention_segment(text_before_cursor: str) -> Optional[Tuple[int, str, bool]]:
        """Return (index after @, partial path, quoted) for completion, or None."""
        if "\n" in text_before_cursor:
            return None
        i = text_before_cursor.rfind("@")
        if i < 0:
            return None
        seg = text_before_cursor[i + 1 :]
        if seg.startswith('"'):
            m = re.match(r'^"([^"]*)$', seg)
            if m:
                return (i + 1, m.group(1), True)
            return None
        if " " in seg:
            return None
        return (i + 1, seg, False)

    def _complete_path_from_root(root: str, partial: str) -> List[str]:
        """Relative paths under root using forward slashes; partial is a path fragment."""
        try:
            root = os.path.realpath(root)
        except OSError:
            return []
        if not os.path.isdir(root):
            return []
        partial = partial.replace("\\", "/").rstrip("/")
        if not partial:
            out: List[str] = []
            try:
                entries = sorted(os.listdir(root))
            except OSError:
                return []
            for e in entries:
                if e.startswith("."):
                    continue
                full = os.path.join(root, e)
                rel = e
                if os.path.isdir(full):
                    rel += "/"
                out.append(rel)
            return out
        parent_rel = os.path.dirname(partial).replace("\\", "/")
        if parent_rel == ".":
            parent_rel = ""
        prefix = os.path.basename(partial)
        d = os.path.join(root, parent_rel) if parent_rel else root
        if not os.path.isdir(d):
            return []
        out = []
        try:
            entries = sorted(os.listdir(d))
        except OSError:
            return []
        for e in entries:
            if e.startswith("."):
                continue
            if prefix and not e.startswith(prefix):
                continue
            full = os.path.join(d, e)
            if parent_rel:
                rel = f"{parent_rel}/{e}".replace("\\", "/")
            else:
                rel = e
            if os.path.isdir(full):
                rel += "/"
            out.append(rel)
        return out

    def _complete_rel_paths_under_roots(partial: str) -> List[str]:
        merged: set[str] = set()
        for r in _mention_roots_list():
            for rel in _complete_path_from_root(r, partial):
                merged.add(rel)
        return sorted(merged)

    task_prompt_session = None
    if PromptSession is not None and Completer is not None and sys.stdin.isatty():

        # Per-item styles stack with class:completion-menu.* (see prompt_toolkit layout/menus.py).
        _CMP = "fg:#5ccfff"
        _CMP_SEL = "fg:#ffffff bg:#345070 bold noreverse"

        class CogemCompleter(Completer):
            def get_completions(self, document, complete_event):
                from prompt_toolkit.completion import Completion

                before = document.text_before_cursor
                info = _at_mention_segment(before)
                if info is not None:
                    start_i, partial, quoted = info
                    seg_replace = before[start_i:]
                    rels = _complete_rel_paths_under_roots(partial)
                    for rel in rels[:_MAX_AT_COMPLETIONS]:
                        if quoted:
                            text = '"' + rel + '"'
                            disp = text
                        else:
                            text = rel
                            disp = rel
                        if rel.endswith("/"):
                            meta = "Directory — tree listing in BUILD prompts"
                        else:
                            meta = "File — contents inlined in BUILD prompts"
                        yield Completion(
                            text,
                            start_position=-len(seg_replace),
                            display=disp,
                            display_meta=_truncate_meta(meta),
                            style=_CMP,
                            selected_style=_CMP_SEL,
                        )
                    return

                sp = _slash_task_prefix(before)
                if sp is None:
                    return
                if sp == "" and not before.strip():
                    for cmd, desc in _SLASH_COMMANDS_META:
                        yield Completion(
                            cmd,
                            start_position=0,
                            display=cmd,
                            display_meta=_truncate_meta(desc),
                            style=_CMP,
                            selected_style=_CMP_SEL,
                        )
                    return
                slash_start = before.find("/")
                if slash_start < 0:
                    return
                replace_len = len(before) - slash_start
                for cmd, desc in _SLASH_COMMANDS_META:
                    if sp and not cmd.startswith(sp):
                        continue
                    yield Completion(
                        cmd,
                        start_position=-replace_len,
                        display=cmd,
                        display_meta=_truncate_meta(desc),
                        style=_CMP,
                        selected_style=_CMP_SEL,
                    )

        # Defaults use light grey (#bbbbbb) + `reverse` on selection — override fully for a dark Codex-like menu.
        _completion_style = (
            Style.from_dict(
                {
                    "completion-menu": "bg:#000000 #cccccc",
                    "completion-menu.completion": "noreverse",
                    "completion-menu.completion.current": "noreverse",
                    "completion-menu.meta.completion": "noreverse",
                    "completion-menu.meta.completion.current": "noreverse",
                    "completion-toolbar": "bg:#1a1a1a #888888",
                    "completion-toolbar.completion": "fg:#5ccfff",
                    "completion-toolbar.completion.current": "fg:#ffffff bg:#345070",
                }
            )
            if Style is not None
            else None
        )

        _cd = None
        if ColorDepth is not None and (
            os.environ.get("COGEM_NO_TRUE_COLOR", "").strip().lower()
            not in ("1", "true", "yes")
        ):
            _cd = ColorDepth.TRUE_COLOR

        _task_prompt_keys = KeyBindings()

        @_task_prompt_keys.add("enter")
        def _enter_handler(event):
            """
            Enter submits; Shift+Enter inserts a newline.

            Note: prompt_toolkit may map Shift+Enter to the same key as Enter.
            We disambiguate using event.data, where terminals typically send
            the ANSI sequence "\x1b[27;2;13~" for Shift+Enter.
            """
            d = event.data or ""
            if "27;2;13" in d or "\x1b[27;2;13" in d:
                event.current_buffer.insert_text("\n")
                return
            event.current_buffer.validate_and_handle()

        @_task_prompt_keys.add("s-tab")
        def _shift_tab_handler(event):
            # Shift+Tab cycles completions backwards (command/path dropdown).
            try:
                event.current_buffer.complete_previous()
            except Exception:
                pass

        task_prompt_session = PromptSession(
            completer=CogemCompleter(),
            history=InMemoryHistory(),
            multiline=True,
            complete_while_typing=True,
            complete_style=CompleteStyle.COLUMN,
            style=_completion_style,
            color_depth=_cd,
            reserve_space_for_menu=14,
            prompt_continuation="  ... ",
            key_bindings=_task_prompt_keys,
        )

    def read_task_line(prompt: str = "What would you like to do? ") -> str:
        if task_prompt_session is not None:
            try:
                return task_prompt_session.prompt(prompt).strip()
            except (EOFError, KeyboardInterrupt):
                raise
        prompt_label = Text(prompt, style=TITLE)
        return console.input(prompt_label).strip()

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

    try:
        with open(os.path.join(AI_PATH, "STITCH_WEBSITE.md"), encoding="utf-8") as f:
            STITCH_WEBSITE_RULES = f.read()
    except OSError:
        STITCH_WEBSITE_RULES = ""

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
                console.print(
                    Text(
                        _llm_status_line(
                            "Codex LLM (draft + improve)",
                            "codex",
                            models.get("codex"),
                        ),
                        style=MUTED,
                    )
                )
                console.print(
                    Text(
                        _llm_status_line(
                            "Gemini LLM (review + summary)",
                            "gemini",
                            models.get("gemini"),
                        ),
                        style=MUTED,
                    )
                )
                console.print(
                    Text(
                        "Session: /build /plan /debug /agent /ask   "
                        "/codex/model <MODEL_ID|reset>   "
                        "/gemini/model <MODEL_ID|reset>   "
                        "/repo/info /test /lint   "
                        "/run <cmd>   "
                        "/github/info <url|owner/repo>   "
                        "/github/clone <url|owner/repo> [dest]   "
                        "@path @folder   (Tab completes / and @)",
                        style=MUTED,
                    )
                )
                console.print()
                first_turn = False
            else:
                console.print()
                console.print(Rule(style=BORDER))
                console.print(Text("Next", style=TITLE))
                console.print(Rule(style=BORDER))
                console.print()

            # ---------- input (prompt_toolkit: / and @ dropdown when TTY) ----------

            task = read_task_line()

            if not task:
                console.print(
                    Text(
                        "No input — type a task when you're ready.",
                        style=MUTED,
                    )
                )
                continue

            if task.startswith("/codex/model"):
                rest = task[len("/codex/model"):].strip()
                if not rest:
                    console.print(
                        Text(
                            "Codex LLM — used for drafting and improving code (`codex exec -m …`). "
                            "Pick any model ID your Codex CLI supports (varies by account; e.g. o3, gpt-5, "
                            "or provider-specific names). Gemini is configured separately with /gemini/model.",
                            style=MUTED,
                        )
                    )
                    console.print(
                        Text(
                            f"  This session: {models.get('codex') or 'default (no -m)'}",
                            style=MUTED,
                        )
                    )
                    console.print(
                        Text(
                            f"  From startup (--codex-model / COGEM_CODEX_MODEL): {_codex_model or '(none)'}",
                            style=MUTED,
                        )
                    )
                    console.print(
                        Text(
                            "  Usage: /codex/model <MODEL_ID>   or   /codex/model reset",
                            style=MUTED,
                        )
                    )
                    continue
                if rest.lower() == "reset":
                    models["codex"] = _codex_model
                    console.print(
                        Text(
                            f"Codex LLM reset to: {models.get('codex') or 'default (no -m)'}",
                            style=TITLE,
                        )
                    )
                    continue
                models["codex"] = rest
                console.print(Text(f"Codex LLM set to: {rest}", style=TITLE))
                continue

            if task.startswith("/gemini/model"):
                rest = task[len("/gemini/model"):].strip()
                if not rest:
                    console.print(
                        Text(
                            "Gemini LLM — used for review and final summary (`gemini -m …`). "
                            "Pick any model ID your Gemini CLI supports (e.g. gemini-2.5-pro, "
                            "gemini-2.5-flash). Codex is configured separately with /codex/model.",
                            style=MUTED,
                        )
                    )
                    console.print(
                        Text(
                            f"  This session: {models.get('gemini') or 'default (no -m)'}",
                            style=MUTED,
                        )
                    )
                    console.print(
                        Text(
                            f"  From startup (--gemini-model / COGEM_GEMINI_MODEL): {_gemini_model or '(none)'}",
                            style=MUTED,
                        )
                    )
                    console.print(
                        Text(
                            "  Usage: /gemini/model <MODEL_ID>   or   /gemini/model reset",
                            style=MUTED,
                        )
                    )
                    continue
                if rest.lower() == "reset":
                    models["gemini"] = _gemini_model
                    console.print(
                        Text(
                            f"Gemini LLM reset to: {models.get('gemini') or 'default (no -m)'}",
                            style=TITLE,
                        )
                    )
                    continue
                models["gemini"] = rest
                console.print(Text(f"Gemini LLM set to: {rest}", style=TITLE))
                continue

            if task.startswith("/repo/info"):
                root = _repo_root()
                console.print()
                section_rule("Repo info")
                console.print()
                console.print(Text(f"Repo root: {root}", style=MUTED))
                try:
                    proc_inside = subprocess.run(
                        ["git", "rev-parse", "--is-inside-work-tree"],
                        capture_output=True,
                        text=True,
                        cwd=root,
                    )
                    inside = (proc_inside.stdout or "").strip().lower() == "true"
                except Exception:
                    inside = False
                if not inside:
                    console.print(Text("Git: not a git repository (or git unavailable).", style=LOG_WARN))
                    console.print()
                    continue
                try:
                    proc_branch = subprocess.run(
                        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                        capture_output=True,
                        text=True,
                        cwd=root,
                    )
                    branch = (proc_branch.stdout or "").strip() or "(unknown)"
                    console.print(Text(f"Git branch: {branch}", style=MUTED))
                except Exception:
                    pass
                try:
                    proc_last = subprocess.run(
                        ["git", "log", "-1", "--oneline"],
                        capture_output=True,
                        text=True,
                        cwd=root,
                    )
                    last = (proc_last.stdout or "").strip()
                    if last:
                        console.print(Text(f"Last commit: {last}", style=MUTED))
                except Exception:
                    pass
                try:
                    proc_status = subprocess.run(
                        ["git", "status", "--porcelain"],
                        capture_output=True,
                        text=True,
                        cwd=root,
                    )
                    status = (proc_status.stdout or "").strip()
                    console.print(Text("Working tree status (git --porcelain):", style=MUTED))
                    console.print(status or "(clean)")
                except Exception:
                    pass
                console.print()
                continue

            if task.startswith("/test"):
                cmd = _select_test_cmd()
                console.print()
                section_rule("Tests")
                if not cmd:
                    console.print(Text("No known test command for this repo type.", style=LOG_WARN))
                    console.print()
                    continue
                rc, out, err = _run_local_command(cmd, "tests")
                if out.strip():
                    console.print(out.strip())
                if rc != 0 and (err or "").strip():
                    console.print(Text(err.strip()[:2000], style=LOG_WARN))
                continue

            if task.startswith("/lint"):
                cmd = _select_lint_cmd()
                console.print()
                section_rule("Lint")
                if not cmd:
                    console.print(Text("No known lint command for this repo type.", style=LOG_WARN))
                    console.print()
                    continue
                rc, out, err = _run_local_command(cmd, "lint")
                if out.strip():
                    console.print(out.strip())
                if rc != 0 and (err or "").strip():
                    console.print(Text(err.strip()[:2000], style=LOG_WARN))
                continue

            if task.startswith("/run"):
                rest = task[len("/run"):].strip()
                if not rest:
                    console.print(Text("Usage: /run <command + args>", style=MUTED))
                    continue
                rc, out, err = _run_local_command(rest, "run")
                console.print()
                section_rule("Command output")
                if out.strip():
                    console.print(out.strip())
                if (err or "").strip():
                    console.print(Text((err or "").strip()[:2000], style=LOG_WARN))
                console.print()
                continue

            if task.startswith("/github/info"):
                rest = task[len("/github/info"):].strip()
                if not rest:
                    console.print(
                        Text("Usage: /github/info <https://github.com/owner/repo or owner/repo>", style=MUTED)
                    )
                    continue
                owner, repo, _clone_url = _parse_github_repo_ref(rest)
                if not owner or not repo:
                    console.print(Text("Could not parse GitHub repository reference.", style=LOG_WARN))
                    continue
                console.print()
                info = _github_repo_info(owner, repo)
                section_rule("GitHub repository info")
                console.print()
                console.print(info)
                console.print()
                continue

            if task.startswith("/github/clone"):
                rest = task[len("/github/clone"):].strip()
                if not rest:
                    console.print(
                        Text("Usage: /github/clone <https://github.com/owner/repo or owner/repo> [dest]", style=MUTED)
                    )
                    continue
                parts = rest.split()
                ref = parts[0].strip()
                dest = parts[1].strip() if len(parts) > 1 else ""
                owner, repo, clone_url = _parse_github_repo_ref(ref)
                if not owner or not repo or not clone_url:
                    console.print(Text("Could not parse GitHub repository reference.", style=LOG_WARN))
                    continue
                target_dir = dest or repo
                if os.path.lexists(target_dir):
                    console.print(Text(f"Target already exists: {target_dir}", style=LOG_WARN))
                    continue
                ensure_run_permissions()
                if not run_permissions.get("granted"):
                    console.print(Text("Local command execution denied by user permission.", style=LOG_WARN))
                    console.print()
                    continue
                proc = _run_with_ascii_progress(
                    "git clone",
                    lambda: _run_proc(["git", "clone", clone_url, target_dir], cwd=os.getcwd()),
                )
                if proc.returncode == 0:
                    console.print(Text(f"Cloned {owner}/{repo} -> {target_dir}", style=LOG_OK))
                else:
                    console.print(Text("Git clone failed.", style=LOG_ERR))
                    if (proc.stderr or "").strip():
                        clip = (proc.stderr or "").strip()[:1200]
                        if len((proc.stderr or "").strip()) > 1200:
                            clip += "..."
                        console.print(Text(clip, style=LOG_WARN))
                console.print()
                continue

            task, session_directive = parse_session_directive(task)
            task_clean, attach_block = expand_at_mentions(task)
            if attach_block:
                n_refs = attach_block.count("### ")
                console.print(
                    Text(
                        f"Loaded {n_refs} path(s) from @ mentions into build context.",
                        style=MUTED,
                    )
                )
                console.print()

            session_tokens["codex"] = 0
            session_tokens["gemini"] = 0

            ensure_auto_permissions()

            mode_hint = CODEX_MODE_HINTS.get(session_directive or "", "")

            # ---------- /ask: conversational only (skip router + build pipeline) ----------
            if session_directive == "ask":
                mem_ctx = mem_block.strip() if mem_block.strip() else "(none yet)"
                ask_task_body = (attach_block or "") + (task_clean or "(no message)")
                ask_raw, ask_err, ask_rc = run_codex(
                    ASK_MODE_PROMPT.replace("__MEMORY__", mem_ctx).replace(
                        "__TASK__", ask_task_body
                    ),
                    "Codex: /ask reply...",
                )
                if ask_rc != 0:
                    console.print()
                    _say(f"[cogem] ERROR: Codex exited with code {ask_rc} for /ask.")
                    if (ask_err or "").strip():
                        console.print(
                            Text((ask_err or "").strip()[:800], style=LOG_ERR)
                        )
                    console.print()
                    _token_turn_footer()
                    continue
                chat_reply = ask_raw.strip()
                chat_reply, auto_persists = extract_persist_directives(chat_reply)
                apply_persist_directives(memory, auto_persists)
                trace_done("Direct /ask reply ready.")
                live_reasoning_banner_chat(task or "/ask")
                section_rule("Reply (/ask)")
                console.print()
                console.print(chat_reply or "(empty reply)")
                console.print()
                _token_turn_footer()
                _say("[cogem] Turn finished. What would you like to do next?")
                continue

            if not (task or "").strip() and not attach_block:
                if session_directive == "build":
                    console.print(
                        Text(
                            "Add a description after /build, or use @path to point at files.",
                            style=MUTED,
                        )
                    )
                else:
                    console.print(
                        Text(
                            "No task text — describe what you want or use @file.",
                            style=MUTED,
                        )
                    )
                continue

            router_hint = ROUTER_DIRECTIVE_HINTS.get(session_directive or "", "")

            # ---------- /build: skip router ----------
            if session_directive == "build":
                mode = "workflow"
                chat_reply = None
                trace_done(
                    "Directive /build: skipping classifier; running the full build pipeline."
                )
            else:
                trace_doing(
                    "I'm having Codex classify this turn: full build pipeline versus a direct conversational reply (using your text and saved context)."
                )
                router_raw, router_err, router_rc = run_codex(
                    build_router_prompt(task_clean, mem_block, router_hint),
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
                if (
                    mode == "chat"
                    and looks_like_build_task(task_clean)
                    and not detect_prerequisite_first_task(task_clean)
                ):
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
                pr_raw, pr_err, pr_rc = run_codex(
                    build_prerequisite_first_prompt(task_clean, mem_block),
                    "Codex: answering prerequisite question first...",
                )
                if pr_rc != 0:
                    trace_done(
                        "Prerequisite answer step failed; fix the error below, then retry or use /ask."
                    )
                    console.print()
                    _say(f"[cogem] ERROR: Codex exited with code {pr_rc}.")
                    if (pr_err or "").strip():
                        clip = (pr_err or "").strip()[:1200]
                        if len((pr_err or "").strip()) > 1200:
                            clip += "..."
                        console.print(Text(clip, style=LOG_ERR))
                    console.print()
                    _token_turn_footer()
                    continue
                mode = "chat"
                chat_reply = (pr_raw or "").strip()
                trace_done(
                    "Prerequisite reply ready; skipping build/Stitch for this turn — ask for the build again when ready."
                )

            if mode == "chat":
                if attach_block:
                    console.print(
                        Text(
                            "@ file/folder mentions are only inlined for BUILD tasks; "
                            "they were not sent to this chat reply.",
                            style=MUTED,
                        )
                    )
                    console.print()
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

            frontend_detected = detect_frontend_task(task_clean)
            prereq_first = detect_prerequisite_first_task(task_clean)
            stitch_block = ""
            stitch_rules_extra = ""
            if frontend_detected and STITCH_WEBSITE_RULES.strip():
                stitch_rules_extra = (
                    "\n\n## STITCH_WEBSITE rules (strict)\n"
                    + STITCH_WEBSITE_RULES
                    + "\n"
                )

            trace_done(
                "Pipeline gating: "
                f"mode={mode}, frontend_detected={frontend_detected}, "
                f"prerequisite_first={prereq_first}, stitch_feature_on={stitch_feature_on}, "
                f"session_directive={session_directive or '(none)'}"
            )

            if (
                stitch_feature_on
                and mode == "workflow"
                and frontend_detected
                and (not prereq_first or session_directive == "build")
            ):
                if should_skip_stitch_due_to_attachments(attach_block):
                    trace_done(
                        "Frontend task detected; skipping Stitch because @ attachments already include UI/HTML."
                    )
                else:
                    trace_doing(
                        "Frontend-heavy task detected; running the Google Stitch stage (adapter or manual handoff)."
                    )
                    stitch_prompt = build_stitch_prompt(task_clean)
                    sr = try_stitch_adapters(stitch_prompt)
                    if sr.mode == "direct" and sr.content:
                        stitch_block = format_stitch_context_for_codex(sr.content)
                        trace_done(
                            f"Stitch: received UI via adapter ({sr.adapter_name}). Continuing with Codex + Gemini."
                        )
                    else:
                        reason = (sr.detail or "").strip()
                        if reason:
                            reason = reason.replace("\n", " ")[:220]
                            trace_done(
                                "Stitch: direct integration unavailable; using manual handoff "
                                f"(reason: {reason})."
                            )
                        else:
                            trace_done(
                                "Stitch: direct integration unavailable; using manual handoff (prompt + export)."
                            )
                        console.print()
                        section_rule("Stitch prompt (copy into Google Stitch)")
                        console.print()
                        console.print(stitch_prompt)
                        console.print()
                        console.print(
                            Text(
                                "Stitch manual fallback.\n"
                                "1) In Stitch, export the generated frontend (HTML/CSS, or a bundled HTML that includes styles).\n"
                                "2) Paste it below (preferred: the main HTML, plus any CSS/JS it depends on).\n"
                                "3) Or provide `@path/to/export.html` / `@path/to/export.css`.\n"
                                "Press Enter on an empty line to skip.",
                                style=MUTED,
                            )
                        )
                        console.print()
                        if not sys.stdin.isatty():
                            console.print(
                                Text(
                                    "Non-interactive stdin: cannot prompt for Stitch paste. "
                                    "Set COGEM_STITCH_CLI or COGEM_STITCH_HTTP_URL, or run cogem in a real terminal.",
                                    style=MUTED,
                                )
                            )
                            trace_done(
                                "Skipping Stitch paste; continuing without Stitch HTML."
                            )
                        else:
                            stitch_in = read_task_line(
                                "Stitch export — paste code or @path (Enter to skip): "
                            )
                            if stitch_in.strip():
                                if looks_like_ui_content(stitch_in):
                                    stitch_block = format_stitch_context_for_codex(stitch_in)
                                else:
                                    _c2, attach_s = expand_at_mentions(stitch_in)
                                    if attach_s:
                                        stitch_block = (
                                            "\n\n---\n\n## Stitch / UI source (from your files)\n\n"
                                            + attach_s
                                        )
                                    else:
                                        stitch_block = format_stitch_context_for_codex(stitch_in)
                                trace_done(
                                    "Stitch export captured; continuing with Codex draft using this UI context."
                                )
                            else:
                                trace_done(
                                    "No Stitch export; Codex will draft from your task alone (no Stitch HTML)."
                                )

            # ---------- generate ----------

            trace_doing(
                "I'm calling Codex with your task, CODEX.md rules, and any saved memory so I can get a first implementation pass."
            )
            raw, draft_err, draft_rc = run_codex(
                f"{mem_block}{attach_block}{stitch_block}{stitch_rules_extra}{mode_hint}{CODEX_RULES}\n\nTASK:\n{task_clean}\n",
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
                f"{mem_block}{attach_block}{stitch_block}{stitch_rules_extra}{mode_hint}{GEMINI_RULES}\n\nCODE:\n{code}",
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
{mem_block}{attach_block}{stitch_block}{stitch_rules_extra}{mode_hint}{CODEX_RULES}

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
{mem_block}{attach_block}{stitch_block}{stitch_rules_extra}{mode_hint}{GEMINI_RULES}

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

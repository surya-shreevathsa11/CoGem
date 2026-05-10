#!/usr/bin/env python3
from dataclasses import dataclass
from typing import List

from clogem import artifacts as artifact_helpers
from clogem.config import Settings
from clogem.logging_utils import get_logger
from clogem import prompts as prompt_defs
from clogem.memory import MemoryStore
from clogem.ui import boot_sequence

logger = get_logger(__name__)


@dataclass
class SubTask:
    id: str
    description: str
    target_files: List[str]
    status: str


async def async_main():
    import asyncio
    import contextvars
    import argparse
    import json
    import subprocess
    import re
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
    from typing import Dict, List, Optional, Set, Tuple

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

    from clogem.stitch import detect_stitch_frontend_heavy_task
    from clogem.stitch.adapters import looks_like_ui_content
    from clogem.task_intent import build_prerequisite_first_prompt, detect_prerequisite_first_task
    from clogem.write_safety import apply_unified_diff_safely, plan_safe_writes
    from clogem.command_policy import ALLOWED_EXECUTABLES, validate_local_command_args
    from clogem.llm_clients import (
        claude_generate,
        claude_generate_async,
        gemini_generate,
        gemini_generate_async,
        gemini_generate_with_google_search,
        gemini_generate_with_google_search_async,
        gemini_generate_with_image,
        gemini_generate_with_image_async,
        openai_generate,
        openai_generate_async,
    )
    from clogem.role_mapping import needed_providers, resolve_role_provider_map
    from clogem.services.commands import handle_pre_pipeline_command
    from clogem.services.contracts import (
        CommandContext,
        StitchStageDeps,
        StitchStageRequest,
        StitchStageUI,
        TurnModeDeps,
        TurnModeRequest,
        TurnModeUI,
    )
    from clogem.services.pipeline import build_context_blocks, maybe_run_stitch_stage
    from clogem.services.realtime_intent import (
        build_realtime_gemini_prompt,
        local_datetime_context_block,
        needs_realtime_web_assist,
    )
    from clogem.services.routing import parse_session_directive, resolve_turn_mode
    from clogem.visual_review import capture_frontend_screenshot

    _ap = argparse.ArgumentParser(
        prog="clogem",
        description="Clogem: Codex + Gemini dual-agent loop (generate, review, improve).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "LLM models are chosen separately for Codex (draft/improve) and Gemini (review/summary).\n"
            "Omit both flags to let each CLI use its default model (no -m passed).\n"
            "\n"
            "Examples:\n"
            "  clogem\n"
            "  clogem --codex-model o3 --gemini-model gemini-2.5-pro\n"
            "  clogem --role-provider coder=claude --claude-model claude-sonnet-4-6\n"
            "\n"
            "Env (when flags omitted): CLOGEM_CODEX_MODEL, CLOGEM_GEMINI_MODEL, CLOGEM_CLAUDE_MODEL\n"
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
        "--claude-model",
        metavar="MODEL_ID",
        default=None,
        help=(
            "LLM for Claude SDK calls. Omit to use CLOGEM_CLAUDE_MODEL/CLOGEM_CLAUDE_SDK_MODEL "
            "or the built-in default."
        ),
    )
    _ap.add_argument(
        "--role-provider",
        metavar="ROLE=PROVIDER",
        action="append",
        default=[],
        help=(
            "Map a role to a provider; repeatable. Roles: orchestrator, planner, coder, reviewer, summariser. "
            "Providers: codex, gemini, claude."
        ),
    )
    _ap.add_argument(
        "--no-stitch",
        action="store_true",
        help=(
            "Disable the Google Stitch stage for UI-heavy tasks (see CLOGEM_STITCH env)."
        ),
    )
    _ap.add_argument(
        "--validation-docker",
        action="store_true",
        help=(
            "Prefer Docker-based validation (tests/lint/typecheck) when available, "
            "fallback to the tempfile filesystem sandbox otherwise."
        ),
    )
    _args = _ap.parse_args()
    _codex_model = (_args.codex_model or os.environ.get("CLOGEM_CODEX_MODEL") or "").strip() or None
    _gemini_model = (_args.gemini_model or os.environ.get("CLOGEM_GEMINI_MODEL") or "").strip() or None
    _claude_model = (_args.claude_model or os.environ.get("CLOGEM_CLAUDE_MODEL") or "").strip() or None
    settings = Settings.from_env()

    loop = asyncio.get_running_loop()

    def _loop_exception_handler(_loop, context) -> None:
        exc = context.get("exception")
        msg = str(context.get("message") or "")
        txt = f"{msg}\n{exc or ''}".lower()
        # Suppress known google-genai async cleanup noise for end users.
        if (
            "task exception was never retrieved" in txt
            and "baseapiclient" in txt
            and "_async_httpx_client" in txt
        ):
            logger.debug(
                "Suppressed google-genai async cleanup exception noise",
                exc_info=True,
            )
            return
        _loop.default_exception_handler(context)

    loop.set_exception_handler(_loop_exception_handler)

    role_provider_map = resolve_role_provider_map(
        env_map_raw=os.environ.get("CLOGEM_ROLE_PROVIDER_MAP", ""),
        cli_pairs=list(_args.role_provider or []),
    )
    stitch_feature_on = (not _args.no_stitch) and (
        (os.environ.get("CLOGEM_STITCH") or "1").strip().lower()
        not in ("0", "false", "no", "off", "disabled")
    )

    validation_docker_requested = bool(_args.validation_docker) or settings.validation_docker
    require_docker_for_validation = settings.strict_sandbox

    if not await asyncio.to_thread(boot_sequence, needed_providers(role_provider_map)):
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
    session_tokens = {"codex": 0, "gemini": 0, "claude": 0}
    # None = not asked yet; True/False = user chose whether to pass Codex --full-auto and Gemini --yolo.
    auto_permissions: dict = {"granted": None}
    # None = not asked yet; True/False = user chose whether clogem can execute local shell commands (/run, /test, /lint, /github/clone).
    run_permissions: dict = {"granted": None}
    # Effective LLM IDs for this process (separate per backend); from CLI/env, change with /codex/model and /gemini/model.
    models: dict = {"codex": _codex_model, "gemini": _gemini_model, "claude": _claude_model}

    def _llm_status_line(human: str, cli_hint: str, model_id: Optional[str]) -> str:
        """human = short label; cli_hint = codex|gemini for messages."""
        if model_id:
            return f"{human}: {model_id}"
        return (
            f"{human}: default (clogem does not pass -m; `{cli_hint}` CLI default model)"
        )

    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    AI_PATH = os.path.join(ROOT, ".ai")
    MEMORY_PATH = os.path.join(ROOT, "memory.json")

    memory_store = MemoryStore(MEMORY_PATH)

    def load_memory():
        return memory_store.load()

    def save_memory(data):
        memory_store.save(data)

    def format_memory_for_prompt(mem):
        return memory_store.format_for_prompt(mem)

    # @ mention parser (quoted and unquoted paths). Image mentions are parsed from this
    # stream as regular @ paths and then filtered by extension (.png/.jpg/.webp).
    _AT_MENTION = re.compile(r'@"([^"]+)"|@\'([^\']+)\'|@([^\s@]+)')

    def _is_supported_image_path(path: str) -> bool:
        p = (path or "").lower()
        return p.endswith(".png") or p.endswith(".jpg") or p.endswith(".jpeg") or p.endswith(".webp")

    def extract_image_mentions(raw: str) -> List[str]:
        """
        Resolve @image mentions from raw task text to absolute paths under allowed roots.
        Supported extensions: .png, .jpg/.jpeg, .webp
        """
        if "@" not in (raw or ""):
            return []
        roots = _mention_roots_list()
        out: List[str] = []
        seen: Set[str] = set()
        for m in _AT_MENTION.finditer(raw or ""):
            rel = (m.group(1) or m.group(2) or m.group(3) or "").strip()
            if not rel or not _is_supported_image_path(rel):
                continue
            abs_p = _resolve_mention_path(rel)
            if not abs_p:
                continue
            if not _path_allowed_for_mention(abs_p, roots):
                continue
            if not os.path.isfile(abs_p):
                continue
            rp = os.path.realpath(abs_p)
            if rp in seen:
                continue
            seen.add(rp)
            out.append(rp)
        return out

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
        wd = os.environ.get("CLOGEM_CODEX_WORKDIR", "").strip()
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
            wd = os.environ.get("CLOGEM_CODEX_WORKDIR", "").strip()
            if wd:
                candidates.append(os.path.join(wd, rel))
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
            max_pages = max(1, int(os.environ.get("CLOGEM_AT_MAX_PDF_PAGES", "30")))
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
                out_parts.append("\n\n[pdf text truncated by CLOGEM_AT_MAX_FILE_BYTES]")
                break
            out_parts.append(block)
            total += len(block)
        if total_pages > show_pages:
            out_parts.append(
                f"\n\n[pdf pages truncated: showing {show_pages}/{total_pages}; "
                f"set CLOGEM_AT_MAX_PDF_PAGES to increase]"
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
                + "\n\n[truncated: file exceeds CLOGEM_AT_MAX_FILE_BYTES]"
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
            max_b = max(4096, int(os.environ.get("CLOGEM_AT_MAX_FILE_BYTES", "400000")))
        except ValueError:
            max_b = 400000
        try:
            max_total = max(8000, int(os.environ.get("CLOGEM_AT_MAX_TOTAL_CHARS", "120000")))
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
        symbol_index_enabled = (
            os.environ.get("CLOGEM_SYMBOL_INDEX", "1").strip().lower()
            not in ("0", "false", "no", "off", "disabled")
        )
        symbol_index_cache = getattr(expand_at_mentions, "_symbol_index_cache", None)
        for rel in paths_order:
            if rel in seen:
                continue
            seen.add(rel)
            abs_p = _resolve_mention_path(rel)
            if not abs_p or not _path_allowed_for_mention(abs_p, roots):
                # Symbol resolution (ctags/universal-ctags) best-effort:
                # allow `@MyClassName` to inline the definition snippet.
                injected_symbol = False
                if symbol_index_enabled:
                    try:
                        from clogem.symbols import SymbolIndex

                        if symbol_index_cache is None:
                            symbol_index_cache = SymbolIndex(_repo_root())
                            setattr(
                                expand_at_mentions,
                                "_symbol_index_cache",
                                symbol_index_cache,
                            )
                        res = symbol_index_cache.resolve_symbol_to_snippet(
                            rel, context_lines=20, max_chars=max_b
                        )
                        if res and _path_allowed_for_mention(res.tag.path, roots):
                            try:
                                label = os.path.relpath(res.tag.path, ROOT)
                            except ValueError:
                                label = res.tag.path
                            block = (
                                f"### @{rel} (symbol in {label}:{res.start_line}-{res.end_line})\n"
                                f"```\n{res.snippet}\n```\n\n"
                            )
                            if total + len(block) <= max_total:
                                chunks.append(block)
                                total += len(block)
                                injected_symbol = True
                    except Exception:
                        injected_symbol = False

                if injected_symbol:
                    continue

                chunks.append(
                    f"### @{rel}\nNot found or not allowed (paths must stay under the project, "
                    f"current working directory, or CLOGEM_CODEX_WORKDIR).\n\n"
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
                    f"[@ context truncated: total size exceeds CLOGEM_AT_MAX_TOTAL_CHARS={max_total}]\n"
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
            headers={"Accept": "application/vnd.github+json", "User-Agent": "clogem-cli"},
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
                f"[clogem] Tokens (~{provider} this call): {n}  "
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
                    "[clogem] Token usage: no counts found in CLI output this turn "
                    "(free-tier CLIs often omit usage; check provider dashboards if needed).",
                    style=MUTED,
                )
            )
        else:
            console.print(
                Text(
                    f"[clogem] Token estimates this turn (parsed from CLI text): "
                    f"codex ~{c}, gemini ~{g}",
                    style=MUTED,
                )
            )

    def _subprocess_timeout_sec() -> Optional[int]:
        return settings.subprocess_timeout_sec

    def _task_preview(task: str, max_len: int = 90) -> str:
        preview = re.sub(r"\s+", " ", task.strip())
        if len(preview) > max_len:
            preview = preview[: max_len - 3] + "..."
        return preview

    def _say(msg: str) -> None:
        """Colored narration (Rich); readable in every terminal that supports ANSI."""
        if msg.startswith("[clogem] START:"):
            console.print(Text(msg, style=LOG_START))
        elif msg.startswith("[clogem] DONE:"):
            console.print(Text(msg, style=LOG_DONE))
        elif msg.startswith("[clogem] WARNING"):
            console.print(Text(msg, style=LOG_WARN))
        elif msg.startswith("[clogem] ERROR"):
            console.print(Text(msg, style=LOG_ERR))
        elif msg.startswith("[clogem]"):
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
        _say("[clogem] Thinking (build)")
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
        _say("[clogem] Thinking (conversation)")
        _say(f"  request: {preview}")
        _say("  next: showing routed reply below (no code pipeline).")
        _say("")

    def trace_doing(msg: str) -> None:
        _say(f"  {_wall_clock()} > {msg}")

    def trace_done(msg: str) -> None:
        _say(f"  {_wall_clock()} ok {msg}")

    async def trace_doing_async(msg: str) -> None:
        await asyncio.to_thread(trace_doing, msg)

    async def trace_done_async(msg: str) -> None:
        await asyncio.to_thread(trace_done, msg)

    def section_heading(label: str) -> None:
        _say("")
        _say(f"---------- {label} ----------")

    def section_rule(label: str) -> None:
        section_heading(label)

    _SPINNER_DIM = "\033[2m"
    _SPINNER_RESET = "\033[0m"
    _TEAM_STATUS: Dict[str, str] = {}
    _TEAM_RENDER_LINES = {"count": 0}
    _TEAM_KEY_VAR = contextvars.ContextVar("clogem_team_key", default="")

    def _render_team_status_board() -> None:
        import sys as _sys

        items = sorted(_TEAM_STATUS.items())
        if not items and _TEAM_RENDER_LINES["count"] == 0:
            return
        # Move cursor up to redraw previous board.
        for _ in range(_TEAM_RENDER_LINES["count"]):
            _sys.stdout.write("\x1b[1A")
        lines: List[str] = []
        if items:
            lines.append("  Team Status:")
            for k, v in items:
                lines.append(f"   - {k}: {v}")
        else:
            lines.append("")
        _TEAM_RENDER_LINES["count"] = len(lines)
        for ln in lines:
            _sys.stdout.write("\r\x1b[2K" + ln + "\n")
        _sys.stdout.flush()

    def _run_with_ascii_progress(label: str, fn):
        """
        ASCII spinner on stdout (no Unicode). Always visible vs Rich / braille.
        """
        import sys as _sys

        _say(f"[clogem] START: {label}")
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
        _say(f"[clogem] DONE:  {label}  ({elapsed:.1f}s)")
        return out

    async def _run_with_ascii_progress_async(label: str, coro_factory):
        """
        Async ASCII spinner for non-blocking SDK calls.
        Keeps terminal responsive while awaiting model coroutines.
        """
        import sys as _sys

        await trace_doing_async(f"START: {label}")
        stop = asyncio.Event()
        t0 = time.monotonic()
        frames = "|/-\\"
        team_key = _TEAM_KEY_VAR.get() or ""

        async def _spin() -> None:
            i = 0
            while not stop.is_set():
                elapsed = int(time.monotonic() - t0)
                ch = frames[i % len(frames)]
                tail = f"... working {ch} ({elapsed}s)"
                line = f"  {label} {tail}"
                pad = max(0, 76 - len(line))
                if team_key:
                    _TEAM_STATUS[team_key] = f"{label} {tail}"
                    _render_team_status_board()
                else:
                    _sys.stdout.write(
                        "\r" + _SPINNER_DIM + line + (" " * pad) + _SPINNER_RESET
                    )
                    _sys.stdout.flush()
                i += 1
                await asyncio.sleep(0.12)

        spin_task = asyncio.create_task(_spin())
        try:
            out = await coro_factory()
        finally:
            stop.set()
            try:
                await spin_task
            except Exception:
                pass
            if team_key:
                _TEAM_STATUS[team_key] = f"{label} done"
                _render_team_status_board()
            else:
                _sys.stdout.write("\r" + (" " * 80) + "\r\n")
                _sys.stdout.flush()
        elapsed = time.monotonic() - t0
        await trace_done_async(f"DONE:  {label}  ({elapsed:.1f}s)")
        return out

    async def run_cmd(
        cmd: List[str], status_msg: Optional[str] = None
    ) -> Tuple[str, str, int]:
        to = _subprocess_timeout_sec()
        exe_name = os.path.basename(cmd[0]).lower() if cmd else ""
        is_gemini_cli = "gemini" in exe_name
        is_codex_cli = "codex" in exe_name

        async def _run_async():
            kw = {"capture_output": True, "text": True}
            if to is not None:
                # Gemini CLI requests (especially research-style prompts) can
                # legitimately take longer than the default subprocess timeout.
                # Codex build/generation turns can also exceed 60s for larger tasks.
                if is_gemini_cli:
                    kw["timeout"] = max(to, 120)
                elif is_codex_cli:
                    kw["timeout"] = max(to, 180)
                else:
                    kw["timeout"] = to
            if is_gemini_cli:
                env = os.environ.copy()
                env.setdefault("GEMINI_CLI_TRUST_WORKSPACE", "true")
                kw["env"] = env
            try:
                return await asyncio.to_thread(subprocess.run, cmd, **kw)
            except subprocess.TimeoutExpired:
                timeout_used = kw.get("timeout", to)
                msg = (
                    f"subprocess timed out after {timeout_used}s "
                    f"(set CLOGEM_SUBPROCESS_TIMEOUT_SEC to adjust)"
                )
                _say(f"[clogem] ERROR: {msg}.")
                # Return a non-zero result instead of raising so callers can
                # gracefully fallback (e.g., /research -> orchestrator).
                return subprocess.CompletedProcess(
                    cmd,
                    124,
                    stdout="",
                    stderr=msg,
                )

        if status_msg:
            result = await _run_with_ascii_progress_async(status_msg, _run_async)
            if result.returncode != 0:
                _say(
                    f"[clogem] WARNING: process exited with code {result.returncode}"
                )
                err = (result.stderr or "").strip()
                if err:
                    clip = err[:800] + ("..." if len(err) > 800 else "")
                    console.print(Text(f"  stderr: {clip}", style=LOG_WARN))
        else:
            result = await _run_async()
        return result.stdout or "", result.stderr or "", result.returncode

    def _auto_permissions_from_env() -> Optional[bool]:
        raw = os.environ.get("CLOGEM_AUTO_PERMISSIONS", "").strip().lower()
        if raw in ("1", "y", "yes", "true", "on"):
            return True
        if raw in ("0", "n", "no", "false", "off"):
            return False
        return None

    def ensure_auto_permissions() -> None:
        """
        Codex/Gemini often block in headless mode until approvals are granted.
        Ask once per session (or use CLOGEM_AUTO_PERMISSIONS=yes|no).
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
                    "[clogem] Non-interactive stdin: not prompting for Codex/Gemini permissions. "
                    "Set CLOGEM_AUTO_PERMISSIONS=yes if builds hang or fail.",
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
                "Tip: set CLOGEM_AUTO_PERMISSIONS=yes or no to skip this prompt.",
                style=MUTED,
            )
        )
        # Use plain stdin input (not Rich input) to avoid terminal state issues
        # after subprocess crashes/spinner redraws. Default to "yes" on Enter.
        try:
            ans_raw = input("Allow both for this clogem session? [Y/n]: ")
        except EOFError:
            ans_raw = ""
        ans = re.sub(r"[^a-zA-Z]", "", (ans_raw or "").strip()).lower()
        auto_permissions["granted"] = ans in ("", "y", "yes")
        if not auto_permissions["granted"]:
            console.print(
                Text(
                    "Continuing without --full-auto / --yolo. If subprocesses hang or exit with "
                    "approval errors, re-run with CLOGEM_AUTO_PERMISSIONS=yes.",
                    style=LOG_WARN,
                )
            )

    def _run_permissions_from_env() -> Optional[bool]:
        raw = os.environ.get("CLOGEM_ALLOW_LOCAL_COMMANDS", "").strip().lower()
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
                    "[clogem] Non-interactive stdin: not prompting to run local commands. "
                    "Set CLOGEM_ALLOW_LOCAL_COMMANDS=yes to enable.",
                    style=LOG_WARN,
                )
            )
            return
        console.print()
        console.print(
            Text(
                "Local tools (/run, /test, /lint, /github/clone) and build-time artifact auto-run "
                "may execute commands on your machine. Allow that for this clogem session?",
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

    _RUN_ALLOW_EXECUTABLES = set(ALLOWED_EXECUTABLES)

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
        ok, reason = validate_local_command_args(args, label)
        if not ok:
            return 1, "", reason

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
        # Node-like
        if _repo_has("package.json"):
            if _repo_has("pnpm-lock.yaml"):
                return "node-pnpm"
            if _repo_has("yarn.lock"):
                return "node-yarn"
            return "node-npm"
        # Python-like
        if _repo_has("pyproject.toml") or _repo_has("requirements.txt") or _repo_has("setup.cfg"):
            if _repo_has("poetry.lock"):
                return "python-poetry"
            if _repo_has("pdm.lock"):
                return "python-pdm"
            return "python"
        # Go / Rust
        if _repo_has("go.mod"):
            return "go"
        if _repo_has("Cargo.toml"):
            return "rust"
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
        if kind in ("node-npm", "node-pnpm", "node-yarn"):
            pj = _read_json_file(os.path.join(_repo_root(), "package.json")) or {}
            if _select_node_script(pj, "test"):
                if kind == "node-pnpm":
                    return "pnpm run test"
                if kind == "node-yarn":
                    return "yarn test"
                return "npm run test"
            if kind == "node-pnpm":
                return "pnpm test"
            if kind == "node-yarn":
                return "yarn test"
            return "npm test"
        if kind == "python-poetry":
            return "poetry run pytest"
        if kind == "python-pdm":
            return "pdm run pytest"
        if kind == "python":
            # Best-effort: use python -m pytest so it works even without a global pytest script.
            return "python -m pytest"
        if kind == "go":
            return "go test ./..."
        if kind == "rust":
            return "cargo test"
        return None

    def _select_lint_cmd() -> Optional[str]:
        kind = _detect_repo_kind()
        if kind in ("node-npm", "node-pnpm", "node-yarn"):
            pj = _read_json_file(os.path.join(_repo_root(), "package.json")) or {}
            if _select_node_script(pj, "lint"):
                if kind == "node-pnpm":
                    return "pnpm run lint"
                if kind == "node-yarn":
                    return "yarn lint"
                return "npm run lint"
            if _select_node_script(pj, "eslint"):
                if kind == "node-pnpm":
                    return "pnpm run eslint"
                if kind == "node-yarn":
                    return "yarn eslint"
                return "npm run eslint"
            return None
        if kind == "python-poetry":
            if shutil.which("ruff"):
                return "poetry run ruff check ."
            if shutil.which("flake8"):
                return "poetry run flake8 ."
            return None
        if kind == "python-pdm":
            if shutil.which("ruff"):
                return "pdm run ruff check ."
            if shutil.which("flake8"):
                return "pdm run flake8 ."
            return None
        if kind == "python":
            # Choose ruff first if available.
            if shutil.which("ruff"):
                return "python -m ruff check ."
            if shutil.which("flake8"):
                return "python -m flake8 ."
            return None
        if kind == "go":
            if shutil.which("golangci-lint"):
                return "golangci-lint run"
            return None
        if kind == "rust":
            return "cargo clippy -- -D warnings"
        return None

    def _select_typecheck_cmd() -> Optional[str]:
        """Best-effort: run TypeScript typecheck when tsconfig exists."""
        kind = _detect_repo_kind()
        if kind not in ("node-npm", "node-pnpm", "node-yarn"):
            if kind in ("python", "python-poetry", "python-pdm"):
                typecheck_pyright_on = (
                    os.environ.get("CLOGEM_TYPECHECK_PYRIGHT", "1").strip().lower()
                    not in ("0", "false", "no", "off", "disabled")
                )
                if not typecheck_pyright_on:
                    return None
                # Best-effort Pyright type checking for Python projects.
                if shutil.which("pyright"):
                    # Uses pyright's config discovery when a pyrightconfig.json exists.
                    if kind == "python-poetry":
                        return "poetry run pyright --verifytypes ."
                    if kind == "python-pdm":
                        return "pdm run pyright --verifytypes ."
                    return "pyright --verifytypes ."
                return None
            if kind == "go":
                # Best-effort static/type-ish check for Go.
                return "go test ./..."
            if kind == "rust":
                return "cargo check"
            return None
        if _repo_has("tsconfig.json"):
            if kind == "node-pnpm":
                return "pnpm exec tsc --noEmit"
            if kind == "node-yarn":
                return "yarn tsc --noEmit"
            return "npx tsc --noEmit"
        return None

    def _run_local_command_in_cwd(
        cmd_raw: str, label: str, cwd: str
    ) -> Tuple[int, str, str]:
        """
        Same allowlist + permission rules as _run_local_command, but executes
        inside provided cwd (used for sandboxed validation).
        """
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
        ok, reason = validate_local_command_args(args, label)
        if not ok:
            return 1, "", reason

        proc = _run_proc(args, cwd=cwd)
        return proc.returncode, proc.stdout or "", proc.stderr or ""

    def _sandbox_copy_repo_for_validation() -> Tuple[str, str]:
        """
        Create a temp copy of the repo and run tests there.
        This reduces risk of generated test code deleting/mutating host files.
        """
        import tempfile

        src = _repo_root()
        sandbox_root = tempfile.mkdtemp(prefix="clogem-validate-")
        include_node_modules = (
            os.environ.get("CLOGEM_SANDBOX_INCLUDE_NODE_MODULES", "").strip().lower()
            in ("1", "true", "yes", "on")
        )

        # Fast path: copy only git-tracked files (near-instant for large repos).
        try:
            from clogem.validation import copy_git_tracked_repo_to_sandbox

            used_git, _copied = copy_git_tracked_repo_to_sandbox(
                src,
                sandbox_root,
                extra_ignore_prefixes=(
                    "node_modules/",
                    ".git/",
                )
                if not include_node_modules
                else (".git/",),
            )
            if used_git:
                return sandbox_root, src
        except Exception:
            # If anything goes wrong, fall back to a safer full copy below.
            pass

        # Fallback: full copy with an ignore list (slower, but robust).
        ignore_dirs = [
            ".git",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            ".tox",
            ".venv",
            "dist",
            "build",
            ".cursor-server",
        ]
        if not include_node_modules:
            ignore_dirs.append("node_modules")

        ignore_patterns = list(ignore_dirs)

        def _ignore(_dirpath: str, names: list[str]) -> set[str]:
            return {n for n in names if n in ignore_patterns}

        shutil.copytree(src, sandbox_root, ignore=_ignore, dirs_exist_ok=False)
        return sandbox_root, src

    def _normalize_sandbox_paths(text: str, sandbox_root: str) -> str:
        if not text:
            return ""
        return text.replace(sandbox_root + os.sep, "")

    def _docker_available() -> bool:
        if shutil.which("docker") is None:
            return False
        try:
            proc = subprocess.run(
                ["docker", "version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return proc.returncode == 0
        except Exception:
            return False

    def _docker_run_tokens(
        image: str, tokens: List[str], *, sandbox_root: str
    ) -> Tuple[int, str, str]:
        to = _subprocess_timeout_sec()
        cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{os.path.abspath(sandbox_root)}:/repo",
            "-w",
            "/repo",
            image,
        ] + tokens
        try:
            kw = {"capture_output": True, "text": True}
            if to is not None:
                kw["timeout"] = to
            proc = subprocess.run(cmd, **kw)
            return proc.returncode, proc.stdout or "", proc.stderr or ""
        except subprocess.TimeoutExpired:
            return 1, "", "docker command timed out"
        except OSError as e:
            return 1, "", f"docker command failed: {e}"

    def _docker_validate_cmd_tokens(cmd_raw: str, label: str) -> Optional[List[str]]:
        """
        Enforce the same safety rules as local execution:
        - no shell operators
        - executable must be allowlisted
        """
        if _contains_shell_operators(cmd_raw):
            return None
        args = _shlex_split_cmd(cmd_raw.strip())
        if not args:
            return None
        ok, _reason = validate_local_command_args(args, label)
        if not ok:
            return None
        return args

    def _docker_install_deps_if_needed(repo_kind: str, sandbox_root: str) -> str:
        """
        Best-effort dependency install inside container so tests/lint can run.
        Returns a short feedback string (empty if nothing to do).
        """
        from clogem.docker_validation import plan_docker_dependency_install

        py_image = os.environ.get("CLOGEM_DOCKER_PY_IMAGE", "python:3.12-slim").strip()
        node_image = (
            os.environ.get("CLOGEM_DOCKER_NODE_IMAGE", "node:20-slim").strip()
        )

        signals = {
            "package-lock.json": os.path.isfile(
                os.path.join(sandbox_root, "package-lock.json")
            ),
            "package.json": os.path.isfile(os.path.join(sandbox_root, "package.json")),
            "pnpm-lock.yaml": os.path.isfile(
                os.path.join(sandbox_root, "pnpm-lock.yaml")
            ),
            "yarn.lock": os.path.isfile(os.path.join(sandbox_root, "yarn.lock")),
            "requirements.txt": os.path.isfile(
                os.path.join(sandbox_root, "requirements.txt")
            ),
            "pyproject.toml": os.path.isfile(
                os.path.join(sandbox_root, "pyproject.toml")
            ),
            "setup.py": os.path.isfile(os.path.join(sandbox_root, "setup.py")),
            "poetry.lock": os.path.isfile(os.path.join(sandbox_root, "poetry.lock")),
            "pdm.lock": os.path.isfile(os.path.join(sandbox_root, "pdm.lock")),
        }

        plan = plan_docker_dependency_install(repo_kind, signals)
        if not plan.commands:
            return ""

        if plan.image_family == "node":
            image = node_image
        else:
            image = py_image

        for tokens in plan.commands:
            rc, out, err = _docker_run_tokens(
                image, tokens, sandbox_root=sandbox_root
            )
            if rc != 0:
                return (
                    f"Dependency install failed (rc={rc}):\n"
                    f"{(err or out).strip()[:4000]}"
                )
        return ""

    def _run_validation_suite_docker() -> Tuple[bool, str]:
        test_cmd = _select_test_cmd()
        lint_cmd = _select_lint_cmd()
        typecheck_cmd = _select_typecheck_cmd()

        if not (test_cmd or lint_cmd or typecheck_cmd):
            return True, "No known test/lint/typecheck commands for this repo."

        repo_kind = _detect_repo_kind()
        sandbox_root, _src = _sandbox_copy_repo_for_validation()

        try:
            combined_parts: List[str] = []
            ok = True

            from clogem.docker_validation import normalize_repo_kind_for_docker

            docker_family = normalize_repo_kind_for_docker(repo_kind)
            if docker_family == "node":
                image = (
                    os.environ.get("CLOGEM_DOCKER_NODE_IMAGE", "node:20-slim").strip()
                )
            else:
                image = (
                    os.environ.get("CLOGEM_DOCKER_PY_IMAGE", "python:3.12-slim").strip()
                )

            dep_feedback = _docker_install_deps_if_needed(repo_kind, sandbox_root)
            if dep_feedback.strip():
                ok = False
                combined_parts.append(dep_feedback)

            for cmd, label in (
                (test_cmd, "tests"),
                (lint_cmd, "lint"),
                (typecheck_cmd, "typecheck"),
            ):
                if not cmd:
                    continue
                tokens = _docker_validate_cmd_tokens(cmd, label)
                if not tokens:
                    ok = False
                    combined_parts.append(
                        f"\n--- COMMAND: {label} ---\n$ {cmd}\n"
                        "Rejected by sandbox/allowlist rules."
                    )
                    continue
                rc, out, err = _docker_run_tokens(
                    image, tokens, sandbox_root=sandbox_root
                )
                if rc != 0:
                    ok = False
                combined_parts.append(
                    f"\n--- COMMAND: {label} ---\n$ {cmd}\n"
                    f"rc={rc}\n"
                    f"stdout:\n{(out or '').strip()}\n"
                    f"stderr:\n{(err or '').strip()}\n"
                )

            feedback = "\n".join(combined_parts).strip()
            feedback = _normalize_sandbox_paths(feedback, sandbox_root)
            if len(feedback) > 12000:
                feedback = feedback[:11990] + "\n...[truncated]"
            return ok, feedback or "Validation ran but produced no output."
        finally:
            try:
                shutil.rmtree(sandbox_root, ignore_errors=True)
            except Exception:
                pass

    def _run_validation_suite() -> Tuple[bool, str]:
        """
        Run test + lint + optional typecheck using either:
        - Docker (preferred when explicitly requested)
        - Temp filesystem sandbox (fast, no setup)

        Returns (ok, combined_feedback).
        """
        test_cmd = _select_test_cmd()
        lint_cmd = _select_lint_cmd()
        typecheck_cmd = _select_typecheck_cmd()

        if not (test_cmd or lint_cmd or typecheck_cmd):
            return True, "No known test/lint/typecheck commands for this repo."

        docker_ok = _docker_available()
        if require_docker_for_validation:
            if not docker_ok:
                msg = "Strict sandbox mode requires Docker, which is not available."
                trace_done(
                    "Validation: strict sandbox requested but Docker is unavailable; failing validation."
                )
                print(msg)
                return False, msg
            trace_done("Validation: using Docker backend (strict).")
            return _run_validation_suite_docker()

        if validation_docker_requested and docker_ok:
            trace_done("Validation: using Docker backend (requested).")
            return _run_validation_suite_docker()

        trace_done("Validation: using temp filesystem sandbox backend.")
        sandbox_root, _src = _sandbox_copy_repo_for_validation()
        try:
            combined_parts: List[str] = []
            ok = True

            for cmd, label in (
                (test_cmd, "tests"),
                (lint_cmd, "lint"),
                (typecheck_cmd, "typecheck"),
            ):
                if not cmd:
                    continue
                rc, out, err = _run_local_command_in_cwd(
                    cmd, label=label, cwd=sandbox_root
                )
                if rc != 0:
                    ok = False
                combined_parts.append(
                    f"\n--- COMMAND: {label} ---\n$ {cmd}\n"
                    f"rc={rc}\n"
                    f"stdout:\n{(out or '').strip()}\n"
                    f"stderr:\n{(err or '').strip()}\n"
                )

            feedback = "\n".join(combined_parts).strip()
            feedback = _normalize_sandbox_paths(feedback, sandbox_root)
            if len(feedback) > 12000:
                feedback = feedback[:11990] + "\n...[truncated]"
            return ok, feedback or "Validation ran but produced no output."
        finally:
            try:
                shutil.rmtree(sandbox_root, ignore_errors=True)
            except Exception:
                pass

    def _codex_argv(prompt: str) -> List[str]:
        """codex exec with flags that avoid failing outside a git repo / trusted tree."""
        base = _shlex_split_cmd(os.environ.get("CLOGEM_CODEX_CMD", "").strip()) or ["codex"]
        argv = base + ["exec", "--skip-git-repo-check"]
        if auto_permissions.get("granted"):
            argv.append("--full-auto")
        wd = os.environ.get("CLOGEM_CODEX_WORKDIR", "").strip()
        if wd:
            argv.extend(["-C", os.path.abspath(wd)])
        cm = models.get("codex")
        if cm:
            argv.extend(["-m", cm])
        argv.append(prompt)
        return argv

    def _gemini_argv(prompt: str) -> List[str]:
        base = _shlex_split_cmd(os.environ.get("CLOGEM_GEMINI_CMD", "").strip()) or ["gemini"]
        argv = list(base)
        if "--skip-trust" not in argv:
            argv.append("--skip-trust")
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
                f"[clogem] ERROR: subprocess timed out after {to}s "
                f"(set CLOGEM_SUBPROCESS_TIMEOUT_SEC)."
            )
            raise

    async def run_codex(prompt: str, status_msg: str) -> Tuple[str, str, int]:
        backend = settings.codex_backend
        sdk_model = (
            models.get("codex")
            or os.environ.get("CLOGEM_CODEX_SDK_MODEL", "").strip()
            or "gpt-4.1-mini"
        )
        timeout = _subprocess_timeout_sec() or 60

        # google-genai async client has shown intermittent cleanup crashes in some
        # environments (`_async_httpx_client` missing). Keep grounded lookup on
        # sync SDK path for stability.
        use_async = False
        codex_cmd_parts = (
            _shlex_split_cmd(os.environ.get("CLOGEM_CODEX_CMD", "").strip()) or ["codex"]
        )
        codex_exe = codex_cmd_parts[0] if codex_cmd_parts else "codex"
        codex_cli_available = bool(shutil.which(codex_exe) or os.path.isfile(codex_exe))

        async def _run_sdk_async():
            return await openai_generate_async(prompt, sdk_model, timeout_sec=timeout)

        def _run_sdk_sync():
            return openai_generate(prompt, sdk_model, timeout_sec=timeout)

        # In auto mode, prefer Codex CLI when available. This avoids unnecessary
        # SDK initialization/failures in environments that intentionally route
        # through the CLI path (for example integration tests and local wrappers).
        should_try_sdk = backend == "sdk" or (backend == "auto" and not codex_cli_available)

        if should_try_sdk:
            try:
                if use_async:
                    if status_msg:
                        r = await _run_with_ascii_progress_async(
                            status_msg, _run_sdk_async
                        )
                    else:
                        r = await _run_sdk_async()
                    if r.returncode != 0:
                        logger.debug(
                            "Gemini async SDK call failed; retrying with sync SDK path. error=%s",
                            r.error,
                        )
                        r = (
                            _run_with_ascii_progress(status_msg, _run_sdk_sync)
                            if status_msg
                            else _run_sdk_sync()
                        )
                else:
                    r = (
                        _run_with_ascii_progress(status_msg, _run_sdk_sync)
                        if status_msg
                        else _run_sdk_sync()
                    )
                if r.returncode == 0:
                    _record_tokens("codex", r.text or "")
                    return r.text or "", "", 0
                if backend == "sdk":
                    return "", r.error or "OpenAI SDK call failed.", 1
            except Exception as e:
                if backend == "sdk":
                    return "", str(e), 1

        stdout, stderr, rc = await run_cmd(_codex_argv(prompt), status_msg)
        combined = (stdout or "") + "\n" + (stderr or "")
        _record_tokens("codex", combined)
        return stdout or "", stderr or "", rc

    async def run_gemini(prompt: str, status_msg: str) -> Tuple[str, str, int]:
        backend = settings.gemini_backend
        sdk_model = (
            models.get("gemini")
            or os.environ.get("CLOGEM_GEMINI_SDK_MODEL", "").strip()
            or "gemini-2.5-flash"
        )
        timeout = _subprocess_timeout_sec() or 60

        # Keep Gemini on sync SDK path for stability. Some google-genai async
        # client versions raise `_async_httpx_client` cleanup errors.
        use_async = False
        gemini_cmd_parts = (
            _shlex_split_cmd(os.environ.get("CLOGEM_GEMINI_CMD", "").strip())
            or ["gemini"]
        )
        gemini_exe = gemini_cmd_parts[0] if gemini_cmd_parts else "gemini"
        gemini_cli_available = bool(
            shutil.which(gemini_exe) or os.path.isfile(gemini_exe)
        )

        async def _run_sdk_async():
            return await gemini_generate_async(prompt, sdk_model, timeout_sec=timeout)

        def _run_sdk_sync():
            return gemini_generate(prompt, sdk_model, timeout_sec=timeout)

        should_try_sdk = backend == "sdk" or (
            backend == "auto" and not gemini_cli_available
        )

        if should_try_sdk:
            try:
                if use_async:
                    if status_msg:
                        r = await _run_with_ascii_progress_async(
                            status_msg, _run_sdk_async
                        )
                    else:
                        r = await _run_sdk_async()
                else:
                    r = (
                        _run_with_ascii_progress(status_msg, _run_sdk_sync)
                        if status_msg
                        else _run_sdk_sync()
                    )
                if r.returncode == 0:
                    _record_tokens("gemini", r.text or "")
                    return (r.text or "").strip(), "", 0
                if backend == "sdk":
                    return "", r.error or "Gemini SDK call failed.", 1
            except Exception as e:
                if use_async:
                    logger.debug(
                        "Gemini async SDK path raised; retrying with sync SDK path",
                        exc_info=True,
                    )
                    try:
                        r = (
                            _run_with_ascii_progress(status_msg, _run_sdk_sync)
                            if status_msg
                            else _run_sdk_sync()
                        )
                        if r.returncode == 0:
                            _record_tokens("gemini", r.text or "")
                            return (r.text or "").strip(), "", 0
                        if backend == "sdk":
                            return "", r.error or "Gemini SDK call failed.", 1
                    except Exception:
                        logger.debug("Gemini sync fallback also failed", exc_info=True)
                if backend == "sdk":
                    return "", str(e), 1

        stdout, stderr, rc = await run_cmd(_gemini_argv(prompt), status_msg)
        combined = (stdout or "") + "\n" + (stderr or "")
        _record_tokens("gemini", combined)
        return (stdout or "").strip(), stderr or "", rc

    async def run_gemini_grounded(prompt: str, status_msg: str) -> Tuple[str, str, int]:
        """
        Gemini + Google Search grounding (SDK only). Used for narrow real-time turns
        (weather, headlines) — see needs_realtime_web_assist().
        """
        backend = settings.gemini_backend
        sdk_model = (
            models.get("gemini")
            or os.environ.get("CLOGEM_GEMINI_SDK_MODEL", "").strip()
            or "gemini-2.5-flash"
        )
        timeout = max(_subprocess_timeout_sec() or 60, 120)

        use_async = settings.async_llm

        async def _run_sdk_async():
            return await gemini_generate_with_google_search_async(
                prompt, sdk_model, timeout_sec=timeout
            )

        def _run_sdk_sync():
            return gemini_generate_with_google_search(
                prompt, sdk_model, timeout_sec=timeout
            )

        if backend == "cli":
            return await run_gemini(
                prompt
                + "\n\n(Note: Live web search requires the Gemini SDK; "
                "set CLOGEM_GEMINI_BACKEND=auto or sdk, not cli.)",
                status_msg,
            )

        if backend in ("auto", "sdk"):
            try:
                if use_async:
                    if status_msg:
                        r = await _run_with_ascii_progress_async(
                            status_msg, _run_sdk_async
                        )
                    else:
                        r = await _run_sdk_async()
                    if r.returncode != 0:
                        logger.debug(
                            "Gemini grounded async call failed; retrying with sync SDK path. error=%s",
                            r.error,
                        )
                        r = (
                            _run_with_ascii_progress(status_msg, _run_sdk_sync)
                            if status_msg
                            else _run_sdk_sync()
                        )
                else:
                    r = (
                        _run_with_ascii_progress(status_msg, _run_sdk_sync)
                        if status_msg
                        else _run_sdk_sync()
                    )
                if r.returncode == 0:
                    _record_tokens("gemini", r.text or "")
                    return (r.text or "").strip(), "", 0
                if backend == "sdk":
                    return "", r.error or "Gemini grounded call failed.", 1
            except Exception as e:
                if use_async:
                    logger.debug(
                        "Gemini grounded async path raised; retrying with sync SDK path",
                        exc_info=True,
                    )
                    try:
                        r = (
                            _run_with_ascii_progress(status_msg, _run_sdk_sync)
                            if status_msg
                            else _run_sdk_sync()
                        )
                        if r.returncode == 0:
                            _record_tokens("gemini", r.text or "")
                            return (r.text or "").strip(), "", 0
                        if backend == "sdk":
                            return "", r.error or "Gemini grounded call failed.", 1
                    except Exception:
                        logger.debug(
                            "Gemini grounded sync fallback also failed",
                            exc_info=True,
                        )
                if backend == "sdk":
                    return "", str(e), 1

        return "", "Gemini grounded call unavailable.", 1

    async def run_claude(prompt: str, status_msg: str) -> Tuple[str, str, int]:
        backend = settings.claude_backend
        sdk_model = (
            models.get("claude")
            or os.environ.get("CLOGEM_CLAUDE_SDK_MODEL", "").strip()
            or "claude-sonnet-4-6"
        )
        timeout = _subprocess_timeout_sec() or 60
        use_async = settings.async_llm

        async def _run_sdk_async():
            return await claude_generate_async(prompt, sdk_model, timeout_sec=timeout)

        def _run_sdk_sync():
            return claude_generate(prompt, sdk_model, timeout_sec=timeout)

        if backend != "sdk":
            return "", "Claude backend supports SDK only.", 1
        try:
            if use_async:
                if status_msg:
                    r = await _run_with_ascii_progress_async(status_msg, _run_sdk_async)
                else:
                    r = await _run_sdk_async()
            else:
                r = (
                    _run_with_ascii_progress(status_msg, _run_sdk_sync)
                    if status_msg
                    else _run_sdk_sync()
                )
            if r.returncode == 0:
                _record_tokens("claude", r.text or "")
                return (r.text or "").strip(), "", 0
            return "", r.error or "Claude SDK call failed.", 1
        except Exception as e:
            return "", str(e), 1

    async def run_role(role: str, prompt: str, status_msg: str) -> Tuple[str, str, int]:
        provider = role_provider_map.get(role, "codex")
        if provider == "codex":
            return await run_codex(prompt, status_msg)
        if provider == "gemini":
            return await run_gemini(prompt, status_msg)
        if provider == "claude":
            return await run_claude(prompt, status_msg)
        return "", f"Unsupported provider for role {role}: {provider}", 1

    def extract_code(text):
        return artifact_helpers.extract_code(text)

    ROUTER_TEMPLATE = prompt_defs.ROUTER_TEMPLATE
    ROUTER_DIRECTIVE_HINTS = prompt_defs.ROUTER_DIRECTIVE_HINTS
    CODEX_MODE_HINTS = prompt_defs.CODEX_MODE_HINTS
    ASK_MODE_PROMPT = prompt_defs.ASK_MODE_PROMPT
    RESEARCH_MODE_PROMPT_WITH_SOURCES = prompt_defs.RESEARCH_MODE_PROMPT_WITH_SOURCES
    RESEARCH_WEB_PROMPT = prompt_defs.RESEARCH_WEB_PROMPT
    RESEARCH_ORCHESTRATOR_FALLBACK = prompt_defs.RESEARCH_ORCHESTRATOR_FALLBACK
    ROUTER_SECONDARY_INTENT_PROMPT = prompt_defs.ROUTER_SECONDARY_INTENT_PROMPT
    GEMINI_REVIEW_PROMPT = prompt_defs.GEMINI_REVIEW_PROMPT
    ARCHITECT_SUBTASK_PROMPT = prompt_defs.ARCHITECT_SUBTASK_PROMPT
    INTEGRATION_REVIEW_PROMPT = prompt_defs.INTEGRATION_REVIEW_PROMPT

    _PERSIST_LINE = re.compile(
        r"^PERSIST\s+(note|stack|constraints|decision)\s*:\s*(.+?)\s*$",
        re.I,
    )

    def build_router_prompt(
        task: str, mem_block: str, router_hint: str = ""
    ) -> str:
        return prompt_defs.build_router_prompt(task, mem_block, router_hint)

    async def classify_intent_secondary(task_text: str, _mem_block: str) -> Optional[str]:
        enabled = settings.secondary_intent_llm
        if not enabled:
            return None
        model = settings.router_classifier_model
        prompt = ROUTER_SECONDARY_INTENT_PROMPT.replace("__TASK__", task_text or "")
        had_prev_model = "gemini" in models
        prev_model = models.get("gemini")
        models["gemini"] = model
        try:
            out, _err, rc = await run_gemini(prompt, "")
        finally:
            if had_prev_model:
                models["gemini"] = prev_model
            else:
                models.pop("gemini", None)
        if rc != 0:
            return None
        first = ((out or "").strip().splitlines() or [""])[0].strip().upper()
        if first in ("BUILD", "CHAT"):
            return first
        return None

    def build_gemini_review_prompt(context_block: str, code_text: str) -> str:
        return prompt_defs.build_gemini_review_prompt(context_block, code_text)

    def _parse_subtasks_json(raw: str) -> List[SubTask]:
        txt = (raw or "").strip()
        if not txt:
            return []
        try:
            data = json.loads(txt)
        except Exception:
            m = re.search(r"```json\s*([\s\S]*?)```", txt, re.I)
            if not m:
                return []
            try:
                data = json.loads((m.group(1) or "").strip())
            except Exception:
                return []
        if not isinstance(data, list):
            return []
        out: List[SubTask] = []
        for i, it in enumerate(data):
            if not isinstance(it, dict):
                continue
            sid = str(it.get("id") or f"team-{i+1}").strip()
            desc = str(it.get("description") or "").strip()
            tf = it.get("target_files") or []
            if not isinstance(tf, list):
                tf = []
            targets = [str(x).strip() for x in tf if str(x).strip()]
            if not sid or not desc:
                continue
            out.append(SubTask(id=sid, description=desc, target_files=targets, status="pending"))
        return out[:4]

    async def run_agent_team(sub_task: SubTask, context: dict) -> str:
        token = _TEAM_KEY_VAR.set(sub_task.id)
        try:
            sub_task.status = "running"
            target_attach = ""
            if sub_task.target_files:
                refs = " ".join(f"@{p}" for p in sub_task.target_files)
                _, target_attach = expand_at_mentions(refs)
            sub_auto_ctx, sub_sym_ctx = build_context_blocks(
                task=" ".join(f"@{p}" for p in sub_task.target_files),
                task_clean=sub_task.description,
                repo_root=_repo_root(),
                mention_pattern=_AT_MENTION,
                resolve_mention_path=_resolve_mention_path,
                mention_roots_list=_mention_roots_list,
                path_allowed_for_mention=_path_allowed_for_mention,
            )
            draft_prompt = (
                f"{context['mem_block']}{target_attach}{sub_auto_ctx}{sub_sym_ctx}"
                f"{context['stitch_block']}{context['stitch_rules_extra']}{context['mode_hint']}{CODEX_RULES}{CODEX_PATCH_RULES}\n\n"
                f"TASK:\n{sub_task.description}\n"
            )
            raw, derr, drc = await run_role(
                "coder", draft_prompt, f"Team {sub_task.id}: Coder draft..."
            )
            if drc != 0:
                sub_task.status = "failed"
                return f"### {sub_task.id}\n[codex draft failed]\n{(derr or '')[:500]}"

            review_prompt = build_gemini_review_prompt(
                f"{context['mem_block']}{target_attach}{context['mode_hint']}{GEMINI_RULES}",
                raw,
            )
            rev, rerr, rrc = await run_role(
                "reviewer", review_prompt, f"Team {sub_task.id}: Reviewer feedback..."
            )
            if rrc != 0:
                rev = f"(review unavailable: {(rerr or '')[:300]})"
            improve_prompt = f"""
{context['mem_block']}{target_attach}{context['stitch_block']}{context['stitch_rules_extra']}{context['mode_hint']}{CODEX_RULES}{CODEX_PATCH_RULES}

TASK:
{sub_task.description}

You wrote:
{raw}

Feedback:
{rev}

Return project edits as:
- unified diff blocks for existing files
- FILE: blocks for new files
"""
            improved, ierr, irc = await run_role(
                "coder", improve_prompt, f"Team {sub_task.id}: Coder improve..."
            )
            if irc != 0:
                sub_task.status = "failed"
                return f"### {sub_task.id}\n[codex improve failed]\n{(ierr or '')[:500]}"
            sub_task.status = "done"
            return f"### {sub_task.id}\n{improved.strip()}\n"
        finally:
            _TEAM_KEY_VAR.reset(token)

    async def run_visual_ui_review(task_text: str) -> Optional[str]:
        enabled = (
            os.environ.get("CLOGEM_VISUAL_REVIEW", "1").strip().lower()
            not in ("0", "false", "no", "off", "disabled")
        )
        if not enabled:
            return None
        screenshot_path = os.path.join(ROOT, ".clogem_visual_review.png")
        ok, err = capture_frontend_screenshot(_repo_root(), screenshot_path)
        if not ok:
            trace_done(f"Visual review skipped: {err}")
            return None
        model = (
            models.get("gemini")
            or os.environ.get("CLOGEM_VISUAL_REVIEW_MODEL", "").strip()
            or "gemini-2.5-pro"
        )
        timeout = _subprocess_timeout_sec() or 60
        prompt = (
            "You are a strict UI reviewer. Analyze this screenshot for layout/UI defects only: "
            "overlapping elements, clipping, broken spacing, alignment issues, unreadable contrast, "
            "mobile/desktop responsiveness hints, and visual regressions. "
            "Return concise actionable fixes for HTML/CSS/JS."
            f"\n\nTask intent:\n{task_text}"
        )
        use_async = (
            os.environ.get("CLOGEM_ASYNC_LLM", "1").strip().lower()
            not in ("0", "false", "no", "off", "disabled")
        )
        if use_async:
            vr = await gemini_generate_with_image_async(
                prompt, model, screenshot_path, timeout_sec=timeout
            )
        else:
            vr = gemini_generate_with_image(
                prompt, model, screenshot_path, timeout_sec=timeout
            )
        try:
            if os.path.isfile(screenshot_path):
                os.remove(screenshot_path)
        except Exception:
            pass
        if vr.returncode != 0:
            trace_done("Visual review failed; continuing without image-based feedback.")
            return None
        return (vr.text or "").strip() or None

    def runtime_stitch_capabilities_block() -> str:
        """
        Help the router/chat model answer correctly about Stitch availability.
        Kept lightweight and derived from env vars + basic executables checks.
        """
        cli_cmd = (os.environ.get("CLOGEM_STITCH_CLI") or "").strip()
        http_url = (os.environ.get("CLOGEM_STITCH_HTTP_URL") or "").strip()
        mcp_raw = (os.environ.get("CLOGEM_STITCH_MCP") or "").strip().lower()

        # Prefer calling the existing helper if available, but keep this robust.
        try:
            from clogem.stitch.mcp_stdio import stitch_mcp_enabled

            mcp_enabled = stitch_mcp_enabled()
        except Exception:
            mcp_enabled = mcp_raw not in ("0", "false", "no", "off", "disabled", "")

        cli_line = (
            f"enabled (CLOGEM_STITCH_CLI={cli_cmd})"
            if cli_cmd
            else "not configured (CLOGEM_STITCH_CLI is unset)"
        )
        mcp_line = (
            f"enabled (CLOGEM_STITCH_MCP={mcp_raw or 'default-on'})"
            if mcp_enabled
            else "disabled (CLOGEM_STITCH_MCP=0)"
        )
        http_line = (
            "enabled (CLOGEM_STITCH_HTTP_URL is set)" if http_url else "not configured"
        )

        return (
            "\n\n## Runtime Stitch capabilities (this session)\n"
            f"- Stitch CLI adapter: {cli_line}\n"
            f"- Stitch MCP adapter: {mcp_line}\n"
            f"- Stitch HTTP adapter: {http_line}\n"
            "- Stitch manual fallback: always available (export/paste)\n"
        )

    def runtime_clogem_commands_capabilities_block() -> str:
        """
        Helps chat/router explain what features exist and how to access them,
        without guessing extra tools.
        """
        allow_local = os.environ.get("CLOGEM_ALLOW_LOCAL_COMMANDS", "").strip()
        allow_local_hint = (
            "auto-granted"
            if allow_local
            else "requires an interactive permission prompt"
        )
        return (
            "\n\n## Known in-session commands\n"
            "- `/plan`: planning emphasis (steps/milestones). Prefer structured guidance.\n"
            "- `/debug`: targeted debugging (root cause and verification).\n"
            "- `/agent`: autonomous multi-step coding within scope.\n"
            "- `/build`: force the full build pipeline this turn.\n"
            "- `/ask`: chat-only; no build pipeline this turn.\n"
            "- `/research`: research-style answer (no build loop); web-grounded when no `@` files, file-grounded when you attach `@` sources.\n"
            "- `/pdf`: generate a PDF from provided text (plain text layout; requires `reportlab`).\n"
            "- `/repo/info`: show repo info (git status/branch/last commit).\n"
            "- `/test`: run detected tests (best-effort).\n"
            "- `/lint`: run detected lint (best-effort).\n"
            "- `/run <cmd>`: run a local command with sandboxed allowlist; may require permission.\n"
            "- `/github/info <url|owner/repo>`: fetch public GitHub repo metadata.\n"
            "- `/github/clone <url|owner/repo> [dest]`: clone a GitHub repo into current dir.\n"
            "- `/mcp/plugins`: list configured MCP plugins.\n"
            "- `/mcp/tools <plugin>`: list tools published by an MCP plugin.\n"
            "- `/mcp/call <plugin> <tool> [json]`: call a plugin tool with JSON args.\n"
            "- `/rag/search <query>`: semantic repo search (vector index; optional deps).\n"
            "\nLocal command execution note: `/run`, `/test`, `/lint` use a permission gate "
            f"({allow_local_hint})."
        )

    # (command, right-column description) — Codex-style two-column completion menu
    _SLASH_COMMANDS_META: Tuple[Tuple[str, str], ...] = (
        ("/build", "Force full implementation pipeline (skip BUILD/CHAT router)"),
        ("/plan", "Planning & milestones emphasis; router still classifies"),
        ("/debug", "Debugging & root-cause focus for this turn"),
        ("/agent", "Autonomous multi-step coding within your scope"),
        ("/ask", "Chat only — no Codex/Gemini build loop this turn"),
        (
            "/research",
            "Research mode: web-grounded (no @) or source-only from @ files; no build loop",
        ),
        ("/exit", "Exit clogem"),
        ("/pdf", "Generate a PDF from provided text (plain text layout)"),
        ("/codex/model", "Show or set Codex LLM (draft + improve)"),
        ("/gemini/model", "Show or set Gemini LLM (review + summary)"),
        ("/claude/model", "Show or set Claude LLM (SDK only)"),
        ("/roles", "Show active role->provider mapping"),
        ("/config", "Show effective runtime config values"),
        ("/roles/<role>/<provider>", "Set role provider inline (e.g. /roles/orchestrator/claude)"),
        ("/repo/info", "Show repo info (git status, branch, last commit)"),
        ("/test", "Run project tests (best-effort; Python or Node)"),
        ("/lint", "Run project lint (best-effort; Python or Node)"),
        ("/run", "Run a local command (permission + allowlist enforced)"),
        ("/github/info", "Inspect public GitHub repository details"),
        ("/github/clone", "Clone a GitHub repo into current directory"),
        ("/mcp/plugins", "List configured MCP plugins"),
        ("/mcp/tools", "List tools from an MCP plugin"),
        ("/mcp/call", "Call a tool on an MCP plugin"),
        ("/rag/search", "Semantic search across full repo index"),
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
            if prefix:
                out_prefix = e.startswith(prefix)
                if out_prefix:
                    full = os.path.join(d, e)
                    if parent_rel:
                        rel = f"{parent_rel}/{e}".replace("\\", "/")
                    else:
                        rel = e
                    if os.path.isdir(full):
                        rel += "/"
                    out.append(rel)
                    continue

                # Fuzzy fallback only when prefix matching produces nothing.
                fuzzy_enabled = (
                    os.environ.get("CLOGEM_FUZZY_AT_COMPLETIONS", "1").strip().lower()
                    not in ("0", "false", "no", "off", "disabled")
                )
                if fuzzy_enabled:
                    def _fuzzy_score(needle: str, hay: str) -> int:
                        n = (needle or "").lower()
                        h = (hay or "").lower()
                        if not n or not h:
                            return 0
                        i = 0
                        score = 0
                        streak = 0
                        for ch in h:
                            if i < len(n) and ch == n[i]:
                                i += 1
                                streak += 1
                                score += 10 * streak
                            else:
                                streak = 0
                        return score if i == len(n) else 0

                    score = _fuzzy_score(prefix, e)
                    if score > 0:
                        # Insert into a temporary list with score.
                        # We'll sort later if prefix matches were empty.
                        if "_fuzzy" not in locals():
                            _fuzzy: List[Tuple[int, str]] = []
                        full = os.path.join(d, e)
                        if parent_rel:
                            rel = f"{parent_rel}/{e}".replace("\\", "/")
                        else:
                            rel = e
                        if os.path.isdir(full):
                            rel += "/"
                        _fuzzy.append((score, rel))
                continue

            full = os.path.join(d, e)
            if parent_rel:
                rel = f"{parent_rel}/{e}".replace("\\", "/")
            else:
                rel = e
            if os.path.isdir(full):
                rel += "/"
            out.append(rel)

        if out:
            return out

        # Prefix match empty: apply fuzzy candidates.
        fuzzy = locals().get("_fuzzy") or []
        if not fuzzy:
            return []
        fuzzy.sort(key=lambda x: -x[0])
        return [rel for _score, rel in fuzzy[:_MAX_AT_COMPLETIONS]]

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

        repo_root_for_symbols = _repo_root()
        symbol_index_box = {"idx": None}
        symbols_completion_enabled = (
            os.environ.get("CLOGEM_SYMBOL_COMPLETIONS", "1").strip().lower()
            not in ("0", "false", "no", "off", "disabled")
        )

        class ClogemCompleter(Completer):
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
                            disp = "FILE " + text
                        else:
                            text = rel
                            disp = "FILE " + rel
                        if rel.endswith("/"):
                            meta = "File — directory listing in BUILD prompts"
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

                    # Symbol completion (ctags/universal-ctags) in addition to @path.
                    # Only attempt when the partial is "symbol-like" (no path separators).
                    if (
                        symbols_completion_enabled
                        and partial
                        and "/" not in partial
                        and "\\" not in partial
                        and not partial.startswith(".")
                    ):
                        try:
                            from clogem.symbols import SymbolIndex

                            if symbol_index_box["idx"] is None:
                                symbol_index_box["idx"] = SymbolIndex(
                                    repo_root_for_symbols
                                )

                            idx = symbol_index_box["idx"]
                            sym_tags = idx.symbols_starting_with(
                                partial, limit=_MAX_AT_COMPLETIONS
                            )
                            fuzzy_symbols = (
                                os.environ.get("CLOGEM_FUZZY_SYMBOL_COMPLETIONS", "1")
                                .strip()
                                .lower()
                                not in ("0", "false", "no", "off", "disabled")
                            )
                            if fuzzy_symbols and not sym_tags:
                                sym_tags = idx.symbols_fuzzy_search(
                                    partial, limit=_MAX_AT_COMPLETIONS
                                )
                            for tag in sym_tags:
                                sym = tag.name
                                text = '"' + sym + '"' if quoted else sym
                                disp = "SYM " + sym
                                try:
                                    relp = os.path.relpath(tag.path, ROOT)
                                except ValueError:
                                    relp = tag.path
                                kind = (tag.kind or "symbol").strip() or "symbol"
                                meta = f"{kind} — {relp}"
                                yield Completion(
                                    text,
                                    start_position=-len(seg_replace),
                                    display=disp,
                                    display_meta=_truncate_meta(meta),
                                    style=_CMP,
                                    selected_style=_CMP_SEL,
                                )
                        except Exception:
                            pass

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
            os.environ.get("CLOGEM_NO_TRUE_COLOR", "").strip().lower()
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
            # When the completion menu is open, Enter should accept the selected
            # completion (not submit the full prompt).
            try:
                cs = event.current_buffer.complete_state
                if cs and cs.current_completion is not None:
                    event.current_buffer.apply_completion(cs.current_completion)
                    return
            except Exception:
                pass
            event.current_buffer.validate_and_handle()

        @_task_prompt_keys.add("s-tab")
        def _shift_tab_handler(event):
            # Shift+Tab cycles completions backwards (command/path dropdown).
            try:
                event.current_buffer.complete_previous()
            except Exception:
                pass

        task_prompt_session = PromptSession(
            completer=ClogemCompleter(),
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

    async def read_task_line(prompt: str = "What would you like to do? ") -> str:
        if task_prompt_session is not None:
            try:
                return (await task_prompt_session.prompt_async(prompt)).strip()
            except (EOFError, KeyboardInterrupt):
                raise
        prompt_label = Text(prompt, style=TITLE)
        return (await asyncio.to_thread(console.input, prompt_label)).strip()

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

    MEMORY_EXTRACT_SESSION = prompt_defs.MEMORY_EXTRACT_SESSION
    MEMORY_EXTRACT_PROJECT = prompt_defs.MEMORY_EXTRACT_PROJECT

    def auto_memory_from_text(mem, raw: str) -> None:
        """Parse PERSIST lines from model output; ignore NONE-only responses."""
        stripped = raw.strip()
        if not stripped or re.match(r"^NONE\s*$", stripped, re.I):
            return
        _, persists = extract_persist_directives(raw)
        if persists:
            apply_persist_directives(mem, persists)

    async def auto_memory_after_code_session(mem, task: str, summary: str) -> None:
        t = task.replace("__", "")[:6000]
        s = summary.replace("__", "")[:12000]
        prompt = (
            MEMORY_EXTRACT_SESSION.replace("__TASK__", t).replace("__SUMMARY__", s)
        )
        _say(
            "[clogem] Saving session memory (extra Codex call) — "
            "you will see START/DONE lines below; this is not stuck."
        )
        out, _err, rc = await run_role(
            "orchestrator",
            prompt,
            "Orchestrator: updating persistent context...",
        )
        if rc != 0:
            console.print(
                Text(
                    f"[clogem] Session memory update skipped (Codex exit {rc}).",
                    style=LOG_WARN,
                )
            )
        else:
            auto_memory_from_text(mem, out)
        _say("[clogem] Session memory step finished.")

    async def auto_memory_after_project_session(mem, task: str, file_names: str) -> None:
        t = task.replace("__", "")[:6000]
        f = file_names.replace("__", "")[:4000]
        prompt = MEMORY_EXTRACT_PROJECT.replace("__TASK__", t).replace("__FILES__", f)
        _say(
            "[clogem] Saving session memory (extra Codex call) — "
            "wait for DONE before the next prompt."
        )
        out, _err, rc = await run_role(
            "orchestrator",
            prompt,
            "Orchestrator: updating persistent context...",
        )
        if rc != 0:
            console.print(
                Text(
                    f"[clogem] Session memory update skipped (Codex exit {rc}).",
                    style=LOG_WARN,
                )
            )
        else:
            auto_memory_from_text(mem, out)
        _say("[clogem] Session memory step finished.")

    def extract_files(text):
        return artifact_helpers.extract_files(text)

    def extract_unified_diff(text: str) -> str:
        return artifact_helpers.extract_unified_diff(text)

    def write_files(files, unified_diff_text: str = "") -> Dict[str, str]:
        """
        Safe writer for model outputs:
        - unified diff patches for existing files
        - FILE: blocks for new files / full-file writes
        Returns {written_relative_path: content}.
        """
        repo_root = _repo_root()
        plan = plan_safe_writes(repo_root=repo_root, file_map=files)

        dry_run = (
            os.environ.get("CLOGEM_WRITE_DRY_RUN", "").strip().lower()
            in ("1", "true", "yes", "on")
        )
        approval_required = (
            os.environ.get("CLOGEM_WRITE_APPROVAL", "").strip().lower()
            in ("1", "true", "yes", "on")
        )

        allowed = [p for p in plan if p.allowed]
        blocked = [p for p in plan if not p.allowed]
        for b in blocked:
            console.print(
                Text(
                    f"[clogem] Blocked model write '{b.original_name}': {b.reason}",
                    style=LOG_WARN,
                )
            )

        written: Dict[str, str] = {}

        # Apply unified diff first (existing files), best-effort.
        if (unified_diff_text or "").strip():
            diff_written, diff_errors = apply_unified_diff_safely(
                repo_root=repo_root,
                diff_text=unified_diff_text,
            )
            for pth in sorted(diff_written.keys()):
                _say(f"  [ok] patched {pth}")
            for err in diff_errors:
                console.print(Text(f"[clogem] Patch warning: {err}", style=LOG_WARN))
            written.update(diff_written)

        if not allowed:
            return written

        if dry_run:
            console.print(Text("[clogem] Dry-run mode: no files were written.", style=LOG_WARN))
            for p in allowed:
                try:
                    rel = os.path.relpath(p.target_path, repo_root)
                except ValueError:
                    rel = p.target_path
                _say(f"  [dry-run] {rel}")
            return written

        if approval_required:
            if not sys.stdin.isatty():
                console.print(
                    Text(
                        "[clogem] Non-interactive session + CLOGEM_WRITE_APPROVAL=1: skipping writes.",
                        style=LOG_WARN,
                    )
                )
                return written
            console.print()
            section_rule("Write approval")
            console.print(Text(f"About to write {len(allowed)} file(s) under repo root:", style=MUTED))
            for p in allowed[:30]:
                try:
                    rel = os.path.relpath(p.target_path, repo_root)
                except ValueError:
                    rel = p.target_path
                console.print(Text(f" - {rel}", style=MUTED))
            if len(allowed) > 30:
                console.print(Text(f" ... and {len(allowed) - 30} more", style=MUTED))
            ans = console.input(Text("Proceed with writes? [y/N]: ", style=TITLE)).strip().lower()
            if ans not in ("y", "yes"):
                console.print(Text("[clogem] Write approval denied; skipping writes.", style=LOG_WARN))
                return written
        for p in allowed:
            content = files.get(p.original_name, "")
            parent = os.path.dirname(p.target_path) or repo_root
            os.makedirs(parent, exist_ok=True)
            with open(p.target_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
            try:
                rel = os.path.relpath(p.target_path, repo_root)
            except ValueError:
                rel = p.target_path
            written[rel.replace("\\", "/")] = content
            _say(f"  [ok] wrote {rel}")
        return written

    def _pick_entry(paths: List[str], preferred_basenames: List[str]) -> str:
        return artifact_helpers.pick_entry(paths, preferred_basenames)

    def run_written_artifacts(files: dict) -> None:
        """Run by extension (internal only): .py, .js, then open .html — generic UI copy."""
        paths = [p.strip() for p in files if p.strip()]
        if not paths:
            return

        # Gate artifact execution behind the same permission as /run, /test, /lint.
        ensure_run_permissions()
        if not run_permissions.get("granted"):
            console.print(
                Text(
                    "[clogem] Skipping auto-run of generated artifacts (local command execution denied).",
                    style=LOG_WARN,
                )
            )
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
        return artifact_helpers.get_diff(old, new)

    # ---------- load rules (once per process) ----------

    with open(os.path.join(AI_PATH, "CODEX.md"), encoding="utf-8") as f:
        CODEX_RULES = f.read()

    CODEX_PATCH_RULES = prompt_defs.CODEX_PATCH_RULES

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
                header.append("clogem", style=TITLE)
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
                        "Session: /build /plan /debug /agent /ask /research   "
                        "/codex/model <MODEL_ID|reset>   "
                        "/gemini/model <MODEL_ID|reset>   "
                        "/claude/model <MODEL_ID|reset>   "
                        "/roles   /roles/<role>/<provider>   /config   "
                        "/repo/info /test /lint   "
                        "/run <cmd>   "
                        "/github/info <url|owner/repo>   "
                        "/github/clone <url|owner/repo> [dest]   "
                        "/mcp/plugins /mcp/tools <plugin> /mcp/call <plugin> <tool> [json]   "
                        "/rag/search <query>   "
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

            task = await read_task_line()

            if not task:
                console.print(
                    Text(
                        "No input — type a task when you're ready.",
                        style=MUTED,
                    )
                )
                continue

            handled, should_exit = await asyncio.to_thread(
                handle_pre_pipeline_command,
                task,
                CommandContext(
                    console=console,
                    Text=Text,
                    MUTED=MUTED,
                    TITLE=TITLE,
                    LOG_WARN=LOG_WARN,
                    LOG_ERR=LOG_ERR,
                    LOG_OK=LOG_OK,
                    section_rule=section_rule,
                    models=models,
                    _codex_model=_codex_model,
                    _gemini_model=_gemini_model,
                    _claude_model=_claude_model,
                    role_provider_map=role_provider_map,
                    settings=settings,
                    _repo_root=_repo_root,
                    _select_test_cmd=_select_test_cmd,
                    _select_lint_cmd=_select_lint_cmd,
                    _run_local_command=_run_local_command,
                    _parse_github_repo_ref=_parse_github_repo_ref,
                    _github_repo_info=_github_repo_info,
                    ensure_run_permissions=ensure_run_permissions,
                    run_permissions=run_permissions,
                    _run_with_ascii_progress=_run_with_ascii_progress,
                    _run_proc=_run_proc,
                    _shlex_split_cmd=_shlex_split_cmd,
                    _mention_roots_list=_mention_roots_list,
                    _resolve_mention_path=_resolve_mention_path,
                    _path_allowed_for_mention=_path_allowed_for_mention,
                    _read_file_for_mention=_read_file_for_mention,
                ),
            )
            if should_exit:
                break
            if handled:
                continue

            task, session_directive = parse_session_directive(task)
            image_mentions = extract_image_mentions(task)
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
            session_tokens["claude"] = 0

            ensure_auto_permissions()

            mode_hint = CODEX_MODE_HINTS.get(session_directive or "", "")

            # ---------- Weather / news / live facts: Gemini + Google Search (skip Codex router) ----------
            _realtime_on = (
                os.environ.get("CLOGEM_GEMINI_REALTIME", "1").strip().lower()
                not in ("0", "false", "no", "off", "disabled")
            )
            if (
                _realtime_on
                and session_directive in (None, "ask")
                and not attach_block
                and needs_realtime_web_assist((task_clean or "").strip())
            ):
                trace_doing(
                    "This looks like a live weather/news question — using Gemini with "
                    "Google Search grounding (not the Codex router)."
                )
                local_block = local_datetime_context_block()
                rt_prompt = build_realtime_gemini_prompt(
                    local_block=local_block,
                    user_question=(task_clean or "").strip(),
                )
                backend_g = (
                    os.environ.get("CLOGEM_GEMINI_BACKEND", "auto").strip().lower()
                    or "auto"
                )
                if backend_g == "cli":
                    console.print(
                        Text(
                            "Tip: For live weather and news, use the Gemini SDK backend "
                            "(CLOGEM_GEMINI_BACKEND=auto or sdk). CLI mode cannot run Google Search grounding.",
                            style=MUTED,
                        )
                    )
                    console.print()
                rt_raw, rt_err, rt_rc = await run_gemini_grounded(
                    rt_prompt,
                    "Gemini: live web lookup...",
                )
                if rt_rc != 0:
                    trace_done(
                        "Gemini grounded lookup failed; retrying with non-grounded Gemini."
                    )
                    rt_raw, rt_err, rt_rc = await run_gemini(
                        rt_prompt,
                        "Gemini: live lookup fallback...",
                    )
                    if rt_rc != 0:
                        console.print()
                        _say(
                            f"[clogem] ERROR: Gemini live lookup exited with code {rt_rc}."
                        )
                        if (rt_err or "").strip():
                            console.print(
                                Text((rt_err or "").strip()[:1200], style=LOG_ERR)
                            )
                        console.print()
                        _token_turn_footer()
                        continue
                chat_reply = (rt_raw or "").strip()
                chat_reply, auto_persists = extract_persist_directives(chat_reply)
                apply_persist_directives(memory, auto_persists)
                trace_done("Gemini live web reply ready.")
                live_reasoning_banner_chat(task or "(live web)")
                section_rule("Reply (Gemini + web)")
                console.print()
                console.print(chat_reply or "(empty reply)")
                console.print()
                _token_turn_footer()
                _say("[clogem] Turn finished. What would you like to do next?")
                continue

            # ---------- /ask: conversational only (skip router + build pipeline) ----------
            if session_directive == "ask":
                mem_ctx = mem_block.strip() if mem_block.strip() else "(none yet)"
                ask_task_body = (attach_block or "") + (task_clean or "(no message)")
                ask_raw, ask_err, ask_rc = await run_role(
                    "orchestrator",
                    ASK_MODE_PROMPT.replace("__MEMORY__", mem_ctx)
                    .replace(
                        "__CAPS__",
                        runtime_stitch_capabilities_block()
                        + runtime_clogem_commands_capabilities_block(),
                    )
                    .replace("__TASK__", ask_task_body),
                    "Orchestrator: /ask reply...",
                )
                if ask_rc != 0:
                    console.print()
                    _say(f"[clogem] ERROR: Codex exited with code {ask_rc} for /ask.")
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
                _say("[clogem] Turn finished. What would you like to do next?")
                continue

            # ---------- /research: academic research (skip router + build pipeline) ----------
            if session_directive == "research":
                research_task_body = (task_clean or "(no question)").strip()
                sources = (attach_block or "").strip()

                if sources:
                    trace_doing(
                        "/research with @ sources — answering from inlined files only "
                        "(cite sources; no web)."
                    )
                    research_prompt = (
                        RESEARCH_MODE_PROMPT_WITH_SOURCES.replace("__SOURCES__", sources)
                        .replace("__TASK__", research_task_body)
                    )
                    research_raw, research_err, research_rc = await run_role(
                        "orchestrator",
                        research_prompt,
                        "Orchestrator: /research (from @ sources)...",
                    )
                    err_label = "LLM"
                else:
                    trace_doing(
                        "/research without @ — using Gemini + Google Search grounding."
                    )
                    local_block = local_datetime_context_block()
                    research_prompt = (
                        RESEARCH_WEB_PROMPT.replace("__LOCAL__", local_block)
                        .replace("__TASK__", research_task_body)
                    )
                    research_raw, research_err, research_rc = await run_gemini_grounded(
                        research_prompt,
                        "Gemini: /research (web-grounded)...",
                    )
                    err_label = "Gemini (grounded)"
                    if research_rc != 0:
                        trace_done(
                            "Grounded research unavailable; trying Gemini without grounding."
                        )
                        research_raw, research_err, research_rc = await run_gemini(
                            research_prompt
                            + "\n\n(Note: Google Search grounding was unavailable. "
                            "Answer conservatively; do not invent citations.)",
                            "Gemini: /research (best-effort)...",
                        )
                        err_label = "Gemini"
                    if research_rc != 0:
                        trace_done(
                            "Gemini unavailable; using orchestrator with conservative instructions."
                        )
                        fb = RESEARCH_ORCHESTRATOR_FALLBACK.replace(
                            "__TASK__", research_task_body
                        )
                        research_raw, research_err, research_rc = await run_role(
                            "orchestrator",
                            fb,
                            "Orchestrator: /research (best-effort)...",
                        )
                        err_label = "LLM"

                if research_rc != 0:
                    console.print()
                    _say(
                        f"[clogem] ERROR: {err_label} exited with code {research_rc} for /research."
                    )
                    if (research_err or "").strip():
                        console.print(
                            Text((research_err or "").strip()[:800], style=LOG_ERR)
                        )
                    console.print()
                    _token_turn_footer()
                    continue

                if sources:
                    trace_done("Direct /research reply ready (from @ sources).")
                else:
                    trace_done("Direct /research reply ready (web-grounded or best-effort).")
                live_reasoning_banner_chat(task or "/research")
                section_rule("Reply (/research)")
                console.print()
                console.print((research_raw or "").strip() or "(empty reply)")
                console.print()
                _token_turn_footer()
                _say("[clogem] Turn finished. What would you like to do next?")
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
            route = await resolve_turn_mode(
                TurnModeRequest(
                    session_directive=session_directive,
                    task_clean=task_clean,
                    mem_block=mem_block,
                    router_hint=router_hint,
                ),
                TurnModeDeps(
                    build_router_prompt=build_router_prompt,
                    run_codex=lambda prompt, status: run_role("orchestrator", prompt, status),
                    runtime_stitch_capabilities_block=runtime_stitch_capabilities_block,
                    runtime_clogem_commands_capabilities_block=runtime_clogem_commands_capabilities_block,
                    detect_stitch_frontend_heavy_task=detect_stitch_frontend_heavy_task,
                    detect_prerequisite_first_task=detect_prerequisite_first_task,
                    build_prerequisite_first_prompt=build_prerequisite_first_prompt,
                    secondary_intent_classifier=classify_intent_secondary,
                ),
                TurnModeUI(
                    trace_doing=trace_doing,
                    trace_done=trace_done,
                    say=_say,
                    console=console,
                    text_factory=Text,
                    log_err_style=LOG_ERR,
                    muted_style=MUTED,
                    token_turn_footer=_token_turn_footer,
                ),
            )
            if route.stop_turn:
                continue
            mode = route.mode
            chat_reply = route.chat_reply

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
                _say("[clogem] Turn finished. What would you like to do next?")
                continue

            trace_done(
                "Classified as a build; live narration starts below as each step runs."
            )
            live_reasoning_banner_build(task, mem_block)

            auto_context_block, symbol_dep_context_block = build_context_blocks(
                task=task,
                task_clean=task_clean,
                repo_root=_repo_root(),
                mention_pattern=_AT_MENTION,
                resolve_mention_path=_resolve_mention_path,
                mention_roots_list=_mention_roots_list,
                path_allowed_for_mention=_path_allowed_for_mention,
            )

            stitch_ctx = await maybe_run_stitch_stage(
                StitchStageRequest(
                    task_clean=task_clean,
                    task_raw=task,
                    mode=mode,
                    session_directive=session_directive,
                    stitch_feature_on=stitch_feature_on,
                    stitch_website_rules=STITCH_WEBSITE_RULES,
                    attach_block=attach_block,
                ),
                StitchStageDeps(
                    read_task_line=read_task_line,
                    expand_at_mentions=expand_at_mentions,
                    looks_like_ui_content=looks_like_ui_content,
                ),
                StitchStageUI(
                    trace_done=trace_done,
                    trace_doing=trace_doing,
                    section_rule=section_rule,
                    console=console,
                    text_factory=Text,
                    muted_style=MUTED,
                ),
            )
            stitch_block = stitch_ctx.stitch_block
            stitch_rules_extra = stitch_ctx.stitch_rules_extra
            frontend_detected_for_turn = stitch_ctx.frontend_detected
            stitch_heavy_for_turn = stitch_ctx.stitch_frontend_heavy

            if (
                session_directive == "build"
                and require_docker_for_validation
                and not _docker_available()
            ):
                print("Strict sandbox mode requires Docker, which is not available.")

            # ---------- generate ----------

            trace_doing(
                "I'm calling Codex with your task, CODEX.md rules, and any saved memory so I can get a first implementation pass."
            )
            visual_spec_block = ""
            if session_directive == "build" and image_mentions:
                trace_doing(
                    "Image @ mentions detected in /build; generating Gemini visual spec for Codex."
                )
                model_vs = (
                    os.environ.get("CLOGEM_IMAGE_SPEC_MODEL", "").strip()
                    or "gemini-2.5-flash"
                )
                # Keep vision spec generation on sync path for the same
                # google-genai async stability reason noted above.
                use_async_vs = False
                vs_parts: List[str] = []
                for img in image_mentions[:4]:
                    prompt_vs = (
                        "Describe this UI image in technical detail for implementation.\n"
                        "Focus on: layout structure, component hierarchy, spacing/grid, "
                        "visual styling (colors, typography, shadows, borders), interaction hints, "
                        "responsive behavior assumptions, and reusable component tokens.\n"
                        "Return markdown with sections: Layout, Components, Styling, Interactions, Responsiveness."
                    )
                    if use_async_vs:
                        vr = await gemini_generate_with_image_async(
                            prompt_vs,
                            model_vs,
                            img,
                            timeout_sec=_subprocess_timeout_sec() or 60,
                        )
                    else:
                        vr = gemini_generate_with_image(
                            prompt_vs,
                            model_vs,
                            img,
                            timeout_sec=_subprocess_timeout_sec() or 60,
                        )
                    if vr.returncode == 0 and (vr.text or "").strip():
                        try:
                            rel_img = os.path.relpath(img, ROOT).replace("\\", "/")
                        except ValueError:
                            rel_img = img
                        vs_parts.append(f"### {rel_img}\n{(vr.text or '').strip()}")
                if vs_parts:
                    visual_spec_block = (
                        "## Visual Spec (from @image mentions via Gemini Vision)\n\n"
                        + "\n\n".join(vs_parts)
                        + "\n\n"
                    )
                    trace_done(
                        "Visual Spec generated and prepended to Codex draft prompt."
                    )
                else:
                    trace_done(
                        "Could not generate Visual Spec from @image mentions; continuing without it."
                    )
            parallel_raw = ""
            architect_subtasks: List[SubTask] = []
            if mode == "workflow":
                try:
                    arch_prompt = ARCHITECT_SUBTASK_PROMPT.replace("__TASK__", task_clean or "")
                    arch_model = (
                        os.environ.get("CLOGEM_ARCHITECT_MODEL", "").strip()
                        or "gemini-2.5-pro"
                    )
                    had_prev_model = "gemini" in models
                    prev_model = models.get("gemini")
                    models["gemini"] = arch_model
                    try:
                        arch_out, _arch_err, arch_rc = await run_gemini(
                            arch_prompt, "Architect: planning parallel subtasks..."
                        )
                    finally:
                        if had_prev_model:
                            models["gemini"] = prev_model
                        else:
                            models.pop("gemini", None)
                    if arch_rc == 0:
                        architect_subtasks = _parse_subtasks_json(arch_out or "")
                except Exception:
                    logger.debug("Architect subtask generation failed", exc_info=True)
                    architect_subtasks = []

            if architect_subtasks:
                trace_done(
                    f"Architect pass created {len(architect_subtasks)} parallel team task(s)."
                )
                team_context = {
                    "mem_block": mem_block,
                    "mode_hint": mode_hint,
                    "stitch_block": stitch_block,
                    "stitch_rules_extra": stitch_rules_extra,
                }
                for st in architect_subtasks:
                    st.status = "queued"
                    _TEAM_STATUS[st.id] = "queued"
                _render_team_status_board()
                team_outputs = await asyncio.gather(
                    *[run_agent_team(st, team_context) for st in architect_subtasks]
                )
                for st in architect_subtasks:
                    _TEAM_STATUS[st.id] = st.status
                _render_team_status_board()
                joined = "\n\n".join(team_outputs).strip()
                integ_model = (
                    os.environ.get("CLOGEM_INTEGRATOR_MODEL", "").strip()
                    or "gemini-2.5-pro"
                )
                integ_prompt = INTEGRATION_REVIEW_PROMPT.replace("__OUTPUTS__", joined[:50000])
                had_prev_model = "gemini" in models
                prev_model = models.get("gemini")
                models["gemini"] = integ_model
                try:
                    integ_out, _integ_err, integ_rc = await run_gemini(
                        integ_prompt, "Integrator: merging team outputs..."
                    )
                finally:
                    if had_prev_model:
                        models["gemini"] = prev_model
                    else:
                        models.pop("gemini", None)
                if integ_rc == 0 and (integ_out or "").strip():
                    parallel_raw = (integ_out or "").strip()
                    trace_done("Integration review produced merged project edits.")
                else:
                    trace_done("Integration review unavailable; using concatenated team outputs.")
                    parallel_raw = joined
                _TEAM_STATUS.clear()
                _render_team_status_board()
            else:
                trace_done("Architect pass decided no parallel split; using sequential fallback.")
            tdd_extra_hint = ""
            if session_directive == "build":
                tdd_extra_hint = (
                    "\n\n## Automated validation loop (test-driven refinement)\n"
                    "Because the user asked for /build, you MUST write tests (create/update) when possible, "
                    "run them mentally (expect failures initially), and then implement fixes so that the repository's "
                    "detected test command passes.\n"
                    "For existing files, prefer unified diff blocks; for new files, use FILE: blocks.\n"
                )
            if parallel_raw:
                raw = parallel_raw
                draft_err = ""
                draft_rc = 0
            else:
                planner_block = ""
                plan_prompt = (
                    f"{mem_block}{attach_block}{auto_context_block}{symbol_dep_context_block}"
                    f"{stitch_block}{stitch_rules_extra}{mode_hint}\n\n"
                    "Create a concise implementation plan for this task. "
                    "Focus on major files to edit, tests to add/update, and likely edge cases.\n\n"
                    f"TASK:\n{task_clean}\n"
                )
                plan_raw, _plan_err, plan_rc = await run_role(
                    "planner",
                    plan_prompt,
                    "Planner: preparing implementation plan...",
                )
                if plan_rc == 0 and (plan_raw or "").strip():
                    planner_block = (
                        "\n\n## Planner guidance\n"
                        + (plan_raw or "").strip()[:4000]
                        + "\n"
                    )
                raw, draft_err, draft_rc = await run_role(
                    "coder",
                    f"{visual_spec_block}{mem_block}{attach_block}{auto_context_block}{symbol_dep_context_block}{stitch_block}{stitch_rules_extra}{mode_hint}{planner_block}{CODEX_RULES}{CODEX_PATCH_RULES}"
                    f"{tdd_extra_hint}\n\nTASK:\n{task_clean}\n",
                    "Coder: drafting initial implementation...",
                )
                if draft_rc != 0:
                    trace_done(
                        "Codex draft failed; no diff/FILE output to continue with."
                    )
                    console.print()
                    _say(f"[clogem] ERROR: Codex draft exited with code {draft_rc}.")
                    if (draft_err or "").strip():
                        clip = (draft_err or "").strip()[:1200]
                        if len((draft_err or "").strip()) > 1200:
                            clip += "..."
                        console.print(Text(clip, style=LOG_ERR))
                    console.print(
                        Text(
                            "Set CLOGEM_CODEX_WORKDIR to your project folder if Codex should write elsewhere.",
                            style=MUTED,
                        )
                    )
                    console.print()
                    _token_turn_footer()
                    continue
                trace_done(
                    "Codex finished; I'm inspecting the response for unified diff patches and/or FILE blocks."
                )
            console.print()

            files = extract_files(raw)
            draft_diff = extract_unified_diff(raw)

            if files or draft_diff:
                trace_doing(
                    f"I'm applying Codex output (FILE blocks and/or unified diff patches), then I'll run preview/script hooks if relevant."
                )
                section_heading("PROJECT MODE")
                console.print()
                written_files = write_files(files, unified_diff_text=draft_diff)
                console.print()
                if written_files:
                    run_written_artifacts(written_files)
                else:
                    console.print(
                        Text(
                            "[clogem] No files written (all blocked, dry-run, or approval denied).",
                            style=LOG_WARN,
                        )
                    )
                console.print()

                # ---------- validation loop (close the loop) ----------
                if session_directive == "build":
                    max_attempts = 2
                    try:
                        max_attempts = max(
                            1, int(os.environ.get("CLOGEM_VALIDATION_MAX_ATTEMPTS", "2"))
                        )
                    except ValueError:
                        max_attempts = 2

                    validated = False
                    attempt = 1
                    while attempt <= max_attempts and not validated:
                        console.print(
                            Text(
                                f"[clogem] Validation attempt {attempt}/{max_attempts} (tests + lint + typecheck) ...",
                                style=MUTED,
                            )
                        )
                        ok, feedback = _run_validation_suite()
                        if ok:
                            validated = True
                            trace_done("Validation suite passed in sandbox.")
                            break

                        trace_done(
                            "Validation suite failed; feeding failure output to Codex for a second pass."
                        )
                        section_rule("Self-Correction feedback (validation failures)")
                        console.print(Text(feedback[:4000], style=LOG_WARN))
                        console.print()

                        if attempt >= max_attempts:
                            trace_done("Max validation attempts reached; proceeding to summary.")
                            break

                        # Ask Codex to fix the project so checks pass.
                        fix_prompt = f"""
{mem_block}{attach_block}{stitch_block}{stitch_rules_extra}{mode_hint}{CODEX_RULES}{CODEX_PATCH_RULES}

TASK:
{task_clean}

Self-Correction feedback (from automated validation run):
{feedback}

Fix the project so the test/lint/typecheck commands pass.
If tests still fail, iterate again (changes must make the validation commands pass).
Return project edits as:
- unified diff blocks for existing files
- FILE: blocks for new files
"""
                        improved_raw, imp_err, imp_rc = await run_role(
                            "coder", fix_prompt, "Coder: fixing via validation feedback..."
                        )
                        if imp_rc != 0:
                            console.print(
                                Text(
                                    f"[clogem] WARNING: Codex validation-fix exited with code {imp_rc}.",
                                    style=LOG_WARN,
                                )
                            )
                            break
                        improved_files = extract_files(improved_raw)
                        improved_diff = extract_unified_diff(improved_raw)
                        if not improved_files and not improved_diff:
                            console.print(
                                Text(
                                    "[clogem] WARNING: No FILE: blocks or diff patches returned from Codex fix pass.",
                                    style=LOG_WARN,
                                )
                            )
                            break

                        console.print()
                        trace_doing("Applying Codex validation-fix output (diff/FILE) ...")
                        written_fix_files = write_files(
                            improved_files, unified_diff_text=improved_diff
                        )
                        console.print()
                        if written_fix_files:
                            run_written_artifacts(written_fix_files)
                        else:
                            console.print(
                                Text(
                                    "[clogem] No files written from validation-fix pass.",
                                    style=LOG_WARN,
                                )
                            )
                        console.print()

                        attempt += 1

                trace_done(
                    "Files and any auto-runs are done; I'm asking Codex to fold this project into long-lived memory next."
                )

                run_visual = frontend_detected_for_turn or stitch_heavy_for_turn
                if run_visual:
                    trace_doing(
                        "Running visual UI validation (screenshot + Gemini vision review)."
                    )
                    visual_review = await run_visual_ui_review(task_clean)
                    if visual_review:
                        section_rule("Visual Review (Gemini Vision)")
                        console.print()
                        console.print(visual_review)
                        console.print()
                        trace_doing(
                            "Applying visual-review feedback with a final Codex fix pass."
                        )
                        visual_fix_prompt = f"""
{mem_block}{attach_block}{stitch_block}{stitch_rules_extra}{mode_hint}{CODEX_RULES}{CODEX_PATCH_RULES}

TASK:
{task_clean}

Visual Review Feedback:
{visual_review}

Fix the project to resolve visual/layout issues.
Return project edits as:
- unified diff blocks for existing files
- FILE: blocks for new files
"""
                        vraw, verr, vrc = await run_role(
                            "coder", visual_fix_prompt, "Coder: applying visual review fixes..."
                        )
                        if vrc == 0:
                            vfiles = extract_files(vraw)
                            vdiff = extract_unified_diff(vraw)
                            if vfiles or vdiff:
                                _ = write_files(vfiles, unified_diff_text=vdiff)
                                trace_done(
                                    "Visual review fixes applied from Codex diff/FILE output."
                                )
                            else:
                                trace_done(
                                    "Visual fix pass returned no FILE blocks or diff patches; skipped."
                                )
                        else:
                            if (verr or "").strip():
                                console.print(Text((verr or "").strip()[:800], style=LOG_WARN))
                            trace_done("Visual fix pass failed; keeping prior project state.")

                await auto_memory_after_project_session(
                    memory, task, ", ".join(sorted(files.keys()))
                )
                _token_turn_footer()
                _say("[clogem] Turn finished. What would you like to do next?")
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
            git_ctx_block = ""
            try:
                if os.environ.get("CLOGEM_GIT_CONTEXT", "1").strip().lower() not in (
                    "0",
                    "false",
                    "no",
                    "off",
                    "disabled",
                ):
                    from clogem.git_context import build_recent_git_log_context

                    abs_files: List[str] = []
                    for m in _AT_MENTION.finditer(task or ""):
                        p = m.group(1) or m.group(2) or m.group(3)
                        if not p:
                            continue
                        abs_p = _resolve_mention_path(p.strip())
                        if not abs_p:
                            continue
                        roots = _mention_roots_list()
                        if not _path_allowed_for_mention(abs_p, roots):
                            continue
                        if os.path.isfile(abs_p):
                            abs_files.append(os.path.realpath(abs_p))
                    git_ctx_block = build_recent_git_log_context(
                        _repo_root(),
                        abs_files,
                        max_entries_per_file=3,
                        max_total_chars=6000,
                    )
            except Exception:
                logger.debug("Git context block generation failed", exc_info=True)
                git_ctx_block = ""
            review_context = (
                f"{mem_block}{attach_block}{stitch_block}{stitch_rules_extra}{mode_hint}{GEMINI_RULES}"
                f"{git_ctx_block}"
            )
            review, gem_rev_err, gem_rev_rc = await run_role(
                "reviewer",
                build_gemini_review_prompt(review_context, code),
                "Reviewer: writing structured review...",
            )
            if gem_rev_rc != 0:
                trace_done("Gemini review failed; stopping this build turn.")
                console.print()
                _say(f"[clogem] ERROR: Gemini exited with code {gem_rev_rc}.")
                if (gem_rev_err or "").strip():
                    clip = (gem_rev_err or "").strip()[:1200]
                    if len((gem_rev_err or "").strip()) > 1200:
                        clip += "..."
                    console.print(Text(clip, style=LOG_ERR))
                console.print(
                    Text(
                        "Free-tier quotas or network issues can cause long waits or failures. "
                        "Try again or set CLOGEM_SUBPROCESS_TIMEOUT_SEC.",
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
            codex_improve_prompt = f"""
{mem_block}{attach_block}{stitch_block}{stitch_rules_extra}{mode_hint}{CODEX_RULES}{CODEX_PATCH_RULES}

You wrote:

{code}

Feedback:

{review}

Improve the code.
Return ONLY code.
"""
            improved_raw = ""
            imp_err = ""
            imp_rc = 1
            stream_diffs = (
                role_provider_map.get("coder", "codex") == "codex"
                and os.environ.get("CLOGEM_STREAM_DIFFS", "0").strip().lower()
                not in ("0", "false", "no", "off", "disabled")
                and sys.stdout.isatty()
            )

            if stream_diffs:
                try:
                    import threading
                    import time
                    import subprocess
                    from rich.live import Live

                    diff_text = Text("[clogem] Streaming diff (v1 vs v2) ...", style=LOG_TRACE)

                    args = _codex_argv(codex_improve_prompt)
                    proc = subprocess.Popen(
                        args,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        bufsize=1,
                    )
                    stdout_buf: List[str] = []
                    stderr_buf: List[str] = []

                    def _drain(stream, sink: List[str]) -> None:
                        try:
                            for chunk in iter(lambda: stream.readline(), ""):
                                if not chunk:
                                    break
                                sink.append(chunk)
                        except Exception:
                            logger.debug("Streaming codex stderr drain failed", exc_info=True)
                            return

                    t_err = threading.Thread(
                        target=_drain, args=(proc.stderr, stderr_buf), daemon=True
                    )
                    t_err.start()

                    def _try_extract_fenced_code(s: str) -> Optional[str]:
                        m = re.search(r"```(?:\\w+)?\\n([\\s\\S]*?)```", s)
                        if not m:
                            return None
                        return (m.group(1) or "").strip() or None

                    last_code = None
                    last_render = 0.0

                    with Live(diff_text, console=console, refresh_per_second=4) as live:
                        while True:
                            line = ""
                            if proc.stdout is not None:
                                line = proc.stdout.readline() or ""
                            if line:
                                stdout_buf.append(line)
                                now = time.monotonic()
                                if now - last_render >= 1.0:
                                    raw_now = "".join(stdout_buf)
                                    cand_code = _try_extract_fenced_code(raw_now)
                                    if cand_code and cand_code != last_code:
                                        last_code = cand_code
                                        diff_output = get_diff(code, cand_code)
                                        diff_output = diff_output[:4000]
                                        live.update(Text(diff_output or "", style=LOG_TRACE))
                                        last_render = now

                            rc = proc.poll()
                            if rc is not None and not line:
                                break
                            if rc is not None and proc.stdout is not None:
                                # Drain any remaining stdout.
                                rest = proc.stdout.read() or ""
                                if rest:
                                    stdout_buf.append(rest)
                                break

                    proc.wait(timeout=_subprocess_timeout_sec() or None)
                    if t_err.is_alive():
                        t_err.join(timeout=1.0)

                    improved_raw = "".join(stdout_buf)
                    imp_err = "".join(stderr_buf)
                    imp_rc = proc.returncode or 1
                    combined = (improved_raw or "") + "\n" + (imp_err or "")
                    _record_tokens("codex", combined)
                except Exception:
                    logger.debug("Streaming diff mode failed; falling back", exc_info=True)
                    # If streaming fails, fall back to the normal non-streaming path.
                    improved_raw, imp_err, imp_rc = await run_role(
                        "coder",
                        codex_improve_prompt,
                        "Coder: applying reviewer feedback...",
                    )
            else:
                improved_raw, imp_err, imp_rc = await run_role(
                    "coder",
                    codex_improve_prompt,
                    "Coder: applying reviewer feedback...",
                )
            if imp_rc != 0:
                console.print(
                    Text(
                        f"[clogem] WARNING: Codex revision exited with code {imp_rc}; "
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
            summary, gem_sum_err, gem_sum_rc = await run_role(
                "summariser",
                f"""
{mem_block}{attach_block}{stitch_block}{stitch_rules_extra}{mode_hint}{GEMINI_RULES}

Compare and summarize improvements.

OLD:
{code}

NEW:
{improved}
""",
                "Summariser: summarizing improvements...",
            )
            if gem_sum_rc != 0:
                summary = (
                    f"(Gemini summary unavailable: CLI exited with code {gem_sum_rc}.)"
                )
                if (gem_sum_err or "").strip():
                    summary += "\n" + (gem_sum_err or "").strip()[:600]
                console.print(
                    Text(
                        "[clogem] WARNING: Gemini summary step failed; see placeholder text in Summary section.",
                        style=LOG_WARN,
                    )
                )
            _say(
                "[clogem] Gemini summary step finished; printing the summary text below."
            )
            trace_done(
                "Summary text received; next I persist session memory (another Codex call), then this turn ends."
            )
            console.print()

            section_rule("Summary (Gemini)")
            console.print()
            console.print(summary)
            console.print()

            await auto_memory_after_code_session(memory, task, summary)
            _token_turn_footer()
            _say("[clogem] Turn finished. What would you like to do next?")

        except KeyboardInterrupt:
            console.print()
            console.print(
                Text(
                    "Press Ctrl+C again to exit clogem.",
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


def main() -> None:
    import asyncio

    asyncio.run(async_main())


if __name__ == "__main__":
    main()

from __future__ import annotations

import os
import re
import inspect
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Set, Tuple

from clogem.graph import build_symbol_dependency_context_from_source_files
from clogem.repo_awareness import AutoRepoContextConfig, auto_repo_context_block_for_task
from clogem.stitch import (
    build_stitch_prompt,
    detect_frontend_task,
    detect_stitch_frontend_heavy_task,
    should_skip_stitch_due_to_attachments,
    try_stitch_adapters,
)
from clogem.stitch.adapters import format_stitch_context_for_codex
from clogem.task_intent import detect_prerequisite_first_task


def _copy_to_clipboard(text: str) -> bool:
    if not (text or "").strip():
        return False

    def _run_clip_cmd(cmd: List[str]) -> bool:
        try:
            subprocess.run(
                cmd,
                input=text,
                text=True,
                capture_output=True,
                check=True,
            )
            return True
        except Exception:
            return False

    try:
        import pyperclip  # type: ignore

        pyperclip.copy(text)
        return True
    except Exception:
        pass

    # Native platform tools are often more reliable than GUI toolkits in
    # headless shells and remote sessions.
    if sys.platform == "darwin" and shutil.which("pbcopy"):
        if _run_clip_cmd(["pbcopy"]):
            return True

    if sys.platform.startswith("win"):
        if shutil.which("clip"):
            if _run_clip_cmd(["clip"]):
                return True
        if shutil.which("powershell"):
            if _run_clip_cmd(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Set-Clipboard -Value ([Console]::In.ReadToEnd())",
                ]
            ):
                return True

    # Linux / Wayland / X11 variants.
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy"):
        if _run_clip_cmd(["wl-copy"]):
            return True
    if os.environ.get("DISPLAY") and shutil.which("xclip"):
        if _run_clip_cmd(["xclip", "-selection", "clipboard"]):
            return True
    if os.environ.get("DISPLAY") and shutil.which("xsel"):
        if _run_clip_cmd(["xsel", "--clipboard", "--input"]):
            return True

    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        root.destroy()
        return True
    except Exception:
        return False


def expand_rag_context_with_symbols(
    rag_chunks: List[str],
    *,
    repo_root: str,
    max_symbols: int = 12,
    max_chars: int = 3500,
) -> str:
    """
    Sym-RAG:
    1) take vector-retrieved text chunks
    2) extract potential class/function names
    3) resolve definitions with SymbolIndex
    4) append snippets to build context
    """
    if not rag_chunks:
        return ""
    try:
        from clogem.symbols import SymbolIndex
    except Exception:
        return ""

    # Symbol candidates from class-like and function-call-like patterns.
    candidates: List[str] = []
    seen: Set[str] = set()
    for chunk in rag_chunks:
        for m in re.finditer(r"\b([A-Z][A-Za-z0-9_]{2,})\b", chunk or ""):
            s = (m.group(1) or "").strip()
            if s and s not in seen:
                seen.add(s)
                candidates.append(s)
        for m in re.finditer(r"\b([a-z_][a-z0-9_]{2,})\s*\(", chunk or ""):
            s = (m.group(1) or "").strip()
            if s and s not in seen:
                seen.add(s)
                candidates.append(s)

    stop = {
        "return",
        "import",
        "from",
        "class",
        "function",
        "const",
        "let",
        "var",
        "true",
        "false",
        "none",
        "null",
        "print",
        "raise",
    }
    candidates = [c for c in candidates if c.lower() not in stop]
    if not candidates:
        return ""

    idx = SymbolIndex(repo_root)
    parts: List[str] = []
    used_loc: Set[Tuple[str, int]] = set()
    total = 0
    remaining = max(1, int(max_symbols))
    limit_chars = max(1, int(max_chars))

    for sym in candidates:
        if remaining <= 0 or total >= limit_chars:
            break
        rs = idx.resolve_symbol_to_snippet(sym, context_lines=14, max_chars=1200)
        if rs is None:
            continue
        loc = (rs.tag.path, rs.tag.line)
        if loc in used_loc:
            continue
        used_loc.add(loc)
        rel = rs.tag.path
        try:
            rel = os.path.relpath(rs.tag.path, repo_root).replace("\\", "/")
        except ValueError:
            pass
        block = (
            f"### {sym} -> {rel}:{rs.tag.line}\n"
            f"```{os.path.splitext(rel)[1].lstrip('.')}\n{rs.snippet}\n```\n"
        )
        if total + len(block) > limit_chars:
            break
        parts.append(block)
        total += len(block)
        remaining -= 1

    if not parts:
        return ""
    return "## Sym-RAG symbol definitions\n\n" + "\n".join(parts).strip()


def build_context_blocks(
    *,
    task: str,
    task_clean: str,
    repo_root: str,
    mention_pattern: Any,
    resolve_mention_path: Any,
    mention_roots_list: Any,
    path_allowed_for_mention: Any,
) -> Tuple[str, str]:
    def _format_rag_rows(rows: List[dict], max_chars: int) -> str:
        parts: List[str] = []
        total = 0
        limit = max(1, int(max_chars))
        for r in rows:
            if total >= limit:
                break
            path = (r.get("path") or "").strip()
            text = (r.get("text") or "").strip()
            if not path or not text:
                continue
            snippet = "\n".join(text.splitlines()[:160]).strip()
            if not snippet:
                continue
            block = f"### {path}\n```\n{snippet}\n```\n"
            if total + len(block) > limit:
                break
            parts.append(block)
            total += len(block)
        return "\n".join(parts).strip()

    auto_repo_context_on = (
        os.environ.get("CLOGEM_AUTO_REPO_CONTEXT", "1").strip().lower()
        not in ("0", "false", "no", "off", "disabled")
    )
    auto_repo_max_chars = int(os.environ.get("CLOGEM_AUTO_REPO_CONTEXT_MAX_CHARS", "8000"))
    auto_repo_max_files = int(os.environ.get("CLOGEM_AUTO_REPO_CONTEXT_MAX_FILES", "6"))
    auto_repo_max_depth = int(os.environ.get("CLOGEM_AUTO_REPO_CONTEXT_MAX_DEPTH", "2"))

    auto_context_block = ""
    if auto_repo_context_on:
        try:
            vector_rag_on = (
                os.environ.get("CLOGEM_VECTOR_RAG", "0").strip().lower()
                not in ("0", "false", "no", "off", "disabled")
            )
            if vector_rag_on:
                try:
                    from clogem.vector_index import (
                        VectorIndexConfig,
                        semantic_search_repo,
                    )
                    vector_cfg = VectorIndexConfig(
                        enabled=True,
                        rebuild=bool(
                            os.environ.get("CLOGEM_VECTOR_REBUILD", "0").strip().lower()
                            in ("1", "true", "yes", "on")
                        ),
                        top_k=int(os.environ.get("CLOGEM_VECTOR_TOP_K", "8")),
                        max_context_chars=auto_repo_max_chars,
                        max_chunk_chars=int(
                            os.environ.get("CLOGEM_VECTOR_CHUNK_CHARS", "2500")
                        ),
                    )
                    rag_rows = semantic_search_repo(
                        repo_root=repo_root,
                        task=task_clean,
                        config=vector_cfg,
                    )
                    auto_context_block = _format_rag_rows(
                        rag_rows, max_chars=auto_repo_max_chars
                    )
                    sym_rag_on = (
                        os.environ.get("CLOGEM_SYM_RAG", "1").strip().lower()
                        not in ("0", "false", "no", "off", "disabled")
                    )
                    if sym_rag_on and rag_rows:
                        rag_chunks = [
                            (r.get("text") or "").strip()
                            for r in rag_rows
                            if isinstance(r, dict)
                        ]
                        sym_block = expand_rag_context_with_symbols(
                            rag_chunks,
                            repo_root=repo_root,
                            max_symbols=int(
                                os.environ.get("CLOGEM_SYM_RAG_MAX_SYMBOLS", "12")
                            ),
                            max_chars=int(
                                os.environ.get("CLOGEM_SYM_RAG_MAX_CHARS", "3500")
                            ),
                        )
                        if sym_block:
                            auto_context_block = (
                                (auto_context_block + "\n\n" if auto_context_block else "")
                                + sym_block
                            )
                except Exception:
                    auto_context_block = ""
            if not auto_context_block:
                auto_context_block = auto_repo_context_block_for_task(
                    task=task_clean,
                    repo_root=repo_root,
                    config=AutoRepoContextConfig(
                        enabled=True,
                        max_chars=auto_repo_max_chars,
                        max_files=auto_repo_max_files,
                        max_depth=auto_repo_max_depth,
                    ),
                )
        except Exception:
            auto_context_block = ""

    symbol_dep_context_on = (
        os.environ.get("CLOGEM_SYMBOL_DEP_CONTEXT", "1").strip().lower()
        not in ("0", "false", "no", "off", "disabled")
    )
    symbol_dep_context_block = ""
    if symbol_dep_context_on:
        try:
            symbol_index_enabled = (
                os.environ.get("CLOGEM_SYMBOL_INDEX", "1").strip().lower()
                not in ("0", "false", "no", "off", "disabled")
            )
            if symbol_index_enabled:
                from clogem.symbols import SymbolIndex

                def _extract_mentioned_source_files(raw_task: str) -> List[str]:
                    files: List[str] = []
                    for m in mention_pattern.finditer(raw_task or ""):
                        p = m.group(1) or m.group(2) or m.group(3)
                        if not p:
                            continue
                        abs_p = resolve_mention_path(p.strip())
                        if not abs_p:
                            continue
                        roots = mention_roots_list()
                        if not path_allowed_for_mention(abs_p, roots):
                            continue
                        if os.path.isfile(abs_p) and abs_p.lower().endswith(
                            (".py", ".js", ".ts", ".tsx", ".jsx")
                        ):
                            files.append(os.path.realpath(abs_p))
                    out: List[str] = []
                    seen: Set[str] = set()
                    for f in files:
                        if f in seen:
                            continue
                        seen.add(f)
                        out.append(f)
                    return out

                source_files = _extract_mentioned_source_files(task or "")
                if source_files:
                    idx = SymbolIndex(repo_root)
                    symbol_dep_context_block = build_symbol_dependency_context_from_source_files(
                        repo_root=repo_root,
                        source_files=source_files,
                        symbol_index=idx,
                        max_symbols=int(
                            os.environ.get("CLOGEM_SYMBOL_DEP_MAX_SYMBOLS", "20")
                        ),
                        max_chars=int(
                            os.environ.get("CLOGEM_SYMBOL_DEP_MAX_CHARS", "4000")
                        ),
                    )
        except Exception:
            symbol_dep_context_block = ""

    return auto_context_block, symbol_dep_context_block


async def maybe_run_stitch_stage(
    *,
    task_clean: str,
    task_raw: str,
    mode: str,
    session_directive: str | None,
    stitch_feature_on: bool,
    stitch_website_rules: str,
    attach_block: str,
    trace_done: Any,
    trace_doing: Any,
    section_rule: Any,
    console: Any,
    Text: Any,
    MUTED: Any,
    read_task_line: Any,
    expand_at_mentions: Any,
    looks_like_ui_content: Any,
) -> Dict[str, str]:
    frontend_detected = detect_frontend_task(task_clean)
    stitch_frontend_heavy = detect_stitch_frontend_heavy_task(task_clean)
    prereq_first = detect_prerequisite_first_task(task_clean)
    stitch_block = ""
    stitch_rules_extra = ""
    if stitch_frontend_heavy and stitch_website_rules.strip():
        stitch_rules_extra = (
            "\n\n## STITCH_WEBSITE rules (strict)\n" + stitch_website_rules + "\n"
        )

    trace_done(
        "Pipeline gating: "
        f"mode={mode}, frontend_detected={frontend_detected}, "
        f"stitch_frontend_heavy={stitch_frontend_heavy}, "
        f"prerequisite_first={prereq_first}, stitch_feature_on={stitch_feature_on}, "
        f"session_directive={session_directive or '(none)'}"
    )

    if (
        stitch_feature_on
        and mode == "workflow"
        and stitch_frontend_heavy
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
                if _copy_to_clipboard(stitch_prompt):
                    console.print(
                        Text(
                            "Copied Stitch prompt to clipboard.",
                            style=MUTED,
                        )
                    )
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
                            "Set CLOGEM_STITCH_CLI or CLOGEM_STITCH_HTTP_URL, or run clogem in a real terminal.",
                            style=MUTED,
                        )
                    )
                    trace_done("Skipping Stitch paste; continuing without Stitch HTML.")
                else:
                    stitch_in_v = read_task_line(
                        "Stitch export — paste code or @path (Enter to skip): "
                    )
                    if inspect.isawaitable(stitch_in_v):
                        stitch_in = await stitch_in_v
                    else:
                        stitch_in = stitch_in_v
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
    return {
        "stitch_block": stitch_block,
        "stitch_rules_extra": stitch_rules_extra,
        "stitch_frontend_heavy": str(bool(stitch_frontend_heavy)),
        "frontend_detected": str(bool(frontend_detected)),
    }


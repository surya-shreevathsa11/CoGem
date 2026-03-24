from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Set, Tuple

from cogem.graph import build_symbol_dependency_context_from_py_files
from cogem.repo_awareness import AutoRepoContextConfig, auto_repo_context_block_for_task
from cogem.stitch import (
    build_stitch_prompt,
    detect_frontend_task,
    detect_stitch_frontend_heavy_task,
    should_skip_stitch_due_to_attachments,
    try_stitch_adapters,
)
from cogem.stitch.adapters import format_stitch_context_for_codex
from cogem.task_intent import detect_prerequisite_first_task


def _copy_to_clipboard(text: str) -> bool:
    if not (text or "").strip():
        return False
    try:
        import pyperclip  # type: ignore

        pyperclip.copy(text)
        return True
    except Exception:
        pass
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
    auto_repo_context_on = (
        os.environ.get("COGEM_AUTO_REPO_CONTEXT", "1").strip().lower()
        not in ("0", "false", "no", "off", "disabled")
    )
    auto_repo_max_chars = int(os.environ.get("COGEM_AUTO_REPO_CONTEXT_MAX_CHARS", "8000"))
    auto_repo_max_files = int(os.environ.get("COGEM_AUTO_REPO_CONTEXT_MAX_FILES", "6"))
    auto_repo_max_depth = int(os.environ.get("COGEM_AUTO_REPO_CONTEXT_MAX_DEPTH", "2"))

    auto_context_block = ""
    if auto_repo_context_on:
        try:
            vector_rag_on = (
                os.environ.get("COGEM_VECTOR_RAG", "0").strip().lower()
                not in ("0", "false", "no", "off", "disabled")
            )
            if vector_rag_on:
                try:
                    from cogem.vector_index import (
                        VectorIndexConfig,
                        semantic_repo_context_block_for_task,
                    )

                    auto_context_block = semantic_repo_context_block_for_task(
                        repo_root=repo_root,
                        task=task_clean,
                        config=VectorIndexConfig(
                            enabled=True,
                            rebuild=bool(
                                os.environ.get("COGEM_VECTOR_REBUILD", "0").strip().lower()
                                in ("1", "true", "yes", "on")
                            ),
                            top_k=int(os.environ.get("COGEM_VECTOR_TOP_K", "8")),
                            max_context_chars=auto_repo_max_chars,
                            max_chunk_chars=int(
                                os.environ.get("COGEM_VECTOR_CHUNK_CHARS", "2500")
                            ),
                        ),
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
        os.environ.get("COGEM_SYMBOL_DEP_CONTEXT", "1").strip().lower()
        not in ("0", "false", "no", "off", "disabled")
    )
    symbol_dep_context_block = ""
    if symbol_dep_context_on:
        try:
            symbol_index_enabled = (
                os.environ.get("COGEM_SYMBOL_INDEX", "1").strip().lower()
                not in ("0", "false", "no", "off", "disabled")
            )
            if symbol_index_enabled:
                from cogem.symbols import SymbolIndex

                def _extract_mentioned_py_files(raw_task: str) -> List[str]:
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
                        if os.path.isfile(abs_p) and abs_p.lower().endswith(".py"):
                            files.append(os.path.realpath(abs_p))
                    out: List[str] = []
                    seen: Set[str] = set()
                    for f in files:
                        if f in seen:
                            continue
                        seen.add(f)
                        out.append(f)
                    return out

                py_files = _extract_mentioned_py_files(task or "")
                if py_files:
                    idx = SymbolIndex(repo_root)
                    symbol_dep_context_block = build_symbol_dependency_context_from_py_files(
                        repo_root=repo_root,
                        py_files=py_files,
                        symbol_index=idx,
                        max_symbols=int(
                            os.environ.get("COGEM_SYMBOL_DEP_MAX_SYMBOLS", "20")
                        ),
                        max_chars=int(
                            os.environ.get("COGEM_SYMBOL_DEP_MAX_CHARS", "4000")
                        ),
                    )
        except Exception:
            symbol_dep_context_block = ""

    return auto_context_block, symbol_dep_context_block


def maybe_run_stitch_stage(
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
                            "Set COGEM_STITCH_CLI or COGEM_STITCH_HTTP_URL, or run cogem in a real terminal.",
                            style=MUTED,
                        )
                    )
                    trace_done("Skipping Stitch paste; continuing without Stitch HTML.")
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
    return {
        "stitch_block": stitch_block,
        "stitch_rules_extra": stitch_rules_extra,
    }


from __future__ import annotations

import os
import subprocess
from typing import Iterable, List, Optional, Sequence, Tuple


def _run_git_log(
    repo_root: str, rel_path: str, max_entries: int = 3
) -> Optional[str]:
    """
    Return a compact `git log` string for the given file path.
    """
    if not repo_root or not rel_path:
        return None
    cmd = [
        "git",
        "log",
        f"-{max_entries}",
        "--pretty=format:%h %ad %an %s",
        "--",
        rel_path,
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    out = (proc.stdout or "").strip()
    return out or None


def build_recent_git_log_context(
    repo_root: str,
    abs_file_paths: Iterable[str],
    *,
    max_entries_per_file: int = 3,
    max_total_chars: int = 6000,
) -> str:
    """
    Build a prompt-ready context block containing recent `git log` entries
    for each file.
    """
    repo_root = os.path.abspath(repo_root)
    parts: List[str] = []
    total = 0

    seen: set[str] = set()
    for abs_fp in abs_file_paths:
        if not abs_fp:
            continue
        try:
            rel = os.path.relpath(abs_fp, repo_root).replace("\\", "/")
        except ValueError:
            rel = abs_fp
        if rel in seen:
            continue
        seen.add(rel)

        log_text = _run_git_log(repo_root, rel, max_entries=max_entries_per_file)
        if not log_text:
            continue
        block = f"### {rel}\n{log_text}\n"
        if total + len(block) > max_total_chars:
            break
        parts.append(block)
        total += len(block)

    if not parts:
        return ""
    return "## Recent git log context (last changes per file)\n\n" + "\n".join(parts)


from __future__ import annotations

import os
import shutil
import subprocess
from typing import Iterable, List, Optional, Sequence, Tuple


def git_tracked_files(repo_root: str) -> List[str]:
    """
    Return git-tracked file paths (relative to repo_root).
    Uses `git ls-files -z` to safely handle spaces.
    """
    repo_root = os.path.abspath(repo_root)
    try:
        proc = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=repo_root,
            capture_output=True,
        )
    except OSError:
        return []

    if proc.returncode != 0:
        return []

    raw = proc.stdout or b""
    if not raw:
        return []
    parts = raw.split(b"\x00")
    out: List[str] = []
    for p in parts:
        if not p:
            continue
        try:
            out.append(p.decode("utf-8"))
        except UnicodeDecodeError:
            out.append(p.decode("utf-8", errors="replace"))
    return out


def copy_files_into_folder(
    repo_root: str,
    sandbox_root: str,
    rel_paths: Iterable[str],
    *,
    extra_ignore_prefixes: Sequence[str] = (),
) -> int:
    """
    Copy listed files from repo_root -> sandbox_root preserving directories.
    Returns number of files successfully copied.
    """
    copied = 0
    for rel in rel_paths:
        if not rel:
            continue
        rel_norm = rel.replace("\\", "/").lstrip("/")
        if any(rel_norm.startswith(prefix) for prefix in extra_ignore_prefixes):
            continue

        src = os.path.join(repo_root, rel_norm)
        if not os.path.isfile(src):
            # Might have been deleted between ls-files and copy.
            continue
        dst = os.path.join(sandbox_root, rel_norm)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1
    return copied


def copy_git_tracked_repo_to_sandbox(
    repo_root: str,
    sandbox_root: str,
    *,
    extra_ignore_prefixes: Sequence[str] = ("node_modules/", ".git/"),
) -> Tuple[bool, int]:
    """
    Copy only git-tracked files into sandbox_root.
    Returns (used_git_tracked, files_copied).
    """
    files = git_tracked_files(repo_root)
    if not files:
        return False, 0
    # mkdir is handled by caller; ensure it exists for safety.
    os.makedirs(sandbox_root, exist_ok=True)
    copied = copy_files_into_folder(
        repo_root,
        sandbox_root,
        files,
        extra_ignore_prefixes=extra_ignore_prefixes,
    )
    return True, copied


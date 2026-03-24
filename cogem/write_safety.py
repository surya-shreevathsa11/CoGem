from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class WritePlanItem:
    original_name: str
    target_path: str
    allowed: bool
    reason: str = ""


@dataclass(frozen=True)
class UnifiedDiffHunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: List[str]


@dataclass(frozen=True)
class UnifiedDiffFilePatch:
    old_path: str
    new_path: str
    hunks: List[UnifiedDiffHunk]


def is_within_root(root: str, path: str) -> bool:
    try:
        r = os.path.realpath(root)
        p = os.path.realpath(path)
    except OSError:
        return False
    return p == r or p.startswith(r + os.sep)


def plan_safe_writes(
    *,
    repo_root: str,
    file_map: Dict[str, str],
) -> List[WritePlanItem]:
    """
    Build a safe write plan for model-generated FILE: outputs.

    Rules:
    - normalize file path relative to repo_root
    - deny empty names and names ending with separator
    - deny writes outside repo_root (path traversal, absolute out-root)
    """
    repo_root = os.path.realpath(repo_root)
    out: List[WritePlanItem] = []
    for raw_name in file_map.keys():
        name = (raw_name or "").strip()
        if not name:
            out.append(
                WritePlanItem(
                    original_name=raw_name,
                    target_path="",
                    allowed=False,
                    reason="empty file name",
                )
            )
            continue

        normalized = name.replace("\\", os.sep).replace("/", os.sep)
        if normalized.endswith(os.sep):
            out.append(
                WritePlanItem(
                    original_name=raw_name,
                    target_path="",
                    allowed=False,
                    reason="directory path not allowed",
                )
            )
            continue

        # Always resolve relative to repo root unless already absolute.
        if os.path.isabs(normalized):
            candidate = normalized
        else:
            candidate = os.path.join(repo_root, normalized)

        try:
            parent = os.path.dirname(candidate) or repo_root
            parent_real = os.path.realpath(parent)
            final = os.path.realpath(candidate)
        except OSError:
            out.append(
                WritePlanItem(
                    original_name=raw_name,
                    target_path="",
                    allowed=False,
                    reason="path resolution failed",
                )
            )
            continue

        if not is_within_root(repo_root, parent_real):
            out.append(
                WritePlanItem(
                    original_name=raw_name,
                    target_path=final,
                    allowed=False,
                    reason="parent escapes repo root",
                )
            )
            continue

        if not is_within_root(repo_root, final):
            out.append(
                WritePlanItem(
                    original_name=raw_name,
                    target_path=final,
                    allowed=False,
                    reason="target escapes repo root",
                )
            )
            continue

        out.append(
            WritePlanItem(
                original_name=raw_name,
                target_path=final,
                allowed=True,
                reason="",
            )
        )
    return out


_HUNK_RE = re.compile(r"^@@\s*-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s*@@")


def parse_unified_diff(diff_text: str) -> List[UnifiedDiffFilePatch]:
    lines = (diff_text or "").splitlines()
    patches: List[UnifiedDiffFilePatch] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith("--- "):
            i += 1
            continue
        old_path = line[4:].strip()
        i += 1
        if i >= len(lines) or not lines[i].startswith("+++ "):
            continue
        new_path = lines[i][4:].strip()
        i += 1
        hunks: List[UnifiedDiffHunk] = []
        while i < len(lines):
            cur = lines[i]
            if cur.startswith("--- "):
                break
            m = _HUNK_RE.match(cur)
            if not m:
                i += 1
                continue
            old_start = int(m.group(1))
            old_count = int(m.group(2) or "1")
            new_start = int(m.group(3))
            new_count = int(m.group(4) or "1")
            i += 1
            hunk_lines: List[str] = []
            while i < len(lines):
                l2 = lines[i]
                if l2.startswith("@@") or l2.startswith("--- "):
                    break
                if l2.startswith("\\ No newline"):
                    i += 1
                    continue
                if l2[:1] in (" ", "+", "-"):
                    hunk_lines.append(l2)
                i += 1
            hunks.append(
                UnifiedDiffHunk(
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count,
                    lines=hunk_lines,
                )
            )
        patches.append(
            UnifiedDiffFilePatch(old_path=old_path, new_path=new_path, hunks=hunks)
        )
    return patches


def _normalize_diff_path(path: str) -> str:
    p = (path or "").strip()
    if p.startswith("a/") or p.startswith("b/"):
        return p[2:]
    return p


def apply_unified_diff_safely(
    *,
    repo_root: str,
    diff_text: str,
) -> Tuple[Dict[str, str], List[str]]:
    """
    Apply unified diff patches to existing files under repo_root.
    Returns (written_map, errors). written_map keys are normalized repo-relative paths.
    """
    repo_root = os.path.realpath(repo_root)
    written: Dict[str, str] = {}
    errors: List[str] = []

    patches = parse_unified_diff(diff_text)
    if not patches:
        return {}, ["No unified diff file patches were detected."]

    # Validate targets first.
    target_map: Dict[str, str] = {}
    for p in patches:
        np = _normalize_diff_path(p.new_path)
        op = _normalize_diff_path(p.old_path)
        if np in ("/dev/null", "NUL"):
            errors.append(f"Patch for '{op}' attempts deletion/new-file mode; use FILE: for new files.")
            continue
        target_map[np] = ""
    plan = plan_safe_writes(repo_root=repo_root, file_map=target_map)
    blocked = {x.original_name: x.reason for x in plan if not x.allowed}

    for p in patches:
        np = _normalize_diff_path(p.new_path)
        op = _normalize_diff_path(p.old_path)
        if np in blocked:
            errors.append(f"Blocked patch '{np}': {blocked[np]}")
            continue
        abs_target = os.path.realpath(os.path.join(repo_root, np))
        if not os.path.isfile(abs_target):
            errors.append(f"Patch target does not exist: {np} (use FILE: for new files)")
            continue
        try:
            with open(abs_target, "r", encoding="utf-8", errors="replace") as f:
                orig = f.read().splitlines()
        except OSError as e:
            errors.append(f"Read failed for {np}: {e}")
            continue

        out: List[str] = []
        idx = 0
        failed = False
        for h in p.hunks:
            start = max(0, h.old_start - 1)
            if start < idx:
                start = idx
            if start > len(orig):
                errors.append(f"Hunk start out of bounds in {np}")
                failed = True
                break
            out.extend(orig[idx:start])
            idx = start
            for hl in h.lines:
                tag = hl[:1]
                txt = hl[1:]
                if tag == " ":
                    if idx >= len(orig) or orig[idx] != txt:
                        errors.append(f"Context mismatch in {np} near line {idx + 1}")
                        failed = True
                        break
                    out.append(orig[idx])
                    idx += 1
                elif tag == "-":
                    if idx >= len(orig) or orig[idx] != txt:
                        errors.append(f"Delete mismatch in {np} near line {idx + 1}")
                        failed = True
                        break
                    idx += 1
                elif tag == "+":
                    out.append(txt)
            if failed:
                break
        if failed:
            continue
        out.extend(orig[idx:])
        new_content = "\n".join(out) + ("\n" if out else "")
        try:
            with open(abs_target, "w", encoding="utf-8", newline="\n") as f:
                f.write(new_content)
            rel = os.path.relpath(abs_target, repo_root).replace("\\", "/")
            written[rel] = new_content
        except OSError as e:
            errors.append(f"Write failed for {np}: {e}")
    return written, errors


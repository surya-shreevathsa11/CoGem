from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class WritePlanItem:
    original_name: str
    target_path: str
    allowed: bool
    reason: str = ""


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


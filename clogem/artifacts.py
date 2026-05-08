from __future__ import annotations

import difflib
import os
import re
from typing import Dict, List


def extract_code(text: str) -> str:
    match = re.search(r"```(?:\w+)?\n([\s\S]*?)```", text or "")
    return match.group(1).strip() if match else (text or "")


def extract_files(text: str) -> Dict[str, str]:
    pattern = r"FILE:\s*(.*?)\n([\s\S]*?)(?=FILE:|$)"
    matches = re.findall(pattern, text or "")
    return {name.strip(): content.strip() for name, content in matches}


def extract_unified_diff(text: str) -> str:
    s = text or ""
    m = re.search(r"```diff\s*\n([\s\S]*?)```", s, re.I)
    if m:
        return (m.group(1) or "").strip()
    # Fallback: treat raw content as diff if it has standard file headers.
    if ("--- a/" in s and "+++ b/" in s) or ("\n--- " in s and "\n+++ " in s):
        return s.strip()
    return ""


def pick_entry(paths: List[str], preferred_basenames: List[str]) -> str:
    for pref in preferred_basenames:
        pl = pref.lower()
        for p in paths:
            if os.path.basename(p).lower() == pl:
                return p
    return sorted(paths)[0]


def get_diff(old: str, new: str) -> str:
    diff = difflib.unified_diff(
        (old or "").splitlines(),
        (new or "").splitlines(),
        lineterm="",
    )
    return "\n".join(diff)

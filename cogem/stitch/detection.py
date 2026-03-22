"""Heuristic detection of UI-heavy / frontend-first tasks for the Stitch stage."""

from __future__ import annotations

import re
from typing import Pattern, Tuple

# Strong signals: user wants a visual web UI, not only backend APIs.
_FRONTEND_LINE_PATTERNS: Tuple[Pattern[str], ...] = (
    re.compile(
        r"\b(build|create|make|design|scaffold|generate)\b.{0,80}\b("
        r"website|web site|landing page|home\s*page|homepage|portfolio\s*site|"
        r"dashboard\s*ui|dashboard|marketing\s*site|saas\s*landing|"
        r"frontend|front-end|static\s*site|single\s*page\s*app|spa\b|"
        r"html\s*/\s*css|html\s*css\s*js|css\s*js|tailwind\s*page|"
        r"responsive\s*(layout|page|site)|ui\s*mockup|wireframe\s*to\s*code"
        r")\b",
        re.I | re.DOTALL,
    ),
    re.compile(
        r"\b("
        r"landing page|marketing page|hero section|navbar|nav bar|"
        r"component library page|design system page|style guide page"
        r")\b",
        re.I,
    ),
)

# Secondary: must appear with at least one primary-ish intent word.
_SECONDARY = re.compile(
    r"\b(ui|ux|interface|layout|styling|responsive|tailwind|css|html|"
    r"component|page design|visual design)\b",
    re.I,
)
_INTENT = re.compile(
    r"\b(build|create|make|design|implement|add|scaffold|generate)\b",
    re.I,
)


def detect_frontend_task(text: str) -> bool:
    """
    Return True when the task is likely a frontend-heavy deliverable suitable
    for a Stitch-first workflow. Conservative: avoid API-only or CLI-only work.
    """
    if not text or len(text.strip()) < 10:
        return False
    t = text.strip()
    # Exclude obvious non-UI backend-only phrases (still may false-negative).
    if re.search(
        r"\b(only\s+)?(rest\s*api|graphql\s*server|database\s*schema|"
        r"migration|dockerfile|kubernetes|terraform)\b",
        t,
        re.I,
    ) and not _SECONDARY.search(t):
        return False

    for pat in _FRONTEND_LINE_PATTERNS:
        if pat.search(t):
            return True

    if _SECONDARY.search(t) and _INTENT.search(t):
        if re.search(
            r"\b(website|web\s*app|frontend|front-end|html|css|page|dashboard|"
            r"landing|portfolio|homepage|tailwind|react|vue|svelte)\b",
            t,
            re.I,
        ):
            return True

    return False


def should_skip_stitch_due_to_attachments(attach_block: str) -> bool:
    """If @ mentions already include substantial HTML/CSS, skip redundant Stitch."""
    if not attach_block or len(attach_block) < 200:
        return False
    lower = attach_block.lower()
    if "<!doctype html" in lower or "<html" in lower:
        return True
    if attach_block.count("### ") >= 1 and (
        ".html" in lower or ".css" in lower or "tailwind" in lower
    ):
        return True
    return False

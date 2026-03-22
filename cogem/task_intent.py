"""
Intent helpers for routing: e.g. user asks for explanation / how-to before implementation.
"""

from __future__ import annotations

import re


def detect_prerequisite_first_task(text: str) -> bool:
    """
    True when the user clearly wants an informational answer *before* a build/coding step.

    Examples:
    - "build a website but before that tell me how to connect Stitch via MCP"
    - "first explain how X works, then we'll implement Y"
    """
    if not text or len(text.strip()) < 12:
        return False
    t = text.strip().lower()

    # Strong single-span: "before that/this" followed soon by tell/explain/how/need
    if re.search(
        r"before\s+(that|this)\b.{0,120}?\b("
        r"tell\s+me|explain|need\s+(you\s+to\s+)?(to\s+)?(tell|know)|"
        r"how\s+(do|can|to)\s+(i|we)|show\s+me\s+how"
        r")\b",
        t,
        re.DOTALL,
    ):
        return True

    # "but first" / "first" then informational ask (not "first build")
    if re.search(
        r"\b(but\s+)?first\b(?!\s+(build|create|make|implement|add|write|code))\b"
        r".{0,140}?\b("
        r"tell\s+me|explain|how\s+(do|can|to)|need\s+to\s+know|show\s+me"
        r")\b",
        t,
        re.DOTALL,
    ):
        return True

    # Before starting work
    if re.search(
        r"before\s+(i|we)\s+(build|start|begin|code)|before\s+(building|starting)\b",
        t,
    ) and re.search(
        r"\b("
        r"tell\s+me|explain|how\s+(do|can|to)|what\s+do\s+i\s+need|need\s+to\s+know"
        r")\b",
        t,
    ):
        return True

    # Ordering + info question in one message (both present)
    has_order = bool(
        re.search(
            r"\b("
            r"before\s+(that|this|you|we)|but\s+before|not\s+yet|"
            r"hold\s+on|wait\b|prerequisite|first\s+though"
            r")\b",
            t,
        )
    )
    has_info = bool(
        re.search(
            r"\b("
            r"tell\s+me\s+how|explain\s+how|how\s+do\s+i|how\s+can\s+i|how\s+to\s+"
            r"(connect|set\s+up|install|configure|use)|"
            r"need\s+(you\s+to\s+)?(tell|explain)|need\s+to\s+know|"
            r"what\s+('?s|is)\s+the\s+(way|steps)"
            r")\b",
            t,
        )
    )
    if has_order and has_info:
        return True

    return False


def build_prerequisite_first_prompt(task: str, mem_block: str) -> str:
    """Codex prompt when we answer the informational part first (router over-corrected to BUILD)."""
    mem_ctx = mem_block.strip() if mem_block.strip() else "(none yet)"
    return (
        "You are Cogem's assistant. The user wrote a message that asks for information, "
        "setup steps, or HOW-TO help *before* they want a full coding/build pipeline.\n"
        "Answer ONLY what they need first (concepts, MCP/Stitch connection steps, env vars, "
        "links to docs). Do NOT generate a full website or multi-file project in this reply.\n"
        "If they asked about Google Stitch + MCP in cogem: mention `COGEM_STITCH_MCP=1`, Node/npx, "
        "`GOOGLE_CLOUD_PROJECT`, `gcloud auth application-default login`, and that cogem can "
        "spawn `npx stitch-mcp` per README — stay consistent with the project's documented behavior.\n"
        "Use plain text. Short fenced blocks only for commands or JSON snippets.\n"
        "Be concise unless they asked for depth.\n\n"
        f"Saved context:\n---\n{mem_ctx}\n---\n\n"
        f"User message:\n---\n{task}\n---\n"
    )

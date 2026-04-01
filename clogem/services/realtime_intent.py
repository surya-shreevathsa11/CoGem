from __future__ import annotations

import datetime
import re
from typing import Optional


def local_datetime_context_block() -> str:
    """Authoritative local 'now' for the user's machine (for 'today' / 'current')."""
    now = datetime.datetime.now().astimezone()
    return (
        f"Local date/time (authoritative for 'today', 'now', 'current'): "
        f"{now.isoformat(timespec='seconds')}\n"
        f"Local timezone: {now.tzname()} (UTC offset {now.strftime('%z')})\n"
    )


def needs_realtime_web_assist(text: str) -> bool:
    """
    True when the user likely needs live web data (weather, headlines, etc.).

    Narrow on purpose: only these turns are routed to Gemini + Google Search grounding.
    """
    t = (text or "").strip().lower()
    if not t or len(t) > 4000:
        return False
    if "```" in t:
        return False
    # Likely coding / repo work — do not hijack with web search.
    if re.search(r"\b(import|from\s+\w+\s+import|def\s+\w+\s*\(|class\s+\w+\s*:)\b", t):
        return False
    if re.search(
        r"\b(build|implement|create|write|refactor|debug|fix)\s+(a\s+)?"
        r"(weather|forecast|news)\s+(app|api|component|site|widget|cli)\b",
        t,
    ):
        return False
    if re.search(r"\bweather\s+(api|app|variable|class|function|module)\b", t):
        return False

    if re.search(r"\b(weather|forecast)\b", t):
        return True
    if re.search(r"\b(temperature|humidity|wind speed)\b", t) and re.search(
        r"\b(in|at|for|near|today|now|current|tonight)\b", t
    ):
        return True
    if re.search(r"\b(latest|breaking|current)\s+news\b", t):
        return True
    if re.search(r"\bnews\s+headlines\b", t) or re.search(r"\bheadlines?\b", t):
        if re.search(r"\b(news|today|latest|breaking|world|local)\b", t):
            return True
    if re.search(
        r"\b(stock|share)\s+price\b.*\b(today|now|current|right now)\b", t
    ) or re.search(
        r"\b(today|now|current)\b.*\b(stock|share)\s+price\b", t
    ):
        return True
    return False


def build_realtime_gemini_prompt(*, local_block: str, user_question: str) -> str:
    return (
        "You answer questions that require up-to-date real-world information.\n"
        "Use Google Search grounding when needed. Do not rely on memorized or outdated "
        "training data for weather, dates, or breaking news.\n\n"
        f"{local_block}\n"
        "User question:\n"
        "---\n"
        f"{(user_question or '').strip()}\n"
        "---\n"
        "Be concise. If you cannot retrieve reliable current data, say so clearly.\n"
    )

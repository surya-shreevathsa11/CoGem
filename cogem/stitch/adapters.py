"""Pluggable Stitch adapters: CLI, HTTP, browser stub, manual fallback."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Literal, Optional


Mode = Literal["direct", "manual", "unavailable"]


@dataclass
class StitchResult:
    """Outcome of attempting to obtain Stitch-generated UI."""

    mode: Mode
    content: Optional[str]  # HTML/CSS/JS text when mode == direct
    adapter_name: str
    detail: str = ""

    @classmethod
    def direct(cls, content: str, adapter_name: str) -> "StitchResult":
        return cls(mode="direct", content=content.strip() or None, adapter_name=adapter_name)

    @classmethod
    def manual(cls, detail: str = "") -> "StitchResult":
        return cls(mode="manual", content=None, adapter_name="manual", detail=detail)

    @classmethod
    def unavailable(cls, adapter_name: str, detail: str = "") -> "StitchResult":
        return cls(mode="unavailable", content=None, adapter_name=adapter_name, detail=detail)


def try_stitch_adapters(stitch_prompt: str) -> StitchResult:
    """
    Try adapters in order:
    1. COGEM_STITCH_CLI — subprocess (stdin or temp file)
    2. COGEM_STITCH_MCP — MCP stdio client to `npx stitch-mcp` (on by default; set COGEM_STITCH_MCP=0 to disable)
    3. COGEM_STITCH_HTTP_URL — HTTP POST JSON { "prompt": "..." }
    4. COGEM_STITCH_BROWSER — optional stub (disabled unless set; not implemented)
    5. manual — always succeeds as fallback
    """
    if not (stitch_prompt or "").strip():
        return StitchResult.manual("empty prompt")

    r = _try_cli_adapter(stitch_prompt)
    if r.mode == "direct" and r.content:
        return r

    r = _try_mcp_adapter(stitch_prompt)
    if r.mode == "direct" and r.content:
        return r

    r = _try_http_adapter(stitch_prompt)
    if r.mode == "direct" and r.content:
        return r

    r = _try_browser_adapter(stitch_prompt)
    if r.mode == "direct" and r.content:
        return r

    return StitchResult.manual(
        "No direct Stitch integration succeeded; use manual export (see cogem instructions)."
    )


def _try_mcp_adapter(prompt: str) -> StitchResult:
    """Talk to the stitch-mcp npm package via MCP over stdio (see mcp_stdio)."""
    try:
        from .mcp_stdio import call_stitch_mcp_generate, stitch_mcp_enabled
    except ImportError:
        return StitchResult.unavailable("mcp", "mcp_stdio not available")

    if not stitch_mcp_enabled():
        return StitchResult.unavailable("mcp", "disabled (set COGEM_STITCH_MCP=1 to enable)")

    html, detail = call_stitch_mcp_generate(prompt)
    if html and looks_like_ui_content(html):
        return StitchResult.direct(html, "mcp")
    if html:
        return StitchResult.direct(html, "mcp")
    return StitchResult.unavailable("mcp", detail or "no HTML returned")


def _try_cli_adapter(prompt: str) -> StitchResult:
    raw_cli = (os.environ.get("COGEM_STITCH_CLI") or "").strip()
    if not raw_cli:
        return StitchResult.unavailable("cli", "COGEM_STITCH_CLI not set")

    argv = shlex_split(raw_cli)
    extra = os.environ.get("COGEM_STITCH_CLI_ARGS", "")
    if extra.strip():
        argv.extend(shlex_split(extra))

    if not shutil.which(argv[0]) and not os.path.isfile(argv[0]):
        return StitchResult.unavailable(
            "cli", f"executable not found: {argv[0]}"
        )

    use_stdin = (os.environ.get("COGEM_STITCH_CLI_STDIN", "1").strip().lower() not in ("0", "false", "no"))
    tmp_path: Optional[str] = None
    try:
        if not use_stdin:
            fd, tmp_path = tempfile.mkstemp(suffix=".txt", prefix="cogem-stitch-")
            os.close(fd)
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(prompt)
            argv.append(tmp_path)

        proc = subprocess.run(
            argv,
            input=prompt if use_stdin else None,
            capture_output=True,
            text=True,
            timeout=_timeout_sec(),
            stdin=subprocess.PIPE if use_stdin else None,
        )
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if proc.returncode == 0 and out and _looks_like_markup(out):
            return StitchResult.direct(out, "cli")
        if proc.returncode == 0 and out:
            return StitchResult.direct(out, "cli")
        return StitchResult.unavailable(
            "cli",
            f"exit={proc.returncode} stderr={err[:1200]}",
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        return StitchResult.unavailable("cli", str(e))
    finally:
        if tmp_path and os.path.isfile(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def shlex_split(s: str) -> list[str]:
    import shlex

    return shlex.split(s, posix=os.name != "nt")


def _timeout_sec() -> int:
    try:
        return max(30, int(os.environ.get("COGEM_STITCH_TIMEOUT_SEC", "300")))
    except ValueError:
        return 300


def looks_like_ui_content(s: str) -> bool:
    """True if text plausibly contains HTML/CSS UI (paste detection)."""
    return _looks_like_markup(s)


def _looks_like_markup(s: str) -> bool:
    t = s[:8000].lower()
    return (
        "<html" in t
        or "<!doctype" in t
        or "<section" in t
        or ("<div" in t and "class=" in t)
        or ("<button" in t and "<" in t)
    )


def _try_http_adapter(prompt: str) -> StitchResult:
    url = (os.environ.get("COGEM_STITCH_HTTP_URL") or "").strip()
    if not url:
        return StitchResult.unavailable("http", "COGEM_STITCH_HTTP_URL not set")

    payload = {"prompt": prompt}
    raw_body = (os.environ.get("COGEM_STITCH_HTTP_BODY") or "").strip()
    if raw_body:
        try:
            payload = json.loads(raw_body)
            if isinstance(payload, dict) and "prompt" not in payload:
                payload["prompt"] = prompt
        except json.JSONDecodeError:
            payload = {"prompt": prompt}

    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    token = (os.environ.get("COGEM_STITCH_HTTP_TOKEN") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    method = (os.environ.get("COGEM_STITCH_HTTP_METHOD") or "POST").upper()
    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=_timeout_sec()) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        parsed = _extract_text_from_http_response(body)
        if parsed and _looks_like_markup(parsed):
            return StitchResult.direct(parsed, "http")
        if parsed:
            return StitchResult.direct(parsed, "http")
        return StitchResult.unavailable("http", "empty or non-text response")
    except (urllib.error.URLError, OSError) as e:
        return StitchResult.unavailable("http", str(e))


def _extract_text_from_http_response(body: str) -> str:
    if not body.strip():
        return ""
    try:
        data = json.loads(body)
        if isinstance(data, dict):
            for key in ("html", "content", "output", "text", "data"):
                v = data.get(key)
                if isinstance(v, str) and v.strip():
                    return v
            # nested
            inner = data.get("result")
            if isinstance(inner, dict):
                for key in ("html", "content", "output"):
                    v = inner.get(key)
                    if isinstance(v, str) and v.strip():
                        return v
        if isinstance(data, str):
            return data
    except json.JSONDecodeError:
        pass
    return body.strip()


def _try_browser_adapter(prompt: str) -> StitchResult:
    flag = (os.environ.get("COGEM_STITCH_BROWSER") or "").strip().lower()
    if flag not in ("1", "yes", "true", "on"):
        return StitchResult.unavailable("browser", "disabled (set COGEM_STITCH_BROWSER=1 to enable)")
    return StitchResult.unavailable(
        "browser",
        "browser automation adapter is not implemented (intentionally brittle; use CLI or manual export).",
    )


def format_stitch_context_for_codex(stitch_content: str) -> str:
    """Wrap Stitch output for Codex/Gemini prompts."""
    return (
        "\n\n---\n\n## Stitch / UI source (preserve layout and visual intent)\n\n"
        "```\n"
        + stitch_content.strip()
        + "\n```\n\n"
        "Refine and improve this UI; do not discard the structure unless a review item requires it.\n"
    )

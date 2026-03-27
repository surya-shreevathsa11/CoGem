"""
Minimal MCP client over stdio (Content-Length framing) for stitch-mcp.

stitch-mcp (npm) is an MCP *server*: clogem spawns it and speaks JSON-RPC to call
tools like generate_screen_from_text. Requires Node/npx and Google auth as per
https://www.npmjs.com/package/stitch-mcp (gcloud, GOOGLE_CLOUD_PROJECT, etc.).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

# Default tool name from Stitch / stitch-mcp docs (Google may rename; override via env).
_DEFAULT_GENERATE = "generate_screen_from_text"


def stitch_mcp_enabled() -> bool:
    raw = (os.environ.get("CLOGEM_STITCH_MCP") or "").strip().lower()
    if raw in ("0", "false", "no", "off", "disabled"):
        return False
    # Default ON for frontend Stitch-first flow.
    return True


def _mcp_argv() -> List[str]:
    cmd = (os.environ.get("CLOGEM_STITCH_MCP_CMD") or "npx").strip()
    args_raw = (os.environ.get("CLOGEM_STITCH_MCP_ARGS") or "-y stitch-mcp").strip()
    return [cmd] + _split_args(args_raw)


def _split_args(s: str) -> List[str]:
    import shlex

    return shlex.split(s, posix=os.name != "nt")


def _frame(body: bytes) -> bytes:
    return f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body


def _read_one_message(stream) -> Optional[Dict[str, Any]]:
    """Read a single JSON-RPC message using Content-Length framing."""
    header = b""
    while True:
        chunk = stream.read(1)
        if not chunk:
            return None
        header += chunk
        if header.endswith(b"\r\n\r\n"):
            break
        if len(header) > 65536:
            raise OSError("MCP: header too large")
    m = re.match(rb"Content-Length:\s*(\d+)\s*", header, re.I)
    if not m:
        raise OSError(f"MCP: bad header: {header[:200]!r}")
    n = int(m.group(1))
    body = stream.read(n)
    if len(body) != n:
        return None
    return json.loads(body.decode("utf-8"))


def _write_message(proc: subprocess.Popen, obj: Dict[str, Any]) -> None:
    raw = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    proc.stdin.write(_frame(raw))
    proc.stdin.flush()


def _extract_text_from_tool_result(result: Any) -> Optional[str]:
    if result is None:
        return None
    if isinstance(result, dict):
        if result.get("isError"):
            parts = result.get("content")
            if isinstance(parts, list) and parts:
                t = parts[0].get("text") if isinstance(parts[0], dict) else None
                if t:
                    return None
        content = result.get("content")
        if isinstance(content, list):
            texts: List[str] = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and isinstance(block.get("text"), str):
                    texts.append(block["text"])
            if texts:
                blob = "\n".join(texts).strip()
                if _looks_like_html(blob):
                    return blob
                try:
                    data = json.loads(blob)
                    return _html_from_stitch_json(data) or blob
                except json.JSONDecodeError:
                    return blob
    return None


def _html_from_stitch_json(data: Any) -> Optional[str]:
    if isinstance(data, str) and _looks_like_html(data):
        return data
    if not isinstance(data, dict):
        return None

    def walk(o: Any) -> Optional[str]:
        if isinstance(o, str) and _looks_like_html(o):
            return o
        if isinstance(o, dict):
            for k in ("html", "htmlCode", "content", "code", "text"):
                v = o.get(k)
                if isinstance(v, str) and _looks_like_html(v):
                    return v
            for v in o.values():
                w = walk(v)
                if w:
                    return w
        if isinstance(o, list):
            for it in o:
                w = walk(it)
                if w:
                    return w
        return None

    return walk(data)


def _looks_like_html(s: str) -> bool:
    t = s[:12000].lower()
    return "<!doctype html" in t or "<html" in t or ("<div" in t and "<" in t)


def call_stitch_mcp_generate(stitch_prompt: str) -> Tuple[Optional[str], str]:
    """
    Spawn stitch-mcp, run MCP handshake, call the generate tool, return (html_or_none, detail).
    """
    if not shutil.which(_mcp_argv()[0]) and not os.path.isfile(_mcp_argv()[0]):
        return None, f"MCP: command not found: {_mcp_argv()[0]}"

    tool = (os.environ.get("CLOGEM_STITCH_MCP_TOOL") or _DEFAULT_GENERATE).strip()
    prompt_key = (os.environ.get("CLOGEM_STITCH_MCP_PROMPT_KEY") or "prompt").strip()

    argv = _mcp_argv()
    env = os.environ.copy()
    proc: Optional[subprocess.Popen] = None
    t_err: Optional[threading.Thread] = None
    try:
        timeout = max(60, int(os.environ.get("CLOGEM_STITCH_MCP_TIMEOUT_SEC", "300")))
    except ValueError:
        timeout = 300

    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=False,
            bufsize=0,
        )
    except OSError as e:
        return None, f"MCP: failed to spawn {argv[0]}: {e}"

    err_chunks: List[bytes] = []

    def _drain_stderr() -> None:
        if proc and proc.stderr:
            for line in iter(proc.stderr.readline, b""):
                err_chunks.append(line)

    t_err = threading.Thread(target=_drain_stderr, daemon=True)
    t_err.start()

    def _watchdog() -> None:
        time.sleep(timeout)
        if proc and proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass

    threading.Thread(target=_watchdog, daemon=True).start()

    next_id = 1

    try:
        _write_message(
            proc,
            {
                "jsonrpc": "2.0",
                "id": next_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "clogem", "version": "0.1"},
                },
            },
        )
        init_id = next_id
        next_id += 1

        init_ok = False
        while True:
            msg = _read_one_message(proc.stdout)
            if msg is None:
                break
            if msg.get("id") is None:
                continue
            if msg.get("id") == init_id and "result" in msg:
                init_ok = True
                break
            if msg.get("id") == init_id and msg.get("error"):
                detail = str(msg.get("error"))
                return None, f"MCP initialize failed: {detail}"

        if not init_ok:
            return None, "MCP: no initialize response"

        _write_message(
            proc,
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        )

        args: Dict[str, Any] = {prompt_key: stitch_prompt}
        extra = (os.environ.get("CLOGEM_STITCH_MCP_TOOL_ARGS_JSON") or "").strip()
        if extra:
            try:
                args.update(json.loads(extra))
            except json.JSONDecodeError:
                return None, "CLOGEM_STITCH_MCP_TOOL_ARGS_JSON is not valid JSON"

        call_id = next_id
        _write_message(
            proc,
            {
                "jsonrpc": "2.0",
                "id": call_id,
                "method": "tools/call",
                "params": {"name": tool, "arguments": args},
            },
        )

        while True:
            msg = _read_one_message(proc.stdout)
            if msg is None:
                break
            if msg.get("method"):
                continue
            if msg.get("id") != call_id:
                continue
            if msg.get("error"):
                return None, f"MCP tools/call error: {msg.get('error')}"
            result = msg.get("result")
            text = _extract_text_from_tool_result(result)
            if text:
                return text, "ok"
            return None, f"MCP: empty or unrecognized tool result: {str(result)[:800]}"

        out = _stderr_hint(err_chunks)
        return None, "MCP: no tools/call response" + (f" | {out}" if out else "")
    except (OSError, json.JSONDecodeError) as e:
        out = _stderr_hint(err_chunks)
        return None, f"MCP transport error: {e}" + (f" | {out}" if out else "")
    finally:
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    proc.kill()
                except OSError:
                    pass
            if t_err is not None:
                t_err.join(timeout=1.0)


def _stderr_hint(err_chunks: List[bytes]) -> str:
    if not err_chunks:
        return ""
    tail = b"".join(err_chunks)[-4000:].decode("utf-8", errors="replace").strip()
    if not tail:
        return ""
    if "Fatal Startup Error" in tail or "gcloud" in tail.lower():
        return f"stderr (auth / project?): {tail[:1200]}"
    return f"stderr: {tail[:800]}"


from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class MCPPluginSpec:
    name: str
    cmd: str
    args: List[str]
    env: Dict[str, str]
    timeout_sec: int = 60


def _frame(body: bytes) -> bytes:
    return f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body


def _read_one_message(stream) -> Optional[Dict[str, Any]]:
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


def _load_specs_from_env() -> Dict[str, MCPPluginSpec]:
    raw = (os.environ.get("CLOGEM_MCP_PLUGINS_JSON") or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    out: Dict[str, MCPPluginSpec] = {}
    for name, cfg in data.items():
        if not isinstance(name, str) or not isinstance(cfg, dict):
            continue
        cmd = str(cfg.get("cmd", "")).strip()
        if not cmd:
            continue
        args_raw = str(cfg.get("args", "")).strip()
        args = shlex.split(args_raw, posix=os.name != "nt") if args_raw else []
        env = cfg.get("env", {})
        if not isinstance(env, dict):
            env = {}
        timeout = int(cfg.get("timeout_sec", 60))
        out[name] = MCPPluginSpec(name, cmd, args, {str(k): str(v) for k, v in env.items()}, timeout)
    return out


def _load_builtin_specs() -> Dict[str, MCPPluginSpec]:
    # Enable by setting *_CMD and optional *_ARGS env vars.
    builtins = {
        "jira": ("CLOGEM_MCP_JIRA_CMD", "CLOGEM_MCP_JIRA_ARGS"),
        "sentry": ("CLOGEM_MCP_SENTRY_CMD", "CLOGEM_MCP_SENTRY_ARGS"),
        "datadog": ("CLOGEM_MCP_DATADOG_CMD", "CLOGEM_MCP_DATADOG_ARGS"),
        "dbschema": ("CLOGEM_MCP_DBSCHEMA_CMD", "CLOGEM_MCP_DBSCHEMA_ARGS"),
    }
    out: Dict[str, MCPPluginSpec] = {}
    for name, (k_cmd, k_args) in builtins.items():
        cmd = (os.environ.get(k_cmd) or "").strip()
        if not cmd:
            continue
        args_raw = (os.environ.get(k_args) or "").strip()
        args = shlex.split(args_raw, posix=os.name != "nt") if args_raw else []
        timeout = max(20, int((os.environ.get("CLOGEM_MCP_TIMEOUT_SEC") or "60").strip() or "60"))
        out[name] = MCPPluginSpec(name=name, cmd=cmd, args=args, env={}, timeout_sec=timeout)
    return out


def load_registry() -> Dict[str, MCPPluginSpec]:
    reg: Dict[str, MCPPluginSpec] = {}
    reg.update(_load_builtin_specs())
    reg.update(_load_specs_from_env())
    return reg


def _start_plugin(spec: MCPPluginSpec) -> Tuple[Optional[subprocess.Popen], str]:
    if not shutil.which(spec.cmd) and not os.path.isfile(spec.cmd):
        return None, f"command not found: {spec.cmd}"
    env = os.environ.copy()
    env.update(spec.env or {})
    try:
        proc = subprocess.Popen(
            [spec.cmd] + list(spec.args),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=False,
            bufsize=0,
        )
        return proc, ""
    except OSError as e:
        return None, str(e)


def _initialize(proc: subprocess.Popen, timeout_sec: int) -> Tuple[bool, str]:
    next_id = 1
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
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_sec:
        msg = _read_one_message(proc.stdout)
        if msg is None:
            break
        if msg.get("id") == init_id and "result" in msg:
            _write_message(
                proc, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
            )
            return True, ""
        if msg.get("id") == init_id and msg.get("error"):
            return False, str(msg.get("error"))
    return False, "initialize timeout/no response"


def _call_jsonrpc(proc: subprocess.Popen, method: str, params: Dict[str, Any], timeout_sec: int) -> Tuple[bool, Any, str]:
    req_id = int(time.time() * 1000) % 100000000
    _write_message(proc, {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_sec:
        msg = _read_one_message(proc.stdout)
        if msg is None:
            break
        if msg.get("method"):
            continue
        if msg.get("id") != req_id:
            continue
        if msg.get("error"):
            return False, None, str(msg.get("error"))
        return True, msg.get("result"), ""
    return False, None, "tools response timeout/no response"


def _close_proc(proc: Optional[subprocess.Popen]) -> None:
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def list_plugins() -> List[str]:
    return sorted(load_registry().keys())


def list_tools(plugin_name: str) -> Tuple[bool, str]:
    reg = load_registry()
    spec = reg.get(plugin_name)
    if not spec:
        return False, f"Unknown plugin: {plugin_name}"
    proc, err = _start_plugin(spec)
    if not proc:
        return False, err
    try:
        ok, detail = _initialize(proc, spec.timeout_sec)
        if not ok:
            return False, detail
        ok, result, detail = _call_jsonrpc(proc, "tools/list", {}, spec.timeout_sec)
        if not ok:
            return False, detail
        tools = []
        for t in (result or {}).get("tools", []) if isinstance(result, dict) else []:
            if isinstance(t, dict):
                nm = str(t.get("name", "")).strip()
                ds = str(t.get("description", "")).strip()
                if nm:
                    tools.append(f"- {nm}: {ds}" if ds else f"- {nm}")
        return True, "\n".join(tools) if tools else "(no tools reported)"
    finally:
        _close_proc(proc)


def call_tool(plugin_name: str, tool_name: str, args_obj: Dict[str, Any]) -> Tuple[bool, str]:
    reg = load_registry()
    spec = reg.get(plugin_name)
    if not spec:
        return False, f"Unknown plugin: {plugin_name}"
    proc, err = _start_plugin(spec)
    if not proc:
        return False, err
    err_chunks: List[bytes] = []

    def _drain_stderr() -> None:
        if proc and proc.stderr:
            for line in iter(proc.stderr.readline, b""):
                err_chunks.append(line)

    t_err = threading.Thread(target=_drain_stderr, daemon=True)
    t_err.start()
    try:
        ok, detail = _initialize(proc, spec.timeout_sec)
        if not ok:
            return False, detail
        ok, result, detail = _call_jsonrpc(
            proc,
            "tools/call",
            {"name": tool_name, "arguments": args_obj or {}},
            spec.timeout_sec,
        )
        if not ok:
            return False, detail
        if isinstance(result, dict):
            c = result.get("content")
            if isinstance(c, list):
                texts: List[str] = []
                for block in c:
                    if isinstance(block, dict) and isinstance(block.get("text"), str):
                        texts.append(block["text"])
                if texts:
                    return True, "\n".join(texts).strip()
        return True, json.dumps(result, ensure_ascii=False, indent=2)
    finally:
        _close_proc(proc)
        t_err.join(timeout=0.5)

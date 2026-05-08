import json
import time

import pytest

from clogem.mcp_plugins import _read_one_message, load_registry


def test_mcp_registry_from_json_env(monkeypatch):
    cfg = {
        "jira": {"cmd": "npx", "args": "-y jira-mcp", "timeout_sec": 42},
        "sentry": {"cmd": "python", "args": "-m sentry_mcp"},
    }
    monkeypatch.setenv("CLOGEM_MCP_PLUGINS_JSON", json.dumps(cfg))
    reg = load_registry()
    assert "jira" in reg
    assert reg["jira"].cmd == "npx"
    assert reg["jira"].timeout_sec == 42
    assert reg["sentry"].cmd == "python"


def test_mcp_builtin_alias_from_env(monkeypatch):
    monkeypatch.delenv("CLOGEM_MCP_PLUGINS_JSON", raising=False)
    monkeypatch.setenv("CLOGEM_MCP_JIRA_CMD", "npx")
    monkeypatch.setenv("CLOGEM_MCP_JIRA_ARGS", "-y jira-mcp")
    reg = load_registry()
    assert "jira" in reg
    assert reg["jira"].cmd == "npx"
    assert "jira-mcp" in " ".join(reg["jira"].args)


def test_mcp_read_one_message_timeout_on_blocking_stream():
    class _BlockingStream:
        def read(self, _n):
            time.sleep(0.2)
            return b""

    t0 = time.monotonic()
    with pytest.raises(TimeoutError):
        _read_one_message(_BlockingStream(), timeout_sec=0.05)
    assert time.monotonic() - t0 < 0.2


"""Tests for Stitch frontend detection and prompt builder."""

import pytest

from cogem.stitch import (
    build_stitch_prompt,
    detect_frontend_task,
    should_skip_stitch_due_to_attachments,
)
from cogem.stitch.adapters import looks_like_ui_content, try_stitch_adapters


def test_detect_frontend_landing_page():
    assert detect_frontend_task("Build a landing page for a SaaS analytics product")


def test_detect_frontend_dashboard():
    assert detect_frontend_task("Create a dashboard UI for admin users with charts")


def test_detect_frontend_negative_api_only():
    assert not detect_frontend_task(
        "Add a REST API with PostgreSQL migrations and Docker only, no UI"
    )


def test_build_stitch_prompt_non_empty():
    p = build_stitch_prompt("make a portfolio site")
    assert "portfolio" in p.lower() or "product" in p.lower()
    assert "accessibility" in p.lower()
    assert "responsive" in p.lower()
    assert "ai template" in p.lower() or "ai-made" in p.lower()


def test_skip_stitch_large_html_attachment():
    block = "### @x\n```\n" + "<!DOCTYPE html><html><body>x</body></html>" * 30 + "\n```\n"
    assert should_skip_stitch_due_to_attachments(block)


def test_looks_like_ui_content():
    assert looks_like_ui_content("<!DOCTYPE html><html></html>")
    assert not looks_like_ui_content("just prose")


def test_try_stitch_adapters_falls_back_manual(monkeypatch):
    monkeypatch.delenv("COGEM_STITCH_CLI", raising=False)
    monkeypatch.delenv("COGEM_STITCH_HTTP_URL", raising=False)
    monkeypatch.delenv("COGEM_STITCH_MCP", raising=False)
    r = try_stitch_adapters("Design a hero section")
    assert r.mode == "manual"


def test_stitch_mcp_flag(monkeypatch):
    from cogem.stitch.mcp_stdio import stitch_mcp_enabled

    monkeypatch.delenv("COGEM_STITCH_MCP", raising=False)
    assert stitch_mcp_enabled()
    monkeypatch.setenv("COGEM_STITCH_MCP", "0")
    assert not stitch_mcp_enabled()
    monkeypatch.setenv("COGEM_STITCH_MCP", "1")
    assert stitch_mcp_enabled()


def test_build_stitch_prompt_style_override_present():
    p = build_stitch_prompt("Build a homepage using the Inter font and dark theme")
    assert "style override rule" in p.lower()
    assert "explicitly requested a style" in p.lower()

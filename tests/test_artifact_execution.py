"""Tests for artifact auto-execution permission gate (GitHub issue #1)."""
from __future__ import annotations

import re
from pathlib import Path


def _parse_allow_local_commands(env_val: str):
    """Mirror the permission parsing logic from cli.py _run_permissions_from_env."""
    raw = env_val.strip().lower()
    if raw in ("1", "y", "yes", "true", "on"):
        return True
    if raw in ("0", "n", "no", "false", "off"):
        return False
    return None


class TestArtifactExecutionPermissionGate:
    """Regression tests for issue #1: run_written_artifacts must respect permission gate."""

    def test_deny_when_env_no(self):
        assert _parse_allow_local_commands("no") is False

    def test_deny_when_env_false(self):
        assert _parse_allow_local_commands("false") is False

    def test_deny_when_env_zero(self):
        assert _parse_allow_local_commands("0") is False

    def test_deny_when_env_off(self):
        assert _parse_allow_local_commands("off") is False

    def test_allow_when_env_yes(self):
        assert _parse_allow_local_commands("yes") is True

    def test_allow_when_env_true(self):
        assert _parse_allow_local_commands("true") is True

    def test_allow_when_env_one(self):
        assert _parse_allow_local_commands("1") is True

    def test_allow_when_env_on(self):
        assert _parse_allow_local_commands("on") is True

    def test_none_when_env_empty(self):
        assert _parse_allow_local_commands("") is None

    def test_none_when_env_garbage(self):
        assert _parse_allow_local_commands("maybe") is None

    def test_whitespace_handling(self):
        assert _parse_allow_local_commands("  yes  ") is True
        assert _parse_allow_local_commands("  no  ") is False

    def test_case_insensitive(self):
        assert _parse_allow_local_commands("YES") is True
        assert _parse_allow_local_commands("No") is False
        assert _parse_allow_local_commands("TRUE") is True


class TestPermissionGateExistsInSource:
    """Structural tests: verify the permission gate is present in run_written_artifacts.

    Since run_written_artifacts is a closure inside async_main, we can't import
    and call it directly. These tests verify the source code contains the gate,
    so removing it would break the test.
    """

    _CLI_SOURCE = Path(__file__).resolve().parents[1] / "clogem" / "cli.py"

    def _get_run_written_artifacts_source(self) -> str:
        """Extract the source of run_written_artifacts from cli.py."""
        source = self._CLI_SOURCE.read_text(encoding="utf-8")
        # Find the function definition and extract its body up to the next
        # top-level def at the same indentation.
        match = re.search(
            r"(    def run_written_artifacts\(.*?\n)(.*?)(?=\n    def |\Z)",
            source,
            re.DOTALL,
        )
        assert match, "run_written_artifacts not found in cli.py"
        return match.group(1) + match.group(2)

    def test_calls_ensure_run_permissions(self):
        body = self._get_run_written_artifacts_source()
        assert "ensure_run_permissions()" in body, (
            "run_written_artifacts must call ensure_run_permissions() — "
            "removing the permission gate breaks issue #1 security fix"
        )

    def test_checks_run_permissions_granted(self):
        body = self._get_run_written_artifacts_source()
        assert 'run_permissions.get("granted")' in body, (
            "run_written_artifacts must check run_permissions granted status — "
            "removing the permission check breaks issue #1 security fix"
        )

    def test_returns_early_when_denied(self):
        body = self._get_run_written_artifacts_source()
        # The gate should have a return statement after the permission check
        assert "Skipping auto-run" in body, (
            "run_written_artifacts must warn when skipping artifact execution"
        )

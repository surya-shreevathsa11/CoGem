from __future__ import annotations

from cogem.command_policy import validate_local_command_args


def test_blocks_shell_executable():
    ok, reason = validate_local_command_args(["bash", "-lc", "echo hi"], "run")
    assert not ok
    assert "not allowed" in reason.lower()


def test_allows_git_status_in_run():
    ok, _ = validate_local_command_args(["git", "status"], "run")
    assert ok


def test_blocks_git_push_in_run():
    ok, reason = validate_local_command_args(["git", "push"], "run")
    assert not ok
    assert "not allowed" in reason.lower()


def test_allows_python_m_pytest_for_tests():
    ok, _ = validate_local_command_args(["python", "-m", "pytest"], "tests")
    assert ok


def test_blocks_python_script_in_run_strict():
    ok, reason = validate_local_command_args(["python", "script.py"], "run")
    assert not ok
    assert "only allows" in reason.lower()


def test_allows_poetry_run_pytest_for_tests():
    ok, _ = validate_local_command_args(["poetry", "run", "pytest"], "tests")
    assert ok


def test_allows_pnpm_test_for_tests():
    ok, _ = validate_local_command_args(["pnpm", "test"], "tests")
    assert ok


def test_allows_go_and_cargo_for_validation():
    ok_go, _ = validate_local_command_args(["go", "test", "./..."], "tests")
    ok_rust, _ = validate_local_command_args(["cargo", "check"], "typecheck")
    assert ok_go
    assert ok_rust


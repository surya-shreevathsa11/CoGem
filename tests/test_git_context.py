from __future__ import annotations

from pathlib import Path

from cogem.git_context import build_recent_git_log_context


def test_git_context_contains_commit_messages(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()

    # Init git repo
    import subprocess

    def run(cmd, cwd):
        subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)

    run(["git", "init"], str(repo))
    run(["git", "config", "user.email", "test@example.com"], str(repo))
    run(["git", "config", "user.name", "Test"], str(repo))

    f = repo / "a.py"
    f.write_text("x = 1\n", encoding="utf-8")
    run(["git", "add", "a.py"], str(repo))
    run(["git", "commit", "-m", "first"], str(repo))

    f.write_text("x = 2\n", encoding="utf-8")
    run(["git", "add", "a.py"], str(repo))
    run(["git", "commit", "-m", "second"], str(repo))

    ctx = build_recent_git_log_context(
        str(repo),
        [str(f)],
        max_entries_per_file=3,
        max_total_chars=4000,
    )
    assert "first" in ctx or "second" in ctx


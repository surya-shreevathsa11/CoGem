from __future__ import annotations

import os
import subprocess
from pathlib import Path

from clogem.validation import copy_git_tracked_repo_to_sandbox, git_tracked_files


def _run(cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def test_git_tracked_copy_excludes_untracked(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()

    _run(["git", "init"], cwd=str(repo))
    _run(["git", "config", "user.email", "test@example.com"], cwd=str(repo))
    _run(["git", "config", "user.name", "Test"], cwd=str(repo))

    tracked = repo / "tracked.txt"
    tracked.write_text("tracked", encoding="utf-8")
    untracked_dir = repo / "untracked_dir"
    untracked_dir.mkdir()
    (untracked_dir / "x.txt").write_text("untracked", encoding="utf-8")

    _run(["git", "add", "tracked.txt"], cwd=str(repo))
    _run(["git", "commit", "-m", "init"], cwd=str(repo))

    assert "tracked.txt" in git_tracked_files(str(repo))
    assert all("untracked_dir" not in p for p in git_tracked_files(str(repo)))

    sandbox = tmp_path / "sandbox"
    used, copied = copy_git_tracked_repo_to_sandbox(str(repo), str(sandbox))
    assert used is True
    assert copied >= 1
    assert (sandbox / "tracked.txt").exists()
    assert not (sandbox / "untracked_dir" / "x.txt").exists()


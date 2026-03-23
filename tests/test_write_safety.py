from __future__ import annotations

from pathlib import Path

from cogem.write_safety import plan_safe_writes


def test_plan_safe_writes_allows_in_repo(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    files = {"src/app.py": "print('ok')"}
    plan = plan_safe_writes(repo_root=str(repo), file_map=files)
    assert len(plan) == 1
    assert plan[0].allowed
    assert str(repo) in plan[0].target_path


def test_plan_safe_writes_blocks_traversal(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    files = {"../../outside.txt": "x"}
    plan = plan_safe_writes(repo_root=str(repo), file_map=files)
    assert len(plan) == 1
    assert not plan[0].allowed
    assert "escapes repo root" in plan[0].reason


def test_plan_safe_writes_blocks_absolute_outside(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside.txt"
    files = {str(outside): "x"}
    plan = plan_safe_writes(repo_root=str(repo), file_map=files)
    assert len(plan) == 1
    assert not plan[0].allowed
    assert "escapes repo root" in plan[0].reason


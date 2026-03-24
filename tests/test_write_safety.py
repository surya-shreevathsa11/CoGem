from __future__ import annotations

from pathlib import Path

from cogem.write_safety import (
    apply_unified_diff_safely,
    parse_unified_diff,
    plan_safe_writes,
)


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


def test_parse_unified_diff_detects_file_patch():
    diff = """--- a/src/app.py
+++ b/src/app.py
@@ -1,2 +1,2 @@
-print("a")
+print("b")
 x = 1
"""
    patches = parse_unified_diff(diff)
    assert len(patches) == 1
    assert patches[0].new_path == "b/src/app.py"
    assert len(patches[0].hunks) == 1


def test_apply_unified_diff_safely_updates_existing_file(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "src" / "app.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('print("a")\nx = 1\n', encoding="utf-8")
    diff = """--- a/src/app.py
+++ b/src/app.py
@@ -1,2 +1,2 @@
-print("a")
+print("b")
 x = 1
"""
    written, errors = apply_unified_diff_safely(repo_root=str(repo), diff_text=diff)
    assert not errors
    assert "src/app.py" in written
    assert target.read_text(encoding="utf-8") == 'print("b")\nx = 1\n'


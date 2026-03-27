from __future__ import annotations

from pathlib import Path

from clogem.repo_awareness import (
    AutoRepoContextConfig,
    build_repo_context_block,
    expand_dependency_closure,
    extract_task_keywords,
)


def test_extract_task_keywords_basic():
    kws = extract_task_keywords("Build a dashboard UI using Tailwind and charts")
    assert "dashboard" in kws or "charts" in kws


def test_python_dependency_closure_imports(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()

    # b.py imports nothing; a.py imports b.py.
    (repo / "b.py").write_text(
        "def meaning_of_life():\n    return 42\n",
        encoding="utf-8",
    )
    (repo / "a.py").write_text(
        "from b import meaning_of_life\n\n\ndef run():\n    return meaning_of_life()\n",
        encoding="utf-8",
    )

    a = str(repo / "a.py")
    closure = expand_dependency_closure([a], str(repo), max_files=5, max_depth=2)
    assert any(p.endswith("b.py") for p in closure)


def test_build_repo_context_block_includes_snippets(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "b.py").write_text(
        "def meaning_of_life():\n    return 42\n",
        encoding="utf-8",
    )
    (repo / "a.py").write_text(
        "from b import meaning_of_life\n\n\ndef run():\n    return meaning_of_life()\n",
        encoding="utf-8",
    )

    cfg = AutoRepoContextConfig(enabled=True, max_chars=6000, max_files=6, max_depth=2)
    block = build_repo_context_block(
        str(repo),
        task="How does meaning_of_life work? Please implement fix for run()",
        max_chars=cfg.max_chars,
        max_files=cfg.max_files,
        max_depth=cfg.max_depth,
    )
    assert "b.py" in block or "a.py" in block


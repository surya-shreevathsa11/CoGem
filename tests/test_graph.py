from __future__ import annotations

from pathlib import Path

from cogem.graph import (
    build_symbol_dependency_context_from_py_files,
    extract_python_imported_symbols,
)
from cogem.symbols import TagMatch, SymbolIndex


def test_extract_python_imported_symbols_from_importfrom():
    src = """
from cogem.symbols import SymbolIndex
from cogem.task_intent import detect_prerequisite_first_task as d
"""
    out = extract_python_imported_symbols(src)
    names = {o.symbol for o in out}
    assert "SymbolIndex" in names
    assert "detect_prerequisite_first_task" in names


def test_build_symbol_dependency_context_prefers_imported_module_path(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()

    symbols_py = repo / "cogem" / "symbols.py"
    symbols_py.parent.mkdir()
    symbols_py.write_text(
        "\n".join(
            [
                "class SymbolIndex:",
                "    pass",
                "",
                "def helper():",
                "    return 1",
            ]
        ),
        encoding="utf-8",
    )

    # Create a python file that imports from cogem.symbols
    use = repo / "use.py"
    use.write_text(
        "\n".join(
            [
                "from cogem.symbols import SymbolIndex",
                "",
                "def x():",
                "    return SymbolIndex()",
            ]
        ),
        encoding="utf-8",
    )

    idx = SymbolIndex(
        str(repo),
        tag_records=[
            TagMatch(
                name="SymbolIndex",
                path=str(symbols_py),
                line=1,
                kind="class",
            )
        ],
    )

    block = build_symbol_dependency_context_from_py_files(
        repo_root=str(repo),
        py_files=[str(use)],
        symbol_index=idx,
        max_symbols=5,
        max_chars=4000,
    )
    assert "SymbolIndex" in block
    assert "Symbol dependencies" in block


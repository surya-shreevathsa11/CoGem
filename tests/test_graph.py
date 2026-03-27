from __future__ import annotations

from pathlib import Path

from clogem.graph import (
    build_symbol_dependency_context_from_py_files,
    build_symbol_dependency_context_from_source_files,
    extract_js_imported_symbols,
    extract_python_imported_symbols,
)
from clogem.symbols import TagMatch, SymbolIndex


def test_extract_python_imported_symbols_from_importfrom():
    src = """
from clogem.symbols import SymbolIndex
from clogem.task_intent import detect_prerequisite_first_task as d
"""
    out = extract_python_imported_symbols(src)
    names = {o.symbol for o in out}
    assert "SymbolIndex" in names
    assert "detect_prerequisite_first_task" in names


def test_extract_js_imported_symbols_from_named_imports_aliases():
    src = """
import {A, B as C} from './m';
import * as Ns from './ns';
import DefaultThing from './d';
import 'side-effect';
"""
    out = extract_js_imported_symbols(src)
    syms = {(o.specifier, o.symbol) for o in out}
    assert ("./m", "A") in syms
    assert ("./m", "B") in syms
    assert ("./ns", "Ns") in syms
    assert ("./d", "DefaultThing") in syms


def test_build_symbol_dependency_context_prefers_imported_module_path(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()

    symbols_py = repo / "clogem" / "symbols.py"
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

    # Create a python file that imports from clogem.symbols
    use = repo / "use.py"
    use.write_text(
        "\n".join(
            [
                "from clogem.symbols import SymbolIndex",
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


def test_build_symbol_dependency_context_from_js_ts_named_imports(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()

    src_dir = repo / "src"
    src_dir.mkdir()

    local_lib = src_dir / "lib.ts"
    local_lib.write_text(
        "\n".join(
            [
                "export const Thing = 123;",
                'export function Other() { return "local"; }',
            ]
        ),
        encoding="utf-8",
    )

    other_lib_dir = src_dir / "other"
    other_lib_dir.mkdir()
    other_lib = other_lib_dir / "lib.ts"
    other_lib.write_text(
        "\n".join(
            [
                "export const Thing = 999;",
                'export function Other() { return "other"; }',
            ]
        ),
        encoding="utf-8",
    )

    use = src_dir / "use.ts"
    use.write_text(
        "\n".join(
            [
                "import { Thing, Other as IgnoredAlias } from './lib';",
                "export const x = Thing;",
            ]
        ),
        encoding="utf-8",
    )

    idx = SymbolIndex(
        str(repo),
        tag_records=[
            TagMatch(
                name="Thing",
                path=str(local_lib.resolve()),
                line=1,
                kind="variable",
            ),
            TagMatch(
                name="Other",
                path=str(local_lib.resolve()),
                line=2,
                kind="function",
            ),
            TagMatch(
                name="Thing",
                path=str(other_lib.resolve()),
                line=1,
                kind="variable",
            ),
            TagMatch(
                name="Other",
                path=str(other_lib.resolve()),
                line=2,
                kind="function",
            ),
        ],
    )

    block = build_symbol_dependency_context_from_source_files(
        repo_root=str(repo),
        source_files=[str(use)],
        symbol_index=idx,
        max_symbols=5,
        max_chars=4000,
    )
    assert "Symbol dependencies" in block
    assert "export const Thing = 123;" in block
    assert "export const Thing = 999;" not in block
    assert 'return "local"' in block


def test_build_symbol_dependency_context_from_js_ts_commonjs_destructuring(
    tmp_path: Path,
):
    repo = tmp_path / "repo"
    repo.mkdir()

    src_dir = repo / "src"
    src_dir.mkdir()

    local_mod = src_dir / "cjsmod.js"
    local_mod.write_text(
        "\n".join(
            [
                "exports.Thing = 111;",
                "exports.Other = 222;",
            ]
        ),
        encoding="utf-8",
    )

    alt_dir = src_dir / "alt"
    alt_dir.mkdir()
    alt_mod = alt_dir / "cjsmod.js"
    alt_mod.write_text(
        "\n".join(
            [
                "exports.Thing = 333;",
                "exports.Other = 444;",
            ]
        ),
        encoding="utf-8",
    )

    use = src_dir / "use.js"
    use.write_text(
        "\n".join(
            [
                "const { Thing, Other } = require('./cjsmod');",
                "console.log(Thing);",
            ]
        ),
        encoding="utf-8",
    )

    idx = SymbolIndex(
        str(repo),
        tag_records=[
            TagMatch(
                name="Thing",
                path=str(local_mod.resolve()),
                line=1,
                kind="variable",
            ),
            TagMatch(
                name="Other",
                path=str(local_mod.resolve()),
                line=2,
                kind="variable",
            ),
            TagMatch(
                name="Thing",
                path=str(alt_mod.resolve()),
                line=1,
                kind="variable",
            ),
            TagMatch(
                name="Other",
                path=str(alt_mod.resolve()),
                line=2,
                kind="variable",
            ),
        ],
    )

    block = build_symbol_dependency_context_from_source_files(
        repo_root=str(repo),
        source_files=[str(use)],
        symbol_index=idx,
        max_symbols=5,
        max_chars=4000,
    )
    assert "Symbol dependencies" in block
    assert "exports.Thing = 111;" in block
    assert "exports.Thing = 333;" not in block
    assert "exports.Other = 222;" in block
    assert "exports.Other = 444;" not in block


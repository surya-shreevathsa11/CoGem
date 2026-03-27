from __future__ import annotations

from pathlib import Path

from clogem.symbols import TagMatch, SymbolIndex


def test_resolve_symbol_snippet(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()

    target = repo / "adapters.py"
    target.write_text(
        "\n".join(
            [
                "class StitchCliAdapter:",
                "    def run(self):",
                "        return 'ok'",
                "",
                "def other():",
                "    return 1",
            ]
        ),
        encoding="utf-8",
    )

    idx = SymbolIndex(
        str(repo),
        tag_records=[
            TagMatch(
                name="StitchCliAdapter",
                path=str(target),
                line=1,
                kind="class",
            )
        ],
    )

    res = idx.resolve_symbol_to_snippet("StitchCliAdapter", context_lines=2, max_chars=5000)
    assert res is not None
    assert "class StitchCliAdapter" in res.snippet
    assert res.start_line <= 1 <= res.end_line


def test_resolve_symbol_prefers_class_over_variable(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()

    header = repo / "x.h"
    header.write_text(
        "\n".join(
            [
                "// header",
                "int Whatever();",
                "",
            ]
        ),
        encoding="utf-8",
    )
    impl = repo / "x.py"
    impl.write_text(
        "\n".join(
            [
                "class MySymbol:",
                "    def f(self):",
                "        return 123",
                "",
                "def helper():",
                "    return 0",
            ]
        ),
        encoding="utf-8",
    )

    idx = SymbolIndex(
        str(repo),
        tag_records=[
            TagMatch(name="MySymbol", path=str(header), line=1, kind="variable"),
            TagMatch(name="MySymbol", path=str(impl), line=1, kind="class"),
        ],
    )

    res = idx.resolve_symbol_to_snippet("MySymbol", context_lines=3, max_chars=5000)
    assert res is not None
    assert "class MySymbol" in res.snippet
    assert res.tag.path.endswith("x.py")


def test_resolve_symbol_prefers_source_over_header(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()

    header = repo / "thing.h"
    header.write_text(
        "\n".join(
            [
                "// header declaration",
                "class Thing {",
                "};",
                "",
            ]
        ),
        encoding="utf-8",
    )
    source = repo / "thing.cpp"
    source.write_text(
        "\n".join(
            [
                "// source implementation",
                "class Thing {",
                "public:",
                "    int run() { return 7; }",
                "};",
                "",
                "int extra() {",
                "    return 1;",
                "}",
            ]
        ),
        encoding="utf-8",
    )

    idx = SymbolIndex(
        str(repo),
        tag_records=[
            TagMatch(name="Thing", path=str(header), line=2, kind="class"),
            TagMatch(name="Thing", path=str(source), line=2, kind="class"),
        ],
    )
    res = idx.resolve_symbol_to_snippet("Thing", context_lines=3, max_chars=5000)
    assert res is not None
    assert "source implementation" in res.snippet or "run() { return 7; }" in res.snippet
    assert res.tag.path.endswith("thing.cpp")


def test_symbols_fuzzy_search_finds_out_of_order_letters():
    repo = "unused"
    idx = SymbolIndex(
        repo,
        tag_records=[
            TagMatch(name="StitchCliAdapter", path="x.py", line=1, kind="class"),
            TagMatch(name="Unrelated", path="y.py", line=1, kind="class"),
        ],
    )

    matches = idx.symbols_fuzzy_search("SCA", limit=5)
    assert matches
    assert matches[0].name == "StitchCliAdapter"


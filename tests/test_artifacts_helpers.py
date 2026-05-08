from __future__ import annotations

from clogem.artifacts import (
    extract_code,
    extract_files,
    extract_unified_diff,
    get_diff,
)


def test_extract_code_from_fenced_block() -> None:
    txt = "```python\nprint('x')\n```"
    assert extract_code(txt) == "print('x')"


def test_extract_files_from_file_blocks() -> None:
    raw = "FILE: a.txt\none\nFILE: b.txt\ntwo\n"
    out = extract_files(raw)
    assert out["a.txt"] == "one"
    assert out["b.txt"] == "two"


def test_extract_unified_diff_from_fenced_diff() -> None:
    raw = "```diff\n--- a/x\n+++ b/x\n@@\n-a\n+b\n```"
    d = extract_unified_diff(raw)
    assert "--- a/x" in d and "+++ b/x" in d


def test_get_diff_contains_unified_markers() -> None:
    d = get_diff("a\n", "b\n")
    assert "---" in d and "+++" in d

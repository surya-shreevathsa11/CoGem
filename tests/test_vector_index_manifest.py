import json
from pathlib import Path

from cogem.vector_index import VectorIndex, VectorIndexConfig


def test_vector_manifest_detects_changes(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    f = repo / "a.py"
    f.write_text("print('a')\n", encoding="utf-8")

    cfg = VectorIndexConfig(enabled=True, index_dir=str(repo / ".vec"))
    idx = VectorIndex(str(repo), cfg)

    # no manifest => stale
    assert idx._index_is_stale() is True

    cur = idx._current_manifest()
    idx._save_manifest(cur)
    assert idx._index_is_stale() is False

    f.write_text("print('b')\n", encoding="utf-8")
    assert idx._index_is_stale() is True


def test_vector_manifest_roundtrip(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    cfg = VectorIndexConfig(enabled=True, index_dir=str(repo / ".vec"))
    idx = VectorIndex(str(repo), cfg)
    data = {"x.py": "abc"}
    idx._save_manifest(data)
    got = idx._load_manifest()
    assert got == data


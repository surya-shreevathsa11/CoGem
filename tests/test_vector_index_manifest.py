import json
from pathlib import Path
import types

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


def test_build_or_load_skips_stale_check_within_throttle_window(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    cfg = VectorIndexConfig(enabled=True, index_dir=str(repo / ".vec"))
    idx = VectorIndex(str(repo), cfg)

    calls = {"stale": 0, "open": 0}
    monkeypatch.setattr(idx, "is_available", lambda: True)

    def fake_stale():
        calls["stale"] += 1
        return False

    class FakeConn:
        def open_table(self, _name):
            calls["open"] += 1
            return {"name": "code_chunks"}

    t = {"now": 100.0}
    monkeypatch.setattr("cogem.vector_index.time.monotonic", lambda: t["now"])
    monkeypatch.setattr(idx, "_index_is_stale", fake_stale)
    monkeypatch.setattr(idx, "_connect", lambda: FakeConn())
    monkeypatch.setitem(__import__("sys").modules, "lancedb", types.SimpleNamespace())

    first = idx.build_or_load()
    second = idx.build_or_load()
    assert first == {"name": "code_chunks"}
    assert second == {"name": "code_chunks"}
    assert calls == {"stale": 1, "open": 1}

    t["now"] = 106.0
    third = idx.build_or_load()
    assert third == {"name": "code_chunks"}
    assert calls == {"stale": 2, "open": 2}


def test_build_or_load_reuses_cached_table(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    cfg = VectorIndexConfig(enabled=True, index_dir=str(repo / ".vec"))
    idx = VectorIndex(str(repo), cfg)

    monkeypatch.setattr(idx, "is_available", lambda: True)
    monkeypatch.setattr(idx, "_index_is_stale", lambda: False)
    opens = {"count": 0}

    class FakeConn:
        def open_table(self, _name):
            opens["count"] += 1
            return {"name": "code_chunks"}

    monkeypatch.setattr(idx, "_connect", lambda: FakeConn())
    monkeypatch.setitem(__import__("sys").modules, "lancedb", types.SimpleNamespace())

    first = idx.build_or_load()
    second = idx.build_or_load()
    assert first == {"name": "code_chunks"}
    assert second == first
    assert opens["count"] == 1


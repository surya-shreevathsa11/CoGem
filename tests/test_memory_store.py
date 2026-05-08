from __future__ import annotations

from clogem.memory import MemoryStore


def test_memory_store_save_and_load_roundtrip(tmp_path):
    p = tmp_path / "memory.json"
    store = MemoryStore(str(p))
    store.save(
        {
            "stack": ["Python", "python", "FastAPI"],
            "constraints": ["No Docker", "no docker"],
            "decisions": ["Use pytest"],
            "notes": "keep this short",
        }
    )
    loaded = store.load()
    assert loaded["stack"] == ["Python", "FastAPI"]
    assert loaded["constraints"] == ["No Docker"]
    assert isinstance(loaded["decisions"], list) and loaded["decisions"]


def test_memory_store_format_for_prompt_empty():
    store = MemoryStore("unused.json")
    assert store.format_for_prompt({}) == ""

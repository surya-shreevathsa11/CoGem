from __future__ import annotations

import os
import json
import hashlib
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


_DEFAULT_INDEX_DIRNAME = ".cogem/vector_db"
_DEFAULT_INCLUDE_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx", ".md", ".css", ".html", ".json"}


def _chunk_text(text: str, *, max_chars: int = 2500) -> List[str]:
    """
    Split text into roughly `max_chars` character chunks.
    Uses paragraph-ish boundaries first to keep context readable.
    """
    if not text:
        return []
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    parts: List[str] = []
    cur: List[str] = []
    cur_len = 0

    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if cur_len + len(para) + 2 <= max_chars:
            cur.append(para)
            cur_len += len(para) + 2
            continue
        if cur:
            parts.append("\n\n".join(cur))
        # Paragraph itself may be huge; hard-chunk it.
        if len(para) <= max_chars:
            cur = [para]
            cur_len = len(para)
        else:
            for i in range(0, len(para), max_chars):
                parts.append(para[i : i + max_chars])
            cur = []
            cur_len = 0

    if cur:
        parts.append("\n\n".join(cur))
    # Final cleanup.
    return [p.strip() for p in parts if p.strip()]


def _safe_read_text(abs_path: str, max_bytes: int) -> str:
    try:
        with open(abs_path, "rb") as f:
            raw = f.read(max_bytes)
        return raw.decode("utf-8", errors="replace")
    except OSError:
        return ""


def _iter_source_files(
    repo_root: str,
    *,
    include_exts: Sequence[str],
    exclude_dirs: Optional[Sequence[str]] = None,
    max_bytes_per_file: int = 300_000,
) -> Iterable[str]:
    exclude = set(exclude_dirs or {".git", "node_modules", ".venv", "dist", "build", "__pycache__"})
    include = set(e.lower() for e in include_exts)
    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in exclude]
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext not in include:
                continue
            fp = os.path.join(root, name)
            try:
                if os.path.getsize(fp) > max_bytes_per_file:
                    continue
            except OSError:
                continue
            yield fp


@dataclass(frozen=True)
class VectorIndexConfig:
    enabled: bool = False
    index_dir: Optional[str] = None
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    rebuild: bool = False
    top_k: int = 8
    max_chunk_chars: int = 2500
    max_file_bytes: int = 300_000
    max_context_chars: int = 8000
    include_exts: Tuple[str, ...] = tuple(sorted(_DEFAULT_INCLUDE_EXTS))


class VectorIndex:
    """
    Optional LanceDB + local embeddings for semantic retrieval.

    If dependencies are missing, the index is unavailable and callers must
    fall back to non-vector retrieval.
    """

    def __init__(self, repo_root: str, config: VectorIndexConfig) -> None:
        self.repo_root = os.path.abspath(repo_root)
        self.config = config
        self.index_dir = config.index_dir or os.path.join(
            self.repo_root, _DEFAULT_INDEX_DIRNAME
        )

    def is_available(self) -> bool:
        try:
            import lancedb  # noqa: F401
            import numpy  # noqa: F401
            from sentence_transformers import SentenceTransformer  # noqa: F401
        except Exception:
            return False
        return True

    def _connect(self):
        import lancedb

        os.makedirs(self.index_dir, exist_ok=True)
        return lancedb.connect(self.index_dir)

    def _manifest_path(self) -> str:
        return os.path.join(self.index_dir, "manifest.json")

    def _file_hash(self, abs_path: str) -> str:
        try:
            with open(abs_path, "rb") as f:
                raw = f.read(self.config.max_file_bytes)
            return hashlib.sha256(raw).hexdigest()
        except OSError:
            return ""

    def _current_manifest(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        idx_root = os.path.realpath(self.index_dir)
        for fp in _iter_source_files(
            self.repo_root,
            include_exts=self.config.include_exts,
            max_bytes_per_file=self.config.max_file_bytes,
        ):
            try:
                rp = os.path.realpath(fp)
                if rp == idx_root or rp.startswith(idx_root + os.sep):
                    continue
            except OSError:
                continue
            rel = os.path.relpath(fp, self.repo_root).replace("\\", "/")
            h = self._file_hash(fp)
            if h:
                out[rel] = h
        return out

    def _load_manifest(self) -> Dict[str, str]:
        p = self._manifest_path()
        if not os.path.isfile(p):
            return {}
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        except Exception:
            return {}
        return {}

    def _save_manifest(self, manifest: Dict[str, str]) -> None:
        p = self._manifest_path()
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)
                f.write("\n")
        except OSError:
            return

    def _index_is_stale(self) -> bool:
        if self.config.rebuild:
            return True
        old = self._load_manifest()
        if not old:
            return True
        cur = self._current_manifest()
        return old != cur

    def _load_embedder(self):
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(self.config.model_name)

    def _build_chunks(self) -> List[dict]:
        """
        Build rows for LanceDB table.

        Each row: {id, path, chunk_index, text, embedding}
        """
        rows: List[dict] = []
        chunk_id = 0
        embedder = self._load_embedder()

        for fp in _iter_source_files(
            self.repo_root,
            include_exts=self.config.include_exts,
            max_bytes_per_file=self.config.max_file_bytes,
        ):
            text = _safe_read_text(fp, max_bytes=self.config.max_file_bytes)
            if not text.strip():
                continue
            chunks = _chunk_text(
                text, max_chars=self.config.max_chunk_chars
            )
            rel = os.path.relpath(fp, self.repo_root).replace("\\", "/")
            for ci, chunk in enumerate(chunks):
                # Embedding is computed here to keep memory modest.
                emb = embedder.encode(
                    chunk,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                )
                rows.append(
                    {
                        "id": chunk_id,
                        "path": rel,
                        "chunk_index": ci,
                        "text": chunk,
                        "embedding": emb.tolist(),
                    }
                )
                chunk_id += 1
        return rows

    def build_or_load(self) -> Optional[object]:
        if not self.config.enabled:
            return None
        if not self.is_available():
            return None
        import lancedb

        conn = self._connect()
        table_name = "code_chunks"

        if self.config.rebuild:
            try:
                conn.drop_table(table_name)
            except Exception:
                pass

        if not self._index_is_stale():
            try:
                return conn.open_table(table_name)
            except Exception:
                pass
        else:
            try:
                conn.drop_table(table_name)
            except Exception:
                pass

        rows = self._build_chunks()
        if not rows:
            return None

        # Create table.
        import pyarrow as pa

        # LanceDB works well with Arrow Tables.
        # Convert dict rows to Arrow via schema inference.
        arr = pa.Table.from_pylist(rows)
        table = conn.create_table(table_name, arr)
        self._save_manifest(self._current_manifest())
        return table

    def query(self, task: str) -> List[dict]:
        if not self.config.enabled:
            return []
        if not self.is_available():
            return []
        if not task or not task.strip():
            return []

        table = self.build_or_load()
        if table is None:
            return []

        embedder = self._load_embedder()
        import numpy as np

        q_emb = embedder.encode(
            task,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        q_emb = np.array(q_emb).astype("float32")

        # LanceDB vector search:
        # - embedding column holds a list[float]
        # - search() uses the vector + metric defaults to inner product for normalized embeddings.
        try:
            res = (
                table.search(q_emb.tolist())
                .limit(int(self.config.top_k))
                .to_list()
            )
        except Exception:
            # Some LanceDB versions use table.search(vectors=...) API.
            try:
                res = (
                    table.search(queries=[q_emb.tolist()])
                    .limit(int(self.config.top_k))
                    .to_list()
                )
            except Exception:
                return []

        return res or []


def semantic_repo_context_block_for_task(
    repo_root: str, task: str, config: VectorIndexConfig
) -> str:
    """
    Return a small context block using LanceDB semantic retrieval.
    Falls back to empty string when unavailable.
    """
    idx = VectorIndex(repo_root, config)
    rows = idx.query(task)
    if not rows:
        return ""

    parts: List[str] = []
    total = 0
    max_chars = max(1, int(config.max_context_chars))

    for r in rows:
        if total >= max_chars:
            break
        path = (r.get("path") or "").strip()
        text = (r.get("text") or "").strip()
        if not path or not text:
            continue
        # Keep each snippet bounded.
        snippet = "\n".join(text.splitlines()[:160])
        block = f"### {path}\n```\n{snippet}\n```\n"
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)

    return "\n".join(parts).strip()


def semantic_search_repo(
    repo_root: str, task: str, config: VectorIndexConfig
) -> List[dict]:
    idx = VectorIndex(repo_root, config)
    return idx.query(task)


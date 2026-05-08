from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from clogem.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class TagMatch:
    name: str
    path: str  # absolute file path
    line: int
    kind: str = ""


@dataclass(frozen=True)
class ResolvedSymbolSnippet:
    tag: TagMatch
    snippet: str
    start_line: int
    end_line: int


def _looks_like_filename(mention: str) -> bool:
    m = (mention or "").strip()
    if not m:
        return False
    if m.endswith(
        (".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".md", ".css", ".html")
    ):
        return True
    # If it includes a path separator, it’s a file path style mention.
    if "/" in m or "\\" in m:
        return True
    return False


def _default_cache_path(repo_root: str) -> str:
    base = os.path.join(repo_root, ".clogem", "cache")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "ctags_index.json")


def _kind_points(kind: str) -> int:
    kl = (kind or "").lower()
    if "class" in kl:
        return 100
    if "interface" in kl:
        return 95
    if "struct" in kl or "enum" in kl:
        return 100
    if "function" in kl:
        return 90
    if "method" in kl:
        return 85
    if "variable" in kl or "var" in kl or "member" in kl:
        return 10
    return 10


def _ext_points(path: str) -> int:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".py", ".ts", ".tsx", ".js", ".jsx"):
        return 30
    if ext in (".c", ".cc", ".cpp", ".cxx"):
        return 25
    if ext in (".h", ".hh", ".hpp", ".hxx"):
        return 5
    return 10


def _size_points(path: str) -> int:
    try:
        return min(25, os.path.getsize(path) // 20000)
    except OSError:
        return 0


class SymbolIndex:
    """
    Minimal symbol index backed by universal-ctags/ctags JSON output.

    Goal: resolve `@MyClassName` (symbol mention) to a file+line snippet,
    so users don’t need to type exact `@path/to/file.py`.

    This is best-effort: if the ctags tool is unavailable, resolution returns None.
    """

    def __init__(
        self,
        repo_root: str,
        *,
        cache_path: Optional[str] = None,
        tag_records: Optional[Sequence[TagMatch]] = None,
        ctags_tool: Optional[str] = None,
    ) -> None:
        self.repo_root = os.path.abspath(repo_root)
        self.cache_path = cache_path or _default_cache_path(self.repo_root)
        self._tag_records = list(tag_records) if tag_records is not None else None
        self._ctags_tool = ctags_tool

    def _tool_candidates(self) -> List[str]:
        if self._ctags_tool:
            return [self._ctags_tool]
        # universal-ctags is preferred for speed and stable output.
        return ["universal-ctags", "ctags"]

    def _find_ctags_tool(self) -> Optional[str]:
        for t in self._tool_candidates():
            if shutil.which(t):
                return t
        return None

    def _parse_ctags_json_lines(self, stdout: str) -> List[TagMatch]:
        out: List[TagMatch] = []
        for line in (stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Expected keys (universal-ctags JSON):
            # - name
            # - path
            # - lineNumber (or line)
            # - kind (or kindName)
            name = (obj.get("name") or "").strip()
            path = (obj.get("path") or "").strip()
            line_no_raw = obj.get("lineNumber") or obj.get("line") or obj.get("lineno")
            kind = (obj.get("kind") or obj.get("kindName") or "").strip()

            if not name or not path or line_no_raw is None:
                continue

            try:
                line_no = int(line_no_raw)
            except (TypeError, ValueError):
                continue

            abs_path = path
            if not os.path.isabs(abs_path):
                abs_path = os.path.join(self.repo_root, path)

            if not os.path.isfile(abs_path):
                continue

            out.append(TagMatch(name=name, path=os.path.realpath(abs_path), line=line_no, kind=kind))
        return out

    def _load_from_cache(self) -> Optional[List[TagMatch]]:
        try:
            if not os.path.isfile(self.cache_path):
                return None
            with open(self.cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            items = data.get("tags") if isinstance(data, dict) else data
            if not isinstance(items, list):
                return None
            out: List[TagMatch] = []
            for it in items:
                if not isinstance(it, dict):
                    continue
                name = (it.get("name") or "").strip()
                path = (it.get("path") or "").strip()
                line_no = it.get("line") or it.get("lineNumber")
                kind = (it.get("kind") or "").strip()
                if not name or not path or line_no is None:
                    continue
                try:
                    ln = int(line_no)
                except (TypeError, ValueError):
                    continue
                abs_path = path
                if not os.path.isabs(abs_path):
                    abs_path = os.path.join(self.repo_root, path)
                if not os.path.isfile(abs_path):
                    continue
                out.append(TagMatch(name=name, path=os.path.realpath(abs_path), line=ln, kind=kind))
            return out
        except Exception:
            logger.debug("Failed loading symbol cache: %s", self.cache_path, exc_info=True)
            return None

    def _save_to_cache(self, tags: Sequence[TagMatch]) -> None:
        try:
            data = {"tags": [t.__dict__ for t in tags]}
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception:
            logger.debug("Failed saving symbol cache: %s", self.cache_path, exc_info=True)
            # Cache is best-effort; never fail symbol resolution for caching.
            return

    def ensure_built(self) -> List[TagMatch]:
        if self._tag_records is not None:
            return self._tag_records

        cached = self._load_from_cache()
        if cached:
            self._tag_records = cached
            return cached

        tool = self._find_ctags_tool()
        if not tool:
            self._tag_records = []
            return []

        # universal-ctags produces JSON per line with --output-format=json.
        # We request extra `lineNumber` to allow snippet extraction.
        cmd = [
            tool,
            "-R",
            "--output-format=json",
            "--fields=+n",
            ".",
        ]

        try:
            proc = subprocess.run(
                cmd,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                self._tag_records = []
                return []
            tags = self._parse_ctags_json_lines(proc.stdout or "")
            self._tag_records = tags
            self._save_to_cache(tags)
            return tags
        except Exception:
            logger.debug("ctags execution failed for symbol index", exc_info=True)
            self._tag_records = []
            return []

    def resolve_symbol_to_snippet(
        self,
        symbol: str,
        *,
        context_lines: int = 18,
        max_chars: int = 6000,
    ) -> Optional[ResolvedSymbolSnippet]:
        symbol = (symbol or "").strip()
        if not symbol:
            return None
        if _looks_like_filename(symbol):
            return None

        tags = self.ensure_built()
        if not tags:
            return None

        # Exact match first.
        matches = [t for t in tags if t.name == symbol]
        if not matches:
            # Fallback: substring match for namespaced symbols, e.g. `mod.Class`.
            matches = [t for t in tags if symbol in t.name]
        if not matches:
            return None

        # Deduplicate identical file+line records (some ctags outputs can repeat).
        uniq: Dict[Tuple[str, int], TagMatch] = {}
        for t in matches:
            uniq[(t.path, t.line)] = t
        candidates = list(uniq.values())

        best_tag: Optional[TagMatch] = None
        best_score = -1
        best_snippet = ""
        best_start = 1
        best_end = 1

        for cand in candidates:
            try:
                with open(cand.path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.read().splitlines()
            except OSError:
                continue

            idx = max(0, cand.line - 1)
            start_line = max(1, idx + 1 - context_lines)
            end_line = min(len(lines), idx + 1 + context_lines)
            snippet_lines = lines[start_line - 1 : end_line]
            snippet = "\n".join(snippet_lines).strip()
            raw_snippet_len = len(snippet)

            if raw_snippet_len > max_chars:
                snippet = snippet[: max(0, max_chars - 20)] + "\n...[truncated]"

            size_points = min(30, raw_snippet_len // 200)
            score = _kind_points(cand.kind) + _ext_points(cand.path) + size_points

            # Deterministic tie-breakers:
            # 1) later line numbers are usually more "implementation"
            # 2) lexicographically smaller path
            if score > best_score or (
                score == best_score
                and (
                    (cand.line > (best_tag.line if best_tag else -1))
                    or (
                        cand.line == (best_tag.line if best_tag else -1)
                        and cand.path < (best_tag.path if best_tag else "~")
                    )
                )
            ):
                best_score = score
                best_tag = cand
                best_snippet = snippet
                best_start = start_line
                best_end = end_line

        if not best_tag:
            return None

        return ResolvedSymbolSnippet(
            tag=best_tag,
            snippet=best_snippet,
            start_line=best_start,
            end_line=best_end,
        )

    def resolve_symbol_to_snippet_preferring_paths(
        self,
        symbol: str,
        *,
        preferred_paths: Optional[Iterable[str]] = None,
        context_lines: int = 18,
        max_chars: int = 6000,
    ) -> Optional[ResolvedSymbolSnippet]:
        """
        Best-effort resolve, but preferentially selects tags whose file is in
        `preferred_paths` (absolute paths). If no preferred tags exist, it
        falls back to unfiltered selection.
        """
        symbol = (symbol or "").strip()
        if not symbol:
            return None
        if _looks_like_filename(symbol):
            return None

        pref: Set[str] = set()
        if preferred_paths:
            for p in preferred_paths:
                if not p:
                    continue
                pref.add(os.path.realpath(p))

        tags = self.ensure_built()
        if not tags:
            return None

        matches = [t for t in tags if t.name == symbol]
        if not matches:
            matches = [t for t in tags if symbol in t.name]
        if not matches:
            return None

        uniq: Dict[Tuple[str, int], TagMatch] = {}
        for t in matches:
            uniq[(t.path, t.line)] = t
        candidates = list(uniq.values())

        preferred_candidates = [c for c in candidates if c.path in pref] if pref else []
        use = preferred_candidates if preferred_candidates else candidates

        best_tag: Optional[TagMatch] = None
        best_score = -1
        best_snippet = ""
        best_start = 1
        best_end = 1

        for cand in use:
            try:
                with open(cand.path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.read().splitlines()
            except OSError:
                continue

            idx = max(0, cand.line - 1)
            start_line = max(1, idx + 1 - context_lines)
            end_line = min(len(lines), idx + 1 + context_lines)
            snippet_lines = lines[start_line - 1 : end_line]
            snippet = "\n".join(snippet_lines).strip()
            raw_snippet_len = len(snippet)

            if raw_snippet_len > max_chars:
                snippet = snippet[: max(0, max_chars - 20)] + "\n...[truncated]"

            size_points = min(30, raw_snippet_len // 200)
            score = _kind_points(cand.kind) + _ext_points(cand.path) + size_points

            if score > best_score or (
                score == best_score
                and (
                    (cand.line > (best_tag.line if best_tag else -1))
                    or (
                        cand.line == (best_tag.line if best_tag else -1)
                        and cand.path < (best_tag.path if best_tag else "~")
                    )
                )
            ):
                best_score = score
                best_tag = cand
                best_snippet = snippet
                best_start = start_line
                best_end = end_line

        if not best_tag:
            return None

        return ResolvedSymbolSnippet(
            tag=best_tag,
            snippet=best_snippet,
            start_line=best_start,
            end_line=best_end,
        )

    def best_tag_for_symbol(self, symbol: str) -> Optional[TagMatch]:
        """
        Best-effort selection among all tags for a given symbol name.
        Used for completion display (kind + file).
        """
        symbol = (symbol or "").strip()
        if not symbol:
            return None

        tags = self.ensure_built()
        if not tags:
            return None

        matches = [t for t in tags if t.name == symbol]
        if not matches:
            matches = [t for t in tags if symbol in t.name]
        if not matches:
            return None

        best: Optional[TagMatch] = None
        best_score = -1
        for t in matches:
            score = _kind_points(t.kind) + _ext_points(t.path) + _size_points(t.path)
            if score > best_score or (score == best_score and t.path < (best.path if best else "~")):
                best_score = score
                best = t
        return best

    def symbols_starting_with(
        self, prefix: str, *, limit: int = 30
    ) -> List[TagMatch]:
        """
        Return best tag per unique symbol name matching a prefix.
        """
        prefix = (prefix or "").strip()
        if not prefix:
            return []

        tags = self.ensure_built()
        if not tags:
            return []

        def _score(t: TagMatch) -> int:
            return _kind_points(t.kind) + _ext_points(t.path) + _size_points(t.path)

        # Deduplicate by name, keep the best tag per name.
        best_by_name: Dict[str, TagMatch] = {}
        pl = prefix.lower()
        for t in tags:
            if not t.name or not t.name.lower().startswith(pl):
                continue
            prev = best_by_name.get(t.name)
            if prev is None or _score(t) > _score(prev):
                best_by_name[t.name] = t

        items = list(best_by_name.values())
        # Best kind first; deterministic secondary order by name.
        items.sort(key=lambda t: (-_kind_points(t.kind), t.name))
        return items[:limit]

    def symbols_fuzzy_search(
        self, query: str, *, limit: int = 30
    ) -> List[TagMatch]:
        """
        Best-effort fuzzy search for symbol names using a subsequence matcher.
        """
        q = (query or "").strip().lower()
        if not q:
            return []

        tags = self.ensure_built()
        if not tags:
            return []

        def _fuzzy_score(needle: str, hay: str) -> int:
            # Subsequence match score with streak bonuses.
            n = (needle or "").lower()
            h = (hay or "").lower()
            if not n or not h:
                return 0
            i = 0
            score = 0
            streak = 0
            for ch in h:
                if i < len(n) and ch == n[i]:
                    i += 1
                    streak += 1
                    score += 10 * streak
                else:
                    streak = 0
            return score if i == len(n) else 0

        best_by_name: Dict[str, Tuple[TagMatch, int]] = {}
        for t in tags:
            if not t.name:
                continue
            fscore = _fuzzy_score(q, t.name)
            if fscore <= 0:
                continue
            # Combine fuzzy score with structural preferences.
            base = _kind_points(t.kind) + _ext_points(t.path)
            total = fscore + base
            prev = best_by_name.get(t.name)
            if prev is None or total > prev[1]:
                best_by_name[t.name] = (t, total)

        items = [v[0] for v in best_by_name.values()]
        items.sort(key=lambda t: (-(_kind_points(t.kind) + _ext_points(t.path)), t.name))

        # Enforce overall limit; stable ranking within the best matches.
        return items[:limit]


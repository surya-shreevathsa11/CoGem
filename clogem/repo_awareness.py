from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple


_DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "dist",
    "build",
    ".tox",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".cursor-server",
}

_SOURCE_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".md", ".css", ".html"}

_PY_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+(?P<from>[a-zA-Z0-9_\.]+)\s+import\s+|import\s+(?P<import>[a-zA-Z0-9_\.]+)\s*)",
    re.M,
)

_JS_IMPORT_RE = re.compile(
    r"""^\s*(?:import\s+(?:[\s\S]+?)\s+from\s+|import\s+|const\s+|let\s+|var\s+|require\()\s*['"](?P<spec>\.[^'"]+)['"]""",
    re.M,
)

_JS_REQUIRE_RE = re.compile(r"""require\(\s*['"](?P<spec>\.[^'"]+)['"]\s*\)""")

_CANDIDATE_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


def _repo_root_if_none(repo_root: Optional[str], fallback: str) -> str:
    return os.path.abspath(repo_root or fallback)


def extract_task_keywords(task: str, *, max_keywords: int = 25) -> List[str]:
    """
    Lightweight keyword extraction for retrieval.
    This is not semantic embeddings; it’s a conservative token-based heuristic.
    """
    if not task:
        return []
    t = task.strip()
    if not t:
        return []
    # Normalize common punctuation to spaces.
    t = re.sub(r"[^A-Za-z0-9_\.\/\- ]+", " ", t)
    tokens = _CANDIDATE_TOKEN_RE.findall(t)
    stop = {
        "build",
        "create",
        "make",
        "design",
        "implement",
        "add",
        "update",
        "fix",
        "with",
        "and",
        "or",
        "the",
        "a",
        "an",
        "for",
        "to",
        "in",
        "on",
        "using",
        "use",
        "frontend",
        "backend",
        "website",
        "landing",
        "page",
        "dashboard",
        "ui",
    }
    out: List[str] = []
    seen: Set[str] = set()
    for tok in tokens:
        low = tok.lower()
        if low in stop:
            continue
        if low in seen:
            continue
        # Keep module-like tokens too (e.g. "clogem.cli").
        if len(low) < 3:
            continue
        seen.add(low)
        out.append(low)
        if len(out) >= max_keywords:
            break
    return out


def iter_source_files(
    repo_root: str,
    *,
    exclude_dirs: Optional[Set[str]] = None,
    max_bytes_per_file: int = 250_000,
) -> Iterator[str]:
    """
    Yield absolute file paths for likely source files.
    """
    exclude_dirs = exclude_dirs or set(_DEFAULT_EXCLUDE_DIRS)
    for root, dirs, files in os.walk(repo_root):
        # Mutate dirs in-place to prune traversal.
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext not in _SOURCE_EXTS:
                continue
            fp = os.path.join(root, name)
            try:
                if os.path.getsize(fp) > max_bytes_per_file:
                    continue
            except OSError:
                continue
            yield fp


def relpath_under_repo(repo_root: str, abs_path: str) -> str:
    try:
        return os.path.relpath(abs_path, repo_root)
    except ValueError:
        return abs_path


def safe_read_text(abs_path: str, *, max_bytes: int) -> str:
    try:
        with open(abs_path, "rb") as f:
            raw = f.read(max_bytes)
    except OSError:
        return ""
    return raw.decode("utf-8", errors="replace")


def python_module_name_from_path(
    repo_root: str, abs_path: str
) -> Optional[str]:
    if not abs_path.endswith(".py"):
        return None
    rel = os.path.relpath(abs_path, repo_root).replace("\\", "/")
    if rel.startswith("../"):
        return None
    parts = rel.split("/")
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = os.path.splitext(parts[-1])[0]
    return ".".join([p for p in parts if p])


def resolve_python_imports(
    abs_path: str, repo_root: str, *, max_depth: int = 2
) -> Set[str]:
    """
    Very lightweight dependency expansion for Python files.
    - Follows `import x` and `from x import ...`
    - Resolves local modules by matching module name -> file path inside repo
    """
    try:
        code = safe_read_text(abs_path, max_bytes=200_000)
        if not code.strip():
            return set()
        tree = ast.parse(code)
    except Exception:
        # Fallback to regex when parsing fails.
        code = safe_read_text(abs_path, max_bytes=200_000)
        modules: Set[str] = set()
        for m in _PY_IMPORT_RE.finditer(code):
            frm = (m.group("from") or "").strip()
            imp = (m.group("import") or "").strip()
            if frm:
                modules.add(frm)
            elif imp:
                modules.add(imp)
        return set(_python_module_names_to_paths(modules, repo_root))

    modules: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name:
                    modules.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)

    return set(_python_module_names_to_paths(modules, repo_root))


def _python_module_names_to_paths(
    modules: Iterable[str], repo_root: str
) -> List[str]:
    out: List[str] = []
    for mod in modules:
        # Only try local modules; ignore stdlib-ish names by only mapping
        # to files that exist under the repo root.
        mod = (mod or "").strip()
        if not mod:
            continue
        parts = mod.split(".")

        # Try package path: a/b/c.py
        candidate_py = os.path.join(repo_root, *parts) + ".py"
        if os.path.isfile(candidate_py):
            out.append(candidate_py)
            continue

        # Try package init: a/b/c/__init__.py
        candidate_init = os.path.join(repo_root, *parts, "__init__.py")
        if os.path.isfile(candidate_init):
            out.append(candidate_init)
            continue

    return out


def resolve_relative_js_imports(
    abs_path: str, repo_root: str
) -> Set[str]:
    """
    Expand relative JS/TS imports: ./x or ../x.
    We only follow relative specifiers (safe + useful).
    """
    code = safe_read_text(abs_path, max_bytes=200_000)
    if not code.strip():
        return set()
    base = os.path.dirname(abs_path)
    specs: Set[str] = set()
    for m in _JS_IMPORT_RE.finditer(code):
        specs.add(m.group("spec"))
    for m in _JS_REQUIRE_RE.finditer(code):
        specs.add(m.group("spec"))

    exts = [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".json"]
    out: Set[str] = set()
    for spec in specs:
        spec = spec.strip()
        if not spec.startswith("."):
            continue
        target_base = os.path.normpath(os.path.join(base, spec))
        # Spec may already include an extension.
        if os.path.isfile(target_base):
            out.add(target_base)
            continue
        for e in exts:
            cand = target_base + e
            if os.path.isfile(cand):
                out.add(cand)
                break
        # Index files for directory imports.
        for e in exts:
            cand = os.path.join(target_base, "index" + e)
            if os.path.isfile(cand):
                out.add(cand)
                break
    return out


def _file_language_kind(abs_path: str) -> str:
    ext = os.path.splitext(abs_path)[1].lower()
    if ext == ".py":
        return "python"
    if ext in (".js", ".ts", ".tsx", ".jsx"):
        return "js"
    return "unknown"


def expand_dependency_closure(
    start_files: Sequence[str],
    repo_root: str,
    *,
    max_files: int = 10,
    max_depth: int = 2,
) -> List[str]:
    """
    BFS expansion of dependency closure, limited by max_files/max_depth.
    """
    visited: Set[str] = set()
    frontier: List[Tuple[str, int]] = [(f, 0) for f in start_files if f]
    closure: List[str] = []
    while frontier and len(closure) < max_files:
        cur, depth = frontier.pop(0)
        if cur in visited:
            continue
        visited.add(cur)
        closure.append(cur)
        if depth >= max_depth:
            continue
        kind = _file_language_kind(cur)
        deps: Set[str] = set()
        if kind == "python":
            deps = resolve_python_imports(cur, repo_root, max_depth=max_depth)
        elif kind == "js":
            deps = resolve_relative_js_imports(cur, repo_root)
        for d in deps:
            if d and d not in visited:
                frontier.append((d, depth + 1))
    return closure


def pick_snippet_from_text(
    abs_text: str,
    *,
    keywords: Sequence[str],
    max_snippet_chars: int,
    max_snippet_lines: int,
) -> str:
    """
    Pick a snippet around the earliest keyword occurrence.
    """
    if not abs_text.strip():
        return ""
    low = abs_text.lower()
    best_idx: Optional[int] = None
    for kw in keywords:
        if not kw:
            continue
        i = low.find(kw.lower())
        if i >= 0 and (best_idx is None or i < best_idx):
            best_idx = i
    if best_idx is None:
        # Fallback: start of file.
        snippet = abs_text[:max_snippet_chars]
        return "\n".join(snippet.splitlines()[:max_snippet_lines])

    # Convert char index to line index roughly.
    before = abs_text[:best_idx]
    start_line = max(0, len(before.splitlines()) - 20)
    lines = abs_text.splitlines()
    end_line = min(len(lines), start_line + max_snippet_lines)
    snippet = "\n".join(lines[start_line:end_line])
    if len(snippet) > max_snippet_chars:
        snippet = snippet[:max_snippet_chars]
    return snippet


def build_repo_context_block(
    repo_root: str,
    *,
    task: str,
    max_chars: int,
    max_files: int,
    max_depth: int,
) -> str:
    """
    Build a small context block by:
    - selecting start files by keyword relevance
    - expanding dependencies (Python imports, JS relative imports)
    - extracting small snippets near keywords
    """
    keywords = extract_task_keywords(task)
    if not keywords:
        return ""

    # Score files by keyword occurrence count.
    scored: List[Tuple[int, str]] = []
    max_bytes_for_scoring = 80_000
    for fp in iter_source_files(repo_root, max_bytes_per_file=250_000):
        txt = safe_read_text(fp, max_bytes=max_bytes_for_scoring).lower()
        if not txt.strip():
            continue
        score = 0
        for kw in keywords[:12]:
            if not kw:
                continue
            score += txt.count(kw.lower())
        if score > 0:
            scored.append((score, fp))

    scored.sort(key=lambda x: x[0], reverse=True)
    start_files = [fp for _score, fp in scored[: max(3, min(6, max_files))]]
    if not start_files:
        return ""

    closure = expand_dependency_closure(
        start_files,
        repo_root,
        max_files=max_files,
        max_depth=max_depth,
    )

    keywords_for_snippet = keywords
    parts: List[str] = []
    total_len = 0
    snippet_chars = max(2000, int(max_chars / max(1, len(closure))))
    for abs_fp in closure:
        rel = relpath_under_repo(repo_root, abs_fp).replace("\\", "/")
        text = safe_read_text(abs_fp, max_bytes=200_000)
        snippet = pick_snippet_from_text(
            text,
            keywords=keywords_for_snippet,
            max_snippet_chars=snippet_chars,
            max_snippet_lines=180,
        )
        if not snippet.strip():
            continue
        block = f"### {rel}\n```\n{snippet}\n```\n"
        if total_len + len(block) > max_chars:
            break
        parts.append(block)
        total_len += len(block)
        if total_len >= max_chars:
            break

    return "\n".join(parts).strip()


@dataclass(frozen=True)
class AutoRepoContextConfig:
    enabled: bool
    max_chars: int
    max_files: int
    max_depth: int


def auto_repo_context_block_for_task(
    *,
    task: str,
    repo_root: str,
    config: AutoRepoContextConfig,
) -> str:
    if not config.enabled:
        return ""
    if not task or not task.strip():
        return ""
    return build_repo_context_block(
        repo_root,
        task=task,
        max_chars=config.max_chars,
        max_files=config.max_files,
        max_depth=config.max_depth,
    )


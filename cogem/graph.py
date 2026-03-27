from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Set, Tuple


@dataclass(frozen=True)
class ImportedPythonSymbol:
    module: Optional[str]  # absolute module path, if known
    symbol: str  # imported name (definition name, not alias)
    as_name: Optional[str] = None


def extract_python_imported_symbols(source: str) -> List[ImportedPythonSymbol]:
    """
    Extract imported symbols from Python source using AST.

    We focus on `from X import Y` since that maps directly to definition names
    used by ctags. For `import X`, we return nothing (module resolution is
    handled elsewhere).
    """
    if not source or not source.strip():
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    out: List[ImportedPythonSymbol] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            # Ignore relative imports for now (no deterministic module->path
            # mapping without package resolution).
            if node.level and node.level > 0:
                continue
            mod = node.module
            for alias in node.names:
                if not alias.name:
                    continue
                out.append(
                    ImportedPythonSymbol(
                        module=mod,
                        symbol=alias.name,
                        as_name=alias.asname,
                    )
                )
    return out


def module_to_local_paths(repo_root: str, module: str) -> List[str]:
    """
    Map an absolute python module to local file candidates.
    """
    if not module:
        return []
    repo_root = os.path.abspath(repo_root)
    mod_path = module.replace(".", os.sep)

    candidates = [
        os.path.join(repo_root, mod_path + ".py"),
        os.path.join(repo_root, mod_path, "__init__.py"),
    ]
    existing: List[str] = []
    for c in candidates:
        if os.path.isfile(c):
            existing.append(os.path.realpath(c))
    return existing


@dataclass(frozen=True)
class ImportedJsSymbol:
    specifier: str  # import specifier, e.g. "./foo" or "react"
    symbol: str  # imported name (definition name, not alias)


def _parse_js_import_members(members_src: str) -> List[str]:
    out: List[str] = []
    for raw in (members_src or "").split(","):
        part = (raw or "").strip()
        if not part:
            continue
        # Handle `B as C`: take the imported name `B`.
        m = re.match(r"^([A-Za-z_$][A-Za-z0-9_$]*)\s+as\s+[A-Za-z_$][A-Za-z0-9_$]*$", part)
        if m:
            out.append(m.group(1))
            continue
        m2 = re.match(r"^([A-Za-z_$][A-Za-z0-9_$]*)$", part)
        if m2:
            out.append(m2.group(1))
    return out


def extract_js_imported_symbols(source: str) -> List[ImportedJsSymbol]:
    """
    Pragmatic JS/TS import extraction (regex-based).

    Supported:
    - `import {A, B as C} from 'module'`
    - `import A from 'module'`
    - `import * as A from 'module'`
    - `const {A, B} = require('module')`

    Notes:
    - Side-effect-only imports (`import 'module'`) are ignored.
    - Returns imported names (definition names), not local alias names.
    """
    if not source or not source.strip():
        return []

    out: List[ImportedJsSymbol] = []

    # Named imports: import {A, B as C} from 'module'
    named_pat = re.compile(
        r"import\s*\{\s*(?P<members>[^}]+)\s*\}\s*from\s*['\"](?P<spec>[^'\"]+)['\"]",
        re.MULTILINE,
    )
    for m in named_pat.finditer(source):
        spec = (m.group("spec") or "").strip()
        members = m.group("members") or ""
        for sym in _parse_js_import_members(members):
            out.append(ImportedJsSymbol(specifier=spec, symbol=sym))

    # Namespace imports: import * as A from 'module'
    ns_pat = re.compile(
        r"import\s*\*\s+as\s+(?P<sym>[A-Za-z_$][A-Za-z0-9_$]*)\s*from\s*['\"](?P<spec>[^'\"]+)['\"]",
        re.MULTILINE,
    )
    for m in ns_pat.finditer(source):
        spec = (m.group("spec") or "").strip()
        sym = (m.group("sym") or "").strip()
        if sym:
            out.append(ImportedJsSymbol(specifier=spec, symbol=sym))

    # Default imports: import A from 'module'
    default_pat = re.compile(
        r"import\s+(?!\{)(?!\*\s+as\b)(?P<sym>[A-Za-z_$][A-Za-z0-9_$]*)\s*from\s*['\"](?P<spec>[^'\"]+)['\"]",
        re.MULTILINE,
    )
    for m in default_pat.finditer(source):
        spec = (m.group("spec") or "").strip()
        sym = (m.group("sym") or "").strip()
        if sym:
            out.append(ImportedJsSymbol(specifier=spec, symbol=sym))

    # CommonJS destructuring: const {A, B} = require('module')
    cjs_pat = re.compile(
        r"(?:const|let|var)\s*\{\s*(?P<members>[^}]+)\s*\}\s*=\s*require\s*\(\s*['\"](?P<spec>[^'\"]+)['\"]\s*\)",
        re.MULTILINE,
    )
    for m in cjs_pat.finditer(source):
        spec = (m.group("spec") or "").strip()
        members = m.group("members") or ""
        for sym in _parse_js_import_members(members):
            out.append(ImportedJsSymbol(specifier=spec, symbol=sym))

    return out


def _js_relative_specifier_to_local_paths(
    *,
    importer_file: str,
    specifier: str,
) -> List[str]:
    """
    Map relative import specifier to local file candidates.

    If `specifier` is `./foo` and importer is `src/use.ts`, candidates include:
    - `src/foo.ts`, `src/foo.tsx`, `src/foo.js`, `src/foo.jsx`
    - `src/foo/index.ts`, ... `index.jsx`
    """
    if not specifier or not specifier.startswith("."):
        return []

    base_dir = os.path.dirname(os.path.abspath(importer_file))
    base = os.path.normpath(os.path.join(base_dir, specifier))
    exts = [".ts", ".tsx", ".js", ".jsx"]

    candidates: List[str] = []
    for ext in exts:
        candidates.append(base + ext)
        candidates.append(os.path.join(base, "index" + ext))

    existing: List[str] = []
    for c in candidates:
        if os.path.isfile(c):
            existing.append(os.path.realpath(c))
    return existing


def build_symbol_dependency_context_from_py_files(
    *,
    repo_root: str,
    py_files: Sequence[str],
    symbol_index,
    max_symbols: int = 20,
    max_chars: int = 4000,
) -> str:
    """
    Build a short context block by:
    - parsing imports from python files
    - resolving each imported symbol via SymbolIndex
    - preferring tags whose path matches imported module candidates
    """
    if not py_files:
        return ""

    parts: List[str] = []
    total = 0
    for fp in py_files:
        if total >= max_chars:
            break
        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                src = f.read()
        except OSError:
            continue

        imported = extract_python_imported_symbols(src)
        if not imported:
            continue

        for imp in imported[:max_symbols]:
            if total >= max_chars:
                break
            preferred = module_to_local_paths(repo_root, imp.module or "")
            resolved = symbol_index.resolve_symbol_to_snippet_preferring_paths(
                imp.symbol,
                preferred_paths=preferred,
                context_lines=12,
                max_chars=min(900, max_chars - total),
            )
            if not resolved or not resolved.snippet.strip():
                continue
            rel = os.path.relpath(resolved.tag.path, repo_root)
            block = (
                f"### {imp.symbol} ({rel}:{resolved.start_line}-{resolved.end_line})\n"
                f"```\n{resolved.snippet}\n```\n\n"
            )
            if total + len(block) > max_chars:
                break
            parts.append(block)
            total += len(block)

    if not parts:
        return ""
    return "## Symbol dependencies (from @python file imports)\n\n" + "".join(parts)


def build_symbol_dependency_context_from_js_ts_files(
    *,
    repo_root: str,
    js_ts_files: Sequence[str],
    symbol_index,
    max_symbols: int = 20,
    max_chars: int = 4000,
) -> str:
    """
    Build a context block by:
    - regex-parsing imports from JS/TS source files
    - resolving each imported symbol via SymbolIndex
    - preferring local paths for relative imports (`./...`)
    """
    if not js_ts_files:
        return ""

    parts: List[str] = []
    total_chars = 0
    remaining_symbols = max(0, int(max_symbols))

    for importer_fp in js_ts_files:
        if remaining_symbols <= 0:
            break
        if total_chars >= max_chars:
            break

        try:
            with open(importer_fp, "r", encoding="utf-8", errors="replace") as f:
                src = f.read()
        except OSError:
            continue

        imported = extract_js_imported_symbols(src)
        if not imported:
            continue

        for imp in imported:
            if remaining_symbols <= 0:
                break
            if total_chars >= max_chars:
                break

            preferred = (
                _js_relative_specifier_to_local_paths(
                    importer_file=importer_fp, specifier=imp.specifier
                )
                if (imp.specifier or "").startswith(".")
                else []
            )

            resolved = symbol_index.resolve_symbol_to_snippet_preferring_paths(
                imp.symbol,
                preferred_paths=preferred if preferred else None,
                context_lines=12,
                max_chars=min(900, max_chars - total_chars),
            )
            if not resolved or not resolved.snippet.strip():
                continue

            rel = os.path.relpath(resolved.tag.path, repo_root)
            block = (
                f"### {imp.symbol} ({rel}:{resolved.start_line}-{resolved.end_line})\n"
                f"```\n{resolved.snippet}\n```\n\n"
            )
            if total_chars + len(block) > max_chars:
                break
            parts.append(block)
            total_chars += len(block)
            remaining_symbols -= 1

    if not parts:
        return ""
    return (
        "## Symbol dependencies (from @js/ts file imports)\n\n" + "".join(parts)
    )


def build_symbol_dependency_context_from_source_files(
    *,
    repo_root: str,
    source_files: Sequence[str],
    symbol_index,
    max_symbols: int = 20,
    max_chars: int = 4000,
) -> str:
    """
    Wrapper: keep Python behavior unchanged; add JS/TS support.
    """
    py_files = [f for f in source_files if (f or "").lower().endswith(".py")]
    js_files = [
        f
        for f in source_files
        if (f or "").lower().endswith((".js", ".ts", ".tsx", ".jsx"))
    ]

    if py_files and not js_files:
        return build_symbol_dependency_context_from_py_files(
            repo_root=repo_root,
            py_files=py_files,
            symbol_index=symbol_index,
            max_symbols=max_symbols,
            max_chars=max_chars,
        )
    if js_files and not py_files:
        return build_symbol_dependency_context_from_js_ts_files(
            repo_root=repo_root,
            js_ts_files=js_files,
            symbol_index=symbol_index,
            max_symbols=max_symbols,
            max_chars=max_chars,
        )

    # Mixed input: build both (best-effort) while respecting overall char budget.
    remaining_chars = max(0, int(max_chars))
    remaining_symbols = max(0, int(max_symbols))
    out_parts: List[str] = []

    if py_files:
        py_block = build_symbol_dependency_context_from_py_files(
            repo_root=repo_root,
            py_files=py_files,
            symbol_index=symbol_index,
            max_symbols=remaining_symbols,
            max_chars=remaining_chars,
        )
        if py_block:
            out_parts.append(py_block)
            used_symbols = sum(
                1 for line in py_block.splitlines() if (line or "").startswith("### ")
            )
            remaining_symbols = max(0, remaining_symbols - used_symbols)
            remaining_chars = max(0, remaining_chars - len(py_block))

    if js_files and remaining_chars > 0 and remaining_symbols > 0:
        js_block = build_symbol_dependency_context_from_js_ts_files(
            repo_root=repo_root,
            js_ts_files=js_files,
            symbol_index=symbol_index,
            max_symbols=remaining_symbols,
            max_chars=remaining_chars,
        )
        if js_block:
            out_parts.append(js_block)

    return "\n\n".join([p for p in out_parts if p]).strip()


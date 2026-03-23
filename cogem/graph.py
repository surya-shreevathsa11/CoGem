from __future__ import annotations

import ast
import os
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


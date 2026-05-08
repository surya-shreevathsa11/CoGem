from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any, Dict, Tuple


def _as_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    v = raw.strip().lower()
    if v in ("1", "true", "yes", "on", "enabled"):
        return True
    if v in ("0", "false", "no", "off", "disabled"):
        return False
    return default


def _as_int(raw: str | None, default: int, *, minimum: int | None = None) -> int:
    if raw is None or not raw.strip():
        out = default
    else:
        try:
            out = int(raw.strip())
        except ValueError:
            out = default
    if minimum is not None:
        out = max(minimum, out)
    return out


def _as_choice(raw: str | None, default: str, allowed: Tuple[str, ...]) -> str:
    v = (raw or "").strip().lower()
    if not v:
        return default
    if v in allowed:
        return v
    return default


@dataclass(frozen=True)
class Settings:
    codex_backend: str = "auto"
    gemini_backend: str = "auto"
    claude_backend: str = "sdk"
    codex_sdk_model: str = "gpt-4.1-mini"
    gemini_sdk_model: str = "gemini-2.5-flash"
    claude_sdk_model: str = "claude-sonnet-4-6"
    async_llm: bool = True
    secondary_intent_llm: bool = True
    router_classifier_model: str = "gemini-2.5-flash-lite"
    subprocess_timeout_sec: int = 60
    validation_docker: bool = False
    strict_sandbox: bool = False
    validation_max_attempts: int = 2
    auto_repo_context: bool = True
    auto_repo_context_max_chars: int = 8000
    auto_repo_context_max_files: int = 6
    auto_repo_context_max_depth: int = 2
    vector_rag: bool = False
    vector_rebuild: bool = False
    vector_top_k: int = 8
    vector_chunk_chars: int = 2500
    sym_rag: bool = True
    sym_rag_max_symbols: int = 12
    sym_rag_max_chars: int = 3500
    symbol_index: bool = True
    symbol_dep_context: bool = True
    symbol_dep_max_symbols: int = 20
    symbol_dep_max_chars: int = 4000
    mcp_timeout_sec: int = 60
    mcp_plugins_json: str = ""
    stitch_mcp: bool = True
    stitch_mcp_cmd: str = "npx"
    stitch_mcp_args: str = "-y stitch-mcp"
    debug: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            codex_backend=_as_choice(
                os.environ.get("CLOGEM_CODEX_BACKEND"),
                "auto",
                ("auto", "sdk", "cli"),
            ),
            gemini_backend=_as_choice(
                os.environ.get("CLOGEM_GEMINI_BACKEND"),
                "auto",
                ("auto", "sdk", "cli"),
            ),
            claude_backend=_as_choice(
                os.environ.get("CLOGEM_CLAUDE_BACKEND"),
                "sdk",
                ("sdk",),
            ),
            codex_sdk_model=(
                os.environ.get("CLOGEM_CODEX_SDK_MODEL", "").strip() or "gpt-4.1-mini"
            ),
            gemini_sdk_model=(
                os.environ.get("CLOGEM_GEMINI_SDK_MODEL", "").strip()
                or "gemini-2.5-flash"
            ),
            claude_sdk_model=(
                os.environ.get("CLOGEM_CLAUDE_SDK_MODEL", "").strip()
                or "claude-sonnet-4-6"
            ),
            async_llm=_as_bool(os.environ.get("CLOGEM_ASYNC_LLM"), True),
            secondary_intent_llm=_as_bool(
                os.environ.get("CLOGEM_SECONDARY_INTENT_LLM"), True
            ),
            router_classifier_model=(
                os.environ.get("CLOGEM_ROUTER_CLASSIFIER_MODEL", "").strip()
                or "gemini-2.5-flash-lite"
            ),
            subprocess_timeout_sec=_as_int(
                os.environ.get("CLOGEM_SUBPROCESS_TIMEOUT_SEC"), 60, minimum=1
            ),
            validation_docker=_as_bool(
                os.environ.get("CLOGEM_VALIDATION_DOCKER"), False
            ),
            strict_sandbox=_as_bool(os.environ.get("CLOGEM_STRICT_SANDBOX"), False),
            validation_max_attempts=_as_int(
                os.environ.get("CLOGEM_VALIDATION_MAX_ATTEMPTS"), 2, minimum=1
            ),
            auto_repo_context=_as_bool(
                os.environ.get("CLOGEM_AUTO_REPO_CONTEXT"), True
            ),
            auto_repo_context_max_chars=_as_int(
                os.environ.get("CLOGEM_AUTO_REPO_CONTEXT_MAX_CHARS"),
                8000,
                minimum=500,
            ),
            auto_repo_context_max_files=_as_int(
                os.environ.get("CLOGEM_AUTO_REPO_CONTEXT_MAX_FILES"), 6, minimum=1
            ),
            auto_repo_context_max_depth=_as_int(
                os.environ.get("CLOGEM_AUTO_REPO_CONTEXT_MAX_DEPTH"), 2, minimum=1
            ),
            vector_rag=_as_bool(os.environ.get("CLOGEM_VECTOR_RAG"), False),
            vector_rebuild=_as_bool(os.environ.get("CLOGEM_VECTOR_REBUILD"), False),
            vector_top_k=_as_int(os.environ.get("CLOGEM_VECTOR_TOP_K"), 8, minimum=1),
            vector_chunk_chars=_as_int(
                os.environ.get("CLOGEM_VECTOR_CHUNK_CHARS"), 2500, minimum=500
            ),
            sym_rag=_as_bool(os.environ.get("CLOGEM_SYM_RAG"), True),
            sym_rag_max_symbols=_as_int(
                os.environ.get("CLOGEM_SYM_RAG_MAX_SYMBOLS"), 12, minimum=1
            ),
            sym_rag_max_chars=_as_int(
                os.environ.get("CLOGEM_SYM_RAG_MAX_CHARS"), 3500, minimum=500
            ),
            symbol_index=_as_bool(os.environ.get("CLOGEM_SYMBOL_INDEX"), True),
            symbol_dep_context=_as_bool(
                os.environ.get("CLOGEM_SYMBOL_DEP_CONTEXT"), True
            ),
            symbol_dep_max_symbols=_as_int(
                os.environ.get("CLOGEM_SYMBOL_DEP_MAX_SYMBOLS"), 20, minimum=1
            ),
            symbol_dep_max_chars=_as_int(
                os.environ.get("CLOGEM_SYMBOL_DEP_MAX_CHARS"), 4000, minimum=500
            ),
            mcp_timeout_sec=_as_int(
                os.environ.get("CLOGEM_MCP_TIMEOUT_SEC"), 60, minimum=1
            ),
            mcp_plugins_json=(os.environ.get("CLOGEM_MCP_PLUGINS_JSON") or "").strip(),
            stitch_mcp=_as_bool(os.environ.get("CLOGEM_STITCH_MCP"), True),
            stitch_mcp_cmd=(os.environ.get("CLOGEM_STITCH_MCP_CMD") or "npx").strip(),
            stitch_mcp_args=(
                os.environ.get("CLOGEM_STITCH_MCP_ARGS") or "-y stitch-mcp"
            ).strip(),
            debug=_as_bool(
                os.environ.get("CLOGEM_DEBUG") or os.environ.get("COGEM_DEBUG"), False
            ),
        )

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)

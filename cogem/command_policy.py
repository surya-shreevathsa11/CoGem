from __future__ import annotations

import os
from typing import List, Optional, Tuple


ALLOWED_EXECUTABLES = {
    "git",
    "python",
    "python3",
    "poetry",
    "pdm",
    "pytest",
    "ruff",
    "flake8",
    "black",
    "mypy",
    "node",
    "npm",
    "npx",
    "pyright",
    "yarn",
    "pnpm",
    "go",
    "golangci-lint",
    "cargo",
    "make",
}


def _allow_relaxed_policy() -> bool:
    return (os.environ.get("COGEM_RUN_POLICY") or "").strip().lower() in (
        "relaxed",
        "legacy",
    )


def validate_local_command_args(args: List[str], label: str) -> Tuple[bool, str]:
    """
    Validate parsed args for /run, /test, /lint, /typecheck flows.

    Returns (ok, reason_if_denied).
    """
    if not args:
        return False, "Empty command."
    exe = os.path.basename(args[0]).lower()
    if exe not in ALLOWED_EXECUTABLES:
        allow = ", ".join(sorted(ALLOWED_EXECUTABLES))
        return False, f"Executable not allowed: {exe}. Allowed: {allow}"

    # Optional relaxed mode for compatibility.
    if _allow_relaxed_policy():
        return True, ""

    # Strict policy for /run; test/lint/typecheck get a narrower, deterministic set.
    sub = args[1].lower() if len(args) > 1 else ""
    label = (label or "").strip().lower()

    if label in ("tests", "lint", "typecheck"):
        if exe in ("pytest", "ruff", "flake8", "mypy", "pyright", "golangci-lint"):
            return True, ""
        if exe in ("go", "cargo"):
            # Allow go/cargo validation commands.
            return True, ""
        if exe in ("poetry", "pdm"):
            # Allow toolchain-managed test/lint/typecheck commands.
            joined = " ".join(a.lower() for a in args[1:])
            ok_tokens = (
                "pytest",
                "test",
                "ruff",
                "flake8",
                "mypy",
                "pyright",
                "check",
                "lint",
            )
            if any(t in joined for t in ok_tokens):
                return True, ""
            return False, f"{exe} command not allowed for {label}; expected test/lint/typecheck commands."
        if exe in ("python", "python3"):
            # Allow python -m <tool>...
            if len(args) >= 3 and args[1] == "-m" and args[2] in (
                "pytest",
                "ruff",
                "flake8",
                "mypy",
            ):
                return True, ""
            return False, "python/python3 only allowed as '-m pytest|ruff|flake8|mypy' for validation."
        if exe in ("npm", "pnpm", "yarn"):
            # Allow only test/lint-ish scripts for validation.
            joined = " ".join(a.lower() for a in args[1:])
            ok_tokens = ("test", "lint", "eslint", "tsc", "typecheck")
            if any(t in joined for t in ok_tokens):
                return True, ""
            return False, f"{exe} command not allowed for {label}; expected test/lint/typecheck scripts."
        if exe == "npx":
            if len(args) >= 2 and args[1] == "tsc":
                return True, ""
            return False, "npx allowed only for 'npx tsc --noEmit' during typecheck."
        return False, f"{exe} not allowed for validation label '{label}'."

    # /run strict policy: allow mostly read-only and developer diagnostics.
    if label == "run":
        if exe == "git":
            if sub in (
                "status",
                "diff",
                "log",
                "show",
                "branch",
                "rev-parse",
                "remote",
                "fetch",
                "pull",
            ):
                return True, ""
            return False, "git subcommand not allowed in strict /run policy."
        if exe in ("npm", "pnpm", "yarn"):
            if sub in ("run", "test", "lint"):
                return True, ""
            return False, f"{exe} subcommand not allowed in strict /run policy."
        if exe in ("poetry", "pdm"):
            joined = " ".join(a.lower() for a in args[1:])
            ok_tokens = ("run", "pytest", "ruff", "flake8", "mypy", "pyright", "check")
            if any(t in joined for t in ok_tokens):
                return True, ""
            return False, f"{exe} command not allowed in strict /run policy."
        if exe == "npx":
            # Allow version checks and tsc.
            if len(args) >= 2 and args[1] in ("tsc", "--version"):
                return True, ""
            return False, "npx command not allowed in strict /run policy."
        if exe in ("pytest", "ruff", "flake8", "black", "mypy", "pyright", "go", "cargo", "make", "golangci-lint"):
            return True, ""
        if exe in ("python", "python3"):
            if len(args) >= 3 and args[1] == "-m" and args[2] in (
                "pytest",
                "ruff",
                "flake8",
                "mypy",
            ):
                return True, ""
            return False, "python/python3 in /run only allows '-m pytest|ruff|flake8|mypy' in strict mode."
        if exe == "node":
            # Keep node very narrow in strict mode.
            if len(args) >= 2 and args[1] in ("--version", "-v"):
                return True, ""
            return False, "node execution is restricted in strict /run policy."
        return False, f"{exe} not allowed in strict /run policy."

    # Unknown labels default to deny.
    return False, f"Unknown command label: {label}."


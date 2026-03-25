# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**CoGem** (Codex + Gemini) is a Python CLI tool that orchestrates multiple AI models into a structured code generation workflow. It combines OpenAI Codex for drafting, Google Gemini for independent review, and validation loops for quality assurance.

## Critical Rules

### Git Operations
- **Never push without explicit user consent.** Always ask first, every time.
- **Never commit directly to main.** Always create a feature branch first.
- **No AI attribution in commits.** No "Co-Authored-By: Claude" or similar lines.
- **All commits must reference a GitHub issue** — add `Closes #N` or `Refs #N` in the commit body.
- **Branch naming:** `feat/<summary>`, `fix/<summary>`, `chore/<summary>`

### Task Management
- **System:** GitHub Issues on `surya-shreevathsa11/CoGem`
- **All work is tracked via GitHub Issues.** Before starting work, confirm which issue(s) you are addressing.
- **Assign the issue** to whoever is working on it (`gh issue edit N --add-assignee USERNAME`).
- **Assign the PR** to the same person (`gh pr edit N --add-assignee USERNAME`).
- **Link issue to PR** via `Closes #N` in the PR body/commit footer — this auto-closes the issue on merge.
- **Never close an issue without tests.** If code was changed, tests must be added/updated and passing.
- To find the current authenticated user: `gh api user --jq '.login'`

## Build & Test Commands

```bash
# Install (editable with dev deps)
pip install -e ".[dev]"

# Run tests
python -m pytest -q

# Run a single test
python -m pytest -v -k "test_function_name"

# Lint (if ruff available)
ruff check cogem/ tests/

# Type check (if pyright available)
pyright cogem/

# Build package
python -m build

# Pre-commit hooks (after setup)
pre-commit run --all-files
```

## Architecture

```
cogem/
├── cli.py              # Main REPL and orchestration (monolith — decomposition planned)
├── llm_clients.py      # OpenAI + Google GenAI SDK wrappers
├── services/
│   ├── routing.py      # BUILD vs CHAT intent classification
│   ├── pipeline.py     # Build pipeline orchestration, Stitch, RAG
│   └── commands.py     # Slash command dispatch
├── stitch/             # Google Stitch frontend integration
│   ├── adapters.py     # CLI/HTTP/MCP/manual adapters
│   ├── detection.py    # Frontend task detection heuristics
│   ├── mcp_stdio.py    # MCP stdio client
│   └── prompt_builder.py
├── graph.py            # Python AST import analysis for symbol deps
├── symbols.py          # ctags-based symbol resolution
├── repo_awareness.py   # Auto repo context for build prompts
├── vector_index.py     # LanceDB semantic retrieval (optional)
├── validation.py       # Sandbox test/lint/typecheck execution
├── mcp_plugins.py      # Generic MCP plugin client
├── command_policy.py   # /run command allowlist
├── git_context.py      # Git operations
├── pdf_tools.py        # PDF generation
├── task_intent.py      # Task type detection
├── visual_review.py    # Playwright screenshot + Gemini Vision
└── write_safety.py     # File write safety checks
```

## HARD RULE: Opus Never Codes

**Opus MUST NOT write code directly.** All code changes go through Sonnet subagents.

- **Opus:** analyze, plan, research (Glob/Grep/Read), review, coordinate, branch management, commits
- **Sonnet:** all file writes, edits, and code changes

### How to Invoke Sonnet for Coding

Use the `sonnet-coder` custom subagent (defined in `.claude/agents/sonnet-coder.md`) via the Agent tool:

```
Agent tool with: subagent_type: "sonnet-coder"
```

The `sonnet-coder` agent has `model: sonnet` in its frontmatter — this ensures it runs on Sonnet, not Opus.

- **DO NOT use the default Agent tool (general-purpose) for coding** — it inherits the parent model (Opus).
- For parallel coding tasks, use `isolation: "worktree"` with the sonnet-coder agent.
- Sonnet prompts must include: clear scope, relevant file paths, acceptance criteria, test requirements.
- **Flag model routing issues immediately** — if you suspect coding work is running on Opus instead of Sonnet, stop and tell the user.

## Claude + Codex Orchestration

Claude (Opus) is the primary orchestrator. Codex is the pair programmer and code reviewer, invoked via `codex exec`. The git repo is the shared state layer.

Codex reads `AGENTS.md` for its role context.

### The Four Phases

Every task goes through all four phases. No skipping, even for small tasks.

#### Phase 1: Planning (Claude + Codex — independent scoping)

**DO NOT skip this step.** Claude MUST invoke Codex for pair planning on EVERY task.

**Step 1 — Claude scopes first (internally).** Read the GitHub issue, analyze requirements, read relevant code. Form your own assessment. Do NOT present this to the user yet.

**Step 2 — Codex scopes independently.** Give Codex only the raw GitHub issue — the same inputs you started with. Do NOT tell it what you found or what approach you prefer.

```bash
codex exec "You are scoping a task independently. Read GitHub issue #N: 'gh issue view N --repo surya-shreevathsa11/CoGem --json body,title'. Read whatever source files you think are relevant. Give your assessment: what's the right approach, what are the edge cases, what should the acceptance criteria be?" --full-auto
```

**Step 3 — Compare and consolidate.** Where you agree, you're probably right. Where you disagree, investigate why. Reconcile into a single plan.

**Step 4 — Update GitHub issue** with the consensus plan and acceptance criteria.

#### Phase 2: Implementation (Claude → Sonnet via sonnet-coder subagent)

1. Claude delegates coding to Sonnet via the `sonnet-coder` subagent (Agent tool with `subagent_type: "sonnet-coder"`)
2. Sonnet writes **tests first**, then implements code to pass them
3. Claude reviews the diff after Sonnet finishes
4. Claude runs verification: `python -m pytest -q`, lint, type-check
5. Claude commits at meaningful milestones
6. **The Opus-never-codes rule still applies**

#### Phase 3: Pre-Push Review (Codex reviews)

After implementation, before pushing, Claude invokes Codex to review:

```bash
codex exec "You are reviewing implementation for GitHub issue #N. Run 'gh issue view N --repo surya-shreevathsa11/CoGem --json body,title' to read the scope. Run 'git diff main...HEAD' to see changes. Review the FULL implementation — trace changes through the codebase, not just the diff. Check: missed requirements, bugs, missing tests, security issues, over-engineering. Verify tests were added/updated. Run 'python -m pytest -q' to check tests pass. Categorize: BLOCKING (must fix) vs NON-BLOCKING (follow-up issue). Be specific — file paths and line numbers." --full-auto
```

#### Phase 4: Resolution (Claude <-> Codex iterate until APPROVED)

- Claude addresses BLOCKING issues via Sonnet subagent
- **Claude MUST re-invoke Codex review after fixing BLOCKING issues** — do not assume the fix is correct
- Loop continues until Codex explicitly says **APPROVED** with no BLOCKING issues
- There is no limit on review rounds — keep iterating until clean
- Non-blocking issues: fix in the same pass if quick, otherwise create a new GitHub Issue
- **Always ask user for permission before pushing**

### Codex CLI Notes

- **Prefer `--full-auto`** for standard planning and review tasks
- **Use `--sandbox danger-full-access`** only when Codex needs network access (e.g., `gh` commands, API calls)
- **Never use `codex review`** — always use `codex exec`

## Pre-Commit Hooks

This project uses `pre-commit` for automated quality gates. Hooks run on every commit:

1. **ruff** — linting and formatting
2. **pytest collection** — verify tests can be collected (no import errors)
3. **compileall** — syntax check all Python files

### Setup

```bash
pip install pre-commit
pre-commit install
```

### If a Hook Fails

Fix the issue and commit again. Do NOT bypass with `--no-verify`.

## Testing Requirements

**All code changes require corresponding test updates.** No exceptions.

### TDD Workflow
1. **Red:** Write failing tests that define expected behavior
2. **Green:** Implement minimum code to make tests pass
3. **Refactor:** Clean up while keeping tests green

### Test Standards
- Tests live in `tests/` alongside the module name (`test_<module>.py`)
- Use pytest fixtures and parametrize for table-driven tests
- Test both success and error paths
- Mock external dependencies (subprocess, SDK calls), not internal logic
- Every bug fix MUST include a regression test

### When Delegating to Sonnet
The prompt MUST include:
- Which tests to write or update
- Instruction to write **failing tests first**
- Acceptance criteria the tests should verify

## Git Commit Conventions

Use the `/commit` command or the `git-commit-helper` agent for assisted commit message crafting.

### Commit Message Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

| Type | Use When |
|------|----------|
| `feat` | New feature or capability |
| `fix` | Bug fix |
| `docs` | Documentation only changes |
| `style` | Code style (formatting, no logic change) |
| `refactor` | Code change that neither fixes nor adds |
| `perf` | Performance improvement |
| `test` | Adding or updating tests |
| `chore` | Build process, deps, tooling |
| `ci` | CI/CD pipeline changes |

### Scope

Use the cogem module name as scope:

`cli`, `llm-clients`, `routing`, `pipeline`, `commands`, `stitch`, `graph`, `symbols`, `repo-awareness`, `vector-index`, `validation`, `mcp`, `command-policy`, `git-context`, `pdf-tools`, `task-intent`, `visual-review`, `write-safety`, `config`, `deps`

Multiple scopes: `feat(routing,pipeline): ...`
Scope-agnostic: `docs: update README`

### Subject Rules

- Imperative mood: "add" not "added" or "adds"
- Don't capitalize the first letter
- No period at the end
- Keep under 50 characters
- Be specific: "add retry logic to LLM calls" not "update stuff"

### Body (when needed)

- Explain **why** the change was made
- Explain **what** problem it solves
- Wrap lines at 72 characters
- Separate from subject with a blank line

### Footer (required)

- **Always reference a GitHub issue**: `Closes #N` (completed) or `Refs #N` (referenced)
- Breaking changes: `BREAKING CHANGE: description`
- **No AI attribution** — no `Co-Authored-By`, no "Generated by AI"

### Examples

```
fix(validation): return failure when strict sandbox has no Docker

Strict mode was returning True with "Validation skipped" when Docker
was unavailable, defeating the purpose of strict validation.

Closes #3
```

```
refactor(cli): extract validation logic into validation module

Move _run_validation_suite, _run_validation_suite_docker, and related
helpers from cli.py into cogem/validation.py as the first step of
cli.py decomposition.

Refs #6
```

### Branching & Workflow

- **Always create a feature branch** before any work: `feat/`, `fix/`, `chore/`
- **Never commit directly to main**
- **Branch naming:** `<type>/<short-description>` (e.g., `fix/strict-sandbox-return-value`)
- **Short-lived branches:** merge within 24 hours, ideally <4 hours
- **Delete branches immediately** after merging
- **One logical change per commit** — split unrelated changes into separate commits
- Tests and implementation for the same change can share a commit

## Key Patterns

### Configuration
- All config is currently via `os.environ.get()` calls scattered across modules
- Centralization into a typed `Settings` object is planned (see GitHub Issue #10)
- Env var prefix: `COGEM_`

### Error Handling
- Many modules use graceful degradation (try feature, fall back silently)
- Structured logging is planned (see GitHub Issue #11)
- When adding new features: log failures at debug level, keep fallback behavior

### LLM Client Usage
- `llm_clients.py` provides sync + async wrappers for OpenAI and Gemini
- SDK-first with CLI fallback (`COGEM_CODEX_BACKEND=auto|sdk|cli`)
- Both sync and async variants available

## Known Issues

Active GitHub Issues track all known problems and planned improvements. Check:
```bash
gh issue list --repo surya-shreevathsa11/CoGem
```

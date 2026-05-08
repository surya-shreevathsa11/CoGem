# Clogem Features

This document is a detailed feature map of what Clogem can do today.

## 1) Multi-model orchestration

Clogem is an orchestrator, not a single-model wrapper.

- Supports providers: `codex`, `gemini`, `claude`
- Supports roles: `orchestrator`, `planner`, `coder`, `reviewer`, `summariser`
- Default behavior emphasizes independent review:
  - Codex for orchestration/planning/coding
  - Gemini for review/summaries
- Role routing is configurable via:
  - CLI flags (`--role-provider role=provider`)
  - Env var (`CLOGEM_ROLE_PROVIDER_MAP`)
  - In-session command (`/roles/<role>/<provider>`)

## 2) Build vs chat turn routing

Each turn can be routed as:

- **BUILD/workflow**: run planning/coding/review/improvement pipeline
- **CHAT**: conversational answer without code pipeline

You can force behavior with session directives:

- `/build`, `/plan`, `/debug`, `/agent`, `/ask`, `/research`

There is also prerequisite-first detection so Clogem answers setup/how-to questions before running a full build when appropriate.

## 3) End-to-end code pipeline

For build turns, Clogem can run a loop like:

1. Draft implementation
2. Independent review
3. Improvement pass
4. Summary output

The goal is to reduce single-model blind spots and make improvements more traceable.

## 4) Provider backends (CLI + SDK)

Clogem supports both CLI and SDK paths depending on provider and configuration.

- Codex: CLI and OpenAI SDK
- Gemini: CLI and Google GenAI SDK
- Claude: Anthropic SDK (SDK-only)

Backend controls include:

- `CLOGEM_CODEX_BACKEND=auto|sdk|cli`
- `CLOGEM_GEMINI_BACKEND=auto|sdk|cli`
- `CLOGEM_CLAUDE_BACKEND=sdk`

In `auto`, Clogem prefers SDK when credentials are available.

## 5) Runtime model control

Models can be set at startup and changed during a live session.

- Startup: `--codex-model`, `--gemini-model`, `--claude-model`
- In-session:
  - `/codex/model`
  - `/gemini/model`
  - `/claude/model`

## 6) In-session command surface

Clogem includes operational commands for repo work and tooling:

- Role and model commands: `/roles`, `/roles/<role>/<provider>`, `/codex/model`, `/gemini/model`, `/claude/model`
- Repo/info: `/repo/info`
- Verification: `/test`, `/lint`
- Local execution (guarded): `/run <cmd>`
- Utility: `/pdf`
- GitHub helpers: `/github/info`, `/github/clone`
- MCP plugin controls: `/mcp/plugins`, `/mcp/tools`, `/mcp/call`
- Semantic retrieval: `/rag/search`

## 7) Claude integration UX

When mapping any role to `claude`, Clogem uses Anthropic SDK.

- If `ANTHROPIC_API_KEY` is missing and user chooses Claude via `/roles/<role>/claude`, Clogem prompts for the key in-session.
- Key can be set permanently through shell profile as well.

## 8) Context expansion with @ mentions

Users can mention files/folders in prompts:

- `@file.py`, `@folder/`, `@docs/spec.pdf`
- Mention handling includes size/page limits and safe path constraints
- Optional symbol mention support (ctags) for `@SymbolName`

This helps inject relevant context directly into build prompts.

## 9) Repo awareness and dependency context

Clogem can auto-build contextual snippets from repository source:

- Keyword-based retrieval from local code
- Python/JS dependency-aware expansion
- Optional symbol dependency context injection

Goal: reduce missing-context mistakes during code generation.

## 10) Optional vector RAG

Clogem can enable semantic retrieval over the full repo:

- Uses LanceDB + sentence-transformers (optional deps)
- Maintains file-hash manifest and incremental rebuild behavior
- Injects top semantic chunks into build context
- Manual query command: `/rag/search <query>`

## 11) Validation loop and safe execution

On `/build`, Clogem can execute repo checks and feed failures into correction passes.

- Test/lint/typecheck detection (best effort by stack)
- Iterative attempts controlled by `CLOGEM_VALIDATION_MAX_ATTEMPTS`
- Validation in temporary sandbox copy
- Optional Docker-preferred validation mode
- Strict mode behavior configurable through env

## 12) Frontend-first Stitch stage

For UI-heavy tasks, Clogem can run Stitch integration before the standard code loop.

- Adapter chain supports CLI, MCP, HTTP, and manual fallback
- Manual fallback remains available when integrations fail
- Can include clipboard-assisted prompt handoff

This is designed to improve UI scaffolding quality in frontend-heavy prompts.

## 13) Visual review (frontend)

For frontend outputs, Clogem can run screenshot-based review:

- Headless screenshot capture (Playwright path)
- Gemini vision review of layout and UI quality
- Findings can be fed back into a fix pass

## 14) MCP plugin ecosystem

Beyond Stitch, Clogem can call external MCP servers:

- Built-in aliases for providers like Jira/Sentry/Datadog/DB schema
- Custom plugin registry via JSON env config
- Runtime discovery and invocation via `/mcp/*` commands

## 15) Memory and continuity

Clogem maintains session/project continuity:

- Uses persisted memory context (`memory.json`)
- Applies memory during routing and responses
- Designed for iterative multi-turn project work

## 16) CLI UX and discoverability

- Rich terminal output and status traces
- Prompt-toolkit completion for `/` and `@` menus
- Session command hints in the REPL
- Boot checks for required providers before workflow starts

---

For command-specific usage, see [`help.md`](help.md).

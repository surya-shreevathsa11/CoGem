# Clogem Command Help

This file is a complete reference for slash commands available inside an active `clogem` session.

## Session directives (turn mode)

Use these at the start of your message to control how that turn is handled:

- `/build <task>`: force full build pipeline
- `/plan <task>`: planning emphasis
- `/debug <task>`: debugging emphasis
- `/agent <task>`: autonomous multi-step implementation style
- `/ask <question>`: answer directly (skip build loop)
- `/research <query>`: research-style response (skip build loop)

## Model commands

- `/codex/model`: show Codex model status
- `/codex/model <MODEL_ID>`: set Codex model for this session
- `/codex/model reset`: restore startup/default Codex model
- `/gemini/model`: show Gemini model status
- `/gemini/model <MODEL_ID>`: set Gemini model for this session
- `/gemini/model reset`: restore startup/default Gemini model
- `/claude/model`: show Claude model status (SDK only)
- `/claude/model <MODEL_ID>`: set Claude model for this session
- `/claude/model reset`: restore startup/default Claude model

## Role mapping commands

- `/roles`: show active role to provider mapping
- `/roles/<role>/<provider>`: set provider for one role in-session
  - Roles: `orchestrator`, `planner`, `coder`, `reviewer`, `summariser`
  - Providers: `codex`, `gemini`, `claude`
  - Example: `/roles/orchestrator/claude`
  - Alias supported: `cover` maps to `coder` (`/roles/cover/claude`)

If you map a role to `claude` and `ANTHROPIC_API_KEY` is missing, Clogem prompts you to enter it for the current session.

- `/config`: show parsed effective runtime settings for debugging

## Repo and local execution commands

- `/repo/info`: show git root/branch/last commit/status
- `/test`: run detected test command (best effort)
- `/lint`: run detected lint command (best effort)
- `/run <command>`: run local command (permission + allowlist policy)

## Utility commands

- `/pdf <text> [out.pdf]`: generate PDF from text
- `/pdf @path/to/file.txt [out.pdf]`: generate PDF from file content
- `/exit`: exit session
- `/quit`: exit session

## GitHub commands

- `/github/info <url|owner/repo>`: show public repo metadata
- `/github/clone <url|owner/repo> [dest]`: clone repo locally

## MCP commands

- `/mcp/plugins`: list configured MCP plugins
- `/mcp/tools <plugin>`: list plugin tools
- `/mcp/call <plugin> <tool> [json-args]`: invoke plugin tool

## RAG command

- `/rag/search <query>`: semantic search over local vector index

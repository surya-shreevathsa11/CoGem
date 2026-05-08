# Clogem (Codex + Gemini Workflow)

A CLI-based development system that combines:

- Codex → code generation
- Gemini → strict code review
- System → diff + improvement summary

This creates a self-improving coding workflow that works for:

- Scripts (Python, JS, etc.)
- Web development (HTML/CSS/JS)
- Backend APIs
- General coding tasks

---

## Features

- Iterative improvement loop
- Independent review (no bias from generation)
- Code diff (before vs after)
- Improvement summary
- Multi-file project generation
- CLI-based workflow (fast and repeatable)

Detailed capability reference: [`features.md`](features.md)  
Command reference: [`help.md`](help.md)

---

## How Codex, Gemini, and Claude work in Clogem

Clogem is an **orchestrator**: it calls external models through **named roles**. You can change which **provider** (Codex / Gemini / Claude) handles each role; defaults favor **Codex for authoring** and **Gemini for independent review**, so the reviewer is never the same “voice” as the drafter.

### Default role → provider map

| Role | Default provider | Role in the app |
|------|------------------|-----------------|
| **orchestrator** | Codex | Turn routing (build vs chat), `/ask`-style chat, memory, and lightweight classifiers |
| **planner** | Codex | Planning step before implementation when the pipeline runs |
| **coder** | Codex | Draft code, apply diffs, improvement passes after review |
| **reviewer** | Gemini | **Independent** review of generated code (security, design, consistency) |
| **summariser** | Gemini | Short summaries of outcomes and diffs |

**Claude** is **optional**. It is used only when you assign one or more roles to `claude` (for example `coder=claude`) via `--role-provider` or `CLOGEM_ROLE_PROVIDER_MAP`. Claude runs through the **Anthropic SDK** only (`ANTHROPIC_API_KEY`); there is no separate `claude` CLI inside Clogem.

### How a typical **build** turn flows

1. **Router** (usually the orchestrator on **Codex**) classifies the message as **BUILD** (run the pipeline) or **CHAT** (reply only).
2. **Planner / coder** (**Codex** by default) produces or edits code.
3. **Reviewer** (**Gemini**) audits the result without having authored it.
4. **Coder** (**Codex**) applies improvements informed by review.
5. **Summariser** (**Gemini**) condenses what changed.

Pure chat turns skip the code pipeline when the router says **CHAT**. Special cases (e.g. **live weather/news**) can call **Gemini + Google Search grounding** on the SDK path only—see `CLOGEM_GEMINI_REALTIME` in this README.

### Backends: CLI vs SDK

| Provider | How Clogem talks to it |
|----------|-------------------------|
| **Codex** | `codex exec …` (**CLI**) and/or **OpenAI SDK** (`CLOGEM_CODEX_BACKEND=auto\|sdk\|cli`) |
| **Gemini** | `gemini …` (**CLI**) and/or **Google GenAI SDK** (`CLOGEM_GEMINI_BACKEND=auto\|sdk\|cli`) — review, summary, optional grounded “today” answers |
| **Claude** | **Anthropic SDK only** (`CLOGEM_CLAUDE_BACKEND=sdk`) |

In **`auto`**, Clogem prefers the SDK when keys are available and falls back to the CLIs. Set keys as needed: `OPENAI_API_KEY`, `GEMINI_API_KEY` or `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`.

---

## Why Use Clogem Over Standalone CLIs?

Standalone CLIs like `codex` or `gemini` are great for quick, direct edits.  
Clogem is optimized for engineering quality on larger tasks by adding routing, review, and validation structure around model calls.

### 1) Workflow Rigor (Dual-Agent Loop)

- **Standalone:** usually single-author flow (model writes, human reviews).
- **Clogem:** `Codex draft -> Gemini independent review -> Codex improve`, which mirrors a PR author/reviewer pattern and reduces shallow or hallucinated output.

### 2) Intent Routing + Prerequisite-First Handling

- **Standalone:** mixed prompts can jump into implementation too early.
- **Clogem:** routing layer separates conversational vs build turns and can answer prerequisite questions before entering the build loop.

### 3) Specialized Frontend Stage (Stitch)

- **Standalone:** strong general-purpose UI generation, but no dedicated design handoff stage.
- **Clogem:** UI-heavy tasks can route through Stitch adapters/manual handoff first, then continue with the normal build/review/improve pipeline.
- Includes clipboard-assisted handoff in manual Stitch mode when available.

### 4) Persistent Context + Managed Memory

- **Standalone:** strong session context, but long-term project decisions are easy to lose across runs.
- **Clogem:** persists stack/constraints/decisions in `memory.json`, with pruning/summarization to keep context focused instead of unbounded growth.

### 5) Self-Correcting Validation Loop

- **Standalone:** you usually run tests/lint manually and paste failures back.
- **Clogem:** can run detected checks in sandbox/Docker and feed failures back into an automatic correction pass.

### Quick Comparison


| Dimension          | Standalone CLIs (`gemini`, `codex`) | Clogem                                         |
| ------------------ | ----------------------------------- | --------------------------------------------- |
| Model usage        | Single-provider, direct             | Multi-provider orchestration                  |
| Review process     | Human-only review                   | Cross-model peer review (`Codex <-> Gemini`)  |
| Context continuity | Mostly session-scoped               | Persistent summarized project memory          |
| Validation         | Manual test/lint loop               | Auto-sandboxed validation + retry             |
| Primary strength   | Speed, one-off tasks                | Quality, correctness, multi-file project work |


### Practical Guidance

- Use **standalone CLIs** for quick scripts, short Q&A, and small one-file changes.
- Use **Clogem** for feature builds, refactors, architecture work, and tasks where you want independent review plus automated verification.

---

## Project Structure

```
ai_automation/
│
├── clogem/
│   ├── cli.py
│   ├── stitch/
│   │   ├── __init__.py
│   │   ├── adapters.py
│   │   ├── detection.py
│   │   └── prompt_builder.py
│   └── __init__.py
├── tests/
│   └── test_stitch.py
│
├── .ai/
│   ├── CODEX.md
│   ├── GEMINI.md
│   └── STITCH_WEBSITE.md
│
├── setup.py
├── README.md
```

---

## Requirements

| Component | Purpose |
|-----------|---------|
| **Python 3.10+** | Required by Clogem (`pyproject.toml`). Older system Pythons (e.g. macOS 3.9) are not enough. |
| **pipx** | Installs the `clogem` command in an isolated environment (recommended). |
| **Node.js + npm** | Installs the **Codex** and **Gemini** CLIs globally (`@openai/codex`, `@google/gemini-cli`). |
| **Codex CLI** (`codex`) | OpenAI Codex — drafting and orchestration (`codex exec …`). |
| **Gemini CLI** (`gemini`) | Google Gemini — review and summaries (`gemini -p …`). |
| **API keys** (for SDK path) | `OPENAI_API_KEY`, `GEMINI_API_KEY` or `GOOGLE_API_KEY`; optional `ANTHROPIC_API_KEY` for Claude roles. |

On **Windows**, you can use **WSL** (below) or native installs if `python3`, `pipx`, `node`, `codex`, and `gemini` are on your `PATH`.

---

## Full installation (end-to-end)

Do these **in order** the first time you set up the machine.

1. **Remove legacy pipx installs** if you used older names — see [Uninstalling old packages](#uninstalling-old-packages-devai-cogem-and-clogem).
2. **Install Python 3.10+** and **pipx** — [macOS](#macos-macos--macbook), [WSL / Linux](#part-a--wsl-windows-subsystem-for-linux), or your OS package manager.
3. **Clone** this repository and `cd` into the project root.
4. **Install Clogem**: `pipx install -e . --force` (use `--python "$(command -v python3.12)"` on macOS if the default Python is too old).
5. **Install Codex + Gemini CLIs** globally with npm (see [Part B](#part-b--nodejs-and-npm-for-codex--gemini-clis)).
6. **Sign in or set keys**: run `codex` / `gemini` once per upstream docs, and export SDK keys if you use `auto`/`sdk` backends.
7. **Verify**: run `clogem` — the boot sequence checks for Codex and Gemini availability.

**Optional — development dependencies** (running tests from a clone): create a venv and run `pip install -e ".[dev]"` (see `pyproject.toml`). This is separate from the `pipx` install you use day-to-day.

---

## Uninstalling old packages (devai, cogem, and Clogem)

Older iterations of this project used different **pipx** application names. Remove them so you do not have stale commands or wrong packages.

```bash
pipx list
```

Uninstall legacy names (ignore errors if a name was never installed):

```bash
pipx uninstall devai
pipx uninstall cogem
pipx uninstall clogem
```

Then install the current package from a fresh clone (see [Full installation](#full-installation-end-to-end)):

```bash
cd /path/to/Clogem
pipx install -e . --force
```

**Virtualenv copy** (if you used `python -m venv .venv` and `pip install -e .` instead of pipx):

```bash
deactivate  # if the venv is active
rm -rf .venv
```

**Global npm CLIs** (only if you want to remove Codex/Gemini CLIs entirely):

```bash
npm uninstall -g @openai/codex @google/gemini-cli
```

---

## macOS (macOS / MacBook)

Apple’s system Python is often **3.9.x**. Clogem needs **Python ≥ 3.10**, so install a newer Python and point **pipx** at it.

### 1. Install tooling (Homebrew — recommended)

Install [Homebrew](https://brew.sh) if you do not have it, then:

```bash
brew install python@3.12 pipx node
pipx ensurepath
```

Close and reopen **Terminal** (or run `source ~/.zshrc`). Confirm:

```bash
python3.12 --version
pipx --version
node -v
npm -v
```

### 2. Clone and install Clogem with pipx

```bash
cd ~/Projects   # or wherever you keep repos
git clone https://github.com/surya-shreevathsa11/Clogem.git
cd Clogem
pipx install -e . --force --python "$(command -v python3.12)"
```

If `pipx` still picks the wrong interpreter, pass the full path from `brew --prefix python@3.12`, e.g. `$(brew --prefix python@3.12)/bin/python3.12`.

### 3. Install Codex and Gemini CLIs

```bash
npm install -g @openai/codex @google/gemini-cli
codex --version
gemini --help
```

Complete **sign-in** for each tool the first time (or configure API keys per upstream docs).

### 4. API keys for SDK mode (optional but common)

Add to `~/.zshrc` (or `~/.bash_profile`):

```bash
export OPENAI_API_KEY="sk-..."
export GEMINI_API_KEY="..."   # or GOOGLE_API_KEY
# export ANTHROPIC_API_KEY="..."  # only if you map roles to Claude
```

Reload the shell: `source ~/.zshrc`.

### 5. Troubleshooting on Mac

| Problem | What to do |
|---------|------------|
| `requires-python` / version error during `pipx install` | Use `--python` with **python3.10+** (see step 2). |
| `command not found: clogem` after pipx | Run `pipx ensurepath`, restart Terminal, check `echo $PATH`. |
| Live weather/news not grounded | Use Gemini **SDK** (`CLOGEM_GEMINI_BACKEND=auto` or `sdk`), not `cli`; set `GEMINI_API_KEY`. |

---

## Part A — WSL (Windows Subsystem for Linux)

Use this when you develop on **Windows** and want Linux tooling in one place.

### 1. Install WSL

Open **PowerShell as Administrator**:

```powershell
wsl --install
```

Restart the machine if Windows asks you to. Optionally install a specific distro (example: Ubuntu):

```powershell
wsl --install -d Ubuntu
```

### 2. Open your distro

From **PowerShell** or **Start menu**:

```powershell
wsl
```

Or launch **Ubuntu** (or your distro) from the app list. You should get a Linux shell (`bash`).

### 3. Update packages (inside WSL)

```bash
sudo apt update && sudo apt upgrade -y
```

### 4. Install Python and pipx (inside WSL)

```bash
sudo apt install -y python3 python3-pip pipx
pipx ensurepath
```

Reload your shell config:

```bash
source ~/.bashrc
```

---

## Part B — Node.js and npm (for Codex + Gemini CLIs)

Both official CLIs are published on **npm** and are typically installed **globally**.

### Install Node.js (inside WSL)

Pick one approach:

**Option 1 — distro packages (simple)**

```bash
sudo apt install -y nodejs npm
```

**Option 2 — current LTS (recommended for latest Node)**

Use the [NodeSource setup](https://github.com/nodesource/distributions) or [nvm](https://github.com/nvm-sh/nvm) for your distro, then confirm:

```bash
node -v
npm -v
```

---

## Part C — Codex CLI (npm)

Official package: `**@openai/codex**`. See [openai/codex](https://github.com/openai/codex) and [Codex documentation](https://developers.openai.com/codex).

### Install globally

```bash
sudo npm install -g @openai/codex
```

### Verify

```bash
codex --version
```

Run `codex` once and complete sign-in (e.g. ChatGPT or API key) per upstream docs.

---

## Part D — Gemini CLI (npm)

Official package: `**@google/gemini-cli**`. See [google-gemini/gemini-cli](https://github.com/google-gemini/gemini-cli) and [Gemini CLI docs](https://geminicli.com/docs/).

### Install globally

```bash
npm install -g @google/gemini-cli
```

Optional tags (from upstream):

```bash
npm install -g @google/gemini-cli@latest
```

### Run without a global install (npx)

```bash
npx @google/gemini-cli --help
```

`clogem` expects the `gemini` command on `PATH`, so prefer a global install for daily use.

### Verify

```bash
gemini --help
gemini -p "hello"
```

Complete **Sign in with Google** or set `**GEMINI_API_KEY`** as described in the [authentication guide](https://github.com/google-gemini/gemini-cli/blob/main/README.md#-authentication-options).

---

## Part E — This project (`clogem`)

You should already have followed [Full installation](#full-installation-end-to-end) and [Uninstalling old packages](#uninstalling-old-packages-devai-cogem-and-clogem). This section is the short version.

### 1. Get the code

```bash
git clone https://github.com/surya-shreevathsa11/Clogem.git
cd Clogem
```

Use your fork URL if applicable.

### 2. Install the `clogem` command (pipx, from repo root)

```bash
pipx install -e . --force
```

On **macOS**, if the default Python is too old:

```bash
pipx install -e . --force --python "$(command -v python3.12)"
```

### 3. Run

```bash
clogem
```

On first launch, Clogem creates **`memory.json`** in the project (git-ignored) for saved stack notes and context.

### 4. Update after `git pull`

```bash
pipx install -e . --force
```

---

## Usage

### General pattern

```
clogem
>>> your task
```

### Examples

Script:

```
>>> write python script to rename files in a folder
```

Web page:

```
>>> create landing page with navbar and hero section
```

Backend:

```
>>> build node API with login route and JWT authentication
```

---

## Workflow

1. Codex generates code
2. Gemini reviews independently
3. Codex improves based on review
4. System outputs:
  - improved code
  - diff
  - summary

---

## Project Mode

If the task includes multiple files:

- The system creates files automatically  
- Open HTML in the browser from Windows, from WSL you can use:

```bash
explorer.exe index.html
```

---

## Important Rules

- Describe what you want, not necessarily how to code it  
- Avoid mixing manual coding with the automated workflow when you want the full loop  
- Use separate folders per project when it helps

---

## Philosophy

This is not a generic chat assistant.

It is a controlled development system where:

- generation is separate from validation  
- review is independent  
- improvements are traceable

---

## Updating the tool

After `git pull`, reinstall the pipx app from the repo root (same as [Part E — step 4](#part-e--this-project-clogem)):

```bash
pipx install -e . --force
```

---

## CLI options (optional)

### LLM models and role/provider mapping

Clogem supports three providers (`codex`, `gemini`, `claude`) and five roles:
`orchestrator`, `planner`, `coder`, `reviewer`, `summariser`.

Default role map:

- `orchestrator=codex`
- `planner=codex`
- `coder=codex`
- `reviewer=gemini`
- `summariser=gemini`

You can override role mapping with:

- `--role-provider ROLE=PROVIDER` (repeatable)
- `CLOGEM_ROLE_PROVIDER_MAP` (comma-separated `role=provider` pairs)

Model overrides:


| Provider         | Model source                               | Used for                                           |
| ---------------- | ------------------------------------------ | -------------------------------------------------- |
| **Codex**        | `--codex-model` / `CLOGEM_CODEX_MODEL`      | Any role mapped to `codex`                         |
| **Gemini**       | `--gemini-model` / `CLOGEM_GEMINI_MODEL`    | Any role mapped to `gemini`                        |
| **Claude (SDK)** | `--claude-model` / `CLOGEM_CLAUDE_MODEL`    | Any role mapped to `claude` (SDK-only, no CLI fallback) |


- **If you do not set a model** for a backend, clogem **does not pass `-m`** for that CLI, so **that tool’s default model** is used (same as running `codex` / `gemini` without `-m`).
- **Valid `MODEL_ID` strings** depend on your installed CLI version and account (OpenAI, Google, etc.). Examples people use include `o3`, `gemini-2.5-pro`, `gemini-2.5-flash`; exact names are defined by each CLI — use `codex exec --help` and `gemini --help` on your machine.

```bash
clogem --codex-model o3 --gemini-model gemini-2.5-pro
clogem --role-provider coder=claude --role-provider reviewer=gemini --claude-model claude-sonnet-4-6
```

Only one backend:

```bash
clogem --gemini-model gemini-2.5-flash
clogem --codex-model o3
```

If a flag is omitted, you can still set defaults with the environment variables in the table below.

### SDK-backed model calls (OpenAI + Google GenAI)

Clogem supports SDK backends for OpenAI, Google GenAI, and Anthropic.

- `CLOGEM_CODEX_BACKEND=auto|sdk|cli` (default `auto`)
- `CLOGEM_GEMINI_BACKEND=auto|sdk|cli` (default `auto`)
- `CLOGEM_GEMINI_REALTIME=1` (default on): questions that look like **live weather or news** are answered with **Gemini + Google Search grounding** (SDK path only), using your machine’s **local date/time** so “today” matches your clock. Set `0` to disable. Grounding needs a Gemini API key (`GEMINI_API_KEY` / `GOOGLE_API_KEY`) and billing per Google’s pricing; use `gemini-2.5-flash` or another [supported model](https://ai.google.dev/gemini-api/docs/google-search).
- `CLOGEM_CLAUDE_BACKEND=sdk` (Claude is SDK-only)
- `CLOGEM_CODEX_SDK_MODEL` (default `gpt-4.1-mini`)
- `CLOGEM_GEMINI_SDK_MODEL` (default `gemini-2.5-flash`)
- `CLOGEM_CLAUDE_SDK_MODEL` (default `claude-sonnet-4-6`)

In `auto` mode, Clogem tries SDK first and falls back to CLI if unavailable.
For SDK mode you need:

- OpenAI: `OPENAI_API_KEY`
- Google GenAI: `GEMINI_API_KEY` or `GOOGLE_API_KEY`
- Anthropic: `ANTHROPIC_API_KEY`

Router secondary intent classifier:

- `CLOGEM_SECONDARY_INTENT_LLM=1` (default on)
- `CLOGEM_ROUTER_CLASSIFIER_MODEL` (default `gemini-2.5-flash-lite`)

Async LLM execution path:

- `CLOGEM_ASYNC_LLM=1` (default on): SDK calls run through async wrappers (`asyncio` + thread offload).

### In-session commands

On an interactive terminal, the main task prompt uses **prompt-style completion**: type `/` or `@` and use **Tab** (or keep typing) to open a **two-column** menu (command/path + short description) with a **dark** theme. For colors closest to the Codex-style blue/grey look, use **Windows Terminal** or another **true-color** terminal. Set `**CLOGEM_NO_TRUE_COLOR=1`** if the menu colors look wrong on legacy consoles.

For a full slash-command reference, see [`help.md`](help.md).

While Clogem is running, you can change models without restarting:


| Command                                    | Meaning                                                                       |
| ------------------------------------------ | ----------------------------------------------------------------------------- |
| `/codex/model`                             | Show Codex LLM (`codex exec -m`), this session, and startup default           |
| `/codex/model <MODEL_ID>`                  | Use that ID for **all Codex** calls this session                              |
| `/codex/model reset`                       | Restore Codex model from `--codex-model` / `CLOGEM_CODEX_MODEL`                |
| `/gemini/model`                            | Show Gemini LLM (`gemini -m`), this session, and startup default              |
| `/gemini/model <MODEL_ID>`                 | Use that ID for **all Gemini** calls this session                             |
| `/gemini/model reset`                      | Restore Gemini model from `--gemini-model` / `CLOGEM_GEMINI_MODEL`             |
| `/claude/model`                            | Show Claude LLM (SDK), this session, and startup default                      |
| `/claude/model <MODEL_ID>`                 | Use that ID for **all Claude SDK** calls this session                         |
| `/claude/model reset`                      | Restore Claude model from `--claude-model` / `CLOGEM_CLAUDE_MODEL`             |
| `/roles`                                   | Show active role-to-provider mapping                                           |
| `/roles/<role>/<provider>`                 | Set role provider in-session (example: `/roles/orchestrator/claude`)          |
| `/repo/info`                               | Show repo info (git root, branch, last commit, status)                        |
| `/test`                                    | Run project tests (best-effort; Python or Node)                               |
| `/lint`                                    | Run project lint (best-effort; Python or Node)                                |
| `/run <cmd>`                               | Run a local command (requires permission; allowlist enforced)                 |
| `/pdf`                                     | Generate a PDF from provided text (plain-text layout; uses `reportlab`)       |
| `/github/info <url or owner/repo>`         | Show public GitHub repository metadata (description, stars, language, branch) |
| `/github/clone <url or owner/repo> [dest]` | Clone repository into local folder (`dest` optional)                          |
| `/mcp/plugins`                             | List configured MCP plugins                                                   |
| `/mcp/tools <plugin>`                      | List tools published by a plugin                                              |
| `/mcp/call <plugin> <tool> [json-args]`    | Invoke an MCP tool with JSON arguments                                        |
| `/rag/search <query>`                      | Run semantic search over the local full-repo vector index                     |


---

## Automated Validation Loop (Execution):

When you use `/build`, clogem now attempts to "close the loop" by running the detected repo checks and feeding failures back into Codex for a second pass.

- It runs the detected test command (Python: `python -m pytest`, Node: `npm test`).
- It runs the detected lint command when available (Python: `ruff` or `flake8`; Node: `npm run lint`/`npm run eslint`).
- If `tsconfig.json` exists in a Node repo, it also runs `npx tsc --noEmit` (best-effort).
- Safety: it executes these checks inside a temporary copy of your repo to reduce the risk of host file deletion.
- The loop stops after `CLOGEM_VALIDATION_MAX_ATTEMPTS` (default `2`) attempts.

### Docker-Preferred, Fallback to Sandbox

By default, validation uses the filesystem sandbox (fast, zero Docker setup).

If you want Docker validation (preferred when available), enable it explicitly:

- CLI: `clogem --validation-docker`
- Env: `CLOGEM_VALIDATION_DOCKER=yes`

Strict mode:

- If `CLOGEM_STRICT_SANDBOX=1` and Docker is not available, validation **fails** (strict mode is a hard gate).

Docker base images:

- Python: `python:3.12-slim` (override with `CLOGEM_DOCKER_PY_IMAGE`)
- Node: `node:20-slim` (override with `CLOGEM_DOCKER_NODE_IMAGE`)

### Faster Filesystem Sandbox

To avoid copying huge projects, the sandbox copies **only git-tracked files** (falls back to a conservative full copy if the repo is not a git checkout).

### Session directives (task mode)

Prefix the **first line** of your message with one of these. They stack with `@` mentions (attachments load into the build context when you end up in BUILD).


| Command    | Meaning                                                                                     |
| ---------- | ------------------------------------------------------------------------------------------- |
| `/build …` | Force the full implementation pipeline (skips the BUILD/CHAT router).                       |
| `/plan …`  | Planning / design emphasis; the router still chooses BUILD vs CHAT unless you use `/build`. |
| `/debug …` | Debugging emphasis (root cause, repro, targeted fixes).                                     |
| `/agent …` | Autonomous, multi-step coding style within the scoped task.                                 |
| `/ask …`   | Pure Q&A (skips the router and the Codex+Gemini build loop for this turn).                  |
| `/research …` | Research-style answer (skips the build loop). Without `@` files, uses **Gemini + Google Search grounding** when the SDK is available; with `@` paths, answers only from inlined sources (no web). |


### @ file and folder mentions

In your task text you can reference paths so their contents are included in **BUILD** prompts (Codex + Gemini):

- `@relative/path/to/file.py` — file contents (UTF-8 text; very large files are truncated)
- `@docs/spec.pdf` — PDF text extraction (best effort; page-limited)
- `@src` or `@docs/` — directory tree listing (depth and entry limits apply)
- `@"path with spaces/file.txt"` — use double quotes inside the `@…` form for spaces

Symbol mentions (ctags/universal-ctags; best-effort):

- `@MyClassName` or `@my_function` — if `universal-ctags`/`ctags` is available on PATH, Clogem will inline a short snippet around the symbol definition (instead of requiring an explicit `@path/to/file`).
You can disable this with `CLOGEM_SYMBOL_INDEX=0`.

Paths must resolve under the **repo root**, your **current working directory**, or `**CLOGEM_CODEX_WORKDIR`**. Anything else is skipped with a note in the attachment block.

Optional limits: `CLOGEM_AT_MAX_FILE_BYTES` (default `400000`), `CLOGEM_AT_MAX_TOTAL_CHARS` (default `120000`) for the whole attachment block.

`@` references are **not** inlined for pure **CHAT** routing (you’ll see a short notice).

### Google Stitch (UI-heavy frontend tasks)

For **frontend-first** builds (websites, landing pages, dashboards, HTML/CSS/JS UIs), clogem can run a **Stitch stage** *before* the usual Codex draft → Gemini review → Codex improve loop:

1. **Detect** a UI-heavy task from your prompt (heuristic).
2. **Try adapters** in order: optional CLI → optional HTTP → optional browser stub (off by default) → **manual handoff**.
3. **Fold** any Stitch output (or your export) into the Codex/Gemini prompts, plus strict rules from `.ai/STITCH_WEBSITE.md`.
4. **Non-frontend** tasks are unchanged.

**Prerequisite questions first:** If you ask how to do something *before* a build (e.g. *“build a site, but before that tell me how to connect Stitch via MCP”*), clogem treats that turn as **conversation first** — no build pipeline, no Stitch stage. Use `**/build`** on a later turn when you only want implementation.

**Disable** the Stitch stage entirely: `CLOGEM_STITCH=0` or `clogem --no-stitch`.

**Manual mode** (default when no adapter succeeds): clogem prints a ready-to-paste **Stitch prompt**, then asks for your **exported HTML/CSS** (paste or `@path`). Non-interactive stdin skips the paste step; use `CLOGEM_STITCH_CLI` or `CLOGEM_STITCH_HTTP_URL` instead.
When available, clogem also copies the generated Stitch prompt to your clipboard automatically (uses `pyperclip` if installed, else tkinter fallback).

### Multimodal UI Validation (Vision Pass)

For frontend-heavy turns, clogem can run a visual validation stage after files are written:

1. Capture a headless screenshot (Playwright; static `index.html` style outputs).
2. Send screenshot + task intent to Gemini Vision for layout review.
3. Feed visual findings into a final Codex fix pass.

Env controls:

- `CLOGEM_VISUAL_REVIEW=1` (default on)
- `CLOGEM_VISUAL_REVIEW_MODEL` (default `gemini-2.5-pro`)

Requirements for screenshot capture:

- `pip install playwright`
- `playwright install chromium`

#### Stitch MCP (`stitch-mcp` on npm)

The community **stitch-mcp** package is an MCP **server** that talks to Google’s Stitch API (with `gcloud` auth). Clogem acts as a minimal MCP **client** over stdio and calls the generate tool automatically for frontend tasks (unless you disable MCP):

1. Install **Google Cloud SDK**, run `gcloud auth application-default login`, and set `**GOOGLE_CLOUD_PROJECT`** (see the [stitch-mcp README](https://www.npmjs.com/package/stitch-mcp)).
2. Install **Node.js** so `**npx`** is available.
3. (Optional) Override defaults if needed: `CLOGEM_STITCH_MCP_CMD=npx` and `CLOGEM_STITCH_MCP_ARGS=-y stitch-mcp`.
4. Run a frontend-style task in clogem; the adapter chain will try **CLI → MCP → HTTP → manual**.
5. To disable MCP explicitly: `CLOGEM_STITCH_MCP=0`.

If MCP fails (auth, API, or tool schema), clogem **falls back** to manual export as before. Tool name defaults to `generate_screen_from_text`; override with `CLOGEM_STITCH_MCP_TOOL` if your server exposes a different name.

There is **no guaranteed public Stitch API** in clogem: integration is **pluggable** via env vars (see table below). Validity of any HTTP/CLI tool is **your** responsibility.

---

## Deep MCP Plugin Integration

Beyond Stitch, Clogem can connect to external MCP tool servers (Jira, Sentry, Datadog, DB schema, custom tools).

### Plugin configuration

Built-in aliases (set command + optional args):

- `CLOGEM_MCP_JIRA_CMD`, `CLOGEM_MCP_JIRA_ARGS`
- `CLOGEM_MCP_SENTRY_CMD`, `CLOGEM_MCP_SENTRY_ARGS`
- `CLOGEM_MCP_DATADOG_CMD`, `CLOGEM_MCP_DATADOG_ARGS`
- `CLOGEM_MCP_DBSCHEMA_CMD`, `CLOGEM_MCP_DBSCHEMA_ARGS`

Custom registry JSON:

- `CLOGEM_MCP_PLUGINS_JSON`

Example:

```json
{
  "jira": { "cmd": "npx", "args": "-y your-jira-mcp", "timeout_sec": 60 },
  "sentry": { "cmd": "npx", "args": "-y your-sentry-mcp" }
}
```

### Plugin command flow

1. `/mcp/plugins`
2. `/mcp/tools jira`
3. `/mcp/call jira get_ticket {"id":"402"}`

This enables workflows like: inspect a Jira ticket, fetch Sentry traces, read DB schema context, then implement + validate fixes in one Clogem session.

---

## Deep Semantic Context (Full-Repo RAG)

Clogem supports local vector retrieval to find related logic beyond exact symbols/imports.

- Backend: LanceDB + sentence-transformers (local embeddings)
- Scope: full repo source traversal (configurable extensions)
- Retrieval: semantic nearest-neighbor chunks injected into build context
- Fallback: if vector deps are unavailable, Clogem falls back to structural repo context

### What this helps with

- "Where else do we handle authentication?"
- "Show similar styling/component patterns."
- "Find related logic that does not share the same symbol names."

### RAG commands

- `/rag/search <query>`: inspect semantic matches directly

### Index lifecycle

- Index is stored under `.clogem/vector_db`
- Clogem maintains a file-hash manifest and only rebuilds the index when tracked source content changes (or when forced)

### Controls

- `CLOGEM_VECTOR_RAG=1` enable vector retrieval for build context
- `CLOGEM_VECTOR_REBUILD=1` force rebuild
- `CLOGEM_VECTOR_TOP_K` number of semantic matches
- `CLOGEM_VECTOR_CHUNK_CHARS` chunk size

Install optional deps:

```bash
pip install ".[vector]"
```

---

## Environment variables (optional)


| Variable                            | Purpose                                                                                                                                          |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `CLOGEM_AUTO_PERMISSIONS`            | `yes` / `no` — skip the interactive prompt for Codex `--full-auto` and Gemini `--yolo`                                                           |
| `CLOGEM_ALLOW_LOCAL_COMMANDS`        | `yes` / `no` — allow local command execution for `/run`, `/test`, `/lint`, `/github/clone`, and build-time artifact auto-run                     |
| `CLOGEM_RUN_POLICY`                  | strict by default; set `relaxed` to allow legacy broad `/run` command behavior                                                                   |
| `CLOGEM_CODEX_WORKDIR`               | Absolute path passed to Codex `-C` (workspace root)                                                                                              |
| `CLOGEM_CODEX_MODEL`                 | Default Codex LLM ID when `--codex-model` is not passed                                                                                          |
| `CLOGEM_GEMINI_MODEL`                | Default Gemini LLM ID when `--gemini-model` is not passed                                                                                        |
| `CLOGEM_CLAUDE_MODEL`                | Default Claude LLM ID when `--claude-model` is not passed                                                                                        |
| `CLOGEM_ROLE_PROVIDER_MAP`           | Role mapping override: comma-separated `role=provider` pairs (e.g. `coder=claude,reviewer=gemini`)                                             |
| `CLOGEM_CODEX_BACKEND`               | Backend mode for codex provider: `auto|sdk|cli`                                                                                                  |
| `CLOGEM_GEMINI_BACKEND`              | Backend mode for gemini provider: `auto|sdk|cli`                                                                                                 |
| `CLOGEM_CLAUDE_BACKEND`              | Backend mode for claude provider: `sdk`                                                                                                          |
| `CLOGEM_CODEX_SDK_MODEL`             | SDK model used by codex provider when using OpenAI SDK                                                                                           |
| `CLOGEM_GEMINI_SDK_MODEL`            | SDK model used by gemini provider when using Google GenAI SDK                                                                                    |
| `CLOGEM_CLAUDE_SDK_MODEL`            | SDK model used by claude provider when using Anthropic SDK                                                                                       |
| `CLOGEM_SUBPROCESS_TIMEOUT_SEC`      | Integer seconds; abort a stuck `codex` / `gemini` subprocess after this time                                                                     |
| `CLOGEM_STREAM_DIFFS`                | `1`/`0` — stream a live unified diff during Codex improvements (opt-in; only when stdout is a TTY)                                               |
| `CLOGEM_VALIDATION_DOCKER`           | `yes` / `no` — prefer Docker-based validation backend (tests/lint/typecheck). See `--validation-docker`                                          |
| `CLOGEM_STRICT_SANDBOX`              | `1` / `0` — when `1`, require Docker for validation; if Docker is missing, validation fails                                                        |
| `CLOGEM_DOCKER_PY_IMAGE`             | Docker image for Python validation (default `python:3.12-slim`)                                                                                  |
| `CLOGEM_DOCKER_NODE_IMAGE`           | Docker image for Node validation (default `node:20-slim`)                                                                                        |
| `CLOGEM_VALIDATION_MAX_ATTEMPTS`     | Max automated validation iterations for `/build` (default `2`)                                                                                   |
| `CLOGEM_TYPECHECK_PYRIGHT`           | `1`/`0` — enable pyright type checking for Python projects (if `pyright` is on PATH). (best-effort; default `1`)                                 |
| `CLOGEM_AT_MAX_FILE_BYTES`           | Max bytes read per `@` file (default `400000`)                                                                                                   |
| `CLOGEM_AT_MAX_TOTAL_CHARS`          | Max total characters for all `@` attachments in one turn (default `120000`)                                                                      |
| `CLOGEM_AT_MAX_PDF_PAGES`            | Max pages extracted from a PDF `@` mention (default `30`)                                                                                        |
| `CLOGEM_SYMBOL_INDEX`                | `1` (default) / `0` — enable ctags-based symbol resolution for `@MyClassName` mentions (best-effort; requires `universal-ctags`/`ctags` on PATH) |
| `CLOGEM_SYMBOL_DEP_CONTEXT`          | `1` (default) / `0` — enable symbol-aware dependency injection for BUILD prompts based on `@some_file.py` imports                                |
| `CLOGEM_SYMBOL_DEP_MAX_SYMBOLS`      | Max imported symbols to resolve/inject per build turn (default `20`)                                                                             |
| `CLOGEM_SYMBOL_DEP_MAX_CHARS`        | Cap for the injected dependency context text (default `4000`)                                                                                    |
| `CLOGEM_SYMBOL_COMPLETIONS`          | `1`/`0` — include `@MySymbol` completions in the `@` menu (best-effort; requires ctags/universal-ctags for real tags)                            |
| `CLOGEM_FUZZY_AT_COMPLETIONS`        | `1`/`0` — enable fuzzy fallback for `@` path completion when prefix matches return nothing                                                       |
| `CLOGEM_FUZZY_SYMBOL_COMPLETIONS`    | `1`/`0` — enable fuzzy fallback for `@` symbol completion when prefix matches return nothing                                                     |
| `CLOGEM_AUTO_REPO_CONTEXT`           | `1`/`0` — auto-retrieve relevant repo snippets for BUILD prompts (keyword + dependency graph)                                                    |
| `CLOGEM_AUTO_REPO_CONTEXT_MAX_CHARS` | Cap for injected auto repo context text (default `8000`)                                                                                         |
| `CLOGEM_AUTO_REPO_CONTEXT_MAX_FILES` | Max files to inject (default `6`)                                                                                                                |
| `CLOGEM_AUTO_REPO_CONTEXT_MAX_DEPTH` | Dependency expansion depth (default `2`)                                                                                                         |
| `CLOGEM_VECTOR_RAG`                  | `1`/`0` — enable LanceDB semantic retrieval for BUILD prompts (best-effort; requires extra deps)                                                 |
| `CLOGEM_VECTOR_REBUILD`              | `1`/`0` — rebuild the local vector index (default `0`)                                                                                           |
| `CLOGEM_VECTOR_TOP_K`                | Number of semantic matches to inject (default `8`)                                                                                               |
| `CLOGEM_VECTOR_CHUNK_CHARS`          | Chunk size for embedding (default `2500`)                                                                                                        |
| `CLOGEM_STITCH`                      | `1` (default) / `0` — enable or disable the Stitch stage for UI-heavy tasks                                                                      |
| `CLOGEM_STITCH_CLI`                  | Optional: executable for a Stitch adapter (stdin sends the prompt unless `CLOGEM_STITCH_CLI_STDIN=0` + temp file)                                 |
| `CLOGEM_STITCH_CLI_ARGS`             | Extra argv appended after the CLI command                                                                                                        |
| `CLOGEM_STITCH_CLI_STDIN`            | `1` (default) / `0` — pass prompt on stdin vs temp file path as last arg                                                                         |
| `CLOGEM_STITCH_HTTP_URL`             | Optional: HTTP endpoint for JSON `{ "prompt": "..." }` (customize body with `CLOGEM_STITCH_HTTP_BODY`)                                            |
| `CLOGEM_STITCH_HTTP_TOKEN`           | Optional `Authorization: Bearer` for HTTP adapter                                                                                                |
| `CLOGEM_STITCH_TIMEOUT_SEC`          | Timeout for CLI/HTTP Stitch attempts (default `300`)                                                                                             |
| `CLOGEM_STITCH_BROWSER`              | `1` to acknowledge browser automation (not implemented; kept off by default)                                                                     |
| `CLOGEM_STITCH_MCP`                  | MCP stdio client toggle for `npx stitch-mcp` (default: **enabled**; set `0`/`false` to disable)                                                  |
| `CLOGEM_STITCH_MCP_CMD`              | Command to launch MCP server (default `npx`)                                                                                                     |
| `CLOGEM_STITCH_MCP_ARGS`             | Args for the server (default `-y stitch-mcp`)                                                                                                    |
| `CLOGEM_STITCH_MCP_TOOL`             | MCP tool name (default `generate_screen_from_text`)                                                                                              |
| `CLOGEM_STITCH_MCP_PROMPT_KEY`       | JSON argument key for the prompt (default `prompt`)                                                                                              |
| `CLOGEM_STITCH_MCP_TOOL_ARGS_JSON`   | Optional extra JSON object merged into tool `arguments`                                                                                          |
| `CLOGEM_STITCH_MCP_TIMEOUT_SEC`      | Max seconds for the MCP round-trip (default `300`)                                                                                               |
| `CLOGEM_MCP_JIRA_CMD`                | MCP server command for Jira plugin alias                                                                                                         |
| `CLOGEM_MCP_JIRA_ARGS`               | Args for Jira MCP server command                                                                                                                 |
| `CLOGEM_MCP_SENTRY_CMD`              | MCP server command for Sentry plugin alias                                                                                                       |
| `CLOGEM_MCP_SENTRY_ARGS`             | Args for Sentry MCP server command                                                                                                               |
| `CLOGEM_MCP_DATADOG_CMD`             | MCP server command for Datadog plugin alias                                                                                                      |
| `CLOGEM_MCP_DATADOG_ARGS`            | Args for Datadog MCP server command                                                                                                              |
| `CLOGEM_MCP_DBSCHEMA_CMD`            | MCP server command for DB schema plugin alias                                                                                                    |
| `CLOGEM_MCP_DBSCHEMA_ARGS`           | Args for DB schema MCP server command                                                                                                            |
| `CLOGEM_MCP_PLUGINS_JSON`            | JSON registry for arbitrary MCP plugins (`name -> {cmd,args,env,timeout_sec}`)                                                                   |
| `CLOGEM_MCP_TIMEOUT_SEC`             | Default timeout for MCP plugin alias servers (default `60`)                                                                                      |
| `CLOGEM_DEBUG`                       | `1`/`0` — enable debug logs for fallback/error paths that normally degrade gracefully                                                            |


---

## Quick reference (copy-paste)

**Remove old pipx apps:** `pipx uninstall devai` · `pipx uninstall cogem` · `pipx uninstall clogem` (ignore errors if missing)  

**macOS (Homebrew):** `brew install python@3.12 pipx node` · `pipx ensurepath` · `pipx install -e . --force --python "$(command -v python3.12)"`  

**WSL (PowerShell, admin):** `wsl --install`  

**WSL shell:** `sudo apt update && sudo apt upgrade -y`  

**Python + pipx (WSL/Linux):** `sudo apt install -y python3 python3-pip pipx && pipx ensurepath`  

**Codex + Gemini CLIs:** `npm install -g @openai/codex @google/gemini-cli`  

**Clogem (any OS, from repo root):** `pipx install -e . --force` then `clogem`  

**Keys (SDK):** `export OPENAI_API_KEY=...` · `export GEMINI_API_KEY=...` (or `GOOGLE_API_KEY`)  
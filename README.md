# Cogem (Codex + Gemini Workflow)

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

---

## Project Structure

```
ai_automation/
│
├── cogem/
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
| **WSL** (Windows) | Recommended environment on Windows; use a Linux distro (e.g. Ubuntu) for Node + Python + CLIs |
| **Python 3** | Runs `cogem` (via pipx) |
| **pipx** | Isolated install of the `cogem` command |
| **Node.js + npm** | Installs **Codex CLI** and **Gemini CLI** globally |
| **Codex CLI** (`codex`) | OpenAI Codex — generation (`codex exec …`) |
| **Gemini CLI** (`gemini`) | Google Gemini — review (`gemini -p …`) |

On Windows you can run `cogem` without WSL if `codex` and `gemini` are already on your `PATH` (same npm global install as below).

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

Official package: **`@openai/codex`**. See [openai/codex](https://github.com/openai/codex) and [Codex documentation](https://developers.openai.com/codex).

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

Official package: **`@google/gemini-cli`**. See [google-gemini/gemini-cli](https://github.com/google-gemini/gemini-cli) and [Gemini CLI docs](https://geminicli.com/docs/).

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

`cogem` expects the `gemini` command on `PATH`, so prefer a global install for daily use.

### Verify

```bash
gemini --help
gemini -p "hello"
```

Complete **Sign in with Google** or set **`GEMINI_API_KEY`** as described in the [authentication guide](https://github.com/google-gemini/gemini-cli/blob/main/README.md#-authentication-options).

---

## Part E — This project (cogem)

### 1. Get the code

```bash
cd ~
git clone https://github.com/surya-shreevathsa11/CoGem.git
cd <CoGem>
```

Or clone your repo URL and `cd` into it.

### 2. Install the `cogem` command

If you still have the old `devai` package from an earlier install:

```bash
pipx uninstall devai
```

Then:

```bash
pipx install -e .
```

### 3. Run

```bash
cogem
```

On first launch, **cogem** creates a **`memory.json`** file next to the project (it is git-ignored). Each clone or machine gets its own file for saved stack notes and context—nothing personal is shipped with the repo.

---

## Usage

### General pattern

```
cogem
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

After pulling changes:

```bash
pipx install -e . --force
```

---

## CLI options (optional)

### LLM models (Codex vs Gemini)

**Yes — you choose LLMs separately.** Cogem wires two different CLIs, each with its own `-m` model flag:

| Role in Cogem | CLI flag | Used for |
|----------------|----------|----------|
| **Codex LLM** | `codex exec -m MODEL_ID` | Drafting code, Codex “improve” pass |
| **Gemini LLM** | `gemini -m MODEL_ID` | Review step, final summary |

- **If you do not set a model** for a backend, cogem **does not pass `-m`** for that CLI, so **that tool’s default model** is used (same as running `codex` / `gemini` without `-m`).
- **Valid `MODEL_ID` strings** depend on your installed CLI version and account (OpenAI, Google, Anthropic, etc.). Examples people use include `o3`, `gemini-2.5-pro`, `gemini-2.5-flash`; exact names are defined by each CLI — use `codex exec --help` and `gemini --help` on your machine.

```bash
cogem --codex-model o3 --gemini-model gemini-2.5-pro
```

Only one backend:

```bash
cogem --gemini-model gemini-2.5-flash
cogem --codex-model o3
```

If a flag is omitted, you can still set defaults with the environment variables in the table below.

### In-session commands

On an interactive terminal, the main task prompt uses **prompt-style completion**: type `/` or `@` and use **Tab** (or keep typing) to open a **two-column** menu (command/path + short description) with a **dark** theme. For colors closest to the Codex-style blue/grey look, use **Windows Terminal** or another **true-color** terminal. Set **`COGEM_NO_TRUE_COLOR=1`** if the menu colors look wrong on legacy consoles.

While Cogem is running, you can change models without restarting:

| Command | Meaning |
|---------|---------|
| `/codex/model` | Show Codex LLM (`codex exec -m`), this session, and startup default |
| `/codex/model <MODEL_ID>` | Use that ID for **all Codex** calls this session |
| `/codex/model reset` | Restore Codex model from `--codex-model` / `COGEM_CODEX_MODEL` |
| `/gemini/model` | Show Gemini LLM (`gemini -m`), this session, and startup default |
| `/gemini/model <MODEL_ID>` | Use that ID for **all Gemini** calls this session |
| `/gemini/model reset` | Restore Gemini model from `--gemini-model` / `COGEM_GEMINI_MODEL` |
| `/repo/info` | Show repo info (git root, branch, last commit, status) |
| `/test` | Run project tests (best-effort; Python or Node) |
| `/lint` | Run project lint (best-effort; Python or Node) |
| `/run <cmd>` | Run a local command (requires permission; allowlist enforced) |
| `/pdf` | Generate a PDF from provided text (plain-text layout; uses `reportlab`) |
| `/github/info <url or owner/repo>` | Show public GitHub repository metadata (description, stars, language, branch) |
| `/github/clone <url or owner/repo> [dest]` | Clone repository into local folder (`dest` optional) |

---
## Automated Validation Loop (Execution)

When you use `/build`, cogem now attempts to "close the loop" by running the detected repo checks and feeding failures back into Codex for a second pass.

- It runs the detected test command (Python: `python -m pytest`, Node: `npm test`).
- It runs the detected lint command when available (Python: `ruff` or `flake8`; Node: `npm run lint`/`npm run eslint`).
- If `tsconfig.json` exists in a Node repo, it also runs `npx tsc --noEmit` (best-effort).
- Safety: it executes these checks inside a temporary copy of your repo to reduce the risk of host file deletion.
- The loop stops after `COGEM_VALIDATION_MAX_ATTEMPTS` (default `2`) attempts.

### Docker-Preferred, Fallback to Sandbox

By default, validation uses the filesystem sandbox (fast, zero Docker setup).

If you want Docker validation (preferred when available), enable it explicitly:
- CLI: `cogem --validation-docker`
- Env: `COGEM_VALIDATION_DOCKER=yes`

Strict mode:
- If `COGEM_STRICT_SANDBOX=1` and Docker is not available, cogem **skips validation** (so you keep zero-friction behavior).

Docker base images:
- Python: `python:3.12-slim` (override with `COGEM_DOCKER_PY_IMAGE`)
- Node: `node:20-slim` (override with `COGEM_DOCKER_NODE_IMAGE`)

### Faster Filesystem Sandbox

To avoid copying huge projects, the sandbox copies **only git-tracked files** (falls back to a conservative full copy if the repo is not a git checkout).

### Session directives (task mode)

Prefix the **first line** of your message with one of these. They stack with `@` mentions (attachments load into the build context when you end up in BUILD).

| Command | Meaning |
|---------|---------|
| `/build …` | Force the full implementation pipeline (skips the BUILD/CHAT router). |
| `/plan …` | Planning / design emphasis; the router still chooses BUILD vs CHAT unless you use `/build`. |
| `/debug …` | Debugging emphasis (root cause, repro, targeted fixes). |
| `/agent …` | Autonomous, multi-step coding style within the scoped task. |
| `/ask …` | Pure Q&A (skips the router and the Codex+Gemini build loop for this turn). |

### @ file and folder mentions

In your task text you can reference paths so their contents are included in **BUILD** prompts (Codex + Gemini):

- `@relative/path/to/file.py` — file contents (UTF-8 text; very large files are truncated)
- `@docs/spec.pdf` — PDF text extraction (best effort; page-limited)
- `@src` or `@docs/` — directory tree listing (depth and entry limits apply)
- `@"path with spaces/file.txt"` — use double quotes inside the `@…` form for spaces

Symbol mentions (ctags/universal-ctags; best-effort):
- `@MyClassName` or `@my_function` — if `universal-ctags`/`ctags` is available on PATH, Cogem will inline a short snippet around the symbol definition (instead of requiring an explicit `@path/to/file`).
You can disable this with `COGEM_SYMBOL_INDEX=0`.

Paths must resolve under the **repo root**, your **current working directory**, or **`COGEM_CODEX_WORKDIR`**. Anything else is skipped with a note in the attachment block.

Optional limits: `COGEM_AT_MAX_FILE_BYTES` (default `400000`), `COGEM_AT_MAX_TOTAL_CHARS` (default `120000`) for the whole attachment block.

`@` references are **not** inlined for pure **CHAT** routing (you’ll see a short notice).

### Google Stitch (UI-heavy frontend tasks)

For **frontend-first** builds (websites, landing pages, dashboards, HTML/CSS/JS UIs), cogem can run a **Stitch stage** *before* the usual Codex draft → Gemini review → Codex improve loop:

1. **Detect** a UI-heavy task from your prompt (heuristic).
2. **Try adapters** in order: optional CLI → optional HTTP → optional browser stub (off by default) → **manual handoff**.
3. **Fold** any Stitch output (or your export) into the Codex/Gemini prompts, plus strict rules from `.ai/STITCH_WEBSITE.md`.
4. **Non-frontend** tasks are unchanged.

**Prerequisite questions first:** If you ask how to do something *before* a build (e.g. *“build a site, but before that tell me how to connect Stitch via MCP”*), cogem treats that turn as **conversation first** — no build pipeline, no Stitch stage. Use **`/build`** on a later turn when you only want implementation.

**Disable** the Stitch stage entirely: `COGEM_STITCH=0` or `cogem --no-stitch`.

**Manual mode** (default when no adapter succeeds): cogem prints a ready-to-paste **Stitch prompt**, then asks for your **exported HTML/CSS** (paste or `@path`). Non-interactive stdin skips the paste step; use `COGEM_STITCH_CLI` or `COGEM_STITCH_HTTP_URL` instead.

#### Stitch MCP (`stitch-mcp` on npm)

The community **stitch-mcp** package is an MCP **server** that talks to Google’s Stitch API (with `gcloud` auth). Cogem acts as a minimal MCP **client** over stdio and calls the generate tool automatically for frontend tasks (unless you disable MCP):

1. Install **Google Cloud SDK**, run `gcloud auth application-default login`, and set **`GOOGLE_CLOUD_PROJECT`** (see the [stitch-mcp README](https://www.npmjs.com/package/stitch-mcp)).
2. Install **Node.js** so **`npx`** is available.
3. (Optional) Override defaults if needed: `COGEM_STITCH_MCP_CMD=npx` and `COGEM_STITCH_MCP_ARGS=-y stitch-mcp`.
4. Run a frontend-style task in cogem; the adapter chain will try **CLI → MCP → HTTP → manual**.
5. To disable MCP explicitly: `COGEM_STITCH_MCP=0`.

If MCP fails (auth, API, or tool schema), cogem **falls back** to manual export as before. Tool name defaults to `generate_screen_from_text`; override with `COGEM_STITCH_MCP_TOOL` if your server exposes a different name.

There is **no guaranteed public Stitch API** in cogem: integration is **pluggable** via env vars (see table below). Validity of any HTTP/CLI tool is **your** responsibility.

---

## Environment variables (optional)

| Variable | Purpose |
|----------|---------|
| `COGEM_AUTO_PERMISSIONS` | `yes` / `no` — skip the interactive prompt for Codex `--full-auto` and Gemini `--yolo` |
| `COGEM_ALLOW_LOCAL_COMMANDS` | `yes` / `no` — allow local command execution for `/run`, `/test`, `/lint`, and `/github/clone` |
| `COGEM_RUN_POLICY` | strict by default; set `relaxed` to allow legacy broad `/run` command behavior |
| `COGEM_CODEX_WORKDIR` | Absolute path passed to Codex `-C` (workspace root) |
| `COGEM_CODEX_MODEL` | Default Codex LLM ID when `--codex-model` is not passed |
| `COGEM_GEMINI_MODEL` | Default Gemini LLM ID when `--gemini-model` is not passed |
| `COGEM_SUBPROCESS_TIMEOUT_SEC` | Integer seconds; abort a stuck `codex` / `gemini` subprocess after this time |
| `COGEM_STREAM_DIFFS` | `1`/`0` — stream a live unified diff during Codex improvements (opt-in; only when stdout is a TTY) |
| `COGEM_VALIDATION_DOCKER` | `yes` / `no` — prefer Docker-based validation backend (tests/lint/typecheck). See `--validation-docker` |
| `COGEM_STRICT_SANDBOX` | `1` / `0` — when `1`, require Docker for validation; if Docker is missing, cogem skips validation |
| `COGEM_DOCKER_PY_IMAGE` | Docker image for Python validation (default `python:3.12-slim`) |
| `COGEM_DOCKER_NODE_IMAGE` | Docker image for Node validation (default `node:20-slim`) |
| `COGEM_VALIDATION_MAX_ATTEMPTS` | Max automated validation iterations for `/build` (default `2`) |
| `COGEM_TYPECHECK_PYRIGHT` | `1`/`0` — enable pyright type checking for Python projects (if `pyright` is on PATH). (best-effort; default `1`) |
| `COGEM_AT_MAX_FILE_BYTES` | Max bytes read per `@` file (default `400000`) |
| `COGEM_AT_MAX_TOTAL_CHARS` | Max total characters for all `@` attachments in one turn (default `120000`) |
| `COGEM_AT_MAX_PDF_PAGES` | Max pages extracted from a PDF `@` mention (default `30`) |
| `COGEM_SYMBOL_INDEX` | `1` (default) / `0` — enable ctags-based symbol resolution for `@MyClassName` mentions (best-effort; requires `universal-ctags`/`ctags` on PATH) |
| `COGEM_SYMBOL_DEP_CONTEXT` | `1` (default) / `0` — enable symbol-aware dependency injection for BUILD prompts based on `@some_file.py` imports |
| `COGEM_SYMBOL_DEP_MAX_SYMBOLS` | Max imported symbols to resolve/inject per build turn (default `20`) |
| `COGEM_SYMBOL_DEP_MAX_CHARS` | Cap for the injected dependency context text (default `4000`) |
| `COGEM_SYMBOL_COMPLETIONS` | `1`/`0` — include `@MySymbol` completions in the `@` menu (best-effort; requires ctags/universal-ctags for real tags) |
| `COGEM_FUZZY_AT_COMPLETIONS` | `1`/`0` — enable fuzzy fallback for `@` path completion when prefix matches return nothing |
| `COGEM_FUZZY_SYMBOL_COMPLETIONS` | `1`/`0` — enable fuzzy fallback for `@` symbol completion when prefix matches return nothing |
| `COGEM_AUTO_REPO_CONTEXT` | `1`/`0` — auto-retrieve relevant repo snippets for BUILD prompts (keyword + dependency graph) |
| `COGEM_AUTO_REPO_CONTEXT_MAX_CHARS` | Cap for injected auto repo context text (default `8000`) |
| `COGEM_AUTO_REPO_CONTEXT_MAX_FILES` | Max files to inject (default `6`) |
| `COGEM_AUTO_REPO_CONTEXT_MAX_DEPTH` | Dependency expansion depth (default `2`) |
| `COGEM_VECTOR_RAG` | `1`/`0` — enable LanceDB semantic retrieval for BUILD prompts (best-effort; requires extra deps) |
| `COGEM_VECTOR_REBUILD` | `1`/`0` — rebuild the local vector index (default `0`) |
| `COGEM_VECTOR_TOP_K` | Number of semantic matches to inject (default `8`) |
| `COGEM_VECTOR_CHUNK_CHARS` | Chunk size for embedding (default `2500`) |
| `COGEM_STITCH` | `1` (default) / `0` — enable or disable the Stitch stage for UI-heavy tasks |
| `COGEM_STITCH_CLI` | Optional: executable for a Stitch adapter (stdin sends the prompt unless `COGEM_STITCH_CLI_STDIN=0` + temp file) |
| `COGEM_STITCH_CLI_ARGS` | Extra argv appended after the CLI command |
| `COGEM_STITCH_CLI_STDIN` | `1` (default) / `0` — pass prompt on stdin vs temp file path as last arg |
| `COGEM_STITCH_HTTP_URL` | Optional: HTTP endpoint for JSON `{ "prompt": "..." }` (customize body with `COGEM_STITCH_HTTP_BODY`) |
| `COGEM_STITCH_HTTP_TOKEN` | Optional `Authorization: Bearer` for HTTP adapter |
| `COGEM_STITCH_TIMEOUT_SEC` | Timeout for CLI/HTTP Stitch attempts (default `300`) |
| `COGEM_STITCH_BROWSER` | `1` to acknowledge browser automation (not implemented; kept off by default) |
| `COGEM_STITCH_MCP` | MCP stdio client toggle for `npx stitch-mcp` (default: **enabled**; set `0`/`false` to disable) |
| `COGEM_STITCH_MCP_CMD` | Command to launch MCP server (default `npx`) |
| `COGEM_STITCH_MCP_ARGS` | Args for the server (default `-y stitch-mcp`) |
| `COGEM_STITCH_MCP_TOOL` | MCP tool name (default `generate_screen_from_text`) |
| `COGEM_STITCH_MCP_PROMPT_KEY` | JSON argument key for the prompt (default `prompt`) |
| `COGEM_STITCH_MCP_TOOL_ARGS_JSON` | Optional extra JSON object merged into tool `arguments` |
| `COGEM_STITCH_MCP_TIMEOUT_SEC` | Max seconds for the MCP round-trip (default `300`) |

---

## Quick reference (copy-paste)

**WSL (PowerShell, admin):** `wsl --install`  

**WSL shell:** `sudo apt update && sudo apt upgrade -y`  

**Python + pipx:** `sudo apt install -y python3 python3-pip pipx && pipx ensurepath`  

**Codex CLI:** `npm install -g @openai/codex`  

**Gemini CLI:** `npm install -g @google/gemini-cli`  

**Cogem:** `pipx install -e .` then `cogem`  

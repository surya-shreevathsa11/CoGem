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
│   └── __init__.py
│
├── .ai/
│   ├── CODEX.md
│   └── GEMINI.md
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

Pass model IDs to the underlying CLIs (same as `codex exec -m` and `gemini -m`). Valid names depend on your Codex / Gemini CLI version and account.

```bash
cogem --codex-model <MODEL> --gemini-model <MODEL>
```

Examples:

```bash
cogem --gemini-model gemini-2.5-flash
cogem --codex-model o3
```

If a flag is omitted, you can still set defaults with environment variables below.

### In-session commands

On an interactive terminal, the main task prompt uses **prompt-style completion**: type `/` or `@` and use **Tab** (or keep typing) to open a **menu of suggestions** for session directives and paths under the project / cwd (same roots as `@` mentions).

While Cogem is running, you can change models without restarting:

| Command | Meaning |
|---------|---------|
| `/codex/model` | Show current Codex model and startup default |
| `/codex/model <MODEL>` | Use `<MODEL>` for all Codex calls this session |
| `/codex/model reset` | Restore the model from `--codex-model` / `COGEM_CODEX_MODEL` |
| `/gemini/model` | Show current Gemini model and startup default |
| `/gemini/model <MODEL>` | Use `<MODEL>` for all Gemini calls this session |
| `/gemini/model reset` | Restore the model from `--gemini-model` / `COGEM_GEMINI_MODEL` |

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
- `@src` or `@docs/` — directory tree listing (depth and entry limits apply)
- `@"path with spaces/file.txt"` — use double quotes inside the `@…` form for spaces

Paths must resolve under the **repo root**, your **current working directory**, or **`COGEM_CODEX_WORKDIR`**. Anything else is skipped with a note in the attachment block.

Optional limits: `COGEM_AT_MAX_FILE_BYTES` (default `400000`), `COGEM_AT_MAX_TOTAL_CHARS` (default `120000`) for the whole attachment block.

`@` references are **not** inlined for pure **CHAT** routing (you’ll see a short notice).

---

## Environment variables (optional)

| Variable | Purpose |
|----------|---------|
| `COGEM_AUTO_PERMISSIONS` | `yes` / `no` — skip the interactive prompt for Codex `--full-auto` and Gemini `--yolo` |
| `COGEM_CODEX_WORKDIR` | Absolute path passed to Codex `-C` (workspace root) |
| `COGEM_CODEX_MODEL` | Default Codex model when `--codex-model` is not passed |
| `COGEM_GEMINI_MODEL` | Default Gemini model when `--gemini-model` is not passed |
| `COGEM_SUBPROCESS_TIMEOUT_SEC` | Integer seconds; abort a stuck `codex` / `gemini` subprocess after this time |
| `COGEM_AT_MAX_FILE_BYTES` | Max bytes read per `@` file (default `400000`) |
| `COGEM_AT_MAX_TOTAL_CHARS` | Max total characters for all `@` attachments in one turn (default `120000`) |

---

## Quick reference (copy-paste)

**WSL (PowerShell, admin):** `wsl --install`  

**WSL shell:** `sudo apt update && sudo apt upgrade -y`  

**Python + pipx:** `sudo apt install -y python3 python3-pip pipx && pipx ensurepath`  

**Codex CLI:** `npm install -g @openai/codex`  

**Gemini CLI:** `npm install -g @google/gemini-cli`  

**Cogem:** `pipx install -e .` then `cogem`  

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
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
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

## Environment variables (optional)

| Variable | Purpose |
|----------|---------|
| `COGEM_AUTO_PERMISSIONS` | `yes` / `no` — skip the interactive prompt for Codex `--full-auto` and Gemini `--yolo` |
| `COGEM_CODEX_WORKDIR` | Absolute path passed to Codex `-C` (workspace root) |
| `COGEM_SUBPROCESS_TIMEOUT_SEC` | Integer seconds; abort a stuck `codex` / `gemini` subprocess after this time |

---

## Quick reference (copy-paste)

**WSL (PowerShell, admin):** `wsl --install`  

**WSL shell:** `sudo apt update && sudo apt upgrade -y`  

**Python + pipx:** `sudo apt install -y python3 python3-pip pipx && pipx ensurepath`  

**Codex CLI:** `npm install -g @openai/codex`  

**Gemini CLI:** `npm install -g @google/gemini-cli`  

**Cogem:** `pipx install -e .` then `cogem`  

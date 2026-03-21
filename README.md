# AI Dev Engine (Codex + Gemini Workflow)

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
DevAi/
│
├── devai/
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

- WSL (Windows Subsystem for Linux)
- Python 3
- pipx
- Codex CLI
- Gemini CLI

---

## Step 1 — Install WSL (Windows)

Open PowerShell as Administrator:

```
wsl --install
```

Restart your system after installation.

---

## Step 2 — Open WSL

After restart:

```
wsl
```

---

## Step 3 — Install dependencies

Update system:
```
sudo apt update && sudo apt upgrade -y
```

Install Python and pipx:
```
sudo apt install python3 python3-pip pipx -y
pipx ensurepath
```

Restart terminal or run:
```
source ~/.bashrc
```

---

## Step 4 — Install CLIs

### Codex CLI

Verify:
```
codex --version
```

---

### Gemini CLI

Verify:
```
gemini --help
```

Run test:
```
gemini -p "hello"
```

---

## Step 5 — Setup Project

Clone the repository:

```
git clone https://github.com/<your-username>/DevAi.git
cd DevAi
```

---

## Step 6 — Install CLI Tool

```
pipx install -e .
```

---

## Step 7 — Run

```
devai
```

---

## Usage

### General pattern

```
devai
>>> your task
```

---

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

If task includes multiple files:

- system creates files automatically  
- open in browser:

```
explorer.exe index.html
```

---

## Important Rules

- Always describe what you want, not how to code it  
- Avoid mixing manual coding with AI workflow  
- Use separate folders for each project  

---

## Philosophy

This is not an assistant.

This is a controlled development system where:
- generation is separate from validation  
- review is independent  
- improvements are traceable  

---

## Updating the Tool

After making changes:

```
pipx install -e . --force
```

---

## License

MIT (or your choice)→ 

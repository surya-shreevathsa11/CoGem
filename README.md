# AI Dev Engine (Codex + Gemini Workflow)

A CLI-based development system that combines:
- Codex → code generation
- Gemini → strict code review
- System → diff + improvement summary

This creates a **self-improving coding workflow** that works for:
- Scripts (Python, JS, etc.)
- Web development (HTML/CSS/JS)
- Backend APIs
- General coding tasks

---

## 🚀 Features

- 🔁 Iterative improvement loop
- 🧠 Independent review (no bias from generation)
- 📊 Code diff (before vs after)
- 📄 Improvement summary
- 📁 Multi-file project generation
- ⚙️ CLI-based workflow (fast + repeatable)

---

## 📁 Project Structure

```
ai_automation/
│
├── main.py
├── README.md
├── .ai/
│   ├── CODEX.md
│   └── GEMINI.md
```

---

## ⚙️ Requirements

- WSL (Windows Subsystem for Linux)
- Python 3
- Node.js (for JS execution)
- Codex CLI
- Gemini CLI

---

## 🖥️ Step 1 — Install WSL (Windows)

Open PowerShell as Administrator:

```
wsl --install
```

Restart your system after installation.

---

## 🐧 Step 2 — Open WSL

After restart:

```
wsl
```

---

## 📦 Step 3 — Install dependencies

### Update system
```
sudo apt update && sudo apt upgrade -y
```

### Install Python
```
sudo apt install python3 python3-pip -y
```

### Install Node.js
```
sudo apt install nodejs npm -y
```

Check:
```
node -v
npm -v
```

---

## 🤖 Step 4 — Install CLIs

### Codex CLI
(Install based on your provider/setup)

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

## 📁 Step 5 — Setup Project

Clone your repo:

```
git clone <your-repo-url>
cd ai_automation
```

---

## 🧠 Step 6 — Setup AI Rules

Ensure these files exist:

```
.ai/CODEX.md
.ai/GEMINI.md
```

These define:
- how code is written
- how code is reviewed

---

## ▶️ Step 7 — Run System

```
python3 main.py
```

---

## ⚡ Optional — Create shortcut command

Add alias:

```
nano ~/.bashrc
```

Add:

```
alias devai="python3 /mnt/d/ai_automation/main.py"
```

Apply:

```
source ~/.bashrc
```

Now run:

```
devai
```

---

## 🧠 Usage

### General pattern

```
devai
>>> your task
```

---

### Examples

#### Script
```
>>> write python script to rename files in a folder
```

#### Web page
```
>>> create landing page with navbar and hero section
```

#### Backend
```
>>> build node API with login route and JWT authentication
```

---

## 🔁 Workflow

1. Codex generates code  
2. Gemini reviews independently  
3. Codex improves based on review  
4. System outputs:
   - improved code
   - diff
   - summary  

---

## 📁 Project Mode

If task includes multiple files:

- system creates files automatically  
- open in browser:

```
explorer.exe index.html
```

---

## ⚠️ Important Rules

- Always describe **what you want**, not how to code it  
- Avoid mixing manual coding with AI workflow  
- Use separate folders for each project  

---

## 🧠 Philosophy

This is not an assistant.

This is a **controlled development system** where:
- generation ≠ validation  
- review is independent  
- improvements are traceable  

---

## 🚀 Future Improvements

- Auto-run servers  
- Auto-fix runtime errors  
- Full-stack project automation  
- Test generation  

---

## 🧾 License

MIT

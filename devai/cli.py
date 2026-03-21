#!/usr/bin/env python3

def main():
    import subprocess
    import re
    import difflib
    import os

    # ---------- helpers ----------

    def run_cmd(cmd):
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout, result.stderr

    def run_codex(prompt):
        stdout, _ = run_cmd(["codex", "exec", prompt])
        return stdout

    def run_gemini(prompt):
        stdout, _ = run_cmd(["gemini", "-p", prompt])
        return stdout.strip()

    def extract_code(text):
        match = re.search(r"```(?:\w+)?\n([\s\S]*?)```", text)
        return match.group(1).strip() if match else text

    def extract_files(text):
        pattern = r"FILE:\s*(.*?)\n([\s\S]*?)(?=FILE:|$)"
        matches = re.findall(pattern, text)
        return {name.strip(): content.strip() for name, content in matches}

    def write_files(files):
        for name, content in files.items():
            with open(name, "w") as f:
                f.write(content)
            print(f"✅ {name} created")

    def get_diff(old, new):
        diff = difflib.unified_diff(
            old.splitlines(),
            new.splitlines(),
            lineterm=""
        )
        return "\n".join(diff)

    # ---------- load rules ----------

    AI_PATH = os.path.join(os.path.dirname(__file__), "..", ".ai")
    AI_PATH = os.path.abspath(AI_PATH)

    with open(f"{AI_PATH}/CODEX.md") as f:
        CODEX_RULES = f.read()

    with open(f"{AI_PATH}/GEMINI.md") as f:
        GEMINI_RULES = f.read()

    # ---------- input ----------

    task = input(">>> What do you want to build: ")

    # ---------- generate ----------

    raw = run_codex(f"{CODEX_RULES}\n\nTASK:\n{task}")

    files = extract_files(raw)

    if files:
        print("\n=== PROJECT MODE ===\n")
        write_files(files)
        print("\n🚀 Open with: explorer.exe index.html")
        return

    code = extract_code(raw)

    print("\n=== INITIAL CODE ===\n")
    print(code)

    # ---------- review ----------

    review = run_gemini(f"{GEMINI_RULES}\n\nCODE:\n{code}")

    print("\n=== REVIEW ===\n")
    print(review)

    # ---------- improve ----------

    improved_raw = run_codex(f"""
{CODEX_RULES}

You wrote:

{code}

Feedback:

{review}

Improve the code.
Return ONLY code.
""")

    improved = extract_code(improved_raw)

    print("\n=== IMPROVED CODE ===\n")
    print(improved)

    # ---------- diff ----------

    print("\n=== DIFF ===\n")
    print(get_diff(code, improved))

    # ---------- summary ----------

    summary = run_gemini(f"""
{GEMINI_RULES}

Compare and summarize improvements.

OLD:
{code}

NEW:
{improved}
""")

    print("\n=== SUMMARY ===\n")
    print(summary)


if __name__ == "__main__":
    main()

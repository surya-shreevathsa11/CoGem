from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _write_fake_clis(bin_dir: Path) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)

    codex_py = bin_dir / "codex_fake.py"
    gemini_py = bin_dir / "gemini_fake.py"

    codex_py.write_text(
        "\n".join(
            [
                "import sys",
                "args = sys.argv[1:]",
                # codex exec ... prompt is the last arg
                "prompt = args[-1] if args else ''",
                "if 'You update long-lived session memory' in prompt:",
                "    print('NONE')",
                "elif 'Improve the code.' in prompt and 'Feedback:' in prompt:",
                "    print('```python\\ndef answer(x: int) -> int:\\n    return x\\n```')",
                "elif 'TASK:' in prompt:",
                "    print('```python\\ndef answer(x):\\n    return x\\n```')",
                "elif 'ROUTING FORMAT' in prompt:",
                "    print('BUILD')",
                "else:",
                "    print('Codex mock reply')",
            ]
        ),
        encoding="utf-8",
    )

    gemini_py.write_text(
        "\n".join(
            [
                "import sys",
                "args = sys.argv[1:]",
                "prompt = ''",
                "if '-p' in args:",
                "    i = args.index('-p')",
                "    if i + 1 < len(args):",
                "        prompt = args[i + 1]",
                "if 'Compare and summarize improvements.' in prompt:",
                "    print('Summary: improved typing and consistency.')",
                "else:",
                "    print('Review: add explicit type hints and tighten style.')",
            ]
        ),
        encoding="utf-8",
    )

    if os.name == "nt":
        codex_cmd = bin_dir / "codex.cmd"
        gemini_cmd = bin_dir / "gemini.cmd"
        codex_cmd.write_text(
            "@echo off\r\n\"{}\" \"{}\" %*\r\n".format(sys.executable, str(codex_py)),
            encoding="utf-8",
        )
        gemini_cmd.write_text(
            "@echo off\r\n\"{}\" \"{}\" %*\r\n".format(sys.executable, str(gemini_py)),
            encoding="utf-8",
        )
    else:
        codex_sh = bin_dir / "codex"
        gemini_sh = bin_dir / "gemini"
        codex_sh.write_text(
            "#!/bin/bash\n\"{}\" \"{}\" \"$@\"\n".format(
                sys.executable.replace("\\", "/"),
                str(codex_py).replace("\\", "/"),
            ),
            encoding="utf-8",
        )
        gemini_sh.write_text(
            "#!/bin/bash\n\"{}\" \"{}\" \"$@\"\n".format(
                sys.executable.replace("\\", "/"),
                str(gemini_py).replace("\\", "/"),
            ),
            encoding="utf-8",
        )
        try:
            os.chmod(codex_sh, 0o755)
            os.chmod(gemini_sh, 0o755)
        except OSError:
            pass


def _run_cli(repo_root: Path, stdin_text: str, bin_dir: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    codex_exec = "codex.cmd" if os.name == "nt" else "codex"
    gemini_exec = "gemini.cmd" if os.name == "nt" else "gemini"
    env["CLOGEM_CODEX_CMD"] = str(bin_dir / codex_exec)
    env["CLOGEM_GEMINI_CMD"] = str(bin_dir / gemini_exec)
    env["CLOGEM_AUTO_PERMISSIONS"] = "yes"
    env["CLOGEM_ALLOW_LOCAL_COMMANDS"] = "yes"
    env["CLOGEM_STITCH"] = "0"
    env["CLOGEM_AUTO_REPO_CONTEXT"] = "0"
    env["CLOGEM_SYMBOL_INDEX"] = "0"
    env["CLOGEM_GIT_CONTEXT"] = "0"
    env["CLOGEM_VECTOR_RAG"] = "0"
    env["CLOGEM_VALIDATION_MAX_ATTEMPTS"] = "1"
    env["CLOGEM_GEMINI_REALTIME"] = "0"
    env["PYTHONIOENCODING"] = "utf-8"

    return subprocess.run(
        [sys.executable, "-m", "clogem.cli"],
        input=stdin_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(repo_root),
        env=env,
        timeout=60,
    )


def test_cli_ask_and_exit(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    bin_dir = tmp_path / "bin"
    _write_fake_clis(bin_dir)

    proc = _run_cli(repo_root, "/ask hello\n/exit\n", bin_dir)
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0
    assert "Reply (/ask)" in out
    assert "Codex mock reply" in out
    assert "Goodbye." in out


def test_cli_build_pipeline_mocked(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    bin_dir = tmp_path / "bin"
    _write_fake_clis(bin_dir)

    proc = _run_cli(repo_root, "/build implement answer\n/exit\n", bin_dir)
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0
    assert "Initial output (Codex)" in out
    assert "Review (Gemini)" in out
    assert "Summary (Gemini)" in out
    assert "Goodbye." in out


def test_cli_pdf_intent_does_not_trigger_build_pipeline(tmp_path: Path):
    """
    Regression: natural-language PDF requests should not enter the build pipeline
    (which can cause unrelated artifact generation).
    """
    repo_root = Path(__file__).resolve().parents[1]
    bin_dir = tmp_path / "bin"
    _write_fake_clis(bin_dir)

    proc = _run_cli(repo_root, "generate a pdf hello\n/exit\n", bin_dir)
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0
    assert "Initial output" not in out
    assert "Review (" not in out
    assert "Summary (" not in out


def test_cli_research_without_attachments_skips_build_pipeline(tmp_path: Path):
    """Regression: /research without @ still runs (web-grounded / best-effort) and skips build."""
    repo_root = Path(__file__).resolve().parents[1]
    bin_dir = tmp_path / "bin"
    _write_fake_clis(bin_dir)

    proc = _run_cli(repo_root, "/research what is CRISPR?\n/exit\n", bin_dir)
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0
    assert "Reply (/research)" in out
    assert "can't verify research claims without sources" not in out.lower()
    assert "Initial output" not in out
    assert "Review (" not in out
    assert "Summary (" not in out


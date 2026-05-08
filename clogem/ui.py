from __future__ import annotations

from clogem.logging_utils import get_logger

logger = get_logger(__name__)


# Boot palette (24-bit ANSI) — matches clogem rose theme, not plain white
_BOOT_ROSE = "\033[38;2;190;85;85m"
_BOOT_SOFT = "\033[38;2;255;175;175m"
_BOOT_BLUSH = "\033[38;2;255;200;200m"
_BOOT_MUTED = "\033[38;2;180;130;130m"
_BOOT_ERR = "\033[38;2;230;70;90m"
_BOOT_RESET = "\033[0m"


def _boot_type_line(text: str, delay: float = 0.008, color: str = _BOOT_SOFT) -> None:
    import sys
    import time

    # In non-interactive contexts (tests, piped output), don't slow down output.
    if not sys.stdout.isatty():
        delay = 0.0

    for char in text:
        sys.stdout.write(f"{color}{char}{_BOOT_RESET}")
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write("\n")
    sys.stdout.flush()


def _boot_spinner_worker(stop_event, label: str) -> None:
    import sys
    import time

    spinner = ["|", "/", "-", "\\"]
    i = 0
    while not stop_event.is_set():
        sys.stdout.write(
            f"\r{_BOOT_MUTED}{label}... {spinner[i % len(spinner)]}{_BOOT_RESET}  "
        )
        sys.stdout.flush()
        time.sleep(0.1)
        i += 1


def _boot_run_step(
    label: str,
    check,
    min_spin: float = 0.35,
) -> bool:
    """Spin; run optional check() -> bool. Clear line and print ok / not found."""
    import sys
    import time
    import threading

    stop = threading.Event()
    t = threading.Thread(target=_boot_spinner_worker, args=(stop, label), daemon=True)
    t.start()
    t0 = time.monotonic()
    ok = True
    if check is not None:
        ok = bool(check())
    while time.monotonic() - t0 < min_spin:
        time.sleep(0.05)
    stop.set()
    t.join(timeout=2.0)
    sys.stdout.write("\r" + " " * 96 + "\r")
    sys.stdout.flush()
    if check is None:
        sys.stdout.write(f"{_BOOT_ROSE}{label}... ok{_BOOT_RESET}\n")
        sys.stdout.flush()
        return True
    if ok:
        sys.stdout.write(f"{_BOOT_ROSE}{label}... ok{_BOOT_RESET}\n")
    else:
        sys.stdout.write(f"{_BOOT_ERR}{label}... not found{_BOOT_RESET}\n")
    sys.stdout.flush()
    return ok


def boot_sequence(required_providers: set[str] | None = None) -> bool:
    """TTY-style boot, real codex/gemini checks. Returns False if deps missing."""
    import os
    import shutil
    import shlex
    import sys

    def _cmd_exists(raw: str, default_cmd: str) -> bool:
        txt = (raw or "").strip() or default_cmd
        try:
            parts = shlex.split(txt, posix=os.name != "nt")
        except Exception:
            logger.debug("Failed to parse command line for dependency check: %s", txt, exc_info=True)
            parts = txt.split()
        if not parts:
            parts = [default_cmd]
        exe = parts[0]
        return bool(shutil.which(exe) or os.path.isfile(exe))

    def _openai_sdk_ready() -> bool:
        if not os.environ.get("OPENAI_API_KEY", "").strip():
            return False
        try:
            import openai  # noqa: F401

            return True
        except Exception:
            logger.debug("OpenAI SDK readiness check failed", exc_info=True)
            return False

    def _gemini_sdk_ready() -> bool:
        if not (
            os.environ.get("GEMINI_API_KEY", "").strip()
            or os.environ.get("GOOGLE_API_KEY", "").strip()
        ):
            return False
        try:
            from google import genai  # noqa: F401

            return True
        except Exception:
            logger.debug("Gemini SDK readiness check failed", exc_info=True)
            return False

    def _claude_sdk_ready() -> bool:
        if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
            return False
        try:
            import anthropic  # noqa: F401

            return True
        except Exception:
            logger.debug("Anthropic SDK readiness check failed", exc_info=True)
            return False

    sys.stdout.write("\n")
    sys.stdout.flush()

    # ANSI Regular–style FIGlet spelling "CLOGEM" (Unicode block chars).
    logo = [
        " ██████ ██       ██████   ██████  ███████ ███    ███",
        "██      ██      ██    ██ ██       ██      ████  ████",
        "██      ██      ██    ██ ██   ███ █████   ██ ████ ██",
        "██      ██      ██    ██ ██    ██ ██      ██  ██  ██",
        " ██████ ███████  ██████   ██████  ███████ ██      ██",
    ]
    for row in logo:
        _boot_type_line(row, 0.002, _BOOT_BLUSH)
    sys.stdout.write("\n")
    sys.stdout.flush()
    _boot_type_line("clogem · build → review → evolve", 0.008, _BOOT_ROSE)
    sys.stdout.write("\n")
    sys.stdout.flush()

    _boot_run_step("initializing engine", None, min_spin=0.45)

    req = set(required_providers or {"codex", "gemini"})

    if "codex" in req:
        codex_ready = _boot_run_step(
            "loading codex",
            lambda: _cmd_exists(os.environ.get("CLOGEM_CODEX_CMD", ""), "codex")
            or _openai_sdk_ready(),
            min_spin=0.35,
        )
        if not codex_ready:
            sys.stdout.write("\n")
            sys.stdout.flush()
            sys.stdout.write(
                f"{_BOOT_ERR}clogem cannot start: codex provider unavailable.{_BOOT_RESET}\n"
            )
            sys.stdout.write(
                f"{_BOOT_MUTED}Install Codex CLI or configure OPENAI_API_KEY + openai SDK.{_BOOT_RESET}\n"
            )
            sys.stdout.flush()
            return False

    if "gemini" in req:
        gemini_ready = _boot_run_step(
            "loading gemini",
            lambda: _cmd_exists(os.environ.get("CLOGEM_GEMINI_CMD", ""), "gemini")
            or _gemini_sdk_ready(),
            min_spin=0.35,
        )
        if not gemini_ready:
            sys.stdout.write("\n")
            sys.stdout.flush()
            sys.stdout.write(
                f"{_BOOT_ERR}clogem cannot start: gemini provider unavailable.{_BOOT_RESET}\n"
            )
            sys.stdout.write(
                f"{_BOOT_MUTED}Install Gemini CLI or configure GOOGLE_API_KEY/GEMINI_API_KEY + google-genai SDK.{_BOOT_RESET}\n"
            )
            sys.stdout.flush()
            return False

    if "claude" in req:
        claude_ready = _boot_run_step(
            "loading claude",
            _claude_sdk_ready,
            min_spin=0.35,
        )
        if not claude_ready:
            sys.stdout.write("\n")
            sys.stdout.flush()
            sys.stdout.write(
                f"{_BOOT_ERR}clogem cannot start: claude provider unavailable.{_BOOT_RESET}\n"
            )
            sys.stdout.write(
                f"{_BOOT_MUTED}Set ANTHROPIC_API_KEY and install anthropic SDK.{_BOOT_RESET}\n"
            )
            sys.stdout.flush()
            return False

    _boot_type_line("system ready >", 0.01, _BOOT_ROSE)
    sys.stdout.write("\n")
    sys.stdout.flush()
    return True

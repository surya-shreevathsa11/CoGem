from __future__ import annotations

import os
from typing import Optional, Tuple


def frontend_entry_file(repo_root: str) -> Optional[str]:
    candidates = (
        "index.html",
        "public/index.html",
        "dist/index.html",
        "build/index.html",
    )
    for rel in candidates:
        p = os.path.join(repo_root, rel)
        if os.path.isfile(p):
            return p
    return None


def capture_frontend_screenshot(
    repo_root: str,
    out_path: str,
    viewport: Tuple[int, int] = (1440, 900),
) -> Tuple[bool, str]:
    """
    Best-effort screenshot capture for static frontend outputs.
    Uses Playwright Python if available.
    """
    entry = frontend_entry_file(repo_root)
    if not entry:
        return False, "No frontend entry file found (index.html/public/dist/build)."
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return (
            False,
            "Playwright is not installed. Install with `pip install playwright` and run `playwright install chromium`.",
        )
    try:
        url = "file:///" + os.path.realpath(entry).replace("\\", "/")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
            page.goto(url, wait_until="networkidle", timeout=20000)
            page.screenshot(path=out_path, full_page=True)
            browser.close()
        return True, ""
    except Exception as e:
        return False, f"Screenshot capture failed: {e}"


from __future__ import annotations

import os
import re
from typing import Iterable, List, Tuple


def _to_reportlab_ascii(s: str) -> str:
    # ReportLab's built-in Helvetica is ASCII-centric. Keep it safe by
    # replacing non-ascii with '?' (no unicode font embedding here).
    return "".join(ch if ord(ch) < 128 else "?" for ch in s)


def _wrap_words(
    canvas,  # reportlab canvas
    text: str,
    font_name: str,
    font_size: float,
    max_width: float,
) -> List[str]:
    words = re.split(r"(\s+)", text)
    lines: List[str] = []
    buf = ""
    for w in words:
        if not w:
            continue
        tentative = buf + w
        if canvas.stringWidth(tentative, font_name, font_size) <= max_width:
            buf = tentative
            continue
        if buf.strip():
            lines.append(buf.strip())
            buf = w.lstrip() if w.isspace() else w
        else:
            # Single very-long word: hard break.
            lines.append(tentative.strip())
            buf = ""
    if buf.strip():
        lines.append(buf.strip())
    return [l for l in lines if l]


def generate_pdf_from_text(
    text: str,
    out_path: str,
    *,
    font_name: str = "Helvetica",
    font_size: float = 11.0,
    leading: float | None = None,
) -> str:
    """
    Generate a basic text PDF using ReportLab.

    Note: This is NOT an HTML->PDF renderer; it lays out plain text lines.
    Returns the final output path.
    """
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        raise ValueError("Refusing to generate an empty PDF.")

    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas as rl_canvas
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "PDF generation requires the 'reportlab' dependency."
        ) from e

    out_dir = os.path.dirname(os.path.abspath(out_path)) or os.getcwd()
    os.makedirs(out_dir, exist_ok=True)

    c = rl_canvas.Canvas(out_path, pagesize=letter)
    width, height = letter
    margin = 36  # half-inch
    max_width = width - 2 * margin
    y = height - margin
    lh = leading if leading is not None else font_size * 1.25

    safe = _to_reportlab_ascii(text)

    for para in safe.split("\n\n"):
        para_lines = para.split("\n")
        for idx, pl in enumerate(para_lines):
            pl = pl.strip()
            if not pl:
                continue
            for line in _wrap_words(c, pl, font_name, font_size, max_width):
                if y - lh < margin:
                    c.showPage()
                    c.setFont(font_name, font_size)
                    y = height - margin
                c.drawString(margin, y, line)
                y -= lh
        # extra blank line between paragraphs
        y -= lh * 0.5
        if y - lh < margin:
            c.showPage()
            c.setFont(font_name, font_size)
            y = height - margin

    c.save()
    return out_path


def pdf_path_for_text_request(cwd: str, desired_out: str | None) -> Tuple[str, str]:
    """
    Compute a safe output path for PDF generation.

    Returns (final_path, display_name).
    """
    if not desired_out or not desired_out.strip():
        desired_out = "cogem-output.pdf"
    desired_out = desired_out.strip().strip('"').strip("'")

    # Force into cwd for safety when user passes a bare filename.
    if not os.path.isabs(desired_out):
        desired_out = os.path.join(cwd, desired_out)

    base_dir = os.path.dirname(desired_out) or cwd
    base_name = os.path.basename(desired_out)

    root, ext = os.path.splitext(base_name)
    if not ext.lower().endswith("pdf"):
        ext = ".pdf"
    final_path = os.path.join(base_dir, root + ext)

    if not os.path.exists(final_path):
        return final_path, final_path

    # Avoid overwriting: bump suffix.
    i = 1
    while True:
        candidate = os.path.join(base_dir, f"{root}_{i}{ext}")
        if not os.path.exists(candidate):
            return candidate, candidate
        i += 1


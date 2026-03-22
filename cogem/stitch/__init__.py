"""Google Stitch integration: frontend detection, prompt building, pluggable adapters."""

from .adapters import StitchResult, looks_like_ui_content, try_stitch_adapters
from .detection import detect_frontend_task, should_skip_stitch_due_to_attachments
from .prompt_builder import build_stitch_prompt

__all__ = [
    "StitchResult",
    "looks_like_ui_content",
    "try_stitch_adapters",
    "detect_frontend_task",
    "should_skip_stitch_due_to_attachments",
    "build_stitch_prompt",
]

from __future__ import annotations

import logging
import os

_CONFIGURED = False


def debug_enabled() -> bool:
    # Support both prefixes for compatibility with historical docs/issues.
    val = (os.environ.get("CLOGEM_DEBUG") or os.environ.get("COGEM_DEBUG") or "").strip().lower()
    return val in ("1", "true", "yes", "on", "debug")


def get_logger(name: str) -> logging.Logger:
    global _CONFIGURED
    if not _CONFIGURED:
        level = logging.DEBUG if debug_enabled() else logging.WARNING
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        _CONFIGURED = True
    return logging.getLogger(name)

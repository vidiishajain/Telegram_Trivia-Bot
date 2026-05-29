"""Logging setup — call `setup_logging()` once, at program startup.

We use **loguru** (https://loguru.readthedocs.io) because it gives great logging
with almost no boilerplate. After `setup_logging()`, you log from anywhere with:

    from loguru import logger
    logger.info("processing message from {}", user_id)
    logger.exception("something blew up")   # inside an `except:` block

Logs go to BOTH places:
  - the **console** (so you watch what's happening live), and
  - a **rotating file** at `logs/agent.log` (so you — and Claude — can read the
    history later: `tail -f logs/agent.log`, or just open the file).

The file rotates at 10 MB and keeps ~10 days of history, so it never grows forever.
"""

import sys
from pathlib import Path

from loguru import logger

from agent.config import get_settings

LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "agent.log"

_CONFIGURED = False


def setup_logging() -> None:
    """Configure console + file logging. Safe to call more than once (no-op after first)."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()
    LOG_DIR.mkdir(exist_ok=True)

    # loguru starts with a default handler on stderr — remove it so we control everything.
    logger.remove()

    fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    # 1) Console: colorized, easy to read while developing.
    logger.add(sys.stderr, level=settings.log_level, format=fmt, colorize=True)

    # 2) File: plain text, rotated and time-limited so it stays manageable.
    logger.add(
        LOG_FILE,
        level=settings.log_level,
        format=fmt,
        colorize=False,
        rotation="10 MB",
        retention="10 days",
        encoding="utf-8",
        enqueue=True,  # safe to log from async code / multiple tasks
        backtrace=True,
        diagnose=True,
    )

    _CONFIGURED = True
    logger.debug("Logging configured (level={}). Writing to {}.", settings.log_level, LOG_FILE)

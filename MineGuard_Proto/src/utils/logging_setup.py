"""logging_setup.py — Structured Logging Configuration for MineGuard.

Provides a single ``setup_logging`` function that every script calls once
instead of duplicating ``logging.basicConfig`` everywhere.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional


# Project root derived from file location
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def setup_logging(
    name: str,
    config: Optional[Dict[str, Any]] = None,
) -> logging.Logger:
    """Configure the root logger and return a named child logger.

    Args:
        name: Human-readable name used in the log filename
              (e.g. ``"main_script"``).
        config: Optional config dict; reads ``config["logging"]`` for
                ``level`` and ``log_file``.

    Returns:
        A configured ``logging.Logger`` instance.
    """
    log_cfg = (config or {}).get("logging", {})
    level_name: str = log_cfg.get("level", "INFO")
    level: int = getattr(logging, level_name.upper(), logging.INFO)

    log_dir = _PROJECT_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Per-script log file
    log_file = log_dir / f"{name}.log"

    # Central pipeline log (shared across all scripts)
    pipeline_log = log_dir / log_cfg.get("log_file", "pipeline.log").replace(
        "logs/", ""
    )

    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    formatter = logging.Formatter(fmt)

    root = logging.getLogger()
    # Avoid duplicate handlers on repeated calls
    if not root.handlers:
        root.setLevel(level)

        # Console
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        root.addHandler(console)

        # Per-script file
        fh_script = logging.FileHandler(str(log_file), encoding="utf-8")
        fh_script.setFormatter(formatter)
        root.addHandler(fh_script)

        # Shared pipeline log
        fh_pipeline = logging.FileHandler(str(pipeline_log), encoding="utf-8")
        fh_pipeline.setFormatter(formatter)
        root.addHandler(fh_pipeline)

    return logging.getLogger(name)

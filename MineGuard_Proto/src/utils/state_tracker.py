"""state_tracker.py — Pipeline State Persistence for MineGuard.

Reads and writes ``logs/pipeline_state.json`` so the pipeline can
detect which stages have completed and resume after a crash.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_STATE_FILE = _PROJECT_ROOT / "logs" / "pipeline_state.json"

_DEFAULT_STATE: Dict[str, bool] = {
    "download_complete": False,
    "processing_complete": False,
    "analysis_complete": False,
}


def load_state() -> Dict[str, Any]:
    """Load pipeline state from disk, or return defaults.

    Returns:
        State dictionary with boolean flags for each stage.
    """
    if _STATE_FILE.exists():
        try:
            with open(_STATE_FILE, "r", encoding="utf-8") as fh:
                state: Dict[str, Any] = json.load(fh)
            logger.info("Pipeline state loaded from %s", _STATE_FILE)
            return state
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read state file (%s). Using defaults.", exc)

    return dict(_DEFAULT_STATE)


def update_state(stage: str, status: bool) -> None:
    """Update a single stage flag and persist to disk.

    Args:
        stage: Key name, e.g. ``"download_complete"``.
        status: ``True`` if the stage finished successfully.
    """
    state = load_state()
    state[stage] = status

    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_STATE_FILE, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)

    logger.info("Pipeline state updated: %s = %s", stage, status)


def reset_state() -> None:
    """Reset all stage flags to ``False``."""
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_STATE_FILE, "w", encoding="utf-8") as fh:
        json.dump(_DEFAULT_STATE, fh, indent=2)

    logger.info("Pipeline state reset.")

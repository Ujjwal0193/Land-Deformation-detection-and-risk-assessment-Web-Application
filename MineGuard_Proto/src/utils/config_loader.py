"""config_loader.py — Central Configuration Loader for MineGuard.

Loads pipeline parameters from config/config.yaml and returns them
as a plain dictionary.
"""

import os
import logging
from pathlib import Path
from typing import Any, Dict

import yaml

logger = logging.getLogger(__name__)

# config/ sits alongside src/ inside MineGuard_Proto
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "config" / "config.yaml"


def load_config(config_path: str | Path | None = None) -> Dict[str, Any]:
    """Load YAML configuration and return as a dictionary.

    Args:
        config_path: Optional override path to a YAML file.
                     Defaults to ``config/config.yaml`` relative to project root.

    Returns:
        Configuration dictionary.

    Raises:
        FileNotFoundError: If the config file does not exist.
        yaml.YAMLError: If the YAML is malformed.
    """
    path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH

    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with open(path, "r", encoding="utf-8") as fh:
        config: Dict[str, Any] = yaml.safe_load(fh) or {}

    logger.info("Configuration loaded from %s", path)
    return config


def sync_config_from_gui(
    roi_bbox: Dict[str, float],
    start_year: str,
    end_year: str,
    frequency: str,
    config_path: str | Path | None = None,
) -> None:
    """Write GUI-selected ROI and timeline values back to config.yaml.

    This ensures main_script.py and the SNAP pipeline read the exact
    parameters the user configured in the web interface.

    Args:
        roi_bbox: Bounding box dict with keys north, south, east, west.
        start_year: Start year as string (e.g. '2015').
        end_year: End year as string (e.g. '2019').
        frequency: One of 'Monthly', 'Quarterly', 'Yearly'.
        config_path: Optional override path.
    """
    path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH

    # Load existing config to preserve all other keys
    existing: Dict[str, Any] = {}
    if path.exists():
        with open(path, "r", encoding="utf-8") as fh:
            existing = yaml.safe_load(fh) or {}

    # ROI: compute centre lat/lon from the bounding box for main_script.py
    centre_lat = (roi_bbox.get("north", 0) + roi_bbox.get("south", 0)) / 2.0
    centre_lon = (roi_bbox.get("east", 0) + roi_bbox.get("west", 0)) / 2.0
    existing["roi"] = {
        "lat": round(centre_lat, 6),
        "lon": round(centre_lon, 6),
        "north": roi_bbox.get("north", 0),
        "south": roi_bbox.get("south", 0),
        "east": roi_bbox.get("east", 0),
        "west": roi_bbox.get("west", 0),
    }

    # Timeline
    years_span = max(int(end_year) - int(start_year) + 1, 1)
    if frequency == "Monthly":
        samples = years_span * 12
    elif frequency == "Quarterly":
        samples = years_span * 4
    else:
        samples = years_span

    existing.setdefault("data_window", {})
    existing["data_window"]["start_date"] = str(start_year)
    existing["data_window"]["end_date"] = str(end_year)
    existing["data_window"]["samples"] = samples

    # Write back
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(existing, fh, default_flow_style=False, sort_keys=False)

    logger.info(
        "config.yaml synced from GUI: ROI=(%.4f, %.4f), bbox=(%s), Timeline=%s–%s, Samples=%d",
        centre_lat, centre_lon, roi_bbox, start_year, end_year, samples,
    )


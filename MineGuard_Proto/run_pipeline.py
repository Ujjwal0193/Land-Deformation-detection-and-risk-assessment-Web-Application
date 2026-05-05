"""run_pipeline.py — Master Execution Script for MineGuard

Executes the full InSAR pipeline in sequence:
1. main_script.py               — Download & SNAP Processing
2. plot_displacement.py          — Displacement Time-Series
3. plot_coherence.py             — Coherence Time-Series
4. plot_displacement_vectors.py  — Vector Field & Strain Maps
5. advanced_analysis.py          — Phase Unwrapping, Direction & 3D Analysis

Tracks pipeline state in logs/pipeline_state.json for crash-resume.
Stops immediately if any step fails.

NOTE: advanced_analysis.py and plot_displacement.py require hotspots.json.
      The pipeline will run hotspot_tracker.py interactively to ask the user
      to click on the map.
"""

import os
import sys
import subprocess
import logging

# --- Ensure src/ is importable ---
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from src.utils.config_loader import load_config
from src.utils.logging_setup import setup_logging
from src.utils.state_tracker import load_state, update_state, reset_state

# --- CONFIGURATION ---
config = load_config()
logger = setup_logging("run_pipeline", config)

SRC_DIR = os.path.join(PROJECT_ROOT, "src")

# Pipeline stages: (display_name, script_path, state_key)
PIPELINE_STAGES = [
    ("Download & Processing",          os.path.join(SRC_DIR, "main_script.py"),                "download_complete"),
    ("Interactive Hotspot Selection",  os.path.join(SRC_DIR, "hotspot_tracker.py"),             "hotspots_complete"),
    ("Displacement Analysis",          os.path.join(SRC_DIR, "plot_displacement.py"),           "displacement_complete"),
    ("Coherence Analysis",             os.path.join(SRC_DIR, "plot_coherence.py"),              "coherence_complete"),
    ("Displacement Vector Field",      os.path.join(SRC_DIR, "plot_displacement_vectors.py"),   "vectors_complete"),
    ("Advanced Displacement Analysis", os.path.join(SRC_DIR, "advanced_analysis.py"),           "advanced_complete"),
]


def run_script(name: str, script_path: str) -> bool:
    """Execute a Python script as a subprocess and report success/failure."""
    logging.info(f"--- Starting Step: {name} ---")

    if not os.path.exists(script_path):
        logging.critical(f"Script not found: {script_path}")
        return False

    try:
        result = subprocess.run(
            [sys.executable, script_path],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=False,
        )
        logging.info(f"[OK] Step '{name}' completed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"[FAIL] Step '{name}' failed with exit code {e.returncode}.")
        return False
    except Exception as e:
        logging.error(f"[FAIL] Step '{name}' failed with exception: {e}")
        return False


def main() -> None:
    """Execute all pipeline steps sequentially with state tracking."""
    logging.info("=========================================")
    logging.info("   MineGuard InSAR Pipeline Started")
    logging.info("=========================================")

    state = load_state()
    logging.info(f"  Pipeline state: {state}")

    for name, script_path, state_key in PIPELINE_STAGES:
        if state.get(state_key, False):
            logging.info(f"[SKIP] '{name}' already complete (state: {state_key}). Skipping.")
            continue

        success = run_script(name, script_path)
        if success:
            update_state(state_key, True)
        else:
            logging.critical("Pipeline aborted due to error.")
            sys.exit(1)

    logging.info("=========================================")
    logging.info("   All Pipeline Steps Completed!")
    logging.info("=========================================")

    # Reset state so next run starts fresh
    reset_state()


if __name__ == "__main__":
    main()

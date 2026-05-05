"""
plot_displacement.py — InSAR LOS Displacement Time-Series

Automatically detects the mine pit (lowest coherence), extracts wrapped phase
from a 5×5 window, validates coherence, and plots cumulative LOS displacement.
Exports results to CSV.
"""

import os
import re
import csv
import json
import glob
import logging
import sys
import traceback
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any

import numpy as np
import warnings
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

warnings.filterwarnings("ignore", category=UserWarning)  # Suppress rasterio NotGeoreferencedWarning
warnings.filterwarnings("ignore", category=RuntimeWarning)

try:
    import rasterio
    from scipy.ndimage import uniform_filter
except ImportError:
    logging.critical("Error: Required libraries not installed.")
    logging.critical("Please run: pip install rasterio scipy")
    sys.exit(1)

# --- PATH CONFIGURATION ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
OUTPUT_INT_DIR = os.path.join(DATA_DIR, "output_int")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")
HOTSPOTS_FILE = os.path.join(CONFIG_DIR, "hotspots.json")

# --- CENTRAL CONFIG + LOGGING ---
sys.path.insert(0, PROJECT_ROOT)
from src.utils.config_loader import load_config
from src.utils.logging_setup import setup_logging

_cfg = load_config()
setup_logging("plot_displacement", _cfg)

os.makedirs(RESULTS_DIR, exist_ok=True)

# Sentinel-1 C-band wavelength (meters)
WAVELENGTH_M = 0.05546
COHERENCE_THRESHOLD = _cfg.get("coherence_threshold", 0.15)
WINDOW_HALF = 2


# --- INTERACTIVE HOTSPOT SELECTION ---

def get_first_hotspot_coordinates() -> Tuple[Optional[int], Optional[int]]:
    """Return the pixel coordinates of the primary user-selected hotspot."""
    if not os.path.exists(HOTSPOTS_FILE):
        logging.warning(f"No interactive hotspots found at {HOTSPOTS_FILE}. Did hotspot_tracker run?")
        return None, None
    try:
        with open(HOTSPOTS_FILE, 'r', encoding='utf-8') as fh:
            hotspots = json.load(fh)
            if not hotspots:
                return None, None
            hs = hotspots[0]
            logging.info(f"  Using interactive hotspot '{hs['label']}' at pixel (x={hs['x']}, y={hs['y']})")
            return hs['x'], hs['y']
    except Exception as e:
        logging.error(f"  Error reading hotspots.json: {e}")
        return None, None

# --- DATE EXTRACTION ---

def extract_dates_from_filename(filename: str) -> List[datetime]:
    """Extract acquisition dates from a Sentinel-1 product filename."""
    matches = re.findall(r'(\d{8})T\d{6}', filename)
    if not matches:
        matches = re.findall(r'(20[12]\d{5})', filename)

    dates = []
    for m in matches:
        try:
            dates.append(datetime.strptime(m, "%Y%m%d"))
        except ValueError:
            continue
    dates.sort()
    return dates


# --- WINDOW SAMPLING ---

def sample_window(src: Any, y: int, x: int) -> Optional[np.ndarray]:
    """Read a small window of data centered at (y, x) from a rasterio source."""
    height, width = src.shape
    y_min = max(0, y - WINDOW_HALF)
    y_max = min(height, y + WINDOW_HALF + 1)
    x_min = max(0, x - WINDOW_HALF)
    x_max = min(width, x + WINDOW_HALF + 1)

    if y_min >= y_max or x_min >= x_max:
        return None

    window = ((y_min, y_max), (x_min, x_max))
    return src.read(1, window=window).astype(np.float64)


def check_coherence(data_dir: str, y: int, x: int) -> Optional[float]:
    """Return the mean coherence in a windowed sample at (y, x)."""
    coh_files = glob.glob(os.path.join(data_dir, "coh_*.img"))
    if not coh_files:
        coh_files = glob.glob(os.path.join(data_dir, "coh_*.hdr"))
    if not coh_files:
        return None

    try:
        with rasterio.open(coh_files[0]) as src:
            data = sample_window(src, y, x)
            if data is None:
                return None
            valid = data[data > 0]
            if len(valid) == 0:
                return None
            return float(np.mean(valid))
    except Exception:
        return None


# --- MAIN DATA COLLECTION ---

def get_displacement_data() -> List[Dict[str, Any]]:
    """Collect wrapped-phase displacement from all interferograms in OUTPUT_INT_DIR."""
    dim_files = glob.glob(os.path.join(OUTPUT_INT_DIR, "*.dim"))
    if not dim_files:
        logging.warning(f"No .dim files found in {OUTPUT_INT_DIR}")
        return []

    results = []

    for dim_file in dim_files:
        basename = os.path.basename(dim_file)
        data_dir = dim_file.replace('.dim', '.data')

        if not os.path.exists(data_dir):
            logging.warning(f"Data directory missing for {basename}")
            continue

        logging.info(f"Processing {basename}...")

        pit_x, pit_y = get_first_hotspot_coordinates()

        if pit_x is None or pit_y is None:
            logging.warning(f"  Interactive hotspot missing. Skipping {basename}.")
            continue

        mean_coh = check_coherence(data_dir, pit_y, pit_x)

        if mean_coh is None:
            logging.warning(f"  Could not read coherence for {basename}. Skipping.")
            continue

        if mean_coh < COHERENCE_THRESHOLD:
            logging.warning(f"  Mean coherence {mean_coh:.3f} < {COHERENCE_THRESHOLD} "
                            f"for {basename}. Interferogram unreliable — skipping.")
            continue

        logging.info(f"  Coherence check passed: {mean_coh:.3f} (Threshold: {COHERENCE_THRESHOLD})")

        phase_files = glob.glob(os.path.join(data_dir, "Phase_*.img"))
        if not phase_files:
            phase_files = glob.glob(os.path.join(data_dir, "Phase_*.hdr"))
        if not phase_files:
            all_imgs = glob.glob(os.path.join(data_dir, "*.img"))
            phase_files = [f for f in all_imgs if "coh_" not in os.path.basename(f).lower()]

        if not phase_files:
            logging.warning(f"  No phase band found for {basename}.")
            continue

        try:
            with rasterio.open(phase_files[0]) as src:
                phase_data = sample_window(src, pit_y, pit_x)

                if phase_data is None:
                    logging.warning(f"  Phase window out of bounds for {basename}.")
                    continue

                valid_phase = phase_data[phase_data != 0]
                if len(valid_phase) == 0:
                    valid_phase = phase_data.flatten()

                mean_phase_rad = float(np.mean(valid_phase))
                displacement_m = (mean_phase_rad * WAVELENGTH_M) / (-4.0 * np.pi)

                dates = extract_dates_from_filename(basename)
                if len(dates) < 2:
                    logging.warning(f"  Could not extract date pair from {basename}. Skipping.")
                    continue

                master_date = dates[0]
                slave_date = dates[1]

                results.append({
                    'master_date': master_date,
                    'slave_date': slave_date,
                    'phase_rad': mean_phase_rad,
                    'los_displacement_m': displacement_m,
                    'coherence': mean_coh,
                    'file': basename
                })

                logging.info(f"  Phase: {mean_phase_rad:.4f} rad -> "
                             f"LOS Displacement: {displacement_m * 1000:.2f} mm "
                             f"({master_date.date()} -> {slave_date.date()})")

        except Exception as e:
            logging.error(f"  Error reading phase for {basename}: {e}")

    results.sort(key=lambda r: r['master_date'])
    return results


# --- CSV EXPORT ---

def save_csv(results: List[Dict[str, Any]], output_path: str = "displacement_timeseries.csv") -> None:
    """Export displacement time-series results to a CSV file in RESULTS_DIR."""
    filepath = os.path.join(RESULTS_DIR, output_path)

    cumulative = 0.0
    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['master_date', 'slave_date', 'los_displacement_m',
                         'cumulative_displacement_m', 'coherence', 'source_file'])
        for r in results:
            cumulative += r['los_displacement_m']
            writer.writerow([
                r['master_date'].strftime('%Y-%m-%d'),
                r['slave_date'].strftime('%Y-%m-%d'),
                f"{r['los_displacement_m']:.6f}",
                f"{cumulative:.6f}",
                f"{r['coherence']:.4f}",
                r['file']
            ])

    logging.info(f"CSV saved to {filepath}")


# --- PLOTTING ---

def plot_cumulative_displacement(results: List[Dict[str, Any]]) -> None:
    """Plot cumulative LOS displacement time-series and save to RESULTS_DIR."""
    if not results:
        logging.warning("No data to plot.")
        return

    dates = [results[0]['master_date']]
    cumulative_values = [0.0]

    running_total = 0.0
    for r in results:
        running_total += r['los_displacement_m']
        dates.append(r['slave_date'])
        cumulative_values.append(running_total)

    cumulative_mm = [v * 1000 for v in cumulative_values]

    fig, ax = plt.subplots(figsize=(12, 6))

    ax.plot(dates, cumulative_mm, marker='o', linestyle='-', linewidth=2,
            color='#2563eb', label='Cumulative LOS Displacement')

    ax.axhline(0, color='gray', linestyle='--', linewidth=1)

    cum_arr = np.array(cumulative_mm)
    ax.fill_between(dates, cumulative_mm, 0,
                    where=(cum_arr >= 0), color='green', alpha=0.08, interpolate=True,
                    label='Uplift / Towards satellite')
    ax.fill_between(dates, cumulative_mm, 0,
                    where=(cum_arr < 0), color='red', alpha=0.08, interpolate=True,
                    label='Subsidence / Away from satellite')

    ax.set_title("Cumulative LOS Displacement — Mine Pit (Wrapped Phase)", fontsize=14)
    ax.set_xlabel("Date", fontsize=12)
    ax.set_ylabel("LOS Displacement (mm)\n(+ toward satellite, − subsidence)", fontsize=12)
    ax.grid(True, alpha=0.3)
    ax.legend(loc='best', fontsize=9)

    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    fig.autofmt_xdate(rotation=30)

    plot_path = os.path.join(RESULTS_DIR, "displacement_plot.png")
    plt.tight_layout()
    plt.savefig(plot_path, dpi=150)
    logging.info(f"Plot saved to {plot_path}")
    # plt.show() # Disabled for headless/pipeline execution


# --- ENTRY POINT ---

if __name__ == "__main__":
    logging.info("Starting displacement time-series analysis...")
    try:
        results = get_displacement_data()

        if results:
            save_csv(results)
            plot_cumulative_displacement(results)
        else:
            logging.warning("No valid displacement data collected. Nothing to plot or export.")

        logging.info("Done.")
    except Exception as e:
        logging.critical(f"Unhandled Exception: {e}")
        traceback.print_exc()

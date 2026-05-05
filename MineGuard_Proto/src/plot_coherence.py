"""
plot_coherence.py — InSAR Coherence Time-Series Analysis

Automatically detects the mining pit region (lowest coherence area),
samples a 5×5 window around it, and plots mean coherence over time.
Exports results to CSV.
"""

import os
import re
import csv
import glob
import logging
import sys
import traceback
from datetime import datetime
from typing import List, Dict, Any, Tuple

import numpy as np
import warnings
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

try:
    import rasterio
except ImportError:
    logging.critical("Error: rasterio not installed. Please run: pip install rasterio")
    sys.exit(1)

try:
    from scipy.ndimage import uniform_filter
except ImportError:
    uniform_filter = None

# --- PATH CONFIGURATION ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
OUTPUT_INT_DIR = os.path.join(DATA_DIR, "output_int")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")

# --- CENTRAL CONFIG + LOGGING ---
sys.path.insert(0, PROJECT_ROOT)
from src.utils.config_loader import load_config
from src.utils.logging_setup import setup_logging

_cfg = load_config()
setup_logging("plot_coherence", _cfg)

os.makedirs(RESULTS_DIR, exist_ok=True)

# Sampling window half-size (5×5 window → half = 2)
WINDOW_HALF = 2


# --- PIT DETECTION ---

def _uniform_filter_fallback(data: np.ndarray, size: int = 5) -> np.ndarray:
    """Pure-numpy fallback for uniform (box) filtering when scipy is unavailable."""
    kernel = np.ones((size, size), dtype=np.float64) / (size * size)
    pad = size // 2
    padded = np.pad(data, pad, mode='reflect')
    out = np.zeros_like(data, dtype=np.float64)
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            out[i, j] = np.sum(padded[i:i + size, j:j + size] * kernel)
    return out


def find_pit_location(coherence_band: np.ndarray) -> Tuple[int, int]:
    """Detect the mine pit location as the pixel with lowest smoothed coherence."""
    valid = np.where(coherence_band > 0, coherence_band, np.nan)

    if uniform_filter is not None:
        smoothed = uniform_filter(np.nan_to_num(valid, nan=1.0), size=50)
    else:
        smoothed = _uniform_filter_fallback(np.nan_to_num(valid, nan=1.0), size=50)

    smoothed[np.isnan(valid)] = 1.0

    min_idx = np.unravel_index(np.argmin(smoothed), smoothed.shape)
    y, x = int(min_idx[0]), int(min_idx[1])
    logging.info(f"Detected pit location at pixel (x={x}, y={y}), smoothed coherence = {smoothed[y, x]:.4f}")
    return y, x


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


# --- COHERENCE SAMPLING ---

def sample_coherence_window(src: Any, y: int, x: int) -> Tuple[float, float]:
    """Sample mean and std-deviation of coherence in a window around (y, x)."""
    height, width = src.shape

    y_min = max(0, y - WINDOW_HALF)
    y_max = min(height, y + WINDOW_HALF + 1)
    x_min = max(0, x - WINDOW_HALF)
    x_max = min(width, x + WINDOW_HALF + 1)

    window = ((y_min, y_max), (x_min, x_max))
    data = src.read(1, window=window).astype(np.float64)

    valid = data[data > 0]
    if len(valid) == 0:
        return np.nan, np.nan

    return float(np.mean(valid)), float(np.std(valid))


# --- MAIN DATA COLLECTION ---

def get_coherence_data() -> List[Dict[str, Any]]:
    """Collect per-interferogram coherence measurements at the detected pit location."""
    dim_files = glob.glob(os.path.join(OUTPUT_INT_DIR, "*.dim"))
    if not dim_files:
        logging.warning(f"No .dim files found in {OUTPUT_INT_DIR}")
        return []

    results = []
    pit_y, pit_x = None, None

    for dim_file in dim_files:
        basename = os.path.basename(dim_file)
        data_dir = dim_file.replace('.dim', '.data')

        if not os.path.exists(data_dir):
            logging.warning(f"Data directory not found for {basename}")
            continue

        coh_files = glob.glob(os.path.join(data_dir, "coh_*.img"))
        if not coh_files:
            coh_files = glob.glob(os.path.join(data_dir, "coh_*.hdr"))
        if not coh_files:
            logging.warning(f"No coherence band found in {data_dir}")
            continue

        coh_path = coh_files[0]

        try:
            with rasterio.open(coh_path) as src:
                if pit_y is None or pit_x is None:
                    full_band = src.read(1).astype(np.float64)
                    pit_y, pit_x = find_pit_location(full_band)

                mean_coh, std_coh = sample_coherence_window(src, pit_y, pit_x)

                dates = extract_dates_from_filename(basename)
                if not dates:
                    logging.warning(f"Could not parse dates from {basename}, skipping.")
                    continue

                if len(dates) < 2:
                    logging.warning(f"Could not parse date pair from {basename}, skipping.")
                    continue

                ref_date = dates[1]  # Use slave date (end of interval) for plotting

                results.append({
                    'date': ref_date,
                    'coherence_mean': mean_coh,
                    'coherence_std': std_coh,
                    'file': basename
                })
                logging.info(f"Sampled {basename}: mean={mean_coh:.4f}, std={std_coh:.4f}, date={ref_date.date()}")

        except Exception as e:
            logging.error(f"Error reading {coh_path}: {e}")

    results.sort(key=lambda r: r['date'])
    return results


# --- CSV EXPORT ---

def save_csv(results: List[Dict[str, Any]], output_path: str = "coherence_timeseries.csv") -> None:
    """Export coherence time-series results to a CSV file in RESULTS_DIR."""
    filepath = os.path.join(RESULTS_DIR, output_path)
    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['date', 'coherence_mean', 'coherence_std', 'source_file'])
        for r in results:
            writer.writerow([
                r['date'].strftime('%Y-%m-%d'),
                f"{r['coherence_mean']:.6f}",
                f"{r['coherence_std']:.6f}",
                r['file']
            ])
    logging.info(f"CSV saved to {filepath}")


# --- PLOTTING ---

def plot_results(results: List[Dict[str, Any]]) -> None:
    """Plot coherence time-series with error bars and save to RESULTS_DIR."""
    if not results:
        logging.warning("No data to plot.")
        return

    dates = [r['date'] for r in results]
    means = [r['coherence_mean'] for r in results]
    stds = [r['coherence_std'] for r in results]

    fig, ax = plt.subplots(figsize=(12, 6))

    ax.errorbar(dates, means, yerr=stds, marker='o', linestyle='-',
                color='#2563eb', ecolor='#93c5fd', capsize=4,
                label='Mean Coherence ± σ')

    ax.set_title("Mine Pit Stability — InSAR Coherence Time-Series", fontsize=14)
    ax.set_xlabel("Acquisition Date", fontsize=12)
    ax.set_ylabel("Coherence (0–1)", fontsize=12)
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)
    ax.legend(loc='upper right')

    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    fig.autofmt_xdate(rotation=30)

    plot_path = os.path.join(RESULTS_DIR, "coherence_plot.png")
    plt.tight_layout()
    plt.savefig(plot_path, dpi=150)
    logging.info(f"Plot saved to {plot_path}")
    # plt.show() # Disabled for headless execution


# --- ENTRY POINT ---

if __name__ == "__main__":
    logging.info("Starting coherence time-series analysis...")
    try:
        results = get_coherence_data()

        if results:
            save_csv(results)
            plot_results(results)
        else:
            logging.warning("No coherence data collected. Nothing to plot or export.")

        logging.info("Done.")
    except Exception as e:
        logging.critical(f"Unhandled Exception: {e}")
        traceback.print_exc()

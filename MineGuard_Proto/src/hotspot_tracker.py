"""hotspot_tracker.py — Interactive Hotspot Selection & Multi-Point Tracking

Provides an interactive workflow for mine pit monitoring:
  1. Displays a coherence preview image of the site
  2. User clicks to mark hotspot locations on the image
  3. Extracts displacement time-series at each hotspot across all interferograms
  4. Plots combined multi-hotspot displacement graph
  5. Detects displacement spikes and flags landslide warnings
  6. Exports hotspot report to CSV
"""

import os
import sys
import csv
import glob
import json
import re
import logging
import warnings
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional

import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

warnings.filterwarnings("ignore", category=UserWarning)
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
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")

# --- CENTRAL CONFIG + LOGGING ---
sys.path.insert(0, PROJECT_ROOT)
from src.utils.config_loader import load_config
from src.utils.logging_setup import setup_logging

_cfg = load_config()
setup_logging("hotspot_tracker", _cfg)

os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(CONFIG_DIR, exist_ok=True)

# Constants
WAVELENGTH_M: float = 0.05546
WINDOW_HALF: int = 2
HOTSPOTS_FILE = os.path.join(CONFIG_DIR, "hotspots.json")
MAX_HOTSPOTS: int = 10

# Hotspot marker colours for plots
HOTSPOT_COLORS = [
    '#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6',
    '#1abc9c', '#e67e22', '#34495e', '#e91e63', '#00bcd4',
]


def extract_dates_from_filename(filename: str) -> List[datetime]:
    """Extract acquisition dates from a Sentinel-1 product filename.

    Args:
        filename: Interferogram filename containing date strings.

    Returns:
        Sorted list of parsed datetime objects.
    """
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


def get_interferogram_list() -> List[Dict[str, Any]]:
    """Discover all interferogram .dim files and extract their date pairs.

    Returns:
        Sorted list of dicts with 'basename', 'data_dir', 'master_date', 'slave_date'.
    """
    dim_files = sorted(glob.glob(os.path.join(OUTPUT_INT_DIR, "*.dim")))
    results = []

    for dim_file in dim_files:
        basename = os.path.basename(dim_file).replace('.dim', '')
        data_dir = dim_file.replace('.dim', '.data')

        if not os.path.exists(data_dir):
            continue

        dates = extract_dates_from_filename(basename)
        if len(dates) >= 2:
            results.append({
                'basename': basename,
                'data_dir': data_dir,
                'master_date': dates[0],
                'slave_date': dates[-1],
            })

    results.sort(key=lambda r: r['master_date'])
    return results


def _load_tie_points(data_dir: str) -> Optional[Tuple[np.ndarray, np.ndarray, Tuple[int, int]]]:
    """Load lat/lon tie-point grids and the full-resolution image shape.

    Args:
        data_dir: Path to the .data directory of an interferogram.

    Returns:
        (lat_grid, lon_grid, (img_height, img_width)) or None on error.
    """
    tp_dir = os.path.join(data_dir, "tie_point_grids")
    lat_path = os.path.join(tp_dir, "latitude.img")
    lon_path = os.path.join(tp_dir, "longitude.img")

    if not os.path.exists(lat_path) or not os.path.exists(lon_path):
        return None

    try:
        with rasterio.open(lat_path) as src:
            lat_grid = src.read(1).astype(np.float64)
        with rasterio.open(lon_path) as src:
            lon_grid = src.read(1).astype(np.float64)

        # Get full image shape from coherence or ifg band
        coh_files = glob.glob(os.path.join(data_dir, "coh_*.img"))
        if coh_files:
            with rasterio.open(coh_files[0]) as src:
                img_shape = src.read(1).shape
        else:
            img_shape = (4176, 5458)  # Fallback

        return lat_grid, lon_grid, img_shape
    except Exception as exc:
        logging.warning("Failed to load tie points: %s", exc)
        return None


def _geo_to_pixel(
    click_lat: float,
    click_lon: float,
    lat_grid: np.ndarray,
    lon_grid: np.ndarray,
    img_shape: Tuple[int, int],
) -> Tuple[int, int]:
    """Convert geographic coordinates to radar pixel coordinates.

    Uses the tie-point grid to find the closest matching pixel via
    bilinear interpolation of the sparse grid to the full image space.

    Args:
        click_lat: Latitude of the clicked point.
        click_lon: Longitude of the clicked point.
        lat_grid: Sparse latitude tie-point grid.
        lon_grid: Sparse longitude tie-point grid.
        img_shape: (height, width) of the full-resolution radar image.

    Returns:
        (pixel_x, pixel_y) in the full-resolution image.
    """
    from scipy.interpolate import RectBivariateSpline

    tp_h, tp_w = lat_grid.shape
    img_h, img_w = img_shape

    # Tie-point grid indices
    tp_rows = np.linspace(0, img_h - 1, tp_h)
    tp_cols = np.linspace(0, img_w - 1, tp_w)

    # Interpolate lat/lon to full resolution
    lat_interp = RectBivariateSpline(tp_rows, tp_cols, lat_grid)
    lon_interp = RectBivariateSpline(tp_rows, tp_cols, lon_grid)

    # Search for closest pixel by evaluating on a coarse grid first
    search_rows = np.linspace(0, img_h - 1, min(500, img_h))
    search_cols = np.linspace(0, img_w - 1, min(500, img_w))

    lat_full = lat_interp(search_rows, search_cols)
    lon_full = lon_interp(search_rows, search_cols)

    # Distance from clicked point
    dist = (lat_full - click_lat)**2 + (lon_full - click_lon)**2
    min_idx = np.unravel_index(np.argmin(dist), dist.shape)

    pixel_y = int(round(search_rows[min_idx[0]]))
    pixel_x = int(round(search_cols[min_idx[1]]))

    return pixel_x, pixel_y


def _download_satellite_basemap(
    lat_center: float,
    lon_center: float,
    lat_extent: Tuple[float, float],
    lon_extent: Tuple[float, float],
    output_path: str,
    width: int = 1024,
    height: int = 768,
) -> Optional[str]:
    """Download a satellite basemap image from Esri World Imagery.

    Args:
        lat_center: Center latitude.
        lon_center: Center longitude.
        lat_extent: (min_lat, max_lat).
        lon_extent: (min_lon, max_lon).
        output_path: Path to save the downloaded image.
        width: Image width in pixels.
        height: Image height in pixels.

    Returns:
        Path to saved image, or None on error.
    """
    import requests

    # Esri World Imagery export endpoint (no API key needed)
    bbox = f"{lon_extent[0]},{lat_extent[0]},{lon_extent[1]},{lat_extent[1]}"
    url = (
        "https://services.arcgisonline.com/arcgis/rest/services/"
        "World_Imagery/MapServer/export"
    )
    params = {
        'bbox': bbox,
        'bboxSR': '4326',
        'imageSR': '4326',
        'size': f'{width},{height}',
        'format': 'png',
        'f': 'image',
    }

    try:
        logging.info("Downloading satellite basemap from Esri World Imagery...")
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()

        with open(output_path, 'wb') as fh:
            fh.write(resp.content)

        logging.info("Satellite basemap saved to %s (%d bytes)", output_path, len(resp.content))
        return output_path

    except Exception as exc:
        logging.warning("Failed to download satellite basemap: %s", exc)
        return None


def interactive_select_hotspots(
    ifg_list: List[Dict[str, Any]],
) -> List[Tuple[int, int]]:
    """Display a satellite basemap of the mine site, let user click hotspots,
    and convert geographic coordinates to radar pixel coordinates.

    Args:
        ifg_list: List of interferogram metadata dicts.

    Returns:
        List of (pixel_x, pixel_y) coordinates in the radar image.
    """
    matplotlib.use('TkAgg')

    # Load tie-point grids for coordinate mapping
    tp_data = None
    for ifg in ifg_list:
        tp_data = _load_tie_points(ifg['data_dir'])
        if tp_data is not None:
            break

    if tp_data is None:
        logging.error("No tie-point grids found. Cannot show basemap.")
        return []

    lat_grid, lon_grid, img_shape = tp_data
    lat_min, lat_max = float(lat_grid.min()), float(lat_grid.max())
    lon_min, lon_max = float(lon_grid.min()), float(lon_grid.max())

    # Zoom to mine site area (+/- 0.03 degrees ~ 3km)
    roi = _cfg.get("roi", {})
    mine_lat = roi.get("lat", 20.96)
    mine_lon = roi.get("lon", 85.09)
    zoom_margin = 0.03

    view_lat = (mine_lat - zoom_margin, mine_lat + zoom_margin)
    view_lon = (mine_lon - zoom_margin, mine_lon + zoom_margin)

    # Download satellite basemap
    basemap_path = os.path.join(RESULTS_DIR, "_satellite_basemap.png")
    result = _download_satellite_basemap(
        mine_lat, mine_lon,
        lat_extent=view_lat,
        lon_extent=view_lon,
        output_path=basemap_path,
        width=1280,
        height=960,
    )

    if result is None:
        logging.warning("Basemap download failed. Falling back to coherence image.")
        # Fallback to coherence
        fallback = _load_coherence_preview(ifg_list)
        if fallback is None:
            return []
        fig, ax = plt.subplots(figsize=(14, 10))
        ax.imshow(fallback, cmap='gray', vmin=0, vmax=0.5, aspect='auto')
        ax.set_title("Click hotspots (coherence fallback)", fontsize=12)
        points = plt.ginput(n=MAX_HOTSPOTS, timeout=0, show_clicks=True)
        plt.close()
        return [(int(round(x)), int(round(y))) for x, y in points]

    # Load and display satellite basemap
    basemap_img = plt.imread(basemap_path)

    fig, ax = plt.subplots(figsize=(14, 10))
    ax.imshow(
        basemap_img,
        extent=[view_lon[0], view_lon[1], view_lat[0], view_lat[1]],
        aspect='auto',
    )

    # Mark mine center
    ax.plot(mine_lon, mine_lat, 'r+', markersize=15, markeredgewidth=2)

    ax.set_title(
        f"SATELLITE VIEW - Click up to {MAX_HOTSPOTS} hotspots, then close window.\n"
        f"Mine site: Lat {mine_lat:.4f}, Lon {mine_lon:.4f}",
        fontsize=13, fontweight='bold',
    )
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")

    logging.info("Opening satellite basemap for hotspot selection...")
    logging.info("Click up to %d points, then close the window.", MAX_HOTSPOTS)

    points = plt.ginput(n=MAX_HOTSPOTS, timeout=0, show_clicks=True)
    plt.close()

    if not points:
        return []

    # We now save geographic coordinates so they can be mapped to different master geometries later.
    hotspots: List[Dict[str, float]] = []
    for click_lon, click_lat in points:
        logging.info(
            "  Clicked Geographic -> Lat: %.4f, Lon: %.4f",
            click_lat, click_lon
        )
        hotspots.append({'lat': click_lat, 'lon': click_lon})

    logging.info("Selected %d hotspot(s).", len(hotspots))
    return hotspots


def _load_coherence_preview(ifg_list: List[Dict[str, Any]]) -> Optional[np.ndarray]:
    """Fallback: load coherence band as preview if basemap download fails.

    Args:
        ifg_list: List of interferogram metadata dicts.

    Returns:
        2D numpy array, or None.
    """
    for ifg in ifg_list:
        coh_files = glob.glob(os.path.join(ifg['data_dir'], "coh_*.img"))
        if coh_files:
            try:
                with rasterio.open(coh_files[0]) as src:
                    return src.read(1).astype(np.float64)
            except Exception:
                continue
    return None


def save_hotspots(hotspots: List[Dict[str, float]]) -> None:
    """Save hotspot coordinates to config/hotspots.json.

    Args:
        hotspots: List of dicts with 'lat', 'lon'.
    """
    data = [{'lat': hs['lat'], 'lon': hs['lon'], 'label': f"Hotspot {i+1}"} for i, hs in enumerate(hotspots)]
    with open(HOTSPOTS_FILE, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2)
    logging.info("Hotspots saved to %s", HOTSPOTS_FILE)


def load_hotspots() -> List[Dict[str, Any]]:
    """Load hotspot coordinates from config/hotspots.json.

    Returns:
        List of hotspot dicts with 'lat', 'lon', 'label', and possibly 'x', 'y' for older configs.
    """
    if not os.path.exists(HOTSPOTS_FILE):
        return []

    with open(HOTSPOTS_FILE, 'r', encoding='utf-8') as fh:
        return json.load(fh)


def sample_displacement_at_point(
    data_dir: str,
    x: int,
    y: int,
    half_window: int = WINDOW_HALF,
) -> Optional[float]:
    """Extract mean displacement from a window around (x, y) in an interferogram.

    Computes phase as atan2(q_ifg, i_ifg) from the real/imaginary bands.

    Args:
        data_dir: Path to the .data directory.
        x, y: Pixel coordinates.
        half_window: Half-size of the sampling window.

    Returns:
        Mean LOS displacement in metres, or None on error.
    """
    try:
        # Find i_ifg and q_ifg bands
        i_files = glob.glob(os.path.join(data_dir, "i_ifg_*.img"))
        q_files = glob.glob(os.path.join(data_dir, "q_ifg_*.img"))

        if not i_files or not q_files:
            return None

        with rasterio.open(i_files[0]) as src_i:
            real_band = src_i.read(1).astype(np.float64)
        with rasterio.open(q_files[0]) as src_q:
            imag_band = src_q.read(1).astype(np.float64)

        h, w = real_band.shape

        y_min = max(0, y - half_window)
        y_max = min(h, y + half_window + 1)
        x_min = max(0, x - half_window)
        x_max = min(w, x + half_window + 1)

        real_win = real_band[y_min:y_max, x_min:x_max]
        imag_win = imag_band[y_min:y_max, x_min:x_max]

        # Compute phase from complex interferogram
        phase_win = np.arctan2(imag_win, real_win)

        # Exclude zero-amplitude pixels (no data)
        amplitude = np.sqrt(real_win**2 + imag_win**2)
        valid_mask = amplitude > 0
        valid_phase = phase_win[valid_mask]

        if len(valid_phase) == 0:
            return None

        mean_phase = float(np.mean(valid_phase))
        displacement = (mean_phase * WAVELENGTH_M) / (-4.0 * np.pi)
        return displacement

    except Exception:
        return None


def track_hotspots(
    hotspots: List[Dict[str, Any]],
    ifg_list: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Track displacement at each hotspot across all interferograms.

    Args:
        hotspots: List of hotspot dicts with 'x', 'y', 'label'.
        ifg_list: Sorted list of interferogram metadata.

    Returns:
        Dict mapping hotspot label to list of time-series records.
    """
    results: Dict[str, List[Dict[str, Any]]] = {}

    for hs in hotspots:
        label = hs['label']
        # Fallback for old configs that stored x,y instead of lat,lon
        lat = hs.get('lat')
        lon = hs.get('lon')
        orig_x = hs.get('x')
        orig_y = hs.get('y')
        
        cumulative = 0.0
        time_series: List[Dict[str, Any]] = []

        logging.info("Tracking %s (Lat: %s, Lon: %s)...", label, lat, lon)

        for ifg in ifg_list:
            tp_data = _load_tie_points(ifg['data_dir'])
            if tp_data is None:
                logging.warning("  No tie points for %s", ifg['basename'])
                continue
                
            lat_grid, lon_grid, img_shape = tp_data
            
            if lat is not None and lon is not None:
                x, y = _geo_to_pixel(lat, lon, lat_grid, lon_grid, img_shape)
            else:
                x, y = orig_x, orig_y
                
            disp = sample_displacement_at_point(ifg['data_dir'], x, y)
            if disp is None:
                logging.warning("  No valid active data for %s in %s at mapped pixel (%s, %s)", label, ifg['basename'], x, y)
                continue

            cumulative += disp
            record = {
                'date': ifg['slave_date'],
                'master_date': ifg['master_date'],
                'incremental_mm': disp * 1000,
                'cumulative_mm': cumulative * 1000,
                'basename': ifg['basename'],
                'mapped_x': x,
                'mapped_y': y,
            }
            time_series.append(record)

            logging.info(
                "  %s -> %s: incremental=%.2f mm, cumulative=%.2f mm",
                ifg['master_date'].strftime('%Y-%m-%d'),
                ifg['slave_date'].strftime('%Y-%m-%d'),
                disp * 1000,
                cumulative * 1000,
            )

        results[label] = time_series

    return results


def detect_spikes(
    time_series: List[Dict[str, Any]],
    threshold_factor: float = 2.0,
) -> List[Dict[str, Any]]:
    """Flag displacement spikes (sudden jumps) in a hotspot time-series.

    A spike is defined as an incremental displacement > threshold_factor
    times the mean incremental displacement.

    Args:
        time_series: List of time-series records for one hotspot.
        threshold_factor: Multiplier for spike detection.

    Returns:
        Updated time-series records with 'warning' flag.
    """
    if len(time_series) < 2:
        for rec in time_series:
            rec['warning'] = False
        return time_series

    increments = [abs(rec['incremental_mm']) for rec in time_series]
    mean_incr = np.mean(increments)
    threshold = mean_incr * threshold_factor

    for rec in time_series:
        if abs(rec['incremental_mm']) > threshold and threshold > 0:
            rec['warning'] = True
            logging.warning(
                "  SPIKE DETECTED at %s: %.2f mm (threshold: %.2f mm)",
                rec['date'].strftime('%Y-%m-%d'),
                rec['incremental_mm'],
                threshold,
            )
        else:
            rec['warning'] = False

    return time_series


def plot_combined_timeseries(
    tracking_results: Dict[str, List[Dict[str, Any]]],
    output_path: str,
) -> None:
    """Plot combined multi-hotspot displacement time-series.

    Args:
        tracking_results: Dict mapping hotspot label to time-series.
        output_path: Path to save the PNG.
    """
    fig, ax = plt.subplots(figsize=(14, 8))

    for i, (label, series) in enumerate(tracking_results.items()):
        if not series:
            continue

        # Add origin point
        dates = [series[0]['master_date']] + [r['date'] for r in series]
        cumulative = [0.0] + [r['cumulative_mm'] for r in series]
        color = HOTSPOT_COLORS[i % len(HOTSPOT_COLORS)]

        ax.plot(dates, cumulative, 'o-', color=color, label=label,
                linewidth=2, markersize=6)

        # Mark spikes with red triangles
        for j, rec in enumerate(series):
            if rec.get('warning', False):
                ax.plot(
                    rec['date'], rec['cumulative_mm'],
                    '^', color='red', markersize=12, zorder=5,
                    markeredgecolor='darkred', markeredgewidth=1.5,
                )

    # Reference line at zero
    ax.axhline(y=0, color='gray', linestyle='--', linewidth=0.8, alpha=0.5)

    # Shading
    ax.fill_between(
        ax.get_xlim(), 0, ax.get_ylim()[0],
        color='#fee2e2', alpha=0.3, label='Subsidence zone',
    )

    ax.set_title("Multi-Hotspot Displacement Tracking - Mine Pit Stability", fontsize=14, fontweight='bold')
    ax.set_xlabel("Date", fontsize=12)
    ax.set_ylabel("Cumulative LOS Displacement (mm)", fontsize=12)
    ax.legend(loc='lower left', fontsize=10)
    ax.grid(True, alpha=0.3)

    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    fig.autofmt_xdate(rotation=30)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    logging.info("Combined hotspot time-series saved to %s", output_path)


def export_hotspot_report(
    tracking_results: Dict[str, List[Dict[str, Any]]],
    output_path: str,
) -> None:
    """Export hotspot tracking results to CSV.

    Args:
        tracking_results: Dict mapping hotspot label to time-series.
        output_path: Path to save the CSV.
    """
    with open(output_path, 'w', newline='', encoding='utf-8') as fh:
        writer = csv.writer(fh)
        writer.writerow([
            'hotspot', 'pixel_x', 'pixel_y',
            'master_date', 'slave_date',
            'incremental_mm', 'cumulative_mm',
            'warning', 'source_file',
        ])

        for label, series in tracking_results.items():
            for rec in series:
                x = rec.get('mapped_x', 0)
                y = rec.get('mapped_y', 0)
                writer.writerow([
                    label, x, y,
                    rec['master_date'].strftime('%Y-%m-%d'),
                    rec['date'].strftime('%Y-%m-%d'),
                    f"{rec['incremental_mm']:.2f}",
                    f"{rec['cumulative_mm']:.2f}",
                    rec.get('warning', False),
                    rec['basename'],
                ])

    logging.info("Hotspot report saved to %s", output_path)


def main() -> None:
    """Run the complete hotspot tracking workflow."""
    logging.info("Starting hotspot tracker...")

    # Discover interferograms
    ifg_list = get_interferogram_list()
    if not ifg_list:
        logging.warning("No interferograms found in %s", OUTPUT_INT_DIR)
        return

    logging.info("Found %d interferogram(s) spanning %s to %s",
                 len(ifg_list),
                 ifg_list[0]['master_date'].strftime('%Y-%m-%d'),
                 ifg_list[-1]['slave_date'].strftime('%Y-%m-%d'))

    # Check for existing hotspots or do interactive selection
    hotspots_data = load_hotspots()

    if hotspots_data:
        logging.info("Loaded %d existing hotspot(s) from %s", len(hotspots_data), HOTSPOTS_FILE)
        response = input("Use existing hotspots? (y/n): ").strip().lower()
        if response != 'y':
            hotspots_data = []

    if not hotspots_data:
        # Interactive selection with satellite basemap
        coords = interactive_select_hotspots(ifg_list)
        if not coords:
            logging.warning("No hotspots selected. Exiting.")
            return

        save_hotspots(coords)
        hotspots_data = load_hotspots()

    # Track each hotspot across all interferograms
    tracking_results = track_hotspots(hotspots_data, ifg_list)

    # Spike detection
    for label in tracking_results:
        tracking_results[label] = detect_spikes(tracking_results[label])

    # Generate combined plot
    plot_combined_timeseries(
        tracking_results,
        output_path=os.path.join(RESULTS_DIR, "hotspot_timeseries.png"),
    )

    # Export report
    export_hotspot_report(
        tracking_results,
        output_path=os.path.join(RESULTS_DIR, "hotspot_report.csv"),
    )

    # Summary
    logging.info("=== HOTSPOT SUMMARY ===")
    for label, series in tracking_results.items():
        if not series:
            continue
        final_disp = series[-1]['cumulative_mm']
        n_warnings = sum(1 for r in series if r.get('warning', False))
        status = "WARNING" if n_warnings > 0 else "OK"
        logging.info(
            "  %s: cumulative=%.2f mm, warnings=%d [%s]",
            label, final_disp, n_warnings, status,
        )

    logging.info("Hotspot tracking complete.")


if __name__ == "__main__":
    main()

"""advanced_analysis.py — Phase Unwrapping, Direction Decomposition & 3D Visualization

Addresses the key limitations of the basic hotspot tracker:
  1. Phase unwrapping → true displacement (no ±13.9 mm cap)
  2. Gradient-based direction decomposition → geographic bearing (N/S/E/W)
  3. Vertical vs horizontal decomposition using incidence angle
  4. 3D visualization of magnitude + direction per hotspot
"""

import os
import sys
import csv
import glob
import json
import re
import math
import logging
import warnings
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import cm
from mpl_toolkits.mplot3d import Axes3D

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

try:
    import rasterio
    from scipy.ndimage import gaussian_filter
    from scipy.interpolate import RectBivariateSpline
    from skimage.restoration import unwrap_phase
except ImportError as exc:
    logging.critical("Missing library: %s", exc)
    logging.critical("Run: pip install rasterio scipy scikit-image")
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
setup_logging("advanced_analysis", _cfg)

os.makedirs(RESULTS_DIR, exist_ok=True)

# Constants
WAVELENGTH_M: float = 0.05546
WINDOW_HALF: int = 5  # Larger window for gradient stability
HOTSPOTS_FILE = os.path.join(CONFIG_DIR, "hotspots.json")

HOTSPOT_COLORS = [
    '#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6',
    '#1abc9c', '#e67e22', '#34495e', '#e91e63', '#00bcd4',
]


# =====================================================================
# DATA LOADING
# =====================================================================

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


def load_hotspots() -> List[Dict[str, Any]]:
    """Load hotspot coordinates from config/hotspots.json.

    Returns:
        List of hotspot dicts with 'x', 'y', 'label'.
    """
    if not os.path.exists(HOTSPOTS_FILE):
        logging.error("No hotspots file found at %s. Run hotspot_tracker.py first.", HOTSPOTS_FILE)
        return []
    with open(HOTSPOTS_FILE, 'r', encoding='utf-8') as fh:
        return json.load(fh)


# =====================================================================
# PHASE UNWRAPPING
# =====================================================================

def compute_unwrapped_displacement(data_dir: str, mapped_hotspots: List[Dict[str, Any]]) -> Optional[np.ndarray]:
    """Compute true LOS displacement using optimized local 2D phase unwrapping.
    
    To prevent infinite CPU hangs, this computes a tight bounding box around the 
    user-selected hotspots + 100px buffer, and only unwraps that specific region.
    
    Args:
        data_dir: Path to the .data directory of an interferogram.
        mapped_hotspots: List of parsed hotspot dicts containing 'x' and 'y' pixels.

    Returns:
        2D numpy array of unwrapped LOS displacement in metres, padded with NaNs.
    """
    i_files = glob.glob(os.path.join(data_dir, "i_ifg_*.img"))
    q_files = glob.glob(os.path.join(data_dir, "q_ifg_*.img"))

    if not i_files or not q_files:
        logging.warning("No i_ifg/q_ifg bands found in %s", data_dir)
        return None

    try:
        with rasterio.open(i_files[0]) as src:
            real_part = src.read(1).astype(np.float64)
        with rasterio.open(q_files[0]) as src:
            imag_part = src.read(1).astype(np.float64)

        # Calculate bounding box around hotspots
        h, w = real_part.shape
        xs = [hs['x'] for hs in mapped_hotspots]
        ys = [hs['y'] for hs in mapped_hotspots]
        if not xs or not ys:
            return None
            
        buffer_px = 100
        x_min = max(0, min(xs) - buffer_px)
        x_max = min(w, max(xs) + buffer_px + 1)
        y_min = max(0, min(ys) - buffer_px)
        y_max = min(h, max(ys) + buffer_px + 1)

        real_patch = real_part[y_min:y_max, x_min:x_max]
        imag_patch = imag_part[y_min:y_max, x_min:x_max]

        # Wrapped phase: [-π, +π]
        wrapped_phase_patch = np.arctan2(imag_patch, real_patch)

        # Mask no-data pixels (zero amplitude)
        amplitude_patch = np.sqrt(real_patch**2 + imag_patch**2)
        valid_mask_patch = amplitude_patch > 0

        # Clean NaNs
        wrapped_phase_clean = np.copy(wrapped_phase_patch)
        wrapped_phase_clean[~valid_mask_patch] = 0.0

        logging.info("  Unwrapping optimized 2D crop region (shape: %s)...", wrapped_phase_clean.shape)

        # 2D phase unwrapping locally
        unwrapped_patch = unwrap_phase(wrapped_phase_clean)
        unwrapped_patch[~valid_mask_patch] = np.nan

        # Convert to LOS displacement (metres)
        displacement_patch = (unwrapped_patch * WAVELENGTH_M) / (-4.0 * np.pi)

        # Re-embed into full-size array for downstream consistency
        full_displacement = np.full((h, w), np.nan, dtype=np.float64)
        full_displacement[y_min:y_max, x_min:x_max] = displacement_patch

        logging.info("  Phase unwrapped successfully in localized crop.")
        return full_displacement

    except Exception as exc:
        logging.error("Phase unwrapping failed for %s: %s", data_dir, exc)
        return None


# =====================================================================
# DIRECTION DECOMPOSITION
# =====================================================================

def load_tie_points(data_dir: str) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, Tuple[int, int]]]:
    """Load lat/lon/incidence tie-point grids.

    Args:
        data_dir: Path to the .data directory.

    Returns:
        (lat_grid, lon_grid, inc_angle_grid, (img_h, img_w)) or None.
    """
    tp_dir = os.path.join(data_dir, "tie_point_grids")
    lat_path = os.path.join(tp_dir, "latitude.img")
    lon_path = os.path.join(tp_dir, "longitude.img")
    inc_path = os.path.join(tp_dir, "incident_angle.img")

    if not os.path.exists(lat_path) or not os.path.exists(lon_path):
        return None

    try:
        with rasterio.open(lat_path) as src:
            lat = src.read(1).astype(np.float64)
        with rasterio.open(lon_path) as src:
            lon = src.read(1).astype(np.float64)

        inc = None
        if os.path.exists(inc_path):
            with rasterio.open(inc_path) as src:
                inc = src.read(1).astype(np.float64)

        # Get image shape
        coh_files = glob.glob(os.path.join(data_dir, "coh_*.img"))
        if coh_files:
            with rasterio.open(coh_files[0]) as src:
                shape = src.read(1).shape
        else:
            shape = (4176, 5458)

        return lat, lon, inc, shape
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
    """Convert geographic coordinates to radar pixel coordinates via grid interpolation."""
    tp_h, tp_w = lat_grid.shape
    img_h, img_w = img_shape

    tp_rows = np.linspace(0, img_h - 1, tp_h)
    tp_cols = np.linspace(0, img_w - 1, tp_w)

    lat_interp = RectBivariateSpline(tp_rows, tp_cols, lat_grid)
    lon_interp = RectBivariateSpline(tp_rows, tp_cols, lon_grid)

    search_rows = np.linspace(0, img_h - 1, min(500, img_h))
    search_cols = np.linspace(0, img_w - 1, min(500, img_w))

    lat_full = lat_interp(search_rows, search_cols)
    lon_full = lon_interp(search_rows, search_cols)

    dist = (lat_full - click_lat)**2 + (lon_full - click_lon)**2
    min_idx = np.unravel_index(np.argmin(dist), dist.shape)

    pixel_y = int(round(search_rows[min_idx[0]]))
    pixel_x = int(round(search_cols[min_idx[1]]))

    return pixel_x, pixel_y


def get_incidence_angle_at_pixel(
    x: int, y: int,
    inc_grid: Optional[np.ndarray],
    img_shape: Tuple[int, int],
) -> float:
    """Interpolate the incidence angle at a given pixel.

    Args:
        x, y: Pixel coordinates.
        inc_grid: Incidence angle tie-point grid.
        img_shape: Full image (height, width).

    Returns:
        Incidence angle in degrees.
    """
    if inc_grid is None:
        return 33.0  # Default IW1 mid-swath

    tp_h, tp_w = inc_grid.shape
    img_h, img_w = img_shape

    tp_rows = np.linspace(0, img_h - 1, tp_h)
    tp_cols = np.linspace(0, img_w - 1, tp_w)

    interp = RectBivariateSpline(tp_rows, tp_cols, inc_grid)
    return float(interp(y, x)[0, 0])


def get_geographic_bearing(
    x: int, y: int,
    lat_grid: np.ndarray,
    lon_grid: np.ndarray,
    img_shape: Tuple[int, int],
) -> Tuple[float, float]:
    """Get the azimuth rotation at a pixel position (image-to-geographic).

    Returns the approximate heading of the along-track (azimuth) and
    across-track (range) directions in geographic degrees.

    Args:
        x, y: Pixel coordinates.
        lat_grid, lon_grid: Tie-point grids.
        img_shape: Full image shape.

    Returns:
        (azimuth_bearing, range_bearing) in degrees from North.
    """
    tp_h, tp_w = lat_grid.shape
    img_h, img_w = img_shape

    tp_rows = np.linspace(0, img_h - 1, tp_h)
    tp_cols = np.linspace(0, img_w - 1, tp_w)

    lat_interp = RectBivariateSpline(tp_rows, tp_cols, lat_grid)
    lon_interp = RectBivariateSpline(tp_rows, tp_cols, lon_grid)

    # Sample lat/lon at this pixel and neighbours
    delta = 50  # pixels offset
    lat_c = float(lat_interp(y, x)[0, 0])
    lon_c = float(lon_interp(y, x)[0, 0])

    # Along azimuth (row direction)
    y2 = min(y + delta, img_h - 1)
    lat_a = float(lat_interp(y2, x)[0, 0])
    lon_a = float(lon_interp(y2, x)[0, 0])

    # Along range (column direction)
    x2 = min(x + delta, img_w - 1)
    lat_r = float(lat_interp(y, x2)[0, 0])
    lon_r = float(lon_interp(y, x2)[0, 0])

    # Azimuth bearing (row direction)
    az_bearing = math.degrees(math.atan2(lon_a - lon_c, lat_a - lat_c)) % 360

    # Range bearing (column direction)
    rg_bearing = math.degrees(math.atan2(lon_r - lon_c, lat_r - lat_c)) % 360

    return az_bearing, rg_bearing


def analyse_hotspot(
    displacement: np.ndarray,
    x: int, y: int,
    lat_grid: np.ndarray,
    lon_grid: np.ndarray,
    inc_grid: Optional[np.ndarray],
    img_shape: Tuple[int, int],
    half_window: int = WINDOW_HALF,
) -> Dict[str, Any]:
    """Analyse displacement at a single hotspot with direction decomposition.

    Args:
        displacement: 2D unwrapped displacement array (metres).
        x, y: Hotspot pixel coordinates.
        lat_grid, lon_grid: Tie-point grids.
        inc_grid: Incidence angle grid.
        img_shape: Full image shape.
        half_window: Sampling half-window.

    Returns:
        Dict with magnitude, direction, vertical/horizontal components.
    """
    h, w = displacement.shape

    y_min = max(0, y - half_window)
    y_max = min(h, y + half_window + 1)
    x_min = max(0, x - half_window)
    x_max = min(w, x + half_window + 1)

    window = displacement[y_min:y_max, x_min:x_max]
    valid = window[~np.isnan(window)]

    if len(valid) == 0:
        return {
            'los_displacement_mm': 0, 'vertical_mm': 0,
            'gradient_magnitude_mm': 0, 'flow_bearing_deg': 0,
            'flow_direction': 'N/A', 'incidence_angle_deg': 33.0,
            'gradient_x_mm': 0.0, 'gradient_y_mm': 0.0,
            'pixel_x': x, 'pixel_y': y,
        }

    los_disp_mm = float(np.mean(valid)) * 1000

    # Incidence angle at this pixel
    inc_angle = get_incidence_angle_at_pixel(x, y, inc_grid, img_shape)

    # Decompose LOS into Vertical
    # Assumption: Motion in the open-pit is predominantly vertical subsidence.
    inc_rad = math.radians(inc_angle)
    vertical_mm = los_disp_mm / math.cos(inc_rad)

    # Gradient for flow direction
    smoothed = gaussian_filter(displacement, sigma=3.0)
    grad_y, grad_x = np.gradient(smoothed)

    # Sample gradient at hotspot
    gx = float(np.nanmean(grad_x[y_min:y_max, x_min:x_max])) * 1000
    gy = float(np.nanmean(grad_y[y_min:y_max, x_min:x_max])) * 1000
    grad_mag = math.sqrt(gx**2 + gy**2)

    # Image-plane direction (radians)
    image_angle = math.atan2(-gy, gx)  # -gy because image y is inverted

    # Convert to geographic bearing using tie points
    _, rg_bearing = get_geographic_bearing(x, y, lat_grid, lon_grid, img_shape)

    # Rotate image direction by range bearing to get geographic bearing
    geo_bearing = (math.degrees(image_angle) + rg_bearing) % 360

    # Cardinal direction
    directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    idx = int(round(geo_bearing / 45)) % 8
    cardinal = directions[idx]

    return {
        'los_displacement_mm': round(los_disp_mm, 2),
        'vertical_mm': round(vertical_mm, 2),
        'gradient_magnitude_mm': round(grad_mag, 4),
        'flow_bearing_deg': round(geo_bearing, 1),
        'flow_direction': cardinal,
        'incidence_angle_deg': round(inc_angle, 1),
        'gradient_x_mm': round(gx, 4),
        'gradient_y_mm': round(gy, 4),
        'pixel_x': x,
        'pixel_y': y,
    }

def decompose_2d_displacement(
    los_asc: float,
    los_dsc: float,
    theta_asc_deg: float,
    theta_dsc_deg: float,
    alpha_asc_deg: float = 350.0,
    alpha_dsc_deg: float = 190.0
) -> Tuple[float, float]:
    """Decomposes Ascending and Descending LOS into East-West and Vertical.
    
    Formula: d_LOS = -sin(theta)cos(alpha) d_E + cos(theta) d_U
    (Ignoring North-South d_N due to S1 insensitivity)
    """
    t_a = math.radians(theta_asc_deg)
    t_d = math.radians(theta_dsc_deg)
    a_a = math.radians(alpha_asc_deg)
    a_d = math.radians(alpha_dsc_deg)

    # Coefficients for d_E and d_U
    ae1 = -math.sin(t_a) * math.cos(a_a)
    au1 = math.cos(t_a)
    ae2 = -math.sin(t_d) * math.cos(a_d)
    au2 = math.cos(t_d)

    # Solve 2x2
    det = ae1 * au2 - au1 * ae2
    if abs(det) < 1e-6:
        return 0.0, 0.0
        
    d_e = (au2 * los_asc - au1 * los_dsc) / det
    d_u = (-ae2 * los_asc + ae1 * los_dsc) / det
    
    return d_e, d_u



# =====================================================================
# VISUALIZATION — THREE OUTPUT PLOTS
# =====================================================================

def _date_to_year(dt: datetime) -> float:
    """Convert datetime to decimal year (e.g. 2018-06-04 → 2018.42)."""
    yday = (dt - datetime(dt.year, 1, 1)).days + 1
    return dt.year + (yday - 1) / 365.25


def _ew_and_vert_per_epoch(
    all_results: Dict[str, Dict[str, Dict[str, Any]]],
    ifg_list: List[Dict[str, Any]],
    dual_results: Optional[Dict[str, Any]],
    hotspot_labels: List[str],
) -> Tuple[List[datetime], Dict[str, List[float]], Dict[str, List[float]]]:
    """Return (epoch_dates, ew_per_epoch, vert_per_epoch) for every hotspot.

    When ASC+DSC dual-orbit decomposition results are available the true
    East-West and vertical components are returned directly.

    Single-orbit fallback:
      vertical = LOS / cos(θ)           (already stored in analyse_hotspot)
      E-W      = -sin(θ)·cos(α) · LOS  (LOS projected onto E-W direction)
        ASC heading α ≈ 350°, DSC heading α ≈ 190°
    """
    using_dual = bool(dual_results)

    if using_dual:
        sorted_pairs = sorted(dual_results.items(), key=lambda kv: kv[1]['date'])
        dates_out: List[datetime] = [p[1]['date'] for p in sorted_pairs]
        ew: Dict[str, List[float]] = {lbl: [] for lbl in hotspot_labels}
        vert: Dict[str, List[float]] = {lbl: [] for lbl in hotspot_labels}
        for _, pair_data in sorted_pairs:
            for lbl in hotspot_labels:
                d2d = pair_data['hotspots'].get(lbl)
                ew[lbl].append(d2d['east_west_mm'] if d2d else 0.0)
                vert[lbl].append(d2d['vertical_mm'] if d2d else 0.0)
        return dates_out, ew, vert

    # Single-orbit: one epoch per interferogram
    dates_out = [ifg['slave_date'] for ifg in ifg_list]
    ew = {lbl: [] for lbl in hotspot_labels}
    vert = {lbl: [] for lbl in hotspot_labels}

    for ifg in ifg_list:
        entry = all_results.get(ifg['basename'])
        orbit = entry['orbit'] if entry else 'ASC'
        alpha = 350.0 if orbit != 'DSC' else 190.0
        for lbl in hotspot_labels:
            data = entry['data'].get(lbl) if entry else None
            if data:
                theta = data['incidence_angle_deg']
                coeff_e = -math.sin(math.radians(theta)) * math.cos(math.radians(alpha))
                ew[lbl].append(coeff_e * data['los_displacement_mm'])
                vert[lbl].append(data['vertical_mm'])
            else:
                ew[lbl].append(0.0)
                vert[lbl].append(0.0)

    return dates_out, ew, vert


# ---- Plot 1: Horizontal (East-West) displacement per year ----

def plot_horizontal_displacement_per_year(
    all_results: Dict[str, Dict[str, Dict[str, Any]]],
    ifg_list: List[Dict[str, Any]],
    output_path: str,
    dual_results: Optional[Dict[str, Any]] = None,
) -> None:
    """Cumulative East-West (horizontal) displacement over time per hotspot.

    Uses proper 2×2 InSAR matrix decomposition when both ASC and DSC passes
    exist (d_LOS = −sin θ cos α · d_E + cos θ · d_U).  Falls back to the
    east-west LOS-projection component for single-orbit datasets.
    """
    hotspot_labels = sorted({lbl for e in all_results.values() for lbl in e['data']})
    if not hotspot_labels or not ifg_list:
        return

    using_dual = bool(dual_results)
    epoch_dates, ew_epochs, _ = _ew_and_vert_per_epoch(
        all_results, ifg_list, dual_results, hotspot_labels)

    start_date = ifg_list[0]['master_date']

    fig, ax = plt.subplots(figsize=(14, 8))
    fig.patch.set_facecolor('#0f172a')
    ax.set_facecolor('#0f172a')
    ax.grid(color='#334155', linestyle=':', linewidth=0.7, alpha=0.5)
    for sp in ('top', 'right'):
        ax.spines[sp].set_visible(False)
    for sp in ('bottom', 'left'):
        ax.spines[sp].set_color('#475569')
    ax.tick_params(colors='#94a3b8', labelsize=10)

    for hs_idx, lbl in enumerate(hotspot_labels):
        color = HOTSPOT_COLORS[hs_idx % len(HOTSPOT_COLORS)]
        dates_plot = [start_date] + epoch_dates
        running = 0.0
        cumul = [0.0]
        for v in ew_epochs[lbl]:
            running += v
            cumul.append(running)

        ax.plot(dates_plot, cumul, color=color, linewidth=2.5,
                marker='o', markersize=6, markerfacecolor='#0f172a',
                markeredgecolor=color, markeredgewidth=2, label=lbl)
        ax.annotate(f'{cumul[-1]:.1f} mm',
                    xy=(dates_plot[-1], cumul[-1]),
                    xytext=(10, 0), textcoords='offset points',
                    color=color, fontsize=9, fontweight='bold', va='center')

    ax.axhline(0, color='#475569', linestyle='--', linewidth=0.8, alpha=0.7)
    ax.set_ylabel('Cumulative E–W Displacement (mm)',
                  color='#e2e8f0', fontweight='bold', fontsize=12)
    ax.set_xlabel('Year', color='#94a3b8', fontsize=11)

    method = '2D Decomposition — ASC+DSC' if using_dual else 'Single-Orbit LOS Projection (approx.)'
    ax.set_title(f'HORIZONTAL (EAST–WEST) DISPLACEMENT PER YEAR\n[{method}]',
                 color='#e2e8f0', fontweight='bold', fontsize=14, pad=16, loc='left')

    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    plt.setp(ax.xaxis.get_majorticklabels(), color='#94a3b8', fontweight='bold')

    legend = ax.legend(loc='upper left', fontsize=10, framealpha=0.3,
                       facecolor='#1e293b', edgecolor='#475569', labelcolor='#e2e8f0')
    for t in legend.get_texts():
        t.set_fontweight('bold')

    if not using_dual:
        ax.text(0.99, 0.03,
                'NOTE: Horizontal isolated from single-orbit data only — '
                'dual orbit (ASC+DSC) preferred.',
                transform=ax.transAxes, fontsize=8, color='#f59e0b',
                ha='right', va='bottom', style='italic')

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight',
                facecolor=fig.get_facecolor(), transparent=False)
    plt.close()
    logging.info("Horizontal displacement plot saved to %s", output_path)


# ---- Plot 2: LOS displacement (per pair + cumulative) ----

def plot_los_displacement(
    all_results: Dict[str, Dict[str, Dict[str, Any]]],
    ifg_list: List[Dict[str, Any]],
    output_path: str,
) -> None:
    """2-panel LOS displacement chart.

    Top panel   — LOS displacement per interferometric pair (grouped bar chart).
    Bottom panel — Cumulative LOS displacement over time (line chart).

    LOS = Line-of-Sight: the raw InSAR measurement, i.e. the change in
    satellite-to-ground distance in mm along the ~33–40° look direction.
    Negative values indicate ground moving away from the satellite (subsidence).
    """
    hotspot_labels = sorted({lbl for e in all_results.values() for lbl in e['data']})
    if not hotspot_labels or not ifg_list:
        return

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 11))
    fig.patch.set_facecolor('#0f172a')

    def _style(ax: plt.Axes) -> None:
        ax.set_facecolor('#0f172a')
        ax.grid(color='#334155', linestyle=':', linewidth=0.7, alpha=0.5)
        for sp in ('top', 'right'):
            ax.spines[sp].set_visible(False)
        for sp in ('bottom', 'left'):
            ax.spines[sp].set_color('#475569')
        ax.tick_params(colors='#94a3b8', labelsize=9)

    _style(ax1)
    _style(ax2)

    # --- Top: per-pair grouped bar chart ---
    pair_labels = [
        f"{ifg['master_date'].strftime('%y-%m')}\n→{ifg['slave_date'].strftime('%y-%m')}"
        for ifg in ifg_list
    ]
    n_hs = len(hotspot_labels)
    n_pairs = len(ifg_list)
    bar_w = 0.7 / n_hs
    x_base = np.arange(n_pairs)

    for hs_idx, lbl in enumerate(hotspot_labels):
        vals = []
        for ifg in ifg_list:
            entry = all_results.get(ifg['basename'])
            data = entry['data'].get(lbl) if entry else None
            vals.append(data['los_displacement_mm'] if data else 0.0)

        color = HOTSPOT_COLORS[hs_idx % len(HOTSPOT_COLORS)]
        offset = (hs_idx - n_hs / 2 + 0.5) * bar_w
        ax1.bar(x_base + offset, vals, width=bar_w * 0.9,
                color=color, alpha=0.85, label=lbl,
                edgecolor='#0f172a', linewidth=0.4)

    ax1.axhline(0, color='#475569', linestyle='--', linewidth=0.8)
    ax1.set_xticks(x_base)
    ax1.set_xticklabels(pair_labels, color='#94a3b8', fontsize=8)
    ax1.set_ylabel('LOS Displacement (mm)', color='#e2e8f0', fontweight='bold')
    ax1.set_title('LOS DISPLACEMENT PER INTERFEROMETRIC PAIR',
                  color='#e2e8f0', fontweight='bold', fontsize=13, pad=12, loc='left')
    leg1 = ax1.legend(loc='upper left', fontsize=9, framealpha=0.3,
                      facecolor='#1e293b', edgecolor='#475569', labelcolor='#e2e8f0')
    for t in leg1.get_texts():
        t.set_fontweight('bold')

    # --- Bottom: cumulative LOS time series ---
    start_date = ifg_list[0]['master_date']
    for hs_idx, lbl in enumerate(hotspot_labels):
        dates_plot = [start_date]
        cumul = [0.0]
        running = 0.0
        for ifg in ifg_list:
            entry = all_results.get(ifg['basename'])
            data = entry['data'].get(lbl) if entry else None
            running += data['los_displacement_mm'] if data else 0.0
            dates_plot.append(ifg['slave_date'])
            cumul.append(running)

        color = HOTSPOT_COLORS[hs_idx % len(HOTSPOT_COLORS)]
        ax2.plot(dates_plot, cumul, color=color, linewidth=2.5,
                 marker='o', markersize=5, markerfacecolor='#0f172a',
                 markeredgecolor=color, markeredgewidth=2, label=lbl)
        ax2.annotate(f'{cumul[-1]:.1f} mm',
                     xy=(dates_plot[-1], cumul[-1]),
                     xytext=(8, 0), textcoords='offset points',
                     color=color, fontsize=9, fontweight='bold', va='center')

    ax2.axhline(0, color='#475569', linestyle='--', linewidth=0.8)
    ax2.set_ylabel('Cumulative LOS Displacement (mm)', color='#e2e8f0', fontweight='bold')
    ax2.set_xlabel('Year', color='#94a3b8', fontsize=11)
    ax2.set_title('CUMULATIVE LOS DISPLACEMENT OVER TIME',
                  color='#e2e8f0', fontweight='bold', fontsize=13, pad=12, loc='left')
    ax2.xaxis.set_major_locator(mdates.YearLocator())
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    plt.setp(ax2.xaxis.get_majorticklabels(), color='#94a3b8', fontweight='bold')
    leg2 = ax2.legend(loc='lower left', fontsize=9, framealpha=0.3,
                      facecolor='#1e293b', edgecolor='#475569', labelcolor='#e2e8f0')
    for t in leg2.get_texts():
        t.set_fontweight('bold')

    fig.text(0.5, 0.005,
             'LOS = Line-of-Sight.  Negative = ground moving away from satellite (subsidence/settlement).',
             ha='center', fontsize=8, color='#64748b', style='italic')

    plt.tight_layout(h_pad=3, rect=[0, 0.02, 1, 1])
    plt.savefig(output_path, dpi=150, bbox_inches='tight',
                facecolor=fig.get_facecolor(), transparent=False)
    plt.close()
    logging.info("LOS displacement plot saved to %s", output_path)


# ---- Plot 3: 3D trajectory ----

def plot_3d_trajectory(
    all_results: Dict[str, Dict[str, Dict[str, Any]]],
    ifg_list: List[Dict[str, Any]],
    output_path: str,
    dual_results: Optional[Dict[str, Any]] = None,
) -> None:
    """3-D trajectory of hotspot movement over the observation period.

    Axes
    ----
    X  — cumulative East-West displacement (mm); positive = eastward
    Y  — cumulative Vertical displacement (mm);  negative = subsidence
    Z  — time (decimal year)

    Each hotspot traces a coloured 3-D path originating at (0, 0, year₀).
    When ASC+DSC dual-orbit decomposition results are available the
    components are physically accurate; otherwise single-orbit approximations
    are used.
    """
    hotspot_labels = sorted({lbl for e in all_results.values() for lbl in e['data']})
    if not hotspot_labels or not ifg_list:
        return

    using_dual = bool(dual_results)
    epoch_dates, ew_epochs, vert_epochs = _ew_and_vert_per_epoch(
        all_results, ifg_list, dual_results, hotspot_labels)

    start_date = ifg_list[0]['master_date']
    t0 = _date_to_year(start_date)
    epoch_years = [_date_to_year(d) for d in epoch_dates]

    fig = plt.figure(figsize=(14, 10))
    fig.patch.set_facecolor('#0f172a')
    ax = fig.add_subplot(111, projection='3d')
    ax.set_facecolor('#0f172a')

    for pane in (ax.xaxis.pane, ax.yaxis.pane, ax.zaxis.pane):
        pane.fill = False
        pane.set_edgecolor('#1e3a5f')

    for axis_obj in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis_obj.label.set_color('#94a3b8')
        for tick in axis_obj.get_ticklabels():
            tick.set_color('#64748b')

    for hs_idx, lbl in enumerate(hotspot_labels):
        color = HOTSPOT_COLORS[hs_idx % len(HOTSPOT_COLORS)]

        ew_c, vert_c, time_c = [0.0], [0.0], [t0]
        ew_run = vert_run = 0.0

        for i, t_yr in enumerate(epoch_years):
            ew_run += ew_epochs[lbl][i]
            vert_run += vert_epochs[lbl][i]
            ew_c.append(ew_run)
            vert_c.append(vert_run)
            time_c.append(t_yr)

        ew_arr = np.array(ew_c)
        vert_arr = np.array(vert_c)
        time_arr = np.array(time_c)

        ax.plot3D(ew_arr, vert_arr, time_arr,
                  color=color, linewidth=2.5, alpha=0.9, label=lbl)
        ax.scatter(ew_arr, vert_arr, time_arr,
                   color=color, s=40, edgecolors='white', linewidths=0.7, zorder=5)
        # Origin marker
        ax.scatter([0.0], [0.0], [t0],
                   color=color, s=90, marker='D',
                   edgecolors='white', linewidths=1.2, zorder=6)
        # End-point label
        ax.text(ew_arr[-1], vert_arr[-1], time_arr[-1] + 0.05,
                f'{lbl}  (EW:{ew_arr[-1]:.0f}, V:{vert_arr[-1]:.0f} mm)',
                color=color, fontsize=8, fontweight='bold')

    # Zero-displacement reference planes (subtle shading)
    try:
        xl, yl, zl = ax.get_xlim(), ax.get_ylim(), ax.get_zlim()
        xx, zz = np.meshgrid([xl[0], xl[1]], [zl[0], zl[1]])
        ax.plot_surface(xx, np.zeros_like(xx), zz, alpha=0.05, color='#94a3b8')
        yy, zz2 = np.meshgrid([yl[0], yl[1]], [zl[0], zl[1]])
        ax.plot_surface(np.zeros_like(yy), yy, zz2, alpha=0.05, color='#94a3b8')
    except Exception:
        pass

    ax.set_xlabel('E–W Displacement (mm)\n← West   East →',
                  color='#94a3b8', fontsize=10, labelpad=12)
    ax.set_ylabel('Vertical Displacement (mm)\n↑ Up   Down ↓',
                  color='#94a3b8', fontsize=10, labelpad=12)
    ax.set_zlabel('Year', color='#94a3b8', fontsize=10, labelpad=8)

    method = '2D ASC+DSC Decomposition' if using_dual else 'Single-Orbit Approximation'
    ax.set_title(f'3D HOTSPOT DISPLACEMENT TRAJECTORY\n[{method}]',
                 color='#e2e8f0', fontweight='bold', fontsize=14, pad=20)

    legend = ax.legend(loc='upper left', fontsize=10, framealpha=0.3,
                       facecolor='#1e293b', edgecolor='#475569', labelcolor='#e2e8f0')
    for t in legend.get_texts():
        t.set_fontweight('bold')

    ax.view_init(elev=25, azim=-50)
    fig.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight',
                facecolor=fig.get_facecolor(), transparent=False)
    plt.close()
    logging.info("3D trajectory plot saved to %s", output_path)


# =====================================================================
# CSV REPORT
# =====================================================================

def write_report_csv(
    all_results: Dict[str, Dict[str, Dict[str, Any]]],
    ifg_list: List[Dict[str, Any]],
    dual_results: Optional[Dict[str, Any]],
    output_path: str,
) -> None:
    """Write the advanced_hotspot_report.csv consumed by the Dashboard summary API.

    Section 1: Per-interferogram single-orbit rows (all hotspots).
    Section 2: 2D ASC+DSC vector decomposition rows (when available).
    """
    hotspot_labels = sorted({lbl for e in all_results.values() for lbl in e['data']})
    if not hotspot_labels:
        return

    with open(output_path, 'w', newline='', encoding='utf-8') as fh:
        writer = csv.writer(fh)

        # --- Section 1: single-orbit rows ---
        writer.writerow([
            'hotspot', 'pixel_x', 'pixel_y',
            'master_date', 'slave_date', 'orbit_pass',
            'los_displacement_mm', 'vertical_approx_mm',
            'gradient_mag_mm', 'flow_bearing_deg',
            'flow_direction', 'incidence_angle_deg',
        ])

        for ifg in ifg_list:
            entry = all_results.get(ifg['basename'])
            if not entry:
                continue
            orbit = entry['orbit']
            for lbl in hotspot_labels:
                data = entry['data'].get(lbl)
                if not data:
                    continue
                writer.writerow([
                    lbl,
                    data['pixel_x'], data['pixel_y'],
                    ifg['master_date'].strftime('%Y-%m-%d'),
                    ifg['slave_date'].strftime('%Y-%m-%d'),
                    orbit,
                    round(data['los_displacement_mm'], 2),
                    round(data['vertical_mm'], 2),
                    round(data['gradient_magnitude_mm'], 4),
                    round(data['flow_bearing_deg'], 1),
                    data['flow_direction'],
                    round(data['incidence_angle_deg'], 1),
                ])

        # --- Section 2: 2D decomposition ---
        if dual_results:
            fh.write('\n--- 2D VECTOR DECOMPOSITION (ASC + DSC) ---\n')
            writer.writerow([
                'hotspot', 'approx_date',
                'true_vertical_mm', 'east_west_mm',
                'los_asc_mm', 'los_dsc_mm',
            ])

            sorted_pairs = sorted(dual_results.items(), key=lambda kv: kv[1]['date'])
            for _, pair_data in sorted_pairs:
                date_str = pair_data['date'].strftime('%Y-%m-%d')
                for lbl in hotspot_labels:
                    d2d = pair_data['hotspots'].get(lbl)
                    if not d2d:
                        continue
                    writer.writerow([
                        lbl, date_str,
                        d2d['vertical_mm'], d2d['east_west_mm'],
                        d2d['los_asc_mm'], d2d['los_dsc_mm'],
                    ])

    logging.info("Advanced report saved to %s", output_path)


# =====================================================================
# MAIN
# =====================================================================

def main() -> None:
    """Run the displacement analysis and generate the 3 required plots."""
    logging.info("=" * 60)
    logging.info("MINEGUARD DISPLACEMENT ANALYSIS")
    logging.info("  Phase unwrapping + 2D decomposition + 3 output plots")
    logging.info("=" * 60)

    ifg_list = get_interferogram_list()
    if not ifg_list:
        logging.error("No interferograms found in %s", OUTPUT_INT_DIR)
        return

    hotspots = load_hotspots()
    if not hotspots:
        logging.error("No hotspots found at %s", HOTSPOTS_FILE)
        return

    logging.info("Found %d interferogram(s), %d hotspot(s)", len(ifg_list), len(hotspots))

    # Remove any PNGs from previous runs so page 7 shows only the 3 new plots
    for old_png in glob.glob(os.path.join(RESULTS_DIR, "*.png")):
        try:
            os.remove(old_png)
        except OSError as exc:
            logging.warning("Could not remove old result %s: %s", old_png, exc)

    # ----------------------------------------------------------------
    # Per-interferogram: unwrap phase → analyse hotspots
    # ----------------------------------------------------------------
    all_results: Dict[str, Dict[str, Dict[str, Any]]] = {}

    for ifg in ifg_list:
        logging.info("")
        logging.info("Processing: %s", ifg['basename'])
        logging.info("  Period: %s → %s",
                     ifg['master_date'].strftime('%Y-%m-%d'),
                     ifg['slave_date'].strftime('%Y-%m-%d'))

        tp_data = load_tie_points(ifg['data_dir'])
        if tp_data is None:
            logging.error("  No tie-point grids for %s — skipped.", ifg['basename'])
            continue

        lat_grid, lon_grid, inc_grid, img_shape = tp_data

        mapped_hotspots = []
        for hs in hotspots:
            lbl = hs['label']
            lat, lon = hs.get('lat'), hs.get('lon')
            if lat is not None and lon is not None:
                px, py = _geo_to_pixel(lat, lon, lat_grid, lon_grid, img_shape)
            else:
                px, py = hs.get('x', 0), hs.get('y', 0)
            mapped_hotspots.append({'x': px, 'y': py, 'label': lbl, 'lat': lat, 'lon': lon})

        displacement = compute_unwrapped_displacement(ifg['data_dir'], mapped_hotspots)
        if displacement is None:
            continue

        ifg_results: Dict[str, Dict[str, Any]] = {}
        for hs in mapped_hotspots:
            result = analyse_hotspot(
                displacement, hs['x'], hs['y'],
                lat_grid, lon_grid, inc_grid, img_shape,
            )
            ifg_results[hs['label']] = result
            logging.info("  %s: LOS=%.2f mm, Vertical~%.2f mm, Direction=%.1f deg %s",
                         hs['label'], result['los_displacement_mm'],
                         result['vertical_mm'],
                         result['flow_bearing_deg'], result['flow_direction'])

        pass_type = ("ASC" if "_ASC_" in ifg['basename']
                     else "DSC" if "_DSC_" in ifg['basename']
                     else "UNKNOWN")
        all_results[ifg['basename']] = {
            'data':  ifg_results,
            'orbit': pass_type,
            'date':  ifg['slave_date'],
        }

    if not all_results:
        logging.error("No results produced — no interferograms could be processed.")
        return

    # ----------------------------------------------------------------
    # 2D decomposition: pair ASC and DSC results by date
    # ----------------------------------------------------------------
    logging.info("")
    logging.info("Attempting 2D decomposition (ASC + DSC)...")
    dual_orbit_results: Dict[str, Any] = {}

    asc_tracks = {r['date'].strftime('%Y%m%d'): r
                  for r in all_results.values() if r['orbit'] == 'ASC'}
    dsc_tracks = {r['date'].strftime('%Y%m%d'): r
                  for r in all_results.values() if r['orbit'] == 'DSC'}

    for date_str, asc_data in asc_tracks.items():
        target_date = datetime.strptime(date_str, '%Y%m%d')
        best_dsc = min(
            dsc_tracks.values(),
            key=lambda d: abs((target_date - d['date']).days),
            default=None,
        )
        if best_dsc is None or abs((target_date - best_dsc['date']).days) > 12:
            continue

        pair_label = f"2D_{date_str}"
        dual_orbit_results[pair_label] = {'date': target_date, 'hotspots': {}}

        for hs in hotspots:
            lbl = hs['label']
            r_a = asc_data['data'].get(lbl)
            r_d = best_dsc['data'].get(lbl)
            if r_a and r_d:
                d_e, d_u = decompose_2d_displacement(
                    r_a['los_displacement_mm'], r_d['los_displacement_mm'],
                    r_a['incidence_angle_deg'], r_d['incidence_angle_deg'],
                )
                dual_orbit_results[pair_label]['hotspots'][lbl] = {
                    'east_west_mm': round(d_e, 2),
                    'vertical_mm':  round(d_u, 2),
                    'los_asc_mm':   r_a['los_displacement_mm'],
                    'los_dsc_mm':   r_d['los_displacement_mm'],
                }

    if dual_orbit_results:
        logging.info("2D decomposition: %d matched ASC/DSC date(s).", len(dual_orbit_results))
    else:
        logging.info("No overlapping ASC/DSC pairs within 12 days — using single-orbit approximations.")

    dual = dual_orbit_results if dual_orbit_results else None

    # ----------------------------------------------------------------
    # Generate the 3 required plots
    # ----------------------------------------------------------------
    logging.info("")
    logging.info("Generating plots...")

    plot_horizontal_displacement_per_year(
        all_results, ifg_list,
        output_path=os.path.join(RESULTS_DIR, "plot_01_horizontal_displacement.png"),
        dual_results=dual,
    )

    plot_los_displacement(
        all_results, ifg_list,
        output_path=os.path.join(RESULTS_DIR, "plot_02_los_displacement.png"),
    )

    plot_3d_trajectory(
        all_results, ifg_list,
        output_path=os.path.join(RESULTS_DIR, "plot_03_3d_trajectory.png"),
        dual_results=dual,
    )

    # ----------------------------------------------------------------
    # Write CSV report (consumed by Dashboard / summary_api)
    # ----------------------------------------------------------------
    write_report_csv(
        all_results, ifg_list, dual,
        output_path=os.path.join(RESULTS_DIR, "advanced_hotspot_report.csv"),
    )

    # Clear stale summary cache so the Dashboard regenerates from fresh CSV
    summary_cache = os.path.join(RESULTS_DIR, "summary_cache.json")
    if os.path.exists(summary_cache):
        try:
            os.remove(summary_cache)
            logging.info("Cleared stale summary cache: %s", summary_cache)
        except OSError as exc:
            logging.warning("Could not remove summary cache: %s", exc)

    logging.info("")
    logging.info("=" * 60)
    logging.info("ANALYSIS COMPLETE - 3 plots + CSV report in: %s", RESULTS_DIR)
    logging.info("=" * 60)


if __name__ == "__main__":
    main()

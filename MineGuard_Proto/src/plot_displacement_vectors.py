"""plot_displacement_vectors.py — 2D Displacement Gradient Vector Field

Reads interferogram phase bands, converts to LOS displacement, computes
spatial gradients (dx, dy) to determine flow direction and magnitude,
and generates:
  - Quiver plot (arrow map) showing displacement flow direction
  - Strain rate heatmap (gradient magnitude — high values = failure risk)
  - CSV export of per-pixel vector data
"""

import os
import sys
import csv
import glob
import logging
import warnings
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

try:
    import rasterio
    from scipy.ndimage import uniform_filter, gaussian_filter
except ImportError:
    logging.critical("Error: Required libraries not installed.")
    logging.critical("Please run: pip install rasterio scipy")
    sys.exit(1)

# --- PATH CONFIGURATION ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
OUTPUT_INT_DIR = os.path.join(DATA_DIR, "output_int")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")

# --- CENTRAL CONFIG + LOGGING ---
sys.path.insert(0, PROJECT_ROOT)
from src.utils.config_loader import load_config
from src.utils.logging_setup import setup_logging

_cfg = load_config()
setup_logging("plot_displacement_vectors", _cfg)

os.makedirs(RESULTS_DIR, exist_ok=True)

# Sentinel-1 C-band wavelength (metres)
WAVELENGTH_M: float = 0.05546
# Downsampling factor for quiver arrows (every Nth pixel)
QUIVER_STEP: int = 20


def load_displacement_map(data_dir: str) -> Optional[np.ndarray]:
    """Load interferogram bands and compute LOS displacement.

    Computes phase as atan2(q_ifg, i_ifg) from the real/imaginary
    interferogram bands. Falls back to Phase_*.img if available.

    Args:
        data_dir: Path to the .data directory of an interferogram.

    Returns:
        2D numpy array of LOS displacement in metres, or None on error.
    """
    try:
        # Primary: compute phase from i_ifg (real) + q_ifg (imaginary)
        # Find i_ifg and q_ifg bands
        i_files = glob.glob(os.path.join(data_dir, "i_ifg_*.img"))
        q_files = glob.glob(os.path.join(data_dir, "q_ifg_*.img"))

        if i_files and q_files:
            with rasterio.open(i_files[0]) as src_i:
                real_part = src_i.read(1).astype(np.float64)
            with rasterio.open(q_files[0]) as src_q:
                imag_part = src_q.read(1).astype(np.float64)

            phase = np.arctan2(imag_part, real_part)
            displacement = (phase * WAVELENGTH_M) / (-4.0 * np.pi)
            logging.info("  Phase computed from i_ifg + q_ifg (shape: %s)", displacement.shape)
            return displacement

        # Fallback: Phase_*.img
        phase_files = glob.glob(os.path.join(data_dir, "Phase_*.img"))
        if phase_files:
            with rasterio.open(phase_files[0]) as src:
                phase = src.read(1).astype(np.float64)
                displacement = (phase * WAVELENGTH_M) / (-4.0 * np.pi)
                return displacement

        logging.warning("  No interferogram bands found in %s", data_dir)
        return None

    except Exception as exc:
        logging.error("Error reading phase from %s: %s", data_dir, exc)
        return None


def load_coherence_map(data_dir: str) -> Optional[np.ndarray]:
    """Load the coherence band from an interferogram.

    Args:
        data_dir: Path to the .data directory of an interferogram.

    Returns:
        2D numpy array of coherence (0-1), or None on error.
    """
    coh_files = glob.glob(os.path.join(data_dir, "coh_*.img"))
    if not coh_files:
        coh_files = glob.glob(os.path.join(data_dir, "coh_*.hdr"))
    if not coh_files:
        return None

    try:
        with rasterio.open(coh_files[0]) as src:
            return src.read(1).astype(np.float64)
    except Exception:
        return None


def compute_gradient_field(
    displacement: np.ndarray,
    smooth_sigma: float = 3.0,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Compute spatial gradient of the displacement field.

    Args:
        displacement: 2D LOS displacement array (metres).
        smooth_sigma: Gaussian smoothing sigma to reduce noise before gradient.

    Returns:
        (dx, dy, magnitude, direction_degrees)
        - dx: gradient in the x (column) direction
        - dy: gradient in the y (row) direction
        - magnitude: sqrt(dx^2 + dy^2)
        - direction_degrees: flow direction in degrees (0=East, 90=North)
    """
    smoothed = gaussian_filter(displacement, sigma=smooth_sigma)
    dy, dx = np.gradient(smoothed)

    magnitude = np.sqrt(dx**2 + dy**2)
    direction_rad = np.arctan2(-dy, dx)  # -dy because image y-axis is inverted
    direction_deg = np.degrees(direction_rad) % 360

    return dx, dy, magnitude, direction_deg


def plot_vector_field(
    displacement: np.ndarray,
    coherence: Optional[np.ndarray],
    dx: np.ndarray,
    dy: np.ndarray,
    magnitude: np.ndarray,
    title: str,
    output_path: str,
    step: int = QUIVER_STEP,
) -> None:
    """Generate a quiver plot showing displacement flow direction.

    Args:
        displacement: 2D displacement map (background).
        coherence: Optional coherence map (used as background if available).
        dx, dy: Gradient components.
        magnitude: Gradient magnitude.
        title: Plot title.
        output_path: Path to save the PNG.
        step: Downsampling factor for arrows.
    """
    h, w = displacement.shape
    Y, X = np.mgrid[0:h:step, 0:w:step]
    U = dx[::step, ::step]
    V = -dy[::step, ::step]  # Invert for image coordinates
    M = magnitude[::step, ::step]

    fig, ax = plt.subplots(figsize=(14, 10))

    # Background: coherence or displacement
    if coherence is not None:
        bg = ax.imshow(coherence, cmap='gray', vmin=0, vmax=0.5, aspect='auto')
        plt.colorbar(bg, ax=ax, label='Coherence', shrink=0.6, pad=0.02)
    else:
        bg = ax.imshow(displacement * 1000, cmap='RdYlBu_r', aspect='auto')
        plt.colorbar(bg, ax=ax, label='LOS Displacement (mm)', shrink=0.6, pad=0.02)

    # Normalise arrow colours by magnitude
    norm = mcolors.Normalize(vmin=np.nanpercentile(M, 5), vmax=np.nanpercentile(M, 95))

    quiv = ax.quiver(
        X, Y, U, V, M,
        cmap='hot',
        norm=norm,
        scale=np.nanpercentile(magnitude, 95) * 30,
        width=0.003,
        headwidth=4,
        headlength=5,
        alpha=0.85,
    )
    plt.colorbar(quiv, ax=ax, label='Gradient Magnitude (mm/pixel)', shrink=0.6, pad=0.02)

    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_xlabel("Pixel X (Range)")
    ax.set_ylabel("Pixel Y (Azimuth)")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    logging.info("Vector field plot saved to %s", output_path)


def plot_strain_map(
    magnitude: np.ndarray,
    title: str,
    output_path: str,
) -> None:
    """Generate a strain rate heatmap (gradient magnitude).

    High gradient magnitude = rapid spatial change = failure risk.

    Args:
        magnitude: Gradient magnitude array.
        title: Plot title.
        output_path: Path to save the PNG.
    """
    fig, ax = plt.subplots(figsize=(14, 10))

    # Convert to mm/pixel for readability
    mag_mm = magnitude * 1000

    vmax = np.nanpercentile(mag_mm, 98)
    im = ax.imshow(mag_mm, cmap='inferno', vmin=0, vmax=vmax, aspect='auto')
    plt.colorbar(im, ax=ax, label='Strain Rate (mm/pixel)', shrink=0.7)

    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_xlabel("Pixel X (Range)")
    ax.set_ylabel("Pixel Y (Azimuth)")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    logging.info("Strain rate map saved to %s", output_path)


def export_vectors_csv(
    dx: np.ndarray,
    dy: np.ndarray,
    magnitude: np.ndarray,
    direction: np.ndarray,
    output_path: str,
    step: int = QUIVER_STEP,
) -> None:
    """Export displacement gradient vectors to CSV.

    Args:
        dx, dy: Gradient components.
        magnitude: Gradient magnitude.
        direction: Flow direction in degrees.
        output_path: Path to save the CSV.
        step: Downsampling factor for export.
    """
    with open(output_path, 'w', newline='', encoding='utf-8') as fh:
        writer = csv.writer(fh)
        writer.writerow(['pixel_x', 'pixel_y', 'dx_mm', 'dy_mm',
                         'magnitude_mm', 'direction_deg'])

        h, w = dx.shape
        for y in range(0, h, step):
            for x in range(0, w, step):
                writer.writerow([
                    x, y,
                    f"{dx[y, x] * 1000:.4f}",
                    f"{dy[y, x] * 1000:.4f}",
                    f"{magnitude[y, x] * 1000:.4f}",
                    f"{direction[y, x]:.1f}",
                ])

    logging.info("Vector data CSV saved to %s", output_path)


def main() -> None:
    """Process all interferograms and generate vector field outputs."""
    logging.info("Starting displacement vector field analysis...")

    dim_files = sorted(glob.glob(os.path.join(OUTPUT_INT_DIR, "*.dim")))
    if not dim_files:
        logging.warning("No .dim files found in %s", OUTPUT_INT_DIR)
        return

    for dim_file in dim_files:
        basename = os.path.basename(dim_file).replace('.dim', '')
        data_dir = dim_file.replace('.dim', '.data')

        if not os.path.exists(data_dir):
            logging.warning("Data directory missing for %s", basename)
            continue

        logging.info("Processing %s...", basename)

        displacement = load_displacement_map(data_dir)
        if displacement is None:
            logging.warning("  Could not load phase for %s. Skipping.", basename)
            continue

        coherence = load_coherence_map(data_dir)

        # Compute gradient field
        dx, dy, magnitude, direction = compute_gradient_field(displacement)

        logging.info("  Gradient computed: max magnitude = %.4f mm/pixel",
                     np.nanmax(magnitude) * 1000)

        # Generate plots
        plot_vector_field(
            displacement, coherence, dx, dy, magnitude,
            title=f"Displacement Flow Direction - {basename}",
            output_path=os.path.join(RESULTS_DIR, f"vector_field_{basename}.png"),
        )

        plot_strain_map(
            magnitude,
            title=f"Strain Rate Map - {basename}",
            output_path=os.path.join(RESULTS_DIR, f"strain_map_{basename}.png"),
        )

        # Export CSV
        export_vectors_csv(
            dx, dy, magnitude, direction,
            output_path=os.path.join(RESULTS_DIR, f"vectors_{basename}.csv"),
        )

    logging.info("Displacement vector field analysis complete.")


if __name__ == "__main__":
    main()

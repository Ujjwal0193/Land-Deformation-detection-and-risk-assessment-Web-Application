"""baseline_utils.py — Baseline Extraction Utilities for MineGuard.

Provides helper functions for extracting acquisition dates, computing
temporal baselines, and estimating perpendicular baselines from
Sentinel-1 SLC product metadata.
"""

import re
import logging
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, Tuple, Dict, List, Any


logger = logging.getLogger(__name__)


def parse_flexible_date(date_str: str) -> date:
    """Parse a date string that may be year-only, year-month, or full date.

    Supports formats:
        '2014'        -> 2014-01-01
        '2014-06'     -> 2014-06-01
        '2014-06-15'  -> 2014-06-15

    Args:
        date_str: Date string in any of the supported formats.

    Returns:
        Parsed date object with missing month/day defaulting to 1.
    """
    date_str = str(date_str).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: '{date_str}'. Use YYYY, YYYY-MM, or YYYY-MM-DD.")


def extract_acquisition_date(product_name: str) -> Optional[date]:
    """Extract the primary acquisition date from a Sentinel-1 product filename.

    Args:
        product_name: Sentinel-1 zip filename or product identifier.

    Returns:
        Acquisition date, or None if parsing fails.
    """
    matches = re.findall(r'(\d{8})T\d{6}', product_name)
    if not matches:
        matches = re.findall(r'(20[12]\d{5})', product_name)

    if matches:
        try:
            return datetime.strptime(matches[0], "%Y%m%d").date()
        except ValueError:
            pass

    logger.warning("Could not extract acquisition date from: %s", product_name)
    return None


def extract_relative_orbit_from_filename(filename: str) -> Optional[int]:
    """Calculate the relative orbit number from a Sentinel-1 zip filename.

    Extracts the satellite (S1A/S1B) and the absolute orbit number,
    then computes the relative orbit.
    """
    match = re.search(r'(S1[AB])_.*?_(\d{6})_', filename)
    if not match:
        return None
    
    sat = match.group(1)
    abs_orbit = int(match.group(2))
    
    if sat == 'S1A':
        return ((abs_orbit - 73) % 175) + 1
    elif sat == 'S1B':
        return ((abs_orbit - 27) % 175) + 1
    return None


def scan_existing_local_years(directory: str) -> Dict[str, Dict[str, Any]]:
    """Scan a directory for complete Sentinel-1 SLC zips and map them by year.

    Only considers files >= 6GB. Calculates their relative orbit.
    
    Returns:
        Dict mapping year string (e.g., '2015') to:
        {'filename': str, 'relative_orbit': int}
    """
    import os
    existing = {}
    min_valid = 6 * 1024 * 1024 * 1024
    
    if not os.path.exists(directory):
        return existing
        
    for f in os.listdir(directory):
        if not f.endswith('.zip'):
            continue
            
        filepath = os.path.join(directory, f)
        if os.path.getsize(filepath) < min_valid:
            continue
            
        match = re.search(r'20[12]\d{5}', f)
        if not match:
            continue
            
        year = match.group()[:4]
        rel_orbit = extract_relative_orbit_from_filename(f)
        
        # Keep the first/largest file found for that year
        if year not in existing:
            existing[year] = {
                'filename': f,
                'relative_orbit': rel_orbit
            }
            
    return existing


def calculate_temporal_baseline(master_date: date, slave_date: date) -> int:
    """Compute the temporal baseline between two acquisition dates.

    Args:
        master_date: Date of the master (earlier) acquisition.
        slave_date: Date of the slave (later) acquisition.

    Returns:
        Absolute number of days between the two acquisitions.
    """
    return abs((slave_date - master_date).days)


def extract_perpendicular_baseline(
    master_zip: str,
    slave_zip: str,
) -> Optional[float]:
    """Estimate the perpendicular baseline from SLC orbit state vectors.

    Reads the orbit state vectors from the manifest.safe inside each
    SLC zip and computes a simplified perpendicular baseline estimate
    from the position difference at mid-swath.

    Args:
        master_zip: Path to the master SLC zip file.
        slave_zip: Path to the slave SLC zip file.

    Returns:
        Estimated perpendicular baseline in metres, or None on error.
    """
    try:
        master_pos = _read_orbit_position(master_zip)
        slave_pos = _read_orbit_position(slave_zip)

        if master_pos is None or slave_pos is None:
            return None

        # Euclidean distance between orbit positions (simplified Bperp)
        dx = slave_pos[0] - master_pos[0]
        dy = slave_pos[1] - master_pos[1]
        dz = slave_pos[2] - master_pos[2]
        spatial_baseline = (dx**2 + dy**2 + dz**2) ** 0.5

        # For near-polar Sentinel-1 orbits, Bperp ~ spatial_baseline * sin(look_angle)
        # Typical IW mid-swath look angle ~33 degrees
        import math
        bperp = spatial_baseline * math.sin(math.radians(33.0))

        logger.debug("Spatial baseline: %.1f m, Bperp estimate: %.1f m",
                      spatial_baseline, bperp)
        return round(bperp, 1)

    except Exception as exc:
        logger.warning("Perpendicular baseline estimation failed: %s", exc)
        return None


def _read_orbit_position(zip_path: str) -> Optional[Tuple[float, float, float]]:
    """Read the first orbit state vector position (X, Y, Z) from manifest.safe.

    Args:
        zip_path: Path to the Sentinel-1 SLC zip.

    Returns:
        (x, y, z) in metres, or None on error.
    """
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            manifest_files = [
                n for n in zf.namelist()
                if n.endswith('manifest.safe')
            ]
            if not manifest_files:
                logger.warning("No manifest.safe in %s", zip_path)
                return None

            root = ET.parse(zf.open(manifest_files[0])).getroot()

            # Namespace handling for Sentinel-1 manifest
            ns = {'safe': 'http://www.esa.int/safe/sentinel-1.0'}

            # Try to find orbit state vectors in metadataSection
            for elem in root.iter():
                if 'orbitReference' in elem.tag or 'orbitNumber' in elem.tag:
                    continue
                # Look for position elements with x, y, z
                x_el = elem.find('.//x')
                y_el = elem.find('.//y')
                z_el = elem.find('.//z')
                if x_el is not None and y_el is not None and z_el is not None:
                    return (
                        float(x_el.text),
                        float(y_el.text),
                        float(z_el.text),
                    )

            # Fallback: parse annotation XML for orbit state vectors
            ann_files = [
                n for n in zf.namelist()
                if 'annotation/' in n.lower()
                and 'iw1' in n.lower()
                and '-vv-' in n.lower()
                and 'calibration' not in n.lower()
                and 'noise' not in n.lower()
                and n.endswith('.xml')
            ]
            if ann_files:
                ann_root = ET.parse(zf.open(ann_files[0])).getroot()
                orbit_list = ann_root.findall('.//orbit')
                if orbit_list:
                    # Use the middle state vector for best mid-swath estimate
                    mid = orbit_list[len(orbit_list) // 2]
                    pos = mid.find('position')
                    if pos is not None:
                        x = float(pos.find('x').text)
                        y = float(pos.find('y').text)
                        z = float(pos.find('z').text)
                        return (x, y, z)

            logger.warning("No orbit state vectors found in %s", zip_path)
            return None

    except Exception as exc:
        logger.warning("Error reading orbit from %s: %s", zip_path, exc)
        return None

def generate_search_windows(
    start_date: date, 
    end_date: date, 
    samples: int,
    window_days: int = 12,
    reference_month_day: str = "",
) -> Dict[str, Tuple[date, date]]:
    """Generate search windows for satellite image acquisition.

    When ``reference_month_day`` is provided (e.g. ``"07-23"``), each
    sample year's search centres on that month-day.  Otherwise the
    targets are equally spaced between *start_date* and *end_date*.

    Args:
        start_date: The beginning of the overall timeline.
        end_date: The end of the overall timeline.
        samples: Number of images to download.
        window_days: +/- days around each target date for the primary
            search window.
        reference_month_day: Optional ``"MM-DD"`` string.  If set,
            searches centre on this month-day for every year instead
            of being evenly spaced.

    Returns:
        Dict mapping string labels to a ``(window_start, window_end)``
        tuple.
    """
    if samples < 1:
        return {}

    windows: Dict[str, Tuple[date, date]] = {}

    if reference_month_day:
        # --- Reference-date mode: one target per year on MM-DD ---
        ref_month, ref_day = (int(x) for x in reference_month_day.split("-"))
        start_year = start_date.year
        end_year = end_date.year
        years = list(range(start_year, end_year + 1))[:samples]

        for i, yr in enumerate(years):
            try:
                target = date(yr, ref_month, ref_day)
            except ValueError:
                target = date(yr, ref_month, min(ref_day, 28))
            name = f"Sample_{i+1:02d}_{target.strftime('%Y_%m_%d')}"
            win_start = target - timedelta(days=window_days)
            win_end = target + timedelta(days=window_days)
            windows[name] = (win_start, win_end)
    else:
        # --- Even-spacing mode ---
        if samples == 1:
            targets = [start_date]
        else:
            total_days = (end_date - start_date).days
            step_days = total_days / (samples - 1)
            targets = [
                start_date + timedelta(days=round(i * step_days))
                for i in range(samples)
            ]
        for i, target in enumerate(targets):
            name = f"Sample_{i+1:02d}_{target.strftime('%Y_%m_%d')}"
            win_start = target - timedelta(days=window_days)
            win_end = target + timedelta(days=window_days)
            windows[name] = (win_start, win_end)

    return windows


def generate_fallback_windows(
    target_date: date,
) -> List[Tuple[str, Tuple[date, date]]]:
    """Generate progressively wider search windows for a given year.

    Called when the primary ±12 day window found no data.  Returns
    four quarterly windows (Q1-Q4) for the target year, each spanning
    ~3 months.

    Args:
        target_date: A date whose year is used for the fallback.

    Returns:
        List of ``(label, (start, end))`` tuples covering each quarter.
    """
    yr = target_date.year
    quarters = [
        ("Q1", date(yr, 1, 1), date(yr, 3, 31)),
        ("Q2", date(yr, 4, 1), date(yr, 6, 30)),
        ("Q3", date(yr, 7, 1), date(yr, 9, 30)),
        ("Q4", date(yr, 10, 1), date(yr, 12, 31)),
    ]
    return [(f"Fallback_{yr}_{q}", (s, e)) for q, s, e in quarters]


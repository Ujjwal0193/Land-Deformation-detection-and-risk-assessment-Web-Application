import logging
from typing import List, Dict, Any, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

def filter_scenes(
    scene_list: List[Dict[str, Any]],
    roi: Dict[str, float],
    start_year: int,
    end_year: int,
    orbit_mode: str = "DOMINANT",
) -> List[Dict[str, Any]]:
    """
    Filters a list of queried Sentinel-1 scenes based on strict InSAR criteria.

    Rules applied:
    - Mode must equal "IW"
    - Polarization must contain "VV"
    - Scene acquisition date must fall within the selected timeline [start_year, end_year]
    - Orbit direction handling depends on orbit_mode:
        - "DOMINANT": keep only the most frequent orbit direction (default, safe for single-orbit)
        - "ASCENDING": keep only ascending scenes
        - "DESCENDING": keep only descending scenes
        - "BOTH": keep scenes from both orbit directions — enables ASC+DSC 2D decomposition
          (each direction was already locked to a single relative orbit at query time)

    Args:
        scene_list (List[Dict[str, Any]]): The raw metadata scenes retrieved from OData.
        roi (Dict[str, float]): The region of interest bounding box (N, S, E, W).
        start_year (int): The starting year of monitoring.
        end_year (int): The ending year of monitoring.
        orbit_mode (str): One of "DOMINANT", "ASCENDING", "DESCENDING", or "BOTH".

    Returns:
        List[Dict[str, Any]]: A clean list of valid scenes ready for download.
    """

    if not scene_list:
        return []

    filtered = []

    # 1. First pass filter for Time, Mode, and Polarization
    for scene in scene_list:

        # Check timeline bounds
        acq_str = scene.get('acquisitionDate', '')
        try:
            # Parse typical CDSE ISO string: '2024-01-28T05:59:59.00Z'
            acq_year = datetime.strptime(acq_str.split('T')[0], "%Y-%m-%d").year
            if not (start_year <= acq_year <= end_year):
                continue
        except ValueError:
            logger.warning(f"Could not parse acquisition date for scene {scene.get('filename')}")
            continue

        # Check Sentinel-1 Mode -> Interferometric Wide (IW)
        # Allow "UNKNOWN" through: the OData query already filters operationalMode=IW,
        # so a missing attribute value is still an IW scene.
        mode = scene.get('mode', 'UNKNOWN')
        if mode not in ('IW', 'UNKNOWN'):
            continue

        # Check Polarization -> We strictly need VV capable scenes
        # Often represented in CDSE as 'VV, VH' or 'VV'
        pol = str(scene.get('polarization', '')).upper()
        if 'VV' not in pol:
            continue

        filtered.append(scene)

    if not filtered:
        logger.warning("No scenes survived the initial Mode/Pol/Time filter.")
        return []

    # 2. Orbit direction consistency enforcement
    mode_upper = orbit_mode.upper()

    if mode_upper == "BOTH":
        # Keep scenes from both orbit directions — ASC and DSC are separately
        # orbit-locked at query time, so mixing here is intentional for 2D decomposition.
        asc_scenes = [s for s in filtered if str(s.get('orbitDirection', '')).upper() == 'ASCENDING']
        dsc_scenes = [s for s in filtered if str(s.get('orbitDirection', '')).upper() == 'DESCENDING']
        final_scenes = asc_scenes + dsc_scenes
        logger.info(
            f"BOTH orbit mode: retaining {len(asc_scenes)} ASC + {len(dsc_scenes)} DSC = "
            f"{len(final_scenes)} scenes for 2D decomposition."
        )
    elif mode_upper in ('ASCENDING', 'DESCENDING'):
        final_scenes = [s for s in filtered if str(s.get('orbitDirection', '')).upper() == mode_upper]
        logger.info(f"Orbit mode {mode_upper}: retained {len(final_scenes)} scenes.")
    else:
        # DOMINANT — pick the most frequent orbit direction
        orbit_counts: Dict[str, int] = {}
        for scene in filtered:
            orbit = str(scene.get('orbitDirection', 'UNKNOWN')).upper()
            if orbit in ['ASCENDING', 'DESCENDING']:
                orbit_counts[orbit] = orbit_counts.get(orbit, 0) + 1

        if not orbit_counts:
            logger.error("No valid orbit directions ('ASCENDING' or 'DESCENDING') found in metadata.")
            return []

        dominant_orbit = max(orbit_counts, key=orbit_counts.get)
        logger.info(f"Dominant orbit direction: {dominant_orbit} ({orbit_counts[dominant_orbit]} scenes)")
        final_scenes = [s for s in filtered if str(s.get('orbitDirection', '')).upper() == dominant_orbit]

    logger.info(f"Filtering complete. Reduced from {len(scene_list)} total -> {len(final_scenes)} valid InSAR scenes.")
    return final_scenes


def estimate_download_size(scene_list: List[Dict[str, Any]]) -> Tuple[float, float]:
    """
    Estimates the total minimum and maximum download size for the selected Sentinel-1 scenes.
    Assumes an average Sentinel-1 SLC IW ZIP file size spans 2GB - 5GB on COP CDSE.

    Args:
        scene_list (List[Dict[str, Any]]): The filtered list of scenes to download.

    Returns:
        Tuple[float, float]: Estimated minimum and maximum total size in Gigabytes (GB).
    """
    count = len(scene_list)
    min_gb = count * 2.0
    max_gb = count * 5.0
    
    return min_gb, max_gb

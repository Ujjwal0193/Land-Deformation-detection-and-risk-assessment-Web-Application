"""
download_originals.py — Sentinel-1 SLC Backup Downloader

Downloads Sentinel-1 SLC products from CDSE OData and maintains backup copies
in a separate directory. Used alongside main_script.py for InSAR deformation
monitoring.
"""

import os
import re
import sys
import shutil
import logging
import requests
import traceback
from pathlib import Path
from datetime import date, datetime
from typing import Optional, Dict, Any, Tuple, List
from tqdm import tqdm

# --- PATH CONFIGURATION ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
# SLC directories live at the workspace root (one level above MineGuard_Proto)
WORKSPACE_ROOT = os.path.dirname(PROJECT_ROOT)
INPUT_SLC_DIR = os.path.join(WORKSPACE_ROOT, "input_slc")
ORIGINAL_SLC_DIR = os.path.join(WORKSPACE_ROOT, "original_slc")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")

# --- CENTRAL CONFIG + LOGGING ---
import sys as _sys
_sys.path.insert(0, PROJECT_ROOT)
from src.utils.config_loader import load_config
from src.utils.baseline_utils import (
    generate_search_windows, 
    parse_flexible_date,
    scan_existing_local_years,
)

_cfg = load_config()
setup_logging("download_originals", _cfg)

# --- CONFIGURATION ---
SCIHUB_USER: Optional[str] = os.getenv("CDSE_USER")
SCIHUB_PASS: Optional[str] = os.getenv("CDSE_PASS")

if not SCIHUB_USER or not SCIHUB_PASS:
    logging.critical("[FAIL] ERROR: Missing environment variables CDSE_USER or CDSE_PASS.")
    logging.critical("Set them before running.")
    sys.exit(1)

_roi = _cfg.get("roi", {})
ROI_WKT = f'POINT({_roi.get("lon", 85.09)} {_roi.get("lat", 20.96)})'
ORBIT_DIRECTION: str = 'ASCENDING'
MAX_TEMPORAL_BASELINE_DAYS = _cfg.get("temporal_baseline_max_days", 400)

_dw = _cfg.get("data_window", {})
DATA_WINDOW_START = parse_flexible_date(_dw.get("start_date", "2014"))
DATA_WINDOW_END = parse_flexible_date(_dw.get("end_date", "2020"))
NUM_SAMPLES = _dw.get("samples", 6)

# Dynamically generate search windows
DATES = generate_search_windows(DATA_WINDOW_START, DATA_WINDOW_END, NUM_SAMPLES)


# --- ODATA API CONFIGURATION ---
AUTH_URL: str = 'https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token'
ODATA_URL: str = 'https://catalogue.dataspace.copernicus.eu/odata/v1'


# Minimum valid SLC zip size — Sentinel-1 SLC products are typically >6 GB
MIN_VALID_SLC_BYTES: int = 6 * 1024 * 1024 * 1024


def get_access_token(username: str, password: str) -> Optional[str]:
    """Acquire an OAuth2 access token from the CDSE identity provider."""
    logging.info("Acquiring access token...")
    data = {
        'client_id': 'cdse-public',
        'username': username,
        'password': password,
        'grant_type': 'password'
    }
    try:
        r = requests.post(AUTH_URL, data=data, timeout=60)
        r.raise_for_status()
        logging.info("Token acquired successfully.")
        return r.json()['access_token']
    except Exception as e:
        logging.error(f"Authentication failed: {e}")
        return None





def search_products(
    token: str,
    roi_wkt: str,
    date_range: Tuple[date, date],
    relative_orbit: Optional[int] = None
) -> Any:
    """Search CDSE OData for Sentinel-1 SLC products matching InSAR criteria.

    Applies SLC product type, IW mode, VV polarization, and orbit direction filters.

    Returns:
        Product dict, 'REFRESH_REQUIRED' string on 401, or None.
    """
    start_date = date_range[0].strftime('%Y-%m-%dT%H:%M:%S.000Z')
    end_date = date_range[1].strftime('%Y-%m-%dT%H:%M:%S.000Z')

    filters = [
        "Collection/Name eq 'SENTINEL-1'",
        f"ContentDate/Start ge {start_date}",
        f"ContentDate/End le {end_date}",
        "Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType' and att/Value eq 'SLC')",
        f"OData.CSC.Intersects(area=geography'SRID=4326;{roi_wkt}')"
    ]

    if relative_orbit:
        filters.append(
            f"Attributes/OData.CSC.IntegerAttribute/any("
            f"att:att/Name eq 'relativeOrbitNumber' and att/Value eq {relative_orbit})"
        )

    params = {
        '$filter': ' and '.join(filters),
        '$top': '20',
        '$orderby': 'ContentDate/Start asc',
        '$expand': 'Attributes'
    }
    
    headers = {'Authorization': f'Bearer {token}'}

    logging.info(f"Searching products for {date_range[0]} — {date_range[1]}...")

    try:
        r = requests.get(f"{ODATA_URL}/Products", headers=headers, params=params, timeout=60)

        if r.status_code == 401:
            logging.warning("Token expired (401). Refresh required.")
            return "REFRESH_REQUIRED"

        r.raise_for_status()
        data = r.json()
        products = data.get('value', [])

        if not products:
            return None

        target_date = date_range[0] + (date_range[1] - date_range[0]) / 2
        target_dt = datetime.combine(target_date, datetime.min.time())

        def sensing_date(p: Dict) -> datetime:
            return datetime.strptime(
                p['ContentDate']['Start'].split('.')[0], "%Y-%m-%dT%H:%M:%S"
            )

        products.sort(key=lambda p: abs((sensing_date(p) - target_dt).total_seconds()))
        
        selected = None
        for p in products:
            valid_pol = False
            for att in p.get('Attributes', []):
                if att['Name'] == 'polarisationChannels' and 'VV' in att['Value']:
                    valid_pol = True
                    break
            
            if valid_pol:
                selected = p
                break
        
        if not selected:
             logging.warning("No product found matching polarisation 'VV'.")
             return None

        delta_days = abs((sensing_date(selected) - target_dt).days)
        if delta_days > MAX_TEMPORAL_BASELINE_DAYS:
            logging.warning(
                f"Closest product is {delta_days} days from target "
                f"(> {MAX_TEMPORAL_BASELINE_DAYS} day threshold). Proceeding with caution."
            )

        logging.info(f"Selected: {selected['Name']} (Date: {selected['ContentDate']['Start']})")
        return selected

    except Exception as e:
        logging.error(f"Search failed: {e}")
        return None


def download_product(token: str, product: Dict[str, Any]) -> Optional[str]:
    """Download a Sentinel-1 product to ORIGINAL_SLC_DIR with resume support.

    The download flow is:
    1. If a complete copy exists in original_slc → skip.
    2. If a complete copy exists in input_slc → copy it over.
    3. If a partial file exists → resume from last byte (HTTP Range).
    4. Otherwise → full download.

    Handles 401 token expiry by returning 'REFRESH_REQUIRED'.

    Returns:
        File path on success, 'REFRESH_REQUIRED' on 401, or None.
    """
    product_id = product['Id']
    name = product['Name']
    filename = f"{name}.zip"

    # Ensure directories exist
    os.makedirs(ORIGINAL_SLC_DIR, exist_ok=True)

    target_path = os.path.join(ORIGINAL_SLC_DIR, filename)
    source_path = os.path.join(INPUT_SLC_DIR, filename)

    logging.info(f"Processing {name}...")

    url = f"{ODATA_URL}/Products({product_id})/$value"
    auth_headers: Dict[str, str] = {'Authorization': f'Bearer {token}'}
    def _is_complete_fast(path: str) -> bool:
        """Quickly check if a file exists and is reasonably sized."""
        return os.path.exists(path) and os.path.getsize(path) >= MIN_VALID_SLC_BYTES

    # --- Checkpoint 1: Complete copy in original_slc ---
    if _is_complete_fast(target_path):
        logging.info(f"  [SKIP] Complete file already exists in original_slc. Skipping API request.")
        return target_path

    # --- Checkpoint 2: Complete copy in input_slc ---
    if _is_complete_fast(source_path):
        logging.info(f"  [SKIP] Complete file in input_slc. Copying to backup...")
        try:
            shutil.copy2(source_path, target_path)
            logging.info(f"  [OK] Copied to {ORIGINAL_SLC_DIR}.")
            return target_path
        except Exception as e:
            logging.warning(f"  Copy failed: {e}. Falling back to download.")

    expected_size: int = 0
    # --- Get expected file size via HEAD request ONLY if not skipped ---
    try:
        head_r = requests.head(url, headers=auth_headers, allow_redirects=True, timeout=30)
        if 'content-length' in head_r.headers:
            expected_size = int(head_r.headers['content-length'])
    except Exception:
        logging.debug("Could not retrieve content-length via HEAD.")

    # --- Checkpoint 3: Partial file -> resume, or full download ---
    existing_size: int = 0
    if os.path.exists(target_path):
        existing_size = os.path.getsize(target_path)
    elif os.path.exists(source_path):
        # Copy partial from input_slc so we can resume into original_slc
        existing_size = os.path.getsize(source_path)
        if existing_size > 0:
            logging.info(f"  [CHECKPOINT] Partial file in input_slc ({existing_size / (1024**2):.1f} MB). Copying to resume...")
            try:
                shutil.copy2(source_path, target_path)
            except Exception as e:
                logging.warning(f"  Copy of partial file failed: {e}. Starting fresh.")
                existing_size = 0

    if existing_size > 0 and expected_size > 0 and existing_size < expected_size:
        logging.info(
            f"  [RESUME] Partial file detected: {existing_size / (1024**2):.1f} MB "
            f"of {expected_size / (1024**2):.1f} MB ({existing_size / expected_size * 100:.1f}%). Resuming..."
        )
    elif existing_size == 0:
        logging.info(f"  [DOWNLOAD] No local file found. Downloading from CDSE...")
    else:
        logging.info(f"  [DOWNLOAD] Downloading from CDSE...")

    try:
        # Build request headers with optional Range for resume
        request_headers = dict(auth_headers)
        if existing_size > 0:
            request_headers['Range'] = f'bytes={existing_size}-'

        r = requests.get(url, headers=request_headers, allow_redirects=False, stream=True, timeout=60)

        # Follow redirects manually to preserve auth
        while r.status_code in (301, 302, 303, 307):
            url = r.headers['Location']
            r = requests.get(url, headers=request_headers, allow_redirects=False, stream=True, timeout=120)

        if r.status_code == 401:
            logging.warning("Token expired during download.")
            return "REFRESH_REQUIRED"

        # Determine if server supports resume
        if r.status_code == 206:
            # Partial content — server accepted our Range header
            logging.info(f"  [RESUME] Server accepted Range request. Resuming from byte {existing_size}.")
            file_mode = 'ab'
            downloaded = existing_size
        elif r.status_code == 200:
            # Full response — server ignored Range or doesn't support it
            if existing_size > 0:
                logging.warning("  [RESUME] Server does not support Range. Restarting full download.")
            file_mode = 'wb'
            downloaded = 0
        else:
            r.raise_for_status()
            file_mode = 'wb'
            downloaded = 0

        if expected_size == 0:
            expected_size = int(r.headers.get('content-length', 0)) + downloaded

        last_update = 0
        last_update = 0
        chunk_size = 1024 * 1024  # 1 MB chunks for smooth updates
        total_mb = expected_size / (1024 ** 2) if expected_size > 0 else None
        
        with open(target_path, file_mode) as f:
            with tqdm(
                total=expected_size,
                initial=downloaded,
                unit='B',
                unit_scale=True,
                unit_divisor=1024,
                desc=f"  Downloading {name[:40]}",
                ncols=80,
                bar_format="  {l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
                leave=False,
            ) as pbar:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    f.write(chunk)
                    downloaded += len(chunk)
                    pbar.update(len(chunk))

        # --- Validate final size ---
        if expected_size > 0:
            actual = os.path.getsize(target_path)
            if abs(actual - expected_size) / expected_size > 0.01:
                logging.warning(
                    f"  Size mismatch! Expected {expected_size}, got {actual}. "
                    f"File may be incomplete."
                )
            else:
                logging.info(f"  [OK] Download complete and validated ({actual / (1024**2):.1f} MB).")
        else:
            logging.info(f"  [OK] Download complete (size not validated).")

        return target_path

    except Exception as e:
        logging.error(f"  Download failed: {e}")
        return None


def get_relative_orbit(product: Dict[str, Any]) -> Optional[int]:
    """Extract the relative orbit number from product attributes."""
    if 'Attributes' in product:
        for att in product['Attributes']:
            if att['Name'] == 'relativeOrbitNumber':
                return att['Value']
    return None


def main() -> None:
    """Main entry point: authenticate, search and download Sentinel-1 backup images.

    Runs a file checkpoint first to detect already-downloaded or partially
    downloaded files.  Only hits the CDSE API for years that still need data.
    """
    os.makedirs(ORIGINAL_SLC_DIR, exist_ok=True)
    os.makedirs(INPUT_SLC_DIR, exist_ok=True)

    logging.info("--- Starting Backup/Download Script ---")
    logging.info("Starting search & download phase for requested coordinates/dates...")

    # --- Authenticate ---
    token = get_access_token(SCIHUB_USER, SCIHUB_PASS)
    if not token:
        logging.critical("Initial authentication failed. Aborting.")
        sys.exit(1)

    sorted_keys = sorted(DATES.keys())
    rel_orbit: Optional[int] = None

    # --- Pre-scan original_slc for existing complete files ---
    existing_local_files = scan_existing_local_years(ORIGINAL_SLC_DIR)
    if existing_local_files:
        logging.info("Found existing robust local files in backup:")
        for yr, info in existing_local_files.items():
            logging.info(f"  [{yr}] {info['filename']} (Rel Orbit: {info['relative_orbit']})")
            if rel_orbit is None and info['relative_orbit'] is not None:
                rel_orbit = info['relative_orbit']
                logging.info(f"Locked Relative Orbit to {rel_orbit} based on existing backup files.")

    for key in sorted_keys:
        logging.info(f"\n--- Processing Period: {key} ---")

        # Check if we already have this year locally
        target_mid = DATES[key][0] + (DATES[key][1] - DATES[key][0]) / 2
        year_str = str(target_mid.year)
        
        if year_str in existing_local_files:
            logging.info(f"  [SKIP] Complete SLC file for {year_str} already exists in original_slc.")
            logging.info("[INFO] Using existing SLC data (download skipped)")
            continue

        # --- Primary search (narrow window) ---
        result = search_products(token, ROI_WKT, DATES[key], relative_orbit=rel_orbit)

        if result == "REFRESH_REQUIRED":
            logging.info("Refreshing token...")
            token = get_access_token(SCIHUB_USER, SCIHUB_PASS)
            if token:
                result = search_products(token, ROI_WKT, DATES[key], relative_orbit=rel_orbit)
            else:
                logging.error("Token refresh failed. Skipping.")
                continue

        # --- Fallback search (quarterly windows) ---
        if not result or not isinstance(result, dict):
            target_mid = DATES[key][0] + (DATES[key][1] - DATES[key][0]) / 2
            logging.info(
                f"  No data in primary window. Trying quarterly "
                f"fallback for {target_mid.year}..."
            )
            from src.utils.baseline_utils import generate_fallback_windows
            fallbacks = generate_fallback_windows(target_mid)
            for fb_label, fb_range in fallbacks:
                logging.info(f"  Searching {fb_label}: {fb_range[0]} -> {fb_range[1]}")
                result = search_products(token, ROI_WKT, fb_range, relative_orbit=rel_orbit)
                if result == "REFRESH_REQUIRED":
                    token = get_access_token(SCIHUB_USER, SCIHUB_PASS)
                    if token:
                        result = search_products(token, ROI_WKT, fb_range, relative_orbit=rel_orbit)
                if result and isinstance(result, dict):
                    logging.info(f"  [FOUND] Data found in {fb_label}.")
                    break

        # --- Download or report missing ---
        if result and isinstance(result, dict):
            if rel_orbit is None:
                orb = get_relative_orbit(result)
                if orb:
                    rel_orbit = orb
                    logging.info(f"Locked Relative Orbit: {rel_orbit}")

            dl_result = download_product(token, result)
            if dl_result == "REFRESH_REQUIRED":
                token = get_access_token(SCIHUB_USER, SCIHUB_PASS)
                if token:
                    download_product(token, result)
        else:
            logging.warning(
                f"[NO DATA] No Sentinel-1 SLC found for {key} "
                f"(Orbit: {rel_orbit})"
            )

    logging.info("\n--- Backup/Download Complete ---")
    logging.info(f"Original images stored in: {ORIGINAL_SLC_DIR}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Interrupted by user.")
    except Exception as e:
        logging.critical(f"Unhandled error: {e}")
        traceback.print_exc()

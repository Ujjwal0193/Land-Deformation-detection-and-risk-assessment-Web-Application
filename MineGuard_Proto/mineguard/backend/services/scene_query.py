import os
import requests
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, date
from dotenv import load_dotenv

# We need baseline tools for the advanced smart-fallback mechanics
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from src.utils.baseline_utils import parse_flexible_date, generate_search_windows, generate_fallback_windows

# Initialize logger
logger = logging.getLogger(__name__)

# Load environment variables — use explicit project root path so it works
# regardless of which directory uvicorn is launched from.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
load_dotenv(os.path.join(_PROJECT_ROOT, '.env'))

AUTH_URL = 'https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token'
ODATA_URL = 'https://catalogue.dataspace.copernicus.eu/odata/v1'

_ACCESS_TOKEN: Optional[str] = None

def get_access_token(force_refresh: bool = False) -> str:
    """
    Acquire or refresh the OAuth2 access token from the CDSE identity provider.

    Args:
        force_refresh (bool): If True, bypasses any cached token and requests a new one.

    Returns:
        str: The newly acquired or cached access token.

    Raises:
        RuntimeError: If authentication fails.
    """
    global _ACCESS_TOKEN
    
    if _ACCESS_TOKEN and not force_refresh:
        return _ACCESS_TOKEN

    username = os.getenv("CDSE_USER")
    password = os.getenv("CDSE_PASS")
    if not username or not password:
        raise RuntimeError(
            "CDSE credentials not set. Please define CDSE_USER and CDSE_PASS environment variables."
        )
    
    data = {
        'client_id': 'cdse-public',
        'username': username,
        'password': password,
        'grant_type': 'password'
    }
    
    logger.info("Requesting new CDSE access token...")
    try:
        r = requests.post(AUTH_URL, data=data, timeout=60)
        r.raise_for_status()
        _ACCESS_TOKEN = r.json()['access_token']
        return _ACCESS_TOKEN
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to get access token: {e}")
        raise RuntimeError(f"Authentication failed: {e}")


def _execute_odata_query(params: Dict[str, str]) -> Dict[str, Any]:
    """
    Executes the OData query, automatically handling 401 token refresh.

    Args:
        params (Dict[str, str]): The OData query parameters.

    Returns:
        Dict[str, Any]: The JSON response from the CDSE API.
        
    Raises:
        requests.exceptions.RequestException: If the request fails for non-auth reasons.
    """
    token = get_access_token()
    headers = {'Authorization': f'Bearer {token}'}
    
    r = requests.get(f"{ODATA_URL}/Products", headers=headers, params=params, timeout=60)
    
    if r.status_code == 401:
        logger.warning("CDSE token expired (401). Refreshing token and retrying...")
        token = get_access_token(force_refresh=True)
        headers = {'Authorization': f'Bearer {token}'}
        r = requests.get(f"{ODATA_URL}/Products", headers=headers, params=params, timeout=60)
        
    r.raise_for_status()
    return r.json()


def advanced_query_scenes(
    roi: Dict[str, float], 
    start_year: str, 
    end_year: str, 
    frequency: str,
    orbit_direction: str = "ASCENDING"
) -> List[Dict[str, Any]]:
    """
    Queries Sentinel-1 SLC metadata with Relative Orbit Locking and Smart Fallbacks.
    Returns identically-orbited sequences suitable for interferometry.
    
    Args:
        orbit_direction: "ASCENDING", "DESCENDING", or "BOTH"
    """
    logger.info(f"Advanced Query: {start_year}-{end_year} at {frequency} freq. Orbit: {orbit_direction}")
    
    if orbit_direction == "BOTH":
        # Recursive resolution for both tracks
        asc = advanced_query_scenes(roi, start_year, end_year, frequency, "ASCENDING")
        dsc = advanced_query_scenes(roi, start_year, end_year, frequency, "DESCENDING")
        return asc + dsc
    
    w = roi.get('west', 0.0)
    s = roi.get('south', 0.0)
    e = roi.get('east', 0.0)
    n = roi.get('north', 0.0)
    wkt_polygon = f"POLYGON(({w} {s}, {e} {s}, {e} {n}, {w} {n}, {w} {s}))"

    # 1. Translate string years and frequency to a target list of dates
    start_date = parse_flexible_date(start_year)
    end_date = parse_flexible_date(end_year)
    
    # Inclusive End Year Fix: If the frontend sends just a 4-digit year, make it Dec 31st
    if len(str(end_year).strip()) == 4:
        end_date = date(int(end_year), 12, 31)
    
    years_span = max(end_date.year - start_date.year + 1, 1)
    if frequency == "Monthly":
        samples = years_span * 12
        ref_day = ""
    elif frequency == "Quarterly":
        samples = years_span * 4
        ref_day = ""
    else: # Yearly — 1 scene per year, consecutive scenes form interferometric pairs
        samples = years_span
        ref_day = "06-15"  # Lock yearly queries to mid-summer for consistent interferometry
        
    dates_dict = generate_search_windows(
        start_date, 
        end_date, 
        samples, 
        window_days=15, 
        reference_month_day=ref_day
    )
    sorted_keys = sorted(dates_dict.keys())
    
    # 2. Sequential Query Loop (Locking the Orbit)
    results: List[Dict[str, Any]] = []
    locked_relative_orbit: Optional[int] = None

    def _extract_relative_orbit(product: Dict[str, Any]) -> Optional[int]:
        for att in product.get("Attributes", []):
            if att.get("Name") == "relativeOrbitNumber":
                return att.get("Value")
        return None

    def _search_window(win_start: date, win_end: date, require_orbit: Optional[int]) -> Optional[Dict[str, Any]]:
        s_date = win_start.strftime('%Y-%m-%dT%H:%M:%S.000Z')
        e_date = win_end.strftime('%Y-%m-%dT%H:%M:%S.000Z')
        
        filters = [
            "Collection/Name eq 'SENTINEL-1'",
            f"ContentDate/Start ge {s_date}",
            f"ContentDate/End le {e_date}",
            "Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType' and att/Value eq 'SLC')",
            "Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'operationalMode' and att/Value eq 'IW')",
            f"Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'orbitDirection' and att/Value eq '{orbit_direction}')",
            f"OData.CSC.Intersects(area=geography'SRID=4326;{wkt_polygon}')"
        ]
        
        if require_orbit is not None:
             filters.append(
                f"Attributes/OData.CSC.IntegerAttribute/any("
                f"att:att/Name eq 'relativeOrbitNumber' and att/Value eq {require_orbit})"
            )
             
        params = {
            '$filter': ' and '.join(filters),
            '$expand': 'Attributes',
            '$orderby': 'ContentDate/Start asc',
            '$top': '50'
        }
        
        # CDSE WAF/Anti-Scraping protection throws HTTP 403 if OData queries burst too rapidly.
        # Adding a deliberate spacing between requests ensures 100% success rate on loop lookups.
        import time
        time.sleep(0.75)
        
        try:
            resp = _execute_odata_query(params)
            prods = resp.get('value', [])

            # Select first VV-polarized scene
            # Primary: check polarisationChannels attribute
            # Fallback: check filename pattern (IW_SLC + DV/SV encodes mode+polarization)
            for p in prods:
                attrs = p.get("Attributes", [])
                filename = p.get("Name", "")
                has_vv_attr = any(
                    att.get("Name") == "polarisationChannels" and "VV" in att.get("Value", "")
                    for att in attrs
                )
                has_vv_filename = ("_IW_SLC" in filename and ("DV" in filename or "SV" in filename))
                if has_vv_attr or has_vv_filename:
                    return p
            return None
        except RuntimeError:
            # Auth/credentials errors must propagate — don't swallow them
            raise
        except Exception as e:
            logger.error(f"Search window failed: {e}")
            return None

    # Track which acquisition years already have a result (used by second pass)
    result_years: set = set()

    def _build_scene(product: Dict[str, Any]) -> Dict[str, Any]:
        fname = product["Name"]
        fname_mode  = "IW"    if "_IW_" in fname else "UNKNOWN"
        fname_pol   = "VV VH" if "DV"   in fname else ("VV" if "SV" in fname else "UNKNOWN")
        fname_orbit = orbit_direction if orbit_direction in ("ASCENDING", "DESCENDING") else "UNKNOWN"
        scene = {
            "id": product["Id"],
            "filename": fname,
            "acquisitionDate": product["ContentDate"]["Start"],
            "downloadURL": f"{ODATA_URL}/Products({product['Id']})/$value",
            "orbitDirection": fname_orbit,
            "polarization": fname_pol,
            "mode": fname_mode,
        }
        for att in product.get("Attributes", []):
            name = att.get("Name"); val = att.get("Value")
            if name == "orbitDirection":         scene["orbitDirection"] = val
            elif name == "polarisationChannels": scene["polarization"]   = val
            elif name in ("operationalMode", "sensorOperationalMode"): scene["mode"] = val
        return scene

    # FIRST PASS — forward in time.
    # The orbit lock is acquired naturally from the first successful hit.
    # Fallbacks always run (not just when locked) so the lock is established
    # even when the primary ±15-day window misses.
    for key in sorted_keys:
        target_range = dates_dict[key]

        found_product = _search_window(target_range[0], target_range[1], locked_relative_orbit)

        if not found_product:
            target_mid = target_range[0] + (target_range[1] - target_range[0]) / 2
            for fb_label, fb_range in generate_fallback_windows(target_mid):
                logger.info(f"Fallback {fb_label}...")
                found_product = _search_window(fb_range[0], fb_range[1], locked_relative_orbit)
                if found_product:
                    break

        if found_product:
            if locked_relative_orbit is None:
                locked_relative_orbit = _extract_relative_orbit(found_product)
                if locked_relative_orbit is not None:
                    logger.info(f"LOCKED Relative Orbit: {locked_relative_orbit}")
            scene = _build_scene(found_product)
            results.append(scene)
            result_years.add(scene["acquisitionDate"][:4])

    # SECOND PASS — retry any expected year that has no result yet, now using the
    # orbit lock established in the first pass.  This recovers scenes for early
    # years that were searched before the lock was available.
    if locked_relative_orbit is not None:
        for key in sorted_keys:
            target_range = dates_dict[key]
            target_year = str(target_range[0].year)
            if target_year in result_years:
                continue

            logger.info(f"Second-pass retry for {target_year} (orbit={locked_relative_orbit})...")
            found_product = _search_window(target_range[0], target_range[1], locked_relative_orbit)
            if not found_product:
                target_mid = target_range[0] + (target_range[1] - target_range[0]) / 2
                for _, fb_range in generate_fallback_windows(target_mid):
                    found_product = _search_window(fb_range[0], fb_range[1], locked_relative_orbit)
                    if found_product:
                        break
            if found_product:
                scene = _build_scene(found_product)
                results.append(scene)
                result_years.add(scene["acquisitionDate"][:4])
                logger.info(f"Second-pass recovered {orbit_direction} scene for {target_year}.")

    logger.info(f"Advanced Query returned {len(results)} fully-paired InSAR scenes.")
    return results

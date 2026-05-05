import os
import logging
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from pipeline.download_manager import start_download, get_download_status
from mineguard.backend.services.scene_query import advanced_query_scenes
from mineguard.backend.services.scene_filter import filter_scenes, estimate_download_size
from mineguard.backend.services.scene_storage import get_existing_scenes, remove_existing_scenes
from src.utils.config_loader import sync_config_from_gui
from shared.config import SCENE_STORAGE_PATH, PROJECT_ROOT

RAW_DATA_DIR = PROJECT_ROOT / SCENE_STORAGE_PATH

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/downloads", tags=["Downloads"])

# --- Request Models ---

class QueryRequest(BaseModel):
    north: float
    south: float
    east: float
    west: float
    start_year: str
    end_year: str
    frequency: str = "Monthly"
    orbit_mode: str = "ASCENDING"  # "ASCENDING", "DESCENDING", or "BOTH"

class StartDownloadRequest(BaseModel):
    scenes: List[Dict[str, Any]]

class LinkDirectoryRequest(BaseModel):
    directory_path: str
    orbit_mode: str = "UNKNOWN"  # "ASCENDING", "DESCENDING", or "BOTH"/"UNKNOWN" for local files

# --- Endpoints ---

@router.post("/query-scenes")
def api_query_scenes(request: QueryRequest):
    """
    Queries CDSE API for Sentinel-1 scenes matching the ROI and Timeline.
    Filters the results strictly for InSAR (IW, VV, Consistent Orbit).
    """
    roi_dict = {
        "north": request.north,
        "south": request.south,
        "east": request.east,
        "west": request.west
    }
    
    # 0. Sync user selections back to config.yaml for SNAP pipeline
    sync_config_from_gui(roi_dict, request.start_year, request.end_year, request.frequency)
    
    # 1. Broad CDSE Query (Now featuring multi-orbit track resolution)
    logger.info(f"Executing advanced CDSE scene query ({request.orbit_mode}) with {request.frequency} cadence...")
    try:
        raw_scenes = advanced_query_scenes(
            roi_dict,
            request.start_year,
            request.end_year,
            request.frequency,
            request.orbit_mode
        )
    except RuntimeError as e:
        # Authentication or credentials error — surface it clearly to the frontend
        raise HTTPException(status_code=503, detail=str(e))
    
    if not raw_scenes:
        return {
            "totalFound": 0,
            "filteredScenes": [],
            "estimatedDownloadSize": "0 GB"
        }
        
    # 2. Strict InSAR Filtering and Grouping by Orbit
    logger.info(f"Filtering {len(raw_scenes)} raw scenes via InSAR criteria (orbit_mode={request.orbit_mode})...")
    filtered_scenes = filter_scenes(
        raw_scenes, roi_dict,
        int(request.start_year), int(request.end_year),
        orbit_mode=request.orbit_mode
    )
    
    # Separate scenes by Orbit Direction to avoid mixing up tracks
    orbit_groups: Dict[str, List[Dict[str, Any]]] = {}
    for s in filtered_scenes:
        od = s.get('orbitDirection', 'UNKNOWN')
        if od not in orbit_groups:
            orbit_groups[od] = []
        orbit_groups[od].append(s)

    generated_pairs = []
    
    for od, scenes in orbit_groups.items():
        # Sort chronologically within the orbit group
        scenes.sort(key=lambda x: x["acquisitionDate"])
        
        # Generate sequential pairs for this specific orbit track
        for i in range(len(scenes) - 1):
            pair = {
                "master": scenes[i],
                "slave": scenes[i+1],
                "pair_name": f"{od}_{scenes[i]['acquisitionDate'][:10]}_{scenes[i+1]['acquisitionDate'][:10]}",
                "orbit": od
            }
            generated_pairs.append(pair)
        
    # 3. Size Estimation
    min_gb, max_gb = estimate_download_size(filtered_scenes)
    est_size_str = f"{min_gb:.0f} - {max_gb:.0f} GB"

    # 4. Compute per-orbit coverage gaps so the frontend can tell the user
    #    exactly which years have no available scene in CDSE.
    start_y = int(request.start_year)
    end_y   = int(request.end_year)
    expected_years = [str(y) for y in range(start_y, end_y + 1)]

    asc_years = {s["acquisitionDate"][:4] for s in filtered_scenes
                 if s.get("orbitDirection", "").upper() == "ASCENDING"}
    dsc_years = {s["acquisitionDate"][:4] for s in filtered_scenes
                 if s.get("orbitDirection", "").upper() == "DESCENDING"}

    missing_asc = sorted([y for y in expected_years if y not in asc_years]) \
        if request.orbit_mode.upper() in ("ASCENDING", "BOTH") else []
    missing_dsc = sorted([y for y in expected_years if y not in dsc_years]) \
        if request.orbit_mode.upper() in ("DESCENDING", "BOTH") else []

    if missing_asc:
        logger.warning(f"No ASCENDING scenes found for years: {missing_asc}. "
                       f"CDSE likely has no IW SLC coverage for this ROI in those years.")
    if missing_dsc:
        logger.warning(f"No DESCENDING scenes found for years: {missing_dsc}.")

    # 5. Persist scene manifest so link-local-directory can resolve ASC/DSC per filename.
    import json as _json
    manifest: dict = {}
    for s in filtered_scenes:
        bare = s["filename"].replace(".zip", "").replace(".SAFE", "")
        manifest[bare] = s.get("orbitDirection", "UNKNOWN")
    manifest_path = PROJECT_ROOT / "pipeline" / "scene_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w") as _f:
        _json.dump(manifest, _f, indent=2)
    logger.info(f"Scene manifest saved ({len(manifest)} entries) → {manifest_path}")

    return {
        "totalFound": len(filtered_scenes),
        "filteredScenes": filtered_scenes,
        "generatedPairs": generated_pairs,
        "estimatedDownloadSize": est_size_str,
        "missingCoverage": {
            "ascending": missing_asc,
            "descending": missing_dsc
        }
    }


@router.post("/start-download")
def api_start_download(request: StartDownloadRequest):
    """
    Accepts a validated list of scenes and spins up the ThreadPoolExecutor
    to begin downloading them into pipeline/data/raw/.
    """
    if not request.scenes:
        raise HTTPException(status_code=400, detail="Scene list is empty.")
        
    # 1. Deduplication Check (Avoid re-downloading existing files)
    pending_scenes = remove_existing_scenes(request.scenes)
    
    if not pending_scenes:
        logger.info("All requested scenes already exist locally. Nothing to download.")
        return {"message": "All requested scenes already downloaded complete.", "started": False}
        
    # 2. Fire and Forget the ThreadPoolExecutor (Don't await to block the API response)
    import threading
    download_thread = threading.Thread(
        target=start_download,
        args=(pending_scenes,),
        daemon=True
    )
    download_thread.start()
    
    return {
        "message": f"Successfully started downloading {len(pending_scenes)} scenes.",
        "started": True
    }


@router.get("/download-status")
def api_download_status():
    """
    Returns the real-time polling state of the thread pool executor queue so React can draw progress loaders natively.
    """
    from pipeline.download_manager import get_download_status
    return get_download_status()


@router.post("/link-local-directory")
def api_link_local_directory(request: LinkDirectoryRequest):
    """
    Ingests local .zip files from a user's directory, mapping them directly
    into the primary raw data pool to avoid massive browser uploads.
    """
    from typing import Optional as _Optional
    from pathlib import Path
    
    dir_path = Path(request.directory_path.strip('"').strip("'"))
    if not dir_path.is_dir():
         raise HTTPException(status_code=400, detail="Invalid directory path. Make sure the folder exists.")
         
    try:
        # ── Direct scan: collect ALL Sentinel-1 SLC ZIPs in the folder ──────────
        # scan_existing_local_years() is intentionally NOT used here because it:
        #   1. Returns only ONE file per calendar year (dict keyed by year), so
        #      a folder with 5 ASC + 5 DSC files across the same 5 years yields
        #      only 5 files instead of 10.
        #   2. Enforces a 6 GB minimum size, rejecting valid CDSE downloads that
        #      are commonly 2–5 GB.
        import re as _re
        from src.utils.config_loader import load_config
        cfg = load_config()
        data_window = cfg.get("data_window", {})
        start_year = int(data_window.get("start_date", "2015")[:4])
        end_year   = int(data_window.get("end_date",   "2025")[:4])

        def _year_from_fname(fname: str) -> _Optional[int]:
            m = _re.search(r'_(20\d{2})\d{4}T', fname)
            return int(m.group(1)) if m else None

        all_zips = [
            f for f in dir_path.iterdir()
            if f.suffix.lower() == ".zip"
            and "S1" in f.name.upper()
            and "IW_SLC" in f.name.upper()
        ]

        valid_files = [
            f for f in all_zips
            if _year_from_fname(f.name) is not None
            and start_year <= _year_from_fname(f.name) <= end_year
        ]

        if not valid_files:
            raise HTTPException(
                status_code=400,
                detail=(f"No Sentinel-1 IW SLC .zip files found in '{dir_path}' "
                        f"for years {start_year}–{end_year}. "
                        f"Ensure filenames contain 'S1' and 'IW_SLC'.")
            )

        linked_names = []
        RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

        for src_path in valid_files:
            fname = src_path.name
            dest_path = RAW_DATA_DIR / fname
            if not dest_path.exists():
                try:
                    os.symlink(src_path, dest_path)
                except OSError:
                    import shutil as _shutil
                    _shutil.copy2(src_path, dest_path)
            linked_names.append(fname)

        # Load the scene manifest early so orbit direction is available for the response
        import json as _json
        manifest_path = PROJECT_ROOT / "pipeline" / "scene_manifest.json"
        manifest: dict = {}
        if manifest_path.exists():
            try:
                with open(manifest_path) as _f:
                    manifest = _json.load(_f)
                logger.info(f"Loaded scene manifest with {len(manifest)} entries.")
            except Exception as _e:
                logger.warning(f"Could not load scene manifest: {_e}")

        abs_orbit_to_direction: dict = {}
        for manifest_key, direction in manifest.items():
            mo = _re.search(r'_(\d{6})_[0-9A-Fa-f]{6}_', manifest_key)
            if mo:
                abs_orbit_to_direction[mo.group(1)] = direction

        def _lookup_orbit(fname: str) -> str:
            bare = fname.replace(".zip", "").replace(".SAFE", "")
            if bare in manifest:
                return manifest[bare]
            mo = _re.search(r'_(\d{6})_[0-9A-Fa-f]{6}_', fname)
            if mo and mo.group(1) in abs_orbit_to_direction:
                return abs_orbit_to_direction[mo.group(1)]
            orbit_mode_upper = request.orbit_mode.upper()
            if orbit_mode_upper in ("ASCENDING", "DESCENDING"):
                return orbit_mode_upper
            return "UNKNOWN"
                
        # ── Generate Processing Queue Pairs ──────────────────────────────────────
        from pipeline.processing_queue import add_interferogram_pairs, clear_queue

        # Clear old pairs from a previous run so the UI isn't cluttered
        clear_queue()
        logger.info("Cleared old processing queue pairs.")

        orbit_mode_upper = request.orbit_mode.upper()

        def get_date_from_name(f: str) -> str:
            match = _re.search(r'_20\d{6}T', f)
            return match.group(0)[1:9] if match else f

        linked_names.sort(key=get_date_from_name)

        # Build scene dicts with resolved orbit direction for each file.
        # _lookup_orbit() uses the manifest + abs-orbit index built above.
        mock_scenes = []
        for fname in linked_names:
            orbit_dir = _lookup_orbit(fname)
            mock_scenes.append({
                "id": f"manual-{get_date_from_name(fname)}",
                "filename": fname,
                "acquisitionDate": get_date_from_name(fname),
                "orbitDirection": orbit_dir,
            })

        num_pairs = 0

        if mock_scenes:
            if orbit_mode_upper in ("ASCENDING", "DESCENDING"):
                # Single orbit: tag all pairs with the selected direction
                add_interferogram_pairs(mock_scenes, orbit=orbit_mode_upper)
                num_pairs = max(0, len(mock_scenes) - 1)
                logger.info(f"Queued {num_pairs} pairs (orbit={orbit_mode_upper}).")
            else:
                # BOTH / UNKNOWN: split scenes by resolved orbit, generate pairs per track
                asc_scenes = [s for s in mock_scenes if s["orbitDirection"] == "ASCENDING"]
                dsc_scenes = [s for s in mock_scenes if s["orbitDirection"] == "DESCENDING"]
                unk_scenes = [s for s in mock_scenes
                              if s["orbitDirection"] not in ("ASCENDING", "DESCENDING")]

                if asc_scenes:
                    add_interferogram_pairs(asc_scenes, orbit="ASCENDING")
                    logger.info(f"Queued {max(0,len(asc_scenes)-1)} ASC pairs.")
                if dsc_scenes:
                    add_interferogram_pairs(dsc_scenes, orbit="DESCENDING")
                    logger.info(f"Queued {max(0,len(dsc_scenes)-1)} DSC pairs.")
                if unk_scenes:
                    add_interferogram_pairs(unk_scenes, orbit="UNKNOWN")
                    logger.warning(f"Queued {max(0,len(unk_scenes)-1)} UNKNOWN-orbit pairs "
                                   f"(not in manifest — 2D decomposition unavailable for these).")
                num_pairs = (max(0, len(asc_scenes) - 1) + max(0, len(dsc_scenes) - 1)
                             + max(0, len(unk_scenes) - 1))

        logger.info(f"Directory linked: {len(linked_names)} files mapped to raw staging.")
        return {
            "message": f"Successfully linked {len(linked_names)} files and queued {num_pairs} pairs for processing.",
            # Return per-file objects so the frontend can split ASC/DSC correctly in the UI
            "linked_scenes": [
                {"filename": s["filename"], "orbitDirection": s["orbitDirection"]}
                for s in mock_scenes
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Directory linking failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Linking failed: {str(e)}")


@router.get("/proxy-download/{scene_id}")
def api_proxy_download(scene_id: str, filename: str = "scene.zip"):
    """Stream a Sentinel-1 scene from CDSE through our backend as a reverse proxy.

    The browser opens this URL directly. FastAPI injects the Bearer token
    server-side, streams the 4GB+ zip via chunked transfer, and the
    browser's native download manager handles the rest.

    Args:
        scene_id: The CDSE product UUID.
        filename: Optional filename for Content-Disposition header.
    """
    import requests as req
    from fastapi.responses import StreamingResponse
    from mineguard.backend.services.scene_query import get_access_token

    ODATA_URL = "https://zipper.dataspace.copernicus.eu/odata/v1"
    download_url = f"{ODATA_URL}/Products({scene_id})/$value"

    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    logger.info(f"Proxy download started for scene {scene_id} -> {filename}")

    try:
        upstream = req.get(download_url, headers=headers, stream=True, allow_redirects=True, timeout=60)

        # Handle 401 with a single token refresh retry
        if upstream.status_code == 401:
            logger.warning("CDSE token expired during proxy download. Refreshing...")
            token = get_access_token(force_refresh=True)
            headers = {"Authorization": f"Bearer {token}"}
            upstream = req.get(download_url, headers=headers, stream=True, allow_redirects=True, timeout=60)

        if upstream.status_code not in (200, 206):
            raise HTTPException(
                status_code=upstream.status_code,
                detail=f"CDSE returned HTTP {upstream.status_code} for product {scene_id}"
            )

        # Build response headers for the browser download manager
        content_length = upstream.headers.get("Content-Length")
        resp_headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
        }
        if content_length:
            resp_headers["Content-Length"] = content_length

        def stream_chunks():
            """Yield 4MB chunks from CDSE upstream."""
            for chunk in upstream.iter_content(chunk_size=4 * 1024 * 1024):
                if chunk:
                    yield chunk

        return StreamingResponse(
            stream_chunks(),
            media_type="application/zip",
            headers=resp_headers,
        )

    except req.exceptions.RequestException as e:
        logger.error(f"Proxy download failed for {scene_id}: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to connect to CDSE: {str(e)}")


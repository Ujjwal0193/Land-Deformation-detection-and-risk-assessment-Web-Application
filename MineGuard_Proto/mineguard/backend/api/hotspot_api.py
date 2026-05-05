"""hotspot_api.py — FastAPI router for translating geographic Hotspots to Radar Space.

Exposes endpoints for the Page 6 and Page 7 React interface:
  - POST /save   → Computes pixel coordinates and writes to config/hotspots.json
  - POST /run    → Spawns Python mapping tools to generate PNGs in /results
  - GET /results → Returns status of completed analysis image paths
"""

import os
import sys
import csv
import json
import logging
import subprocess
from typing import List, Dict, Any, Optional
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from shared.config import PROJECT_ROOT
from src.hotspot_tracker import get_interferogram_list, _load_tie_points, _geo_to_pixel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/hotspots", tags=["Hotspots"])

class HotspotObj(BaseModel):
    lat: float
    lon: float
    color: str
    label: str

class SaveHotspotsRequest(BaseModel):
    hotspots: List[HotspotObj]

@router.post("/save")
def api_save_hotspots(req: SaveHotspotsRequest) -> Dict[str, Any]:
    """
    Accepts geographic pins from Leaflet frontend.
    Extracts tie-point grid from earliest processed .dim dataset to translate 
    to precise Sentinel-1 synthetic aperture radar pixels.
    Saves the JSON configuration correctly for python matplotlib graphing logic.
    """
    ifgs = get_interferogram_list()
    if not ifgs:
        raise HTTPException(
            status_code=400, 
            detail="No interferograms exist to extract tie-points. Ensure Processing (Page 5) finished successfully."
        )
        
    first_ifg = ifgs[0]
    tp_data = _load_tie_points(first_ifg['data_dir'])
    if not tp_data:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to load tie-point matrix from primary dataset: {first_ifg['basename']}"
        )
        
    lat_grid, lon_grid, img_shape = tp_data
    
    tracker_hotspots = []
    
    for idx, h in enumerate(req.hotspots):
        try:
            px, py = _geo_to_pixel(h.lat, h.lon, lat_grid, lon_grid, img_shape)
            tracker_hotspots.append({
                "id": idx + 1,
                "label": h.label,
                "lat": h.lat,
                "lon": h.lon,
                "x": int(px),
                "y": int(py),
                "color": h.color
            })
            logger.info(f"Geomapped {h.label} ({h.lat}, {h.lon}) -> Px({int(px)}, {int(py)})")
        except Exception as e:
            logger.error(f"Failed coordinate mapping for hotspot {idx} ({h.label}): {e}")
            raise HTTPException(status_code=500, detail=f"Failed mapping radar coordinates on {h.label}")
            
    # Write to local tracking file path expected by advanced_analysis.py
    hotspots_file = PROJECT_ROOT / "config" / "hotspots.json"
    hotspots_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(hotspots_file, "w", encoding="utf-8") as f:
        json.dump(tracker_hotspots, f, indent=4)
        
    return {
        "message": f"Successfully mapped and saved {len(tracker_hotspots)} local tracker identifiers.",
        "count": len(tracker_hotspots)
    }

# Track async graphing execution 
_analysis_process = None

@router.post("/run")
def api_run_analysis():
    """
    Background-spawns the extensive Matplotlib visualization toolkit
    (advanced_analysis.py and portions of hotspot_tracker.py).
    """
    global _analysis_process
    
    if _analysis_process is not None and _analysis_process.poll() is None:
         return {"message": "Analysis is already crunching data...", "running": True}
         
    script_path = str(PROJECT_ROOT / "src" / "advanced_analysis.py")
    python_exe = sys.executable
    
    logger.info(f"Spawning Advanced Analysis graph generator: {python_exe} {script_path}")
    
    try:
        log_file_path = PROJECT_ROOT / "logs" / "advanced_analysis.log"
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = open(log_file_path, "a", encoding="utf-8")
        
        _analysis_process = subprocess.Popen(
            [python_exe, script_path],
            cwd=str(PROJECT_ROOT),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        )
        return {"message": "Analytics engine fired up.", "running": True}
    except Exception as e:
        logger.error(f"Analysis boot failure: {e}")
        raise HTTPException(status_code=500, detail="Failed to hook advanced metrics generator.")


@router.get("/results")
def api_pull_results():
    """
    Polls the status of the background analysis toolkit.
    Returns the paths of freshly minted graphs if available.
    """
    global _analysis_process
    
    res_dir = PROJECT_ROOT / "results"
    
    # Collect available PNGs
    graphs = []
    if res_dir.exists():
        graphs = [f.name for f in res_dir.iterdir() if f.is_file() and f.suffix == '.png']
        
    running = _analysis_process is not None and _analysis_process.poll() is None
    
    return {
        "running": running,
        "graphs": graphs,
        "dir": "/results"  # Staticly mounted FastApi alias
    }

@router.get("/list")
def api_get_hotspots():
    """
    Retrieves the currently saved hotspots JSON config.
    Used by the Page 7 Results Dashboard to render a static Map Preview.
    """
    hotspots_file = PROJECT_ROOT / "config" / "hotspots.json"
    if not hotspots_file.exists():
        return {"hotspots": []}
        
    try:
        with open(hotspots_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {"hotspots": data}
    except Exception as e:
        logger.error(f"Failed to load hotspots: {e}")
        return {"hotspots": []}


@router.get("/roi")
def api_get_roi():
    """Retrieves the ROI bounding box from config.yaml or interferogram metadata.
    
    Falls back to extracting the bbox from processed interferogram
    tie-point grids when the config doesn't contain explicit bbox data.
    """
    import yaml
    config_path = PROJECT_ROOT / "config" / "config.yaml"
    
    # Strategy 1: Read explicit bbox from config.yaml
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            roi = cfg.get("roi", {})
            if all(k in roi for k in ("north", "south", "east", "west")):
                return {"bbox": {
                    "north": roi["north"],
                    "south": roi["south"],
                    "east": roi["east"],
                    "west": roi["west"],
                }}
        except Exception as e:
            logger.error(f"Failed to read ROI from config: {e}")
    
    # Strategy 2: Derive bbox from interferogram tie-point grids
    try:
        ifgs = get_interferogram_list()
        if ifgs:
            tp_data = _load_tie_points(ifgs[0]['data_dir'])
            if tp_data:
                lat_grid, lon_grid, _ = tp_data
                bbox = {
                    "north": float(lat_grid.max()),
                    "south": float(lat_grid.min()),
                    "east": float(lon_grid.max()),
                    "west": float(lon_grid.min()),
                }
                logger.info(f"Derived ROI bbox from tie-points: {bbox}")
                return {"bbox": bbox}
    except Exception as e:
        logger.error(f"Failed to derive ROI from tie-points: {e}")
    
    return {"bbox": None}

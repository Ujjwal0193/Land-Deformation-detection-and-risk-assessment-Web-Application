import os
import sys
import time
import requests
import logging
import threading
import concurrent.futures
from typing import List, Dict, Any

from shared.config import PROJECT_ROOT, SCENE_STORAGE_PATH, MAX_DOWNLOAD_WORKERS, DOWNLOAD_RETRY_LIMIT

# Import local backend service logic
sys.path.insert(0, str(PROJECT_ROOT / "mineguard"))
try:
    from mineguard.backend.services.scene_query import get_access_token
except ImportError:
    logger = logging.getLogger(__name__)
    logger.error("Could not import scene_query. Ensure MineGuard module is in path.")

logger = logging.getLogger(__name__)

RAW_DATA_DIR = PROJECT_ROOT / SCENE_STORAGE_PATH

# --- Global Download Status Tracking ---
status_lock = threading.Lock()

download_status = {
    "is_active": False,
    "total_files": 0,
    "completed_files": 0,
    "current_file": None,
    "total_bytes": 0,
    "downloaded_bytes": 0,
    "progress_percentage": 0.0,
    "download_speed_mbps": 0.0,
    "estimated_time_remaining_sec": 0.0
}

# Speed tracking variables
_last_speed_time = 0.0
_last_speed_bytes = 0

def get_download_status() -> Dict[str, Any]:
    """
    Exposes a thread-safe snapshot of the current global download pipeline status.
    This is intended to be consumed by the FastAPI endpoints feeding the Page-4 UI.
    """
    with status_lock:
        return dict(download_status)

def _reset_status(total_files: int):
    global _last_speed_time, _last_speed_bytes
    with status_lock:
        download_status.update({
            "is_active": True,
            "total_files": total_files,
            "completed_files": 0,
            "current_file": None,
            "total_bytes": 0,
            "downloaded_bytes": 0,
            "progress_percentage": 0.0,
            "download_speed_mbps": 0.0,
            "estimated_time_remaining_sec": 0.0
        })
        _last_speed_time = time.time()
        _last_speed_bytes = 0

def _update_progress(chunk_size: int, filename: str, expected_size: int):
    """Safely updates global progress counters and calculates real-time download speed."""
    global _last_speed_time, _last_speed_bytes
    
    with status_lock:
        download_status["current_file"] = filename
        download_status["downloaded_bytes"] += chunk_size
        
        # Only set total bytes once per file to avoid constant locking overwrites
        if download_status["total_bytes"] == 0 and expected_size > 0:
            # If we know the sum expected size of all files, we use that.
            # But CDSE often chunk-encodes streams, so we rely on tracking the current file dynamically if overall is unknown.
            pass
            
        current_time = time.time()
        time_diff = current_time - _last_speed_time
        
        # Recalculate speed matrix every ~1.5 seconds for smoothness
        if time_diff > 1.5:
            bytes_diff = download_status["downloaded_bytes"] - _last_speed_bytes
            speed_bps = bytes_diff / time_diff if time_diff > 0 else 0
            speed_mbps = speed_bps / (1024 * 1024)
            
            download_status["download_speed_mbps"] = round(speed_mbps, 2)
            
            # If we have an expected size logic, update ETA. Otherwise leave as N/A until we handle full queue logic.
            # We base percentage on completed files vs total files for overall progress accuracy.
            
            _last_speed_time = current_time
            _last_speed_bytes = download_status["downloaded_bytes"]


def _download_single_scene(scene: Dict[str, Any]) -> bool:
    """
    Downloads a single Sentinel-1 scene from CDSE API utilizing stream chunking.
    Includes smart retry-logic governed by DOWNLOAD_RETRY_LIMIT.

    Args:
        scene (Dict[str, Any]): Dictionary containing 'id', 'filename', and 'downloadURL'.

    Returns:
        bool: True if downloaded perfectly, False if failed.
    """
    url = scene.get('downloadURL')
    raw_filename = scene.get('filename', 'Unknown_Scene')
    
    # Preemptively enforce required .zip suffix for Sentinel SLC files
    if not raw_filename.endswith('.zip'):
        raw_filename += '.zip'
        
    out_path = RAW_DATA_DIR / raw_filename
    
    expected_file_size = 0
    existing_size = 0
    
    if out_path.exists():
        existing_size = os.path.getsize(out_path)

    logger.info(f"Download start: {raw_filename}")
    
    for attempt in range(1, DOWNLOAD_RETRY_LIMIT + 1):
        try:
            token = get_access_token()
            headers = {'Authorization': f'Bearer {token}'}

            # 1. Fetch exact file size using HEAD to determine if we can skip/resume
            try:
                head_r = requests.head(url, headers=headers, allow_redirects=True, timeout=30)
                if 'content-length' in head_r.headers:
                    expected_file_size = int(head_r.headers['content-length'])
            except Exception as e:
                logger.debug(f"HEAD request failed: {e}")
                
            # If we know the size, and the file is that size (or somehow larger), it's already done
            if expected_file_size > 0 and existing_size >= expected_file_size:
                logger.info(f"[SKIP] Validated complete scene already exists: {raw_filename} ({existing_size/(1024**3):.2f} GB)")
                with status_lock:
                    download_status["completed_files"] += 1
                    if download_status["total_files"] > 0:
                        download_status["progress_percentage"] = round((download_status["completed_files"] / download_status["total_files"]) * 100, 2)
                return True

            # 2. Assign Range headers if we have a partial file
            if existing_size > 0:
                headers['Range'] = f'bytes={existing_size}-'
                logger.info(f"[RESUME CHECK] Requesting Continuation from byte {existing_size}...")

            with requests.get(url, headers=headers, stream=True, allow_redirects=True, timeout=60) as r:
                
                if r.status_code == 401:
                    logger.warning(f"[Attempt {attempt}/{DOWNLOAD_RETRY_LIMIT}] 401 Unauthorized for {raw_filename}. Forcing token refresh.")
                    get_access_token(force_refresh=True)
                    continue 
                
                r.raise_for_status()
                
                # Verify if the server accepted our Partial Content request
                mode = 'ab' if r.status_code == 206 else 'wb'
                if mode == 'wb':
                     if existing_size > 0:
                         logger.warning(f"[RESUME REJECTED] Server did not return HTTP 206. Restarting {raw_filename} from byte 0.")
                     existing_size = 0 # reset tracked
                else:
                     logger.info(f"[RESUME ACCEPTED] Seamlessly continuing {raw_filename} from byte {existing_size}.")
                     
                if expected_file_size == 0 and 'content-length' in r.headers:
                     expected_file_size = int(r.headers['content-length']) + (existing_size if mode == 'ab' else 0)
                
                with open(out_path, mode) as f:
                    for chunk in r.iter_content(chunk_size=4*1024*1024): 
                        if chunk: 
                            f.write(chunk)
                            _update_progress(len(chunk), raw_filename, expected_file_size)
            
            # Post-download validation
            final_size = os.path.getsize(out_path)
            # Sentinel zips are usually > 4GB. If it's oddly small, it's corrupted HTML.
            if final_size < (1024 * 1024 * 1024): 
                 logger.error(f"[CORRUPTION ERROR] Downloaded file is suspiciously small ({final_size} bytes). Deleting.")
                 os.remove(out_path)
                 existing_size = 0
                 continue # trigger next retry attempt
            
            logger.info(f"Download complete: {raw_filename}")
            
            with status_lock:
                download_status["completed_files"] += 1
                if download_status["total_files"] > 0:
                    download_status["progress_percentage"] = round((download_status["completed_files"] / download_status["total_files"]) * 100, 2)
                    
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"[Attempt {attempt}/{DOWNLOAD_RETRY_LIMIT}] Download interrupted for {raw_filename}: {e}")
            
            # DO NOT DELETE the file on connection drops so we can HTTP Resume on the next attempt loop
            if out_path.exists():
                existing_size = os.path.getsize(out_path)
            
            if attempt < DOWNLOAD_RETRY_LIMIT:
                logger.info(f"Backing off for 15 seconds before retry {attempt + 1}...")
                time.sleep(15)

    logger.error(f"[FAIL] Exhausted all {DOWNLOAD_RETRY_LIMIT} tracking retries for {raw_filename}.")
    return False


def start_download(scene_list: List[Dict[str, Any]]) -> None:
    """
    Executes a threaded downloading queue based on MAX_DOWNLOAD_WORKERS limit.
    Filters out previously downloaded targets, then spins up the ThreadPoolExecutor.

    Args:
        scene_list (List[Dict[str, Any]]): The filtered list of missing scenes required.
    """
    if not scene_list:
        logger.info("No scenes queued for download. Process complete.")
        return
        
    os.makedirs(RAW_DATA_DIR, exist_ok=True)
    total_scenes = len(scene_list)
    
    _reset_status(total_scenes)
    logger.info(f"Initiating ThreadPoolExecutor with {MAX_DOWNLOAD_WORKERS} workers for {total_scenes} scenes.")

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_DOWNLOAD_WORKERS) as executor:
        future_to_scene = {executor.submit(_download_single_scene, scene): scene for scene in scene_list}
        
        success_count = 0
        failure_count = 0

        for future in concurrent.futures.as_completed(future_to_scene):
            scene = future_to_scene[future]
            try:
                success = future.result()
                if success:
                    success_count += 1
                else:
                    failure_count += 1
            except Exception as exc:
                logger.error(f"Thread critically failed for scene {scene.get('filename')}: {exc}")
                failure_count += 1

    with status_lock:
        download_status["is_active"] = False
        download_status["progress_percentage"] = 100.0 if failure_count == 0 else download_status["progress_percentage"]

    logger.info("=========================================")
    logger.info("   Mass Download Operation Concluded     ")
    logger.info("=========================================")
    logger.info(f"Requested: {total_scenes}")
    logger.info(f"Successful: {success_count}")
    logger.info(f"Failed: {failure_count}")
    logger.info(f"Data resides in: {RAW_DATA_DIR}")

    # --- Auto-trigger interferogram pairing using the EXISTING queue logic ---
    if success_count > 0:
        from pipeline.processing_queue import add_interferogram_pairs
        logger.info("Automatically generating interferogram pairs from downloaded scenes...")
        add_interferogram_pairs(scene_list)

        # --- Spawn the existing SNAP worker (main_script.py) as a background subprocess ---
        import subprocess
        snap_script = str(PROJECT_ROOT / "src" / "main_script.py")
        logger.info(f"Launching SNAP Processing Worker: {snap_script}")
        try:
            subprocess.Popen(
                [sys.executable, snap_script],
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info("SNAP Worker spawned successfully. Processing will run in the background.")
        except Exception as e:
            logger.error(f"Failed to spawn SNAP Worker: {e}")

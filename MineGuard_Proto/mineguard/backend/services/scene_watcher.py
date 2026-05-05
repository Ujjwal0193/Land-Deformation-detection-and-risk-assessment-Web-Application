import os
import time
import logging
from threading import Thread
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from shared.config import PROJECT_ROOT, SCENE_STORAGE_PATH
from pipeline.download_manager import download_status, status_lock

logger = logging.getLogger(__name__)
RAW_DATA_DIR = PROJECT_ROOT / SCENE_STORAGE_PATH

class SentinelDownloadHandler(FileSystemEventHandler):
    """
    Watches for strictly Sentinel-1 '.zip' file creations or rename completions
    inside the download directory. Ignored temporary '.crdownload' or '.part'.
    """
    
    def _process_file(self, file_path: str):
        filename = os.path.basename(file_path)
        
        # 1. Validation Logic
        if not filename.endswith(".zip"):
             return
             
        if "S1" not in filename or "SLC" not in filename or "IW" not in filename or "VV" not in filename:
             logger.warning(f"Watcher ignored non-InSAR zip: {filename}")
             return
             
        # 2. Wait strictly for the browser file-lock to release
        # Chrome/Edge locks files while downloading. We poll until we can open it safely.
        logger.info(f"Watcher detected incoming scene: {filename}. Awaiting browser locks...")
        retries = 0
        while retries < 60:
            try:
                # Attempt to open file exclusively to check if download finished
                with open(file_path, 'a'):
                    pass
                break
            except IOError:
                time.sleep(2)
                retries += 1
                
        if retries >= 60:
             logger.error(f"Watcher timed out waiting for file lock release on {filename}.")
             return

        # 3. Post-Download Size Validation
        size_bytes = os.path.getsize(file_path)
        if size_bytes < (1024 * 1024 * 1024):
             logger.warning(f"Watcher detected oddly small InSAR file ({size_bytes} bytes). Ignoring completion signal.")
             return
             
        # 4. Inject completion signal into React's API payload globally
        logger.info(f"Watcher successfully ingested native browser download: {filename}")
        with status_lock:
             # Ensure the tracking system knows there's an active process taking place
             if download_status["total_files"] == 0:
                  download_status["total_files"] = 1
             else:
                  # If we detect a file that wasn't in our math, bump the total dynamically
                  if download_status["completed_files"] >= download_status["total_files"]:
                       download_status["total_files"] += 1
                       
             download_status["completed_files"] += 1
             download_status["progress_percentage"] = round((download_status["completed_files"] / download_status["total_files"]) * 100, 2)
             download_status["is_active"] = (download_status["completed_files"] < download_status["total_files"])

    def on_created(self, event):
        if not event.is_directory:
            # Run in a detached thread so we don't block the watchdog observer polling mechanism while waiting for Chrome file locks
            Thread(target=self._process_file, args=(event.src_path,), daemon=True).start()

    def on_moved(self, event):
        # Triggers when a .crdownload is successfully renamed to .zip
        if not event.is_directory:
             Thread(target=self._process_file, args=(event.dest_path,), daemon=True).start()


def start_directory_watcher():
    """
    Spawns the background daemon thread watching the raw dataset folder.
    Should be called during FastAPI execution lifespan.
    """
    os.makedirs(RAW_DATA_DIR, exist_ok=True)
    
    event_handler = SentinelDownloadHandler()
    observer = Observer()
    observer.schedule(event_handler, str(RAW_DATA_DIR), recursive=False)
    
    # Start the daemon
    observer.daemon = True
    observer.start()
    
    logger.info(f"Registered Watchdog Event Listener on: {RAW_DATA_DIR}")
    return observer

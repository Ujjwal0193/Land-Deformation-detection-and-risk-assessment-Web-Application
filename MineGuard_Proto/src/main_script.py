"""main_script.py — Sentinel-1 InSAR Pipeline

Downloads Sentinel-1 SLC products from CDSE OData, pairs them
chronologically, and executes SNAP GPT interferometric processing.
"""

import os
import sys
import subprocess
import requests
import logging
import time
import shutil
import zipfile
import re
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime, date
from typing import Optional, Dict, Any, Tuple, List
import psutil
from tqdm import tqdm

# Connect the new GUI Queue architecture endpoint safely
from pipeline.processing_queue import (
    get_next_processing_task,
    mark_task_complete,
    mark_task_failed,
    recover_stuck_tasks,
    skip_already_processed_tasks,
)

# --- PATH CONFIGURATION ---
# PROJECT_ROOT is up one level from src/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
# SLC directories live at the workspace root (one level above MineGuard_Proto)
WORKSPACE_ROOT = os.path.dirname(PROJECT_ROOT)
INPUT_SLC_DIR = os.path.join(WORKSPACE_ROOT, "input_slc")
ORIGINAL_SLC_DIR = os.path.join(WORKSPACE_ROOT, "original_slc")
OUTPUT_INT_DIR = os.path.join(DATA_DIR, "output_int")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")

# Corrected graph path: src/graphs/process_graph.xml
GRAPH_PATH = os.path.join(PROJECT_ROOT, "src", "graphs", "process_graph.xml")

# --- CENTRAL CONFIG + LOGGING ---
sys.path.insert(0, PROJECT_ROOT)
from src.utils.config_loader import load_config
from src.utils.logging_setup import setup_logging

_cfg = load_config()
setup_logging("main_script", _cfg)

# Mine Site Coordinates — driven by config.yaml
_roi = _cfg.get("roi", {})
ROI_WKT = f'POINT({_roi.get("lon", 85.09)} {_roi.get("lat", 20.96)})'

# Allow dynamic subswath overriding (default to IW1)
SUBSWATH = _cfg.get("snap", {}).get("subswath", "IW1").upper()

logging.info("Configuration Loaded.")
logging.info(f"  PROJECT_ROOT: {PROJECT_ROOT}")
logging.info(f"  INPUT_SLC_DIR: {INPUT_SLC_DIR}")
logging.info(f"  OUTPUT_INT_DIR: {OUTPUT_INT_DIR}")
logging.info(f"  GRAPH_PATH: {GRAPH_PATH}")
logging.info(f"  ROI_WKT: {ROI_WKT}")


def check_snap_path() -> bool:
    """Verify SNAP GPT is accessible, searching common install paths if needed."""
    try:
        subprocess.run(['gpt', '-h'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logging.info("SNAP 'gpt' found in PATH.")
        return True
    except FileNotFoundError:
        logging.info("SNAP 'gpt' not found in PATH. Searching common locations...")
        common_paths = [
            r"C:\Program Files\snap\bin",
            r"C:\Program Files(x86)\snap\bin",
            r"C:\Program Files\esa-snap\bin"
        ]
        for path in common_paths:
            gpt_exe = os.path.join(path, 'gpt.exe')
            if os.path.exists(gpt_exe):
                logging.info(f"Found SNAP at: {path}")
                os.environ["PATH"] += os.pathsep + path
                return True
        logging.error("CRITICAL: SNAP 'gpt' not found! Please install SNAP.")
        return False


def detect_bursts_for_aoi(
    zip_path: str,
    default_subswath: str,
    aoi_lat: float,
    aoi_lon: float,
    buffer_bursts: int = 1,
) -> Tuple[int, int, str]:
    """Parse SLC annotation XML to find bursts covering an AOI point."""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            # Order to check: default first, then others
            swaths_to_check = [default_subswath.lower()]
            for sw in ['iw1', 'iw2', 'iw3']:
                if sw not in swaths_to_check:
                    swaths_to_check.append(sw)

            for sw in swaths_to_check:
                ann_files = [
                    n for n in zf.namelist()
                    if 'annotation/' in n.lower()
                    and sw in n.lower()
                    and '-vv-' in n.lower()
                    and 'calibration' not in n.lower()
                    and 'noise' not in n.lower()
                    and n.endswith('.xml')
                ]
                if not ann_files:
                    continue

                root = ET.parse(zf.open(ann_files[0])).getroot()

                bursts = root.findall('.//burst')
                lpb_el = root.find('.//linesPerBurst')
                if not bursts or lpb_el is None:
                    continue

                lines_per_burst: int = int(lpb_el.text)
                total_bursts: int = len(bursts)
                geos = root.findall('.//geolocationGridPoint')

                matching_bursts: List[int] = []
                for idx in range(total_bursts):
                    first_line = idx * lines_per_burst
                    last_line = (idx + 1) * lines_per_burst - 1
                    pts = [
                        g for g in geos
                        if first_line <= int(g.find('line').text) <= last_line
                    ]
                    if not pts:
                        continue

                    lats = [float(g.find('latitude').text) for g in pts]
                    lons = [float(g.find('longitude').text) for g in pts]
                    min_lat, max_lat = min(lats), max(lats)
                    min_lon, max_lon = min(lons), max(lons)

                    if min_lat <= aoi_lat <= max_lat and min_lon <= aoi_lon <= max_lon:
                        matching_bursts.append(idx + 1)  # 1-indexed

                if matching_bursts:
                    first = max(1, min(matching_bursts) - buffer_bursts)
                    last = min(total_bursts, max(matching_bursts) + buffer_bursts)
                    logging.info(f"  [BURST] AOI ({aoi_lat}, {aoi_lon}) found in {sw.upper()}, "
                                 f"Selected range: {first}-{last}.")
                    return (first, last, sw.upper())

            logging.warning(f"AOI ({aoi_lat}, {aoi_lon}) not found. "
                            f"Falling back to {default_subswath.upper()} all bursts.")
            return (1, 9999, default_subswath.upper())

    except Exception as e:
        logging.warning(f"Burst detection failed: {e}. Using all bursts on default subswath.")
        return (1, 9999, default_subswath.upper())


def process_pairs() -> None:
    """Pair SLC images chronologically and execute SNAP GPT interferometry.

    Continuously pulls 'pending' tasks from pipeline/data/processing_queue.json 
    generated by the Data Download UI manager.
    Detects which bursts cover the AOI dynamically for each pair.
    Uses OpenCL acceleration and optimised tiling for SLC data.
    """
    logging.info("--- Starting SAR-Optimised Processing Phase ---")

    # On startup, reset any tasks left stuck as 'processing' from a previous
    # crashed run so they are retried rather than silently skipped forever.
    recovered = recover_stuck_tasks()
    if recovered:
        logging.info(f"Startup recovery: {recovered} task(s) reset from 'processing' → 'pending'.")

    # Pre-scan: mark 'pending' tasks as 'complete' if their output .dim files
    # already exist on disk. Prevents re-running SNAP GPT for pairs that were
    # processed in a prior session but whose queue status was never updated.
    pre_skipped = skip_already_processed_tasks(OUTPUT_INT_DIR)
    if pre_skipped:
        logging.info(f"Startup pre-scan: {pre_skipped} pending task(s) already have output files — skipped.")

    cpu_count = min(os.cpu_count() or 4, 4)
    total_ram_gb = psutil.virtual_memory().total / (1024**3)
    
    # Hard limit the GPT java heap per user request
    heap_gb = min(int(total_ram_gb * 0.70), 5)
    cache_size = f"{min(int(total_ram_gb * 0.30), 2)}G"
    
    logging.info(
        f"  CPU Threads: {cpu_count}, Heap: {heap_gb}G, "
        f"Cache: {cache_size}, Total RAM: {total_ram_gb:.1f}G"
    )

    if not os.path.exists(INPUT_SLC_DIR):
        logging.error(f"Input directory {INPUT_SLC_DIR} does not exist.")
        return

    os.makedirs(OUTPUT_INT_DIR, exist_ok=True)

    # Extract AOI lat/lon from ROI_WKT (POINT format)
    pt_match = re.search(r'POINT\s*\(\s*([\-\d.]+)\s+([\-\d.]+)\s*\)', ROI_WKT)
    if pt_match:
        aoi_lon = float(pt_match.group(1))
        aoi_lat = float(pt_match.group(2))
    else:
        aoi_lon, aoi_lat = 85.09, 20.96  # fallback
        logging.warning(f"Could not parse ROI_WKT. Using default AOI: ({aoi_lat}, {aoi_lon})")

    # ==============================================================
    # Continuous Queue Processing Loop with Worker Lock
    # ==============================================================
    WORKER_LOCK_PATH = os.path.join(DATA_DIR, "worker.lock")
    from filelock import FileLock, Timeout
    
    worker_lock = FileLock(WORKER_LOCK_PATH, timeout=0)  # Try to lock instantly
    
    try:
        with worker_lock:
            logging.info("Worker Lock acquired. Starting queue processor.")
            tasks_processed = 0
            empty_polls = 0
            MAX_EMPTY_POLLS = 6  # Exit after 30 seconds of empty queue with no pending tasks

            while True:
                task = get_next_processing_task()
                if not task:
                    # Check if all tasks are in a terminal state — if so, we're done
                    from pipeline.processing_queue import _load_queue as _check_queue
                    current_q = _check_queue()
                    if current_q:
                        all_terminal = all(
                            t.get("status") in ("complete", "failed") for t in current_q
                        )
                        if all_terminal:
                            logging.info(f"All {len(current_q)} tasks are complete/failed. Worker exiting cleanly.")
                            break
                    empty_polls += 1
                    if empty_polls >= MAX_EMPTY_POLLS:
                        logging.info("Queue has been empty for 30s with no pending tasks. Worker exiting.")
                        break
                    logging.info(f"No pending tasks. Waiting... ({empty_polls}/{MAX_EMPTY_POLLS})")
                    time.sleep(5)
                    continue
                empty_polls = 0  # Reset counter when a real task is found
                    
                task_id = task.get("task_id")
                master = task.get("master_scene")
                slave = task.get("slave_scene")
                orbit = task.get("orbit", "UNK")

                # Normalise orbit to short tag: ASCENDING→ASC, DESCENDING→DSC
                # advanced_analysis.py checks for _ASC_ / _DSC_ in the basename.
                # NOTE: "DSC" is NOT a substring of "DESCENDING" (D-E-S-C not D-S-C),
                # so we must check for "ASCENDING"/"DESCENDING" explicitly.
                ou = orbit.upper()
                if "ASCENDING" in ou or ou == "ASC":
                    orbit_tag = "ASC"
                elif "DESCENDING" in ou or ou == "DSC":
                    orbit_tag = "DSC"
                else:
                    orbit_tag = "UNK"

                logging.info(f"\n[QUEUE] Handling Task {task_id} ({orbit_tag})")
                logging.info(f"Processing Pair: {master} -> {slave}")

                # Use acquisition DATES (not truncated filenames) for the output name.
                # master[:20] truncation causes collisions: all scenes from 2017-2019
                # start with the same prefix "S1A_IW_SLC__1SDV_201", so pairs
                # 2017→2018 and 2018→2019 would generate the SAME filename and the
                # second pair would be falsely skipped by the pre-existing-file check.
                master_date = task.get("master_date") or master[:8]
                slave_date  = task.get("slave_date")  or slave[:8]
                target_name = f"Int_{orbit_tag}_{master_date}_{slave_date}.dim"
                target_path = os.path.join(OUTPUT_INT_DIR, target_name)
                target_data_dir = target_path.replace('.dim', '.data')
        
                master_path = os.path.join(INPUT_SLC_DIR, master)
                slave_path = os.path.join(INPUT_SLC_DIR, slave)
                
                if not os.path.exists(master_path) or not os.path.exists(slave_path):
                    error_msg = f"Missing physical SLC files for task {task_id}. Skipping."
                    logging.error(error_msg)
                    mark_task_failed(task_id, error_msg)
                    continue
                    
                # --- Check for Pre-existing Target Files ---
                if os.path.exists(target_path) and os.path.exists(target_data_dir):
                    logging.info(f"  [SKIP] Processed pair data for {target_name} already exists.")
                    mark_task_complete(task_id)
                    continue
                    
                import shutil
                # If only partially existing (e.g. crashed midway), clean it up
                if os.path.exists(target_path):
                    os.remove(target_path)
                    logging.info(f"  [CLEANUP] Deleted corrupted/orphan file: {target_name}")
                if os.path.exists(target_data_dir):
                    shutil.rmtree(target_data_dir)
                    logging.info(f"  [CLEANUP] Deleted corrupted/orphan dir: {os.path.basename(target_data_dir)}")
        
                # --- Dynamic burst detection from master SLC ---
                first_burst, last_burst, detected_subswath = detect_bursts_for_aoi(
                    master_path, SUBSWATH.lower(), aoi_lat, aoi_lon
                )
                
                # --- Dynamic burst detection from slave SLC (Consistency validation) ---
                # First attempt: use the same default subswath preference
                slave_first, slave_last, slave_subswath = detect_bursts_for_aoi(
                    slave_path, SUBSWATH.lower(), aoi_lat, aoi_lon
                )
        
                if detected_subswath != slave_subswath:
                    # The AOI sits near a subswath boundary. Different orbital
                    # geometry between passes can cause master and slave to
                    # initially resolve to different subswaths (e.g. IW1 vs IW2).
                    # Both scenes on the same relative orbit DO overlap — retry
                    # the slave with the master's detected subswath forced as
                    # the primary preference so SNAP gets a consistent pair.
                    logging.warning(
                        f"Subswath mismatch: M({detected_subswath}) != S({slave_subswath}). "
                        f"Retrying slave burst detection forcing {detected_subswath}..."
                    )
                    slave_first, slave_last, slave_subswath = detect_bursts_for_aoi(
                        slave_path, detected_subswath.lower(), aoi_lat, aoi_lon
                    )

                    if detected_subswath != slave_subswath:
                        # Even after forcing, the slave truly does not cover the
                        # AOI in the master's subswath — this pair is unusable.
                        error_msg = (
                            f"Skipping pair: subswath mismatch persists after retry. "
                            f"M({detected_subswath}) != S({slave_subswath}). "
                            f"Slave scene may not cover the AOI footprint."
                        )
                        logging.warning(error_msg)
                        mark_task_failed(task_id, error_msg)
                        continue

                    logging.info(
                        f"Subswath reconciled to {detected_subswath} after retry. "
                        f"Slave bursts: {slave_first}-{slave_last}"
                    )
                    
                logging.info(f"[INFO] AOI located in subswath {detected_subswath}. Selected bursts: {first_burst}-{last_burst}")
        
                # --- Build GPT command with tiling and memory flags ---
                base_cmd = [
                    'gpt',
                    f'-J-Xms2G',
                    f'-J-Xmx{heap_gb}G',
                    '-J-Dsnap.dataio.reader.tileWidth=512',
                    '-J-Dsnap.dataio.reader.tileHeight=512',
                    '-J-Dsnap.jai.tileCacheSize=4096',
                ]

                gpu_args = [
                    '-Dsnap.gpf.useOpenCL=true',
                    '-q', str(cpu_count),
                    '-c', cache_size,
                ]

                graph_params = [
                    f'-Pmaster={master_path}',
                    f'-Pslave={slave_path}',
                    f'-Ptarget={target_path}',
                    f'-Psubswath={detected_subswath}',
                    f'-PmasterFirstBurst={first_burst}',
                    f'-PmasterLastBurst={last_burst}',
                    f'-PslaveFirstBurst={slave_first}',
                    f'-PslaveLastBurst={slave_last}',
                ]

                command = base_cmd + gpu_args + [GRAPH_PATH] + graph_params
                logging.info(f"  GPT: Xmx={heap_gb}G, param={detected_subswath}, bursts={first_burst}-{last_burst}, tiles=512x512")

                # Write SNAP GPT output to a dedicated log file so:
                # 1. Output is visible in real-time (not buffered in RAM for 45 min)
                # 2. User can inspect failures without digging through Python logs
                # 3. capture_output=True pipe-buffer deadlock risk is eliminated
                os.makedirs(LOG_DIR, exist_ok=True)
                gpt_log_path = os.path.join(LOG_DIR, f"snap_gpt_{task_id[:8]}.log")

                # On Windows, 'gpt' is a batch file (gpt.bat).
                # Batch files REQUIRE shell=True to be launched correctly; without it
                # subprocess raises FileNotFoundError or silently skips the .bat wrapper.
                IS_WINDOWS = os.name == "nt"

                # Build the final command string for shell=True on Windows,
                # quoting any argument that contains spaces.
                if IS_WINDOWS:
                    def _q(s: str) -> str:
                        return f'"{s}"' if (" " in s or "\t" in s) else s
                    shell_cmd = " ".join(_q(c) for c in command)
                else:
                    shell_cmd = command  # list form is correct on Linux/Mac

                MAX_RETRIES = 2  # Retry up to 2 times on non-zero exit (e.g. transient OOM)

                start_time = time.time()
                last_error = ""

                for attempt in range(1, MAX_RETRIES + 2):  # attempts: 1, 2, 3
                    if attempt > 1:
                        logging.warning(f"  [RETRY {attempt - 1}/{MAX_RETRIES}] Retrying GPT for {target_name}…")
                        time.sleep(10)  # Brief pause before retry to let OS reclaim memory

                    # Use append mode on retry so previous attempt's output is preserved
                    file_mode = 'w' if attempt == 1 else 'a'
                    try:
                        with open(gpt_log_path, file_mode, encoding='utf-8', errors='replace') as gpt_log:
                            gpt_log.write(f"\n--- Attempt {attempt} — {datetime.utcnow().isoformat()}Z ---\n")
                            if attempt == 1:
                                gpt_log.write(f"Task: {task_id}\n")
                                gpt_log.write(f"Command: {shell_cmd if IS_WINDOWS else ' '.join(command)}\n")
                                gpt_log.write("-" * 80 + "\n")
                            gpt_log.flush()

                            gpt_proc = subprocess.Popen(
                                shell_cmd,
                                stdout=gpt_log,
                                stderr=gpt_log,
                                cwd=str(PROJECT_ROOT),
                                shell=IS_WINDOWS,
                            )

                        logging.info(f"  [GPT PID {gpt_proc.pid} / attempt {attempt}] Log: {gpt_log_path}")

                        # Store PID so the API can confirm real liveness in the UI
                        from pipeline.processing_queue import mark_task_gpt_started
                        mark_task_gpt_started(task_id, gpt_proc.pid, gpt_log_path)

                        # Block until GPT finishes (the API and UI keep polling independently)
                        returncode = gpt_proc.wait()

                    except FileNotFoundError:
                        last_error = (
                            "SNAP GPT executable not found. "
                            "Ensure 'gpt' (or gpt.bat) is in PATH or installed at "
                            "C:\\Program Files\\snap\\bin or C:\\Program Files\\esa-snap\\bin."
                        )
                        logging.error(last_error)
                        mark_task_failed(task_id, last_error)
                        break  # No point retrying if gpt.bat doesn't exist
                    except Exception as e:
                        last_error = f"Execution Error: {str(e)}"
                        logging.error(last_error)
                        mark_task_failed(task_id, last_error)
                        break

                    elapsed = time.time() - start_time

                    if returncode == 0:
                        logging.info(f"[OK] SUCCESS: Processed {target_name} in {elapsed:.2f}s")
                        mark_task_complete(task_id)
                        tasks_processed += 1
                        break  # Done — do not retry

                    # Non-zero exit — read last 3 KB of log for diagnostics
                    try:
                        with open(gpt_log_path, 'r', encoding='utf-8', errors='replace') as lf:
                            lf.seek(0, 2)
                            sz = lf.tell()
                            lf.seek(max(0, sz - 3000))
                            last_error = lf.read()
                    except Exception:
                        last_error = "(log unreadable)"

                    logging.error(
                        f"[FAIL attempt {attempt}] GPT exit code {returncode} for {target_name}. "
                        f"Tail: {last_error[-200:]}"
                    )

                    if attempt > MAX_RETRIES:
                        # All retries exhausted
                        error_msg = (
                            f"SNAP GPT failed after {MAX_RETRIES} retries. "
                            f"Exit code: {returncode}. See {gpt_log_path}. "
                            f"Tail: {last_error[-500:]}"
                        )
                        mark_task_failed(task_id, error_msg)
                        # Continue to next task — do not crash the entire worker
        
            logging.info(f"--- Queue Drained. Processed {tasks_processed} successful InSAR pairs. ---")
            
    except Timeout:
        logging.warning("Another SNAP Processing Worker is already running. Worker Lock is actively held. Exiting silently.")
        return


def main() -> None:
    """Main entry point: execute InSAR pairs from the JSON processing queue."""
    logging.info("Execution started. Data Download is now handled by GUI Manager.")
    check_snap_path()
    process_pairs()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Execution interrupted by user.")
    except Exception as e:
        logging.critical(f"Unhandled Exception: {e}")
        traceback.print_exc()

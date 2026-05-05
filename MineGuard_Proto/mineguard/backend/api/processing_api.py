"""processing_api.py — FastAPI router for SNAP GPT processing orchestration.

Exposes endpoints for the Page 5 Processing Phase UI:
  - GET  /queue-status  → Returns full processing queue state for React polling
  - POST /start         → Spawns src/main_script.py as a detached background process
"""

import os
import sys
import time
import logging
import subprocess
from typing import Dict, Any, List, Optional
from datetime import datetime

import psutil
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from pipeline.processing_queue import _load_queue, QUEUE_FILE_PATH, LOCK_FILE_PATH
from shared.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/processing", tags=["Processing"])

# Track when the SNAP worker was spawned so we can estimate progress
_snap_process: Optional[subprocess.Popen] = None
_processing_start_times: Dict[str, float] = {}

# Average SNAP GPT processing time per pair (seconds) — used for progress estimation
ESTIMATED_PAIR_DURATION_SEC: float = 2700.0  # ~45 minutes


def _gpt_pid_alive(pid: Any) -> bool:
    """Return True if a process with this PID is currently running."""
    if not pid:
        return False
    try:
        return psutil.pid_exists(int(pid))
    except Exception:
        return False


def _read_queue_unlocked() -> list:
    """Read the queue file without acquiring a lock.

    Safe for the status endpoint: the JSON file is small (~4 KB) so reads
    complete before any concurrent write can produce a partial view.
    Falls back to a locked read only when JSON parsing fails (rare mid-write race).
    """
    import json as _json
    from filelock import FileLock, Timeout

    if not QUEUE_FILE_PATH.exists():
        return []
    try:
        with open(QUEUE_FILE_PATH, "r", encoding="utf-8") as f:
            return _json.load(f)
    except (_json.JSONDecodeError, ValueError):
        # Caught mid-write: wait briefly then retry with the lock
        lock = FileLock(LOCK_FILE_PATH, timeout=2)
        try:
            with lock:
                return _load_queue()
        except Timeout:
            return []
    except Exception:
        return []


@router.get("/queue-status")
def api_queue_status() -> Dict[str, Any]:
    """Return the full processing queue state for the React UI.

    Reads the JSON queue file and enriches each task with elapsed time
    and estimated progress percentage for currently-processing tasks.

    Returns:
        Dict with tasks list, summary counts, and overall progress.
    """
    queue = _read_queue_unlocked()

    # Enrich tasks with progress estimation and real GPT liveness
    enriched_tasks: List[Dict[str, Any]] = []
    gpt_actually_running = False

    for task in queue:
        enriched = dict(task)
        task_id = task.get("task_id", "")
        gpt_pid = task.get("gpt_pid")
        gpt_alive = _gpt_pid_alive(gpt_pid)

        if task.get("status") == "processing":
            if task_id not in _processing_start_times:
                _processing_start_times[task_id] = time.time()

            elapsed = time.time() - _processing_start_times[task_id]
            progress = min((elapsed / ESTIMATED_PAIR_DURATION_SEC) * 100, 99.0)

            enriched["elapsed_seconds"] = round(elapsed, 1)
            enriched["estimated_progress"] = round(progress, 1)
            enriched["gpt_alive"] = gpt_alive

            if gpt_alive:
                gpt_actually_running = True
            else:
                # GPT PID is gone but task is still "processing" — it has either:
                # (a) just been started and PID not yet written (< 10s)
                # (b) crashed without the worker catching it
                # Signal the frontend so the user knows GPT is not active
                enriched["gpt_stalled"] = elapsed > 30  # give 30s grace for PID write
        elif task.get("status") == "complete":
            enriched["estimated_progress"] = 100.0
            enriched["gpt_alive"] = False
            _processing_start_times.pop(task_id, None)
        elif task.get("status") == "failed":
            enriched["estimated_progress"] = 0.0
            enriched["gpt_alive"] = False
            _processing_start_times.pop(task_id, None)
        else:
            enriched["estimated_progress"] = 0.0
            enriched["gpt_alive"] = False

        enriched_tasks.append(enriched)

    # Summary counts
    total = len(enriched_tasks)
    pending = sum(1 for t in enriched_tasks if t.get("status") == "pending")
    processing = sum(1 for t in enriched_tasks if t.get("status") == "processing")
    complete = sum(1 for t in enriched_tasks if t.get("status") == "complete")
    failed = sum(1 for t in enriched_tasks if t.get("status") == "failed")

    python_worker_alive = _snap_process is not None and _snap_process.poll() is None

    return {
        "tasks": enriched_tasks,
        "total": total,
        "pending": pending,
        "processing": processing,
        "complete": complete,
        "failed": failed,
        "all_complete": total > 0 and (complete + failed) == total,
        # worker_active: the Python main_script.py process is running
        "worker_active": python_worker_alive,
        # gpt_active: java/SNAP GPT is actually executing right now
        "gpt_active": gpt_actually_running,
    }


@router.post("/start")
def api_start_processing() -> Dict[str, Any]:
    """Spawn the SNAP GPT worker as a detached background subprocess.

    The worker script (src/main_script.py) continuously pulls tasks from
    the processing queue and executes SNAP GPT interferometry.

    Returns:
        Dict with status message and worker PID.
    """
    global _snap_process

    # Check if worker is already running
    if _snap_process is not None and _snap_process.poll() is None:
        return {
            "message": "SNAP worker is already running.",
            "pid": _snap_process.pid,
            "already_running": True,
        }

    # --- Pre-scan: mark pending tasks as complete if output files already exist ---
    # Done here in the API (synchronously) so the queue is correct before the
    # worker starts and before the first frontend poll.
    output_int_dir = str(PROJECT_ROOT / "data" / "output_int")
    try:
        from pipeline.processing_queue import skip_already_processed_tasks
        pre_skipped = skip_already_processed_tasks(output_int_dir)
        if pre_skipped:
            logger.info(
                f"Pre-scan: {pre_skipped} task(s) already have output files on disk "
                f"— marked complete without starting SNAP."
            )
    except Exception as e:
        logger.warning(f"Pre-scan failed (non-fatal): {e}")

    # Verify the queue still has pending tasks after the pre-scan
    queue = _read_queue_unlocked()
    pending_count = sum(1 for t in queue if t.get("status") == "pending")

    if pending_count == 0:
        return {
            "message": "All pairs already processed — output files found on disk. No worker needed.",
            "pid": None,
            "already_running": False,
            "all_skipped": True,
        }

    # Spawn main_script.py as a detached subprocess
    script_path = str(PROJECT_ROOT / "src" / "main_script.py")
    python_exe = sys.executable

    logger.info(f"Spawning SNAP worker: {python_exe} {script_path}")

    try:
        _snap_process = subprocess.Popen(
            [python_exe, script_path],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

        logger.info(f"SNAP worker spawned with PID {_snap_process.pid}")

        return {
            "message": f"SNAP processing started. Worker PID: {_snap_process.pid}",
            "pid": _snap_process.pid,
            "already_running": False,
        }

    except Exception as e:
        logger.error(f"Failed to spawn SNAP worker: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start processing: {str(e)}")


@router.post("/stop")
def api_stop_worker() -> Dict[str, Any]:
    """Terminate the running SNAP worker process (Python main_script.py).

    Sends SIGTERM (or TerminateProcess on Windows) to the worker subprocess
    tracked in _snap_process.  Use this to clean up a stale worker before
    starting a fresh run.
    """
    global _snap_process
    if _snap_process is None or _snap_process.poll() is not None:
        _snap_process = None
        return {"message": "No active worker to stop.", "stopped": False}
    try:
        pid = _snap_process.pid
        _snap_process.terminate()
        try:
            _snap_process.wait(timeout=5)
        except Exception:
            _snap_process.kill()
        _snap_process = None
        logger.info(f"SNAP worker PID {pid} terminated by user request.")
        return {"message": f"Worker PID {pid} terminated.", "stopped": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop worker: {e}")


@router.post("/reset-stuck")
def api_reset_stuck() -> Dict[str, Any]:
    """Reset all tasks stuck in 'processing' state back to 'pending'.

    Use this when the previous SNAP worker crashed mid-run and one or more tasks
    are permanently frozen as 'processing' with no live GPT process.
    """
    from pipeline.processing_queue import recover_stuck_tasks
    recovered = recover_stuck_tasks()
    return {
        "message": f"Reset {recovered} stuck task(s) to 'pending'. They will be retried on the next worker run.",
        "recovered": recovered,
    }


@router.get("/logs/{task_id_prefix}", response_class=PlainTextResponse)
def api_get_task_log(task_id_prefix: str) -> str:
    """Return the last 15 KB of the SNAP GPT log for a task.

    The task_id_prefix is the first 8 characters of the task UUID, matching
    the log filename written by main_script.py.
    """
    log_file = PROJECT_ROOT / "logs" / f"snap_gpt_{task_id_prefix}.log"
    if not log_file.exists():
        return f"No log file found for task prefix '{task_id_prefix}'.\n"
    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 15360))  # Last 15 KB
            return f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not read log: {e}")

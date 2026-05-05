import os
import json
import logging
import uuid
import time
from typing import List, Dict, Any, Optional
from datetime import datetime
from shared.config import PROJECT_ROOT
from filelock import FileLock, Timeout

logger = logging.getLogger(__name__)

QUEUE_FILE_PATH = PROJECT_ROOT / "pipeline" / "data" / "processing_queue.json"
LOCK_FILE_PATH = PROJECT_ROOT / "pipeline" / "data" / "processing_queue.lock"


def _load_queue() -> List[Dict[str, Any]]:
    """Loads the processing queue from the JSON file. MUST be called inside a FileLock."""
    if not QUEUE_FILE_PATH.exists():
        return []
        
    try:
        with open(QUEUE_FILE_PATH, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse {QUEUE_FILE_PATH}. Returning empty queue.")
        return []


def _save_queue(queue: List[Dict[str, Any]]) -> None:
    """Saves the processing queue safely to the JSON file. MUST be called inside a FileLock."""
    os.makedirs(QUEUE_FILE_PATH.parent, exist_ok=True)
    with open(QUEUE_FILE_PATH, 'w') as f:
        json.dump(queue, f, indent=4)


def add_interferogram_pairs(scene_list: List[Dict[str, Any]], orbit: str = "UNKNOWN") -> None:
    """
    Pairs chronological scenes together to form Interferometric pairs (Master-Slave combinations)
    and appends them to the persistent JSON processing queue. Thread-safe.

    Args:
        scene_list: The list of downloaded scenes, pre-sorted by date.
        orbit: Orbit direction for these scenes ("ASCENDING", "DESCENDING", or "UNKNOWN").
               Used by main_script.py to tag output interferogram filenames (_ASC_/_DSC_).
    """
    if len(scene_list) < 2:
        logger.warning("Not enough scenes to form an interferogram pair.")
        return

    sorted_scenes = sorted(scene_list, key=lambda x: x.get('acquisitionDate', ''))
    added_count = 0

    lock = FileLock(LOCK_FILE_PATH, timeout=10)

    try:
        with lock:
            queue = _load_queue()

            for i in range(len(sorted_scenes) - 1):
                master = sorted_scenes[i]
                slave = sorted_scenes[i + 1]

                if master.get('id') == slave.get('id'):
                    continue

                pair_task = {
                    "task_id": str(uuid.uuid4()),
                    "master_scene": master.get('filename', '') + '.zip' if not master.get('filename', '').endswith('.zip') else master.get('filename', ''),
                    "master_date": master.get('acquisitionDate', ''),
                    "slave_scene": slave.get('filename', '') + '.zip' if not slave.get('filename', '').endswith('.zip') else slave.get('filename', ''),
                    "slave_date": slave.get('acquisitionDate', ''),
                    "orbit": orbit,
                    "status": "pending",
                    "added_at": datetime.utcnow().isoformat() + "Z",
                    "completed_at": None,
                    "error_message": None
                }
                
                is_dup = any(
                    t.get("master_scene") == pair_task["master_scene"] and 
                    t.get("slave_scene") == pair_task["slave_scene"]
                    for t in queue
                )
                
                if not is_dup:
                    queue.append(pair_task)
                    added_count += 1
                    
            if added_count > 0:
                _save_queue(queue)
                logger.info(f"Added {added_count} new interferogram pairs to the processing queue.")
            
    except Timeout:
        logger.error("Timeout occurred trying to acquire queue lock during 'add_interferogram_pairs'.")
    except Exception as e:
        logger.error(f"Error adding pairs to queue: {e}")


def get_next_processing_task() -> Optional[Dict[str, Any]]:
    """
    Retrieves the oldest 'pending' task from the queue and marks it as 'processing'. Thread-safe.
    
    Returns:
        The task dictionary, or None if the queue is empty.
    """
    lock = FileLock(LOCK_FILE_PATH, timeout=10)
    
    try:
        with lock:
            queue = _load_queue()
            
            for task in queue:
                if task.get("status") == "pending":
                    task["status"] = "processing"
                    _save_queue(queue)
                    
                    logger.info(f"Pulled task {task['task_id']} for SNAP processing (Master: {task['master_scene']} -> Slave: {task['slave_scene']})")
                    return task
            return None
    except Timeout:
        logger.error("Timeout occurred trying to acquire queue lock during 'get_next_processing_task'.")
        return None
    except Exception as e:
        logger.error(f"Error getting next processing task: {e}")
        return None


def mark_task_gpt_started(task_id: str, gpt_pid: int, log_path: str = "") -> bool:
    """Stores the SNAP GPT process PID and log path once java actually launches.

    This lets the API verify real liveness: if the PID is gone while the task
    is still 'processing', GPT has crashed and the task should be marked failed.
    """
    lock = FileLock(LOCK_FILE_PATH, timeout=10)
    try:
        with lock:
            queue = _load_queue()
            for task in queue:
                if task.get("task_id") == task_id:
                    task["gpt_pid"] = gpt_pid
                    task["gpt_log"] = log_path
                    _save_queue(queue)
                    logger.info(f"Stored GPT PID {gpt_pid} for task {task_id}.")
                    return True
            logger.warning(f"Task ID {task_id} not found to store GPT PID.")
            return False
    except Timeout:
        logger.error("Timeout acquiring queue lock during 'mark_task_gpt_started'.")
        return False
    except Exception as e:
        logger.error(f"Error storing GPT PID: {e}")
        return False


def mark_task_complete(task_id: str) -> bool:
    """Marks a task as 'complete' in a thread-safe manner."""
    lock = FileLock(LOCK_FILE_PATH, timeout=10)
    
    try:
        with lock:
            queue = _load_queue()
            for task in queue:
                if task.get("task_id") == task_id:
                    task["status"] = "complete"
                    task["completed_at"] = datetime.utcnow().isoformat() + "Z"
                    _save_queue(queue)
                    logger.info(f"Marked task {task_id} as Complete.")
                    return True
            logger.warning(f"Task ID {task_id} not found to mark as complete.")
            return False
    except Timeout:
        logger.error("Timeout occurred trying to acquire queue lock during 'mark_task_complete'.")
        return False
        
        
def mark_task_failed(task_id: str, error_message: str = "") -> bool:
    """Marks a task as 'failed' in a thread-safe manner so it doesn't block."""
    lock = FileLock(LOCK_FILE_PATH, timeout=10)
    
    try:
        with lock:
            queue = _load_queue()
            for task in queue:
                if task.get("task_id") == task_id:
                    task["status"] = "failed"
                    task["error_message"] = error_message
                    _save_queue(queue)
                    logger.error(f"Marked task {task_id} as FAILED. Reason: {error_message}")
                    return True
            logger.warning(f"Task ID {task_id} not found to mark as failed.")
            return False
    except Timeout:
        logger.error("Timeout occurred trying to acquire queue lock during 'mark_task_failed'.")
        return False

def recover_stuck_tasks() -> int:
    """Reset tasks stuck in 'processing' state back to 'pending'.

    This is called at worker startup.  If a previous run crashed (Python OOM,
    SIGKILL, power loss) after marking a task 'processing' but before calling
    mark_task_complete / mark_task_failed, the task would stay 'processing'
    forever because get_next_processing_task() only dequeues 'pending' tasks.

    Returns:
        Number of tasks recovered.
    """
    lock = FileLock(LOCK_FILE_PATH, timeout=10)
    try:
        with lock:
            queue = _load_queue()
            recovered = 0
            for task in queue:
                if task.get("status") == "processing":
                    task["status"] = "pending"
                    task.pop("gpt_pid", None)   # stale PID from the dead run
                    task.pop("gpt_log", None)
                    recovered += 1
            if recovered > 0:
                _save_queue(queue)
                logger.info(f"Recovered {recovered} stuck task(s) from 'processing' → 'pending'.")
            return recovered
    except Timeout:
        logger.error("Timeout acquiring queue lock during 'recover_stuck_tasks'.")
        return 0
    except Exception as e:
        logger.error(f"Error recovering stuck tasks: {e}")
        return 0


def skip_already_processed_tasks(output_int_dir: str) -> int:
    """Mark 'pending' tasks as 'complete' if their output files already exist on disk.

    Called at worker startup before the processing loop. Prevents re-running SNAP GPT
    for pairs that were processed in a previous session but whose queue status is still
    'pending' (e.g. queue was reset, or re-populated from scratch after a prior run).

    Args:
        output_int_dir: Absolute path to the directory containing .dim output files.

    Returns:
        Number of tasks marked complete.
    """
    lock = FileLock(LOCK_FILE_PATH, timeout=10)
    try:
        with lock:
            queue = _load_queue()
            skipped = 0
            for task in queue:
                if task.get("status") != "pending":
                    continue
                orbit = task.get("orbit", "UNK").upper()
                if "ASCENDING" in orbit or orbit == "ASC":
                    orbit_tag = "ASC"
                elif "DESCENDING" in orbit or orbit == "DSC":
                    orbit_tag = "DSC"
                else:
                    orbit_tag = "UNK"
                master_date = task.get("master_date", "")
                slave_date = task.get("slave_date", "")
                target_name = f"Int_{orbit_tag}_{master_date}_{slave_date}.dim"
                target_path = os.path.join(output_int_dir, target_name)
                target_data_dir = target_path.replace(".dim", ".data")
                if os.path.exists(target_path) and os.path.exists(target_data_dir):
                    task["status"] = "complete"
                    task["completed_at"] = datetime.utcnow().isoformat() + "Z"
                    skipped += 1
                    logger.info(
                        f"  [PRE-SKIP] Output already on disk for task {task['task_id']} "
                        f"({orbit_tag} {master_date}→{slave_date})"
                    )
            if skipped > 0:
                _save_queue(queue)
                logger.info(
                    f"Startup pre-scan: {skipped} task(s) marked complete "
                    f"(output files already exist on disk)."
                )
            return skipped
    except Timeout:
        logger.error("Timeout acquiring queue lock during 'skip_already_processed_tasks'.")
        return 0
    except Exception as e:
        logger.error(f"Error in skip_already_processed_tasks: {e}")
        return 0


def clear_queue() -> bool:
    """Empties the processing queue safely."""
    lock = FileLock(LOCK_FILE_PATH, timeout=10)
    try:
        with lock:
            _save_queue([])
            logger.info("Processing queue has been cleared.")
            return True
    except Timeout:
        logger.error("Timeout occurred trying to acquire queue lock during 'clear_queue'.")
        return False

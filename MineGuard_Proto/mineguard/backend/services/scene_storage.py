import os
import logging
from typing import List, Dict, Any, Set
from shared.config import PROJECT_ROOT, SCENE_STORAGE_PATH

logger = logging.getLogger(__name__)

# Absolute resolution from the unified config
RAW_DATA_DIR = PROJECT_ROOT / SCENE_STORAGE_PATH


def get_existing_scenes() -> Set[str]:
    """
    Scans the configured Scene Storage Path (pipeline/data/raw) 
    and returns a set of filenames currently present to prevent duplicate downloads.

    Returns:
        Set[str]: A set containing exactly the filenames of the existing local SLC products.
    """
    existing_files: Set[str] = set()

    if not RAW_DATA_DIR.exists():
        logger.warning(f"Storage directory does not exist yet: {RAW_DATA_DIR}")
        return existing_files

    for file_path in RAW_DATA_DIR.iterdir():
        if file_path.is_file() and file_path.suffix == '.zip':
            # Store the raw filename (e.g., S1A_IW_SLC__1SDV_20200101T000000...zip)
            existing_files.add(file_path.name)
            
    logger.info(f"Found {len(existing_files)} existing Sentinel-1 scenes in local storage ({SCENE_STORAGE_PATH}).")
    return existing_files


def remove_existing_scenes(scene_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filters out any Sentinel-1 scenes that have already been downloaded to the local raw storage.

    Args:
        scene_list (List[Dict[str, Any]]): The full list of valid queried scenes.

    Returns:
        List[Dict[str, Any]]: The remaining scenes that must still be downloaded.
    """
    if not scene_list:
        return []

    existing_filenames = get_existing_scenes()
    if not existing_filenames:
        # Nothing is downloaded yet, request full list
        return scene_list

    remaining_scenes = []
    skipped_count = 0

    for scene in scene_list:
        # Copernicus API returns filename without .zip extension usually.
        # We ensure we check against the .zip version found on the actual filesystem.
        expected_filename = scene.get('filename', '')
        if not expected_filename.endswith('.zip'):
            expected_filename += '.zip'
            
        if expected_filename in existing_filenames:
            skipped_count += 1
            logger.debug(f"Skipping already downloaded scene: {expected_filename}")
        else:
            remaining_scenes.append(scene)

    logger.info(
        f"Duplicate Check: Filtered out {skipped_count} scenes. "
        f"{len(remaining_scenes)} remain to be downloaded."
    )
    
    return remaining_scenes

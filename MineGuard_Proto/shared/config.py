import os
from pathlib import Path

# Always derive PROJECT_ROOT from __file__ as per User Request Rules
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_DIR = PROJECT_ROOT / "pipeline"

# Unified Scene Storage
SCENE_STORAGE_PATH = "pipeline/data/raw"

# Download Configuration Limits
MAX_DOWNLOAD_WORKERS = 4
DOWNLOAD_RETRY_LIMIT = 3

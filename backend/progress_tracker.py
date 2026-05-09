"""
Progress tracking for download operations.
Writes progress to a JSON file that can be read by the API.
"""

import json
import re
import time
from pathlib import Path
from typing import Dict, Optional
from threading import Lock

# Progress files directory
PROGRESS_DIR = Path(__file__).parent.parent / "data" / "progress"
PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
_PROGRESS_DIR_RESOLVED = PROGRESS_DIR.resolve()

# Task IDs are generated with uuid.uuid4(), so they only ever contain
# hex digits and dashes. Reject anything else to keep user-controlled
# values from steering the file path outside PROGRESS_DIR.
_TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# Thread lock for file operations
_file_lock = Lock()


def _safe_progress_path(task_id: str) -> Optional[Path]:
    """Return the progress file path for `task_id`, or None if the id
    is malformed or would escape PROGRESS_DIR."""
    if not isinstance(task_id, str) or not _TASK_ID_PATTERN.match(task_id):
        return None
    candidate = (PROGRESS_DIR / f"{task_id}.json").resolve()
    try:
        candidate.relative_to(_PROGRESS_DIR_RESOLVED)
    except ValueError:
        return None
    return candidate


def write_progress(task_id: str, status: str, message: str, details: Optional[Dict] = None):
    """
    Write progress update to file.
    
    Args:
        task_id: Task/process ID
        status: Status (searching, loading, saving, completed, failed)
        message: Human-readable message
        details: Optional dictionary with additional details (counts, percentages, etc.)
    """
    progress_file = _safe_progress_path(task_id)
    if progress_file is None:
        return

    progress_data = {
        'task_id': task_id,
        'status': status,
        'message': message,
        'timestamp': time.time(),
        'details': details or {}
    }

    with _file_lock:
        try:
            with open(progress_file, 'w') as f:
                json.dump(progress_data, f, indent=2)
        except Exception:
            # Don't fail if progress writing fails
            pass


def read_progress(task_id: str) -> Optional[Dict]:
    """
    Read progress from file.
    
    Args:
        task_id: Task/process ID
        
    Returns:
        Progress dictionary or None if not found
    """
    progress_file = _safe_progress_path(task_id)
    if progress_file is None:
        return None

    with _file_lock:
        try:
            if progress_file.exists():
                with open(progress_file, 'r') as f:
                    return json.load(f)
        except Exception:
            pass

    return None


def clear_progress(task_id: str):
    """Clear progress file for a task."""
    progress_file = _safe_progress_path(task_id)
    if progress_file is None:
        return

    with _file_lock:
        try:
            if progress_file.exists():
                progress_file.unlink()
        except Exception:
            pass


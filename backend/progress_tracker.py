"""
Progress tracking for download operations.
Writes progress to a JSON file that can be read by the API.
"""

import json
import time
from pathlib import Path
from typing import Dict, Optional
from threading import Lock

# Progress files directory
PROGRESS_DIR = Path(__file__).parent.parent / "data" / "progress"
PROGRESS_DIR.mkdir(parents=True, exist_ok=True)

# Thread lock for file operations
_file_lock = Lock()


def write_progress(task_id: str, status: str, message: str, details: Optional[Dict] = None):
    """
    Write progress update to file.
    
    Args:
        task_id: Task/process ID
        status: Status (searching, loading, saving, completed, failed)
        message: Human-readable message
        details: Optional dictionary with additional details (counts, percentages, etc.)
    """
    progress_file = PROGRESS_DIR / f"{task_id}.json"
    
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
        except Exception as e:
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
    progress_file = PROGRESS_DIR / f"{task_id}.json"
    
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
    progress_file = PROGRESS_DIR / f"{task_id}.json"
    
    with _file_lock:
        try:
            if progress_file.exists():
                progress_file.unlink()
        except Exception:
            pass


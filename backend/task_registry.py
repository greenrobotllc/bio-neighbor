"""
Task registry for tracking download tasks by UUID.
Maps UUID task IDs to process information to prevent PID probing attacks.
"""

import json
import time
import uuid
from pathlib import Path
from typing import Dict, Optional
from threading import Lock

# Task registry file
TASKS_FILE = Path(__file__).parent.parent / "data" / "progress" / "tasks.json"
TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)

# Thread lock for registry operations
_registry_lock = Lock()


def register_task(pid: int, cmd: list, task_type: str = "download") -> str:
    """
    Register a new task and return its UUID.
    
    Args:
        pid: Process ID
        cmd: Command that was executed
        task_type: Type of task (e.g., "download")
        
    Returns:
        UUID string for the task
    """
    task_id = str(uuid.uuid4())
    
    task_info = {
        'task_id': task_id,
        'pid': pid,
        'cmd': cmd,
        'task_type': task_type,
        'started_at': time.time(),
        'progress_path': str(Path(__file__).parent.parent / "data" / "progress" / f"{task_id}.json")
    }
    
    with _registry_lock:
        # Load existing tasks
        tasks = _load_tasks()
        tasks[task_id] = task_info
        _save_tasks(tasks)
    
    return task_id


def get_task_info(task_id: str) -> Optional[Dict]:
    """
    Get task information by UUID.
    
    Args:
        task_id: UUID task ID
        
    Returns:
        Task info dictionary or None if not found
    """
    with _registry_lock:
        tasks = _load_tasks()
        return tasks.get(task_id)


def remove_task(task_id: str):
    """
    Remove a task from the registry.
    
    Args:
        task_id: UUID task ID
    """
    with _registry_lock:
        tasks = _load_tasks()
        if task_id in tasks:
            del tasks[task_id]
            _save_tasks(tasks)


def cleanup_old_tasks(max_age_seconds: int = 86400):
    """
    Remove tasks older than max_age_seconds from the registry.
    
    Args:
        max_age_seconds: Maximum age in seconds (default: 24 hours)
    """
    current_time = time.time()
    
    with _registry_lock:
        tasks = _load_tasks()
        to_remove = []
        
        for task_id, task_info in tasks.items():
            started_at = task_info.get('started_at', 0)
            if current_time - started_at > max_age_seconds:
                to_remove.append(task_id)
        
        for task_id in to_remove:
            del tasks[task_id]
        
        if to_remove:
            _save_tasks(tasks)


def _load_tasks() -> Dict[str, Dict]:
    """Load tasks from file."""
    try:
        if TASKS_FILE.exists():
            with open(TASKS_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_tasks(tasks: Dict[str, Dict]):
    """Save tasks to file."""
    try:
        with open(TASKS_FILE, 'w') as f:
            json.dump(tasks, f, indent=2)
    except Exception:
        pass


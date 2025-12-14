"""
Helper to stream subprocess output in real-time and update progress.
"""

import threading
import subprocess
from typing import Optional, Callable
from pathlib import Path


def stream_output(process: subprocess.Popen, log_callback: Optional[Callable[[str], None]] = None):
    """
    Stream subprocess output in real-time.
    
    Args:
        process: Subprocess to stream
        log_callback: Optional callback for each line (for server logging)
    """
    def read_output(pipe, is_stderr=False):
        """Read from pipe and log/output lines."""
        try:
            for line in iter(pipe.readline, ''):
                if not line:
                    break
                line = line.rstrip()
                if line:
                    prefix = "STDERR" if is_stderr else "STDOUT"
                    log_msg = f"[PID {process.pid}] {prefix}: {line}"
                    
                    # Log to server console
                    if log_callback:
                        log_callback(log_msg)
                    else:
                        print(log_msg)
                    
                    # Update progress file if line contains progress info
                    # The download script writes progress via progress_tracker
                    # We just need to ensure output is visible
        except Exception as e:
            if log_callback:
                log_callback(f"Error reading output: {e}")
            else:
                print(f"Error reading output: {e}")
        finally:
            pipe.close()
    
    # Start threads to read stdout and stderr
    stdout_thread = threading.Thread(target=read_output, args=(process.stdout, False))
    stderr_thread = threading.Thread(target=read_output, args=(process.stderr, True))
    
    stdout_thread.daemon = True
    stderr_thread.daemon = True
    
    stdout_thread.start()
    stderr_thread.start()
    
    return stdout_thread, stderr_thread


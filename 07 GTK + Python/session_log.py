"""Session-log file helpers.

Low-level utilities for creating per-run log files, appending raw subprocess
lines, writing the final trailer, and enforcing the session-log size cap.
These functions are stateless so they can be used by both the GUI runner
(BackupRunner) and the headless profile runner.
"""

import os
import re
import time
from datetime import datetime

from config_core import SESSION_LOG_DIR
from log_index import LogIndex
from logging_config import log_msg, truncate_session_log

# How often to check the session log size while a runner is active.
_LOG_SIZE_CHECK_INTERVAL = 5  # seconds


def create_session_log_file(
    tab_type: str,
    name: str | None = None,
    session_log_dir: str | None = None,
) -> str | None:
    """Create a new session log file and return its path.

    The filename includes a timestamp and the tab type. If *name* is given
    (e.g. a profile name), it is sanitized and included in the filename;
    otherwise the file is marked as a GUI-run log.
    """
    if session_log_dir is None:
        session_log_dir = SESSION_LOG_DIR
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    # Regex: [^A-Za-z0-9_-]
    # Purpose: Sanitize tab_type and name for safe use in log filenames.
    #          Strips any character that is not a letter, digit, hyphen, or underscore.
    # Example: "Backup Profile #1" -> "BackupProfile1"
    safe_type = re.sub(r"[^A-Za-z0-9_-]", "", tab_type) if tab_type else "backup"
    if name:
        safe_name = re.sub(r"[^A-Za-z0-9_-]", "", name)
        filename = f"{ts}_{safe_type}_profile-{safe_name}.log"
    else:
        filename = f"{ts}_{safe_type}_gui.log"

    os.makedirs(session_log_dir, exist_ok=True)
    path = os.path.join(session_log_dir, filename)
    try:
        open(path, "a").close()
    except OSError:
        return None
    return path


def write_raw_line(session_log_file: str | None, line: str) -> None:
    """Append a raw subprocess line to the session log file with a timestamp."""
    if not session_log_file:
        return
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(session_log_file, "a") as fh:
            fh.write(f"{ts}  {line}\n")
    except OSError:
        pass


def write_session_trailer(
    session_log_file: str | None,
    session_start_time: float | None,
    rc: int | None = None,
    cancelled: bool = False,
    bytes_transferred: int = 0,
) -> None:
    """Write the final trailer line and persist metadata to the log index."""
    if not session_log_file:
        return
    duration = (
        time.time() - session_start_time if session_start_time else 0.0
    )
    status = "cancelled" if cancelled else (
        f"rc={rc}" if rc is not None else "done"
    )
    trailer = f"# END: {status}, duration={duration:.1f}s"
    if bytes_transferred:
        trailer += f", bytes={bytes_transferred}"
    try:
        with open(session_log_file, "a") as fh:
            fh.write(trailer + "\n")
    except OSError:
        pass

    # Persist final metadata so the Logs tab does not need to rescan.
    try:
        index = LogIndex.load()
        index.set_status(
            session_log_file,
            status="Cancelled" if cancelled else (
                "Done" if rc == 0 else "Failed"
            ),
            duration=duration,
            bytes_transferred=bytes_transferred,
        )
        index.save()
    except Exception as e:
        log_msg(f"WARN: Could not update log index: {e}")


def maybe_truncate_session_log(
    session_log_file: str | None,
    last_check_time: float,
    interval: int = _LOG_SIZE_CHECK_INTERVAL,
) -> tuple[bool, float]:
    """Truncate the session log if it has grown beyond the cap.

    Returns a tuple ``(truncated, new_last_check_time)``. When truncation
    occurs the persistent index entry is removed so the Logs tab rescans the
    smaller file.
    """
    if not session_log_file:
        return False, last_check_time
    now = time.time()
    if now - last_check_time < interval:
        return False, last_check_time
    if truncate_session_log(session_log_file):
        log_msg("WARN: Session log exceeded size cap and was truncated")
        try:
            index = LogIndex.load()
            index.remove(session_log_file)
            index.save()
        except Exception as e:
            log_msg(f"WARN: Could not reset log index after truncation: {e}")
        return True, now
    return False, now

"""Logging configuration — message levels, GUI sink, and log output."""

import inspect
import os
import re
import sys
from contextlib import contextmanager
from datetime import datetime


MSG_LEVELS = ("DEBUG", "VERB", "INFO", "WARN", "FATAL")
DEFAULT_MSG_LEVEL = "INFO"


_MSG_PRIORITY = {
    "DEBUG": 0,
    "VERB": 1,
    "INFO": 2,
    "WARN": 3,
    "FATAL": 4,
}

# Implied level for messages/lines without a recognized LEVEL: prefix.
# It has the highest priority and is always displayed in viewers.
NONE_LEVEL = None
NONE_PRIORITY = 5

_gui_log_sink = None


def set_log_sink(sink):
    """Set a callable sink for log messages (e.g., app.log_message)."""
    global _gui_log_sink
    _gui_log_sink = sink


def get_log_sink():
    """Return the current log sink, or None."""
    return _gui_log_sink


def _restore_env(name, previous):
    """Restore an environment variable to its previous value (or unset it)."""
    if previous is not None:
        os.environ[name] = previous
    elif name in os.environ:
        del os.environ[name]


def set_session_log(path):
    """Set ZFSUTILITIES_LOG_FILE and ZFSUTILITIES_LOG_INHERIT, returning prior values.

    Returns a tuple (previous_log_file, previous_log_inherit) suitable for
    passing to restore_session_log().
    """
    previous = (
        os.environ.get("ZFSUTILITIES_LOG_FILE"),
        os.environ.get("ZFSUTILITIES_LOG_INHERIT"),
    )
    os.environ["ZFSUTILITIES_LOG_FILE"] = path
    os.environ["ZFSUTILITIES_LOG_INHERIT"] = "Y"
    return previous


def restore_session_log(previous):
    """Restore session-log environment variables from a set_session_log() tuple."""
    prev_file, prev_inherit = previous
    _restore_env("ZFSUTILITIES_LOG_FILE", prev_file)
    _restore_env("ZFSUTILITIES_LOG_INHERIT", prev_inherit)


@contextmanager
def session_log_context(path):
    """Context manager that sets/restores ZFSUTILITIES_LOG_FILE and _LOG_INHERIT."""
    previous = set_session_log(path)
    try:
        yield
    finally:
        restore_session_log(previous)


def get_msg_level(config):
    level = config.get("msg_level")
    return level if level in MSG_LEVELS else DEFAULT_MSG_LEVEL


def parse_msg_level(text):
    """Return the level token at the start of *text*, or None.

    The expected format is an optional timestamp and file:line prefix followed
    by "LEVEL: ". Lines without a recognized level are treated as the implied
    "(none)" level (highest priority, always displayed in viewers).
    """
    if not text:
        return NONE_LEVEL
    # Strip optional leading timestamp: "YYYY-MM-DD HH:MM:SS  "
    stripped = re.sub(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\s+", "", text)
    m = re.match(r"(?:[^:]+:\d+):\s+(DEBUG|VERB|INFO|WARN|FATAL):", stripped)
    if m:
        return m.group(1)
    return NONE_LEVEL


def viewer_should_show(level, min_level):
    """Return True if *level* should be visible when *min_level* is selected.

    The implied "(none)" level (None) is always visible. Otherwise the level
    must have priority >= min_level.
    """
    if level is NONE_LEVEL:
        return True
    if level not in _MSG_PRIORITY or min_level not in _MSG_PRIORITY:
        return True
    return _MSG_PRIORITY[level] >= _MSG_PRIORITY[min_level]


def log_msg(*parts):
    """Log a message with file:line prefix, GUI sink, and session log file.

    All messages are always emitted (to the GUI sink or stderr) and appended
    to the session log file when one is configured. Filtering by message level
    is performed by the GUI log viewers.
    """
    msg = " ".join(str(p) for p in parts)

    frame = inspect.currentframe().f_back
    try:
        while frame is not None:
            frame_file = inspect.getfile(frame)
            if os.path.basename(frame_file) != "logging_config.py":
                break
            frame = frame.f_back
        if frame is not None:
            prefix = f"{os.path.realpath(inspect.getfile(frame))}:{frame.f_lineno}:"
        else:
            prefix = "zfsutilities:"
    except (TypeError, OSError):
        prefix = "zfsutilities:"
    finally:
        del frame

    full = f"{prefix} {msg}"

    if _gui_log_sink is not None:
        _gui_log_sink(full)
    else:
        _term = os.environ.get("TERM", "")
        if (
            hasattr(sys.stderr, "isatty")
            and sys.stderr.isatty()
            and _term != "dumb"
        ):
            if msg.startswith("WARN:"):
                print(f"\033[38;5;208m{full}\033[0m", file=sys.stderr)
            elif msg.startswith("FATAL:"):
                print(f"\033[1;31m{full}\033[0m", file=sys.stderr)
            else:
                print(full, file=sys.stderr)
        else:
            print(full, file=sys.stderr)

    log_file = os.environ.get("ZFSUTILITIES_LOG_FILE")
    if log_file:
        try:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(log_file, "a") as fh:
                fh.write(f"{ts}  {full}\n")
        except OSError:
            pass

    return full

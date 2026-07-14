"""Core configuration — JSON load/save, generic UI state, and path helpers."""

import json
import os
from datetime import datetime

from config_migrations import CONFIG_VERSION, run_migrations
from file_locking import config_lock_read, config_lock_write
from logging_config import log_msg, MSG_LEVELS

CONFIG_PATH = os.environ.get(
    "ZFSUTILITIES_CONFIG_PATH",
    os.path.expanduser("~/.config/zfsutilities.json"),
)


BACKUP_DEFAULTS = {
    "variables": {
        "autoresume": "Y",
        "includes": "",
        "excludes": "",
        "startwith": "",
        "endwith": "",
        "receive_F_option": "F",
        "releaseholds": "N",
        "doincrementals": "Y",
        "dointermediates": "Y",
        "allow_destructive": "N",
        "verify_after_transfer": "Y",
        "label": "dailybackup",
    },
    "pull_steps": [],
    "send_receive_steps": [],
    "post_steps": {
        "remove_snapfile": True,
        "run_retention": True,
    },
    "pre_backup_script_enabled": False,
    "pre_backup_script": "",
    "post_backup_script_enabled": False,
    "post_backup_script": "",
    "zfs_keys_path": "",
    "zfs_keys_dest": "",
    "pull_steps_active": True,
    "pause_scrubs": False,
}


DASHBOARD_DEFAULTS = {
    "low_space_threshold": 80,
}


def get_profiles_dir():
    """Return the directory where profile JSON files are stored."""
    profiles_dir = os.path.join(os.path.dirname(CONFIG_PATH), "profiles")
    os.makedirs(profiles_dir, exist_ok=True)
    return profiles_dir


def _deep_copy(obj):
    return json.loads(json.dumps(obj))


def load_config():
    """Load JSON config from CONFIG_PATH. Returns defaults on any error."""
    config = None
    if os.path.exists(CONFIG_PATH):
        try:
            with config_lock_read():
                with open(CONFIG_PATH) as f:
                    config = json.load(f)
        except (json.JSONDecodeError, OSError):
            config = None

    if config is not None:
        current_ver = config.get("config_version")
        if current_ver is None:
            config["config_version"] = CONFIG_VERSION
            try:
                save_config(config)
            except OSError:
                pass
        elif current_ver < CONFIG_VERSION:
            config = run_migrations(config, save_config)
        elif current_ver > CONFIG_VERSION:
            log_msg(
                f"WARN: Config version {current_ver} is newer than "
                f"software expects ({CONFIG_VERSION}). "
                f"Some features may not work correctly."
            )
        return config

    config = {
        "backup": _deep_copy(BACKUP_DEFAULTS),
        "dashboard": _deep_copy(DASHBOARD_DEFAULTS),
        "config_version": CONFIG_VERSION,
    }
    try:
        save_config(config)
    except OSError:
        pass
    return config


def save_config(config):
    """Write config dict to CONFIG_PATH. Raises OSError on permission failure."""
    config_dir = os.path.dirname(CONFIG_PATH)
    os.makedirs(config_dir, exist_ok=True)
    with config_lock_write():
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=2)


def save_msg_level(config, level):
    if level not in MSG_LEVELS:
        raise ValueError(f"invalid msg_level: {level!r}")
    config["msg_level"] = level
    save_config(config)


def get_docs_editor(config):
    """Return the configured markdown editor command, or empty string for default."""
    return config.get("gui", {}).get("docs_editor", "")


def save_docs_editor(config, command):
    """Store the markdown editor command string."""
    config.setdefault("gui", {})["docs_editor"] = command
    save_config(config)


UI_STATE_DEFAULTS = {
    "main_window": {
        "width": None,
        "height": None,
        "x": None,
        "y": None,
        "maximized": False,
        "vpaned_position": None,
    },
    "log_window": {
        "popped_out": False,
        "width": None,
        "height": None,
        "x": None,
        "y": None,
    },
    "docs_viewer": {
        "width": None,
        "height": None,
        "x": None,
        "y": None,
        "maximized": False,
        "zoom": 1.0,
        "theme": "default",
    },
    "treeview_columns": {},
    "paned_positions": {},
}


def get_ui_state(config):
    defaults = _deep_copy(UI_STATE_DEFAULTS)
    saved = config.get("ui_state", {})
    result = {}
    for key, default_val in defaults.items():
        result[key] = dict(default_val)
        result[key].update(saved.get(key, {}))
    return result


def save_ui_state(config, state_dict):
    if "ui_state" not in config:
        config["ui_state"] = {}
    for key, val in state_dict.items():
        if isinstance(val, dict):
            config["ui_state"].setdefault(key, {})
            config["ui_state"][key].update(val)
        else:
            config["ui_state"][key] = val
    save_config(config)


DEFAULT_LOG_RETENTION_DAYS = 30
DEFAULT_HISTORY_RETENTION_DAYS = 90
DEFAULT_SESSION_LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_SESSION_LOG_TAIL_BYTES = 1 * 1024 * 1024   # 1 MB
DEFAULT_SESSION_LOG_START_BYTES = 64 * 1024        # 64 KB
SESSION_LOG_DIR = "/var/log/zfsutilities/sessions"


def get_log_retention_days(config):
    days = config.get("log_retention_days")
    return days if isinstance(days, int) and days >= 0 else DEFAULT_LOG_RETENTION_DAYS


def save_log_retention_days(config, days):
    if not isinstance(days, int) or days < 0:
        raise ValueError(f"invalid log_retention_days: {days!r}")
    config["log_retention_days"] = days
    save_config(config)


def get_history_retention_days(config):
    days = config.get("history_retention_days")
    return days if isinstance(days, int) and days >= 0 else DEFAULT_HISTORY_RETENTION_DAYS


def save_history_retention_days(config, days):
    if not isinstance(days, int) or days < 0:
        raise ValueError(f"invalid history_retention_days: {days!r}")
    config["history_retention_days"] = days
    save_config(config)


def get_session_log_max_bytes(config):
    """Return the configured session-log size cap in bytes."""
    value = config.get("session_log_max_bytes")
    if isinstance(value, int) and value > 0:
        return value
    return DEFAULT_SESSION_LOG_MAX_BYTES


def save_session_log_max_bytes(config, max_bytes):
    """Persist the session-log size cap in bytes."""
    if not isinstance(max_bytes, int) or max_bytes <= 0:
        raise ValueError(f"invalid session_log_max_bytes: {max_bytes!r}")
    config["session_log_max_bytes"] = max_bytes
    save_config(config)


def prune_old_logs(retention_days):
    """Remove session log files older than retention_days. Returns count removed."""
    if not os.path.isdir(SESSION_LOG_DIR):
        return 0
    cutoff = datetime.now().timestamp() - (retention_days * 86400)
    removed = 0
    for name in os.listdir(SESSION_LOG_DIR):
        path = os.path.join(SESSION_LOG_DIR, name)
        if not os.path.isfile(path):
            continue
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
                log_msg(f"VERB: Pruned old log: {path}")
                removed += 1
        except OSError:
            pass
    if removed:
        log_msg(f"INFO: Pruned {removed} old log file(s)")
    return removed


def get_dashboard_config(config):
    """Return the dashboard config dict, creating defaults if absent."""
    dashboard = config.get("dashboard")
    if not isinstance(dashboard, dict):
        dashboard = _deep_copy(DASHBOARD_DEFAULTS)
        config["dashboard"] = dashboard
    if "low_space_threshold" not in dashboard:
        dashboard["low_space_threshold"] = DASHBOARD_DEFAULTS["low_space_threshold"]
    return dashboard


def save_dashboard_config(config, dashboard_data):
    """Store dashboard config and persist to disk."""
    config["dashboard"] = dict(dashboard_data)
    save_config(config)

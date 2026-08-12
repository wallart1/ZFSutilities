"""Centralized path resolution for the ZFS Utilities runtime layout.

This module defines the FHS-aligned directories used for configuration,
state, logs, transient runtime files, and advisory locks. All paths can be
overridden via environment variables so tests and non-standard installs do
not need to patch individual consumers.

Legacy path helpers are also provided so migration code (Step 5) can refer
to the old locations without duplicating them.
"""

import os


def _env_or_default(env_var: str, default: str) -> str:
    """Return the environment override, or *default* if it is unset/empty."""
    return os.environ.get(env_var, default) or default


# ---------------------------------------------------------------------------
# Base directories
# ---------------------------------------------------------------------------


def get_system_config_dir() -> str:
    """Return the system administrator configuration directory."""
    return _env_or_default("ZFSUTILITIES_SYSTEM_CONFIG_DIR", "/etc/zfsutilities")


def get_config_dir() -> str:
    """Return the runtime configuration directory.

    This mirrors ``get_system_config_dir`` for the new layout. It is kept
    as a separate helper so callers can distinguish system/admin config
    from runtime config if the layout ever diverges.
    """
    return _env_or_default("ZFSUTILITIES_CONFIG_DIR", "/etc/zfsutilities")


def get_state_dir() -> str:
    """Return the persistent runtime-state directory."""
    return _env_or_default("ZFSUTILITIES_STATE_DIR", "/var/lib/zfsutilities")


def get_log_dir() -> str:
    """Return the log directory."""
    return _env_or_default("ZFSUTILITIES_LOG_DIR", "/var/log/zfsutilities")


def get_run_dir() -> str:
    """Return the transient runtime-state directory."""
    return _env_or_default("ZFSUTILITIES_RUN_DIR", "/run/zfsutilities")


def get_lock_dir() -> str:
    """Return the advisory-lock directory."""
    return _env_or_default("ZFSUTILITIES_LOCK_DIR", "/run/lock/zfs")


# ---------------------------------------------------------------------------
# Derived file paths
# ---------------------------------------------------------------------------


def get_config_path() -> str:
    """Return the path to the main JSON configuration file."""
    return os.path.join(get_state_dir(), "config.json")


def get_profiles_dir() -> str:
    """Return the directory where profile JSON files are stored.

    Creates the directory if it does not already exist.
    """
    profiles_dir = os.path.join(get_state_dir(), "profiles")
    os.makedirs(profiles_dir, exist_ok=True)
    return profiles_dir


def get_history_path() -> str:
    """Return the path to the backup-history JSON file."""
    return os.path.join(get_state_dir(), "history.json")


def get_scrub_state_path() -> str:
    """Return the path to the scrub-manager state file."""
    return os.path.join(get_state_dir(), "scrub_state.json")


def get_offsite_snapfile_path() -> str:
    """Return the path to the offsite next-snapshot file."""
    return os.path.join(get_state_dir(), "nextsnap_offsite")


def get_snapfile_path(label: str = "dailybackup") -> str:
    """Return the path to the saved next-snapshot file for *label*.

    The offsite label uses ``nextsnap_offsite``; all other labels share
    ``nextsnap``.
    """
    if label == "offsite":
        return get_offsite_snapfile_path()
    return os.path.join(get_state_dir(), "nextsnap")


def get_run_snapfile_prefix() -> str:
    """Return the prefix for per-caller transient next-snapshot files."""
    return os.path.join(get_run_dir(), "nextsnap_")


def get_pid_file_path() -> str:
    """Return the path to the GUI PID file."""
    return os.path.join(get_run_dir(), "main.pid")


def get_session_log_dir() -> str:
    """Return the directory for per-session log files."""
    return os.path.join(get_log_dir(), "sessions")


def get_log_index_path() -> str:
    """Return the path to the session-log index file."""
    return os.path.join(get_session_log_dir(), ".log_index.json")


def get_cron_file_path() -> str:
    """Return the path to the cron drop-in file."""
    return _env_or_default("ZFSUTILITIES_CRON_FILE", "/etc/cron.d/zfsutilities")


def get_profile_lock_dir() -> str:
    """Return the directory for per-profile advisory locks."""
    return os.path.join(get_lock_dir(), "profiles")


# ---------------------------------------------------------------------------
# Legacy paths (for migration/rollback compatibility)
# ---------------------------------------------------------------------------


def _legacy_config_home() -> str:
    """Return the legacy per-user config directory under ``~/.config``."""
    return os.path.expanduser("~/.config")


def get_legacy_config_path() -> str:
    """Return the legacy main JSON config path."""
    return os.path.join(_legacy_config_home(), "zfsutilities.json")


def get_legacy_history_path() -> str:
    """Return the legacy backup-history path."""
    return os.path.join(_legacy_config_home(), "zfsutilities-history.json")


def get_legacy_profiles_dir() -> str:
    """Return the legacy profile directory."""
    return os.path.join(_legacy_config_home(), "profiles")


def get_legacy_scrub_state_path() -> str:
    """Return the legacy scrub-state path."""
    return os.path.join(_legacy_config_home(), "zfsutilities", "scrub_state.json")


def get_legacy_snapfile_path(label: str = "dailybackup") -> str:
    """Return the legacy saved next-snapshot path for *label*."""
    suffix = "offsite" if label == "offsite" else ""
    name = "zfsutilities_{}nextsnap".format("offsite_" if suffix else "")
    return os.path.join(_legacy_config_home(), name)


def get_legacy_system_config_paths() -> dict[str, str]:
    """Return a mapping of new system-config paths to their legacy paths.

    This is the shape Step 5's migration helper expects: keys are the new
    paths under ``/etc/zfsutilities/`` and values are the old top-level
    ``/etc`` paths.
    """
    return {
        os.path.join(get_system_config_dir(), "node.conf"): "/etc/zfsutilities-node.conf",
        os.path.join(get_system_config_dir(), "deploy.conf"): "/etc/zfsutilities-deploy.conf",
        os.path.join(
            get_system_config_dir(), "iscsi-encrypted-luns.conf"
        ): "/etc/iscsi-encrypted-luns.conf",
        os.path.join(get_system_config_dir(), "two-node.conf"): "/etc/two-node.conf",
    }

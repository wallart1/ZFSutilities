"""Logrotate drop-in management for the zfsutilities persistent logs.

Writes the logrotate drop-in (path from config_core.get_paths_config) so the
cron output log and the scrub-manager event log are rotated weekly instead of
growing without bound.  Rotated generations stay readable by non-root users.
"""

import os

from backup_config import log_msg

# Rotation policy per log:
#   weekly / rotate 8     — keep roughly two months of history
#   maxsize 100M          — rotate early if a runaway run inflates the log
#   compress              — the GUI log viewer reads .gz rotations transparently
#   create 0644 root root — every generation stays readable by non-root users
#   missingok / notifempty — harmless before the log first exists
# Rename+create rotation is safe here: all writers are short-lived processes
# that open the log in append mode per run.
_STANZA_DIRECTIVES = (
    "    weekly\n"
    "    rotate 8\n"
    "    maxsize 100M\n"
    "    missingok\n"
    "    notifempty\n"
    "    compress\n"
    "    create 0644 root root"
)

_HEADER = (
    "# Managed by ZFS Utilities — do not edit manually.\n"
    "# Regenerated whenever the cron schedule is saved.\n"
)


def build_logrotate_content(paths_cfg):
    """Return the drop-in content for the persistent logs in *paths_cfg*."""
    sections = []
    for key in ("cron_log", "scrub_manager_log"):
        sections.append(f"{paths_cfg[key]} {{\n{_STANZA_DIRECTIVES}\n}}")
    return _HEADER + "\n" + "\n\n".join(sections) + "\n"


def write_logrotate_file(paths_cfg):
    """Write (or refresh) the logrotate drop-in for the persistent logs."""
    target = paths_cfg["logrotate_file"]
    content = build_logrotate_content(paths_cfg)
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w") as f:
            f.write(content)
        os.chmod(target, 0o644)
        log_msg(f"VERB: Logrotate file updated: {target}")
    except OSError as e:
        log_msg(f"FATAL: Could not write logrotate file {target}: {e}")
        raise

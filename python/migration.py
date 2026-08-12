"""One-time migration of ZFS Utilities state files to the FHS-aligned layout.

The migration is automatic, idempotent, and rollback-compatible: after moving a
file or directory from its legacy location to the new location, a symlink is
left at the legacy path so older deployed versions can still find their data.

Migration is skipped when the ``ZFSUTILITIES_DISABLE_MIGRATION`` environment
variable is set (used by the test suites) and is gated by a sentinel file so it
only runs once per state directory.
"""

import os
import shutil
from datetime import datetime, timezone

from logging_config import log_msg
from paths import (
    get_config_path,
    get_history_path,
    get_legacy_config_path,
    get_legacy_history_path,
    get_legacy_profiles_dir,
    get_legacy_scrub_state_path,
    get_legacy_snapfile_path,
    get_legacy_system_config_paths,
    get_scrub_state_path,
    get_snapfile_path,
    get_state_dir,
)

MIGRATION_SENTINEL = ".migration_complete"


def _is_disabled():
    """Return True if migration has been disabled via environment variable."""
    return os.environ.get("ZFSUTILITIES_DISABLE_MIGRATION", "") not in ("", "0")


def get_migration_sentinel_path():
    """Return the path to the migration sentinel file."""
    return os.path.join(get_state_dir(), MIGRATION_SENTINEL)


def _backup_path(path):
    """Return a unique backup path with an ISO timestamp suffix."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{path}.{timestamp}.bak"


def _migrate_item(new_path, old_path, create_symlink=True):
    """Move *old_path* to *new_path* and optionally leave a rollback symlink.

    Rules:
      - If *new_path* exists and *old_path* does not: nothing to do.
      - If *new_path* does not exist and *old_path* exists: move it and leave
        a symlink at the legacy location.
      - If both exist: back up the legacy path with a timestamp suffix and
        leave the new path untouched; do not create a symlink.
    """
    new_exists = os.path.lexists(new_path)
    old_exists = os.path.lexists(old_path)

    if not new_exists and not old_exists:
        return

    if new_exists and not old_exists:
        return

    if not new_exists and old_exists:
        new_dir = os.path.dirname(new_path)
        if new_dir:
            os.makedirs(new_dir, exist_ok=True)
        try:
            shutil.move(old_path, new_path)
        except OSError as exc:
            log_msg(f"WARN: Could not migrate {old_path} to {new_path}: {exc}")
            return
        if create_symlink:
            try:
                os.symlink(new_path, old_path)
                log_msg(
                    f"INFO: Migrated {old_path} -> {new_path} "
                    f"(legacy symlink left for rollback compatibility)"
                )
            except OSError as exc:
                log_msg(
                    f"WARN: Migrated {old_path} -> {new_path} but could not "
                    f"create legacy symlink: {exc}"
                )
        else:
            log_msg(f"INFO: Migrated {old_path} -> {new_path}")
        return

    # Both exist: back up the legacy path and prefer the new one.
    backup = _backup_path(old_path)
    try:
        shutil.move(old_path, backup)
        log_msg(
            f"WARN: Both {old_path} and {new_path} exist; "
            f"legacy path backed up to {backup}. Using {new_path}."
        )
    except OSError as exc:
        log_msg(
            f"WARN: Both {old_path} and {new_path} exist but could not back up legacy path: {exc}"
        )


def migrate_state_files():
    """Migrate all state files and directories owned by the Python layer."""
    _migrate_item(get_config_path(), get_legacy_config_path())
    _migrate_item(get_history_path(), get_legacy_history_path())
    _migrate_item(
        os.path.join(get_state_dir(), "profiles"),
        get_legacy_profiles_dir(),
    )
    _migrate_item(get_scrub_state_path(), get_legacy_scrub_state_path())
    _migrate_item(get_snapfile_path(), get_legacy_snapfile_path())
    _migrate_item(
        get_snapfile_path("offsite"),
        get_legacy_snapfile_path("offsite"),
    )


def migrate_system_config_files():
    """Migrate system administrator config files under ``/etc/zfsutilities/``.

    This is normally invoked by the bash migration helper, but is exposed here
    for testing and for any Python callers that need it.
    """
    for new_path, old_path in get_legacy_system_config_paths().items():
        _migrate_item(new_path, old_path)


def run_migration():
    """Run the one-time state-file migration if it has not already run.

    Returns immediately when migration is disabled via environment variable or
    when the sentinel file already exists.
    """
    if _is_disabled():
        return

    sentinel = get_migration_sentinel_path()
    if os.path.exists(sentinel):
        return

    state_dir = get_state_dir()
    os.makedirs(state_dir, exist_ok=True)

    migrate_state_files()

    try:
        with open(sentinel, "w", encoding="utf-8") as f:
            f.write(datetime.now(timezone.utc).isoformat())
        log_msg(f"INFO: ZFS Utilities state migration complete ({sentinel})")
    except OSError as exc:
        log_msg(f"WARN: Could not write migration sentinel {sentinel}: {exc}")

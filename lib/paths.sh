#!/usr/bin/bash
# lib/paths.sh — Centralized path layout for ZFS Utilities bash scripts.
#
# This file defines the FHS-aligned directories and file paths used by the
# bash layer. All base directories can be overridden via environment variables
# so tests and non-standard installs do not need to patch every script.
#
# Source this file after bashinit (or rely on bashinit to source it
# automatically) so the variables are available to callers.

# Base directories (override via environment)
ZFSUTILITIES_CONFIG_DIR="${ZFSUTILITIES_CONFIG_DIR:-/etc/zfsutilities}"
ZFSUTILITIES_STATE_DIR="${ZFSUTILITIES_STATE_DIR:-/var/lib/zfsutilities}"
ZFSUTILITIES_LOG_DIR="${ZFSUTILITIES_LOG_DIR:-/var/log/zfsutilities}"
ZFSUTILITIES_RUN_DIR="${ZFSUTILITIES_RUN_DIR:-/run/zfsutilities}"
ZFSUTILITIES_LOCK_DIR="${ZFSUTILITIES_LOCK_DIR:-/run/lock/zfs}"
ZFSUTILITIES_SYSTEM_CONFIG_DIR="${ZFSUTILITIES_SYSTEM_CONFIG_DIR:-/etc/zfsutilities}"

# Derived runtime paths
ZFSUTILITIES_CONFIG_PATH="${ZFSUTILITIES_CONFIG_PATH:-${ZFSUTILITIES_STATE_DIR}/config.json}"
ZFSUTILITIES_HISTORY_PATH="${ZFSUTILITIES_HISTORY_PATH:-${ZFSUTILITIES_STATE_DIR}/history.json}"
ZFSUTILITIES_PROFILES_DIR="${ZFSUTILITIES_PROFILES_DIR:-${ZFSUTILITIES_STATE_DIR}/profiles}"
ZFSUTILITIES_SCRUB_STATE_PATH="${ZFSUTILITIES_SCRUB_STATE_PATH:-${ZFSUTILITIES_STATE_DIR}/scrub_state.json}"
ZFSUTILITIES_NEXTSNAP_FILE="${ZFSUTILITIES_NEXTSNAP_FILE:-${ZFSUTILITIES_STATE_DIR}/nextsnap}"
ZFSUTILITIES_OFFSITE_NEXTSNAP_FILE="${ZFSUTILITIES_OFFSITE_NEXTSNAP_FILE:-${ZFSUTILITIES_STATE_DIR}/nextsnap_offsite}"
ZFSUTILITIES_RUN_NEXTSNAP_PREFIX="${ZFSUTILITIES_RUN_NEXTSNAP_PREFIX:-${ZFSUTILITIES_RUN_DIR}/nextsnap_}"
ZFSUTILITIES_SCRUBALL_STATEFILE="${ZFSUTILITIES_SCRUBALL_STATEFILE:-${ZFSUTILITIES_RUN_DIR}/zfsscruball.state}"
ZFSUTILITIES_PID_FILE="${ZFSUTILITIES_PID_FILE:-${ZFSUTILITIES_RUN_DIR}/main.pid}"
ZFSUTILITIES_SESSION_LOG_DIR="${ZFSUTILITIES_SESSION_LOG_DIR:-${ZFSUTILITIES_LOG_DIR}/sessions}"
ZFSUTILITIES_CRON_FILE="${ZFSUTILITIES_CRON_FILE:-/etc/cron.d/zfsutilities}"
ZFSUTILITIES_PROFILE_LOCK_DIR="${ZFSUTILITIES_PROFILE_LOCK_DIR:-${ZFSUTILITIES_LOCK_DIR}/profiles}"

# Legacy paths (for migration/rollback compatibility)
ZFSUTILITIES_LEGACY_CONFIG_HOME="${ZFSUTILITIES_LEGACY_CONFIG_HOME:-/root/.config}"
ZFSUTILITIES_LEGACY_CONFIG_PATH="${ZFSUTILITIES_LEGACY_CONFIG_PATH:-${ZFSUTILITIES_LEGACY_CONFIG_HOME}/zfsutilities.json}"
ZFSUTILITIES_LEGACY_HISTORY_PATH="${ZFSUTILITIES_LEGACY_HISTORY_PATH:-${ZFSUTILITIES_LEGACY_CONFIG_HOME}/zfsutilities-history.json}"
ZFSUTILITIES_LEGACY_PROFILES_DIR="${ZFSUTILITIES_LEGACY_PROFILES_DIR:-${ZFSUTILITIES_LEGACY_CONFIG_HOME}/profiles}"
ZFSUTILITIES_LEGACY_SCRUB_STATE_PATH="${ZFSUTILITIES_LEGACY_SCRUB_STATE_PATH:-${ZFSUTILITIES_LEGACY_CONFIG_HOME}/zfsutilities/scrub_state.json}"
ZFSUTILITIES_LEGACY_NEXTSNAP_FILE="${ZFSUTILITIES_LEGACY_NEXTSNAP_FILE:-${ZFSUTILITIES_LEGACY_CONFIG_HOME}/zfsutilities_nextsnap}"
ZFSUTILITIES_LEGACY_OFFSITE_NEXTSNAP_FILE="${ZFSUTILITIES_LEGACY_OFFSITE_NEXTSNAP_FILE:-${ZFSUTILITIES_LEGACY_CONFIG_HOME}/zfsutilities_offsite_nextsnap}"
ZFSUTILITIES_LEGACY_NODE_CONF="${ZFSUTILITIES_LEGACY_NODE_CONF:-/etc/zfsutilities-node.conf}"
ZFSUTILITIES_LEGACY_DEPLOY_CONF="${ZFSUTILITIES_LEGACY_DEPLOY_CONF:-/etc/zfsutilities-deploy.conf}"
ZFSUTILITIES_LEGACY_ISCSI_ENCRYPTED_CONF="${ZFSUTILITIES_LEGACY_ISCSI_ENCRYPTED_CONF:-/etc/iscsi-encrypted-luns.conf}"
ZFSUTILITIES_LEGACY_TWO_NODE_CONF="${ZFSUTILITIES_LEGACY_TWO_NODE_CONF:-/etc/two-node.conf}"

# ---------------------------------------------------------------------------
# One-time migration helper (Step 5)
# ---------------------------------------------------------------------------

# _zfsutilities_migration_disabled
# Return 0 if migration has been disabled via environment variable.
_zfsutilities_migration_disabled() {
    case "${ZFSUTILITIES_DISABLE_MIGRATION:-}" in
        ""|"0") return 1 ;;
        *)       return 0 ;;
    esac
}

# _zfsutilities_migration_sentinel
# Print the path to the migration sentinel file.
_zfsutilities_migration_sentinel() {
    printf '%s/.migration_complete\n' "$ZFSUTILITIES_STATE_DIR"
}

# _zfsutilities_backup_path <path>
# Print a unique backup path with an ISO timestamp suffix.
_zfsutilities_backup_path() {
    local path="$1"
    local ts
    ts=$(date -u +%Y%m%dT%H%M%S)
    printf '%s.%s.bak\n' "$path" "$ts"
}

# _migrate_path_item <new_path> <old_path>
# Move old_path to new_path and leave a symlink at the legacy location for
# rollback compatibility. Handles both files and directories.
_migrate_path_item() {
    local new_path="$1"
    local old_path="$2"

    [[ -z "$new_path" || -z "$old_path" ]] && return 0
    [[ "$new_path" == "$old_path" ]] && return 0

    local new_exists=0 old_exists=0
    [[ -e "$new_path" || -L "$new_path" ]] && new_exists=1
    [[ -e "$old_path" || -L "$old_path" ]] && old_exists=1

    if [[ $new_exists -eq 0 && $old_exists -eq 0 ]]; then
        return 0
    fi

    if [[ $new_exists -eq 1 && $old_exists -eq 0 ]]; then
        return 0
    fi

    if [[ $new_exists -eq 0 && $old_exists -eq 1 ]]; then
        mkdir -p "$(dirname "$new_path")"
        if mv "$old_path" "$new_path" 2>/dev/null; then
            if ln -s "$new_path" "$old_path" 2>/dev/null; then
                log_msg "INFO: Migrated ${old_path} -> ${new_path} " \
                    "(legacy symlink left for rollback compatibility)"
            else
                log_msg "INFO: Migrated ${old_path} -> ${new_path}"
            fi
        else
            log_msg "WARN: Could not migrate ${old_path} to ${new_path}"
        fi
        return 0
    fi

    # Both exist: back up the legacy path and prefer the new one.
    local backup
    backup=$(_zfsutilities_backup_path "$old_path")
    if mv "$old_path" "$backup" 2>/dev/null; then
        log_msg "WARN: Both ${old_path} and ${new_path} exist; " \
            "legacy path backed up to ${backup}. Using ${new_path}."
    else
        log_msg "WARN: Both ${old_path} and ${new_path} exist but could not " \
            "back up legacy path"
    fi
}

# migrate_zfsutilities_state
# Run the one-time migration of state files and system config files to the new
# FHS-aligned layout. This function is safe to call repeatedly: it returns
# immediately if migration is disabled, not running as root, or the sentinel
# file already exists.
migrate_zfsutilities_state() {
    # Tests and non-root contexts must not trigger production migration.
    if _zfsutilities_migration_disabled; then
        return 0
    fi
    if [[ $EUID -ne 0 && "${ZFSUTILITIES_MIGRATION_ALLOW_NONROOT:-}" != "1" ]]; then
        return 0
    fi

    local sentinel
    sentinel=$(_zfsutilities_migration_sentinel)
    if [[ -e "$sentinel" ]]; then
        return 0
    fi

    mkdir -p "$ZFSUTILITIES_STATE_DIR"

    # State files owned by the Python layer (also consumed from bash).
    _migrate_path_item "$ZFSUTILITIES_CONFIG_PATH" "$ZFSUTILITIES_LEGACY_CONFIG_PATH"
    _migrate_path_item "$ZFSUTILITIES_HISTORY_PATH" "$ZFSUTILITIES_LEGACY_HISTORY_PATH"
    _migrate_path_item "$ZFSUTILITIES_PROFILES_DIR" "$ZFSUTILITIES_LEGACY_PROFILES_DIR"
    _migrate_path_item "$ZFSUTILITIES_SCRUB_STATE_PATH" "$ZFSUTILITIES_LEGACY_SCRUB_STATE_PATH"
    _migrate_path_item "$ZFSUTILITIES_NEXTSNAP_FILE" "$ZFSUTILITIES_LEGACY_NEXTSNAP_FILE"
    _migrate_path_item "$ZFSUTILITIES_OFFSITE_NEXTSNAP_FILE" "$ZFSUTILITIES_LEGACY_OFFSITE_NEXTSNAP_FILE"

    # System administrator config files under /etc/zfsutilities/.
    _migrate_path_item "${ZFSUTILITIES_SYSTEM_CONFIG_DIR}/node.conf" "$ZFSUTILITIES_LEGACY_NODE_CONF"
    _migrate_path_item "${ZFSUTILITIES_SYSTEM_CONFIG_DIR}/deploy.conf" "$ZFSUTILITIES_LEGACY_DEPLOY_CONF"
    _migrate_path_item "${ZFSUTILITIES_SYSTEM_CONFIG_DIR}/iscsi-encrypted-luns.conf" "$ZFSUTILITIES_LEGACY_ISCSI_ENCRYPTED_CONF"
    _migrate_path_item "${ZFSUTILITIES_SYSTEM_CONFIG_DIR}/two-node.conf" "$ZFSUTILITIES_LEGACY_TWO_NODE_CONF"

    if touch "$sentinel" 2>/dev/null; then
        log_msg "INFO: ZFS Utilities state migration complete (${sentinel})"
    else
        log_msg "WARN: Could not write migration sentinel ${sentinel}"
    fi
}

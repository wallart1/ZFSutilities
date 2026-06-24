"""
Action dispatch tables and page button specifications for the main GUI window.

This module separates the declarative page metadata from the window class
to keep zfsutilities_gui.py focused on UI construction and core behaviour.
"""

from backup_config import log_msg, get_scrub_manager_config
from backup_page import (
    collect_backup_config, load_backup_config,
    on_backup_run, on_backup_cancel, on_backup_save, on_backup_revert,
    backup_set_all_active, check_backup_dirty,
)
from offsite_page import (
    collect_offsite_config, load_offsite_config,
    on_offsite_run, on_offsite_cancel, on_offsite_save, on_offsite_revert,
    offsite_set_all_active,
    check_offsite_dirty,
)
from restore_page import (
    collect_restore_config, load_restore_config,
    on_restore_run, on_restore_cancel, on_restore_save, on_restore_revert,
    check_restore_dirty,
)
from pools_page import refresh_pools_page
from pool_actions import (
    on_pools_watch, on_pools_details, on_pools_add, on_pools_remove,
    on_pools_import, on_pools_export,
    on_pools_save, on_pools_revert, check_pools_dirty,
    on_scrub_start, on_scrub_pause, on_scrub_resume, on_scrub_stop,
)
from datasets_page import (
    refresh_datasets_page,
    update_ds_button_sensitivity,
    expand_selected_datasets,
)
from dataset_actions import (
    on_datasets_snapshot, on_datasets_delete,
    on_datasets_hold, on_datasets_rollback,
    on_datasets_show_files,
    on_datasets_browse_snapshot, on_datasets_unmount_snapshot,
)
from retention_page import (
    collect_retention_profile_config, load_retention_profile_config,
)
from retention_actions import (
    on_retention_add_bucket, on_retention_remove_bucket,
    on_retention_add_policy, on_retention_remove_policy,
    on_retention_prune,
    on_retention_save, on_retention_revert, check_retention_dirty,
)
from checkagainst_page import (
    on_checkagainst_add, on_checkagainst_remove,
    on_checkagainst_save, on_checkagainst_revert, check_checkagainst_dirty,
)
from schedule_page import (
    on_schedule_save, on_schedule_revert, on_schedule_delete,
    check_schedule_dirty,
)
from profile_dialogs import show_add_profile_dialog, show_recall_profile_dialog
from logs_page import (
    _sync_log_list, _on_delete_selected, _on_prune_old,
    _setup_logs_actions,
)
from dashboard_page import (
    refresh_dashboard_page, on_dashboard_refresh, on_dashboard_fix_locks,
    on_dashboard_cancel_selected, on_dashboard_view_log, setup_dashboard_actions,
)


# ---------------------------------------------------------------------------
# Page action button specifications
# ---------------------------------------------------------------------------
# Each entry defines buttons, runner info, dry-run toggle, and dirty-check
# for a single page.  Used by update_action_buttons().
PAGE_SPECS = {
    "backup": {
        "runner": "backup_runner",
        "run": ("Run Backup", "media-playback-start"),
        "dry_run": True,
        "buttons": [
            ("Select All", "edit-select-all", None),
            ("Select None", "edit-clear", None),
            ("Save Config", "document-save", "_save_config_button"),
            ("Revert Config", "document-revert", None),
            ("Add Profile to Schedule", "list-add", None),
            ("Recall Profile", "document-open", None),
        ],
        "dirty_check": check_backup_dirty,
        "dirty_attr": "_backup_saved_state",
    },
    "offsite": {
        "runner": "offsite_runner",
        "run": ("Run Offsite", "media-playback-start"),
        "dry_run": True,
        "buttons": [
            ("Select All", "edit-select-all", None),
            ("Select None", "edit-clear", None),
            ("Save Config", "document-save", "_offsite_save_button"),
            ("Revert Config", "document-revert", None),
            ("Add Profile to Schedule", "list-add", None),
            ("Recall Profile", "document-open", None),
        ],
        "dirty_check": check_offsite_dirty,
        "dirty_attr": "_offsite_saved_state",
    },
    "restore": {
        "runner": "restore_runner",
        "run": ("Run Restore", "media-playback-start"),
        "dry_run": True,
        "buttons": [
            ("Save Config", "document-save", "_restore_save_button"),
            ("Revert Config", "document-revert", None),
            ("Add Profile to Schedule", "list-add", None),
            ("Recall Profile", "document-open", None),
        ],
        "dirty_check": check_restore_dirty,
        "dirty_attr": "_restore_saved_state",
    },
    "schedule": {
        "buttons": [
            ("Save", "document-save", "_schedule_save_button"),
            ("Revert", "document-revert", None),
            ("Delete", "edit-delete", None),
        ],
        "dirty_check": check_schedule_dirty,
        "dirty_attr": "_schedule_saved_state",
    },
    "pools": {
        "buttons": [
            ("Watch", "utilities-system-monitor", None),
            ("Add", "list-add", None),
            ("Remove", "list-remove", None),
            ("Import", "document-open", None),
            ("Export", "media-eject", None),
            ("Save", "document-save", "_pools_save_button"),
            ("Revert", "document-revert", None),
            ("Refresh", "view-refresh", None),
            (None, None, None),                       # spacer
            ("Start Scrub", "media-playback-start", None),
            ("Pause Scrub", "media-playback-pause", None),
            ("Resume Scrub", "media-seek-forward", None),
            ("Stop Scrub", "media-playback-stop", None),
            ("Add Profile to Schedule", "list-add", None),
        ],
        "dirty_check": check_pools_dirty,
        "dirty_attr": "_pools_saved_state",
    },
    "datasets": {
        "buttons": [
            ("Snapshot", "list-add", "_ds_snapshot_btn"),
            ("Delete", "edit-delete", "_ds_delete_btn"),
            ("Add Hold", "changes-prevent", "_ds_hold_btn"),
            ("Rollback", "edit-undo", "_ds_rollback_btn"),
            ("Show Files", "folder-open", "_ds_showfiles_btn"),
            ("Browse Snapshot", "folder-open", "_ds_browsesnap_btn"),
            ("Unmount Snapshot", "media-eject", "_ds_unmountsnap_btn"),
            ("Refresh", "view-refresh", None),
            ("Expand Selected", "zoom-in", "_ds_expand_selected_btn"),
            ("Collapse All", "list-remove", None),
        ],
        "post_setup": update_ds_button_sensitivity,
    },
    "checkagainst": {
        "buttons": [
            ("Add Row", "list-add", None),
            ("Remove Row", "list-remove", None),
            ("Save", "document-save", "_ca_save_button"),
            ("Revert", "document-revert", None),
        ],
        "dirty_check": check_checkagainst_dirty,
        "dirty_attr": "_ca_original",
    },
    "dashboard": {
        "buttons": [
            ("Refresh", "view-refresh", None),
            ("Fix Locks", "edit-clear", "_fix_locks_button"),
            ("Cancel Selected Tasks", "process-stop", "_cancel_selected_button"),
            ("View Log", "text-x-generic", "_view_log_button"),
        ],
        "post_setup": setup_dashboard_actions,
    },
    "logs": {
        "buttons": [
            ("Refresh", "view-refresh", None),
            ("Delete Selected", "edit-delete", "_logs_delete_button"),
            ("Prune Old", "edit-clear", None),
        ],
        "post_setup": _setup_logs_actions,
    },
    "retention": {
        "runner": "retention_runner",
        "run": ("Prune", "media-playback-start"),
        "dry_run": True,
        "buttons": [
            ("Add Policy", "list-add", None),
            ("Remove Policy", "list-remove", None),
            ("Add Bucket", "list-add", None),
            ("Remove Bucket", "list-remove", None),
            ("Save", "document-save", "_ret_save_button"),
            ("Revert", "document-revert", None),
            ("Add Profile to Schedule", "list-add", None),
            ("Recall Profile", "document-open", None),
        ],
        "dirty_check": check_retention_dirty,
        "dirty_attr": "_ret_original",
    },
}


def _collect_scrub_config(app):
    """Gather current scrub settings for profile creation."""
    from pools_page import get_selected_pool_names
    selected = get_selected_pool_names(app.scrub_view)
    if not selected:
        queue = app.scrub_queue
        selected = sorted(queue.pending | queue.active | queue.paused)
    cfg = get_scrub_manager_config(app.config)
    return {
        "pools": selected,
        "simultaneous": app.scrub_queue.target,
        "refresh_seconds": cfg.get("refresh_seconds", 10),
        "system_scrub_weekly": cfg.get("system_scrub_weekly", False),
        "system_scrub_monthly": cfg.get("system_scrub_monthly", False),
    }


# ---------------------------------------------------------------------------
# Context wrapper for Phase 4 handlers
# ---------------------------------------------------------------------------
def _ctx_handler(fn):
    """Wrap a handler that needs the AppContext as a second argument.

    action_dispatch handlers are called with the window (`app`) only. Phase 4
    page handlers accept `(app, ctx)`; this wrapper supplies `app.ctx`.
    """
    return lambda app: fn(app, app.ctx)


# ---------------------------------------------------------------------------
# Helper wrappers for handlers that need post-processing
# ---------------------------------------------------------------------------
def _handler_pools_save(app):
    on_pools_save(app)
    app.update_action_buttons("pools")


def _handler_pools_revert(app):
    on_pools_revert(app)
    app.update_action_buttons("pools")


def _handler_datasets_refresh(app):
    refresh_datasets_page(app)
    log_msg("INFO: Datasets refreshed")


def _handler_checkagainst_save(app):
    on_checkagainst_save(app)
    app.update_action_buttons("checkagainst")


def _handler_checkagainst_revert(app):
    on_checkagainst_revert(app)
    app.update_action_buttons("checkagainst")


def _handler_retention_add_policy(app):
    on_retention_add_policy(app, app.ctx)
    app.update_action_buttons("retention")


def _handler_retention_remove_policy(app):
    on_retention_remove_policy(app, app.ctx)
    app.update_action_buttons("retention")


def _handler_retention_save(app):
    on_retention_save(app, app.ctx)
    app.update_action_buttons("retention")


def _handler_retention_revert(app):
    on_retention_revert(app, app.ctx)
    app.update_action_buttons("retention")


def _handler_retention_cancel(app):
    if app.retention_runner and app.retention_runner.running:
        app.retention_runner.cancel()


# ---------------------------------------------------------------------------
# Two-level dispatch table for action buttons
# ---------------------------------------------------------------------------
ACTION_HANDLERS = {
    "backup": {
        "Run Backup": _ctx_handler(on_backup_run),
        "Cancel": _ctx_handler(on_backup_cancel),
        "Select All": lambda app: backup_set_all_active(app, app.ctx, True),
        "Select None": lambda app: backup_set_all_active(app, app.ctx, False),
        "Save Config": _ctx_handler(on_backup_save),
        "Revert Config": _ctx_handler(on_backup_revert),
        "Add Profile to Schedule": lambda app: show_add_profile_dialog(
            app, "backup", collect_backup_config(app),
            dry_run=getattr(app, '_dry_run_active', False)
        ),
        "Recall Profile": lambda app: show_recall_profile_dialog(
            app, "backup", lambda p: load_backup_config(app, p["config"])
        ),
    },
    "offsite": {
        "Run Offsite": _ctx_handler(on_offsite_run),
        "Cancel": _ctx_handler(on_offsite_cancel),
        "Select All": lambda app: offsite_set_all_active(app, app.ctx, True),
        "Select None": lambda app: offsite_set_all_active(app, app.ctx, False),
        "Save Config": _ctx_handler(on_offsite_save),
        "Revert Config": _ctx_handler(on_offsite_revert),
        "Add Profile to Schedule": lambda app: show_add_profile_dialog(
            app, "offsite", collect_offsite_config(app),
            dry_run=getattr(app, '_dry_run_active', False)
        ),
        "Recall Profile": lambda app: show_recall_profile_dialog(
            app, "offsite", lambda p: load_offsite_config(app, p["config"])
        ),
    },
    "restore": {
        "Run Restore": _ctx_handler(on_restore_run),
        "Cancel": _ctx_handler(on_restore_cancel),
        "Save Config": _ctx_handler(on_restore_save),
        "Revert Config": _ctx_handler(on_restore_revert),
        "Add Profile to Schedule": lambda app: show_add_profile_dialog(
            app, "restore", collect_restore_config(app),
            dry_run=getattr(app, '_dry_run_active', False)
        ),
        "Recall Profile": lambda app: show_recall_profile_dialog(
            app, "restore", lambda p: load_restore_config(app, p["config"])
        ),
    },
    "pools": {
        "Watch": on_pools_watch,
        "Details": on_pools_details,
        "Add": on_pools_add,
        "Remove": on_pools_remove,
        "Import": on_pools_import,
        "Export": on_pools_export,
        "Save": _handler_pools_save,
        "Revert": _handler_pools_revert,
        "Refresh": refresh_pools_page,
        "Start Scrub": on_scrub_start,
        "Pause Scrub": on_scrub_pause,
        "Resume Scrub": on_scrub_resume,
        "Stop Scrub": on_scrub_stop,
        "Add Profile to Schedule": lambda app: show_add_profile_dialog(
            app, "scrub", _collect_scrub_config(app)
        ),
    },
    "datasets": {
        "Snapshot": on_datasets_snapshot,
        "Delete": on_datasets_delete,
        "Add Hold": on_datasets_hold,
        "Rollback": on_datasets_rollback,
        "Show Files": on_datasets_show_files,
        "Browse Snapshot": on_datasets_browse_snapshot,
        "Unmount Snapshot": on_datasets_unmount_snapshot,
        "Refresh": _handler_datasets_refresh,
        "Expand Selected": expand_selected_datasets,
        "Collapse All": lambda app: app.datasets_view.collapse_all(),
    },
    "checkagainst": {
        "Add Row": on_checkagainst_add,
        "Remove Row": on_checkagainst_remove,
        "Save": _handler_checkagainst_save,
        "Revert": _handler_checkagainst_revert,
    },
    "schedule": {
        "Save": on_schedule_save,
        "Revert": on_schedule_revert,
        "Delete": on_schedule_delete,
    },
    "logs": {
        "Refresh": _sync_log_list,
        "Delete Selected": _on_delete_selected,
        "Prune Old": _on_prune_old,
    },
    "dashboard": {
        "Refresh": on_dashboard_refresh,
        "Fix Locks": on_dashboard_fix_locks,
        "Cancel Selected Tasks": on_dashboard_cancel_selected,
        "View Log": on_dashboard_view_log,
    },
    "retention": {
        "Add Policy": _handler_retention_add_policy,
        "Remove Policy": _handler_retention_remove_policy,
        "Add Bucket": _ctx_handler(on_retention_add_bucket),
        "Remove Bucket": _ctx_handler(on_retention_remove_bucket),
        "Save": _handler_retention_save,
        "Revert": _handler_retention_revert,
        "Add Profile to Schedule": lambda app: show_add_profile_dialog(
            app, "retention", collect_retention_profile_config(app),
            dry_run=getattr(app, '_dry_run_active', False)
        ),
        "Recall Profile": lambda app: show_recall_profile_dialog(
            app, "retention", lambda p: load_retention_profile_config(app, p["config"])
        ),
        "Prune": _ctx_handler(on_retention_prune),
        "Cancel": _handler_retention_cancel,
    },
}

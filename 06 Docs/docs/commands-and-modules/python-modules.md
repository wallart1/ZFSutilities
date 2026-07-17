# Python Modules Reference

These modules make up the GTK GUI and command-orchestration layer of ZFS
Utilities. They read and write the shared JSON config, build `bash` commands,
run them through `subprocess`, and present the results in the GTK interface.

Most modules are in `07 GTK + Python/`. They are grouped below by role:

- [Config and data](#config-and-data)
- [ZFS repository and info](#zfs-repository-and-info)
- [Command builders and runners](#command-builders-and-runners)
- [GUI pages and actions](#gui-pages-and-actions)
- [Managers and helpers](#managers-and-helpers)
- [Entry points](#entry-points)

Cross-references:

- Shared data structures are documented in full on
  [Data Structures](../developer-guide/data-structures.md).
- Bash commands and modules that the Python layer invokes are in
  [Commands](commands.md) and [Modules](modules.md).

---

## Config and data

### `config_core.py`

Low-level config I/O and small, cross-cutting configuration helpers.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `load_config()` | Read the JSON config from `CONFIG_PATH`, applying migrations |
| `save_config(config)` | Atomically write the full config dict back to disk |
| `run_migrations(config)` | Apply pending migrations via `config_migrations.py` |
| `get_ui_state()` / `save_ui_state()` | Load/save window geometry and paned positions |
| `get_dashboard_config()` / `save_dashboard_config()` | Dashboard threshold settings |
| `get_log_retention_days()` / `save_log_retention_days()` | Session-log retention days |
| `get_history_retention_days()` / `save_history_retention_days()` | History retention days |
| `get_session_log_max_bytes()` / `save_session_log_max_bytes()` | Session-log size cap |
| `prune_old_logs(retention_days)` | Delete session logs older than the retention setting |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `config_migrations` | Run schema migrations on load |
| `logging_config` | `log_msg` for warnings |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| JSON config (`/root/.config/zfsutilities.json`) | [JSON config][ds-json] |
| Session log directory | [Session log index][ds-log] |

---

### `feature_config.py`

Feature-specific getters and setters for the JSON config sections that back
the GUI tabs and the bash scripts.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `get_backup_config()` / `save_backup_config()` | Backup tab state |
| `get_offsite_config()` / `save_offsite_config()` | Offsite tab state |
| `get_restore_config()` / `save_restore_config()` | Restore tab state |
| `get_pools()` / `save_pools()` | Registered pool list, including `offsite_candidate` flag |
| `get_checkagainst()` / `save_checkagainst()` | fss table rows |
| `get_retention()` / `save_retention()` | Per-pool retention policies |
| `get_archive_path()` / `save_archive_path()` | Offsite archive path |
| `get_prune_label()` / `save_prune_label()` | Global retention prune label |
| `get_prune_pools_order()` / `save_prune_pools_order()` | Retention Prune pool order |
| `get_retention_mass_delete_config()` / `save_retention_mass_delete_config()` | Retention tab Mass Delete card settings |
| `get_scrub_manager_config()` / `save_scrub_manager_config()` | Scrub queue settings |
| `load_scrub_state()` / `save_scrub_state()` | Scrub queue persistence |
| `generate_snapshot_name()` | Generate a backup snapshot name and update the snapfile |
| `generate_offsite_snapshot_name()` | Generate an offsite snapshot name and update the snapfile |
| `import_legacy_retention()` | One-time scan of `zfsretainpol-*` files |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `config_core` | `save_config`, `_deep_copy`, default constants |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| JSON config feature sections | [backup/offsite/restore/pools/retention/checkagainst/scrub][ds-json] |
| Snapshot name persistence and one-minute reservation | [Snapshot name persistence][ds-snapfile] |

---

### `backup_config.py`

Backward-compatibility facade that re-exports the public API of
`config_core`, `feature_config`, and `logging_config`. Older modules import
from `backup_config`; newer code imports directly from the specialised module.

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `logging_config` | Re-export `log_msg`, message levels, log sink helpers |
| `config_core` | Re-export config I/O and UI-state helpers |
| `feature_config` | Re-export feature getters/setters and snapshot naming |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| Same as `config_core` and `feature_config` | [JSON config][ds-json] |

---

### `config_migrations.py`

Config schema migrations. `CONFIG_VERSION` and the `MIGRATIONS` list are the
single source of truth for the JSON config format version.

**Key items:**

| Item | Purpose |
| ---- | ------- |
| `CONFIG_VERSION` | Current schema version |
| `MIGRATIONS` | Ordered list of one-version migration functions |
| `run_migrations(config)` | Apply all pending migrations |

**Called modules / imported helpers:** none.

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| `config_version` field | [config_version][ds-config-migrations] |

---

## ZFS repository and info

### `zfs_repository.py`

Isolates all direct `zfs`/`zpool` subprocess calls. The repository returns
typed dataclasses instead of raw tab-separated strings, which makes the GUI
and tests easy to mock.

**Key classes:**

| Class | Purpose |
| ----- | ------- |
| `PoolRow` | One row from `zpool list -H -o name,health,size,alloc,free,cap` |
| `DatasetRow` | One row from `zfs list -H -o name,creation,type,used,avail,refer,origin,clones` |
| `SnapshotRow` | One row from `zfs list -t snapshot -H -o ...` |
| `HoldRow` | One row from `zfs holds -H <snapshot>` |
| `ZfsRepository` | Wraps all `zfs`/`zpool` subprocess commands |

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `get_default_repository()` | Returns a module-level default `ZfsRepository` instance |

**Called modules / imported helpers:** none (uses `subprocess` directly).

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| `ZfsRepository` dataclasses | [ZfsRepository dataclasses][ds-zfsrepo] |

---

### `zfsinfo.py`

Small CLI helper that prints pool, dataset, and snapshot information. It is
the Python equivalent of a few ad-hoc `zpool list` / `zfs list` one-liners.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `get_pools()` | Return pool health list via `ZfsRepository` |
| `get_datasets(pool)` | Return dataset tree via `ZfsRepository` |
| `get_snapshot_counts()` | Return snapshot count per dataset |
| `print_summary()` | Print aggregate statistics |
| `main()` | CLI entry point |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `zfs_repository` | `get_default_repository` and row dataclasses |
| `logging_config` | `log_msg` |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| `ZfsRepository` dataclasses | [ZfsRepository dataclasses][ds-zfsrepo] |

---

### `diagnose_zfs_repository.py`

CLI diagnostic wrapper around `ZfsRepository`. Used to exercise repository
methods directly for troubleshooting.

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `zfs_repository` | `ZfsRepository` |

---

## Command builders and runners

### `command_builders.py`

Builds the `bash` command strings and `BashStep` objects used by the backup,
offsite, restore, and retention runners.

**Key class:**

| Class | Purpose |
| ----- | ------- |
| `BashStep` | A single executable step: `command` list, `description`, `is_rsync`, `fatal` |

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `parse_rsync_endpoint(endpoint)` | Split `user@host:path` into host and path |
| `build_rsync_command(source, dest)` | Build an rsync pull command |
| `build_send_receive_command(...)` | Build the `bash` command for a ZFS send/receive step |
| `build_pre_backup_command(cmd)` / `build_post_backup_command(cmd)` | Wrap user pre/post commands |
| `build_retention_command(...)` | Build the `zfscleanup` invocation |
| `build_installed_programs_command(host)` | Build `backup-installed-programs` over SSH |

**Called modules / imported helpers:** none (stdlib only).

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| `BashStep` | [BashStep][ds-bashstep] |

---

### `backup_runner.py`

Runs a list of `BashStep` objects asynchronously. Manages the session log,
progress parsing, cancellation, and final history/log-index entries.

**Key class:**

| Class | Purpose |
| ----- | ------- |
| `BackupRunner` | Async runner for GUI-initiated backup/offsite/restore operations |

**Internal flow:**

1. `prepare_session_log()` creates a timestamped log under `SESSION_LOG_DIR`.
2. `start()` spawns each step in a PTY so output can be streamed.
3. `_on_stdout()` / `_on_stderr()` parse `pv`/`zfs receive` progress and
   append raw lines to the log.
4. `_write_session_trailer()` writes the `# END` trailer and updates the
   log index.
5. `_maybe_truncate_session_log()` enforces the configured size cap.

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `logging_config` | Session log context, truncation, `log_msg` |
| `log_index` | `LogIndex` for updating cached log metadata |
| `backup_history` | Build and append history entries |
| `command_builders` | `BashStep` |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| `BashStep` | [BashStep][ds-bashstep] |
| Session log files | [Session log index][ds-log] |
| Session log index | [Session log index][ds-log] |
| Backup history | [Backup history][ds-history] |

---

### `offsite_runner.py`

Offsite-specific command building and pool detection.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `detect_offsite_pool(candidates)` | Find the first online pool in the candidate list |
| `build_offsite_step_command(...)` | Build an offsite send/receive step with optional holds |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `command_builders` | `BashStep`, `_dryrun_assignments` |
| `logging_config` | `log_msg` |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| `BashStep` | [BashStep][ds-bashstep] |
| Offsite candidate pool list (JSON config `pools`) | [JSON config][ds-json] |

---

### `restore_runner.py`

Computes restore destination paths and builds the restore `BashStep`.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `compute_auto_destination(...)` | Derive default destination by stripping qualifiers |
| `compute_restore_params(sourcefs, destfs)` | Compute send/receive parameters for restore |
| `build_restore_command(...)` | Build the `bash` command for a restore operation |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `command_builders` | `BashStep`, `_dryrun_assignments` |
| `logging_config` | `log_msg` |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| `BashStep` | [BashStep][ds-bashstep] |

---

### `profile_runner.py`

Runs scheduled/cron profiles from JSON files. Reuses much of the same logic
as the GUI runners but writes its own session logs and history entries.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `run_backup_profile(profile)` | Build and run a backup profile |
| `run_offsite_profile(profile)` | Build and run an offsite profile |
| `run_restore_profile(profile)` | Build and run a restore profile |
| `run_retention_profile(profile)` | Run retention/cleanup for configured pools |
| `run_scrub_profile(profile)` | Queue and poll scrubs for configured pools |
| `_check_weekday_ordinal(weekday_field)` | Runtime guard for weekday ordinal expressions |
| `_profile_lock_path(profile_name)` | Path to the per-profile lock file |
| `acquire_profile_lock(profile_name, timeout=1.0)` | Acquire the profile lock; suppress duplicate runs |
| `release_profile_lock(fd, lock_path)` | Release the profile lock |
| `main()` | CLI entry point for cron execution |

**Internal flow:**

1. Load the requested profile from disk to determine its tab type.
2. Create a session log so that lock-skip messages and early errors are
   recorded.
3. Acquire a per-profile advisory lock so a duplicate cron invocation exits
   cleanly instead of running the profile twice.
4. If the profile's cron weekday field contains an ordinal expression
   (`#1`–`#5` or `#L`), verify today matches it; otherwise skip the run.
5. Generate snapshot names and build `BashStep` lists using the same helpers
   as the GUI pages.
6. Run each step, write the trailer, and append a history entry.

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `command_builders` | Build rsync, send/receive, retention, pre/post `BashStep`s |
| `offsite_runner` | Detect offsite pool and build offsite steps |
| `restore_runner` | Compute restore params |
| `profile_manager` | Load profile JSON |
| `scrub_manager` | Scrub queue operations |
| `config_core` | `load_config`, session log directory |
| `feature_config` | Snapshot naming, pool names, snapfile removal |
| `logging_config` | Session log context, truncation, `log_msg` |
| `log_index` | Update log index entries |
| `backup_history` | Append history entries |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| `BashStep` | [BashStep][ds-bashstep] |
| JSON config | [JSON config][ds-json] |
| Session log files / index | [Session log index][ds-log] |
| Backup history | [Backup history][ds-history] |
| Scrub state / `ScrubQueue` | [Scrub state][ds-scrub] |

---

### `runner_factory.py`

Creates `BackupRunner` instances pre-bound to the main window's log and
progress callbacks.

**Key class:**

| Class | Purpose |
| ----- | ------- |
| `RunnerFactory` | Factory for runners sharing the same GUI sink |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `backup_runner` | `BackupRunner` |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| `BackupRunner` | produced by this module |

---

### `backup_history.py`

Append-only history store for backup/offsite/restore/prune runs.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `load_history()` / `save_history()` | Read/write `/root/.config/zfsutilities-history.json` |
| `add_history_entry(entry)` | Append a new entry and prune old ones |
| `prune_history(history, days)` | Remove entries older than `days` |
| `get_success_rate(history, days)` | Compute success percentage for recent entries |
| `get_recent_entries(limit)` | Return newest entries |
| `format_duration(seconds)` | Format seconds as `HH:MM:SS` |
| `_parse_human_size(size)` | Parse `pv` size strings to bytes |
| `build_entry(...)` | Construct a standard history dict |

**Called modules / imported helpers:** none (stdlib only).

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| Backup history | [Backup history][ds-history] |

---

## GUI pages and actions

### `app_context.py`

Cross-cutting, non-GTK state container passed to GUI pages and action
handlers.

**Key class:**

| Class | Purpose |
| ----- | ------- |
| `AppContext` | Shared state: loaded config, script directories, version, `ZfsRepository` |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| `AppContext` | [AppContext][ds-appctx] |

---

### `action_dispatch.py`

Central dispatch tables for the main-window action panel. Each page exports
button specifications; this module maps them to the correct handler function
and wraps handlers that need the `AppContext`.

**Key items:**

| Item | Purpose |
| ---- | ------- |
| `PAGE_SPECS` | List of page button specs used to build the action panel |
| `ACTION_HANDLERS` | Dictionary mapping action names to handler functions |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `backup_page` | Backup tab handlers |
| `offsite_page` | Offsite tab handlers |
| `restore_page` | Restore tab handlers |
| `pools_page` / `pool_actions` | Pool tab handlers |
| `datasets_page` / `dataset_actions` | Datasets tab handlers |
| `retention_page` / `retention_actions` | Retention tab handlers |
| `checkagainst_page` | Checkagainst tab handlers |
| `schedule_page` | Schedule tab handlers |
| `dashboard_page` | Dashboard tab handlers |
| `logs_page` | Logs tab handlers |
| `profile_dialogs` | Add/recall profile dialogs |
| `backup_config` | `log_msg`, scrub config helpers |

---

### `backup_page.py`

Backup tab: UI for pull steps, send/receive steps, pre/post commands, and
snapshot-name generation.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `create_backup_page(ctx, ...)` | Build the Backup tab widget |
| `load_backup_config()` / `collect_backup_config()` | Move data between UI and config dict |
| `check_backup_dirty()` / `mark_backup_clean()` | Track unsaved changes |
| `on_backup_run()` | Build `BashStep`s and start a `BackupRunner` |
| `on_backup_cancel()` | Cancel the running backup |
| `on_backup_save()` / `on_backup_revert()` | Persist or revert config |
| `backup_set_all_active()` | Toggle all step Active checkboxes |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `feature_config` | Read/write backup config and snapshot names |
| `command_builders` | Build `BashStep`s |
| `backup_runner` | Run the generated steps |
| `gui_helpers` | Widget helpers, dirty tracking |
| `profile_dialogs` | Add/recall profile dialogs |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| `backup` config object | [backup object][ds-backup] |
| `BashStep` | [BashStep][ds-bashstep] |
| Snapshot name persistence | [Snapshot name persistence][ds-snapfile] |

---

### `offsite_page.py`

Offsite Backup tab: one or more offsite send/receive steps, offsite pool
detection, and snapshot-name generation.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `create_offsite_page()` | Build the Offsite tab widget |
| `collect_offsite_config()` / `load_offsite_config()` | UI ↔ config |
| `check_offsite_dirty()` / `mark_offsite_clean()` | Dirty-state tracking |
| `do_detect_offsite_pool()` | Find an online offsite candidate pool |
| `on_offsite_run()` / `on_offsite_cancel()` | Start/cancel an offsite run |
| `offsite_set_all_active()` | Toggle step Active checkboxes |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `feature_config` | Offsite config and snapshot names |
| `offsite_runner` | Detect pool and build offsite steps |
| `backup_runner` | Run steps (via returned `BashStep`s) |
| `gui_helpers` | Widget helpers |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| `offsite` config object | [JSON config][ds-json] |
| `BashStep` | [BashStep][ds-bashstep] |

---

### `restore_page.py`

Restore tab: choose a source snapshot, compute an auto-destination, and run
`zfs-send-receive` in restore mode.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `create_restore_page()` | Build the Restore tab widget |
| `collect_restore_config()` / `load_restore_config()` | UI ↔ config |
| `check_restore_dirty()` / `mark_restore_clean()` | Dirty-state tracking |
| `refresh_restore_destination()` | Recompute default destination |
| `on_restore_run()` / `on_restore_cancel()` | Start/cancel a restore |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `feature_config` | Pool list and restore config |
| `restore_runner` | Destination computation and command building |
| `backup_runner` | Run restore steps |
| `command_builders` | `BashStep` |
| `gui_helpers` | Widget helpers |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| `restore` config object | [JSON config][ds-json] |
| `BashStep` | [BashStep][ds-bashstep] |

---

### `retention_page.py`

Retention Policies tab: edit per-pool bucket policies and the prune pool
list.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `create_retention_page()` | Build the Retention tab widget |
| `collect_retention_profile_config()` / `load_retention_profile_config()` | Profile support |
| `refresh_prune_pools()` | Refresh the prune list with online pools that have policies |
| `_on_ret_save()` / `_on_ret_revert()` | Persist or revert policy changes |
| `_clear_non_default_policies_on_new_install()` | Fresh-install cleanup |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `feature_config` | Retention getters/setters, legacy import |
| `config_core` | `save_config` |
| `gui_helpers` | TreeView helpers |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| `retention` config object | [JSON config][ds-json] |

---

### `checkagainst_page.py`

Checkagainst tab: edit the fss table that tells
[`zfscheckagainst`](modules.md#zfscheckagainst) which counterpart datasets must
share a common snapshot before a source snapshot can be deleted safely.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `create_checkagainst_page()` | Build the Checkagainst tab widget |
| `on_checkagainst_add()` / `on_checkagainst_remove()` | Add/remove rows |
| `on_checkagainst_save()` / `on_checkagainst_revert()` | Persist or revert |
| `check_checkagainst_dirty()` | Highlight unsaved changes |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `feature_config` | Read/write fss table |
| `gui_helpers` | TreeView column setup |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| `zfscheckagainst` config rows / fss table | [fss table][ds-fss] |

---

### `datasets_page.py`

Datasets tab: a lazy-loading tree of pools, datasets, snapshots, and holds.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `create_datasets_page()` | Build the Datasets tab widget |
| `refresh_datasets_page()` | Refresh the tree, preserving expansion state |
| `expand_selected_datasets()` | Expand selected rows recursively |
| `update_ds_button_sensitivity()` | Enable/disable action buttons |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `gui_helpers` | Tree building, search, selection helpers |
| `logging_config` | `log_msg` |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| `ZfsRepository` dataclasses (via helper functions) | [ZfsRepository dataclasses][ds-zfsrepo] |

---

### `dashboard_page.py`

Dashboard tab: pool health, recent operations, iSCSI issues, running tasks,
version comparison with a two-node peer, and warnings.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `create_dashboard_page()` | Build the Dashboard tab widget |
| `refresh_dashboard_page()` | Re-gather all dashboard data |
| `_get_pool_health()` | Query `zpool list` via `ZfsRepository` |
| `_get_warnings()` | Compile warning strings from all sources |
| `_get_peer_host()` / `_get_host_version()` | Two-node peer version check |
| Dashboard action handlers | Refresh, fix locks, cancel tasks, view log |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `zfs_repository` | Default repository for pool queries |
| `config_core` | Dashboard config |
| `backup_history` | Recent operations |
| `logs_page` | Select log by path |
| `gui_helpers` | TreeView helpers |
| `logging_config` | `log_msg` |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| `ZfsRepository` dataclasses | [ZfsRepository dataclasses][ds-zfsrepo] |
| Backup history | [Backup history][ds-history] |
| Session log index | [Session log index][ds-log] |
| Node configuration | [Node configuration][ds-node] |

---

### `pools_page.py`

Pools tab: registered pool list, health/capacity/errors table, offsite
candidate flags, and scrub state table.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `create_pools_page()` | Build the Pools tab widget |
| `refresh_pools_page()` | Refresh pool table from `zpool list` |
| `refresh_scrub_table()` | Update scrub state table |
| `get_selected_pool_names()` | Return selected pool names |
| `_on_offsite_toggled()` | Toggle `offsite_candidate` flag |
| `_on_pools_drag_end()` | Persist pool reordering |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `feature_config` | Pool registry and scrub config |
| `scrub_manager` | Scrub queue and state parsing |
| `gui_helpers` | TreeView helpers |
| `logging_config` | `log_msg` |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| `pools` config object | [JSON config][ds-json] |
| Scrub state / `ScrubQueue` | [Scrub state][ds-scrub] |

---

### `schedule_page.py`

Schedule tab: list saved profiles, edit cron lines, preview next run times,
and enable/disable scheduled entries.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `create_schedule_page()` | Build the Schedule tab widget |
| `collect_schedule_config()` / `load_schedule_config()` | UI ↔ cron dict |
| `_regenerate_cron()` | Rewrite the cron drop-in file |
| `_refresh_profile_list()` | Show all profiles of the current tab type |
| `_on_selection_changed()` | Update the detail pane (cron entry + config summary) |
| `on_schedule_save()` / `on_schedule_revert()` / `on_schedule_delete()` | Persist/revert/delete |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `profile_manager` | Profile CRUD |
| `cron_manager` | Cron line generation/interpretation |
| `profile_dialogs` | Add/recall profile dialogs |
| `gui_helpers` | Widget helpers |
| `logging_config` | `log_msg` |

---

### `logs_page.py`

Logs tab: scan session log files, show metadata, tail running logs, filter by
message level, and display the success-rate summary.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `create_logs_page()` | Build the Logs tab widget |
| `_sync_log_list()` | Rescan `SESSION_LOG_DIR` and update the list |
| `_tail_log_file()` | Append new lines from a running log |
| `_load_log_into_viewer()` | Load selected log, tail-first if large |
| `_on_load_full_log_clicked()` | Switch from tail to full-file mode |
| `_on_prune_old()` | Delete logs older than retention |
| `_update_success_rate_label()` | Show recent success rate from history |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `log_index` | Persistent log metadata |
| `backup_history` | Success-rate calculation |
| `config_core` | Session log dir, retention settings |
| `logging_config` | Message levels and filtering |
| `gui_helpers` | Text-view search, popout window |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| Session log files / index | [Session log index][ds-log] |
| Backup history | [Backup history][ds-history] |

---

## Managers and helpers

### `path_utils.py`

Shared path-resolution helpers for the Python layer. Mirrors the Bash
`$mydir` / `find_zfsutility_script` / `remote_zfsutilities_bin` behavior so
the GTK GUI can locate sibling scripts, read the deployed version, resolve
the built docs path, and resolve remote SSH paths without hard-coding
installation locations.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `get_script_dir(depth=1)` | Return the caller's source-file directory |
| `find_script(name, script_dir=None)` | Search candidate directories for a sibling script |
| `resolve_local_bin(name, script_dir=None)` | Absolute path to a sibling executable, or `None` |
| `is_deployed_layout(script_dir=None)` | `True` if running inside a versioned deployment |
| `get_version(script_dir=None)` | Read the `VERSION` file for the current layout |
| `get_docs_path(script_dir=None)` | Path to built docs `index.html`, or `None` |
| `get_profile_runner_path(script_dir=None)` | Path to `profile_runner.py` for cron / Run Now |
| `resolve_remote_bin(host, timeout=15)` | Resolve remote active-version `bin/` over SSH |
| `resolve_remote_script(host, name)` | Remote path to a script, or just `name` on failure |
| `resolve_remote_version(host, timeout=15)` | Read remote `VERSION` file over SSH |

**Environment overrides:**

| Variable | Purpose |
| -------- | ------- |
| `ZFSUTILITIES_VERSION_BASE` | Base directory for versioned deployments (default `/usr/local/lib/zfsutilities`) |
| `ZFSUTILITIES_REMOTE_BIN` | Remote `bin/` path used by `resolve_remote_bin` |
| `ZFSUTILITIES_REMOTE_VERSION` | Remote `VERSION` path used by `resolve_remote_version` |

**Called modules / imported helpers:** none (stdlib only).

---

### `profile_manager.py`

CRUD for saved profile JSON files under the profiles directory.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `build_profile_name(user, tab, name)` | Construct `<user>-<tab>-<name>` |
| `create_profile(...)` | Save current tab settings as a profile |
| `load_profile(name)` / `save_profile(name, data)` / `delete_profile(name)` | Profile CRUD |
| `list_profiles()` | Return all profiles sorted by name |
| `profile_exists(name)` | Check for duplicate names |
| `validate_custom_name(name)` | Reject illegal characters |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `backup_config` | Profiles directory and `log_msg` |

---

### `profile_dialogs.py`

Simple GTK dialogs for adding a new profile and recalling an existing one.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `show_add_profile_dialog(...)` | Prompt for a profile name and save |
| `show_recall_profile_dialog(...)` | List profiles of a given tab type |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `profile_manager` | Profile CRUD |
| `gui_helpers` | Dialog helpers |
| `logging_config` | `log_msg` |

---

### `cron_manager.py`

Generates, interprets, and previews the cron drop-in file that schedules
profiles.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `write_cron_file(profiles)` | Regenerate the cron drop-in from scratch |
| `generate_cron_line(profile)` | Build one crontab line |
| `interpret_cron(expression)` | Human-readable description of a cron expression |
| `next_run_times(expression, count)` | Next `count` datetimes matching the expression |
| `format_next_runs(expression)` | Formatted next-run preview |
| `_parse_weekday(value)` | Parse weekday field with optional `#n`/`#L` ordinal suffix |
| `_match_weekday_ordinal(date, weekday, specs)` | Check whether `date` satisfies ordinal specs |
| `_format_ordinal_specs(specs)` | Human-readable phrase for ordinal specs |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `backup_config` | `log_msg` |

---

### `scrub_manager.py`

Scrub state parsing, queue management, and start/pause/resume/stop actions.

**Key classes:**

| Class | Purpose |
| ----- | ------- |
| `ScrubState` | Enum: `NONE`, `PENDING`, `SCANNING`, `PAUSED`, `FINISHED`, `CANCELED`, `UNKNOWN` |
| `ScrubInfo` | Dataclass with state, progress, remaining time, ETA, errors |
| `ScrubQueue` | Persistent pending/active/paused/finished pool sets with concurrency target |

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `parse_scrub_status(text)` | Parse `zpool status` output into `ScrubInfo` |
| `get_all_pool_scrub_states()` | Map every online pool to its `ScrubInfo` |
| `start_scrub()` / `pause_scrub()` / `resume_scrub()` / `stop_scrub()` | Scrub actions |
| `sync_system_scrub_for_pools()` | Enable/disable systemd weekly/monthly scrub timers |
| `load_scrub_state()` / `save_scrub_state()` | Persist queue state |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `zfs_repository` | Pool status and scrub commands |
| `file_locking` | `scrub_state_*` lock helpers |
| `zfs_lock_manager` | Per-pool scrub locks |
| `backup_config` | `log_msg` |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| Scrub state / `ScrubInfo` / `ScrubQueue` | [Scrub state][ds-scrub] |

---

### `pool_watch.py`

Independent per-pool watch window that auto-refreshes a dataset tree for a
single pool.

**Key class:**

| Class | Purpose |
| ----- | ------- |
| `PoolWatchWindow` | Standalone window with auto-refresh timer |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `gui_helpers` | Tree building helpers |
| `logging_config` | `log_msg` |

---

### `dataset_actions.py`

Action handlers for the Datasets tab: snapshot, delete, hold, rollback, browse,
and unmount snapshots.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `on_datasets_snapshot()` | Snapshot selected datasets |
| `on_datasets_delete()` | Delete selected datasets/snapshots/holds |
| `on_datasets_hold()` | Place holds on selected snapshots |
| `on_datasets_rollback()` | Rollback a dataset to a selected snapshot |
| `on_datasets_show_files()` / `on_datasets_browse_snapshot()` | Open file manager |
| `on_datasets_unmount_snapshot()` | Unmount a `.zfs/snapshot` mount |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `gui_helpers` | Dialogs, busy-process diagnosis |
| `datasets_page` | Refresh tree and button sensitivity |
| `command_builders` | `BashStep` for destructive operations |
| `zfs_lock_manager` | Pre-flight lock checks and direct locks |
| `logging_config` | `log_msg` |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| `BashStep` | [BashStep][ds-bashstep] |

---

### `pool_actions.py`

Action handlers for the Pools tab: watch, details, import/export, add/remove
registry entries, and scrub queue operations.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `on_pools_watch()` | Open `PoolWatchWindow` for selected pools |
| `on_pools_import()` / `on_pools_export()` | Import/export pools |
| `on_pools_add()` / `on_pools_remove()` | Modify the registered pool list |
| `on_pools_save()` / `on_pools_revert()` | Persist/revert pool registry |
| Scrub action handlers | start, pause, resume, stop |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `pools_page` | Refresh and selection helpers |
| `scrub_manager` | Scrub queue actions |
| `pool_watch` | Watch window |
| `gui_helpers` | Dialog helpers |
| `backup_config` | Save pools, `log_msg` |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| `pools` config object | [JSON config][ds-json] |
| Scrub state / `ScrubQueue` | [Scrub state][ds-scrub] |

---

### `retention_actions.py`

Action handlers for the Retention Policies tab: add/remove policies and
buckets, run prune, and dirty-state tracking.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `on_retention_add_policy()` / `on_retention_remove_policy()` | Manage per-pool policies |
| `on_retention_add_bucket()` / `on_retention_remove_bucket()` | Manage buckets |
| `on_retention_prune()` | Run `zfscleanup` for selected pools |
| `on_retention_mass_delete()` | Mass-delete snapshots across selected pools |
| `on_retention_save()` / `on_retention_revert()` | Persist/revert |
| `check_retention_dirty()` | Highlight unsaved changes |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `feature_config` | Retention getters/setters, defaults |
| `retention_page` | Page helpers and constants |
| `command_builders` | Build retention `BashStep` |
| `gui_helpers` | Button markup helpers |
| `zfs_lock_manager` | Pre-flight pool lock checks |
| `logging_config` | `log_msg` |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| `retention` config object | [JSON config][ds-json] |
| `BashStep` | [BashStep][ds-bashstep] |

---

### `snapshot_manager.py`

Secondary window for managing snapshots of a specific dataset.

**Key class:**

| Class | Purpose |
| ----- | ------- |
| `SnapshotManagerWindow` | Snapshot list, hold, delete, rollback for one dataset |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `gui_helpers` | TreeView helpers, busy diagnosis |
| `logging_config` | `log_msg` |

---

### `gui_helpers.py`

Reusable GTK helpers and utility functions used by nearly every page.

**Key classes:**

| Class | Purpose |
| ----- | ------- |
| `DirtyTracker` | Generic save/revert dirty-state tracker |
| `EditableListView` | Reusable ListStore with Add/Remove/Move |
| `TreeSearch` | Debounced search with prev/next for a `Gtk.TreeView` |
| `TextViewSearch` | Search/navigation for a `Gtk.TextView` |
| `LogPopoutWindow` | Independent window for popping out the info panel |
| `UIStateManager` | Debounced save/restore of window geometry |

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `build_full_dataset_name()` | Walk tree parents to build the full ZFS name |
| Tree loading helpers | Load pools, datasets, and snapshots on demand |
| `get_busy_processes()` / `diagnose_dataset_busy()` | Find and explain why a dataset is busy |
| `create_info_panel()` | Build the shared log/info panel |
| `create_menu_bar()` | Build the application menu bar |
| `confirm_and_minimize_width()` | Reset column widths and shrink window |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `logging_config` | `log_msg`, message levels, log sink |
| `zfs_repository` | Default repository, `DatasetRow` |
| `backup_config` | `log_msg` re-export (historical) |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| `ZfsRepository` dataclasses | [ZfsRepository dataclasses][ds-zfsrepo] |

---

### `log_index.py`

Persistent index of session-log metadata so the Logs tab does not re-read
every log file on refresh.

**Key class:**

| Class | Purpose |
| ----- | ------- |
| `LogIndex` | Load/save/update `/var/log/zfsutilities/sessions/.log_index.json` |

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `scan_file(path)` | Parse a log file and return a complete index entry |
| `update_entry_incrementally(entry, path)` | Update an entry with only newly appended bytes |
| `_status_from_trailer()` | Map trailer return code to Done/Failed/Cancelled |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `config_core` | `SESSION_LOG_DIR` |
| `logging_config` | Message-level parsing, `log_msg` |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| Session log index | [Session log index][ds-log] |

---

### `file_locking.py`

Advisory `flock` wrappers for the shared JSON and state files used by both
Python and bash code.

**Key functions / context managers:**

| Function | Purpose |
| -------- | ------- |
| `file_lock(path, lock_type, timeout=None)` | Acquire `LOCK_SH`/`LOCK_EX` on `path` |
| `config_lock_read()` / `config_lock_write()` | Lock the JSON config file |
| `history_lock_read()` / `history_lock_write()` | Lock the backup history file |
| `log_index_lock_read()` / `log_index_lock_write()` | Lock the session-log index |
| `scrub_state_lock_read()` / `scrub_state_lock_write()` | Lock the scrub queue state |

**Called modules / imported helpers:** none (stdlib only).

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| JSON config / history / log index / scrub state | [JSON config][ds-json], [Backup history][ds-history], [Session log index][ds-log], [Scrub state][ds-scrub] |

---

### `zfs_lock_manager.py`

Python client for the same advisory-lock scheme that `zfslockmanager` uses.
Python mutators use this module so they can interoperate with bash scripts
without conflicting on the same lock files.

**Key functions / context managers:**

| Function | Purpose |
| -------- | ------- |
| `check(dataset, lock_type)` | Return whether a lock can be acquired |
| `acquire(dataset, lock_type, description="")` | Acquire a lock and return a lock ID |
| `acquire_multiple(lock_type, datasets)` | Acquire several locks in deadlock-free order |
| `release(lock_id)` / `release_all()` | Release one lock or all locks held by this process |
| `lock(dataset, lock_type, description="")` | Context manager for a single lock |
| `locks(lock_type, datasets)` | Context manager for multiple locks |

**Called modules / imported helpers:** none (stdlib only).

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| Lock files | [Lock files](../developer-guide/data-structures.md#lock-files) |

---

### `logging_config.py`

Priority-based logging, session-log management, and GUI sink routing.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `log_msg(*args)` | Log with `file:line:` prefix, GUI sink, and session log |
| `set_log_sink()` / `get_log_sink()` | Route messages to the GUI info panel |
| `set_session_log()` / `restore_session_log()` | Manage `ZFSUTILITIES_LOG_FILE` env |
| `truncate_session_log()` | Enforce the 1 GB cap with tail retention |
| `session_log_context()` | Context manager for session log env |
| `parse_msg_level()` / `viewer_should_show()` | Message-level parsing and filtering |

**Called modules / imported helpers:** none.

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| Session log files | [Session log index][ds-log] |

---

## Entry points

### `main.py`

Application entry point and single-instance guard.

**Key class:**

| Class | Purpose |
| ----- | ------- |
| `ZFSUtilitiesApp` | GTK `Gtk.Application` subclass |

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `_pid_file_status()` | Detect stale PID files |
| `_terminate_with_wait()` | Gracefully replace a stuck instance |
| `_show_wait_dialog()` / `_pump_events_for()` | Transient wait dialog during instance replacement |
| `main()` | Entry point |

**Internal flow:**

1. Parse arguments.
2. Check the PID file; if another instance is running and healthy, raise it.
3. If the instance is stuck, show a wait dialog and terminate it.
4. Launch `ZFSUtilitiesWindow` from `zfsutilities_gui.py`.

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `logging_config` | `log_msg` |

---

### `zfsutilities_gui.py`

Main application window. Builds the sidebar, stack of pages, action panel,
info panel, dry-run toggle, and startup checks.

**Key class:**

| Class | Purpose |
| ----- | ------- |
| `ZFSUtilitiesWindow` | Main GTK window |

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `_detect_parent_dir()` | Find the directory containing the bash scripts |
| `create_sidebar_and_stack()` | Build the left sidebar and page stack |
| `update_action_buttons()` | Show the action buttons for the current page |
| `log_message()` / `_update_progress()` | Feed the info panel |
| `_check_peer_version_async()` | Two-node peer version comparison |

**Internal flow:**

1. Build an `AppContext` with config, directories, version, and repository.
2. Create each page and add it to the stack.
3. Connect the action panel to `action_dispatch.PAGE_SPECS` and
   `ACTION_HANDLERS`.
4. Start dashboard and scrub refresh timers.
5. On startup, compare versions with the peer node in a background thread.

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `app_context` | `AppContext` |
| `action_dispatch` | Page/action dispatch tables |
| `backup_runner` / `runner_factory` | Run GUI-initiated operations |
| `config_core` / `feature_config` / `logging_config` | Config and logging setup |
| All page modules | Build each tab |
| `docs_viewer` | Standalone documentation window |
| `gui_helpers` | Menu bar, info panel, UI state |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| `AppContext` | [AppContext][ds-appctx] |
| JSON config | [JSON config][ds-json] |

---

### `docs_viewer.py`

Standalone documentation viewer. Serves the built MkDocs site from a local
HTTP server and renders it in a WebKit window.

**Key classes:**

| Class | Purpose |
| ----- | ------- |
| `_DocsServer` | Tiny static-file server for the built docs |
| `DocsViewerWindow` | WebKit window with zoom, navigation, and state persistence |

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `resolve_docs_path()` | Locate `06 Docs/site/index.html` or deployed equivalent |
| `main()` | Launch the viewer |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `config_core` / `backup_config` | UI state, docs editor, `log_msg` |

---

### `legacy_retention.py`

One-time parser for legacy `zfsretainpol-<pool>` bash files.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `_parse_legacy_retention_file(path)` | Parse a single legacy retention file |
| `scan_legacy_retention(parent_dir, retention_dict)` | Add missing pools from legacy files |

**Called modules / imported helpers:** none.

**See also:**

- [`feature_config.import_legacy_retention()`](#feature_configpy) — the GUI hook
  that calls this scanner.
- Retention policy arrays in
  [Retention policy arrays][ds-retention].

[ds-json]: ../developer-guide/data-structures.md#json-config-rootconfigzfsutilitiesjson
[ds-log]: ../developer-guide/data-structures.md#session-log-index-varlogzfsutilitiessessionslog_indexjson
[ds-history]: ../developer-guide/data-structures.md#backup-history-rootconfigzfsutilities-historyjson
[ds-bashstep]: ../developer-guide/data-structures.md#bashstep-command_builderspy
[ds-appctx]: ../developer-guide/data-structures.md#appcontext-app_contextpy
[ds-zfsrepo]: ../developer-guide/data-structures.md#zfsrepository-dataclasses-zfs_repositorypy
[ds-scrub]: ../developer-guide/data-structures.md#scrub-state-scrub_managerpy
[ds-snapfile]: ../developer-guide/data-structures.md#snapshot-name-persistence
[ds-fss]: ../developer-guide/data-structures.md#fss-table-in-memory-rows-from-zfscheckagainst-json
[ds-node]: ../developer-guide/data-structures.md#node-configuration-file-etczfsutilities-nodeconf
[ds-backup]: ../developer-guide/data-structures.md#backup-object
[ds-config-migrations]: ../developer-guide/data-structures.md#config-migrations
[ds-retention]: ../developer-guide/data-structures.md#retention-policy-arrays-bktname-bktretain-minage

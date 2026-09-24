# Python Modules Reference

These modules make up the GTK GUI and command-orchestration layer of ZFS
Utilities. They read and write the shared JSON config, build `bash` commands,
run them through `subprocess`, and present the results in the GTK interface.

Most modules are in `python/`. They are grouped below by role:

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
| JSON config (`/var/lib/zfsutilities/config.json`) | [JSON config][ds-json] |
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
| `get_checkagainst()` / `save_checkagainst()` | Nested checkagainst object (derived + user entries) |
| `derive_checkagainst_entries()` | Build forward/reverse rows from active Backup/Offsite steps |
| `merge_checkagainst_entries()` | Merge derived and user entries for `zfsconfig_get_checkagainst` |
| `add_checkagainst_entry()` | Append a row to `user_entries` if not already present |
| `get_retention()` / `save_retention()` | Per-pool retention policies |
| `get_workload_profiles()` / `save_workload_profiles()` | Workload profile config |
| `delete_workload_profile()` / `reset_workload_profiles()` | Remove/reset workload profiles |
| `get_archive_path()` / `save_archive_path()` | Offsite archive path |
| `get_prune_label()` / `save_prune_label()` | Global retention prune label |
| `get_prune_pools_order()` / `save_prune_pools_order()` | Retention Prune pool order |
| `get_retention_mass_delete_config()` / `save_retention_mass_delete_config()` | Retention tab Advanced Prune Options card settings |
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
| JSON config feature sections | [backup/offsite/restore/pools/retention/checkagainst/scrub/workload_profiles][ds-json] |
| Snapshot name persistence and one-minute reservation | [Snapshot name persistence][ds-snapfile] |

---

### `workload_profiles.py`

Pure-logic workload profile helpers used by the Datasets tab Apply Profile workflow.
Contains no GTK code and no direct subprocess calls; all ZFS I/O is delegated to
``ZfsRepository`` callers.

**Key constants:**

| Constant | Purpose |
| -------- | ------- |
| `LIVE_PROPERTIES` | Properties that can be changed with `zfs set` |
| `CREATION_ONLY_PROPERTIES` | Properties fixed at dataset creation (`volblocksize`, `ashift`) |
| `ALL_KNOWN_PROPERTIES` | Union of the two groups |

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `properties_for_profile(profile, ds_type)` | Return the profile properties that apply to the dataset type |
| `match_profile(profiles, ds_type, live_props)` | Find the first profile whose live properties match the dataset |
| `build_apply_plan(profile, dataset, ds_type, live_props)` | Build a preview plan of property changes |
| `build_zfs_set_commands(plan)` | Emit the `zfs set` commands for plan entries that will apply |
| `zfs_set_commands_with_entries(plan)` | Like `build_zfs_set_commands`, but pairs each command with its plan entry so callers can describe steps without re-parsing the command string |
| `profile_has_warning(name, profile, pool_has_special)` | Whether the profile selection should show a warning |
| `warning_text(name, profile, pool_has_special)` | Warning text, or `None` if no warning applies |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `feature_config` | Seed profile definitions |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| Workload profile objects | [workload_profiles][ds-workload] |

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

### `paths.py`

Centralized path resolution for the Python layer. Mirrors the FHS-aligned
layout defined in `lib/paths.sh` and provides legacy-path helpers for migration
code.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `get_system_config_dir()` | System/admin configuration directory |
| `get_config_dir()` | Runtime configuration directory |
| `get_state_dir()` | Persistent runtime-state directory |
| `get_log_dir()` | Log directory |
| `get_run_dir()` | Transient runtime-state directory |
| `get_lock_dir()` | Advisory-lock directory |
| `get_zvol_mount_dir()` | Base directory for mounting zvol loop partitions (default `/mnt/zfsutilities`) |
| `get_config_path()` | Main JSON config file path |
| `get_profiles_dir()` | Profile directory (created on demand) |
| `get_history_path()` | Backup-history JSON file path |
| `get_scrub_state_path()` | Scrub-manager state file path |
| `get_snapfile_path(label)` | Saved next-snapshot file path |
| `get_offsite_snapfile_path()` | Saved offsite next-snapshot file path |
| `get_run_snapfile_prefix()` | Transient next-snapshot file prefix |
| `get_pid_file_path()` | GUI PID file path |
| `get_session_log_dir()` | Per-session log directory |
| `get_log_index_path()` | Session-log index file path |
| `get_cron_file_path()` | Cron drop-in file path |
| `get_profile_lock_dir()` | Per-profile advisory-lock directory |
| `get_legacy_*()` | Legacy `/root/.config/` path helpers |
| `get_legacy_system_config_paths()` | Mapping of new system-config paths to legacy paths |

**Called modules / imported helpers:** none.

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| All paths listed above | [Path layout](../index.md#path-layout-and-migration) |

---

### `migration.py`

One-time migration of ZFS Utilities state files to the FHS-aligned layout. The
migration is automatic, idempotent, and rollback-compatible: after moving a file
or directory from its legacy location, a symlink is left at the old path so
older deployed versions can still find their data.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `run_migration()` | Run the one-time migration if it has not already run |
| `migrate_state_files()` | Migrate Python-layer state files and directories |
| `migrate_system_config_files()` | Migrate system administrator config files |
| `_migrate_item(new_path, old_path, create_symlink)` | Move one item and leave a rollback symlink |
| `get_migration_sentinel_path()` | Path to the migration sentinel file |

**Called modules / imported helpers:**

| Module | Purpose |
| ------ | ------- |
| `paths` | New and legacy path resolution |
| `logging_config` | `log_msg` for warnings and status |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| Migration sentinel (`${STATE_DIR}/.migration_complete`) | [Path layout](../index.md#path-layout-and-migration) |
| State/config files under `/var/lib/zfsutilities/` and `/etc/zfsutilities/` | [JSON config][ds-json], [Session log index][ds-log], [Snapshot name persistence][ds-snapfile] |

---

## ZFS repository and info

### `zfs_repository.py`

Isolates all direct `zfs`/`zpool` subprocess calls. The repository returns
typed dataclasses instead of raw tab-separated strings, which makes the GUI
and tests easy to mock.

**Key classes:**

| Class | Purpose |
| ----- | ------- |
| `PoolRow` | One row from `zpool list -H -o name,health,size,alloc,free,cap,ckpoint` |
| `DatasetRow` | One row from `zfs list -H -o name,creation,type,used,avail,refer,origin,clones,mounted` |
| `SnapshotRow` | One row from `zfs list -t snapshot -H -o ...` |
| `HoldRow` | One row from `zfs holds -H <snapshot>` |
| `LoopPartition` | One mountable entry on a loop device backing a zvol (partition or bare device, with/without filesystem) |
| `ZfsRepository` | Wraps all `zfs`/`zpool` subprocess commands |

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `get_default_repository()` | Returns a module-level default `ZfsRepository` instance |
| `is_dataset_encrypted(path)` | Return `True` if *path* resides on an encrypted ZFS dataset |
| `zvol_device_path(dataset)` | Return the `/dev/zvol/…` block-device path for a ZFS volume |
| `get_property(dataset, prop)` | Value of a single ZFS property |
| `get_properties(dataset, props)` | Values for a list of ZFS properties; missing properties return `"-"` |
| `get_all_properties(dataset)` | All ZFS properties for *dataset* |
| `set_property(dataset, prop, value)` | Set a ZFS property; returns success/failure |
| `loop_attach(zvol_dev)` | Attach a zvol device to a new read-only, partition-scanned loop device (`losetup --find --show --partscan --read-only`); returns the `/dev/loopN` path |
| `loop_find(zvol_dev)` | Return the loop device currently attached to a zvol device, or `None` |
| `loop_detach(loop_dev)` | Detach a loop device (`losetup -d`); returns success/failure |
| `loop_partitions(loop_dev)` | Parse `lsblk --json` into `LoopPartition` entries (partitions, or the bare device when there is no partition table) |
| `device_mountpoint(device)` | Return the mountpoint a block device is mounted at, or `None` (`findmnt`) |
| `build_create_pool_command()` | Pure `zpool create` argv builder (by-id paths, topology minimums) |
| `build_add_vdev_command()` | Pure `zpool add` argv builder for data and special/log/cache vdevs |
| `build_attach_command()` | Pure `zpool attach` argv builder (mirror grow / RAIDZ expansion) |
| `build_replace_command()` | Pure `zpool replace` argv builder |
| `build_detach_command()` | Pure `zpool detach` argv builder |
| `build_recursive_snapshot_command()` | Pure `zfs snapshot -r` argv builder for migration snapshots |
| `build_migration_send_receive_command()` | Pure `bash -c` argv sourcing `zfs-migrate-send` for a resumable, pv-instrumented migration copy (optional `rate_limit` for `pv -L`) |
| `build_pool_export_command()` | Pure `zpool export` argv builder |
| `build_pool_import_rename_command()` | Pure `zpool import <temp> <name>` argv builder (cutover rename) |
| `build_pool_destroy_command()` | Pure `zpool destroy` argv builder (holding-mode migration only) |
| `build_destroy_dataset_command()` | Pure `zfs destroy -r` argv builder for dropping migration copies |

**Called modules / imported helpers:** none (uses `subprocess` directly).

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| `ZfsRepository` dataclasses | [ZfsRepository dataclasses][ds-zfsrepo] |

---

### `disk_repository.py`

Isolates non-ZFS block-device commands used by the Disks tab: `lsblk`,
`/dev/disk/by-id` resolution, and `smartctl`. Methods return typed dataclasses
and degrade gracefully when `smartctl` is missing or a device does not support
SMART.

**Key classes:**

| Class | Purpose |
| ----- | ------- |
| `DiskInfo` | One physical disk from `lsblk --json` |
| `DiskInventory` | Full inventory plus a path -> `DiskInfo` index |
| `DiskRepository` | Wraps `lsblk`, `find`, and `smartctl` subprocess calls |

**Key methods:**

| Method | Purpose |
| ------ | ------- |
| `list_disks()` | Return disks and their partitions, excluding loops, zvols, and the system boot disk (plus its partitions) |
| `resolve_by_id()` | Map kernel device paths to the best `/dev/disk/by-id` name |
| `smart_health(path)` | Return `PASSED`, `FAILED`, or `n/a` for a device |
| `smart_wear(path)` | Return SSD/NVMe wear percentage (0-100) from `smartctl -j -A` JSON, or `None` |
| `smart_details(path)` | Return raw `smartctl -a` text or `n/a` |
| `disk_inventory()` | Combine the above into a single inventory object; SSD/NVMe disks get one combined `smartctl -j -H -A` probe yielding both health and `DiskInfo.wear_percent`, HDDs keep the quick `-H` check |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `backup_config` | `log_msg` for warnings |

---

### `zfs_capabilities.py`

Runtime OpenZFS release-variation layer. Parses both userland and kernel-module
versions from `zfs version`, gates features on the kernel-module version, and
warns when the two differ.

**Key classes:**

| Class | Purpose |
| ----- | ------- |
| `ZfsVersion` | Parsed `(major, minor, patch)` tuples for userland and kmod |
| `ZfsCapabilities` | `supports(name)`, `requires(name)`, and `supports_pool_feature(pool, feature)` pool-feature cross-checks (whitespace-column parsing of `zpool get all` output) |

**Key constants:**

| Constant | Purpose |
| -------- | ------- |
| `FEATURE_MIN_VERSION` | Mapping of feature name to minimum `(major, minor, patch)`; patch matters for `zfs_rewrite` (2.3.4, not 2.3.0) |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `backup_config` | `log_msg` for warnings |
| `zfs_repository` | `ZfsRepository.version_output()` and `pool_get_all()` |

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

### `pool_create.py`

Pure logic for the Disks-page create-pool wizard (see
`pool_create_wizard.py` for the GTK half): disk eligibility and partition
policy, topology validation, pool-name validation, ashift suggestion, and the
RAIDZ capacity estimator. No GTK and no direct subprocess calls — ZFS I/O is
delegated to `zfs_repository` via the app context, and the actual `zpool
create` argv is built by `zfs_repository.build_create_pool_command()`.

**Key classes / constants:**

| Name | Purpose |
| ---- | ------- |
| `TopologySpec` | One selectable topology (stripe, mirror, raidz1-3, draid, raid10): minimum disks, vdev-width rules |
| `TOPOLOGIES` | Registry of selectable topology names to `TopologySpec` |
| `EligibilityResult` | Why a disk or partition is usable or not (in-use pool match, partition policy) |
| `CapacityEstimate` | Raw vs effective capacity result of `estimate_effective_capacity()` |
| `MAX_POOL_NAME_LEN` | Pool-name length limit (temp migration names append a suffix under it) |
| `SOLID_STATE_TYPES` | Disk rotational types that get the SSD/NVMe ashift suggestion |

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `disk_eligibility()` | Decide whether a disk/partition may be used for a new pool (in-use, boot-disk, alias matching) |
| `_apply_partition_policy()` | Whole-disk vs partition usage rules for the selected disks |
| `validate_vdev_selection()` | Topology-specific vdev composition checks (widths, mirrors, mixed sizes) |
| `validate_raid10_count()` | RAID10 requires an even disk count of at least four |
| `validate_pool_name()` | Name syntax, reserved words, length, and collision checks |
| `recommend_ashift()` | Recommended pool blocksize (ashift): defaults to 12 (4096 bytes); prior-pool label or reported-sector evidence can only raise it, never lower it |
| `estimate_effective_capacity()` | Effective capacity estimator for redundancy layouts |
| `pool_filesystem_options()` | `-O` filesystem properties from a workload profile for the pool root |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `disk_repository` | `DiskInfo` |
| `workload_profiles` | `LIVE_PROPERTIES`, `properties_for_profile` |

---

### `pool_growth.py`

Pure policy logic for the Disks-page pool-growth operations (Phase 4): attach,
replace, detach, and infrastructure-vdev additions. No GTK and no direct
subprocess calls — the only function that reads live ZFS state,
`scrub_blocks_pool_op`, takes the repository as a parameter (mirroring how
`pool_create.py` is pure logic). Complements the pure argv builders in
`zfs_repository` (`build_add_vdev_command`, `build_attach_command`,
`build_replace_command`, `build_detach_command`), which enforce by-id paths and
topology minimums.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `classify_attach_target()` | Classify a topology-tree selection: stripe-to-mirror, mirror grow, or RAIDZ expansion |
| `classify_replace_source()` | Classify a topology-tree selection as a replaceable disk member |
| `assess_detach()` | Mirror-leaf-only detach assessment with redundancy/irreversibility warnings |
| `validate_replace_pair()` | Replace validation; flags a smaller-than-source replacement |
| `validate_infra_vdev()` | special/log/cache rules: special must be a mirror, cache cannot be |
| `scrub_blocks_pool_op()` | Refuse a pool operation while the pool's scrub is SCANNING or PAUSED |
| `resolve_member_by_id()` | Map a `zpool status -P` leaf path to its `/dev/disk/by-id` form |
| `mixed_size_warning()` | Warn when vdev members differ in size |
| `infra_vdev_notes()` | Tailored explainer lines per infrastructure vdev kind |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `pool_create` | `TOPOLOGIES`, `validate_vdev_selection` (eligibility reuse) |
| `scrub_manager` | Pool scrub state reads |
| `zfs_repository` | `TopologyNode` |
| `disk_repository` | `DiskInfo` |
| `backup_config` | `log_msg` |

---

### `pool_migrate.py`

Pure-logic helpers for copy-based pool migration (the Disks-page Migrate Pool
wizard's logic half). No GTK and no direct subprocess calls; command
construction is delegated to the migration argv builders in
`zfs_repository`. Migration exists because ZFS cannot change a vdev's
redundancy class in place (stripe to raidz, mirror to raidz, width or ashift
changes): snapshot the source pool, replicate every top-level dataset to a
destination (a new pool on new disks, or an existing holding pool with enough
free space), verify the copy, then cut over by exporting the source pool and
re-importing the migrated pool under the source pool's name so every
`pool/dataset` path is preserved.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `migration_snapshot_name()` | Bucket-less `@migrate-<timestamp>` name (retention never prunes it) |
| `migration_snapshot_bare_name()` | Strip the leading `@` for the zfs argv builders |
| `generate_temp_pool_name()` | Valid unused temporary pool name (`<source>_mig`, `_mig2`, …) |
| `holding_migration_namespace()` | Reserved holding-pool dataset namespace (`migrate_<source>`) so holding copies can never collide with backup/offsite paths |
| `plan_migration_steps()` | Ordered `MigrationStep` plan for new-disks or holding-pool mode |
| `check_destination_capacity()` | Refuse/warn when destination free space is short of source allocated |
| `verify_trees_match()` | Per-dataset `used`-bytes comparison between source and migrated trees |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `pool_create` | `validate_pool_name`, `MAX_POOL_NAME_LEN` (temp-name generation) |

---

### `pool_migrate_dialogs.py`

GTK dialog and Disks-page execution handler for Migrate Pool, the copy-based
pool-expansion path (see `pool_migrate.py`). The dialog collects the source
pool and destination mode (new disks + topology, or an existing holding
pool), shows the full step plan, and gates the run behind typed confirmation
of the source pool name. Execution is two runner phases: the copy phase
(recursive migration snapshot, one resumable `zfs-migrate-send` step —
`zfs send -Rw` received with `zfs receive -u -F -s -v`, with `pv` in the
pipeline and an optional bandwidth limit — per top-level dataset, then
per-dataset tree verification) and the cutover
phase, which starts only after a second typed confirmation — export the
source pool, then re-import the migrated pool under the source pool's name
(new disks) or destroy/rebuild/copy-back/swap (holding pool). Holding-mode
copies land under `<holding>/migrate_<source>/<dataset>` and the cutover
removes that namespace with a single destroy. Before anything starts, the
handler re-reads the source pool's dataset layout and aborts with an
explanation when it changed after the review. The pool
hosting the root filesystem is never offered; both phases hold a `zlm`
write lock on the source pool and run in the session log.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `show_migrate_pool_dialog()` | Run the dialog; returns a `MigrationRequest` or None |
| `build_request()` | Build the execution request from a validated dialog state |
| `build_migration_steps()` | Build the (copy, cutover) `BashStep` lists for a request |
| `_source_layout_changed()` | Compare the request's dataset list against a fresh pool listing; abort reason when stale |
| `on_disks_migrate_pool()` | Disks-page action: gates, data gathering, two-phase runner execution |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `pool_migrate` | Step planning, capacity checks, snapshot/temp-name generation |
| `pool_growth_dialogs` | Shared disk picker and typed-entry handlers |
| `zfs_repository` | Migration argv builders |
| `zfs_lock_manager` | Source-pool write lock across both phases |

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
| `build_rsync_command(source, dest, remote_log_path=None)` | Build an rsync pull/push command |
| `build_send_receive_command(...)` | Build the `bash` command for a ZFS send/receive step |
| `build_pre_backup_command(cmd)` / `build_post_backup_command(cmd)` | Wrap user pre/post commands |
| `build_retention_command(...)` | Build the `zfscleanup` invocation (accepts the dataset selection criteria forwarded to `zfsbuildfsarray`) |
| `build_backup_prune_command(...)` | Build a non-fatal prune `BashStep` that prunes only the datasets the backup's active send/receive steps back up (destination names re-derived at prune time via `zfscleanup`'s explicit `prune_datasets` mode) |

**Called modules / imported helpers:** none (stdlib only).

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| `BashStep` | [BashStep][ds-bashstep] |

---

### `session_log.py`

Low-level, stateless helpers for per-run session log files. Used by both the
GUI runner (`backup_runner.py`) and the headless profile runner
(`profile_runner.py`) so both paths create, append, and truncate logs the same
way.

**Key functions:**

| Function | Purpose |
| -------- | --------- |
| `create_session_log_file(tab_type, name=None)` | Create a timestamped log file under `SESSION_LOG_DIR` |
| `write_raw_line(session_log_file, line)` | Append a raw subprocess line with a timestamp |
| `write_session_trailer(...)` | Write the `# END` trailer and update the log index |
| `maybe_truncate_session_log(...)` | Enforce the configured session-log size cap |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `config_core` | `SESSION_LOG_DIR` |
| `log_index` | `LogIndex` for cached log metadata |
| `logging_config` | `log_msg`, `truncate_session_log` |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| Session log files | [Session log index][ds-log] |
| Session log index | [Session log index][ds-log] |

---

### `backup_runner.py`

Runs a list of `BashStep` objects asynchronously. Manages the session log,
progress parsing, cancellation, and final history/log-index entries.

**Key class:**

| Class | Purpose |
| ----- | ------- |
| `BackupRunner` | Async runner for GUI-initiated backup/offsite/restore operations |

**Internal flow:**

1. `prepare_session_log()` uses `session_log.create_session_log_file()` to
   create a timestamped log under `SESSION_LOG_DIR`.
2. `start()` spawns each step in a PTY so output can be streamed.
3. `_on_stdout()` / `_on_stderr()` parse `pv`/`zfs receive` progress and
   append raw lines to the log via `session_log.write_raw_line()`.
4. `_write_session_trailer()` uses `session_log.write_session_trailer()` to
   write the `# END` trailer and update the log index.
5. `_maybe_truncate_session_log()` uses `session_log.maybe_truncate_session_log()`
   to enforce the configured size cap.

**Completion contract:** the `on_complete` callback passed to `start()` is
invoked as `on_complete(cancelled=False, rc=<result code>)` when the run ends
on its own — `rc` is `0` on success, non-zero when a fatal step failed or the
runner aborted unexpectedly. Cancel/abort paths invoke it as
`on_complete(cancelled=True)` (`rc` defaults to `None`). `_finish()` logs
`INFO: <label> complete` only when `rc == 0` and `WARN: <label> failed (rc=N)`
otherwise, so completion messages in the log always reflect the real result.

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `session_log` | Create, append, truncate, and finalize session logs |
| `logging_config` | Session log context, `log_msg` |
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
| `acquire_profile_lock(profile_name, timeout=1.0, log_file=None)` | Acquire the profile lock; wait for an existing run and suppress duplicates on timeout |
| `release_profile_lock(fd, lock_path)` | Release the profile lock |
| `main()` | CLI entry point for cron execution |

**Internal flow:**

1. Load the requested profile from disk to determine its tab type.
2. Create a session log with `session_log.create_session_log_file()` so that
   lock-skip messages and early errors are recorded.
3. Acquire a per-profile advisory lock so a duplicate cron invocation waits
   for the running instance (by default up to 10 minutes) and then exits
   cleanly instead of running the profile twice.
4. If the profile's cron weekday field contains an ordinal expression
   (`#1`–`#5` or `#L`), verify today matches it; otherwise skip the run.
5. Generate snapshot names and build `BashStep` lists using the same helpers
   as the GUI pages.
6. Run each step, write the trailer, and append a history entry.

Failed rsync steps log the raw exit code and a human-readable diagnosis
(for example, `rc=24` is reported as "Source files vanished during transfer")
so cron logs and session logs explain the failure without looking up rsync
exit codes manually.

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `command_builders` | Build rsync, send/receive, retention, pre/post `BashStep`s |
| `offsite_runner` | Detect offsite pool and build offsite steps |
| `restore_runner` | Compute restore params |
| `profile_manager` | Load profile JSON |
| `scrub_manager` | Scrub queue operations |
| `config_core` | `load_config`, session log directory |
| `feature_config` | Snapshot naming, pool names, snapfile removal, scrub state |
| `session_log` | Create, append, truncate, and finalize session logs |
| `logging_config` | Session log context, `log_msg` |
| `log_index` | Update log index entries |
| `backup_history` | Append history entries |
| `zfs_repository` | `is_dataset_encrypted` for ZFS keys destination checks |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| `BashStep` | [BashStep][ds-bashstep] |
| JSON config | [JSON config][ds-json] |
| Session log files / index | [Session log index][ds-log] |
| Backup history | [Backup history][ds-history] |
| Scrub state / `ScrubQueue` | [Scrub state][ds-scrub] |

---

### `profile_validation.py`

Scope-alignment validation for backup and offsite jobs.  Detects when backup
and offsite profiles send overlapping datasets to the same destination but
snap different subsets, which would force the daily backup to roll back
`@offsite` snapshots on the destination.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `validate_gui_settings(backup_cfg, offsite_cfg)` | Validate the current GUI Backup and Offsite tab settings |
| `validate_profiles(profiles)` | Validate a list of saved profiles |
| `validate_effective_steps(items)` | Validate a normalized list of backup/offsite send/receive steps |

**Called modules / imported helpers:** none (stdlib only: `fnmatch`, `shlex`).

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| Backup/offsite config dicts | [JSON config][ds-json] |
| Profile dicts | [Profiles][ds-profiles] |

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
| `load_history()` / `save_history()` | Read/write `/var/lib/zfsutilities/history.json` |
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

### `disk_actions.py`

Action handlers for the **Disks** tab. Kept separate from `disks_page.py` so
page layout and action logic can be tested independently.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `on_disks_smart_details(app)` | Dump `smartctl -a` for the selected disk to the GUI log |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `disks_page` | Column constants and selected-disk lookup |
| `logging_config` | `log_msg` |

---

### `disk_surface_test.py`

Disk surface tester for HDDs. A surface test is a SMART self-test run by the
drive firmware (`smartctl -t short|long`), so it runs independently of the
GUI, survives restarts, and supports concurrent tests on different disks.
Holds the state machine, the JSON state file (`surface_test_state.json`,
flock-protected like scrub state), Disk Inventory cell-text formatting, and
the start/cancel dialog.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `load_surface_test_state()` / `save_surface_test_state()` | Flock-protected persistence of per-disk test entries |
| `build_entry()` / `update_entry_from_poll()` / `update_entries_from_polls()` | State machine: running → passed/failed/aborted, with progress and ETA |
| `surface_cell_text()` / `format_minutes()` | Disk Inventory cell rendering (`42% (1h 23m)`, `Passed`, …) |
| `start_surface_test()` / `cancel_surface_test()` | Start (`smartctl -t`) / cancel (`smartctl -X`) plus state updates |
| `show_surface_test_dialog()` | Fast/Slow picker, or live status + Cancel Test when already running |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `disk_repository` | `classify_selftest_status` and the `smartctl` subprocess wrappers |
| `file_locking` | Surface-state read/write locks |
| `paths` | State-file path |

The smartctl wrappers (`start_self_test`, `abort_self_test`,
`estimate_test_minutes`, `poll_self_test`) live on `DiskRepository` next to
the other smartctl methods; the text parsers (`_parse_selftest_progress`,
`_parse_test_minutes`, `_parse_selftest_status`) are module-level pure
functions in `disk_repository.py`.

---

### `disks_page.py`

The **Disks** tab UI: a radio-button view switcher (Inventory and Topology,
Performance) over a `Gtk.Stack`, holding the disk inventory TreeView, pool
selector, vdev topology TreeView, and a placeholder Performance view. Slow
block-device and ZFS calls are cached in a background loader following the
`ImportablePoolCache` pattern.

**Key classes:**

| Class | Purpose |
| ----- | ------- |
| `DiskInventoryData` | Snapshot returned by the cache |
| `DiskInventoryCache` | Async TTL cache for inventory + topology |

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `create_disks_page(app)` | Build and return the Disks tab widget |
| `_on_view_radio_toggled(radio, view_name, app)` | Switch the visible view in response to the view-switcher radio row |
| `refresh_disks_page(app)` | Repopulate disk inventory and topology stores |
| `on_disks_refresh(app)` | Invalidate cache and refresh the page |
| `update_disks_button_sensitivity(app)` | Enable/disable action buttons based on the active view and selection |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `disk_repository` | `DiskRepository`, `DiskInfo` |
| `zfs_repository` | `ZfsRepository`, `TopologyNode` |
| `gui_helpers` | `bold_label`, `configure_treeview_column`, `setup_row_scroll` |
| `logging_config` | `log_msg` |

---

### `profile_dialogs.py`

Workload-profile dialogs and execution, shared by page actions that operate
on a caller-supplied dataset list: the Apply Profile picker/preview, the
profile manager and editor, and Rewrite Data (`zfs rewrite -P`). Selection
collection and page refresh live with the calling page (the Datasets tab);
pool topology facts the dialog needs are passed in. Execution acquires one
`zlm` write lock per dataset and runs `zfs set` / `zfs rewrite` BashSteps
under the dataset runner.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `show_apply_profile_dialog(app, datasets, pool_has_special)` | Preview and confirm applying a workload profile to a dataset list |
| `on_apply_profile(app, datasets, profile, refresh)` | Run the `zfs set` steps for the chosen profile (requires the dialog to have been confirmed) |
| `show_manage_profiles_dialog(app)` / `show_profile_editor_dialog(app, name)` | Workload profile manager and add/edit dialog |
| `on_rewrite_data(app, datasets, refresh)` | Run `zfs rewrite -P -r -x -v` on filesystem datasets, one write lock each |
| `_build_rewrite_command(ds_name, mountpoint)` | Bash script for one rewrite: mount-if-needed, rewrite, restore prior mount state |
| `_topology_has_special_vdev(topology)` | Whether a pool topology tree contains a special vdev |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `feature_config` | Workload profile getters/setters |
| `workload_profiles` | Profile matching, apply plan, and command builders |
| `zfs_lock_manager` | Advisory locks for dataset actions |
| `gui_helpers` | `create_dialog`, `configure_treeview_column` |

---

### `pool_growth_dialogs.py`

GTK dialogs and Disks-page execution handlers for the five Phase 4 pool-growth
operations: Add Data Vdev, Expand Vdev, Replace, Detach, and Add Infrastructure
Vdev. All dialogs share the `_ReviewScaffold` (exact-command preview, tailored
warnings, and a confirmation step matched to the danger: typed pool-name
confirmation, an acknowledgment checkbox, or a YES/NO question). Every
operation refuses to run while the pool's scrub is SCANNING or PAUSED, executes
as one session-logged `BashStep` through the Dataset action runner, and holds a
pool-scope `zlm` write lock until completion. Decision logic stays in pure,
unit-tested helpers; capability gating uses `ctx.zfs_caps` exclusively.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `show_add_vdev_dialog()` | Add-Data-Vdev dialog: pool selector, disk picker, topology choice, typed confirmation |
| `show_attach_dialog()` | Attach dialog: topology-tree target, per-kind warnings, RAIDZ-expansion gating |
| `show_replace_dialog()` | Replace dialog: source member, eligible replacement, smaller-disk warning |
| `show_detach_dialog()` | Detach dialog: mirror-leaf-only target tree, typed confirmation |
| `show_add_infra_vdev_dialog()` | Infra-vdev dialog: special/log/cache kind selector with per-kind confirmation |
| `on_disks_add_vdev()` / `on_disks_attach_device()` / `on_disks_replace_device()` / `on_disks_detach_device()` / `on_disks_add_infra_vdev()` | Disks-page action handlers: guards, dialog, pool-scope lock, one fatal `BashStep`, refresh |
| `_ReviewScaffold` | Shared review area: command preview, warnings, typed entry, acknowledgment checkbox |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `pool_growth` | Pure validation, classification, warnings, scrub gate |
| `pool_create` | `TOPOLOGIES`, `disk_eligibility` |
| `zfs_repository` | Pure argv builders, `TopologyNode` |
| `command_builders` | `BashStep` |
| `zfs_lock_manager` | Pool-scope write locks |
| `disks_page` | Page refresh and button sensitivity |
| `pools_page` | Pools tab refresh |
| `node_config` | Two-node storage-host guard |
| `gui_helpers` | `create_dialog`, `configure_treeview_column` |
| `logging_config` | `log_msg` |

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
| `disks_page` / `pool_growth_dialogs` / `pool_migrate_dialogs` | Disks tab handlers (SMART details, pool growth, pool migration) |
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
| `refresh_prune_pools()` | Refresh the prune list with pools that `zfscleanup` would prune |
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

Datasets tab: a lazy-loading tree of datasets, snapshots, and holds. Each pool
is represented by its root dataset at the top level. Also hosts the
dataset-tuning actions: Apply Profile (one dialog for the whole multi-select),
Rewrite Data, and the workload profile manager.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `create_datasets_page()` | Build the Datasets tab widget |
| `refresh_datasets_page()` | Refresh the tree, preserving expansion state |
| `update_mounted_states()` | Refresh only the mounted flag/color of visible rows after a mount or unmount |
| `expand_selected_datasets()` | Expand selected rows recursively |
| `update_ds_button_sensitivity()` | Enable/disable action buttons |
| `on_datasets_apply_profile()` | Collect the tunable tree selection, show the profile picker once, and apply the chosen profile to every selected dataset |
| `on_datasets_rewrite_data()` | Rewrite the selected filesystem datasets in place (`zfs rewrite -P`) |
| `on_datasets_manage_profiles()` | Open the workload profile manager |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `gui_helpers` | Tree building, search, selection helpers |
| `profile_dialogs` | Apply Profile / Rewrite Data / profile manager dialogs and execution |
| `workload_profiles` | Profile matching against live properties |
| `feature_config` | Workload profile store |
| `logging_config` | `log_msg` |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| `ZfsRepository` dataclasses (via helper functions) | [ZfsRepository dataclasses][ds-zfsrepo] |

---

### `dashboard_page.py`

Dashboard tab: pool health, recent operations, iSCSI issues, running tasks,
version comparison with a two-node peer, and warnings.

Expensive data gathering (pool queries, SSH version checks) runs in a
background thread by default so the GTK main loop stays responsive.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `create_dashboard_page()` | Build the Dashboard tab widget |
| `refresh_dashboard_page(sync=False)` | Re-gather all dashboard data asynchronously (`sync=True` to block) |
| `_get_pool_health()` | Query `zpool list` via `ZfsRepository` |
| `_get_warnings()` | Compile warning strings from all sources |
| `_format_disk_wear_warnings()` | Warning strings for SSD/NVMe disks at/above `DISK_WEAR_WARNING_THRESHOLD` (80%) |
| `_get_disk_wear_warnings()` | Wear warnings from `disk_repository.disk_inventory()`, TTL-cached 300 s so the 30 s refresh never re-runs a smartctl sweep |
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

Next-run computation is performed in a background thread and cached per
cron expression per minute so the UI remains responsive.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `create_schedule_page()` | Build the Schedule tab widget |
| `refresh_schedule_page(sync=False)` | Refresh the schedule list asynchronously (`sync=True` to block) |
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
| `ScrubQueue` | Persistent pending/active/paused/finished pool sets with concurrency target; buckets are disjoint, stale entries are pruned by `tick()`, and `reload()` re-reads persisted state before each GUI/Dashboard tick |

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

### `iscsi_enroll.py`

Two-node iSCSI enrollment offer for newly created or migrated pools. After
the Create Pool wizard creates a pool on the storage host in a two-node
configuration, this module asks whether to run the
[`enroll-iscsi-pool`](../commands-and-modules/two-node.md#enroll-iscsi-pool-storage-node)
script: it adds the pool to the `POOL_TARGET` map in `node.conf` on both
nodes, creates the pool's iSCSI target on the storage host, and rescans the
compute host. The Migrate Pool cutover also uses these helpers to decide
whether a chained `repair-iscsi-luns` step is needed. Decision logic is kept
in pure helpers (testable without GTK); the enrollment itself runs as a
non-fatal `BashStep` on the dataset runner so an enrollment failure does not
look like a pool-creation failure.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `derive_target_short(pool_name)` | Derive the iSCSI target short name (lowercase, keeping only `[a-z0-9.-]`); mirrors the bash `derive_target_short` |
| `is_iscsi_managed_pool(pool_name, config)` | True when the config is two-node and the pool has a `POOL_TARGET` entry |
| `build_enroll_command(pool_name, short_name, dry_run)` | Pure `enroll-iscsi-pool` argv builder |
| `log_manual_enrollment_steps(pool_name)` | Log the three manual enrollment steps (used when the offer does not apply or is declined) |
| `offer_iscsi_enrollment(app, pool_name, on_done)` | GTK offer dialog; hands the enrollment step to the dataset runner, or logs the manual steps and returns False |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `node_config` | Two-node/host detection, `POOL_TARGET` lookup |
| `command_builders` | `BashStep` |
| `path_utils` | `resolve_local_bin` |
| `disks_page` / `pools_page` | Post-enrollment refresh |
| `backup_config` | `log_msg` |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| `node.conf` `POOL_TARGET` map | [Node config](../developer-guide/data-structures.md#node-configuration-file-etczfsutilitiesnodeconf) |
| `BashStep` | [BashStep][ds-bashstep] |

---

### `retention_actions.py`

Action handlers for the Retention Policies tab: add/remove policies and
buckets, run prune, and dirty-state tracking.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `on_retention_add_policy()` / `on_retention_remove_policy()` | Manage per-pool policies |
| `on_retention_add_bucket()` / `on_retention_remove_bucket()` | Manage buckets |
| `on_retention_prune()` | Prune selected pools; respects retention policies by default, or deletes all matching snapshots when **Ignore retention policies** is checked |
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

### `gui_helpers.py`

Reusable GTK helpers and utility functions used by nearly every page.

**Key classes:**

| Class | Purpose |
| ----- | ------- |
| `DirtyTracker` | Generic save/revert dirty-state tracker |
| `EditableListView` | Reusable ListStore with Add/Remove/Move |
| `TreeSearch` | Debounced search with prev/next for a `Gtk.TreeView` |
| `TextViewSearch` | Search/navigation for a `Gtk.TextView`; matches are stored as character offsets (not `Gtk.TextIter`s, which buffer edits invalidate) so prev/next keeps working as the buffer grows; `refresh()` folds new text into an active search without scrolling |
| `LogPopoutWindow` | Independent window for popping out the info panel |
| `UIStateManager` | Debounced save/restore of window geometry |

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `build_full_dataset_name()` | Walk tree parents to build the full ZFS name |
| Tree loading helpers | Load pools, datasets, and snapshots on demand |
| `get_busy_processes()` / `diagnose_dataset_busy()` | Find and explain why a dataset is busy |
| `get_mounted_snapshots()` | Parse `mount -t zfs` output to detect explicitly mounted snapshots (the `.zfs/snapshot` directory alone is an automount stub) |
| `show_error_dialog()` / `show_warning_dialog()` | Modal error/warning message dialogs |
| `style_expander_label()` | Color an Advanced expander label orange when any child value differs from its defaults |
| `style_widget_value_nondefault()` / `style_var_widgets_nondefault()` | Color the non-default values themselves orange (via a `zfsu-nondefault` CSS class) in addition to the expander label |
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

Stale-lock cleanup verifies that the script recorded in each lock file still
appears in the holder's `/proc/<pid>/cmdline`. Locks recorded by a process
launched via `python -m <package>` are matched by package name, since
`argv[0]` in that case is the package's `__main__.py`, which never appears in
the process cmdline.

**Key functions / context managers:**

| Function | Purpose |
| -------- | ------- |
| `check(dataset, lock_type)` | Return whether a lock can be acquired |
| `acquire(dataset, lock_type, description="")` | Acquire a lock and return a lock ID |
| `acquire_multiple(lock_type, datasets)` | Acquire several locks in deadlock-free order |
| `release(lock_id)` / `release_all()` | Release one lock or all locks held by this process |
| `lock(dataset, lock_type, description="")` | Context manager for a single lock |
| `locks(lock_type, datasets)` | Context manager for multiple locks |
| `list_active_locks()` | Return all currently active (non-stale) dataset locks |

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
5. Trigger the first asynchronous Dashboard refresh.

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
| `resolve_docs_path()` | Locate `docs/site/index.html` or deployed equivalent |
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

[ds-json]: ../developer-guide/data-structures.md#json-config-varlibzfsutilitiesconfigjson
[ds-log]: ../developer-guide/data-structures.md#session-log-index-varlogzfsutilitiessessionslog_indexjson
[ds-history]: ../developer-guide/data-structures.md#backup-history-varlibzfsutilitieshistoryjson
[ds-bashstep]: ../developer-guide/data-structures.md#bashstep-command_builderspy
[ds-appctx]: ../developer-guide/data-structures.md#appcontext-app_contextpy
[ds-zfsrepo]: ../developer-guide/data-structures.md#zfsrepository-dataclasses-zfs_repositorypy
[ds-scrub]: ../developer-guide/data-structures.md#scrub-state-scrub_managerpy
[ds-snapfile]: ../developer-guide/data-structures.md#snapshot-name-persistence
[ds-fss]: ../developer-guide/data-structures.md#fss-table-in-memory-rows-from-zfscheckagainst-json
[ds-node]: ../developer-guide/data-structures.md#node-configuration-file-etczfsutilitiesnodeconf
[ds-profiles]: ../user-guide/profiles.md
[ds-backup]: ../developer-guide/data-structures.md#backup-object
[ds-config-migrations]: ../developer-guide/data-structures.md#config-migrations
[ds-retention]: ../developer-guide/data-structures.md#retention-policy-arrays-bktname-bktretain-minage
[ds-workload]: ../developer-guide/data-structures.md#workload_profiles-object

---

### `installer_retention.py`

Initializes the shared JSON config retention section for the installers. On a
new install it ensures only the `default` retention policy exists, clearing any
pool-specific policies. On an existing install it leaves user-created per-pool
policies untouched and only adds a missing `default` policy.

**Key functions:**

| Function | Purpose |
| -------- | ------- |
| `ensure_default_retention_profile(config_path, new_install)` | Load or create the JSON config and enforce the default retention rule |
| `main()` | CLI entry point used by `install-two-node` over SSH |

**Called modules / imported helpers:**

| Module | Purpose in this module |
| ------ | ------------------------ |
| `config_core` | `load_config`, `save_config`, `CONFIG_PATH` |
| `feature_config` | `get_all_retention` |
| `logging_config` | `log_msg` |

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| JSON config `retention` | [Retention policy arrays](../developer-guide/data-structures.md#retention-policy-arrays-bktname-bktretain-minage) |

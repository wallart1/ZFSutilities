# Data Structures

This page documents the non-trivial shared data structures — arrays,
associative arrays, and the on-disk JSON config — that carry state between
scripts. Scalars (plain global variables) are on the
[Global Variables](global-variables.md) page.

## `$fsarray` / `$fsarraylen`

Output of [`zfsbuildfsarray`](../commands-and-modules/modules.md#zfsbuildfsarray).
A plain indexed bash array of fully-qualified dataset names (or snapshots, or
pools — depends on `$buildfsarraytype`) that survived the include/exclude/
startwith/endwith filters.

| Part          | Type    | Purpose                                                  |
| ------------- | ------- | -------------------------------------------------------- |
| `$fsarray[i]` | string  | Dataset name at index `i`                                |
| `$fsarraylen` | integer | Final length of the array (set at end of `buildfsarray`) |

Consumers iterate with `for ((i=0; i<fsarraylen; i++))`. The array persists
after `buildfsarray` returns because scripts are sourced, not forked.

## `$zfspoolarray`

Output of `poolarray` (from [`zfsconfig`](../commands-and-modules/modules.md#zfsconfig),
historically from `zfsallthepools`). Plain indexed array of pool names as
configured in the JSON config's `pools` key. This is a registry — it does not
reflect import state; use `zpool list` output for that.

## Snapshot name persistence

[`zfssnapbuild`](../commands-and-modules/modules.md#zfssnapbuild) writes the generated
snapshot name to a per-caller file in `/tmp` so that the same name can be reused
if the calling script is rerun. This keeps incremental replication chains stable
across multiple invocations.

| File pattern | Writer | Consumers | Purpose |
| ------------ | ------ | --------- | ------- |
| `/tmp/zfsnextsnap_<caller>` | `zfssnapbuild` | `zfs-send-receive`, `zfssendoffsite`, `zfssend`, `zfsdailybackup` | Reuse the same snapshot name on rerun |

`removesnapfile` (called by orchestrators such as `zfsdailybackup`) deletes the
snapfile at the end of a successful run. In dry-run mode the snapfile is left in
place.

## Snapshot-name reservation

To prevent two concurrent jobs from generating a snapshot name at the exact same
instant, both `zfssnapbuild` and `feature_config.generate_snapshot_name()` acquire
a brief global lock (`/run/lock/zfs/.snapname.lock`) while building the name and
recording it in a one-minute reservation file
(`/run/lock/zfs/.snapname.reserved`). The reservation records the most recently
issued name for each label/bucket with a timestamp; stale entries expire after 60
seconds. The lock is released immediately after the reservation is written.

## `fss` table (in-memory rows from [zfscheckagainst](../commands-and-modules/modules.md#zfscheckagainst) JSON)

Used by [`zfscheckagainst`](../commands-and-modules/modules.md#zfscheckagainst)
to map a snapshot to the counterpart dataset that must still share a common
snapshot with it before deletion is safe. Loaded at [zfscheckagainst](../commands-and-modules/modules.md#zfscheckagainst) time from
`zfsconfig_get_checkagainst`. Each row has four functional whitespace-separated
fields; an optional fifth `comment` field is stored in the JSON config and
ignored by the bash consumer:

| Field | Variable name in script                 | Purpose                                                          |
| ----- | --------------------------------------- | ---------------------------------------------------------------- |
| 1     | apply-to dataset (`$fs`)                | Matches the source dataset tree. May contain `<offsite>` anywhere; every occurrence is replaced with each offsite-candidate pool name at run-time |
| 2     | qualifiers to delete (`$delquals`)      | Leading path components to strip                                 |
| 3     | qualifiers to prepend (`$checkagainst`) | Path prefix to prepend, or `-` for none                          |
| 4     | label                                   | Snapshot label this row applies to (`dailybackup`, `offsite`, …) |
| 5     | comment                                 | Optional UI-only note (JSON-only, not emitted by `zfsconfig_get_checkagainst`) |

See [`zfscheckagainst` → The fss table](../commands-and-modules/modules.md#the-fss-table)
for the matching algorithm and a worked example.

### Legacy format (`zfscheckagainst.conf`)

Before the JSON config, the fss table was stored in a plain text file at the
project root:

```
# zfscheckagainst.conf
# Format: <dataset> <delquals> <prepend> <label> [<comment>]
threeamigos          0 fivebays    dailybackup
fivebays/threeamigos 2 threeamigos dailybackup
```

This file is **deprecated**. The GUI imports it into the JSON config
automatically on first run. After import, the standalone file can be removed.

## Retention policy arrays (`$bktname` / `$bktretain` / `$minage`)

Produced by `zfsconfig_get_retention <pool>` as a sourceable bash fragment.
After `eval "$(zfsconfig_get_retention <pool>)"`, three parallel indexed
arrays hold the policy:

| Array           | Purpose                                                                      |
| --------------- | ---------------------------------------------------------------------------- |
| `$bktname[i]`   | Bucket letter (`d`, `w`, `m`, `s`)                                           |
| `$bktretain[i]` | Number of snapshots to keep in that bucket                                   |
| `$minage[i]`    | Minimum age (days) before a snapshot in that bucket is eligible for deletion |

`$bktlen=${#bktname[@]}` gives the count. [zfsretain](../commands-and-modules/modules.md#zfsretain) iterates these arrays
in Phase 2 to decide which snapshots exceed their bucket's cap. Order
follows the JSON config entry order (typically `d, w, m, s`).

## `snaparray` / `bktsnaparray` (zfsretain)

Two arrays built inside [`zfsretain`](../commands-and-modules/modules.md#zfsretain):

| Array             | Contents                                                                                   | Used by                                                  |
| ----------------- | ------------------------------------------------------------------------------------------ | -------------------------------------------------------- |
| `$snaparray[]`    | `zfs list -Ht snapshot -o name,creation -s creation` output (name + creation date per row) | Phase 0 offsite same-month prune, Phase 1 same-day dedup |
| `$bktsnaparray[]` | `zfs list -Ht snapshot -o name -s creation` (names only)                                   | Phase 2 bucket assignment                                |

Phase 2 also builds per-bucket arrays via indirect references:

```
snapbucket_d[0..n]     snapbucketlen_d
snapbucket_w[0..n]     snapbucketlen_w
snapbucket_m[0..n]     snapbucketlen_m
snapbucket_s[0..n]     snapbucketlen_s
```

These are populated with `declare` using computed variable names
(`snapbucket_${bktname[$i]}[$l]`) because bash has no true nested arrays.

## `ISCSI_TEARDOWN` (associative array)

Used by [`zfsdelfs`](../commands-and-modules/commands.md#zfsdelfs) to bridge
teardown → rebuild across a zfs destroy/receive cycle. In single-node mode
this stays empty.

```
ISCSI_TEARDOWN[<dataset>]="<target>:<lun_num>:<backstore_name>:<encrypted_flag>"
```

| Key                                                      | Value                                                                                                     |
| -------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| Dataset name (e.g., `threeamigos/proxmox/vm-101-disk-0`) | Colon-separated quadruple: iSCSI target IQN, LUN number, backstore name, `Y` if the backstore was encrypted |

Populated by `iscsi_teardown_zvol` before `zfs destroy`; consumed by
`iscsi_rebuild_torn_down` (called from [`zfs-send-receive`](../commands-and-modules/modules.md#zfs-send-receive)) after the replacement
`zfs receive` completes, which re-adds the LUN at the original LUN number so
that by-path device symlinks on the compute node remain stable.

## `POOL_TARGET` (associative array)

Set in `/etc/zfsutilities-node.conf` on two-node systems. Maps ZFS pool
names to iSCSI target short names.

```bash
declare -A POOL_TARGET=(
    [threeamigos]="threeamigos"
    [NVME1]="nvme1"
)
```

| Key           | Value                                                                  |
| ------------- | ---------------------------------------------------------------------- |
| ZFS pool name | Short name used as the IQN target suffix (`<IQN_PREFIX>:<short-name>`) |

Read by `node-lib.sh` via `pool_to_target`, `pool_list`, and `is_known_pool`.
Only pools listed here are managed by two-node iSCSI scripts. In single-node
mode, this array is empty and the helpers are no-ops.

## Node configuration file (`/etc/zfsutilities-node.conf`)

Sourceable bash. Read by `node-lib.sh` and by repo-root scripts with a legacy
fallback to `/etc/two-node.conf`. See [Node Configuration](two-node-config.md)
for the full field list.

| Variable       | Mode        | Purpose                                  |
| -------------- | ----------- | ---------------------------------------- |
| `NODE_MODE`    | both        | `single-node` or `two-node`              |
| `THIS_HOST`    | single-node | Short hostname of this node              |
| `STORAGE_HOST` | two-node    | Storage node short hostname              |
| `COMPUTE_HOST` | two-node    | Compute node short hostname              |
| `STORAGE_IP`   | two-node    | Storage network IP of the storage node   |
| `IQN_PREFIX`   | two-node    | IQN prefix for iSCSI targets             |
| `POOL_TARGET`  | two-node    | Pool → target short-name map (see above) |

## JSON config (`/root/.config/zfsutilities.json`)

Shared by the GTK Python layer (`config_core.py` / `feature_config.py`) and
the bash scripts ([`zfsconfig`](../commands-and-modules/modules.md#zfsconfig)).
Top-level keys:

| Key                                                                   | Type                                 | Contents                                                                                                             |
| --------------------------------------------------------------------- | ------------------------------------ | -------------------------------------------------------------------------------------------------------------------- |
| `pools`                                                               | array of strings or objects          | Registered pool names. String entries are supported for backward compatibility; v14 migrates them to `{"name", "offsite_candidate"}` objects |
| [zfscheckagainst](../commands-and-modules/modules.md#zfscheckagainst) | array of objects                     | fss table rows (`dataset`, `quals`, `counterpart`, `label`, optional `comment`)                                   |
| `retention`                                                           | object keyed by pool name | Per-pool retention policy. Each value is an array of `{name, retain, minage}` entries. Key `default` is the fallback |
| `backup`                                                              | object                    | GUI Backup tab settings (see below)                                                                                  |
| `offsite`                                                             | object                    | GUI Offsite tab settings                                                                                             |
| `restore`                                                             | object                    | GUI Restore tab settings                                                                                             |
| `msg_level`                                                           | string                    | Deprecated. Kept for backward compatibility; no longer used for filtering.                                           |
| `history_retention_days`                                              | integer                   | How many days of backup log history entries to keep (default `90`)                                                   |
| `config_version`                                                      | integer                   | Config schema version (see migrations below)                                                                         |

All sections default to empty on first run — the user populates them through
the GUI. Override the path in the environment with `$ZFSCONFIG_PATH`.

### Python access

The Python config API is split across two modules:

- `config_core.load_config()` / `save_config()` — read/write the whole JSON file
- `config_core.get_ui_state()` / `save_ui_state()` — main/docs/log window geometry
- `config_core.get_dashboard_config()` / `save_dashboard_config()` — dashboard thresholds
- `config_core.get_log_retention_days()` / `save_log_retention_days()` — session log pruning
- `config_core.get_history_retention_days()` / `save_history_retention_days()` — history pruning
- `feature_config.get_backup_config()` / `save_backup_config()` — Backup tab state
- `feature_config.get_offsite_config()` / `save_offsite_config()` — Offsite tab state
- `feature_config.get_restore_config()` / `save_restore_config()` — Restore tab state
- `feature_config.get_retention()` / `save_retention()` — per-pool retention policies
- `feature_config.get_pools()` / `save_pools()` — registered pool list
- `feature_config.get_checkagainst()` / `save_checkagainst()` — fss table
- `feature_config.generate_snapshot_name()` / `generate_offsite_snapshot_name()` — snapshot naming

`backup_config.py` still re-exports all of these for backward compatibility.

### `backup` object

Persisted by the GUI Backup tab and read by [zfsdailybackup](../commands-and-modules/commands.md#zfsdailybackup) (via overrides).

| Key                         | Type                              | Purpose                                                                                                                                                                                                                                |
| --------------------------- | --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `variables`                 | object                            | Bash variable overrides: `label`, `autoresume`, `doincrementals`, `dointermediates`, `allow_destructive`, `receive_F_option`, `releaseholds`, `verify_after_transfer`, `pv_rate_limit`, `includes`, `excludes`, `startwith`, `endwith` |
| `pull_steps`                | array of `{active, source, dest}` | Rsync pull operations                                                                                                                                                                                                                  |
| `send_receive_steps`        | array of `{active, source, dest}` | ZFS send/receive operations                                                                                                                                                                                                            |
| `post_steps`                | object                            | `remove_snapfile` (bool), `run_retention` (bool)                                                                                                                                                                                       |
| `pre_backup_script_enabled` | bool                              | Whether to run the pre-backup command                                                                                                                                                                                                  |
| `pre_backup_script`         | string                            | Bash command to run before all backup steps                                                                                                                                                                                            |
| `post_backup_script_enabled`| bool                              | Whether to run the post-backup command                                                                                                                                                                                                 |
| `post_backup_script`        | string                            | Bash command to run after all backup steps (even on fatal error)                                                                                                                                                                       |

### Config migrations

The `config_version` key tracks the schema of the JSON config independently of
the software release version. When the config structure changes, bump
`CONFIG_VERSION` in `config_migrations.py` and add a migration function.

**Migration chain** (`config_migrations.py`):

```python
CONFIG_VERSION = 15

MIGRATIONS = [
    _migrate_1_to_2,
    _migrate_2_to_3,
    _migrate_3_to_4,
    _migrate_4_to_5,
    _migrate_5_to_6,
    _migrate_6_to_7,
    _migrate_7_to_8,
    _migrate_8_to_9,
    _migrate_9_to_10,
    _migrate_10_to_11,
    _migrate_11_to_12,
    _migrate_12_to_13,
    _migrate_13_to_14,
    _migrate_14_to_15,
]
```

Each migration function upgrades the config by one version:

```python
def _migrate_14_to_15(config):
    for entry in config.get("checkagainst", []):
        if "comment" not in entry:
            entry["comment"] = ""
    config["config_version"] = 15
    return config
```

**How it works at runtime:**

1. `load_config()` reads the file
2. If `config_version` is missing, backfill to current `CONFIG_VERSION`
3. If `config_version < CONFIG_VERSION`, run `_run_migrations(config)` —
   each function in `MIGRATIONS` is called in turn, saving after every step
4. If `config_version > CONFIG_VERSION`, a warning is printed (config is
   newer than the software) but execution continues

Adding a new migration:

1. Write the migration function
2. Append it to `MIGRATIONS`
3. Bump `CONFIG_VERSION`

## Python command and I/O structures

These dataclasses live in `07 GTK + Python/` and carry state between the GUI,
the command builders, and the runners.

### `BashStep` (`command_builders.py`)

A single step in a backup, offsite, restore, or retention run. Replaces the
loosely-typed `(cmd_list, description)` tuples used before the refactor.

| Attribute | Type | Purpose |
| --------- | ---- | ------- |
| `command` | `List[str]` | Arguments for `subprocess` (`["bash", "-c", "..."]` for bash steps) |
| `description` | `str` | Human-readable step description shown in the UI and logs |
| `is_rsync` | `bool` | True for rsync transfers (uses rsync log parsing) |
| `fatal` | `bool` | True if a non-zero return code should abort the run |

### `AppContext` (`app_context.py`)

Cross-cutting, non-GTK state passed to GUI pages and action handlers.

| Attribute | Type | Purpose |
| --------- | ---- | ------- |
| `config` | `dict` | Loaded JSON configuration dict (mutated in place by savers) |
| `script_dir` | `str` | Directory containing the Python GUI modules |
| `parent_dir` | `str` | Directory containing the bash scripts (deployed `bin/` or repo root) |
| `version` | `str` | Deployed/repository version string |
| `is_new_install` | `bool` | `True` when the config file was created fresh this session; used by the Retention tab to clear legacy pool-specific policies |
| `zfs_repository` | `ZfsRepository` | Repository for ZFS/zpool I/O |

### `ZfsRepository` dataclasses (`zfs_repository.py`)

Read methods return typed rows instead of raw tab-separated strings.

| Class | Fields | Source command |
| ----- | ------ | -------------- |
| `PoolRow` | `name`, `health`, `size`, `alloc`, `free`, `cap` | `zpool list -H -o name,health,size,alloc,free,cap` |
| `DatasetRow` | `name`, `creation`, `ds_type`, `used`, `avail`, `refer`, `origin`, `clones` | `zfs list -H -o name,creation,type,used,avail,refer,origin,clones` |
| `SnapshotRow` | `name`, `creation`, `ds_type`, `used`, `avail`, `refer`, `origin`, `clones` | `zfs list -t snapshot -H -o name,creation,type,used,avail,refer,origin,clones` |
| `HoldRow` | `snapshot`, `tag`, `date` | `zfs holds -H <snapshot>` |

Additional `ZfsRepository` methods:

| Method | Return | Purpose |
| ------ | ------ | ------- |
| `pool_status_errors(pool)` | `dict` | Parses `zpool status <pool>` and returns `has_errors` (`bool`), `errors_summary` (`str`), `data_errors` (`list` of paths), and `vdev_errors` (`list` of `{name, read, write, cksum}` dicts). Used by the Dashboard and Pools tab to color the **Errors** column. |

### Scrub state (`scrub_manager.py`)

`ScrubState` is an enum and `ScrubInfo` is a dataclass produced by
`scrub_manager.parse_scrub_status()` from raw `zpool status` output. They are
consumed by the Pools tab, Dashboard, and `ScrubQueue`.

| Enum value | Meaning |
| ---------- | ------- |
| `NONE` | No scrub requested |
| `PENDING` | Queued but not yet started by the manager |
| `SCANNING` | Scrub in progress |
| `PAUSED` | Scrub paused |
| `FINISHED` | Scrub completed |
| `CANCELED` | Scrub canceled |
| `UNKNOWN` | Could not determine state |

| `ScrubInfo` field | Type | Purpose |
| ----------------- | ---- | ------- |
| `state` | `ScrubState` | Current scrub state |
| `progress_percent` | `float` or `None` | Percentage done when scanning/paused |
| `scan_line` | `str` | Raw scan lines from `zpool status` |
| `last_scrub` | `str` | Timestamp/description of the last scrub event |
| `errors` | `int` | Error count from finished/canceled scrubs |
| `remaining_seconds` | `int` or `None` | Seconds remaining when `zpool status` reports `HH:MM:SS to go` (or `N days HH:MM:SS to go`) |
| `eta` | `str` or `None` | Estimated completion timestamp (`YYYY-MM-DD HH:MM`) computed from `remaining_seconds` |

`ScrubQueue` persists pending/active/paused/finished/paused_by_user pool sets
and a concurrency target to the JSON config under the scrub-manager section.

## iSCSI expected-backstores manifest

Plain-text file, one backstore name per line:

```
/etc/rtslib-fb-target/expected-backstores.txt
```

Authoritative source of truth for [`safe-iscsi-save`](../commands-and-modules/two-node.md#safe-iscsi-save-storage-node).
Each line names a backstore that should be active in the iSCSI target:

```
# /etc/rtslib-fb-target/expected-backstores.txt
vm-101-disk-0
vm-102-disk-0
vm-103-disk-1
```

[safe-iscsi-save](../commands-and-modules/two-node.md#safe-iscsi-save-storage-node) counts entries in this manifest and compares against the
number of active block backstores in `targetcli`. If fewer backstores are
active than expected, the save is aborted to prevent overwriting
`saveconfig.json` with a degraded (partial) configuration.

Comments (`#`) and blank lines are ignored. Maintained by [new-vm-disk](../commands-and-modules/two-node.md#new-vm-disk-both)
(adds), [unarchive-vm](../commands-and-modules/two-node.md#unarchive-vm-both) (adds restored backstores), and the
`zfs-send-receive` rebuild path (re-adds after a torn-down destination is
re-created). [remove-vm-disk](../commands-and-modules/two-node.md#remove-vm-disk-both) (removes),
[detach-vm-disk](../commands-and-modules/two-node.md#detach-vm-disk-both) (removes),
[move-vm-disk](../commands-and-modules/two-node.md#move-vm-disk-both) source side (removes), and
[zfsdelfs](../commands-and-modules/commands.md#zfsdelfs) iSCSI teardown (removes) keep the manifest in sync with
removal or destructive operations.

[repair-iscsi-luns](../commands-and-modules/two-node.md#repair-iscsi-luns-storage-node) regenerates the entire
manifest from the current targetcli backstore list, and
[safe-iscsi-save](../commands-and-modules/two-node.md#safe-iscsi-save-storage-node) regenerates it after every
successful save so the manifest stays authoritative when LUNs are moved or
added.

## iSCSI encrypted-LUNs config

```
/etc/iscsi-encrypted-luns.conf
```

Lists backstore names whose backing zvols are encrypted. Format:

```
# /etc/iscsi-encrypted-luns.conf
# Format: backstore_name:device_path:target_short_name
vm-101-disk-1:/dev/zvol/threeamigos/proxmox/vm-101-disk-1:threeamigos
vm-202-disk-5:/dev/zvol/threeamigos/proxmox/vm-202-disk-5:threeamigos
```

Consumed by [iscsi-add-encrypted-luns](../commands-and-modules/two-node.md#iscsi-add-encrypted-luns-storage-node) after keys are loaded, and by
[safe-iscsi-save](../commands-and-modules/two-node.md#safe-iscsi-save-storage-node) to generate the boot-safe config. Maintained by
`new-vm-disk --encrypted` (adds) and [remove-vm-disk](../commands-and-modules/two-node.md#remove-vm-disk-both) (removes).

See [ZFS Key Handling](../installation/zfs-keys.md) for how keys are stored on
the LUKS-encrypted USB and how unattended boot is configured.

## Session log index (`/var/log/zfsutilities/sessions/.log_index.json`)

A JSON cache maintained by `log_index.py` so the Logs tab does not need to
re-read every historical session log file on refresh. The top-level object maps
log filenames (e.g. `2026-06-22_07-00-00_backup_gui.log`) to entry dicts.

Each entry has this schema:

| Key                 | Type    | Description                                                            |
| ------------------- | ------- | ---------------------------------------------------------------------- |
| `size`              | integer | Last-known file size in bytes                                          |
| `mtime`             | float   | Last-known file modification time (Unix epoch seconds)                 |
| `status`            | string  | `Done`, `Failed`, `Cancelled`, or `Running`                            |
| `duration`          | float   | Elapsed time in seconds from the trailer                               |
| `bytes_transferred` | integer | Bytes transferred from the trailer (may be `null`)                     |
| `highest_level`     | string  | Highest `log_msg` level seen: `DEBUG`, `VERB`, `INFO`, `WARN`, `FATAL` (may be `null`) |
| `has_trailer`       | boolean | Whether the trailer has been parsed                                    |

**Lifecycle:**

- `BackupRunner._write_session_trailer()` and `profile_runner._write_session_trailer()`
  create or update an entry with the final status, duration, and bytes after
  writing the trailer.
- `logs_page._scan_logs()` scans any log that has no entry or is newer than its
  cached `size`/`mtime`, removes entries for files that no longer exist, and
  persists the index.
- `logs_page._tail_log_file()` updates the current log's entry incrementally
  while the log is open in the viewer.
- Deleting a log via the Logs tab removes its entry from the index.

If a log file contains more than one `# END` trailer (for example because the
file was reused or appended), the index treats the **last** trailer and the
highest message level found anywhere in the file as authoritative. This keeps
the Logs tab in sync with the final run rather than an earlier one.

If the index file is missing or unreadable, the Logs tab scans log files
directly and rebuilds the index. The file is written atomically (temp + rename)
and ignored by log retention pruning.

## iSCSI boot-safe config

```
/etc/rtslib-fb-target/saveconfig-boot.json
```

A copy of `saveconfig.json` with encrypted backstores stripped out.
Generated automatically by [safe-iscsi-save](../commands-and-modules/two-node.md#safe-iscsi-save-storage-node) every time the full config
is saved.

At boot, the systemd drop-in for `rtslib-fb-targetctl.service` restores
from this file instead of the full config. This prevents `targetctl restore`
from failing when encrypted zvol device nodes don't exist yet because
keys haven't been loaded.

## Backup history (`/root/.config/zfsutilities-history.json`)

A separate JSON file (not part of the main config) that stores per-run metrics
for every backup, offsite, restore, and prune operation. It is append-only:
new entries are inserted at the front, and old entries are pruned automatically
based on `history_retention_days`.

Each entry is a dict with this schema:

| Key                 | Type    | Description                                         |
| ------------------- | ------- | --------------------------------------------------- |
| `timestamp`         | string  | ISO-8601 datetime when the run finished             |
| `type`              | string  | `backup`, `offsite`, `restore`, or `prune`          |
| `name`              | string  | GUI label or profile name (e.g. `Backup`, `Daily`)  |
| `duration`          | float   | Elapsed time in seconds                             |
| `result`            | string  | `success`, `failed`, or `cancelled`                 |
| `bytes_transferred` | integer | Total bytes received across all `zfs receive` steps |

The file is written atomically (temp + rename) to avoid corruption.

**Consumers:**

- `backup_runner.py` — creates an entry when a GUI run finishes
- `profile_runner.py` — creates an entry when a scheduled/cron run finishes
- `logs_page.py` — reads the file to compute and display the success-rate summary

## zfsscruball state file

[`zfsscruball`](../commands-and-modules/commands.md#zfsscruball) uses a temporary
state file to remember which pools have already finished when resuming a paused
or interrupted scrub run.

```
/tmp/zfsscruball.state
```

**Format:** one finished pool name per line.

**Lifecycle:**

- `do_start` truncates the file at the beginning of a new run.
- Each parallel scrub worker appends its pool name on successful completion.
- `do_resume` reads the file and skips any pool listed there.
- `do_scrubs` removes the file after all pools finish.

Because the file lives on `tmpfs`, it is cleared on reboot and a resume after
reboot starts fresh.

## Lock files

Written by [`zfslockmanager`](../commands-and-modules/modules.md#zfslockmanager)
under `/run/lock/zfs/.locks/`:

```
<path-encoded-dataset>.<type>.<pid>.<lock-id>
```

Cleared automatically at reboot (tmpfs). Path separators and special
characters in dataset names are URL-encoded (`%2F` for `/`, `%40` for `@`).

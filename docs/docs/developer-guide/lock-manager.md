# ZFS Lock Manager

## Overview

A hierarchical dataset lock manager for ZFS utilities that prevents conflicting operations on datasets, with support for multiple lock types, stale lock detection, and interactive conflict resolution.

## Design Points

- **Lock storage**: `/run/lock/zfsutilities/` (cleared on reboot)
- **Stale detection**: PID-based (check if process exists) + EXIT traps
- **CLI tool**: [zfslockctl](../commands-and-modules/commands.md#zfslockctl) for manual lock management
- **Chain awareness**: Independent (no checkagainst integration for now)

## Lock Types

| Type              | Code | Description                                | Conflicts With |
| ----------------- | ---- | ------------------------------------------ | -------------- |
| Shared Read       | `r`  | Reading metadata, listing                  | `w`, `x`       |
| Exclusive Write   | `w`  | Creating/modifying snapshots, send/receive | `r`, `w`, `x`  |
| Exclusive Destroy | `x`  | Destroying datasets/snapshots              | All types      |

## Hierarchical Rules

When acquiring a lock on `/pool/parent/child`:

1. Check ancestors (`/pool`, `/pool/parent`) for conflicting locks
2. Check descendants (`/pool/parent/child/*`) for conflicting locks

**Conflict matrix:**

- `x` (destroy) on parent → conflicts with ANY lock on descendants
- `w` (write) on parent → conflicts with `w`, `x` on descendants
- `r` (read) on parent → conflicts with `x` on descendants
- Any lock on child → blocks `x` on ancestors

## Lock File Structure

```
/run/lock/zfsutilities/
├── .locks/                    # Lock data files
│   ├── pool.lock
│   ├── pool%2Fdataset.lock    # URL-encoded paths
│   └── pool%2Fparent%2Fchild.lock
└── .pids/                     # PID tracking for stale detection
    └── <pid>                  # Contains list of locks held by this PID
```

**Lock file format (JSON):**

```json
{
  "dataset": "pool/parent/child",
  "type": "w",
  "pid": 12345,
  "script": "zfsdailybackup",
  "acquired": "2026-01-10T14:30:00-05:00",
  "description": "send-receive to fivebays"
}
```

## Lock Manager Scripts

### zfslockmanager

#### Core lock management functions (sourced by other scripts)

##### Lock acquisition

`zfslock_acquire <dataset> <type> [description]`

- Returns: 0=success, 1=conflict, 2=error
- Sets: $zfslock_id on success

##### Lock release

`zfslock_release <lock_id>`

`zfslock_release_all`

- Release all locks held by current PID

##### Conflict checking

`zfslock_check <dataset> <type>`

- Returns: 0=no conflict, 1=conflict exists
- Sets: $zfslock_conflict_info

##### Interactive conflict resolution

`zfslock_wait_or_resolve <dataset> <type> [description]`

- Returns: 0=acquired, 1=user aborted, 2=user skipped

When stdin is not a TTY or `ZFSUTILITIES_HEADLESS=Y` is set, the function does not
prompt. By default it logs a `FATAL:` message and returns 1 immediately. This
prevents cron or headless profile runs from hanging indefinitely.

If `ZFSLOCK_HEADLESS_WAIT_SECONDS` is set to a positive number, the function
will wait up to that many seconds for the lock to become free before logging
`FATAL:` and returning 1.  Between attempts it sleeps for
`ZFSLOCK_WAIT_INTERVAL` seconds (default 30).  `profile_runner.py` exports
this variable for all bash steps it invokes.

The conflict-resolution loop also throttles repeated acquisition attempts with a
short backoff when a conflict persists, so a closed stdin or an invalid choice
cannot spin the CPU.

Before prompting, the conflicting lock file is explicitly checked for staleness.
If it is stale, it is removed and acquisition is retried automatically.

##### Stale detection

`zfslock_is_stale <lock_file>`
`zfslock_cleanup_stale`

### zfslockctl

##### Standalone CLI tool:

```text
zfslockctl list [dataset]           List active locks (HOST column in two-node mode)
zfslockctl status <dataset>         Check lock status
zfslockctl release <lock_id>        Force release a lock
zfslockctl cleanup                  Remove stale locks
zfslockctl wait <dataset> <type>    Wait for lock availability
```

In two-node mode, `status`, `wait`, `release`, and `cleanup` forward to the
storage node when the dataset is storage-owned.

### Python client

`python/zfs_lock_manager.py` provides `list_active_locks()`, which returns all
currently active (non-stale) locks as a list of dicts with `dataset`, `type`,
`pid`, `script`, `acquired`, `description`, and `host` keys. The Dashboard uses
this to populate its **Active Locks** section.

## Key Implementation Details

### EXIT Trap for Automatic Cleanup

```bash
_zfslock_cleanup_trap() {
    zfslock_release_all
}
trap _zfslock_cleanup_trap EXIT
```

### Stale Lock Detection

A lock is stale if:

1. The PID in the lock file no longer exists (`kill -0 $pid` fails)
2. The PID exists but is a different process (check `/proc/$pid/cmdline`)

A live process may have an empty `/proc/$pid/cmdline` briefly after `fork()`
before the new program's `argv` is visible.  An empty cmdline is treated as
inconclusive, so the lock is left in place rather than removed prematurely.

### Atomic Lock File Creation

Lock files are written to a temporary file in the same directory and renamed
into place.  Other processes therefore never see a partially-written or
truncated lock file, even if the writer is interrupted between `open()` and
`close()`.

### Interactive Conflict Resolution

When conflict detected, options are offered:

```
CONFLICT: A lock could not be acquired for 'fivebays/NVME1' because another task is using the dataset or a related dataset.
  Locked dataset: fivebays/NVME1
  Script: zfssendoffsite (PID 12345)
  Type: write
  Since: 2026-01-10 14:30:00 (2 hours ago)
  Description: send-receive to z22tb

Options:
  [W] Wait and retry (checks every 30 seconds)
  [R] Retry now (re-check immediately)
  [S] Skip this dataset and continue
  [A] Abort entire operation
  [F] Force release lock (DANGEROUS)

Choice [W/R/S/A/F]:
```

**Wait (`W`)** keeps checking the lock every `ZFSLOCK_WAIT_INTERVAL` seconds and
retries automatically as soon as the lock is free. Press `Ctrl+C` to stop waiting
and return to the choice prompt. Values below `1` second are clamped to `1` second
to avoid busy-waiting.

**Retry now (`R`)** immediately re-checks whether the lock can be acquired. This is
useful when you have resolved the conflict externally (for example, by stopping the
holding process) and want to retry without waiting for the next poll interval. If the
lock is still held, the prompt is shown again.

**Skip (`S`)** skips only the current dataset and continues with the next one.

**Abort (`A`)** returns 1 to the caller. Scripts such as `zfs-send-receive` treat
this as a request to abort the entire operation.

### Hierarchy Checking Algorithm

```bash
zfslock_check_hierarchy() {
    local dataset="$1"
    local type="$2"

    # Check ancestors
    local parent="$dataset"
    while [[ "$parent" == */* ]]; do
        parent="${parent%/*}"
        if zfslock_conflicts "$parent" "$type" "ancestor"; then
            return 1
        fi
    done

    # Check descendants (glob lock files matching prefix)
    for lockfile in /run/lock/zfsutilities/.locks/"${dataset_encoded}"*; do
        if zfslock_conflicts "$lockfile" "$type" "descendant"; then
            return 1
        fi
    done

    return 0
}
```

### Acquiring Multiple Locks

When a script needs to lock several datasets at once, it must acquire them in a
deterministic order to avoid deadlocks. Use:

```bash
zfslock_acquire_multiple <type> <dataset> [<dataset> ...]
```

- `<type>` is one of `r`, `w`, or `x`.
- Returns `0` on success, `1` on conflict, and `2` on error.
- On success, the global array `zfslock_ids` contains the acquired lock file
  paths.
- If any individual lock cannot be acquired, all locks acquired during the
  call are released before returning, so the caller never holds a partial set.

### Ordering rule

1. Sort requested datasets by path depth (shallowest first), then
   lexicographically within the same depth.
2. Remove duplicates.
3. If one requested path is an ancestor of another requested path, keep only
   the most specific (deepest) path. A lock on the deepest dataset blocks the
   same conflicting operations on its ancestors through the hierarchical rules,
   so the broader lock is redundant.
4. Acquire the remaining locks in sorted order.

Example:

```bash
zfslock_acquire_multiple w "pool/a" "pool/b/child" "pool/a/grandchild"
# Acquires only "pool/a/grandchild" and "pool/b/child", in that order.
```

## Path Encoding

Dataset paths are URL-encoded for safe filenames:

- `/` → `%2F`
- `@` → `%40` (for snapshots)

## Two-Node Operation

In a two-node configuration, all ZFS dataset locks are held on the storage node.
The compute node forwards lock operations for storage-owned datasets to the
storage node over the existing root-SSH path. Single-node behaviour is unchanged.

### How dataset ownership is decided

The lock manager reads `/etc/zfsutilities/node.conf` (with legacy fallbacks) and
compares the local short hostname with the configured `STORAGE_HOST`. If the
local host is the compute node and the dataset's pool appears in `POOL_TARGET`,
the lock is forwarded to `STORAGE_HOST`.

### Remote lock agent

`bin/zfslockmanager-remote` runs on the storage node and provides the subcommands
used by the compute side:

- `hold <dataset> <type> [description]` — acquire the lock, print the lock file
  path, then sleep until the SSH session ends.
- `check <dataset> <type>` — return JSON indicating whether the lock is
  available.
- `list` — return a JSON array of active locks.
- `release <lockfile>` — force-remove a lock file.
- `cleanup` — remove stale locks.

### Compute-side forwarding

- `zfslock_acquire` spawns `zfslockmanager-remote hold ...` via SSH, records the
  SSH session PID, and returns a `REMOTE:<lockfile>` lock id.
- `zfslock_release` terminates the SSH session and also sends a `release`
  command to the storage node to ensure the lock file is removed.
- `zfslock_check` runs the remote `check` command and converts a conflict into a
  local temporary lock file so the existing interactive prompt can display it.
- `zfslock_wait_or_resolve` polls the remote lock authority; force-release of a
  remote lock is forwarded to the storage node.

The Python client (`python/zfs_lock_manager.py`) uses the same SSH-based remote
agent. Remote holds are kept alive by a `subprocess.Popen` instance; an
`atexit` handler terminates them when the Python process exits.

### Environment overrides (for tests and non-standard installs)

| Variable | Purpose |
| --- | --- |
| `ZFSLOCK_REMOTE_DISABLED=1` | Force local-only locking. |
| `ZFSLOCK_REMOTE_HOST` | Override the storage hostname. |
| `ZFSLOCK_REMOTE_POOLS` | Space-separated list of pools to treat as remote. |
| `ZFSLOCK_REMOTE_BIN` | Override the remote `bin/` directory. |
| `ZFSLOCK_THIS_HOST` | Override the local hostname. |
| `ZFSUTILITIES_NODE_CONF` | Path to the node configuration file. |

### Dashboard

The Dashboard's **Active Locks** list includes a `Host` column. In two-node mode,
`list_active_locks()` merges local locks with locks queried from the storage
node, so the Dashboard shows cluster-wide locks.

## Integration Points

Scripts and modules that have lock integration:

| Script / module       | Lock Type | Dataset(s) / pools                              |
| --------------------- | --------- | ----------------------------------------------- |
| zfs-send-receive      | `w`       | source, destination                             |
| zfsrestoresendstream  | `w`       | destination dataset per receive                 |
| zfsmount              | `w`       | each dataset being mounted/unmounted            |
| zfsunmount            | `w`       | each dataset being unmounted                    |
| zfsretain             | `w`       | filesystem being retained                       |
| zfscleanup            | `w`       | per dataset (via `zfsretain`)                   |
| zfsdelsnap            | `w`       | snapshot's parent dataset                       |
| zfsdelallsnaps        | `w`       | parent dataset (via `zfsdelsnap`)               |
| zfsmassdelsnaps       | `w`       | each parent dataset                             |
| zfsdelfs              | `x`       | top-level dataset being destroyed               |
| clone-vm / zfsclone-vm| `w`       | source and destination zvols                    |
| move-vm-disk          | `x`/`w`   | source and destination zvols                    |
| rename-vm-disk        | `w`       | affected zvol                                   |
| remove-vm-disk        | `x`       | affected zvol                                   |
| resize-vm-disk        | `w`       | affected zvol / pool                            |
| new-vm-disk           | `w`       | affected zvol / pool                            |
| promote-vm-clone      | `w`       | zvol being promoted                             |
| archive-vm            | `w`       | archived zvols                                  |
| unarchive-vm          | `w`       | restored zvols                                  |
| PVE-send-to-archive   | `w`       | archived zvols                                  |
| zfshold / zfsholds    | `w`/`r`   | affected datasets                               |
| zfsdelallholds*       | `w`       | parent dataset of the snapshot                  |
| zfscleanupbadoffsiteholds | `w`   | parent dataset of snapshots with self-referencing offsite holds |
| zfsresume             | `w`       | resumable destination                           |
| dataset_actions.py    | `w`       | dataset for snapshot/delete/hold/rollback/umount |
| retention_actions.py  | `w`       | pool-level pre-flight check before prune        |
| zfsdailybackup        |           | orchestrates other scripts                      |
| zfssendoffsite        |           | orchestrates other scripts                      |

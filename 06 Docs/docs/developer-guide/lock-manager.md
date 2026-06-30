# ZFS Lock Manager

## Overview

A hierarchical dataset lock manager for ZFS utilities that prevents conflicting operations on datasets, with support for multiple lock types, stale lock detection, and interactive conflict resolution.

## Design Points

- **Lock storage**: `/run/lock/zfs/` (cleared on reboot)
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
/run/lock/zfs/
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
- Sets: $ZFSLOCK_ID on success

##### Lock release

`zfslock_release <lock_id>`

`zfslock_release_all`

- Release all locks held by current PID

##### Conflict checking

`zfslock_check <dataset> <type>`

- Returns: 0=no conflict, 1=conflict exists
- Sets: $ZFSLOCK_CONFLICT_INFO

##### Interactive conflict resolution

`zfslock_wait_or_resolve <dataset> <type> [description]`

- Returns: 0=acquired, 1=user aborted, 2=user skipped

When stdin is not a TTY or `ZFSUTILITIES_HEADLESS=Y` is set, the function does not
prompt. It logs a `FATAL:` message and returns 1 immediately. This prevents cron or
headless profile runs from hanging indefinitely.

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

`zfslockctl list [dataset]`                  List active locks


`zfslockctl status <dataset> `            Check lock status


`zfslockctl release <lock_id> `          Force release a lock


`zfslockctl cleanup`                               Remove stale locks


`zfslockctl wait <dataset> <type>`    Wait for lock availability

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
2. The PID exists but is a different process (check /proc/$pid/cmdline)

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
    for lockfile in /run/lock/zfs/.locks/"${dataset_encoded}"*; do
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
- On success, the global array `ZFSLOCK_IDS` contains the acquired lock file
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

## Integration Points

Scripts that have lock integration:

| Script           | Lock Type | Dataset(s) / pools               |
| ---------------- | --------- | -------------------------------- |
| zfs-send-receive | `w`       | source, destination              |
| zfsretain        | `w`       | filesystem being retained        |
| zfscleanup       | `w`       | per dataset (via `zfsretain`)    |
| zfsdelsnap       | `w`       | snapshot's parent dataset        |
| zfsdelallsnaps   | `w`       | parent dataset (via `zfsdelsnap`)|
| zfsdelfs         | `x`       | top-level dataset being destroyed|
| zfsscruball      | `w`       | pool being scrubbed              |
| zfsdailybackup   |           | orchestrates other scripts       |
| zfssendoffsite   |           | orchestrates other scripts       |

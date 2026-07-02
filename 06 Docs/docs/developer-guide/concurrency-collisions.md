# Concurrency and Collision Risks in ZFS Utilities

This document describes what happens when two or more ZFS Utilities jobs run at
the same time, and which collisions are **not** currently prevented by the
existing locking code.

## What is protected today

The project has a hierarchical lock manager, `zfslockmanager`, that supports
three lock types on ZFS datasets:

| Type | Meaning | Conflicts with |
|------|---------|----------------|
| `r`  | Shared read (metadata/listing) | `w`, `x` |
| `w`  | Exclusive write (snapshots, send/receive) | `r`, `w`, `x` |
| `x`  | Exclusive destroy (dataset/snapshot destruction) | `r`, `w`, `x` |

Locks are stored in `/run/lock/zfs/.locks/` and are automatically released on
process exit. The manager also detects hierarchical conflicts: a lock on
`pool/parent` blocks conflicting locks on descendants, and locks on descendants
block a parent `x` lock.

Only two modules currently use the lock manager:

* **`zfs-send-receive`** acquires a `w` lock on the source dataset **and** a `w`
  lock on the destination dataset before creating or choosing a snapshot and
  before each transfer.
* **`zfsdelsnap`** acquires a `w` lock on the parent dataset before deleting a
  snapshot.

The GUI no longer globally serializes `Backup`, `Offsite`, and `Restore`.
All three may run concurrently; per-dataset locks still serialize them when
they touch the same datasets. Each GUI runner keeps its Python-level log
output in its own session log so concurrent runs do not cross-write.

Everything else runs without coordination.

## Job types and the resources they touch

| Job type | Entry points | Datasets / pools | Snapshots | Config / state files | Other shared resources |
|----------|--------------|------------------|-----------|----------------------|------------------------|
| **Backup** | `zfsdailybackup`, GUI Backup, profiles | Source + dest pools (e.g. `threeamigos/proxmox`, `NVME1` → `fivebays`) | Creates `@dailybackup-*` | Reads backup steps, pools | `/tmp/zfsnextsnap_*`, session log, rsync endpoints |
| **Offsite** | `zfssendoffsite`, GUI Offsite, profiles | Source pools → offsite pool | Creates `@offsite-*`, applies holds | Reads offsite pool list | `/tmp/zfsnextsnap_*`, session log |
| **Restore** | `zfsrestore`/`zfsfullcopy`, GUI Restore, profiles | Source backup pool → dest pool | Copies/rolls back snapshots | Restore params | iSCSI LUNs if restoring zvols |
| **Prune** | `zfscleanup`/`zfsretain`, GUI Retention, profiles | All configured/online pools | **Destroys** snapshots | Retention policies | Calls `delsnap` |
| **Scrub** | `zfsscruball`, GUI Pools, profiles, systemd timers | One or more pools | — | `scrub_state.json` | `/tmp/zfsscruball.state` |
| **Dataset destroy** | GUI Datasets → Delete | Selected subtree | Destroys all snapshots | — | iSCSI manifest, encrypted-LUN config |
| **Snapshot delete** | GUI Datasets → Delete selected snapshots | Selected snapshots | Destroys snapshots | — | Holds must be released first |
| **Checkagainst** | `zfscheckagainst`, GUI Checkagainst | Counterpart pools/datasets | Reads snapshot GUIDs | `checkagainst` table | — |

## Unaccounted-for collision scenarios

The scenarios below are ordered roughly by severity.

### 1. Prune running at the same time as a backup or restore

`zfscleanup` and `zfsretain` never lock the datasets they iterate. Only the
individual `delsnap` calls lock the parent dataset for the moment of deletion.
This means a prune job can enumerate snapshots, decide which ones to delete, and
start deleting them while another job is in the middle of a long-running
`zfs-send-receive` that depends on those snapshots.

**Possible outcomes**

* An incremental send fails because its base snapshot was deleted.
* A restore that needs an older common snapshot cannot find it.
* A resumable receive cannot be resumed because the snapshot it depends on is
gone.
* The prune itself logs a "Dataset is busy" warning (`skipbusy='Y'`) and skips
a snapshot that was actually deleted by the concurrent job, but the warning is
not treated as an error.

**How to trigger it**

Start a restore or offsite backup, then click **Prune** in the GUI while the
first job is still sending/receiving. There is no GUI check that prevents this.

### 2. Two prune jobs on the same pool

Nothing prevents two `zfscleanup` runs (GUI + profile, profile + profile, or GUI
+ GUI) from targeting the same pool at the same time. Both enumerate the same
snapshot list and try to delete the same snapshots. One will succeed; the other
will get "dataset does not exist" or "Dataset is busy" warnings that are logged
and ignored.

### 3. Dataset destroy colliding with backup, restore, or prune

`zfsdelfs` does not call `zfslockmanager`. It destroys a dataset and all its
snapshots without acquiring an `x` lock. If a backup is sending/receiving that
dataset, or a prune is deleting snapshots inside it, the concurrent destroy can
fail partway through, leave partial state, or cause the other job to fail.

This is especially risky for restores: a full-copy restore calls `delfs` on the
destination before receiving, and `zfsdelfs` does not coordinate with another
restore or backup targeting the same destination.

### 4. Snapshot-name collisions

Snapshot names are generated from the current minute. Both bash and Python
generators now serialize name generation with a brief global lock and record the
issued name in a one-minute reservation file (`/run/lock/zfs/.snapname.reserved`).

* Bash callers use `zfssnapbuild`, which writes `/tmp/zfsnextsnap_<caller>`.
* Python callers use `feature_config.generate_snapshot_name()` and
  `generate_offsite_snapshot_name()`, which write
  `/root/.config/zfsutilities_nextsnap` and
  `/root/.config/zfsutilities_offsite_nextsnap`.

The lock prevents two jobs from generating a name at the exact same instant. Two
jobs that run sequentially within the same minute still receive the same name,
but any collision on the same dataset is prevented by the per-dataset `w` locks
from Phases 1 and 2.

### 5. Config and state-file write races

**Resolved by Phase 4.**

Shared JSON/state files now use advisory `flock` locking with one lock file per
data file. Python callers use `fcntl.flock`; the `zfsconfig` bash helper uses
the system `flock` command on the same lock files so both environments
interoperate.

| File | Writers | Readers | Lock file |
|------|---------|---------|-----------|
| `/root/.config/zfsutilities.json` | GUI (`save_config`), `zfsconfig` bash helper | Bash scripts via `zfsconfig`, `profile_runner.py` at startup | `/run/lock/zfs/.config.lock` |
| `/root/.config/zfsutilities-history.json` | `BackupRunner._finish()`, `profile_runner.py` | Logs tab, dashboard | `/run/lock/zfs/.history.lock` |
| `/var/log/zfsutilities/sessions/.log_index.json` | `BackupRunner`, `profile_runner.py`, Logs tab | Logs tab | `/run/lock/zfs/.log_index.lock` |
| `/root/.config/zfsutilities/scrub_state.json` | `ScrubQueue` | `ScrubQueue` on restart | `/run/lock/zfs/.scrub_state.lock` |

The following files are still not lock-protected because they are outside the
scope of this phase:

| File | Writers | Readers | Risk |
|------|---------|---------|------|
| `/etc/rtslib-fb-target/expected-backstores.txt` | `zfsdelfs`, `new-vm-disk`, `remove-vm-disk`, two-node scripts | Two-node target rebuild | Concurrent modifications can leave an inconsistent manifest. |
| `/etc/iscsi-encrypted-luns.conf` | Same as above | Same as above | Encrypted LUN entries can be duplicated or lost. |
| `/var/log/zfsutilities/rsync-backup.log` | rsync pull/push steps | Users | `BackupRunner` truncates this file when a runner starts; concurrent runners interleave or lose output. |

### 6. Scrub jobs managed by multiple uncoordinated paths

There are at least four ways a scrub can be started or controlled:

* GUI Pools tab (`ScrubQueue` in `scrub_manager.py`).
* Scheduled scrub profiles via `profile_runner.py`.
* Standalone `zfsscruball`.
* Systemd timers (if `system_scrub_weekly` / `system_scrub_monthly` are enabled).

Scrub actions do not use the hierarchical dataset lock manager because a scrub
has no dependency on backup, restore, prune, or dataset destruction.  Instead,
each action consults the live `zpool status` scrub state and skips itself when
the requested transition is invalid (for example, pausing a pool that is not
currently scanning).  ZFS itself rejects invalid transitions, so the worst-case
outcome of concurrent scrub control is a logged warning, not data loss.

### 7. Headless `profile_runner.py` has no global lock

`profile_runner.py run <profile>` is what cron executes. It:

* Sets `ZFSUTILITIES_HEADLESS=Y`, which makes `zfslock_wait_or_resolve` **abort**
  immediately on a dataset lock conflict instead of waiting.
* Has no global mutex, so the same profile can be started again by cron while the
  previous instance is still running.
* Can run at the same time as the GUI, a manual CLI script, or another profile.

Because headless mode aborts on lock conflict, a scheduled job can fail with
`rc=9` just because a manual operation happened to be holding a dataset lock at
that moment.

### 8. Checkagainst reads while deletions are in progress

`zfscheckagainst` reads snapshot lists and GUIDs to compare source and
counterpart datasets. It does not lock the datasets it reads. If a prune or
dataset destroy runs concurrently, `zfscheckagainst` may see a snapshot that
disappears before it finishes, or it may report spurious mismatches.

### 9. GUI tab isolation is incomplete

The GUI only blocks `Backup`, `Offsite`, and `Restore` from starting while
another of those three is running. It does **not** block:

* Prune while Backup/Offsite/Restore is running.
* Dataset destroy while Backup/Offsite/Restore/Prune is running.
* Scrub while any of the above is running.
* Snapshot creation while any of the above is running.
* Checkagainst while Prune is running.

Each of these has its own `running` flag (`retention_runner`,
`dataset_runner`, `scrub_queue`, etc.), but there is no cross-type guard.

The Backup, Offsite, and Restore tabs now offer an optional **Pause scrubs on
source/destination pools during each step** setting. When enabled, the runner
pauses scrubs on the pools used by the current send/receive step and resumes
them after the step finishes. This closes the scrub-versus-backup/restore gap
for those pools, but it does not block other concurrent actions such as prune
or destroy.

### 10. Two restores targeting the same destination

A restore does lock the source and destination datasets inside
`zfs-send-receive`, but that protection is per-dataset and per-step. Two restore
jobs can both decide to destroy the same destination dataset (via `delfs` inside
`zfsfullcopy`) before the send/receive lock is acquired, because the destroy
happens before or during destination preparation.

## Severity summary

| Risk | Severity | Currently detected? | Currently prevented? |
|------|----------|---------------------|----------------------|
| Prune deletes snapshot needed by running backup/restore | **High** | Only as a logged WARN | **Yes** (Phase 1 bash locks + Phase 2 GUI pre-check) |
| Dataset destroy collides with backup/restore/prune | **High** | Error from `zfs` | **Yes** (Phase 1 bash `x` lock + Phase 2 GUI pre-check) |
| Two restores targeting same destination | **High** | Per-dataset lock after prepare | **Yes** (Phase 1 bash `x` lock on `zfsdelfs` + `w` lock in `zfs-send-receive`) |
| Snapshot-name collision | **Medium** | `zfs snapshot` fails | **Partially** (Phase 3 global lock + one-minute reservation) |
| Concurrent snapshot creation on the same dataset | **High** | Rollback during receive | **Yes** (lock before snapshot in `zfs-send-receive`) |
| Two prune jobs on same pool | **Medium** | Logged warnings | **Yes** (Phase 1 per-dataset `w` lock) |
| History/log-index/config write races | **Medium** | Silent data loss or stale UI | **Yes** (Phase 4 file locking) |
| Uncoordinated scrub paths | **Low** | Live state check + `zpool scrub` reject | **Yes** (live `zpool status` checks) |
| Headless profile overlap | **Medium** | `rc=9` on lock conflict | **Yes** (Phase 5 per-profile `flock`) |
| Checkagainst during deletions | **Low** | Spurious mismatch or error | **No** |
| rsync log truncation/interleaving | **Low** | Mixed or missing output | **No** |

## Short-term operational guidance

Until the gaps are closed:

1. Do not run **Prune**, **Destroy Dataset**, or **Scrub** while a
   **Backup**, **Offsite**, or **Restore** is in progress. If you want scrubs
   paused automatically during these jobs, enable the **Pause scrubs on
   source/destination pools during each step** option on the corresponding tab.
2. Avoid scheduling profiles so close together that they can overlap.
3. Do not run `zfsscruball` from the command line while the GUI is managing
   scrubs.
4. Do not edit retention policies or pool lists while a headless profile is
   running.
5. If a scheduled profile fails with `rc=9`, check whether another job was
   holding the dataset lock at that time.

## Longer-term hardening recommendations

The safest fix is to extend the existing `zfslockmanager` usage to the jobs that
mutate shared resources:

1. **`zfscleanup` / `zfsretain`** should acquire at least a `w` lock on each
dataset before enumerating its snapshots, and hold it for the duration of prune
on that dataset. This prevents prune vs. backup/restore collisions and
overlapping prunes.
2. **`zfsdelfs`** should acquire an `x` lock on the dataset being destroyed
before teardown and hold it until destruction is complete.
3. **Snapshot-name generation** is now serialized with a brief global lock and a
   one-minute reservation file. The naming format was kept unchanged; a future
   enhancement could add a sequence suffix if guaranteed distinct same-minute
   names become required.
4. **Config/state-file writes** should use `flock` around the read-modify-write
sequence, or move critical shared updates through a single writer process.
5. **Scrub management** should have a single authority: either consolidate on
`ScrubQueue` and disable direct `zfsscruball`/systemd scrub, or have all paths
consult a shared scrub lock/state file.
6. **GUI** should add cross-type guards so that destructive or state-changing
actions (prune, destroy, scrub) cannot start while a backup/offsite/restore is
running, and vice versa.
7. **`profile_runner.py`** should acquire a global per-profile or per-job-type
lock before starting, so cron cannot launch a second instance of the same
profile while the first is still running.

## Recently resolved (Phase 2)

Python/GUI mutators now participate in the lock manager:

* New `07 GTK + Python/zfs_lock_manager.py` reads and writes the same JSON
  lock files as `zfslockmanager`, so Python operations interoperate with bash
  locks.
* Direct Python mutators acquire `w` locks:
  - `dataset_actions.on_datasets_snapshot` locks the target dataset.
  - `dataset_actions._delete_snapshots` locks the parent datasets.
  - `dataset_actions._release_holds` locks the parent datasets.
  - `dataset_actions.on_datasets_hold` locks the parent datasets.
  - `dataset_actions.on_datasets_rollback` locks the parent dataset.
* Bash-wrapped GUI mutators perform a pre-flight conflict check instead of
  holding Python locks (to avoid cross-PID hierarchy deadlock):
  - `dataset_actions._delete_datasets` aborts if any selected dataset is
    already locked.
  - `retention_actions.on_retention_prune` aborts if any selected pool is
    already locked.
* Scrub control has been moved out of the lock manager.  `scrub_manager`
  consults live `zpool status` before start/pause/resume/stop, and `zfsscruball`
  no longer acquires a pool lock while scrubbing.

## Recently resolved (Phase 3)

Snapshot-name generation is now coordinated across bash and Python:

* Both `zfssnapbuild` and `feature_config.generate_snapshot_name()` /
  `generate_offsite_snapshot_name()` acquire a brief global lock
  (`/run/lock/zfs/.snapname.lock`) while building a name.
* Each generated name is recorded in a one-minute reservation file
  (`/run/lock/zfs/.snapname.reserved`) shared between bash and Python.
* The existing snapshot naming format is unchanged.

## Recently resolved (Phase 6)

Integration tests now exercise concurrent profile execution end-to-end, and
user documentation explains the new behavior.

* `tests/python/test_profile_integration.py` runs two profiles in separate
  subprocesses and verifies:
  - Disjoint datasets: both profiles succeed.
  - Same dataset: one profile fails safely with a lock conflict rather than
    corrupting data.
  - Backup + prune: the prune step is blocked by the backup's dataset lock and
    exits safely.
* `06 Docs/docs/user-guide/profiles.md` documents what profiles are, how they
  run concurrently, and how conflicts are resolved.
* The severity summary table above has been refreshed to mark Phase 5
  (headless profile overlap) and remaining Phase 1 gaps (two prunes on the same
  pool, two restores to the same destination, scrub path coordination) as
  resolved.

## Recently resolved (snapshot-before-lock)

`zfs-send-receive` now acquires `w` locks on the source and destination datasets
before it creates or selects a snapshot.  This closes the race where two
concurrent jobs could create snapshots on the same dataset, causing a later
incremental receive with `-F` to roll back a newer ZFSutilities-generated
snapshot.

* `zfs-send-receive` reordered so locks precede `zfs snapshot` and
  `getcommonsnap`.
* `tests/test-zfs-send-receive-dryrun` checks the lock-before-snapshot ordering.

## Related files and tests

- `zfslockmanager` — lock implementation.
- `zfs-send-receive` — example of per-dataset `w` locking.
- `zfsdelsnap` — example of parent-dataset `w` locking.
- `zfscleanup`, `zfsretain`, `zfsdelfs`, `zfsscruball`, `zfscheckagainst` —
  lock-protected by Phase 1.
- `zfssnapbuild` and `07 GTK + Python/feature_config.py` — snapshot-name
  generation, now coordinated by Phase 3.
- `07 GTK + Python/zfs_lock_manager.py` — Python lock client.
- `07 GTK + Python/profile_runner.py`, `backup_runner.py`, `scrub_manager.py`,
  `dataset_actions.py`, `retention_actions.py` — Python dispatch paths.
- `tests/test-zfslockmanager` — covers the lock manager itself.
- `tests/test-zfssnapbuild` — Phase 3 bash coverage.
- `tests/python/test_zfs_lock_manager.py`,
  `tests/python/test_dataset_actions.py`,
  `tests/python/test_retention_actions.py`,
  `tests/python/test_scrub_manager.py`,
  `tests/python/test_feature_config.py` — Phase 2 and Phase 3 coverage.

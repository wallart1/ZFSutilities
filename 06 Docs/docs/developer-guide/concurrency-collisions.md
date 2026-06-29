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
  lock on the destination dataset before each transfer.
* **`zfsdelsnap`** acquires a `w` lock on the parent dataset before deleting a
  snapshot.

The GUI also prevents `Backup`, `Offsite`, and `Restore` runners from starting
while another of those three is already running.

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

Snapshot names are generated from the current minute and are written to a
snapfile:

* Bash callers use `zfssnapbuild`, which writes `/tmp/zfsnextsnap_<caller>`.
* Python callers use `feature_config.generate_snapshot_name()` and
  `generate_offsite_snapshot_name()`, which write
  `/root/.config/zfsutilities_nextsnap` and
  `/root/.config/zfsutilities_offsite_nextsnap`.

There is no lock around reading or writing these files, and the generated name
only has minute precision. If two backup or offsite jobs start in the same
minute, they can produce the same `@label-<timestamp>-<bucket>` name and both try
to create the same snapshot. The second `zfs snapshot` fails with "snapshot
already exists".

This can happen with:

* A GUI Backup and a scheduled profile backup starting in the same minute.
* Two scheduled profiles that both include a backup step.
* A manual `zfsdailybackup` run while a profile backup is active.

### 5. Config and state-file write races

Several files are read and written without file locking:

| File | Writers | Readers | Risk |
|------|---------|---------|------|
| `/root/.config/zfsutilities.json` | GUI (`save_config`), `zfsconfig` bash helper | Bash scripts via `zfsconfig`, `profile_runner.py` at startup | A GUI save while a bash script is reading the file can produce a partially-written or inconsistent config. Two concurrent GUI saves can overwrite each other. |
| `/root/.config/zfsutilities-history.json` | `BackupRunner._finish()`, `profile_runner.py` | Logs tab, dashboard | Writes are atomic (`tempfile` + `os.replace`), but there is no inter-process lock. Two concurrent runs can load the same list, each append an entry, and the second write loses the first. |
| `/var/log/zfsutilities/sessions/.log_index.json` | `BackupRunner`, `profile_runner.py`, Logs tab | Logs tab | Atomic writes but no lock; concurrent updates can drop entries or revert status. |
| `/root/.config/zfsutilities/scrub_state.json` | `ScrubQueue` | `ScrubQueue` on restart | No atomic write; concurrent GUI/profile scrub management can corrupt or lose queue state. |
| `/etc/rtslib-fb-target/expected-backstores.txt` | `zfsdelfs`, `new-vm-disk`, `remove-vm-disk`, two-node scripts | Two-node target rebuild | Concurrent modifications can leave an inconsistent manifest. |
| `/etc/iscsi-encrypted-luns.conf` | Same as above | Same as above | Encrypted LUN entries can be duplicated or lost. |
| `/var/log/zfsutilities/rsync-backup.log` | rsync pull/push steps | Users | `BackupRunner` truncates this file when a runner starts; concurrent runners interleave or lose output. |

### 6. Scrub jobs managed by multiple uncoordinated paths

There are at least four ways a scrub can be started or controlled:

* GUI Pools tab (`ScrubQueue` in `scrub_manager.py`).
* Scheduled scrub profiles via `profile_runner.py`.
* Standalone `zfsscruball`.
* Systemd timers (if `system_scrub_weekly` / `system_scrub_monthly` are enabled).

These paths do not coordinate. For example:

* The GUI queue may think a scrub is active while `zfsscruball` also starts one.
* `profile_runner.py` can resume a scrub that the GUI paused.
* `zfsscruball pause` may pause a scrub that the GUI queue believes is running.

ZFS itself rejects a second scrub on the same pool, but pause/resume/stop races
are not prevented.

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

### 10. Two restores targeting the same destination

A restore does lock the source and destination datasets inside
`zfs-send-receive`, but that protection is per-dataset and per-step. Two restore
jobs can both decide to destroy the same destination dataset (via `delfs` inside
`zfsfullcopy`) before the send/receive lock is acquired, because the destroy
happens before or during destination preparation.

## Severity summary

| Risk | Severity | Currently detected? | Currently prevented? |
|------|----------|---------------------|----------------------|
| Prune deletes snapshot needed by running backup/restore | **High** | Only as a logged WARN | **No** |
| Dataset destroy collides with backup/restore/prune | **High** | Error from `zfs` | **No** |
| Two restores targeting same destination | **High** | Per-dataset lock after prepare | **No** |
| Snapshot-name collision | **Medium** | `zfs snapshot` fails | **No** |
| Two prune jobs on same pool | **Medium** | Logged warnings | **No** |
| History/log-index/config write races | **Medium** | Silent data loss or stale UI | **No** |
| Uncoordinated scrub paths | **Medium** | `zpool scrub` may reject | **No** |
| Headless profile overlap | **Medium** | `rc=9` on lock conflict | **No** |
| Checkagainst during deletions | **Low** | Spurious mismatch or error | **No** |
| rsync log truncation/interleaving | **Low** | Mixed or missing output | **No** |

## Short-term operational guidance

Until the gaps are closed:

1. Do not run **Prune**, **Destroy Dataset**, or **Scrub** while a
   **Backup**, **Offsite**, or **Restore** is in progress.
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
3. **Snapshot-name generation** should be serialized (e.g. a single lock file or
a monotonically increasing counter) so two jobs cannot produce the same name.
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

## Related files and tests

- `zfslockmanager` — lock implementation.
- `zfs-send-receive` — example of per-dataset `w` locking.
- `zfsdelsnap` — example of parent-dataset `w` locking.
- `zfscleanup`, `zfsretain`, `zfsdelfs`, `zfsscruball`, `zfscheckagainst` —
  currently unprotected.
- `07 GTK + Python/profile_runner.py`, `backup_runner.py`, `scrub_manager.py`,
  `dataset_actions.py`, `retention_actions.py` — Python dispatch paths.
- `tests/test-zfslockmanager` — covers the lock manager itself, but does not
  exercise the higher-level scripts.

# Concurrency and Collision Risks in ZFS Utilities

This document describes what happens when two or more ZFS Utilities jobs run at
the same time, and how each collision is fenced. The governing rule for every
fence: serialize the smallest critical section that protects the data —
per-dataset, per-file, or per-state-file — never per-pool or GUI-wide gates.

## What is protected today

The project has a hierarchical lock manager, `zfslockmanager`, that supports
three lock types on ZFS datasets:

| Type | Meaning | Conflicts with |
|------|---------|----------------|
| `r`  | Shared read (metadata/listing) | `w`, `x` |
| `w`  | Exclusive write (snapshots, send/receive) | `r`, `w`, `x` |
| `x`  | Exclusive destroy (dataset/snapshot destruction) | `r`, `w`, `x` |

Locks are stored in `/run/lock/zfsutilities/.locks/` and are automatically released on
process exit. The manager detects hierarchical conflicts: a lock on
`pool/parent` blocks conflicting locks on descendants, and locks on descendants
block a parent `x` lock. A same-process acquire of a **stronger** type converts
the held lock in place (`w` → `x`): the lock file is rewritten atomically after
the normal conflict check, so a caller never needs a release/re-acquire window
to escalate. Weaker requests keep the stronger held type.

The following scripts and modules currently use the lock manager:

* **`zfs-send-receive`** acquires a `w` lock on the source dataset **and** a `w`
  lock on the destination dataset before creating or choosing a snapshot and
  before each transfer. When a forced full copy must destroy the destination
  first, the destination lock stays held: `zfsdelfs`'s `x` acquisition by the
  same shell converts the held `w` lock in place, so no other job can slip
  between a release and a re-acquisition.
* **`zfsrestoresendstream`** acquires a `w` lock on the destination dataset
  before each `zfs receive`.
* **`zfsresume`** acquires a `w` lock on the resumable destination dataset before
  reading or aborting its receive resume token.
* **`zfsmount`** and **`zfsunmount`** acquire a `w` lock on each dataset before
  changing its mount state.
* **`zfsdelfs`** acquires an `x` lock on the dataset being destroyed before
  teardown and holds it until destruction is complete.
* **`zfsdelsnap`**, **`zfsdelallsnaps`**, **`zfsmassdelsnaps`** and related
  snapshot-deletion helpers acquire a `w` lock on the parent dataset before
  deleting snapshots.
* **`zfscheckagainst`** takes a non-blocking shared `r` lock on the
  candidate's dataset and on every counterpart dataset it reads, for the
  duration of the check. A busy dataset is treated exactly like an offline
  pool (rc 6, deletion blocked for safety) — it never waits, so concurrent
  prunes on mirrored trees refuse each other but cannot deadlock. A caller
  already holding the dataset (a prune's `w`) re-enters and proceeds.
* **`zfsretain`** / **`zfscleanup`** acquire a `w` lock on each filesystem
  before pruning its snapshots.
* **VM-disk lifecycle scripts** (`clone-vm`, `zfsclone-vm`, `move-vm-disk`,
  `rename-vm-disk`, `remove-vm-disk`, `resize-vm-disk`, `new-vm-disk`,
  `sever-vm-clone`, `archive-vm`, `unarchive-vm`)
  acquire `w` or `x` locks on the affected zvols.
* **Hold helpers** (`zfshold`, `zfsholds`, `zfsdelallholds`, etc.) acquire
  `w`/`r` locks on the affected datasets.
* **GUI dataset actions** (`python/dataset_actions.py`,
  `python/datasets_page.py`, `python/disk_actions.py`,
  `python/pool_growth_dialogs.py`, `python/pool_create_wizard.py`,
  `python/pool_migrate_dialogs.py`, `python/profile_dialogs.py`, and the
  enrollment modules) use the Python `zfs_lock_manager` client to lock the
  datasets they touch — per-dataset locks for dataset operations, a write
  lock on the pool root for pool-wide operations. Each action runs on its
  own `BackupRunner` (created per action by the `DatasetActionRunners`
  tracker in `python/runner_factory.py`); there is no shared-runner gate.

The GUI dose not globally serialize `Backup`, `Offsite`, and `Restore`,
and dataset actions are not serialized behind a single shared runner
either. Transfer runs and dataset actions may proceed concurrently;
per-dataset locks serialize them when they touch the same datasets.

Everything else runs without coordination.

## Job types and the resources they touch

| Job type | Entry points | Datasets / pools | Snapshots | Config / state files | Other shared resources |
|----------|--------------|------------------|-----------|----------------------|------------------------|
| **Backup** | `zfsdailybackup`, GUI Backup, profiles | Source + dest pools (e.g. `threeamigos/proxmox`, `NVME1` → `fivebays`) | Creates `@dailybackup-*` | Reads backup steps, pools | `/run/zfsutilities/nextsnap_*`, session log, rsync endpoints |
| **Offsite** | `zfssendoffsite`, GUI Offsite, profiles | Source pools → offsite pool | Creates `@offsite-*`, applies holds | Reads offsite pool list | `/run/zfsutilities/nextsnap_*`, session log |
| **Restore** | `zfsrestore`/`zfsfullcopy`, GUI Restore, profiles | Source backup pool → dest pool | Copies/rolls back snapshots | Restore params | iSCSI LUNs if restoring zvols |
| **Prune** | `zfscleanup`/`zfsretain`, GUI Retention, profiles | All configured/online pools | **Destroys** snapshots | Retention policies | Calls `delsnap` |
| **Scrub** | `zfsscruball`, GUI Pools, profiles, systemd timers | One or more pools | — | `scrub_state.json` | `/run/zfsutilities/zfsscruball.state` |
| **Dataset destroy** | GUI Datasets → Delete | Selected subtree | Destroys all snapshots | — | iSCSI manifest, encrypted-LUN config |
| **Snapshot delete** | GUI Datasets → Delete selected snapshots | Selected snapshots | Destroys snapshots | — | Holds must be released first |
| **Checkagainst** | `zfscheckagainst`, GUI Checkagainst | Counterpart pools/datasets | Reads snapshot GUIDs | `checkagainst` table | — |

## Collision scenarios

The scenarios below are ordered roughly by severity.

### 1. Prune running at the same time as a backup or restore

`zfsretain` acquires a `w` lock on each dataset before enumerating its
snapshots, and `zfscleanup` initializes the lock manager so each `zfsretain`
invocation can acquire those per-dataset locks. The lock is held for the
duration of pruning on that dataset, not just for the moment of deletion.
This prevents a prune job from deleting snapshots that a concurrent backup or
restore still needs.

**Possible outcomes**

* A concurrent prune is blocked by the dataset `w` lock held by `zfs-send-receive`
  until the send/receive step finishes.
* Two prune jobs targeting the same dataset serialize on the per-dataset `w` lock.

**How to trigger it**

Start a restore or offsite backup, then click **Prune** in the GUI while the
first job is still sending/receiving. The per-dataset `w` locks acquired by
`zfs-send-receive` block the prune from touching the same datasets.

### 2. Two prune jobs on the same pool

`zfsretain` acquires the per-dataset `w` lock **before** enumerating the
dataset's snapshots and holds it for the whole prune on that dataset, so two
`zfscleanup` runs (GUI + profile, profile + profile, or GUI + GUI) targeting
the same pool serialize per dataset: the second run re-enumerates only after
the first finished and can never act on a stale snapshot list. A
`tests/test-zfsretain` ordering test pins the lock-before-enumeration
sequence. Residual "dataset does not exist" warnings can still appear when
a snapshot is removed by something outside the lock manager (a manual
`zfs destroy`); the deletion itself is idempotent, so those warnings are
logged and ignored by design.

### 3. Dataset destroy colliding with backup, restore, or prune

`zfsdelfs` acquires an `x` lock on the target dataset before teardown. If a
backup is sending/receiving that dataset, or a prune is deleting snapshots
inside it, the concurrent destroy will block until the existing lock is
released, preventing partial teardown or torn iSCSI state.

Full-copy restores hold the destination lock continuously: `zfsdelfs`'s `x`
acquisition by the same shell converts the held `w` lock in place
(same-PID lock conversion, see *What is protected today*). There is no
release/re-acquire window, while two restores targeting the same
destination still serialize on the one lock.

### 4. Snapshot-name collisions

Snapshot names are generated from the current minute. Both bash and Python
generators serialize name generation with a brief global lock and record the
issued name in a one-minute reservation file (`/run/lock/zfsutilities/.snapname.reserved`).

* Bash callers use `zfssnapbuild`, which writes `/run/zfsutilities/nextsnap_<caller>`.
* Python callers use `feature_config.generate_snapshot_name()` and
  `generate_offsite_snapshot_name()`, which write
  `/var/lib/zfsutilities/nextsnap` and
  `/var/lib/zfsutilities/nextsnap_offsite`.

The lock prevents two jobs from generating a name at the exact same instant. Two
jobs that run sequentially within the same minute still receive the same name,
but any collision on the same dataset is prevented by the per-dataset `w` locks.

### 5. Config and state-file write races

Shared JSON/state files use advisory `flock` locking with one lock file per
data file. Python callers use `fcntl.flock`; the `zfsconfig` bash helper uses
the system `flock` command on the same lock files so both environments
interoperate.

| File | Writers | Readers | Lock file |
|------|---------|---------|-----------|
| `/var/lib/zfsutilities/config.json` | GUI (`save_config`), `zfsconfig` bash helper | Bash scripts via `zfsconfig`, `profile_runner.py` at startup | `/run/lock/zfsutilities/.config.lock` |
| `/var/lib/zfsutilities/history.json` | `BackupRunner._finish()`, `profile_runner.py` | Logs tab, dashboard | `/run/lock/zfsutilities/.history.lock` |
| `/var/log/zfsutilities/sessions/.log_index.json` | `BackupRunner`, `profile_runner.py`, Logs tab | Logs tab | `/run/lock/zfsutilities/.log_index.lock` |
| `/var/lib/zfsutilities/scrub_state.json` | `ScrubQueue` (GUI Pools tab/Dashboard, `profile_runner.py` scrub profiles) | `ScrubQueue` on restart, and via `reload()` inside each transactional tick | `/run/lock/zfsutilities/.scrub_state.lock` |
| `/etc/rtslib-fb-target/expected-backstores.txt` | `lib/iscsi-lib.sh` helpers (used by `zfsdelfs` teardown/rebuild, the VM-disk lifecycle scripts, and their ssh-heredoc copies), `safe-iscsi-save` regeneration, `repair-iscsi-luns`, `reconcile-iscsi-state` | Two-node target rebuild, Dashboard | `/run/lock/zfsutilities/.iscsi_manifest.lock` |
| `/etc/zfsutilities/iscsi-encrypted-luns.conf` | Same writer set, through the same lib helpers | `iscsi-add-encrypted-luns`, `restart-iscsi-services`, `safe-iscsi-save` boot-config generation, Dashboard | `/run/lock/zfsutilities/.encrypted_luns.lock` |

Every read-modify-write of the two iSCSI authority files runs under its
file lock (the compact `( flock -x 9; … ) 9>>"$lock"` idiom in bash, the
matching `file_locking` context managers in Python, so bash and GUI
writers interoperate). Removals rewrite via a temp file and an atomic
rename with the original mode copied, so unlocked readers never observe a
partial file. Regenerations re-list the live targetcli state inside the
lock, so a backstore another flow appended while the regenerating script
ran cannot be dropped. `reconcile-iscsi-state` nests the file lock inside
its existing `iscsi-lio` fence — the nesting order is always fence first,
file second.

`/var/log/zfsutilities/rsync-backup.log` uses a reader/writer split on
`/run/lock/zfsutilities/.rsync_log.lock`: `BackupRunner` holds the
**shared** lock for the lifetime of each rsync append handle, and the
once-per-day truncate (when the mtime is from a previous day) takes the
**exclusive** lock. Concurrent runners still append side by side — chunks
from two runs may interleave, which is by design — but a midnight
truncate can no longer land under a live appender. The bash-side twin in
`command_builders.py` gives `rsync-pull.log` the same split with a
co-located `<log>.lock` file on the host where the log lives.

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

The persistent `ScrubQueue` state can be mutated concurrently by the GUI Pools
tab and a headless scrub profile. The mechanisms that keep the instances from
diverging:

* **Every queue mutation is transactional.** `ScrubQueue.transaction()` holds
  the `scrub_state.json` write lock across the whole reload-mutate-save cycle
  (the same pattern `pause_scrubs_for_pools` already used, generalized), and
  every mutator (`add_pending`, `remove_pools`, `pause_pools`, `resume_pools`,
  `set_order`, `set_target`) reloads persisted state inside that lock before
  mutating. A save by one process can therefore never overwrite a change the
  other process just made — the pre-transaction lost-update window is closed,
  and a `tests/python/test_scrub_manager.py` test pins it (two instances
  mutating in sequence lose no entry).
* The GUI Pools tab, the Dashboard, and the headless scrub-profile loop all
  drive the queue through `tick_locked()`: reload + tick as one transaction.
  Pool-state gathering stays outside the lock; the queue's own `zpool
  start/pause` calls run inside it (they are sub-second). On contention the
  cycle is skipped with a WARN and state converges from live `zpool status`
  on the next cycle; mutators wait up to 10 s under the same rule.
* Queue buckets are disjoint: re-queuing a pool (`add_pending`) removes it from
  the `finished` bucket, and `tick()` drops `finished` entries for pools that no
  longer exist, so the summary counts never double-count a pool.
* A pool that is absent from the live pool list (offline, exported, or a
  transient `zpool list` failure in that process) is dropped from the
  `active`/`paused`/`finished` buckets only after several consecutive ticks
  (`MAX_POOL_MISSING_TICKS`), so a single missed observation cannot evict a
  scrubbing pool from the persisted state and make another process re-detect
  it as an external scrub on every refresh.

The scrub-start paths are deliberately **not** consolidated onto a single
authority. `zfsscruball` and the systemd scrub timers act directly on ZFS,
which rejects a conflicting scrub transition itself, and the queue adopts
external scrubs as `active`/`paused` on every tick. Consolidating would
reduce the number of concurrent start paths without protecting any data —
the worst case today is a logged `zpool` rejection.

### 7. Headless `profile_runner.py` waits for profile and dataset locks

`profile_runner.py run <profile>` is what cron executes. It:

* Acquires a per-profile advisory lock. If the same profile is already running,
  the new invocation waits up to `ZFSUTILITIES_PROFILE_LOCK_TIMEOUT` (default
  600) for the prior run to finish.
* Exports `ZFSLOCK_HEADLESS_WAIT_SECONDS=600` to its bash steps, so
  `zfslock_wait_or_resolve` waits up to 10 minutes for a dataset lock before
  aborting instead of failing immediately.
* Can run at the same time as the GUI, a manual CLI script, or another profile,
  as long as they touch disjoint datasets.

If the timeouts expire, the blocked invocation logs a warning and exits cleanly
(with code `0` for a duplicate-run suppression, or `rc=9` for a dataset-level
abort) so cron does not treat a transient overlap as an error.

### 8. Checkagainst reads while deletions are in progress

`zfscheckagainst` reads snapshot lists and GUIDs to compare source and
counterpart datasets, under non-blocking shared `r` locks on the candidate's
dataset and each counterpart it actually consults. A concurrent prune or
dataset destroy therefore serializes against the check (its `w`/`x` conflicts
with the `r`), so the check cannot see a snapshot that disappears mid-compare
or report a spurious verdict. A **busy** dataset — one whose lock cannot be
taken — is treated exactly like an offline pool: rc 6, deletion blocked for
safety, and the refusal WARN names the holder. The locks are never waited
for, so two prunes on mirrored trees refuse each other's checks instead of
deadlocking; each catches up on its next run. Multiple checkagainst runs
overlap freely, because `r` is shared.

### 9. GUI **tab** isolation is incomplete

The GUI doesn't gate one operation type on another: `Backup`, `Offsite`,
`Restore`, and every dataset action may be in flight at the same time (each on
its own runner), and `Retention` pruning performs a pre-flight lock check that
aborts if any selected pool is already locked. Nothing in the GUI, other than
dataset locks, blocks:

* Dataset destroy while Backup/Offsite/Restore/Prune is running.
* Scrub while any of the above is running.
* Snapshot creation while any of the above is running.
* Checkagainst while Prune is running.

Each of these has its own `running` flag (`backup_runner`,
`retention_runner`, the per-action dataset runners, `scrub_queue`, etc.), but
there is no cross-type guard — the per-dataset locks are the fence, by
design. A GUI-wide gate would serialize operations that touch disjoint
datasets without protecting any additional data.

The Backup, Offsite, and Restore tabs offer an optional **Pause scrubs on
source/destination pools during each step** setting. When enabled, the runner
pauses scrubs on the pools used by the current send/receive step and resumes
them after the step finishes. This closes the scrub-versus-backup/restore gap
for those pools, but it does not block other concurrent actions such as prune
or destroy.

### 10. Two restores targeting the same destination

A restore locks the source and destination datasets inside
`zfs-send-receive` for the whole full copy, including the destructive
destination preparation: the destination `w` lock is held continuously and
`zfsdelfs`'s `x` acquisition converts it in place (same-PID lock conversion).
Two restore jobs targeting the same destination therefore serialize
completely on that one lock — the second waits (or aborts under the headless
timeout) at its own destination acquisition; there is no window in which one
restore's destroy can interleave with the other's preparation or receive.

## Severity summary

| Risk | Severity | Currently detected? | Currently prevented? |
|------|----------|---------------------|----------------------|
| Prune deletes snapshot needed by running backup/restore | **High** | Only as a logged WARN | **Yes** (bash locks + GUI pre-check) |
| Dataset destroy collides with backup/restore/prune | **High** | Error from `zfs` | **Yes** (bash `x` lock + GUI pre-check) |
| Two restores targeting same destination | **High** | Per-dataset lock, held through prepare | **Yes** (continuous lock; `delfs` converts `w` → `x` in place) |
| Snapshot-name collision | **Medium** | `zfs snapshot` fails | **Yes** for data safety (per-dataset `w` lock + idempotent create); same-minute same-name across datasets is intended backup-set behavior |
| Concurrent snapshot creation on the same dataset | **High** | Rollback during receive | **Yes** (lock before snapshot in `zfs-send-receive`) |
| Two prune jobs on same pool | **Medium** | Logged warnings | **Yes** (per-dataset `w` lock before enumeration) |
| History/log-index/config write races | **Medium** | Silent data loss or stale UI | **Yes** (file locking) |
| Manifest / encrypted-LUN conf write races | **Medium** | Inconsistent manifest or lost entries | **Yes** (per-file flock; bash and Python interoperate) |
| rsync log truncation under a live appender | **Low** | Missing output | **Yes** (shared-append / exclusive-truncate lock) |
| Uncoordinated scrub paths | **Low** | Live state check + `zpool scrub` reject | **Yes** (live `zpool status` checks; not consolidated by design) |
| Scrub state lost update (GUI vs profile) | **Medium** | Queue entry silently dropped | **Yes** (transactional reload-mutate-save) |
| Headless profile overlap | **Medium** | Waits, then `rc=9` only on timeout | **Yes** (per-profile `flock` + timed dataset waits) |
| Checkagainst during deletions | **Low** | Spurious mismatch or error | **Yes** (non-blocking `r` locks; busy → deletion blocked) |

## Operational guidance

1. If a scheduled profile fails with `rc=9`, check whether another job was
   holding the dataset lock at that time.
2. If a checkagainst-gated deletion reports "deletion blocked for safety"
   with a *locked* counterpart, another operation was reading or writing that
   dataset; re-run the prune once it finishes.
3. If a scrub-profile log shows "scrub queue state busy", the GUI (or another
   profile) held the state lock for that cycle; the queue converges on the
   next 10-second poll without action.

## Hardening decisions

1. ~~`zfscleanup`/`zfsretain` should lock before enumerating.~~ **Resolved:**
   the per-dataset `w` lock precedes snapshot enumeration and is held for the
   whole prune on that dataset.
2. ~~`zfsdelfs` should hold an `x` lock through destruction.~~ **Resolved.**
3. **Snapshot-name generation** keeps its global lock and one-minute
   reservation file. The reservation file *records* issued names (bash and
   Python share it); it does not reject or deduplicate, and nothing in
   production consults it for a decision. Same-minute name reuse across
   datasets is the backup-set contract (one run stamps one name across every
   dataset it touches), and same-dataset creation is idempotent under the
   `w` lock, so no sequence suffix is warranted — a suffix would break the
   shared-name contract.
4. **Config/state-file writes** use `flock` around each read-modify-write;
   the two iSCSI authority files and the rsync log joined the locked set
   (see scenario 5).
5. **Scrub management** keeps multiple start paths and does **not**
   consolidate on a single authority: ZFS itself rejects conflicting scrub
   transitions, the queue adopts external scrubs, and the queue's own state
   is transactional. Consolidation would reduce concurrency without
   protecting data.
6. **GUI** deliberately has no cross-type guards: per-dataset locks are the
   fence (see scenario 9).
7. ~~`profile_runner.py` should hold a per-profile lock.~~ **Resolved:** a
   per-profile `flock` with a configurable wait, plus headless dataset-lock
   waits, see scenario 7.

## Notes

### Python/GUI mutators participate in the lock manager:

* New `python/zfs_lock_manager.py` reads and writes the same JSON
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
* `scrub_manager` consults live `zpool status` before start/pause/resume/stop.

### Snapshot-name generation is coordinated across bash and Python:

* Both `zfssnapbuild` and `feature_config.generate_snapshot_name()` /
  `generate_offsite_snapshot_name()` acquire a brief global lock
  (`/run/lock/zfsutilities/.snapname.lock`) while building a name.
* Each generated name is recorded in a one-minute reservation file
  (`/run/lock/zfsutilities/.snapname.reserved`) shared between bash and Python.
* The existing snapshot naming format is unchanged.

### Integration tests exercise concurrent profile execution end-to-end, and
user documentation explains the new behavior.

* `tests/python/test_profile_integration.py` runs two profiles in separate
  subprocesses and verifies:
  - Disjoint datasets: both profiles succeed.
  - Same dataset: one profile fails safely with a lock conflict rather than
    corrupting data.
  - Backup + prune: the prune step is blocked by the backup's dataset lock and
    exits safely.
* `docs/docs/user-guide/profiles.md` documents what profiles are, how they
  run concurrently, and how conflicts are resolved.

### `zfs-send-receive` acquires `w` locks on the source and destination datasets
before it creates or selects a snapshot.  This closes the race where two
concurrent jobs could create snapshots on the same dataset, causing a later
incremental receive with `-F` to roll back a newer ZFSutilities-generated
snapshot.

* `zfs-send-receive` reordered so locks precede `zfs snapshot` and
  `getcommonsnap`.
* `tests/test-zfs-send-receive-dryrun` checks the lock-before-snapshot ordering.

### The two iSCSI recovery mutators — `reconcile-iscsi-state` and
`iscsi-restore-luns` — share three authorities (the live LIO tree,
`saveconfig.json`, and the expected-backstores manifest) with no mutual
exclusion. They hold the lock manager's global `iscsi-lio` `w` lock
for their whole mutate+persist extent (`zfslock_acquire_lio_mutator`).
The key is deliberately slash-free, so the hierarchy walk treats it as a
flat lock and the two-node forwarder ignores it; the semantics are
refuse, never wait — the refusal WARN names the running sibling by pid
and command, and a lock-manager error also refuses (fail closed). Two
residue classes died with the fence: reconcile's manifest regen can no
longer install a comment-only manifest when every apply action failed,
and its summary prints apply-truthful counts (`created: N of M`)
instead of plan totals. Found live by the j17 journey (F-040); verified
by unit suites and the journey's fenced-race gate.

* `tests/test-reconcile-iscsi-state`,
  `tests/test-iscsi-restore-luns` — refusal, manifest guard, counts.
* The fence is scoped to the two recovery mutators only; the everyday
  LIO writers (`new-vm-disk`, `remove-vm-disk`, `setup-iscsi-targets`,
  …) serialize on the per-file locks described in scenario 5 instead —
  a flat refuse-never-wait global fence would serialize every VM-disk
  lifecycle operation against every other.

### Same-PID lock conversion closes the full-copy window

`zfslock_acquire` treats a same-PID acquire of a stronger type as an
in-place conversion: the lock file is rewritten atomically (type,
description, acquired timestamp; the holder's pid and script are kept)
after the normal conflict check runs against every other holder. The
Python client mirrors the rule, and the two-node forwarder asks the
storage-side agent (`zfslockmanager-remote convert`) to convert a
forwarded lock — an older agent keeps the held (weaker) type with a VERB
note, never a weaker fence, until both nodes run this version.
`zfs-send-receive` holds its destination lock through the destructive
full-copy preparation instead of releasing and re-acquiring around
`zfsdelfs`.

* `tests/test-zfslockmanager` — conversion matrix (upgrade in place,
  weaker keeps the stronger type, foreign descendant `r` blocks a `w`→`x`
  conversion).
* `tests/test-zfslockmanager-remote` — `convert` subcommand: strengthens
  live-held locks, refuses weakening, refuses stale locks and paths
  outside the lock directory.
* `tests/test-zfs-send-receive-dryrun` — the destination lock is held
  continuously through the destroy, with exactly one destination
  acquisition per dataset.

## Related files and tests

- `zfslockmanager`, `zfslockmanager-remote` — lock implementation and the
  two-node agent (including `convert`).
- `zfs-send-receive` — example of per-dataset `w` locking and same-PID
  conversion.
- `zfsdelsnap` — example of parent-dataset `w` locking.
- `zfscleanup`, `zfsretain`, `zfsdelfs`, `zfscheckagainst` —
  lock-protected (`zfsscruball` coordinates through ZFS itself, by design).
- `zfssnapbuild` and `python/feature_config.py` — snapshot-name
  generation.
- `python/zfs_lock_manager.py` — Python lock client.
- `python/file_locking.py` — per-file flock helpers shared with bash.
- `lib/iscsi-lib.sh` — locked manifest/encrypted-conf helpers.
- `python/profile_runner.py`, `backup_runner.py`, `scrub_manager.py`,
  `dataset_actions.py`, `retention_actions.py` — Python dispatch paths.
- `tests/test-zfslockmanager` — covers the lock manager itself.
- `tests/test-zfsretain` — lock-before-enumeration ordering.
- `tests/test-zfscheckagainst` — `r`-lock refusal and release paths.
- `tests/test-safe-iscsi-save` — lib helper locking, blocked while held,
  concurrent appends.
- `tests/python/test_scrub_manager.py` — transactional no-lost-update.
- `tests/python/test_backup_runner.py` — truncate-waits-for-appender.
- `tests/test-zfssnapbuild` — bash coverage.
- `tests/python/test_zfs_lock_manager.py`,
  `tests/python/test_dataset_actions.py`,
  `tests/python/test_retention_actions.py`,
  `tests/python/test_scrub_manager.py`,
  `tests/python/test_feature_config.py`.

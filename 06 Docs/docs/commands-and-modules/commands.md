# Commands

Scripts intended to be run directly from the shell (as root).

!!! note "Scripts are on PATH after deployment"
    After running [`deploy-version`](two-node.md#deploy-version-repo-root) and `switch-version`,
    scripts are available on `PATH` via `/usr/local/lib/zfsutilities/bin`.
    Run them by name (e.g., `sudo zfsdailybackup`). Use `./scriptname`
    only when running directly from a repository checkout.

Cross-references: globals mentioned per entry are documented in full on the
[Global Variables](../developer-guide/global-variables.md) page; shared
arrays and on-disk tables are on [Data Structures](../developer-guide/data-structures.md).

## Jump to

- [`backup-installed-programs`](#backup-installed-programs)
- [`datesubtract`](#datesubtract)
- [`getlinecount`](#getlinecount)
- [`PVE-send-to-archive`](#pve-send-to-archive)
- [`unroot`](#unroot)
- [`watchit`](#watchit)
- [`zfsaddisk`](#zfsaddisk)
- [`zfscleanup`](#zfscleanup)
- [`zfscleanupbadoffsiteholds`](#zfscleanupbadoffsiteholds)
- [`zfsdailybackup`](#zfsdailybackup)
- [`zfsdelallsnaps`](#zfsdelallsnaps)
- [`zfsdelfs`](#zfsdelfs)
- [`zfsdelholds`](#zfsdelholds)
- [`zfs-diagnose-busy`](#zfs-diagnose-busy)
- [`zfsfullcopy`](#zfsfullcopy)
- [`zfsgetashift`](#zfsgetashift)
- [`zfsgetsnapage`](#zfsgetsnapage)
- [`zfsgetsendsize`](#zfsgetsendsize)
- [`zfsholds`](#zfsholds)
- [`zfslistkeys`](#zfslistkeys)
- [`zfsloadkeys`](#zfsloadkeys)
- [`zfslockctl`](#zfslockctl)
- [`zfslockmanager-test`](#zfslockmanager-test)
- [`zfsmaketest`](#zfsmaketest-archived)
- [`zfsmount`](#zfsmount)
- [`zfsreadthru`](#zfsreadthru)
- [`zfsrecurse`](#zfsrecurse)
- [`zfsrestore`](#zfsrestore)
- [`zfsrestoresendstream`](#zfsrestoresendstream)
- [`zfsresizevol`](#zfsresizevol)
- [`zfsresume`](#zfsresume)
- [`zfsscruball`](#zfsscruball)
- [`zfssend`](#zfssend)
- [`zfssendoffsite`](#zfssendoffsite)
- [`zfsoffsiteretain`](#zfsoffsiteretain)
- [`zfssetarcsize`](#zfssetarcsize)
- [`zfsshowbigstuff`](#zfsshowbigstuff)
- [`zfsshowholds`](#zfsshowholds)
- [`zfsshowtuneables`](#zfsshowtuneables)
- [`zfsshowzpooldevices`](#zfsshowzpooldevices)
- [`retire-vm`](#retire-vm)
- [`unretire-vm`](#unretire-vm)
- [`zfsstatus`](#zfsstatus)
- [`zfsunmount`](#zfsunmount)
- [`zfswatcharc`](#zfswatcharc)

---

### `backup-installed-programs`

Saves a list of manually-installed apt packages to a file called
`installed-programs` in the current directory.

```bash
sudo backup-installed-programs
```

**Arguments:** none.

**Globals:** none.

Uses `apt-mark showmanual` to generate the list. Logs success or failure.
On failure, removes the partial output file.

---

### `datesubtract`

Calculates the number of days, months, and years between two dates.

```bash
datesubtract "2025-01-01" "2026-01-01"
```

**Arguments:**

| Argument | Description                                   |
| -------- | --------------------------------------------- |
| `$1`     | Start date (any format accepted by `date -d`) |
| `$2`     | End date                                      |

**Globals:** none.

Outputs days, months (decimal), and years (decimal).

---

### `getlinecount`

Counts files and total lines in the project root directory (non-recursive).
Hard-coded to `/NFS1/dan(NFS1)/zfsutilities-dev`. Intended as a development
utility.

**Arguments:** none.

**Globals:** none.

---

### `PVE-send-to-archive`

Sends a single ZFS dataset to an archive file on disk using
`zfs send`. This creates a \*.zfssendstream file in the host's filesystem. Intended for long-term cold storage.

**Arguments:** none (configured via in-script variables).

**In-script variables** (set before running):

| Variable          | Description                                                                                                | Reference                                                                          |
| ----------------- | ---------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `$subtrees`       | List of ZFS pools/filesystems where the source dataset(s) resides                                          | —                                                                                  |
| `$includes`       | Substring list to match dataset names                                                                      | [Selection](../developer-guide/global-variables.md#dataset-and-snapshot-selection) |
| `$destinationdir` | Directory where the archive file will be placed                                                            | —                                                                                  |
| `$archivename`    | Short name of the output archive file                                                                      | —                                                                                  |
| `$proxmoxconfig`  | Path to the Proxmox VM configuration file. If specified, this file is stored along with the archive files. | —                                                                                  |

---

### `unroot`

Relinquishes root privileges by switching to a normal user.

```bash
unroot username
```

**Arguments:**

| Argument | Default   | Description       |
| -------- | --------- | ----------------- |
| `$1`     | `$suuser` | User to switch to |

**Globals:**

| Variable  | Role                                 |
| --------- | ------------------------------------ |
| `$suuser` | Default user if `$1` is not provided |

Has no effect if not currently running as root.

---

### `watchit`

Displays a periodically-refreshing terminal-based view of ZFS pool and dataset status for a
given subtree. Refreshes every 30 seconds.

```bash
watchit pool-or-dataset
```

**Arguments:**

| Argument | Description              |
| -------- | ------------------------ |
| `$1`     | Pool or dataset to watch |

**Globals:** none.

Uses `Watchall/watchall` with `zpool list` and `zfs list` output.

---

### `zfsaddisk`

Adds a virtual disk to a Proxmox VM. Works around a Proxmox GUI issue where
incorrect disk numbers are sometimes assigned.

```bash
sudo zfsaddisk <vmid> <disk-number> <storage-name> <size-GiB>
```

**Arguments:**

| Argument | Description                                                          |
| -------- | -------------------------------------------------------------------- |
| `$1`     | Proxmox VM ID (numeric)                                              |
| `$2`     | Disk number for the new disk (must be higher than any existing disk) |
| `$3`     | Proxmox storage name where the disk will reside                      |
| `$4`     | Size of the new disk in GiB                                          |

**Globals:** none.

Prompts for confirmation before issuing the `qm set` command.

---

### `zfscleanup`

Applies retention policies to one pool, to the pools registered in the JSON
config, or — when no pools are configured — to all online pools.

```bash
sudo zfscleanup <pool> only <label> [overrides]
```

**Arguments:**

| Argument | Default                                                   | Description                                                     |
| -------- | --------------------------------------------------------- | --------------------------------------------------------------- |
| `$1`     | pools from JSON config, or all online pools if none exist | Pool or subtree to clean up                                     |
| `$2`     | recurse                                                   | `'only'` = do not recurse                                       |
| `$3`     | —                                                         | Snapshot label that must match (required)                       |
| `$4`     | —                                                         | Override string (see [`zfsoverrides`](modules.md#zfsoverrides)) |

**Behavior:**

- If `$1` is given, only that pool/subtree is processed.
- Otherwise, `zfscleanup` reads `config.pools` via [`poolarray`](modules.md#zfsconfig).
  If the configured pool list is empty, it falls back to `zpool list -Ho name`
  so retention is not silently skipped.
- Pools in the list that are not currently online are skipped.

**Globals:**

| Variable                    | Role                                                              | Reference                                                                     |
| --------------------------- | ----------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| `$autoproceed`              | `'Y'` = skip prompts                                              | [Execution Control](../developer-guide/global-variables.md#execution-control) |
| `$dryrun`                   | `'Y'` = report without deleting                                   | [Execution Control](../developer-guide/global-variables.md#execution-control) |
| `$releaseholds`             | `'Y'` = release holds before deletion                             | [Execution Control](../developer-guide/global-variables.md#execution-control) |
| `$leadingqualifiestodelete` | Passed to `zfsretain` for `checkagainst` counterpart construction | [Retention](../developer-guide/global-variables.md#retention)                 |

Calls [`zfsretain`](modules.md#zfsretain) for each pool.

---

### `zfs-diagnose-busy`

Diagnoses why a ZFS dataset or snapshot cannot be destroyed. Called
automatically by `zfsdelsnap`, `zfsdelfs`, `remove-vm-disk`, `retire-vm`, and
`clone-vm` whenever `zfs destroy` fails with a "dataset is busy" error.

```bash
source $mydir/zfs-diagnose-busy
diagnose_dataset_busy <dataset_or_snapshot> [stderr_from_failed_destroy]
```

**Checks performed (in order):**

| Check                | What it looks for                                             |
| -------------------- | ------------------------------------------------------------- |
| Clone dependents     | `zfs list -o clones` shows non-`-` values                     |
| ZFS holds            | `zfs holds` lists tags on the snapshot                        |
| Mounted / open files | `mounted=yes` plus `fuser`/`lsof` on the mountpoint           |
| Active send/receive  | `receive_resume_token` present, or `zfs send` process running |
| Bookmarks            | `zfs list -t bookmark` shows references to the snapshot       |
| iSCSI LUN            | `targetcli` shows the zvol as a backstore/LUN                 |
| Running VM           | `qm status` reports `running` for the VM ID                   |
| NFS/SMB share        | `sharenfs` or `sharesmb` is not `off`                         |

If no specific cause is found, a fallback message suggests checking for open
files via `fuser` or `lsof`, or verifying whether a pool scrub/resilver is in
progress.

The Python GUI equivalent is `gui_helpers.diagnose_dataset_busy()`, used by
dataset and snapshot delete actions.

---

### `zfscleanupbadoffsiteholds`

Removes incorrectly self-referencing holds from an offsite pool. A
self-referencing hold is one where the hold name is `offsite-<pool>` on a
snapshot that already resides in `<pool>` — a bug from earlier versions of
`applyholds`.

```bash
sudo zfscleanupbadoffsiteholds <pool> [dryrun]
```

**Arguments:**

| Argument | Description                                            |
| -------- | ------------------------------------------------------ |
| `$1`     | Pool to inspect                                        |
| `$2`     | `dryrun` = show what would be removed without removing |

**Globals:** none.

Lists snapshot holds via `zfs list -Hrt snapshot ... | xargs zfs holds -H`,
then releases any hold whose name matches `offsite-<pool>` on a snapshot within
that same pool.

---

### `zfsdailybackup`

Main daily backup orchestrator. Runs the full backup sequence:

1. Pull rsync backups from remote hosts (`rocky`, `COMPUTE_HOST`, `STORAGE_HOST`)
2. Snapshot `threeamigos/proxmox` and copy to `fivebays`
3. Snapshot `NVME1` and copy to `fivebays`
4. Apply retention policies to all affected pools

```bash
sudo zfsdailybackup [overrides]
```

**Arguments:**

| Argument | Description                                                                                                     |
| -------- | --------------------------------------------------------------------------------------------------------------- |
| `$1`     | Optional override string passed to [`zfsoverrides`](modules.md#zfsoverrides) as `name='value'; name='value'; …` |

**In-script defaults (overridable):**

| Variable                     | Default | Purpose                                                          |
| ---------------------------- | ------- | ---------------------------------------------------------------- |
| `pull_rocky`                 | `'Y'`   | Pull rsync backup from host `rocky`                              |
| `pull_tweety`                | `'Y'`   | Pull rsync backup from `$COMPUTE_HOST` (two-node only)           |
| `pull_stewie`                | `'Y'`   | Pull rsync backup from `$STORAGE_HOST`                           |
| `backup_threeamigos_proxmox` | `'Y'`   | Snapshot and copy `threeamigos/proxmox` → `fivebays`             |
| `backup_NVME1`               | `'Y'`   | Snapshot and copy `NVME1` → `fivebays`                           |
| `prune`                      | `'Y'`   | Run retention via `zfscleanup` on affected pools after the sends |
| `autoresume`                 | `'Y'`   | Allow resumable-receive tokens to be picked up                   |
| `receive_F_option`           | `'F'`   | Force rollback of destination modifications on receive           |

**Global variables read:**

| Variable                                    | Role                                                                               | Reference                                                                          |
| ------------------------------------------- | ---------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `$dryrun`                                   | `'Y'` = simulate without writing (skips rsync, sends, prune, and snapfile cleanup) | [Execution Control](../developer-guide/global-variables.md#execution-control)      |
| `$nextsnap`                                 | Generated by `zfssnapbuild` at start of run; shared across all sends               | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)             |
| `$releaseholds`                             | Passed to `zfscleanup` during prune                                                | [Execution Control](../developer-guide/global-variables.md#execution-control)      |
| `$includes`, `$excludes`, `$startwith`      | Dataset filters forwarded to `zfs-send-receive`                                    | [Selection](../developer-guide/global-variables.md#dataset-and-snapshot-selection) |
| `NODE_MODE`, `STORAGE_HOST`, `COMPUTE_HOST` | Node-config vars that gate the two-node rsync-pull steps                           | [Node Configuration](../developer-guide/global-variables.md#node-configuration)    |

Example overrides:

```bash
sudo zfsdailybackup "backup_NVME1='N'; prune='N'"
sudo zfsdailybackup "dryrun='Y'"
```

---

### `zfsdelallsnaps`

Deletes all snapshots of a dataset, with safety checks via [`zfsdelsnap`](modules.md#zfsdelsnap).

```bash
sudo zfsdelallsnaps <dataset> [overrides]
```

**Arguments:**

| Argument | Description                                            |
| -------- | ------------------------------------------------------ |
| `$1`     | Dataset (or subtree) whose snapshots should be deleted |
| `$2`     | Optional override string                               |

**Globals:**

| Variable                           | Role                                                                | Reference                                                                          |
| ---------------------------------- | ------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `$includes`, `$excludes`, `$depth` | Forwarded to `zfsbuildfsarray` (with `buildfsarraytype='snapshot'`) | [Selection](../developer-guide/global-variables.md#dataset-and-snapshot-selection) |
| `$releaseholds`                    | `'Y'` = release holds before deletion                               | [Execution Control](../developer-guide/global-variables.md#execution-control)      |
| `$autoproceed`                     | `'Y'` = skip per-deletion prompts                                   | [Execution Control](../developer-guide/global-variables.md#execution-control)      |
| `$dryrun`                          | `'Y'` = report without deleting                                     | [Execution Control](../developer-guide/global-variables.md#execution-control)      |

Each snapshot is individually verified via [`zfscheckagainst`](modules.md#zfscheckagainst)
before deletion.

If a snapshot cannot be destroyed, [`zfs-diagnose-busy`](modules.md#zfs-diagnose-busy)
is automatically called to diagnose the specific cause.

**Return code:**

- `0` — all snapshots were deleted successfully, or there were no snapshots to delete.
- `1` — one or more snapshots could not be deleted.

---

### `zfsdelfs`

Deletes a dataset along with all of its snapshots and holds.

```bash
sudo zfsdelfs <subtree> [includes] [excludes] [startwith] [overrides]
```

This is the ordinary way to destroy a ZFS dataset (or a filtered subtree of
datasets). For non-VM datasets the operation is a straightforward
`zfs destroy`; the iSCSI handling described below only applies to zvols that
follow the `vm-<N>-disk-<N>` naming convention in a two-node configuration.

**Arguments:**

| Argument | Description                                   |
| -------- | --------------------------------------------- |
| `$1`     | Subtree to delete                             |
| `$2`     | Optional includes filter (sets `$includes`)   |
| `$3`     | Optional excludes filter (sets `$excludes`)   |
| `$4`     | Optional startwith filter (sets `$startwith`) |
| `$5`     | Optional overrides                            |

**Globals:**

| Variable                                         | Role                                                                                   | Reference                                                                          |
| ------------------------------------------------ | -------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `$includes`, `$excludes`, `$startwith`, `$depth` | Forwarded to `zfsbuildfsarray`                                                         | [Selection](../developer-guide/global-variables.md#dataset-and-snapshot-selection) |
| `$autoproceed`, `$dryrun`, `$releaseholds`       | Execution control passed through to `zfsdelallsnaps`                                   | [Execution Control](../developer-guide/global-variables.md#execution-control)      |
| `NODE_MODE`, `COMPUTE_HOST`                      | Determines whether iSCSI teardown/rebuild is attempted, and how `qm status` is queried | [Node Configuration](../developer-guide/global-variables.md#node-configuration)    |

**Data structures produced:**

| Structure                                                                                  | Reference                                                                                                          |
| ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| [`ISCSI_TEARDOWN`](../developer-guide/data-structures.md#iscsi_teardown-associative-array) | Populated before `zfs destroy`; consumed by `zfs-send-receive` to rebuild LUNs after the replacement `zfs receive` |

Calls `zfsdelallsnaps` first to clear snapshots, then destroys the dataset.
For VM-disk zvols in two-node mode it automatically tears down the matching
iSCSI LUN/backstore before `zfs destroy` and records the teardown so that
`zfs-send-receive` can rebuild the LUN afterwards. During teardown it removes
the backstore from `/etc/rtslib-fb-target/expected-backstores.txt` and, if the
zvol is encrypted, from `/etc/iscsi-encrypted-luns.conf`. The `zfs-send-receive`
rebuild path re-adds those entries after the replacement `zfs receive` so the
manifests remain consistent.

**Clone dependency check:** If any dataset in the deletion list has ZFS clone
dependents (another zvol was created from one of its snapshots), `zfsdelfs`
aborts before touching anything and displays a `[ZFS clone dependents — cannot
delete]` annotation. Run [`promote-vm-clone`](two-node.md#promote-vm-clone-both)
on a dependent VM first to cut the dependency, then retry.

**Destroy diagnostics:** If `zfs destroy` fails (e.g. "dataset is busy"),
`zfsdelfs` automatically calls [`zfs-diagnose-busy`](#zfs-diagnose-busy) to
report the specific cause — holds, open files, iSCSI LUNs, running VMs, etc.

---

### `zfsdelholds`

Releases ZFS snapshot holds matching an optional pattern across a subtree.

```bash
sudo zfsdelholds <subtree> [snap-prefix] [depth]
```

**Arguments:**

| Argument | Description                                            |
| -------- | ------------------------------------------------------ |
| `$1`     | Subtree to process                                     |
| `$2`     | Optional leading substring of snapshot names to filter |
| `$3`     | Optional recursion depth (overrides `$depth`)          |

**Globals:**

| Variable       | Role                                            | Reference                                                                          |
| -------------- | ----------------------------------------------- | ---------------------------------------------------------------------------------- |
| `$depth`       | Default recursion depth if `$3` is not supplied | [Selection](../developer-guide/global-variables.md#dataset-and-snapshot-selection) |
| `$autoproceed` | `'Y'` = skip per-hold prompts                   | [Execution Control](../developer-guide/global-variables.md#execution-control)      |

---

### `zfsfullcopy`

Performs a two-step full dataset restore. Intended to be called by other
scripts (not run directly — use [`zfsrestore`](#zfsrestore) for interactive use).

Step 1: Full copy from the oldest available snapshot

Step 2: Incremental copy to pull in all remaining snapshots

**Arguments:** none (configured via globals).

**Globals:**

| Variable                            | Required | Role                                                                     | Reference                                                                     |
| ----------------------------------- | -------- | ------------------------------------------------------------------------ | ----------------------------------------------------------------------------- |
| `$restorefs`                        | yes      | Dataset to restore (source)                                              | —                                                                             |
| `$destfs`                           | yes      | Destination pool/subpool                                                 | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)        |
| `$sourcefsremovequalifiers`         | no       | Leading qualifiers to strip from `$restorefs`before prepending `$destfs` | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)        |
| `$nextsnap`                         | no       | If set, limits copy to this snapshot                                     | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)        |
| `$label`                            | no       | Snapshot label to match                                                  | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)        |
| `$autoproceed`, `$force`, `$dryrun` | no       | Forwarded to `zfs-send-receive`                                          | [Execution Control](../developer-guide/global-variables.md#execution-control) |

---

### `zfsgetashift`

Displays the ashift value and corresponding block size for a disk partition.

```bash
sudo zfsgetashift /dev/sdd1
```

**Arguments:**

| Argument | Description                |
| -------- | -------------------------- |
| `$1`     | Disk partition device path |

**Globals:** none.

| ashift | Block size |
| ------ | ---------- |
| 9      | 512 B      |
| 12     | 4 KiB      |
| 13     | 8 KiB      |

Useful when creating a new pool. `ashift` is the power of 2 that will be the pool's basic block size. (2^ashift)

---

### `zfsgetsnapage`

Returns the age of a ZFS snapshot in days.

```bash
zfsgetsnapage pool/dataset@snapshot
```

**Arguments:**

| Argument | Description   |
| -------- | ------------- |
| `$1`     | Snapshot name |

**Globals:** none.

Uses `zfs get creation` (epoch seconds) and calculates the difference from
the current time. Can be sourced by other scripts (`source $mydir/zfsgetsnapage`)
and called as `getsnapage <snapshot>`.

---

### `zfsgetsendsize`

Calculates the size of a ZFS send stream for a given snapshot.

```bash
zfsgetsendsize pool/dataset@snapshot
```

**Arguments:**

| Argument | Description   |
| -------- | ------------- |
| `$1`     | Snapshot name |

**Globals:** none.

Outputs both raw bytes and human-readable size (e.g., `8925341712 8.3G`).
Returns an empty string if the size cannot be determined.

---

### `zfsholds`

Lists all snapshot holds in a subtree.

```bash
zfsholds <subtree> [depth]
```

**Arguments:**

| Argument | Description                               |
| -------- | ----------------------------------------- |
| `$1`     | Subtree to inspect                        |
| `$2`     | Optional depth limit (overrides `$depth`) |

**Globals:**

| Variable | Role                    | Reference                                                                          |
| -------- | ----------------------- | ---------------------------------------------------------------------------------- |
| `$depth` | Default recursion depth | [Selection](../developer-guide/global-variables.md#dataset-and-snapshot-selection) |

See also: [`zfsshowholds`](#zfsshowholds) for a simpler version without depth support.

---

### `zfslistkeys`

Lists ZFS datasets with available encryption keys (keystatus = available,
keylocation != prompt).

```bash
sudo zfslistkeys [dataset]
```

**Arguments:**

| Argument | Description                                |
| -------- | ------------------------------------------ |
| `$1`     | Optional dataset or pool to limit the scan |

**Globals:** none. If `$1` is omitted, iterates over all imported pools.

---

### `zfsloadkeys`

Loads ZFS encryption keys from a USB key device labeled `ZFSkeys`.

```bash
sudo zfsloadkeys
```

**Arguments:** none.

**Globals:** none.

Mounts `/dev/disk/by-label/ZFSkeys` at `/mnt/ZFSkeys`, runs `zfs load-key -a`
and `zfs mount -a`, then unmounts and LUKS-closes the key device.

---

### `zfslockctl`

Command-line tool for inspecting and managing ZFS dataset locks.

```bash
sudo zfslockctl <command> [args]
```

**Subcommands:**

| Command   | Arguments          | Description                                        |
| --------- | ------------------ | -------------------------------------------------- |
| `list`    | `[dataset]`        | List active locks (optionally filtered by dataset) |
| `status`  | `<dataset>`        | Check lock status for a dataset                    |
| `release` | `<lock-id>`        | Force-release a lock                               |
| `cleanup` | —                  | Remove stale locks (held by dead processes)        |
| `wait`    | `<dataset> <type>` | Wait until a dataset becomes available             |

Lock types: `r` (shared read), `w` (exclusive write), `x` (exclusive destroy).

**Globals:** none.

**Data structures:**

| Structure                                                      | Reference                         |
| -------------------------------------------------------------- | --------------------------------- |
| [Lock files](../developer-guide/data-structures.md#lock-files) | Read from `/run/lock/zfs/.locks/` |

See also: [`zfslockmanager`](modules.md#zfslockmanager).

---

### `zfslockmanager-test`

Automated test suite for [`zfslockmanager`](modules.md#zfslockmanager). Runs 28 tests covering:

- Basic acquire/release
- Same-dataset conflicts (r/w/x combinations)
- Hierarchy conflicts (ancestor/descendant)
- Stale lock detection
- Re-entrant locking (same PID)
- Concurrent access blocking
- Path encoding (`%2F`, `%40`)
- `zfslockctl` CLI commands

```bash
sudo zfslockmanager-test
```

**Arguments:** none.

**Globals:** none.

All 28 tests should pass.

---

### `zfsmaketest` (Archived)

> **Inactive.** This script has been moved to `03 Stash/zfsmaketest` and is not
> currently in use. It will be revisited when work on the automated test
> framework resumes.

Creates test datasets and runs copy scenarios to validate
[`zfs-send-receive`](modules.md#zfs-send-receive). Creates `nvme/test` and
`nvme/test2`.

```bash
sudo zfsmaketest
```

**Arguments:** none (in-script variables).

**In-script variables** (set before running):

| Variable               | Values            | Role                                                                                     | Reference                                                              |
| ---------------------- | ----------------- | ---------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `$doincrementals`      | `'Y'` / `'N'`     | Full vs incremental copies                                                               | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive) |
| `$dointermediates`     | `'Y'` / `'N'`     | Include intermediate snapshots                                                           | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive) |
| `$commsnap_mostrecent` | `'OLDEST'` / `''` | `'OLDEST'` = start from oldest snapshot on source; otherwise most recent common snapshot | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive) |

---

### `zfsmount`

Mounts or unmounts all filesystems in a subtree.

```bash
sudo zfsmount <mount|unmount> <subtree>
```

**Arguments:**

| Argument | Description          |
| -------- | -------------------- |
| `$1`     | `mount` or `unmount` |
| `$2`     | Subtree to process   |

**Globals:**

| Variable       | Role                            | Reference                                                                     |
| -------------- | ------------------------------- | ----------------------------------------------------------------------------- |
| `$autoproceed` | `'Y'` = skip per-dataset prompt | [Execution Control](../developer-guide/global-variables.md#execution-control) |

When mounting: targets unmounted (`mounted=no`) filesystems.
When unmounting: targets mounted filesystems and volumes.

---

### `zfsreadthru`

Reads all snapshots in a dataset tree, forcing ZFS to verify every block.
Useful for locating unrecovered data errors when `zpool status -v` is
uninformative.

```bash
sudo zfsreadthru <dataset> [overrides] [first-snapshot] [last-snapshot]
```

**Arguments:**

| Argument | Description                                                     |
| -------- | --------------------------------------------------------------- |
| `$1`     | Head of tree to read (required)                                 |
| `$2`     | Override string (see [`zfsoverrides`](modules.md#zfsoverrides)) |
| `$3`     | First snapshot to read (default: oldest)                        |
| `$4`     | Last snapshot to read (default: newest)                         |

**Globals:**

| Variable                                                     | Role                           | Reference                                                                          |
| ------------------------------------------------------------ | ------------------------------ | ---------------------------------------------------------------------------------- |
| `$includes`, `$excludes`, `$startwith`, `$endwith`, `$depth` | Forwarded to `zfsbuildfsarray` | [Selection](../developer-guide/global-variables.md#dataset-and-snapshot-selection) |

---

### `zfsrecurse`

Runs any ZFS command recursively over a dataset tree. **Work in progress —
exits immediately with an error message if run.**

---

### `zfsrestore`

Interactive two-step full dataset restore. Configured by editing variables
inside the script.

```bash
sudo zfsrestore [overrides-part1]
```

**Arguments:**

| Argument | Description                                    |
| -------- | ---------------------------------------------- |
| `$1`     | Optional override string applied before Step 1 |

**In-script variables** (edit before running):

| Variable                    | Role                                                                      | Reference                                                                          |
| --------------------------- | ------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `$restoresourcefs`          | Source dataset (backup location)                                          | —                                                                                  |
| `$sourcefsremovequalifiers` | Leading qualifiers to strip                                               | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)             |
| `$destfs`                   | Pool/subpool to prepend after stripping leading qualifiers.               | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)             |
| `$label`                    | Snapshot label to restore                                                 | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)             |
| `$includes`, `$excludes`    | Dataset filters                                                           | [Selection](../developer-guide/global-variables.md#dataset-and-snapshot-selection) |
| `$nextsnap`                 | Snapshot name limit (optional; `'notneeded'` to look up newest on source) | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)             |

Step 1 does a full copy from the oldest snapshot. 

Step 2 does an incremental-with-intermediates
to catch up to the newest.

---

### `zfsrestoresendstream`

Restores a ZFS dataset from a send stream saved to disk (a `.zfssendstream`
file). Configured by editing variables inside the script.

**Arguments:** none (in-script variables).

**In-script variables:**

| Variable     | Role                                              |
| ------------ | ------------------------------------------------- |
| `$vm`        | Proxmox VM ID string (e.g., `vm-205`)             |
| `$vmname`    | VM name (used to construct source directory path) |
| `$destfs`    | Destination dataset                               |
| `$sourcedir` | Directory containing the `.zfssendstream` files   |

**Globals:**

| Variable       | Role                                       | Reference                                                                     |
| -------------- | ------------------------------------------ | ----------------------------------------------------------------------------- |
| `$force`       | `'Y'` = destroy destination before receive | [Execution Control](../developer-guide/global-variables.md#execution-control) |
| `$autoproceed` | `'Y'` = skip confirmations                 | [Execution Control](../developer-guide/global-variables.md#execution-control) |

---

### `zfsresizevol`

Resizes a ZFS volume. **Work in progress — exits immediately with an error
message if run.**

---

### `zfsresume`

Resumes an interrupted ZFS receive that has a `receive_resume_token`.

```bash
sudo zfsresume <destination-dataset>
```

**Arguments:**

| Argument | Description                                           |
| -------- | ----------------------------------------------------- |
| `$1`     | Destination dataset carrying a `receive_resume_token` |

**Globals:** none.

Retrieves the resume token, validates it, and either resumes the transfer or
reports that the token is stale (and clears it with `zfs receive -A`).

---

### `zfsscruball`

Scrubs all known ZFS pools. Supports pause and resume.

```bash
sudo zfsscruball [start|pause|resume]
```

**Arguments:**

| Argument | Default | Description                  |
| -------- | ------- | ---------------------------- |
| `$1`     | `start` | `start` / `pause` / `resume` |

**Globals:** none.

State is tracked in `/tmp/zfsscruball.state` during a run.

---

### `zfssend`

Snapshots and copies a dataset. Configured by editing variables inside the
script. Primarily used for ad-hoc sends during development and testing.

**Arguments:** none (in-script variables).

**In-script variables:**

| Variable          | Role                                   | Reference                                                                     |
| ----------------- | -------------------------------------- | ----------------------------------------------------------------------------- |
| `$sourcefs`       | Source dataset                         | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)        |
| `$destfs`         | Destination pool                       | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)        |
| `$doincrementals` | `'Y'` = incremental, `'N'` = full copy | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)        |
| `$autoproceed`    | `'Y'` = no prompts                     | [Execution Control](../developer-guide/global-variables.md#execution-control) |

---

### `zfssendoffsite`

Copies datasets to the currently-online offsite pool (`z22tb` or `z40tb`).
Runs multiple steps depending on configuration.

```bash
sudo zfssendoffsite [overrides]
```

**Arguments:**

| Argument | Description                                                              |
| -------- | ------------------------------------------------------------------------ |
| `$1`     | Optional override string (see [`zfsoverrides`](modules.md#zfsoverrides)) |

**In-script defaults (overridable):**

| Variable     | Default | Purpose                                      |
| ------------ | ------- | -------------------------------------------- |
| `step1`      | `'Y'`   | Copy `temp` → offsite                        |
| `step2`      | `'Y'`   | Copy `threeamigos` → `fivebays`              |
| `step3`      | `'Y'`   | Copy `NVME1` → `fivebays`                    |
| `step4`      | `'Y'`   | Copy `fivebays` → offsite                    |
| `applyholds` | `'Y'`   | Apply `offsite-<pool>` holds after each step |

**Globals:**

| Variable                                 | Role                               | Reference                                                                     |
| ---------------------------------------- | ---------------------------------- | ----------------------------------------------------------------------------- |
| `$autoproceed`, `$dryrun`, `$force`      | Forwarded to `zfs-send-receive`    | [Execution Control](../developer-guide/global-variables.md#execution-control) |
| `$label`, `$originlabel`, `$targetlabel` | Set to `offsite` for this workflow | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)        |

| Step | Source        | Destination |
| ---- | ------------- | ----------- |
| 1    | `temp`        | `<offsite>` |
| 2    | `threeamigos` | `fivebays`  |
| 3    | `NVME1`       | `fivebays`  |
| 4    | `fivebays`    | `<offsite>` |

After each step, applies named holds to source and destination snapshots to help
prevent accidental deletion.

When `$dryrun='Y'`, send/receive is simulated and hold application is skipped.

```bash
sudo zfssendoffsite "dryrun='Y'"
```

---

### `zfsoffsiteretain`

Prunes `@offsite` snapshots from source pools, respecting retention policies
and protecting snapshots that offline offsite pools still need as incremental
bases.

```bash
sudo zfsoffsiteretain [overrides]
```

**Arguments:**

| Argument | Description              |
| -------- | ------------------------ |
| `$1`     | Optional override string |

**Globals:**

| Variable        | Role                                               | Reference                                                                     |
| --------------- | -------------------------------------------------- | ----------------------------------------------------------------------------- |
| `$dryrun`       | `'Y'` = report only                                | [Execution Control](../developer-guide/global-variables.md#execution-control) |
| `$autoproceed`  | `'Y'` = skip prompts                               | [Execution Control](../developer-guide/global-variables.md#execution-control) |
| `$releaseholds` | Set to `'Y'` internally when invoking `zfscleanup` | [Execution Control](../developer-guide/global-variables.md#execution-control) |

Dynamically discovers all online pools that contain `@offsite` snapshots,
then runs `zfscleanup` with label `offsite` and `releaseholds='Y'` against
each one. No pool names are hardcoded — any pool with offsite snapshots is
included automatically.

Safety is provided by [`zfscheckagainst`](modules.md#zfscheckagainst): when a
counterpart pool is offline, hold-tag verification determines whether
deletion is safe. Retention counts come from each pool's retention policy
(`s` bucket) in the JSON config. Supports a dry run:

```bash
sudo zfsoffsiteretain "dryrun='Y'"
```

---

### `zfssetarcsize`

Sets the ZFS ARC maximum size both immediately (sysfs) and persistently
(`/etc/modprobe.d/zfs.conf` + `update-initramfs`). Edit the `GiB` variable
inside the script before running.

**Arguments:** none (in-script variable).

**In-script variables:**

| Variable | Role                      |
| -------- | ------------------------- |
| `$GiB`   | ARC max size in gibibytes |

---

### `zfsshowbigstuff`

Shows the largest (or smallest) datasets within a pool or dataset, sorted by
multiple metrics.

```bash
zfsshowbigstuff <pool-or-dataset> [largest|smallest] [count]
```

**Arguments:**

| Argument | Default   | Description                |
| -------- | --------- | -------------------------- |
| `$1`     | —         | Pool or dataset to inspect |
| `$2`     | `largest` | `largest` or `smallest`    |
| `$3`     | `5`       | Number of results to show  |

**Globals:** none.

Sorts by: `used`, `usedds`, `usedsnap`, `written`, `quota`, `refer`,
`refquota`, `reservation`.

---

### `zfsshowholds`

Lists all snapshot holds for a dataset or subtree.

```bash
zfsshowholds <dataset>
```

**Arguments:**

| Argument | Description        |
| -------- | ------------------ |
| `$1`     | Dataset or subtree |

**Globals:** none.

Simple wrapper around `zfs list ... | xargs zfs holds`. For depth control,
use [`zfsholds`](#zfsholds) instead.

---

### `zfsshowtuneables`

Verifies that `/etc/modprobe.d/zfs.conf` is present, correctly formatted, and
embedded in the initramfs. Shows current ZFS module parameters.

```bash
zfsshowtuneables
```

**Arguments:** none.

**Globals:** none.

---

### `zfsshowzpooldevices`

Lists the physical devices in a ZFS pool with vendor, model, size, and serial
number.

```bash
sudo zfsshowzpooldevices <pool>
```

**Arguments:**

| Argument | Description |
| -------- | ----------- |
| `$1`     | Pool name   |

**Globals:** none.

---

### `zfsstatus`

Auto-refreshing ZFS status display (pool list + pool status). Refreshes
every 60 seconds. Implemented as a one-liner that calls `Watchall/watchall`.

```bash
zfsstatus
```

**Arguments:** none.

**Globals:** none.

---

### `zfsunmount`

Unmounts all filesystems in a subtree.

```bash
zfsunmount <subtree>
```

**Arguments:**

| Argument | Description        |
| -------- | ------------------ |
| `$1`     | Subtree to unmount |

**Globals:** none.

Simpler than `zfsmount unmount` — no interactivity.

---

### `zfswatcharc`

Monitors ZFS ARC statistics with hit rates and throughput, updated at a
configurable interval.

```bash
zfswatcharc [interval-seconds]
```

**Arguments:**

| Argument | Default | Description                 |
| -------- | ------- | --------------------------- |
| `$1`     | `2`     | Refresh interval in seconds |

**Globals:** none.

Displays ARC size, target, hit rate, miss rate, and hits/misses per second.

---

### `retire-vm`

Automates the retirement of a VM. Discovers
clone dependencies, optionally promotes them, archives zvols and Proxmox config,
verifies archive integrity, and optionally removes the VM.

```bash
sudo retire-vm <vmid>
```

**Arguments:**

| Argument | Description                        |
| -------- | ---------------------------------- |
| `$1`     | VM ID of the template VM to retire |

**Flow:**

1. **Discover clones** — Finds all VMs whose zvols depend on snapshots of the VM's zvols
2. **Promote clones** — If any clones exist, asks whether to promote each one (calls
   `promote-vm-clone`), severing the dependency so the VM can be removed
3. **Archive zvols** — For each disk, runs `zfs send -cw <snapshot>` into a new ZFS dataset
   under the archive base, setting `volblocksize=1M` for space efficiency. Saves the original
   `volblocksize` to a `.original_volblocksize` sidecar and the disk's Proxmox config info
   (disk key, LUN, target) to a `.disk_info` sidecar.
4. **Archive config** — Copies `/etc/pve/qemu-server/<vmid>.conf` into the archive mount
5. **Verify** — Confirms all archived datasets and the config file exist and have expected sizes
6. **Remove VM** — Asks whether to remove the VM; if yes, removes the Proxmox config
   and destroys each zvol (including iSCSI teardown via `remove-vm-disk` in two-node mode)

**Globals:** node-config globals only (see [Two-Node Infrastructure Commands](two-node.md)).

---

### `unretire-vm`

Restores a retired VM from archive: recreates zvols with their original
`volblocksize`, rebuilds iSCSI infrastructure (two-node), and restores the Proxmox
config with updated disk lines.

```bash
sudo unretire-vm <vmid> [archive_base]
```

**Arguments:**

| Argument       | Description                                                                       |
| -------------- | --------------------------------------------------------------------------------- |
| `vmid`         | VM ID of the retired VM to restore                                                |
| `archive_base` | Optional ZFS dataset that contains the archive (defaults to JSON-configured path) |

**Flow:**

1. **Discover archive** — Finds archived zvol datasets and the Proxmox config under the archive base
2. **Validate** — Checks that destination zvols and Proxmox config do not already exist; verifies
   `.original_volblocksize` and `.disk_info` sidecar files are present
3. **Restore zvols** — Sends each archived zvol back to its original path, restoring the original
   `volblocksize` from the sidecar
4. **Rebuild iSCSI** (two-node) — Creates backstores and LUNs for each restored zvol, updates
   the expected-backstores manifest and encrypted-luns config
5. **Restore config** — Copies the archived Proxmox config; in two-node mode, rewrites each
   disk line with the new LUN number using the `.disk_info` sidecar mapping
6. **Rescan** (two-node) — Triggers iSCSI rescan on the compute host

**Globals:** node-config globals only.

---

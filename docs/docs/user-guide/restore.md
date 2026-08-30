# Restore Operations

## Identifying What to Restore

What you restore is always a snapshot. A copy of that snapshot becomes a snapshot of the restored dataset.

List snapshots for a backup dataset:

```bash
zfs list -t snapshot -o name,creation pool/dataset
```

List available snapshots across all pools:

```bash
zfs list -t snapshot -r -o name,creation,used
```

## Restoring a File or Directory (from snapshot)

ZFS snapshots are accessible at `/<mountpoint>/.zfs/snapshot/<name>/` within the
dataset's mount point. Use `df -Th` to find mounted ZFS filesystems. If your
data is not located in any listed mountpoint, use `zfs mount` to mount the
dataset first.

```bash
ls /<mountpoint>/.zfs/snapshot/dailybackup-2026-02-21T02:00-05:00-d/
cp /<mountpoint>/.zfs/snapshot/dailybackup-2026-02-21T02:00-05:00-d/path/to/file /destination/
```

## Restoring a Dataset (full copy)

!!! warning
    Restoring a dataset will overwrite its current contents. Ensure no
    applications or workloads are using the dataset.

!!! note "Clones"
    If the dataset being restored was originally a ZFS clone, it will be restored as a
    regular dataset. It will contain all data and be fully functional, but it will no longer
    share blocks with its former origin. This is expected and correct behavior.

A two-step restore gives the most complete result: a full copy of the oldest
available source snapshot followed by an incremental copy that brings the
destination up to date. Customize and use
[`zfsrestore`](../commands-and-modules/commands.md#zfsrestore), which automates
this two-step process.

### Recursive restores

By default, the command-line `zfsrestore` and `zfsfullcopy` scripts restore the
named dataset **and all of its descendants** (they use unlimited recursion when
building the dataset list). In the GTK GUI, the Restore tab defaults to restoring
**only the named dataset**; enable **Restore entire subtree (recursive)** to
include all descendants.

You can also limit or restore recursion from the command line by setting the
`depth` variable. `depth=0` restores only the named dataset, `depth=1` includes
one level of children, and `depth=""` (the default) includes the full subtree.

In a two-node configuration, the restore pipeline also ensures that restored
VM disk zvols are exported as iSCSI LUNs. It reads the LUN index from the
existing Proxmox VM config and recreates the backstore/LUN if it is missing,
then rescans the compute host so `/dev/disk/by-path` symlinks are available
when the VM starts.

Restore operations are not globally serialized with daily or offsite backups.
Multiple operations can run concurrently when they operate on disjoint datasets;
per-dataset locks still prevent collisions on the same datasets.

For details of the two-step restore, see the
[Architecture - Restore Flow](../developer-guide/architecture.md#restore-flow).

## Pause Scrubs During Restore

The Restore tab has an option to **pause scrubs on the source and destination
pools while the restore step is running**. This reduces I/O contention while
large snapshot data is being read and written, and resumes scrubs automatically
when the restore finishes.

- Enable it in the Restore tab → **Advanced** →
  **Pause scrubs on source/destination pools during each step**.
- Pools whose scrub has already finished or that are not online are skipped;
  they are not marked as user-paused.
- In dry-run mode the option logs what it would pause/resume but does not
  change scrub state.

## Advanced Options

The Restore tab's **Advanced** section exposes two transfer options that are
also available on the Backup and Offsite tabs:

- `verify_after_transfer` — Verify the ZFS stream after each transfer step
  (default **Y**). When enabled, `zfs-send-receive` re-reads the received
  stream to detect corruption. This applies to both Part 1 (full copy) and
  Part 2 (incremental copy).
- `pv_rate_limit` — Optional rate limit passed to `pv` during the transfer,
  for example `100M` to cap throughput at 100 MB/s. Leave blank for no limit.

## Preserving Target Holds During a Restore

A ZFS send stream does not include snapshot holds, so a restore normally loses
any hold tags that existed on the destination. `zfsrestore` and `zfsfullcopy`
now preserve those target holds automatically:

1. Before the destination dataset is destroyed/recreated, all holds on its
   snapshots are captured to a temporary file.
2. After the two-step restore finishes, the captured holds are reapplied to the
   restored snapshots.

This behavior is on by default. To disable it, set:

```bash
sudo zfsrestore "preserve_target_holds='N'"
```

You can also capture and reapply holds manually with the
[`zfsreapplyholds`](../commands-and-modules/commands.md#zfsreapplyholds)
helper:

```bash
sudo zfsreapplyholds --capture pool/dest /tmp/dest-holds.tsv
# ... perform the restore ...
sudo zfsreapplyholds --apply pool/dest /tmp/dest-holds.tsv
```

In dry-run mode, `zfsrestore`/`zfsfullcopy` log the holds that would be
reapplied without modifying the destination.

## Checking Holds Before Deletion

If a snapshot has holds, you must release them before it can be deleted:

```bash
zfs holds -r pool/dataset@snapshot
zfs release <holdname> pool/dataset@snapshot
```

Or use [`zfsdelholds`](../commands-and-modules/commands.md#zfsdelholds) to
release all holds matching a pattern.

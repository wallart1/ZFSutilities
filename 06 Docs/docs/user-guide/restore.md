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
common snapshot followed by an incremental copy that brings the destination up
to date. Customize and use [`zfsrestore`](../commands-and-modules/commands.md#zfsrestore),
which automates this two-step process.

For details of the two-step restore, see the
[Architecture - Restore Flow](../developer-guide/architecture.md#restore-flow).

## Checking Holds Before Deletion

If a snapshot has holds, you must release them before it can be deleted:

```bash
zfs holds -r pool/dataset@snapshot
zfs release <holdname> pool/dataset@snapshot
```

Or use [`zfsdelholds`](../commands-and-modules/commands.md#zfsdelholds) to
release all holds matching a pattern.

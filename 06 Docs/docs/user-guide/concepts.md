# Concepts and Terminology

This page introduces the ZFS concepts and project-specific terminology you
need to operate ZFS Utilities effectively. If you are already familiar with
ZFS, skim the headings and focus on the project-specific sections.

---

## ZFS Data Model

### Pools

A **pool** (`zpool`) is a storage unit built from one or more physical drives.
It manages the raw storage and provides redundancy (mirroring, RAID-Z) if
multiple drives are present. All data in ZFS lives inside a pool.

This documentation uses the following pools as examples:

| Pool          | Role                          | Typical redundancy |
| ------------- | ----------------------------- | ------------------ |
| `NVME1`       | Primary fast storage          | Single NVMe drive  |
| `threeamigos` | Primary storage — applications | 5-drive RAID-Z2    |
| `fivebays`    | Local backup destination      | 5-drive RAID-Z2    |
| `temp`        | Miscellaneous / staging       | 2-drive stripe     |
| `z22tb`       | Offsite backup (removable)    | 2-drive stripe     |

### Datasets

A **dataset** is a named filesystem that lives inside a pool. Datasets are
arranged in a tree rooted at the pool:

```
threeamigos
├── data
│   ├── dataset-a
│   ├── dataset-b
│   └── dataset-c
└── archive
```

A dataset's full name is its path from the pool root, separated by `/` (no leading slash):

```
threeamigos/data/dataset-a
```

Datasets can be nested to any depth. Each dataset has its own properties
(quota, compression, mountpoint, etc.) and can be snapshotted independently.

### Dataset Types

ZFS provides several dataset types:

| Type | Description | Typical use |
|------|-------------|-------------|
| **Filesystem** | A mounted directory tree with files and subdirectories. This is the default dataset type. | General data storage, application data, user home directories |
| **Volume (zvol)** | A block device rather than a filesystem. Colloquially called a **zvol** (from "ZFS volume"). It is not mounted; instead it appears as a device under `/dev/zvol/`. | VM disk images, swap space, iSCSI LUN backstores |
| **Snapshot** | A read-only, point-in-time copy of a filesystem or volume. See [Snapshots](#snapshots) below. | Backup base, clone origin, rollback target |
| **Clone** | A writable dataset created from a snapshot. Initially shares all blocks with its source; diverges as writes occur. See [ZFS Clones](#zfs-clones) below. | Rapid VM provisioning from a template, test environments |

A **zvol** is the term the ZFS community uses for a ZFS volume. In this
documentation, "zvol" and "volume" are used interchangeably.

### Backup Datasets in ZFS Utilities

When a dataset is copied to another pool, the destination dataset's name is modified. The name of the destination pool is prepended onto the entire source dataset's name, including its pool. So, as datasets are backed up to a subsequent pool, their names grow by adding the new pool at the beginning.

When a backup dataset is restored, these extra elements in the names must be removed. ZFSutilities has a way to do this and will be covered in the section about restoring backups.

### Snapshots

A **ZFS snapshot** is a read-only, point-in-time copy of a dataset. Snapshots:

- Are created instantly (they are copy-on-write references, not full copies)
- Consume no extra space at creation — storage is only used as the live
  dataset diverges from the snapshot
- Are named with an `@` separator appended to the dataset name:

```
threeamigos/data@dailybackup-2026-02-21T02:00-05:00-d
```

Snapshots can be listed with:

```bash
zfs list -t snapshot -r threeamigos/data
```

---

## Snapshot Naming Convention

This project uses a structured naming format for all snapshots:

```
@<label>-<yyyy-mm-dd>T<hh:mm><tz>-<bucket>
```

| Component    | Example       | Meaning                                                                                                                                                                                                      |
| ------------ | ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `label`      | `dailybackup` | User-defined purpose for the snapshot. There are three reserved labels: "dailybackup", "offsite" and "clone". Labels serve as snapshot "partitions" and serve to limit the scope of operations on snapshots. |
| `yyyy-mm-dd` | `2026-02-21`  | Date when the ZFSutilities job that created the snapshot was run.                                                                                                                                            |
| `T<hh:mm>`   | `T02:00`      | Time when the ZFSutilities job was run. This date and time can be different than the actual dataset creation date and time stored in ZFS dataset properties.                                                 |
| `<tz>`       | `-05:00`      | Timezone offset                                                                                                                                                                                              |
| `bucket`     | `d`           | Retention bucket (see below)                                                                                                                                                                                 |

**Full example:** `@dailybackup-2026-02-21T02:00-05:00-d`

**NOTE:**  ZFSutilities does not explicitly prevent the use of other snapshot names. Using your own labels is the recommended way. Since the label is the first element of the snapshot name, anything other than `dailybackup`, `offsite`, or `clone` is a custom label, and the snapshot will be generally ignored, with exceptions. For example, deleting a dataset with the [zfsdelfs](../commands-and-modules/commands.md#zfsdelfs) script involves deleting all of its snapshots, including custom ones. Custom labels are not fully tested at this time.

### Retention Buckets

The trailing letter groups snapshots for retention purposes:

| Bucket | Label       | Kept by                                                                                   |
| ------ | ----------- | ----------------------------------------------------------------------------------------- |
| `d`    | dailybackup | Daily backup                                                                              |
| `w`    | dailybackup | When a daily backup falls on a Sunday<br/>Overrides "d"                                   |
| `m`    | dailybackup | When a daily backup falls on the first day of a month<br/>Overrides "d" and "w"           |
| `s`    | offsite     | Set by [zfssendoffsite](../commands-and-modules/commands.md#zfssendoffsite) when creating an offsite backup                                   |
| `c`    | clone       | Set by [zfsclone-vm](../commands-and-modules/two-node.md#zfsclone-vm-both) when creating a clone. Not subject to retention policies. |

### How Retention Works

Retention policies are **per-pool** and stored in the shared JSON config. Every
pool has its own list of buckets, plus a `default` policy that is used when a
pool has no explicit entry.

For each bucket, two numbers control pruning:

- **Retain Count** — how many snapshots to keep. When a bucket grows larger
  than this number, older snapshots become candidates for deletion.
- **Min Age (days)** — the minimum age a snapshot must reach before it can be
  pruned, even if the bucket is over its Retain Count. `0` means no minimum age.

Pruning runs in three phases (see [Retention Policies](retention.md) for the
full algorithm):

1. **Offsite same-month pruning** (`@offsite` label only) — keeps only the most
   recent offsite snapshot per month per dataset.
2. **Same-day deduplication** — within each bucket, keeps only the most recent
   snapshot per day.
3. **Bucket count enforcement** — deletes oldest snapshots until only the Retain
   Count remains. Empty snapshots (`written=0`) are logged as `(empty)` but are
   not preferred for deletion over older snapshots with unique data. The most
   recent snapshot in each bucket is always protected as the incremental backup
   base.

Clone snapshots (`c` bucket) are **never touched** by retention.

---

## ZFS Send and Receive

ZFS send/receive is the mechanism used to copy datasets.

### Full Copy

A **full copy** transfers an entire dataset from scratch, using a single
snapshot as the source. In ZFSutilities, the destination dataset is destroyed and recreated.

Use a full copy when:

- No common snapshot exists between source and destination, preventing incremental copies
- You are restoring a dataset from a backup

### Incremental Copy

An **incremental copy** transfers only the data that changed between two
snapshots — a `from` snapshot and a later`to`
snapshot. This is usually much faster than a full copy.

Incremental copies require a **common snapshot**: a snapshot that exists
on both source and destination with the same GUID (usually also the same name). If no common snapshot
is found, the incremental fails and a full copy must be performed instead.

### Intermediate Snapshots

When copying incrementally, ZFSutilities can transfer all snapshots between
the common one and a later one (usually the most current one). This is called
**intermediate snapshot** mode. It ensures the destination has a complete
snapshot history, not just the most recent state.

### The Two-Step Restore

ZFSutilities fully restores a dataset by performing:

1. **Full copy** from the oldest available snapshot
2. **Incremental copy** with intermediates to bring the destination up to date

This is automated by [zfsrestore](../commands-and-modules/commands.md#zfsrestore).

---

## The Backup Chain

Data flows through backup tiers. For example:

```
  Primary                    Local backup      Offsite
  threeamigos/data     ──┐
  NVME1                  ├──→  fivebays  ───→  z22tb
                         ┘               ───→  z40tb
  temp                   |──────────────────→  z22tb
  temp                   |──────────────────→  z40tb
```

| Tier         | Pools                | Updated by        | Frequency         |
| ------------ | -------------------- | ----------------- | ----------------- |
| Primary      | `threeamigos, NVME1` | Applications, workloads | Continuously      |
| Primary      | `temp`               | Various           | As needed         |
| Local backup | `fivebays`           | [zfsdailybackup](../commands-and-modules/commands.md#zfsdailybackup)  | Daily             |
| Offsite      | `z22tb`, `z40tb`     | [zfssendoffsite](../commands-and-modules/commands.md#zfssendoffsite)  | Manually, rotated |

The offsite pools are manually **rotated**: one is kept offsite while the other is
connected for an update run, then swapped. This maintains two independent
offsite copies at different points in time.

Because each tier serves as a true backup of the previous tier, the general rule is that the same snapshots must exist in all tiers. ZFSutiities is designed to allow dropping of non-offsite snapshots from the Offsite tier, however. In addition, adding extra snapshots to a destination tier (`fivebays, z22tb, z40tb`) is not supported. If this occurs, the extra snapshots will be removed, or may cause a full copy, or cause further backups of the dataset to fail.

---

## Holds

A **hold** is a special tag applied to a ZFS snapshot that prevents it from being deleted. ZFSutilities uses holds to protect offsite snapshots from accidental deletion until their pools have been successfully rotated back from offsite storage.

List holds on a snapshot:

```bash
zfs holds pool/dataset@snapshot
```

Release a hold (Not recommended. Allow ZFSutilities to do this for you.):

```bash
zfs release <holdname> pool/dataset@snapshot
```

---

## ZFS Clones

### What Is a ZFS Clone?

A **ZFS clone** is a writable dataset created from a snapshot of another dataset. Like
a snapshot, a clone is instantaneous and initially consumes no extra storage — it shares
all blocks with its source. As the clone diverges (because it receives writes), only the
new and changed blocks consume additional space. This is called **copy-on-write (COW)**.

Clones are used by ZFSutilities to create new writable datasets rapidly and space-efficiently from a template snapshot.

```
source-dataset
    ├── @clone-2026-03-04T10:00-05:00-c   (clone origin snapshot)
    │       └── clone-a   (clone — new dataset)
    └── @clone-2026-03-05T10:00-05:00-c   (another clone origin snapshot)
            └── clone-b   (another new dataset)
```

Each clone created by [`zfsclone-vm`](../commands-and-modules/two-node.md#zfsclone-vm-both) gets its own origin snapshot
with a unique timestamp. This means clone-a and clone-b each depend on a
separate snapshot, and promoting one does not affect the other.

### Clone Origin Snapshot

When [zfsclone-vm](../commands-and-modules/two-node.md#zfsclone-vm-both) creates a clone, it first takes a snapshot of each source dataset and names it with the label `clone` and bucket `c`:

```
@clone-<yyyy-mm-dd>T<hh:mm><tz>-c
```

This snapshot is the **clone origin** — it is the point in time when the clone was created. 
ZFS prevents deletion while any clone created from it still exists.

When pruning snapshots, ZFSutilities ignores `@clone-...-c` snapshots entirely. ZFS will only allow their removal after all dependent clones have been destroyed or promoted.

### Clone Dependencies

ZFS tracks the relationship between a clone and its origin snapshot. You can inspect these relationships with:

```bash
# See what a clone was created from:
zfs get origin pool/dataset/clone-a

# See what clones depend on a snapshot:
zfs list -t snapshot -o name,clones -r pool/dataset/source-dataset
```

A snapshot that has clone dependents **cannot be destroyed** until those dependents are
removed or promoted. [zfsdelfs](../commands-and-modules/commands.md#zfsdelfs) detects this condition and aborts before touching
anything, with a clear error message.

If a destroy fails for any reason — clone dependents, holds, open files, active
sends/receives, iSCSI LUNs, running workloads, or shares — [zfs-diagnose-busy](../commands-and-modules/commands.md#zfs-diagnose-busy) is
automatically invoked to report the specific cause and suggest the fix.

### Clones and Backup/Restore

**How clones are backed up:** [zfs-send-receive](../commands-and-modules/modules.md#zfs-send-receive) (used by [zfsdailybackup](../commands-and-modules/commands.md#zfsdailybackup) and [zfssendoffsite](../commands-and-modules/commands.md#zfssendoffsite))
treats clones as regular datasets. Each clone is sent independently, and at the destination it
becomes a normal dataset containing the clone's full state. It is **not** received as a clone.

**Why this is correct:** A clone's own snapshots (`clone-a@dailybackup-...`) are in the
clone's dataset lineage, not the origin's. ZFS cannot receive a clone's incremental snapshots
into a clone relationship because the snapshot histories diverge. Even advanced tools like
zrepl and sanoid/syncoid treat clones as regular datasets on the receiver.

**Space implication:** If both the dataset and its clones are backed up, the shared blocks
exist twice on the backup pool. This is the cost of making each dataset independently restorable.
`zfs send -R` can preserve clone relationships, but it requires sending the entire hierarchy
(including all snapshots and descendents) and is incompatible with this project's selective,
incremental backup architecture.

**Restore behavior:** Restoring a clone produces a regular dataset. It contains all data and is
fully functional, but it no longer shares blocks with its former origin. This is expected.

**Do not skip clones from backup:** The `$skipclones` parameter in [zfsbuildfsarray](../commands-and-modules/modules.md#zfsbuildfsarray) can exclude
clones, but this **causes data loss** because clones are writable datasets with their own unique
blocks. Only use it for transient test clones you genuinely don't need to back up.

### Promoting a Clone

Over time, you may want to destroy the original dataset. You cannot destroy it while
clones still depend on its snapshots. The solution is `zfs promote`:

**`zfs promote`** reverses the parent-child relationship between a clone and its origin.
After promotion:

- The promoted clone's dataset becomes independent (its `origin` property becomes `-` when you display it)
- The shared clone-origin snapshot moves from the original dataset to the promoted clone
- Any other clones that happen to share the same origin snapshot would re-parent automatically to the promoted clone. In ZFSutilities, each clone typically has its own origin snapshot, so this usually does not apply
- The original dataset, now a clone of the promoted dataset, can be destroyed once it has no remaining dependents of its own

`promote-vm-clone` automates this process for all datasets at once.

!!! note "One promotion per snapshot"
    If the source has multiple clone-origin snapshots (because [zfsclone-vm](../commands-and-modules/two-node.md#zfsclone-vm-both) was run at
    different times), each snapshot with dependents requires one [promote-vm-clone](../commands-and-modules/two-node.md#promote-vm-clone-both) run against one of its dependents. Each promotion cuts one snapshot's dependency chain.

---

## Glossary

| Term                       | Meaning                                                                                                                                                              |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **pool**                   | A ZFS storage unit made from one or more drives                                                                                                                      |
| **dataset**                | A named node inside a pool. May be a filesystem, a volume (zvol), a snapshot, a clone.                                                                               |
| **snapshot**               | A read-only point-in-time state of a dataset. It contains the exact data in the dataset at the time the snapshot was created.                                        |
| **send/receive**           | ZFS mechanism to copy datasets between pools. Send and receive are two separate commands.                                                                            |
| **common snapshot**        | A snapshot with the same identification (not just the name) on both source and destination, used as the base for incremental transfers                               |
| **full copy**              | Transfer of an entire dataset from scratch                                                                                                                           |
| **incremental copy**       | Transfer of only changes since a certain (usually the last) common snapshot                                                                                          |
| **intermediate snapshots** | All snapshots between a common one and a later one, transferred in order. By default ZFS does not copy intermediate snapshots. ZFSutilities includes this function.  |
| **bucket**                 | ZFSutiltiies retention category: `d` daily, `w` weekly, `m` monthly, `s` offsite, `c` clone origin                                                                   |
| **hold**                   | A ZFS tag on a snapshot that prevents its deletion                                                                                                                   |
| **retention policy**       | Rules in ZFSutilities specifying how many snapshots to keep per bucket per pool                                                                                      |
| **label**                  | The name component of a ZFSutilities snapshot (e.g., `dailybackup`, `offsite`, `clone`)                                                                              |
| **clone**                  | A writable ZFS dataset created from a snapshot. Initially shares all blocks with its source (COW); diverges as writes occur                                          |
| **clone origin**           | The snapshot from which a clone was created. Cannot be deleted while any clone still depends on it                                                                   |
| **copy-on-write (COW)**    | ZFS storage strategy: shared blocks are only duplicated when one copy is modified, so clones start at zero extra storage. (This is a simplification of the concept.) |
| **zfs promote**            | ZFS operation that reverses the parent-child relationship between a clone and its origin, making the clone independent                                               |

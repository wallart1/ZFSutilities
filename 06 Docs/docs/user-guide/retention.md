# Retention Policies

Retention policies control how long snapshots are kept. Use the zfscleanup command to run an independent snapshot cleanup. The retention policies are applied by[`zfsretain`](../commands-and-modules/modules.md#zfsretain), which is called from [`zfsdailybackup`](../commands-and-modules/commands.md#zfsdailybackup) (and others) and can also be run manually or from the GUI.

## How Retention Works

Pruning happens in three phases:

1. **Offsite same-month pruning** (`@offsite` label only) — keeps only the most
   recent offsite snapshot per month for each dataset.
2. **Same-day pruning** — keeps only the most recent snapshot per day within
   each bucket. Older snapshots from the same day are removed.
3. **Bucket count limits** — for the buckets `d`, `w`, `m`, `s`, keeps only
   the N most recent snapshots as specified in the pool's retention policy. When a bucket overflows, the oldest snapshots are deleted first. The most recent snapshot in each bucket is always protected so it can serve as the base for the next incremental backup.

Clone snapshots (`c` bucket) are **never touched** by retention.

For the complete algorithm, see the
[`zfsretain` module reference](../commands-and-modules/modules.md#zfsretain).

## Policy Parameters

Each bucket in a retention policy has two parameters:

- **`retain`** — how many snapshots of this bucket are kept. When a bucket has
  more than this many snapshots, the oldest snapshots are deleted first. The
  most recent snapshot in each bucket is always protected so it can serve as
  the base for the next incremental backup.
- **`minage`** — the minimum age, in days, before a snapshot in this bucket is
  allowed to be deleted. It is **not** a maximum age: setting `minage=65` does
  not mean snapshots are deleted after 65 days; it means they cannot be deleted
  until they are at least 65 days old. A snapshot older than `minage` is still
  kept if it is within the `retain` count or is the most recent snapshot in its
  bucket.

For example, an offsite (`s`) bucket configured as `retain=4 minage=65` keeps
up to four offsite snapshots and never deletes any of them until each one is at
least 65 days old. A snapshot that is 80 days old will be kept if it is one of
the four newest offsite snapshots for that dataset.

## Editing Retention Policies

The easiest way to edit policies is the GUI's **Retention** tab. You can also
edit the JSON config with a text editor if you are comfortable doing so.

### Fresh Install Behavior

On a new installation, the installers create exactly one retention policy — the
`default` policy — and do not install pool-specific sample policies. If you
re-run the installer on a system where you have already added per-pool policies,
those policies are left untouched.

### Example: Default Policy

Typically configured as:

- 3 daily, 2 weekly, 2 monthly

### Example: Offsite Pool Policy

Offsite pools often have fewer copies due to storage constraints:

- 2 offsite (`s` bucket) snapshots

## Snapshot Buckets

| Bucket | Label   | When created                      |
| ------ | ------- | --------------------------------- |
| `d`    | daily   | Every run of `zfsdailybackup`     |
| `w`    | weekly  | Every weekly run (if configured)  |
| `m`    | monthly | Every monthly run (if configured) |
| `s`    | offsite | Every run of `zfssendoffsite`     |

## Running Retention Manually

When called directly, `zfsretain` defaults to **dry-run mode** — it reports
what would be deleted without deleting anything. To actually delete, you must
explicitly set `dryrun='N'`.

```bash
# Dry run (default): shows what would be deleted
sudo ./zfsretain fivebays dailybackup

# Live run: actually deletes
export dryrun='N'
sudo -E ./zfsretain fivebays dailybackup
unset dryrun
```

`zfsdailybackup` calls retention via `zfscleanup`, which defaults to live mode.
The dry-run default only applies when calling `zfsretain` directly.

When `zfscleanup` is invoked without a specific pool, it processes the pools
registered in the JSON config. If the config pool list is empty, it falls back
to all online pools so retention is not silently skipped.

## Held Snapshots

By default, `zfsretain` sets `$skipbusy='Y'`, meaning if a snapshot has a ZFS
hold (or is otherwise busy) and cannot be deleted, a warning is logged and
pruning continues with the next snapshot.

When a destroy fails, `zfsdelsnap` automatically runs
[`zfs-diagnose-busy`](../commands-and-modules/commands.md#zfs-diagnose-busy)
to check all known causes — holds, clone dependents, mounted snapshots, open
files, active sends/receives, bookmarks, iSCSI LUNs, running workloads, and
NFS/SMB shares — and prints specific guidance for whatever it finds.

If `zfs-diagnose-busy` is missing from the deployment, `zfsdelsnap` logs a
fatal error and exits immediately rather than silently skipping snapshots.

To restore the old fatal behavior (set `$skipbusy='N'`), pass an override:

```bash
./zfsdailybackup "skipbusy='N'"
```

## Safety Checks During Pruning

Before deleting any snapshot, `zfsdelsnap` calls
[`zfscheckagainst`](../commands-and-modules/modules.md#zfscheckagainst) to
verify the snapshot is not the last common snapshot shared with a counterpart
dataset. This prevents losing the ability to do incremental backups.

If the counterpart pool is offline, `zfscheckagainst` uses hold tags to
determine safety. `zfssendoffsite` places a hold named
`offsite-<counterpart_pool>` on each source and destination snapshot it
successfully replicates. These serve as receipts.

For deletion to be safe, the incremental chain must remain intact: there must
be another snapshot that both the source and the counterpart share. If the
offsite pool is offline and no other snapshot of the source dataset has the appropriate hold tag, deletion is blocked:

```
WARN: Cannot verify counterpart - pool(s) offline: z22tb
Deletion blocked for safety. Bring the counterpart pool(s) online to verify.
```

For the full safety-check algorithm, see the
[`zfscheckagainst` module reference](../commands-and-modules/modules.md#zfscheckagainst).

## Mass Delete

The Retention tab provides a **Mass Delete** action for deleting many snapshots
at once outside the normal three-phase pruning flow. Select one or more pools in
the Prune list, configure the filters in the **Mass Delete** card, and click
**Mass Delete**.

!!! warning "Mass Delete can break incremental chains"
    When **Ignore retention policies** is enabled, snapshots are deleted without
    consulting `zfscheckagainst`. This can remove the last common snapshot shared
    with an offsite or backup pool and break future incremental backups. Use this
    mode only when you are certain the snapshots are no longer needed.

### Filter options

| Field              | Purpose                                                                |
| ------------------ | ---------------------------------------------------------------------- |
| **Includes**       | Space-separated dataset name substrings to include                     |
| **Excludes**       | Space-separated dataset name substrings to exclude                     |
| **Start With**     | Skip datasets until this substring is seen                             |
| **End With**       | Stop processing datasets after this substring                          |
| **Snapshot Has**   | Only consider snapshots whose full name contains this substring        |
| **Release Holds**  | Release ZFS holds before deleting; enabled only when **Ignore retention policies** is checked |
| **Ignore Retention Policies** | When enabled, delete all matching snapshots regardless of retention policy |

### Modes

- **Respect retention policies** (default) — behaves like running **Prune** for
  each selected pool, using the configured retention policies. Dry Run shows the
  candidates that `zfscleanup` would remove.
- **Ignore retention policies** — lists every matching snapshot and deletes them
  after confirmation, bypassing retention counts, `minage`, and
  `zfscheckagainst`. This is the fastest way to free space, but it is also the
  most destructive.

Before either mode deletes anything, the candidate list is followed by an
**estimated disk space** message. The estimate is the sum of each snapshot's
`used` property (space unique to that snapshot). If **Release Holds** is enabled,
holds are released automatically without an additional confirmation per snapshot.

### Command-line equivalent

The GUI action invokes [`zfsmassdelsnaps`](../commands-and-modules/commands.md#zfsmassdelsnaps):

```bash
# Respect retention policies (default)
sudo ./zfsmassdelsnaps fivebays

# Ignore retention policies and delete all matching dailybackup snapshots
export snapshot_label="dailybackup" ignore_retention_policies="Y"
sudo -E ./zfsmassdelsnaps fivebays
```

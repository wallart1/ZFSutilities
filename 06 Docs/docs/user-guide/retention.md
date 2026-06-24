# Retention Policies

Retention policies control how long snapshots are kept. They are applied by
[zfsretain](../commands-and-modules/modules.md#zfsretain) (called from [`zfsdailybackup`](../commands-and-modules/commands.md#zfsdailybackup)).

## How Retention Works

Pruning happens in three phases:

**Phase 0 - Offsite same-month pruning (offsite label only):** When the label
is `@offsite`, keeps only the most recent offsite snapshot per month for each
dataset. Older offsite snapshots in the same month are removed.

**Phase 1 - Same-day pruning:** Keeps only the most recent snapshot per
day per bucket. Older snapshots from the same day are removed.

**Phase 2 - Bucket count limits:** For each bucket (`d`, `w`, `m`, `s`), keeps
only the N most recent snapshots as specified in the retention policy. When a
bucket overflows, the oldest snapshots are deleted first until only the retain
count remains. Empty snapshots (`written=0` — duplicates of the prior state) are
logged as `(empty)` but are not preferred over older snapshots with unique data.
The most recent snapshot in each bucket is always protected as the incremental
backup base.

!!! note "Clone snapshots are protected"
    Snapshots with label `clone` or bucket `c` are **never touched** by retention. They are skipped in all phases because clone-origin snapshots cannot be deleted while dependent clones exist.

## Where Policies Live

Per-pool retention policies are stored in the shared JSON config at
`/root/.config/zfsutilities.json` under the `retention` key. Each pool has a
list of buckets (along with`name`, `retain`, `minage`values), and a `default` entry is used as
the fallback when a pool has no explicit policy.

### Legacy format (`zfsretainpol-*` files)

Older installations may have retention policies as standalone bash files in the
project root:

```bash
# zfsretainpol-default
bktname[0]='d';     bktretain[0]=3; minage[0]=0
bktname[1]='w';     bktretain[1]=2; minage[1]=0
bktname[2]='m';     bktretain[2]=2; minage[2]=0
bktname[3]='s';     bktretain[3]=4; minage[3]=65
```

The JSON config is the authoritative source for the GUI since version 0.1.3.
On first visit to the Retention tab, the GUI imports any `zfsretainpol-*` files
it finds into the JSON config automatically. However, some CLI workflows may
still read or regenerate these files, so do not assume they are obsolete.

The easiest way to edit them is the GUI's **Retention** tab, which lets you
pick a pool, adjust retain counts and minimum ages, and save back to the JSON.
The tab also offers:

- **Add Policy** / **Remove Policy** — create or delete a per-pool entry. New
  policies are seeded from the current `default`. Removing a policy deletes the
  pool's entry and falls back to `default`; it is also removed from the Prune
  list.
- **Prune** — a multi-select, drag-reorderable list of online pools that have
  an explicit retention policy. The runner invokes `zfscleanup <pool> '' <label>`
  for each selected pool in the visual list order, regardless of selection order.
  Pools without an explicit policy do not appear in the list. Dragging a pool to
  a new position persists the order in the JSON config under `prune_pools_order`,
  so the list order survives GUI restarts and scheduled retention profiles.
  The snapshot label entry is sized for 20 characters, and output streams
  to the log panel at the bottom of the window. The label is saved globally in
  the JSON config under `prune_label` (default `dailybackup`).
- **Fresh-install cleanup** — on a brand-new install, any pool-specific policies
  imported from legacy `zfsretainpol-*` files are cleared so only the `default`
  policy remains. This prevents stale sample policies from being applied
  automatically.

See the [GTK GUI Reference](gtk-gui.md#retention-tab) for a full walk-through.

Under the hood, [zfsretain](../commands-and-modules/modules.md#zfsretain) reads policies via `zfsconfig_get_retention <pool>`,
which emits a sourceable bash fragment of the form:

```bash
bktname[0]='d'; bktretain[0]=7; minage[0]=0
bktname[1]='w'; bktretain[1]=4; minage[1]=0
bktname[2]='m'; bktretain[2]=12; minage[2]=0
```

### Example: Default Policy

Typically configured as:

- 3 daily, 2 weekly, 2 monthly

### Example: Offsite Pool Policy

Offsite pools often have fewer copies due to storage constraints:

- 2 offsite (`s` bucket) snapshots

## Snapshot Buckets

| Bucket | Label   | When created                      |
| ------ | ------- | --------------------------------- |
| `d`    | daily   | Every run of [zfsdailybackup](../commands-and-modules/commands.md#zfsdailybackup)     |
| `w`    | weekly  | Every weekly run (if configured)  |
| `m`    | monthly | Every monthly run (if configured) |
| `s`    | offsite | Every run of [zfssendoffsite](../commands-and-modules/commands.md#zfssendoffsite)     |

## Running Retention Manually

When called directly, [zfsretain](../commands-and-modules/modules.md#zfsretain) defaults to **dry-run mode** — it reports
what would be deleted without deleting anything. To actually delete, you must
explicitly set `dryrun='N'`.

### Held snapshots

By default, [zfsretain](../commands-and-modules/modules.md#zfsretain) sets `$skipbusy='Y'`, meaning if a snapshot has a ZFS
hold (or is otherwise busy) and cannot be deleted, a `WARN:` message is logged
and pruning continues with the next snapshot.

When a destroy fails, [zfsdelsnap](../commands-and-modules/modules.md#zfsdelsnap) automatically runs [zfs-diagnose-busy](../commands-and-modules/commands.md#zfs-diagnose-busy) to
check all known causes — holds, clone dependents, mounted snapshots, open
files, active sends/receives, bookmarks, iSCSI LUNs, running workloads, and
NFS/SMB shares — and prints specific guidance for whatever it finds.

If `zfs-diagnose-busy` is missing from the deployment (for example, because
`deploy-version` was run from an incomplete source), `zfsdelsnap` logs a **FATAL**
error and exits immediately rather than silently skipping snapshots.

To restore the old fatal behavior (set `$skipbusy='N'`), pass an override:

```bash
./zfsdailybackup "skipbusy='N'"
```

```bash
# Dry run (default): shows what would be deleted
sudo ./zfsretain fivebays dailybackup

# Live run: actually deletes
export dryrun='N'
sudo -E ./zfsretain fivebays dailybackup
unset dryrun
```

Note: [zfsdailybackup](../commands-and-modules/commands.md#zfsdailybackup) calls retention via [zfscleanup](../commands-and-modules/commands.md#zfscleanup), which defaults to
live mode. The dry-run default only applies when calling [zfsretain](../commands-and-modules/modules.md#zfsretain) directly.

When [zfscleanup](../commands-and-modules/commands.md#zfsdailybackup) is invoked without a specific pool, it processes the pools registered
in the JSON config. If the config pool list is empty, it falls back to all online
pools so retention is not silently skipped.

## Safety Checks During Pruning

Before deleting any snapshot, [zfsdelsnap](../commands-and-modules/modules.md#zfsdelsnap) calls [zfscheckagainst](../commands-and-modules/modules.md#zfscheckagainst) to verify
the snapshot is not the last common snapshot shared with a counterpart dataset.
This prevents losing the ability to do incremental backups.

If the counterpart pool is offline, [zfscheckagainst](../commands-and-modules/modules.md#zfscheckagainst) uses hold tags to determine
safety. [zfssendoffsite](../commands-and-modules/commands.md#zfssendoffsite) places a hold named `offsite-<counterpart_pool>` on
each source and destination snapshot it successfully replicates. These serve as receipts.

For deletion to be safe, the incremental chain must remain intact: there must
be another snapshot that both the source and the counterpart share.
[zfscheckagainst](../commands-and-modules/modules.md#zfscheckagainst) verifies this for offline pools by scanning other `@offsite` snapshots on the same
dataset for an `offsite-<counterpart_pool>` hold:

- **Another snapshot has the hold**: The counterpart received that snapshot too.
  A second common snapshot is confirmed — deletion of the current one is safe.
- **No other snapshot has the hold**: Cannot verify another common snapshot
  exists. Deletion is blocked:

```
WARN: Cannot verify counterpart - pool(s) offline: z22tb
Deletion blocked for safety. Bring the counterpart pool(s) online to verify.
```

Note: holds on non-offsite labels (e.g. `dailybackup`) are not used — those
backup series do not apply holds, so offline counterparts always block.

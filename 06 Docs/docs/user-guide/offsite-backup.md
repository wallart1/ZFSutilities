# Offsite Backup

[`zfssendoffsite`](../commands-and-modules/commands.md#zfssendoffsite) copies
datasets to a removable pool that can be taken off-site for disaster recovery.

Like `zfsdailybackup`, this script is intended as a template. Review and
customize it to match your pools and offsite targets, or use the GUI's Offsite
tab to configure the equivalent workflow.

## Running the Offsite Backup

1. Import the offsite pool:
   
   ```bash
   sudo zpool import <pool>
   ```

2. Run the offsite backup:
   
   ```bash
   sudo zfssendoffsite
   ```

3. Export and remove the pool:
   
   ```bash
   sudo zpool export z22tb
   ```

## What Gets Copied

The backup chain (for example):

```
temp ──────────────────────────────────────→ <offsite>
                                               ▲
threeamigos/proxmox ──→ fivebays ──────────────┘
                         ▲
NVME1 ───────────────────┘
```

| Step | Source        | Destination | Notes                  |
| ---- | ------------- | ----------- | ---------------------- |
| 1    | `temp`        | `<offsite>` | Excludes `temp/temp`   |
| 2    | `threeamigos` | `fivebays`  | `proxmox` subtree only |
| 3    | `NVME1`       | `fivebays`  | All datasets           |
| 4    | `fivebays`    | `<offsite>` | All datasets           |

The `<offsite>` token is replaced at run time with the first online offsite
pool marked as an offsite candidate in the pool registry.

## Snapshot Label and Holds

Offsite snapshots use the label `offsite` and bucket `s`
(e.g., `@offsite-2026-02-21T10:00-05:00-s`).

Holds named `offsite-<counterpart_pool>` are placed on both source and
destination snapshots to prevent accidental deletion. These holds also act as
**receipts** that help retention safety checks work while an offsite pool is
offline (see [Hold Tags as Receipts](#hold-tags-as-receipts)).

## Skipping Steps

```bash
sudo ./zfssendoffsite "step1='N'"
sudo ./zfssendoffsite "step2='N'; step3='N'"
```

See the [`zfssendoffsite` command reference](../commands-and-modules/commands.md#zfssendoffsite)
for the full list of step flags.

## Dry Run

To simulate the offsite backup without making changes:

```bash
sudo ./zfssendoffsite "dryrun='Y'"
```

In dry-run mode, the script logs what it would send but does not create
snapshots, transfer data, or apply holds. Hold application is skipped entirely
when dry-run is enabled.

## Pause Scrubs During Send/Receive

The Offsite tab has an option to **pause scrubs on the source and destination
pools while each offsite step is running**. This reduces I/O contention during
the offsite copy and resumes scrubs automatically when the step finishes.

- Enable it in the Offsite tab → **Advanced** →
  **Pause scrubs on source/destination pools during each step**.
- Only the pools used by the current step are paused.
- In dry-run mode the option logs what it would pause/resume but does not
  change scrub state.

## Hold Tags as Receipts

When `zfssendoffsite` copies a snapshot, it places a hold on both the source
and destination snapshots. The hold tag encodes the counterpart pool:

| Snapshot location          | Hold tag           | Meaning                    |
| -------------------------- | ------------------ | -------------------------- |
| `fivebays/...@offsite-...` | `offsite-z22tb`    | z22tb has this snapshot    |
| `z22tb/...@offsite-...`    | `offsite-fivebays` | fivebays has this snapshot |

These holds serve as **receipts** — proof that the counterpart pool has the
snapshot. This is critical for safe retention when offsite pools are offline.

When an offsite pool is offline, retention cannot confirm a common snapshot by
checking the pool directly. Instead, it looks for another `@offsite` snapshot on
the same source dataset that carries the hold tag `offsite-<counterpart_pool>`.
If such a snapshot exists, the counterpart received it too, so the current
snapshot is safe to delete. If no such hold exists, deletion is blocked until
the offsite pool comes back online.

For the full algorithm, see the
[`zfscheckagainst` module reference](../commands-and-modules/modules.md#zfscheckagainst).

## Cleaning Up Old Offsite Snapshots

### Automated: [`zfsoffsiteretain`](../commands-and-modules/commands.md#zfsoffsiteretain)

The recommended way to prune offsite snapshots:

```bash
sudo ./zfsoffsiteretain
```

This discovers all online pools that contain `@offsite` snapshots and runs
retention against each one using that pool's retention policy (`s` bucket
counts). The same safety checks apply as when pruning from the GUI.

### GUI: Retention Tab

Use the **Retention** tab in the GUI to prune `@offsite` snapshots. Select the
pool whose retention policy you want to apply and click **Prune**. This runs the
retention policy against all snapshot labels on that pool, including the `s`
(offsite) bucket.

- Dry-run mode is respected if the **Dry Run** toggle is active.
- The **Prune** button is disabled while a retention job is running.

### Manual: [`zfscleanup`](../commands-and-modules/commands.md#zfscleanup)

You can also prune offsite snapshots per-pool manually:

```bash
sudo ./zfscleanup '<poolname>' '' 'offsite'
```

This removes `offsite`-labeled snapshots beyond the retention count for that
pool's policy. The same safety checks apply.

# Offsite Backup

[zfssendoffsite](../commands-and-modules/commands.md#zfssendoffsite) copies datasets to a removable pool that can be taken off-site
for disaster recovery. 

Please review this script and lightly modify to meet your needs.

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

## Snapshot Label and Holds

Offsite snapshots use the label `offsite` and bucket `s`
(e.g., `@offsite-2026-02-21T10:00-05:00-s`).

Holds named `offsite-<counterpart_pool>` are placed on both source and destination snapshots to prevent accidental deletion.

## Skipping Steps

```bash
sudo ./zfssendoffsite "step1='N'"
sudo ./zfssendoffsite "step2='N'; step3='N'"
```

## Dry Run

To simulate the offsite backup without making changes:

```bash
sudo ./zfssendoffsite "dryrun='Y'"
```

In dry-run mode, the script logs what it would send but does not create
snapshots, transfer data, or apply holds. Hold application is skipped entirely
when dry-run is enabled.

## Hold Tags as Receipts

When [zfssendoffsite](../commands-and-modules/commands.md#zfssendoffsite) copies a snapshot, it places a hold on both the source and
destination snapshots. The hold tag encodes the counterpart pool:

| Snapshot location          | Hold tag           | Meaning                    |
| -------------------------- | ------------------ | -------------------------- |
| `fivebays/...@offsite-...` | `offsite-z22tb`    | z22tb has this snapshot    |
| `z22tb/...@offsite-...`    | `offsite-fivebays` | fivebays has this snapshot |

These holds serve as **receipts** — proof that the counterpart pool has the
snapshot. This is critical for safe retention when offsite pools are offline
(see below).

## Cleaning Up Old Offsite Snapshots

### Automated: [zfsoffsiteretain](../commands-and-modules/commands.md#zfsoffsiteretain)

The recommended way to prune offsite snapshots:

```bash
sudo ./zfsoffsiteretain
```

This dynamically discovers all online pools that contain `@offsite`
snapshots and runs retention against each one using that pool's retention
policy (`s` bucket counts). It relies on the
[zfscheckagainst](../commands-and-modules/modules.md#zfscheckagainst) safety
checks to prevent deleting snapshots that an offline offsite pool still needs.

**How it stays safe when the offsite pool is offline:**

For incremental backups to work, source and destination must share a common
snapshot. While preparing to remove a snapshot, if [zfscheckagainst](../commands-and-modules/modules.md#zfscheckagainst) encounters an offline counterpart pool, it scans
other `@offsite` snapshots on the same source dataset for a hold tag
`offsite-<counterpart_pool>`. If another snapshot carries that hold, the
counterpart received it too — a second common snapshot is confirmed and
deletion of the current one is safe. If no other snapshot has the hold, the
current snapshot may be the only common one; deletion is blocked until the
counterpart pool is brought online for verification.

### GUI: Retention Tab

Use the **Retention** tab in the GUI to prune `@offsite` snapshots. Select the
pool whose retention policy you want to apply and click **Prune**. This runs the
retention policy against all snapshot labels on that pool, including the `s`
(offsite) bucket.

- Dry-run mode is respected if the **Dry Run** toggle is active.
- The **Prune** button is disabled while a retention job is running.

### Manual: [zfscleanup](../commands-and-modules/commands.md#zfscleanup)

You can also prune offsite snapshots per-pool manually:

```bash
sudo ./zfscleanup '<poolname>' '' 'offsite'
```

This removes `offsite`-labeled snapshots beyond the retention count for that
pool's policy. The same [zfscheckagainst](../commands-and-modules/modules.md#zfscheckagainst) safety checks apply.

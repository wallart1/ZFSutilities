# Daily Backup

See [Concepts and Terminology](concepts.md) for background on pools, datasets,
snapshots, and the backup chain before reading this page.

The daily backup job ([`zfsdailybackup`](../commands-and-modules/commands.md#zfsdailybackup))
is the main ZFSutilities operation. It:

1. Pulls custom rsync backups from remote hosts
2. Snapshots source datasets and copies them to their destination pools
3. Applies retention policies to prune old snapshots

`zfsdailybackup` is intended as a starting template. Sites customize it
to match their pools and hosts, or configure and run the equivalent workflow
from the GUI's Backup tab.

## Running the Daily Backup

```bash
sudo zfsdailybackup
```

The daily backup is not globally serialized with offsite or restore jobs.
Multiple operations can run at the same time when they operate on disjoint
datasets; per-dataset locks still prevent collisions on the same datasets.

## Step Failure Handling

Different steps have different consequences when they fail:

- **Pre-backup script** — fatal. The entire backup aborts immediately.
- **Pull steps (rsync)** — non-fatal. The failure is logged as a warning, but
  the backup continues with the remaining steps. This lets a single unreachable
  remote host prevent only its own pull rather than canceling the whole job.
- **ZFS keys backup (rsync)** — non-fatal. The failure is logged as a warning
  and the backup continues.
- **Send/receive steps** — fatal. A ZFS transfer failure aborts the remaining
  backup steps.
- **Retention/prune step** — non-fatal. A per-dataset pruning failure is logged
  as a warning and `zfscleanup` continues with the next dataset/pool.

The post-backup command, if enabled, always runs after the step list finishes,
even when a fatal failure aborted the backup early.

## Pre-Backup Command

You can run a custom command before any backup steps begin. If the command fails,
the entire backup aborts immediately.

Enable and set it via override:

```bash
sudo ./zfsdailybackup "pre_backup_script_enabled='Y'; pre_backup_script='echo starting backup'"
```

Or configure it permanently in the GUI (Backup tab → **Pre-Backup**).

## Post-Backup Command

You can run a custom command after all backup steps finish. Unlike the pre-backup
command, the post-backup command executes **even if a fatal error aborts the backup
early** — for example, if the pre-backup command fails or a ZFS send/receive step
errors out. This makes it useful for notifications, cleanup, or status reporting
that must run regardless of outcome.

Enable and set it via override:

```bash
sudo ./zfsdailybackup "post_backup_script_enabled='Y'; post_backup_script='echo backup finished'"
```

Or configure it permanently in the GUI (Backup tab → **Post-Backup Steps**).

## ZFS Keys Backup

The daily backup can optionally copy your ZFS encryption key files to an
encrypted destination dataset. This is configured in the GUI (Backup tab →
Advanced expander) or in the JSON config as `zfs_keys_path` (source) and
`zfs_keys_dest` (destination).

Both fields accept rsync endpoint syntax:

- Local path: `/mnt/ZFSkeys/`
- Remote path: `storage-host:/backups/zfs-keys/`

If either field is empty, the keys backup step is skipped.

The destination dataset **must be encrypted**. If the destination is not
encrypted, the step is skipped with a warning.

### The Circular Dependency Problem

Because the keys backup destination is itself encrypted, the backed-up key
files cannot be accessed without the keys that unlock that destination. This
creates a circular dependency:

```
You need the ZFS keys → to unlock the destination dataset → to read the
backed-up keys
```

**Therefore, the ZFS keys backup is NOT a substitute for an independent,
offline copy of your encryption keys.**

### Recommended Key Storage

Keep at least one additional copy of your ZFS encryption keys **outside the
ZFS pools**:

- Store the keys on a **removable USB device**.
- Protect that device with **LUKS full-disk encryption**.
- The **LUKS password should exist only in your memory** — do not write it
  down on the device, on the host, or in any password manager that lives on
  systems protected by these same keys.

This offline copy ensures you can recover your data even if the backup
destination is inaccessible or the keys stored within it cannot be retrieved.

## Skipping Individual Steps

Pass a quoted override string to disable specific steps:

```bash
sudo ./zfsdailybackup "backup_NVME1='N'"
sudo ./zfsdailybackup "prune='N'"
sudo ./zfsdailybackup "backup_NVME1='N'; prune='N'"
```

Available overrides include: `backup_threeamigos`, `backup_NVME1`, `prune`,
and the rsync-pull flags for each configured host. See the
[`zfsdailybackup` command reference](../commands-and-modules/commands.md#zfsdailybackup)
for the full list.

To skip the package-list backup step that runs before rsync on each pull host:

```bash
sudo ./zfsdailybackup "run_installed_programs='N'"
```

To skip **all** pull steps at once (for example, when the remote hosts are
unreachable and you only want to run ZFS send/receive and retention):

```bash
sudo ./zfsdailybackup "pull_steps_active='N'"
```

This is the same setting controlled by the **Active** checkbox on the Backup
tab in the GUI.

## Dry Run

To simulate the entire backup without making changes:

```bash
sudo ./zfsdailybackup "dryrun='Y'"
```

In dry-run mode, the script logs what it would do but skips:

- Pre-backup script execution
- Remote rsync pulls and local package list backups
- ZFS snapshot creation and send/receive
- Snapfile cleanup
- Retention pruning

This is useful for verifying configuration and estimating transfer sizes before
a live run.

## Pause Scrubs During Send/Receive

ZFS scrubs and send/receive operations both read the same pool data, which can
compete for disk I/O. The Backup tab has an option to **pause scrubs on the
source and destination pools while each send/receive step is running**. Scrubs
resume automatically when the step finishes.

- The option is off by default; enable it in the Backup tab → **Advanced** →
  **Pause scrubs on source/destination pools during each step**.
- Only the pools used by the current step are paused, not every pool in the job.
- Pools whose scrub has already finished or that are not online are skipped;
  they are not marked as user-paused.
- Pre/post scripts, rsync pulls, and retention are not affected.
- In dry-run mode the option logs what it would pause/resume but does not
  change scrub state.

## What a Successful Run Looks Like

```
[zfsdailybackup:45] *** Step: Sending NVME1 to fivebays ***
[zfs-send-receive:88] Snapshot fivebays/NVME1@dailybackup-2026-02-21T02:00-05:00-d already exists. Skipping.
...
[zfsdailybackup:60] *** Retention: fivebays ***
[zfsretain:32] Phase 0: Removing offsite same-month duplicates ...
[zfsretain:58] Phase 1: Removing same-day duplicates ...
[zfsretain:84] Phase 2: Pruning by bucket counts ...
*** zfsdailybackup completed. ***
```

## Common Issues

### "A common snapshot ... was NOT found"

The source and destination have no snapshot in common. This prevents an
incremental transfer. The script will ask whether to do a full copy.

**Cause**: The destination pool was re-created, no backup has ever run, or a
required destination snapshot was deleted.

**Action**: If expected, answer `y` to proceed with a full copy. Be aware a
full copy can take hours for large datasets. There is no way to do an
incremental transfer without at least one common snapshot. Restoring
destination snapshots from another backup will probably not fix this.

### Remote rsync SSH failure

If the job SSHes to a remote host and the known_hosts entry is stale:

```
Host key verification failed.
```

**Action**: On the backup host, run:

```bash
ssh-keygen -f "/root/.ssh/known_hosts" -R "<hostname>"
ssh-keyscan <hostname> >> /root/.ssh/known_hosts
```

A single pull-step failure is non-fatal: the backup continues with the remaining
pull steps and send/receive steps. The overall job still returns the failing
pull's return code, so monitoring systems can flag it.

## Rerunning After Failure

The daily backup is idempotent for the snapshot-and-copy steps (zfs-send-receive): if a snapshot
with today's name already exists, that step is skipped. You can safely rerun
the job using the same snapshot name after fixing a failure.

When a failed backup is rerun, the snapshot-name generator will ask whether to reuse the previous
name. Answer `y` to keep everything consistent.

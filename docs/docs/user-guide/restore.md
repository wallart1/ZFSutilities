# Restore Operations

## Identifying What to Restore

In ZFS parlance, what you restore is always a snapshot. Restoring a snapshot results in a restored dataset that has the same snapshot.

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
ls /<mountpoint>/.zfs/snapshot/dailybackup-2026-02-21T07:00Z-d/
cp /<mountpoint>/.zfs/snapshot/dailybackup-2026-02-21T07:00Z-d/path/to/file /destination/
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

By default, the command-line `zfsrestore` and
[`zfsfullcopy`](../commands-and-modules/modules.md#zfsfullcopy) scripts restore the
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

## What a Restore Preserves

Backups in ZFSutilities are **data-only streams**. Every backup path — the
bash scripts (`zfsdailybackup`, `zfssendoffsite`, `zfssend`) as well as the
GUI's Backup, Offsite, and Restore tabs and scheduled profiles — transfers
snapshots with `zfs send -cw` (compressed, raw) through the shared
[`zfs-send-receive`](../commands-and-modules/modules.md#zfs-send-receive)
engine; the restore paths (`zfsrestore`, `zfsfullcopy`) use the same engine.

Those streams carry the snapshot data and the encryption state, but **no
dataset properties** — so each dataset's locally-set properties are recorded
separately, in a **property manifest** written next to the backup right
after its transfer verifies
([property-manifest-lib.sh](../commands-and-modules/modules.md#property-manifest-libsh)).
At restore time the replay step re-applies them with `zfs set`, so the
restored datasets come back with their data intact (transfer verification
compares snapshot GUIDs — see [Advanced Options](#advanced-options))
*wearing the source's* `compression`, `recordsize`, `keylocation`, user
properties (for example `org.debian:periodic-scrub`), and similar settings
rather than the destination hierarchy's inherited defaults.

Replay runs automatically after the transfer in `zfsrestore`, the GUI
Restore tab, and scheduled restore profiles (the Advanced
`replay_properties` option, default **Y**, turns it off).
[`zfsrestoresendstream`](../commands-and-modules/commands.md#zfsrestoresendstream)
applies a `<name>.props` sibling when one sits next to a
`<name>.zfssendstream` file. The replay is best-effort by contract:

- The manifest for the backup copy's **newest snapshot** — the generation
  just restored — is used; if it is missing, the newest available manifest
  for that dataset applies instead, with a WARN that the settings may be
  from an older generation.
- The manifest store is looked up by the backup copy's position in the
  chain, probing the deeper offsite hop (`<offsite>/<root>/<pool>/...`)
  before the direct backup root — so restores from an offsite pool find
  the manifests that traveled with the copies.
- Backups that predate property manifests have none: the restore WARNs and
  the datasets keep their inherited defaults (the data is unaffected).
- A manifest is verified (format, dataset, and body checksum) before
  anything is applied; a corrupt or wrong-dataset manifest is skipped with
  a WARN.
- A property this host cannot set (older OpenZFS release, unknown
  property) is skipped with a WARN; the remaining properties still apply.

Two deliberate exceptions keep their own property handling:

- **Migrate Pool** (Disks page) uses replication streams (`zfs send -Rw`,
  with `-RIw` incrementals at cutover), which do carry dataset properties —
  a pool migration is intended to reproduce the source configuration.
- **archive-vm** records each archived zvol's original `volblocksize` in a
  `.original_volblocksize` sidecar and `unarchive-vm` re-applies it on
  restore; see
  [archive-vm](../commands-and-modules/commands.md#archive-vm).
  `volblocksize` is also excluded from property manifests: raw streams
  carry it, and it cannot be set after creation.

Snapshot holds are handled separately; see
[Preserving Target Holds During a Restore](#preserving-target-holds-during-a-restore).

### Encrypted datasets

Encrypted datasets always travel as raw (`-w`) streams — that is what keeps
them encrypted end to end. A received copy of an encrypted dataset becomes
**its own encryption root**: it is not linked into the destination pool's
key hierarchy, even when it is received under an encrypted parent. The
encryption algorithm, key format, PBKDF2 iterations, and key material all
travel inside the stream, so the data comes back encrypted exactly as it was
sent.

The streams do not carry `keylocation`: a received encrypted dataset starts
with `keylocation=prompt`, because the source's key-file path would not
exist on the destination. The property manifest deliberately records the
source's `keylocation`, and the replay step sets it and then attempts a
non-interactive `zfs load-key` — but only for `file://` locations (any other
location is set and left locked for you to unlock by hand). When the key
file is missing or unreadable on the restore host, the replay WARNs and the
dataset stays locked; point it at your key store and unlock:

```bash
sudo zfs set keylocation=file:///mnt/ZFSkeys/pool.key pool/dataset
sudo zfs load-key pool/dataset
sudo zfs mount pool/dataset
```

See [ZFS Key Handling](../installation/zfs-keys.md) for the key-store layout
and boot-time behavior.

### Block size and compression at rest

`zfs receive` never rewrites received data to match the destination's
settings: blocks keep the record size they were written with, and
already-compressed blocks are not recompressed. Destination `recordsize` and
`compression` affect only **future writes** after the restore. The practical
consequences:

- Backup storage footprint is governed by the source's settings, not the
  destination's.
- A zvol's `volblocksize` cannot change once the zvol is written. The only
  receive-time lever is `zfs receive -o volblocksize=`, whose support varies
  by OpenZFS version (some releases refuse the override outright), and raw
  streams can only be received as-is. Reblocking a zvol therefore means
  copying its data into a freshly created zvol — the approach the
  [archive-vm](../commands-and-modules/commands.md#archive-vm) copy method
  takes.

### Why not reblock backups to the largest block size

Saving space by reblocking every backed-up zvol to the largest possible
`volblocksize` does work — but only on write-once copies, never on the
incremental chain:

- **Incremental destinations must stay bit-identical.** Each backup is
  received into a snapshot lineage; the next incremental builds on the
  snapshots the destination already holds. A reblocked copy is a new
  dataset with no snapshot history, so an incremental receive into it is
  impossible — every later backup would have to be a full transfer. The
  space saved is paid back many times over in transfer volume.
- **Reblocking pays where data is written once.** Larger blocks pack RAIDZ
  parity more efficiently and give compression more to work with, so a
  write-once copy at a large block size commonly occupies a fraction of
  its live footprint. That is what the
  [archive-vm](../commands-and-modules/commands.md#archive-vm) copy method
  is: the archive zvol is created thin at `volblocksize=1M` and the source
  is device-copied onto it — the reblock-for-space-efficiency mechanism.
  Encrypted zvols are the exception (raw receive keeps their original
  block size, because a device copy would read plaintext), and
  `unarchive-vm` restores each zvol's original `volblocksize` from its
  sidecar.
- **Running VMs want small blocks.** Live zvol block sizes are small by
  design: with very large blocks, every random guest write triggers
  copy-on-write write amplification. Large blocks are for cold data.

The rule of thumb: **reblock write-once copies (archives, long-term
retention); keep incremental chains bit-identical.** When pool space is
the concern, the lever is archiving cold VMs — the reblock happens as
part of the archive.

## Pause Scrubs During Restore

The Restore tab in the GUI has an option to **pause scrubs on the source and destination
pools while the restore step is running**. This reduces I/O contention while
large snapshot data is being read and written, and resumes scrubs automatically
when the restore finishes.

- Enable it in the Restore tab → **Advanced** →
  **Pause scrubs on source/destination pools during each step**.
- Pools that are not scrubbing at runtime are ignored.
- In dry-run mode the option logs what it would pause/resume but does not
  change scrub state.

## Advanced Options

The Restore tab's **Advanced** section exposes two transfer options that are
also available on the Backup and Offsite tabs:

- `verify_after_transfer` — Verify the received snapshot after each transfer
  step (default **Y**). When enabled, `zfs-send-receive` compares the `guid`
  ZFS property of the destination snapshot against the source snapshot; a
  mismatch is treated as fatal. This applies to both Part 1 (full copy) and
  Part 2 (incremental copy).
- `replay_properties` — Replay each restored dataset's captured
  [property manifest](#what-a-restore-preserves) onto the destination after
  the transfer (default **Y**). Missing or unreadable manifests only WARN;
  the affected datasets keep their inherited defaults. Set **N** to restore
  with the destination's inherited settings only.
- `transfer_rate_limit` — Optional rate limit used during the transfer,
  for example `100M` to cap throughput at 100 MB/s. Leave blank for no limit.

## Interrupted Restores

A restore that is cancelled or interrupted (GUI closed, host rebooted, SSH
drop) can simply be run again — the rerun analyzes each destination dataset
and completes only what is missing:

- **Interrupted resumable receive** — transfers above the resumable
  threshold are received with `zfs receive -s`, so an interrupted receive
  leaves a resume token on the destination. The rerun validates each token
  and continues the interrupted receive from it (a stale token is discarded
  and the dataset continues down the checks below).
- **Verified snapshot lineage** — a destination dataset whose snapshots
  GUID-match the source already has completed restore work. The rerun
  skips the destructive full copy for it and only catches the remaining
  snapshots up incrementally.
- **No lineage** — a destination that does not exist or shares no
  GUID-matched snapshot with the source is destroyed and fully re-copied
  from the oldest snapshot, as a first-run restore would.

The analysis is per dataset, so a run interrupted mid-way (some datasets
done, some mid-receive, some untouched) resumes correctly in one pass.
Both the GUI's Run Restore and scheduled restore profiles use this
behavior.

## Preserving Target Holds During a Restore

A ZFS send stream does not include snapshot holds, so a full copy normally
loses any hold tags that existed on the destination snapshots.
`zfs-send-receive` preserves those target holds automatically on every full
copy (`doincrementals='N'`, or `force='Y'`) — whether invoked through
`zfsrestore`, `zfsfullcopy`, or directly:

1. Before any dataset is touched, all holds under the destination are captured
   to a temporary file. If the capture fails, the run aborts before
   transferring anything, so hold tags are never silently lost.
2. After the transfer completes, the captured holds are reapplied to the
   restored snapshots.

This behavior is on by default and is controlled by `$preserve_target_holds`.
To disable it, set:

```bash
sudo zfsrestore "preserve_target_holds='N'"
```

Hold preservation does not run for plain incremental backups or in dry-run
mode, since nothing is destroyed in either case. Note that if the restore
itself fails mid-run, the captured-holds temp file is left in place (under
`/tmp`, named `zfs-send-receive-target-holds.*`); it can be applied manually:

```bash
sudo zfsreapplyholds --apply pool/dest /tmp/zfs-send-receive-target-holds.XXXXXX
```

You can also capture and reapply holds yourself with the
[`zfsreapplyholds`](../commands-and-modules/commands.md#zfsreapplyholds)
helper:

```bash
sudo zfsreapplyholds --capture pool/dest /tmp/dest-holds.tsv
# ... perform the restore ...
sudo zfsreapplyholds --apply pool/dest /tmp/dest-holds.tsv
```

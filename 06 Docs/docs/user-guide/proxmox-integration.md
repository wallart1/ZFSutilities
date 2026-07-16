# Proxmox Integration

This page applies only if you are using Proxmox VE.

How ZFSutilities interacts with the Proxmox GUI depends on whether you are
running a **single-node** setup (ZFS pools local to the Proxmox host) or a
**two-node** setup (ZFS pools on a separate storage host, exported via
iSCSI).

---

## Storage Configuration

### Single-node

Proxmox manages the ZFS pools directly. In **Datacenter → Storage**, each
pool appears as a `ZFS` storage entry (type `zfspool` in
`/etc/pve/storage.cfg`):

```
zfspool: threeamigos
    pool threeamigos/proxmox
    content images,rootdir
    sparse 1
```

Proxmox has full read-write access to the storage layer.

### Two-node

Proxmox discovers LUNs from the iSCSI target on the storage host. In
**Datacenter → Storage**, each target appears as an `iSCSI` entry:

```
iscsi: iscsi-threeamigos
    portal 192.168.100.1
    target iqn.2026-02.local.stewie:threeamigos
    content images
```

Proxmox treats these LUNs as **administratively read-only block devices** — it
can attach and detach them, but cannot create, resize, or delete them.

---

## Feature Comparison

| Operation                       | Single-node (local ZFS)                                                          | Two-node (iSCSI)                                                                       |
| ------------------------------- | -------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| **Create VM disk**              | Proxmox GUI: Hardware → Add → Hard Disk → select ZFS pool                        | Script only: [`new-vm-disk`](../commands-and-modules/two-node.md#new-vm-disk-both)       |
| **Resize VM disk**              | Proxmox GUI: Hardware → select disk → Disk Action → Resize                       | Script only: [`resize-vm-disk`](../commands-and-modules/two-node.md#resize-vm-disk-both) |
| **Delete VM disk**              | Proxmox GUI: Hardware → select disk → Detach, then Remove                        | Script only: [`remove-vm-disk`](../commands-and-modules/two-node.md#remove-vm-disk-both) |
| **Detach VM disk**              | Proxmox GUI: Hardware → select disk → Detach                                     | Script only: [`detach-vm-disk`](../commands-and-modules/two-node.md#detach-vm-disk-both) |
| **Attach existing disk**        | Proxmox GUI: Hardware → Add → Hard Disk → select existing                        | Script only: [`attach-vm-disk`](../commands-and-modules/two-node.md#attach-vm-disk-both) |
| **Move VM disk to another VM**  | Proxmox GUI: not supported for iSCSI LUNs                                        | Script only: [`move-vm-disk`](../commands-and-modules/two-node.md#move-vm-disk-both)     |
| **Clone VM (full copy)**        | Proxmox GUI: right-click VM → Clone (Mode: Full Clone)                           | Script only: [`clone-vm`](../commands-and-modules/two-node.md#clone-vm-both)             |
| **Clone VM (linked/ZFS clone)** | Proxmox GUI: right-click VM → Clone (Mode: Linked Clone)                         | Script only: [`zfsclone-vm`](../commands-and-modules/two-node.md#zfsclone-vm-both)       |
| **Promote clone**               | Not exposed in Proxmox GUI — use [`promote-vm-clone`](../commands-and-modules/two-node.md#promote-vm-clone-both) | [`promote-vm-clone`](../commands-and-modules/two-node.md#promote-vm-clone-both)          |
| **Snapshots (Proxmox-managed)** | Proxmox GUI: Snapshots tab → Take Snapshot                                       | Not available (no ZFS awareness)                                                       |
| **Snapshots (ZFSutilities)**    | ZFSutilities GTK GUI or scripts                                                  | ZFSutilities GTK GUI or scripts                                                        |
| **View pool status**            | Proxmox GUI: node → Disks → ZFS, or ZFSutilities GUI                             | ZFSutilities GUI or `zpool` on storage host                                            |
| **View datasets/snapshots**     | Proxmox GUI (limited) or ZFSutilities GUI                                        | ZFSutilities GUI only                                                                  |
| **Start/stop VMs**              | Proxmox GUI                                                                      | Proxmox GUI                                                                            |
| **VM hardware settings**        | Proxmox GUI                                                                      | Proxmox GUI                                                                            |
| **Retention / prune**           | ZFSutilities GTK GUI or [`zfsretain`](../commands-and-modules/modules.md#zfsretain) | ZFSutilities GTK GUI or [`zfsretain`](../commands-and-modules/modules.md#zfsretain)      |
| **Backup (zfs send/receive)**   | ZFSutilities scripts                                                             | ZFSutilities scripts                                                                   |
| **Offsite backup**              | ZFSutilities scripts                                                             | ZFSutilities scripts                                                                   |

---

## Creating a VM

### Single-node

Use the standard Proxmox workflow entirely from the Proxmox GUI:

1. **Create VM** → General → set VM ID and name
2. **OS** → select ISO
3. **Disks** → select your ZFS pool as storage, set disk size
4. **CPU / Memory / Network** → configure as needed
5. **Confirm** → Proxmox creates the zvol and attaches it automatically

You can also add disks after creation: **Hardware → Add → Hard Disk** →
choose the ZFS pool and size.

### Two-node

Proxmox cannot create zvols on the remote storage host. The workflow
requires a helper script before touching the GUI.

#### BIOS boot VMs (legacy SeaBIOS)

For most Linux VMs:

1. On the storage host (or compute host — the script delegates via SSH):
   
   ```bash
   sudo new-vm-disk threeamigos 300 0 50G    # boot disk
   sudo new-vm-disk threeamigos 300 1 500G   # data disk (optional)
   ```

2. In the Proxmox GUI: **Create VM** → set VM ID 300
   
   - On the **Disks** step: select "No disk" or delete the default disk
   
   - After creation: **Hardware → Add → Hard Disk → iSCSI** → select the
     LUNs created in step 1

3. Attach ISO, boot, install OS

#### UEFI boot VMs (EFI disk)

Required for Windows 11 and recommended for modern Linux. The EFI disk
stores UEFI firmware variables (boot order, Secure Boot state, etc.).

1. Create the **EFI firmware disk first** (this also sets the VM BIOS to
   OVMF and adds the `efidisk0` config line):
   
   ```bash
   sudo new-vm-disk threeamigos 300 0 EFI
   ```
   
   The script will ask about Secure Boot:
   
   - **y** — pre-enroll Microsoft + distro keys (required for Windows 11)
   - **N** — clean slate, Secure Boot off (simpler for Linux; can enable later)

2. Create the boot and data disks as normal:
   
   ```bash
   sudo new-vm-disk threeamigos 300 1 50G    # boot disk
   sudo new-vm-disk threeamigos 300 2 500G   # data disk (optional)
   ```

3. In the Proxmox GUI: **Create VM** → set VM ID 300
   
   - On the **System** tab: set BIOS to **OVMF (UEFI)** and **uncheck**
     "Add EFI Disk" (the script already created and configured it)
   - On the **Disks** step: select "No disk" or delete the default disk
   - After creation: **Hardware → Add → Hard Disk → iSCSI** → select the
     boot/data LUNs

4. Attach ISO, boot, install OS
   
   !!! warning "Do not use Proxmox's 'Add EFI Disk' button with iSCSI"
   
       The Proxmox GUI's **Add EFI Disk** button does not work with iSCSI
       storage — it fails trying to initialize the disk. Use
       `new-vm-disk EFI` instead; it creates the zvol, exports the LUN,
       initializes the firmware variables, and adds the required VM config
       lines.

!!! warning "UEFI 2023 certificate enrollment for iSCSI-backed VMs"
       When you choose Secure Boot pre-enrollment, `new-vm-disk EFI` adds
       `ms-cert=2023k` to the `efidisk0` config line. This marks the 2023
       Microsoft UEFI certificates as enrolled and suppresses the Proxmox
       warning about the expiring 2011 certificates.

       For existing VMs that show that warning, use the helper script on
       the compute node:

       ```bash
       sudo enroll-efi-keys-vm <vmid>
       ```

       This grows the EFI zvol to 4M, re-initializes it with the Microsoft
       UEFI CA 2023 certificates, and updates the Proxmox config.

       Do **not** use the Proxmox GUI (**Hardware → EFI Disk → Disk Action →
       Enroll Updated Certificates**) or `qm enroll-efi-keys` for iSCSI
       by-path EFI disks. Both parse the volume identifier on `:` and fail
       with an error such as `unable to parse volume ID
       '/dev/disk/by-path/ip-...:3260-iscsi-...'`. Always use
       `sudo enroll-efi-keys-vm <vmid>` for iSCSI-backed VMs.

       For Windows VMs with BitLocker, disable BitLocker protectors inside
       the VM before enrolling.

!!! tip "Avoiding kernel log spam"
    By default, Proxmox's `pvestatd` runs `iscsiadm --rescan` roughly every
    10 seconds to discover new LUNs. This causes the Linux iSCSI target on
    the storage host to log `MODE SENSE: unimplemented page/subpage`
    messages repeatedly (one per LUN per rescan).

    The `install-two-node` installer patches
    `/usr/share/perl5/PVE/Storage/ISCSIPlugin.pm` on the compute host to
    limit automatic rescans to once per day. The disk-management scripts
    trigger explicit rescans immediately when they make changes, so
    day-to-day operation is unaffected.

---

## Detaching and Removing Disks

### Single-node

In the Proxmox GUI:

- **Detach** (keep zvol): Hardware → select disk → **Detach**
- **Remove** (destroy zvol): Hardware → select disk → **Detach**, then **Remove**

### Two-node

The Proxmox GUI can detach a disk from the VM config, but it cannot destroy
the underlying zvol or remove the iSCSI LUN. For full cleanup, use the scripts:

**Detach (keep the zvol):**

```bash
sudo detach-vm-disk 300 scsi1
```

This removes the disk from the VM config and tears down the iSCSI LUN and
backstore, but leaves the zvol intact so it can be re-attached later.

**Attach a previously detached zvol:**

```bash
sudo attach-vm-disk threeamigos/proxmox/vm-100-disk-0 200
```

This rebuilds any missing iSCSI infrastructure and adds the disk to the
destination VM config. The destination device slot is auto-detected; you can
override it: `attach-vm-disk ... 200 scsi2`.

**Remove permanently (destroy the zvol):**

```bash
sudo remove-vm-disk threeamigos 300 1
```

This destroys the zvol, backstore, and LUN. Use with caution — the data is
permanently lost.

---

## Resizing a Disk

### Single-node

In the Proxmox GUI:

1. Select the VM → **Hardware** → select the disk
2. **Disk Action → Resize**
3. Enter the **additional** size
4. The guest OS sees the new size after it rescans or is rebooted 

### Two-node

The Proxmox GUI cannot resize iSCSI LUNs. Use the script:

```bash
sudo resize-vm-disk threeamigos 300 0 100G
```

NOTE: Unlike single-node, for the new size, enter the TOTAL new size, not the size increase.

The script grows the zvol and triggers an iSCSI rescan so the compute host
sees the new size. The guest OS still needs its own rescan or reboot.

---

## Moving a Disk to Another VM

### Single-node

The Proxmox GUI has a direct "move disk to another VM" operation. You may also use the script:

```bash
sudo move-vm-disk 100 scsi1 200          # move scsi1 from VM 100 → next free scsi on VM 200
sudo move-vm-disk 100 scsi1 200 scsi0    # move scsi1 from VM 100 → scsi0 on VM 200
```

Both VMs must be stopped. The script edits `/etc/pve/qemu-server/<vmid>.conf`
directly — no data is copied and no zvols are renamed.

### Two-node

The same script works for iSCSI-backed disks:

```bash
sudo move-vm-disk 100 scsi1 200
```

The script verifies the iSCSI LUN exists on the storage node via SSH, confirms
both VMs are stopped, and moves the disk line from the source VM config to the
destination VM config. The LUN number and device path do not change.

---

## Cloning a VM

### Single-node

Proxmox offers both clone types through its GUI:

- **Full Clone** (right-click VM → Clone → Mode: Full Clone): creates an
  independent copy.
- **Linked Clone** (right-click VM → Clone → Mode: Linked Clone): creates a
  ZFS clone with shared blocks.

!!! note "ZFSutilities clone scripts vs Proxmox GUI clones"
    In single-node mode, you can use **either** the Proxmox GUI or the
    ZFSutilities clone scripts. The Proxmox GUI handles everything
    automatically — disk creation, VM config, MAC regeneration. The scripts
    provide the same result but with more control over snapshot naming and
    clone lifecycle management via [`promote-vm-clone`](../commands-and-modules/two-node.md#promote-vm-clone-both) and [`list-vm-disks`](../commands-and-modules/two-node.md#list-vm-disks-both).

    If you use Proxmox GUI clones, Proxmox manages the clone dependency
    chain. If you use [`zfsclone-vm`](../commands-and-modules/two-node.md#zfsclone-vm-both),
    ZFSutilities manages it. Do not mix the two approaches for the same VM —
    pick one and stay with it.

### Two-node

Proxmox has no ZFS awareness over iSCSI, so neither clone type works from
the Proxmox GUI. Use the scripts:

- **Full copy**: `clone-vm <src_vmid> <dst_vmid> <name>`
- **ZFS clone**: `zfsclone-vm <src_vmid> <dst_vmid> <name>`

For background on how ZFS clones work, see
[ZFS Clones](concepts.md#zfs-clones) in Concepts and Terminology.

---

### Prerequisites

- The source VM must be **stopped** before cloning.
- In a two-node configuration, the source VM's disks must use the iSCSI by-path
  format in Proxmox config (all VMs created by ZFS Utilities satisfy this).
- In a two-node configuration, run from the compute node. If run from the
  storage node, the script delegates to the compute node automatically.

### Creating a ZFS-Cloned VM

```bash
sudo zfsclone-vm <src_vmid> <dst_vmid> <new_name>
```

| Argument   | Description                                |
| ---------- | ------------------------------------------ |
| `src_vmid` | VM ID of the template VM (must be stopped) |
| `dst_vmid` | New VM ID for the clone                    |
| `new_name` | Name for the new VM                        |

**Example:**

```bash
sudo zfsclone-vm 904 310 myvm
```

The script discovers the source VM's disks, snapshots each source zvol, creates
a ZFS clone from each snapshot, and (in two-node mode) registers the clones as
new iSCSI LUNs. It then writes a new Proxmox VM config with fresh MAC
address(es), `vmgenid`, and SMBIOS UUID. After the script completes, the new VM
appears in Proxmox.

**Review the hardware settings in the GUI before starting it** — CPU, memory,
and network settings are copied from the source and may need adjustment.

For the exact steps the script performs in single-node vs two-node mode, see
the [`zfsclone-vm` command reference](../commands-and-modules/two-node.md#zfsclone-vm-both).

#### What the clone shares with the source

The new VM's disks start as exact copies of the VM at the moment of the clone
snapshot. As the new VM runs and writes data, only the changed blocks consume
additional storage. The source VM and all other clones continue sharing
unchanged blocks.

#### Clone origin snapshot

`zfsclone-vm` creates a snapshot on each source zvol named:

```
@clone-<yyyy-mm-dd>T<hh:mm><tz>-c
```

This snapshot is retained on the source zvols for as long as any clone depends
on it. If you clone the same source VM multiple times, snapshots from earlier
runs are preserved alongside the new one.

### Viewing Clone Relationships

```bash
sudo list-vm-disks
```

Each line shows the LUN number, disk name, size, and clone annotations:

```
  lun25   vm-904-disk-0   4M    [cloned by: vm-310, vm-315]
  lun26   vm-904-disk-1   50G   [cloned by: vm-310, vm-315]
  lun27   vm-310-disk-0   4M    [clone of vm-904]
  lun28   vm-310-disk-1   50G   [clone of vm-904]
```

You can also query ZFS directly on the storage node:

```bash
# Show what a disk was cloned from:
zfs get origin threeamigos/proxmox/vm-310-disk-1

# Show all snapshots of a zvol and their clone dependents:
zfs list -t snapshot -o name,clones -r threeamigos/proxmox/vm-904-disk-1
```

### Troubleshooting

#### "No iSCSI disks found in source VM config"

The source VM has no disks in the iSCSI by-path format. This can happen if:

- The VM has only a CDROM or no disks (e.g., a placeholder VM)
- Disks are still in the old `scsi-<NAA-ID>` format rather than by-path

VMs created or modified with [`new-vm-disk`](../commands-and-modules/two-node.md#new-vm-disk-both)
always use the correct by-path format.

#### "Destination VM config already exists"

A VM with the specified `dst_vmid` already exists in Proxmox. Choose a different VM ID.

#### "ZFS clone dependents — cannot delete"

[`zfsdelfs`](../commands-and-modules/commands.md#zfsdelfs) is blocking deletion because a zvol has clone dependents. Run
[`promote-vm-clone`](../commands-and-modules/two-node.md#promote-vm-clone-both)
on one of the dependent VMs first, then retry.

### Backup Considerations

Cloned datasets are backed up normally by `zfsdailybackup` and
`zfssendoffsite`. In the backup stream, they are treated as **regular
datasets**, not as clones. This means:

- Each clone is sent independently and is restorable as a full dataset.
- Therefore, shared blocks between the dataset and its clones are stored twice on the backup pool.
- This is the correct behavior: clones have their own snapshot lineage and cannot be
  incrementally replicated while preserving their clone relationship.

**Do not enable `$skipclones`** in production backup scripts. Clones are writable datasets
with their own unique data. Excluding them from backup causes data loss.

---

## Archiving a VM

The [`archive-vm`](../commands-and-modules/commands.md#archive-vm) script
handles the entire archive process automatically. Archiving a VM permanently
severs all clone relationships associated with the VM and archives the VM's
data before destruction.

```bash
sudo archive-vm <vmid>
```

The script stops the VM, discovers any clone VMs that still depend on its
zvol snapshots, and (if any exist) asks you to promote them first. It then
reads the Proxmox VM config to determine which disks are currently attached
and archives only those referenced zvols. Any zvols that match the VM ID but
are no longer referenced in the config are left behind with a warning, so you
can decide whether to archive or destroy them separately. After archiving the
zvols under an archive base path of your choice and copying the Proxmox VM
config alongside the archive, it — after confirmation — removes the original
VM config and destroys the original referenced zvols.

For the exact archive layout and single-node vs two-node behavior, see the
[`archive-vm` command reference](../commands-and-modules/commands.md#archive-vm).

### Unarchiving a VM

If you later need to restore an archived VM from archive, use
[`unarchive-vm`](../commands-and-modules/commands.md#unarchive-vm):

```bash
sudo unarchive-vm <vmid> [archive_base] [--new-vmid <new_vmid>]
```

| Argument         | Description                                                                                |
| ---------------- | ------------------------------------------------------------------------------------------ |
| `vmid`           | VM ID of the archived VM to restore                                                         |
| `archive_base`   | Optional ZFS dataset that contains the archive (defaults to the path saved in JSON config)  |
| `--new-vmid`     | Optional new VM ID to use for restored resources                                            |

The script discovers archived zvols, restores each one with its original
`volblocksize`, rebuilds iSCSI backstores and LUNs in two-node mode, restores
the Proxmox config, and triggers an iSCSI rescan. Cloned datasets are archived
as full datasets and are therefore restored as full datasets.

If the original `vmid` is already in use and you do not pass `--new-vmid`, the
script prompts you to enter a new VM ID or cancel. When a new VM ID is used,
the restored zvols, iSCSI backstores, LUNs, and Proxmox config are all named
with the new VM ID, and `vmgenid`/`smbios1` UUIDs are regenerated so the
restored VM does not share identifiers with the original.

For the exact restoration steps and sidecar files used, see the
[`unarchive-vm` command reference](../commands-and-modules/commands.md#unarchive-vm).

---

## Snapshots

### Proxmox-managed snapshots (single-node only)

With local ZFS, Proxmox can take VM snapshots from the Proxmox GUI (**Snapshots →
Take Snapshot**). These include VM state (RAM) if the VM is running, and
create ZFS snapshots of each disk zvol. Proxmox names them
`__replicate_<N>` or uses the name you provide.

These are managed entirely by Proxmox — visible in the Snapshots tab, and
can be rolled back or deleted from there.

### ZFSutilities-managed snapshots (both modes)

ZFSutilities creates its own snapshots for backup and retention purposes,
using the naming convention `@<label>-<timestamp>-<bucket>`. These are
**not** visible in the Proxmox GUI Snapshots tab (Proxmox only shows
snapshots it created). Manage them through:

- The **ZFSutilities GTK GUI** → Datasets tab (view, create, delete, hold,
  rollback)
- The command line: `zfs list -t snapshot`, `zfs destroy`, etc.

!!! warning "Do not delete ZFSutilities snapshots from the Proxmox GUI"
    If a ZFSutilities snapshot appears in the Proxmox Snapshots tab (unlikely
    but possible in single-node mode), do not delete it from there. ZFS holds
    and incremental backup chains may depend on it. Use the ZFSutilities
    GUI or scripts to manage these snapshots.

---

## Pool and Dataset Monitoring

### Single-node

- **Proxmox GUI**: Node → **Disks → ZFS** shows pool status, health, and
  usage. This is a read-only summary — useful for a quick health check.
- **ZFSutilities GTK GUI**: The **Pools** tab shows detailed pool status
  (health, size, alloc, free, fragmentation, capacity). The **Datasets**
  tab shows the full dataset/snapshot/hold tree with clone relationships.
  Pool Watch windows provide per-pool auto-refreshing views.

### Two-node

- **Proxmox GUI**: Node → **Disks** shows iSCSI block devices but has no
  ZFS awareness. Pool health is not visible.
- **ZFSutilities GTK GUI**: Run on the storage host. Provides the same
  Pools and Datasets views as single-node mode.
- **Command line on storage host**: `zpool status`, `zpool list`, `zfs list`

---

## Pre-restore Checks

Before restoring a dataset that is on a Proxmox storage pool, verify no VMs are
running that use it. The restore will be blocked if running VMs are detected.

Use the [`zfscheckrunningvms`](../commands-and-modules/modules.md#zfscheckrunningvms)
helper:

```bash
source ./zfscheckrunningvms
checkrunningvms "pool/dataset"
```

---

## What Proxmox Can Always Do (Both Modes)

These Proxmox GUI operations work identically regardless of node configuration:

- **Start / stop / restart VMs** — the VM management layer is the same
- **Console access** — VNC/SPICE console, serial terminal
- **CPU, memory, network settings** — Hardware tab
- **ISO management** — upload ISOs to local storage
- **Firewall rules** — per-VM or per-node
- **Backup to Proxmox Backup Server** — if configured (separate from
  ZFSutilities backups)
- **Migration** — not applicable (single node or non-clustered two-node)
- **Task logs and syslog** — node-level logging

---

## Summary: When to Use the Proxmox GUI vs. Scripts

### Single-node

Use the Proxmox GUI for most day-to-day operations. You only need
ZFSutilities scripts and the GTK GUI for:

- **Multi-pool backup and replication** ([`zfsdailybackup`](../commands-and-modules/commands.md#zfsdailybackup), [`zfssendoffsite`](../commands-and-modules/commands.md#zfssendoffsite))
- **Retention policy management** (GTK GUI Retention tab or [`zfsretain`](../commands-and-modules/modules.md#zfsretain))
- **Detailed dataset/snapshot browsing** with clone relationships (GTK GUI
  Datasets tab)
- **Offsite backup** to portable drives ([`zfssendoffsite`](../commands-and-modules/commands.md#zfssendoffsite))

### Two-node

The Proxmox GUI handles VM runtime management (start, stop, console,
hardware settings). For everything storage-related, use ZFSutilities:

- **All disk operations**: create, resize, delete, move ([`new-vm-disk`](../commands-and-modules/two-node.md#new-vm-disk-both),
  [`resize-vm-disk`](../commands-and-modules/two-node.md#resize-vm-disk-both),
  [`remove-vm-disk`](../commands-and-modules/two-node.md#remove-vm-disk-both),
  [`move-vm-disk`](../commands-and-modules/two-node.md#move-vm-disk-both))
- **All clone operations**: [`zfsclone-vm`](../commands-and-modules/two-node.md#zfsclone-vm-both),
  [`clone-vm`](../commands-and-modules/two-node.md#clone-vm-both),
  [`promote-vm-clone`](../commands-and-modules/two-node.md#promote-vm-clone-both)
- **Pool and dataset monitoring**: ZFSutilities GTK GUI
- **Backup, retention, offsite**: ZFSutilities scripts

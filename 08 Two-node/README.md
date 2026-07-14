# Two-Node VM Disk Management (Example Deployment)

This README describes an example two-node deployment. Replace hostnames, pool
names, and IQN prefixes with your own infrastructure.

# VM Disk Management Scripts

Scripts for managing Proxmox VM disks stored as ZFS zvols and exported via iSCSI.

## Problem

Proxmox's iSCSI storage type is read-only — it can discover and attach existing
LUNs but cannot create new zvols. Adding a new VM or disk requires manual steps
on storage-host before anything can happen in the Proxmox GUI.

## Scripts

All scripts are installed on **both storage-host and compute-host** and run from **compute-host**.
When run on compute-host, they automatically SSH to storage-host for storage operations and
handle the iSCSI rescan locally.

### On Tweety (run these as the admin)

| Script | Purpose |
|--------|---------|
| `new-vm-disk <pool> <vmid> <disk-num> <size>` | Create zvol + add iSCSI LUN |
| `remove-vm-disk <pool> <vmid> <disk-num>` | Remove LUN + destroy zvol |
| `detach-vm-disk <vmid> <disk-key>` | Remove disk from VM config + tear down iSCSI (keeps zvol) |
| `attach-vm-disk <zvol> <vmid> [dst-key]` | Attach existing zvol to a VM (rebuilds iSCSI if needed) |
| `list-vm-disks [--with-devices]` | List exported LUNs with VMID, VM name, host/guest device names |
| `resize-vm-disk <pool> <vmid> <disk-num> <new-size>` | Grow zvol online |
| `clone-vm <src_vmid> <dst_vmid> <new_name>` | Clone a VM (disks + config) |
| `move-vm-disk <src_vmid> <src_key> <dst_vmid> [dst_key]` | Move a disk from one VM to another |
| `rescan-storage` | Rescan iSCSI sessions to see new/changed LUNs |
| `show-lun-map` | Show LUN → /dev/sdX mapping with sizes |

## Installation

### Prerequisites

Root SSH key trust must be established **in both directions** between the
storage host and the compute host. The installer will fail early if either
direction is not working.

**1. Storage host → compute host:**

On the storage host:
```bash
ssh-copy-id root@<compute-host>
```

**2. Compute host → storage host:**

On the compute host:
```bash
ssh-copy-id root@<storage-host>
```

### Install

Use the versioned installer from the repository root:

```bash
sudo /path/to/zfsutilities-dev/10 Installers/install-two-node
```

This deploys scripts as a versioned installation to
`/usr/local/lib/zfsutilities/versions/<version>/` on both hosts, creates
PATH configuration via `/usr/local/lib/zfsutilities/bin/`, and checks SSH/sudo prerequisites.

For a simpler single-node setup (no separate storage host):

```bash
sudo /path/to/zfsutilities-dev/10 Installers/install-single-node
```

**Legacy:** The old `install-scripts` in this directory is deprecated. Use the
new installers above.

## Workflow: Adding a New VM (without EFI)

For VMs using legacy BIOS (SeaBIOS) — simpler, works for most Linux VMs:

```bash
# On compute-host — all commands run here
sudo new-vm-disk tank 300 0 50G    # boot disk
sudo new-vm-disk tank 300 1 500G   # data disk (if needed)

# In Proxmox GUI:
#   Create VM 300 (select "Do not use any media" for disk)
#   Hardware → Add → Hard Disk → Storage: iscsi-tank → select LUN
#   Attach ISO, configure, boot
```

## Workflow: Adding a New VM (with EFI / UEFI boot)

Required for Windows 11, and recommended for modern Linux. The EFI disk stores
UEFI firmware variables (boot order, Secure Boot state, etc.) and must be
initialized before first boot — the script handles this automatically.

```bash
# On compute-host — all commands run here

# 1. Create the EFI firmware disk first
#    The script will ask about Secure Boot:
#      y = pre-enroll Microsoft + distro keys (required for Windows 11)
#      N = clean slate, Secure Boot off (simpler for Linux, can enable later)
sudo new-vm-disk tank 300 0 EFI

# 2. Create the boot and data disks as normal
sudo new-vm-disk tank 300 1 50G    # boot disk
sudo new-vm-disk tank 300 2 500G   # data disk (if needed)

# In Proxmox GUI:
#   Create VM 300 — on the System tab, set BIOS to OVMF (UEFI) and
#     uncheck "Add EFI Disk" (our script already created and configured it)
#   Hardware → Add → Hard Disk → Storage: iscsi-tank → select boot LUN
#   Attach ISO, configure, boot
```

**Note:** The Proxmox GUI's "Add EFI Disk" button does not work with iSCSI
storage — it fails trying to initialize the disk. The `new-vm-disk EFI` script
does the full job: creates the zvol, exports the LUN, initializes the firmware
variables with `dd`, and adds `bios: ovmf` + `efidisk0:` to the VM config.

When you choose Secure Boot pre-enrollment, the generated `efidisk0` line
includes `ms-cert=2023k`, which tells Proxmox that the 2023 Microsoft UEFI
certificates are enrolled. This avoids the Proxmox warning about expired 2011
certificates.

For existing VMs created before this change, use the helper script:

```bash
sudo enroll-efi-keys-vm <vmid>
```

This grows the EFI zvol to 4M, re-initializes it with the 2023 Microsoft
vars file, and updates the Proxmox config.

!!! warning "Do not use Proxmox's 'Enroll Updated Certificates' action with iSCSI"

    The Proxmox GUI (**Hardware → EFI Disk → Disk Action → Enroll Updated
    Certificates**) and the `qm enroll-efi-keys` command cannot parse the
    raw `by-path` volume identifier used for iSCSI EFI disks. They fail with
    an error such as `unable to parse volume ID '/dev/disk/by-path/...'`.

    For iSCSI-backed VMs, always use `sudo enroll-efi-keys-vm <vmid>`
    instead.

## Workflow: Cloning a VM

The Proxmox GUI clone operation does not work with iSCSI storage — it cannot
create zvols. Use `clone-vm` instead. It ZFS-copies all disks on storage-host, creates
new iSCSI LUNs, and writes a new Proxmox config with a fresh vmgenid and MAC
address.

```bash
# 1. Stop the source VM in Proxmox GUI (required — disks must be idle)

# 2. On compute-host:
sudo clone-vm 904 310 fileserver2

# The script will:
#   - Show the disks it will clone and ask for confirmation
#   - ZFS snapshot + send/receive each disk zvol on storage-host
#   - Create new iSCSI LUNs for the cloned zvols
#   - Write /etc/pve/qemu-server/310.conf (copied from 904, with new LUNs,
#     new vmgenid, new MAC address, and the new name)
#   - Rescan iSCSI so compute-host sees the new LUNs

# 3. In Proxmox GUI:
#   VM 310 appears immediately — review hardware before starting
```

**Note:** The config is copied as-is (CPU, RAM, machine type, boot order, etc.),
which is the point of cloning from a template. Adjust anything you need in the
GUI after the clone.

## Workflow: Moving a Disk to Another VM

```bash
# 1. Stop both VMs in the Proxmox GUI

# 2. On compute-host:
sudo move-vm-disk 100 scsi1 200          # move scsi1 from VM 100 → next free scsi on VM 200
# or:
sudo move-vm-disk 100 scsi1 200 scsi0    # move scsi1 from VM 100 → scsi0 on VM 200

# The script will:
#   - Verify both VMs are stopped
#   - Verify the disk exists in the source VM config
#   - SSH to storage-host to confirm the backing zvol exists (two-node only)
#   - Auto-select the next free disk slot on the destination VM (if not specified)
#   - Ask for confirmation, then move the config line
#   - Rescan iSCSI
```

**Note:** The underlying zvol and iSCSI LUN are not renamed. Only the Proxmox VM
config attachment changes. The zvol name will still reference the original VM ID,
which is harmless metadata. To reverse the move, run the command with source and
destination swapped.

## Workflow: Detaching a Disk (without destroying it)

Use this when you want to remove a disk from a VM but keep the zvol for later
re-attachment or manual management:

```bash
# 1. Stop the VM in the Proxmox GUI

# 2. On compute-host:
sudo detach-vm-disk 300 scsi1

# The script will:
#   - Remove scsi1 from VM 300's Proxmox config
#   - Remove the iSCSI LUN and backstore (two-node)
#   - Leave the underlying zvol intact
#   - Trigger an iSCSI rescan
```

## Workflow: Attaching an Existing Disk to a VM

Use this to attach a zvol that was previously detached (or created manually)
to a VM:

```bash
# On compute-host:
sudo attach-vm-disk tank/proxmox/vm-100-disk-0 200
# or specify the destination slot:
sudo attach-vm-disk tank/proxmox/vm-100-disk-0 200 scsi2

# The script will:
#   - Verify the zvol exists
#   - Rebuild iSCSI backstore and LUN if missing (two-node)
#   - Auto-detect the next free scsi slot (or use the one you specified)
#   - Add the disk line to VM 200's Proxmox config
#   - Trigger an iSCSI rescan
```

## Workflow: Removing a VM's Disks (permanent destruction)

```bash
# 1. In Proxmox GUI: Stop VM → Hardware → select disk → Detach → Remove

# 2. On compute-host:
sudo remove-vm-disk tank 300 0
sudo remove-vm-disk tank 300 1
```

## Workflow: Resizing a Disk

```bash
# First, find the current size:
sudo list-vm-disks

# Then resize — specify the TOTAL final size, not the increment.
# (This differs from the Proxmox GUI, which asks for the amount to add.)
# Example: disk is currently 100G and you want it to be 200G:
sudo resize-vm-disk tank 300 1 200G

# Then inside the VM: resize partition + filesystem (growpart, resize2fs, etc.)
```

## Pool → Target Mapping

| Pool | iSCSI Target | Proxmox Storage Name |
|------|-------------|---------------------|
| `tank` | `iqn.2026-02.local.storage-host:tank` | `iscsi-tank` |
| `nvme-pool` | `iqn.2026-02.local.storage-host:nvme1` | `iscsi-nvme1` |

## Important Notes

- **Stop VMs before removing disks.** Removing an active LUN causes I/O errors.
- **ZFS only grows, never shrinks.** `resize-vm-disk` only accepts larger sizes.
- **Encrypted zvols**: vm-101-disk-1 and vm-202-disk-5 require the LUKS USB key
  to be loaded. See `06 Docs/docs/installation/zfs-keys.md` for the full
  key-handling workflow.
- All zvols are created with `compression=lz4`.

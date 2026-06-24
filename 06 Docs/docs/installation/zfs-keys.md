# ZFS Key Handling for Two-Node Installations

In a two-node setup the Proxmox VM disks are stored as encrypted ZFS zvols on
the storage node (`stewie`). The encryption keys themselves are stored on a
removable USB device that is protected by LUKS full-disk encryption. This
guide explains how to prepare the USB device, create keys, create encrypted
zvols, and recover from a boot where the USB was not inserted.

## Overview

```
┌─────────────────┐      LUKS       ┌─────────────────┐      ZFS       ┌─────────────┐
│  USB drive with │  ─────────────► │  decrypted key  │  ────────────► │ encrypted   │
│  key files      │   passphrase    │  files          │   load-key     │ zvols       │
└─────────────────┘                 └─────────────────┘                └─────────────┘
```

- **ZFS native encryption** protects the zvols at rest.
- **LUKS encryption** protects the USB device that holds the ZFS keys.
- At boot, the `zfs-keys-unlock.service` unlocks the LUKS volume and loads the
  ZFS keys into kernel memory. The USB can then be removed.
- If the USB is not present at boot, the storage node still starts iSCSI, but
  the encrypted LUNs remain offline until keys are loaded manually.

## Requirements

- A USB drive (or multiple USB drives) large enough to hold a few small key
  files. A few megabytes is plenty.
- Root access to the storage node.
- The `cryptsetup` package installed.

## Preparing the USB device

These commands run on the storage node as root. Replace `/dev/sdX1` with the
actual partition you want to use.

!!! warning "This will destroy all data on /dev/sdX1"
    Double-check the device name. `lsblk` can help identify the correct USB
    device.

```bash
# Create a LUKS-encrypted partition
cryptsetup luksFormat /dev/sdX1

# Open the LUKS volume with a temporary mapper name
cryptsetup luksOpen /dev/sdX1 zfskeys-setup

# Create a filesystem with the label ZFSkeys
mkfs.ext4 /dev/mapper/zfskeys-setup -L ZFSkeys

# Close the LUKS volume
cryptsetup luksClose zfskeys-setup
```

Set the partition label to `ZFSkeys` as well so the boot scripts can find the
USB:

```bash
# Set the partition label (optional but recommended)
parted /dev/sdX --name 1 ZFSkeys
```

## Generating and storing ZFS keys

Each encrypted dataset needs its own key file. Generate random key files on
the USB:

```bash
# Mount the USB
mkdir -p /mnt/ZFSkeys
cryptsetup luksOpen /dev/sdX1 keys
mount LABEL=ZFSkeys /mnt/ZFSkeys

# Generate a key file for each encrypted dataset
dd if=/dev/urandom of=/mnt/ZFSkeys/key1 bs=32 count=1
dd if=/dev/urandom of=/mnt/ZFSkeys/key2 bs=32 count=1
chmod 400 /mnt/ZFSkeys/key1 /mnt/ZFSkeys/key2

# Unmount and lock
umount /mnt/ZFSkeys
cryptsetup luksClose keys
```

Keep offline backups of:

- the key files on the USB, and
- the LUKS passphrase.

Without both the LUKS passphrase and a copy of the key files, the encrypted
zvols cannot be recovered.

## Creating an encrypted zvol

Use `new-vm-disk` with the `--encrypted` flag. The script will prompt for the
key file on `/mnt/ZFSkeys`:

```bash
sudo new-vm-disk threeamigos 300 0 50G --encrypted
```

The script:

1. Asks you to insert the ZFS keys USB.
2. Unlocks the LUKS volume (prompting for the passphrase if no
   `/root/.luks-key` exists).
3. Mounts the decrypted filesystem at `/mnt/ZFSkeys`.
4. Lists the available key files and asks which one to use.
5. Creates the zvol with `keylocation=file:///mnt/ZFSkeys/<keyname>`.
6. Records the zvol in `/etc/iscsi-encrypted-luns.conf`.
7. Secures the keys (unmounts and closes the LUKS volume).

## Boot-time behaviour

### With `/root/.luks-key` (unattended boot)

If you created `/root/.luks-key` during installation (or manually afterward),
the boot process is fully automatic:

1. `zfs-keys-unlock.service` waits for the USB device.
2. It unlocks the LUKS volume using `/root/.luks-key`.
3. It mounts the filesystem at `/mnt/ZFSkeys`.
4. It loads the ZFS keys for all encrypted zvols.
5. It unmounts and closes the LUKS volume.
6. `rtslib-fb-targetctl.service` starts and adds the encrypted LUNs back to
   the iSCSI target.

The USB can be removed once the service reports success.

### Without `/root/.luks-key` (manual boot)

If no keyfile exists, the boot service exits cleanly and iSCSI starts without
the encrypted LUNs. To bring them online:

1. Insert the ZFS keys USB.
2. If Cinnamon/udisksd prompts for the LUKS passphrase, you can enter it
   (the device will be mounted at `/mnt/ZFSkeys`), or cancel and let the
   script handle unlocking.
3. Run:
   ```bash
   sudo unlock-zfs-keys
   ```
4. The script prompts for the LUKS passphrase if needed, loads the ZFS keys,
   and adds the encrypted LUNs to the iSCSI target without restarting it.

## Recovery after a boot without the USB

If the storage node booted without the USB:

1. Verify the non-encrypted LUNs are online:
   ```bash
   targetcli /backstores/block ls
   ```
2. Insert the USB.
3. Run `sudo unlock-zfs-keys` (or `sudo unlock-zfs-keys-auto` if
   `/root/.luks-key` exists).
4. Verify the encrypted LUNs are online:
   ```bash
   targetcli /backstores/block ls | grep -E 'vm-101-disk-1|vm-202-disk-5'
   ```

## Enabling unattended boot later

To create `/root/.luks-key` after installation:

```bash
# Generate a random keyfile
sudo dd if=/dev/urandom of=/root/.luks-key bs=4096 count=1
sudo chmod 400 /root/.luks-key

# Add it to each ZFS keys USB device
for dev in $(sudo blkid -t PARTLABEL=ZFSkeys -o device); do
    sudo cryptsetup luksAddKey "$dev" /root/.luks-key
done
```

Verify it works on each device:

```bash
for dev in $(sudo blkid -t PARTLABEL=ZFSkeys -o device); do
    sudo cryptsetup luksOpen "$dev" keys --key-file /root/.luks-key
    sudo cryptsetup luksClose keys
    echo "OK: $dev"
done
```

## Disabling unattended boot

To remove the keyfile from all devices and delete it:

```bash
for dev in $(sudo blkid -t PARTLABEL=ZFSkeys -o device); do
    sudo cryptsetup luksRemoveKey "$dev" /root/.luks-key
done
sudo rm -f /root/.luks-key
```

## Interaction with the Cinnamon desktop

The Cinnamon desktop includes `udisksd`, which may prompt for the LUKS
passphrase when the USB is inserted after boot. This is not a problem:

- At boot, `zfs-keys-unlock.service` runs before the desktop and is in full
  control.
- After boot, you can use the Cinnamon prompt to unlock and mount the USB, or
  cancel it and use `unlock-zfs-keys` instead. The script detects an
  already-mounted `/mnt/ZFSkeys` and reuses it.

## Multiple USB keys

You can maintain multiple LUKS-encrypted USB devices with the same label
(`ZFSkeys`). The boot scripts use the first one found. Add `/root/.luks-key` to
all of them if you want any one of them to work for unattended boot.

## Security notes

- `/root/.luks-key` is root-readable only (`chmod 400`). It is required for
  unattended boot. Anyone with root access or physical access to the unmounted
  root filesystem can read it.
- The LUKS passphrase is still required to add or remove the keyfile. Store it
  securely and separately from the USB devices.
- Key files on the USB are not encrypted by ZFSutilities; they are protected
  by the LUKS container on the USB. Keep the USB physically secure.
- Remove the USB after boot once keys are loaded.

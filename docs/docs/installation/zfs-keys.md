# ZFS Key Handling for Two-Node Installations

In a two-node setup the Proxmox VM disks can be stored as encrypted ZFS zvols on
the storage node (`stewie`). ZFS Utilities does **not** provide automatic
unlocking or automatic mounting of a LUKS-protected key store. Instead, the
operator manually unlocks the key store, loads the ZFS keys, and brings the
encrypted LUNs online.

This guide explains how to prepare key files, create encrypted zvols, and bring
them online after a reboot.

For an overview of all documentation sections, return to the
[ZFS Utilities home page](../index.md).

## Why there is no automatic unlock

Earlier versions of ZFS Utilities shipped with `zfs-keys-unlock.service`,
`unlock-zfs-keys`, and `/root/.luks-key` to automate LUKS USB detection and ZFS
key loading. That automation was removed because it created several production
problems:

- **Ordering race** — iSCSI target startup and ZFS key loading had to be
  sequenced exactly. On many systems the race was invisible until a slow boot or
  a missing USB caused `rtslib-fb-targetctl` to fail entirely.
- **USB availability race** — The boot service waited for a USB device with
  `PARTLABEL=ZFSkeys`. If the device was on a hub that enumerated late, or was
  not inserted, the service would time out or leave iSCSI in a failed state.
- **`keylocation=prompt` console block** — If any encrypted dataset used
  `keylocation=prompt`, `zfs load-key -a` blocked on the physical console. In
  headless or remote environments this could hang the boot indefinitely.
- **Root-on-ZFS mismatch** — On systems where `/` is on ZFS, the encrypted root
  dataset needed its key before userspace could run, but the helper scripts ran
  from `/root/bashinit` after root was already supposed to be mounted.
- **`/root/.luks-key` undermined the theft model** — A root-readable keyfile that
  unlocks the LUKS container holding the ZFS keys is only slightly harder to
  steal than the keys themselves. Automatic unattended boot with that keyfile
  was convenient but reduced the security benefit of keeping keys on a separate,
  removable device.

The replacement is a small, explicit manual workflow that keeps encrypted-zvol
support intact without any of the boot-time races.

## Requirements

- A secure location for ZFS key files. A LUKS-encrypted USB drive is a common
  choice, but any path the operator can make available at runtime will work.
- Root access to the storage node.
- The `cryptsetup` package installed if you use LUKS.

## Preparing a LUKS-encrypted USB key store (optional)

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

## Generating and storing ZFS keys

Each encrypted dataset needs its own key file. Generate random key files on the
unlocked key store:

```bash
# Mount the key store
sudo cryptsetup luksOpen /dev/sdX1 keys
sudo mkdir -p /mnt/ZFSkeys
sudo mount /dev/mapper/keys /mnt/ZFSkeys

# Generate a key file for each encrypted pool/dataset
sudo mkdir -p /mnt/ZFSkeys/keys
sudo dd if=/dev/urandom of=/mnt/ZFSkeys/keys/threeamigos.key bs=32 count=1
sudo dd if=/dev/urandom of=/mnt/ZFSkeys/keys/NVME1.key bs=32 count=1
sudo chmod 400 /mnt/ZFSkeys/keys/*.key
```

Keep offline backups of:

- the key files on the USB, and
- the LUKS passphrase.

Without both the LUKS passphrase and a copy of the key files, the encrypted
zvols cannot be recovered.

## Creating an encrypted zvol

Use `new-vm-disk` with the `--encrypted` flag. The script will prompt for the
absolute path to an already-accessible key file:

```bash
sudo new-vm-disk threeamigos 300 0 50G --encrypted
```

The script:

1. Asks for the absolute key-file path (e.g. `/mnt/ZFSkeys/keys/threeamigos.key`).
2. Verifies the file exists, is readable, and is not group- or world-readable.
3. Verifies the key file does not reside on the pool or dataset being created.
4. Creates the zvol with `keylocation=file:///mnt/ZFSkeys/keys/threeamigos.key`.
5. Records the zvol in `/etc/zfsutilities/iscsi-encrypted-luns.conf`.

The key file must already be accessible when you run `new-vm-disk --encrypted`.

## Boot-time behaviour

At boot:

1. `rtslib-fb-targetctl.service` starts and restores the boot-safe config
   (`saveconfig-boot.json`), which excludes encrypted backstores. This lets the
   storage node come online without the encrypted LUNs.
2. Encrypted LUNs remain offline until you manually load their keys and run
   `iscsi-add-encrypted-luns`.

## Bringing encrypted zvols online after boot

To bring encrypted zvols online:

1. Unlock and mount the key store:
   ```bash
   sudo cryptsetup luksOpen /dev/sdX1 keys
   sudo mkdir -p /mnt/ZFSkeys
   sudo mount /dev/mapper/keys /mnt/ZFSkeys
   ```
2. Load all ZFS keys:
   ```bash
   sudo zfs load-key -a
   ```
   Note: `-a` loads keys for all pools and blocks on any `keylocation=prompt`
   dataset. Use `zfs load-key <pool/dataset>` for a single dataset if needed.
3. Add the encrypted LUNs to the running iSCSI target:
   ```bash
   sudo iscsi-add-encrypted-luns
   ```
4. Unmount and lock the key store:
   ```bash
   sudo umount /mnt/ZFSkeys
   sudo cryptsetup luksClose keys
   ```

## Restarting iSCSI services

If you restart the iSCSI target service (`restart-iscsi-services`), it restores
`saveconfig-boot.json` and then explicitly calls `iscsi-add-encrypted-luns` to
re-add encrypted LUNs whose zvols are already available.

## Recovery after a boot without the USB

If the storage node booted without the key store:

1. Verify the non-encrypted LUNs are online:
   ```bash
   targetcli /backstores/block ls
   ```
2. Make the key store accessible.
3. Run `sudo zfs load-key -a` and `sudo iscsi-add-encrypted-luns`.
4. Verify the encrypted LUNs are online:
   ```bash
   targetcli /backstores/block ls | grep -E 'vm-101-disk-1|vm-202-disk-5'
   ```

## Interaction with the desktop

The Cinnamon desktop includes `udisksd`, which may prompt for the LUKS passphrase
when the USB is inserted after boot. You can use that prompt to unlock and mount
the key store, then run the commands above.

## Multiple USB keys

You can maintain multiple LUKS-encrypted USB devices with the same key files.
There is no automation that selects among them; mount whichever device you have
available and use its path when loading keys or creating zvols.

## Security notes

- Key files on the USB are not encrypted by ZFSutilities; they are protected by
  the LUKS container on the USB. Keep the USB physically secure.
- Do not store key files on the same pool that they encrypt. `new-vm-disk`
  rejects such paths.
- Keep key files readable only by root (`chmod 400`). `new-vm-disk` rejects
  group- or world-readable keys.
- Remove the USB after keys are loaded.
- ZFS Utilities no longer creates or manages `/root/.luks-key`.

# Two-Node Infrastructure Commands

These scripts manage the two-node Proxmox/ZFS setup: a **compute node** (running VMs) and a dedicated **storage node** (hosting the ZFS pools and exporting VM disks via iSCSI). They are deployed via the versioned installation to `/usr/local/lib/zfsutilities/bin/` on one or both nodes and are not part of the core ZFS Utilities backup system.

Scripts marked **both** run on either node and delegate automatically via SSH as appropriate. Scripts marked **storage node** or **compute node** are node-specific.

All of these scripts source `/usr/local/lib/node-lib.sh`, which reads
`/etc/zfsutilities-node.conf` and populates the node-configuration global variables.
These global variables apply to every entry below — they are documented once here
rather than repeated in every entry:

| Variable                       | Purpose                                                                | Reference                                                                          |
| ------------------------------ | ---------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `NODE_MODE`                    | `single-node` or `two-node` — gates all iSCSI and SSH-delegation logic | [Node Configuration](../developer-guide/global-variables.md#node-configuration)    |
| `THIS_HOST`                    | Short hostname of the current node (single-node)                       | [Node Configuration](../developer-guide/global-variables.md#node-configuration)    |
| `STORAGE_HOST`, `COMPUTE_HOST` | Short hostnames of the two nodes (two-node)                            | [Node Configuration](../developer-guide/global-variables.md#node-configuration)    |
| `STORAGE_IP`                   | Storage-network IP of the storage node                                 | [Node Configuration](../developer-guide/global-variables.md#node-configuration)    |
| `IQN_PREFIX`                   | iSCSI IQN prefix for all targets                                       | [Node Configuration](../developer-guide/global-variables.md#node-configuration)    |
| `POOL_TARGET`                  | Pool → target short-name map                                           | [POOL_TARGET](../developer-guide/data-structures.md#pool_target-associative-array) |

The script-specific Arguments and Globals tables below omit these unless a
script uses one in a non-obvious way.

## Jump to

- [`attach-vm-disk` (both)](#attach-vm-disk-both)
- [`clone-vm` (both)](#clone-vm-both)
- [`deploy-version` (repo root)](#deploy-version-repo-root)
- [`detach-vm-disk` (both)](#detach-vm-disk-both)
- [`iscsi-add-encrypted-luns` (storage node)](#iscsi-add-encrypted-luns-storage-node)
- [`iscsi-restore-luns` (storage node)](#iscsi-restore-luns-storage-node)
- [`list-vm-disks` (both)](#list-vm-disks-both)
- [`lock-zfs-keys` (storage node)](#lock-zfs-keys-storage-node)
- [`move-vm-disk` (both)](#move-vm-disk-both)
- [`new-vm-disk` (both)](#new-vm-disk-both)
- [`switch-version` (any host)](#switch-version-any-host)
- [`uninstall-version` (any host)](#uninstall-version-any-host)
- [`promote-vm-clone` (both)](#promote-vm-clone-both)
- [`remove-vm-disk` (both)](#remove-vm-disk-both)
- [`unretire-vm` (both)](#unretire-vm-both)
- [`rescan-storage` (both)](#rescan-storage-both)
- [`resize-vm-disk` (both)](#resize-vm-disk-both)
- [`restart-iscsi-services` (storage node)](#restart-iscsi-services-storage-node)
- [`safe-iscsi-save` (storage node)](#safe-iscsi-save-storage-node)
- [`show-lun-map` (compute node)](#show-lun-map-compute-node)
- [`unlock-zfs-keys` (storage node)](#unlock-zfs-keys-storage-node)
- [`unlock-zfs-keys-auto` (storage node)](#unlock-zfs-keys-auto-storage-node)
- [`zfsclone-vm` (both)](#zfsclone-vm-both)

---

### `clone-vm` (both)

Creates a new Proxmox VM by copying its source VM's disk zvols via `zfs send/receive`.
Produces a fully independent copy with no ongoing ZFS dependency on the source.

```bash
sudo clone-vm <src_vmid> <dst_vmid> <new_name>
```

**Arguments:**

| Argument   | Description                    |
| ---------- | ------------------------------ |
| `src_vmid` | Source VM ID (must be stopped) |
| `dst_vmid` | New VM ID                      |
| `new_name` | Name for the new VM            |

**Globals:** node-config globals only (see table above).

For space-efficient provisioning from a gold template, use
[`zfsclone-vm`](#zfsclone-vm-both) instead.

---

### `deploy-version` (repo root)

Deploys the current repository state as a new versioned installation without
activating it. Run from the repository root.

```bash
sudo ./deploy-version [version] [group ...]
```

**Arguments:**

| Argument  | Description                                                                                                   |
| --------- | ------------------------------------------------------------------------------------------------------------- |
| `version` | Optional version string (default: reads `./VERSION`)                                                          |
| `group`   | Optional deployment-group name(s) (see `/etc/zfsutilities-deploy.conf`). If omitted, all groups are deployed. |

**Deployment targets:**

- **Local host** — always deployed directly

- **Remote hosts** — defined by `/etc/zfsutilities-deploy.conf` via named groups:
  
  ```bash
  # /etc/zfsutilities-deploy.conf
  DEPLOY_GROUP_production="stewie tweety"
  DEPLOY_GROUP_staging="staging-host"
  ```
  
  Each host in the selected group(s) receives the version. The group names do not have any special meaning to ZFSutilities. The hosts must be reachable via `ssh root@<hostname>`(password prompting  works if running from a terminal).

`deploy-version` creates a self-contained version directory at `/usr/local/lib/zfsutilities/versions/<version>/`.
Each version carries its own `bin/` (executable scripts) and `lib/` (helper libraries)
so that multiple versions can coexist on disk. Because every version is complete, rollback is
just `switch-version` repointing `current` and refreshing the production wiring — no files need to be copied or restored.

`deploy-version` does **not** touch active production wiring. It does not update the `current`
symlink, `PATH` configuration, `/root/bashinit`, library symlinks, or desktop shortcuts. It is safe to run at any time.

Files in the repository root are copied if they are **executable OR have a shebang** (`#!`),
so a script missing the executable bit in the repository is still deployed.
Retention policy files (`zfsretainpol-*`) and other executable data files are
also copied. Repository root exclusions: `*.md`, `.gitignore`, `installed-programs`, `PROMPT*`,
`VERSION`.

After copying files, `deploy-version` validates that critical root-level scripts
(`zfs-diagnose-busy`, `zfsdelsnap`, `zfscleanup`, `zfsretain`, `zfs-send-receive`)
are present in the versioned `bin/` directory. If any are missing, a warning is
printed so the operator knows the deployment is incomplete.

`deploy-version` refuses to run from a deployed path (it checks that the current
directory contains `.git/` or `VERSION`). This prevents accidentally deploying
an incomplete set of files when the script is invoked from `$PATH` rather than
the repository root.

If MkDocs is available, `deploy-version` also rebuilds the static documentation
site in the deployed directory so the pre-built fallback carries the correct
version stamp.

`deploy-version` creates two launcher symlinks in the versioned `bin/`
directory:

- `zfsutilities-gui` → `../07 GTK + Python/zfsutilities_gui.py`
- `zfsutilities-docs` → `../07 GTK + Python/docs_viewer.py`

These let you launch the GUI and standalone documentation viewer by name after
activating the version.

`deploy-version` also generates `/etc/zfsutilities-deploy.conf` at install time
(from `10 Installers/deploy.conf.template`) so the production hostnames are
available for future deployments.

See [Installation](../installation/index.md) for the full workflow.

---

### `iscsi-add-encrypted-luns` (storage node)

Adds iSCSI backstores and LUNs for encrypted zvols whose keys are currently loaded. ZFS encryption keys are not available at boot-time (when iSCSI is initiated), so the encrypted backstores are added separately when the encryption keys are available and loaded by ZFS.
Called automatically by [`unlock-zfs-keys`](#unlock-zfs-keys-storage-node) after
manual key loading and by [`restart-iscsi-services`](#restart-iscsi-services-storage-node)
at service startup.

**Arguments:** none.

**Globals:** node-config globals only.

**Data structures consumed:**

| Structure                        | Reference                                                                                  |
| -------------------------------- | ------------------------------------------------------------------------------------------ |
| `/etc/iscsi-encrypted-luns.conf` | [Encrypted-LUNs config](../developer-guide/data-structures.md#iscsi-encrypted-luns-config) |

---

### `iscsi-restore-luns` (storage node)

Restores missing iSCSI backstores and LUN mappings from `saveconfig.json`.
Idempotent — safe to run even if nothing is missing.

```bash
sudo iscsi-restore-luns
```

**Arguments:** none.

**Globals:** node-config globals only.

**What it does:**

1. Reads `/etc/rtslib-fb-target/expected-backstores.txt` for the authoritative list of expected LUN backstores

2. Compares against current `targetcli` backstores

3. For each missing backstore:
   
   - Creates the block backstore from the corresponding zvol device
   
   - Maps it to the correct iSCSI target with the original LUN index

4. Saves the updated iSCSI config

5. Runs `rescan-storage` on the compute host so its kernel sees the restored LUNs

Handles both encrypted and non-encrypted LUNs. Preserves original LUN indexes so compute node configs remain valid.

---

### `list-vm-disks` (both)

Lists all zvols currently exported as iSCSI LUNs, with sizes and clone relationships.

```bash
sudo list-vm-disks [--with-devices]
```

**Arguments:**

| Argument         | Description                                                                                                |
| ---------------- | ---------------------------------------------------------------------------------------------------------- |
| `--with-devices` | Also show the LUN-to-block-device map from the compute node ([`show-lun-map`](#show-lun-map-compute-node)) |

**Globals:** node-config globals only.

Output includes a `[clone of vm-N]` annotation for zvols that were created by
[`zfsclone-vm`](#zfsclone-vm-both), and a `[cloned by: vm-N, vm-M]`
annotation for zvols whose snapshots have clone dependents.

---

### `lock-zfs-keys` (storage node)

Safely unmounts `/mnt/ZFSkeys` and closes the LUKS mapper opened by the unlock
scripts. Run this before physically removing the USB drive. If udisksd opened a
different mapper name, it is left alone.

```bash
sudo lock-zfs-keys
```

**Arguments:** none.

**Globals:** none.

See [ZFS Key Handling](../installation/zfs-keys.md).

---

### `attach-vm-disk` (both)

Attaches an existing zvol to a Proxmox VM. In two-node mode, rebuilds the iSCSI
backstore and LUN if they do not exist. The destination disk slot is
auto-detected (next free `scsiN`) unless overridden. Adds the disk to the VM's configuration.

```bash
sudo attach-vm-disk <zvol> <vmid> [dst-disk-key]
```

**Arguments:**

| Argument       | Description                                                                             |
| -------------- | --------------------------------------------------------------------------------------- |
| `zvol`         | Full zvol path, e.g. `threeamigos/proxmox/vm-100-disk-0`                                |
| `vmid`         | Destination Proxmox VM ID                                                               |
| `dst-disk-key` | Optional target slot in the VM's configuration, e.g. `scsi2`. Auto-detected if omitted. |

**Globals:** node-config globals only.

In single-node mode, the script adds a `storage:vm-<id>-disk-<n>` line to the
VM config. In two-node mode, it SSHes to the storage host to create the
iSCSI backstore and LUN (or reuse existing ones), saves the iSCSI config, rescans,
then writes a `/dev/disk/by-path/...` line to the VM config.

---

### `detach-vm-disk` (both)

Removes a disk from a Proxmox VM config and tears down the iSCSI LUN and
backstore (two-node), leaving the underlying zvol intact so it can be
re-attached later.

```bash
sudo detach-vm-disk <vmid> <disk-key>
```

**Arguments:**

| Argument   | Description                                           |
| ---------- | ----------------------------------------------------- |
| `vmid`     | Proxmox VM ID                                         |
| `disk-key` | Disk key to detach, e.g. `scsi0`, `scsi1`, `efidisk0` |

**Globals:** node-config globals only.

The VM must be stopped. The script parses the disk line from the VM config,
removes it, and (in two-node mode) deletes the matching LUN and iSCSI backstore on
the storage host. A rescan is triggered on the compute host so Proxmox sees
the change.

---

### `move-vm-disk` (both)

Moves an existing VM disk from one Proxmox VM to another. The underlying zvol
is renamed from `vm-<src>-disk-<N>` to `vm-<dst>-disk-<M>` so the zvol name
remains authoritative for VM ownership. The iSCSI backstore is recreated with
the new name, and the original LUN number is reused whenever possible so
compute-node `by-path` symlinks remain stable.

```bash
sudo move-vm-disk <src-vmid> <src-disk-key> <dst-vmid> [dst-disk-key]
```

**Arguments:**

| Argument       | Description                                                                                                             |
| -------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `src-vmid`     | Source VM ID (must be stopped)                                                                                          |
| `src-disk-key` | Disk key in the source VM config (e.g. `scsi0`, `scsi1`, `efidisk0`)                                                    |
| `dst-vmid`     | Destination VM ID (must be stopped)                                                                                     |
| `dst-disk-key` | Optional. Desired disk key in the destination VM. If omitted, the next free slot of the same bus type is auto-selected. |

**Recovery options:**

| Option                  | Description                                                     |
| ----------------------- | --------------------------------------------------------------- |
| `--continue <state>`    | Resume an interrupted move from the recorded state file.        |
| `--rollback <state>`    | Revert a partially completed move using the recorded state file.|

**Globals:** node-config globals only.

**Two-node behavior:**

- SSHes to the storage node to verify the backing zvol and determine the current
  iSCSI LUN/backstore.
- Tears down the old iSCSI LUN and backstore.
- Renames the zvol to match the destination VMID and disk number.
- Recreates the iSCSI backstore and LUN (reusing the original LUN number).
- Updates `/etc/rtslib-fb-target/expected-backstores.txt` and
  `/etc/iscsi-encrypted-luns.conf` if the disk is encrypted.
- Saves the iSCSI config via `safe-iscsi-save` and rescans the compute node.
- Rewrites the Proxmox VM config lines on the compute host.

**Single-node behavior:**

- Validates the source disk line matches the `storage:vm-<vmid>-disk-<num>` pattern.
- `zfs rename`s the zvol to match the destination VMID and disk number.
- Rewrites the Proxmox VM config lines.

**Safety checks:**

- Both VMs must be stopped.
- The destination disk key must not already exist in the destination VM config.
- The destination zvol name must not already exist.
- Prompts for confirmation before making changes.
- Writes a state file to `/tmp/move-vm-disk-<src>-<dst>-<timestamp>.state` for
  recovery if the operation is interrupted.

To move the disk back, run the command with source and destination swapped.

---

### `new-vm-disk` (both)

Creates a new zvol on the storage node, registers it as an iSCSI LUN, and writes
the disk line to the VM config on the compute node.

```bash
sudo new-vm-disk <pool> <vmid> <disk-num> <size> [--encrypted]
```

**Arguments:**

| Argument      | Description                                                                                                            |
| ------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `pool`        | ZFS pool (e.g. `threeamigos`, `NVME1`)                                                                                 |
| `vmid`        | Proxmox VM ID                                                                                                          |
| `disk-num`    | Disk number (appended to zvol name: `vm-<vmid>-disk-<N>`)                                                              |
| `size`        | Zvol size (e.g., `50G`, `4M` for EFI, or `EFI` as a shorthand for a 4 MiB EFI zvol with Secure Boot enrollment prompt) |
| `--encrypted` | Optional. Create as an encrypted zvol; records the backstore in `/etc/iscsi-encrypted-luns.conf`                       |

**Globals:** node-config globals only.

**Data structures modified:**

| Structure                                             | Reference                                                                                                |
| ----------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `/etc/rtslib-fb-target/expected-backstores.txt`       | [Expected-backstores manifest](../developer-guide/data-structures.md#iscsi-expected-backstores-manifest) |
| `/etc/iscsi-encrypted-luns.conf` (with `--encrypted`) | [Encrypted-LUNs config](../developer-guide/data-structures.md#iscsi-encrypted-luns-config)               |

All zvols are created sparse (`-s`) with `compression=lz4`.

With `--encrypted`, the following additional ZFS properties are set:

| Property      | Value                                                                                              |
| ------------- | -------------------------------------------------------------------------------------------------- |
| `encryption`  | `aes-256-gcm` by default; auto-detected from an existing entry in `/etc/iscsi-encrypted-luns.conf` if available |
| `keyformat`   | `raw` by default; auto-detected from an existing entry in `/etc/iscsi-encrypted-luns.conf` if available |
| `keylocation` | `file:///mnt/ZFSkeys/<keyname>` (the script checks the file exists but never reads its contents)   |

---

### `promote-vm-clone` (both)

Promotes a ZFS-cloned VM's disk zvols, cutting the dependency on the source VM.

```bash
sudo promote-vm-clone <vmid>
```

**Arguments:**

| Argument | Description                          |
| -------- | ------------------------------------ |
| `vmid`   | VM ID whose zvols should be promoted |

**Globals:** node-config globals only.

Runs `zfs promote` on each zvol of the VM that has an origin (is a clone). After
promotion, the VM's zvols become independent (no origin), the shared clone-origin
snapshots move to this VM, and all other clones that shared those snapshots re-parent
automatically. The former source VM can then be destroyed.

This is a metadata-only operation — no data is moved and no iSCSI reconfiguration
is required. Safe to run while the VM is running.

See [Retiring a VM](../user-guide/proxmox-integration.md#retiring-a-vm)
for the full workflow.

---

### `remove-vm-disk` (both)

Removes a VM disk from iSCSI and destroys the zvol.

```bash
sudo remove-vm-disk <pool> <vmid> <disk-num>
```

**Arguments:**

| Argument   | Description           |
| ---------- | --------------------- |
| `pool`     | ZFS pool              |
| `vmid`     | Proxmox VM ID         |
| `disk-num` | Disk number to remove |

**Globals:** node-config globals only.

**Data structures modified:**

| Structure                                       | Reference                                                                                                             |
| ----------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `/etc/rtslib-fb-target/expected-backstores.txt` | [Expected-backstores manifest](../developer-guide/data-structures.md#iscsi-expected-backstores-manifest)              |
| `/etc/iscsi-encrypted-luns.conf`                | [Encrypted-LUNs config](../developer-guide/data-structures.md#iscsi-encrypted-luns-config) (entry removed if present) |

Prompts for confirmation. Tears down the iSCSI LUN and backstore, removes the entry
from the expected-backstores manifest, destroys the zvol, saves the iSCSI config
via [`safe-iscsi-save`](#safe-iscsi-save-storage-node), and rescans the compute node.

---

### `unretire-vm` (both)

Restores a retired VM from archive. Rebuilds iSCSI backstores and LUNs for
each restored zvol and rewrites the Proxmox config disk lines with new LUN numbers.

```bash
sudo unretire-vm <vmid> [archive_base]
```

**Arguments:**

| Argument       | Description                                                                                             |
| -------------- | ------------------------------------------------------------------------------------------------------- |
| `vmid`         | VM ID of the retired VM to restore                                                                      |
| `archive_base` | Optional ZFS dataset that contains the archive. If not specified, the last-used `archive-base` is used. |

**Globals:** node-config globals only.

**Data structures modified:**

| Structure                                       | Reference                                                                                                                     |
| ----------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `/etc/rtslib-fb-target/expected-backstores.txt` | [Expected-backstores manifest](../developer-guide/data-structures.md#iscsi-expected-backstores-manifest)                      |
| `/etc/iscsi-encrypted-luns.conf`                | [Encrypted-LUNs config](../developer-guide/data-structures.md#iscsi-encrypted-luns-config) (entry added if zvol is encrypted) |

On the storage node, restores each archived zvol with its original `volblocksize`,
creates iSCSI backstores and LUNs, and updates the manifests. On the compute node,
restores the Proxmox config while rewriting each disk line's by-path to use the
new LUN number. Uses `.disk_info` sidecar files created during retirement to map
config disk keys (e.g. `scsi0`) to the correct restored zvols.

See [Unretiring a VM](../user-guide/proxmox-integration.md#unretiring-a-vm)
for the full workflow.

---

### `rescan-storage` (both)

Triggers an iSCSI rescan on the compute node so newly added or resized LUNs become visible.

```bash
sudo rescan-storage
```

**Arguments:** none.

**Globals:** node-config globals only.

---

### `resize-vm-disk` (both)

Resizes a VM disk zvol and rescans so the compute node sees the new size.

```bash
sudo resize-vm-disk <pool> <vmid> <disk-num> <new-size>
```

**Arguments:**

| Argument   | Description                                                       |
| ---------- | ----------------------------------------------------------------- |
| `pool`     | ZFS pool                                                          |
| `vmid`     | Proxmox VM ID                                                     |
| `disk-num` | Disk number to resize                                             |
| `new-size` | Target size (e.g., `100G`) — must be larger than the current size |

**Globals:** node-config globals only.

ZFS supports online zvol growth. The guest OS may require additional steps (e.g.,
`growpart`, filesystem resize) after the block device grows.

---

### `restart-iscsi-services` (storage node)

Stops and restarts the iSCSI target service, then adds any encrypted LUNs whose
keys are currently loaded.

```bash
sudo restart-iscsi-services
```

**Arguments:** none.

**Globals:** node-config globals only.

**Safety check:** Before stopping the target service, the script checks whether
any VMs attached to the exported LUNs are running on the compute host. If running
VMs are detected, the script aborts with an error. It never restarts iSCSI while
VMs are running.

Uses [`safe-iscsi-save`](#safe-iscsi-save-storage-node) rather than `targetcli saveconfig`
directly.

---

### `safe-iscsi-save` (storage node)

Saves the iSCSI targetcli configuration only if all expected LUNs are currently
active. Compares active backstores against an authoritative manifest file,
preventing a degraded state from overwriting a good config.

```bash
sudo safe-iscsi-save
```

**Arguments:** none.

**Globals:** none.

**Data structures consumed:**

| Structure                                       | Reference                                                                                                |
| ----------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `/etc/rtslib-fb-target/expected-backstores.txt` | [Expected-backstores manifest](../developer-guide/data-structures.md#iscsi-expected-backstores-manifest) |

The manifest contains one backstore name per line (`vm-<vmid>-disk-<N>` format).
Comments and blank lines are ignored. This file is the authoritative source of
truth for expected LUN count — it is not derived from `saveconfig.json` or ZFS.

| Script                                   | Manifest action                                                 |
| ---------------------------------------- | --------------------------------------------------------------- |
| [`new-vm-disk`](#new-vm-disk-both)       | Adds entry when creating a disk                                 |
| [`remove-vm-disk`](#remove-vm-disk-both) | Removes entry when destroying a disk                            |
| [`zfsdelfs`](commands.md#zfsdelfs)       | Removes entry during teardown; `zfs-send-receive` rebuild re-adds |
| [`move-vm-disk`](#move-vm-disk-both)     | Removes source entry and adds destination entry                 |

Use `safe-iscsi-save` instead of `targetcli saveconfig` in any script that modifies
iSCSI config.

---

### `show-lun-map` (compute node)

Shows which iSCSI LUN maps to which block device (`/dev/sdX`) and which Proxmox VM
on the compute node.

```bash
sudo show-lun-map
```

**Arguments:** none.

**Globals:** none.

---

### `switch-version` (any host)

Wires a deployed version into active production and updates the `current` symlink.

```bash
sudo switch-version <version>|previous|--list|--uninstall
```

**Arguments:**

| Argument     | Description                                        |
| ------------ | -------------------------------------------------- |
| `version`    | Version string to activate                         |
| `previous`   | Roll back to the previously active version         |
| `--list`     | Show all installed versions and which is active    |
| `--uninstall`| Remove this version's production wiring            |

When switching to a new version, `switch-version`:

1. Records the outgoing version as `previous` for instant rollback.
2. Calls the prior version's own `switch-version --uninstall` so version-specific
   wiring can be cleaned up.
3. Repoints the `current` symlink.
4. Re-executes the target version's `switch-version` so its code performs the wiring.
5. Creates or refreshes production wiring:
   - `/usr/local/lib/zfsutilities/bin` symlink (exposed on `PATH`)
   - `/etc/profile.d/zfsutilities.sh` and `/etc/sudoers.d/zfsutilities`
   - `/root/bashinit` symlink
   - `/usr/local/lib/node-lib.sh` and `/usr/local/lib/two-node-lib.sh` symlinks
   - Desktop shortcuts in the installing user's home directory
6. Stops any running documentation server so it restarts from the new version
   on next access.

New script invocations immediately use the new version; already-running scripts
are unaffected.

`switch-version --uninstall` removes the per-version wiring installed by step 5
(above) while leaving the version directory in place. It is invoked automatically
when switching away from a version and may also be run manually.

---

### `uninstall-version` (any host)

Removes a deployed version directory. Refuses to remove the currently active
version.

```bash
sudo uninstall-version <version>
```

**Arguments:**

| Argument  | Description              |
| --------- | ------------------------ |
| `version` | Version string to remove |

---

### `unlock-zfs-keys` (storage node)

Unlocks the LUKS-encrypted USB key drive, mounts the key files at `/mnt/ZFSkeys`,
loads ZFS encryption keys for all encrypted zvols, and adds any missing encrypted
iSCSI LUNs without restarting the target service. This keeps running VMs connected.

If `/mnt/ZFSkeys` is already mounted (for example by Cinnamon/udisksd after the
USB was inserted post-boot), the script reuses the existing mount. If
`/mnt/ZFSkeys` already contains files, they are left untouched and the script
attempts to load keys from there.

```bash
sudo unlock-zfs-keys [device]
```

**Arguments:**

| Argument | Description                                                                                     |
| -------- | ----------------------------------------------------------------------------------------------- |
| `device` | Optional LUKS partition path. If omitted, auto-detects the USB drive by partition label `ZFSkeys`. |

**Globals:** none.

See [ZFS Key Handling](../installation/zfs-keys.md) for the full workflow.

---

### `unlock-zfs-keys-auto` (storage node)

Automatic version of [`unlock-zfs-keys`](#unlock-zfs-keys-storage-node). Waits
for USB insertion and auto-detects the drive by partition label `ZFSkeys`. Uses
`/root/.luks-key` to unlock the LUKS volume non-interactively. Intended for
systemd service use.

If the USB is not present at boot, or `/root/.luks-key` does not exist, the
script exits cleanly so iSCSI can start without the encrypted LUNs.

**Arguments:** none.

**Globals:** none.

See [ZFS Key Handling](../installation/zfs-keys.md) for how to create
`/root/.luks-key`.

---

### `zfsclone-vm` (both)

Creates a new Proxmox VM by ZFS-cloning the source VM's disk zvols. The new VM initially shares all blocks with the source via
copy-on-write.

```bash
sudo zfsclone-vm <src_vmid> <dst_vmid> <new_name>
```

**Arguments:**

| Argument   | Description                    |
| ---------- | ------------------------------ |
| `src_vmid` | Source VM ID (must be stopped) |
| `dst_vmid` | New VM ID                      |
| `new_name` | Name for the new VM            |

**Globals:** node-config globals only.

On the storage node, creates a `@clone-<timestamp>-c` snapshot of each zvol in the VM,
then creates a ZFS clone from that snapshot and registers it as a new iSCSI LUN.
On the compute node, writes a new VM config with fresh MAC address(es), `vmgenid`,
and SMBIOS UUID. Strips `protection:` and `meta:` fields from the cloned config.

The clone-origin snapshot is **retained** on the source zvols. ZFS prevents its deletion
while any clone created from it exists. Use [`promote-vm-clone`](#promote-vm-clone-both)
to cut dependencies before retiring the source VM.

See [VM Clone Provisioning](../user-guide/proxmox-integration.md#cloning-a-vm) for the full workflow.

---

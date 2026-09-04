# Two-Node Infrastructure Commands

These scripts manage the two-node Proxmox/ZFS setup: a **compute node** running
Proxmox VE VMs and a dedicated **storage node** hosting the ZFS pools and
exporting VM disks via iSCSI. The storage node is plain Debian-based ZFS/iSCSI
and does not need Proxmox VE. The scripts are deployed via the versioned
installation to `/usr/local/lib/zfsutilities/bin/` on one or both nodes and are
not part of the core ZFS Utilities backup system.

Scripts marked **both** run on either node and delegate automatically via SSH as appropriate. Scripts marked **storage node** or **compute node** are node-specific.

Every script that touches VM disks or iSCSI configuration begins by sourcing
`/usr/local/lib/node-lib.sh` (repo: `lib/node-lib.sh`). That library
reads `/etc/zfsutilities/node.conf` (falling back to `/etc/zfsutilities/two-node.conf`, legacy `/etc/zfsutilities-node.conf` and `/etc/two-node.conf` also work) and
populates the node-configuration global variables below (lowercase working
copies of the uppercase names used in the config file). These variables apply to
every entry below — they are documented once here rather than repeated in every
entry:

| Variable                       | Purpose                                                                | Reference                                                                          |
| ------------------------------ | ---------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `node_mode`                    | `single-node` or `two-node` — gates all iSCSI and SSH-delegation logic | [Node Configuration](../developer-guide/global-variables.md#node-configuration)    |
| `this_host`                    | Short hostname of the current node                                     | [Node Configuration](../developer-guide/global-variables.md#node-configuration)    |
| `storage_host`, `compute_host` | Short hostnames of the two nodes (two-node); both equal `this_host` in single-node | [Node Configuration](../developer-guide/global-variables.md#node-configuration) |
| `storage_ip`                   | Storage-network IP of the storage node                                 | [Node Configuration](../developer-guide/global-variables.md#node-configuration)    |
| `iqn_prefix`                   | iSCSI IQN prefix for all targets                                       | [Node Configuration](../developer-guide/global-variables.md#node-configuration)    |
| `pool_target`                  | Pool → target short-name map                                           | [pool_target](../developer-guide/data-structures.md#pool_target-associative-array) |

The library also defines helper functions used throughout these scripts:

| Function                    | Behavior                                                                 |
| --------------------------- | ------------------------------------------------------------------------ |
| `is_single_node`            | Returns 0 in `single-node` mode                                          |
| `is_two_node`               | Returns 0 in `two-node` mode                                             |
| `pool_to_target <pool>`     | Echoes the full IQN for a pool; returns 1 if unknown or single-node      |
| `pool_list`                 | Echoes valid pool names from `pool_target` (empty in single-node)        |
| `is_known_pool <pool>`      | Returns 0 if the pool is in `pool_target` (always 1 in single-node)      |
| `find_zfsutility_script <name>` | Locates a sibling script across repo or deployed layouts; respects `ZFSUTILITIES_BIN_DIR`, `ZFSUTILITIES_CURRENT_BIN_DIR`, and `ZFSUTILITIES_SYSTEM_LIB_DIR` overrides |
| `remote_zfsutility_script <host> <name>` | Returns the remote path to `<name>` on `<host>`, or just `<name>` on failure |

The script-specific Arguments and Globals tables below omit these unless a
script uses one in a non-obvious way.

## Dashboard iSCSI Issues (two-node GUI)

In two-node mode the Dashboard shows an **iSCSI Issues** box that compares the
authoritative [`expected-backstores.txt`](../developer-guide/data-structures.md#iscsi-expected-backstores-manifest)
manifest against the backstores currently loaded in `targetcli`.

### What "not exported" means

Each VM disk is a ZFS zvol that is shared to the compute node over iSCSI. When
the Dashboard reports that a disk is **not exported**, the disk is still listed
as expected but is not currently loaded in the iSCSI target. The affected VM
may not be able to see or use the disk until the export is restored.

A message like:

```text
VM 207 disk 2 (vm-207-disk-2) is not exported as an iSCSI LUN on target
threeamigos. The VM may not see this disk.
```

means VM 207's second disk should be exported from the pool/target named
`threeamigos`, but the iSCSI backstore or LUN mapping is missing.

### Common causes

- **Detached disk** — the disk was removed from a VM with `detach-vm-disk` but
  the expected-backstores manifest was not updated.
- **Encryption key not loaded** — the backing zvol is encrypted and its key has
  not been loaded yet.
- **Pool not imported** — the source pool is offline or not imported.
- **Missing backstore/LUN** — the iSCSI export was never created or was deleted
  manually.

### Fix this button

Clicking **Fix this** runs [`repair-iscsi-luns`](#repair-iscsi-luns-storage-node)
on the storage host. It recreates any missing backstores/LUNs for entries in the
manifest, regenerates the manifest, saves the target configuration, and rescans
the compute host.

### Intentionally detached disks

A disk that has been deliberately detached from a VM should **not** appear as an
issue. [`detach-vm-disk`](#detach-vm-disk-both) removes the backstore/LUN from
the target and also removes the entry from `expected-backstores.txt`, so the
Dashboard will not warn about it. [`repair-iscsi-luns`](#repair-iscsi-luns-storage-node)
only exports disks that are listed in the manifest, so detached disks stay
detached unless you later re-attach them with `attach-vm-disk` or `new-vm-disk`.

## Jump to

- [Dashboard iSCSI Issues](#dashboard-iscsi-issues-two-node-gui)
- [`attach-vm-disk` (both)](#attach-vm-disk-both)
- [`clone-vm` (both)](#clone-vm-both)
- [`deploy-version` (repo root)](#deploy-version-repo-root)
- [`detach-vm-disk` (both)](#detach-vm-disk-both)
- [`enroll-efi-keys-vm` (compute node)](#enroll-efi-keys-vm-compute-node)
- [`iscsi-add-encrypted-luns` (storage node)](#iscsi-add-encrypted-luns-storage-node)
- [`iscsi-restore-luns` (storage node)](#iscsi-restore-luns-storage-node)
- [`list-vm-disks` (both)](#list-vm-disks-both)
- [`repair-iscsi-luns` (storage node)](#repair-iscsi-luns-storage-node)
- [`repair-vm-disk-sizes` (compute node)](#repair-vm-disk-sizes-compute-node)
- [`move-vm-disk` (both)](#move-vm-disk-both)
- [`new-vm-disk` (both)](#new-vm-disk-both)
- [`switch-version` (any host)](#switch-version-any-host)
- [`uninstall-version` (any host)](#uninstall-version-any-host)
- [`promote-vm-clone` (both)](#promote-vm-clone-both)
- [`archive-vm` (both)](../commands-and-modules/commands.md#archive-vm)
- [`remove-vm` (both)](../commands-and-modules/commands.md#remove-vm)
- [`remove-vm-disk` (both)](#remove-vm-disk-both)
- [`unarchive-vm` (both)](#unarchive-vm-both)
- [`rescan-storage` (both)](#rescan-storage-both)
- [`resize-vm-disk` (both)](#resize-vm-disk-both)
- [`restart-iscsi-services` (storage node)](#restart-iscsi-services-storage-node)
- [`safe-iscsi-save` (storage node)](#safe-iscsi-save-storage-node)
- [`setup-iscsi-targets` (storage node)](#setup-iscsi-targets-storage-node)
- [`show-lun-map` (compute node)](#show-lun-map-compute-node)
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

**Called modules / commands:**

| Script / command | Purpose |
| ---------------- | ------- |
| `safe-iscsi-save` (storage host) | Persist new backstores/LUNs after clone |
| `rescan-storage` | Make new LUNs visible on the compute host |
| `zfs-diagnose-busy` | Diagnose snapshot-destroy failures |
| `zfslockmanager` | Acquire per-disk source/destination zvol write locks |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| Source/dest VM configs | Read source; write destination | — |
| `expected-backstores.txt` | New backstore added on storage host | [Expected-backstores manifest](../developer-guide/data-structures.md#iscsi-expected-backstores-manifest) |

**Internal flow / algorithm:**

1. Validate arguments and delegate to the compute host in two-node mode.
2. Parse disk lines from the source VM config (single-node: `storage:vm-...`;
   two-node: iSCSI `by-path`).
3. For each disk:
    - Acquire a write lock on the source zvol and the destination zvol.
      These locks are visible in the Dashboard **Active Locks** list and are
      released when the disk finishes cloning.
    - Snapshot the source zvol as `@clone-to-<dst>`.
    - `zfs send | zfs receive` to a new destination zvol.
    - Destroy the source and destination clone snapshots.
    - In two-node mode, create an iSCSI backstore and LUN on the storage host.
    - Add the new backstore to `expected-backstores.txt`.
4. In two-node mode, save iSCSI config on the storage host.
5. Write the destination VM config with new LUN numbers, fresh MAC addresses,
   and a new `vmgenid`.
6. Trigger iSCSI rescan on the compute host.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Clone completed successfully |
| non-zero | Validation, SSH, ZFS, or iSCSI failure |

Side effects: new zvols, new iSCSI LUNs (two-node), new VM config file.

For space-efficient provisioning from a gold template, use
[`zfsclone-vm`](#zfsclone-vm-both) instead.

---

### `deploy-version` (repo root)

Deploys the current repository state as a new versioned installation without
activating it. Run from the repository root.

```bash
sudo ./bin/deploy-version [version] [group ...]
```

**Arguments:**

| Argument  | Description                                                                                                   |
| --------- | ------------------------------------------------------------------------------------------------------------- |
| `version` | Optional version string (default: reads `./VERSION`)                                                          |
| `group`   | Optional deployment-group name(s) (see `/etc/zfsutilities-deploy.conf`). If omitted, all groups are deployed. |

**Globals:**

| Variable | Role | Reference |
| -------- | ---- | --------- |
| `NODE_MODE`, `STORAGE_HOST`, `COMPUTE_HOST` | Legacy remote-host fallback when no deploy.conf exists | [Node Configuration](../developer-guide/global-variables.md#node-configuration) |

**Called modules:**

| Script | Purpose |
| ------ | ------- |
| `lib/desktop-launcher-lib.sh` | Desktop shortcut helpers |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `/etc/zfsutilities/deploy.conf` | Deployment group definitions | — |
| Node config | Legacy remote host list | [Node config](../developer-guide/data-structures.md#node-configuration-file-etczfsutilitiesnodeconf) |
| `/usr/local/lib/zfsutilities/versions/<version>/` | Deployed version directory | — |

**Internal flow / algorithm:**

1. Parse arguments; read `./VERSION` if no version is supplied.
2. Load `/etc/zfsutilities/deploy.conf` groups, or fall back to the node config for remote hosts.
3. Create the version directory (`versions/<version>/bin`, `lib`, `python`, `docs`, `share`).
4. Copy `bin/`, `lib/`, `python/`, `docs/`, and `share/` from the repository into the version directory via `rsync`.
5. Create launcher symlinks `zfsutilities-gui` → `../python/zfsutilities_gui.py` and `zfsutilities-docs` → `../python/docs_viewer.py` in the versioned `bin/` directory.
6. Copy the `VERSION` file into the version directory.
7. Rebuild the static MkDocs site in the versioned `docs/` directory.
8. Validate that critical scripts (`zfs-diagnose-busy`, `zfsdelsnap`, `zfscleanup`, `zfsretain`, `zfs-send-receive`) are present in the deployed `bin/` directory.
9. `rsync` the version directory to each remote host in the selected groups.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Deployment completed |
| `1`  | Fatal error (wrong directory, missing version, unknown group, etc.) |

Side effects: creates the versioned installation tree; does not touch active
production wiring (`current`, `PATH`, `/root/bashinit`, etc.).

**Deployment targets:**

- **Local host** — always deployed directly

- **Remote hosts** — defined by `/etc/zfsutilities/deploy.conf` via named groups:
  
  ```bash
  # /etc/zfsutilities/deploy.conf
  DEPLOY_GROUP_production="stewie tweety"
  DEPLOY_GROUP_staging="staging-host"
  ```
  
  Each host in the selected group(s) receives the version. The group names do not have any special meaning to ZFSutilities. The hosts must be reachable via `ssh root@<hostname>`(password prompting  works if running from a terminal).

`deploy-version` creates a self-contained version directory at `/usr/local/lib/zfsutilities/versions/<version>/`.
Each version carries its own `bin/` (executable scripts), `lib/` (helper libraries),
`python/` (GUI and Python helpers), `docs/` (built documentation), and `share/`
(templates and sample configs) so that multiple versions can coexist on disk.
Because every version is complete, rollback is just `switch-version` repointing
`current` and refreshing the production wiring — no files need to be copied or restored.

`deploy-version` does **not** touch active production wiring. It does not update the `current`
symlink, `PATH` configuration, `/root/bashinit`, library symlinks, or desktop shortcuts. It is safe to run at any time.

The repository directories `bin/`, `lib/`, `python/`, `docs/`, and `share/` are copied
wholesale into the version directory. The `VERSION` file is copied separately. Exclusions
are limited to build artifacts such as `__pycache__/` and `*.pyc`.

After copying files, `deploy-version` validates that critical scripts
(`zfs-diagnose-busy`, `zfsdelsnap`, `zfscleanup`, `zfsretain`, `zfs-send-receive`)
are present in the versioned `bin/` directory. If any are missing, a warning is
printed so the operator knows the deployment is incomplete.

`deploy-version` refuses to run from a deployed path (it checks that the current
directory contains `.git/` or `VERSION`). This prevents accidentally deploying
an incomplete set of files when the script is invoked from `$PATH` rather than
the repository root.

`deploy-version` also rebuilds the static documentation site in the deployed
directory so the built site carries the correct version stamp.

`deploy-version` creates two launcher symlinks in the versioned `bin/`
directory:

- `zfsutilities-gui` → `../python/zfsutilities_gui.py`
- `zfsutilities-docs` → `../python/docs_viewer.py`

These let you launch the GUI and standalone documentation viewer by name after
activating the version.

`deploy-version` also generates `/etc/zfsutilities/deploy.conf` at install time
(from `share/installer/deploy.conf.template`) so the production hostnames are
available for future deployments.

See [Installation](../installation/index.md) for the full workflow.

---

### `iscsi-add-encrypted-luns` (storage node)

Adds iSCSI backstores and LUNs for encrypted zvols whose keys are currently loaded. ZFS encryption keys are not available at boot time (when iSCSI is initiated), so the encrypted backstores are added separately after the operator has loaded the keys with `zfs load-key`.
Called explicitly by the operator after loading keys and by
[`restart-iscsi-services`](#restart-iscsi-services-storage-node) after it restarts
the iSCSI target service.

**Arguments:** none.

**Globals:** node-config globals only.

**Called modules / commands:**

| Script | Purpose |
| ------ | ------- |
| `safe-iscsi-save` | Persist config after adding encrypted LUNs |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `/etc/zfsutilities/iscsi-encrypted-luns.conf` | Authoritative list of encrypted backstores to add | [Encrypted-LUNs config](../developer-guide/data-structures.md#iscsi-encrypted-luns-config) |
| `/etc/rtslib-fb-target/saveconfig.json` | Used to look up original LUN indexes | [iSCSI boot-safe config](../developer-guide/data-structures.md#iscsi-boot-safe-config) |

**Internal flow / algorithm:**

1. In single-node mode, print an informational message and exit.
2. For each entry in `/etc/zfsutilities/iscsi-encrypted-luns.conf`:
    - Skip if the device node is not present (keys not loaded).
    - Skip if the backstore already exists.
    - Look up the original LUN index from `saveconfig.json` to preserve stable
      compute-node `by-path` symlinks.
    - Create the block backstore and map it to the target at the original LUN
      index (or auto-allocate if no index is found).
3. Save the iSCSI config via `safe-iscsi-save`.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Completed (may have added zero LUNs) |

Side effects: creates missing encrypted backstores/LUNs; regenerates
`saveconfig-boot.json` via `safe-iscsi-save`.

---

### `iscsi-restore-luns` (storage node)

Restores missing iSCSI backstores and LUN mappings from `saveconfig.json`.
Idempotent — safe to run even if nothing is missing.

```bash
sudo iscsi-restore-luns
```

**Arguments:** none.

**Globals:** node-config globals only.

**Called modules / commands:**

| Script | Purpose |
| ------ | ------- |
| `safe-iscsi-save` | Persist restored config only when all expected LUNs are active |
| `rescan-storage` | Make restored LUNs visible on the compute host |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `/etc/rtslib-fb-target/saveconfig.json` | Authoritative source of expected backstores and LUN indexes | [iSCSI boot-safe config](../developer-guide/data-structures.md#iscsi-boot-safe-config) |
| `/etc/rtslib-fb-target/expected-backstores.txt` | Verified by `safe-iscsi-save` before saving | [Expected-backstores manifest](../developer-guide/data-structures.md#iscsi-expected-backstores-manifest) |

**Internal flow / algorithm:**

1. Exit silently in single-node mode.
2. Parse `/etc/rtslib-fb-target/saveconfig.json` directly (not `expected-backstores.txt`).
3. For each block storage object in `saveconfig.json`, create the backstore if
   missing and its backing device is available.
4. For each LUN mapping in `saveconfig.json`, recreate the mapping at the
   original LUN index if missing.
5. Save the updated iSCSI config via `safe-iscsi-save`.
6. If any backstores or LUNs were added, trigger a compute-host rescan.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Restore completed (nothing added, or backstores/LUNs restored) |
| `1`  | `saveconfig.json` not found |

Side effects: recreates missing iSCSI resources; updates `saveconfig.json` and
`saveconfig-boot.json`.

Handles both encrypted and non-encrypted LUNs. Preserves original LUN indexes so compute node configs remain valid.

---

### `repair-iscsi-luns` (storage node)

Diagnoses and repairs missing iSCSI LUN exports on the storage host. Discovers
all VM zvols in the configured pools, ensures each one has a block backstore and
a LUN mapping, preserves existing LUN indexes, regenerates the authoritative
`expected-backstores.txt` manifest, saves the target config, and always rescans
the compute host. It only exports disks that are listed in the manifest, so
intentionally detached disks stay detached. Use `--dry-run` to preview changes
and `--force-relogin` to re-log iSCSI sessions when a rescan alone does not
reveal all LUNs.

```bash
sudo repair-iscsi-luns [--dry-run] [--force-relogin]
```

**Prerequisites:** `targetcli` and the `rtslib-fb-targetctl` systemd service must
be installed on the storage host (Debian/Ubuntu package `targetcli-fb`).
Proxmox VE is **not** required on the storage host.

**Arguments:**

| Argument | Description |
| -------- | ----------- |
| `--dry-run` | Report what would be changed without making changes |
| `--force-relogin` | Re-log iSCSI sessions if the rescan does not increase visible devices (briefly disconnects all LUNs) |

**Globals:** node-config globals only.

**Called modules / commands:**

| Script | Purpose |
| ------ | ------- |
| `safe-iscsi-save` | Persist repaired config after verifying all expected LUNs are active |
| `rescan-storage` | Make repaired LUNs visible on the compute host |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `/etc/rtslib-fb-target/saveconfig.json` | Full targetcli config (backed up and overwritten) | [iSCSI boot-safe config](../developer-guide/data-structures.md#iscsi-boot-safe-config) |
| `/etc/rtslib-fb-target/expected-backstores.txt` | Regenerated from current targetcli backstores | [Expected-backstores manifest](../developer-guide/data-structures.md#iscsi-expected-backstores-manifest) |

**Internal flow / algorithm:**

1. Exit silently in single-node mode.
2. Parse current targetcli backstores and LUN mappings.
3. Discover all VM zvols (`vm-<N>-disk-<N>`) under configured pools.
4. Read `/etc/rtslib-fb-target/expected-backstores.txt`. If the manifest is
   missing, fall back to the discovered zvol list. If it exists but is empty,
   treat it as authoritative (nothing expected).
5. For each expected backstore that has a corresponding zvol, create the
   backstore and LUN mapping if missing.
6. For each loaded backstore that is listed in the manifest but not mapped to a
   LUN, create the missing LUN mapping at the next free index.
7. Report any zvols that exist but are not in the manifest without exporting
   them.
8. If any target-side changes were made, back up `saveconfig.json`, regenerate
   `expected-backstores.txt`, and save the config via `safe-iscsi-save`.
9. If no target-side changes were needed, still regenerate
   `expected-backstores.txt` to keep the manifest authoritative.
10. Rescan the compute host. If `--force-relogin` is set and the visible device
    count did not increase, re-log iSCSI sessions.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Repair completed (nothing added, or backstores/LUNs repaired) |
| `1`  | Not running on the storage host, not running as root, or invalid option |

Side effects: may create backstores/LUNs; updates `saveconfig.json`,
`saveconfig-boot.json`, and `expected-backstores.txt`; triggers compute-host
rescan (and optionally re-login).

---

### `list-vm-disks` (both)

Lists all zvols currently exported as iSCSI LUNs, together with the VM that
owns each disk, the VM name, the host-side device names, and (when the VM is
running and the QEMU guest agent is available) the device names seen inside the
guest.

```bash
sudo list-vm-disks [--with-devices]
```

**Arguments:**

| Argument         | Description                                                                                                |
| ---------------- | ---------------------------------------------------------------------------------------------------------- |
| `--with-devices` | Accepted for backward compatibility; device information is now included by default. |

**Globals:** node-config globals only.

**Called modules / commands:**

| Command | Purpose |
| ------- | ------- |
| `qm list` / `qm guest exec` (compute host) | Detect running VMs and query guest device names. |
| `targetcli` (storage host) | Enumerate exported LUNs. |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `/etc/pve/qemu-server/<vmid>.conf` | Map LUNs/zvols to actual VMID and name. | — |
| `/dev/disk/by-path/ip-<storage-ip>*` | Map LUNs to compute-host `/dev/sdX` and by-path names. | — |
| `zpool list` / `zfs list -t volume` | Enumerate local zvols (single-node) | — |
| `targetcli` backstores/luns | Enumerate exported LUNs (two-node) | — |

**Internal flow / algorithm:**

1. Scan `/etc/pve/qemu-server/*.conf` on the compute host to build a map from
   LUN/zvol to the actual VMID, VM name, and Proxmox disk key.  This reflects
   disks that have been moved between VMs.
2. On the compute host, build a LUN-to-host-device map from
   `/dev/disk/by-path/ip-${storage_ip}*`.
3. For running VMs, use `qm guest exec` to list the guest's
   `/dev/disk/by-path` entries and resolve the symlink to the guest's
   `/dev/sdX`.  SCSI disks are matched by disk key (`scsiN` →
   `*scsi-0:0:N:0` inside the guest).
4. In single-node mode, enumerate local pools and their `vm-*` zvols directly
   and merge with the VM/guest maps.
5. In two-node mode, gather LUN/zvol metadata from the storage host and merge
   with the VM/guest maps from the compute host.
6. Annotate each zvol with clone relationships:
    - `[clone of <snapshot>]` if the zvol is a ZFS clone, where `<snapshot>`
      is the full origin snapshot dataset name (e.g.
      `threeamigos/proxmox/vm-904-disk-0@clone-2026-07-30T12:00-0400-c`).
    - `[cloned by: vm-N, vm-M]` if any of its snapshots have clone dependents.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Inventory displayed |
| `1`  | Error (e.g., SSH failure) |

Side effects: read-only; no changes to ZFS or iSCSI state.

Guest device information is best-effort: it is shown only when the VM is
running and the QEMU guest agent responds.  Stopped VMs or guests without the
agent show `-` for guest device names.

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

**Called modules / commands:**

| Script | Purpose |
| ------ | ------- |
| `safe-iscsi-save` (storage host) | Persist backstore/LUN changes |
| `rescan-storage` | Make the LUN visible on the compute host |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| Source zvol | Existing zvol to attach | — |
| `/etc/pve/qemu-server/<vmid>.conf` | Destination VM config | — |

**Internal flow / algorithm:**

1. Validate arguments and delegate to the compute host in two-node mode.
2. Parse the zvol path into pool, source VMID, and disk number.
3. Verify the zvol exists and read its `volsize`.
4. Determine the destination disk key (auto-detect next free `scsiN`).
5. In two-node mode, SSH to the storage host to create/reuse the backstore and
   LUN, then save iSCSI config and rescan.
6. Build a `by-path` disk line (two-node) or `storage:vm-...` disk line
   (single-node).
7. Prompt for confirmation and append the disk line to the VM config.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Disk attached (or user aborted) |
| `1`  | Validation, SSH, or targetcli failure |

Side effects: may create a new iSCSI backstore/LUN; appends a disk line to the
VM config.

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

**Called modules / commands:**

| Script | Purpose |
| ------ | ------- |
| `safe-iscsi-save` (storage host) | Persist LUN/backstore removal |
| `rescan-storage` (compute host) | Update compute host device view |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `/etc/pve/qemu-server/<vmid>.conf` | Source VM config | — |
| `/etc/rtslib-fb-target/expected-backstores.txt` | Backstore removed so the detached disk is no longer expected | [Expected-backstores manifest](../developer-guide/data-structures.md#iscsi-expected-backstores-manifest) |

**Internal flow / algorithm:**

1. Validate arguments and delegate to the compute host in two-node mode.
   When delegating, the script resolves the compute host's active
   `/usr/local/lib/zfsutilities/current` symlink so the remote copy of
   `detach-vm-disk` is invoked from the active deployed version rather than a
   hardcoded path.
2. Read the VM config and locate the requested disk line.
3. Warn if the VM is running; prompt for confirmation.
4. Remove the disk line from the VM config.
5. In two-node mode:
    - Parse the target and LUN from the disk line and remove the LUN mapping and
      backstore on the storage host.
    - Remove the backstore name from `expected-backstores.txt` so the Dashboard
      does not report the detached disk as missing and `safe-iscsi-save` can
      save the degraded-but-intentional config.
    - Save the iSCSI config via `safe-iscsi-save` (found relative to this
      script).
    - Resolve the compute host's active deployed version again and trigger a
      compute-host rescan using that version's `rescan-storage`.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Disk detached (or user aborted) |
| `1`  | Validation or targetcli failure |

Side effects: removes the disk line from the VM config; removes the iSCSI LUN
and backstore in two-node mode; removes the backstore entry from
`expected-backstores.txt`. The zvol is **not** destroyed.

---

### `enroll-efi-keys-vm` (compute node)

Re-initializes a VM's EFI vars disk with the Microsoft UEFI CA 2023
certificates. This is useful when Proxmox warns that the EFI disk is missing
`ms-cert=2023k`, and it is required for iSCSI-backed VMs: both the Proxmox
GUI **Enroll Updated Certificates** action and `qm enroll-efi-keys` split the
volume identifier on `:` and cannot parse the raw `by-path` path (for example,
`unable to parse volume ID '/dev/disk/by-path/ip-192.168.100.1:3260-iscsi-...'`).

```bash
sudo enroll-efi-keys-vm <vmid>
```

**Arguments:**

| Argument | Description                 |
| -------- | --------------------------- |
| `vmid`   | Proxmox VM ID to enroll     |

**Globals:** node-config globals only.

**Called modules / commands:**

| Script | Purpose |
| ------ | ------- |
| `rescan-storage` | Refresh compute-host view of the resized EFI device |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `/etc/pve/qemu-server/<vmid>.conf` | VM config updated with `size=4M`, `ms-cert=2023k` | — |

**Internal flow / algorithm:**

1. Delegate to the compute host in two-node mode.
2. Shut down the VM gracefully if it is running.
3. Parse `efidisk0:` from the VM config and resolve the backing zvol via the
   iSCSI target/LUN (two-node) or storage reference (single-node).
4. Grow the EFI zvol to 4M if it is smaller.
5. Rescan iSCSI on the compute node so the new size is visible.
6. Wait for the `by-path` device to appear at the new size.
7. Write `/usr/share/pve-edk2-firmware/OVMF_VARS_4M.ms.fd` to the EFI disk.
8. Update the Proxmox config to `size=4M` and add `ms-cert=2023k`.
9. Remove any stale `[PENDING]` change block.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | EFI keys enrolled |
| `1`  | Validation, shutdown, resize, or write failure |

Side effects: grows the EFI zvol; rewrites EFI vars; updates the VM config.
The VM is left stopped. After starting it, watch the console — the UEFI boot
order is reset and may need to be re-selected in the firmware setup.

---

### `repair-vm-disk-sizes` (compute node)

Repairs the `size=` parameter on Proxmox VM disk lines. Proxmox stores the
disk size in each config disk line (for example
`scsi0: /dev/disk/by-path/.../threeamigos-lun-8,...,size=100G`). For raw
by-path/iSCSI disks this value is only metadata — QEMU uses the actual block
device size, so a wrong value does not affect the guest — but it makes the GUI
display the wrong size and breaks `qm resize` and disk reporting. An earlier
`enroll-efi-keys-vm` bug rewrote every disk line's `size=` to `size=4M`
(instead of only the `efidisk0` line); this script restores the correct value.

```bash
sudo repair-vm-disk-sizes [--dry-run] [--vmid <vmid>]
```

**Arguments:**

| Argument   | Description                                        |
| ---------- | -------------------------------------------------- |
| `--dry-run` | Report what would change without editing configs  |
| `--vmid`    | Repair only the given VM ID (default: all VMs)    |

**Globals:** node-config globals only.

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `/etc/pve/qemu-server/<vmid>.conf` | Disk-line `size=` values corrected | — |

**Internal flow / algorithm:**

1. Delegate to the compute host in two-node mode.
2. For each VM config (or only `--vmid`), scan disk lines (`efidisk0`,
   `scsi`/`sata`/`ide`/`virtio` slots) that record a `size=` value.
3. Resolve the correct size: for `/dev/disk/by-path/...` volumes, from the live
   block device on the compute node; for `pool:vm-N-disk-M` storage references,
   from the backing zvol `volsize` (local ZFS in single-node mode, SSH to the
   storage host in two-node mode).
4. Rewrite only the disk lines whose recorded size differs; lines whose volume
   cannot be resolved (for example a LUN that is not logged in) are skipped
   with a warning.
5. Print a checked/fixed/skipped summary.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Scan completed (skipped lines do not fail the run) |
| `1`  | Bad arguments or missing VM config |

Side effects: edits VM config `size=` values in place. For VMs that are
running, Proxmox only re-reads the config on the next config change or VM
restart, so applying the repair while a VM is running is safe but the GUI
updates only afterwards.

---

### `move-vm-disk` (both)

Moves an existing VM disk from one Proxmox VM to another. By default the
underlying zvol is renamed from `vm-<src>-disk-<N>` to `vm-<dst>-disk-<M>` so
the zvol name remains authoritative for VM ownership. The iSCSI backstore is
recreated with the new name, and the original LUN number is reused whenever
possible so compute-node `by-path` symlinks remain stable.

Use `--no-rename` to leave the zvol, backstore, and LUN unchanged and only move
the Proxmox disk reference from the source VM config to the destination VM
config.

```bash
sudo move-vm-disk [--no-rename] <src-vmid> <src-disk-key> <dst-vmid> [dst-disk-key]
```

**Arguments:**

| Argument       | Description                                                                                                             |
| -------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `src-vmid`     | Source VM ID (must be stopped)                                                                                          |
| `src-disk-key` | Disk key in the source VM config (e.g. `scsi0`, `scsi1`, `efidisk0`)                                                    |
| `dst-vmid`     | Destination VM ID (must be stopped)                                                                                     |
| `dst-disk-key` | Optional. Desired disk key in the destination VM. If omitted, the next free slot of the same bus type is auto-selected. |

**Recovery options:**

| Option                  | Description                                                      |
| ----------------------- | ---------------------------------------------------------------- |
| `--no-rename`           | Move only the Proxmox disk reference; leave the zvol, iSCSI      |
|                         | backstore, and LUN unchanged.                                    |
| `--continue <state>`    | Resume an interrupted move from the recorded state file.         |
| `--rollback <state>`    | Revert a partially completed move using the recorded state file. |

**Globals:** node-config globals only.

**Called modules / commands:**

| Script | Purpose |
| ------ | ------- |
| `safe-iscsi-save` (inside SSH on storage host) | Persist teardown/rebuild |
| `rescan-storage` | Refresh compute-host device view |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| Source/dest VM configs | Read source; rewrite destination | — |
| `/etc/rtslib-fb-target/expected-backstores.txt` | Source removed, destination added | [Expected-backstores manifest](../developer-guide/data-structures.md#iscsi-expected-backstores-manifest) |
| `/etc/zfsutilities/iscsi-encrypted-luns.conf` | Source removed, destination added if encrypted (legacy `/etc/iscsi-encrypted-luns.conf` fallback) | [Encrypted-LUNs config](../developer-guide/data-structures.md#iscsi-encrypted-luns-config) |
| `/tmp/move-vm-disk-<src>-<dst>-<ts>.state` | Recovery state file | — |

**Internal flow / algorithm:**

1. Validate arguments; `--continue`/`--rollback` must run on the compute host.
2. Parse the source disk line to determine pool, target, LUN, and backing zvol.
   The zvol is discovered by searching the entire pool for the backstore name,
   so disks living outside the `proxmox` dataset are handled correctly.
3. Verify both VMs are stopped and (unless `--no-rename` is used) the
   destination zvol name is free.
4. Write an initial state file (`/tmp/move-vm-disk-<src>-<dst>-<timestamp>.state`).
5. Prompt for confirmation.
6. **Storage-node operations (two-node), skipped when `--no-rename` is used:**
    - Tear down the old LUN and backstore.
    - Remove the source entry from `expected-backstores.txt` and
      `/etc/zfsutilities/iscsi-encrypted-luns.conf` if encrypted.
    - `zfs rename` the zvol to the destination name.
    - The destination zvol is placed in the same parent dataset as the source
      zvol (for example, `pool/custom/vm-100-disk-0` → `pool/custom/vm-200-disk-0`).
    - Create the new backstore and LUN, reusing the original LUN number if possible.
    - Add the destination entry to the manifests.
    - Save iSCSI config via `safe-iscsi-save`.
7. **Single-node operations, skipped when `--no-rename` is used:** `zfs rename`
   the zvol to the destination name.
8. Move the disk line from the source VM config to the destination VM config.
9. Rescan iSCSI on the compute host.
10. Mark the state file as completed.

**Rollback (`--rollback`):**

- Removes the destination config line and restores the source line.
- When `--no-rename` was not used: tears down the destination backstore/LUN and
  recreates the original source backstore/LUN if the source zvol still exists;
  renames the zvol back to the source name; rescans iSCSI.
- When `--no-rename` was used: no storage-side changes are reverted because none
  were made.
- Deletes the state file.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Move completed or rolled back |
| `1`  | Validation, SSH, ZFS rename, or targetcli failure |

Side effects (default): renames the zvol; recreates iSCSI backstore/LUN with the
new name; updates manifests and VM configs. With `--no-rename`, only the VM
configs are changed.

**Safety checks:**

- Both VMs must be stopped.
- The destination disk key must not already exist in the destination VM config.
- The destination zvol name must not already exist (except with `--no-rename`).
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
| `--encrypted` | Optional. Create as an encrypted zvol; prompts for an already-accessible absolute key-file path and records the backstore in `/etc/zfsutilities/iscsi-encrypted-luns.conf` |

**Globals:** node-config globals only.

**Called modules / commands:**

| Script | Purpose |
| ------ | ------- |
| `safe-iscsi-save` | Persist new backstore/LUN |
| `rescan-storage` | Make the new LUN visible on the compute host |
| `new-vm-disk --config-only=<lun>` (self-delegation on compute host) | Write VM config line / initialize EFI vars |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `/etc/rtslib-fb-target/expected-backstores.txt` | Backstore added | [Expected-backstores manifest](../developer-guide/data-structures.md#iscsi-expected-backstores-manifest) |
| `/etc/zfsutilities/iscsi-encrypted-luns.conf` | Entry added with `--encrypted` (legacy `/etc/iscsi-encrypted-luns.conf` fallback) | [Encrypted-LUNs config](../developer-guide/data-structures.md#iscsi-encrypted-luns-config) |
| `/etc/pve/qemu-server/<vmid>.conf` | Disk or EFI lines appended | — |

**Internal flow / algorithm:**

1. Validate arguments and delegate storage work to the storage host via SSH in
   two-node mode.
2. If `--encrypted`:
    - Auto-detect encryption algorithm/keyformat from existing encrypted LUNs.
    - Prompt for the absolute path to an already-accessible key file.
    - Validate that the file exists, is readable, is not group-/world-readable,
      and does not reside on the pool/dataset being created.
3. Create the zvol (`zfs create -V ... -s -o compression=lz4`); for encrypted
   zvols, also set `encryption`, `keyformat`, and `keylocation`.
5. In two-node mode:
    - Create the iSCSI backstore and LUN.
    - Add the backstore to `expected-backstores.txt`.
    - Add an entry to `iscsi-encrypted-luns.conf` if encrypted.
    - Save config via `safe-iscsi-save`.
    - Determine the assigned LUN number.
    - Trigger a compute-host rescan.
    - Re-invoke `new-vm-disk --config-only=<lun>` on the compute host to write
      the VM config line (or initialize EFI vars for `EFI` size).
6. Single-node mode: only the zvol is created. The VM config line must be added
   separately (the script does not write `storage:vm-...` lines or initialize EFI
   disks in single-node mode).

**EFI special case:**

- `size=EFI` creates a 4M zvol.
- Prompts whether to pre-enroll Secure Boot keys (`ms-cert=2023k`).
- Writes `bios: ovmf` and `efidisk0:` lines to the VM config.
- Initializes the EFI disk by writing the OVMF vars file to the LUN device.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Zvol created and registered (or user aborted) |
| `1`  | Validation, key, ZFS, or iSCSI failure |

Side effects: creates a zvol; creates iSCSI backstore/LUN (two-node); updates
manifests; appends disk lines to the VM config.

All zvols are created sparse (`-s`) with `compression=lz4`.

With `--encrypted`, the following additional ZFS properties are set:

| Property      | Value                                                                                              |
| ------------- | -------------------------------------------------------------------------------------------------- |
| `encryption`  | `aes-256-gcm` by default; auto-detected from an existing entry in `/etc/zfsutilities/iscsi-encrypted-luns.conf` if available |
| `keyformat`   | `raw` by default; auto-detected from an existing entry in `/etc/zfsutilities/iscsi-encrypted-luns.conf` if available |
| `keylocation` | `file://<absolute-key-path>` (the script checks the file exists but never reads its contents)   |

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

**Called modules / commands:** none.

**Data structures consumed / produced:** none.

**Internal flow / algorithm:**

1. Validate arguments and delegate to the compute host in two-node mode.
2. Discover zvols of the VM that have an origin (are clones).
3. Display the clone dependencies and prompt for confirmation.
4. Run `zfs promote` on each clone zvol locally or via SSH to the storage host.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Promotion completed (or user aborted) |
| `1`  | Validation, SSH, or `zfs promote` failure |

Side effects: reverses the clone/origin relationship — the VM's zvols become
independent, shared clone-origin snapshots move to this VM, and other clones
re-parent automatically. No iSCSI reconfiguration is required. Safe to run while
the VM is running.

See [Archiving a VM](../user-guide/proxmox-integration.md#archiving-a-vm)
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

**Called modules / commands:**

| Script | Purpose |
| ------ | ------- |
| `safe-iscsi-save` | Persist LUN/backstore removal |
| `rescan-storage` | Refresh compute-host device view |
| `zfs-diagnose-busy` | Diagnose `zfs destroy` failure |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `/etc/rtslib-fb-target/expected-backstores.txt` | Entry removed | [Expected-backstores manifest](../developer-guide/data-structures.md#iscsi-expected-backstores-manifest) |
| `/etc/zfsutilities/iscsi-encrypted-luns.conf` | Entry removed if present (legacy `/etc/iscsi-encrypted-luns.conf` fallback) | [Encrypted-LUNs config](../developer-guide/data-structures.md#iscsi-encrypted-luns-config) |

**Internal flow / algorithm:**

1. Validate arguments and delegate storage work to the storage host via SSH in
   two-node mode.
2. Resolve the zvol path, target, and backstore name.
3. Prompt twice for confirmation.
4. In two-node mode:
    - Find and remove the LUN mapping.
    - Remove the block backstore.
    - Remove entries from `expected-backstores.txt` and
      `/etc/zfsutilities/iscsi-encrypted-luns.conf`.
    - Save iSCSI config via `safe-iscsi-save`.
    - Trigger a compute-host rescan.
5. Destroy the zvol. If `zfs destroy` fails, source `zfs-diagnose-busy` and
   print the cause before exiting fatally.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Disk removed (or user aborted) |
| `1`  | Validation, targetcli, or destroy failure |

Side effects: destroys the zvol and its data; removes iSCSI LUN/backstore and
manifest entries in two-node mode.

---

### `unarchive-vm` (both)

Restores an archived VM from archive. Rebuilds iSCSI backstores and LUNs for
each restored zvol and rewrites the Proxmox config disk lines with new LUN numbers.

```bash
sudo unarchive-vm <vmid> [archive_base] [--new-vmid <new_vmid>]
```

**Arguments:**

| Argument       | Description                                                                                             |
| -------------- | ------------------------------------------------------------------------------------------------------- |
| `vmid`         | VM ID of the archived VM to restore                                                                      |
| `archive_base` | Optional ZFS dataset that contains the archive. If not specified, the last-used `archive-base` is used.  |
| `--new-vmid`   | Optional new VM ID for restored zvols, iSCSI resources, and Proxmox config                               |

**Globals:** node-config globals only.

**Called modules / commands:**

| Script | Purpose |
| ------ | ------- |
| `safe-iscsi-save` (inside SSH on storage host) | Persist rebuilt iSCSI config |
| `rescan-storage` | Refresh compute-host device view |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `/etc/rtslib-fb-target/expected-backstores.txt` | Restored backstores added | [Expected-backstores manifest](../developer-guide/data-structures.md#iscsi-expected-backstores-manifest) |
| `/etc/zfsutilities/iscsi-encrypted-luns.conf` | Encrypted restored LUNs added (legacy `/etc/iscsi-encrypted-luns.conf` fallback) | [Encrypted-LUNs config](../developer-guide/data-structures.md#iscsi-encrypted-luns-config) |
| JSON config `archive_path` | Default archive base | [JSON config](../developer-guide/data-structures.md#json-config-varlibzfsutilitiesconfigjson) |
| `.original_volblocksize` sidecars | Restore original `volblocksize` | — |
| `.disk_info` sidecars | Map disk keys to restored zvols/LUNs | — |

**Internal flow / algorithm:**

1. Validate arguments and delegate to the compute host in two-node mode.
2. Resolve the archive base (argument, JSON config, or prompt).
3. Discover archived zvol datasets and the archived Proxmox config.
4. Verify sidecar files exist and destination zvols/config do not already exist.
5. If the original VMID is in use and `--new-vmid` is not supplied, prompt for a
   new VMID.
6. Restore each archived zvol with `zfs send -cw | zfs receive -o volblocksize=<original>`.
7. In two-node mode, create backstores and LUNs for each restored zvol and
   update `expected-backstores.txt` and `/etc/zfsutilities/iscsi-encrypted-luns.conf`.
8. Save iSCSI config via `safe-iscsi-save`.
9. Restore/rewrite the Proxmox config:
    - Single-node: rewrite VMID in disk lines if `--new-vmid` was used.
    - Two-node: rewrite disk lines with new target/LUN paths using `.disk_info`.
    - Regenerate `vmgenid` and `smbios1` UUIDs when `--new-vmid` is used.
10. Trigger iSCSI rescan on the compute host.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | VM unretired |
| `1`  | Validation, archive, SSH, ZFS, or iSCSI failure |

Side effects: creates new zvols; creates iSCSI backstores/LUNs (two-node);
updates manifests; writes a new VM config.

See [Unarchiving a VM](../user-guide/proxmox-integration.md#unarchiving-a-vm)
for the full workflow.

---

### `rescan-storage` (both)

Triggers an iSCSI rescan on the compute node so newly added or resized LUNs become visible.

```bash
sudo rescan-storage
```

**Arguments:** none.

**Globals:** node-config globals only.

**Called modules / commands:** none.

**Data structures consumed / produced:** none.

**Internal flow / algorithm:**

1. Exit silently in single-node mode.
2. Delegate to the compute host if run elsewhere.
3. List active iSCSI sessions; abort if none are found.
4. Run `iscsiadm -m session --rescan`.
5. Count `/dev/disk/by-path/ip-${storage_ip}*` devices and warn if the count is
   unexpectedly low.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Rescan completed (or single-node no-op) |
| `1`  | No iSCSI sessions found |

Side effects: read-only rescan; no changes to ZFS or iSCSI configuration.

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

**Called modules / commands:**

| Script | Purpose |
| ------ | ------- |
| `rescan-storage` | Refresh compute-host device view after resize |

**Data structures consumed / produced:** none.

**Internal flow / algorithm:**

1. Validate arguments and delegate storage work to the storage host via SSH in
   two-node mode.
2. Verify the zvol exists and read its current `volsize`.
3. Run `zfs set volsize=<new-size>` on the zvol.
4. In two-node mode, trigger a compute-host rescan.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Zvol resized |
| `1`  | Validation, ZFS, or SSH failure |

Side effects: grows the zvol. ZFS supports online zvol growth. The guest OS may
require additional steps (e.g., `growpart`, filesystem resize) after the block
device grows.

---

### `restart-iscsi-services` (storage node)

Stops and restarts the iSCSI target service, then adds any encrypted LUNs whose
keys are currently loaded.

```bash
sudo restart-iscsi-services
```

**Prerequisites:** `targetcli` and the `rtslib-fb-targetctl` systemd service must
be installed on the storage host (Debian/Ubuntu package `targetcli-fb`). The
compute host must run Proxmox VE so the script can check VM status, but Proxmox
VE is **not** required on the storage host.

**Arguments:** none.

**Globals:** node-config globals only.

**Called modules / commands:**

| Script | Purpose |
| ------ | ------- |
| `iscsi-add-encrypted-luns` | Re-add encrypted LUNs after service start (called explicitly by this script) |
| `safe-iscsi-save` | Persist final config |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `/etc/zfsutilities/iscsi-encrypted-luns.conf` | Lists encrypted backstores to restore (legacy `/etc/iscsi-encrypted-luns.conf` fallback) | [Encrypted-LUNs config](../developer-guide/data-structures.md#iscsi-encrypted-luns-config) |
| `/etc/rtslib-fb-target/saveconfig-boot.json` | Boot-safe config restored by the service | [iSCSI boot-safe config](../developer-guide/data-structures.md#iscsi-boot-safe-config) |

**Internal flow / algorithm:**

1. Check whether any VMs attached to exported LUNs are running on the compute
   host; abort if any are running.
2. Stop `rtslib-fb-targetctl`.
3. Start `rtslib-fb-targetctl`. The boot-config.conf drop-in restores
   `saveconfig-boot.json` (encrypted backstores excluded).
4. Explicitly call `iscsi-add-encrypted-luns` to add encrypted LUNs whose
   devices are available.
5. Display encrypted LUN status from `/etc/zfsutilities/iscsi-encrypted-luns.conf`.
6. Save the config via `safe-iscsi-save`.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Service restarted and config saved (systemctl and save status are not checked) |
| `1`  | Running VMs detected, or required tools (`targetcli`, `rtslib-fb-targetctl`) missing |

Side effects: restarts the iSCSI target; may add encrypted LUNs; updates
`saveconfig.json` and `saveconfig-boot.json`.

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

**Called modules / commands:** none.

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `/etc/rtslib-fb-target/expected-backstores.txt` | Authoritative expected backstore list | [Expected-backstores manifest](../developer-guide/data-structures.md#iscsi-expected-backstores-manifest) |
| `/etc/zfsutilities/iscsi-encrypted-luns.conf` | Backstores to exclude from boot config (legacy `/etc/iscsi-encrypted-luns.conf` fallback) | [Encrypted-LUNs config](../developer-guide/data-structures.md#iscsi-encrypted-luns-config) |
| `/etc/rtslib-fb-target/saveconfig.json` | Full targetcli config (read and overwritten) | [iSCSI boot-safe config](../developer-guide/data-structures.md#iscsi-boot-safe-config) |
| `/etc/rtslib-fb-target/saveconfig-boot.json` | Boot-safe copy with encrypted backstores stripped | [iSCSI boot-safe config](../developer-guide/data-structures.md#iscsi-boot-safe-config) |

**Internal flow / algorithm:**

1. Verify `saveconfig.json` and `expected-backstores.txt` exist.
2. Count expected backstores from the manifest (ignoring comments and blanks).
3. Count active block backstores in `targetcli`.
4. If active < expected, abort without overwriting `saveconfig.json`.
5. If active > expected, warn but save anyway.
6. Run `targetcli saveconfig`.
7. Generate `saveconfig-boot.json` by stripping encrypted backstores listed in
   `/etc/zfsutilities/iscsi-encrypted-luns.conf`.
8. Regenerate `expected-backstores.txt` from the current list of loaded
   backstores so the manifest stays authoritative after LUN moves or repairs.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Config saved successfully |
| `1`  | Missing files, degraded state, or save skipped |

Side effects: overwrites `saveconfig.json`; regenerates `saveconfig-boot.json`;
regenerates `expected-backstores.txt`.

The manifest contains one backstore name per line (`vm-<vmid>-disk-<N>` format).
Comments and blank lines are ignored. This file is the authoritative source of
truth for expected LUN count — it is not derived from `saveconfig.json` or ZFS.

| Script                                      | Manifest action                                                   |
| ------------------------------------------- | ----------------------------------------------------------------- |
| [`new-vm-disk`](#new-vm-disk-both)          | Adds entry when creating a disk                                   |
| [`remove-vm-disk`](#remove-vm-disk-both)    | Removes entry when destroying a disk                              |
| [`zfsdelfs`](commands.md#zfsdelfs)          | Removes entry during teardown; `zfs-send-receive` rebuild re-adds |
| [`move-vm-disk`](#move-vm-disk-both)        | Removes source entry and adds destination entry                   |
| [`repair-iscsi-luns`](#repair-iscsi-luns-storage-node) | Regenerates the entire manifest from current targetcli backstores |

Use `safe-iscsi-save` instead of `targetcli saveconfig` in any script that modifies
iSCSI config.

---

### `setup-iscsi-targets` (storage node)

Creates iSCSI targets, TPGs, and portals from the pool-to-target mappings
defined in `/etc/zfsutilities/node.conf`. Idempotent — safe to run multiple
times. Skips targets that already exist and adds missing portals to existing
targets.

```bash
sudo setup-iscsi-targets
```

**Arguments:** none.

**Globals:** node-config globals only.

**Called modules / commands:**

| Script | Purpose |
| ------ | ------- |
| `node-lib.sh` | Two-node host/target resolution |
| `targetcli` | Create targets, TPGs, and portals |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `/etc/zfsutilities/node.conf` | `POOL_TARGET` and `IQN_PREFIX` source | [Node config](../developer-guide/data-structures.md#node-configuration-file-etczfsutilitiesnodeconf) |
| `targetcli` iSCSI config | Targets, TPGs, and portals created or verified | — |

**Internal flow / algorithm:**

1. Exit silently in single-node mode.
2. Verify the script is running on the storage host.
3. Ensure `targetcli` is installed.
4. For each entry in `pool_target`:
    - Create the target IQN if it does not already exist.
    - Ensure TPG1 exists.
    - Disable authentication and demo-mode write protect.
    - Create the portal `${storage_ip}:3260` if it does not already exist.
5. Save the targetcli configuration if anything changed.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Targets configured |
| `1`  | Not running on the storage host, or `targetcli` not found |

Side effects: creates or verifies iSCSI targets, TPGs, and portals.

---

### `show-lun-map` (compute node)

Shows which iSCSI LUN maps to which block device (`/dev/sdX`) and which Proxmox VM
on the compute node.

```bash
sudo show-lun-map
```

**Arguments:** none.

**Globals:** node-config globals only.

**Called modules / commands:** none.

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `/dev/disk/by-path/ip-${storage_ip}*` | iSCSI device symlinks | — |
| `pool_target` | Valid target short names for filtering | [pool_target](../developer-guide/data-structures.md#pool_target-associative-array) |

**Internal flow / algorithm:**

1. Exit silently in single-node mode.
2. Delegate to the compute host if run elsewhere.
3. Build a target regex from `pool_target` values.
4. Iterate over `/dev/disk/by-path/ip-${storage_ip}*` symlinks, extracting target
   and LUN from each basename.
5. Resolve each symlink to its `/dev/sdX` device and read its size.
6. Print a sorted target/LUN/device/size table.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Map displayed |
| `1`  | No iSCSI devices found or error |

Side effects: read-only; no changes to ZFS or iSCSI state.

---

### `switch-version` (any host)

Wires a deployed version into active production and updates the `current` symlink.

```bash
sudo switch-version <version>|previous|--list|--uninstall
```

**Arguments:**

| Argument      | Description                                        |
| ------------- | -------------------------------------------------- |
| `version`     | Version string to activate                         |
| `previous`    | Roll back to the previously active version         |
| `--list`      | Show all installed versions and which is active    |
| `--uninstall` | Remove this version's production wiring            |

**Globals:**

| Variable | Role | Reference |
| -------- | ---- | --------- |
| `ZFSUTILITIES_VERSION_BASE` | Override base directory (tests) | — |
| `ZFSUTILITIES_BASHINIT_LINK`, etc. | Override wiring targets (tests) | — |

**Called modules / commands:**

| Script | Purpose |
| ------ | ------- |
| `rootcheck` | Verify root privileges |
| `lib/desktop-launcher-lib.sh` | Desktop shortcut helpers |

**Data structures consumed / produced:**

| Path | Role |
| ---- | ---- |
| `/usr/local/lib/zfsutilities/current` | Active version symlink |
| `/usr/local/lib/zfsutilities/previous` | Previous version symlink |
| `/usr/local/lib/zfsutilities/bin` | PATH symlink |
| `/etc/profile.d/zfsutilities.sh` | PATH export |
| `/etc/sudoers.d/zfsutilities` | `secure_path` for sudo |
| `/root/bashinit` | Symlink to active version's `bashinit` |
| `/usr/local/lib/node-lib.sh`, `/usr/local/lib/two-node-lib.sh`, `/usr/local/lib/rootcheck` | Library symlinks |

**Internal flow / algorithm:**

1. `--list`: enumerate installed versions and mark current/previous.
2. `--uninstall`: remove production wiring (symlinks, profile, sudoers, desktop
   shortcuts) while leaving the version directory intact.
3. Version activation:
    - Resolve `previous` to a version name if requested.
    - Verify the target version directory exists.
    - If the requested version is not already active:
        - Call the prior version's own `switch-version --uninstall` to clean up its
          wiring.
        - Record the current version as `previous`.
        - Repoint the `current` symlink.
        - Re-execute the target version's `switch-version` so its code performs the
          wiring.
    - Install wiring: `bin` symlink, `/etc/profile.d`, `/etc/sudoers.d`,
      `/root/bashinit`, library symlinks, desktop shortcuts.
    - Stop any running documentation server on port 8000.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Version switched, listed, or unwired |
| `1`  | Validation or filesystem error |

Side effects: repoints symlinks; writes/updates `profile.d`, `sudoers.d`, and
desktop shortcuts. New script invocations immediately use the new version;
already-running scripts are unaffected.

---

### `uninstall-version` (any host)

Removes a deployed version directory. Refuses to remove the currently active
version.

```bash
sudo uninstall-version [-y|--yes] <version>
```

**Arguments:**

| Argument    | Default | Description                       |
| ----------- | ------- | --------------------------------- |
| `-y`        | off     | Skip the confirmation prompt      |
| `--yes`     | off     | Skip the confirmation prompt      |
| `version`   | —       | Version string to remove          |

**Globals:** none.

**Called modules / commands:** none.

**Data structures consumed / produced:** none.

**Internal flow / algorithm:**

1. Verify root privileges and a single argument.
2. Verify the version directory exists.
3. Refuse if the version is the current active target.
4. If `-y`/`--yes` was not given, prompt for confirmation.
5. `rm -rf` the version directory.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Version removed (or user aborted) |
| `1`  | Validation error or attempt to remove active version |

Side effects: deletes the version directory under
`/usr/local/lib/zfsutilities/versions/<version>/`.

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

**Called modules / commands:**

| Script | Purpose |
| ------ | ------- |
| `safe-iscsi-save` (storage host) | Persist new backstores/LUNs |
| `rescan-storage` | Make new LUNs visible on the compute host |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| Source/dest VM configs | Read source; write destination | — |
| `@clone-<timestamp>-c` snapshots | Clone-origin snapshots retained on source zvols | — |

**Internal flow / algorithm:**

1. Validate arguments and delegate to the compute host in two-node mode.
2. Parse disk lines from the source VM config (single-node: `storage:vm-...`;
   two-node: iSCSI `by-path`).
3. For each disk:
    - Create a `@clone-<timestamp>-c` snapshot on the source zvol if it does not
      already exist (same snapshot reused across all disks in this operation).
    - `zfs clone` the snapshot to a new destination zvol.
    - In two-node mode, create an iSCSI backstore and LUN on the storage host.
4. In two-node mode, save iSCSI config on the storage host via `safe-iscsi-save`.
5. Write the destination VM config with new LUN numbers, fresh MAC addresses,
   new `vmgenid`, and new SMBIOS UUID.
6. Drop `protection:` and `meta:` fields from the cloned config.
7. Trigger iSCSI rescan on the compute host.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Clone completed successfully |
| non-zero | Validation, SSH, ZFS, or iSCSI failure |

Side effects: creates ZFS clone zvols dependent on the source snapshots; creates
new iSCSI LUNs (two-node); writes a new VM config. The clone-origin snapshot is
**retained** on the source zvols. ZFS prevents its deletion while any clone
created from it exists.

Use [`promote-vm-clone`](#promote-vm-clone-both)
to cut dependencies before retiring the source VM.

See [VM Clone Provisioning](../user-guide/proxmox-integration.md#cloning-a-vm) for the full workflow.

---

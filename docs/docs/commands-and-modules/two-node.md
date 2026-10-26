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

- [Bare-Metal Restore Runbook](#bare-metal-restore-runbook-two-node)
- [Dashboard iSCSI Issues](#dashboard-iscsi-issues-two-node-gui)
- [`attach-vm-disk` (both)](#attach-vm-disk-both)
- [`check-vm-disk-paths` (compute node)](#check-vm-disk-paths-compute-node)
- [`clone-vm` (both)](#clone-vm-both)
- [`deploy-version` (repo root)](#deploy-version-repo-root)
- [`detach-vm-disk` (both)](#detach-vm-disk-both)
- [`enroll-efi-keys-vm` (compute node)](#enroll-efi-keys-vm-compute-node)
- [`enroll-iscsi-pool` (storage node)](#enroll-iscsi-pool-storage-node)
- [`export-iscsi-state` (storage node)](#export-iscsi-state-storage-node)
- [`iscsi-add-encrypted-luns` (storage node)](#iscsi-add-encrypted-luns-storage-node)
- [`iscsi-restore-luns` (storage node)](#iscsi-restore-luns-storage-node)
- [`list-vm-disks` (both)](#list-vm-disks-both)
- [`repair-iscsi-luns` (storage node)](#repair-iscsi-luns-storage-node)
- [`repair-vm-disk-refs` (compute node)](#repair-vm-disk-refs-compute-node)
- [`repair-vm-disk-sizes` (compute node)](#repair-vm-disk-sizes-compute-node)
- [`reconcile-iscsi-state` (storage node)](#reconcile-iscsi-state-storage-node)
- [`move-vm-disk` (both)](#move-vm-disk-both)
- [`new-vm-disk` (both)](#new-vm-disk-both)
- [`switch-version` (any host)](#switch-version-any-host)
- [`uninstall-version` (any host)](#uninstall-version-any-host)
- [`sever-vm-clone` (both)](#sever-vm-clone-both)
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

## Bare-Metal Restore Runbook (two-node)

Recovery from an OS-disk bare-metal restore on either node. The design keeps
three authorities off the OS disks: the **pool-resident state map**
(`iscsi-state.json`, written by [`export-iscsi-state`](#export-iscsi-state-storage-node)
onto every online pool after every LUN change), the **compute-host VM
configs**, and the **pool zvols** themselves. The LIO config and the
expected-backstores manifest are derived state — both regress with an OS-disk
restore and get rebuilt from the authorities. Identity during recovery is the
backstore/zvol name, never the LUN number alone; anything ambiguous is
refused with evidence, never guessed.

### Before a restore ever happens (already done by the tooling)

- Every `safe-iscsi-save` refreshes the pool state map on every online pool;
  pool-wide snapshot/retention policies give it history. No manual step.
- On two-node compute hosts, the `zfsutilities-iscsi-fence.timer` (installed
  by [switch-version](#switch-version-any-host) activation) runs
  [`check-vm-disk-paths --recover`](#check-vm-disk-paths-compute-node) every
  5 minutes.

### Scenario A — storage host restored (LUNs vanished)

Symptom: the fence fails within ~5 minutes (VM disk references missing), or
`sudo check-vm-disk-paths` exits 1. The regressed objects are the LIO config
and the manifest on the storage host's OS disk.

1. **Let the fence work, or run it once by hand** on the compute host:
   `sudo check-vm-disk-paths --recover`. It rescans the local iSCSI sessions
   and, when references are still missing, runs
   [`reconcile-iscsi-state --yes`](#reconcile-iscsi-state-storage-node) on the
   storage host (one ssh). The reconcile recreates every map backstore whose
   zvol still exists — backstore with `emulate_tpu=1`, LUN at the recorded
   number, ACL bindings — then regenerates the manifest, saves the LIO tree,
   refreshes the pool map, and rescans the compute host.
2. **Inspect refusals, if any.** Identity conflicts (a LUN slot held by a
   different backstore, a backstore pointing at a different zvol, a missing
   target) are refused per item with evidence and are never auto-resolved.
   Resolve them by hand on the storage host (delete the conflicting live
   object or restore the recorded layout) and re-run
   `sudo reconcile-iscsi-state`. Map entries whose zvol is gone (offline
   pool, deleted dataset) are skipped and preserved in the map.
3. **Confirm green:** `sudo check-vm-disk-paths` exits 0; the VMs start.

### Scenario B — compute host restored (VM configs regressed)

Symptom: VM configs reference (target, LUN) slots that now hold different
backstores — the dangerous case, because Proxmox would silently attach the
wrong disk. The storage host is healthy and current.

1. **On the compute host**, run
   [`sudo repair-vm-disk-refs --dry-run`](#repair-vm-disk-refs-compute-node).
   It fetches the storage host's newest pool state map (read-only,
   `export-iscsi-state --print-map`) and the live LUN topology
   (`list-vm-disks --gather-lun-info`), resolves each config reference to the
   backstore its slot held at map time, and reports what it would rewrite.
2. **Review the plan.** Rewrites only happen when the map identity is the
   VM's own disk and that disk is exported live at a different (target, LUN):
   the by-path volume is repointed and every disk option is preserved
   byte-for-byte. Everything ambiguous is refused with evidence: a reference
   with no map entry, a disk that now belongs to another VM, a backstore not
   exported live (run Scenario A's reconcile first), a running VM, or two
   references resolving to one backstore.
3. **Apply:** `sudo repair-vm-disk-refs` and confirm (or use `--yes`). The
   script verifies every rewritten reference resolves to a live device,
   rescanning iSCSI sessions first when needed.
4. **Resolve refusals deliberately.** A refused reference means identity
   could not be established — re-attach that disk by hand (for example with
   [`attach-vm-disk`](#attach-vm-disk-both)) instead of guessing a LUN.
5. **Confirm green:** `sudo check-vm-disk-paths` exits 0; the VMs start.

### Scenario C — both nodes restored

Run Scenario A first (restore the LUN topology from the pool map), then
Scenario B (re-point any regressed configs). The map on the pools is the
surviving authority for both halves.

### Coexistence with a hand-rolled health check

The fence units installed by switch-version activation leave any existing
hand-rolled iSCSI health check in `/usr/local/bin` untouched; the two can
coexist indefinitely, and the hand-rolled check can be retired at the
operator's discretion once the fence has proven itself.

---

### `clone-vm` (both)

Creates a new Proxmox VM by copying its source VM's disk zvols via `zfs send/receive`.
Produces a fully independent copy with no ongoing ZFS dependency on the source.
The copies run through the shared transfer engine
([`transfer-lib.sh`](modules.md#transfer-libsh)), so per-enclosure rate caps
apply on the node that streams (single-node: locally; two-node: the storage
host, where the pools live) — clone-vm prompts for no rate of its own, and
with no cap configured the copy pipeline is identical to the plain
send/receive.

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
| `transfer-lib.sh` | `transfer_do` copy pipeline (rate governance incl. enclosure caps) |
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
    - Copy to a new destination zvol via `transfer_do` (`zfs send | zfs
      receive`, paced when an enclosure cap applies).
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
Called by the `boot-config.conf` drop-in's `ExecStartPost` hook after the
iSCSI target service starts (covering keys available at boot, e.g. via
`keylocation=file://`), explicitly by the operator after loading keys, and by
[`restart-iscsi-services`](#restart-iscsi-services-storage-node) after it restarts
the iSCSI target service.

**Arguments:** none.

**Globals:** node-config globals only.

**Called modules / commands:**

| Script | Purpose |
| ------ | ------- |
| `safe-iscsi-save` | Persist config after adding encrypted LUNs (only when something was added) |

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
    - Look up the original LUN index from `saveconfig.json`, scoped to the
      exact target IQN, to preserve stable compute-node `by-path` symlinks
      (a global first-match lookup could return an orphan target's index).
    - Create the block backstore and map it to the target at the original LUN
      index (or auto-allocate if no index is found).
3. Save the iSCSI config via `safe-iscsi-save`, but only when a backstore was
   added — a keyless boot-time run must not re-save (and FATAL-log) a
   degraded state on every boot.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Completed (may have added zero LUNs) |

Side effects: creates missing encrypted backstores/LUNs; regenerates
`saveconfig-boot.json` via `safe-iscsi-save`.

---

### `iscsi-recover-encrypted-luns` (storage node)

Reconstructs encrypted iSCSI LUNs after keys are loaded post-boot, then
rescans the compute host. Boot restores `saveconfig-boot.json` (encrypted
backstores stripped), so encrypted LUNs are gone until re-added: at boot by
the drop-in's `ExecStartPost` hook when keys are available, or post-boot by
this script after the operator loads keys manually (e.g. from a LUKS USB
drive unlocked at the console after login).

```bash
sudo iscsi-recover-encrypted-luns
```

**Arguments:** none.

**Globals:** node-config globals only.

**Called modules / commands:**

| Script | Purpose |
| ------ | ------- |
| `safe-iscsi-save` | Persist config after changes (only when something was added) |
| `rescan-storage` | Surface restored LUNs on the compute host (self-delegates via SSH) |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `/etc/zfsutilities/iscsi-encrypted-luns.conf` | Authoritative list of encrypted backstores to recover | [Encrypted-LUNs config](../developer-guide/data-structures.md#iscsi-encrypted-luns-config) |
| `/etc/rtslib-fb-target/saveconfig.json` | Source of the recorded LUN index per backstore and target | [iSCSI boot-safe config](../developer-guide/data-structures.md#iscsi-boot-safe-config) |

**Internal flow / algorithm:**

1. In single-node mode, print an informational message and exit.
2. For each entry in `/etc/zfsutilities/iscsi-encrypted-luns.conf`:
    - WARN and mark unavailable if the device node is not present (keys not
      loaded).
    - Skip when the backstore and its LUN mapping already exist (idempotent).
    - Look up the recorded LUN index from `saveconfig.json`, scoped to the
      exact target IQN. Never auto-assign: a missing index is a FATAL for
      that entry, because auto-assignment can collide or pick the wrong
      slot when orphan targets under a different IQN prefix exist.
    - (Re)create the backstore and mapping, then verify the mapping took.
3. When anything was added: persist via `safe-iscsi-save`, then run
   `rescan-storage`.
4. Print the per-run summary counters and finish. Start the recovered VMs
   afterwards from the Proxmox GUI (or `qm start <vmid>` on the compute
   host) — the script does not print start commands.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Every configured encrypted LUN is mapped (re-added or already present) |
| `1`  | Any entry failed or its device was unavailable |

Side effects: recreates encrypted backstores/LUNs; updates `saveconfig.json`
and `saveconfig-boot.json`; rescans the compute host.

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
guest.  Results are printed as one table per iSCSI target (two-node) or per
pool (single-node); long values such as by-path names wrap onto multiple lines
inside their table cells, and the table width follows the terminal.

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
3. For each running VM, issue a single `qm guest exec` that walks all of that
   VM's scsi disks and lists the guest's `/dev/disk/by-path` entries and the
   resolved `/dev/sdX` targets, so a VM with N scsi disks costs one guest
   round-trip instead of N.  SCSI disks are matched by disk key, using the
   VM's `scsihw` type to translate `scsiN` into the guest SCSI address:
   `scsiN` → `*scsi-0:0:N:0` (target N) with the default multi-disk
   controllers (`lsi`, `virtio-scsi`), and `scsiN` → `*scsi-0:0:0:N`
   (target 0, lun N — one controller per disk) with `virtio-scsi-single`.
4. In single-node mode, enumerate local pools and their `vm-*` zvols directly
   and merge with the VM/guest maps.
5. In two-node mode, gather LUN/zvol metadata from the storage host and merge
   with the VM/guest maps from the compute host.  ZFS sizes, clone origins,
   and snapshot clone dependents are looked up with one batched `zfs get` and
   one `zfs list -t snapshot` per pool rather than one invocation per zvol.
6. Annotate each zvol with clone relationships:
    - `[clone of <snapshot>]` if the zvol is a ZFS clone, where `<snapshot>`
      is the full origin snapshot dataset name (e.g.
      `threeamigos/proxmox/vm-904-disk-0@clone-2026-07-30T16:00Z-c`).
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
3. Verify the zvol exists and read its `volsize` — locally in single-node
   mode and when invoked on the storage host; over SSH on the storage host
   when invoked on the compute host in two-node mode (the zvol lives on the
   storage host, which local `zfs` on the compute host cannot see).
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

### `enroll-iscsi-pool` (storage node)

Enrolls a pool in two-node iSCSI export end to end:

1. Adds the pool to the `POOL_TARGET` map in `/etc/zfsutilities/node.conf` on
   **both** nodes — the peer node's config is updated first (over SSH), so a
   peer failure aborts before the local change leaves the nodes inconsistent.
2. Runs `setup-iscsi-targets` on the storage host to create the pool's target
   and portal.
3. Runs `rescan-storage` so the compute host discovers the LUNs.

Idempotent — re-running for an already-enrolled pool skips the config change and
just re-verifies the target and rescans. The Create Pool wizard offers this
automatically after creating a pool on the storage host in two-node mode, so a
new pool no longer needs the three manual enrollment steps.

```bash
sudo enroll-iscsi-pool [--dry-run] [--update-config-only] <pool> [short-name]
```

**Arguments:**

| Argument | Meaning |
| -------- | ------- |
| `<pool>` | Pool name to enroll (required) |
| `[short-name]` | Target short name (IQN suffix); derived from the pool name when omitted (lowercased, keeping only `a-z`, `0-9`, `.`, `-`) |
| `--dry-run` | Print each planned action without changing anything |
| `--update-config-only` | Only update node.conf on this node; skip target setup and rescan (used for the SSH peer call and for manual node.conf repair) |

**Globals:** node-config globals only. Test overrides: `ENROLL_ISCSI_NODE_LIB`,
`ENROLL_ISCSI_NODE_CONF`, `ENROLL_ISCSI_SETUP_TARGETS`,
`ENROLL_ISCSI_RESCAN_STORAGE`, `ENROLL_ISCSI_TEST_MODE`.

**Called modules / commands:**

| Script | Purpose |
| ------ | ------- |
| `node-lib.sh` | Two-node host/target resolution |
| `setup-iscsi-targets` | Create the pool's iSCSI target and portal |
| `rescan-storage` | Compute-host LUN discovery rescan (delegates via SSH) |
| `ssh` | Update the peer node's node.conf |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `/etc/zfsutilities/node.conf` | `POOL_TARGET` entry added on both nodes (one-time backup kept as `<conf>.bak-enroll-<date>`) | [Node config](../developer-guide/data-structures.md#node-configuration-file-etczfsutilitiesnodeconf) |
| `targetcli` iSCSI config | Target and portal created or verified | — |

**Internal flow / algorithm:**

1. Exit silently in single-node mode.
2. Verify the script is running on the storage host (`--update-config-only`
   excepted — that mode is the peer-delegation path and may run on either node).
3. Derive the target short name if not given.
4. Update the peer node's node.conf via SSH (`--update-config-only`); FATAL
   with a "nodes may be out of sync" hint on failure, before touching the local
   config.
5. Update the local node.conf (idempotent skip when already enrolled).
6. Run `setup-iscsi-targets` (FATAL on failure).
7. Run `rescan-storage` (WARN on failure — the target already exists, so a
   manual `sudo rescan-storage` on the compute host finishes the job).

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Pool enrolled (or nothing to do); a rescan failure still returns `0` |
| `1`  | Usage error, not the storage host, peer/local config update failed, or `setup-iscsi-targets` failed |

Side effects: modifies node.conf on both nodes (with backup); creates or
verifies the pool's iSCSI target and portal; rescans the compute host.

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

### `sever-vm-clone` (both)

Severs a ZFS-cloned VM's disk zvols from their origin snapshots by copying each
clone zvol in full into a fresh, origin-free zvol that is swapped in under the
same name, so Proxmox configs and iSCSI references keep working unchanged.
Unlike `zfs promote` — which inverts the clone relationship, keeps the origin
snapshot alive, and re-parents every sibling clone onto the promoted dataset —
severance leaves both sides with independent blocks and releases the origin
snapshot for destruction.

```bash
sudo sever-vm-clone <vmid>
sudo sever-vm-clone <dataset> [dataset...]
```

**Arguments:**

| Argument  | Description                                                                                                                                                         |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `vmid`    | Sever every clone zvol of this VM                                                                                                                                   |
| `dataset` | Sever only the named clone zvols; datasets that are not clone zvols are skipped with an INFO line. A VM ID and named datasets are mutually exclusive.                |

**Recovery options:**

| Option                    | Description                                                                                                          |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `--continue <state-file>` | Resume an interrupted cutover from the recorded phase — no re-copy; an interrupted catch-up resumes from its receive resume token |
| `--rollback <state-file>` | Revert an interrupted run before the destroy: destroy the staged copies, remove the `@sever-*` snapshots, reapply the released holds. Impossible once an original zvol was destroyed — complete the swap with `--continue` instead |

**Globals:** node-config globals only.

**Called modules / commands:**

| Script | Purpose |
| ------ | ------- |
| `zfs-migrate-send` | Full copy, catch-up incremental, and holding-pool copy-back through the migration engine (receive-resume support) |
| `zfsreapplyholds` (sourced) | Capture/release the original's snapshot holds; reapply them on the swapped-in zvol |
| `zfs-diagnose-busy` (sourced) | Diagnose a failed origin-snapshot destroy in the release offer |
| `zfslockmanager` | `w` locks for the transfer; `x` locks spanning the destroy→rename window |
| `safe-iscsi-save` (storage host) | Persist the backstore re-export (two-node) |
| `rescan-storage` | Compute-host rescan after the cutover (two-node) |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `/tmp/sever-vm-clone-<key>-<ts>.state` (+ `.holds<N>` files) | Cutover recovery state file and per-disk captured-holds files | — |
| `<pool>/proxmox/sever_<vmid>/`, `<holding>/sever_<vmid>/` | Temp namespaces holding the staged copies (removed once empty) | — |
| `/etc/rtslib-fb-target/expected-backstores.txt` | Backstore removed before the swap, re-added after | [Expected-backstores manifest](../developer-guide/data-structures.md#iscsi-expected-backstores-manifest) |
| `/etc/zfsutilities/iscsi-encrypted-luns.conf` | Entry removed/re-added when the zvol is encrypted (legacy `/etc/iscsi-encrypted-luns.conf` fallback) | [Encrypted-LUNs config](../developer-guide/data-structures.md#iscsi-encrypted-luns-config) |

**Internal flow / algorithm:**

1. Validate arguments and require Proxmox (`qm`). In two-node mode the compute
   host is the canonical entry — an invocation on the storage host delegates
   over SSH before the `qm` guard runs; recovery modes delegate too.
2. Discovery, run where the zvols live (over SSH in two-node mode): the clone
   zvols (VM mode: every `vm-<vmid>-disk-<N>` zvol under a `proxmox` dataset
   that has an origin; dataset mode: the named datasets), each with its origin
   snapshot, used/referenced bytes, and encryption, plus every pool's free
   space. Non-clone and non-zvol datasets are skipped with an INFO line; a
   missing dataset is fatal.
3. Display the severance plan: per zvol the origin and sizes, per pool a
   same-pool space verdict — each source pool needs largest-disk × 1.1 free,
   because copies are swapped in and their originals destroyed one disk at a
   time. When a source pool is that tight, the confirmation step asks for an
   intermediate holding pool (candidate imported pools are listed; encrypted
   sources trigger a key check on the holding pool; the copies then stage in
   `<holding>/sever_<vmid>/`) and confirms destruction of the destroyable
   origin snapshots against a plan-time copy-back space estimate.
4. Prompt for confirmation.
5. **Phase 1 — transfer (online; the owning VMs may keep running):** per disk,
   sequentially, under `w` locks on the source zvol and the temp-namespace
   parent: a bucket-less `@sever-<UTC timestamp>` snapshot (retention never
   prunes it), a full copy through the `zfs-migrate-send` engine into the temp
   namespace (clone sources are copied origin-free — a plain full send of the
   oldest snapshot plus `-w -I` incrementals; a replication stream of a clone
   would let a same-pool receive link the destination straight back to the
   still-present origin), `refreservation=none` on the received zvol, the
   received snapshot's GUID, and an origin check that refuses any staged copy
   that is still a clone. An interrupted receive resumes from its receive
   resume token on re-run.
6. **Phase 2 — cutover (the owning VMs must be stopped; enforced with
   `qm status`):** write the cutover state file, then per disk, inside one
   storage-side worker under `set -e` (a child shell; an
   `ssh root@<storage_host> bash -s` heredoc in two-node mode — locks
   included, so the destroy-class locks span the destroy→rename window):
    - Take a `@sever-<UTC timestamp>-cutover` snapshot and receive a catch-up
      incremental through the engine, so every write made during Phase 1 lands
      in the staged copy before anything is destroyed.
    - Verify the cutover-snapshot GUID on source and copy (a mismatch aborts
      with nothing destroyed); in holding mode, re-check copy-back space
      feasibility with fresh numbers before any destruction.
    - Capture then release the original's snapshot holds.
    - Two-node: tear the zvol's iSCSI LUN and backstore down — a live
      backstore pins the device node the destroy frees.
    - Destroy the original clone zvol — snapshot by snapshot first (children
      first: `zfs destroy <dataset>` refuses while any child snapshot lives,
      and the original carries retention snapshots beyond this tool's
      `@sever-*` ones); in holding mode, destroy the confirmed
      origin snapshot and copy the staged copy back into the source-pool temp
      namespace through the engine (GUID verified again).
    - `zfs rename` the copy into the original name — the name-preserving swap
      — and wait for `/dev/zvol/<name>` to return via udev.
    - Two-node: re-create the backstore named for the zvol and re-export it at
      the SAME LUN id (a slot taken meanwhile falls back to auto-assign with a
      WARN for the PVE `by-path` reference), keep the manifest and
      encrypted-LUNs bookkeeping in step, and run `safe-iscsi-save`.
    - Verify the post-swap GUID and that the swapped-in zvol is origin-free
      (a swap that is still a clone fails verification — the VM stays usable
      under its own name, but nothing was severed), reapply the captured
      holds, destroy the holding-pool copy (holding mode), destroy this
      tool's `@sever-*` scaffolding snapshots, and release the locks. Every
      step is idempotent and recorded per disk in the state file.
7. Remove the now-empty temp namespaces; in two-node mode run `rescan-storage`
   on the compute host when any disk was exported; then print the
   origin-snapshot report: for every origin, snapshots still cloned or held
   are only reported (with the clones/holds named); unpinned, hold-free
   origins are offered for destruction with typed confirmation — that offer is
   where the pinned space actually comes back. An unpinned origin can report
   `releases 0B` with an explanation line: a snapshot's `used` counts only its
   unique data, and a fully-shared origin (every block still referenced by the
   live dataset or its other snapshots) releases nothing immediately — the
   space returns as the remaining references are destroyed. This is normal ZFS
   accounting, not a defect of the severance.
8. Remove the state file.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Severance completed (or user aborted before any mutation) |
| `1`  | Validation, SSH, ZFS, iSCSI, or transfer failure |

Side effects: true severance — no clone relationship remains after the cutover
and the origin snapshots become deletable (offered with typed confirmation).
The fresh origin-free zvols replace the clones under the same names, and the
iSCSI LUN is preserved (re-exported at the same LUN id), so no Proxmox or
iSCSI reconfiguration is needed. The transfer phase runs online; the VM must
be stopped for the cutover.

See [Severing a Clone](../user-guide/concepts.md#severing-a-clone) for what
severance does and why `zfs promote` is not it. In the GTK GUI, the Datasets
tab's **Sever Clone** button runs this script on the selected clone
dataset(s) — see the GUI reference under
[Snapshot and hold actions](../user-guide/gtk-gui.md#snapshot-and-hold-actions).

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

**Globals:** node-config globals; `EXPECTED_BACKSTORES_MANIFEST` optionally
overrides the expected-backstores manifest path.

**Called modules / commands:**

| Script | Purpose |
| ------ | ------- |
| [`zfsdelfs`](commands.md#zfsdelfs) | Destroy the zvol with its snapshot children and their holds (`autoproceed='Y'`) |
| `safe-iscsi-save` | Persist LUN/backstore removal |
| `rescan-storage` | Refresh the compute-host device view — also after a failed remote run, since the LUN may already be gone |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `/etc/rtslib-fb-target/expected-backstores.txt` | Entry removed | [Expected-backstores manifest](../developer-guide/data-structures.md#iscsi-expected-backstores-manifest) |
| `/etc/zfsutilities/iscsi-encrypted-luns.conf` | Entry removed if present (legacy `/etc/iscsi-encrypted-luns.conf` fallback) | [Encrypted-LUNs config](../developer-guide/data-structures.md#iscsi-encrypted-luns-config) |

**Internal flow / algorithm:**

1. Validate arguments and delegate storage work to the storage host via
   `ssh -t` (TTY-allocating, so the remote confirm prompts are visible; the
   input-hold env prefix keeps numbered GUI prompts working across the hop)
   with `--skip-rescan` — the wrapper performs one compute-host rescan itself,
   even when the remote run failed.
2. Resolve the zvol path, target, and backstore name.
3. Prompt twice for confirmation; declining either exits 0 having destroyed
   nothing.
4. In two-node mode:
    - Find and remove the LUN mapping (skipping gracefully if already gone).
    - Remove the block backstore (likewise).
    - Remove entries from `expected-backstores.txt` and
      `/etc/zfsutilities/iscsi-encrypted-luns.conf`.
    - Save iSCSI config via `safe-iscsi-save`.
5. Destroy the zvol via `zfsdelfs ... autoproceed='Y'` — any VM that has run
   through dailybackup carries child snapshots (usually held), which a bare
   `zfs destroy` refuses; `zfsdelfs` deletes the subtree bottom-up, releasing
   holds, and takes its own destroy lock. Clone dependents abort the destroy
   (`zfsdelfs` reports them; sever with `sever-vm-clone` first).

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

**Globals:** node-config globals; `transfer_rate_limit` (transfer rate limit,
empty = unlimited; prompted with the JSON-config default `archive_rate_limit`).

**Called modules / commands:**

| Script | Purpose |
| ------ | ------- |
| `safe-iscsi-save` (storage side, via `on_storage`) | Persist rebuilt iSCSI config |
| `rescan-storage` (compute side, via `on_compute`) | Refresh compute-host device view (after targeted discovery + login of the mapped targets) |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `/etc/rtslib-fb-target/expected-backstores.txt` | Restored backstores added | [Expected-backstores manifest](../developer-guide/data-structures.md#iscsi-expected-backstores-manifest) |
| `/etc/zfsutilities/iscsi-encrypted-luns.conf` | Encrypted restored LUNs added (legacy `/etc/iscsi-encrypted-luns.conf` fallback) | [Encrypted-LUNs config](../developer-guide/data-structures.md#iscsi-encrypted-luns-config) |
| JSON config `archive_path` | Default archive base | [JSON config](../developer-guide/data-structures.md#json-config-varlibzfsutilitiesconfigjson) |
| `.original_volblocksize` sidecars | Original `volblocksize` (required for copy-method restores, informational for raw) | — |
| `.disk_info` sidecars | Map disk keys to restored zvols/LUNs; carry the `METHOD=copy\|raw` archive marker and the `RESTORED_AS=` completion marker appended after each verified restore | — |

**Internal flow / algorithm:**

1. Validate arguments. The script runs wherever it was invoked:
   storage-side payloads go through `on_storage` (local on the storage host)
   and compute-side operations through `on_compute` (local on the compute
   host) — no delegate-to-compute bounce.
2. Resolve the archive base (argument, JSON config, or prompt), then prompt
   for the transfer rate limit (saved as the shared JSON default).
3. Discover archived zvol datasets and the archived Proxmox config.
4. Verify the `.disk_info` sidecars exist, then classify existing
   destinations for re-run idempotency: a `RESTORED_AS` marker means the
   disk is already restored (skipped); an existing zvol without the marker
   is only destroyed after an explicit confirm; a destination config with
   every disk marked means the restore already completed (clean exit).
   Missing `.original_volblocksize` sidecars warn; the shared engine
   enforces them per restore method.
5. If the original VMID is in use and `--new-vmid` is not supplied, prompt for a
   new VMID.
6. Restore each archived zvol with the shared transfer engine
   (`lib/archive-engine.sh`, sourced on the storage host): `METHOD=copy`
   archives create the destination zvol at the sidecar's original
   `volblocksize` and device-copy the archive snapshot onto it (in-flight
   source hash plus a destination read-back verify);
   `METHOD=raw` and unmarked legacy archives use `zfs send -cw | zfs receive`.
7. In two-node mode, resolve each restored zvol's pool against the live LIO
   target tree before mapping anything (node-lib's `pool_to_target` plus the
   live-tree helpers, resolved on the storage host):
    - A target that exists in the live tree is used as constructed.
    - When every live pool target shares one IQN prefix that differs from the
      node config's, the config is the regressed side (typically a recovery
      install that rewrote it): `IQN_PREFIX` is converged onto the live prefix
      on BOTH hosts, with a timestamped `node.conf.bak-*` kept beside each
      conf.
    - A constructed target absent from the tree resolves to the single live
      target already carrying the pool's short name (IQN-prefix drift where
      convergence is not unambiguous); the by-path rewrite in step 9 follows
      the resolved target.
    - A pool whose short name no live target carries gets its target created
      with the `setup-iscsi-targets` recipe (authentication off, write-protect
      off, portal on the storage network, demo-mode ACLs only when the TPG
      carries no explicit ACLs).
    - Multiple live targets sharing a pool's short name abort the restore
      BEFORE any iSCSI mutation, naming every candidate.
   Backstores and LUNs are then created per restored zvol and
   `expected-backstores.txt` and `/etc/zfsutilities/iscsi-encrypted-luns.conf`
   updated; an unmapped pool aborts the restore.
8. Save iSCSI config via `safe-iscsi-save`.
9. Restore/rewrite the Proxmox config (written on the compute host —
   base64-shipped through `on_compute` when orchestrating elsewhere):
    - Single-node: rewrite VMID in disk lines if `--new-vmid` was used.
    - Two-node: rewrite disk lines with new target/LUN paths using `.disk_info`.
    - Regenerate `vmgenid` and `smbios1` UUIDs when `--new-vmid` is used.
10. On the compute host, discover the storage portal's current target set,
    log in to the targets this run mapped (freshly created targets become
    reachable this way; already-logged-in targets answer rc 15 and pass),
    then trigger the iSCSI rescan.

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
   below the optional `EXPECTED_ISCSI_DEVICES` minimum from the node config
   (no warning when it is unset).

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

**Called modules / commands:**

| Script | Purpose |
| ------ | ------- |
| [`export-iscsi-state`](#export-iscsi-state-storage-node) | Refresh the pool-resident LUN map after the save (best-effort; a failure never fails the save) |

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
9. Invoke [`export-iscsi-state`](#export-iscsi-state-storage-node) to refresh
   the pool-resident LUN map on every online pool. Best-effort: a warning is
   logged and the save still reports success if the export fails. Callers
   that own the refresh decision —
   [`reconcile-iscsi-state`](#reconcile-iscsi-state-storage-node) suppresses
   this hook with `SAFE_ISCSI_SAVE_SKIP_EXPORT_ISCSI_STATE=1` so a partial
   reconcile cannot overwrite the pool map.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Config saved successfully |
| `1`  | Missing files, degraded state, or save skipped |

Side effects: overwrites `saveconfig.json`; regenerates `saveconfig-boot.json`;
regenerates `expected-backstores.txt`; refreshes the pool-resident LUN map
(see [`export-iscsi-state`](#export-iscsi-state-storage-node)).

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
| [`reconcile-iscsi-state`](#reconcile-iscsi-state-storage-node) | Regenerates the manifest from the pool state map's ensured set |

Use `safe-iscsi-save` instead of `targetcli saveconfig` in any script that modifies
iSCSI config.

---

### `export-iscsi-state` (storage node)

Records the live iSCSI LUN topology as a pool-resident state map, so it
survives an OS-disk loss on the storage host. A bare-metal restore regresses
both `saveconfig.json` and `expected-backstores.txt` (they live on the OS
disk) while the pools re-import current — LUNs created after the backup point
vanish and the manifest cannot restore them. This script writes the
authoritative map (`iscsi-state.json`: per-target LUN → backstore,
per-backstore zvol device, ACL initiators) plus a copy of `node.conf` onto
every online pool at `<pool>/zfsutilities/`, so any surviving pool can serve
recovery. `safe-iscsi-save` invokes it after every successful save, keeping
the map as fresh as the last LUN change.

```bash
sudo export-iscsi-state [--check] [--force] [--print-map]
```

**Prerequisites:** `targetcli` (as for [`repair-iscsi-luns`](#repair-iscsi-luns-storage-node))
for every mode except `--print-map`; pools listed in the node config provide
the write targets. Pool-wide snapshot/retention policies (no explicit
includes) pick up the new `zfsutilities` dataset automatically and provide
the map's history.

**Arguments:**

| Argument | Description |
| -------- | ----------- |
| `--check` | Compare live state against the newest map found on any pool and report drift (manual `targetcli` edits since the last export); never writes |
| `--force` | Record the live state even when it is degraded (fewer active backstores than the manifest or the newest map expects) |
| `--print-map` | Print the newest pool-resident map to stdout, read-only — the fetch path [`repair-vm-disk-refs`](#repair-vm-disk-refs-compute-node) uses over ssh from the compute host; collects no live state and writes nothing |

**Globals:** node-config globals only.

**Called modules / commands:**

| Script | Purpose |
| ------ | ------- |
| `lib/iscsi-lib.sh` | Shared targetcli parsers (`parse_backstores`, `parse_target_luns`, `parse_target_acls`) |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `<pool>/zfsutilities/iscsi-state.json` | Written (atomically) on every online pool | [iSCSI pool-resident state map](../developer-guide/data-structures.md#iscsi-pool-resident-state-map) |
| `<pool>/zfsutilities/node.conf` | Copy of the active node config, written beside the map | [Node configuration file](../developer-guide/data-structures.md#node-configuration-file-etczfsutilitiesnodeconf) |
| `/etc/rtslib-fb-target/expected-backstores.txt` | Expected-backstore count for the degraded-state fence | [Expected-backstores manifest](../developer-guide/data-structures.md#iscsi-expected-backstores-manifest) |

**Internal flow / algorithm:**

1. Exit silently in single-node mode; refuse to run anywhere but the storage
   host.
2. `--print-map`: locate the newest map across online pools and dump it to
   stdout (pure JSON, no banner); exit 1 when no pool holds one. Nothing
   else runs — no live-state collection, no writes, no `targetcli`
   dependency.
3. Collect the live topology: per-target LUN mappings and ACL initiators for
   every pool in the node config, plus every VM backstore and its zvol device.
4. Render the state map as deterministic JSON (sections sorted; only the
   `generated` timestamp varies between runs).
5. `--check`: locate the newest map across online pools, compare it with the
   live state, print `DRIFT:` lines for moved LUNs, missing/extra backstores,
   ACL and node-identity changes; exit 1 on drift, 0 on match. Never writes.
6. Refuse to record a degraded live state (fewer active backstores than the
   manifest — or, without a manifest, than the newest pool map — expects)
   unless `--force` is given. This keeps a half-restored LIO tree from
   destroying the recovery authority.
7. For every pool in the node config: skip offline pools with a warning;
   create the `<pool>/zfsutilities` dataset on first use; atomically install
   `iscsi-state.json` and the `node.conf` copy (temp file + `mv` in the
   destination directory).
8. Fail when no pool received the map.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Map written to at least one pool, `--check` found no drift, or `--print-map` dumped the newest map |
| `1`  | Invalid option, not on the storage host, not root, degraded-state refusal, no pool writable, or (`--check`) drift detected, or (`--check`/`--print-map`) no map found |

Side effects: may create a `<pool>/zfsutilities` dataset per pool; writes
`iscsi-state.json` and `node.conf` on every online pool.

---

### `reconcile-iscsi-state` (storage node)

Rebuilds the iSCSI LUN topology from the pool-resident state map after a
storage-host bare-metal restore. A restore regresses `saveconfig.json` and
`expected-backstores.txt` together (both live on the OS disk) while the pools
re-import current, so [`repair-iscsi-luns`](#repair-iscsi-luns-storage-node) —
whose authority is the regressed manifest — cannot restore LUNs created after
the backup point. This script treats the pool map written by
[`export-iscsi-state`](#export-iscsi-state-storage-node) as the authority and
recreates the recorded topology: every map backstore whose zvol still exists
gets its backstore (`emulate_tpu=1`), its LUN at the recorded number, and its
ACL bindings; encrypted backstores are re-flagged in
`/etc/zfsutilities/iscsi-encrypted-luns.conf` so the boot-config flow stays
consistent. LIO config and the manifest are derived state, rebuilt from the
authorities.

```bash
sudo reconcile-iscsi-state [--dry-run] [--yes] [--from <file>]
```

**Prerequisites:** `targetcli` (as for
[`repair-iscsi-luns`](#repair-iscsi-luns-storage-node)); a pool-resident map
from `export-iscsi-state` on at least one online pool; iSCSI targets created
([`setup-iscsi-targets`](#setup-iscsi-targets-storage-node)) — a map entry on
a target that does not exist live is refused with a pointer to that script,
which itself detects the post-restore signature after target setup and
offers to run this script directly.

**Safety model:**

- Create-only — never deletes a live object and never remaps an existing LUN
  to a different number.
- Identity is the backstore/zvol name at the recorded LUN number, never the
  LUN number alone. Conflicts are refused per item with evidence and the run
  continues with the remaining items.
- Map entries whose zvol is gone (offline pool, deleted dataset) are skipped,
  and the pool map is left unchanged so the entry survives for when the zvol
  returns (a partial reconcile must never overwrite the recovery authority).

**Arguments:**

| Argument | Description |
| -------- | ----------- |
| `--dry-run` | Print the plan and the VM-config cross-check without making changes; exits 1 if identity conflicts exist |
| `--yes` | Apply without the interactive `y/N` confirmation |
| `--from <file>` | Reconcile from a specific map snapshot (e.g. a pool snapshot's copy) instead of the newest online map |

**Globals:** node-config globals only.

**Called modules / commands:**

| Script | Purpose |
| ------ | ------- |
| `lib/iscsi-lib.sh` | Shared parsers and `newest_iscsi_state_map` (newest-map discovery) |
| [`safe-iscsi-save`](#safe-iscsi-save-storage-node) | Persists the rebuilt tree; its post-save map hook is suppressed (`SAFE_ISCSI_SAVE_SKIP_EXPORT_ISCSI_STATE=1`) because reconcile owns the refresh decision |
| [`export-iscsi-state`](#export-iscsi-state-storage-node) | Refreshes the pool map after a complete reconcile |
| `list-vm-disks --gather-vm-info` over ssh | VM-config disk references (including efidisk) for the cross-check |
| [`rescan-storage`](#rescan-storage-both) | Makes recreated LUNs visible on the compute host |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `<pool>/zfsutilities/iscsi-state.json` | Recovery authority; newest copy across online pools (or `--from`) | [iSCSI pool-resident state map](../developer-guide/data-structures.md#iscsi-pool-resident-state-map) |
| `/etc/rtslib-fb-target/expected-backstores.txt` | Regenerated from the ensured set before the save (derived state) | [Expected-backstores manifest](../developer-guide/data-structures.md#iscsi-expected-backstores-manifest) |
| `/etc/zfsutilities/iscsi-encrypted-luns.conf` | Re-flagged for ensured backstores whose zvol is encrypted | [Encrypted-LUNs config](../developer-guide/data-structures.md#iscsi-encrypted-luns-config) |
| VM configs on the compute host | Read-only cross-check of `(target, LUN)` references (`/etc/pve/qemu-server/*.conf`, gathered via `list-vm-disks --gather-vm-info`) | — |

**Internal flow / algorithm:**

1. Exit silently in single-node mode; refuse to run anywhere but the storage
   host.
2. Resolve the map: `--from <file>`, else the newest `iscsi-state.json`
   across online pools. Refuse a map generated on a different host.
3. Parse the map (backstores, per-target LUNs, ACLs) and collect the live
   LIO topology for the map's targets (including each TPG's ACL mode).
4. Plan per map backstore whose zvol exists: create the backstore if missing
   (device must match the map), create the LUN at the recorded number when
   the slot is free, and note live objects the map does not know (left
   untouched). Refuse per item — never guess, never remap — when the backstore
   points at a different device, is mapped at a different (target, LUN), or
   the recorded slot is held by a different backstore, or the target is
   missing live. Skip (with a warning) when the zvol does not exist.
5. Recreate explicit-mode ACL initiators recorded in the map (with mapped
   LUNs); demo-mode TPGs are left alone — their ACL nodes self-generate on
   initiator login.
6. Show the evidence (actions, skips, refuses) and ask `y/N` before applying
   (`--yes` skips; `--dry-run` stops here after the cross-check).
7. Apply the plan, re-collect live state, re-flag encrypted backstores, and
   regenerate the manifest from the ensured set (so `safe-iscsi-save`'s
   degraded gate matches what reconcile actually ensured).
8. Run `safe-iscsi-save` (map hook suppressed), then refresh the pool map —
   but only when the reconcile is complete; otherwise the map is deliberately
   left unchanged and skipped/refused entries are preserved in it.
9. Cross-check compute-host VM disk references: refs whose `(target, LUN)`
   is in the map but still missing live are reported with the map identity
   and the item outcome; refs with no map entry are listed with candidate
   unexported zvols of the same VMID (informational — nothing is guessed).
10. Rescan the compute host and print the summary.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Topology reconciled (or already matching); VM references resolvable or informational |
| `1`  | Invalid option / wrong host / not root / no map found / map from another host; or identity conflicts, failed actions, a failed configuration save, or VM references that remain missing after the reconcile |

Skips alone (zvol gone) exit 0 with warnings; the pool map is preserved so
re-running after the pool returns completes the recovery.

Side effects: creates backstores/LUNs/ACLs in the live LIO tree; regenerates
`expected-backstores.txt`; appends re-flagged entries to
`iscsi-encrypted-luns.conf`; saves `saveconfig.json` (via `safe-iscsi-save`);
refreshes `iscsi-state.json` on every online pool after a complete reconcile;
triggers a compute-host rescan.

---

### `check-vm-disk-paths` (compute node)

The iSCSI VM-disk path fence: verifies that every VM-config disk reference
(including `efidisk`) has its iSCSI by-path device link on this host, and —
with `--recover` — repairs the missing ones unattended. After a storage-host
bare-metal restore, LUNs created after the backup point vanish from the
regressed LIO config while the pools and the VM configs here stay current;
Proxmox then aborts VM start on the missing
`/dev/disk/by-path/ip-<ip>:3260-iscsi-<iqn>:<target>-lun-<n>` link. This
script detects that state from the compute host and drives
[`reconcile-iscsi-state`](#reconcile-iscsi-state-storage-node) on the storage
host to rebuild it.

Normally invoked every 5 minutes by the `zfsutilities-iscsi-fence.timer`
systemd unit, which [switch-version](#switch-version-any-host) activation
installs and enables on two-node compute hosts (gated on `qm`'s presence and
the node config not declaring single-node mode; a hand-rolled health check
already on the host is left untouched). A healthy tick is entirely local —
no ssh — so the fence adds nothing to the storage host's journal. A failed
run (exit 1) means VM disk references are missing; check the unit's journal.

```bash
sudo check-vm-disk-paths [--recover]
```

**Arguments:**

| Argument | Description |
| -------- | ----------- |
| `--recover` | Attempt recovery when references are missing: a local iSCSI rescan first, then `reconcile-iscsi-state --yes` on the storage host (exactly one ssh), then a re-check |

**Globals:** node-config globals only.

**Called modules / commands:**

| Script | Purpose |
| ------ | ------- |
| `list-vm-disks --gather-vm-info` (local) | VM-config disk references, including efidisk |
| [`rescan-storage`](#rescan-storage-both) | Local recovery step: rescan running iSCSI sessions |
| `reconcile-iscsi-state --yes` over ssh | Storage-side rebuild; its own safety model applies unchanged (create-only, identity conflicts refused, never remapped) — conflicts remain report-only here |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| VM configs on this host | Read via `list-vm-disks --gather-vm-info` (`/etc/pve/qemu-server/*.conf`) | — |
| `/dev/disk/by-path/` | The expected `ip-<ip>:3260-iscsi-<iqn>:<target>-lun-<n>` links are checked for existence | — |

**Internal flow / algorithm:**

1. Exit silently in single-node mode; refuse to run anywhere but the compute
   host or without Proxmox VE (`qm`).
2. Gather the VM disk references locally and verify each expected by-path
   link. Missing references are reported one per line with the VM, disk key,
   target IQN, LUN, and expected link.
3. All present: print the one-line summary and exit 0 (no ssh was made).
4. Without `--recover`: report the count and exit 1.
5. With `--recover`: rescan locally first (`rescan-storage`); re-check and
   exit 0 when everything reappeared.
6. Still missing: run `reconcile-iscsi-state --yes` on the storage host over
   a single ssh (its output streams into this run's journal), re-check, and
   report. A non-zero reconcile (identity conflict, unreachable host) is a
   warning — the fence never retries, guesses, or remaps.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | All references present (initially, or after recovery); or no VM disk references exist |
| `1`  | Invalid option / wrong host / not root / gather failure; or references missing (without `--recover`), or still missing after recovery |

Side effects with `--recover`: an iSCSI session rescan; when references are
still missing afterwards, the storage-side reconcile (which itself saves the
rebuilt LIO tree, refreshes the pool state map, and rescans this host).

---

### `repair-vm-disk-refs` (compute node)

The compute-host half of bare-metal-restore recovery: re-points **regressed VM
config disk references** at the correct iSCSI LUNs by disk identity. When the
compute host is restored from an older backup, `/etc/pve` (and its VM
configs) regress while the storage host stays current — a restored config can
then reference a (target, LUN) slot that now holds a *different* VM's disk,
and Proxmox would attach the wrong disk silently. This script is the mirror
of [`reconcile-iscsi-state`](#reconcile-iscsi-state-storage-node): it never
maps by LUN number. Each reference is resolved through the storage host's
pool-resident state map (fetched read-only via
[`export-iscsi-state --print-map`](#export-iscsi-state-storage-node)) to the
backstore that slot held when the map was written; the live topology
(`list-vm-disks --gather-lun-info`) says where that backstore sits now. When
the two disagree, only the by-path volume portion of the disk line is
rewritten via `qm set <vmid> --<key> <new-by-path>,<options>` — every option
after the volume is preserved byte-for-byte.

```bash
sudo repair-vm-disk-refs [--dry-run] [--yes]
```

**Prerequisites:** Proxmox VE (`qm`) on this compute host; the storage host
reachable over ssh.

**Arguments:**

| Argument | Description |
| -------- | ----------- |
| `--dry-run` | Report the planned rewrites and refusals without editing any VM config (exit 1 when refusals exist) |
| `--yes` | Apply without the interactive confirmation |

**Globals:** node-config globals only.

**Called modules / commands:**

| Script | Purpose |
| ------ | ------- |
| `export-iscsi-state --print-map` over ssh | Read-only fetch of the newest pool-resident state map (the identity authority) |
| `list-vm-disks --gather-lun-info` over ssh | Read-only fetch of the live LUN topology (where each backstore sits now) |
| `qm set` | The only mutation: rewrites the planned disk lines (volume only, options preserved) |
| `qm status` | Running-VM gate per planned rewrite |
| [`rescan-storage`](#rescan-storage-both) | Post-apply verification: brings in rewritten references whose device is not present yet |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `/etc/pve/qemu-server/*.conf` | Read for disk references (including `efidisk`) and their option suffixes; rewritten only through `qm set` | — |
| `<pool>/zfsutilities/iscsi-state.json` | Identity bridge: config (target, LUN) → backstore at map time | [iSCSI pool-resident state map](../developer-guide/data-structures.md#iscsi-pool-resident-state-map) |
| Live LUN topology | Backstore → (target, LUN) right now | — |

**Internal flow / algorithm:**

1. Exit silently in single-node mode; refuse to run anywhere but the compute
   host or without Proxmox VE.
2. Gather every iSCSI disk reference from the VM configs on this host (no
   ssh). No references: done, exit 0.
3. Two ssh round trips to the storage host: the newest pool state map and
   the live LUN topology. A map generated on another host — or recording a
   different IQN prefix / storage IP than this site's node.conf — is refused
   outright.
4. Resolve each reference through the identity chain
   `config (target, LUN) → map backstore → live (target, LUN)`:
    - Refused, with evidence: no map entry for the reference (identity
      unknown); the backstore now belongs to a different VMID; two references
      resolving to one backstore (ambiguous); the backstore not exported live
      (run `reconcile-iscsi-state` on the storage host first); the VM running
      or its status unverifiable.
    - Reference already matching live state: reported, left alone.
    - Otherwise: planned rewrite.
5. Print the plan (old volume → new volume, with the backstore identity),
   the already-correct notes, and the refusals; `--dry-run` stops here.
6. After `y/N` confirmation (or `--yes`), apply each rewrite with
   `qm set`; only the volume portion changes.
7. Verify every rewritten reference resolves to a live device on this host;
   run `rescan-storage` first when one does not. A device still missing after
   the rescan is a FATAL — exactly the VM-start-abort state this repair
   exists to prevent.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | No iSCSI references found; or no rewrites needed and nothing refused; or every planned rewrite applied and verified with zero refusals |
| `1`  | Invalid option / wrong host / not root / fetch failures / bad map; or any refusal, `qm set` failure, or device still missing after the rescan |

Side effects: `qm set` rewrites of the planned VM config disk lines; an
iSCSI session rescan when a rewritten reference's device is not yet present.
VM configs are never edited directly, and nothing on the storage host is
modified.

---

### `setup-iscsi-targets` (storage node)

Creates iSCSI targets, TPGs, and portals from the pool-to-target mappings
defined in `/etc/zfsutilities/node.conf`. Idempotent — safe to run multiple
times. Skips targets that already exist and adds missing portals to existing
targets.

After target setup, runs the post-restore detection (`lib/iscsi-lib.sh`
detectors): on a bare-metal-restore signature it prints the evidence and
offers to run [`reconcile-iscsi-state`](#reconcile-iscsi-state-storage-node)
— the map-driven LUN rebuild — with the same verified-evidence + `y/N`
pattern as orphan-target deletion.

```bash
sudo setup-iscsi-targets
```

**Arguments:** none.

**Globals:** node-config globals only.

**Called modules / commands:**

| Script | Purpose |
| ------ | ------- |
| `node-lib.sh` | Two-node host/target resolution and the orphan usage probe (`probe_target_usage`) |
| `lib/iscsi-lib.sh` | Shared parsers plus the post-restore detectors (`detect_stale_lio_files`, `detect_manifest_without_zvols`, `detect_vm_refs_missing_live`) |
| `targetcli` | Create targets, TPGs, and portals |
| `ssh` → compute host | Usage probe and VM-reference gather (`list-vm-disks --gather-vm-info`, read-only) |
| [`reconcile-iscsi-state`](#reconcile-iscsi-state-storage-node) | Offered when a post-restore signature is detected (never invoked without confirmation) |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `/etc/zfsutilities/node.conf` | `POOL_TARGET` and `IQN_PREFIX` source | [Node config](../developer-guide/data-structures.md#node-configuration-file-etczfsutilitiesnodeconf) |
| `targetcli` iSCSI config | Targets, TPGs, and portals created or verified | — |
| `/etc/rtslib-fb-target/saveconfig.json`, `expected-backstores.txt` | Read by the post-restore detectors (mtime vs newest VM zvol; entries vs zvols) | [Expected-backstores manifest](../developer-guide/data-structures.md#iscsi-expected-backstores-manifest) |

**Internal flow / algorithm:**

1. Exit silently in single-node mode.
2. Verify the script is running on the storage host.
3. Ensure `targetcli` is installed.
4. For each entry in `pool_target`:
    - Before creating a missing target, detect orphan targets: live targets
      carrying the same short name under a different IQN prefix (drift from
      an earlier install — the default prefix is date-derived). Each orphan
      is probed for usage first (`probe_target_usage`: guest configs on the
      compute host and live sessions); one verified unused may be deleted
      after confirmation, while one in use — or unverifiable — is refused
      outright and blocks creation for this pool (the run exits 1).
    - Create the target IQN if it does not already exist.
    - Ensure TPG1 exists.
    - Disable authentication and demo-mode write protect.
    - Enable demo-mode ACLs (`generate_node_acls=1`) on TPGs that carry no
      explicit ACLs, so initiators can log in; the dedicated storage network
      is the isolation boundary. A TPG that already carries ACLs is never
      modified.
    - Create the portal `${storage_ip}:3260` if it does not already exist.
5. Save the targetcli configuration if anything changed.
6. Run the post-restore detection: (a) `saveconfig.json`/manifest older
   than the newest VM zvol, (b) compute-host VM disk references whose
   (target, LUN) is absent from the live tree, (c) manifest entries with no
   zvol. With findings, print the evidence and offer
   `reconcile-iscsi-state` (`y` runs it — it prints its own plan and asks
   again before applying; declining leaves the system untouched).

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Targets configured (and, when offered, the reconcile ran cleanly or was declined) |
| `1`  | Not running on the storage host, `targetcli` not found, or target creation skipped because an orphan target remains; or an accepted `reconcile-iscsi-state` run reported problems |

Side effects: creates or verifies iSCSI targets, TPGs, and portals; may run
`reconcile-iscsi-state` after explicit confirmation.

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
| `/etc/systemd/system/rtslib-fb-targetctl.service.d/` | Refreshed from the activated version's `share/two-node/` drop-ins (storage hosts only — gated on `targetctl`'s presence) |
| `/etc/systemd/system/zfsutilities-iscsi-fence.{service,timer}` | Installed/refreshed from the activated version's `share/two-node/` and the timer enabled (two-node compute hosts only — gated on `qm`'s presence and only skipped when a node config explicitly says single-node; a compute host with no node config yet, as on a fresh two-node install's activation step, still gets the fence; see [`check-vm-disk-paths`](#check-vm-disk-paths-compute-node)) |

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
    - Refresh the `rtslib-fb-targetctl` systemd drop-ins from the activated
      version's `share/two-node/` (storage hosts only), so a release carrying
      drop-in changes takes effect on activation without any manual step;
      reload the systemd daemon when a drop-in actually changed.
    - Install/enable the iSCSI VM-disk path fence units
      (`zfsutilities-iscsi-fence.service` + `.timer`) from the activated
      version's `share/two-node/` on two-node compute hosts, so the fence
      always matches the activated release; idempotent.
    - Stop any running documentation server on port 8000.

**Return codes / side effects:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Version switched, listed, or unwired |
| `1`  | Validation or filesystem error |

Side effects: repoints symlinks; writes/updates `profile.d`, `sudoers.d`, and
desktop shortcuts; on storage hosts, re-installs the `rtslib-fb-targetctl`
drop-ins when the activated version ships different ones; on two-node compute
hosts, installs and enables the `zfsutilities-iscsi-fence` units. New script
invocations immediately use the new version; already-running scripts are
unaffected.

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

Use [`sever-vm-clone`](#sever-vm-clone-both)
to sever the clone dependency before retiring the source VM.

See [VM Clone Provisioning](../user-guide/proxmox-integration.md#cloning-a-vm) for the full workflow.

---

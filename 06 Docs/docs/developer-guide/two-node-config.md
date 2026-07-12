# Node Configuration

## Overview

ZFSutilities supports two deployment modes:

- **Single-node** — All ZFS pools are local to the Proxmox host. No iSCSI,
  no separate storage server. Zvols are accessed directly via `/dev/zvol/...`.
- **Two-node** — A dedicated storage host exports zvols via iSCSI to a
  separate compute host running Proxmox VMs.

Both modes use the same scripts and the same config file format. The
`NODE_MODE` variable controls which code paths are active.

## Config File: `/etc/zfsutilities-node.conf`

A POSIX-shell sourceable file, installed by the interactive installers in
`10 Installers/`. Site admins can edit this file directly.

### Single-node example

```bash
# /etc/zfsutilities-node.conf
NODE_MODE="single-node"
THIS_HOST="myhost"
```

### Two-node example

```bash
# /etc/zfsutilities-node.conf
NODE_MODE="two-node"

STORAGE_HOST="stewie"
COMPUTE_HOST="tweety"

STORAGE_IP="192.168.100.1"

IQN_PREFIX="iqn.2026-02.local.stewie"

declare -A POOL_TARGET=(
    [threeamigos]="threeamigos"
    [NVME1]="nvme1"
)
```

The `IQN_PREFIX` value contains the literal host string because it is part of
the standards-based iSCSI target's persistent name — renaming the host does **not**
rename the target.

## Config File: `/etc/zfsutilities-deploy.conf`

A separate, optional configuration file used by [`deploy-version`](../commands-and-modules/two-node.md#deploy-version-repo-root) to determine which remote hosts receive a deployment.

**Why it exists:** The local node's configuration (e.g. a single-node test system or a developer workstation) may differ from the production deployment targets. Keeping deployment groups in their own file lets you deploy to `stewie` and `tweety` from a laptop that is neither.

**Format:**

```bash
# /etc/zfsutilities-deploy.conf
DEPLOY_GROUP_production="stewie tweety"
DEPLOY_GROUP_staging="staging-host"
```

Each `DEPLOY_GROUP_<name>` variable is a space-separated list of host short names. Pass the group name(s) to `deploy-version` to deploy only to those hosts:

```bash
sudo ./deploy-version 1.2.0 production
```

If no groups are specified, `deploy-version` deploys to all defined groups plus the local host.

**Legacy fallback:** If `/etc/zfsutilities-deploy.conf` does not exist, `deploy-version` falls back to the node configuration (`/etc/zfsutilities-node.conf` or `/etc/two-node.conf`) and deploys to `STORAGE_HOST` and `COMPUTE_HOST` when `NODE_MODE="two-node"`.

**Installation:** `install-two-node` generates this file from `10 Installers/deploy.conf.template`, substituting the hostnames you enter during setup. The installer **never overwrites** an existing file, so manual edits are safe across re-runs.

## Helper Library: `node-lib.sh`

Installed to `/usr/local/lib/node-lib.sh` on all hosts.

All scripts in `08 Two-node/` and `09 ZFS clone support/` begin with:

```bash
source /usr/local/lib/node-lib.sh
```

The library:

1. Sources `/etc/zfsutilities-node.conf`
2. In single-node mode: sets `STORAGE_HOST=COMPUTE_HOST=$THIS_HOST`,
   leaves iSCSI variables empty
3. Provides helper functions:

```bash
is_single_node()   # returns 0 if NODE_MODE == "single-node"
is_two_node()      # returns 0 if NODE_MODE == "two-node"
pool_to_target()   # echoes full IQN for a pool (two-node only)
pool_list()        # echoes pool names from POOL_TARGET (two-node only)
is_known_pool()    # returns 0 if pool is in POOL_TARGET (two-node only)
```

In single-node mode, `pool_to_target`, `pool_list`, and `is_known_pool`
return errors — scripts use `zpool list -H -o name` for pool validation
instead.

## Version Consistency

Both nodes in a two-node deployment should run the same ZFSutilities version.
The GTK GUI checks the peer node's version at startup by reading
`/usr/local/lib/zfsutilities/current/VERSION` via SSH as `root`. It logs an
INFO message when the versions match and a WARN message when they differ or
the peer cannot be reached. The check is asynchronous and does not block GUI
startup.

Use [`deploy-version`](../commands-and-modules/two-node.md#deploy-version-repo-root)
and [`switch-version`](../commands-and-modules/two-node.md#switch-version-any-host)
to keep the nodes in sync.

## How Scripts Use Mode

### SSH delegation pattern

Many scripts delegate to the other host as needed.

### iSCSI operations

iSCSI operations (targetcli, backstore, LUN, rescan) are wrapped in
`is_two_node` checks. In single-node mode, zvols are accessed directly
via `/dev/zvol/...` — no iSCSI layer:

```bash
if is_two_node; then
    TARGET=$(pool_to_target "$POOL") || exit 1
    targetcli /backstores/block create "$BSNAME" "$ZVOL_DEV"
    targetcli "/iscsi/${TARGET}/tpg1/luns" create "/backstores/block/${BSNAME}"
    safe-iscsi-save
    ssh root@"$COMPUTE_HOST" rescan-storage
fi
```

### Pool validation

```bash
# Two-node: validates against POOL_TARGET
if is_two_node; then
    is_known_pool "$POOL" || die "Unknown pool: $POOL ..."
fi

# Single-node: validates against live zpool list
if is_single_node; then
    zpool list -H -o name | grep -qx "$POOL" || die "Pool $POOL not found"
fi
```

### iSCSI-only scripts

Scripts that are entirely iSCSI-specific exit immediately in single-node
mode:

```bash
is_single_node && { echo "Not applicable in single-node mode."; exit 0; }
```

This applies to: [rescan-storage](../commands-and-modules/two-node.md#rescan-storage-both), [show-lun-map](../commands-and-modules/two-node.md#show-lun-map-compute-node), [safe-iscsi-save](../commands-and-modules/two-node.md#safe-iscsi-save-storage-node),
[restart-iscsi-services](../commands-and-modules/two-node.md#restart-iscsi-services-storage-node), [iscsi-add-encrypted-luns](../commands-and-modules/two-node.md#iscsi-add-encrypted-luns-storage-node),
[repair-iscsi-luns](../commands-and-modules/two-node.md#repair-iscsi-luns-storage-node).

## Repo-Root Scripts

If [zfsdelfs](../commands-and-modules/commands.md#zfsdelfs), [zfsdailybackup](../commands-and-modules/commands.md#zfsdailybackup), and `rsync-dailybackup` run from the
ZFSutilities project tree (not from the versioned installation PATH), they source
the config directly instead of using the library. Running from the repo-root is supported only in a development environment.

```bash
NODE_CONF="/etc/zfsutilities-node.conf"
if [[ ! -r "$NODE_CONF" ]]; then
    echo "✗ Missing $NODE_CONF — install via: 10 Installers/install-single-node" >&2
    exit 1
fi
source "$NODE_CONF"
if [[ "$NODE_MODE" == "single-node" ]]; then
    STORAGE_HOST="${THIS_HOST:-$(hostname -s)}"
    COMPUTE_HOST="$STORAGE_HOST"
fi
```

### Cross-host conf delivery for `rsync-dailybackup`

`rsync-dailybackup` gets `scp`'d to remote hosts and runs there. The
config must be present on every host that runs the script:

| Host              | How the config arrives                                                                                                               |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| Storage host      | `10 Installers/install-single-node` or `install-two-node`                                                                            |
| Compute host      | `install-two-node` SSHes in and installs the config                                                                                  |
| Other rsync hosts | [zfsdailybackup](../commands-and-modules/commands.md#zfsdailybackup)'s `push_rsync_scripts()` `scp`s the config alongside the script |

## Installers

### `10 Installers/install-single-node`

Interactive installer for single-node mode:

1. Installs MkDocs (for documentation editing)
2. Prompts for hostname (default: `$(hostname -s)`)
3. Generates `/etc/zfsutilities-node.conf`
4. Installs `node-lib.sh` and compatibility symlink locally
5. Deploys VM disk management and clone scripts to the versioned installation
6. Does NOT install iSCSI-only scripts or systemd drop-ins

### `10 Installers/install-two-node`

Interactive installer for two-node mode:

1. Installs MkDocs (for documentation editing)
2. Prompts for storage host, compute host, storage IP, IQN prefix,
   and pool-to-target mappings (auto-detects online pools)
3. Generates `/etc/zfsutilities-node.conf`
4. Installs scripts on both hosts via SSH
5. Installs systemd drop-ins, `zfs-keys-unlock.service`, and the encrypted
   LUNs config
6. Optionally creates `/root/.luks-key` for unattended LUKS unlocking
7. Verifies SSH key authorization between hosts
8. If PVE is present on the compute host, patches
   `/usr/share/perl5/PVE/Storage/ISCSIPlugin.pm` to limit automatic iSCSI
   rescans to once per day (eliminates kernel log spam on the storage host)

See [ZFS Key Handling](../installation/zfs-keys.md) for the full key-handling
workflow.

### Mode switching

Either installer detects an existing config and handles mode switching:

- **Single to two-node**: `install-two-node` detects `NODE_MODE=single-node`
  and prompts for the additional two-node settings.
- **Two to single-node**: `install-single-node` detects `NODE_MODE=two-node`,
  warns that iSCSI scripts remain installed but operations will be skipped,
  and rewrites the config.

Both installers assume that ZFS pools are already installed and active on the single node (for single-node mode) and on the storage node (for two-node mode). When switching modes, please move the storage beforehand. 

## systemd Drop-ins

Two-node mode installs three systemd drop-ins for
`rtslib-fb-targetctl.service` under
`/etc/systemd/system/rtslib-fb-targetctl.service.d/`:

### `boot-config.conf`

Restores from `saveconfig-boot.json` (encrypted backstores excluded) instead
of the full `saveconfig.json`. Without this, `targetctl restore` would fail
at boot when encrypted zvol device nodes don't exist yet.

If `saveconfig-boot.json` doesn't exist yet, falls back to the default
`saveconfig.json`.

### `pre-start-backup.conf`

Backs up `saveconfig.json` to `saveconfig.json.pre-start` before each
restore. If something later saves a degraded config, the last-known-good
copy is always available.

### `wait-for-zfs-keys.conf`

Ensures `zfs-keys-unlock.service` completes before the iSCSI target starts,
and runs [iscsi-add-encrypted-luns](../commands-and-modules/two-node.md#iscsi-add-encrypted-luns-storage-node) as an `ExecStartPost` to re-add encrypted
LUNs after keys are loaded.

If the ZFS keys USB is not present or `/root/.luks-key` does not exist,
`zfs-keys-unlock.service` exits cleanly and iSCSI starts without the encrypted
LUNs. See [ZFS Key Handling](../installation/zfs-keys.md) for recovery.

## Script-by-Script Mode Behavior

| Script                                                                              | Single-node                        | Two-node                                       |
| ----------------------------------------------------------------------------------- | ---------------------------------- | ---------------------------------------------- |
| [new-vm-disk](../commands-and-modules/two-node.md#new-vm-disk-both)                 | Creates zvol only                  | Creates zvol + iSCSI backstore/LUN + rescan    |
| [remove-vm-disk](../commands-and-modules/two-node.md#remove-vm-disk-both)           | Destroys zvol only                 | Removes LUN/backstore + destroys zvol + rescan |
| [resize-vm-disk](../commands-and-modules/two-node.md#resize-vm-disk-both)           | Grows zvol only                    | Grows zvol + rescan                            |
| [list-vm-disks](../commands-and-modules/two-node.md#list-vm-disks-both)             | Lists zvols from all pools         | Lists iSCSI LUN mappings                       |
| [clone-vm](../commands-and-modules/two-node.md#clone-vm-both)                       | Local `zfs send/receive`           | SSH delegation + iSCSI LUN setup               |
| [zfsclone-vm](../commands-and-modules/two-node.md#zfsclone-vm-both)                 | Local ZFS snapshot + clone         | SSH delegation + iSCSI LUN setup               |
| [promote-vm-clone](../commands-and-modules/two-node.md#promote-vm-clone-both)       | Local `zfs promote`                | SSH delegation to storage host                 |
| [rescan-storage](../commands-and-modules/two-node.md#rescan-storage-both)           | N/A (exits)                        | Rescans iSCSI sessions                         |
| [show-lun-map](../commands-and-modules/two-node.md#show-lun-map-compute-node)       | N/A (exits)                        | Shows LUN-to-device mapping                    |
| [safe-iscsi-save](../commands-and-modules/two-node.md#safe-iscsi-save-storage-node) | N/A (exits)                        | Saves targetcli config with safety check       |
| [zfsdailybackup](../commands-and-modules/commands.md#zfsdailybackup)                | Skips compute-host pull            | Full cross-host backup                         |
| [zfsdelfs](../commands-and-modules/commands.md#zfsdelfs)                            | Skips iSCSI teardown/rebuild       | Full iSCSI lifecycle management                |
| `rsync-dailybackup`                                                                 | Local rsync or SSH to storage host | Same                                           |

## Variable Reference

### Single-node variables

| Variable       | Source  | Description                        |
| -------------- | ------- | ---------------------------------- |
| `NODE_MODE`    | Config  | Always `"single-node"`             |
| `THIS_HOST`    | Config  | Short hostname (`hostname -s`)     |
| `STORAGE_HOST` | Derived | Set to `$THIS_HOST` by lib/scripts |
| `COMPUTE_HOST` | Derived | Set to `$THIS_HOST` by lib/scripts |

### Two-node variables

| Variable       | Source | Description                                       |
| -------------- | ------ | ------------------------------------------------- |
| `NODE_MODE`    | Config | Always `"two-node"`                               |
| `STORAGE_HOST` | Config | Storage host short name                           |
| `COMPUTE_HOST` | Config | Compute host short name                           |
| `STORAGE_IP`   | Config | iSCSI portal IP                                   |
| `IQN_PREFIX`   | Config | iSCSI IQN prefix                                  |
| `POOL_TARGET`  | Config | Associative array: pool name -> target short name |

## Notable Design Decisions

- **Variable names describe roles, not hostnames.** `STORAGE_HOST` and
  `COMPUTE_HOST` remain correct after a host rename — only the config
  file values change.
- **[zfsdailybackup](../commands-and-modules/commands.md#zfsdailybackup) override flags** (`pull_tweety`, `pull_stewie`) retain
  their literal-hostname names because they are part of the user-facing
  override interface (`./zfsdailybackup "pull_tweety='N'"`). This script is intended to be lightly modified to meet your specific needs.
- **iSCSI target discovery at runtime.** The `09 ZFS clone support/` scripts
  query `targetcli` to find the current target for a given LUN rather than
  building the IQN from config. This survives any IQN rename.

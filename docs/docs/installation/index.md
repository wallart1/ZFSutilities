# Installation

ZFSutilities supports two deployment modes:

- **Single-node** — All ZFS pools are local to this host. No iSCSI, no
  separate storage server. Proxmox VE is optional; it is only needed if you
  want VM disk lifecycle management. This is the default for new installations.
- **Two-node** — A dedicated storage host exports zvols via iSCSI to a
  separate compute host running Proxmox VE VMs. The storage host does not need
  Proxmox VE.

For an overview of all documentation sections, return to the
[ZFS Utilities home page](../index.md).

## Capabilities by Deployment Mode

The table below summarizes what works where, before you choose between the
modes described above. The columns mirror the deployment situations this
guide uses throughout: the two single-node variants (Proxmox VE installed
or not) and the two two-node host roles. An em-dash (—) means the
capability does not apply in that situation. Two rules of thumb underlie
every row:

- **Core backup features follow the pools** — they run wherever the ZFS
  pools live: a single-node host or the two-node storage host.
- **VM disk and iSCSI features follow the VMs** — VM disk lifecycle
  requires Proxmox VE on the host running the VMs, and iSCSI tooling
  exists only in two-node mode.

| Capability                                                                              | Single-node (no Proxmox VE) | Single-node (with Proxmox VE) | Two-node storage host | Two-node compute host |
| --------------------------------------------------------------------------------------- | --------------------------- | ----------------------------- | --------------------- | --------------------- |
| [Snapshots and retention policies](../user-guide/retention.md)                          | Yes                         | Yes                           | Yes                   | —                     |
| [Daily backup](../user-guide/daily-backup.md)                                           | Yes                         | Yes                           | Yes                   | —                     |
| [Offsite backup and rotation](../user-guide/offsite-backup.md)                          | Yes                         | Yes                           | Yes                   | —                     |
| [Restore](../user-guide/restore.md)                                                     | Yes                         | Yes                           | Yes                   | —                     |
| Pool creation, health, and scrubbing                                                    | Yes                         | Yes                           | Yes                   | —                     |
| [GTK GUI](../user-guide/gtk-gui.md), documentation viewer, profiles, and scheduling     | Yes                         | Yes                           | Yes                   | Yes                   |
| [VM disk lifecycle](../user-guide/proxmox-integration.md)                               | —                           | Yes                           | Yes                   | Yes                   |
| VM archive and unarchive ([archive-vm](../commands-and-modules/commands.md#archive-vm)) | —                           | Yes                           | Yes                   | Yes                   |
| iSCSI target setup and LUN export/repair                                                | —                           | —                             | Yes                   | —                     |
| [Encrypted LUN workflow](zfs-keys.md)                                                   | —                           | —                             | Yes                   | —                     |
| iSCSI LUN mapping and initiator-side repair                                             | —                           | —                             | —                     | Yes                   |

On the two-node compute host the GUI is installed and runs, but the
ZFSutilities-managed pools are on the storage host, so its day-to-day role
there is the Dashboard — which in two-node mode adds the
[iSCSI issues panel](../commands-and-modules/two-node.md#dashboard-iscsi-issues-two-node-gui)
— and log browsing. The VM lifecycle scripts marked *both* in the
[two-node reference](../commands-and-modules/two-node.md) run on either
host and delegate over SSH as appropriate.

The Proxmox VE requirements behind these columns are detailed under
[Prerequisites](#prerequisites) below.

## Prerequisites

### Required

- **Debian-based Linux** (e.g., Linux Mint, Ubuntu, Proxmox VE)

- **ZFS pools already created** (`zpool create`) — or create one afterward
  from the GUI's Disks page wizard (storage host)

- **Root access**

- **Python 3** (for the GTK GUI)

- **WebKit2** — `apt install gir1.2-webkit2-4.1 libwebkit2gtk-4.1-0` (required
     for the embedded documentation viewer)

!!! warning "ZFS root filesystem not tested"
    ZFS Utilities has **not been tested** on systems where the Linux root filesystem
    (`/`) is stored on a ZFS dataset (root-on-ZFS). Pool operations, snapshot
    retention, and iSCSI lifecycle scripts may interact with the root pool in
    unexpected ways. Proceed at your own risk.

!!! note "ZFS bookmarks"
    ZFSutilities never creates, destroys, sends, or makes decisions from ZFS
    bookmarks — they are tolerated but never acted upon. Bookmarks present in
    backup or destination pools are **untested** — ZFSutilities never replicates
    bookmarks, so any found there were created by other tooling.

### OpenZFS Version Requirements

An OpenZFS
2.1 baseline is assumed: core backups, snapshots, retention, restores, and
the read-only views work on any 2.1-or-newer installation. Operations that
need newer OpenZFS features are individually gated — before the GUI offers
or starts one, it checks the running version and refuses with a WARN when
the feature is not available. Nothing runs half-supported: an action either
passes its gate or is aborted up front.

The gates read `zfs version`, which prints two versions — the userland
tools (`zfs-2.2.2`) and the loaded kernel module (`zfs-kmod-2.2.2`). Every
feature decision uses the **kernel-module** version, because that is the
code that actually implements the feature. The two can differ after a
partial upgrade (new tools with an old module, or the reverse);
ZFSutilities warns when they don't match. Patch levels matter — the
minimums below are exact `major.minor.patch` versions:

| Capability             | Minimum OpenZFS | What it gates                                                                                                                                                                                                                               |
| ---------------------- | --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `draid`                | 2.1             | dRAID vdev topologies — reserved (no gated action yet)                                                                                                                                                                                      |
| `json_output`          | 2.3             | JSON output from `zfs`/`zpool` commands — reserved                                                                                                                                                                                          |
| `zfs_rewrite`          | 2.3.4           | Datasets page **Rewrite Data** action — `zfs rewrite -P` rewrites a filesystem's existing blocks in place so changed properties (compression, `recordsize`) apply to already-written data, without a full copy. Shipped in 2.3.4, not 2.3.0 |
| `raidz_expansion`      | 2.3             | RAID-Z expansion in the pool-growth dialogs — attaching disks to an existing raidz group; unsupported raidz rows grey out with the required version                                                                                         |
| `fast_dedup`           | 2.3             | the fast dedup implementation — reserved                                                                                                                                                                                                    |
| `direct_io`            | 2.3             | direct I/O on zvols — reserved                                                                                                                                                                                                              |
| `ssb_on_zvols`         | 2.4             | `special_small_blocks` on volumes — reserved                                                                                                                                                                                                |
| `ssb_non_power_of_two` | 2.4             | `special_small_blocks` with non-power-of-two recordsize values — reserved                                                                                                                                                                   |

Keys marked *reserved* are recognized by the capability layer so there is
one authoritative minimum per feature, but no ZFSutilities action is gated
on them yet — today only **Rewrite Data** (`zfs_rewrite`) and RAID-Z
expansion (`raidz_expansion`) enforce their gates.

A version gate is necessary but not always sufficient. Features that change
on-disk state also need the pool itself to carry the matching feature flag.
**Rewrite Data** additionally checks the pool's `physical_rewrite` flag and
tells you how to enable it
(`zpool set feature@physical_rewrite=enabled <pool>`). This covers the case
where the kernel module is new enough but a particular pool — created
earlier, or constrained by a pool compatibility setting — does not have the
feature enabled (`zpool get feature@physical_rewrite <pool>` shows its
state).

To see what you are running:

```bash
zfs version
```

The GUI's Performance tab also shows the detected kernel-module version
next to the ARC header. The module-level reference is
[`zfs_capabilities.py`](../commands-and-modules/python-modules.md#zfs_capabilitiespy).

### Proxmox VE (optional on single node and storage node)

Proxmox VE is **required** on a two-node compute host and on a single-node host
that runs VMs. It is **optional** on a single-node host that only needs ZFS
backup, snapshot, and retention features and on a two-node storage host.

- **Single node without VMs/iSCSI**: Proxmox VE is not required.
- **Compute node or single node with VMs**: Proxmox VE 8.x or 9.x is required
  for VM disk lifecycle integration.
- **Two-node storage node**: Proxmox VE is not required. The storage host is a
  plain Debian-based ZFS/iSCSI server.

!!! warning "Non-Proxmox hypervisors are unsupported"
    ZFSutilities VM disk lifecycle scripts are tightly coupled to Proxmox VE
    (`qm`, `/etc/pve/qemu-server/`, PVE config formats). Running these scripts
    against other hypervisors is unsupported and may damage VM configurations and data.

### GUI Desktop Environment

The GTK GUI requires a **GTK3-capable desktop environment or window manager**
with X11 or Wayland. Cinnamon is the tested and reference environment, but
GNOME, XFCE, and others may also work.

### Two-node Additional Prerequisites

For two-node mode, root SSH key trust must be established **in both
directions** between the storage host and compute host **before** running
the installer. The installer will verify this and fail early if either
direction is not working.

On the **storage host**:

```bash
ssh-copy-id root@<compute-host>
```

On the **compute host**:

```bash
ssh-copy-id root@<storage-host>
```

The storage and compute hosts also need a **high-speed IP network connection**
between them. VM disk traffic and runs over
this link, so its bandwidth and latency directly affect VM performance.
How to provide that connection (dedicated NICs, VLAN, bonded
links, etc.) is outside the scope of ZFSutilities.

The installer will also check for and offer to install the following iSCSI
packages if they are missing:

- **Storage host:** `targetcli-fb` (provides `targetcli` and the
  `rtslib-fb-targetctl` systemd service)
- **Compute host:** `open-iscsi` (provides the `iscsiadm` initiator tool and
  the socket-activated `iscsid` daemon)

## Quick Start

### Single-node (recommended for new installs)

```bash
sudo /path/to/zfsutilities-repo/bin/install-single-node
```

The installer will:

1. Check that required single-node prerequisites are present
2. Explain any missing prerequisites and offer to install them automatically
3. Install the documentation server (MkDocs) and explain what it provides
4. Prompt for your hostname (default: current hostname)
5. Generate the installation configuration file `/etc/zfsutilities/node.conf`
   (legacy `/etc/zfsutilities-node.conf` also works)
6. Deploy scripts as a **versioned installation** to `/usr/local/lib/zfsutilities/versions/<version>/`
7. Activate the version and wire it into active production:
    - Configure `PATH` in `/etc/profile.d` and `/etc/sudoers.d`
    - Create the `/root/bashinit` symlink
    - Create the `/usr/local/lib/zfsutilities/bin` symlink and library symlinks
    - Create links for the GUI and standalone documentation viewer in the installing user's
      home directory:
      **ZFSutilities GUI** and **ZFSutilities Documentation**

### Two-node

Run on the **storage host** (the machine with the ZFS pools):

```bash
sudo /path/to/zfsutilities-repo/bin/install-two-node
```

The installer will:

1. Check that required two-node prerequisites are present
2. Explain any missing prerequisites and offer to install them automatically
3. Install the documentation server (MkDocs)
4. Verify/offer to install the iSCSI target stack (`targetcli-fb`) on the
   storage host and the iSCSI initiator (`open-iscsi`) on the compute host
5. Prompt for storage host, compute host, storage network IP, iSCSI IQN
   prefix, and pool-to-target mappings
6. Generate the installation configuration file `/etc/zfsutilities/node.conf`
   (legacy `/etc/zfsutilities-node.conf` also works)
7. **Add iSCSI targets** on the storage host
8. Deploy scripts as a **versioned installation** on both hosts via SSH
9. Activate the version on both hosts and wire it into active production:
    - Configure `PATH` in `/etc/profile.d` and `/etc/sudoers.d`
    - Create the `/root/bashinit` symlink
    - Create the `/usr/local/lib/zfsutilities/bin` symlink and library symlinks
    - Create links in the installing user's home directory:
      **ZFSutilities GUI** and **ZFSutilities Documentation**
10. Verify SSH key authorization between hosts
11. **Patch PVE's iSCSI rescan rate limit** on the compute host when PVE is
    detected — limits automatic `iscsiadm --rescan` to once per day, which
    eliminates repetitive kernel log spam on the storage host. If PVE is not
    detected, the installer prints a reminder that Proxmox VE is required on
    the compute host but does not fail.

The installer asks for an **iSCSI Qualified Name (IQN) prefix** when
configuring pool-to-target mappings. This becomes part of every iSCSI target's
persistent on-disk name and is baked in when the LUN is first created. Changing
it later requires recreating Proxmox iSCSI storage entries and re-mapping LUNs,
so accept the generated default unless your site already uses a registered
naming convention. See [Two-node configuration](../developer-guide/two-node-config.md)
for details.

See [Next Steps](#next-steps) for what to do after installation.

## How to Upgrade

1. **Acquire the new version.** Download or clone the release you want to
   install into a fresh directory (do not reuse an old directory that may have
   local changes):

   ```bash
   git clone https://github.com/wallart1/ZFSutilities.git \<target-directory\>
   cd \<target-directory\>
   ```

2. **Deploy it** with [deploy-version](../commands-and-modules/two-node.md#deploy-version-repo-root)
   from that directory. This copies the repository into a new version directory without touching the
   running system:

   ```bash
   sudo ./bin/deploy-version
   sudo switch-version --list
   sudo switch-version \<version\>
   ```

- [deploy-version](../commands-and-modules/two-node.md#deploy-version-repo-root) copies the current
  repo state into a new version directory without touching active production
- [switch-version](../commands-and-modules/two-node.md#switch-version-any-host) wires a deployed
  version into active production by updating the `current` symlink, refreshing `PATH` configuration,
  library symlinks, and desktop shortcuts
  + Roll back instantly: `sudo switch-version previous`
  + List deployed versions: `sudo switch-version --list`
  + Remove a version's wiring: `sudo switch-version --uninstall`

The versioned deployment model is described in the
[Architecture](../developer-guide/architecture.md) page.

## Switching Modes

To switch from single-node to two-node, run `install-two-node`. It detects
the existing single-node config and prompts for the additional two-node
settings.

To switch from two-node to single-node, run `install-single-node`. It
rewrites the config for single-node mode. iSCSI scripts remain installed
but their operations are skipped.

The install scripts assume that storage devices and ZFS pools are *already active* on the new system
configuration. The install scripts themselves do not assist with this. After installation, the GUI's
Disks page wizard can create pools from unused disks on the storage host.

Run the install scripts at the node which has the storage pools.

## Uninstalling ZFSutilities

A dedicated `uninstall-zfsutilities` script is installed alongside the other
tools. Run it as `root` to remove the software from the current host:

```bash
sudo uninstall-zfsutilities
```

The script is interactive: it shows what is installed, explains the available
choices, and asks what you want to remove.

### Default uninstall

Removes the deployed software and production wiring:

- Versioned deployment under `/usr/local/lib/zfsutilities/`
- `/root/bashinit`, `/usr/local/lib/node-lib.sh`, and related symlinks
- `/etc/profile.d/zfsutilities.sh` and `/etc/sudoers.d/zfsutilities`
- Desktop shortcuts (`ZFSutilities GUI`, `ZFSutilities Documentation`)
- `/etc/cron.d/zfsutilities`
- systemd service/drop-in files installed by ZFSutilities

Your downloaded repository directories, configuration, logs, and history are preserved.

### Purge mode

Add `--purge` to also remove user data and system-integration remnants:

```bash
sudo uninstall-zfsutilities --purge
```

This also removes:

- `/etc/zfsutilities/node.conf`, `/etc/zfsutilities/two-node.conf`, and `/etc/zfsutilities/deploy.conf`
- `/etc/zfsutilities/iscsi-encrypted-luns.conf`
- `/var/lib/zfsutilities/config.json`, `/var/lib/zfsutilities/history.json`,
  `/var/lib/zfsutilities/profiles/`, `/var/lib/zfsutilities/scrub_state.json`,
  `/var/lib/zfsutilities/nextsnap`, and `/var/lib/zfsutilities/nextsnap_offsite`
- `/root/.cache/zfsutilities/`
- `/var/log/zfsutilities/` (session logs, cron log, rsync-backup log)
- Scripts, service, and logs from `share/cache-warm/`

### Two-node deployments

Run the uninstall on the storage host. To clean up the compute host as well,
add `--all-nodes`:

```bash
sudo uninstall-zfsutilities --purge --all-nodes
```

The script reads `/etc/zfsutilities/node.conf` (falling back to the legacy `/etc/zfsutilities-node.conf`), determines the peer host, and
runs the same uninstall command on it via SSH. If the peer is unreachable, the
local uninstall continues and a warning is printed so you can rerun with
`--all-nodes` later.

### Non-interactive and dry-run use

- `--yes` / `-y` — skip all confirmation prompts
- `--dry-run` — print every action without modifying the system

```bash
sudo uninstall-zfsutilities --purge --yes
sudo uninstall-zfsutilities --purge --dry-run
```

### What is not removed

The uninstaller intentionally does **not** touch:

- ZFS pools, datasets, snapshots, or iSCSI targets/LUNs
- The Proxmox iSCSI rescan-rate patch on the compute host
  (`/usr/share/perl5/PVE/Storage/ISCSIPlugin.pm`)
- Packages that may be used by other software (e.g., MkDocs, mkdocs-material)
- A pre-existing `/root/bashinit.bak`

### Restartability and installer integration

The uninstall script is idempotent: if a previous run was interrupted, you can
rerun it safely. The install scripts (`install-single-node` and
`install-two-node`) detect remnants of a partial uninstall and offer to run
`uninstall-zfsutilities` first.

## Configuration Files

ZFSutilities uses two configuration files with different purposes.
The node configuration is not versioned; the runtime configuration
contains an internal schema version. Both files persist across version switches.

### Node Configuration (`/etc/zfsutilities/node.conf`)

System-wide settings generated by the installer. Contains node mode
(`single-node` or `two-node`), hostnames, storage-network IP, iSCSI IQN
prefix, and pool-to-target mappings. The legacy path `/etc/zfsutilities-node.conf`
is still recognized as a fallback.
See [Two-Node Configuration](../developer-guide/two-node-config.md) for
the full reference.

### Runtime Configuration (`/var/lib/zfsutilities/config.json`)

A shared JSON config read by both the GTK GUI and the bash scripts.
Contains the pool registry, retention policies, backup/offsite/restore
steps, checkagainst mappings, and GUI settings. It is created and
maintained by the application; the installer scripts do not populate it.

The file includes a `config_version` field that tracks the schema of the
JSON config independently of the software release version. When the
config structure changes, the GUI migrates the file automatically on
first access.

## What Gets Installed

### Versioned Scripts

Scripts are installed under `/usr/local/lib/zfsutilities/versions/<version>/`
and activated via symlink:

| Location                                              | Contents                                |
| ----------------------------------------------------- | --------------------------------------- |
| `/usr/local/lib/zfsutilities/versions/<version>/bin/` | All executable scripts                  |
| `/usr/local/lib/zfsutilities/versions/<version>/lib/` | `node-lib.sh`, `two-node-lib.sh`        |
| `/usr/local/lib/zfsutilities/versions/<version>/`     | Full project (docs, GUI, subdirs)       |
| `/usr/local/lib/zfsutilities/current`                 | Symlink → active version                |
| `/usr/local/lib/zfsutilities/bin`                     | Symlink → `current/bin/` (in `PATH`)    |
| `/usr/local/lib/zfsutilities/current/bin/zfsutilities-gui` | Symlink → `../python/zfsutilities_gui.py` |
| `/usr/local/lib/zfsutilities/current/bin/zfsutilities-docs` | Symlink → `../python/docs_viewer.py` |
| `/usr/local/lib/node-lib.sh`                          | Symlink → `.../current/lib/node-lib.sh` |
| `/usr/local/lib/rootcheck`                            | Symlink → `.../current/bin/rootcheck`   |

### Install Configuration

| Location                         | Contents                              |
| -------------------------------- | ------------------------------------- |
| `/etc/zfsutilities/node.conf`    | Node configuration                    |
| `/usr/local/lib/two-node-lib.sh` | Compatibility symlink → `node-lib.sh` |

### Two-node only (storage host)

| Location                                             | Contents                               |
| ---------------------------------------------------- | -------------------------------------- |
| `/etc/systemd/system/rtslib-fb-targetctl.service.d/` | systemd drop-ins for boot config       |
| `/etc/zfsutilities/iscsi-encrypted-luns.conf`        | Encrypted LUN registry (if applicable) |

See [ZFS Key Handling](zfs-keys.md) for the manual encrypted-zvol workflow.

### Two-node only (compute host)

| Location                      | Contents                  |
| ----------------------------- | ------------------------- |
| `/etc/zfsutilities/node.conf` | Node configuration (copy) |

## Editing Documentation

MkDocs and the Material theme are **required** for a complete installation.
The installer installs them automatically; they are used to build the static
`site/` directory consumed by the GUI documentation viewer and to run the live
documentation server.

With MkDocs installed, `mkdocs serve` will auto-rebuild the site when you
edit `.md` files.

## Invoking Scripts and the GUI

All scripts are available via `PATH` through `/usr/local/lib/zfsutilities/bin`
and can be run from any directory:

```bash
sudo move-vm-disk 100 scsi1 200
sudo switch-version --list
sudo new-vm-disk threeamigos 300 0 50G
```

The GTK GUI and standalone documentation viewer are also on `PATH` after
installation:

```bash
sudo zfsutilities-gui
zfsutilities-docs
```

The installer creates links in the installing user's home directory:

- **ZFSutilities GUI** → `/usr/local/lib/zfsutilities/current/bin/zfsutilities-gui`
- **ZFSutilities Documentation** → `/usr/local/lib/zfsutilities/current/bin/zfsutilities-docs`

You can run these links directly, add them to a panel or start menu, or
invoke the underlying Python scripts from a checkout during development:

```bash
sudo python3 '/path/to/zfsutilities-repo/python/zfsutilities_gui.py'
sudo python3 '/path/to/zfsutilities-repo/python/docs_viewer.py'
```

## Next Steps

After installation:

- **Single-node**:
  - Read [Concepts and Terminology](../user-guide/concepts.md) for the snapshot,
    retention, and backup-chain vocabulary used throughout this documentation.
  - Configure the [GTK GUI](../user-guide/gtk-gui.md) for backup and retention management.
  - Browse the [Commands & Modules Reference](../commands-and-modules/index.md) for the
    command-line side of every script.
- **Two-node**:
  - If you have encrypted zvols, read [ZFS Key Handling](zfs-keys.md) for the manual workflow.
  - Run [safe-iscsi-save](../commands-and-modules/two-node.md#safe-iscsi-save-storage-node) to generate the boot config.
  - See [Proxmox Integration](../user-guide/proxmox-integration.md).
- Configure the [GTK GUI](../user-guide/gtk-gui.md) for backup and
  retention management

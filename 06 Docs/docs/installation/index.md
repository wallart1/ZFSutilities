# Installation

ZFSutilities supports two deployment modes:

- **Single-node** — All ZFS pools are local to the Proxmox host. No iSCSI,
  no separate storage server. This is the default for new installations.
- **Two-node** — A dedicated storage host exports zvols via iSCSI to a
  separate compute host running Proxmox VMs.

## Prerequisites

### Required

- **Debian-based Linux** (e.g., Linux Mint, Ubuntu, Proxmox VE)

- **ZFS pools already created** (`zpool create`)

- **Root access**

- **Python 3** (for the GTK GUI)

- **WebKit2** — `apt install gir1.2-webkit2-4.1 libwebkit2gtk-4.1-0` (required for the embedded documentation viewer)

!!! warning "ZFS root filesystem not tested"
    ZFS Utilities has **not been tested** on systems where the root filesystem
    (`/`) is stored on a ZFS dataset (ZFS-on-root). Pool operations, snapshot
    retention, and iSCSI lifecycle scripts may interact with the root pool in
    unexpected ways. Proceed at your own risk.

### Proxmox VE (optional)

Proxmox VE is **only required for VM management, iSCSI initiator integration,
and PVE-specific patches**. For single-node deployments that only need ZFS
backup, snapshot, and retention features, Proxmox VE is optional.

- **Single node without VMs/iSCSI**: Proxmox VE is not required.
- **Compute node or single node with VMs**: Proxmox VE 8.x or 9.x is required
  for VM disk lifecycle integration.
- **Two-node storage node**: Proxmox VE is strongly recommended for iSCSI
  target support, but the core ZFS features work on any ZFS-capable
  Debian-based Linux distribution.

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

## Quick Start

### Single-node (recommended for new installs)

```bash
sudo /path/to/zfsutilities-dev/10\ Installers/install-single-node
```

The installer will:

1. Check that required single-node prerequisites are present
2. Explain any missing prerequisites and offer to install them automatically
3. Ask whether you want the optional documentation server (MkDocs) and explain
   what it provides
4. Prompt for your hostname (default: current hostname)
5. Generate the installation configuration file `/etc/zfsutilities-node.conf`
6. Deploy scripts as a **versioned installation** to `/usr/local/lib/zfsutilities/versions/<version>/`
7. Activate the version and wire it into active production:
   - Configure `PATH` in `/etc/profile.d` and `/etc/sudoers.d`
   - Create the `/root/bashinit` symlink
   - Create the `/usr/local/lib/zfsutilities/bin` symlink and library symlinks
   - Create desktop shortcuts in the installing user's home directory:
     **ZFSutilities GUI** and **ZFSutilities Documentation**

### Two-node

Run on the **storage host** (the machine with the ZFS pools):

```bash
sudo /path/to/zfsutilities-dev/10\ Installers/install-two-node
```

The installer will:

1. Check that required two-node prerequisites are present
2. Explain any missing prerequisites and offer to install them automatically
3. Ask whether you want the optional documentation server (MkDocs)
4. Prompt for storage host, compute host, storage network IP, iSCSI IQN
   prefix, and pool-to-target mappings
5. Generate the installation configuration file `/etc/zfsutilities-node.conf`
6. **Create iSCSI targets** on the storage host automatically (idempotent —
   skips targets that already exist)

The installer asks for an **iSCSI Qualified Name (IQN) prefix**. This becomes
part of every iSCSI target's persistent on-disk name and is baked in when the
LUN is first created. Changing it later requires recreating Proxmox iSCSI
storage entries and re-mapping LUNs, so accept the generated default unless
your site already uses a registered naming convention. See
[Two-node configuration](../developer-guide/two-node-config.md) for details.

7. Deploy scripts as a **versioned installation** on both hosts via SSH
8. Activate the version on both hosts and wire it into active production:
   - Configure `PATH` in `/etc/profile.d` and `/etc/sudoers.d`
   - Create the `/root/bashinit` symlink
   - Create the `/usr/local/lib/zfsutilities/bin` symlink and library symlinks
   - Create desktop shortcuts in the installing user's home directory:
     **ZFSutilities GUI** and **ZFSutilities Documentation**
9. Verify SSH key authorization between hosts
11. **Patch PVE's iSCSI rescan rate limit** on the compute host (if PVE is
    detected) — limits automatic `iscsiadm --rescan` to once per day, which
    eliminates repetitive kernel log spam on the storage host

See [Next Steps](#next-steps) for what to do after installation.

## Versioned Upgrades

After the initial install, use [deploy-version](../commands-and-modules/two-node.md#deploy-version-repo-root) from the repository root to
install new versions without touching the running system:

```bash
cd /path/to/zfsutilities-dev
sudo ./deploy-version
sudo switch-version 0.34.0
```

- [deploy-version](../commands-and-modules/two-node.md#deploy-version-repo-root) copies the current repo state into a new version directory without touching active production
- [switch-version](../commands-and-modules/two-node.md#switch-version-any-host) wires a deployed version into active production by updating the `current` symlink, refreshing `PATH` configuration, library symlinks, and desktop shortcuts
- Roll back instantly: `sudo switch-version previous`
- List deployed versions: `sudo switch-version --list`
- Remove a version's wiring manually: `sudo switch-version --uninstall`

The versioned deployment model is described in the [Architecture](../developer-guide/architecture.md) page.

## Switching Modes

To switch from single-node to two-node, run `install-two-node`. It detects
the existing single-node config and prompts for the additional two-node
settings.

To switch from two-node to single-node, run `install-single-node`. It
rewrites the config for single-node mode. iSCSI scripts remain installed
but their operations are skipped.

The install scripts assume that storage devices and ZFS pools are already active on the new system configuration. The scripts do not assist with this. 

## Configuration Files

ZFSutilities uses two configuration files with different purposes.
The node configuration is not versioned; the runtime configuration
contains an internal schema version. Both files persist across version switches.

### Node Configuration (`/etc/zfsutilities-node.conf`)

System-wide settings generated by the installer. Contains node mode
(`single-node` or `two-node`), hostnames, storage-network IP, iSCSI IQN
prefix, and pool-to-target mappings.
See [Two-Node Configuration](../developer-guide/two-node-config.md) for
the full reference.

### Runtime Configuration (`/root/.config/zfsutilities.json`)

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
| `/usr/local/lib/zfsutilities/current/bin/zfsutilities-gui` | Symlink → `../07 GTK + Python/zfsutilities_gui.py` |
| `/usr/local/lib/zfsutilities/current/bin/zfsutilities-docs` | Symlink → `../07 GTK + Python/docs_viewer.py` |
| `/usr/local/lib/node-lib.sh`                          | Symlink → `.../current/lib/node-lib.sh` |

### Install Configuration

| Location                         | Contents                              |
| -------------------------------- | ------------------------------------- |
| `/etc/zfsutilities-node.conf`    | Node configuration                    |
| `/usr/local/lib/two-node-lib.sh` | Compatibility symlink → `node-lib.sh` |

### Two-node only (storage host)

| Location                                             | Contents                               |
| ---------------------------------------------------- | -------------------------------------- |
| `/etc/systemd/system/rtslib-fb-targetctl.service.d/` | systemd drop-ins for boot config       |
| `/etc/iscsi-encrypted-luns.conf`                     | Encrypted LUN registry (if applicable) |
| `/root/.luks-key`                                    | Optional LUKS keyfile for unattended boot |

See [ZFS Key Handling](zfs-keys.md) for how to prepare the LUKS USB device and
configure unattended boot.

### Two-node only (compute host)

| Location                      | Contents                  |
| ----------------------------- | ------------------------- |
| `/etc/zfsutilities-node.conf` | Node configuration (copy) |

## Editing Documentation

MkDocs is only required if you plan to **edit** the documentation source files
or run the live documentation server. The pre-built `site/` directory can be
viewed without it, and the GUI documentation viewer does not require a running
MkDocs server.

Install MkDocs and the Material theme:

```bash
pip install mkdocs mkdocs-material
```

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
sudo zfsutilities-docs
```

The installer creates desktop shortcuts in the installing user's home directory:

- **ZFSutilities GUI** → `/usr/local/lib/zfsutilities/current/bin/zfsutilities-gui`
- **ZFSutilities Documentation** → `/usr/local/lib/zfsutilities/current/bin/zfsutilities-docs`

You can run these launchers directly, add them to a panel or start menu, or
invoke the underlying Python scripts from a checkout during development:

```bash
sudo python3 '/path/to/zfsutilities-dev/07 GTK + Python/zfsutilities_gui.py'
sudo python3 '/path/to/zfsutilities-dev/07 GTK + Python/docs_viewer.py'
``` 

## Next Steps

After installation:

- **Single-node**: See [Proxmox Integration](../user-guide/proxmox-integration.md)
  for how to manage VM disks
- **Two-node**:
  - If you have encrypted zvols, read [ZFS Key Handling](zfs-keys.md).
  - Run [safe-iscsi-save](../commands-and-modules/two-node.md#safe-iscsi-save-storage-node) to generate the boot config.
  - See [Proxmox Integration](../user-guide/proxmox-integration.md).
- Configure the [GTK GUI](../user-guide/gtk-gui.md) for backup and
  retention management

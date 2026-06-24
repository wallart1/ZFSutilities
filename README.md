# ZFS Utilities

A collection of bash scripts for managing ZFS backup, snapshot, and retention operations across multiple ZFS pools. Designed for system administrators managing ZFS-based backup infrastructure.

## Features

- **Automated Backups**: Daily backup orchestration with configurable source/destination pools
- **Incremental Transfers**: Efficient ZFS send/receive with support for intermediate snapshots
- **Retention Policies**: Configurable snapshot retention by bucket (daily, weekly, monthly, offsite)
- **Resumable Transfers**: Automatic resume token handling for interrupted large transfers
- **Lock Management**: Interlock system prevents conflicting operations on datasets
- **Safety Checks**:
  - Space validation before transfers
  - Running VM detection (Proxmox VE)
  - Offline pool protection for snapshot deletion
  - Counterpart snapshot verification

## Requirements

- Debian-based Linux (e.g., Linux Mint, Ubuntu, Proxmox VE)
- ZFS (`zfsutils-linux`)
- Bash 4.0+
- `pv` (progress visualization for large transfers)
- `rsync`
- Root privileges for ZFS operations
- For the GTK GUI: `apt install gir1.2-webkit2-4.1 libwebkit2gtk-4.1-0`
  (these are not installed by default on Mint/Cinnamon)
- Optional: Proxmox VE (only needed for VM detection and iSCSI features)

## Installation

1. Clone or copy the repository to your system:
   ```bash
   git clone https://github.com/USERNAME/zfsutilities.git
   cd zfsutilities
   ```

2. Copy `bashinit` to your home directory and root's home:
   ```bash
   cp bashinit ~/
   sudo cp bashinit /root/
   ```

3. Ensure scripts are executable:
   ```bash
   chmod +x zfs* rsync*
   ```

4. Configure retention policies by editing or creating:
   - `zfsretainpol-<poolname>` for pool-specific policies
   - `zfsretainpol-default` for fallback policy

## Quick Start

### Daily Backup
```bash
sudo ./zfsdailybackup
```

### Manual Send/Receive
```bash
# Source the script and call the function
source ./zfs-send-receive
sourcefs="sourcepool/dataset"
destfs="destpool"
send-receive
```

### Snapshot Management
```bash
# Create a snapshot
sudo ./zfssnapbuild

# Delete a snapshot (with safety checks)
source ./zfsdelsnap
delsnap "pool/dataset@snapshot" 0
```

### Check Lock Status
```bash
sudo ./zfslockctl list
sudo ./zfslockctl status pool/dataset
```

## Directory Structure

| Directory | Contents |
|-----------|----------|
| `/` (root) | Active scripts and utilities |
| `06 Docs/` | Documentation manuals (source) |
| `07 GTK + Python/` | GTK/Python GUI |
| `08 Two-node/` | Two-node / iSCSI utilities |
| `09 ZFS clone support/` | VM clone lifecycle scripts |
| `10 Installers/` | Single-node and two-node installers |
| `Cache-warm/` | ZFS ARC cache warming helpers |
| `tests/` | Bash and Python test suites |
| `Watchall/` | Monitoring helpers |

## Configuration

### Snapshot Naming Convention

Format: `@<label>-<yyyy-mm-dd>T<hh:mm><tz>-<bucket>`

Example: `@dailybackup-2026-01-21T14:30-05:00-d`

Buckets:
- `d` - daily
- `w` - weekly
- `m` - monthly
- `s` - offsite

### Retention Policy Files

Create `zfsretainpol-<poolname>` with:
```bash
bktname[0]='d';     bktretain[0]=7   # Keep 7 daily
bktname[1]='w';     bktretain[1]=4   # Keep 4 weekly
bktname[2]='m';     bktretain[2]=12  # Keep 12 monthly
```

## Documentation

- `AGENTS.md` - Guidance for AI coding assistants
- `06 Docs/User Guide/` - End-user how-to guides
- `06 Docs/Developer Guide/` - Developer procedures
- `06 Docs/Commands and Modules Reference/` - Complete reference
- `06 Docs/Messages/` - Message catalog

## Versioned Deployment

Scripts are installed to `/usr/local/lib/zfsutilities/versions/<version>/` and activated
via symlink. This allows instant rollback without data loss. For a new single-node
installation on Linux Mint or another Debian-based distribution, run
`10 Installers/install-single-node` as root.

```bash
# Deploy current repo state as a new version (run from repo root)
sudo ./deploy-version

# Activate the new version
sudo switch-version 0.2.0

# Roll back if something breaks
sudo switch-version previous

# List installed versions
sudo switch-version --list

# Remove an old version
sudo uninstall-version 0.1.0
```

See `AGENTS.md` for details.

## Quick Reference: Invoking Scripts and GUI

All scripts are in `PATH` via `/usr/local/lib/zfsutilities/bin/` — run from
any directory:

```bash
sudo move-vm-disk 100 scsi1 200          # move a disk between VMs
sudo new-vm-disk tank 300 0 50G          # create a new VM disk
sudo resize-vm-disk tank 300 0 100G
sudo switch-version --list
```

The GTK GUI can be launched from the desktop start menu (**ZFSutilities**
under System tools) or from the terminal:

```bash
sudo zfsutilities-gui
```

## Security

These scripts are designed to run as `root` and operate directly on live ZFS
pools. Review every script before running it in production, and ensure you have
backups of any data you cannot afford to lose.

## Contributing

Bug reports, feature requests, and pull requests are welcome. Please open an
issue on GitHub before submitting large changes.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file
for details.

## Acknowledgments

Developed with assistance from Claude Code (Anthropic).

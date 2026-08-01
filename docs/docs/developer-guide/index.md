# Developer Guide

This guide covers the architecture, conventions, and internal design decisions
relevant to developers working on ZFS Utilities.

## Contents

| Page                                         | Description                                                         |
| -------------------------------------------- | ------------------------------------------------------------------- |
| [Architecture](architecture.md)              | Overall design, script patterns, data flow                          |
| [Conventions](conventions.md)                | Coding standards and patterns used throughout                       |
| [Testing](testing.md)                        | Automated test harness, mock infrastructure, and writing new suites |
| [Lock Manager](lock-manager.md)              | The interlock system for preventing conflicting operations          |
| [Two-Node Configuration](two-node-config.md) | Centralised config for storage host / compute host scripts          |
| [Documentation Server](doc-server.md)        | MkDocs configuration and edit-in-MarkText integration               |
| [Development Provenance](provenance.md)      | AI-assisted development notes and CLAUDE files                      |

## Repository Structure

| Directory               | Contents                            |
| ----------------------- | ----------------------------------- |
| `/` (root)              | Bash scripts                        |
| `06 Docs/`              | This documentation                  |
| `07 GTK + Python/`      | GTK GUI frontend                    |
| `08 Two-node/`          | Two-node infrastructure scripts     |
| `09 ZFS clone support/` | VM clone provisioning scripts       |
| `10 Installers/`        | Single-node and two-node installers |

## Key Dependencies

### Core runtime

- `bashinit` — session logging and `$mydir` setup. For development, copy to
  home: `cp bashinit ~`. `/root/bashinit` is auto-managed as a symlink by
  `deploy-version` and `switch-version`.
- `pv` — progress visualization for large transfers (`sudo apt install pv`)
- `zfsutils-linux` — ZFS userspace utilities (`sudo apt install zfsutils-linux`)
- `rsync` — file synchronization (`sudo apt install rsync`)
- `python3` — required by config helpers, iSCSI scripts, and the GUI

### Two-node / iSCSI (only if using two-node mode)

- `openssh-client` (`ssh`, `scp`) — remote deployment and two-node host
  delegation
- `targetcli` (`rtslib-fb-targetctl`) — iSCSI target management on the storage
  host
- `open-iscsi` (`iscsiadm`) — iSCSI initiator on the compute host
- `qm` — Proxmox VE VM management tools (for VM disk lifecycle scripts)

### GUI (optional)

- `python3-gi`, `python3-gi-cairo`, `gir1.2-gtk-3.0` — GTK bindings
- `gir1.2-webkit2-4.1`, `libwebkit2gtk-4.1-0` — embedded documentation viewer

### Development / diagnostics

- `lsof` — used by `switch-version` and `zfs-diagnose-busy`

## Testing

The automated test framework lives in `tests/` and is run with `./run-tests`.
See the [Testing](testing.md) page for the full guide, including how to write
new suites and use the mock infrastructure.

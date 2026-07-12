# User Guide

This guide covers day-to-day operations: running backups, managing offsite
copies, restoring data, and understanding how retention works. Operations are
described both as command-line invocations and through the GTK GUI where
applicable.

If you prefer a graphical interface, the [GTK GUI Reference](gtk-gui.md) covers
the same workflows through the ZFSutilities GUI.

If you are new to this system, start with [Concepts and Terminology](concepts.md)
before reading the task pages.

## Contents

| Page                                                      | Description                                                                                                |
| --------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| **Concepts and Terminology**                              |                                                                                                            |
| &nbsp;&nbsp;[Overview](concepts.md)                       | ZFS fundamentals, naming conventions, the backup chain                                                     |
| &nbsp;&nbsp;[Profiles](profiles.md)                       | Save, recall, and schedule reusable backup/offsite/restore configurations                                  |
| **[GTK GUI Reference](gtk-gui.md)**                       | Tabs, color conventions, Pool Watch windows, session Logs, Retention runner, embedded documentation viewer |
| **Command Line Reference**                                | The same workflows invoked from the shell                                                                  |
| &nbsp;&nbsp;[Daily Backup](daily-backup.md)               | Run or troubleshoot the nightly backup job                                                                 |
| &nbsp;&nbsp;[Offsite Backup](offsite-backup.md)           | Copy backups to a removable pool for offsite storage                                                       |
| &nbsp;&nbsp;[Restore Operations](restore.md)              | Recover a dataset or file from a snapshot                                                                  |
| &nbsp;&nbsp;[Retention Policies](retention.md)            | Understand and configure how long snapshots are kept                                                       |
| &nbsp;&nbsp;[Proxmox Integration](proxmox-integration.md) | Use ZFS Utilities with Proxmox VE                                                                          |

## Prerequisites

- Root (or `sudo`) access on the backup server
- ZFS pools must be imported and online (`zpool status` to check)
- Scripts are installed to `PATH` and can be run from any directory (handled by the installer scripts)

## Getting Help

All messages are written to stderr and include a `file:line` prefix that
identifies exactly where the message was issued:

```
[zfs-send-receive:142] A common snapshot was NOT found on fivebays/proxmox.
```

For a full explanation of any message, see the
[Messages](../messages/index.md) reference.

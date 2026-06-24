# ZFS Utilities Documentation

A collection of bash scripts and a graphical user interface (GUI) for managing ZFS backup, snapshot, and retention
operations across multiple ZFS pools.

## What's Here

| Section                                                       | Description                                                |
| ------------------------------------------------------------- | ---------------------------------------------------------- |
| [Installation](installation/index.md)                         | Installing ZFS Utilities on single-node or two-node setups |
| [User Guide](user-guide/index.md)                             | Task-based how-to guides for operating the system          |
| [Developer Guide](developer-guide/index.md)                   | Architecture, conventions, and developer procedures        |
| [Commands & Modules Reference](commands-and-modules/index.md) | Alphabetical reference for all scripts and functions       |
| [Messages](messages/index.md)                                 | Catalog of all messages with causes and responses          |

## Quick Navigation

**Common tasks:**

- [Run a daily backup](user-guide/daily-backup.md)
- [Send backups offsite](user-guide/offsite-backup.md)
- [Restore from a snapshot](user-guide/restore.md)
- [Understand retention policies](user-guide/retention.md)

## Key Concepts

### Snapshot Naming

Snapshots follow the format: `@<label>-<yyyy-mm-dd>T<hh:mm><tz>-<bucket>`

Example: `@dailybackup-2026-02-21T02:00-05:00-d`

| Bucket | Meaning                          |
| ------ | -------------------------------- |
| `d`    | Daily                            |
| `w`    | Weekly                           |
| `m`    | Monthly                          |
| `s`    | Offsite (sent to removable pool) |

Labels are used to "partition" snapshots. Only one label is operated upon during any major task. The labels "dailybackup", "offsite" and "clone" have special meanings. They are to be used only by the ZFSutilities system. 

Otherwise, anywhere you can enter a label, you may use any text that is valid in a ZFS snapshot name and does not contain "@" or "-". When using custom labels, the rest of the format is not used.  As custom labels are snapshot partitions, their snapshots are ignored (e.g., during pruning) unless you specify one in a major task.

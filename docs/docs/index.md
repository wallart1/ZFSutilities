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

## Path Layout and Migration

ZFS Utilities stores its files in the following FHS-aligned locations:

| Category | Directory | Contents |
|----------|-----------|----------|
| System / admin config | `/etc/zfsutilities/` | `node.conf`, `deploy.conf`, `iscsi-encrypted-luns.conf`, legacy `two-node.conf` |
| Runtime state / data | `/var/lib/zfsutilities/` | `config.json`, `history.json`, `profiles/`, `scrub_state.json`, `nextsnap`, `nextsnap_offsite` |
| Logs | `/var/log/zfsutilities/` | `sessions/`, `cron.log`, `rsync-pull.log`, etc. |
| Transient runtime state | `/run/zfsutilities/` | `nextsnap_<caller>`, `zfsscruball.state`, `main.pid` |
| Advisory locks | `/run/lock/zfsutilities/` | `.config.lock`, `.history.lock`, `.snapname.lock`, dataset locks, profile locks |

If you are upgrading from an older release that stored files under
`/root/.config/` or directly under `/etc/`, the first run after upgrade
automatically moves your data to the new locations. A backward-compatibility
symlink is left at each old path so older deployed versions can still find their
configuration and state if you switch back to them.

When you are confident you no longer need rollback compatibility, run
`cleanup-zfsutilities-legacy` to remove the legacy symlinks and, optionally,
uninstall the old deployed versions that do not understand the new layout:

```bash
sudo cleanup-zfsutilities-legacy
```

See `cleanup-zfsutilities-legacy --help` for options such as `--remove-older-than`
and `--dry-run`.

## Quick Navigation

**Common tasks:**

- [Run a daily backup](user-guide/daily-backup.md)
- [Send backups offsite](user-guide/offsite-backup.md)
- [Restore from a snapshot](user-guide/restore.md)
- [Understand retention policies](user-guide/retention.md)


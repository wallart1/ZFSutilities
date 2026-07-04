# Messages Reference

This section catalogs messages that may be issued by ZFS Utilities scripts,
organized by the script that issues them. Each entry describes:

- **Meaning** — what the message indicates
- **Cause(s)** — what conditions lead to this message
- **Outcome** — what happens after the message is issued
- **Response** — what action (if any) is appropriate

!!! note "Work in progress"
    This section is being populated. Messages will be added as they are encountered
    and documented.

---

## Message Format

All messages are issued via `log_msg` — from `bashinit` for bash scripts, or
from `backup_config.py` for Python scripts. Bash messages are written to
**stderr**; Python messages route to the GUI log panel when the GUI is running,
or to **stderr** in CLI mode. Every message is prefixed with the source location:

```
/path/to/script:linenum: Message text here.
```

When a Python runner wraps a bash subprocess, the raw line captured from the
subprocess may already contain a bash `file:line:` prefix. The viewer's level
parser strips one or more leading `file:line:` prefixes (plus an optional
timestamp) before looking for the `LEVEL:` token, so nested prefixes do not
prevent priority filtering.

When a session is active, both bash and Python `log_msg` append messages to the
session log file pointed to by the `ZFSUTILITIES_LOG_FILE` environment
variable. Python code always writes to the file when the variable is set;
`ZFSUTILITIES_LOG_INHERIT` is checked only by bash subprocesses so they do not
create a competing log.

In the GTK GUI, `BackupRunner.prepare_session_log()` creates the session file
and exports `ZFSUTILITIES_LOG_FILE` before any pre-start messages are emitted.
`ZFSUTILITIES_LOG_INHERIT=Y` is passed via `child_env` to bash subprocesses;
`BackupRunner` reads raw stdout/stderr from the subprocess pipes and writes
every line to the session log file, making it the single writer. The previous
environment is restored when the task finishes or is cancelled, keeping
concurrent runs isolated.

Session logs are stored in `/var/log/zfsutilities/sessions/` with filenames
like:

```
YYYY-MM-DD_HH-MM-SS_<type>_<name>.log
```

GUI runs, scheduled cron jobs, and direct CLI script executions all produce
session logs automatically.

Fatal messages (`FATAL:`) are followed by script termination. Informational
messages (`INFO:`) are progress indicators. Warning messages (`WARN:`) flag
non-fatal issues — for example, a safety check that prevented an operation
from proceeding.

When output is directed to a terminal (not a file or pipe), `WARN:` messages
are shown in **orange** and `FATAL:` messages in **red** for visibility. Log
files and GUI sinks receive plain text without color codes.

### Priority prefixes

Messages may begin with one of the following priority tokens (lowest to
highest):

```
DEBUG:  VERB:  INFO:  WARN:  FATAL:  [none]
```

`log_msg` always emits every message to stderr (or the GUI sink) and to the
session log file. Filtering by priority is performed by the GUI log viewers,
not by `log_msg`. The main info panel and the Logs tab viewer each have an
independent **Level** selector. A message without a recognized prefix uses the
implied "(none)" level and is always displayed. See
[Developer Guide — Message priorities](../developer-guide/conventions.md#message-priorities).

---

## Message Index

### zfscheckagainst

| Message prefix                                      | Meaning                                                     | Response                                                                |
| --------------------------------------------------- | ----------------------------------------------------------- | ----------------------------------------------------------------------- |
| `Snapshot ... does not exist`                       | The snapshot passed to checkagainst was not found           | Check snapshot name; script aborts                                      |
| `No eligible enteries in the checkagainst array`    | The dataset has no entry in the fss lookup table            | Deletion proceeds without counterpart check; add entry to fss if needed |
| `This is the last remaining common snap`            | Deleting this snapshot would break incremental backup chain | Do not delete; check why counterpart is missing                         |
| `A counterpart snap for ... was not found`          | No common snapshot between source and counterpart           | Incremental backup may already be broken                                |
| `WARN: Cannot verify counterpart - pool(s) offline` | Counterpart pool is offline; deletion blocked for safety    | Import the counterpart pool, then rerun                                 |

### zfs-send-receive

| Message prefix                                              | Meaning                                                   | Response                                                                               |
| ----------------------------------------------------------- | --------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `WARN: No common snapshot found between ...`                | Destination exists but shares no snapshot with the source | Answer y/n to full copy prompt, or investigate why the destination has no common base  |
| `INFO: Destination ... does not exist; creating new dataset` | New destination dataset will be created from a full copy  | Informational; confirm the destination pool/dataset path is correct                    |
| `INFO: Approximately ... bytes to transfer`                 | Estimated full copy size                                  | Informational; shown before the transfer begins                                        |
| `VERB: Full copy — transfer of ... will be resumable`       | Full copy will use resumable receive (`zfs receive -s`)   | Informational; visible in the GUI log viewers when the level filter is `VERB` or `DEBUG` |
| `Insufficient space on destination`                         | Not enough free space for transfer                        | Free up space or reduce transfer scope                                                 |

### zfsretain

| Message prefix                                    | Meaning                                | Response      |
| ------------------------------------------------- | -------------------------------------- | ------------- |
| `Phase 0: Removing offsite same-month duplicates` | Starting offsite same-month prune pass | Informational |
| `Phase 1: Removing same-day duplicates`           | Starting same-day dedup pass           | Informational |
| `Phase 2: Pruning by bucket counts`               | Starting bucket count pruning          | Informational |

### zfs-diagnose-busy

Issued automatically when `zfs destroy` fails. Each `WARN:` line names a
specific cause and suggests the fix.

| Message prefix                                                        | Meaning                                              | Response                                                                                                |
| --------------------------------------------------------------------- | ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `Snapshot has clone dependents: ...`                                  | One or more clones were created from this snapshot   | Promote or destroy the dependent clones first                                                           |
| `Snapshot has holds: ...`                                             | ZFS hold tags are present                            | Use `releaseholds` or `zfs release <tag> <snap>`                                                        |
| `Dataset is mounted at ... with open processes: ...`                  | Files are open on the mountpoint                     | Stop the listed processes or unmount first                                                              |
| `Dataset has an active or interrupted receive (resume token present)` | A `zfs receive` is in progress or was interrupted    | Allow it to complete, or abort with `zfs receive -A <dataset>`                                          |
| `An active 'zfs send' involving ... is running`                       | A `zfs send` process is using the dataset/snapshot   | Wait for it to finish                                                                                   |
| `Snapshot is referenced by bookmark(s): ...`                          | A bookmark points to this snapshot                   | Destroy the bookmark first                                                                              |
| `Zvol is exposed as an iSCSI LUN on ...`                              | The zvol is mapped to an iSCSI target/LUN            | Use [remove-vm-disk](../commands-and-modules/two-node.md#remove-vm-disk-both) or targetcli to tear down |
| `VM ... is RUNNING and may be using ...`                              | A Proxmox VM is active on this zvol                  | Stop the VM before destroying                                                                           |
| `Dataset is shared via NFS/SMB (...)`                                 | The dataset is exported via `sharenfs` or `sharesmb` | Unshare with `zfs set sharenfs=off` or `sharesmb=off`                                                   |
| `No specific cause identified`                                        | None of the above checks matched                     | Try `fuser -m <mountpoint>` or `lsof +D <mountpoint>` manually; check for pool scrub/resilver           |

### zfssendoffsite

| Message prefix                                 | Meaning                             | Response                                     |
| ---------------------------------------------- | ----------------------------------- | -------------------------------------------- |
| `ERROR: No offsite pools are currently online` | Neither z22tb nor z40tb is imported | Import an offsite pool: `zpool import z22tb` |
| `INFO: Will be sending to pool ...`            | Identified the active offsite pool  | Informational                                |

---

*Further messages will be documented here as the catalog is built out.*

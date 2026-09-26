# GTK GUI Reference

The `zfsutilities_gui.py` application graphical frontend for the ZFSutilities scripts. It must be run as root:

```bash
sudo zfsutilities-gui
```

The installer creates a symbolic link named **ZFSutilities GUI** in the
installing user's home directory. You can also launch the script directly or
add `/usr/local/lib/zfsutilities/current/bin/zfsutilities-gui` to a panel or
start-menu launcher.

All settings are persisted to `/var/lib/zfsutilities/config.json`, the same
shared config read by the bash scripts. See
[Architecture — JSON config](../developer-guide/architecture.md) for details.

## Single-Instance Behavior

Only one primary GUI instance is allowed. If the GUI is already running, a
second launch automatically terminates the existing instance and starts a fresh
primary instance. A transient wait dialog is shown while the previous window is
closing:

```
Please wait: closing the previous ZFS Utilities window...
```

If a previous launch crashed or hung without showing a usable window, it is
detected as stuck and terminated automatically without prompting.

The `--replace` command-line flag is still accepted for backward compatibility,
but it is no longer required; replacement is now the default behavior.

For the underlying mechanism (PID file, D-Bus, window detection), see
[Architecture — GUI ↔ Bash Integration](../developer-guide/architecture.md#gui-bash-integration-architecture).

## Closing the GUI

If a GUI-started task is still running when you close the main window or choose
**File → Quit**, a confirmation dialog lists the tasks that would be aborted
and asks whether you really want to quit. Scrubs are not listed because they
continue independently of the GUI; scheduled or profile tasks started outside
this GUI process are also excluded.

Choosing **Cancel** keeps the window open so the tasks can finish normally.

## The Main Window

When you open the ZFS Utilities GUI, the main window is titled **ZFS Utilities**.
It is vertically divided into three areas: the menu bar at the top, the working area in the
middle, and the log panel at the bottom.

### Menu bar

The menu bar runs across the top of the window and contains three menus:

- **File**
  - **Quit** — closes the application.
- **View**
  - **Minimize Width...** — resets every resizable table column to its narrowest
    width and shrinks the window as small as possible.
- **Help**
  - **Documentation** — opens the built-in documentation viewer.
  - **Help with this page** — opens the viewer at the section for the currently
    selected tab.
  - **Set Documentation Editor...** — chooses the external editor used when you
    click the pencil icon in the documentation viewer.
  - **About** — shows the version, license, and credits.

### Working area

The middle of the window is split into three parts:

- **Left sidebar** — the vertical list of tabs. Click a tab name to open that
  page.
- **Central pane** — the large area that shows the contents of the currently
  selected tab. This is where you review status, fill in settings, and view lists
  or tables.
- **Actions panel** — the vertical panel on the right, labeled **Actions**. The
  buttons change depending on which tab is open. Common buttons include
  **Run Backup**, **Run Offsite**, **Save Config**, **Revert Config**,
  **Add Profile to Schedule**, and **Refresh**. While a job is running, the run
  button changes to **Cancel**.

The sidebar tabs are:

| Tab                               | What it is for                                             |
| --------------------------------- | ---------------------------------------------------------- |
| [Dashboard](#dashboard-tab)       | At-a-glance system health, recent operations, and warnings |
| [Backup](#backup-tab)             | Configure and run the daily backup                         |
| [Offsite](#offsite-tab)           | Configure and run offsite backups                          |
| [Restore](#restore-tab)           | Restore datasets from backups                              |
| [Schedule](#schedule-tab)         | Manage scheduled profiles                                  |
| [Disks](#disks-tab)               | Physical disk inventory, pool topology, and pool growth    |
| [Pools](#pools-tab)               | Register pools and manage scrubs                           |
| [Datasets](#datasets-tab)         | Browse datasets and manage snapshots/holds                 |
| [Retention](#retention-tab)       | Per-pool retention policies and pruning                    |
| [Checkagainst](#checkagainst-tab) | Edit snapshot safety checks                                |
| [Logs](#logs-tab)                 | Browse, search, and delete session log files               |

### Bottom panel

The bottom panel shows live messages from the application and from any running
job.

- **Log/output area** — the large read-only text area where progress messages,
  warnings, and errors appear while a job runs.
- **Search bar** — above the log area. Type text and use the buttons to find and
  highlight messages.
- **Input** box and **Send** button — when a running job asks a question, type
  your answer in the **Input** box and click **Send** (or press Enter).
- **Log** dropdown — chooses which message levels are shown in the bottom panel:
  `DEBUG`, `VERB`, `INFO`, `WARN`, or `FATAL`. The default is `INFO`. This only
  filters the on-screen view; everything is still written to the session log
  files.
- **Short prefix** toggle — when on, each log line shows only the date and time;
  when off, it shows the full source-location prefix.
- **Clear** button — empties the visible log text.
- **Pop-out button** — the window-icon button at the far right detaches the
  bottom panel into its own separate window; click it again to put the panel
  back.

### Log Panel

The bottom panel shows a scrollable log of all operations. Every line is
prefixed with a `YYYY-MM-DD HH:MM:SS` timestamp in the system's local time.
The divider between the main content area and the log panel can be dragged to
resize the log.

A **Pop Out** button (window icon) next to the **Log** level dropdown detaches the
log viewer into an independent window.
While popped out, the viewer pane is removed from the Logs tab; it is restored
when the pop-out window is closed or docked again. 

### Search and Clear

Above the text view, a search bar provides:

- **Search entry** — type some search text and press Enter (or click **Search**)
- **Search** button — finds and highlights every match. The current match is
  highlighted in **orange**; all other matches are highlighted in **yellow**.
- **Reset** button — clears highlights and empties the search entry field
- **Previous / Next** arrow buttons — cycle through matches, wrapping around at
  the first/last match. A counter shows the current position (e.g. `3 / 12`).
  The viewer scrolls so the current match is visible.
- Search text is **case-insensitive**.
- Navigation keeps working while new log lines arrive: matches in newly added lines are folded into
  the highlight set and counter automatically.

A **Clear** button next to the **Input** entry empties the log buffer, clears
search highlights, and resets the warning/error indicator.

A
status area below the log view displays the current job step and progress text,
including progress lines for interactive runs and for profiles started
with **Run Now** from the Schedule tab.

In the [Logs tab](#logs-tab), the log viewer also has its own status label.
When you select a **Running** log, the viewer shows the latest progress
line for that specific task.

### Warning and error indicator

Next to the **Log** level dropdown, a colored indicator appears when the log
contains a `WARN:` or `FATAL:` message:

| Indicator              | Meaning                                       |
| ---------------------- | --------------------------------------------- |
| **Orange** `⚠ Warning` | At least one `WARN:` message has been logged  |
| **Red** `✗ Error`      | At least one `FATAL:` message has been logged |

The indicator remains until you initiate a new action (e.g., clicking **Run
Backup** or **Run Offsite**), so you can notice warnings even if they scrolled
out of view. `FATAL:` takes precedence over `WARN:`. Clearing the log buffer
with the **Clear** button also resets the indicator.

`WARN:` and `FATAL:` lines are also shown in color inside the log panel
itself (orange and red, respectively).

!!! tip "Jump to the latest warning/error"
    Click the indicator to search the log for the most recent message of the
    same level. The search box opens (if it is hidden) and the view jumps to
    the latest `WARN:` or `FATAL:` entry.

!!! tip
    The live log panel is useful for the current operation. For reviewing
    historical runs, open the [Logs tab](#logs-tab).

---

## First Run

On a fresh install the JSON config starts empty — no pools, no backup steps,
no offsite steps, and no checkagainst entries. The log panel will show
warnings for each missing section. Configure them through the relevant tabs:

1. **[Dashboard](#dashboard-tab)** — review system health at a glance
2. **[Pools](#pools-tab)** — online pools appear in red; select the pool, click **Add** then **Save**
   to register them. Check the **Offsite** box for any registered pool that will spend time offline. Use the Scrub Manager below the registry to queue, start, pause, resume, and stop scrubs.
3. **[Backup](#backup-tab)** — add rsync pull steps and send/receive steps
4. **[Offsite](#offsite-tab)** — review the automatically detected offsite pool and add offsite backup steps
5. **[Retention](#retention-tab)** — a `default` policy is auto-created. Add per-pool policies with **Add Policy** when needed.
6. **[Checkagainst](#checkagainst-tab)** — add dataset-counterpart mappings

## Startup Version Check (Two-Node)

When the GUI starts on a host configured for two-node operation, it
checks the peer node's ZFSutilities version by reading
`/usr/local/lib/zfsutilities/current/VERSION`. The result is
logged in the GUI's log panel:

- **INFO** — the peer is running the same version as this node.
- **WARN** — the peer is running a different version, or the peer could not be
  reached.

The check is non-blocking; the GUI starts normally even if the peer is offline
or the connection fails. Keeping both nodes on the same version is
important, especially before running backup, restore, or iSCSI operations.

## Tabs

The sidebar exposes these pages:

| Tab                               | Purpose                                                                                         |
| --------------------------------- | ----------------------------------------------------------------------------------------------- |
| [Dashboard](#dashboard-tab)       | At-a-glance system health, recent operations, and warnings                                      |
| [Backup](#backup-tab)             | Configure and run [`zfsdailybackup`](../commands-and-modules/commands.md#zfsdailybackup)        |
| [Offsite](#offsite-tab)           | Configure and run [`zfssendoffsite`](../commands-and-modules/commands.md#zfssendoffsite)        |
| [Restore](#restore-tab)           | Configure and run [`zfsrestore`](../commands-and-modules/commands.md#zfsrestore)                |
| [Schedule](#schedule-tab)         | Manage scheduled jobs                                                                           |
| [Disks](#disks-tab)               | Physical disk inventory, pool topology, and pool growth                                         |
| [Pools](#pools-tab)               | Pool registry + live `zpool list` status + scrub manager                                        |
| [Datasets](#datasets-tab)         | Collapsible dataset tree with inline snapshot/hold management (pool root datasets at top level) |
| [Retention](#retention-tab)       | Per-pool retention policies + prune runner                                                      |
| [Checkagainst](#checkagainst-tab) | Edit the [`zfscheckagainst`](../commands-and-modules/modules.md#zfscheckagainst) table          |
| [Logs](#logs-tab)                 | Browse, search, and prune session log files                                                     |

## Dashboard Tab

The Dashboard provides an at-a-glance overview of ZFS health and active locks.
It refreshes automatically every 30 seconds while visible, or manually via the
**Refresh** action button.

!!! tip "Dashboard data during heavy load"
    Pool and iSCSI information comes from live `zpool`/`targetcli` commands with
    a short timeout. If a refresh happens while the pools are very busy (for
    example, during a large backup), the command may time out. Instead of
    showing empty cards, the Dashboard keeps the last successful data and
    displays an italic *"data may be stale"* note until the next refresh
    succeeds.

### Warnings

Live compilation of issues that need attention:

- Degraded or offline pools
- Pools above the low-space threshold
- Pools with ZFS errors (vdev or permanent data errors)
- Pools with an active ZFS checkpoint
- SSD/NVMe disks at or above 80% wear (e.g. `SSD "/dev/sda" (Samsung SSD 870 QVO 1TB) wear at 85%`); probed in the background and cached for a few minutes
- Missing backup/offsite/checkagainst configuration
- Unregistered pools
- Stale lock files in `/run/lock/zfsutilities/.locks/`

### Pool Health

A live table from `zpool list` showing:

| Column         | Meaning                                                                                                        |
| -------------- | -------------------------------------------------------------------------------------------------------------- |
| **Pool**       | Pool name, prefixed with a green ● (online), red ● (degraded), or orange ● (other)                             |
| **Capacity**   | Progress bar showing used percentage; turns **red** at the low-space warning threshold or above                |
| **Last Scrub** | Date of the most recent scrub (including the date a scrub was canceled), or *"In progress"* if one is running. |
| **Scrub**      | Current scrub status: progress bar while **scrubbing**, or `paused` / `—` / `finished`                         |
| **Errors**     | `No errors` (green) or a short summary of vdev/data errors from `zpool status` (red)                           |

A **Low-space warning threshold** spin button sits above the pool table. It
sets the capacity percentage at which the Dashboard warns about low space.
The default is **80 %** (range 50–95 %).

### Running Tasks

A unified view of all currently running operations. Select one or more rows
and click **Cancel Selected Tasks** to stop them. The cancel button is enabled
only when the selection contains at least one real task; selecting the
*"No running tasks"* placeholder row keeps it disabled.

| Task type                | Source                                                                                                                                                                                                                                   | Cancel behaviour                                                                                                      |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| **GUI**                  | Backup, Offsite, Restore, or Prune started from their respective tabs                                                                                                                                                                    | Graceful cancel (SIGTERM the runner subprocess)                                                                       |
| **Dataset action**       | Disks-page pool operations — Migrate Pool, Create Pool, vdev growth (Add Data Vdev, Attach, Replace, Detach, Add Infra Vdev), Enroll iSCSI — and Datasets-page profile actions (Apply Profile, Rewrite Data), started from their dialogs | Graceful cancel (SIGTERM the runner subprocess). Shown with its operation name and Step N/M status.                   |
| **Scrub**                | Pool scrubs started from the Pools tab or detected as externally running                                                                                                                                                                 | `zpool scrub -s <pool>`. While running, the progress text includes an ETA when `zpool status` reports remaining time. |
| **ZFS-native operation** | In-progress resilver, RAIDZ expansion, or vdev removal on any pool, discovered from live `zpool status` on every refresh                                                                                                                 | Cannot be cancelled from the GUI; ZFS offers no cancel for these. The status shows percent done.                      |
| **Profile**              | `profile_runner.py` jobs launched by **Run Now** in the Schedule tab                                                                                                                                                                     | SIGTERM the profile-runner process                                                                                    |
| **Scheduled**            | `profile_runner.py` jobs launched by cron                                                                                                                                                                                                | SIGTERM the profile-runner process                                                                                    |

The operation name shown on a **Dataset action** row (for example,
*Migrate Pool: fivebays*) is set by the dialog that started the action before
the runner begins, so the row always names the operation you launched.

Cron launches each scheduled profile through a compound shell command
(`mkdir -p ... && python3 .../profile_runner.py run <name> ...`), so the
cron shell stays alive as a parent process while the runner executes. The
Dashboard resolves the profile name from that wrapper's command line and
folds it into the **Profile** row reported by the profile lock file, so a
scheduled run appears only once. A runner process that cannot be matched to
a profile name (for example, an invocation without a profile argument) is
listed as **Scheduled: profile_runner.py (PID N)** so the row still
identifies the process.

The scrub list is reconciled against live `zpool status` on every refresh, so
scrubs that finish or are paused externally — for example, by a headless
profile that uses the **Pause scrubs during each step** option — do not keep
showing as running after the actual scrub state changes. Scrubs paused outside
zfsutilities (for example, with `zpool scrub -p <pool>`) are treated as
user-paused and remain paused until you explicitly resume them from the
[Pools tab](#pools-tab).

### Active Locks

Lists every currently held (non-stale) ZFS dataset lock. Each row shows:

| Column          | Meaning                                                                         |
| --------------- | ------------------------------------------------------------------------------- |
| **Dataset**     | Locked dataset path                                                             |
| **Type**        | Lock type: `r` (shared read), `w` (exclusive write), or `x` (exclusive destroy) |
| **PID**         | Process ID holding the lock                                                     |
| **Script**      | Name of the script or process that acquired the lock                            |
| **Acquired**    | ISO timestamp when the lock was acquired                                        |
| **Description** | Optional description written when the lock was acquired                         |

The list refreshes automatically with the rest of the Dashboard. Stale locks
(whose owning process has exited) are not shown here; they are reported in the
**Warnings** section and can be removed with the **Fix Locks** action button.

### Recent Operations

A scrollable table showing the last **10** history entries:

| Column            | Meaning                                                                                                                           |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| **Date/Time**     | When the operation finished (`YYYY-MM-DDTHH:MM±TZ`)                                                                               |
| **Type**          | `backup`, `offsite`, `restore`, or `prune`                                                                                        |
| **Name**          | GUI label or scheduled profile name                                                                                               |
| **Message Level** | Highest message level issued during the operation, from its session log: green `✓` INFO/VERB/DEBUG, amber `⚠` WARN, red `✗` FATAL |

The list refreshes automatically with the rest of the Dashboard.

A WARN message does **not** mean the operation failed — many scripts warn and
continue. When a session log is unavailable or contains no levelled messages,
the cell falls back to the exit-code result (`✓ success`, `✗ failed`).

Each row also stores the operation's session-log path in a hidden column. The
[**View Log**](#actions) action uses this path to jump to the log in the
[Logs tab](#logs-tab).

### iSCSI Issues *(two-node only)*

Compares the expected LUN list against `targetcli` backstores. If any LUN is
missing, an orange warning row appears with a **Fix this** button that runs
[`repair-iscsi-luns`](../commands-and-modules/two-node.md#repair-iscsi-luns-storage-node)
on the storage host. The button output is displayed in the GUI log so you can
see which backstores and LUN mappings were added or verified.

This section is hidden entirely on single-node systems.

### Configuration

Shows the current node mode (`single-node` or `two-node`), hostnames, the
ZFSutilities version(s), the operating system(s) in use, and the **ZFS
version(s)**. In two-node mode the
versions of the storage host and compute host are fetched remotely; if both
roles resolve to the same host it is shown once with both role labels. If a
remote host cannot be reached, its version is shown as *unknown*.

### Actions

| Button                    | Behaviour                                                                                                                                                                                                                                                                                       |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Refresh**               | Re-gather all dashboard data immediately                                                                                                                                                                                                                                                        |
| **Fix Locks**             | Removes stale locks and refreshes the view                                                                                                                                                                                                                                                      |
| **Cancel Selected Tasks** | Cancels the selected rows in the **Running Tasks** list                                                                                                                                                                                                                                         |
| **View Log**              | Switches to the Logs tab and selects the session log for the selected **Running Tasks** or **Recent Operations** row. The log path is cached when the button becomes sensitive, so the action still opens the intended log even if a background refresh changes the selection before you click. |

---

## Backup Tab

This tab configures and runs the daily backup job ([`zfsdailybackup`](../commands-and-modules/commands.md#zfsdailybackup)).

### Layout

- **Pre-Backup** — One checkbox and a command entry:
  **Run pre-backup command** — Enable a custom command that runs before all backup steps. If it fails, the backup aborts.

- **Pull Steps** — Editable list of rsync pull operations. The frame header has
  an **Active** checkbox; unchecking it bypasses every pull step while still
  running the other backup steps. Each row has three columns:
  
  - **Source** — the remote hostname or IP and file path to pull from. Examples:
    `proxmox1:/etc`, `192.168.1.50:/root`, `backup-server.local:/home`.
  - **Destination path** — the local directory where pulled files are placed.
    Example: `/backups/proxmox1`
  - **Excludes** — optional rsync exclude patterns as a space-separated list.
    Patterns are passed directly to rsync as `--exclude=PATTERN`; use shell-style
    quoting for patterns that contain spaces. See
    [Daily Backup — Rsync Exclude Patterns](daily-backup.md#rsync-exclude-patterns)
    for details and examples.
  
  Add or remove rows with the buttons; reorder by dragging rows.
  
  A pull-step failure is **non-fatal**: it is logged as a warning, the backup
  continues with the remaining steps, and the job returns the failing pull's
  return code at the end. When an rsync step fails, a short human-readable
  diagnosis (for example, "SSH connection refused" or "No space left on
  destination") is appended to the session log after the exit code to make
  common network, permission, and disk-space failures easier to identify.

- **Snapshot** — Enter a snapshot name (or click **Generate** to build one
  from the current time). The `@` prefix is added automatically if omitted. This name will be used for every snapshot that is created during the job run.
  This section sits just above the **Send/Receive Steps** so you can review the
  snapshot name immediately before running the backup.

- **Send/Receive Steps** — Editable list of ZFS send/receive operations
  (Source pool, Destination pool). Reorder by dragging rows.

- **Advanced** — Collapsible expander, placed after the send/receive steps, with
  [dataset-selection criteria](#dataset-selection-criteria)
  (`includes`, `excludes`, `depth`, `startwith`, `endwith`), [advanced options](#advanced-options),
  and:
  
  - **ZFS Keys Backup** — Two entries:
    - **ZFS keys source** — rsync endpoint where the key files currently live
      (e.g. `/mnt/ZFSkeys/` or `storage-host:/backups/zfs-keys/`)
    - **ZFS keys destination** — rsync endpoint where the copied keys should be placed.
      Must resolve to an **encrypted ZFS dataset**; the step is skipped with a
      warning if it does not. See [Daily Backup — ZFS Keys Backup](daily-backup.md#zfs-keys-backup)
      for the security implications.

- **Post-Backup Steps** — Three checkboxes and a command entry:
  
  - **Clear snapshot name memory** after sending
  - **Prune snapshots** when the backup finishes — prunes only the datasets
    the active send/receive steps back up, on both the source and destination
    sides (the backup's dataset list is re-derived at prune time; each source
    dataset is pruned together with its mapped destination name); skipped when
    no send/receive steps are active, since no new snapshots were created. See
    [Daily Backup — Step Failure Handling](daily-backup.md#step-failure-handling).
  - **Run post-backup command** — Enable a custom command that runs after all
    backup steps finish. It executes even if a fatal error aborts the backup early.

### Actions

| Button                      | Behavior                                                                                                                                                                                                   |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Run Backup**              | Shows a confirmation dialog with the new snapshot name.<br>Click **OK** to proceed, **Cancel** to abort, or **Generate** to build a new snapshot name and review again.<br>Then launches `zfsdailybackup`. |
| **Cancel**                  | Appears while a backup is running; stops the backup job                                                                                                                                                    |
| **Select All**              | Marks every step as active                                                                                                                                                                                 |
| **Select None**             | Marks every step as inactive                                                                                                                                                                               |
| **Save Config**             | Persists the current tab state to JSON. Turns **red** while there are unsaved changes.                                                                                                                     |
| **Revert Config**           | Discards edits and reloads from JSON                                                                                                                                                                       |
| **Add Profile to Schedule** | Saves a snapshot of current backup settings as a scheduled profile (see [Schedule tab](#schedule-tab))                                                                                                     |
| **Recall Profile**          | Loads a previously-saved profile into this tab so you can edit it and/or run on demand (see [Recalling profiles](#recalling-and-editing-profiles))                                                         |

While a backup runs, messages stream to the log panel and any interactive
prompts from the job may be responded to in the **Input** entry next to the
**Send** button.

!!! note "Concurrent GUI runners"
    The Backup, Offsite, and Restore tabs are no longer globally serialized.
    You can start a backup while an offsite or restore job is running, provided
    they operate on disjoint datasets. Per-dataset locks still prevent two jobs
    from modifying the same dataset at the same time.

---

## Offsite Tab

This tab configures offsite backups ([`zfssendoffsite`](../commands-and-modules/commands.md#zfssendoffsite)).

### Layout

- **Offsite Pool** — A read-only **Detected pool** label. Candidates are
  selected in the [Pools tab](#pools-tab) entries using the **Offsite** checkbox; the
  first online candidate becomes the active offsite target at run time. Updates automatically.

- **Snapshot** — Enter a snapshot name (or click **Generate** to build one
  from the current time). The `@` prefix is added automatically if omitted.

- **Send/Receive Steps** — Editable list with columns: Active, Source,
  Destination, Includes, Excludes. Reorder rows by dragging. The `<offsite>`
  token in the Destination column is replaced at runtime with the detected
  offsite pool name.

- **Advanced** — Collapsible expander, placed after the send/receive steps, with
  [dataset-selection criteria](#dataset-selection-criteria)
  (`includes`, `excludes`, `depth`, `startwith`, `endwith`) and advanced send/receive options.

### Actions

| Button                       | Behavior                                                                                                                                                                                                                                                         |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Run Offsite**              | Detects the offsite pool, then shows a confirmation dialog with the new snapshot name and detected pool.<br>Click **OK** to proceed, **Cancel** to abort, or **Generate** to build a new snapshot name and review again.<br>Then launches the send/receive steps |
| **Cancel**                   | Appears while a job is running. Click to immediately terminate the job.                                                                                                                                                                                          |
| **Select All / Select None** | Mark every step active or inactive                                                                                                                                                                                                                               |
| **Save Config**              | Persists the tab state; turns **red** when there are unsaved changes.                                                                                                                                                                                            |
| **Revert Config**            | Reloads from JSON and refreshes the detected pool label                                                                                                                                                                                                          |
| **Add Profile to Schedule**  | Saves a copy of the current offsite settings as a profile in the Schedule tab.                                                                                                                                                                                   |
| **Recall Profile**           | Loads a previously-saved offsite profile into this tab for editing or on-demand execution                                                                                                                                                                        |

!!! note "Concurrent GUI runners"
    The Offsite tab can run at the same time as the Backup or Restore tabs when
    the operations touch disjoint datasets. Per-dataset locks prevent collisions
    on the same datasets.

---

## Restore Tab

This tab restores a backup dataset ([`zfsrestore`](../commands-and-modules/commands.md#zfsrestore)).

### Layout

- **Source and Destination** — Two text entries for the source dataset and
  the destination pool/dataset. The source dataset is the one created by the
  Backup tab. The destination dataset is the one that was originally backed up.
  Any pre-existing dataset with the same name as the destination will be
  destroyed before being restored from the source.
  
  Enable **Auto-determine destination** to have the GUI compute the destination
  from the source. When
  the checkbox is active, the destination entry is disabled and populated with
  the computed destination. When you uncheck it, the previously entered manual
  destination is restored and the entry becomes editable again. The computed
  destination is also refreshed when the Restore tab is opened or when the
  source entry changes while auto-destination is enabled.
  
  Enable **Restore entire subtree (recursive)** to restore the named dataset
  and all of its descendants. When unchecked (the default), only the named
  dataset is restored. The Advanced **depth** field overrides this checkbox if
  set.

- **Advanced** — Collapsible expander with
  [dataset-selection criteria](#dataset-selection-criteria)
  (`depth`, `includes`, `excludes`, `startwith`, `endwith`), the snapshot
  **label**, and:
  
  | Option                            | Purpose                                                                                          |
  | --------------------------------- | ------------------------------------------------------------------------------------------------ |
  | **label**                         | Snapshot label for matching. Only snapshots with this label are considered as source candidates. |
  | **Pause scrubs during each step** | Pause ZFS scrubs on the source and destination pools while the restore step is running.          |

- **Restore Steps** — Two checkboxes:
  
  - **Part 1** — Full copy of the oldest available source snapshot
  - **Part 2** — Incremental copy of remaining snapshots

- **Notes** — A reminder that Part 1 is destructive on the destination.
  Part 1 asks once for confirmation of the dataset list and then proceeds
  automatically; Part 2 runs incrementally without prompting.

### Actions

| Button                      | Behavior                                                                                                                                                                  |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Run Restore**             | Validates entries, warns if Part 1 is selected, then launches the restore                                                                                                 |
| **Cancel**                  | Stops a running restore                                                                                                                                                   |
| **Save Config**             | Saves settings; turns **red** when there are unsaved changes                                                                                                              |
| **Revert Config**           | Reloads from saved settings                                                                                                                                               |
| **Add Profile to Schedule** | Saves the current restore settings as a profile in the Schedule tab.                                                                                                      |
| **Recall Profile**          | Loads a previously-saved Schedule tab profile into this tab for editing or on-demand execution. Click the Add Profile to Schedule button to save changes to the schedule. |

!!! note "Concurrent GUI runners"
    The Restore tab can run at the same time as the Backup or Offsite tabs when
    the operations touch disjoint datasets. Per-dataset locks prevent collisions
    on the same datasets.

### Scrub profiles

The **Pools** tab can also save scrub settings as a scheduled profile.
Click **Add Profile to Schedule** to snapshot the currently **selected**
pools in the scrub table along with all settings (simultaneous count,
refresh interval, and system scrub toggles). The profile runner starts
the scrubs and polls until they finish.

---

## Schedule Tab

This tab manages scheduled profiles. Profiles are created by clicking "Add Profile to Schedule" from the
**Backup**, **Offsite**, **Restore**, **Retention** and **Pools (Scrub Manager)** tabs. They appear here as disabled entries where they may be scheduled and activated.

### Profile list

The top pane lists every saved profile with columns:

| Column           | Meaning                                                       |
| ---------------- | ------------------------------------------------------------- |
| **Active**       | Checkbox — toggles whether the profile is active              |
| **Profile Name** | Full name: `<user>-<tab>-<custom>` (e.g. `root-backup-daily`) |
| **Type**         | `backup`, `offsite`, `restore`, `retention`, or `scrub`       |
| **Schedule**     | Current cron expression (`min hour day month weekday`)        |
| **Comment**      | Optional free-form note for the profile                       |
| **Next Run**     | Next scheduled execution time                                 |

Click any column header to sort by **Profile Name**, **Type**, **Comment**, or **Next Run**.
Click any row to select it; use **Ctrl**/**Shift**-click to select multiple rows.
The detail pane below populates with the first selected profile's cron settings
(the first row in tree order when multiple rows are selected).

The profile list refreshes automatically every **60 seconds** while the Schedule
tab is visible, and immediately when you switch to the tab or click
**Refresh**. If the set of profiles has not changed, the **Next Run** values are
updated in place and the current selection is preserved. If profiles were added
or removed outside the Schedule tab (for example, by another GUI instance or by
editing the profile files directly), the list is rebuilt and any pending
unsaved changes for deleted profiles are discarded.

**Next Run** is computed from the cron expression only. If a profile has an
optional **Condition**, the condition is evaluated at runtime by `/bin/sh`; a
matching cron time does not guarantee the profile will run if the condition
exits non-zero.

### Run Now

Select one or more profiles and click **Run Now** in the Actions panel to execute
them immediately. **Run Now ignores the Active checkbox** — even disabled
profiles run. Each profile is launched via `profile_runner.py`, so it produces
its own session log and history entry exactly like a scheduled cron run. Output
streams to the info panel with a `[profile-name]` prefix so you can tell which
log line came from which running profile.

### Creating a profile

Profiles are **not** created from the Schedule tab. Go to the relevant
tab, configure the settings you want, and click **Add Profile to Schedule** in
the Actions panel. A dialog asks for a custom name and prepends the
`<user>-<tab>-` prefix automatically. The current tab settings — including the
**Dry Run** toggle state — are placed into the profile file.

!!! note
    Clicking **Add Profile to Schedule** does **not** save the tab's normal config
    settings. It only creates the profile in the Schedule tab. Use **Save Config**
    separately if you also want to save the settings as the default. Click **Revert** to bring back the original saved settings.

### Recalling and editing profiles

Every tab that supports **Add Profile to Schedule** also has a **Recall
Profile** button. Clicking it opens a dialog listing all saved profiles for
that tab. Selecting a profile loads its saved settings into the tab's
widgets, just as if you had typed them manually.

This is useful for two workflows:

1. **Edit and re-save** — Recall a profile, tweak the settings, then click
   **Add Profile to Schedule** again and give it the same name (to overwrite)
   or a new name (to create a variant).
2. **Run on demand** — Either click **Run Now** on the Schedule tab to run the
   selected profile(s) immediately, or recall a profile and click the tab's
   **Run** button. The job executes using the saved profile settings without
   waiting for the scheduled cron time.

Recalling a profile does **not** modify the saved config file. If you want to
make the recalled settings the new default, click **Save Config**
after recalling.

### Detail pane (profile selected)

- **Profile / Type** — read-only name and tab type
- **Comment** — optional free-form note; editable inline in the treeview or in this entry
- **Cron Parameters** — six editable fields. The first five accept numbers, `*` (any value), comma-separated lists,
  ranges, and steps:
  - **Minute** — `0-59`, `*`, e.g. `1,15,30`, `9-17`, `*/5`
  - **Hour** — `0-23`, `*`, e.g. `0,6,12`, `9-17`, `*/2`
  - **Day of Month** — `1-31`, `*`, e.g. `1,15`, `10-20`
  - **Month** — `1-12`, `*`, e.g. `1,4,7,10`, `3-5`
  - **Day of Week** — `0-7` (`0` and `7` are Sunday), `*`, e.g. `1-5`, `*/2`,
    plus ordinal qualifiers `6#1` (first Saturday) through `6#5`, `6#L` (last
    Saturday), lists `6#1,3`, and ranges `6#1,3-5`
  - **Condition (optional)** — a shell command prepended to the profile command
    with `&&`. The profile runs only when this command exits 0. This allows
    runtime checks that cron expressions cannot express, such as
    `[ $(date +%d) -ge 28 ]` to run only during the last three days of the
    month.
- **Interpretation** — live prose explanation of the cron expression
  (e.g. *"At 02:00 every day"* or *"Every 15 minutes on weekdays"*). When a
  condition is set, the interpretation notes that the profile runs only when
  the shell condition exits 0.
- **Examples** — next three datetimes that match the expression
- **Crontab entry** — for active profiles, the exact cron line that was written
  to `/etc/cron.d/zfsutilities`. This is shown at the top of the detail pane so
  you can verify the command, arguments, and output redirect without opening the
  cron file manually.
- **Config Summary** — collapsible, scrollable JSON dump of the full profile
  config. The text is selectable; right-click for **Copy** and **Select All**.

### Cron syntax

The Schedule tab supports a subset of standard Vixie cron syntax in each
field:

| Pattern      | Example           | Meaning                                          |
| ------------ | ----------------- | ------------------------------------------------ |
| Single value | `15`              | At minute 15                                     |
| Any value    | `*`               | Every minute/hour/day/etc.                       |
| List         | `1,15,30`         | At minutes 1, 15, and 30                         |
| Range        | `9-17`            | From 9 through 17 (inclusive)                    |
| Step         | `*/5` or `9-17/2` | Every 5 units, or every 2 units inside the range |

These patterns can be combined within a field (e.g. `1,9-17/2,30`).

**Weekday ordinals:** The Day-of-Week field supports ordinal qualifiers using
`#` to schedule a specific occurrence of a weekday within the month. Standard
Vixie cron does not understand this syntax, so the GUI writes a plain weekday
to `/etc/cron.d/zfsutilities` and `profile_runner.py` applies the ordinal
check at runtime.

| Example   | Meaning                                     |
| --------- | ------------------------------------------- |
| `6#1`     | First Saturday of the month                 |
| `6#2`     | Second Saturday of the month                |
| `6#3`     | Third Saturday of the month                 |
| `6#4`     | Fourth Saturday of the month                |
| `6#5`     | Fifth Saturday of the month (may not occur) |
| `6#L`     | Last Saturday of the month                  |
| `6#1,3`   | First and third Saturdays                   |
| `6#1,3-5` | First, third, fourth, and fifth Saturdays   |
| `6#1,L`   | First and last Saturdays                    |

**Not supported:** textual weekday or month names (`MON`, `JAN`), cron
special strings (`@daily`, `@hourly`), `L`/`W` qualifiers for non-weekday
fields, `W`/`?` qualifiers, or question marks. For a full cron syntax
reference, see [crontab.guru](https://crontab.guru/).

### Actions

| Button     | Behavior                                                                                                                                                                                      |
| ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Save**   | Saves all pending changes (active toggles, comments, and cron parameters) and regenerates `/etc/cron.d/zfsutilities`. Turns **red** when any row, comment, or cron field has unsaved changes. |
| **Revert** | Restores all pending changes to their last-saved values.                                                                                                                                      |
| **Delete** | Removes the selected profile file and its cron entry (with confirmation)                                                                                                                      |

Toggling the **Active** checkbox marks that profile as dirty. The change
is committed when you click **Save**.

### How cron works

Each active profile becomes one line in `/etc/cron.d/zfsutilities`, a
system drop-in file managed exclusively by the ZFS Utilities GUI. The file
sets `MAILTO=""` so cron does not send email; the GUI and runner write their
own session logs.

Scheduled jobs automatically
track whatever active version is installed.

Scheduled jobs run in the background and execute the same commands the GUI would run:

- **backup** — generates snapshot name, runs the pre-backup command, rsync
  pulls, ZFS send/receive, and the post-backup snapshot prune
- **offsite** — generates offsite snapshot, detects online offsite pool,
  runs send/receive steps with optional holds
- **restore** — runs the two-part restore (full + incremental)
- **retention** — runs `zfscleanup` for each selected pool with the specified snapshot label
- **scrub** — queues pools for scrubbing and polls until all finish or time out

!!! notice
    To change the tab-related parameters of a profile
    (pull steps, send/receive steps, pool lists, etc.), go to the appropriate
    tab, recall the profile, make your changes and click **Add Profile to Schedule**.

    The **Save** button on the Schedule tab commits only the items whose **Active** checkbox is selected. Others are removed from cron.

---

## Disks Tab

The **Disks** tab shows the physical storage layer underneath your ZFS pools.
A row of radio buttons across the top of the tab switches between two
views: **Inventory and Topology** (the Disk Inventory and Pool Topology
sections) and **Performance** (a placeholder for forthcoming
performance-monitoring sections). The pool drop-down under the radio row
selects the pool whose vdev topology is shown. The tab content scrolls
vertically as a whole when the window is too short; the Inventory and
Topology view also keeps a minimum height so it stays usable instead of
being squashed.

### Disk inventory

The Disk Inventory pane lists every physical block device detected on the system, plus
any partitions that belong to those devices. The system boot disk — the disk
hosting the root filesystem, however it is layered (plain partition, LVM,
BTRFS subvolume, or ZFS) — and all of its partitions are always hidden, so
they can never be offered by the create-pool wizard or any of the pool-growth
pickers:

| Column    | Meaning                                                                                                                                                                                                                                        |
| --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Name      | Kernel device node (e.g. `/dev/sda` or `/dev/sda1`)                                                                                                                                                                                            |
| by-id     | Best `/dev/disk/by-id` symlink name for the device or partition                                                                                                                                                                                |
| Model     | Device model string from `lsblk` (blank for partitions)                                                                                                                                                                                        |
| Serial    | Device serial number (blank for partitions)                                                                                                                                                                                                    |
| Size      | Capacity in human-readable units                                                                                                                                                                                                               |
| Type      | `HDD`, `SSD`, `NVMe`, `part`, or `unknown`                                                                                                                                                                                                     |
| Log-sec   | Logical sector size                                                                                                                                                                                                                            |
| Phy-sec   | Physical sector size                                                                                                                                                                                                                           |
| Transport | Transport type (e.g. `sata`, `nvme`, `sas`)                                                                                                                                                                                                    |
| Pools     | Pool membership determined from vdev topology                                                                                                                                                                                                  |
| SMART     | Overall SMART health (`PASSED`, `FAILED`, or `n/a`)                                                                                                                                                                                            |
| Wear/Test | For SSD/NVMe, the wear percentage from SMART data (`85%`). For HDDs, the surface self-test status (see [Surface Test](#surface-test)): `-`, `42% (1h 23m)` while running, or `Passed`/`Failed`/`Aborted`/`Canceled`. `-` when neither applies. |

Device scans and SMART probes can be slow, so the inventory is loaded in a
background thread and cached for a few seconds. Only SSD/NVMe disks get the
extended SMART query that yields wear data — HDDs keep the quick health check —
so the sweep stays fast even with many spinning disks. The two panes stay in sync
visually: selecting a disk or partition tints every device that resides on it
in the Pool Topology pane (drawn in teal), and selecting a pool, vdev, or
device node in the topology pane tints the corresponding rows in the
inventory. Neither pane ever changes the other's selection — the correlation
is teal text only.

### Pool topology

The Pool Topology pane shows the vdev topology of the pool selected in the drop-down.
The tree is shown fully expanded every time it is refreshed (Refresh button or
pool change). Selecting a node highlights the corresponding member disks and
partitions in the inventory view (their text is drawn in teal): the pool node
highlights every device in the pool, a vdev node highlights every device in
that vdev, and a device node highlights just that device. Clearing the
topology selection restores the pool-wide highlight. Selecting a disk or
partition in the inventory switches the pool selector to that disk's pool and
tints every topology device that resides on the selected disk (a whole disk
tints all of its partitions; a partition tints just that device), no matter
which pool's topology is being displayed:

| Column               | Meaning                                                                          |
| -------------------- | -------------------------------------------------------------------------------- |
| Name                 | Pool, vdev label, or full device path                                            |
| Type                 | `mirror`, `raidz1/2/3`, `stripe`, `disk`, `special`, `log`, `cache`, `spare`     |
| State                | ZFS state for the vdev or device                                                 |
| Read / Write / Cksum | Error counters from `zpool status`                                               |
| Blocksize            | Effective pool blocksize for the vdev, shown in bytes (512 bytes, 4096 bytes, …) |

### Creating Pools

Click **Create Pool…** to open the create-pool wizard, which builds a new pool
from unused disks with the project's signature safety: you always see the
exact command and a live dry-run before anything runs, and execution requires
typed confirmation.

The wizard has four steps:

1. **Disks** — select the member disks. Only eligible disks can be selected:
   whole disks (`TYPE=disk`) with no partitions, or individual partitions of
   solid-state disks (partitions of rotating disks are not eligible). A disk
   that is a member of any imported or importable pool is ineligible, and a
   disk without a `/dev/disk/by-id` path cannot be used (the command is built
   from by-id paths so it survives device-name changes). Ineligible disks are
   listed greyed out with the reason. USB-attached disks produce a warning —
   USB storage can drop out under load, which is dangerous for redundancy
   groups. **SMR (Shingled Magnetic Recording)** disks write new tracks partly
   on top of previously written tracks, like roof shingles. That layout makes
   them slower and less predictable under the heavy, random rewrite workload
   that ZFS RAIDZ can create; parity writes and resilvers can perform poorly,
   so a pool built from SMR drives may be sluggish and rebuilds can take far
   longer than expected. The wizard cannot reliably detect SMR from the drive,
   so check the drive specs before building RAIDZ from rotational disks.
2. **Topology** — choose `stripe`, `mirror`, `raidz1`, `raidz2`, `raidz3`,
   or `raid10` (striped mirrors). Minimum disk counts are enforced (mirror ≥
   2, raidz1 ≥ 3, raidz2 ≥ 4, raidz3 ≥ 5). `raid10` requires an even count of
   at least 4 disks and builds `mirror d1 d2 mirror d3 d4 …` — pairs of
   mirrored disks striped together. Any single disk, plus one disk from each
   other mirror, may fail without data loss; capacity is 50% of raw at 2×2.
   A mixed-size selection warns that vdev capacity is limited by
   its smallest member. A live capacity estimate shows both raw and effective
   capacity for the selected workload profile's block size.
3. **Pool settings** — enter the pool name (validated against `zpool` naming
   rules and checked for collisions with imported and importable pools),
   choose the pool blocksize, and pick a workload profile whose live
   filesystem properties are written explicitly as `-O` options — never left
   to `zpool create` defaults, which drift between releases. The pool
   blocksize is the GUI name for the ZFS `ashift` property: `512 bytes` =
   ashift 9, `4096 bytes` = ashift 12, and `8192 bytes` = ashift 13. The
   wizard computes a **recommended** pool blocksize for the selected disks
   and pre-selects it, so the review step shows `-o ashift=<value>` in the
   exact command. The recommendation starts at `4096 bytes` and only ever
   goes up: a blocksize above 4096 recorded in a previous pool's labels on
   the disks (read with `zdb -l`) or a disk reporting a physical sector size
   above 4096 (e.g. 8K-native NVMe) raises it to `8192 bytes`. It is never
   automatically lowered to `512 bytes`, because no available probe can tell
   an honest 512-byte-native drive apart from a 4K-native drive misreporting
   512 — and a too-small blocksize permanently hurts the modern drive while
   a slightly-too-large one is harmless to the old one. `512 bytes` remains
   in the list as a manual choice for experts who know their hardware.
   `auto (let ZFS decide)` also remains available, but ZFS trusts what the
   drive reports — that is exactly the misreporting weakness the wizard's
   recommendation avoids.
4. **Review** — the exact `zpool create` command plus the live output of
   `zpool create -n` (a dry run that validates the command without creating
   anything). The **Create** button stays insensitive until you type the pool
   name — stronger than the usual YES/NO dialog, because a mistaken create can
   destroy data on reused disks.

After execution, the Disks and Pools tabs refresh
automatically, and you are offered the chance to register the new pool in the
pool registry so backups and retention can include it. On a two-node
configuration you are also offered iSCSI enrollment: accepting it adds the pool
to the `POOL_TARGET` map in `node.conf` on both nodes (via
`enroll-iscsi-pool`), creates the pool's iSCSI target on the storage host, and
rescans the compute host — so VM disks created on the new pool work over iSCSI
immediately, with nothing to configure by hand.

On a two-node configuration the wizard is available only on the storage host;
on the compute host the button is disabled with an explanatory tooltip.

### Growing and Maintaining Pools

Five actions grow or maintain an existing pool. Every one of them follows the
same safety pattern as the create-pool wizard: you pick the pool (it defaults to
the pool selected in the topology pane) and the disks or members involved, then
a review page shows the exact command that will run, warnings tailored to how
dangerous the operation is, and a confirmation step matched to that danger.
Disk eligibility uses the same rules as create-pool, and an operation is refused while
the pool's scrub is running or paused — stop the scrub (or wait for it to finish)
from the Pools tab Scrub Manager first. On two-node systems the buttons are available only on
the storage host, and all six are disabled while a dataset action is running.

#### Add Data Vdev

A **vdev** (virtual device) is one top-level unit of a ZFS pool. A pool is made
of one or more vdevs, and each vdev provides its own redundancy. For example, a
mirror vdev can survive the loss of one member, while a stripe vdev cannot
survive any. If a vdev fails entirely, the whole pool can fail — ZFS cannot
recover data that was on a lost vdev using redundancy from a different vdev.
When you add a data vdev, you are extending the pool with another independent
redundancy group, so choose the topology carefully.

Pick the disks for a new data vdev from the eligible-disk picker (members of
imported or importable pools are greyed out, as in the create-pool wizard) and
choose the topology: `stripe`, `mirror`, `raidz1`, `raidz2`, or `raidz3`, with
the same minimum disk counts and mixed-size warning as pool creation. A
mixed-size selection warns that vdev capacity is limited to the smallest member.
Adding a **mirror** vdev to a pool of mirror vdevs extends a RAID10
(striped-mirror) layout — that is how a RAID10 pool grows. Because growing the
wrong pool is hard to undo, the action requires typed
confirmation of the pool name. The exact command is
`zpool add <pool> <topology> <by-id…>`.

#### Expand Vdev

Expand an existing vdev by attaching a new device: convert a stripe to a
mirror, grow a mirror by one member, or expand a raidz vdev. Pick the target
in the pool's topology tree, then one eligible disk:

- A **stripe member** — the attach converts the stripe vdev into a mirror. A
  YES/NO warning dialog explains that the new device becomes a redundant copy
  of the existing one. ZFS cannot attach a disk to an existing stripe vdev:
  if the goal is more capacity without mirroring, the warning points you at
  **Add Data Vdev** with the stripe topology, which adds a new top-level
  stripe vdev instead.
- A **mirror member** — the attach grows the mirror by one member, with a note
  showing the new member count.
- A **raidz group** — the attach offers a RAIDZ expansion
  (`zpool attach <pool> <raidzN> <new>`). This requires OpenZFS 2.3+; on older
  versions the target is disabled with an explanatory tooltip. The warnings
  explain that existing data keeps its old data:parity ratio until rewritten —
  afterwards use the **Rewrite Data** action per dataset to restripe existing
  data at the new ratio. RAIDZ expansion confirms with typed confirmation of
  the pool name.

#### Replace

Pick the pool member to replace in the topology tree — each row shows the
member or group size — then an eligible replacement disk (the source device
is excluded from the picker). If the
replacement is smaller than the source, a prominent warning says the replace
may fail or reduce available space; typed confirmation of the pool name is required. After the replace starts, the topology pane shows `resilvering` in the
pool state column — watch live progress in the Pools tab Watch window. The
exact command is `zpool replace <pool> <old-by-id> <new-by-id>`.

#### Detach

Detach removes a member from a **mirror** vdev — nothing else. In the
topology tree only disk members of a mirror vdev are selectable; raidz
members, stripe (single-disk) members, groups, and special/log/cache devices
are greyed out. When no imported pool has a mirror member at all, the action
explains that and does not open the dialog. The warnings state that detaching
reduces redundancy and is not undoable without re-attaching a device, and
that detaching one leg of a 2-member mirror leaves a single non-redundant
disk. Because the operation is irreversible, it confirms with typed
confirmation of the pool name. The exact command is `zpool detach <pool> <by-id>`.

#### Add Infrastructure Vdev

Adds a `special`, `log`, or `cache` vdev from the kind selector. Two or more
selected disks form a mirror; one disk is a single device:

- **special** (metadata) — must be a mirror of at least 2 devices. The warning
  is blunt: losing the special vdev loses the entire pool, because metadata
  lives only there. Typed confirmation of the pool name is required.
- **log** (SLOG) — only accelerates synchronous writes; it holds no pool data.
  A single device is allowed, with a warning that losing it may lose a narrow
  window of already-acknowledged synchronous writes (application data, not
  metadata). Mirror the SLOG on separate physical
  devices if that cannot be tolerated. The warnings also note that an SLOG
  only needs to hold ~5 seconds of synchronous writes (max pool write speed
  × 5 s), so oversized devices gain nothing. An acknowledgment checkbox
  replaces the typed confirmation.
- **cache** (L2ARC) — a read cache that needs no
  redundancy. A YES/NO question confirms the addition.

The exact command is `zpool add <pool> <special|log|cache> [mirror] <by-id…>`.

#### Migrate Pool

Copy-based expansion for changes ZFS cannot perform in place — converting a
stripe to raidz (or mirror to raidz), changing vdev width, or changing the
pool blocksize (the `ashift` property).
Pick the source pool and one of two destination modes:

- **New disks** — select eligible disks and a topology for a new pool (built
  under a temporary name like `<pool>_mig`), or
- **Holding pool** — pick another imported pool with free space at least equal
  to the source pool's allocated data; the source pool is then destroyed and
  rebuilt with the chosen topology before the data is copied back. Any other
  imported non-root pool qualifies, even an empty one —
  a pool only needs datasets to be a migration *source*, not a holding pool.
  The holding pool is a temporary waystation, not a destination: it keeps its
  name and its own datasets, and only the reserved migration namespace inside
  it is removed afterwards. Holding-mode copies land in that reserved
  namespace (`<holding-pool>/migrate_<source-pool>/<dataset>`) so they can
  never collide with backup or offsite copies of the same datasets — a pool
  that also receives backups is a valid holding pool. The rebuilt pool's
  disks are your choice: the source pool's own disks (pre-selected, since the
  cutover destroy frees them) plus any eligible unused disks — so the new
  topology can use the old disks, new disks, or any mix. Disks you leave
  unselected simply stay free for later use.

Choose **New disks** when you have unused disks to build the new pool on (the
old disks are freed untouched and remain re-importable). Choose **Holding
pool** when the new topology should be built from the existing disks — alone
or combined with additional unused disks — or whenever you have no spare
disks at all.

The review page lists every step that will run, from the recursive migration
snapshot through one `zfs send -Rw` replication step per top-level dataset
(received with `zfs receive -u -F -s -v`; snapshots, descendants, and
properties included; encrypted datasets are sent raw; `-v` logs each dataset
as it is received so progress through the tree is visible in the log) to a
dataset-tree verification.
An optional **Bandwidth limit** (a `pv` rate such as `100m`) throttles the
copy. Every copy is resumable: an interrupted transfer leaves a receive
resume token on the destination, and re-running Migrate Pool resumes from
that token instead of starting over, with live `pv` progress shown in the
status area. Typed confirmation of the source pool name starts the copy
phase. If the pool's dataset layout changed after the review (a dataset was
renamed, added, or removed while the wizard was open), the run is aborted
before anything starts with an explanation — re-open Migrate Pool and review
the plan again. When the copy finishes, a second
typed confirmation gates the cutover: the source pool is exported and the
migrated pool is re-imported under the source pool's name — a permanent
rename written to the pool label, so every future import uses the normal
pool name — and every `pool/dataset` path, and everything that references
it, survives the swap.

Aborting a migration is safe at every point before the destructive steps:
stopping during the copy phase loses nothing (the source pool is untouched);
after the export but before the destroy, the source pool re-imports intact;
in holding mode after the source pool is destroyed, the complete verified
copy remains on the holding pool, so re-running Migrate Pool resumes the
copies and finishes the job. Your regular backups are never touched by a
migration. If cutover is deferred, the migration snapshot and copies remain
in place; in
holding mode the cutover also removes the migration namespace from the
holding pool.

Snapshot holds survive the migration. ZFS send streams never carry holds, so
Migrate Pool captures every hold on the source pool (including its own, such
as offsite receipts) into a temporary file before the cutover, then reapplies
them once the migrated pool has been imported under the source pool's name —
in both destination modes. In holding mode the holds are released after
capture and before the source pool is destroyed (a held snapshot cannot be
destroyed, so the destroy would fail otherwise). Holds are never placed on
the holding-pool copy, so removing the migration namespace cannot fail on a
hold. If the cutover fails or is cancelled after the holds were released,
the captured file is kept and its path logged, together with the
`zfsreapplyholds --apply` command that restores the holds once the pool is
imported again. Holds placed on the source pool *while* a migration is
running (after the capture step) are not preserved.

After a successful cutover, if the migrated pool is enrolled in two-node iSCSI
(`POOL_TARGET`), a follow-up `repair-iscsi-luns` step rebuilds its backstores
and LUN mappings and rescans the compute host automatically.
Cutover refuses to start while the
pool's scrub is running or paused. The pool hosting the root filesystem is
never offered for migration, and a pool with no datasets is never offered as
a source (there is nothing to copy); if the Disks-page pool selector points
at such a pool when you start Migrate Pool, the run refuses to open with an
explanation instead of silently switching to another pool.

### Workload profiles

Dataset tuning lives on the [Datasets](#datasets-tab) tab: select one or
more datasets there and use **Apply Profile…** to change live properties
with `zfs set`, **Rewrite Data** to restripe existing blocks in place, and
**Advanced: Manage Profiles…** to maintain the profiles themselves. Profiles
hold dataset-scope properties (recordsize, compression, atime, logbias,
sync, primarycache, special_small_blocks, and the creation-only
volblocksize). The pool's blocksize (ashift) is pool-scope and cannot be
changed on a live pool — it is recorded in a profile for information only;
use Migrate Pool to rewrite a pool with a different blocksize.

### Actions

The pool- and disk-scoped actions (Create Pool, Add Data Vdev, Expand Vdev,
Replace, Detach, Add Infra Vdev, Migrate Pool, SMART Details, Surface Test)
are enabled in the **Inventory and Topology** view and greyed out in the
**Performance** view; hover for a tooltip pointing at the view where the
action lives.

- **Create Pool…** — open the create-pool wizard to build a new pool from
  unused disks (see [Creating Pools](#creating-pools)). Storage host only on
  two-node systems; disabled while a dataset action is running. The system
  boot disk and its partitions never appear in the disk picker.
- **Add Data Vdev…** — add a new data vdev to an existing pool (see
  [Add Data Vdev](#add-data-vdev)). Storage host only on two-node systems;
  disabled while a dataset action is running.
- **Expand Vdev…** — expand a pool vdev by attaching a device: convert a
  stripe to a mirror, grow a mirror, or expand a raidz vdev (see
  [Expand Vdev](#expand-vdev)). Storage host only on two-node systems;
  disabled while a dataset action is running. Raidz expansion additionally
  requires OpenZFS 2.3+ in the running kernel module — without it, raidz
  rows are greyed and only the mirror-related tasks are available.
- **Replace…** — replace a pool member with an eligible disk and watch the
  resilver (see [Replace](#replace)). Storage host only on two-node systems;
  disabled while a dataset action is running.
- **Detach…** — detach a member from a mirror vdev (see [Detach](#detach)).
  Storage host only on two-node systems; disabled while a dataset action is
  running.
- **Add Infra Vdev…** — add a special, log (SLOG), or cache (L2ARC) vdev (see
  [Add Infrastructure Vdev](#add-infrastructure-vdev)). Storage host only on
  two-node systems; disabled while a dataset action is running.
- **Migrate Pool…** — copy a pool to new disks (or via a holding pool) to
  change its topology, then swap (see [Migrate Pool](#migrate-pool)). Storage
  host only on two-node systems; disabled while a dataset action is running.
- **SMART Details** — dumps `smartctl -a` output for the selected disk to the
  GUI log panel. Requires a single disk to be selected and `smartctl` to be
  installed; otherwise a warning is logged.
- **Surface Test…** — run a SMART surface self-test on the selected HDD (see
  [Surface Test](#surface-test)). Storage host only on two-node systems.
- **Refresh** — reloads the disk inventory and topology from cache.

### Surface Test

A surface test is a SMART self-test run by the drive's own firmware. **Fast**
(`smartctl -t short`, ~2 minutes) reads a sample of the surface; **Slow**
(`smartctl -t long`, typically hours) reads the entire disk. The test:

- runs **independently** — it continues on the disk even if the GUI closes or
  the machine reboots, and multiple disks can be tested at the same time;
- is **cancelable** — select the disk and click Surface Test… again (Cancel
  Test), or cancel it from the Dashboard's Running Tasks;
- shows **live status and ETA** in the Disk Inventory's *Wear/Test* column
  (`42% (1h 23m)` while running, then `Passed`/`Failed`/`Aborted`/`Canceled`;
  SSDs and NVMe devices show their wear percentage in the same column);
- adds disk load, so I/O slows while it runs (safe on pooled disks).

### Feature requirements

| Feature                                                                        | Minimum OpenZFS                                                                                       |
| ------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------- |
| Read-only Disks views                                                          | 2.1+                                                                                                  |
| Apply Profile (live property changes)                                          | 2.1+                                                                                                  |
| Rewrite Data                                                                   | 2.3.4+/2.4+ (`zfs rewrite`), plus the pool's `physical_rewrite` feature                               |
| Create Pool                                                                    | 2.1+ (standard `zpool create`; no separate feature gate)                                              |
| Add Data Vdev / Expand Vdev (mirror tasks) / Replace / Detach / Add Infra Vdev | 2.1+ (standard `zpool add`/`attach`/`replace`/`detach`; no separate feature gate)                     |
| RAIDZ expansion (Expand Vdev on a raidz group)                                 | 2.3+                                                                                                  |
| Migrate Pool                                                                   | 2.1+ (standard `zfs snapshot`/`send`/`receive` and `zpool export`/`import`; no separate feature gate) |

## Pools Tab

This tab shows every pool known to the system (from `zpool list`), pools
that are present but not yet imported (`zpool import`), and pools that you add manually. The tab also contains the **Scrub Manager** for
starting, pausing, resuming, and stopping pool scrubs.

### Pool table

Columns: **Pool**, **Offsite**, **Health**, **Errors**, **Size**, **Alloc**, **Free**, **Freeing**,
**Ckpoint**, **Frag**, **Cap**.

Multiple pools can be selected at once (Ctrl+click or Shift+click). Most
actions operate on every selected row.

**Pool name column:**

| Style         | Meaning                                                                                                              |
| ------------- | -------------------------------------------------------------------------------------------------------------------- |
| **Red**       | Pool is online or importable but *not* in the registry. Select the pool, click **Add** then **Save** to register it. |
| Orange        | Pool is registered but currently offline.                                                                            |
| Default color | Pool is registered and online.                                                                                       |

The **Offsite** column shows a checkbox for every registered pool. Checking it
marks that pool as an offsite candidate; the Offsite tab detects an online candidate at run time. Unregistered pools cannot be marked as offsite candidates

**Health column:**

| Style          | Meaning                                                                               |
| -------------- | ------------------------------------------------------------------------------------- |
| Green          | `ONLINE`                                                                              |
| Blue, bold     | `IMPORTABLE` (the pool is present but is not imported)                                |
| Orange, bold   | `DEGRADED`(a device in the pool is not operational but the pool is still operational) |
| Orange, normal | `OFFLINE` (the pool is registered but not ONLINE or IMPORTABLE)                       |
| Red            | Any other state (`FAULTED`, `UNAVAIL`, `REMOVED`, …)                                  |

**Errors column:**

| Style             | Meaning                                                                |
| ----------------- | ---------------------------------------------------------------------- |
| Green             | `No errors` — `zpool status` reports no data or vdev errors            |
| Red, bold         | Error summary. Vdev READ/WRITE/CKSUM counters or permanent data errors |
| Default color `—` | Pool is offline or status could not be obtained                        |

### Actions — Pool Registry

| Button      | Behavior                                                                                                                                                    |
| ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Watch**   | Opens a [Pool Watch window](#pool-watch-windows) for the selected online registered pool. Multiple watch windows are supported.                             |
| **Details** | Writes `zpool status` output and `zpool get all` output for the single selected pool to the log panel                                                       |
| **Add**     | Adds the selected unregistered pool to the registry (or opens a dialog to type a name if none is selected)                                                  |
| **Remove**  | Removes all selected registered pools from the registry (not from ZFS) after confirmation                                                                   |
| **Import**  | Enabled only when at least one selected pool is `IMPORTABLE`. Imports those pools directly, or opens a dialog listing importable pools if none are selected |
| **Export**  | Confirms, then runs `zpool export` on all selected online pools                                                                                             |
| **Save**    | Saves registry changes; turns **red** while there are unsaved changes                                                                                       |
| **Revert**  | Reloads registry from the last saved settings                                                                                                               |
| **Refresh** | Re-runs `zpool list`, rescans importable pools, and refreshes the table                                                                                     |

Action buttons enable or disable automatically based on the current selection.
For example, **Watch** is only available when at least one selected pool is
registered and online, **Details** requires exactly one selected pool,
**Export** requires at least one selected online pool, and **Import** is
enabled only for `IMPORTABLE` pools.

The importable-pool scan runs in the background on a schedule. Click **Refresh** to force an immediate rescan.

Right-click any cell to open a context menu with **Copy** actions (cell value
or full row, tab-separated) and **Send details to log**, which writes the raw
`zpool get all` output for the selected pool to the log panel. **Send details
to log** requires a single selected pool.

### Scrub Manager

Below the pool registry is the Scrub Manager, separated by a draggable
divider. It maintains a queue of pending, active, paused, and finished
scrubs. The queue is saved to disk automatically and survives GUI restarts.

#### Controls

| Control                  | Purpose                                                                    |
| ------------------------ | -------------------------------------------------------------------------- |
| **Simultaneous scrubs**  | Target number of scrubs running at the same time (1–10). Default: **1**.   |
| **Refresh every (s)**    | How often the scrub status table updates (1–300 seconds). Default: **10**. |
| **System weekly scrub**  | Enable the ZFS pre-installed weekly scrub timer for every registered pool  |
| **System monthly scrub** | Enable the ZFS pre-installed monthly scrub timer for every registered pool |

The system-scrub toggles are independent of the ZFS Utilities schedule.
They modify systemd timer units directly and persist across GUI restarts.

#### Scrub status table

Columns: **Pool**, **Status**, **Progress**, **Last Scrub**, **Scan Line**.

`Last Scrub` shows the date the last scrub finished or was canceled; it is
blank (`—`) if the pool has never been scrubbed.

`Scan Line` shows additional information provided by ZFS.

Drag rows to reorder scrub priority — pools at the top of the list are
preferred over lower ones when the manager chooses the next scrub to start. The order is saved with the scrub queue and
survives GUI restarts.

Multi-select rows with Ctrl+click or Shift+click, then use the action
buttons to control them. 

#### Actions — Scrub Manager

| Button                      | Behavior                                                                                                                                                                           |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Start Scrub**             | Adds selected pools to the pending queue. Selected pools that are currently paused are re-queued as pending. The manager automatically starts them when a scrub slot is available. |
| **Pause Scrub**             | Pauses selected active or pending scrubs (`zpool scrub -p`)                                                                                                                        |
| **Resume Scrub**            | Returns selected paused pools to the pending queue. They resume when a scrub slot is available and do not preempt scrubs that are already running.                                 |
| **Stop Scrub**              | Stops selected scrubs (`zpool scrub -s`) and removes them from the queue                                                                                                           |
| **Add Profile to Schedule** | Saves selected pools and all settings as a scheduled profile. When the profile runs, it is as if the **Start Scrub** button were clicked.                                          |

After any scrub action, the status table refreshes in a short burst so state
changes appear quickly even when the normal refresh interval is long.

Scrub actions are independent and run simultaneously with backup, restore, prune, and dataset-deletion
jobs.  They use live `zpool status` to decide whether a requested transition is
valid, so pressing **Pause Scrub** does not fail just because a backup is
running on a dataset in the same pool. (Backups may temporarily pause some scrubs while the backup is running.)

#### How the queue works

1. **Pending** — pools waiting to be scrubbed. A pool is added here when
   you press **Start Scrub**, even if `zpool status` currently shows a prior
   finished or canceled scrub; the manager still starts a fresh scrub. The manager repeatedly starts pending scrubs until the simultaneous target is reached.
2. **Active** — pools currently **scrubbing**.
3. **Paused** — pools that were paused manually or by lowering the target.
   A manually paused pool stays paused until you press **Resume Scrub** or
   **Start Scrub**; either action returns it to the pending queue. It then
   waits for an available scrub slot and does not preempt running scrubs.
   Scrubs paused only because the target was lowered are resumed automatically
   when the target is raised again or a running scrub finishes.
4. **Finished** — pools whose scrubs were completed or were canceled. Finished
   entries are automatically replaced when a new scrub starts on the same pool.

If you lower the simultaneous target below the current active count, the
manager pauses the newest active scrubs. If you raise it, pending scrubs are started or paused scrubs are resumed.

Externally-started scrubs (e.g. from the command line or a systemd timer)
are detected automatically and incorporated into the active, paused, or
finished buckets. A 30-second grace period prevents freshly-started scrubs
from being mistakenly marked finished while ZFS is still initializing them.

---

### Pool Watch Windows

The **Watch** action on the Pools tab opens an **independent** window for
the selected pool. Each window:

- Has its own dataset tree, refreshed every 30 seconds
- Starts collapsed; use **Expand All** / **Collapse All**
- Can be opened for multiple pools simultaneously
- Clicking **Watch** again for a pool that already has a window brings that
  window to the front instead of creating a duplicate

The list inside a Pool Watch window follows the same conventions as the
[Datasets tab](#datasets-tab).

---

## Datasets Tab

This tab displays a hierarchical, collapsible tree of all datasets, snapshots,
and hold tags.

### Tree conventions

The dataset tree uses typography to indicate row kind:

| Style            | Meaning                                                   |
| ---------------- | --------------------------------------------------------- |
| **Bold**         | Pool root dataset (top-level row)                         |
| Normal           | Regular dataset                                           |
| Normal `[clone]` | Dataset that is a ZFS clone (origin shown in last column) |
| *Italic*         | Snapshot or hold tag                                      |

Holds are shown as children of their snapshot. Expanding a snapshot
row reveals any hold tags attached to it.

The **Origin / Clones** column shows:

- For clone datasets: the origin snapshot the clone was created from
- For snapshots with dependent clones: a comma-separated list of clone
  dataset names
- Empty for all other rows

Unmounted filesystems and snapshots are shown in **teal** text so you can spot
at a glance which items are not currently browseable. Each snapshot has its own
mount indicator; the parent dataset's mount state is shown separately on the
parent row.

### Snapshot and hold actions

The list supports multi-select; action buttons are enabled or disabled
based on what is selected.

| Button                         | Enabled when                                                                                                                          | Behavior                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Snapshot**                   | Exactly one dataset is selected                                                                                                       | Creates a new snapshot (prompts for name; suggests `manual-YYYY-mm-ddTHH:MM`)                                                                                                                                                                                                                                                                                                                                                                    |
| **Delete**                     | Only snapshots and/or holds selected                                                                                                  | Releases the selected hold tags, then destroys the selected snapshots (`zfs destroy`). If a selected snapshot still has holds that were not selected, the operation is aborted and the unselected hold tags are listed so you can select them as well.                                                                                                                                                                                           |
| **Add Hold**                   | At least one snapshot selected                                                                                                        | Prompts for a tag (default `keep`) and applies it to each selected snapshot                                                                                                                                                                                                                                                                                                                                                                      |
| **Rollback**                   | Exactly one snapshot selected                                                                                                         | Rolls the dataset back to that snapshot (destroys newer snapshots and data updates)                                                                                                                                                                                                                                                                                                                                                              |
| **Browse**                     | Exactly one mounted filesystem, snapshot, or volume partition selected                                                                | Opens the selected item in the default file manager. Filesystems (including pool root datasets) open at their ZFS mountpoint; snapshots open via `.zfs/snapshot/<name>`; volume partitions open at their loop-mount directory.                                                                                                                                                                                                                   |
| **Mount**                      | One or more mountable filesystems, snapshots, or volumes selected                                                                     | Mounts each selected filesystem (`sudo zfs mount`) or triggers ZFS auto-mount for each selected snapshot. Unmounted ancestor datasets are mounted first so the target's mountpoint is not hidden. A selected volume is attached to a read-only loop device and its partitions are listed under the volume's entry (see below). Partitions labeled `No filesystem` cannot be mounted. Disabled for holds.                                         |
| **Unmount**                    | One or more mounted filesystems, snapshots, volume partitions, or loop-attached volumes selected                                      | Unmounts each selected filesystem (`sudo zfs unmount`) or snapshot (`sudo umount` on its `.zfs/snapshot/<name>` path). Pool root datasets can be unmounted. Unmounting a filesystem also unmounts its mounted children (see the note below). Unmounting a volume detaches its loop device after unmounting its mounted partitions. If processes are still using an item, a warning dialog lists them and asks you to close them before retrying. |
| **Apply Profile…**             | Every selected item is a pool/dataset row (filesystem or volume); snapshots, holds, and volume partitions in the selection disable it | Shows the workload-profile picker **once** and applies the chosen profile equally to every selected dataset. A preview lists the exact `zfs set` commands; profiles that may be unsafe (e.g. `sync=disabled`) require explicit confirmation. Applying to a pool root sets pool-wide inheritance defaults. See [Workload profiles](#workload-profiles).                                                                                           |
| **Rewrite Data**               | Every selected item is a filesystem dataset, and OpenZFS 2.3.4+/2.4+ with the pool's `physical_rewrite` feature                       | Runs `zfs rewrite -P -r -x -v <mountpoint>` on each selected dataset in turn, physically rewriting existing blocks so they match the current properties (see [Workload profiles](#workload-profiles)). Volumes cannot be rewritten. Unmounted datasets are mounted temporarily and returned to their prior state. This may take a long time and cannot be undone.                                                                                |
| **Advanced: Manage Profiles…** | Always                                                                                                                                | Opens the workload profile manager: add, edit, delete, or reset profiles (built-in profiles are immutable). See [Workload profiles](#workload-profiles).                                                                                                                                                                                                                                                                                         |
| **Refresh**                    | Always                                                                                                                                | Re-reads all datasets, snapshots, and holds while preserving the tree's vertical scroll position and current selection whenever possible.                                                                                                                                                                                                                                                                                                        |
| **Expand Selected**            | One or more pool/dataset/snapshot rows selected                                                                                       | Recursively expands each selected row and its descendants.                                                                                                                                                                                                                                                                                                                                                                                       |
| **Collapse All**               | Always                                                                                                                                | Collapses the entire tree                                                                                                                                                                                                                                                                                                                                                                                                                        |
| **Show Big Stuff**             | Exactly one pool root dataset selected                                                                                                | Runs [`zfsshowbigstuff`](../commands-and-modules/commands.md#zfsshowbigstuff) on the selected pool and streams the output to the log panel. Useful for quickly finding the largest datasets in a pool.                                                                                                                                                                                                                                           |

Right-click any cell for a context menu:

- **Copy** — copies the clicked cell value
- **Copy row** — copies the full row (tab-separated)
- **Copy full name** — copies the fully-qualified dataset or snapshot name
  (e.g. `pool/data/dataset-a@offsite-…`). For hold tags,
  this copies the parent snapshot name.
- **Send details to log** — logs all ZFS properties of the selected dataset
  or snapshot to the bottom panel (holds log their tag, snapshot, and dataset
  instead of fetching properties). This is useful for diagnostics and for
  checking property values that are not shown in the tree columns.

!!! note "Unmounting a parent dataset cascades to its children"
    Unmounting a filesystem also unmounts any of its mounted children. For
    example, unmounting `zfstest3/zfstest2` also unmounts
    `zfstest3/zfstest2/zfstest1`. This is inherent ZFS/Linux behavior, not a
    GUI limitation: a child's mount always lives underneath its parent's
    mountpoint, so a parent cannot be unmounted while a child is still mounted
    beneath it. The plain `zfs unmount` command behaves the same way. If you
    want only one dataset unmounted, unmount the child (leaf) dataset and
    leave its parents mounted.

### Mounting ZFS volumes (zvols)

A ZFS **volume** is a block device, not a filesystem, so it cannot be mounted
directly. Clicking **Mount** with a volume selected instead attaches the
volume's `/dev/zvol/…` device to a **read-only loop device** with partition
scanning (`losetup --find --show --partscan --read-only`). The attach is
read-only because these volumes are often live VM disks (in use via iSCSI) or
active backup targets; a read-write attach could corrupt them.

Once attached, the volume's entry in the Datasets tree lists what the loop
device contains:

- **Partitioned volume** — one row per partition (`loop0p1`, …). The row's
  Type column shows the filesystem (`ext4`, `xfs`, …). Each partition with a
  filesystem can be mounted with **Mount** (read-only, under
  `/mnt/zfsutilities/<volume-path>/<partition>`) and then browsed with
  **Browse**. A partition without a filesystem is listed with Type
  `No filesystem` and cannot be mounted or browsed.
- **Whole-device filesystem** — if the volume has no partition table but does
  have a filesystem, the loop device itself (`loop0`) is listed as a single
  mountable/browseable row.

Unmounting a mounted partition row (`sudo umount`) releases just that
partition. Unmounting the volume row itself unmounts any mounted partitions
and then detaches the loop device (`losetup -d`), removing the partition rows
from the tree.

---

## Retention Tab

This tab manages per-pool retention policies (see also
[Retention Policies](retention.md)).

### Pool selector and policy editor

The drop-down list at the top lists `default` plus every pool with an
explicit entry. Selecting a pool loads its bucket list into the editor
table; edits show **Unsaved changes** in orange until you click **Save**
or **Revert**.

The label above the editor table shows which pool is currently being edited
(e.g. *"Editing retention policy for pool: default"*).

### Editor table

The editor table has four columns:

- **Bucket** — the single-letter bucket key (`d`, `w`, `m`, `s`, or a custom
  letter). ZFSutilities groups snapshots by this letter during pruning. You can add
  or remove bucket rows with the **Add Bucket** / **Remove Bucket** buttons.
- **Type** — a read-only display name derived from the bucket letter (`d`→Daily,
  `w`→Weekly, `m`→Monthly, `s`→Offsite). Custom buckets show the uppercase letter.
  This column is gray to indicate it is not editable.
- **Retain Count** — how many snapshots in this bucket to keep. When a bucket
  exceeds this count, older snapshots become candidates for deletion.
- **Min Age** — minimum age in **days** before a snapshot in this bucket can be
  pruned. A snapshot younger than this is protected even if the bucket is over
  its Retain Count. Setting Min Age > 0 while Retain Count is 0 has no effect;
  the status line warns you when this happens.

The status line below the table turns **orange** when there are unsaved changes
or when a Min Age is set on a bucket whose Retain Count is 0.

### Policy actions

| Action                      | Behavior                                                                                                                                                                                                          |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Add Policy**              | Creates a new pool-level retention entry seeded from `default`. A dialog offers a drop-down list of known and online pools that do not already have a policy, or a free-form entry if all candidates are covered. |
| **Remove Policy**           | Deletes the currently-selected pool's entry (after confirmation). Blocked for `default`. The pool is removed from the policy editor and falls back to the `default` policy.                                       |
| **Add Bucket**              | Adds a new bucket row to the editor table                                                                                                                                                                         |
| **Remove Bucket**           | Removes the selected bucket row                                                                                                                                                                                   |
| **Save**                    | Saves the policy for the currently-selected pool, any pending bucket edits made to other pools, the prune snapshot label, and the advanced prune options                                                          |
| **Revert**                  | Discards all pending edits (for every pool) and reloads the saved policy, prune label, and advanced prune options                                                                                                 |
| **Add Profile to Schedule** | Saves a snapshot of current prune settings (label + selected pools) as a scheduled profile                                                                                                                        |
| **Recall Profile**          | Loads a previously-saved retention profile into this tab for editing or on-demand execution                                                                                                                       |

### Prune runner

Below the editor, a multi-select list shows the pools that `zfscleanup` would
prune: the pools registered in the JSON config (`config.pools`) that are
currently online, or all online pools when `config.pools` is empty. Drag rows to
reorder the pool list. Select one or more, set the snapshot label (default
`dailybackup`), and click **Prune** to run a prune job for each pool in
sequence. Pools without an explicit policy are pruned using the `default`
policy.

The **Prune** button becomes **Cancel** while a prune job is running;
output streams to the log panel at the bottom of the window, and any
interactive prompts may be responded to in the **Input** entry next to the **Send**
button.

#### What happens during a prune

By default, for each selected pool, the GUI runs a prune job that applies the
pool's retention policy to all datasets. It prunes in three phases:

1. offsite
   same-month deduplication (only for `@offsite` snapshots), 

2. same-day
   deduplication within each bucket, and 

3. bucket-count enforcement. 
   The most
   recent snapshot in each bucket is protected as the incremental backup base.

Clone origin snapshots (`c` bucket) are skipped entirely.

Before any snapshot is destroyed, `zfscheckagainst` verifies it is not the
last common snapshot shared with a counterpart dataset (e.g. an offsite pool).

If **Dry Run** is active, deletions are simulated and the log panel shows what
would be deleted without actually destroying anything.

For the full algorithm, see the
[`zfsretain` module reference](../commands-and-modules/modules.md#zfsretain).

#### Ignore retention policies

The **Advanced Prune Options** card lets you change what the **Prune** button
deletes. The **Ignore Retention Policies** toggle sits at the top of the card:
check it to run
[`zfsmassdelsnaps`](../commands-and-modules/commands.md#zfsmassdelsnaps) instead
of `zfscleanup`. In this mode, **Prune** lists every matching snapshot and
deletes them after confirmation, bypassing retention counts, minimum age, and
counterpart snapshot checking (Checkagainst).

Below the toggle, the red **Mass Delete Filters - Danger Zone** frame restricts
which snapshots a mass delete matches:

- **Includes / Excludes / Start With / End With** — dataset name filters passed
  to `zfsbuildfsarray`
- **Snapshot Has** — only snapshots whose full name contains this substring are
  considered
- **Release Holds** — release ZFS holds before deleting; this one applies in
  both normal and ignore-retention prune

The filter fields only apply when **Ignore Retention Policies** is checked, so
they are greyed out otherwise; **Release Holds** stays editable in both modes.
An inline caption under the toggle restates this, so the card explains itself
without the manual.

Dry Run previews the affected snapshots without deleting anything. Before
confirming a real delete, the candidate list is followed by an estimated amount
of disk space that would be freed (the sum of each snapshot's `used` property).
When **Release Holds** is enabled, holds are released automatically without an
additional confirmation for each snapshot.

!!! warning
    Ignore mode can delete snapshots that are still needed for incremental
    backups. Use it only when you are certain the snapshots are no longer needed.

---

## Checkagainst Tab

This tab edits the [`zfscheckagainst`](../commands-and-modules/modules.md#zfscheckagainst)
table used for verification when deleting snapshots.

The table is split into four sections:

- **Backup-derived entries** — rows generated from active Backup tab
  send/receive steps.
- **Offsite-derived entries** — rows generated from active Offsite tab
  send/receive steps.
- **User entries** — manually maintained rows that always override
  derived rows for the same `(label, source_root)` pair.
- **Merged fss table** — read-only preview of the effective runtime table
  after the active derived sections and user entries are merged.

`zfscheckagainst` uses the merged table to map a snapshot to its
counterpart dataset(s). Before a snapshot is deleted, the script verifies
that the candidate snapshot is not the last common snapshot shared with any
counterpart. If the counterpart pool is offline and the snapshot label is
`offsite`, hold tags are used as receipts to decide whether deletion is
safe.

For the full algorithm and return codes, see the
[`zfscheckagainst` module reference](../commands-and-modules/modules.md#zfscheckagainst).

### Layout

The two derived sections are read-only tables. Each has an **Active**
checkbox at the top:

- When checked, the rows in that section are included in the merged
  runtime table.
- When unchecked, the section is ignored.

The **User entries** section is an editable, reorderable table.
Drag rows to reorder them; click a cell to edit it.

| Column               | Meaning                                                                                                                                                                                                                                                 |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Snapshot label**   | Snapshot label to match. This entry applies only to snapshots carrying this label (e.g. `dailybackup`, `offsite`).                                                                                                                                      |
| **Source root**      | The root of the Source dataset tree this row applies to. A snapshot's dataset must be this root or one of its descendants. `<offsite>` may appear anywhere. In effect, it creates a separate row for each offsite-designated pool.                      |
| **Destination root** | Destination dataset tree where the counterpart is expected. The counterpart is built by replacing the source-root prefix of the snapshot's dataset with this value. `<offsite>` may appear anywhere and expands per offsite-candidate pool at run-time. |
| **Comment**          | Optional note stored in the saved configuration and shown in this table. Use for documenting the entry's purpose.                                                                                                                                       |

Hover your mouse pointer over any column header to see a tooltip explaining the field.

### How the counterpart dataset is constructed

`zfscheckagainst` builds the counterpart dataset by replacing the snapshot's
source-root prefix with the destination-root prefix.

For example, with a snapshot dataset of `poolA/data/vm-101-disk-0`:

| Source root        | Destination root   | Counterpart dataset              |
| ------------------ | ------------------ | -------------------------------- |
| `poolA/data`       | `poolB/poolA/data` | `poolB/poolA/data/vm-101-disk-0` |
| `poolB/poolA/data` | `poolA/data`       | `poolA/data/vm-101-disk-0`       |

For the project's normal Backup/Restore pool names, a snapshot on
`threeamigos/proxmox/vm-101-disk-0@dailybackup-…-d` produces:

| Source root            | Destination root       | Counterpart dataset                          |
| ---------------------- | ---------------------- | -------------------------------------------- |
| `threeamigos`          | `fivebays/threeamigos` | `fivebays/threeamigos/proxmox/vm-101-disk-0` |
| `fivebays/threeamigos` | `threeamigos`          | `threeamigos/proxmox/vm-101-disk-0`          |

### Special value `<offsite>`

`<offsite>` may be used anywhere in the Source root or Destination root
column. Every occurrence is replaced at run time with every pool marked as
an offsite candidate in the [Pools tab](#pools-tab).

Examples using a snapshot dataset of `poolA/data/vm-101-disk-0`:

| Source root      | Destination root | Counterpart dataset(s)                                                |
| ---------------- | ---------------- | --------------------------------------------------------------------- |
| `poolA/data`     | `<offsite>`      | `z22tb/poolA/data/vm-101-disk-0`, `z40tb/poolA/data/vm-101-disk-0`, … |
| `<offsite>/temp` | `temp`           | `temp/vm-101-disk-0` (after replacing `z22tb/temp`, `z40tb/temp`, …)  |

### Merged fss table preview

The **Merged fss table** section at the bottom of the tab is a read-only,
live-updating preview of the table that `zfscheckagainst` will actually use.
It is built by merging the active derived sections and the user entries with
this precedence for the same `(label, source_root)` key:

1. **User entries** — highest precedence.
2. **Offsite-derived entries**.
3. **Backup-derived entries** — lowest precedence.

Rows that are missing a required field (Snapshot label, Source root, or
Destination root) are not shown in the preview, because they cannot be used
by `zfscheckagainst`.

`<offsite>` is displayed as a literal placeholder in the preview. Expansion
to the actual offsite-candidate pools happens at run time inside
`zfscheckagainst`.

### Derived entries

Derived rows are generated automatically from the Backup and Offsite tab
send/receive steps. When the Checkagainst tab is first opened, the
Backup-derived and Offsite-derived sections are populated immediately from
the current Backup/Offsite configurations, so the tables should never be
empty if steps are configured.

For each active step `source → dest` with label `dailybackup` (Backup) or
`offsite` (Offsite), two rows are produced:

- **Forward**: `source <actual_destination> <label>`
- **Reverse**: `<actual_destination> source <label>`

The actual destination root is the destination path that `zfs-send-receive`
will use. When the Offsite Destination column contains `<offsite>`, the
derived row keeps the placeholder as-is. `zfscheckagainst` expands it to
every pool marked as an offsite candidate in the [Pools tab](#pools-tab) at
run time, so one derived row can verify against all candidate pools.

If you edit the Backup or Offsite tab and return to Checkagainst while it is
still open, the **Get Entries** button turns **red** to show that the derived
rows no longer match the current Backup/Offsite configurations. Click **Get
Entries** to refresh the derived sections; the **Save** then turns red so you can
save the updated rows.

### Actions

| Button          | Behavior                                                                                                                                                                                                                           |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Get Entries** | Refresh the Backup-derived and Offsite-derived sections from the current Backup/Offsite configs. The button label turns **red** when the displayed derived rows are stale; clicking it updates the tables and marks the tab dirty. |
| **Add pair...** | Open an assistant that asks for snapshot label, source root, destination root, and comment; it appends the forward row **and** the reverse row to the user table.                                                                  |
| **Add Row**     | Appends a new empty row to the user table.                                                                                                                                                                                         |
| **Remove Row**  | Deletes the selected row(s) from the user table.                                                                                                                                                                                   |
| **Save**        | Saves the whole `checkagainst` page after validation. Turns **red** while there are unsaved changes.                                                                                                                               |
| **Revert**      | Discards all changes and reloads from the last saved page.                                                                                                                                                                         |

A status label below the table shows **orange** "Unsaved changes" while
edits are pending, or a **red** validation error if a row is missing a
required field (Source root, Destination root, or Snapshot label).

### User entries

The **User entries** table is maintained manually: use **Add pair...** or
**Add row** to create rows, **Remove Row** to delete them, and **Save** to
persist.

---

## Logs Tab

Browse, view, search, and manage session log files produced by every GUI run,
scheduled cron job, and direct CLI script execution.

### Log list (top pane)

A sortable table with columns:

| Column        | Description                                                              |
| ------------- | ------------------------------------------------------------------------ |
| **Date/Time** | When the session started. Default sort is **descending** (newest first). |
| **Type**      | `backup`, `offsite`, `restore`, `prune` — the operation type             |
| **Name**      | `gui` for GUI runs, or `profile-<name>` for scheduled/cron runs          |
| **Status**    | `Done`, `Failed`, `Cancelled`, `Running`, `Warn`, or `Fatal`.            |
| **Log Size**  | Size of the log file on disk                                             |
| **Duration**  | Total elapsed time in `HH:MM:SS`                                         |
| **Transfer**  | Total bytes transferred during ZFS send/receive steps                    |

Click any column heading to change the sort order.

Click any row to load that log into the viewer below. Hold Ctrl or Shift to
select multiple rows; the **Delete Selected** action and the right-click menu
operate on the full selection.

Right-click any row to open a context menu:

- **Copy path** — copy the full log file path to the clipboard
- **Delete selected log(s)** — remove every selected log file after confirmation

### Log viewer (bottom pane)

- **Text view** — The currently-selected log appears here.

- **Level filter** — a dropdown above the text view lets you show only messages
  at the selected priority or higher. It works the same way as the bottom-panel
  **Log** level filter and does not affect what is stored in the log file.

- **Live tail** — when a log with status **Running** is selected, the viewer
  automatically loads all existing content and shows new lines as they arrive.
  Auto-scroll to the bottom occurs only if the scroll position was already near
  the bottom; if you have scrolled up to read earlier output, your position is
  preserved.

- **Large logs** — log files larger than **1 MB** are opened tail-first. The
  viewer shows a header indicating that the beginning is skipped and displays a
  **Load Full Log** button. Clicking it prompts for confirmation, then reads the
  entire file from the start. This prevents the GUI from hanging if a session
  log grows very large.

- **Pop Out** — a button in the search bar detaches the entire viewer into an independent window. While popped out,
  the Log Viewer pane is removed from the Logs tab; it is restored when the
  pop-out window is closed or docked again.

- **Search bar** — above the text view:
  
  - **Search entry** — type some search text and press Enter (or click **Search**)
  - **Search** button — finds and highlights every occurrence. The current
    match is highlighted in **orange**; all other matches are highlighted in
    **yellow**.
  - **Reset** button — clears highlights and empties the search field
  - **Previous / Next** arrow buttons — cycle through matches, wrapping around
    at the first/last match. A counter shows the current position (e.g. `3 / 12`).
    The viewer scrolls so the current match is visible.
  - Searches are **case-insensitive**.
  - The search query is **retained** when you switch to a different log file;
    the search automatically reruns against the newly loaded log.
  - While you watch a **Running** log, the viewer shows the new output;
    **Previous / Next** keep working and matches in the newly arrived lines are
    added to the highlights and counter without disturbing your scroll
    position.

### Retention control

A **success-rate summary** appears above the log list (e.g. *"Success rate (30 days): 95 % (19 / 20)"*). It is computed from the backup history file and updates automatically every time the log list refreshes.

A **Retention (days)** spin button above the log list sets how long logs are kept. The default is **30 days**. Old files are pruned automatically
when the GUI starts and whenever a scheduled run starts; they can also be
removed manually via the **Prune Old** action button.

!!! warning "Setting retention to 0"
    A value of **0** means **all** log files will be deleted. Use this with caution.

### Actions

| Button              | Behavior                                                                                                                                                                         |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Refresh**         | Rescan `/var/log/zfsutilities/sessions/` and refresh the list. The list also refreshes automatically whenever files are created, modified, or deleted in the sessions directory. |
| **Delete Selected** | Remove the selected log file(s) after confirmation                                                                                                                               |
| **Prune Old**       | Delete all logs older than the retention setting                                                                                                                                 |

---

## Dataset Selection Criteria

The **Advanced** expander on the [Backup](#backup-tab), [Offsite](#offsite-tab),
and [Restore](#restore-tab) tabs controls which datasets are included in an
operation. These settings are passed to
[`zfsbuildfsarray`](../commands-and-modules/modules.md#zfsbuildfsarray).

On the **Backup** tab, the same criteria (`includes`, `excludes`, `startwith`,
`endwith`) define the dataset list for both the send/receive steps **and** the
post-backup prune step: the prune step re-derives each step's source dataset
list at run time and prunes it on **both sides** — every source dataset and
its mapped destination name (via `zfscleanup`'s explicit `prune_datasets`
mode). When no send/receive steps are active, the prune step is skipped —
no new snapshots were created, so there is nothing to prune.

### Execution sequence

The filters are applied in this order:

1. **Start pool / source dataset** — every dataset under the source pool or
   dataset is enumerated.
2. **Includes** — keep only datasets that match at least one include pattern.
   If no includes are specified, all datasets are kept.
3. **Excludes** — remove any dataset that matches an exclude pattern.
4. **Depth** — limit recursion depth (`0` = root dataset only, `""` = unlimited).
5. **Startwith** — remove all datasets *before* the first match. The match
   itself is kept.
6. **Endwith** — remove all datasets *after* the first match. The match itself
   is kept.

If `startwith` or `endwith` is specified and no dataset matches it, the
operation aborts with an error.

### Fields

| Field         | GUI Widget | Purpose                                                                                                               |
| ------------- | ---------- | --------------------------------------------------------------------------------------------------------------------- |
| **Includes**  | Entry      | Space-separated list of substrings. Only datasets whose full name contains at least one of these substrings are kept. |
| **Excludes**  | Entry      | Space-separated list of substrings. Any dataset whose full name contains one of these substrings is dropped.          |
| **Depth**     | Entry      | Recursion depth passed to `zfs list -d`. `0` = root only, `""` = unlimited.                                           |
| **Startwith** | Entry      | A single substring. All datasets before the first match are discarded.                                                |
| **Endwith**   | Entry      | A single substring. All datasets after the first match are discarded.                                                 |

### Syntax

By default, every pattern is a **substring** match. It can appear anywhere in
the dataset name:

- `data` matches `pool/data` and `pool/data/dataset-a`
- `dataset-a` matches `pool/data/dataset-a`
- `dataset` matches any dataset with `dataset`

Prefix a pattern with `=` to require an **exact** match instead of a substring:

- `=pool/data` matches **only** `pool/data`
- `=pool/data/dataset-a` matches **only** that exact dataset

### Quoting

Patterns may be quoted with double quotes so that spaces become part of the
pattern rather than separators:

- `"dataset a"` — matches a dataset whose name contains `dataset a` (with a space)
- `="my exact dataset"` — exact-match a dataset name that contains spaces

Unquoted strings are split on whitespace, so `dataset a` is two separate patterns
(`dataset` and `a`).

### Examples

**Include only data datasets:**

- Includes: `data`
- Result: only dataset names containing `data` are included.

**Exclude temp and scratch datasets:**

- Excludes: `temp scratch`
- Result: any dataset whose name contains `temp` or `scratch` is skipped.

**Process only dataset-a through dataset-e:**

- Startwith: `dataset-a`
- Endwith: `dataset-e`
- Result: datasets are sorted alphabetically; everything before the first `dataset-a` and
  after the first `dataset-e` is removed.

**Exact-match a single dataset:**

- Includes: `=pool/data/dataset-a`
- Result: only that exact dataset is processed.

## Advanced Options

The **Advanced** expander on the [Backup](#backup-tab), [Offsite](#offsite-tab),
and [Restore](#restore-tab) tabs also exposes the variables below. They control
send/receive behaviour, holds, and verification rather than dataset selection.
The **Advanced Prune Options** expander on the
[Retention](#retention-tab) tab holds the *Ignore retention policies* toggle
and the *Mass Delete Filters* danger-zone frame that restricts mass deletes.

The expander label turns **orange** whenever any value inside the expander
differs from its default, so hidden non-default parameters are visible at a
glance even while the expander is collapsed. When the expander is open, the
differing values themselves are also shown in orange, so you can see exactly
which fields have been changed from their defaults.

| Variable                  | Tabs                     | Type | Purpose                                                                                             |
| ------------------------- | ------------------------ | ---- | --------------------------------------------------------------------------------------------------- |
| **label**                 | Backup, Offsite, Restore | text | Snapshot label for matching and bucket assignment (e.g. `dailybackup`, `offsite`).                  |
| **autoresume**            | Backup                   | Y/N  | `'Y'` = allow resumable-receive tokens to be picked up (`zfs receive -s`).                          |
| **receive_F_option**      | Backup, Offsite          | text | `'F'` = force rollback of destination modifications later than the common snapshot.                 |
| **releaseholds**          | Backup                   | Y/N  | `'Y'` = release holds on snapshots before destroying rather than refusing.                          |
| **doincrementals**        | Backup, Offsite          | Y/N  | `'Y'` = incremental send from the most recent common snapshot; `'N'` = full send.                   |
| **dointermediates**       | Backup, Offsite          | Y/N  | `'Y'` = include all intermediate snapshots (`-I`); `'N'` = skip them (`-i`).                        |
| **allow_destructive**     | Backup, Offsite          | Y/N  | `'Y'` = full copy may destroy an existing destination dataset and its children.                     |
| **verify_after_transfer** | Backup, Offsite          | Y/N  | `'Y'` = after each receive, compare destination snapshot GUID with source; treat mismatch as fatal. |
| **pv_rate_limit**         | Backup, Offsite          | text | Max transfer rate for `pv -L` (e.g. `200M`, `1G`). Empty = no limit.                                |
| **applyholds**            | Offsite                  | Y/N  | `'Y'` = apply `offsite-<pool>` holds after each offsite step.                                       |

For more detail on how these map to the bash engine, see
[Architecture — Send/Receive Decision Flow](../developer-guide/architecture.md#sendreceive-decision-flow)
and [Commands & Modules — zfs-send-receive](../commands-and-modules/modules.md#zfs-send-receive).

---

## Dry Run Mode

A **Dry Run** toggle button appears in the action panel for the **Backup**,
**Offsite**, **Restore**, and **Retention** tabs. When enabled, operations are
simulated without making changes and the button label turns **red** so the
active state is obvious at a glance.

| Tab           | What Dry Run does                                                                                                         |
| ------------- | ------------------------------------------------------------------------------------------------------------------------- |
| **Backup**    | Skips rsync pulls, pre-backup commands, ZFS send/receive (logs what it would do), snapfile cleanup, and retention pruning |
| **Offsite**   | Skips ZFS send/receive (logs what it would do) and hold application                                                       |
| **Restore**   | Skips ZFS send/receive (logs what it would do) for both Part 1 and Part 2                                                 |
| **Retention** | Logs what snapshots would be pruned without deleting them                                                                 |

The toggle state persists while the GUI is running and is reset by clicking it again or on GUI restart.

When you click **Add Profile to Schedule** in a tab, the current dry-run state
is captured in the profile. Scheduled executions of that profile then run in
dry-run mode automatically, independent of the GUI's live toggle. Recalling a
profile loads its saved dry-run flag into the tab so you can review or change it
before re-saving.

## Log Level

The **Log** dropdown in the bottom panel (next to the **Send** button) filters
which messages are shown in the live info panel. It does **not** affect what is
written to log files. Levels are `DEBUG`, `VERB`, `INFO`, `WARN`, and `FATAL` (default: `INFO`).

- `DEBUG` — shows verbose diagnostics
- `VERB` — shows INFO plus extra detail messages
- `INFO` — shows routine progress output
- `WARN` — shows warnings and fatal errors only
- `FATAL` — shows fatal errors only

The setting controls only the bottom-panel viewer. The [Logs tab](#logs-tab)
viewer has its own independent **Level** filter. Both filters use the same
rule: a message is visible when its priority is greater than or equal to the
selected level. Messages without a recognized priority prefix (raw subprocess
output, trailers, etc.) use the implied "(none)" level and are always displayed.

See [Messages — Priority prefixes](../messages/index.md#priority-prefixes)
for details on the priority tokens.

!!! tip "Session log files"
    Every GUI run, scheduled profile run, and direct CLI script execution
    automatically creates a session log file in
    `/var/log/zfsutilities/sessions/`. These files capture both
    `file:line`-prefixed `log_msg` output and raw subprocess stdout/stderr
    (dataset lists, `zfs receive` progress, separator lines, etc.). Use the
    [Logs tab](#logs-tab) to browse and search them.

    When multiple GUI runners are active at the same time (for example, a Backup
    and an Offsite job running concurrently), each runner writes its
    messages to its own session log so the logs do not cross-write.
    
    Scheduled backup profiles also stream rsync pull-step output (both remote
    pulls and local pulls that resolve to the current host) to
    `/var/log/zfsutilities/rsync-pull.log` instead of the session log, so the
    GUI Logs tab is not flooded with file-list progress from routine rsync jobs.
    
    For how the single-writer log mechanism works, see
    [Architecture — Session logging](../developer-guide/architecture.md#session-logging).

## Help Menu

The **Help** menu contains:

| Item                            | Purpose                                                                 |
| ------------------------------- | ----------------------------------------------------------------------- |
| **Documentation**               | Open the embedded documentation viewer                                  |
| **Help with this page**         | Open the viewer scrolled to the section for the currently visible tab   |
| **Set Documentation Editor...** | Choose the external editor for the pencil (edit) icon inside the viewer |
| **About**                       | Version, license, and credits                                           |

### Documentation Viewer

**Help → Documentation** opens a standalone window that renders the
documentation website using an embedded browser.

!!! note "Pre-built content only"
    The embedded viewer serves the last built copy of the documentation
    (`docs/site/`). It does not auto-rebuild when source Markdown files change.
    For live updates while editing, use `startdocserver` and a web browser as
    described in [Documentation Server](../developer-guide/doc-server.md).

The installer creates a symbolic link named **ZFSutilities Documentation**
in the installing user's home directory. This can be used to open the documentation viewer independently of the GUI. Open the link directly, or run `zfsutilities-docs`; the documentation viewer does not require root.

The viewer window includes a toolbar:

| Button | Action                                |
| ------ | ------------------------------------- |
| **←**  | Go back in page history               |
| **→**  | Go forward in page history            |
| **↻**  | Refresh the current page              |
| **⌂**  | Return to the documentation home page |
| **+**  | Zoom in                               |
| **−**  | Zoom out                              |
| **0**  | Reset zoom to 100%                    |

If a page fails to load, a status message appears and the **Home** button resets
the view.

#### Palette Toggle

The Material theme provides a light / dark palette toggle (sun/moon icon at the
top-right of each page). The selected mode persists across sessions via the
browser's local storage and is also remembered by the GUI so the viewer reopens
in the same mode.

#### Remembered State

The viewer remembers its window size, position, maximized state, zoom level,
and the active Material light / dark palette. When the viewer is opened from
the GUI or as root, these values are stored in the `ui_state.docs_viewer`
section of the system GUI configuration file. When it is opened without root
privileges (for example, from the **ZFSutilities Documentation** symlink in a
user's home directory), they are stored in that user's own configuration file
(`$XDG_CONFIG_HOME/zfsutilities/docs_viewer_state.json`, falling back to
`~/.config/zfsutilities/docs_viewer_state.json`). The values are restored the
next time the documentation window opens.

#### Editing Pages

Every documentation page has a pencil icon at the upper-right. Clicking it opens
the source `.md` (markdown) file in the editor configured via **Help → Set Documentation Editor...**

- **Default** — if no editor is configured, the system default application for
  markdown files is used (`xdg-open`).
- **Custom command** — enter any executable path or command name (e.g.
  `gedit`, `/home/dan/MarkText/marktext`, `runuser -u dan xdg-open`).
  The file path is always appended as the final argument.

!!! note "Editor runs as the desktop user"
    The GUI runs as root when it is started, but the editor is automatically
    dropped to the original desktop user so Electron-based editors (such as
    MarkText) do not crash inside their sandboxes.

#### Blocked Links

Links that use unknown URI schemes (anything other than `http://`, `https://`,
`file://`, or `about:`) are cancelled and a brief status message is shown in
the toolbar. This prevents accidental navigation to external sites from the
offline documentation. Directory-style `file://` links are automatically
rewritten to `index.html` before loading.

#### Fallback Mode

If WebKit2 is not installed or the pre-built site is missing, the viewer shows
a plain-text markdown instead of the rendered page.

For how the embedded server and edit links are implemented, see
[Documentation Server](../developer-guide/doc-server.md).

## View Menu

The GUI's **View** menu contains global display actions.

| Item                  | Purpose                                                                                                                                  |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| **Minimize Width...** | Reset every resizable table column to its own minimum width, clear saved column widths, and shrink the main window as narrow as possible |

Choosing **Minimize Width...** flushes any pending save, discards saved widths,
and resets every resizable column to its own minimum width. The action asks for
confirmation before resizing the window.


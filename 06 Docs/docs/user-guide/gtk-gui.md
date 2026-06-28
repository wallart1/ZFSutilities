# GTK GUI Reference

The `zfsutilities_gui.py` application (in `07 GTK + Python/`) is a GTK3
graphical frontend for the ZFSutilities scripts. It must be run as root:

```bash
sudo zfsutilities-gui
```

The installer creates a symbolic link named **ZFSutilities GUI** in the
installing user's home directory. You can also launch the script directly or
add `/usr/local/lib/zfsutilities/current/bin/zfsutilities-gui` to a panel or
start-menu launcher.

All settings are persisted to `/root/.config/zfsutilities.json`, the same
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

## First Run

On a fresh install the JSON config starts empty — no pools, no backup steps,
no offsite steps, and no checkagainst entries. The log panel will show
warnings for each missing section. Configure them through the relevant tabs:

1. **[Dashboard](#dashboard-tab)** — review system health at a glance
2. **[Pools](#pools-tab)** — online pools appear in red; select the pool, click **Add** then **Save**
   to register them. Check the **Offsite** box for any registered pool that will spend time offline. Use the Scrub Manager below the registry to queue, start, pause, resume, and stop scrubs.
3. **[Backup](#backup-tab)** — add rsync pull steps and send/receive steps
4. **[Offsite](#offsite-tab)** — review the automatically detected offsite pool and add offsite backup steps
5. **[Checkagainst](#checkagainst-tab)** — add dataset-counterpart mappings
6. **[Retention](#retention-tab)** — a `default` policy is auto-created. Add per-pool policies with **Add Policy** when needed.

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

The toggle state persists while the GUI is running and is reset on restart.

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

The installer creates a symbolic link named **ZFSutilities Documentation**
in the installing user's home directory. This can be used to open the documentation viewer independently of the GUI. Open the link directly, or run `zfsutilities-docs`; either will prompt for authorization if needed.

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
and the active Material light / dark palette. These values are stored in the
`ui_state.docs_viewer` section of the GUI configuration file and are restored
the next time the documentation window opens.

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
a plain-text message instead of the rendered page.

For how the embedded server and edit links are implemented, see
[Documentation Server](../developer-guide/doc-server.md).

## View Menu

The GUI's **View** menu contains global display actions.

| Item                  | Purpose                                                                                                                                  |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| **Minimize Width...** | Reset every resizable table column to its own minimum width, clear saved column widths, and shrink the main window as narrow as possible |

Column widths across the GUI are normally restored from the saved `ui_state`
when the window opens. All tables use fixed-width, resizable columns hosted
inside scrollable viewports, so the main window can always be shrunk
horizontally even when columns were previously widened.

Choosing **Minimize Width...** discards saved widths and resets every
resizable column to its own minimum width. The action asks for confirmation
before resizing the window.

## Tabs

The sidebar exposes these pages:

| Tab                               | Purpose                                                                                  |
| --------------------------------- | ---------------------------------------------------------------------------------------- |
| [Dashboard](#dashboard-tab)       | At-a-glance system health, recent operations, and warnings                               |
| [Backup](#backup-tab)             | Configure and run [`zfsdailybackup`](../commands-and-modules/commands.md#zfsdailybackup) |
| [Offsite](#offsite-tab)           | Configure and run [`zfssendoffsite`](../commands-and-modules/commands.md#zfssendoffsite) |
| [Restore](#restore-tab)           | Configure and run [`zfsrestore`](../commands-and-modules/commands.md#zfsrestore)         |
| [Schedule](#schedule-tab)         | Manage scheduled jobs                                                                    |
| [Checkagainst](#checkagainst-tab) | Edit the [`zfscheckagainst`](../commands-and-modules/modules.md#zfscheckagainst) table   |
| [Pools](#pools-tab)               | Pool registry + live `zpool list` status + scrub manager                                 |
| [Datasets](#datasets-tab)         | Collapsible dataset tree with inline snapshot/hold management                            |
| [Retention](#retention-tab)       | Per-pool retention policies + prune runner                                               |
| [Logs](#logs-tab)                 | Browse, search, and prune session log files                                              |

## Dataset Selection Criteria

The **Advanced** expander on the [Backup](#backup-tab), [Offsite](#offsite-tab),
and [Restore](#restore-tab) tabs controls which datasets are included in an
operation. These settings are passed to
[`zfsbuildfsarray`](../commands-and-modules/modules.md#zfsbuildfsarray).

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

## Dashboard Tab

The Dashboard provides an at-a-glance overview of ZFS health. It refreshes
automatically every 30 seconds while visible, or manually via the **Refresh**
action button.

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
- Missing backup/offsite/checkagainst configuration
- Unregistered pools
- Stale lock files in `/run/lock/zfs/.locks/`

### Pool Health

A live table from `zpool list` showing:

| Column         | Meaning                                                                                                        |
| -------------- | -------------------------------------------------------------------------------------------------------------- |
| **Pool**       | Pool name, prefixed with a green ● (online), red ● (degraded), or orange ● (other)                             |
| **Capacity**   | Progress bar showing used percentage; turns **red** at the low-space warning threshold or above                |
| **Last Scrub** | Date of the most recent scrub (including the date a scrub was canceled), or *"In progress"* if one is running. |
| **Scrub**      | Current scrub status: progress bar while **scrubbing**, or `paused` / `—` / `finished`                         |

A **Low-space warning threshold** spin button sits above the pool table. It
sets the capacity percentage at which the Dashboard warns about low space.
The default is **80 %** (range 50–95 %). 

### Running Tasks

A unified view of all currently running operations. Select one or more rows
and click **Cancel Selected Tasks** to stop them.

| Task type     | Source                                                                   | Cancel behaviour                                |
| ------------- | ------------------------------------------------------------------------ | ----------------------------------------------- |
| **GUI**       | Backup, Offsite, Restore, or Prune started from their respective tabs    | Graceful cancel (SIGTERM the runner subprocess) |
| **Scrub**     | Pool scrubs started from the Pools tab or detected as externally running | `zpool scrub -s <pool>`                         |
| **Scheduled** | `profile_runner.py` jobs launched by cron                                | SIGTERM the profile-runner process              |

### Recent Operations

A scrollable table showing the last **10** history entries:

| Column        | Meaning                                                                  |
| ------------- | ------------------------------------------------------------------------ |
| **Date/Time** | When the operation finished (`YYYY-MM-DDTHH:MM±TZ`)                      |
| **Type**      | `backup`, `offsite`, `restore`, or `prune`                               |
| **Name**      | GUI label or scheduled profile name                                      |
| **Outcome**   | Coloured icon + text (`✓ success`, `✗ failed`, `⏹ cancelled`, *running*) |

The list refreshes automatically with the rest of the Dashboard.

Each row also stores the operation's session-log path in a hidden column. The
[**View Log**](#actions) action uses this path to jump to the log in the
[Logs tab](#logs-tab).

### iSCSI Issues *(two-node only)*

Compares the expected LUN list against `targetcli` backstores. If any LUN is missing, an orange warning row appears with a **Fix this** button that tries to restore LUNs with encrypted backstores.

This section is hidden entirely on single-node systems.

### Configuration

Shows the current node mode (`single-node` or `two-node`), hostnames, and the
zfsutilities version on each host. In two-node mode the versions of the
storage host and compute host are fetched remotely.

### Actions

| Button                    | Behaviour                                                                                       |
| ------------------------- | ----------------------------------------------------------------------------------------------- |
| **Refresh**               | Re-gather all dashboard data immediately                                                        |
| **Fix Locks**             | Removes stale locks and refreshes the view                                                      |
| **Cancel Selected Tasks** | Cancels the selected rows in the **Running Tasks** list                                         |
| **View Log**              | Switches to the Logs tab and selects the session log for the selected **Recent Operations** row |

---

## Backup Tab

This tab configures and runs the daily backup job ([`zfsdailybackup`](../commands-and-modules/commands.md#zfsdailybackup)).

### Layout

- **Pre-Backup** — One checkbox and a command entry:
  **Run pre-backup command** — Enable a custom command that runs before all backup steps. If it fails, the backup aborts. 

- **Advanced** — Collapsible expander with
  [dataset-selection criteria](#dataset-selection-criteria)
  (`includes`, `excludes`, `depth`, `startwith`, `endwith`) plus [advanced options](#advanced-options).

- **Pull Steps** — Editable list of rsync pull operations. The frame header has
  an **Active** checkbox; unchecking it bypasses every pull step while still
  running the other backup steps. Each row has two columns:
  
  - **Source** — the remote hostname or IP and file path to pull from. Examples:
    `proxmox1:/etc`, `192.168.1.50:/root`, `backup-server.local:/home`.
  - **Destination path** — the local directory where pulled files are placed.
    Example: `/backups/proxmox1`
  
  Add or remove rows with the buttons; reorder by dragging rows.
  
  A pull-step failure is **non-fatal**: it is logged as a warning, the backup
  continues with the remaining steps, and the job returns the failing pull's
  return code at the end.

- **Snapshot** — Enter a snapshot name (or click **Generate** to build one
  from the current time). The `@` prefix is added automatically if omitted. This name will be used for every snapshot that is created during the job run.
  This section sits just above the **Send/Receive Steps** so you can review the
  snapshot name immediately before running the backup.

- **Send/Receive Steps** — Editable list of ZFS send/receive operations
  (Source pool, Destination pool). Reorder by dragging rows.

- **Post-Backup Steps** — Three checkboxes and a command entry:
  
  - **Clear snapshot name memory** after sending
  - **Prune snapshots** when the backup finishes
  - **Run post-backup command** — Enable a custom command that runs after all
    backup steps finish. It executes even if a fatal error aborts the backup early.

- **ZFS Keys Backup** — Two entries in the Advanced expander:
  
  - **ZFS keys source** — rsync endpoint where the key files currently live
    (e.g. `/mnt/ZFSkeys/` or `storage-host:/backups/zfs-keys/`)
  - **ZFS keys destination** — rsync endpoint where the copied keys should be placed.
    Must resolve to an **encrypted ZFS dataset**; the step is skipped with a
    warning if it does not. See [Daily Backup — ZFS Keys Backup](daily-backup.md#zfs-keys-backup)
    for the security implications.

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

---

## Offsite Tab

This tab configures offsite backups ([`zfssendoffsite`](../commands-and-modules/commands.md#zfssendoffsite)).

### Layout

- **Offsite Pool** — A read-only **Detected pool** label. Candidates are
  selected in the [Pools tab](#pools-tab) entries using the **Offsite** checkbox; the
  first online candidate becomes the active offsite target at run time. Updates automatically.

- **Advanced** — Collapsible expander with
  [dataset-selection criteria](#dataset-selection-criteria)
  (`includes`, `excludes`, `depth`, `startwith`, `endwith`) and advanced send/receive options.

- **Snapshot** — Enter a snapshot name (or click **Generate** to build one
  from the current time). The `@` prefix is added automatically if omitted.
 
- **Send/Receive Steps** — Editable list with columns: Active, Source,
  Destination, Includes, Excludes. Reorder rows by dragging. The `<offsite>`
  token in the Destination column is replaced at runtime with the detected
  offsite pool name.

### Actions

| Button                       | Behavior                                                                                                                                                                                                                                                         |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Run Offsite**              | Detects the offsite pool, then shows a confirmation dialog with the new snapshot name and detected pool.<br>Click **OK** to proceed, **Cancel** to abort, or **Generate** to build a new snapshot name and review again.<br>Then launches the send/receive steps |
| **Cancel**                   | Appears while a job is running. Click to immediately terminate the job.                                                                                                                                                                                                                                   |
| **Select All / Select None** | Mark every step active or inactive                                                                                                                                                                                                                               |
| **Save Config**              | Persists the tab state; turns **red** when there are unsaved changes.                                                                                                                                                                                                                 |
| **Revert Config**            | Reloads from JSON and refreshes the detected pool label                                                                                                                                                                                                          |
| **Add Profile to Schedule**  | Saves a copy of the current offsite settings as a profile in the Schedule tab.                                                                                                                                                                                              |
| **Recall Profile**           | Loads a previously-saved offsite profile into this tab for editing or on-demand execution                                                                                                                                                                        |

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

- **Advanced** — Collapsible expander with
  [dataset-selection criteria](#dataset-selection-criteria)
  (`depth`, `includes`, `excludes`, `startwith`, `endwith`) and:
  
  | Option    | Purpose                                                                                                          |
  | --------- | ---------------------------------------------------------------------------------------------------------------- |
  | **label** | Snapshot label for matching. Only snapshots with this label are considered as source candidates for the restore. |

- **Restore Steps** — Two checkboxes:
  
  - **Part 1** — Full copy of the oldest common snapshot
  - **Part 2** — Incremental copy of remaining snapshots

- **Notes** — A reminder that Part 1 is destructive on the destination.
  Part 1 asks once for confirmation of the dataset list and then proceeds
  automatically; Part 2 runs incrementally without prompting.

### Actions

| Button                      | Behavior                                                                                                                                                                  |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Run Restore**             | Validates entries, warns if Part 1 is selected, then launches the restore                                                                                |
| **Cancel**                  | Stops a running restore                                                                                                                                                   |
| **Save Config**             | Saves settings; turns **red** when there are unsaved changes                                                                                                                             |
| **Revert Config**           | Reloads from saved settings                                                                                                                                           |
| **Add Profile to Schedule** | Saves the current restore settings as a profile in the Schedule tab.                                                                                            |
| **Recall Profile**          | Loads a previously-saved Schedule tab profile into this tab for editing or on-demand execution. Click the Add Profile to Schedule button to save changes to the schedule. |

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
| **Next Run**     | Next scheduled execution time                                 |

Click any column header to sort by **Profile Name**, **Type**, or **Next Run**.
Click any row to
select it; the detail pane below populates with that profile's cron settings.

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
2. **Run on demand** — Recall a profile and click the tab's **Run** button
   immediately. The job executes using the recalled settings without waiting
   for the scheduled cron time.

Recalling a profile does **not** modify the saved config file. If you want to
make the recalled settings the new default, click **Save Config**
after recalling.

### Detail pane (profile selected)

- **Profile / Type** — read-only name and tab type
- **Cron Parameters** — five editable fields. Each field accepts numbers, `*` (any value), comma-separated lists,
  ranges, and steps:
  - **Minute** — `0-59`, `*`, e.g. `1,15,30`, `9-17`, `*/5`
  - **Hour** — `0-23`, `*`, e.g. `0,6,12`, `9-17`, `*/2`
  - **Day of Month** — `1-31`, `*`, e.g. `1,15`, `10-20`
  - **Month** — `1-12`, `*`, e.g. `1,4,7,10`, `3-5`
  - **Day of Week** — `0-7` (`0` and `7` are Sunday), `*`, e.g. `1-5`, `*/2`
- **Interpretation** — live prose explanation of the cron expression
  (e.g. *"At 02:00 every day"* or *"Every 15 minutes on weekdays"*)
- **Examples** — next three datetimes that match the expression
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

**Not supported:** textual weekday or month names (`MON`, `JAN`), cron
special strings (`@daily`, `@hourly`), `L`/`W`/`#` qualifiers, or question
marks. For a full cron syntax reference, see
[crontab.guru](https://crontab.guru/).

### Actions

| Button     | Behavior                                                                                                                                                                 |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Save**   | Saves all pending changes (active toggles and cron parameters) and regenerates `/etc/cron.d/zfsutilities`. Turns **red** when any row or cron field has unsaved changes. |
| **Revert** | Restores all pending changes to their last-saved values.                                                                                                                 |
| **Delete** | Removes the selected profile file and its cron entry (with confirmation)                                                                                                 |

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

## Checkagainst Tab

This tab edits the [`zfscheckagainst`](../commands-and-modules/modules.md#zfscheckagainst)
table used for verification when deleting snapshots.

### Layout

An editable, reorderable table with five columns. Drag rows to reorder them; click a cell to edit it.

| Column          | Meaning                                                                                                                                                          |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Dataset**     | Source dataset tree this row applies to. `<offsite>` may appear anywhere; each occurrence is replaced with each offsite-candidate pool name at run-time.         |
| **Quals**       | Number of leading path segments to strip from the dataset's name. This is the first of two steps for constructing the counterpart dataset name.                                                                                       |
| **Counterpart** | Path prefix to prepend after stripping. A literal `-` means "no prepend". `<offsite>` may appear anywhere and is replaced with each offsite-candidate pool name. This is the second of two steps for constructing the counterpart dataset name.|
| **Label**       | Snapshot label to match. This entry will be used only when the snapshot has this label.                                                                                                                                          |
| **Comment**     | Optional note stored in the saved configuration and shown in this table. Use for documenting the entry's purpose or a short blurb of what it does.                                                                                                  |

`zfscheckagainst` uses this table to map a snapshot to its counterpart
dataset(s). Before a snapshot is deleted, the script verifies that the candidate snapshot
is not the last common snapshot shared with any counterpart. If the
counterpart pool is offline and the snapshot label is `offsite`, hold tags
are used as receipts to decide whether deletion is safe.

For the full algorithm and return codes, see the
[`zfscheckagainst` module reference](../commands-and-modules/modules.md#zfscheckagainst).

### Actions

| Button         | Behavior                                                                            |
| -------------- | ----------------------------------------------------------------------------------- |
| **Add Row**    | Appends a new empty row                                                             |
| **Remove Row** | Deletes the selected row(s)                                                         |
| **Save**       | Saves the table after validation. Turns **red** while there are unsaved changes. |
| **Revert**     | Discards all changes and reloads from the last saved table.                                                                   |

A status label below the table shows **orange** "Unsaved changes" while
edits are pending, or a **red** validation error if a row is missing a
required field (Dataset, Counterpart, or Label) or has an invalid Quals
value.

---

## Pools Tab

This tab shows every pool known to the system (from `zpool list`) and
lets you maintain the pool registry stored in JSON. It also contains the
**Scrub Manager** for starting, pausing, resuming, and stopping pool scrubs.

### Pool table

Columns: **Pool**, **Offsite**, **Health**, **Size**, **Alloc**, **Free**, **Freeing**,
**Ckpoint**, **Frag**, **Cap**.

Multiple pools can be selected at once (Ctrl+click or Shift+click). Most
actions operate on every selected row.

**Pool name column:**

| Style          | Meaning                                                                                                |
| -------------- | ------------------------------------------------------------------------------------------------------ |
| **Red**  | Pool is online but *not* in the registry. Select the pool, click **Add** then **Save** to register it. |
| Orange | Pool is registered but currently offline (not returned by `zpool list`).                               |
| Default color  | Pool is registered and online.                                                                         |

The **Offsite** column shows a checkbox for every registered pool. Checking it
marks that pool as an offsite candidate; the Offsite tab detects the first
online candidate at run time. Unregistered pools cannot be marked as offsite
candidates. The checkbox state is saved with the registry when you click
**Save**.

**Health column:**

| Style          | Meaning                                              |
| -------------- | ---------------------------------------------------- |
| Green    | `ONLINE`                                             |
| Orange, bold   | `DEGRADED`                                           |
| Orange, normal | `OFFLINE` (not present in `zpool list`)              |
| Red      | Any other state (`FAULTED`, `UNAVAIL`, `REMOVED`, …) |

### Actions — Pool Registry

| Button      | Behavior                                                                                                   |
| ----------- | ---------------------------------------------------------------------------------------------------------- |
| **Watch**   | Opens a [Pool Watch window](#pool-watch-windows) for each selected online pool                             |
| **Add**     | Adds the selected unregistered pool to the registry (or opens a dialog to type a name if none is selected) |
| **Remove**  | Removes all selected registered pools from the registry (not from ZFS) after confirmation                  |
| **Import**  | Imports selected offline pools directly, or opens a dialog listing importable pools if none are selected   |
| **Export**  | Confirms, then runs `zpool export` on all selected pools                                                   |
| **Save**    | Saves registry changes; turns **red** while there are unsaved changes                                                          |
| **Revert**  | Reloads registry from the last saved settings                                                                   |
| **Refresh** | Re-runs `zpool list` and refreshes the table                                                               |

Right-click any cell to **Copy** the cell value or the full row
(tab-separated).

### Scrub Manager

Below the pool registry is the Scrub Manager, separated by a draggable
divider. It maintains a queue of pending, active, paused, and finished
scrubs. The queue is saved to disk automatically and survives GUI restarts.

#### Controls

| Control                  | Purpose                                                                             |
| ------------------------ | ----------------------------------------------------------------------------------- |
| **Simultaneous scrubs**  | Target number of scrubs running at the same time (1–10). Default: **1**.            |
| **Refresh every (s)**    | How often the scrub status table updates (1–300 seconds). Default: **10**.          |
| **System weekly scrub**  | Enable the pre-installed `zfs-scrub-weekly@<pool>.timer` for every registered pool  |
| **System monthly scrub** | Enable the pre-installed `zfs-scrub-monthly@<pool>.timer` for every registered pool |

The system-scrub toggles are independent of the ZFS Utilities schedule.
They modify systemd timer units directly and persist across GUI restarts.

#### Scrub status table

Columns: **Pool**, **Status**, **Progress**, **Last Scrub**, **Scan Line**.

`Last Scrub` shows the date the last scrub finished or was canceled; it is
blank (`—`) if the pool has never been scrubbed.

Multi-select rows with Ctrl+click or Shift+click, then use the action
buttons to control them.

#### Actions — Scrub Manager

| Button                      | Behavior                                                                                          |
| --------------------------- | ------------------------------------------------------------------------------------------------- |
| **Start Scrub**             | Adds selected pools to the pending queue. The manager automatically starts them up to the target. |
| **Pause Scrub**             | Pauses selected active or pending scrubs (`zpool scrub -p`)                                       |
| **Resume Scrub**            | Moves selected paused pools back to the pending queue so the manager can restart them                          |
| **Stop Scrub**              | Stops selected scrubs (`zpool scrub -s`) and removes them from the queue                          |
| **Add Profile to Schedule** | Saves selected pools and all settings as a scheduled profile                                      |

#### How the queue works

1. **Pending** — pools waiting to be scrubbed. A pool is added here when
   you press **Start Scrub**, even if `zpool status` currently shows a prior
   finished or canceled scrub; the manager still starts a fresh scrub. The manager starts pending pools until the simultaneous target is reached.
2. **Active** — pools currently **scrubbing**.
3. **Paused** — pools that were paused manually or by lowering the target.
   Manually paused pools stay paused until you press **Resume Scrub**, even
   if the simultaneous target would otherwise allow more active scrubs.
   Pools paused only because the target was lowered are resumed automatically
   when the target is raised again or a running scrub finishes.
4. **Finished** — pools whose scrub completed or was canceled. Finished
   entries are automatically replaced when a new scrub starts on the same pool.

If you lower the simultaneous target below the current active count, the
manager pauses the newest active scrubs. If you raise it, pending scrubs are started or paused scrubs are resumed.

Externally-started scrubs (e.g. from the command line or a systemd timer)
are detected automatically and incorporated into the active, paused, or
finished buckets. A 30-second grace period prevents freshly-started scrubs
from being mistakenly marked finished while ZFS is still initializing them.

---

## Log Panel

The bottom panel shows a scrollable log of all operations. Every line is
prefixed with a `YYYY-MM-DD HH:MM:SS` timestamp. The divider between
the main content area and the log panel can be dragged to resize the log.

A **Pop Out** button (window icon) next to the **Log** level dropdown detaches the
entire bottom panel into an independent window. This lets you further resize the
window or move it to a second monitor. Click the button again (or close
the pop-out window) to dock it back. The pop-out window's size and position are
remembered across sessions. The search bar and Clear button travel with the
panel when popped out.

### Search and Clear

Above the text view, a search bar provides:

- **Search entry** — type a query and press Enter (or click **Search**)
- **Search** button — finds and highlights every match. The current match is
  highlighted in **orange**; all other matches are highlighted in **yellow**.
- **Reset** button — clears highlights and empties the search field
- **Previous / Next** arrow buttons — cycle through matches, wrapping around at
  the first/last match. A counter shows the current position (e.g. `3 / 12`).
  The viewer scrolls so the current match is visible.
- Searches are **case-insensitive**.

A **Clear** button next to the **Input** entry empties the log buffer, clears
search highlights, and resets the warning/error indicator.

Job progress is shown as text in the log stream. Each running step logs its
description, and `zfs receive` summary lines report bytes transferred. A
status label below the log view displays the current step and progress text.

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
| **Log Size**  | Size of the log file on disk                                           |
| **Duration**  | Total elapsed time in `HH:MM:SS`                                       |
| **Transfer**  | Total bytes transferred during ZFS send/receive steps                  |

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

- **Pop Out** — a button in the search bar detaches the entire viewer (search
  controls + text view + Show More) into an independent window.

- **Search bar** — above the text view:
  
  - **Search entry** — type a query and press Enter (or click **Search**)
  - **Search** button — finds and highlights every occurrence. The current
    match is highlighted in **orange**; all other matches are highlighted in
    **yellow**.
  - **Reset** button — clears highlights and empties the search field
  - **Previous / Next** arrow buttons — cycle through matches, wrapping around
    at the first/last match. A counter shows the current position (e.g. `3 / 12`).
    The viewer scrolls so the current match is visible.
  - Searches are **case-insensitive**.
  - The search query is **retained** when you switch to a different log file;
    the search automatically reruns against the newly loaded text.

### Retention control

A **success-rate summary** appears above the log list (e.g. *"Success rate (30 days): 95 % (19 / 20)"*). It is computed from the backup history file and updates automatically every time the log list refreshes.

A **Retention (days)** spin button above the log list sets how long session
files are kept. The default is **30 days**. Old files are pruned automatically
when a scheduled run starts, or manually via the **Prune Old** action button.

!!! warning "Setting retention to 0"
    A value of **0** means **all** session log files will be deleted. Use this with caution.

### Actions

| Button              | Behavior                                                                                                                                                                         |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Refresh**         | Rescan `/var/log/zfsutilities/sessions/` and refresh the list. The list also refreshes automatically whenever files are created, modified, or deleted in the sessions directory. |
| **Delete Selected** | Remove the selected log file(s) after confirmation                                                                                                                               |
| **Prune Old**       | Delete all session files older than the retention setting                                                                                                                        |

---

## Datasets Tab

This tab displays a hierarchical, collapsible tree of all pools, datasets,
snapshots, and hold tags.

### Tree conventions

The dataset tree uses typography to indicate row kind:

| Style            | Meaning                                                     |
| ---------------- | ----------------------------------------------------------- |
| **Bold**         | Pool name (top-level row)                                   |
| Normal           | Regular dataset                                             |
| Normal `[clone]` | Dataset that is a ZFS clone (origin shown in last column)   |
| *Italic*         | Snapshot or hold tag |

Holds are shown as children of their snapshot. Expanding a snapshot
row reveals any hold tags attached to it.

The **Origin / Clones** column shows:

- For clone datasets: the origin snapshot the clone was created from
- For snapshots with dependent clones: a comma-separated list of clone
  dataset names
- Empty for all other rows

### Snapshot and hold actions

The list supports multi-select; action buttons are enabled or disabled
based on what is selected.

| Button               | Enabled when                                     | Behavior                                                                                                                                                                                                         |
| -------------------- | ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Snapshot**         | Exactly one pool or dataset selected             | Creates a new snapshot (prompts for name; suggests `manual-YYYY-mm-ddTHH:MM`)                                                                                                                                    |
| **Delete**           | Only snapshots and/or holds selected             | Holds are released (`zfs release`); snapshots are destroyed (`zfs destroy`). Mixed selections are supported: holds are released first, then snapshots deleted. Snapshots with remaining holds won't be deleted. |
| **Add Hold**         | At least one snapshot selected                   | Prompts for a tag (default `keep`) and applies it to each selected snapshot                                                                                                                                      |
| **Rollback**         | Exactly one snapshot selected                    | Rolls the dataset back to that snapshot (destroys newer snapshots)                                                                                                                                               |
| **Show Files**       | Exactly one mounted filesystem selected          | Opens the dataset's mountpoint in the default file manager (via `xdg-open`). Disabled for pools, volumes, snapshots, holds, and unmounted filesystems.                                                           |
| **Browse Snapshot**  | Exactly one snapshot selected, parent mounted    | Opens the snapshot via `.zfs/snapshot/<name>` in the default file manager. ZFS auto-mounts the snapshot on first access.                                                                                         |
| **Unmount Snapshot** | Exactly one snapshot selected, currently mounted | Runs `sudo umount` on the snapshot's `.zfs/snapshot/<name>` path. If processes are still using the snapshot, a warning dialog lists them and asks you to close them before retrying.                             |
| **Refresh**          | Always                                           | Re-reads all pools, datasets, snapshots, and holds while preserving the tree's vertical scroll position and current selection whenever possible                                                                  |
| **Expand Selected**  | One or more pool/dataset/snapshot rows selected  | Recursively expands each selected row and its lazy-loaded descendants. Placeholder rows and hold tags are skipped.                                                                                               |
| **Collapse All**     | Always                                           | Collapses the entire tree                                                                                                                                                                                        |

Right-click any cell for a context menu:

- **Copy** — copies the clicked cell value
- **Copy row** — copies the full row (tab-separated)
- **Copy full name** — copies the fully-qualified dataset or snapshot name
  (e.g. `pool/data/dataset-a@offsite-…`). For hold tags,
  this copies the parent snapshot name.

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
  letter). The GUI groups snapshots by this letter during pruning. You can add
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
| **Remove Policy**           | Deletes the currently-selected pool's entry (after confirmation). Blocked for `default`. The pool is removed from the Prune list and falls back to the `default` policy.                                          |
| **Add Bucket**              | Adds a new bucket row to the editor table                                                                                                                                                                         |
| **Remove Bucket**           | Removes the selected bucket row                                                                                                                                                                                   |
| **Save**                    | Saves the policy for the currently-selected pool, any pending bucket edits made to other pools, and the prune snapshot label                                                                                      |
| **Revert**                  | Discards all pending edits (for every pool) and reloads the saved policy and prune label                                                                                                                          |
| **Add Profile to Schedule** | Saves a snapshot of current prune settings (label + selected pools) as a scheduled profile                                                                                                                        |
| **Recall Profile**          | Loads a previously-saved retention profile into this tab for editing or on-demand execution                                                                                                                       |

### Prune runner

Below the editor, a multi-select list shows online pools that have an explicit
retention policy. Drag rows to reorder the pool list. Select one or more, set
the snapshot label (default `dailybackup`), and click **Prune** to run a prune
job for each pool in sequence. Pools without an explicit policy are not shown
here; they are pruned according to the `default` policy only when called from
`zfsdailybackup`.

The label is persisted in the JSON config under `prune_label` and survives
across GUI restarts. Changing the label marks the page dirty; click **Save**
to persist it, or **Revert** to restore the saved value.

The **Prune** button becomes **Cancel** while a prune job is running;
output streams to the log panel at the bottom of the window, and any
interactive prompts may be responded to in the **Input** entry next to the **Send**
button.

#### What happens during a prune

For each selected pool, the GUI runs a prune job that applies the pool's
retention policy to all datasets. It prunes in three phases: offsite
same-month deduplication (only for `@offsite` snapshots), same-day
deduplication within each bucket, and bucket-count enforcement. The most
recent snapshot in each bucket is protected as the incremental backup base.
Clone snapshots (`c` bucket) are skipped entirely.

Before any snapshot is destroyed, `zfscheckagainst` verifies it is not the
last common snapshot shared with a counterpart dataset (e.g. an offsite pool).

If **Dry Run** is active, deletions are simulated and the log panel shows what
would be deleted without actually destroying anything.

For the full algorithm, see the
[`zfsretain` module reference](../commands-and-modules/modules.md#zfsretain).

---

## Pool Watch Windows

The **Watch** action on the Pools tab opens an **independent** window for
the selected pool. Each window:

- Has its own dataset tree, refreshed every 30 seconds
- Starts collapsed; use **Expand All** / **Collapse All**
- Can be opened for multiple pools simultaneously
- Runs its own refresh timer, stopped automatically when the window is closed
- Clicking **Watch** again for a pool that already has a window brings that
  window to the front instead of creating a duplicate

The list inside a Pool Watch window follows the same conventions as the
[Datasets tab](#datasets-tab).

---

## Context Menus

All dataset lists in the GUI support right-click → **Copy** for the clicked
cell and the full row (tab-separated). The Datasets view and Pool Watch
windows additionally offer **Copy full name**, which copies the
fully-qualified dataset or snapshot name.

The **Schedule** tab's Config Summary text view also has a right-click menu
with **Copy** (current selection, or all text if nothing is selected) and
**Select All**.

# Changelog

## 0.62.1

*Released 2026-07-16*

### Fixed

- **Retention tab vertical resizing** — The Retention tab content is now
  wrapped in a `Gtk.ScrolledWindow` so the main window can shrink vertically
  without hiding the Mass Delete and profile controls.

### Tests

- Added `TestRetentionPageLayout` in `tests/python/test_retention_page.py`
  to verify the page is returned inside a `Gtk.ScrolledWindow`.

## 0.62.0

### Added

- **Mass Delete snapshots from the Retention tab** — A new **Mass Delete**
  toolbar button on the Retention tab deletes snapshots across selected pools
  in bulk. Two modes are supported:
  - *Respect retention policies* (default) — runs `zfscleanup` for each selected
    pool and deletes only the snapshots the retention policy would prune.
  - *Ignore retention policies* — deletes every matching snapshot regardless of
    retention counts, `minage`, or `zfscheckagainst` safety checks.
- **`zfsmassdelsnaps` command** — New bash script that implements the mass-delete
  logic. It can be invoked directly from the command line or through the GUI.
  It supports dataset filters (`includes`, `excludes`, `startwith`, `endwith`),
  a snapshot-name substring filter, dry-run mode, and optional hold release.
- **Mass Delete settings persistence** — The Retention tab's Mass Delete card
  settings are saved in the JSON config under `retention_mass_delete`.
- **Prune label and pool-order persistence** — The global prune snapshot label
  (`prune_label`) and the order of pools in the Prune list
  (`prune_pools_order`) are now persisted in the JSON config.

### Changed

- **Retention tab action handlers refactored** — Prune and Mass Delete actions
  moved from `retention_page.py` to the new `retention_actions.py` module to
  keep page construction and action logic separate.

### Documentation

- Added the [`zfsmassdelsnaps`](commands-and-modules/commands.md#zfsmassdelsnaps)
  section to the command reference.
- Added a **Mass Delete** section to the [Retention Policies](user-guide/retention.md)
  user guide.
- Updated the [Retention Tab](user-guide/gtk-gui.md#retention-tab) GUI reference
  with the **Mass Delete** button and card documentation.
- Documented `prune_label`, `prune_pools_order`, and `retention_mass_delete` in
  the [JSON config reference](developer-guide/data-structures.md).
- Added `get_retention_mass_delete_config()` / `save_retention_mass_delete_config()`
  and `on_retention_mass_delete()` to the Python modules reference.

### Tests

- Added `tests/test-zfsmassdelsnaps` covering ignore mode, respect mode, dry run,
  user approval, and `releaseholds` forwarding.
- Added `TestOnRetentionMassDelete` in `tests/python/test_retention_actions.py`.
- Expanded `tests/python/test_retention_page.py` with tests for Mass Delete
  widget creation, dirty detection, and config save/load.

## 0.61.1

*Released 2026-07-16*

### Fixed

- **Dashboard crash when no tasks are running** — The Running Tasks
  `ListStore` gained a fifth hidden column (`log_file`) in 0.61.0, but the
  "No running tasks" placeholder row still appended only four elements. This
  caused a `ValueError` on Dashboard refresh whenever the task list was empty.
  The placeholder now supplies all five columns.

### Tests

- Added `test_empty_tasks_placeholder_has_five_columns` in
  `tests/python/test_dashboard_page.py` to prevent the placeholder/schema
  mismatch from regressing.

## 0.61.0

*Released 2026-07-16*

### Removed

- **Obsolete `08 Two-node/install-scripts` script** — The deprecated
  two-node installer has been removed. It was already superseded by
  `10 Installers/install-two-node`. Updated `deploy-version`,
  `08 Two-node/two-node-lib.sh`, `08 Two-node/README.md`, and
  `08 Two-node/two-node.conf.template` to remove all references and point
  users to the current installer.

### Added

- **Dashboard shows host operating-system information** — The Dashboard
  config section now displays the operating-system name and version for each
  configured host. Detection order is Proxmox VE (`pveversion`), standard
  `/etc/os-release`, and finally `inxi -S`. Remote hosts in two-node mode are
  queried over SSH.
- **Dashboard "View Log" works for running tasks** — The Dashboard's
  **View Log** button now prefers a selected **Running Tasks** row that has a
  recorded session log and falls back to the selected **Recent Operations**
  row. Profile locks, GUI runners, and legacy scheduled tasks all expose their
  session log path so the Dashboard can jump directly to the live log.
- **Dashboard shows tasks waiting for dataset locks** — Running tasks now
  report a "Waiting for dataset lock" status, and warnings call out exactly
  which tasks are blocked on a lock.
- **Logs tab shows live `pv` progress** — The log viewer in the Logs tab has
  a new status label that displays the latest `pv` progress line while a log
  is running.
- **Schedule "Run Now" shows `pv` progress** — Profile runs started with
  **Run Now** from the Schedule tab now update the global status label with
  `pv` progress lines and clear the progress when the run finishes.
- **Schedule summary preserves scroll position** — The schedule summary
  textview keeps its scroll position when the profile selection changes but
  the generated summary text is unchanged.

### Tests

- Updated `tests/python/test_dashboard_page.py`,
  `tests/python/test_logs_page.py`,
  `tests/python/test_profile_runner_concurrency.py`, and
  `tests/python/test_schedule_page.py` to cover the new Dashboard, Logs, and
  Schedule behavior.
- Updated `tests/test-deploy-version` to reflect the removal of
  `install-scripts` from the deployed two-node script list.

## 0.60.1

*Released 2026-07-16*

### Fixed

- **`switch-version` tolerates missing `desktop-launcher-lib.sh`** — When the
  desktop-launcher helper library is absent from a deployed version (for
  example, an older deployment with an empty `10 Installers/` directory),
  `switch-version` now defines fallback no-op helpers and continues creating
  core production wiring instead of emitting shell errors about undefined
  functions.
- **`uninstall-zfsutilities` tolerates missing `desktop-launcher-lib.sh`** —
  Applies the same conditional source logic so uninstall can complete even
  when the launcher library is missing.

### Tests

- Added `test-switch-version` case verifying graceful behavior when
  `desktop-launcher-lib.sh` is not present.
- Added `test-uninstall-zfsutilities` case verifying graceful behavior when
  `desktop-launcher-lib.sh` is not present.

## 0.60.0

*Released 2026-07-16*

### Changed

- **Renamed VM lifecycle scripts** — `retire-vm` is now `archive-vm` and
  `unretire-vm` is now `unarchive-vm`. The scripts behave exactly as before;
  only their names have changed to better describe their purpose.

### Added

- **`remove-vm`** — New script that removes a VM's zvols and Proxmox config
  without archiving. It scans pools for `vm-<VMID>-disk-*` zvols, lists any
  iSCSI target/LUN mappings, asks for confirmation, destroys the zvols with
  `zfsdelfs`, and deletes the VM definition.

## 0.59.18

### Changed

- **`BackupRunner` cleanup hardening** — `_cleanup_io()` now accesses the GLib
  main context and removes each I/O source inside `try/except` blocks so an
  unexpected error during source removal is logged but does not propagate.
  `GLib.MainContext.default()` is used instead of the older `get_default()`
  alias.
- **`BackupRunner` finish hardening** — `_finish()` now wraps UI cleanup,
  history entry creation, session trailer writing, previous log restoration,
  and the `on_complete` callback in individual `try/except` blocks. A failure
  in any one of these steps logs a warning and the remaining cleanup steps
  still run.

### Tests

- Updated `tests/python/test_backup_runner.py` to mock
  `GLib.MainContext.default()` instead of `get_default()`.
- Added `test_cleanup_io_uses_real_glib_api` to verify `_cleanup_io()` does
  not raise against the real GLib API when no sources are active.
- Added `test_finish_recovers_from_cleanup_exceptions` to verify `_finish()`
  completes even when UI cleanup, history entry creation, session trailer
  writing, log restoration, and the completion callback all raise.

## 0.59.17

### Changed

- **`zfsretain` returns instead of aborting** — Missing retention policies,
  unexpected lock-acquisition errors, and malformed policy fragments now log a
  warning and return `8` rather than calling `exit 8`. This lets callers decide
  whether to stop or continue.
- **`zfscleanup` continues on per-dataset retain errors** — When `retain`
  returns a non-zero code for a dataset, `zfscleanup` logs the return code and
  proceeds with the next dataset and pool instead of halting the entire run.
- **`BackupRunner` hardening** — `_run_next_step()` and `_check_process()` are
  now wrapped in try/except so unexpected internal exceptions log a traceback
  and cleanly finish the runner rather than leaving the GUI run stuck. Added
  debug logging when starting a step and when a step process exits. GLib source
  removal warnings are suppressed during I/O cleanup.
- **Retention policy comment clarity** — The offsite-bucket comment in all
  `zfsretainpol-*` files now explicitly states that `minage=65` means snapshots
  are not deleted before they are 65 days old.

### Documentation

- Added a **Policy Parameters** section to `user-guide/retention.md` explaining
  `retain` and `minage`.
- Updated `commands-and-modules/modules.md` to describe `zfsretain` return
  codes `1` and `8` as "skipped" rather than fatal.
- Updated `commands-and-modules/commands.md` to note that `zfscleanup` logs
  warnings and continues on retain errors.
- Updated `user-guide/daily-backup.md` so the retention/prune step is listed as
  non-fatal.

### Tests

- Added `tests/test-zfsretain` cases for missing-policy and lock-error return
  paths.
- Added `tests/test-zfscleanup` cases verifying continuation after a retain
  policy error and across pools.
- Added `TestRunnerRobustness` in `tests/python/test_backup_runner.py` to cover
  exception recovery and normal step advancement.

## 0.59.16

### Changed

- **Unified path resolution across the codebase** — New helpers eliminate
  hard-coded `/usr/local/lib/zfsutilities/...` paths so scripts work from the
  repo, a deployed version, or an arbitrary installation prefix.
  - `bashinit` now provides `find_zfsutility_script <name>`, which searches
    repo subdirectories and deployed `bin/` / `lib/` / `/usr/local/lib/`
    layouts and prints the absolute path of a sibling script or library.
  - `08 Two-node/node-lib.sh` adds `remote_zfsutilities_bin <host>` and
    `remote_zfsutility_script <host> <name>` to resolve the active deployed
    version on a peer node over SSH.
  - New `07 GTK + Python/path_utils.py` mirrors the bash behavior for the
    Python layer: `find_script`, `resolve_local_bin`, `get_version`,
    `get_docs_path`, `get_profile_runner_path`, `resolve_remote_bin`,
    `resolve_remote_script`, and `resolve_remote_version`. It honors
    `ZFSUTILITIES_VERSION_BASE`, `ZFSUTILITIES_REMOTE_BIN`, and
    `ZFSUTILITIES_REMOTE_VERSION` overrides.
- **Standardized node-aware script headers** — All scripts in `08 Two-node/`
  and `09 ZFS clone support/` now use the same initialization sequence:
  `source ~/bashinit`, `bashinit`, locate `node-lib.sh` and `rootcheck` via
  `find_zfsutility_script`, then call `rootcheck`. `NODE_LIB` can be set
  explicitly for tests or unusual layouts.
- **Standardized fatal handling and logging** — `deploy-version`,
  `switch-version`, `uninstall-version`, and the two-node/clone-support
  scripts now use `log_msg "FATAL: ..."` and `bashfatal` instead of ad-hoc
  `echo >&2; exit 1` patterns. Shebangs are normalized to `#!/usr/bin/bash`.
- **GUI uses centralized path helpers** — `dashboard_page.py`,
  `docs_viewer.py`, `schedule_page.py`, and `zfsutilities_gui.py` now call
  `path_utils` functions instead of embedding their own path/version logic.

### Documentation

- Added `path_utils.py` to the Python modules reference.
- Documented `find_zfsutility_script` and `remote_zfsutility_script` in the
  `node-lib.sh` and two-node command reference pages.
- Updated `conventions.md` with the node-aware script header pattern.
- Removed stale planning documents (`Installer test plan.md`,
  `InternalsDocPlan.md`, `ROADMAP2.md`).

### Tests

- Added `tests/test-node-lib` covering `node-lib.sh` helpers including
  `find_zfsutility_script`.
- Added `tests/python/test_path_utils.py` covering all public functions in
  `path_utils.py`.
- Updated `tests/python/test_dashboard_page.py`,
  `tests/python/test_gui_infrastructure.py`, and
  `tests/python/test_schedule_page.py` for the path-utils refactor.
- Updated bash tests for `list-vm-disks`, `restart-iscsi-services`,
  `retire-vm`, `safe-iscsi-save`, and `unlock-zfs-keys` to match the new
  script headers and logging.

## 0.59.15

### Changed

- **Dashboard iSCSI warnings are now user-friendly** — The Dashboard iSCSI Issues
  box no longer reports raw "LUN missing on target" messages. It now shows plain
  language such as "VM 207 disk 2 (vm-207-disk-2) is not exported as an iSCSI LUN
  on target threeamigos." Labels and the Fix this button have tooltips that
  explain what the warning means and what the repair action does.
- **Intentionally detached disks no longer trigger iSCSI warnings** —
  `detach-vm-disk` now removes the backstore from
  `/etc/rtslib-fb-target/expected-backstores.txt` before saving the iSCSI config,
  so the Dashboard does not report detached disks as missing.
- **`repair-iscsi-luns` respects the expected-backstores manifest** — It now only
  creates iSCSI backstores/LUNs for entries listed in `expected-backstores.txt`.
  Zvols that exist but are not in the manifest are reported as unexported but are
  not auto-exported, so detached disks stay detached. If the manifest is missing,
  the script falls back to the previous behavior of repairing all discovered
  zvols.
- **`repair-iscsi-luns` finds helper scripts relative to itself** — Calls to
  `safe-iscsi-save` and `rescan-storage` now resolve from the script's own
  directory, so the script works when run directly from the repo, through a
  deployed-version symlink, or from `/usr/local/lib/zfsutilities/bin`. This
  fixes the "command not found" errors that occurred when the GUI invoked the
  repair script with a minimal `PATH`.
- **`detach-vm-disk` resolves the remote active version for SSH calls** —
  Remote calls to `detach-vm-disk` and `rescan-storage` on the compute host no
  longer hardcode `/usr/local/lib/zfsutilities/bin`. The script resolves the
  remote host's `/usr/local/lib/zfsutilities/current` symlink to discover the
  active version directory and runs the helper from there.
- **Schedule tab warns when cron is out of sync** — `schedule_page.py` now
  compares active profiles against `/etc/cron.d/zfsutilities` and logs warnings
  when profiles are missing from the crontab or the crontab contains inactive
  profiles.
- **MkDocs is required** — The documentation server and static site build now
  require MkDocs and the Material theme. `check-prerequisites` fails if they are
  missing, `startdocserver` no longer falls back to a static `http.server`, and
  the installers now install MkDocs unconditionally.

### Documentation

- Added a user-focused **Dashboard iSCSI Issues** section to `two-node.md` that
  explains what a missing LUN means, common causes, the Fix this button, and how
  intentionally detached disks are handled.
- Updated `detach-vm-disk` and `repair-iscsi-luns` sections in `two-node.md` and
  the `expected-backstores.txt` description in `data-structures.md` to reflect
  manifest-driven repair and detached-disk handling.
- Updated `commands.md` and `doc-server.md` to reflect that MkDocs is required
  and that `startdocserver` no longer falls back to `http.server`.
- Updated `installation/index.md` to describe MkDocs as a required component
  installed by the installers.

### Tests

- Updated `tests/test-repair-iscsi-luns` for manifest-driven repair, including
  fallback behavior and detached-zvol reporting.
- Added `tests/test-detach-vm-disk` covering removal of the backstore entry from
  `expected-backstores.txt`.
- Updated `tests/python/test_dashboard_page.py` to cover the new user-friendly
  iSCSI warning text and tooltips.
- Updated `tests/python/test_schedule_page.py` to cover cron consistency checks.
- Updated `tests/python/test_zfsutilities_gui.py` for recent GUI startup changes.
- Updated `tests/test-startdocserver` for the MkDocs-only server behavior.

## 0.59.14

### Changed

- **`retire-vm` archives only config-referenced zvols** — `retire-vm` now reads
  `/etc/pve/qemu-server/<vmid>.conf` to determine which disks are attached to the
  VM and archives only those zvols. Zvols that match the VM ID but are no longer
  referenced in the config are reported as warnings and are not archived or
  destroyed.
- **`retire-vm` auto-creates retire snapshots** — When a referenced zvol has no
  existing snapshot, `retire-vm` now acquires a write lock through
  `zfslockmanager` and creates a dedicated `@retire-` snapshot before archiving.
- **`retire-vm` two-node volblocksize handling** — The original `volblocksize` is
  now read on the storage host during two-node archives instead of on the compute
  host.
- **`enroll-efi-keys-vm` iSCSI by-path parsing** — Added a dedicated
  `parse_iscsi_by_path()` helper that correctly handles `by-path` symlinks
  containing IPv4 portals and IQN colons. Error messages now explicitly direct
  users to use `enroll-efi-keys-vm` instead of `qm enroll-efi-keys` for
  iSCSI-backed EFI disks.
- **`zfslockmanager` lock directory override** — `ZFSLOCK_DIR` can now be
  overridden via environment variable, enabling isolated testing.
- **Coding policy updates** — `AGENTS.md` and the developer coding policies now
  require that every function have more than one calling site and that regular
  expressions longer than 10 characters be profusely documented.

### Documentation

- Updated `commands.md`, `proxmox-integration.md`, `two-node.md`, and
  `08 Two-node/README.md` to describe the new `retire-vm` behavior and warn that
  Proxmox's **Enroll Updated Certificates** action and `qm enroll-efi-keys` do
  not work for iSCSI by-path EFI disks.

### Tests

- Added `tests/test-retire-vm` with nine tests covering single-node and two-node
  snapshot selection, auto-snapshot creation, referenced-disk filtering, orphan
  warnings, storage-host volblocksize handling, and message-level compliance.
- Extended `tests/test-enroll-efi-keys-vm` with tests for `parse_iscsi_by_path()`.

## 0.59.13

### Changed

- **Standalone documentation viewer no longer requires root** —
  `docs_viewer.py` no longer relaunches itself through `pkexec` when run as a
  normal user. The viewer now stores its config and lock files under the
  running user's home directory, so users can open `zfsutilities-docs` or the
  **ZFSutilities Documentation** desktop shortcut without elevation. The
  embedded viewer inside the GTK GUI still runs with the GUI's privileges.
- **Configuration and lock paths respect the running user** —
  `config_core.py` defaults `CONFIG_PATH` to `~/.config/zfsutilities.json`
  (overridable with `ZFSUTILITIES_CONFIG_PATH`). `file_locking.py` defaults
  lock files to `/run/lock/zfs/` for root and `~/.cache/zfsutilities/` for
  non-root users (existing environment overrides continue to work).
- **Documentation viewer toolbar styling** — Toolbar buttons now use
  symbolic icons and a shared CSS class so they render consistently against
  dark themes. The zoom-reset button uses a text label (`1`) for clarity.
- **README refresh** — Rewrote `README.md` with an expanded project
  description, feature overview, and updated GUI screenshot.
- **Terminal width guidance** — `AGENTS.md` now records the calibrated
  terminal width for this environment (95 columns → 85-character response
  target).

### Fixed

- **Deployed documentation permissions** — `deploy-version` now sets
  `0755`/`0644` permissions on the built MkDocs `site/` directory so the
  non-root documentation viewer can read all pages and assets.

### Tests

- Replaced `docs_viewer.py` root-elevation tests with tests that verify the
  viewer launches without `pkexec` when run as a normal user.
- Updated `tests/python/test_config_core.py` and
  `tests/python/test_file_locking.py` to assert user-aware default paths.
- Added `tests/python/test_gui_infrastructure.py` tests for symbolic toolbar
  icons, text-label toolbar buttons, and navigation-button behavior.
- Updated `tests/python/test_docs_viewer.py` to reflect the removal of
  `pkexec` elevation logic.

### Documentation

- Updated `06 Docs/docs/user-guide/gtk-gui.md` to state that the standalone
  documentation viewer does not require root.
- Added GitHub Issues and Discussions links to
  `06 Docs/docs/user-guide/index.md`.

## 0.59.12

### Fixed

- **Dashboard Running Tasks stale scrub display** — `dashboard_page.py` now
  reconciles the scrub queue against live `zpool status` before listing running
  tasks. Scrubs that finished or were paused externally (for example, by a
  headless profile using **Pause scrubs during each step**) no longer remain in
  the **Running Tasks** list with a stale in-memory queue entry.
- **Scrub pause filtering** — `scrub_manager.py` `pause_scrubs_for_pools()` now
  marks pools as user-paused only when they have a live scrub in progress or are
  already queued to start. Finished, unknown, or offline pools are skipped and
  are no longer logged as paused.
- **Schedule Run Now child-watch signature** — `schedule_page.py` now uses the
  modern `GLib.child_watch_add(priority, pid, callback, user_data)` signature,
  packing `app`, `profile_name`, and `process` into a single `user_data` tuple.
  If GLib watch setup fails, the launched profile is terminated and a `FATAL`
  message is logged instead of silently leaving the process unwatched.

### Changed

- **Agent guidance** — `AGENTS.md` now describes the agent as a "meticulous and
  expert coding agent" and adds a rule to take the correct approach even when
  it is more difficult. The `test_schedule_page` test count was updated to 35.

### Tests

- Added `tests/python/test_dashboard_page.py` tests verifying that finished
  scrubs are removed from **Running Tasks** and that mixed stale/live queue
  states display only the still-running scrubs.
- Added `tests/python/test_schedule_page.py` tests for the modern
  `GLib.child_watch_add` signature, `_on_profile_finished` tuple unpacking, and
  FATAL logging when watch setup fails.
- Added `tests/python/test_scrub_manager.py` tests verifying that finished
  pools are not moved to the paused queue and not marked user-paused.

### Documentation

- Updated `06 Docs/docs/user-guide/gtk-gui.md` **Running Tasks** section to list
  the **Profile** task type and to explain scrub-task reconciliation against
  live `zpool status`.
- Updated `06 Docs/docs/user-guide/daily-backup.md`,
  `offsite-backup.md`, and `restore.md` to note that pools whose scrub has
  already finished or that are not online are skipped during automatic scrub
  pause/resume.

## 0.59.11

### Fixed

- **Docs viewer WebKit2 deprecation** — `docs_viewer.py` now uses the modern
  `WebKit2.WebView.evaluate_javascript()` / `evaluate_javascript_finish()` APIs
  instead of the deprecated `run_javascript()` / `run_javascript_finish()`
  methods. Navigation-policy decisions now read the request through
  `NavigationPolicyDecision.get_navigation_action()`, matching current WebKit2
  4.1 bindings. This prevents runtime warnings and future breakage on newer
  distributions.

### Changed

- **User Guide organization** — `06 Docs/docs/user-guide/index.md` and
  `06 Docs/mkdocs.yml` now group the User Guide into **Concepts and
  Terminology**, **GTK GUI Reference**, and **Command Line Reference** sections.
  The new **Profiles** page is listed under Concepts. A new
  `06 Docs/docs/assets/stylesheets/extra.css` file ensures the top-level
  "GTK GUI Reference" link renders consistently with the other section headers.
- **Agent guidance** — `AGENTS.md` now instructs coding assistants to look for
  and correct deprecated code and features, and not to implement new deprecated
  code.

### Tests

- Added `tests/python/test_gui_infrastructure.py` tests for
  `DocsViewerWindow._on_decide_policy()`: navigation-action URI extraction,
  allowed-scheme passthrough, unknown-scheme blocking, and non-navigation
  decision handling. Updated the WebKit2 mock in
  `tests/python/test_support.py` to provide `evaluate_javascript`,
  `evaluate_javascript_finish`, and `NavigationPolicyDecision.get_navigation_action`.

## 0.59.10

### Fixed

- **Dashboard Cancel Selected Tasks** — The **Cancel Selected Tasks** button on
  the Dashboard is now enabled only when the selection contains a real task.
  Selecting the *"No running tasks"* placeholder row (or a mixed selection that
  includes only placeholders) no longer leaves the button active.
- **Schedule tab auto-refresh** — The Schedule tab now refreshes automatically
  every 60 seconds while visible, and immediately when switching to the tab or
  clicking **Refresh**. Next Run values are updated in place when the profile
  list is unchanged; the list is rebuilt when profiles are added or removed
  externally, preserving the current selection and any pending unsaved changes.
- **Rsync backup log rotation** — `BackupRunner` no longer truncates
  `/var/log/zfsutilities/rsync-backup.log` on every run. Instead, it truncates
  the file once per day (when the file's mtime is from a previous day), keeping
  one day of rsync output appended together while avoiding unbounded growth.

### Tests

- Added `TestRsyncLogDailyRotation` in `tests/python/test_backup_runner.py` to
  verify the new daily truncation behavior.
- Extended `tests/python/test_dashboard_page.py` to verify the Cancel button
  state for placeholder-only, mixed, and real-task selections.
- Added `TestRefreshSchedulePage` in `tests/python/test_schedule_page.py`
  covering in-place Next Run updates, list rebuilds, pending-change
  preservation, deleted-profile cleanup, and selection restore.
- Added timer-lifecycle tests in `tests/python/test_zfsutilities_gui.py` for the
  dashboard, scrub, and new schedule auto-refresh timers.

### Documentation

- Updated `06 Docs/docs/user-guide/gtk-gui.md` with the Dashboard Cancel button
  behaviour and the Schedule tab auto-refresh behaviour.
- Updated `06 Docs/docs/developer-guide/concurrency-collisions.md` to describe
  the new daily truncation of `/var/log/zfsutilities/rsync-backup.log`.

## 0.59.9

### Fixed

- **`deploy-version` Two-node script list** — Added `repair-iscsi-luns` and
  `iscsi-restore-luns` to the `TWO_NODE_SCRIPTS` array so they are symlinked
  into the deployed `bin/` directory. Previously they were copied into
  `08 Two-node/` but were not on `PATH`, causing `repair-iscsi-luns: command not
  found` after switching to v0.59.8.

### Tests

- Updated `tests/test-deploy-version` to include `repair-iscsi-luns` and
  `iscsi-restore-luns` in the Two-node symlink simulation and added explicit
  tests verifying both scripts are listed in `deploy-version`.

### Documentation

- Updated `06 Docs/docs/developer-guide/testing.md` test count for
  `test-deploy-version`.

## 0.59.8

### Added

- **`repair-iscsi-luns` (storage node)** — New diagnostic/repair script that
  discovers all VM zvols in configured pools, ensures each has a block backstore
  and a LUN mapping, preserves existing LUN indexes, regenerates
  `expected-backstores.txt`, saves the target config via `safe-iscsi-save`, and
  always rescans the compute host. Supports `--dry-run` to preview changes and
  `--force-relogin` to re-log iSCSI sessions when a rescan alone does not reveal
  all LUNs.

### Fixed

- **Dashboard "Fix this" iSCSI button** — The button now runs
  `repair-iscsi-luns` instead of `iscsi-restore-luns`, and it displays the
  command's stdout and stderr in the GUI log so the result is visible.
- **`safe-iscsi-save` manifest regeneration** — After a successful save,
  `safe-iscsi-save` now regenerates `expected-backstores.txt` from the current
  targetcli backstore list. This keeps the manifest accurate when LUNs are moved
  between VMs or when `repair-iscsi-luns` adds missing LUNs.
- **`safe-iscsi-save` active-count arithmetic** — Fixed a bug where `grep -c`
  returning `1` for no matches, combined with a fallback `|| echo "0"`, could
  produce a two-line string that broke the active-backstore count comparison.

### Tests

- Added `tests/test-repair-iscsi-luns` covering backstore/LUN parsing, zvol
  discovery, gap-free LUN index allocation, missing backstore/LUN creation,
  existing-backstore LUN mapping, dry-run mode, and compute-host rescan.
- Added `tests/test-safe-iscsi-save` covering the degraded-config guard and
  manifest regeneration after a successful save.
- Updated `tests/python/test_dashboard_page.py` for the new
  `repair-iscsi-luns` "Fix this" button behavior.

### Documentation

- Updated `06 Docs/docs/commands-and-modules/two-node.md` with the new
  `repair-iscsi-luns` section and updated `safe-iscsi-save` flow.
- Updated `06 Docs/docs/user-guide/gtk-gui.md` to describe the new
  `repair-iscsi-luns` "Fix this" button behavior.
- Updated `06 Docs/docs/developer-guide/testing.md`,
  `two-node-config.md`, and `data-structures.md` to reference the new script,
  tests, and manifest-regeneration behavior.

## 0.59.7

### Added

- **Installer retention-profile initialization** — New installs now initialize
  the shared JSON config with exactly one retention policy, the `default`
  policy. Pool-specific sample policies are no longer installed or imported on
  fresh systems. Re-running the installer on an existing system preserves any
  user-entered per-pool policies. Initialization is handled by the new
  `10 Installers/installer_retention.py` helper, invoked from
  `install-single-node` and `install-two-node` (including on the remote compute
  host in two-node setups).
- **`list-vm-disks` VM disk inventory** — `08 Two-node/list-vm-disks` now shows
  the VM that owns each exported LUN/zvol, the VM name, the compute-host
  `/dev/sdX` and `/dev/disk/by-path` names, and (for running VMs with a QEMU
  guest agent) the device names seen inside the guest. Device information is now
  included by default; `--with-devices` is accepted for backward compatibility.
  New flags `--gather-vm-info` and `--gather-lun-info` are available for
  selective inventory gathering.

### Fixed

- **GUI editable-cell Tab navigation** — The Checkagainst and Retention tables
  now support Tab and Shift+Tab to move between editable cells while editing,
  matching the behavior already provided for other editable lists.
- **Pools page multi-selection handling** — Drag-reorder and pool action
  handlers now use the multi-selection API correctly, preserving all selected
  rows after a drag and avoiding crashes when no rows are selected.
- **Backup runner I/O cleanup** — `backup_runner.py` now clears the correct
  source ID when the merged stderr stream ends and checks that a GLib source is
  still registered before removing it, preventing warnings from duplicate
  removals.
- **Stale action-button rebuilds** — `zfsutilities_gui.py` ignores asynchronous
  runner/profile completion callbacks that request action-button rebuilds for a
  tab the user has already left.
- **Two-node interactive SSH delegation** — `attach-vm-disk`, `clone-vm`,
  `detach-vm-disk`, `move-vm-disk`, `promote-vm-clone`, `retire-vm`,
  `unretire-vm`, and `zfsclone-vm` now allocate a TTY (`ssh -t`) when
  delegating to the compute host, improving behavior for interactive prompts.
- **`check-prerequisites` documentation warnings** — `mkdocs` and
  `mkdocs-material` are now reported as warnings rather than failures; the
  installer will install them if needed.

### Tests

- Added `tests/test-installer-retention` and
  `tests/python/test_installer_retention.py` covering default-profile creation,
  new-install pool-specific policy clearing, and preservation of existing
  user profiles.
- Added `tests/test-list-vm-disks` covering VM config parsing, host/guest device
  mapping, running-VM detection, and single-node/two-node output paths.
- Updated `tests/test-deploy-version` to verify that only
  `zfsretainpol-default` is shipped and pool-specific legacy policy files are
  excluded.
- Updated `tests/python/test_checkagainst_page.py`,
  `test_gui_infrastructure.py`, `test_pool_actions.py`, `test_pools_page.py`,
  `test_retention_page.py`, and `test_zfsutilities_gui.py` for the new Tab
  navigation, multi-selection, backup-runner cleanup, and stale-rebuild fixes.

### Documentation

- Updated `06 Docs/docs/commands-and-modules/two-node.md` to describe the new
  `list-vm-disks` output and flow.
- Updated `06 Docs/docs/user-guide/retention.md` to document fresh-install
  retention behavior and policy preservation.
- Updated `AGENTS.md` to reflect the new installer retention-profile behavior,
  deploy-version retention-policy filtering, and new test suites.

## 0.59.6

### Fixed

- **Headless `pv` behavior** — `zfs-send-receive::do_transfer()` no longer
  forces a progress display through `pv` in non-interactive/headless mode.
  When a rate limit is configured, `pv` is invoked as `pv -q -L <rate>` so the
  transfer is throttled without emitting progress lines that no one sees.  When
  no rate limit is configured, `pv` is skipped entirely in headless mode.
- **Priority parsing for nested `file:line` prefixes** —
  `logging_config.parse_msg_level()` now strips one or more leading
  `file:line:` prefixes (plus an optional timestamp) before looking for the
  `LEVEL:` token.  This fixes level filtering for lines emitted by a bash
  subprocess and captured by a Python runner, where both layers prefix the line
  with their own source location.

### Changed

- **Schedule tab crontab preview** — When an active scheduled profile is
  selected, the detail pane now shows the exact crontab entry written to
  `/etc/cron.d/zfsutilities` at the top of the summary, making it easy to verify
  the cron schedule, runner path, and output redirect.
- **Scrub pause/resume log noise reduction** — `scrub_manager.py` downgraded
  "pool is not online" and "scrub is not in the expected state" messages from
  `INFO` to `DEBUG` during `pause_scrubs_for_pools()` and
  `resume_scrubs_for_pools()`.  These messages described skipped actions rather
  than meaningful progress.

### Tests

- Added `tests/test-zfs-send-receive-dryrun` tests covering headless-mode `pv`
  behavior: `pv -q -L <rate>` when a rate limit is set, and no `pv` invocation
  when no rate limit is set.
- Added `tests/python/test_logging_config.py` tests for nested `file:line`
  prefix parsing and `VERB` level filtering.
- Added `tests/python/test_schedule_page.py` tests verifying that active
  profiles show their crontab entry in the summary pane and inactive profiles do
  not.

### Documentation

- Updated `06 Docs/docs/user-guide/gtk-gui.md` to describe the Schedule tab
  crontab entry preview.
- Updated `06 Docs/docs/messages/index.md` to document nested `file:line:`
  prefix handling.
- Updated `06 Docs/docs/commands-and-modules/python-modules.md` to list
  `_on_selection_changed()` in the `schedule_page.py` key-functions table.

## 0.59.5

### Fixed

- **Silent scheduled-profile skips** — `cron_manager.py` no longer wraps
  scheduled `profile_runner.py` invocations with a `flock -n -E 0` cron command.
  The runner already acquires its own per-profile advisory lock, and the extra
  cron-level flock caused every scheduled invocation to exit silently with no
  session log.  Cron stdout/stderr is now appended to
  `/var/log/zfsutilities/cron.log` so that errors occurring before the runner
  creates its own session log remain visible.
- **Resumable ZFS receive** — `zfs-send-receive::send-receive()` no longer
  appends `"$fs$nextsnap"` as an extra positional argument when `$sendopts`
  contains `-t <resume-token>`, because the token already encodes the snapshot.
  This fixes the `too many arguments` error that aborted resume transfers.

### Changed

- **`profile_runner.py` early session logging** — The runner now creates its
  session log before acquiring the per-profile advisory lock.  "Profile not
  found" failures and "already running" skips are therefore recorded in a
  session log instead of being lost.

### Tests

- Updated `tests/python/test_cron_manager.py` to reflect the removed flock
  wrapper and the new `/var/log/zfsutilities/cron.log` redirect.
- Added `tests/python/test_profile_runner.py::TestMainEarlyLogging` to verify
  that missing-profile and duplicate-invocation scenarios both create session
  logs and write the correct session trailer.
- Updated `tests/python/test_profile_runner_concurrency.py` for the new
  session-log creation order.
- Added `tests/test-zfs-send-receive-dryrun` tests covering resume-token mode
  (omits snapshot argument) and normal mode (includes snapshot argument).

### Documentation

- Updated `06 Docs/docs/commands-and-modules/python-modules.md` to describe the
  new `profile_runner.py` internal flow (session log created before lock).
- Updated `06 Docs/docs/user-guide/profiles.md` to document the cron-log output
  destination.

## 0.59.4

### Added

- **Concurrent Backup/Offsite/Restore GUI runners** — The Backup, Offsite, and
  Restore tabs are no longer globally serialized. Multiple GUI runners can now
  execute at the same time when they operate on disjoint datasets; per-dataset
  locks still prevent collisions on the same datasets.
- **Per-runner session logging** — `backup_runner.py` now routes its Python-level
  log output through a runner-specific session log file via the new
  `_runner_log()` helper and the `session_log_file=` keyword argument added to
  `logging_config.log_msg()`. Concurrent runners no longer cross-write their
  Python log messages into each other's session logs.
- **Scrub callback log routing** — `scrub_manager.py` `pause_scrubs_for_pools()`,
  `resume_scrubs_for_pools()`, and `attach_step_scrub_callbacks()` now accept an
  optional `log_func` callback. Backup, Offsite, and Restore tabs pass the
  runner's own log function so scrub pause/resume messages appear in the
  correct session log.

### Changed

- **`move-vm-disk` zvol discovery** — The script now searches the entire target
  pool for the backing zvol (not only the `proxmox` dataset) and places the
  destination zvol in the same parent dataset as the source zvol. This supports
  VMs whose disks live outside the `proxmox` dataset.
- **`zfslockmanager` stale cleanup** — `zfslock_cleanup_stale()` now always
  returns `0` and logs only when it actually removes stale lock files.
- **GUI PID file cleanup** — `main.py` now removes the PID file only when this
  process actually wrote it, avoiding an `is_remote()` check after `app.run()`
  has already finalized the application object.

### Tests

- Added `tests/python/test_scrub_manager.py` tests for the `log_func` parameter
  on `pause_scrubs_for_pools()`, `resume_scrubs_for_pools()`, and
  `attach_step_scrub_callbacks()`.
- Existing tests for `backup_page.py`, `backup_runner.py`, `logging_config.py`,
  `main.py`, `offsite_page.py`, `restore_page.py`, and `test-zfslockmanager`
  were updated to cover the concurrent-runner, per-runner logging, and stale-lock
  cleanup changes.

### Documentation

- Updated `06 Docs/docs/user-guide/gtk-gui.md`, `daily-backup.md`,
  `offsite-backup.md`, and `restore.md` to describe concurrent GUI runners and
  per-runner session logs.
- Updated `06 Docs/docs/developer-guide/concurrency-collisions.md` to reflect
  that the GUI no longer globally serializes Backup/Offsite/Restore.
- Updated `06 Docs/docs/commands-and-modules/two-node.md` `move-vm-disk` section
  to describe the broader zvol discovery and destination-parent behavior.

## 0.59.3

### Added

- **Scrub command debug logging** — `zfs_repository.py` and `zfsscruball` now
  log the exact `zpool scrub` command they are about to issue at `DEBUG` level,
  making it easier to trace scrub lifecycle in session logs.

### Changed

- **ZFS step output ordering in session logs** — `backup_runner.py` now merges
  child `stdout` into `stderr` for non-rsync steps. This keeps bash `echo`
  separators and `log_msg` / `zfs` output in their original interleaved order
  in the captured session log. Rsync steps keep separate stdout and stderr
  streams because rsync stdout is written to a dedicated log file.

### Fixed

- **`move-vm-disk` zvol lookup scope** — The script now searches for the backing
  zvol only under the target pool's `proxmox` dataset (`zfs list -r
  ${POOL}/proxmox`) instead of scanning every volume on the system, avoiding
  mismatches when the same backstore name exists on multiple pools.

### Tests

- Added `test_merged_output_preserves_input_order`,
  `test_non_rsync_merges_stderr_into_stdout`, and
  `test_rsync_keeps_separate_stdout_and_stderr` to
  `tests/python/test_backup_runner.py`.
- Added scrub-command debug-log tests to `tests/python/test_zfs_repository.py`.
- Updated `tests/test-zfsscruball` to assert the new `DEBUG` messages before
  `zpool scrub -w` and `zpool scrub -p`.

## 0.59.2

### Changed

- **Scrub resume is queue-driven and non-preemptive** — In the Pools tab,
  **Resume Scrub** and **Start Scrub** on a paused pool now return the pool to
  the pending queue instead of issuing `zpool scrub` immediately. The scrub
  manager resumes pending live-paused pools only when a scrub slot is available,
  so resumed scrubs no longer preempt scrubs that are already running. Pools
  paused only because the simultaneous target was lowered are still resumed
  automatically when a slot frees up.

### Tests

- Expanded `tests/python/test_scrub_manager.py` and
  `tests/python/test_pool_actions.py` to cover queue-driven resume, re-queueing
  paused pools via **Start Scrub**, and non-preemptive pending-paused promotion.

## 0.59.1

### Changed

- **Schedule tab multi-selection** — The profile list now uses GTK multi-selection
  consistently. The detail pane, cron edits, revert, and delete actions read the
  first selected row (in tree order) when multiple rows are selected. **Run Now**
  continues to execute every selected profile.

### Tests

- Updated `tests/python/test_schedule_page.py` mocks and added
  `TestScheduleDelete` to cover the new multi-selection Delete behavior.

## 0.59.0

### Added

- **Pause scrubs during Backup/Offsite/Restore** — Each of these tabs now has
  an option to **pause scrubs on the source and destination pools while each
  send/receive step is running**. Scrubs resume automatically when the step
  finishes. The option is stored in the JSON config under the tab's section and
  also applies to headless profile/cron runs via `profile_runner.py`. Already
  paused scrubs are left untouched.
- **Run Now for scheduled profiles** — The Schedule tab supports selecting one
  or more profiles and clicking **Run Now** to execute them immediately. Run Now
  ignores the **Active** checkbox; output streams to the info panel with a
  `[profile-name]` prefix so concurrent profiles can be distinguished.
- **Profile overwrite confirmation** — Recalling a profile and saving it under
  an existing name now prompts for overwrite confirmation via
  `profile_dialogs.py`.

### Changed

- **Scrub control decoupled from dataset lock manager** — `scrub_manager.py`
  and `zfsscruball` now consult live `zpool status` scrub state instead of
  acquiring hierarchical dataset locks. This makes scrub pause/resume/start/stop
  independent of backup, restore, prune, and dataset-destruction jobs; the worst
  race outcome is a logged warning from ZFS rejecting an invalid transition.
- **`zfsscruball` pause/resume** — `zfsscruball` now accepts `pause` and
  `resume` arguments and tracks completed pools in `/tmp/zfsscruball.state`.
- **Cron output suppression** — `cron_manager.py` prefixes scheduled profile
  lines with `mkdir -p /run/lock/zfs/profiles &&` and suffixes them with
  `> /dev/null 2>&1`. This prevents cron from mailing profile-runner output on
  systems where `MAILTO=""` alone is not honoured, while the runner continues
  to log everything to the session log file.
- **Configuration schema** — Migration 16 → 17 adds the `pause_scrubs` flag to
  the Backup, Offsite, and Restore config sections.

### Tests

- Expanded `test_scrub_manager.py`, `test_profile_runner.py`,
  `test_schedule_page.py`, `test_backup_page.py`, `test_backup_runner.py`,
  `test_cron_manager.py`, `test_config_migrations.py`, `test_dashboard_page.py`,
  `test_pool_actions.py`, `test_profile_manager.py`, `test_profile_dialogs.py`,
  `test_action_dispatch.py`, and `test_restore_page.py` to cover the new scrub
  pause, Run Now, overwrite, and cron-output features.
- Updated `tests/test-zfsscruball` and `tests/test-zfsdelallsnaps` for the new
  pause/resume behaviour and lock integration.

## 0.58.0

### Added

- **Phase 4 shared-state file locking** — New `07 GTK + Python/file_locking.py`
  provides advisory `flock` context managers for the JSON config, backup
  history, session-log index, and scrub state files. The `zfsconfig` bash
  helper uses the same lock files so Python and bash interoperate.
  `add_history_entry()` now performs its read-modify-write under a single
  exclusive lock.
- **Phase 5 per-profile advisory locks** — `profile_runner.py` acquires a
  profile-specific lock under `/run/lock/zfs/profiles/`. Duplicate cron
  invocations exit with code `0` and an informative log, preventing duplicate-run
  email. `cron_manager.py` wraps scheduled profile lines with `flock -n -E 0`,
  and the Dashboard Running Tasks list shows active profiles.
- **Phase 6 profile integration tests** — New
  `tests/python/test_profile_integration.py` runs concurrent profiles in
  separate subprocesses and verifies disjoint datasets run in parallel,
  same-dataset conflicts fail safely, and backup+prune operations serialize.
- **Python lock client** — New `07 GTK + Python/zfs_lock_manager.py` reads and
  writes the same JSON lock files as `zfslockmanager`, so Python mutators
  participate in the same lock hierarchy as bash scripts.
- **Snapshot-name coordination** — `zfssnapbuild` and
  `feature_config.generate_snapshot_name()` now acquire a brief global lock
  (`/run/lock/zfs/.snapname.lock`) and record the issued name in a one-minute
  reservation file (`/run/lock/zfs/.snapname.reserved`) shared between bash and
  Python.
- **Profile user guide** — New `06 Docs/docs/user-guide/profiles.md` documents
  creating, scheduling, running, and resolving conflicts for profiles.

### Changed

- **Lock-before-snapshot ordering** — `zfs-send-receive` now acquires `w` locks
  on the source and destination datasets before creating or selecting a
  snapshot, closing the race where concurrent jobs could force an incremental
  receive with `-F` to roll back a newer snapshot.
- **Per-operation lock coverage** — `zfscleanup`, `zfsretain`, `zfsdelfs`, and
  `zfsscruball` now acquire the appropriate dataset or pool locks through
  `zfslockmanager` or `zfs_lock_manager`.
- **`<offsite>` placeholder expansion** — `zfscheckagainst` now allows the
  `<offsite>` placeholder in either the Dataset or Counterpart column of the fss
  table, expands every occurrence at run-time, and skips the meaningless
  self-check against the source pool.
- **Session-log defenses** — Python runners enforce a 1 GB session-log cap with
  100 MB tail + 64 KB start retention when the cap is exceeded. The Logs tab
  opens files larger than 1 MB tail-first and offers a "Load Full Log" button.
- **`zfslockmanager` multiple-lock helper** — Added
  `zfslock_acquire_multiple <type> <dataset> ...` for deadlock-free acquisition
  of several locks.
- **Cron output suppression** — `cron_manager.py` now prefixes scheduled profile
  lines with `mkdir -p /run/lock/zfs/profiles &&` and suffixes them with
  `> /dev/null 2>&1`. This prevents cron from mailing profile-runner output on
  systems where `MAILTO=""` alone is not honoured, while the runner continues
  to log everything to the session log file.

### Tests

- Added `tests/python/test_file_locking.py`,
  `tests/python/test_zfs_lock_manager.py`,
  `tests/python/test_profile_runner_concurrency.py`,
  `tests/python/test_profile_integration.py`, and `tests/test-zfsscruball`.
- Expanded lock, file-locking, snapshot-name, profile concurrency, and offsite
  placeholder coverage across the existing bash and Python test suites.

## 0.57.0

### Added

- **Weekday ordinal cron scheduling** — the Schedule tab and `cron_manager.py`
  now support ordinal qualifiers in the Day-of-Week field: `6#1` (first
  Saturday), `6#2` through `6#5`, `6#L` (last Saturday), lists such as
  `6#1,3`, and ranges such as `6#1,3-5`. `interpret_cron()` and
  `next_run_times()` parse and describe these expressions; `generate_cron_line()`
  strips the ordinal suffix when writing `/etc/cron.d/zfsutilities` because
  standard cron does not understand it.
- **Runtime weekday-ordinal guard** — `profile_runner.py` applies the ordinal
  check at profile execution time so scheduled jobs skip days that do not match
  the requested weekday occurrence.
- **Persistent paned divider positions** — `gui_helpers.UIStateManager` now
  saves and restores the divider position of registered `Gtk.Paned` widgets.
  The Pools tab uses this to persist the split between the pool/scrub table
  and the scrub state table.
- **Concurrency and collision risks document** — new
  `developer-guide/concurrency-collisions.md` documents what the lock manager
  protects today, the shared resources each job type touches, and unaccounted
  collision scenarios (prune vs backup/restore, concurrent prunes, dataset
  destroys, snapshot-name collisions, config/state-file races, scrub management
  races, headless `profile_runner.py` concurrency, and GUI tab isolation gaps).

### Fixed

- **Docs viewer WebKit callback signature** — `docs_viewer.py`
  `_on_theme_captured()` now accepts the optional third user-data argument
  expected by newer WebKit2/GTK versions.

### Tests

- Added `TestUIStateManagerPanedPositions` in
  `tests/python/test_gui_infrastructure.py` covering paned restore, ignored
  zero positions, and save collection.
- Expanded `tests/python/test_cron_manager.py` to cover weekday ordinal
  parsing, formatting, interpretation, and next-run computation.
- Expanded `tests/python/test_profile_runner.py` to cover the runtime ordinal
  guard and cron-line stripping behavior.
- Expanded `tests/python/test_pools_page.py` to cover scrub panel expansion
  and paned wiring.
- Fixed GTK mock isolation in `tests/python/test_gui_infrastructure.py` so
  `bold_label` and `add_scrolled_text_view` tests pass when the module is run
  directly.

### Documentation

- Updated `user-guide/gtk-gui.md` with the weekday ordinal syntax, examples,
  and the note that standard cron receives a plain weekday while the runtime
  guard handles the ordinal.
- Updated `commands-and-modules/python-modules.md` to document
  `_parse_weekday`, `_match_weekday_ordinal`, `_format_ordinal_specs`, and
  `_check_weekday_ordinal`.
- Updated `developer-guide/testing.md` test counts for `test_cron_manager`,
  `test_gui_infrastructure`, and `test_profile_runner`.

## 0.56.1

### Added

- **Python Modules reference** — new `commands-and-modules/python-modules.md`
  documents all 43 Python modules that make up the GTK GUI and command-
  orchestration layer in `07 GTK + Python/`. The page is grouped by role
  (config/data, ZFS repository/info, command builders/runners, GUI pages,
  managers/helpers, entry points) and cross-references the bash commands and
  modules they invoke.

### Changed

- **Commands reference expansion** — `commands-and-modules/commands.md` now
  covers many previously undocumented root-level scripts (e.g.
  `check-prerequisites`, `deploy-version`, `git-release`, `run-tests`,
  `startdocserver`, `switch-version`, `uninstall-version`, `zfsallthepools`,
  `zfssendrepo`) and adds Arguments, Globals, Called modules, Data structures,
  Internal flow, and Return codes tables throughout.
- **Modules reference expansion** — `commands-and-modules/modules.md` adds
  detailed entries for `bashinit`, `zfsbuildfsarray`, `zfscheckagainst`, and
  other sourceable helpers with consistent structure.
- **Two-node reference expansion** — `commands-and-modules/two-node.md`
  documents the `node-lib.sh` helper functions and adds detailed sections for
  `clone-vm`, `deploy-version`, `iscsi-add-encrypted-luns`,
  `iscsi-restore-luns`, `list-vm-disks`, `lock-zfs-keys`, and others.
- **MkDocs navigation** — `mkdocs.yml` and `commands-and-modules/index.md` now
  list four sections, including the new Python Modules page.
- **Data structures update** — `developer-guide/data-structures.md` now notes
  that `unretire-vm`, `zfs-send-receive` rebuild, `move-vm-disk` source side,
  and `zfsdelfs` iSCSI teardown also maintain the
  `/etc/rtslib-fb-target/expected-backstores.txt` manifest.

### Tests

- Added `TestPythonModulesReference` in `tests/python/test_docs_integrity.py`
  to verify every module documented in `python-modules.md` exists as a real
  file in `07 GTK + Python/`.
- Added `extract_python_module_names()` helper in `tests/python/test_support.py`
  to parse module names from `### \`module.py\`` headers.

## 0.56.0

### Added

- **Pool error reporting** — `ZfsRepository.pool_status_errors()` parses
  `zpool status` and surfaces both permanent data errors and vdev
  READ/WRITE/CKSUM counter errors. The Pools tab now shows an **Errors**
  column with green `No errors` or a red/bold error summary; offline or
  unavailable pools show `—`.
- **Dashboard pool-error warnings** — the Warnings list now includes any pool
  whose `zpool status` reports errors.
- **Scrub ETA** — `scrub_manager.parse_scrub_status()` extracts the remaining
  time from `zpool status` (`HH:MM:SS to go` or `N days HH:MM:SS to go`) and
  computes an estimated completion timestamp. Running scrub tasks in the
  Dashboard show this ETA alongside the percentage.
- **Dashboard ZFS version display** — the Configuration card now lists the
  **ZFS version(s)** in use. In two-node mode it fetches the version from the
  remote storage/compute hosts, deduplicates identical hosts, and labels each
  by role.

### Tests

- Expanded `tests/python/test_zfs_repository.py` to 30 tests, adding
  `TestPoolStatusErrors` for no-error, data-error, and vdev-error scenarios.
- Expanded `tests/python/test_pools_page.py` to 17 tests, adding
  `TestErrorsSummaryForPool` and `TestPoolErrorsCellFunc` for label translation,
  subprocess-error fallback, and color/weight styling.
- Expanded `tests/python/test_scrub_manager.py` to 35 tests, adding coverage
  for `remaining_seconds` and `eta` extraction.
- Expanded `tests/python/test_dashboard_page.py` to 117 tests, adding coverage
  for status-error warnings, scrub ETA display, local/remote ZFS version lookup,
  and two-node host deduplication.

### Documentation

- Updated `user-guide/gtk-gui.md` to describe the new Pools tab **Errors**
  column, Dashboard pool-error warnings, scrub ETA, and ZFS version row.
- Updated `developer-guide/data-structures.md` with `ZfsRepository.pool_status_errors()`
  and the new `ScrubInfo.remaining_seconds` / `ScrubInfo.eta` fields.
- Updated `developer-guide/testing.md` test counts for
  `test_dashboard_page`, `test_scrub_manager`, and `test_zfs_repository`.

## 0.55.6

### Fixed

- **`BackupRunner` session-log reuse** — `cancel()` and the rc=9 abort path now
  reset `_session_log_file` and `_session_start_time` to `None`, just like
  `_finish()` already did. A `BackupRunner` instance can now start a fresh
  session log for a subsequent run instead of reusing or appending to the
  previous run's file.
- **`log_index.py` last-trailer wins** — `_update_entry_from_text()` no longer
  stops at the first `# END` trailer. It scans to the end of the text so that
  reused or appended session logs report the status, duration, and transfer
  bytes of the **final** run, and the highest message level found anywhere in
  the file.

### Tests

- Expanded `tests/python/test_backup_runner.py` to 24 tests, adding
  `TestSessionLogReuse` to verify a second run gets a fresh log file and that
  `cancel()` clears the session-log state.
- Expanded `tests/python/test_log_index.py` to 29 tests, adding coverage for
  multiple trailers in both `scan_file()` and `update_entry_incrementally()`.

### Documentation

- Updated `developer-guide/architecture.md` to describe `BackupRunner`
  session-log reset behavior and the persistent log index's last-trailer-wins
  semantics.
- Updated `developer-guide/data-structures.md` with the same last-trailer-wins
  note for the session-log index.
- Updated `user-guide/gtk-gui.md` (Logs tab) to mention reused/appended logs.
- Updated `developer-guide/testing.md` test counts for `test_backup_runner`
  and added the `test_log_index` row.

## 0.55.5

### Added

- **Configurable session-log size cap** — `config_core.py` adds a
  `session_log_max_bytes` setting with a default of **10 MB**. The cap is read
  from `/root/.config/zfsutilities.json`; use
  `config_core.get_session_log_max_bytes()` and
  `config_core.save_session_log_max_bytes()` to read or change it.
- **Live log viewer buffer cap** — while tailing a running log, the Logs tab
  viewer now keeps only the most recent **2 MB** of characters in memory and
  drops older content, preventing unbounded RAM growth on very long-running
  jobs.

### Changed

- **Session-log truncation defaults reduced** — `logging_config.py` now uses a
  10 MB maximum, 1 MB tail, and 64 KB start by default (down from the previous
  hard-coded 1 GB / 100 MB / 64 KB). The values are still configurable via
  `session_log_max_bytes`.
- **`zfs-send-receive` non-interactive handling** — when stdin is not a TTY,
  rollback prompts (common snapshot exists but destination is newer) and
  resume-token validation errors now skip the dataset with a `WARN:` message
  instead of hanging indefinitely.

### Fixed

- **`autoproceed='Y'` now covers rollback and resume-token prompts** — in
  `zfs-send-receive`, a destination rollback required by a common snapshot is
  performed automatically when `$autoproceed='Y'`, and resume-token validation
  failures abort the token and retry without prompting.

### Tests

- Expanded `tests/python/test_config_core.py` to 23 tests covering
  `session_log_max_bytes` read/write helpers.
- Expanded `tests/python/test_logging_config.py` to 26 tests covering the
  configurable cap and default values.
- Expanded `tests/python/test_logs_page.py` to 35 tests covering the live
  viewer buffer cap.
- Expanded `tests/test-zfs-send-receive-dryrun` to 22 tests covering rc=16
  autoproceed rollback and non-interactive skip behavior.

## 0.55.4

### Added

- **Scrub-table refresh burst** — after any manual scrub action in the Pools tab
  (Start, Pause, Resume, Stop), the scrub status table refreshes several times
  over the next few seconds. This gives immediate visual feedback even when the
  normal refresh interval is long.

### Fixed

- **Resume Scrub issues `zpool scrub` immediately** — the Resume button now
  calls `zpool scrub` for selected paused pools before returning them to the
  pending queue, instead of relying solely on the queue tick to restart them.
- **Pending pools no longer promoted while still live-paused** — after a resume,
  `zpool status` can briefly continue to report a pool as paused. The scrub
  manager now waits until the scrub shows as scanning before moving the pool
  from pending to active.
- **Stale "scrub paused" continuation lines filtered** — `parse_scrub_status()`
  drops stale `scrub paused` lines that can appear alongside `scrub in progress`
  right after a resumed scrub starts.

### Tests

- Expanded `tests/python/test_scrub_manager.py` to 31 tests covering the
  refresh-burst scheduling, resume-only-paused logic, stale-paused scan-line
  filtering, and the pending-paused queue tick behavior.

## 0.55.3

### Changed

- **GUI single-instance behavior** — a second launch of the GUI now automatically
  terminates the existing instance instead of showing a confirmation dialog. A
  transient wait dialog is displayed while the previous window closes, and GTK
  events are pumped so the dialog remains responsive.
- **`--replace` is a compatibility no-op** — the flag is still accepted, but
  replacement is now the default behavior.

### Fixed

- **Logs tab column-header tooltips** — tooltips are now attached to a
  `Gtk.Label` widget set with `TreeViewColumn.set_widget()`, because
  `Gtk.TreeViewColumn` is not a `Gtk.Widget` and cannot display tooltips itself.

### Tests

- Expanded `tests/python/test_main.py` to 41 tests covering auto-replace,
  transient wait-dialog creation, event pumping, retry after remote registration,
  and `--replace` as a no-op.
- Expanded `tests/python/test_logs_page.py` to 33 tests covering column-header
  label tooltips.

## 0.55.2

### Added

- **Session log size cap** — `logging_config.py` adds a 1 GB cap on session log
  files. Logs that exceed the cap are rewritten as 64 KB of opening context, a
  marker line, and 100 MB of recent tail. The Python runners (`backup_runner.py`
  and `profile_runner.py`) check the shared log file every 5 seconds, so the cap
  also bounds output written by inherited bash subprocesses. After truncation,
  the persistent log index entry for that file is removed so the Logs tab
  rescans the smaller file.
- **Tail-only log viewer** — the Logs tab now opens files larger than 1 MB at
  the tail instead of loading the entire file from the start. A **Load Full
  Log** button (with a size warning confirmation) lets you read the whole file
  when needed.
- **Logs tab clarity** — the `Size` column is renamed to `Log Size` and all
  log-list columns now have tooltips explaining the difference between log size
  and transfer bytes.

### Tests

- Added `test_logging_config.py` cases for `truncate_session_log()`.
- Added `test_backup_runner.py` and `test_profile_runner.py` cases verifying
  that truncation resets the persistent log index entry.
- Added `test_logs_page.py` cases for tail-only loading and the Load Full Log
  confirmation dialog.

## 0.55.1

### Fixed

- **Large session log files no longer exhaust RAM on GUI startup** —
  `log_index.py::scan_file()` previously read the entire log file into memory
  with `fh.read()`. A session log that grew to ~18 GB caused the GUI process
  to consume all system memory and swap, making the GUI unresponsive and the
  node unstable. `scan_file()` now scans only the trailing portion of files
  larger than 1 MB, which is where the trailer and recent message levels live.

### Tests

- Added `test_log_index.py` cases for large-file tail scanning, including
  trailer detection, highest-level extraction, and running-status handling
  when no trailer is present.

## 0.55.0

### Added

- **`enroll-efi-keys-vm`** — new `08 Two-node/` helper that re-initializes a
  Proxmox VM's EFI vars disk with the Microsoft UEFI CA 2023 certificates.
  Grows the backing EFI zvol to 4M, rewrites it from `OVMF_VARS_4M.ms.fd`, and
  updates the VM config with `size=4M` and `ms-cert=2023k`. Supports two-node
  configurations by delegating to the compute host via SSH.
- **Secure Boot 2023 certificate pre-enrollment** — `new-vm-disk` now emits
  `ms-cert=2023k` on the `efidisk0` line when Secure Boot is enabled, so new
  VMs boot with the current Microsoft UEFI CA already enrolled.
- **`unretire-vm --new-vmid <id>`** — retired VMs can be unretired under a new
  VM ID. The script rewrites disk lines, regenerates `vmgenid` and `smbios1`
  UUIDs, and interactively prompts for a new VM ID when the original is still
  in use. A test mode (`UNRETIRE_VM_TEST_NO_ROOT=1`) enables unit testing.
- **Datasets tab full-path search** — the Datasets tree search can now match
  full ZFS dataset paths, not just the displayed node label. Lazy-loaded
  ancestors are expanded automatically when a match is selected.
- **Documentation viewer auto-elevation** — `zfsutilities-docs` (`docs_viewer.py`)
  automatically relaunches through `pkexec` when not run as root, preserving
  `DISPLAY`, `XAUTHORITY`, and `WAYLAND_DISPLAY`.
- **Internals reference expansion** — `commands-and-modules/commands.md` now
  includes Called modules, Data structures consumed/produced, Internal flow,
  and Return codes tables for most entries. `developer-guide/data-structures.md`
  adds sections for snapshot-name persistence, scrub state, and the
  `zfsscruball` state file.

### Changed

- `deploy-version` now symlinks `enroll-efi-keys-vm` into the deployed `bin/`
  directory, and both installers include it in their script lists so the helper
  is available after installation.
- `unretire-vm` validation was refactored for robustness and now supports
  single-node and two-node storage-reference conventions.

### Tests

- Added `tests/test-enroll-efi-keys-vm` (5 tests) covering `parse_efidisk_line()`
  and `update_efidisk_config()`.
- Added `tests/test-new-vm-disk` (3 tests) covering `build_efidisk_line()`.
- Added `tests/test-unretire-vm` (6 tests) covering `--new-vmid`, prompting,
  UUID regeneration, and conflict rejection.
- Expanded `tests/test-deploy-version` with tests verifying
  `enroll-efi-keys-vm` is included in `TWO_NODE_SCRIPTS` and symlinked into
  the deployed `bin/` directory.
- Updated `tests/test-module-dependencies` so its source-line regex handles
  quoted paths such as `source "$MYDIR/rootcheck"`.
- Expanded `tests/python/test_gui_infrastructure.py` for `TreeSearch` full-name
  matching, `expand_path_to_row()`, and `_goto_match()` /
  `_update_matches_from_store()`.
- Expanded `tests/python/test_docs_viewer.py` for `pkexec` root elevation and
  optional environment-variable omission.
- Expanded `tests/python/test_datasets_page.py` to ensure
  `refresh_datasets_page()` re-runs an active search.

### Documentation

- Added `enroll-efi-keys-vm` to `commands-and-modules/two-node.md` and updated
  `user-guide/proxmox-integration.md` to describe EFI key enrollment and the
  `--new-vmid` option.
- Streamlined and updated `user-guide/gtk-gui.md`, `user-guide/concepts.md`,
  `user-guide/daily-backup.md`, `user-guide/offsite-backup.md`,
  `user-guide/retention.md`, and `user-guide/restore.md` for clarity and
  consistency.
- Fixed a typo in `user-guide/retention.md`.
- Added `InternalsDocPlan.md` documenting the phased plan to enhance the
  Commands & Modules Reference.

## 0.54.1

### Added

- **`<offsite>` placeholder in the Dataset column** — `zfscheckagainst` fss
  table rows may now use `<offsite>` in the Dataset value. Every occurrence is
  replaced at run-time with each pool marked as an offsite candidate in the
  Pools tab, creating one expanded row per candidate.
- **`<offsite>` anywhere in the Counterpart column** — the token is no longer
  restricted to a prefix or `<offsite>/suffix`; it may appear anywhere in the
  Counterpart value (e.g. `poolA/<offsite>/backup`).
- **Self-check skipping** — rows expanded from an `<offsite>` dataset skip the
  meaningless check of a pool against itself (e.g. `z22tb/temp` vs.
  `z22tb/temp`).

### Changed

- Updated the Checkagainst tab help text in the GTK GUI to document that
  `<offsite>` may appear in the Dataset or Counterpart column.

### Tests

- Expanded `tests/test-zfscheckagainst` from 22 to 26 tests, adding coverage
  for dataset-placeholder expansion, no-candidate handling, dual-column
  expansion, and non-leading counterpart placeholders.

### Documentation

- Updated `commands-and-modules/modules.md` and
  `developer-guide/data-structures.md` to describe `<offsite>` use in Dataset
  and Counterpart values.
- Updated `user-guide/gtk-gui.md` Checkagainst tab description.
- Updated `developer-guide/testing.md` with the current
  `test-zfscheckagainst` count.

## 0.54.0

### Changed

- **Deployment vs. activation separation** — `deploy-version` now only places
  software in `/usr/local/lib/zfsutilities/versions/<version>/` and no longer
  creates production wiring such as `/root/bashinit`, `PATH` configuration,
  library symlinks, or the `/usr/local/lib/zfsutilities/bin` symlink.
- **`switch-version` is the wiring authority** — all production wiring
  (`/root/bashinit`, `/etc/profile.d/zfsutilities.sh`,
  `/etc/sudoers.d/zfsutilities`, library symlinks, desktop shortcuts, and
  cleanup of old `/usr/local/bin` symlinks) is now created or refreshed by
  `switch-version`.
- **Version-specific uninstall** — `switch-version` supports `--uninstall` to
  remove the wiring installed by a given version. When switching to a new
  version, the currently active version's `switch-version --uninstall` is
  invoked first so version-specific wiring can be cleaned up.
- **Two-node compute host activation** — `install-two-node` now runs
  `switch-version` on the compute host via SSH so both hosts are wired after
  installation.

### Tests

- Added `tests/test-switch-version` covering wiring creation, prior-version
  uninstall invocation, `previous` rollback, `--uninstall`, `--list`, and
  graceful handling of a missing prior `switch-version`.
- Updated `tests/test-deploy-version` to assert that `deploy-version` no
  longer creates production wiring.
- Updated `tests/test-installer-checks` to source the new
  `desktop-launcher-lib.sh` and include the launcher helper tests in the
  summary.

### Documentation

- Updated `installation/index.md` to describe `deploy-version` as a pure
  placement tool and `switch-version` as the wiring authority.
- Updated `commands-and-modules/two-node.md` with the new `switch-version`
  syntax (`--uninstall`), wiring responsibilities, and corrected two-node
  behavior.
- Updated `developer-guide/architecture.md` to describe `switch-version` as
  the wiring authority and document `switch-version --uninstall`.
- Updated `developer-guide/testing.md` with current bash test-suite counts
  and the new `test-switch-version` suite.
- Updated `user-guide/retention.md` to document persisted prune-pool order
  (`prune_pools_order`) and visual-order execution.

## 0.53.2

### Added

- **Dict-style pool registry entries in `zfsconfig`** — `config.pools` entries
  may now be `{"name": "pool", "offsite_candidate": true}` objects in addition
  to plain strings. `zfsconfig_get_pools` emits the `name` field for both forms,
  and `zfsconfig_get_offsite_candidates` selects only objects marked
  `offsite_candidate: true`.
- **`zfscleanup` fallback to online pools** — when run without a specific pool
  argument and the JSON config has no registered pools, `zfscleanup` now falls
  back to all online pools (`zpool list -Ho name`) instead of silently doing
  nothing.

### Tests

- Added `tests/test-zfscleanup` covering configured-pool selection, explicit
  pool argument, fallback to online pools, and skipping of offline pools.
- Expanded `tests/test-zfsconfig` for string/dict/mixed pool entries and
  missing/empty/null name handling.

### Documentation

- Updated `commands-and-modules/commands.md` for the `zfscleanup` fallback
  behavior and argument defaults.
- Updated `commands-and-modules/modules.md` for dict-style pool entries in
  `zfsconfig`.
- Updated `developer-guide/testing.md` with the new `test-zfscleanup` suite
  and revised `test-zfsconfig` count/description.
- Updated `user-guide/retention.md` to note the online-pool fallback.

## 0.53.1

### Added

- **Standalone documentation viewer launcher** — `docs_viewer.py` now has a
  `main()` entry point and is symlinked as `zfsutilities-docs` by
  `deploy-version` and the installers.
- **Desktop shortcuts** — `install-single-node` and `install-two-node` create
  **ZFSutilities GUI** and **ZFSutilities Documentation** shortcuts in the
  installing user's home directory via new `installer-lib.sh` helpers.
- **Restore tab auto-destination persistence** — enabling **Auto-determine
  destination** computes and installs the destination; disabling it restores the
  previous manual destination. The destination is refreshed when the Restore tab
  is opened or the source entry changes while auto-destination is active.
- **Retention tab fresh-install cleanup** — on a new install, pool-specific
  policies imported from legacy `zfsretainpol-*` files are cleared, leaving only
  the `default` policy.
- **`is_new_install` flag on `AppContext`** — tracks whether the JSON config
  file was created fresh this session.

### Changed

- **GUI single-instance behavior** — instead of D-Bus remote activation, a
  second launch now shows a confirmation dialog asking whether to terminate the
  existing instance. The stuck-instance timeout was reduced from 30 seconds to
  10 seconds.
- **Restore Part 1 confirmation** — the restore now confirms the dataset list
  once and then proceeds automatically, rather than prompting before each
  dataset group.
- **Retention Prune list** — now shows only online pools that have an explicit
  retention policy; pools without a policy fall back to `default` and are not
  shown in the list.
- **`zfs-send-receive` autoproceed** — after the initial dataset-list prompt,
  `autoproceed` is set to `Y` so subsequent datasets proceed without further
  prompts.

### Tests

- Added `tests/python/test_docs_viewer.py` for the standalone docs viewer
  launcher.
- Expanded `tests/python/test_app_context.py` to cover `is_new_install`.
- Expanded `tests/python/test_main.py` for the new single-instance confirmation
  dialog.
- Expanded `tests/python/test_restore_page.py` for auto-destination behavior.
- Expanded `tests/python/test_retention_page.py` for fresh-install cleanup and
  prune-list filtering.
- Expanded `tests/python/test_retention_actions.py` for Add/Remove Policy
  prune-list refresh.
- Expanded `tests/python/test_gui_infrastructure.py` for the clear-button
  status-bar reset.
- Expanded `tests/python/test_zfsutilities_gui.py` for Restore tab destination
  refresh.
- Expanded `tests/test-deploy-version` for GUI/docs launcher symlinks.
- Expanded `tests/test-installer-checks` for desktop-user detection and symlink
  creation.
- Expanded `tests/test-zfs-send-receive-dryrun` for autoproceed prompt-once
  behavior.

### Documentation

- Updated the GTK GUI Reference for the single-instance confirmation dialog,
  `zfsutilities-gui` / `zfsutilities-docs` launchers, Restore tab
  auto-destination, and Retention tab changes.
- Updated the Installation guide for desktop shortcuts and the new launcher
  commands.
- Updated the Retention Policies guide for fresh-install cleanup and prune-list
  filtering.
- Updated `data-structures.md` for `AppContext.is_new_install`.
- Updated `testing.md` with new and expanded suite counts.
- Updated `commands-and-modules/two-node.md` to note the launcher symlinks
  created by `deploy-version`.

## 0.53.0

### Added

- **`<offsite>` placeholder in Checkagainst** — the Counterpart column in the
  Checkagainst tab and in `zfscheckagainst` now accepts `<offsite>` (or
  `<offsite>/suffix`), which expands at run-time to every pool marked as an
  offsite candidate in the Pools tab.
- **Offline hold-tag verification** — for snapshots with the `offsite` label,
  `zfscheckagainst` can verify safety even when a counterpart pool is offline by
  checking for another `@offsite` snapshot on the source that carries the
  `offsite-<pool>` hold tag.
- **Comment field for checkagainst entries** — the GUI table now has a Comment
  column, and a new `comment` key is stored in the JSON config for each
  checkagainst row.
- **`zfsconfig_get_offsite_candidates()`** — bash helper that returns the names
  of pools configured with `offsite_candidate: true`.
- **`installer-lib.sh`** — shared library used by both installers for
  interactive prompts, prerequisite-failure parsing, and optional doc-server
  setup.
- **New bash test suites** — `tests/test-zfscheckagainst` and
  `tests/test-zfsconfig`.

### Changed

- **`zfscheckagainst`** now loops over every expanded `<offsite>` candidate and
  aggregates per-candidate results before deciding whether deletion is safe.
- **`checkagainst_page.py`** table is now reorderable by dragging, all columns
  are editable, includes the Comment column, and documents the `<offsite>`
  placeholder.
- **`config_migrations.py`** bumped the JSON schema to version 15; the new
  `_migrate_14_to_15` function injects `"comment": ""` into existing
  checkagainst entries.
- **`check-prerequisites`** now supports `--single-node`, `--two-node`, and
  `--list-failures` modes; reports failures in a machine-readable format for the
  installer; treats Proxmox and MkDocs as optional.
- **`install-single-node` and `install-two-node`** now use `installer-lib.sh`,
  run interactive prerequisite checks with optional auto-install, make the
  MkDocs documentation server optional, and call `switch-version` from the repo.
- **`zfssendrepo`** is now tracked by git.

### Tests

- Added `tests/test-zfscheckagainst` (22 tests) covering `<offsite>` expansion,
  offline hold-tag verification, literal counterparts, missing-snapshot fatal
  error, and legacy `.conf` fallback.
- Added `tests/test-zfsconfig` (6 tests) for offsite-candidate selection and
  checkagainst field emission.
- Expanded `tests/python/test_checkagainst_page.py` to 35 tests, covering the
  Comment column, reorderable TreeView, cell editing, Save-button styling, and
  empty-field validation.
- Expanded `tests/python/test_config_migrations.py` to 28 tests, covering v15
  idempotency, non-dict entries, and the end-to-end v14→15 migration.

### Documentation

- Updated the GTK GUI Reference to describe the Checkagainst table's Comment
  column, reorderable rows, and `<offsite>` placeholder.
- Updated `modules.md` to list `zfsconfig_get_offsite_candidates`.
- Updated `architecture.md` to fix the `zfscheckagainst` return-code table and
  reference the v15 migration chain.
- Updated `data-structures.md` to show `pools` as strings or objects and
  reference the v15 migration chain.
- Updated `testing.md` with the new bash/Python suites and updated test counts.

## 0.52.3

### Changed

- **Dashboard section order** — the Dashboard tab now shows sections in the order
  **Warnings → Pool Health → Running Tasks → Recent Operations → iSCSI Issues →
  Configuration**, so the most actionable information appears first.
- **Low-space threshold moved into Pool Health** — the threshold spinner that sets
  the low-space warning percentage is now located inside the **Pool Health** section,
  directly above the pool table, instead of above all Dashboard sections.

### Tests

- Expanded `tests/python/test_dashboard_page.py` with layout tests that verify the
  new section order, the threshold spinner placement, frame/widget creation, and
  iSCSI hide/show behavior in single-node vs two-node mode.

### Documentation

- Updated the GTK GUI Reference to describe the new Dashboard section order and
  the threshold spinner's new location inside Pool Health.
- Updated the Testing guide and `AGENTS.md` to reflect the expanded
  `test_dashboard_page` suite count.

## 0.52.2

### Added

- **`MAILTO=""` in cron header** — `cron_manager.py` now writes `MAILTO=""` at the top of
  `/etc/cron.d/zfsutilities` so cron does not send email for scheduled profile runs.
  The GUI and `profile_runner.py` already write their own session logs.
- **Datasets tab refresh preserves scroll and selection** — refreshing the Datasets tab
  now remembers the vertical scroll offset and the current selection, restoring them
  after the tree is repopulated so the view does not jump to the top.

### Changed

- **Retention Policies label wording** — the description label now reads
  "selected pool" instead of "pool selected above" for consistency with the pool
  selector layout.

### Documentation

- Updated the GTK GUI Reference to show the full managed cron header, including
  `MAILTO=""`, `SHELL`, and `PATH`.
- Documented that the Datasets tab **Refresh** action preserves scroll position
  and selection.

### Tests

- Expanded `tests/python/test_cron_manager.py` to verify the new `MAILTO=""` header
  and its placement before generated cron lines.
- Expanded `tests/python/test_datasets_page.py` with tests for scroll preservation,
  `_restore_scroll` clamping, and missing-adjustment edge cases.

## 0.52.1

### Added

- **Persistent session-log index** — the Logs tab now keeps a JSON index at
  `/var/log/zfsutilities/sessions/.log_index.json` that caches each session log's
  size, status, duration, bytes transferred, and highest message level. This lets
  the Logs tab refresh quickly even with hundreds of large historical logs.
- **`log_index.py`** — new module responsible for scanning, incrementally
  updating, and persisting the session-log index.
- **Index updates from runners** — `BackupRunner` and `profile_runner` write the
  final status, duration, and bytes to the index after writing the session-log
  trailer.
- **Index maintenance in Logs tab** — `_scan_logs` builds or refreshes entries,
  `_tail_log_file` updates the current log incrementally, and deleting a log
  removes its entry.

### Changed

- **Logs tab status source** — the **Status** column now reads from the cached
  index; `WARN:`/`FATAL:` levels are surfaced as **Warn**/**Fatal** from the
  cached `highest_level` field.
- **Removed `_highest_msg_level()`** from `logs_page.py` because level scanning
  is now handled by `log_index.py`.

### Documentation

- Updated the GTK GUI Reference to describe the persistent log index and the
  updated **Status** column behavior.
- Added a **Persistent log index** subsection to the developer architecture guide.
- Documented the `.log_index.json` schema and lifecycle in the data-structures
  guide.

### Tests

- Added `tests/python/test_log_index.py` — unit tests for scanning, incremental
  updates, load/save round-trips, corrupt JSON recovery, and edge cases.
- Expanded `tests/python/test_backup_runner.py` with integration tests verifying
  trailer metadata is persisted to `LogIndex`.
- Expanded `tests/python/test_profile_runner.py` with integration tests verifying
  trailer metadata is persisted to `LogIndex`.
- Expanded `tests/python/test_logs_page.py` with integration tests for index
  creation/reuse and index cleanup on log deletion; removed the now-obsolete
  `TestHighestMsgLevel` tests.

## 0.52.0

### Added

- **Logs tab status override** — the Logs tab **Status** column now reflects the
  highest message level in the session log. If a completed or failed log contains
  `WARN:` or `FATAL:` messages, the status is displayed as **Warn** or **Fatal**
  instead of the generic **Done** or **Failed** label. **Running** logs keep their
  running status until they finish.

### Documentation

- Updated the GTK GUI Reference to document the new **Warn** and **Fatal** Logs
  tab status values.

### Tests

- Expanded `tests/python/test_logs_page.py` with tests for the new status override
  behavior, including `rc=0` with warnings, `rc=255` with warnings, `FATAL`
  precedence, and the running-state exception.

## 0.51.0

### Added

- **Expand Selected in Datasets tab** — the Datasets tab now has an **Expand
  Selected** action button. Select one or more pool, dataset, or snapshot rows
  and click the button to recursively expand them and their lazy-loaded
  descendants. Placeholder rows and hold tags are skipped.
- **`TreeSearch.freeze()` and `TreeSearch.thaw()`** — new helpers that suppress
  search re-runs while the tree is being expanded in bulk.

### Documentation

- Updated the GTK GUI Reference with the new **Expand Selected** Datasets tab
  action.
- Refreshed the Python test suite table in the developer testing guide.

### Tests

- Expanded `tests/python/test_action_dispatch.py` with Datasets page spec and
  handler tests.
- Expanded `tests/python/test_datasets_page.py` with button sensitivity and
  `expand_selected_datasets()` coverage.
- Expanded `tests/python/test_gui_infrastructure.py` with tests for
  `expand_tree_recursively()` and `TreeSearch.freeze/thaw()`.

## 0.50.2

### Added

- **Generate button in offsite confirmation dialog** — clicking **Run Offsite**
  now shows a dialog with **OK**, **Cancel**, and **Generate** buttons. Choose
  **Generate** to rebuild the offsite snapshot name and review it again before
  proceeding.
- **Auto-detect offsite pool on tab switch** — the Offsite tab now refreshes its
  **Detected pool** label automatically whenever the tab is selected, as well as
  when the tab is opened or reverted.

### Changed

- **Offsite tab layout** — the **Snapshot** section has moved from the top of
  the tab to just above the **Send/Receive Steps** section, so the snapshot name
  is reviewed immediately before the send/receive operations it will create.
- **`snapshot_manager.py` cleanup** — moved `create_dialog` to the top-level
  import, relocated `_repo()` after widget setup, and restored the constructor
  initialization order.

### Documentation

- Updated the GTK GUI Reference to reflect the new Offsite tab section order,
  the automatic offsite-pool detection on tab selection, and the **Generate**
  button in the offsite confirmation dialog.

### Tests

- Added `tests/python/test_offsite_page.py` — tests for automatic offsite-pool
  detection, snapshot-frame placement, and the Generate-button dialog loop.
- Expanded `tests/python/test_zfsutilities_gui.py` with tests for offsite-pool
  refresh behavior when switching to the Offsite tab.
- Expanded `tests/python/test_gui_infrastructure.py` with tests for
  `set_monospace_font`, `create_dialog`, `add_scrolled_text_view`,
  `get_tree_selection_items`, `get_expanded_rows`, and `restore_expanded_rows`.

## 0.50.1

### Added

- **`gui_helpers.bold_label()`** — new helper that returns a `Gtk.Label` rendered
  with bold Pango markup for section headings.
- **Generate button in backup confirmation dialog** — clicking **Run Backup**
  now shows a dialog with **OK**, **Cancel**, and **Generate** buttons. Choose
  **Generate** to rebuild the snapshot name and review it again before proceeding.

### Changed

- **Bold frame and expander headings** — all tabbed pages now render section
  headings (frames and expanders) in bold via `bold_label()` instead of plain
  frame labels.
- **Backup tab layout** — the **Snapshot** section has moved from the top of the
  tab to just above the **Send/Receive Steps** section, so the snapshot name is
  reviewed immediately before the send/receive operations it will create.

### Documentation

- Updated the GTK GUI Reference to reflect the new Backup tab section order,
  the bold section headings, and the Generate button in the backup confirmation
  dialog.

### Tests

- Added tests for `gui_helpers.bold_label()`.
- Added dialog-loop tests for the backup **Run** button (OK, Cancel, Generate).
- Added frame/expander label-widget tests for the Backup, Logs, Offsite,
  Restore, and Schedule tabs.
- Created `tests/python/test_restore_page.py` for Restore tab UI construction.

## 0.50.0

### Added

- **Offsite candidate flag in pool registry** — registered pools are now stored
  as dicts (`{"name": "...", "offsite_candidate": true|false}`). The Pools tab
  exposes an **Offsite** checkbox for each registered pool.
- **`get_pool_names()` and `get_offsite_candidate_names()` helpers** —
  `feature_config` and `backup_config` now provide helpers that return plain
  name lists from the dict registry.
- **Config schema version 14** — `config_version` is now `14`. Existing configs
  are automatically migrated to convert legacy string pool entries into dicts
  with `offsite_candidate = false`.

### Changed

- **Offsite pool candidates are managed in the Pools tab** — the Offsite tab no
  longer has a candidate-pools entry field. Candidates are selected via the
  Pools tab **Offsite** checkbox; the Offsite tab shows a read-only **Detected
  pool** label and refreshes automatically.
- **Removed Offsite tab actions** — **Detect Pool** and **Prune Offsite** buttons
  are gone. Pool detection is automatic; offsite snapshot pruning is handled by
  the Retention tab.
- **`save_pools()` syncs offsite candidates** — saving the pool registry writes
  candidate names into `config["offsite"]["offsite_pools"]` so existing offsite
  runners and saved profiles continue to work.
- **Restore auto-destination uses `get_pool_names()`** — unaffected by the
  registry format change.

### Documentation

- Updated the GTK GUI Reference to describe the new Pools tab **Offsite**
  checkbox, the simplified Offsite tab, and the automatic offsite-pool
  detection behavior.
- Updated the Offsite Backup page to remove the GUI **Prune Offsite** button
  reference and point users to the Retention tab for pruning `@offsite`
  snapshots.

### Tests

- Expanded `tests/python/test_feature_config.py` with dict-pool normalization,
  `get_pool_names`, `get_offsite_candidate_names`, and offsite-pool sync tests.
- Expanded `tests/python/test_config_migrations.py` with tests for the 13 → 14
  migration.
- Expanded `tests/python/test_backup_config.py` and
  `tests/python/test_page_runners.py` for the new registry helpers.
- Added `tests/python/test_pools_page.py` for the Offsite column, toggle, and
  drag-end flag preservation.
- Added `tests/python/test_pool_actions.py` for add/remove/save/revert with
  dict pools.
- Added `tests/python/test_offsite_page.py` for automatic offsite-pool
  detection and registry-based candidates.
- Added `tests/python/test_retention_actions.py` for retention-policy
  candidate extraction from dict pools.
- Expanded `tests/python/test_action_dispatch.py` to verify the removed
  Offsite buttons are no longer wired.

## 0.49.0

### Added

- **Independent level filters in GUI viewers** — the bottom-panel info log and
  the Logs tab viewer each have their own **Level** dropdown. Filtering no
  longer affects what `log_msg` writes to session log files or what bash
  subprocesses emit.
- **Logs tab multi-select and delete** — Ctrl/Shift-click to select multiple
  log files; **Delete Selected** removes them after confirmation. Right-clicking
  a row also offers **Delete selected log(s)**.
- **Logs tab viewer level filter** — the log viewer now has a **Level** dropdown
  that hides lower-priority messages without changing the underlying file.

### Changed

- **`log_msg` no longer filters by priority** — both bash and Python `log_msg`
  always emit every message to stderr/sink and to the session log file.
  Priority filtering is performed by the GUI viewers.
- **Pre-backup/post-backup labels** — remaining user-visible "script"
  references in the GUI and docs now say "command" consistently.

### Documentation

- Updated the GTK GUI Reference to describe the new info-panel level filter,
  Logs-tab multi-select, delete action, and viewer level filter.
- Updated the Data Structures guide to reflect `CONFIG_VERSION` 13, the full
  migration chain, and the backup object's post-backup command fields.
- Updated the Messages reference for viewer-based level filtering.
- Updated the Testing guide counts for `test_action_dispatch`,
  `test_backup_page`, `test_backup_runner`, and `test_zfsutilities_gui`.

### Tests

- Expanded `tests/python/test_zfsutilities_gui.py` with dry-run toggle and
  dataset runner tests.
- Expanded `tests/python/test_action_dispatch.py` with Logs page spec tests.
- Expanded `tests/python/test_backup_page.py` with pre/post command label tests.
- Expanded `tests/python/test_backup_runner.py` with the fatal pre-backup
  command message test.

## 0.48.1

### Added

- **Persistent prune snapshot label** — the snapshot label used by the
  Retention tab's **Prune** runner is now stored in the shared JSON config as
  `prune_label` (default: `dailybackup`). It survives GUI restarts and is
  honored by scheduled retention profiles.
- **`feature_config` prune-label helpers** — `get_prune_label(config)` and
  `save_prune_label(config, label)` read and write the global prune label.

### Changed

- **Backup tab label consistency** — the pre-backup and post-backup checkboxes
  now read **Run pre-backup command** and **Run post-backup command** to match
  the placeholder text and the fact that the entry is executed via `bash -c`.
  Step descriptions and log messages were updated to use "command" as well.
- **Config schema version 13** — `config_version` is now `13`. Existing configs
  are automatically migrated to add `prune_label = "dailybackup"`.
- **Retention tab Save/Revert scope** — **Save** now commits the currently
  visible pool, any pending bucket edits from other pools, and the prune label
  in one operation. **Revert** discards pending edits for every pool and
  restores the prune label, matching Save's scope.
- **Retention tab dirty detection** — changing the prune label or editing a
  previously-visited pool now marks the page dirty.

### Documentation

- Updated the Retention Policies page to describe the persistent global
  `prune_label`.
- Updated the GTK GUI Reference Retention tab section to describe the saved
  prune label and multi-pool Save/Revert behavior.
- Updated the Testing guide with corrected Python suite counts and the missing
  `test_retention_page` entry.

### Tests

- Expanded `tests/python/test_config_migrations.py` with tests for the
  12 → 13 migration.
- Expanded `tests/python/test_feature_config.py` with tests for
  `get_prune_label` and `save_prune_label`.
- Expanded `tests/python/test_retention_page.py` with tests for prune-label
  dirty detection, persistence, multi-pool pending edits, Save/Revert behavior,
  and profile round-trips.

## 0.48.0

### Added

- **Session log paths in history entries** — every backup, offsite, restore,
  and prune operation now records the path to its session log file in the
  backup history entry (`log_file`). GUI runs, scheduled profile runs, and
  direct CLI executions that create a session log all populate this field.
- **Dashboard "View Log" action** — the Dashboard tab now has a **View Log**
  action button. Select any row in the **Recent Operations** list and click
  **View Log** to switch directly to the Logs tab with that operation's session
  log selected and loaded.

### Changed

- **`zfslockmanager` lock-file PID detection** — the Dashboard stale-lock
  detector now reads the PID from the JSON content written by
  `zfslockmanager` (`{"dataset":"...","pid":12345,...}`). The previous
  `.pid.` filename fallback and companion `.pids/` file fallback remain
  supported for older lock files.

### Documentation

- Updated the GTK GUI reference to describe the new Dashboard **View Log**
  action and the hidden session-log column in **Recent Operations**.
- Updated the Testing guide with the expanded Python suite counts and the new
  `test_logs_page` suite.

### Tests

- Added `tests/python/test_logs_page.py` — 3 tests for
  `logs_page.select_log_by_path()`.
- Expanded `tests/python/test_dashboard_page.py` with tests for JSON lock-file
  PID parsing, the View Log button/action, and the hidden log-file column.
- Expanded `tests/python/test_action_dispatch.py` with tests for the dashboard
  "View Log" page spec and handler wiring.
- Expanded `tests/python/test_backup_history.py` with the empty-string
  `log_file` edge case.
- Expanded `tests/python/test_backup_runner.py` and
  `tests/python/test_profile_runner.py` to verify the session log path is
  recorded in history entries.

## 0.47.3

### Changed

- **Dataset destruction uses the async runner** — the Datasets tab now routes
  dataset deletion through a dedicated `Dataset action` `BackupRunner`, just like
  backups, offsite copies, restores, and retention. Each destroyed dataset
  becomes a separate `BashStep`, so progress is shown in the info panel, stdin
  input is forwarded if a step prompts, and the datasets page refreshes when the
  runner completes. Missing or already-running runner states are handled with a
  warning instead of crashing.
- **`zfsdelallsnaps` return code** — `delallsnaps` now returns `1` if any
  individual snapshot deletion fails, and `0` only when every snapshot is
  deleted successfully (or there is nothing to delete). This lets callers and
  profiles detect partial failures.

### Added

- **`tests/python/test_dataset_actions`** — 6 tests for the new runner-based
  `_delete_datasets` behavior: step building, runner start/callback, missing
  runner, busy runner, and cancel handling.
- **`tests/test-zfsdelallsnaps`** — 4 tests for the new return-code behavior:
  all-success returns `0`, any failure returns `1`, no snapshots returns `0`,
  and a filter that matches nothing returns `0`.

### Documentation

- Updated the `zfsdelallsnaps` command reference to note the new return-code
  behavior.
- Updated the Testing guide with the new suites and refreshed Python suite test
  counts.

## 0.47.2

### Fixed

- **`zfscheckagainst` missing dependency** — `zfscheckagainst` now sources
  `zfsremoveleadingqualifiers` so `remove_leading_qualifiers` is defined when
  `zfsdelsnap` runs the safety check. Previously the function was only
  available when `zfscheckagainst` was invoked from `zfsretain` or
  `zfs-send-receive`, causing `zfsdelsnap` to fail with
  `remove_leading_qualifiers: command not found` and report an empty
  counterpart dataset.

### Added

- **`tests/test-module-dependencies`** — new static checker that scans every
  root-level bash module and fails if a known module function is called without
  sourcing the module that defines it.

### Documentation

- Updated the Modules reference to note that `zfscheckagainst` depends on
  `zfsremoveleadingqualifiers`.
- Updated the Testing guide to describe the new `test-module-dependencies`
  suite and the expanded `test-zfsdelsnap` coverage.

## 0.47.1

### Added

- **Backup pull-step toggle** — the Backup tab now has an **Active** checkbox
  on the **Pull Steps (rsync)** frame. Unchecking it bypasses every pull step
  while still running pre-backup scripts, ZFS send/receive steps, and
  post-backup steps. The toggle is saved in the backup config as
  `pull_steps_active` and is honored by scheduled backup profiles and the
  headless `profile_runner.py`.

### Changed

- **Config schema version 12** — `config_version` is now `12`. Existing configs
  are automatically migrated to add `backup.pull_steps_active = true`.
- **TreeView column widths** — all GUI tables now use fixed-width, resizable
  columns via the shared `configure_treeview_column()` helper. The main window
  can be shrunk horizontally without columns forcing it wider; overflow is
  handled with horizontal scrollbars. Restored column widths are clamped to
  each column's own minimum width, and **View → Minimize Width...** resets
  columns to that minimum instead of a hard-coded 20 px.

### Documentation

- Updated the GTK GUI reference and changelog to describe the pull-step toggle
  and the improved column-width behavior.

## 0.47.0

### Changed

- **Retention Phase 2 pruning order** — `zfsretain` now deletes the oldest
  snapshots first when a bucket overflows its retention count. Empty snapshots
  (`written=0`) are still logged as `(empty)`, but they are no longer preferred
  over older snapshots that contain unique data. The most recent snapshot in
  each bucket remains protected as the incremental backup base when
  `retain > 0`; when `retain = 0` the most recent snapshot is also eligible
  for deletion.

### Documentation

- Updated user-guide and command-reference pages to describe the new Phase 2
  pruning behavior.
- Expanded `tests/test-zfsretain` coverage for oldest-first pruning, the
  `(empty)` log tag, and the `retain = 0` edge case.

## 0.46.8

### Changed

- **Schedule cron entry width** — the five cron parameter entry fields are now
  sized for 15 characters, making multi-value expressions such as `*/5`,
  `9-17`, and `1,15,30` easier to read and edit.

### Fixed

- **TreeView column width corruption on startup** — `UIStateManager` no longer
  saves column widths for TreeViews that are not yet realized or whose columns
  still report placeholder widths. This prevents hidden Gtk.Stack pages from
  overwriting saved widths with near-zero values before GTK allocates them.

## 0.46.7

### Added

- **Schedule tab sorting** — the Profile Name, Type, and Next Run columns in
  the Schedule tab are now sortable. Next Run sorting uses a hidden
  chronological key so dates order correctly regardless of the displayed
  formatted text.
- **Dry Run visual indicator** — the **Dry Run** toggle button label now turns
  red when dry-run mode is active, making it obvious at a glance that
  operations will be simulated.

### Changed

- **Schedule cron entry width** — the five cron parameter entry fields are now
  sized for two characters, improving readability of values such as `15` or
  `*/5`.
- **Next Run computation** — the Schedule tab now computes the Next Run value
  with `cron_manager.next_run_times()` instead of `format_next_runs()`,
  producing both a human-readable display string and a machine-readable sort
  key.

### Fixed

- **Dry-run size estimate log level** — when `zfs-send-receive` cannot obtain a
  stream size estimate in dry-run mode, it logs an `INFO` message rather than
  a `WARN`, since the missing estimate is expected when the target snapshot
  has not been created yet.

## 0.46.6

### Added

- **Dry-run scheduled profiles** — when you create a scheduled profile from the
  Backup, Offsite, Restore, or Retention tab, the current **Dry Run** toggle
  state is now saved in the profile. Scheduled executions then run in dry-run
  mode automatically, while on-demand runs from the GUI still use the live
  toggle. Recall a profile to review or change its stored dry-run flag before
  re-saving.

### Fixed

- **Local pull-step logging** — scheduled backup profiles now also stream rsync
  output from local pulls (including endpoints that resolve to the local host,
  such as `stewie:/etc/`) to `/var/log/zfsutilities/rsync-pull.log`, matching
  the behavior already implemented for remote pulls in 0.46.5. Previously these
  local pulls still flooded the session log shown in the GUI Logs tab.

## 0.46.5

### Added

- **Remote pull-step logging** — rsync pull steps and ZFS-keys backups that
  pull from a remote host now stream their output to
  `/var/log/zfsutilities/rsync-pull.log` on the source host instead of
  sending it back to the machine running the backup. The remote log file is
  truncated the first time it is used each day and appended to afterwards.

### Fixed

- **`zfsdailybackup` pull-step failures no longer abort the job** — a failed
  rsync pull (remote script push, `backup-installed-programs`, or
  `rsync-dailybackup`) is now logged as a `WARN:` and the backup continues with
  the remaining steps, matching the behavior already documented for pull steps.
- **Headless session log ordering** — `profile_runner.py` now streams
  subprocess output line-by-line with merged stdout/stderr, so the session
  log preserves the exact order the step emitted it and timestamps each line
  as it arrives.
- **Duplicate `# END` trailers** — `zfs-send-receive` and `zfsdailybackup`
  no longer write their own `# END` trailer when a Python runner owns the
  session log (`ZFSUTILITIES_LOG_INHERIT=Y`). This removes trailers that
  previously appeared in the middle of the log.

## 0.46.4

### Fixed

- **Lock Manager high CPU usage** — `zfslock_wait_or_resolve()` now throttles
  repeated lock-acquisition attempts with a short backoff, so a closed stdin or
  an invalid choice cannot spin the CPU. `ZFSLOCK_WAIT_INTERVAL` is also guarded
  to a minimum of 1 second in both the conflict prompt and `zfslockctl wait`.

### Added

- **Lock Manager "Retry now" option** — when a lock conflict occurs, the prompt
  now offers `[R] Retry now`, which immediately re-checks whether the lock can be
  acquired. This lets users resolve a conflict externally and retry without
  waiting for the polling interval.

### Changed

- **Lock Manager headless behavior** — when stdin is not a TTY or
  `ZFSUTILITIES_HEADLESS=Y` is set, the lock manager logs a `FATAL:` message and
  aborts instead of prompting.

## 0.46.3

### Fixed

- **Datasets tab expansion** — expanding a dataset row now correctly loads its
  snapshots and direct child datasets. The regression in 0.46.1/0.46.2 used
  `zfs list -t snapshot -d 0 <dataset>`, which does not list a dataset's own
  snapshots. The GUI now uses `-d 1` and filters out snapshots that belong to
  direct children, matching the convention already used by the bash scripts.

### Changed

- Removed the temporary INFO-level diagnostics that were added in 0.46.2 to
  trace the Datasets tab expansion problem.

## 0.46.2

### Added

- Temporary diagnostics for the Datasets tab expansion regression:
  - `07 GTK + Python/diagnose_zfs_repository.py` exercises the same
    `ZfsRepository` calls the GUI uses, without launching the GUI.
  - INFO-level logging in `on_row_expanded` and `load_dataset_children`.

## 0.46.1

### Fixed

- **Datasets tab expansion regression** — `load_dataset_children` was calling
  `repo.list_datasets(pool=ds_name)` to load snapshots, but `list_datasets`
  lists only filesystems and volumes. It now uses `repo.list_snapshots()`.

### Changed

- Extended `SnapshotRow` and `list_snapshots` to return the full 8-column field
  set (`name,creation,type,used,avail,refer,origin,clones`), matching the tree
  column layout.
- Added `tests/python/test_datasets_tree.py` regression tests.

# Changelog

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

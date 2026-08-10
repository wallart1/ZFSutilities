# Changelog

## 0.79.0

*Released 2026-08-09*

### Added

- **`space_check_min_buffer` environment variable** — `zfs-send-receive` now
  lets callers override the 1 GiB minimum destination free-space buffer used
  during space checks. Setting this to `0` allows the real-pool integration
  suite to run on the small `zfstest1`/`zfstest2` test pools; production
  behavior is unchanged when the variable is unset.

- **Real-pool integration suite for `zfs-send-receive`** — New
  `tests/integration/test-zfs-send-receive-pools` exercises full copy,
  incremental copy with/without intermediates, destination rollback, resume
  token recovery, space-check skip, and clone copy against actual ZFS pools.
  Requires root and the `zfstest1`/`zfstest2` local test pools described in
  `docs/docs/developer-guide/testing.md`.

### Changed

- **Pin MkDocs to `mkdocs<2`** — MkDocs 2.x is incompatible with this project.
  `bin/check-prerequisites` now fails if MkDocs >= 2 is installed and reports
  `"mkdocs<2"` as the required package. `lib/installer-lib.sh` installs
  `"mkdocs<2"` via pip3 when distribution packages are unavailable.

### Tests

- Added `tests/test-check-prerequisites` covering `check_mkdocs_version`:
  absent mkdocs, mkdocs 1.x, mkdocs 2.x, mkdocs 10.x, and malformed version
  output.

- Extended `tests/test-installer-checks` to verify `install_doc_server` passes
  `"mkdocs<2"` to pip3.

- Extended `tests/test-zfs-send-receive-dryrun` to cover the new
  `space_check_min_buffer` override and its default 1 GiB behavior.

### Documentation

- Updated `docs/docs/developer-guide/testing.md` to describe the new
  integration suite, required test pools, and how to create them.

- Updated `docs/docs/commands-and-modules/commands.md`,
  `docs/docs/commands-and-modules/modules.md`,
  `docs/docs/developer-guide/doc-server.md`, and
  `docs/docs/developer-guide/global-variables.md` to document the `mkdocs<2`
  requirement and the `space_check_min_buffer` variable.

## 0.78.0

*Released 2026-08-09*

### Added

- **Rsync exclude patterns per pull step** — Each rsync pull step in the Backup
  tab and in scheduled backup profiles can now have its own list of rsync
  exclude patterns. Enter them in the new **Excludes** column as a
  space-separated list; patterns containing spaces can be quoted with shell
  syntax. They are saved in `backup.pull_steps[*].excludes` and passed to rsync
  as `--exclude=PATTERN`.

- **Pools tab context menu: Send details to log** — Right-clicking a row in the
  Pool Registry now offers **Send details to log** in addition to the existing
  Copy actions. It writes all `zpool get all` properties for the selected pool
  to the log panel.

- **`ZfsRepository.get_all_pool_properties()`** — New repository method that
  returns a dict of all `zpool` properties for a given pool, used by the Pools
  tab **Send details to log** feature.

- **`EditableListView` generalized columns** — `EditableListView` now accepts
  `columns` and `column_names` constructor arguments so the same widget can be
  reused for tables with more than two editable columns (for example, the
  three-column pull-steps table).

### Changed

- **Config schema version 23** — Existing configurations are automatically
  migrated to add an empty `excludes` list to every backup pull step.

### Tests

- Added `tests/python/test_backup_page.py` coverage for loading, saving, and
  running pull steps with exclude patterns.

- Extended `tests/python/test_command_builders.py` coverage for rsync commands
  with `excludes`.

- Extended `tests/python/test_config_migrations.py` coverage for the version
  22→23 migration.

- Extended `tests/python/test_feature_config.py` coverage for normalizing the
  `excludes` field in `get_backup_config()`.

- Extended `tests/python/test_gui_infrastructure.py` coverage for
  `EditableListView` custom `column_names` and `get_data()`.

- Added `tests/python/test_pools_page.py` coverage for the Pool Registry
  right-click context menu and the **Send details to log** helper.

- Extended `tests/python/test_profile_runner.py` coverage to verify that
  profile-driven rsync pull steps pass excludes through to the command.

- Extended `tests/python/test_zfs_repository.py` coverage for
  `get_all_pool_properties()`.

### Documentation

- Updated `docs/docs/user-guide/gtk-gui.md` to document the Backup tab pull-step
  **Excludes** column and the Pools tab **Send details to log** context-menu
  item.

- Added `docs/docs/user-guide/daily-backup.md#rsync-exclude-patterns` with
  syntax details and examples.

## 0.77.0

*Released 2026-08-08*

### Added

- **Datasets tab context menu: Send details to log** — Right-clicking a pool,
  dataset, snapshot, or hold tag in the Datasets tab now offers **Send details
  to log**. Pools, datasets, and snapshots log all ZFS properties; holds log
  their tag, snapshot, and dataset. This makes it easy to inspect property
  values that are not shown in the tree columns.

- **`ZfsRepository.get_all_properties()`** — New repository method that returns
  a dict of all ZFS properties for a given dataset or snapshot, used by the
  **Send details to log** feature.

- **Caller-location forwarding for logging wrappers** — `log_msg()` now accepts
  optional `caller_file` and `caller_line` keyword arguments. Wrappers such as
  `BackupRunner._runner_log()` and `scrub_manager._emit()` use these so the
  file:line prefix in the log points to the original message issuer rather than
  the wrapper.

### Changed

- **Scrub pause/resume now verifies the resulting state** —
  `pause_scrubs_for_pools()` and `resume_scrubs_for_pools()` no longer update
  the on-disk queue until `zpool scrub` succeeds *and* the live scrub state is
  confirmed to have changed. If the state does not change as expected, a
  warning is logged with the raw `zpool status` output and the pool is not
  recorded as paused/resumed.

- **Scrub pause/resume log level adjusted** — The per-pool "Pausing scrub" and
  "Scrub paused" / "Resuming scrub" and "Scrub resumed" messages are now
  emitted at `VERB` level; the summary "Pools paused:" / "Pools resumed:"
  lines remain at `INFO`.

### Tests

- Added `tests/python/test_datasets_page.py` coverage for the new right-click
  context menu and the **Send details to log** helper.

- Extended `tests/python/test_logging_config.py` coverage for the
  `caller_file`/`caller_line` override.

- Extended `tests/python/test_backup_runner.py` coverage to verify that
  `_runner_log()` forwards caller location to `log_msg()`.

- Extended `tests/python/test_scrub_manager.py` coverage for state-verified
  pause/resume and for warnings when the scrub state does not change.

- Extended `tests/python/test_zfs_repository.py` coverage for
  `get_all_properties()`.

### Documentation

- Updated `docs/docs/user-guide/gtk-gui.md` to document the Datasets tab
  **Send details to log** context-menu item.

## 0.76.0

*Released 2026-08-08*

### Added

- **`<offsite>` retention policy placeholder** — You can now create a single
  retention policy keyed as `<offsite>` instead of adding a separate policy for
  each offsite-candidate pool. At prune time it expands to every online
  offsite-candidate pool, so removable pools such as `z22tb` and `z40tb` can be
  pruned with whichever one is currently attached. The placeholder appears in
  the GUI Retention tab's prune list, is validated when adding a policy, and is
  supported by scheduled retention profiles and `profile_runner.py`.

- **GUI close/quit confirmation** — Closing the main window or choosing
  **File → Quit** now warns when GUI-started tasks are still running and lists
  the tasks that would be aborted. Scrubs and tasks started by other processes
  are excluded from the warning.

### Changed

- **Pool Details logs to the log panel** — The Pools tab **Details** button no
  longer opens a modal dialog. It now writes `zpool status` output directly to
  the GUI log panel, making the text searchable and copyable.

- **Restore pause-scrubs option moved** — The **Pause scrubs on source/
  destination pools during each step** checkbox has moved from the **Restore
  Steps** frame to the **Advanced** expander on the Restore tab, alongside the
  other per-step options.

- **New-install retention cleanup is interactive** — When the GUI starts for the
  first time and finds pool-specific retention policies (for example,
  legacy-imported sample policies), it now asks whether to keep them or clear
  them and keep only the `default` policy, instead of deleting them silently.

- **Scrub Start button sensitivity** — The Pools tab **Start Scrub** button is
  now disabled when the selected scrub entry is already `scrubbing` or
  `pending`.

### Tests

- Added `tests/python/test_offsite_runner.py` coverage for the new
  `detect_offsite_pools()` helper.

- Extended `tests/python/test_profile_runner.py` coverage for `<offsite>`
  expansion in retention profiles.

- Extended `tests/python/test_retention_actions.py` coverage for pool-name
  validation and `<offsite>` expansion in interactive pruning.

- Extended `tests/python/test_retention_page.py` coverage for the interactive
  new-install cleanup dialog and for displaying the `<offsite>` placeholder in
  the prune list.

- Extended `tests/python/test_zfsutilities_gui.py` coverage for the close/quit
  confirmation when running tasks are present.

- Updated `tests/python/test_pool_actions.py` and
  `tests/python/test_pools_page.py` for the new pool-details logging and scrub
  start-button behavior.

### Documentation

- Updated `docs/docs/user-guide/retention.md` to document the `<offsite>`
  retention policy placeholder.

- Updated `docs/docs/user-guide/gtk-gui.md` to reflect the new close/quit
  confirmation, the pool-details log output, and the relocated Restore tab
  pause-scrubs option.

- Updated `docs/docs/user-guide/restore.md` to point to the **Advanced**
  expander for the pause-scrubs option.

## 0.75.0

*Released 2026-08-08*

### Added

- **Pools tab Details button** — The Pools tab now has a **Details** button that
  opens a read-only details dialog for the single selected pool.

- **Dynamic button sensitivity on the Pools tab** — All Pools and Scrub Manager
  action buttons now enable or disable automatically based on the current
  selection. For example, **Watch** is only available for registered online
  pools, **Details** requires exactly one selected pool, and scrub pause/resume/
  stop buttons reflect the selected scrub states.

### Changed

- **Coding-policy clarification** — `AGENTS.md` and
  `docs/docs/developer-guide/coding-policies.md` now distinguish the proper
  use of `return` inside functions, `exit` at the top level of executed
  scripts, `bashreturn` for dual-mode scripts, and `bashfatal`/`die` for
  fatal termination from sourced helpers, instead of the previous blanket
  prohibition on bare `return`/`exit`.

### Documentation

- Updated `docs/docs/user-guide/offsite-backup.md` to explain how daily and
  offsite backups can run concurrently when their source scopes are aligned,
  and how per-dataset locks prevent snapshot-history corruption.

- Updated `docs/docs/user-guide/gtk-gui.md` to document the new **Details**
  button and the dynamic sensitivity behavior of the Pools tab action buttons.

### Tests

- Added `tests/python/test_action_dispatch.py` coverage for the Pools page
  button attributes and `post_setup` hook.

- Added `tests/python/test_pools_page.py` coverage for
  `update_pools_button_sensitivity()`, including selection-driven enable/disable
  rules and scrub-state-driven scrub controls.

- Added `tests/python/test_profile_validation.py` coverage confirming that
  concurrently runnable daily and offsite profiles with aligned source scopes
  produce no warning.

## 0.74.11

*Released 2026-08-08*

### Fixed

- **`ensure-restored-vm-iscsi` fallback LUN assignment** — When a Proxmox VM's
  zvol disk number does not match its config slot (common when an EFI disk
  consumes disk-0), `expected_lun_for_zvol()` in `bin/ensure-restored-vm-iscsi`
  now scans all non-EFI disk lines, sorts them by bus priority and index, and
  picks the first unused LUN. Size matching is used when the zvol `volsize` is
  known so the correct config entry is selected. LUNs already assigned during
  the same run are tracked so two zvols cannot be mapped to the same config
  entry.

- **`lun_from_by_path_line` always returns cleanly** — The helper now ends
  with an explicit `return 0` so malformed by-path lines do not cause an
  unintended `set -e` exit.

### Changed

- **Deterministic work ordering in `ensure-restored-vm-iscsi`** — Work items
  are now sorted by VM ID and disk number before LUN lookup so fallback
  assignment is reproducible when multiple data disks have mismatched numbers.

### Tests

- Expanded `tests/test-ensure-restored-vm-iscsi` to 23 tests, adding coverage
  for fallback LUN assignment, assigned-LUN tracking, local-host detection,
  local config-file reading, and remote command forwarding for
  `exec_on_storage()`.

- Updated `docs/docs/developer-guide/testing.md` and `AGENTS.md` with the new
  test count and description.

## 0.74.10

*Released 2026-08-08*

### Fixed

- **`cleanup-zfsutilities-legacy` and `ensure-restored-vm-iscsi` use `bashreturn`** —
  Both scripts replaced bare `exit` calls with the project's `bashreturn` helper so
  they behave correctly when sourced as well as when executed directly.
  `cleanup-zfsutilities-legacy` now returns cleanly from `--help` and from user
  cancellations at confirmation prompts.

- **`ensure-restored-vm-iscsi` skips `rootcheck` when already mocked** — The script
  now loads `rootcheck` only if it is not already defined, matching the pattern used
  by `cleanup-zfsutilities-legacy` and making the script safe to source in tests.

### Changed

- **Documentation path corrections** — `README.md` and the usage comments in
  `bin/run-tests` now refer to `./bin/run-tests`, matching the actual repository
  layout.

- **Added dedicated `ensure-restored-vm-iscsi` command reference** —
  `docs/docs/commands-and-modules/commands.md` now has a standalone section for
  `ensure-restored-vm-iscsi` with arguments, environment variables, return codes,
  and called modules; the `zfsfullcopy` section links to it.

### Tests

- **`test-ensure-restored-vm-iscsi` sources real helpers** — The suite no longer
  duplicates the production parsing logic; it sources the real helper functions
  from `bin/ensure-restored-vm-iscsi` and exercises them with mocks.

- **Added cancellation test for `cleanup-zfsutilities-legacy`** —
  `test_cancellation_returns_zero` verifies that declining a confirmation prompt
  returns exit code 0.

## 0.74.9

*Released 2026-08-07*

### Fixed

- **`ensure-restored-vm-iscsi` detects EFI disks by size** — Proxmox EFI zvols are
  always 4 MiB and are keyed to `efidisk0:` in the VM config, independent of the
  zvol's disk number. `expected_lun_for_zvol()` in `bin/ensure-restored-vm-iscsi`
  now reads the zvol `volsize` and treats `4M` or `4194304` as an EFI disk,
  matching `efidisk0:` before falling back to the numbered disk keys. This fixes
  restores where the EFI zvol has a non-zero disk number and would otherwise be
  skipped or mismatched.

### Tests

- Added `test_expected_lun_for_efi_disk_nonzero_disknum`,
  `test_expected_lun_for_efi_disk_disknum_zero`, and
  `test_expected_lun_for_efi_disk_byte_size` to
  `tests/test-ensure-restored-vm-iscsi`, covering EFI disk detection for both
  human-readable and byte-size `volsize` values.

### Changed

- Updated `docs/docs/developer-guide/architecture.md`,
  `docs/docs/commands-and-modules/commands.md`,
  `docs/docs/developer-guide/testing.md`, and `AGENTS.md` to describe EFI disk
  detection and the new test count.

## 0.74.8

*Released 2026-08-07*

### Fixed

- **`ensure-restored-vm-iscsi` correctly forwards scripts to the storage host** —
  `run_on_storage()` in `bin/ensure-restored-vm-iscsi` now reads the storage-side
  script from stdin (the heredoc supplied by each caller) and passes the caller's
  positional parameters to `bash -s`. Previously the function consumed the first
  positional argument as the script and ignored the heredoc, so the wrong shell
  code was executed on the storage node.

### Tests

- Added `test_run_on_storage_remote_forwards_heredoc`,
  `test_run_on_storage_local_forwards_heredoc`, and
  `test_ensure_lun_on_storage_sends_correct_storage_script` to
  `tests/test-ensure-restored-vm-iscsi`, covering the corrected storage-side
  script forwarding.

### Changed

- Updated `docs/docs/developer-guide/testing.md` and `AGENTS.md` to reflect that
  `test-ensure-restored-vm-iscsi` now contains 14 tests and covers storage-side
  script forwarding.

## 0.74.7

*Released 2026-08-07*

### Fixed

- **`bin/bashinit` is now safe under `set -u`** — The startup checks for
  `mydir`, `BASH_SOURCE[1]`, and `PATHS_LIB` now use `${var:-}` expansions so
  `bashinit` can be sourced in shells running with `set -euo pipefail` without
  triggering "unbound variable" errors.

### Changed

- **Documentation now points to the correct test harness path** —
  `AGENTS.md`, `docs/docs/developer-guide/testing.md`,
  `docs/docs/commands-and-modules/commands.md`, and
  `docs/docs/developer-guide/index.md` now refer to `tests/run-tests` rather
  than the repo-root `./run-tests` wrapper that no longer exists. The invalid
  `./run-tests -v` example was replaced with `tests/run-tests --failures-only`.

### Tests

- Added `test_bashinit_safe_under_set_u` to `tests/test-node-lib`, verifying
  that `bashinit` loads `lib/paths.sh` correctly when invoked under
  `set -euo pipefail` with `mydir` and `PATHS_LIB` unset.

## 0.74.6

*Released 2026-08-07*

### Added

- **`ensure-restored-vm-iscsi` helper** (two-node) — New `bin/ensure-restored-vm-iscsi`
  script that re-creates iSCSI backstores and LUN mappings for restored Proxmox VM
  disk zvols. It reads the LUN index already recorded in the Proxmox VM config on
  the compute host, ensures the backstore and LUN exist on the storage host at that
  same index, updates the iSCSI manifest and encrypted-LUN config, saves the target
  configuration, and rescans the compute host. In single-node mode it is a no-op.

- **Restore pipeline automatically re-exports VM disk LUNs** — Both `bin/zfsrestore`
  and `python/restore_runner.py` now call `ensure-restored-vm-iscsi` after the final
  send-receive step (Part 1 when Part 2 is not run, or Part 2 when it is). This
  handles restores to a missing or detached VM disk while preserving the LUN index
  recorded in the Proxmox VM config.

### Fixed

- **`zfs-send-receive` avoids self-lock conflict during forced full copy** —
  When `force='Y'` requires destroying the destination dataset before a full
  copy, `zfs-send-receive` now releases its own destination `w` lock before
  invoking `zfsdelfs` and reacquires it after preparation. This prevents a
  self-conflict because `zfsdelfs` acquires an `x` lock on the same dataset.
  Dry-run mode continues to skip the real destroy and therefore does not
  release the lock.

### Changed

- **Concurrency documentation updated** — `docs/docs/developer-guide/concurrency-collisions.md`
  now correctly lists `zfsdelfs` as a lock-manager participant and describes the
  coordinated lock hand-off used by forced full copies.

### Tests

- Added `test_full_copy_releases_dest_lock_around_zfsdelfs`,
  `test_full_copy_keeps_dest_lock_in_dryrun`, and
  `test_full_copy_releases_dest_lock_zfsdelfs_failure` to
  `tests/test-zfs-send-receive-dryrun`, covering the lock release/reacquire
  behavior around destination preparation.

- Added `tests/test-ensure-restored-vm-iscsi` covering zvol basename/pool
  extraction, VM disk parsing, LUN extraction from `by-path` entries, and
  Proxmox VM-config LUN lookup.

- Added `test_ensure_iscsi_step_present_after_part1_only`,
  `test_ensure_iscsi_step_present_after_part1_and_part2`, and
  `test_ensure_iscsi_step_skipped_in_dry_run` to
  `tests/python/test_restore_runner.py`, verifying that the generated restore
  command includes the iSCSI ensure step and honors dry-run mode.

## 0.74.5

*Released 2026-08-07*

### Changed

- **`source_helper` uses `bashfatal`/`bashreturn` helpers** — When
  `source_helper` cannot locate a sibling script or library, it logs a `FATAL`
  message and invokes `bashfatal` as the primary exit path. If `bashfatal`
  itself cannot be found, it falls back to `bashreturn` so sourced callers regain
  control instead of killing the parent shell. The previous bare `exit 8` path
  has been removed.

- **`cleanup-zfsutilities-legacy` uses `source_helper`** — The legacy cleanup
  script now loads `rootcheck` through `source_helper` (matching the rest of the
  codebase) instead of `source "$MYDIR/rootcheck"`. `main()` terminates via
  `bashreturn` rather than a bare `return`.

- **`uninstall-some-versions` uses `find_zfsutility_script`** — The bulk
  uninstall helper now locates `uninstall-version` through
  `find_zfsutility_script` instead of hard-coding `$mydir/uninstall-version`.

### Tests

- Added `test_source_helper_fallback_returns_when_sourced` to
  `tests/test-node-lib`, verifying that `source_helper` falls back to
  `bashreturn` when `bashfatal` is missing and the caller is sourced.

## 0.74.4

*Released 2026-08-07*

### Changed

- **`source_helper` is now provided by `bashinit`** — The helper that resolves
  and sources sibling scripts/libraries via `find_zfsutility_script` is now
  defined once in `bin/bashinit` instead of being duplicated in every script.
  All scripts that previously defined their own local `source_helper()` now use
  the shared implementation.

- **Scripts bootstrap themselves with their own `bashinit`** — Every bash script
  now sources the `bashinit` in its own directory first, falling back to
  `~/bashinit` only when a local copy is not present. This lets a repository
  checkout or newly deployed version run before it has been activated via
  `switch-version`, and it eliminates version skew between a script and its
  `bashinit` helpers. Test mocks that provide a fake `bashinit` in `$HOME`
  continue to work through the fallback path.

- **Documentation reflects the current sourcing pattern** — Developer and
  command-reference docs now show `source_helper <name>` (or
  `source "$(find_zfsutility_script <name>)"` when an argument is required)
  instead of the older `source $mydir/<name>` examples.

### Removed

- **`zfsresizevol`** — Removed the unfinished `bin/zfsresizevol` stub and its
  documentation entry. The script only logged `FATAL: WIP!` and exited.

### Fixed

- **`zfssend` function definition** — Corrected `send function {` to
  `function send {`, which had prevented the script from being parsed.

- **`zfsfullcopy` input validation** — Fixed several broken constructs in the
  restore helper:
  - `if [[ overrides != '' ]]` now reads `$overrides` so overrides are only
    applied when an argument is actually provided.
  - `local $sourcefsremovequalifiers='0'` no longer has the erroneous `$`.
  - Comparisons for `$restoresourcefs`, `$sourcefsremovequalifiers`, and
    `$destfs` use `==` consistently.
  - Missing-helper fatal exits use `find_zfsutility_script bashfatal`.

### Tests

- Added `tests/test-zfsfullcopy` covering overrides handling, default
  `sourcefsremovequalifiers`, and missing required arguments.
- Added `tests/test-zfssend` verifying the `send` function is defined after
  sourcing.
- Added `source_helper` tests to `tests/test-node-lib`.
- Updated `tests/test-uninstall-version` and
  `tests/test-uninstall-some-versions` to provide `source_helper` in their
  fake `bashinit` stubs.

## 0.74.3

*Released 2026-08-05*

### Fixed

- **`zfs-send-receive` calls the correct dataset-deletion helper** — When
  `prepare_destination_for_full_copy` needs to destroy an existing destination
  for a full copy/restore, it now invokes `zfsdelfs` via
  `find_zfsutility_script` instead of the undefined `delfs` command. This
  restores the destructive full-copy path that failed with
  `delfs: command not found` in 0.74.2.

## 0.74.2

*Released 2026-08-05*

### Fixed

- **`zfs-send-receive` resume-token loop on non-existent destination** — When
  restoring to a destination dataset that does not yet exist, the script no
  longer checks for or validates a `receive_resume_token`. Previously, the
  validation would fail and the retry path could loop indefinitely because the
  destination had not been created yet.

### Changed

- **`zfs-send-receive` stderr suppression** — `zfs get receive_resume_token`
  and the destination-existence check for full-copy preparation now redirect
  stderr to `/dev/null`, avoiding spurious error output during dry-run and
  non-existent-destination flows.

### Tests

- Added `test_dryrun_nonexistent_destination_no_resume_loop` to
  `tests/test-zfs-send-receive-dryrun`.
- Updated test-suite counts in `AGENTS.md` and
  `docs/docs/developer-guide/testing.md`.

## 0.74.1

*Released 2026-08-05*

### Changed

- **Logging hygiene** — Several recoverable or warning conditions that were
  logged as `FATAL` are now logged as `WARN`, leaving `FATAL` for true aborts:
  - `find_zfsutility_script` when a sibling script cannot be found.
  - `pool_to_target` for unknown pools or single-node iSCSI lookups.
  - `zfs-send-receive` dataset/snapshot deletion failures and unhandled
    `zfscommsnap` return codes.
  - Python offsite profile, profile runner, and schedule-page errors.
- **`bashinit` / `lib/paths.sh` loading** — `bashinit` now locates and sources
  `lib/paths.sh` even when `$mydir` is not preset, such as when bash is invoked
  from the Python GUI via `bash -c`.
- **`archive-vm` error handling** — Remote storage-host snapshot failures are
  now reported with an explicit `__ARCHIVE_VM_ERROR__` sentinel instead of
  relying on a `FATAL:` prefix in stdout. The archive loop also aborts cleanly
  when snapshot determination fails, instead of continuing with an empty
  snapshot name.
- **Development setup instructions** — `AGENTS.md` and the developer guide now
  recommend symlinking `~/bashinit` from the repo (`ln -sfn`) rather than
  copying it, matching the production symlink model.

### Fixed

- **`archive-vm` abort on snapshot failure** — Fixed a bug where a failure to
  determine or create a retire snapshot did not stop the archive loop because
  the failure was detected inside a command-substitution subshell.
- **`tests/test-archive-vm` helper** — `run_archive` now returns the actual
  exit code of the archived script instead of the exit code of the trailing
  `cat` commands.

### Tests

- Added `tests/test-node-lib` case verifying `bashinit` loads `lib/paths.sh`
  when `$mydir` is unset.
- Added `tests/test-archive-vm` case verifying a storage-host snapshot error
  aborts the archive with a `FATAL` message.
- Added `tests/python/test_backup_runner.py` case verifying
  `_check_process` returns `False` immediately when the runner is stopped.
- Updated existing tests to expect `WARN` instead of `FATAL` for the downgraded
  log messages.

## 0.74.0

*Released 2026-08-05*

### Added

- **FHS-aligned runtime path layout** — ZFS Utilities now stores its files in
  conventional system directories:
  - `/etc/zfsutilities/` — system/admin configuration (`node.conf`,
    `deploy.conf`, `iscsi-encrypted-luns.conf`, `two-node.conf`)
  - `/var/lib/zfsutilities/` — persistent runtime state (`config.json`,
    `history.json`, `profiles/`, `scrub_state.json`, `nextsnap`,
    `nextsnap_offsite`)
  - `/var/log/zfsutilities/` — logs and session files
  - `/run/zfsutilities/` — transient runtime state
  - `/run/lock/zfs/` — advisory locks
- **`lib/paths.sh`** — Centralized bash path layout. Defines all base and
  derived path variables, legacy-path aliases, and the one-time state migration
  helper `migrate_zfsutilities_state()`.
- **`python/paths.py`** — Python equivalent of `lib/paths.sh`; provides
  FHS-aligned path helpers and legacy-path helpers for migration code.
- **`python/migration.py`** — One-time, idempotent, rollback-compatible
  migration of state files and system config files from their legacy locations
  to the new layout. Leaves symlinks at the old paths so older deployed versions
  can still operate.
- **`bin/cleanup-zfsutilities-legacy`** — New utility to remove the
  backward-compatibility symlinks left by the FHS migration and optionally
  uninstall old deployed versions that do not understand the new layout.

### Changed

- **`bashinit`** — Automatically sources `lib/paths.sh` and invokes
  `migrate_zfsutilities_state()` when running as root. Search paths in
  `find_zfsutility_script` now include `lib/`, `python/`, and `share/` at the
  repo level.
- **`bin/zfsconfig`**, **`bin/uninstall-zfsutilities`**, **`bin/install-single-node`**,
  **`bin/install-two-node`**, **`lib/node-lib.sh`**, **`lib/iscsi-lib.sh`**, and
  other scripts — Updated to use the centralized path variables from
  `lib/paths.sh` with legacy fallbacks.
- **Session logs** — Default session-log directory moved from
  `/var/log/zfsutilities/sessions` (still the default value) to be derived from
  `ZFSUTILITIES_SESSION_LOG_DIR` in `lib/paths.sh`.

### Tests

- Added `tests/test-paths` and `tests/python/test_paths.py` for the new path
  modules.
- Added `tests/test-migration` and `tests/python/test_migration.py` for the
  migration helpers.
- Added `tests/test-cleanup-zfsutilities-legacy` for the legacy cleanup script.
- Updated `tests/test-zfsconfig` with path-resolution coverage.
- Updated `tests/test-uninstall-zfsutilities`, `tests/test-zfsdailybackup`,
  `tests/test-zfsscruball`, `tests/test-zfssnapbuild`, and `tests/test-lib.sh`
  for the new path layout.
- Updated Python tests to use the new path helpers via `test_support.py`.

### Documentation

- Updated `docs/docs/index.md` with the new path layout and migration notes.
- Added `cleanup-zfsutilities-legacy` to `commands-and-modules/commands.md`.
- Added `paths.sh` to `commands-and-modules/modules.md` and updated the
  `bashinit` entry.
- Added `paths.py` and `migration.py` to
  `commands-and-modules/python-modules.md`.
- Updated installation, two-node, and developer-guide source files to reference
  the new `/etc/zfsutilities/` paths while documenting legacy fallbacks.
- Updated `AGENTS.md` path references and retention-policy notes.

## 0.73.1

*Released 2026-08-02*

### Fixed

- **`deploy-version` repo-root detection** — Fixed `MYDIR` resolution so the
  script correctly identifies the repository root when invoked as
  `./bin/deploy-version`. The previous calculation resolved to `bin/`, causing
  the repo-root guard to fail and preventing deployment.
- **`git-release` repo-root detection** — Applied the same parent-directory
  fix so `REPO_ROOT` resolves to the repository root instead of `bin/`.
  Corrected the usage example from `./release` to `./bin/git-release`.

### Documentation

- Updated all source documentation examples that referenced `./deploy-version`
  or `./git-release` to use the correct `./bin/` paths
  (`installation/index.md`, `commands-and-modules/two-node.md`,
  `commands-and-modules/commands.md`, and
  `developer-guide/two-node-config.md`).

## 0.73.0

*Released 2026-08-02*

### Changed

- **Repository directory restructure** — Replaced the old numbered/named
  directories (`06 Docs/`, `07 GTK + Python/`, `08 Two-node/`,
  `09 ZFS clone support/`, `10 Installers/`, `Cache-warm/`, `Watchall/`) with a
  clean, conventional layout:
  - `bin/` — all executable bash scripts
  - `lib/` — sourced shell libraries (`node-lib.sh`, `installer-lib.sh`, etc.)
  - `python/` — GTK GUI and Python helpers
  - `docs/` — MkDocs documentation source and built site
  - `share/` — static resources, templates, and sample configurations
  - `tests/` — bash and Python test suites (unchanged location)
- **`deploy-version`** — Now copies the `bin/`, `lib/`, `python/`, `docs/`, and
  `share/` directories wholesale into the versioned deployment, and creates the
  GUI/docs launcher symlinks relative to `python/`. Removed the old root-level
  script selection and per-directory symlink logic.
- **`switch-version`** and **installers** — Updated to resolve libraries and
  resources from the new `lib/` directory.
- **`bashinit` / `find_zfsutility_script`** — Search paths now cover the new
  repo layout (`bin/`, `lib/`, `python/`, `share/`) instead of the old
  directory names.
- **`python/path_utils.py`** — Updated repo-relative paths to use `python/`,
  `docs/`, `lib/`, `bin/`, and `share/`.

### Tests

- Updated bash test suites to locate scripts under `bin/` and libraries under
  `lib/`.
- Rewrote `tests/test-deploy-version` to validate the new directory-copy
  deployment model.
- Updated `tests/test-module-dependencies` to guard against stale legacy
  directory literals.

### Fixed

- **Shellcheck clean-up** — Fixed all ShellCheck SC2155 warnings by separating
  `local` declarations from command substitutions in modified test files
  (`test-deploy-version`, `test-installer-retention`, `test-zfs-diagnose-busy`,
  `test-zfslockmanager`). Replaced the confusing nested quoting that triggered
  SC1078 in `tests/test-zfsdelsnap` with `env` variable passing. Removed
  unused/dead variables from `bin/install-single-node`,
  `bin/install-two-node`, and `lib/installer-lib.sh`. Added file-level
  ShellCheck disable directives to test files and node-aware scripts so that
  project-specific false positives (globals set by `bashinit`, test-framework
  variables, and dynamic `source` calls via `find_zfsutility_script`) are
  inhibited rather than left as noise.

### Documentation

- Updated all developer-guide, installation, commands-and-modules, and
  user-guide source files to reference the new directory layout.
- Fixed a duplicated directory reference in
  `developer-guide/conventions.md`.

## 0.72.1

*Released 2026-08-01*

### Changed

- **Python import and formatting cleanup** — Sorted and normalised imports
  across the GUI modules and tests, removed unused imports, and fixed minor
  formatting inconsistencies (for example, `restore_runner.py` now uses plain
  string literals where no interpolation is required).

### Added

- **`pyproject.toml` with Ruff configuration** — Added a project-level
  `pyproject.toml` configuring Ruff (`line-length = 100`, `target-version =
  "py310"`) and documenting the intentionally ignored rules.

### Tests

- Updated imports and minor assertions across the Python test suite to match
  the cleaned-up module structure.
- Expanded `tests/python/test_docs_integrity.py` coverage.

### Documentation

- Added a **Linting** subsection to `developer-guide/coding-policies.md`
  describing the Ruff setup in `pyproject.toml`.
- Added a linting tip to `developer-guide/testing.md`.

## 0.72.0

*Released 2026-08-01*

### Added

- **Datasets tab "Show Big Stuff" action** — Select exactly one pool in the
  Datasets tab and click **Show Big Stuff** to run `zfsshowbigstuff` on that
  pool. Output streams to the log panel.
- **Rsync failure diagnosis** — When an rsync step fails during a GUI or
  scheduled backup run, `BackupRunner` now appends a human-readable diagnosis
  to the session log. Common cases such as SSH connection refused, permission
  denied, no space left on destination, and vanished source files are detected
  from the exit code and stderr output.

### Changed

- **Dashboard selection preservation** — The **Recent Operations** list now
  preserves its current selection across automatic Dashboard refreshes when
  the selected log file is still present. The **View Log** action also caches
  the log path when the button becomes sensitive, so it opens the intended log
  even if a background refresh clears or moves the selection before the click.

### Tests

- Added `TestShowBigStuff` to `tests/python/test_dataset_actions.py`.
- Added Show Big Stuff button/handler coverage to
  `tests/python/test_action_dispatch.py` and sensitivity tests to
  `tests/python/test_datasets_page.py`.
- Added `TestRsyncFailureDiagnosis` to `tests/python/test_backup_runner.py`.
- Added Dashboard selection-preservation and cached View Log tests to
  `tests/python/test_dashboard_page.py`.

### Documentation

- Updated `user-guide/gtk-gui.md` to describe the new **Show Big Stuff** button,
  the cached **View Log** behavior, and the rsync failure-diagnosis messages.
- Updated `commands-and-modules/commands.md` to note that `zfsshowbigstuff` is
  reachable from the GUI Datasets tab.

## 0.71.0

*Released 2026-07-31*

### Changed

- **`pv` progress lines are no longer written to session logs** — In both
  `profile_runner.py` (scheduled and **Run Now** profile runs) and the Schedule
  tab's live log handler, `pv` rate/progress lines still update the GUI status
  bar but are filtered out before being written to the session log. This
  prevents the log file from growing by one line per second during large
  transfers.
- **`BackupRunner._finish` clears the status bar** — When a GUI-run job
  finishes, the progress callback now receives `(None, None)` so the status
  label is cleared instead of leaving stale "… complete" text.
- **`zfs-send-receive` forces `pv` output for captured runs** — When
  `ZFSUTILITIES_LOG_INHERIT=Y` is set, `pv` progress output is now forced even
  when stdin is not a terminal. This ensures profile runs and other captured
  contexts still produce parseable progress lines.
- **`run-tests` is now a thin wrapper** — The repo-root `run-tests` script no
  longer implements its own harness; it execs the unified bash + Python harness
  at `tests/run-tests`.

### Tests

- Added `test_do_transfer_forces_pv_when_log_inherit` to
  `tests/test-zfs-send-receive-dryrun`.
- Added `TestFinishProgress` to `tests/python/test_backup_runner.py`.
- Added `test_run_command_suppresses_pv_lines_from_session_log` to
  `tests/python/test_profile_runner.py`.
- Added `TestLogProfileLine` to `tests/python/test_schedule_page.py`.

### Documentation

- Updated `commands-and-modules/commands.md` to describe the new `run-tests`
  wrapper behavior.
- Added a "The Main Window" section to `user-guide/gtk-gui.md` describing the
  menu bar, working area, and bottom panel.
- Updated `developer-guide/architecture.md` and `user-guide/gtk-gui.md` to
  clarify that `pv` progress lines update the status bar but are omitted from
  the session log.

## 0.70.0

*Released 2026-07-31*

### Changed

- **Retention tab Prune/Mass Delete consolidation** — The Retention tab now has
  a single **Prune** button. Checking **Ignore retention policies** in the
  **Advanced Prune Options** card runs `zfsmassdelsnaps` instead of
  `zfscleanup`; unchecking it runs the normal retention-policy prune. The
  separate **Mass Delete** toolbar button and `on_retention_mass_delete()`
  handler have been removed.
- **Advanced Prune Options card** — Renamed the advanced expander and danger
  frame from "Mass Delete" to "Advanced Prune Options" /
  "Ignore Retention Policies - Danger Zone". Added a tooltip to the
  **Ignore retention policies** checkbox explaining that Prune deletes every
  matching snapshot in that mode.

### Tests

- Added `TestRetentionPageSpec` and `TestRetentionHandlers` in
  `tests/python/test_action_dispatch.py` to verify the removed **Mass Delete**
  button/handler and the registered **Prune** handler.
- Expanded `TestOnRetentionPruneIgnoreMode` in
  `tests/python/test_retention_actions.py` with dry-run coverage.
- Added tooltip coverage in `tests/python/test_retention_page.py`.
- Fixed pre-existing `ruff` warnings in `tests/python/test_action_dispatch.py`
  (unused variable and a duplicate test class name).

### Documentation

- Updated `user-guide/gtk-gui.md`, `user-guide/retention.md`,
  `commands-and-modules/commands.md`, `commands-and-modules/python-modules.md`,
  and `developer-guide/data-structures.md` to describe the consolidated Prune
  flow and renamed Advanced Prune Options card.

## 0.69.1

*Released 2026-07-31*

### Fixed

- **Static-analysis and lint compliance** — Addressed `ruff` warnings across
  Python GUI modules and tests, including timezone-aware `datetime` usage,
  explicit `subprocess.run(check=False)`, more specific exception handling,
  and `ClassVar` annotation for the page-anchor mapping.
- **Bash shellcheck errors** — Fixed a `shellcheck` parsing error in
  `zfsretain` dynamic bucket-length arithmetic and added a header to the
  `someinstalledversions` data file.

### Tests

- Updated `tests/python/test_gui_infrastructure.py` to parse both
  `ast.Assign` and `ast.AnnAssign` when extracting `_PAGE_ANCHORS` from
  `zfsutilities_gui.py`.

## 0.69.0

*Released 2026-07-30*

### Added

- **`uninstall-version -y|--yes`** — `uninstall-version` now accepts `-y` or
  `--yes` to skip the interactive `Remove <version>?` confirmation prompt,
  making non-interactive version cleanup possible.
- **`uninstall-some-versions [listfile]`** — New bulk-uninstall helper that
  reads version numbers from a list file and invokes `uninstall-version -y`
  for each entry. The list file defaults to `./someinstalledversions` and may
  be overridden with a positional argument. Leading whitespace and blank lines
  are ignored.

### Changed

- **`deploy-version` now deploys `uninstall-some-versions`** — The helper is
  included in `VERSIONING_SCRIPTS` so it is installed alongside the other
  version-management scripts.
- **`uninstall-version` strict mode** — Added `set -u` and `set -o pipefail`
  and a `UNINSTALL_VERSION_TEST_NO_ROOT` escape hatch for the root check so the
  script can be exercised by the test suite.

### Tests

- Added `tests/test-uninstall-version` covering default confirmation,
  `-y`/`--yes`, active-version protection, missing-version handling, help,
  unknown options, missing arguments, and flag ordering.
- Added `tests/test-uninstall-some-versions` covering bulk removal,
  whitespace/blank-line tolerance, missing list file, and missing helper.
- Expanded `tests/test-deploy-version` to verify `uninstall-some-versions` is
  listed in `VERSIONING_SCRIPTS`.

### Documentation

- Updated `commands-and-modules/commands.md` with the `-y`/`--yes` option and
  a new `uninstall-some-versions` reference entry.
- Updated `commands-and-modules/two-node.md` and
  `developer-guide/architecture.md` to mention the new `uninstall-version`
  option.

## 0.68.0

*Released 2026-07-30*

### Added

- **Verbose retention decisions** — The Retention tab now has a
  “Verbose retention decisions” checkbox. When enabled, prune runs emit
  `VERB:`-level messages explaining why individual snapshots are kept
  (wrong label, protected incremental base, within retention count,
  clone/bucket `c` exclusion, etc.). Headless runs can opt in by setting
  `retain_verb='Y'`.
- **Configurable Dashboard refresh interval** — The Dashboard tab now has
  a “Refresh every (s):” spinner (1–300 s, default 30 s). The value is
  persisted in `dashboard.refresh_seconds` and takes effect immediately.
- **Checkagainst merged-table preview** — The Checkagainst tab now shows
  a fourth read-only section, “Merged fss table,” which previews the
  effective runtime table after merging active derived sections and user
  entries.

### Changed

- **`list-vm-disks` clone annotation** — Clone zvols are now annotated
  with their full origin snapshot dataset name (e.g.
  `[clone of threeamigos/proxmox/vm-904-disk-0@clone-2026-07-30T12:00-0400-c]`)
  instead of `[clone of vm-<id>]`.
- **Dashboard refresh indicator** — The async refresh no longer
  desensitizes every dashboard section; it shows a simple “Refreshing”
  label next to the refresh-interval spinner.

### Tests

- Added `tests/python/test_config_migrations.py` coverage for the
  20→21 (`retention_verb_messages`) and 21→22 (`dashboard.refresh_seconds`)
  migrations.
- Added `tests/python/test_config_core.py` coverage for the default
  `dashboard.refresh_seconds` value.
- Added `tests/python/test_retention_actions.py` and
  `tests/python/test_retention_page.py` coverage for the verbose-retention
  toggle.
- Added `tests/python/test_dashboard_page.py` and
  `tests/python/test_zfsutilities_gui.py` coverage for the configurable
  refresh interval.
- Added `tests/python/test_checkagainst_page.py` coverage for the merged
  fss table preview.
- Added `tests/test-list-vm-disks` coverage for the full origin snapshot
  name in both two-node and single-node modes.
- Added `tests/test-zfsretain` coverage for `retain_verb='Y'` and the
  default disabled behavior.

### Documentation

- Updated `user-guide/retention.md` with the verbose-retention feature.
- Updated `user-guide/gtk-gui.md` with the Checkagainst merged-table
  preview and expanded `<offsite>` examples.
- Updated `commands-and-modules/two-node.md` and
  `user-guide/proxmox-integration.md` for the new `list-vm-disks` clone
  annotation.
- Updated `commands-and-modules/commands.md` and
  `commands-and-modules/modules.md` to document `retain_verb`.

## 0.67.1

*Released 2026-07-30*

### Fixed

- **`deploy-version` now deploys `attach-vm-disk` and `detach-vm-disk`** — Both
  scripts existed in `08 Two-node/` but were missing from the `TWO_NODE_SCRIPTS`
  list, so `deploy-version` / `switch-version` did not symlink them into the
  production `bin/` directory. They are now wired like the other two-node scripts.

### Tests

- Added `tests/test-attach-vm-disk` covering zvol path parsing, VM ID format,
  and disk-key format validation.
- Expanded `tests/test-deploy-version` with in-list and symlink tests for
  `attach-vm-disk` and `detach-vm-disk`, and updated the existing symlink
  fixture to include both scripts.

### Documentation

- Updated `developer-guide/testing.md` to list `test-attach-vm-disk` and
  `test-detach-vm-disk`, and corrected the `test-deploy-version` test count.

## 0.67.0

*Released 2026-07-29*

### Added

- **Asynchronous Dashboard refresh** — `dashboard_page.refresh_dashboard_page()`
  now gathers pool health, SSH version, and iSCSI data in a background thread.
  Dashboard sections are desensitized while refreshing, and overlapping refresh
  requests are coalesced. Pass `sync=True` to block until the refresh completes.
- **Asynchronous Schedule refresh** — `schedule_page.refresh_schedule_page()`
  computes next-run times in a background thread and also coalesces overlapping
  requests. Next-run results are cached per cron expression per minute.
- **Initial Dashboard refresh on startup** — `main.py` now triggers the first
  Dashboard refresh after the window is shown so the GTK main loop is running.

### Changed

- **`refresh_dashboard_page()` and `refresh_schedule_page()`** — Both functions
  now default to asynchronous refresh. The previous synchronous behavior is
  still available via the new `sync=True` keyword argument.
- **`dashboard_page._on_fix_iscsi_clicked()`** — `repair-iscsi-luns` stdout/stderr
  lines are now passed through unchanged so embedded `INFO`/`WARN` levels from
  the bash script are preserved instead of being reclassified.
- **`schedule_page._next_run_strings()`** — Cache key now includes the current
  minute so cached values cannot become stale as time advances.
- **`main.py`** — Added `gi.require_version('Gdk', '3.0')` before importing from
  `gi.repository` to avoid Gdk version conflicts when tests import modules in a
  different order.

### Tests

- Added `tests/python/test_dashboard_page.py` coverage for loading-state helpers,
  async refresh completion callbacks, exception handling in the worker thread,
  and log-level preservation for `repair-iscsi-luns` output.
- Added `tests/python/test_schedule_page.py` coverage for async refresh
  argument passing, UI-state capture, and time-bucketed next-run caching.
- Added `tests/python/test_main.py` coverage for `ZFSUtilitiesApp.do_activate()`
  creating the window and triggering the initial Dashboard refresh.

### Documentation

- Updated `python-modules.md` to describe the async refresh behavior and new
  `sync=True` parameter for `dashboard_page.py` and `schedule_page.py`.
- Updated `testing.md` and `AGENTS.md` test-suite counts.

## 0.66.1

*Released 2026-07-29*

### Changed

- **Offsite pool candidates are resolved at runtime** — profiles and the bash
  `zfsfindoffsitepool` helper no longer store a fixed list of offsite pools.
  Candidates are read from the Pools tab registry every time an offsite job
  runs.
- **`feature_config.py`** — `save_pools()` no longer mirrors candidate names
  into `config["offsite"]["offsite_pools"]`, and `collect_offsite_config()`
  no longer includes `offsite_pools` in the saved offsite config.
- **`profile_runner.py`** — `run_offsite_profile()` now uses
  `get_offsite_candidate_names(config)` from the live config instead of the
  profile's snapshotted `offsite_pools`.
- **`zfsfindoffsitepool`** — Uses `zfsconfig_get_offsite_candidates()` instead
  of the hard-coded `('z22tb' 'z40tb')` list.
- **Documentation** — Updated `modules.md` `zfsfindoffsitepool` section to
  describe runtime candidate resolution.

### Added

- **Config schema version 20** — `_migrate_19_to_20()` drops the stale
  `offsite_pools` key from existing configs.

### Tests

- Added `tests/test-findoffsitepool` for runtime offsite-pool discovery in the
  bash helper.
- Updated `tests/python/test_offsite_page.py`,
  `tests/python/test_feature_config.py`,
  `tests/python/test_profile_runner.py`,
  `tests/python/test_config_migrations.py`, and
  `tests/python/test_schedule_page.py` for the runtime-resolution behavior.
- Added `tests/python/test_action_dispatch.py` coverage for the backup/offsite
  `dirty_attr` values.
- Fixed `tests/run-tests` so that `-q` and `--failures-only` suppress passing
  suite output, eliminating truncation caused by log messages from passing
  tests. Failing suites still print their full output.

## 0.66.0

*Released 2026-07-29*

### Added

- **`profile_validation.py`** — New Python module that detects backup/offsite
  scope misalignment.  Warns when a backup and an offsite job send overlapping
  datasets to the same destination but snapshot different subsets, which would
  force the daily backup to roll back `@offsite` snapshots.
- **Scope warnings in the GUI** — Saving Backup/Offsite tab settings or saving a
  profile now shows a warning dialog when a scope mismatch is detected.
- **Scope warnings in `profile_runner.py`** — Headless backup and offsite runs
  log scope-alignment warnings before executing their steps.
- **Scope mismatch diagnosis in `zfs-send-receive`** — When a rollback is
  required because destination snapshots are newer than the common snapshot,
  the script reports which snapshot labels caused the mismatch.

### Changed

- **`zfs_lock_manager.py`** — Lock files are now written atomically via a
  temporary file and `os.replace()`.  Stale detection no longer treats a live
  process with an empty `/proc/<pid>/cmdline` as stale.
- **`zfslockmanager`** — Same atomic-write and empty-cmdline robustness fixes as
  the Python lock client.
- **`profile_runner.py`** — Datetime calls are now timezone-aware; broad
  `except Exception` blocks narrowed to expected subprocess/OSError types.
- **`gui_helpers.py`** — Added `show_warning_dialog()` and fixed two
  `subprocess.run` calls in `diagnose_dataset_busy()` to use `check=False`.

### Tests

- Added `tests/python/test_profile_validation.py` covering filter parsing,
  destination-dataset computation, and scope-alignment scenarios.
- Extended `tests/python/test_backup_page.py` with save-time validation tests.
- Extended `tests/python/test_offsite_page.py` with save-time validation tests.
- Extended `tests/python/test_profile_dialogs.py` with profile-scope warning
  tests.
- Extended `tests/python/test_profile_runner.py` with `_log_scope_warnings`
  tests.
- Extended `tests/python/test_zfs_lock_manager.py` with atomic-write and
  empty-cmdline tests.
- Extended `tests/test-zfslockmanager` with atomic-write and empty-cmdline
  tests.
- Extended `tests/test-zfs-send-receive-dryrun` with a scope-mismatch rollback
  test.

### Documentation

- Updated `commands-and-modules/python-modules.md` to add `profile_validation.py`
  and document `show_warning_dialog()` in `gui_helpers.py`.
- Updated `user-guide/profiles.md` with a scope-alignment section.
- Updated `user-guide/daily-backup.md` and `user-guide/offsite-backup.md` with
  scope mismatch causes and actions.
- Updated `developer-guide/lock-manager.md` with atomic-write and empty-cmdline
  stale-detection details.

## 0.65.0

*Released 2026-07-28*

### Added

- **`session_log.py`** — New shared Python module that consolidates per-run
  session-log creation, raw-line writing, trailer writing, and size-cap
  enforcement. Both the GUI `BackupRunner` and the headless
  `profile_runner.py` now use the same stateless helpers.
- **`iscsi-lib.sh`** — New shared bash library containing iSCSI teardown and
  rebuild helpers previously duplicated in `zfsdelfs`. `zfs-send-receive` and
  `zfsdelfs` now source this library instead of embedding the logic.
- **`bashinit` helpers** — Added `die` and `warn` convenience functions and an
  optional default-answer argument for `ask_yn`.
- **`node-lib.sh` clone helpers** — Added `gen_mac()` and
  `get_json_archive_path()` so the VM clone/archive scripts no longer define
  their own copies.
- **Scrub-state persistence in `feature_config.py`** — `load_scrub_state()` and
  `save_scrub_state()` now live alongside the other feature getters/setters and
  validate bucket types on load.
- **`is_dataset_encrypted()` in `zfs_repository.py`** — Replaced the
  walk-up-the-filesystem implementation with a single `zfs list -o name,mountpoint`
  lookup.

### Changed

- **`two-node-lib.sh`** is now a deprecated compatibility wrapper that sources
  `node-lib.sh`. New code should source `node-lib.sh` directly.
- **Python type annotations** modernized across `zfs_repository.py`,
  `scrub_manager.py`, `command_builders.py`, and others (`List` → `list`,
  `Optional[X]` → `X | None`).
- **`zfs-send-receive`** now sources `iscsi-lib.sh` directly rather than all of
  `zfsdelfs`.
- **Installers** (`install-single-node`, `install-two-node`) now source
  `bashinit` so they can share its `die`/`ask_yn` helpers.
- **Deployment wiring** for `iscsi-lib.sh`: `deploy-version` ships it into the
  versioned `lib/` directory and `switch-version` creates/removes the
  `/usr/local/lib/iscsi-lib.sh` symlink.

### Removed

- **`snapshot_manager.py`** and its test — Snapshot hold/delete/rollback actions
  are now reached through the Datasets tab action buttons.
- **Root-level `monitor-cache.sh`** duplicate; the canonical copy remains in
  `Cache-warm/`.
- **Unused helpers:** `zfsconfig_set_pools`,
  `zfsconfig_set_checkagainst_file`, `zfslockmanager::_zfslock_decode`,
  `zfsretain::get_minage_for_bucket`,
  `command_builders::build_installed_programs_command`, and
  `installer-lib.sh::ensure_retention_profiles_remote`.

### Tests

- Added `tests/python/test_session_log.py` covering file creation, raw-line
  writing, trailers, log-index updates, and truncation.
- Added `tests/python/test_feature_config.py` scrub-state persistence tests.
- Extended `tests/test-logging` with `ask_yn` default-answer, `warn`, and `die`
  coverage.
- Extended `tests/test-node-lib` with `gen_mac`, `get_json_archive_path`, and
  `two-node-lib.sh` wrapper tests.
- Renamed stale `test_remote_rsync_log_setup_command` in
  `tests/python/test_command_builders.py`.

### Documentation

- Updated `commands-and-modules/python-modules.md` to add `session_log.py`,
  document `is_dataset_encrypted`, and remove stale function references.
- Updated `commands-and-modules/modules.md` for the new `bashinit` helpers and
  `iscsi-lib.sh`.

## 0.64.0

*Released 2026-07-27*

### Changed

- **Checkagainst now uses source/destination roots instead of strip/prepend**
  — The `zfscheckagainst` fss table and the GUI Checkagainst tab have been
  simplified from four fields (`dataset`, `quals`, `counterpart`, `label`) to
  three (`source_root`, `dest_root`, `label`). The counterpart dataset is now
  built by replacing the snapshot's `source_root` prefix with the `dest_root`
  prefix, which matches how `zfs-send-receive` constructs destination paths and
  removes the need to compute leading-segment strip counts.

### Added

- **Config migration v18 → v19** — Existing checkagainst rows using the legacy
  `dataset`/`quals`/`counterpart` format are automatically converted to
  `source_root`/`dest_root` when the JSON config is loaded.
- **Legacy `.conf` conversion** — `zfscheckagainst` now reads legacy
  4-field `zfscheckagainst.conf` rows and converts them to the new 3-field
  `source_root`/`dest_root`/`label` format on the fly.

### Removed

- **`zfsretain` no longer parses `$leadingqualifiertodelete`** — The variable
  and the unused `remove_leading_qualifiers` calls have been removed from
  retention pruning; counterpart resolution is now handled entirely by
  `zfscheckagainst` using the config's `source_root`/`dest_root` rows.

### Tests

- Updated `tests/test-zfsdelsnap` so the "real `zfscheckagainst` sources
  cleanly" test no longer expects the removed `zfsremoveleadingqualifiers`
  helper.
- Added `_normalize_checkagainst_row` coverage for legacy null-prepend
  (`counterpart: "-"`) rows in
  `tests/python/test_checkagainst_derivation.py`.
- Fixed `tests/test-lib.sh` so `teardown_test_env` propagates `test_summary`'s
  non-zero exit code; failing suites are no longer reported as passed when
  teardown is the last command.

### Documentation

- Updated `commands-and-modules/modules.md`,
  `developer-guide/architecture.md`, `developer-guide/data-structures.md`,
  `developer-guide/global-variables.md`, `developer-guide/testing.md`, and
  `user-guide/gtk-gui.md` to document the new `source_root`/`dest_root`
  checkagainst schema.

## 0.63.4

*Released 2026-07-26*

### Fixed

- **Checkagainst tab now scrolls vertically when content overflows** — The
  Checkagainst page is wrapped in a `Gtk.ScrolledWindow` with a vertical-only
  scrollbar policy, so long derived/user entry tables remain accessible on
  smaller displays.

### Tests

- Added `test_page_is_wrapped_in_scrolled_window` in
  `tests/python/test_checkagainst_page.py` to verify the page root widget and
  its scrolling policy.

## 0.63.3

*Released 2026-07-25*

### Fixed

- **GTK TreeView column widths no longer shrink after version switches or
  maximized sessions** — Column widths are now persisted as the user's intended
  `fixed_width` (not the allocated width) and keyed by column header title. The
  old scaling logic that shrank restored widths to fit a stale saved window
  width has been removed, and legacy list-format configs continue to restore
  until the next save rewrites them in the title-keyed dict format.

- **Backup runner no longer duplicates subprocess output in the session log** —
  All subprocess output handlers now route lines through the GUI sink once and
  write the raw line to the session log once, instead of calling the runner log
  helper that also wrote to the session log.

### Changed

- `View → Minimize Width...` now flushes any pending debounced UI-state save
  before clearing saved column widths, preventing the cleared widths from being
  immediately re-written.

### Added

- **Dashboard warns about active ZFS checkpoints** — `zpool list` output now
  includes the `ckpoint` property; pools with an active checkpoint appear in
  the Dashboard warnings list.

## 0.63.2

*Released 2026-07-23*

### Added

- **`$releaseholds_tags` variable** — Selective ZFS hold release. When
  `$releaseholds='Y'`, only hold tags matching one of the patterns in
  `$releaseholds_tags` are released before snapshot deletion. Defaults to
  `('offsite-*')`. Snapshots that still have unmatched user holds are skipped
  with a warning instead of failing the job. Set to `('*')` to restore the
  previous all-holds behavior.
- **GUI support for `releaseholds_tags`** — The Backup tab advanced variables
  and the Retention tab mass-delete dialog expose the new setting. Commands
  emitted by the Python layer include `releaseholds_tags=("offsite-*")`
  whenever hold release is enabled.

### Changed

- `zfsdelsnap`, `zfsdelallholds`, `zfsdelallsnaps`, `zfsmassdelsnaps`,
  `zfs-send-receive`, `zfscleanup`, `zfsretain`, `zfsoffsiteretain`,
  `zfsrestore`, `zfsfullcopy`, and `zfsresizevol` now default
  `releaseholds_tags` to `offsite-*` and only release matching holds.
- `zfsdelallholds` now accepts glob tag patterns and reports unreleased holds
  in `$ZFS_DELALLHOLDS_REMAINING_TAGS`.

### Tests

- Added `tests/test-zfsdelallholds` covering selective hold release and
  remaining-tag reporting.
- Extended `tests/test-zfsdelsnap` to verify user holds block deletion under
  the new semantics.
- Added coverage for `releaseholds_tags` defaults in `test-zfsretain`,
  `test-zfscleanup`, and `test-zfsdelallsnaps`.
- Added Python tests verifying `releaseholds_tags` in command builders, backup
  defaults, mass-delete defaults, and backup-page variable wiring.

### Documentation

- Updated `commands-and-modules/commands.md`, `commands-and-modules/modules.md`,
  `developer-guide/global-variables.md`, and `AGENTS.md` to document
  `$releaseholds_tags` and the new selective hold-release behavior.

## 0.63.1

*Released 2026-07-22*

### Added

- **`rootcheck` is now a first-class deployed script** — `deploy-version`
  validates that `rootcheck` is present in the versioned `bin/` directory,
  `switch-version` creates and removes `/usr/local/lib/rootcheck` as a
  production-wiring symlink, and `uninstall-zfsutilities` cleans it up.
- **`find_zfsutility_script` deployment overrides** — The absolute directories
  searched for deployed siblings can be overridden with
  `ZFSUTILITIES_BIN_DIR`, `ZFSUTILITIES_CURRENT_BIN_DIR`, and
  `ZFSUTILITIES_SYSTEM_LIB_DIR`. This makes the helper testable without root
  and supports non-standard installs.
- **`node-lib.sh` fallback parity** — The fallback `find_zfsutility_script`
  definition in `node-lib.sh` now searches the same active/current deployment
  directories as `bashinit`.

### Tests

- Added `tests/test-node-lib` cases verifying
  `find_zfsutility_script` resolves scripts via
  `ZFSUTILITIES_BIN_DIR`, `ZFSUTILITIES_CURRENT_BIN_DIR`, and
  `ZFSUTILITIES_SYSTEM_LIB_DIR`.
- Added `tests/test-uninstall-zfsutilities` case verifying that the
  `/usr/local/lib/rootcheck` symlink is removed during uninstall.

### Documentation

- Updated `commands-and-modules/two-node.md`, `commands-and-modules/modules.md`,
  `installation/index.md`, `developer-guide/conventions.md`,
  `developer-guide/two-node-config.md`, and `AGENTS.md` to document the
  `rootcheck` symlink and the new `find_zfsutility_script` environment
  overrides.

## 0.63.0

*Released 2026-07-19*

### Added

- **Nested Checkagainst configuration (config schema v18)** — The
  `checkagainst` key in `/root/.config/zfsutilities.json` is now a nested
  object with `backup_derived_active`, `offsite_derived_active`,
  `backup_derived`, `offsite_derived`, and `user_entries` sections. Existing
  flat lists are migrated automatically to `user_entries` by
  `_migrate_17_to_18`.
- **Derived Checkagainst entries from Backup/Offsite steps** —
  `feature_config.derive_checkagainst_entries()` builds forward and reverse
  checkagainst rows from active Backup and Offsite send/receive steps. The
  bash helper `zfsconfig_get_checkagainst()` now calls
  `feature_config.merge_checkagainst_entries()` to combine derived sections
  with user entries at runtime.
- **GUI Checkagainst tab redesign** — The tab now shows three sections:
  read-only **Backup-derived entries**, read-only **Offsite-derived entries**
  (each with an **Active** toggle), and an editable **User entries** table.
  Column order and labels were updated to match the new workflow, and each
  column header has a descriptive tooltip.
- **Get Entries action** — Refreshes the derived sections from the current
  Backup and Offsite configurations.
- **Add pair... assistant** — Opens a dialog that asks for snapshot label,
  source dataset, destination dataset, and comment, then computes the correct
  strip-segment count and appends both the forward and reverse rows to the
  user table.
- **Auto-seed checkagainst after GUI runs** — After a successful Backup,
  Offsite, or Restore run started from the GUI, a matching checkagainst row
  is automatically added to `user_entries` (skipped for `<offsite>`
  destinations and duplicates).

### Changed

- `feature_config.get_checkagainst()` now returns the nested dict structure
  and transparently wraps legacy flat lists for backward compatibility.
- `feature_config.save_checkagainst()` persists the full nested object.
- `BashStep` gains an optional `metadata` field that carries `source`,
  `dest`, and `label` for successful send/receive steps so the GUI can
  auto-seed the checkagainst table.

### Tests

- Added `tests/python/test_checkagainst_derivation.py` covering
  `_compute_strip_segments()`, `derive_checkagainst_entries()`,
  `merge_checkagainst_entries()`, `get_checkagainst()`, and
  `add_checkagainst_entry()`.
- Updated `tests/python/test_checkagainst_page.py` for the three-section UI,
  dirty detection, action handlers, and the Add pair assistant.
- Updated `tests/python/test_config_migrations.py` for the v17→v18
  migration.
- Updated `tests/python/test_feature_config.py`,
  `test_backup_config.py`, `test_backup_runner.py`,
  `test_command_builders.py`, `test_offsite_runner.py`,
  `test_restore_runner.py`, `test_page_runners.py`, and
  `test_action_dispatch.py` for the new schema, metadata, and seeding
  behavior.
- Updated `tests/test-zfsconfig` to verify merging, active flags, and
  backward-compatible flat-list handling.

### Documentation

- Updated `06 Docs/docs/commands-and-modules/modules.md` with the new
  derivation rules and merge precedence.
- Updated `06 Docs/docs/developer-guide/data-structures.md` with the nested
  `checkagainst` schema.
- Updated `06 Docs/docs/user-guide/gtk-gui.md` with the redesigned tab,
  sections, tooltips, Get Entries, Add pair, and auto-seeding behavior.
- Updated `06 Docs/docs/commands-and-modules/python-modules.md` to list the
  new `feature_config` helpers.

## 0.62.4

*Released 2026-07-17*

### Changed

- **Snapshot Mass Delete space estimate** — `zfsmassdelsnaps` now prints an
  estimated disk-space-free message after listing snapshots that would be
  deleted. The estimate is the sum of each snapshot's `used` property and is
  shown in both ignore and respect modes, including during dry runs.
- **Snapshot Mass Delete auto-proceeds hold releases** — In ignore mode, the
  deletion loop now sets `autoproceed='Y'` so releasing holds no longer prompts
  the user to press Enter for every snapshot. The single approval prompt before
  deletion remains.

### Tests

- Updated `tests/test-zfsmassdelsnaps` to verify the space-estimate message in
  ignore/respect modes and to confirm `autoproceed='Y'` is active during ignore
  mode deletions.
- Added edge-case tests in `tests/test-zfsmassdelsnaps` for zero and
  non-numeric snapshot `used` values in the space estimate.
- Added `test_bind_treeview_no_resizable_columns_does_nothing` in
  `tests/python/test_gui_infrastructure.py` to ensure `bind_treeview()` handles
  all-fixed column layouts gracefully.

### Documentation

- Updated `06 Docs/docs/user-guide/gtk-gui.md` to mention the Mass Delete space
  estimate and automatic hold release.

## 0.62.3

*Released 2026-07-16*

### Changed

- **Mass Delete releaseholds defaults to enabled and is only editable in ignore
  mode** — The Retention tab's Mass Delete card now defaults
  `releaseholds='Y'`. The **Release Holds** control is enabled only when
  **Ignore retention policies** is checked; in respect mode it is disabled and
  forced to `'N'` so retention-policy pruning never silently releases holds.
- **Generic Y/N combo default** — `gui_helpers.add_var_row()` now defaults an
  absent Y/N variable to `'N'` consistently, matching the Mass Delete behavior.

### Tests

- Added `TestMassDeleteConfig` in `tests/python/test_feature_config.py` to cover
  `get_retention_mass_delete_config()` defaults and merge behavior.
- Added `TestAddVarRowYNCombo` in `tests/python/test_gui_infrastructure.py` to
  verify Y/N combo active state for present and missing variables.
- Added dirty-detection tests in `tests/python/test_retention_page.py` for
  `releaseholds` tracking in ignore vs. respect mode.
- Fixed `tests/test-repair-iscsi-luns` to provide `find_zfsutility_script()` so
  the evaluated script can locate `rootcheck` in test environments where the
  deployed `bashinit` does not define it.

## 0.62.2

*Released 2026-07-16*

### Fixed

- **`zfsmassdelsnaps` respect mode with no matching snapshots** — When no
  snapshots would be removed by the retention policy, the respect-mode path no
  longer attempts to deduplicate an empty candidate list. It now reports
  "No snapshots would be removed by retention policies." and exits cleanly.
- **Invalid escape sequence in diagnostic script** — The docstring in
  `07 GTK + Python/diagnose_zfs_repository.py` now uses a raw string so the
  escaped shell path no longer emits a `SyntaxWarning`.

### Tests

- Added `test_respect_no_matching_snapshots` to `tests/test-zfsmassdelsnaps` to
  verify the respect-mode no-match path.

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

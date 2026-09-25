# Testing

ZFS Utilities has a two-layer test framework:

- **Bash suites** in `tests/` — test bash scripts with mock `zfs` / `zpool` overrides.
- **Python suites** in `tests/python/` — test Python modules (`backup_config.py`,
  `command_builders.py`, GUI helpers, etc.) with `unittest` and `MagicMock`.

Both layers are run automatically by `tests/run-tests`.

---

## Running Tests

```bash
# All suites (bash + Python)
tests/run-tests

# Single bash suite
tests/run-tests test-zfsretain

# Single Python suite
tests/run-tests test_backup_config

# Quiet — summary only
tests/run-tests -q

# Failures only
tests/run-tests --failures-only

# Include the *-soak timing suites (see "Soak suites" below)
tests/run-tests --with-soak

# List live per-suite test counts (--count is an alias for --list). Bash
# suites run quietly once so the counts are executed totals, not estimates;
# Python suites are counted by pytest collection, which runs no tests.
tests/run-tests --list

# Bash suites: limit parallelism (default is one below nproc, min 2)
tests/run-tests --jobs 4

# Bash suites: serial debug mode (same results, no parallelism)
tests/run-tests --jobs 1

# Show the 10 slowest bash suites at the end (N optional, default 10)
tests/run-tests --slowest 10

# Persist the full console stream to a file (overwrites any previous file)
tests/run-tests --log /tmp/zfs-run.log
```

The `--log` option captures the harness's own console output, including
failing-suite dumps and the overall summary; it pairs with the
redirect-and-read pattern in `tests/AGENTS.md` so a truncated interactive
console never forces a full-suite rerun.

Test counts are intentionally not maintained in documentation — use
`--list` whenever a current number is needed.

The `tests/run-tests` harness detects whether a name starts with `test_` (Python) or
`test-` (bash) and routes it to the correct runner.

### Parallel bash runs and per-suite timing

Bash suites run in parallel by default (`--jobs N`; default `nproc - 1`, min 2,
leaving one core for the system). Suites are self-contained — mocked `zfs`/`zpool`,
own `mktemp` state, per-suite lock dirs — so parallel runs are safe; `--jobs 1` is
the serial debug mode and produces identical pass/fail results.

Per-suite wall time is always recorded. At the end of every run:

- `--slowest N` prints the N slowest bash suites with their durations.
- A soft budget warns (never fails) about non-soak suites taking more than 5
  seconds, listed in an `Over budget (> 5s)` section. Keep suites under the
  budget using the env-overridable timing knobs (see "Soak suites" below), not
  by deleting coverage.

### Soak suites

Bash suites whose name ends in `-soak` contain randomized, time-dependent
timing-conflict coverage (for example `test-zfslockmanager-soak`). They run at
realistic timings — seconds, not milliseconds — so they are excluded from default
runs: `tests/run-tests` reports them as `SKIPPED (soak suite)` and they do not
affect the exit code. Run them on demand or nightly, either by naming the suite
explicitly (`tests/run-tests test-zfslockmanager-soak`) or with `--with-soak`.

New tests must not use real `sleep` calls to probe timing behavior — use the
env-overridable timing knobs the product exposes (for the lock manager see
[lock-manager.md](lock-manager.md#timing-knobs-environment-overrides)) and keep
genuinely time-dependent conflict scenarios in a `-soak` suite.

### Environment preflight and skips

A red suite must always mean a real problem, so `tests/run-tests` detects the
environment up front — GTK (`gi`), `pv`, `zfs`/`zpool`, root, and the
integration test pools — and compares it against the requirements declared in
`tests/requirements.manifest` (one `capability path` line per suite).

Suites whose requirements are missing are reported as
`SKIPPED (missing: <caps>)` with the reason stated, are not executed, and never
affect the exit code; when skips are the only non-passes the run still exits 0.
The first line of a normal run summarizes the detection:

```text
Environment: gi=present pv=present zfs=present root=MISSING test-pools=MISSING
```

Python suites that use GTK-dependent modules without `mock_gtk()` declare the
dependency in `tests/requirements.manifest` and guard it, so direct
`pytest tests/python/...` invocations skip identically:

- Module-level imports of GTK-dependent modules go through
  `test_support.import_or_skip_gi("<module>")` (so collection survives
  without gi), paired with `pytestmark = requires_gi` (so a mock-bound
  module already in the `sys.modules` cache cannot let tests run against
  mocks).
- GTK used only inside test bodies — `@patch` decorators on GUI modules, or
  runtime GUI imports outside a `mock_gtk()` context — is covered by
  `pytestmark = requires_gi` alone.

A consistency check in `test_gui_infrastructure.py` enforces both rules and
that the manifest matches the guarded suites. Skipped Python tests are
counted separately in the overall summary (`Python tests skipped`).

The upshot: in a bare container (no GTK/ZFS/pv) the harness runs every
environment-independent suite green and lists every skipped suite with its
reason — nothing red that is not a real regression. Unexpected skips on a
development machine are environment problems to report, never to work around.

### CI and dev container

One canonical test environment is defined in code and used by both CI and the
dev container. `share/dev/install-test-deps.sh` installs every system and
Python dependency the suite needs (Debian/Ubuntu); it is the single source of
truth, consumed by both of the following.

`.devcontainer/` builds an Ubuntu 24.04 image with all dependencies. To run
the suite in it from a repo checkout:

```bash
docker build -f .devcontainer/Dockerfile -t zfsutilities-dev .
docker run --rm --init -v "$PWD:/workspace" -w /workspace zfsutilities-dev xvfb-run -a bash tests/run-tests
```

The GUI suites instantiate real GTK widgets, so the container (which has no
display) runs the suite under `xvfb-run`. `--init` gives the container a real
init process (`xvfb-run` waits on a signal from `Xvfb` and misbehaves as PID
1), and invoking the suite through `bash` keeps the command identical on any
volume/filesystem. Inside the container the run is
green; the only skips are the soak suite (excluded from default runs) and the
integration suite (no test pools in a container).

`.github/workflows/tests.yml` runs on every push and pull request: install
dependencies, run the suite under `xvfb-run -a`, then run the
documentation-integrity suite. A scheduled nightly job runs
`tests/run-tests --with-soak`.

---

## Bash Test Suites

| Suite | What it covers |
|-------|----------------|
| `test-archive-vm` | `archive-vm` retire-snapshot selection and invocation (single-node and two-node) |
| `test-attach-vm-disk` | `attach-vm-disk` zvol-path parsing and validation |
| `test-check-prerequisites` | `check-prerequisites` tool version checks (mkdocs major-version gating) |
| `test-cleanup-zfsutilities-legacy` | `cleanup-zfsutilities-legacy` prompt, `--yes`, `--dry-run`, and non-symlink guards |
| `test-clone-vm` | `clone-vm` storage heredoc bootstrap and lock sourcing |
| `test-datesubtract` | `datesubtract` usage errors and day/month/year output via `log_msg` |
| `test-deploy-version` | Root-level script selection, exclusions, retention-policy file filtering, critical-script validation, no production wiring, and VERSION-file casing |
| `test-detach-vm-disk` | `detach-vm-disk` iSCSI manifest removal |
| `test-enroll-efi-keys-vm` | `enroll-efi-keys-vm` EFI-disk and iSCSI by-path parsing for Secure Boot enrollment |
| `test-enroll-iscsi-pool` | `enroll-iscsi-pool` POOL_TARGET insertion (multi-line/single-line/no declaration), idempotence, peer-first ordering, storage-host gating, dry-run, single-node no-op |
| `test-ensure-restored-vm-iscsi` | `ensure-restored-vm-iscsi` parsing: zvol basename/pool extraction, by-path LUN extraction, VM-config LUN lookup, EFI disk detection by size, fallback LUN assignment when zvol disk numbers do not match config slots, and storage-side script forwarding |
| `test-findoffsitepool` | `findoffsitepool` online-candidate selection |
| `test-installer-checks` | Installer prerequisite checks and desktop-launcher helper functions |
| `test-installer-retention` | Installer default retention profile initialization and preservation of existing user profiles |
| `test-iscsi-add-encrypted-luns` | Encrypted-LUN config path resolution (modern + legacy fallback) and targetcli invocation |
| `test-list-vm-disks` | `list-vm-disks` VM disk maps: configs, LUN/host-device maps, running VMs |
| `test-lock-coverage` | Static checks that locked scripts source zfslockmanager, initialize it, and acquire locks |
| `test-logging` | `log_msg` writes all messages to the session log file and ignores `msg_level`; unset `ZFSUTILITIES_LOG_FILE` handling; `ask_yn`, `warn`, and `die` helpers |
| `test-migration` | One-time migration of config/history/profiles/system files with legacy symlinks |
| `test-module-dependencies` | Static analysis: root-level bash modules source the modules whose functions they call |
| `test-move-vm-disk` | `move-vm-disk` helper functions: disk-key parsing, manifest add/remove, validation helpers, state round-trip, heredoc bootstrap |
| `test-new-vm-disk` | `new-vm-disk` EFI disk-line building with `ms-cert` gating |
| `test-node-lib` | `find_zfsutility_script` resolution across `bin/`, `lib/`, and `python/` layouts |
| `test-paths` | `paths.sh` defaults, composed paths, legacy paths, and environment overrides |
| `test-proxmox-required-guards` | Proxmox scripts fail fast when `qm`/`pct` are absent |
| `test-remove-vm` | `remove-vm` VMID validation, config-referenced/orphan/reassigned zvol classification, `--cleanup-orphans`, and user confirmation |
| `test-rename-vm-disk` | `rename-vm-disk` VM-config reference discovery (single- and two-node) |
| `test-repair-iscsi-luns` | `repair-iscsi-luns` backstore/target parsing and zvol discovery |
| `test-repair-vm-disk-sizes` | `repair-vm-disk-sizes` size byte-to-human conversion, by-path/storage-ref size resolution, config line repair, dry-run |
| `test-restart-iscsi-services` | VM running-state detection before iSCSI target restart and main() helper invocation |
| `test-run-tests-preflight` | Harness self-test: run-tests environment preflight, manifest requirement skips, soak-suite gating, and the pytest exit-5 rule |
| `test-safe-iscsi-save` | Degraded-config guard for iSCSI saveconfig and encrypted-backstore boot-config stripping |
| `test-startdocserver` | Server health checks, PID discovery, CWD mismatch, restart logic |
| `test-switch-version` | Version switching, production wiring, prior-version uninstall, rollback, `--uninstall`, `--list`, and obsolete systemd artifact cleanup |
| `test-test-lib` | Harness assertion helpers: pass/fail/skip counter semantics and golden assertions |
| `test-unarchive-vm` | `--new-vmid` rewriting, UUID regeneration, conflict handling |
| `test-uninstall-some-versions` | Bulk version uninstall from an explicit list file |
| `test-uninstall-version` | Single-version uninstall prompting with `-y`/`--yes` |
| `test-uninstall-zfsutilities` | Full uninstall: preserve-by-default, `--purge`, `--dry-run` |
| `test-zfs-diagnose-busy` | Diagnostic output from `zfs-diagnose-busy` — busy dataset causes |
| `test-zfs-send-receive-dryrun` | Dry-run logging, space checks, resume-token helpers (including non-existent destination), clone messages, pv quiet in headless mode, full-copy lock hand-off, two-step full transfers, pool-root full-copy fallback |
| `integration/test-zfs-send-receive-pools` | Real-pool integration tests for `zfs-send-receive`: full copy, incremental with/without intermediates, rollback, resume token, space-check skip, clone copy. Requires root and the local test pools described below. |
| `test-zfsbuildfsarray` | Dataset array building with includes/excludes/depth/sorting |
| `test-zfscheckagainst` | `zfscheckagainst` snapshot verification against backup/offsite counterparts (online and hold-tag paths) |
| `test-zfscheckrunningvms` | `zfscheckrunningvms` exit codes when `qm`/`pct` are missing |
| `test-zfscleanup` | Pool selection: config pools, explicit argument, fallback to online pools, offline skip |
| `test-zfscommsnap` | Common snapshot detection by GUID, most-recent/oldest modes |
| `test-zfsconfig` | `zfsconfig` pool-entry emission (string, dict, and mixed forms) |
| `test-zfsdailybackup` | `zfsdailybackup` pull/push failure WARN-and-continue and dry-run logging |
| `test-zfsdelallholds` | Selective hold release by tag patterns |
| `test-zfsdelallsnaps` | Return-code behavior and lock acquisition around snapshot deletion |
| `test-zfsdelfs` | iSCSI teardown/rebuild manifest cleanup for `zfsdelfs` |
| `test-zfsdelsnap` | Snapshot deletion safety checks, hold release, `zfscheckagainst` dependency sourcing, user-hold blocking |
| `test-zfsfullcopy` | `zfsfullcopy` full-copy wrapper: overrides, required parameters, single `send-receive` invocation, parameter forwarding |
| `test-zfslockctl` | `zfslockctl cmd_wait` availability and interval validation: fractional `ZFSLOCK_WAIT_INTERVAL`, invalid/zero fallback, no-sleep fast path |
| `test-zfslockmanager` | Lock acquire/release, conflict detection, hierarchy, stale cleanup, headless abort, multi-lock acquisition, timing-knob sanitization, `source_helper` loading context |
| `test-zfslockmanager-remote` | Remote lock hold/check/conflict protocol |
| `test-zfslockmanager-soak` | Randomized timing-conflict scenarios for the lock manager at realistic timings — including wait/retry loops and headless timed waits (skipped by default; see "Soak suites") |
| `test-zfsmassdelsnaps` | Mass snapshot deletion: ignore/respect retention, dry-run, approval, releaseholds forwarding |
| `test-zfsmount` | Lock acquisition before mount/unmount per dataset |
| `test-zfsreapplyholds` | Capture/apply snapshot holds, CLI argument parsing, dry-run apply |
| `test-zfsrestore` | `zfsrestore` full-copy wrapper: overrides, legacy second overrides, required parameters, single `send-receive` invocation, parameter forwarding |
| `test-zfsrestoresendstream` | Lock acquisition before each zfs receive destination |
| `test-zfsresume` | Lock acquisition before reading resume token |
| `test-zfs-migrate-send` | `zfs-migrate-send` fresh-send pipeline (`-Rw`/`-u -F -s -v`), `-nPRw` size estimate, resume via `zfs send -t <token>` (received `-v`), stale/unexpected token abort + fresh retry, failure re-run hint (rc 8), pv/rate-limit plumbing |
| `test-transfer-lib` | `transfer-lib.sh` pv-arg construction (tty/LOG_INHERIT/headless/rate limit), resume-token validation and stale-string classification, token abort (live + dry-run), space-check math and WARN text, `transfer_do` pipeline argv and FATAL rc |
| `test-zfsretain` | Retention policy phases (offsite dedup, same-day dedup, oldest-first bucket pruning, empty logging, retain=0) |
| `test-zfsretain-debug` | `zfsretain` sources cleanly and defines the retain function |
| `test-zfsscruball` | `zfsscruball` state file, `zpool scrub -w` invocation, completed-pool skip |
| `test-zfssend` | `zfssend` defines a send function after sourcing |
| `test-zfsshowbigstuff` | `zfsshowbigstuff` usage errors and sort-option handling |
| `test-zfssnapbuild` | Snapshot name generation, bucket logic, snapfile handling |
| `test-zfsunmount` | Lock acquisition before unmount per dataset |

Bash tests run without a real ZFS pool — commands are intercepted with bash
function overrides so every suite can execute as a normal user.

### Writing a New Bash Suite

1. Create `tests/test-<scriptname>` (executable, no extension).
2. Source `test-lib.sh` at the top.
3. Define test functions that call `test_start` plus any assertion helpers.
4. Call `test_summary` at the end.

If the suite genuinely needs a system binary that other suites mock (rather
than overriding the command the way `test-lib.sh` mocks do), declare the
requirement with a `capability tests/test-<scriptname>` line in
`tests/requirements.manifest` so the harness skips it cleanly where the binary
is absent.

Minimal example:

```bash
#!/usr/bin/bash
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/test-lib.sh"

test_example() {
    test_start "Addition works"
    local result=$(( 2 + 2 ))
    assert_equals "4" "$result"
}

test_example
test_summary
```

### Bash Assertion Helpers

| Helper | Usage |
|--------|-------|
| `assert_equals expected actual` | Pass if strings match |
| `assert_contains haystack needle` | Pass if haystack contains needle |
| `assert_rc expected actual` | Pass if return codes match |
| `assert_array_len expected "${arr[@]}"` | Pass if array length matches |
| `assert_golden name actual` | Compare against `tests/golden/<suite>/<name>.golden` (see below) |

### Golden Files

Command-construction tests compare against golden files instead of
per-argument assertion clusters. `assert_golden <name> <actual>` (bash) and
`golden.check(testcase, actual)` (Python) compare against
`tests/golden/<suite>/<name>.golden` in canonical form: exactly one trailing
newline, and argv lists serialized one element per line so diffs read
per-argument.

After a legitimate refactor, run `UPDATE_GOLDEN=1 tests/run-tests <suite>`,
then `git diff` the goldens and review them like code. Update mode rewrites
only goldens whose content actually changed (an update run with no product
change produces an empty `git diff`), and marks those tests "updated" (bash:
the `Updated:` summary line; Python: skips) rather than passed. Missing
goldens fail with the command that creates them. Regeneration runs should
target single suites (they run serially through `run-tests`); update mode
under a parallel full run is not the documented path.

### Bash Mock Infrastructure

`test-lib.sh` overrides `zfs()`, `zpool()`, `delsnap()`, `ask_yn()`, `date()`, and
`log_msg()` (redirected to a per-test log file).
Because scripts are *sourced* into the test shell, these overrides intercept
`$(zfs ...)` and pipeline invocations automatically — no `PATH` manipulation is
needed.

#### Common Mock State Variables

| Variable | Purpose |
|----------|---------|
| `_mock_zfs_fs_list` | Output for general `zfs list` dataset listings |
| `_mock_zfs_snap_lists[<dataset>]` | Snapshot names per dataset (for `zfs list -t snap`) |
| `_mock_zfs_guid_lists[<dataset>]` | GUID list per dataset (for `zfs list -o guid`) |
| `_mock_zfs_props[<dataset>:<property>]` | Property values returned by `zfs get` |
| `_mock_zfs_snaps[<snapshot>]` | Snapshot existence flag (for `zfs list -t snapshot <snap>`) |
| `_mock_zfs_datasets[<dataset>]` | Dataset existence flag (for `zfs list <dataset>`) |
| `_mock_zfs_send_size` | Byte size returned by `zfs send -nP` |
| `_mock_zpool_list` | Output for `zpool list -Ho name` |

#### Setting Up Mocks

```bash
# Dataset listing
mock_zfs_fs_list "pool/src/data\npool/src/vm"

# Snapshots for a specific dataset
mock_zfs_snap_list_for "pool/src" "pool/src@snap1\npool/src@snap2"

# Property lookup
mock_zfs_prop "pool/src" "available" "10000000000"
mock_zfs_prop "pool/src@snap1" "type" "snapshot"
```

---

## Python Test Suites

| Suite | What it covers |
|-------|----------------|
| `test_action_dispatch` | Page button specs, action dispatch table, Logs tab button wiring, and Disks tab pool-growth button wiring |
| `test_app_context` | Shared operational state (app context) helpers for GUI pages |
| `test_backup_config` | Config load/save, defaults, pools, retention, UI state, snapshot name generation, log pruning, message level |
| `test_backup_history` | History entry schema, load/save/prune, success-rate calculation, human-size parsing, duration formatting |
| `test_backup_page` | Backup tab UI labels (including pre/post command labels), config load/collect helpers, and frame header widget support |
| `test_backup_runner` | Session log creation, subprocess output parsing, byte counting, trailer formatting, completion-callback rc/failure reporting, fatal step messages, and log size cap |
| `test_checkagainst_derivation` | Checkagainst derived-row generation, merge, and source/dest-root helpers |
| `test_checkagainst_page` | Checkagainst tab table editing and config persistence |
| `test_command_builders` | Rsync/ZFS command builders, retention step descriptions, endpoint parsing, dry-run assignments, host detection |
| `test_config_core` | JSON config load/save and generic state helpers |
| `test_config_migrations` | Schema migrations 1→24, idempotency, missing migration errors |
| `test_cron_manager` | Cron line generation, condition support, human-readable interpretation, next-run computation |
| `test_dashboard_page` | Dashboard layout, task handling, pool/VM/scrub/history queries, warning indicators (incl. SSD/NVMe wear), surface-test running-task cancel, async refresh loading state |
| `test_dataset_actions` | Datasets tab actions (mount/unmount/destroy/holds) driven through BackupRunner |
| `test_datasets_page` | Datasets tab UI, dataset tree, and mounted-state refresh |
| `test_datasets_tree` | Lazy dataset-tree loading in `gui_helpers` |
| `test_diagnose_zfs_repository` | `diagnose_zfs_repository.py` — diagnostic main() output for pools, datasets, snapshots, and error paths |
| `test_disk_actions` | `disk_actions.py` — Disks tab SMART-details action and selected-disk path resolution (name/by-id fallback) |
| `test_disk_repository` | `disk_repository.py` — lsblk, by-id, and smartctl subprocess isolation, wear/self-test parsing, boot-disk filtering |
| `test_disk_surface_test` | `disk_surface_test.py` — SMART self-test state machine, JSON persistence under flock, cell-text formatting, start/cancel dialog, Disks-page sensitivity gating and dashboard cancel dispatch |
| `test_disks_page` | Disks tab UI, including topology-selection highlighting in the inventory |
| `test_profile_dialogs` | Apply Profile picker treeview/dialog/execution, Rewrite Data gating, workload profile manager/editor (driven from the Datasets page); Add/Recall schedule-profile dialogs and duplicate-name overwrite handling |
| `test_disks_page_growth_buttons` | Disks tab pool-growth button sensitivity gating (Add Data Vdev, Expand Vdev, Replace, Detach, Add Infra Vdev, Migrate Pool): compute-host, runner-busy, tooltip precedence |
| `test_docs_integrity` | MkDocs nav consistency, orphan-file detection, internal link resolution, anchor existence, hook importability; AGENTS.md repo-relative path and `Branch:` reference validation |
| `test_docs_viewer` | Standalone documentation viewer launcher |
| `test_feature_config` | Per-feature config getters/setters, snapshot name generation, checkagainst entry merge, workload profile immutability |
| `test_file_locking` | Advisory flock helpers |
| `test_golden` | `golden.py` golden-file helper — canonical serialization, compare/update modes, missing-golden errors |
| `test_gui_helpers` | `gui_helpers` utilities, including mounted-snapshot detection via `mount -t zfs` and orange non-default expander labels |
| `test_gui_infrastructure` | GTK mock setup, GUI module imports, docs viewer zoom/navigation/state persistence, anchor scrolling |
| `test_installer_retention` | Installer retention profile initialization: default-only on new install and preservation of existing profiles |
| `test_iscsi_enroll` | `iscsi_enroll.py` — derive_target_short, is_iscsi_managed_pool, enroll argv building, post-create enrollment offer (two-node gating, decline/failure paths) |
| `test_legacy_retention` | Legacy `zfsretainpol-*` file parsing and pool scanning |
| `test_log_index` | Persistent session-log metadata index |
| `test_logging_config` | Message levels, GUI sink, session log env helpers, and session log truncation |
| `test_logs_page` | Log list scanning, filtering, deletion, status parsing, tail-only viewer for large files, column-header label tooltips, and pop-out reparenting |
| `test_main` | GUI entry point: PID-file single-instance, auto-replace, transient wait dialog, event pumping, retry-after-remote registration, pkexec logic, initial dashboard refresh |
| `test_migration` | One-time state-file migration helper |
| `test_node_config` | Two-node configuration loading and resolution |
| `test_offsite_page` | Offsite tab UI, offsite pool detection, and config helpers |
| `test_offsite_runner` | Offsite run command builders and pool detection |
| `test_page_runners` | Backup/offsite/restore run handlers, session log preparation, auto-destination, pull-step activation |
| `test_path_utils` | Shared path helpers mirroring bash `$mydir` / `find_zfsutility_script` behavior |
| `test_paths` | Centralized path-resolution module (local and remote deployed layouts) |
| `test_pool_actions` | Pool registry add/remove/save/revert action handlers |
| `test_pool_create` | `pool_create.py` — disk eligibility and partition policy, vdev separation, pool-name validation, ashift suggestion, RAIDZ capacity estimator, RAID10 count validation, profile -O options |
| `test_pool_create_wizard` | `pool_create_wizard.py` — wizard page gating, exact command building (incl. RAID10 mirror pairs), handler guards, Create Pool button sensitivity, scripted end-to-end flow with lock acquire/release and registry offer |
| `test_pool_growth` | `pool_growth.py` — attach/replace/detach classification, replace-pair and infra-vdev validation, scrub-block check |
| `test_pool_growth_dialogs` | `pool_growth_dialogs.py` — Add Vdev/Attach/Replace/Detach/Infra-Vdev pure helpers, handler guards, and dialog flows |
| `test_pool_migrate` | `pool_migrate.py` — migration snapshot/temp-pool naming, step planning, capacity checks, tree verification, migration argv builders |
| `test_pool_migrate_dialogs` | `pool_migrate_dialogs.py` — Migrate Pool dialog problems/warnings/plan, scrub-block gate, handler guards, two-phase copy/cutover execution, iSCSI repair chaining |
| `test_pool_watch` | Per-pool dataset watch window |
| `test_pools_page` | Pools tab registry UI |
| `test_profile_integration` | Concurrent profile execution: disjoint datasets, same-dataset conflict, backup+prune serialization |
| `test_profile_manager` | Profile CRUD, update, name validation, listing, existence checks, lifecycle logging, condition defaults |
| `test_profile_runner` | Backup/offsite/restore/retention profile step building, rsync failure diagnosis in headless runs |
| `test_profile_runner_concurrency` | Per-profile advisory locks, duplicate-invocation suppression, and metadata |
| `test_profile_validation` | Backup/offsite profile scope-alignment checks |
| `test_restore_page` | Restore tab UI widgets, config load/collect, auto-destination, advanced variables |
| `test_restore_runner` | Restore destination computation and zfs-send-receive parameter mapping |
| `test_retention_actions` | Retention tab action handlers |
| `test_retention_page` | Retention Policies tab UI |
| `test_runner_factory` | Runner factory wiring for page runners |
| `test_runner_shim` | `runner.py` deprecation shim — legacy argument translation to pytest and deprecation notice |
| `test_schedule_page` | Schedule page path resolution, dirty tracking, condition field, run-now child-watch handling, fatal-fallback logging, async refresh, and next-run caching |
| `test_scrub_manager` | Scrub state parsing, queue/target management, priority ordering, tick logic, systemd timers, ZFS-native in-progress operation parsing |
| `test_scrub_page` | Scrub page store schema, flicker-free refresh logic, and drag-and-drop priority ordering |
| `test_session_log` | Per-run session log helpers (create, append, trailer, size cap) |
| `test_workload_profiles` | Workload profile property filtering, profile matching, apply plan, `zfs set` command building, warnings |
| `test_zfs_capabilities` | OpenZFS release-variation gating (incl. patch-level minimums such as `zfs_rewrite` at 2.3.4), pool-feature cross-check parsing |
| `test_zfs_diagnostics` | `gui_helpers.diagnose_dataset_busy` — detects each known cause via mocked `subprocess.run` |
| `test_zfs_lock_manager` | `zfs_lock_manager` two-node lock behavior and stale-lock cleanup (including unverifiable holder scripts) |
| `test_zfs_repository` | `zfs_repository.py` — ZFS/zpool subprocess isolation, importable-pool config parsing, `zpool create` (incl. RAID10 mirror pairs) and pool-growth/migration command building and execution |
| `test_zfsinfo` | Pool/dataset/snapshot info gathering with mocked `subprocess` |
| `test_zfsutilities_gui` | Main GUI window behavior, dashboard/scrub/disks timer lifecycle |

Most Python suites are standard `unittest.TestCase` classes executed by
[pytest](https://docs.pytest.org/) with
[pytest-xdist](https://pytest-xdist.readthedocs.io/) parallelism — no test
rewrite was needed and assertion failures get pytest's expected-vs-actual
diff output. A few suites (for example `test_golden`) use pytest fixtures
directly. `tests/run-tests` remains the single entry point for both
layers; `tests/python/runner.py` is a deprecated shim that forwards to
pytest for older invocations.

### Python Dependencies

- `pytest` and `pytest-xdist` — the test runner. Install both with
  `python3 -m pip install -r requirements-dev.txt`.
- `pyyaml` — required only for `test_docs_integrity` (parses `mkdocs.yml`).
  Install with `python3 -m pip install pyyaml`.
- `gi` — the GTK tests mock `gi.repository` so no display server is needed.

### Running Python Suites Directly

```bash
# All Python suites, parallel across CPUs (worker count auto-capped by
# available memory — each xdist worker peaks at ~600-900 MB; override with
# ZFSUTILITIES_PYTEST_JOBS=N)
python3 -m pytest tests/python -n auto -q

# Specific suite (fail-fast, short tracebacks)
python3 -m pytest tests/python/test_backup_config.py -x --tb=short

# Single-process run (definition order; useful for order-dependence checks)
python3 -m pytest tests/python -q

# Legacy entry points still work (runner.py prints a deprecation notice)
./tests/run-python-tests
./tests/run-python-tests test_backup_config
```

`--failures-only` has no exact pytest equivalent; it maps to `-q`, which
prints only failures plus the final summary.

GUI suites import their modules under `test_support.mock_gtk()`. Without
options, the first `mock_gtk()` context that imports a GUI module wins: the
module keeps that context's `Gtk`/`GLib` mocks for the rest of the session,
and each `Gtk.Widget()` returns one shared per-class mock whose call history
accumulates across every test that ran before. Tests must therefore not rely
on unittest's alphabetical method ordering and must not assert per-test call
counts on shared widget mocks without resetting them first; likewise, patch
attributes on the module object the code under test actually imported (e.g.
patch `gui_helpers.Gtk.MessageDialog` — via a module reference bound at the
test file's own import — not a re-imported copy).

For per-test module freshness, pass `fresh=True`: every loaded GUI module
(see `test_support.GUI_MODULES`) is evicted from `sys.modules` for the
duration of the context and restored on exit, so imports inside the context
bind the current context's mocks and call history starts empty — without
leaking a different module object to the rest of the session. Use it whenever
a test asserts on widget call counts or needs to patch a GUI module it did
not itself import. Helpers that re-import a GUI module (the `_import_*`
helpers several suites use) must always pass `fresh=True`: otherwise a GUI
dependency cached with real bindings — for example `gui_helpers` imported at
collection time by a suite that uses real GTK — leaks real Gtk into the
re-imported module and crashes tests that hand mock windows to real dialog
constructors (`TypeError: could not convert value for property
'transient_for' from MagicMock to GtkWindow`).

One binding-shape rule prevents the cross-suite flakes that only appear under
`pytest -n auto`: an in-function import of a GUI module must never run bare.
Inside a test or helper, either import under a `mock_gtk()` context (the
suite's own first import establishes the sticky binding), evict the module
with `sys.modules.pop` first, or use `import_gui_fresh`. A bare import binds
whatever the `sys.modules` cache happens to hold — real classes cached by
another suite's decorator-driven import, or a mock copy from another context
— and mixing the two fails in bizarre ways (`AttributeError: Attempting to
set unsupported magic method '__init__'`, `TypeError: isinstance() arg 2
must be a type`). `TestGiImportGuards` in `test_gui_infrastructure.py`
enforces this statically.

### Writing a New Python Suite

1. Create `tests/python/test_<modulename>.py`.
2. Import `unittest` and helpers from `test_support.py`.
3. Define `unittest.TestCase` subclasses.
4. Use `test_support` fixtures for config isolation, log capture, subprocess
   mocking, and GTK mocking.
5. If the suite uses a GTK-dependent module from `python/` without
   `mock_gtk()`, declare it in `tests/requirements.manifest` and guard it:
   `test_support.import_or_skip_gi("<module>")` (with
   `pytestmark = requires_gi`) for module-level imports, or
   `pytestmark = requires_gi` alone for GTK used only inside test bodies.
   A consistency check in `test_gui_infrastructure.py` enforces this.

Minimal example:

```python
import unittest
from test_support import temp_config_dir, capture_logs

import config_core


class TestMyFeature(unittest.TestCase):
    def test_loads_default(self):
        with temp_config_dir():
            cfg = config_core.load_config()
            self.assertIn("pools", cfg)


if __name__ == "__main__":
    unittest.main()
```

### Python Golden Files

The `golden` module (`tests/python/golden.py`) is the Python half of the
golden-file workflow (see "Golden Files" above):

```python
import golden

golden.check(self, step.command)  # list: one element per line
```

`golden.check(testcase, actual, name=None)` resolves the golden as
`tests/golden/<module>/<Class>.<test>.golden` (an explicit `name` overrides
the default) and raises `AssertionError` with a unified diff on mismatch.
With `UPDATE_GOLDEN=1` a differing golden is rewritten and the test is
skipped; identical content passes and leaves the file untouched.

In update mode, updated tests appear as skips; the harness 'skipped' total
then includes golden updates in addition to any environment skips.
Compare-mode skips are environment or marker skips only.

### Python Test Support Fixtures

`tests/python/test_support.py` provides shared infrastructure:

| Fixture | Purpose |
|---------|---------|
| `temp_config_dir()` | Overrides `CONFIG_PATH`, `CRON_FILE`, `SNAPFILE`, `OFFSITE_SNAPFILE`, `SESSION_LOG_DIR`, and advisory-lock paths to a temp directory |
| `mock_subprocess()` | Patches `subprocess.run` with a stateful mock that handles `zfs`, `zpool`, `rsync`, and `ssh` commands |
| `capture_logs()` | Captures `log_msg` output to a list for assertions |
| `capture_stderr()` | Captures `sys.stderr` to a string |
| `mock_gtk()` | Patches `gi.repository` with `MagicMock` so GUI modules import without a display |
| `import_gui_fresh(name)` | Inside a `mock_gtk()` context: evicts *name* and the whole GUI closure from `sys.modules`, then imports — guarantees the module binds to the *current* context's mocks instead of a stale copy cached by another suite |
| `import_or_skip_gi(name)` | Imports a GTK-dependent module at module level, skipping the whole suite cleanly when `gi` is unavailable |
| `requires_gi` | Module-level `pytest.mark.skipif` for suites that use GTK only inside test bodies |
| `check_pyyaml()` | Skips the current test if `pyyaml` is not installed |

### Python Mock Subprocess

The `MockSubprocess` class tracks every call and returns canned output:

```python
from test_support import mock_subprocess

with mock_subprocess() as m:
    m.add_zpool_list([{"name": "tank", "health": "ONLINE"}])
    m.add_zfs_list([{"name": "tank/data", "used": "10G"}])
    # ... code that calls subprocess.run(...) ...
    self.assertEqual(len(m.calls), 2)
```

---

## Integration Tests with Real Pools

In addition to the mock-based bash and Python suites, the repository contains a
small real-pool integration suite:

```
tests/integration/test-zfs-send-receive-pools
```

This suite exercises `bin/zfs-send-receive` against actual ZFS pools. It is kept
separate from `tests/run-tests` because it requires root privileges and
dedicated test pools.

### Required Test Pools

The suite expects two local test pools. Defaults:

- Source: `zfstest1`
- Destination: `zfstest2`

Pool names are configurable via environment variables:

```bash
export ZFSUTILITIES_TEST_SRC_POOL=zfstest1
export ZFSUTILITIES_TEST_DST_POOL=zfstest2
sudo tests/integration/test-zfs-send-receive-pools
```

Only pools in the suite's explicit allow-list (`zfstest1`, `zfstest2`,
`zfstest3`) may be used. The suite refuses to run if a configured pool is not
in the allow-list or is not online.

### Creating Local Test Pools

On the development VM, `/dev/sdb` is a 75 GiB empty virtual disk. It can be
partitioned and used to create three small RAIDZ1 test pools:

```bash
# Create a GPT label and 15 ~5 GiB partitions.
parted -s /dev/sdb mklabel gpt
for i in {1..15}; do
    if [[ $i -eq 1 ]]; then
        start="1MiB"
    else
        start="$(( (i-1)*5120 ))MiB"
    fi
    if [[ $i -eq 15 ]]; then
        end="100%"
    else
        end="$(( i*5120 ))MiB"
    fi
    parted -a optimal -s /dev/sdb mkpart primary "${start}" "${end}"
done
partprobe /dev/sdb

# Create three RAIDZ1 pools.
zpool create -f zfstest1 raidz1 /dev/sdb1 /dev/sdb2 /dev/sdb3 /dev/sdb4 /dev/sdb5
zpool create -f zfstest2 raidz1 /dev/sdb6 /dev/sdb7 /dev/sdb8 /dev/sdb9 /dev/sdb10
zpool create -f zfstest3 raidz1 /dev/sdb11 /dev/sdb12 /dev/sdb13 /dev/sdb14 /dev/sdb15
```

Each pool reports roughly 24.5 GiB of raw space, yielding about 20 GiB of
usable space after RAIDZ1 parity. The integration suite still sets
`space_check_min_buffer=0` for its normal scenarios to keep the existing small-
transfer logic path. The space-check scenario itself verifies the skip behavior
by setting an artificially large buffer.

### Running the Integration Suite

```bash
sudo tests/integration/test-zfs-send-receive-pools
```

The suite skips cleanly with a stated reason when named via the harness on a
machine that lacks root or the test pools:

```bash
tests/run-tests tests/integration/test-zfs-send-receive-pools
# SKIPPED (missing: root test-pools) (test-zfs-send-receive-pools)
```

The suite:

- Skips cleanly with a message if not run as root.
- Validates pool names against the allow-list.
- Creates uniquely named test datasets for each scenario.
- Uses `trap` to destroy all test datasets on success and on failure.

After a run, verify that no test datasets remain:

```bash
zfs list -r zfstest1 zfstest2
```

### Scenarios Covered

| Scenario | What it exercises |
|----------|-------------------|
| Full copy to empty destination | `doincrementals='N'` two-step transfer: full copy of oldest snapshot + incremental catch-up to target |
| Full copy with one source snapshot | `doincrementals='N'` degenerates to a single full transfer |
| Incremental copy with common snapshot | `doincrementals='Y'` with `dointermediates='Y'` |
| Incremental copy without intermediates | `doincrementals='Y'` with `dointermediates='N'` |
| Destination rollback | `handle_commsnap_rc` rc=16 with `autoproceed='Y'` |
| Resume token handling | Partial receive leaves a token; re-run resumes and completes |
| Space check skip | Large `space_check_min_buffer` causes skip |
| Clone dataset copy | Clone replicates as an independent dataset |

## Tips and Gotchas

### Bash

* **Log redirection** — `log_msg` output is redirected to a per-test log file by
`test-lib.sh` so the harness stays quiet.  Tests that need to assert on
`log_msg` output should read the file returned by `get_test_log_file()` (or
use `get_stderr_log()` from `test-zfs-send-receive-dryrun`).
* **Root check** — [rootcheck](../commands-and-modules/modules.md#rootcheck) is mocked to a no-op.  Any future suite that
legitimately requires root should check `$EUID` and call `test_skip` when
non-root.
* **Inner functions** — Functions defined *inside* another function (e.g.
`check_space_available` inside `send-receive`) become available for direct
testing **after** the outer function has been executed once.
* **Bash array scope** — Always declare and assign arrays on one line:
  `local arr=($@)`.  Splitting `arr=($@); local arr` can create an empty
array in bash 5.2.
* **Snapshot existence** — The `zfs list -t snapshot <name@snap>` mock returns
exit code 1 when the snapshot is not present in `_mock_zfs_snaps`, so scripts
that test existence with `! zfs list ...` work correctly.
* **Combined short options** — The mock parses `-Hp` as combined flags, so
`zfs get -Hp -o value available pool` resolves the property and dataset
correctly.

### Python

- **Clear stale bytecode as a wrap-up practice.** `__pycache__` directories
are gitignored artifacts that Python regenerates on demand, but stale `.pyc`
files (for example a cache left behind by a renamed or deleted suite) can
cause phantom import or test behavior. Periodically removing all
`__pycache__` directories — a good development-cycle wrap-up step before the
final full test run — keeps the caches honest; the suite run regenerates only
what it needs.
* **Config isolation** — Always wrap config-mutating tests in
`temp_config_dir()` so they do not touch the real `/var/lib/zfsutilities/config.json`.
* **GTK mocking** — Use `mock_gtk()` as a context manager when importing any
module that touches `gi.repository.Gtk`. The mock provides enough structure
for `Window` subclasses to instantiate without a display.
* **Memory footprint** — Each pytest-xdist worker peaks at roughly 600-900 MB
(the full serial layer peaks under 1 GB). `tests/run-tests` caps the worker
count by `MemAvailable` (banner line `pytest-workers=N`; override with
`ZFSUTILITIES_PYTEST_JOBS=N`) so a full run cannot crowd a desktop browser
into an OOM kill. If a run dies to the OOM killer anyway, check for leftover
trees first: interrupting the harness terminates its pytest tree, but runs
started directly with `pytest -n` leave nothing to clean up either — an
`execnet` worker exits when its controller dies.
* **Subprocess in background** — Some code spawns subprocesses with `&`.
Capturing output from a mock requires writing to a temp file from the mock
function and calling `wait` before reading it back.
* **Log capture** — `capture_logs()` intercepts `backup_config.log_msg()`
output. It works for both Python modules and bash scripts invoked via
`subprocess.run` because the bash `log_msg` writes to stderr, which can be
captured separately with `capture_stderr()`.
* **Linting** — Run `ruff check .` from the repository root before committing
Python changes. The Ruff configuration is in `pyproject.toml`.

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

# Count tests without running them (per suite + total)
tests/run-tests --count
```

Test counts are intentionally not maintained in documentation — use
`--count` whenever a current number is needed.

The `tests/run-tests` harness detects whether a name starts with `test_` (Python) or
`test-` (bash) and routes it to the correct runner.

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
| `test-remove-vm` | `remove-vm` VMID validation, zvol listing, and user confirmation |
| `test-rename-vm-disk` | `rename-vm-disk` VM-config reference discovery (single- and two-node) |
| `test-repair-iscsi-luns` | `repair-iscsi-luns` backstore/target parsing and zvol discovery |
| `test-repair-vm-disk-sizes` | `repair-vm-disk-sizes` size byte-to-human conversion, by-path/storage-ref size resolution, config line repair, dry-run |
| `test-restart-iscsi-services` | VM running-state detection before iSCSI target restart and main() helper invocation |
| `test-safe-iscsi-save` | Degraded-config guard for iSCSI saveconfig and encrypted-backstore boot-config stripping |
| `test-startdocserver` | Server health checks, PID discovery, CWD mismatch, restart logic |
| `test-switch-version` | Version switching, production wiring, prior-version uninstall, rollback, `--uninstall`, `--list`, and obsolete systemd artifact cleanup |
| `test-test-lib` | Harness assertion helpers: pass/fail/skip counter semantics |
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
| `test-zfslockmanager` | Lock acquire/release, conflict detection, hierarchy, stale cleanup, headless abort, wait/retry, multi-lock acquisition, headless timed wait |
| `test-zfslockmanager-remote` | Remote lock hold/check/conflict protocol |
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
| `test_disks_page_dataset_tuning` | Disks tab dataset-tuning pane (including the Size column), Apply Profile picker treeview/dialog/execution, Rewrite Data gating, workload profile manager |
| `test_disks_page_growth_buttons` | Disks tab pool-growth button sensitivity gating (Add Data Vdev, Expand Vdev, Replace, Detach, Add Infra Vdev, Migrate Pool): compute-host, runner-busy, tooltip precedence |
| `test_docs_integrity` | MkDocs nav consistency, orphan-file detection, internal link resolution, anchor existence, hook importability |
| `test_docs_viewer` | Standalone documentation viewer launcher |
| `test_feature_config` | Per-feature config getters/setters, snapshot name generation, checkagainst entry merge, workload profile immutability |
| `test_file_locking` | Advisory flock helpers |
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
| `test_profile_dialogs` | Add/Recall profile dialogs, duplicate-name overwrite handling |
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
| `test_schedule_page` | Schedule page path resolution, dirty tracking, condition field, run-now child-watch handling, fatal-fallback logging, async refresh, and next-run caching |
| `test_scrub_manager` | Scrub state parsing, queue/target management, priority ordering, tick logic, systemd timers, ZFS-native in-progress operation parsing |
| `test_scrub_page` | Scrub page store schema, flicker-free refresh logic, and drag-and-drop priority ordering |
| `test_session_log` | Per-run session log helpers (create, append, trailer, size cap) |
| `test_workload_profiles` | Workload profile property filtering, profile matching, apply plan, `zfs set` command building, warnings |
| `test_zfs_capabilities` | OpenZFS release-variation gating (incl. patch-level minimums such as `zfs_rewrite` at 2.3.4), pool-feature cross-check parsing |
| `test_zfs_diagnostics` | `gui_helpers.diagnose_dataset_busy` — detects each known cause via mocked `subprocess.run` |
| `test_zfs_lock_manager` | `zfs_lock_manager` two-node lock behavior |
| `test_zfs_repository` | `zfs_repository.py` — ZFS/zpool subprocess isolation, importable-pool config parsing, `zpool create` (incl. RAID10 mirror pairs) and pool-growth/migration command building and execution |
| `test_zfsinfo` | Pool/dataset/snapshot info gathering with mocked `subprocess` |
| `test_zfsutilities_gui` | Main GUI window behavior, dashboard/scrub/disks timer lifecycle |

Python tests run with the standard library `unittest` module (no pytest required).
A custom coloured runner (`tests/python/runner.py`) produces output that matches
the bash harness format.

### Python Dependencies

- `pyyaml` — required only for `test_docs_integrity` (parses `mkdocs.yml`).
  Install with `python3 -m pip install pyyaml`.
- `gi` — the GTK tests mock `gi.repository` so no display server is needed.

### Running Python Suites Directly

```bash
# All Python suites
./tests/run-python-tests

# Specific suite
./tests/run-python-tests test_backup_config

# Run from inside tests/python
cd tests/python && python3 runner.py

# Specific suite
cd tests/python && python3 runner.py test_backup_config

# Verbose / quiet
cd tests/python && python3 runner.py -v
cd tests/python && python3 runner.py -q

# The suites must also pass under a single-process pytest run (definition
# order, not unittest's alphabetical order):
cd tests/python && python3 -m pytest -q
```

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
not itself import.

### Writing a New Python Suite

1. Create `tests/python/test_<modulename>.py`.
2. Import `unittest` and helpers from `test_support.py`.
3. Define `unittest.TestCase` subclasses.
4. Use `test_support` fixtures for config isolation, log capture, subprocess
   mocking, and GTK mocking.

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

### Python Test Support Fixtures

`tests/python/test_support.py` provides shared infrastructure:

| Fixture | Purpose |
|---------|---------|
| `temp_config_dir()` | Overrides `CONFIG_PATH`, `CRON_FILE`, `SNAPFILE`, `OFFSITE_SNAPFILE`, `SESSION_LOG_DIR`, and advisory-lock paths to a temp directory |
| `mock_subprocess()` | Patches `subprocess.run` with a stateful mock that handles `zfs`, `zpool`, `rsync`, and `ssh` commands |
| `capture_logs()` | Captures `log_msg` output to a list for assertions |
| `capture_stderr()` | Captures `sys.stderr` to a string |
| `mock_gtk()` | Patches `gi.repository` with `MagicMock` so GUI modules import without a display |
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
* **Subprocess in background** — Some code spawns subprocesses with `&`.
Capturing output from a mock requires writing to a temp file from the mock
function and calling `wait` before reading it back.
* **Log capture** — `capture_logs()` intercepts `backup_config.log_msg()`
output. It works for both Python modules and bash scripts invoked via
`subprocess.run` because the bash `log_msg` writes to stderr, which can be
captured separately with `capture_stderr()`.
* **Linting** — Run `ruff check .` from the repository root before committing
Python changes. The Ruff configuration is in `pyproject.toml`.

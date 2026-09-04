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
```

The `tests/run-tests` harness detects whether a name starts with `test_` (Python) or
`test-` (bash) and routes it to the correct runner.

---

## Bash Test Suites

| Suite | Tests | What it covers |
|-------|-------|----------------|
| `test-archive-vm` | 10 | `archive-vm` retire-snapshot selection and invocation (single-node and two-node) |
| `test-attach-vm-disk` | 9 | `attach-vm-disk` zvol-path parsing and validation |
| `test-check-prerequisites` | 7 | `check-prerequisites` tool version checks (mkdocs major-version gating) |
| `test-cleanup-zfsutilities-legacy` | 13 | `cleanup-zfsutilities-legacy` prompt, `--yes`, `--dry-run`, and non-symlink guards |
| `test-clone-vm` | 7 | `clone-vm` storage heredoc bootstrap and lock sourcing |
| `test-datesubtract` | 4 | `datesubtract` usage errors and day/month/year output via `log_msg` |
| `test-deploy-version` | 23 | Root-level script selection, exclusions, retention-policy file filtering, critical-script validation, no production wiring, and VERSION-file casing |
| `test-detach-vm-disk` | 2 | `detach-vm-disk` iSCSI manifest removal |
| `test-enroll-efi-keys-vm` | 8 | `enroll-efi-keys-vm` EFI-disk and iSCSI by-path parsing for Secure Boot enrollment |
| `test-ensure-restored-vm-iscsi` | 24 | `ensure-restored-vm-iscsi` parsing: zvol basename/pool extraction, by-path LUN extraction, VM-config LUN lookup, EFI disk detection by size, fallback LUN assignment when zvol disk numbers do not match config slots, and storage-side script forwarding |
| `test-findoffsitepool` | 5 | `findoffsitepool` online-candidate selection |
| `test-installer-checks` | 29 | Installer prerequisite checks and desktop-launcher helper functions |
| `test-installer-retention` | 3 | Installer default retention profile initialization and preservation of existing user profiles |
| `test-iscsi-add-encrypted-luns` | 3 | Encrypted-LUN config path resolution (modern + legacy fallback) and targetcli invocation |
| `test-list-vm-disks` | 16 | `list-vm-disks` VM disk maps: configs, LUN/host-device maps, running VMs |
| `test-lock-coverage` | 1 | Static checks that locked scripts source zfslockmanager, initialize it, and acquire locks |
| `test-logging` | 19 | `log_msg` writes all messages to the session log file and ignores `msg_level`; unset `ZFSUTILITIES_LOG_FILE` handling; `ask_yn`, `warn`, and `die` helpers |
| `test-migration` | 6 | One-time migration of config/history/profiles/system files with legacy symlinks |
| `test-module-dependencies` | 2 | Static analysis: root-level bash modules source the modules whose functions they call |
| `test-move-vm-disk` | 14 | `move-vm-disk` helper functions: disk-key parsing, manifest add/remove, validation helpers, state round-trip, heredoc bootstrap |
| `test-new-vm-disk` | 3 | `new-vm-disk` EFI disk-line building with `ms-cert` gating |
| `test-node-lib` | 37 | `find_zfsutility_script` resolution across `bin/`, `lib/`, and `python/` layouts |
| `test-paths` | 6 | `paths.sh` defaults, composed paths, legacy paths, and environment overrides |
| `test-proxmox-required-guards` | 16 | Proxmox scripts fail fast when `qm`/`pct` are absent |
| `test-remove-vm` | 6 | `remove-vm` VMID validation, zvol listing, and user confirmation |
| `test-rename-vm-disk` | 10 | `rename-vm-disk` VM-config reference discovery (single- and two-node) |
| `test-repair-iscsi-luns` | 13 | `repair-iscsi-luns` backstore/target parsing and zvol discovery |
| `test-repair-vm-disk-sizes` | 13 | `repair-vm-disk-sizes` size byte-to-human conversion, by-path/storage-ref size resolution, config line repair, dry-run |
| `test-restart-iscsi-services` | 13 | VM running-state detection before iSCSI target restart and main() helper invocation |
| `test-safe-iscsi-save` | 6 | Degraded-config guard for iSCSI saveconfig and encrypted-backstore boot-config stripping |
| `test-startdocserver` | 13 | Server health checks, PID discovery, CWD mismatch, restart logic |
| `test-switch-version` | 8 | Version switching, production wiring, prior-version uninstall, rollback, `--uninstall`, `--list`, and obsolete systemd artifact cleanup |
| `test-test-lib` | 4 | Harness assertion helpers: pass/fail/skip counter semantics |
| `test-unarchive-vm` | 6 | `--new-vmid` rewriting, UUID regeneration, conflict handling |
| `test-uninstall-some-versions` | 7 | Bulk version uninstall from an explicit list file |
| `test-uninstall-version` | 10 | Single-version uninstall prompting with `-y`/`--yes` |
| `test-uninstall-zfsutilities` | 10 | Full uninstall: preserve-by-default, `--purge`, `--dry-run` |
| `test-zfs-diagnose-busy` | 8 | Diagnostic output from `zfs-diagnose-busy` — busy dataset causes |
| `test-zfs-send-receive-dryrun` | 39 | Dry-run logging, space checks, resume-token helpers (including non-existent destination), clone messages, pv quiet in headless mode, full-copy lock hand-off, two-step full transfers, pool-root full-copy fallback |
| `integration/test-zfs-send-receive-pools` | 7 | Real-pool integration tests for `zfs-send-receive`: full copy, incremental with/without intermediates, rollback, resume token, space-check skip, clone copy. Requires root and the local test pools described below. |
| `test-zfsbuildfsarray` | 10 | Dataset array building with includes/excludes/depth/sorting |
| `test-zfscheckagainst` | 29 | `zfscheckagainst` snapshot verification against backup/offsite counterparts (online and hold-tag paths) |
| `test-zfscheckrunningvms` | 3 | `zfscheckrunningvms` exit codes when `qm`/`pct` are missing |
| `test-zfscleanup` | 9 | Pool selection: config pools, explicit argument, fallback to online pools, offline skip |
| `test-zfscommsnap` | 6 | Common snapshot detection by GUID, most-recent/oldest modes |
| `test-zfsconfig` | 19 | `zfsconfig` pool-entry emission (string, dict, and mixed forms) |
| `test-zfsdailybackup` | 4 | `zfsdailybackup` pull/push failure WARN-and-continue and dry-run logging |
| `test-zfsdelallholds` | 6 | Selective hold release by tag patterns |
| `test-zfsdelallsnaps` | 5 | Return-code behavior and lock acquisition around snapshot deletion |
| `test-zfsdelfs` | 10 | iSCSI teardown/rebuild manifest cleanup for `zfsdelfs` |
| `test-zfsdelsnap` | 6 | Snapshot deletion safety checks, hold release, `zfscheckagainst` dependency sourcing, user-hold blocking |
| `test-zfsfullcopy` | 9 | `zfsfullcopy` full-copy wrapper: overrides, required parameters, single `send-receive` invocation, parameter forwarding |
| `test-zfslockmanager` | 42 | Lock acquire/release, conflict detection, hierarchy, stale cleanup, headless abort, wait/retry, multi-lock acquisition, headless timed wait |
| `test-zfslockmanager-remote` | 7 | Remote lock hold/check/conflict protocol |
| `test-zfsmassdelsnaps` | 16 | Mass snapshot deletion: ignore/respect retention, dry-run, approval, releaseholds forwarding |
| `test-zfsmount` | 2 | Lock acquisition before mount/unmount per dataset |
| `test-zfsreapplyholds` | 11 | Capture/apply snapshot holds, CLI argument parsing, dry-run apply |
| `test-zfsrestore` | 15 | `zfsrestore` full-copy wrapper: overrides, legacy second overrides, required parameters, single `send-receive` invocation, parameter forwarding |
| `test-zfsrestoresendstream` | 1 | Lock acquisition before each zfs receive destination |
| `test-zfsresume` | 1 | Lock acquisition before reading resume token |
| `test-zfsretain` | 17 | Retention policy phases (offsite dedup, same-day dedup, oldest-first bucket pruning, empty logging, retain=0) |
| `test-zfsretain-debug` | 1 | `zfsretain` sources cleanly and defines the retain function |
| `test-zfsscruball` | 5 | `zfsscruball` state file, `zpool scrub -w` invocation, completed-pool skip |
| `test-zfssend` | 1 | `zfssend` defines a send function after sourcing |
| `test-zfsshowbigstuff` | 10 | `zfsshowbigstuff` usage errors and sort-option handling |
| `test-zfssnapbuild` | 13 | Snapshot name generation, bucket logic, snapfile handling |
| `test-zfsunmount` | 1 | Lock acquisition before unmount per dataset |

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

| Suite | Tests | What it covers |
|-------|-------|----------------|
| `test_action_dispatch` | 44 | Page button specs, action dispatch table, and Logs tab button wiring |
| `test_app_context` | 9 | Shared operational state (app context) helpers for GUI pages |
| `test_backup_config` | 32 | Config load/save, defaults, pools, retention, UI state, snapshot name generation, log pruning, message level |
| `test_backup_history` | 36 | History entry schema, load/save/prune, success-rate calculation, human-size parsing, duration formatting |
| `test_backup_page` | 23 | Backup tab UI labels (including pre/post command labels), config load/collect helpers, and frame header widget support |
| `test_backup_runner` | 59 | Session log creation, subprocess output parsing, byte counting, trailer formatting, fatal step messages, and log size cap |
| `test_checkagainst_derivation` | 24 | Checkagainst derived-row generation, merge, and source/dest-root helpers |
| `test_checkagainst_page` | 59 | Checkagainst tab table editing and config persistence |
| `test_command_builders` | 51 | Rsync/ZFS command builders, retention step descriptions, endpoint parsing, dry-run assignments, host detection |
| `test_config_core` | 26 | JSON config load/save and generic state helpers |
| `test_config_migrations` | 55 | Schema migrations 1→24, idempotency, missing migration errors |
| `test_cron_manager` | 41 | Cron line generation, condition support, human-readable interpretation, next-run computation |
| `test_dashboard_page` | 195 | Dashboard layout, task handling, pool/VM/scrub/history queries, warning indicators, async refresh loading state |
| `test_dataset_actions` | 43 | Datasets tab actions (mount/unmount/destroy/holds) driven through BackupRunner |
| `test_datasets_page` | 52 | Datasets tab UI, dataset tree, and mounted-state refresh |
| `test_datasets_tree` | 13 | Lazy dataset-tree loading in `gui_helpers` |
| `test_diagnose_zfs_repository` | 6 | `diagnose_zfs_repository.py` — diagnostic main() output for pools, datasets, snapshots, and error paths |
| `test_disk_actions` | 6 | `disk_actions.py` — Disks tab SMART-details action and selected-disk path resolution (name/by-id fallback) |
| `test_disk_repository` | 9 | `disk_repository.py` — lsblk, by-id, and smartctl subprocess isolation |
| `test_disks_page` | 14 | Disks tab UI |
| `test_disks_page_phase2` | 36 | Disks tab dataset-tuning pane, Apply Profile dialog/execution, Rewrite Data gating, workload profile manager |
| `test_docs_integrity` | 14 | MkDocs nav consistency, orphan-file detection, internal link resolution, anchor existence, hook importability |
| `test_docs_viewer` | 9 | Standalone documentation viewer launcher |
| `test_feature_config` | 64 | Per-feature config getters/setters and snapshot name generation |
| `test_file_locking` | 9 | Advisory flock helpers |
| `test_gui_helpers` | 7 | `gui_helpers` utilities, including mounted-snapshot detection via `mount -t zfs` |
| `test_gui_infrastructure` | 144 | GTK mock setup, GUI module imports, docs viewer zoom/navigation/state persistence, anchor scrolling |
| `test_installer_retention` | 6 | Installer retention profile initialization: default-only on new install and preservation of existing profiles |
| `test_legacy_retention` | 7 | Legacy `zfsretainpol-*` file parsing and pool scanning |
| `test_log_index` | 30 | Persistent session-log metadata index |
| `test_logging_config` | 42 | Message levels, GUI sink, session log env helpers, and session log truncation |
| `test_logs_page` | 54 | Log list scanning, filtering, deletion, status parsing, tail-only viewer for large files, column-header label tooltips, and pop-out reparenting |
| `test_main` | 40 | GUI entry point: PID-file single-instance, auto-replace, transient wait dialog, event pumping, retry-after-remote registration, pkexec logic, initial dashboard refresh |
| `test_migration` | 8 | One-time state-file migration helper |
| `test_node_config` | 9 | Two-node configuration loading and resolution |
| `test_offsite_page` | 19 | Offsite tab UI, offsite pool detection, and config helpers |
| `test_offsite_runner` | 17 | Offsite run command builders and pool detection |
| `test_page_runners` | 10 | Backup/offsite/restore run handlers, session log preparation, auto-destination, pull-step activation |
| `test_path_utils` | 28 | Shared path helpers mirroring bash `$mydir` / `find_zfsutility_script` behavior |
| `test_paths` | 35 | Centralized path-resolution module (local and remote deployed layouts) |
| `test_pool_actions` | 15 | Pool registry add/remove/save/revert action handlers |
| `test_pool_watch` | 6 | Per-pool dataset watch window |
| `test_pools_page` | 50 | Pools tab registry UI |
| `test_profile_dialogs` | 14 | Add/Recall profile dialogs, duplicate-name overwrite handling |
| `test_profile_integration` | 3 | Concurrent profile execution: disjoint datasets, same-dataset conflict, backup+prune serialization |
| `test_profile_manager` | 20 | Profile CRUD, update, name validation, listing, existence checks, lifecycle logging, condition defaults |
| `test_profile_runner` | 71 | Backup/offsite/restore/retention profile step building, rsync failure diagnosis in headless runs |
| `test_profile_runner_concurrency` | 10 | Per-profile advisory locks, duplicate-invocation suppression, and metadata |
| `test_profile_validation` | 23 | Backup/offsite profile scope-alignment checks |
| `test_restore_page` | 15 | Restore tab UI widgets, config load/collect, auto-destination, advanced variables |
| `test_restore_runner` | 22 | Restore destination computation and zfs-send-receive parameter mapping |
| `test_retention_actions` | 23 | Retention tab action handlers |
| `test_retention_page` | 47 | Retention Policies tab UI |
| `test_runner_factory` | 4 | Runner factory wiring for page runners |
| `test_schedule_page` | 66 | Schedule page path resolution, dirty tracking, condition field, run-now child-watch handling, fatal-fallback logging, async refresh, and next-run caching |
| `test_scrub_manager` | 91 | Scrub state parsing, queue/target management, priority ordering, tick logic, systemd timers |
| `test_scrub_page` | 8 | Scrub page store schema, flicker-free refresh logic, and drag-and-drop priority ordering |
| `test_session_log` | 16 | Per-run session log helpers (create, append, trailer, size cap) |
| `test_workload_profiles` | 30 | Workload profile property filtering, profile matching, apply plan, `zfs set` command building, warnings |
| `test_zfs_capabilities` | 12 | OpenZFS release-variation gating |
| `test_zfs_diagnostics` | 8 | `gui_helpers.diagnose_dataset_busy` — detects each known cause via mocked `subprocess.run` |
| `test_zfs_lock_manager` | 6 | `zfs_lock_manager` two-node lock behavior |
| `test_zfs_repository` | 71 | `zfs_repository.py` — ZFS/zpool subprocess isolation |
| `test_zfsinfo` | 10 | Pool/dataset/snapshot info gathering with mocked `subprocess` |
| `test_zfsutilities_gui` | 44 | Main GUI window behavior |

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
```

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

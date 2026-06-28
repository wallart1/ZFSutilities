# Testing

ZFS Utilities has a two-layer test framework:

- **Bash suites** in `tests/` — test bash scripts with mock `zfs` / `zpool` overrides.
- **Python suites** in `tests/python/` — test Python modules (`backup_config.py`,
  `command_builders.py`, GUI helpers, etc.) with `unittest` and `MagicMock`.

Both layers are run automatically by `./run-tests`.

---

## Running Tests

```bash
# All suites (bash + Python)
./run-tests

# Single bash suite
./run-tests test-zfsretain

# Single Python suite
./run-tests test_backup_config

# Verbose — show every assertion
./run-tests -v

# Quiet — summary only
./run-tests -q
```

The `./run-tests` harness detects whether a name starts with `test_` (Python) or
`test-` (bash) and routes it to the correct runner.

---

## Bash Test Suites

| Suite | Tests | What it covers |
|-------|-------|----------------|
| `test-deploy-version` | 16 | Root-level script selection logic: executable files, shebang files, exclusions; validation of critical scripts; GUI and docs launcher symlinks; no production wiring |
| `test-installer-checks` | 12 | Installer safety checks: ZFS root filesystem detection with `findmnt`; desktop-user detection; home-directory symlink creation and removal |
| `test-move-vm-disk` | 8 | `move-vm-disk` helper functions: disk-key parsing, manifest add/remove |
| `test-switch-version` | 6 | Version switching, production wiring, prior-version uninstall invocation, rollback, `--uninstall`, and `--list` |
| `test-restart-iscsi-services` | 8 | VM running-state detection before iSCSI target restart |
| `test-startdocserver` | 15 | Server health checks (`curl`), PID discovery (`lsof` / `fuser` / `pgrep` / `http.server`), CWD mismatch detection, `--restart` logic |
| `test-unlock-zfs-keys` | 9 | ZFS key file loading and unlock helper functions |
| `test-zfsbuildfsarray` | 14 | Dataset array building with includes, excludes, exact-match (`=` prefix), depth limits, `startwith` / `endwith`, clone skipping |
| `test-zfscommsnap` | 6 | Common snapshot detection by GUID, most-recent / oldest modes, return codes (0, 4, 8, 16) |
| `test-zfscleanup` | 5 | Pool selection: configured pools, explicit argument, fallback to online pools, offline-pool skipping |
| `test-zfscheckagainst` | 26 | `<offsite>` placeholder expansion in Dataset and Counterpart columns, offline hold-tag verification, literal counterparts, missing-snapshot fatal error, legacy `.conf` fallback |
| `test-zfsconfig` | 13 | Pool entry parsing: strings, dicts, mixed entries, missing/empty/null names; offsite-candidate selection; checkagainst field emission and default/incomplete-entry handling |
| `test-zfs-diagnose-busy` | 8 | Diagnostic output from `zfs-diagnose-busy` — detects busy dataset causes (clones, holds, open files, sends, receives, shares, iSCSI LUNs) |
| `test-zfsdelfs` | 7 | iSCSI teardown/rebuild manifest cleanup for `zfsdelfs` |
| `test-zfsdelsnap` | 7 | Fatal error when required helper `zfs-diagnose-busy` is missing; normal operation when helper is present; `checkagainst` rc handling; regression test that the real `zfscheckagainst` sources `zfsremoveleadingqualifiers` |
| `test-zfsdelallsnaps` | 4 | Return-code behavior of `zfsdelallsnaps`: all-success returns `0`, any `delsnap` failure returns `1`, empty list returns `0` |
| `test-zfslockmanager` | 33 | Lock acquire / release, same-dataset conflicts, hierarchy conflicts, stale detection, concurrent access, path encoding. **Requires root.** |
| `test-zfsretain` | 10 | Retention policy phases: offsite monthly dedup, same-day dedup, bucket pruning with empty-snapshot preference, empty logging, retain=0 |
| `test-zfs-send-receive-dryrun` | 20 | Dry-run logging, space-check logic, resume-token decisions, `handle_commsnap_rc` paths, new-destination vs existing-destination messages, VERB-level resumable and clone logging, autoproceed prompt-once behavior |
| `test-zfssnapbuild` | 9 | Snapshot name generation, bucket logic (daily / weekly / monthly / offsite), snapfile reuse |
| `test-logging` | 4 | `log_msg` writes all messages to the session log file and ignores `msg_level` |
| `test-module-dependencies` | 1 | Static analysis: every root-level bash module call to a known module function is satisfied by a local definition, a sourced module, or `bashinit` |

Bash tests run without a real ZFS pool — commands are intercepted with bash
function overrides so every suite can execute as a normal user (root is only
needed for the lock-manager suite).

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
| `test_action_dispatch` | 18 | Page button specs, action dispatch table, and Logs/Datasets/Offsite button wiring |
| `test_app_context` | 5 | `AppContext` dataclass fields, `is_new_install`, and default repository |
| `test_backup_config` | 32 | Config load/save, defaults, pools, retention, UI state, snapshot name generation, log pruning, message level |
| `test_config_core` | 18 | Core config load/save, UI state, log/history retention, dashboard config, pruning |
| `test_checkagainst_page` | 35 | Checkagainst tab page construction, Comment column, dirty tracking, cell editing, Save/Revert/Add/Remove handlers |
| `test_feature_config` | 23 | Backup/offsite/restore config, retention, snapshot names, scrub manager, pools/checkagainst, prune label |
| `test_backup_history` | 36 | History entry schema, load/save/prune, success-rate calculation, human-size parsing, duration formatting |
| `test_backup_page` | 8 | Backup tab UI labels (including pre/post command labels), config load/collect helpers, and frame header widget support |
| `test_backup_runner` | 17 | Session log creation, subprocess output parsing, byte counting, trailer formatting, and fatal step messages |
| `test_command_builders` | 30 | Rsync/ZFS command builders, retention step descriptions, endpoint parsing, dry-run assignments, host detection |
| `test_config_migrations` | 28 | JSON config migration chain (v1 → v15), idempotency, missing-migration handling |
| `test_cron_manager` | 17 | Cron expression formatting, next-run calculation, profile scheduling, cron file generation |
| `test_dashboard_page` | 107 | Dashboard layout, task handling, pool/VM/scrub/history queries, warning indicators |
| `test_docs_integrity` | 11 | MkDocs nav consistency, orphan-file detection, internal link resolution, anchor existence, hook importability |
| `test_docs_viewer` | 1 | Standalone documentation viewer launcher (`docs_viewer.main()`) |
| `test_gui_infrastructure` | 95 | GTK mock setup, `gi.repository` patching, module imports without a display server, docs viewer HTTP server, zoom/navigation/state persistence, anchor scrolling, tree expansion helpers, TreeSearch freeze/thaw, clear-button status-bar reset |
| `test_legacy_retention` | 7 | Legacy `zfsretainpol-*` file parsing, malformed-line handling, JSON config import |
| `test_logging_config` | 20 | `log_msg` sink/file behavior, session log environment helpers, and viewer level helpers |
| `test_main` | 41 | GUI entry point: PID-file single-instance, auto-replace, transient wait dialog, event pumping, retry-after-remote registration, pkexec logic, X11 window visibility for stuck-instance detection |
| `test_page_runners` | 6 | Backup/offsite/restore run handlers, session log preparation, auto-destination, pull-step activation |
| `test_profile_manager` | 15 | Profile CRUD, name validation, duplicate detection, override string generation |
| `test_profile_runner` | 45 | Step building, pool selection, rsync/ZFS command generation, error handling, dataset encryption detection, dry-run profile execution |
| `test_restore_runner` | 11 | Restore destination computation and zfs-send-receive parameter mapping |
| `test_retention_page` | 22 | Retention tab: prune-label persistence, dirty detection, multi-pool Save/Revert, profile round-trip, fresh-install cleanup, prune-list filtering |
| `test_runner_factory` | 4 | `RunnerFactory` creates `BackupRunner` instances with shared callbacks |
| `test_schedule_page` | 15 | Schedule page path resolution for deployed vs repo layouts; dirty tracking and multi-row Save/Revert for active toggles and cron edits; dry-run flag display in profile summary |
| `test_scrub_manager` | 24 | Scrub state parsing, queue/target management, tick logic, systemd timers |
| `test_scrub_page` | 5 | Scrub page store schema and flicker-free refresh logic |
| `test_zfs_diagnostics` | 8 | `gui_helpers.diagnose_dataset_busy` — detects each known cause via mocked `subprocess.run` |
| `test_datasets_page` | 17 | Datasets tab UI: page construction, pool refresh, button sensitivity, and the Expand Selected action |
| `test_datasets_tree` | 6 | Datasets tree lazy loading: row expansion, full-name building, exact-dataset snapshot filtering |
| `test_zfsinfo` | 10 | Pool/dataset/snapshot parsing, summary counting, CLI output formatting |
| `test_dataset_actions` | 6 | Dataset destruction routed through `BackupRunner`: `BashStep` building, runner start/callback, missing/busy runner, cancel handling |
| `test_logs_page` | 33 | Log list scanning, filtering, deletion, status parsing, tail-only viewer for large files, Load Full Log confirmation, and column-header label tooltips |
| `test_zfs_repository` | 25 | `ZfsRepository` pool/dataset/snapshot/hold parsing and write-method success/failure |
| `test_zfsutilities_gui` | 17 | Window behavior: peer-version check, dry-run toggle, dataset-runner creation, stdin forwarding, info-panel level filtering, Restore tab destination refresh |

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
| `temp_config_dir()` | Overrides `CONFIG_PATH`, `CRON_FILE`, `SNAPFILE`, and `OFFSITE_SNAPFILE` to a temp directory |
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
    m.add_zpool_list([
        {"name": "tank", "health": "ONLINE"}
    ])
    m.add_zfs_list([
        {"name": "tank/data", "used": "10G"}
    ])
    # ... code that calls subprocess.run(...) ...
    self.assertEqual(len(m.calls), 2)
```

---

## Tips and Gotchas

### Bash

* **Log redirection** — `log_msg` output is redirected to a per-test log file by
`test-lib.sh` so the harness stays quiet.  Tests that need to assert on
`log_msg` output should read the file returned by `get_test_log_file()` (or
use `get_stderr_log()` from `test-zfs-send-receive-dryrun`).
* **Root check** — [rootcheck](../commands-and-modules/modules.md#rootcheck) is mocked to a no-op.  Suites that require root
(e.g. `test-zfslockmanager`) should check `$EUID` and call `test_skip` when
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

* **Config isolation** — Always wrap config-mutating tests in
`temp_config_dir()` so they do not touch the real `/root/.config/zfsutilities.json`.
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

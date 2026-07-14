# AGENTS.md

This file provides guidance to AI coding assistants when working with code in this repository.

## Terminal Output

All responses in the terminal window must keep lines **10 characters shorter**
than the terminal width. This prevents missing characters at the end of
response lines. This rule applies to every response, every session.

For this environment the terminal has been calibrated to approximately
**95 columns**, so the effective maximum line length is **85 characters**.
Future sessions should target 85 characters per line unless the user
recalibrates the width.

#

# Development Agent

You are a meticulous and expert coding agent. For every task:

1. Enter plan mode and analyze the codebase. You do not need to ask permission to enter plan mode.
2. Propose a clear implementation plan with steps.
3. Wait for user approval or revision.
4. Execute only the approved plan.
5. Always test and debug your work after executing the plan and before responding.
6. Use concise, professional language.
7. Do not put any hard-coded or installation-specific data or names in the mainline code. These must be entered by the user at runtime using text-based and GUI dialogs and will usually be saved in a saved configuration file.
8. Look for and correct any deprecated code and features. Do not implement any deprecated code or features.
9. Don't be lazy. Take the approach that is correct even though it may be more difficult to implement.

## Hard Rules

- **Git mutations require explicit confirmation, every time.** Before running
  `git commit`, `git push`, `git reset`, `git rebase`, or any other git
  mutation, ask the user for confirmation. Do not skip this step even if the
  user previously said "commit it," "bump the version," or similar.
- Do not automatically bump the version.
- Do not automatically commit.
- You may not modify anything except what is in the current working directory and its subdirectories.
- You may see uncommitted changed files that you did not change. Do not be alarmed by this. They are either my manual changes or were changed by Kimi in an earlier session. These changes will be included when I instruct you to perform a commit.
- Do not automatically update the VERSION file unless I specifically tell you to.
- Do not automatically update the change log unless I specifically tell you to.
- Do not try to use the deploy-version script.
- Do not try to use the switch-version script.
- Do not attempt to do what the deploy-version or switch-version scripts do.
- Please reread AGENTS.md every 3 prompts for rules to closely follow during this session.

## Project Overview

ZFS Utilities is a collection of bash scripts for managing ZFS backup, snapshot, and retention operations across multiple ZFS pools. All scripts require root privileges and operate on live ZFS datasets.

## Running Scripts

All scripts must be run as root:

```bash
sudo scriptname
```

Scripts are deployed to `/usr/local/lib/zfsutilities/current/bin/` and made
available via the `PATH` environment variable (set in `/etc/profile.d/` and
`/etc/sudoers.d/`). You can still run `./scriptname` directly from the repo
checkout for development.

## Architecture

### Script Sourcing Pattern

All scripts follow this initialization pattern:

```bash
source ~/bashinit
bashinit
source $mydir/rootcheck
rootcheck
```

- `bashinit` is wired as a symlink at `/root/bashinit` →
  `/usr/local/lib/zfsutilities/current/bin/bashinit` by `switch-version` (tracks
  the active version)
- `$mydir` is set by `bashinit` to the calling script's directory
- Function scripts are sourced (not executed) and call functions by name

### Core Components

**`zfs-send-receive`** - Main workhorse for copying ZFS data. Key parameters:

- `$sourcefs` - Source dataset
- `$destfs` - Destination pool/dataset
- `$sourcefsremovequalifiers` - Number of leading path segments to strip from source when constructing destination path
- `$doincrementals` - 'Y' for incremental, 'N' for full copy
- `$includes` / `$excludes` - Arrays for dataset filtering
- `$autoproceed` - 'Y' to suppress interactive prompts

**`zfsbuildfsarray`** - Builds filtered dataset arrays. Uses:

- `$includes` - Array of substrings to include (prefix with `=` for exact match)
- `$excludes` - Array of substrings to exclude
- `$startwith` - Skip datasets before this match
- `$depth` - Limit recursion depth
- `$bottomup` - 'Y' for descending sort

**`zfsretain`** - Applies retention policies in three phases:

1. For `@offsite` snapshots, remove all but the most recent per month per dataset
2. Remove same-day duplicate snapshots
3. Prune by bucket retention counts (prefers deleting empty snapshots with `written=0`; protects most recent snapshot as incremental base)

Snapshots with label `clone` or bucket `c` are skipped entirely in all phases.

### Python ZFS Repository

All direct `zfs`/`zpool` subprocess calls from the GTK/Python GUI layer are
isolated in `07 GTK + Python/zfs_repository.py` via the `ZfsRepository` class.
GUI pages and action handlers receive the repository from `app.ctx.zfs_repository`
(or fall back to `get_default_repository()`). This keeps subprocess mocking
straightforward: Python tests patch `subprocess.run` and the repository methods
pass the mocked calls through.

### Snapshot Naming Convention

Format: `@<label>-<yyyy-mm-dd>T<hh:mm><tz>-<bucket>`

Buckets: `d` (daily), `w` (weekly), `m` (monthly), `s` (offsite), `c` (clone origin)

### Retention Policies

Live per-pool retention policies are stored in the shared JSON config at
`/root/.config/zfsutilities.json` under the `retention` key. Each pool has a
list of bucket dicts:

```json
"retention": {
  "default": [
    {"name": "d", "retain": 3, "minage": 0},
    {"name": "w", "retain": 2, "minage": 0},
    {"name": "m", "retain": 2, "minage": 0},
    {"name": "s", "retain": 4, "minage": 65}
  ]
}
```

Legacy project-root files `zfsretainpol-<poolname>` or `zfsretainpol-default`
are imported once into the JSON config and then ignored. On a new install, only
`zfsretainpol-default` is kept; any pool-specific legacy policies are cleared
so the Retention tab starts with a single default policy. The installers
(`install-single-node` and `install-two-node`) initialize the JSON config
retention section with only the `default` policy when the config does not yet
exist, leaving any existing user-entered per-pool policies untouched. The
`deploy-version` script only ships `zfsretainpol-default` to the deployed `bin/`
directory; pool-specific sample policy files are excluded so they cannot be
re-imported later. Use the GUI Retention tab or `backup_config.get_retention` /
`save_retention` to add or edit per-pool policies. The Prune list only shows
online pools that have an explicit retention policy; pools without a policy are
not pruned. When `zfscleanup` is run without a specific pool argument, it
iterates over the pools registered in the JSON config (`config.pools`). If that
list is empty, it falls back to all online pools so retention is not silently
skipped.

### Parameter Override System

`zfsoverrides` enables runtime parameter changes via command line:

```bash
./zfsdailybackup "backup_NVME1='N'; prune='N'"
```

## Key Directories

- Root directory: Active utilities and scripts
- `06 Docs/` - Documentation manuals (source)
- `07 GTK + Python/` - GTK/Python GUI
- `08 Two-node/` - Two-node / iSCSI utilities
- `09 ZFS clone support/` - VM clone lifecycle scripts
- `10 Installers/` - Single-node and two-node installers
- `Cache-warm/` - ZFS ARC cache warming helpers
- `tests/` - Bash and Python test suites
- `Watchall/` - Monitoring helpers

## Pool Names Referenced

Primary pools: `threeamigos`, `fivebays`, `NVME1`, `temp`
Offsite pools: `z22tb`, `z40tb`

## System Dependencies

- `pv` - Progress visualization for large transfers
- `zfsutils-linux` - ZFS userspace utilities
- `rsync` - File synchronization for pull operations

## Common Workflows

**Daily backup** (`zfsdailybackup`):

1. Pull rsync backups from remote hosts
2. Snapshot and copy `threeamigos/proxmox` → `fivebays`
3. Snapshot and copy `NVME1` → `fivebays`
4. Apply retention policies

**Two-step restore** (`zfsfullcopy` or manual):

1. Full copy with `doincrementals='N'`, `commsnap_mostrecent='OLDEST'`
2. Incremental copy with `doincrementals='Y'`, `dointermediates='Y'`

**Clone handling:** Cloned datasets are backed up as regular datasets.
`zfs-send-receive` treats them as independent datasets because ZFS clones cannot be
incrementally replicated while preserving their clone relationship. This is the correct
and expected behavior. Do not enable `$skipclones` in production backup scripts — it
causes data loss.

## Important Variables

- `$nextsnap` - New snapshot name (generated by `zfssnapbuild`)
- `$force='Y'` - Force operations (destroy destination before full copy)
- `$releaseholds='Y'` - Auto-release holds when deleting snapshots
- `$receive_s_option='s'` - Enable resumable receives
- `$resumablethreshold` - Size threshold for resumable transfers (default 50GB)

## bashinit Helper Functions

The `bashinit` script provides these functions:

- `bashinit` - Sets `$mydir` to the calling script's directory; auto-creates a session log file for directly-executed scripts
- `log_msg "message"` - Logs with file:line prefix to stderr and to `$ZFSUTILITIES_LOG_FILE` if set. All messages are always emitted; filtering by message level is done in the GUI log viewers.
- `ask_yn "prompt"` - Prompts for y/n with input validation; returns 0 for yes, 1 for no
- `calledbybash` - Returns 0 if script was executed directly (not sourced)

**Deployment**: `deploy-version` places software under
`/usr/local/lib/zfsutilities/versions/<version>/` without touching active
production. `switch-version` creates and updates production wiring, including
`/root/bashinit`, `PATH` configuration, library symlinks, and desktop
shortcuts. When `switch-version` changes the active version, `/root/bashinit`
tracks automatically — no manual copying needed.

For development (running scripts from the repo without `sudo`), keep a local copy:

```bash
cp bashinit ~
```

## zfsscruball Pause/Resume

`zfsscruball` supports pause and resume:

- `./zfsscruball` or `./zfsscruball start` - Start fresh scrub of all pools
- `./zfsscruball pause` - Pause all running scrubs
- `./zfsscruball resume` - Resume paused scrubs, continue with remaining, skip completed

State is tracked in `/tmp/zfsscruball.state` during a run.

## Versioned Deployment

Scripts are installed to `/usr/local/lib/zfsutilities/versions/<version>/` and activated
via symlink. This allows instant rollback.

- **`deploy-version [version]`** — Deploy current repo state as a new version (run from repo root)
- **`switch-version <version>|previous|--list|--uninstall`** — Wire a deployed version into active production, roll back, list versions, or remove a version's wiring
- **`uninstall-version <version>`** — Remove an old version

Directory structure:

```
/usr/local/lib/zfsutilities/versions/v1.1.0/bin/   # scripts
/usr/local/lib/zfsutilities/versions/v1.1.0/lib/   # libraries
/usr/local/lib/zfsutilities/current -> versions/v1.1.0
/usr/local/lib/zfsutilities/bin -> current/bin     # PATH entry
```

Both VMs must be stopped before switching versions if storage scripts are in use.

### Two-Node Startup Version Check

In a two-node configuration, the GUI checks the peer node's deployed version at
startup (`zfsutilities_gui.py` → `dashboard_page.py`). It resolves the peer host
from `/etc/zfsutilities-node.conf` (fallback `/etc/two-node.conf`), reads the
peer's `/usr/local/lib/zfsutilities/current/VERSION` via SSH as `root`, and logs
a warning if the versions differ or the peer is unreachable. The check runs in a
background thread so GUI startup is not delayed.

## Test Framework

An automated bash test harness lives in `tests/`.

### Running Tests

```bash
# Run all suites
./run-tests

# Run a specific suite
./run-tests test-zfsretain

# Verbose output (show every test)
./run-tests -v

# Quiet (summary only)
./run-tests -q

# Large test output
If, when running the tests, the output is truncated, then break up the tests so that their outputs are not truncated. Or, run tests in a way that reduces their output volume without reducing accuracy.
```

### Test Suite Files

| Suite                          | Tests | Description                                                                                                   |
| ------------------------------ | ----- | ------------------------------------------------------------------------------------------------------------- |
| `test-deploy-version`          | 20    | Root-level script selection, exclusions, retention-policy file filtering, critical-script validation, and no production wiring |
| `test-installer-checks`        | 12    | Installer prerequisite checks and desktop-launcher helper functions                                           |
| `test-installer-retention`     | 3     | Installer default retention profile initialization and preservation of existing user profiles                 |
| `test-move-vm-disk`            | 8     | `move-vm-disk` helper functions: disk-key parsing, manifest add/remove                                        |
| `test-restart-iscsi-services`  | 8     | VM running-state detection before iSCSI target restart                                                        |
| `test-startdocserver`          | 15    | Server health checks, PID discovery, CWD mismatch, restart logic                                              |
| `test-switch-version`          | 6     | Version switching, production wiring, prior-version uninstall, rollback, `--uninstall`, and `--list`          |
| `test-unlock-zfs-keys`         | 9     | ZFS key file loading and unlock helper functions                                                              |
| `test-zfsbuildfsarray`         | 14    | Dataset array building with includes/excludes/depth/sorting                                                   |
| `test-zfscommsnap`             | 6     | Common snapshot detection by GUID, most-recent/oldest modes                                                   |
| `test-zfscleanup`              | 5     | Pool selection: config pools, explicit argument, fallback to online pools, offline skip                       |
| `test-zfs-diagnose-busy`       | 8     | Diagnostic output from `zfs-diagnose-busy` — busy dataset causes                                              |
| `test-zfsdelfs`                | 7     | iSCSI teardown/rebuild manifest cleanup for `zfsdelfs`                                                        |
| `test-zfsdelsnap`              | 7     | Snapshot deletion safety checks, hold release, and `zfscheckagainst` dependency sourcing                      |
| `test-zfslockmanager`          | 35    | Lock acquire/release, conflict detection, hierarchy, stale cleanup, headless abort, wait/retry, multi-lock acquisition |
| `test-zfsretain`               | 10    | Retention policy phases (offsite dedup, same-day dedup, oldest-first bucket pruning, empty logging, retain=0) |
| `test-zfs-send-receive-dryrun` | 27    | Dry-run logging, space checks, resume-token helpers, clone messages, pv quiet in headless mode                |
| `test-zfssnapbuild`            | 9     | Snapshot name generation, bucket logic, snapfile handling                                                     |
| `test-module-dependencies`     | 1     | Static analysis: root-level bash modules source the modules whose functions they call                         |

### Writing New Tests

1. Create `tests/test-<scriptname>` (executable, no file extension).
2. Source `test-lib.sh` at the top.
3. Define test functions that call `test_start`, `assert_equals`, `assert_rc`, etc.
4. Call `test_summary` at the end.

```bash
#!/usr/bin/bash
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/test-lib.sh"

test_example() {
    test_start "Descriptive test name"
    assert_equals "expected" "$actual"
}

test_example
```

### Mock Infrastructure

`test-lib.sh` provides mock overrides for `zfs`, `zpool`, `delsnap`, `ask_yn`, and `date`.  Scripts are tested by sourcing them into the same shell so function overrides intercept `$(zfs ...)` and pipeline invocations.  No `PATH` manipulation or external mock binaries are used.

Assertion helpers:

- `assert_equals expected actual` — pass if strings match
- `assert_contains haystack needle` — pass if haystack contains needle
- `assert_rc expected actual` — pass if return codes match
- `assert_array_len expected "${arr[@]}"` — pass if array length matches

Key mock state variables:

- `_mock_zfs_fs_list` — dataset listing for `zfs list`
- `_mock_zfs_snap_lists[<dataset>]` — snapshot listing per dataset
- `_mock_zfs_guid_lists[<dataset>]` — GUID list per dataset (for `zfs list -o guid`)
- `_mock_zfs_props[<dataset>:<property>]` — property values for `zfs get`
- `_mock_zfs_snaps[<snapshot>]` — snapshot existence for `zfs list -t snapshot`
- `_mock_zfs_datasets[<dataset>]` — dataset existence for `zfs list`
- `_mock_zfs_send_size` — size returned by `zfs send -nP`
- `_mock_zpool_list` — output for `zpool list -Ho name` and `zpool list -H -o name`

### Important Notes

- Test output is redirected to a per-test log file by `test-lib.sh` so the test
  harness stays quiet. Tests that need to assert on `log_msg` output should read
  the file returned by `get_test_log_file()` or use `get_stderr_log()` from
  `test-zfs-send-receive-dryrun`.
- `rootcheck` is mocked to a no-op so tests run as non-root.  Tests that require root (e.g. `test-zfslockmanager`) check `$EUID` and emit `SKIP` when non-root.
- The `zfs` mock handles combined short options (e.g. `-Hp`) and per-dataset snapshot lists.
- Inner functions defined inside a function (e.g. `send-receive`) become available for direct testing **after** the outer function has been executed once.

### Python Tests

A Python test harness lives in `tests/python/` and uses Python's built-in `unittest` module. The only optional dependency is `pyyaml`, required by `test_docs_integrity` for parsing `mkdocs.yml`.

#### Running Python Tests

```bash
# Run all Python test suites
./tests/run-python-tests

# Run a specific Python suite
./tests/run-python-tests test_backup_config

# Run via the unified harness (bash + Python)
./tests/run-tests
./tests/run-tests test_backup_config
./tests/run-tests test-zfsretain test_backup_config
```

#### Test Suite Files

| Suite                     | Tests | Description                                                                                                    |
| ------------------------- | ----- | -------------------------------------------------------------------------------------------------------------- |
| `test_action_dispatch`    | 8     | Page button specs, action dispatch table, and Logs tab button wiring                                           |
| `test_backup_config`      | 32    | Config load/save, defaults, pools, retention, UI state, snapshot name generation, log pruning, message level   |
| `test_backup_history`     | 33    | History entry schema, load/save/prune, success-rate calculation, human-size parsing, duration formatting       |
| `test_backup_page`        | 8     | Backup tab UI labels (including pre/post command labels), config load/collect helpers, and frame header widget support |
| `test_backup_runner`      | 19    | Session log creation, subprocess output parsing, byte counting, trailer formatting, fatal step messages, and log size cap |
| `test_command_builders`   | 31    | Rsync/ZFS command builders, retention step descriptions, endpoint parsing, dry-run assignments, host detection |
| `test_config_migrations`  | 17    | Schema migrations 1→12, idempotency, missing migration errors                                                  |
| `test_cron_manager`       | 17    | Cron line generation, human-readable interpretation, next-run computation                                      |
| `test_dashboard_page`     | 107   | Dashboard layout, task handling, pool/VM/scrub/history queries, warning indicators                             |
| `test_docs_integrity`     | 11    | MkDocs nav consistency, orphan-file detection, internal link resolution, anchor existence, hook importability  |
| `test_gui_infrastructure` | 81    | GTK mock setup, GUI module imports, docs viewer zoom/navigation/state persistence, anchor scrolling            |
| `test_installer_retention` | 5     | Installer retention profile initialization: default-only on new install and preservation of existing profiles |
| `test_legacy_retention`   | 7     | Legacy `zfsretainpol-*` file parsing and pool scanning                                                         |
| `test_logging_config`     | 24    | Message levels, GUI sink, session log env helpers, and session log truncation                                  |
| `test_logs_page`          | 33    | Log list scanning, filtering, deletion, status parsing, tail-only viewer for large files, and column-header label tooltips |
| `test_main`               | 41    | GUI entry point: PID-file single-instance, auto-replace, transient wait dialog, event pumping, retry-after-remote registration, pkexec logic |
| `test_page_runners`       | 6     | Backup/offsite/restore run handlers, session log preparation, auto-destination, pull-step activation           |
| `test_profile_manager`    | 18    | Profile CRUD, update, name validation, listing, existence checks, lifecycle logging                            |
| `test_profile_dialogs`    | 11    | Add/Recall profile dialogs, duplicate-name overwrite handling                                                  |
| `test_profile_runner`     | 43    | Backup/offsite/restore/retention profile step building                                                         |
| `test_profile_runner_concurrency` | 7 | Per-profile advisory locks, duplicate-invocation suppression, and metadata                                  |
| `test_profile_integration` | 3    | Concurrent profile execution: disjoint datasets, same-dataset conflict, backup+prune serialization             |
| `test_restore_runner`     | 11    | Restore destination computation and zfs-send-receive parameter mapping                                         |
| `test_schedule_page`      | 35    | Schedule page path resolution, dirty tracking, run-now child-watch handling, and fatal-fallback logging          |
| `test_scrub_manager`      | 24    | Scrub state parsing, queue/target management, tick logic, systemd timers                                       |
| `test_scrub_page`         | 5     | Scrub page store schema and flicker-free refresh logic                                                         |
| `test_zfs_diagnostics`    | 8     | `gui_helpers.diagnose_dataset_busy` — detects each known cause via mocked `subprocess.run`                     |
| `test_zfsinfo`            | 10    | Pool/dataset/snapshot info gathering with mocked `subprocess`                                                  |

#### Writing New Python Tests

1. Create `tests/python/test_<modulename>.py`.

2. Import helpers from `test_support`:

   ```python
   from test_support import temp_config_dir, mock_subprocess, capture_logs, mock_gtk
   ```

3. Subclass `unittest.TestCase` and define `test_*` methods.

#### Mock Infrastructure (`test_support.py`)

- **`temp_config_dir()`** — Overrides `CONFIG_PATH`, `CRON_FILE`, `SNAPFILE`, and `OFFSITE_SNAPFILE` to a temporary directory.
- **`mock_subprocess()`** — Patches `subprocess.run`. Provides `add_zpool_list()`, `add_zfs_list()`, `add_zfs_snaps()`, `add_zfs_prop()`, and `set_command_handler()`. The returned `MockSubprocess` instance records every call in `m.calls`.
- **`capture_logs()`** — Captures all `log_msg` output to a list.
- **`capture_stderr()`** — Captures `sys.stderr` to a `StringIO` buffer.
- **`mock_gtk()`** — Patches `gi.repository` with mock objects so GUI modules import without a display server.
- **`check_pyyaml()`** — Skips the current test if `pyyaml` is not installed.

#### Important Notes

- `msg_level` defaults to `INFO` in Python tests (unlike bash tests where it is `FATAL`).
- GUI tests mock GTK at the module level; they verify import and logic but do not render widgets.
- Subprocess mocks handle both `shell=True` (string commands) and `shell=False` (list commands).

## Coding Standards

### Bash

This project uses **bash** (not sh). Follow these conventions:

- **Use `set -euo pipefail`** at the start of scripts for strict error handling.
- **Indent with 4 spaces**, never tabs.
- **Limit line length to 100 characters**. Break long commands with backslashes, aligning continuations under the first argument.
- **Quote variables** using `"${var}"` to prevent word splitting and globbing.
- **Prefer `[[ ]]`** over `[ ]` for conditionals.
- **Use `$(...)`** for command substitution, never backticks.
- **Use long option names** when clarity is needed (`rm --recursive --force`).
- **Shebang**: `#!/usr/bin/bash` for root utilities, `#!/usr/bin/env bash` only when portability across systems is required.
- **No file extensions** on executable scripts.
- **Variable naming**: lowercase for local/script variables (`my_var`), uppercase for environment variables (`PATH`).
- **Function naming**: lowercase with underscores (`start_server`, `cleanup_temp_files`).
- **Declare `local` variables** inside functions.
  - **Exception**: output variables that callers read (like `$fsarray`) are intentionally global and should **not** be declared `local`.
- **Apply Single Responsibility Principle**: each function should do one thing.

**Project-specific patterns:**

- Start scripts with the standard initialization:

  ```bash
  source ~/bashinit
  bashinit
  source $mydir/rootcheck
  rootcheck
  ```

- Never use bare `exit` or `return`. For fatal errors, source `bashfatal` at the
  point of exit. For non-fatal returns in dual-mode scripts, source `bashreturn`.

- Use `usage()` for argument errors, showing help and exiting.

- Use `bashreturn` (source it) when a script may be called either directly or sourced, and you need to return to the caller properly.

- Use the dual-mode guard for scripts that define reusable functions:

  ```bash
  if calledbybash; then myfunc "$@"; fi
  ```

- Use `log_msg "message"` (from bashinit) for consistent logging when available.

- **Do not `export -f log_msg`** into subshells (e.g., `xargs` or `parallel`).
  `log_msg` depends on internal helper functions and an associative array that
  `export -f` does not propagate. Instead, `source ~/bashinit` inside each
  subshell so `log_msg` and its dependencies are fully initialized.

- Use `trap cleanup EXIT` for cleanup of temporary files.

- Start each script with a header comment describing purpose, usage, arguments/globals, and return values.

- Any code path that creates a ZFS snapshot must hold a `w` lock on the target
  dataset (via `zfslockmanager` or `zfs_lock_manager`) before calling
  `zfs snapshot`.  This prevents concurrent jobs from creating out-of-sequence
  snapshots that would force an incremental receive with `-F` to roll back.

- Use arrays for include/exclude lists: `includes=('proxmox')`, `excludes=('temp/temp')`; empty arrays are `includes=()`.

### Python

The GTK GUI code in `07 GTK + Python/` follows standard Python conventions:

- **PEP 8**: 4 spaces, 100-character line limit.
- **Naming**: `lowercase_with_underscores` for variables/functions, `CapWords` for classes, `UPPERCASE_WITH_UNDERSCORES` for constants.
- **Imports**: One per line, grouped as standard library, third-party, local modules.
- **Docstrings**: Triple quotes (`"""`) for modules, classes, and functions.
- **Avoid mutable defaults** in function parameters.
- **Comparisons to `None`**: Use `is None` / `is not None`.

**Logging:**

All Python modules import `log_msg` from `backup_config` and use it for all output:

```python
from backup_config import log_msg

log_msg("INFO: backup started")
log_msg("WARN: something unexpected")
log_msg("DEBUG: variable =", value)
```

- Priority levels: `DEBUG` < `VERB` < `INFO` < `WARN` < `FATAL` < none
- Messages without a recognized `LEVEL:` prefix are always emitted
- Default threshold is `INFO` (controlled by `msg_level` environment variable)
- In the GUI, messages route to the info panel; in CLI mode they go to `sys.stderr`
- When `ZFSUTILITIES_LOG_FILE` is set, both bash and Python `log_msg` append the
  formatted message to that file. All messages are written regardless of message
  level; the GUI log viewers filter what is displayed.
- `ZFSUTILITIES_LOG_INHERIT=Y` is passed to bash subprocesses so they do not
  create a competing session log; the Python runner remains the single writer.
- Each line is prefixed with `file:line:` via `inspect`

---

## Recent Session Notes (2026-07-11)

- Added `repair-iscsi-luns` to diagnose and repair missing iSCSI LUN exports on
  the storage host. It discovers all VM zvols in configured pools, ensures each
  has a block backstore and LUN mapping while preserving existing LUN indexes,
  regenerates `expected-backstores.txt`, saves the target config, and always
  rescans the compute host. Use `--dry-run` to preview changes and
  `--force-relogin` to re-log iSCSI sessions when a rescan alone does not reveal
  all LUNs.
- Fixed the Dashboard "Fix this" iSCSI button: it now runs `repair-iscsi-luns`
  (instead of `iscsi-restore-luns`) and displays the command output.
- Hardened `safe-iscsi-save`: after a successful save it regenerates
  `expected-backstores.txt` from the current targetcli backstore list so the
  manifest stays accurate when LUNs are moved or added.
- Updated `08 Two-node/install-scripts` to deploy `repair-iscsi-luns` on the
  storage host.

## Recent Session Notes (2026-07-03)

- Fixed silent scheduled-profile skips: `cron_manager.py` no longer wraps
  `profile_runner.py` with a `flock -n -E 0` cron command; the runner already
  acquires its own advisory lock, and the cron wrapper caused double-locking
  that made every cron invocation exit silently with no session log. Cron
  output is now appended to `/var/log/zfsutilities/cron.log` instead of
  `/dev/null` so pre-log errors remain visible. `profile_runner.py` creates
  its session log before acquiring the profile lock, so "already running"
  skips and "profile not found" failures are recorded in the session log.
- Fixed resumable ZFS receive: `zfs-send-receive::do_transfer()` no longer
  appends `"$fs$nextsnap"` when `$sendopts` contains `-t <resume-token>`,
  because the token already encodes the snapshot. Previously this produced a
  `too many arguments` error from `zfs send` and aborted the resume.

## Recent Session Notes (2026-06-30)

- Pause scrubs during Backup/Offsite/Restore: Added a per-tab `pause_scrubs`
  option (default disabled) on the Backup, Offsite, and Restore tabs. When
  enabled, scrubs on the source and destination pools are paused immediately
  before each send/receive step and resumed after the step finishes. The option
  is stored in the JSON config under each tab's section and also applies to
  headless profile/cron runs via `profile_runner.py`. New helpers live in
  `scrub_manager.py` (`pause_scrubs_for_pools`, `resume_scrubs_for_pools`,
  `attach_step_scrub_callbacks`); `BashStep` gained optional `pre_callback` and
  `post_callback` hooks used by `backup_runner.py` and `profile_runner.py`.
  Already-paused scrubs are left untouched.

## Recent Session Notes (2026-06-29)

- Phase 4 file-locking: Added `07 GTK + Python/file_locking.py` to serialize
  access to shared JSON/state files (`/root/.config/zfsutilities.json`,
  `zfsutilities-history.json`, `scrub_state.json`, and the session-log index).
  Python modules use `fcntl.flock` context managers; the bash `zfsconfig`
  helper uses the system `flock` command on the same lock files. Lock paths are
  overridable via environment variables for testing. `add_history_entry()` now
  performs its read-modify-write under a single exclusive lock so concurrent
  runners cannot lose history entries.
- Phase 5 profile-level concurrency: Added per-profile advisory locks in
  `profile_runner.py` under `/run/lock/zfs/profiles/<profile>.lock`. A second
  invocation of the same profile exits 0 without running, so cron does not mail
  on the expected duplicate-run case. The Dashboard Running Tasks list now shows
  "Profile" entries and warns when a profile is active. The lock directory is
  overridable via `ZFSUTILITIES_PROFILE_LOCK_DIR` for testing.

## Recent Session Notes (2026-06-29)

- Phase 6 integration testing and documentation: Added
  `tests/python/test_profile_integration.py`, which runs concurrent profiles in
  separate subprocesses and verifies that disjoint datasets run in parallel,
  same-dataset conflicts fail safely, and backup+prune operations serialize.
  Created `06 Docs/docs/user-guide/profiles.md` to explain profiles, scheduling,
  concurrent execution, and conflict resolution. Updated
  `06 Docs/docs/developer-guide/concurrency-collisions.md` to mark the
  Phase 1/5 gaps (two prunes on the same pool, two restores to the same
  destination, scrub path coordination, and headless profile overlap) as
  resolved.

## Recent Session Notes (2026-06-27)

- Session log defenses: Added a 1 GB size cap with 100 MB tail + 64 KB start
  retention to prevent runaway backup/offsite logs from filling disk. The cap is
  enforced from the Python runners (`backup_runner.py`, `profile_runner.py`) so
  it also bounds output written by inherited bash subprocesses. When a log is
  truncated, its persistent index entry is reset so the Logs tab rescans the
  smaller file.
- Logs tab viewer: Files larger than 1 MB are now opened tail-first; a
  "Load Full Log" button with a confirmation prompt allows reading the entire
  file when needed. The Size column was renamed to "Log Size" and column
  tooltips were added to clarify the difference between log size and transfer
  bytes.

## Recent Session Notes (2026-06-25)

- `zfscheckagainst`: The `<offsite>` placeholder may now appear anywhere in the
  Dataset *or* Counterpart column of the fss table. Every occurrence is replaced
  at run-time with each configured offsite-candidate pool name; rows expanded
  from an `<offsite>` dataset skip the meaningless self-check against the source
  pool. The GUI Checkagainst tab notes and the documentation were updated
  accordingly; `tests/test-zfscheckagainst` was expanded to cover the new cases.

## Recent Session Notes (2026-03-13)

- `zfsretain`: Phase 2 now deletes the oldest snapshots first when a bucket overflows; empty snapshots (`written=0`) are still logged as `(empty)` but no longer receive deletion preference. Most recent snapshot in each bucket is always protected as incremental base
- `zfsgetsnapage`: New utility — returns snapshot age in days
- iSCSI boot-config fix: `saveconfig-boot.json` strips encrypted backstores for safe boot
- Encrypted zvol lifecycle: `/etc/iscsi-encrypted-luns.conf` is single source of truth; `new-vm-disk --encrypted` and `remove-vm-disk` maintain it
- Python `log_msg()`: All Python scripts now use priority-filtered logging via `backup_config.log_msg()`, mirroring the bash `log_msg()` behavior with `file:line:` prefixes and GUI sink support

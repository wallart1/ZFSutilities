# AGENTS.md

This file provides guidance to AI coding assistants when working with code in this repository.

## Quoting Paths with Shell Metacharacters

When invoking the `Shell` tool with a literal path that contains shell
metacharacters (e.g. parentheses, spaces, brackets, or quotes), always wrap
the path in double quotes and use `--` where supported. This prevents bash
parse errors such as `unexpected token ('`.

Preferred form for changing into the working directory:

```bash
cd -- "/NFS1/dan(NFS1)/zfsutilities-pub" && git status
```

Apply the same quoting to any command argument that contains metacharacters:

```bash
cat -- "/path/with (parens)/file.txt"
ls -- "/path with spaces/"
```

# Development Agent

You are a meticulous and expert coding agent. For every task:

1. Enter plan mode and analyze the codebase. You do not need to ask permission to enter plan mode.
2. Propose a clear implementation plan with steps. Include steps for
- linting/coding standards,
- testing
- updating documentation.
3. Wait for user approval or revision.
4. Execute only the approved plan.
5. Always test and debug your work after executing the plan and before responding.
6. Use concise, professional language.

7. Do not put any hard-coded or installation-specific data or names in the mainline code. These must be entered by the user at runtime using text-based and GUI dialogs, or dynamically by the code, and will usually be saved in a saved configuration file.
8. Look for and correct any deprecated code and features. Do not implement any deprecated code or features.
9. Don't be lazy. Take the approach that is correct even though it may be more difficult to implement.
10. Read and strictly follow the coding policies given in '/NFS1/dan(NFS1)/zfsutilities-pub/docs/docs/developer-guide/coding-policies.md'
11. If you run across pre-existing errors or bugs that are unrelated to the immediate task, identify them with a clear messages so that I can put them on my TODO list.
12. When I give you a plan file to execute, as in "Please execute the plan file ...," that means that I just want you to execute the plan. Do not modify the plan. Do not enter plan mode. Just execute the plan.
13. You may see uncommitted changed files that you did not change. Do not be alarmed by this. They are either the user's manual changes or were changed by Kimi in an earlier session. These changes will be included when I instruct you to perform a commit.
14. Avoid ad hoc workarounds. Make the existing architecture work and use it.
15. Do not limit or reduce the scope of a task just because it "might take a long time" or "might be tedious."
16. Always remember to update the documentaion before you finish.

## Hard Rules

- **Git mutations require explicit confirmation, every time.** Before running
  `git commit`, `git push`, `git reset`, `git rebase`, or any other git
  mutation, ask the user for confirmation. Do not skip this step even if the
  user previously said "commit it," "bump the version," or similar.
- Do not automatically bump the version.
- Do not automatically commit.
- You may not modify anything except what is in the current working directory and its subdirectories.
- Do not automatically update the VERSION file unless I specifically tell you to.
- Do not automatically update the change log unless I specifically tell you to.
- Do not try to use the deploy-version script.
- Do not try to use the switch-version script.
- Do not attempt to do what the deploy-version or switch-version scripts do.
- The system prompt says, "Make MINIMAL changes to achieve the goal." Do not use this statement to talk yourself out of your responsibilities to follow the user's instructions.
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
_local_bashinit=$(dirname "$(realpath "${BASH_SOURCE[0]}")")/bashinit
if [[ -f "$_local_bashinit" ]]; then
    source "$_local_bashinit"
else
    source ~/bashinit
fi
bashinit
unset _local_bashinit

source_helper rootcheck
rootcheck
```

`source_helper <name>` is provided by `bashinit`.  It resolves the named
sibling script or library through `find_zfsutility_script` and sources it,
logging a fatal message and exiting if the helper cannot be found.

Scripts prefer the `bashinit` in their own directory so a checkout or
deployed version always bootstraps itself with its matching helpers. The
fallback to `~/bashinit` preserves test layouts that only provide a fake
`bashinit` in `$HOME`.

- `bashinit` is wired as a symlink at `/root/bashinit` →
  `/usr/local/lib/zfsutilities/current/bin/bashinit` by `switch-version` (tracks
  the active version)
- `$mydir` is set by `bashinit` to the calling script's directory
- Function scripts are sourced (not executed) and call functions by name

### Node-Aware Scripts

Scripts that interact with the storage/compute hosts (in `bin/`) add
`node-lib.sh` (in `lib/`) to the standard header:

```bash
_local_bashinit=$(dirname "$(realpath "${BASH_SOURCE[0]}")")/bashinit
if [[ -f "$_local_bashinit" ]]; then
    source "$_local_bashinit"
else
    source ~/bashinit
fi
bashinit
unset _local_bashinit

NODE_LIB="${NODE_LIB:-$(find_zfsutility_script node-lib.sh)}"
source "$NODE_LIB"
source_helper rootcheck
rootcheck
```

`NODE_LIB` is optional; it lets tests (and unusual layouts) point at the
library explicitly while production deployments fall back to
`find_zfsutility_script node-lib.sh`.

`bashinit` provides `find_zfsutility_script` for locating sibling scripts
and libraries across the repo or deployed `bin/` directory (e.g.
`find_zfsutility_script promote-vm-clone`).  `node-lib.sh` consumes this
helper rather than defining its own copy; it provides mode-aware
configuration, pool helpers (`pool_to_target`, `pool_list`,
`is_known_pool`), remote resolution (`remote_zfsutility_script`), and
clone/archive helpers (`gen_mac`, `get_json_archive_path`).
Remote `bash -s` heredocs use
`mydir=$(realpath /usr/local/lib/zfsutilities/current/bin)` so the code
running on the remote side locates its own installed copy.

`iscsi-lib.sh` contains the shared iSCSI teardown/rebuild helpers used by
`zfsdelfs` and `zfs-send-receive`. It declares the `ISCSI_TEARDOWN`
associative array, sources `node-lib.sh` for remote resolution, and provides
`iscsi_teardown_zvol` and `iscsi_rebuild_torn_down`. Both callers locate it
via `find_zfsutility_script iscsi-lib.sh`.

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
isolated in `python/zfs_repository.py` via the `ZfsRepository` class.
GUI pages and action handlers receive the repository from `app.ctx.zfs_repository`
(or fall back to `get_default_repository()`). This keeps subprocess mocking
straightforward: Python tests patch `subprocess.run` and the repository methods
pass the mocked calls through.

### Session Log Utilities

Per-run session log helpers live in `python/session_log.py`.
`BackupRunner` (GUI) and `profile_runner.py` (headless/cron) both use these
stateless functions to create log files, append raw subprocess output, write
trailers, and enforce the session-log size cap.

### Snapshot Naming Convention

Format: `@<label>-<yyyy-mm-dd>T<hh:mm><tz>-<bucket>`

Buckets: `d` (daily), `w` (weekly), `m` (monthly), `s` (offsite), `c` (clone origin)

### Retention Policies

Live per-pool retention policies are stored in the shared JSON config at
`/var/lib/zfsutilities/config.json` (legacy fallback `/root/.config/zfsutilities.json`)
under the `retention` key. Each pool has a
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
exist, leaving any existing user-entered per-pool policies untouched. Only
`share/retention/zfsretainpol-default` is kept under version control; pool-specific
sample policy files are not shipped so they cannot be re-imported later.
`deploy-version` copies the entire `share/` tree into the deployed version, so any
pool-specific files accidentally added to `share/retention/` would also be
deployed. Use the GUI Retention tab or `backup_config.get_retention` /
`save_retention` to add or edit per-pool policies. The Prune list matches the
pool selection semantics of `zfscleanup`: it uses the pools registered in the
JSON config (`config.pools`) when that list is non-empty, and falls back to all
online pools when it is empty. Offline configured pools are omitted. Pools
without an explicit retention policy are pruned using the `default` policy, so
they are still listed when they would be pruned by `zfscleanup`.

### Parameter Override System

`zfsoverrides` enables runtime parameter changes via command line:

```bash
./zfsdailybackup "backup_NVME1='N'; prune='N'"
```

## Key Directories

- Root directory: Active utilities and scripts
- `bin/` - Executable scripts
- `lib/` - Sourced shell libraries
- `python/` - GTK/Python GUI source
- `docs/docs/` - Documentation source (MkDocs)
- `docs/site/` - Generated documentation site (not tracked; run `mkdocs build` in `docs/`)
- `share/` - Static resources, templates, and sample configurations
- `tests/` - Bash and Python test suites

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

**Two-step restore** (`zfsfullcopy` or `zfs-send-receive` with `doincrementals='N'`):

`zfs-send-receive` performs both steps internally when asked to do a full copy:

1. Full copy of the oldest available snapshot (`doincrementals='N'`, `commsnap_mostrecent='OLDEST'`)
2. Incremental copy with intermediates from that oldest snapshot to the target

`zfsfullcopy` and `zfsrestore` make a single `send-receive` call; the two-step behavior is now internal to `zfs-send-receive`.

**Clone handling:** Cloned datasets are backed up as regular datasets.
`zfs-send-receive` treats them as independent datasets because ZFS clones cannot be
incrementally replicated while preserving their clone relationship. This is the correct
and expected behavior. Do not enable `$skipclones` in production backup scripts — it
causes data loss.

## Important Variables

- `$nextsnap` - New snapshot name (generated by `zfssnapbuild`)
- `$force='Y'` - Force operations (destroy destination before full copy)
- `$releaseholds='Y'` - Release matching holds when deleting snapshots.
  Matching tags are controlled by `$releaseholds_tags` (default `offsite-*`).
  Snapshots that still have unmatched holds are skipped with a warning.
- `$receive_s_option='s'` - Enable resumable receives
- `$resumablethreshold` - Size threshold for resumable transfers (default 50GB)

## bashinit Helper Functions

The `bashinit` script provides these functions:

- `bashinit` - Sets `$mydir` to the calling script's directory; auto-creates a session log file for directly-executed scripts
- `log_msg [--long-prefix] "message"` - Logs to stderr and to `$ZFSUTILITIES_LOG_FILE` if set. The `file:line:` prefix is omitted on terminals by default; pass `--long-prefix` to force it. All messages are always emitted; filtering by message level is done in the GUI log viewers.
- `ask_yn "prompt" ["Y"|"N"]` - Prompts for y/n with input validation; optional second argument is the default answer (N if omitted); returns 0 for yes, 1 for no
- `die [--long-prefix] "message"` - Logs a FATAL message and terminates the process via `bashfatal`; `--long-prefix` forces the `file:line:` prefix
- `warn [--long-prefix] "message"` - Logs a WARN message; `--long-prefix` forces the `file:line:` prefix

A small number of scripts are intentional exceptions to the `log_msg`/`warn`/`die` requirement (for example, pure data wrappers, test harnesses, and scripts that must format interactive tables). Those exceptions are recorded in `docs/docs/developer-guide/bash-logging-exceptions.md`.

- `calledbybash` - Returns 0 if script was executed directly (not sourced)
- `find_zfsutility_script <name>` - Searches the repo or deployed layout for a sibling script or library and prints its absolute path. Used to locate `node-lib.sh`, `rootcheck`, and other siblings from scripts in `bin/` without hard-coding paths. The absolute deployment directories can be overridden with `ZFSUTILITIES_BIN_DIR`, `ZFSUTILITIES_CURRENT_BIN_DIR`, and `ZFSUTILITIES_SYSTEM_LIB_DIR`.

**Deployment**: `deploy-version` places software under
`/usr/local/lib/zfsutilities/versions/<version>/` without touching active
production. `switch-version` creates and updates production wiring, including
`/root/bashinit`, `PATH` configuration, library symlinks (`node-lib.sh`,
`two-node-lib.sh` as a deprecated compatibility wrapper, and `rootcheck`),
and desktop shortcuts. When `switch-version` changes the active version, `/root/bashinit`
tracks automatically — no manual copying needed.

For development (running scripts from the repo without `sudo`), use a symlink:

```bash
ln -sfn /path/to/repo/bin/bashinit ~
```

## zfsscruball Pause/Resume

`zfsscruball` supports pause and resume:

- `./zfsscruball` or `./zfsscruball start` - Start fresh scrub of all pools
- `./zfsscruball pause` - Pause all running scrubs
- `./zfsscruball resume` - Resume paused scrubs, continue with remaining, skip completed

State is tracked in `/run/zfsutilities/zfsscruball.state` during a run.

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
from `/etc/zfsutilities/node.conf` (fallback `/etc/zfsutilities/two-node.conf`,
legacy `/etc/zfsutilities-node.conf` also works), reads the
peer's `/usr/local/lib/zfsutilities/current/VERSION` via SSH as `root`, and logs
a warning if the versions differ or the peer is unreachable. The check runs in a
background thread so GUI startup is not delayed.

Path resolution for the Python layer is centralized in
`python/path_utils.py`, which mirrors the bash `$mydir` /
`find_zfsutility_script` / `remote_zfsutilities_bin` behavior.  The module
honors `ZFSUTILITIES_VERSION_BASE`, `ZFSUTILITIES_REMOTE_BIN`, and
`ZFSUTILITIES_REMOTE_VERSION` environment overrides for non-standard
installations.

## Test Framework

An automated bash test harness lives in `tests/`.

### Running Tests

When running many suites, start with `-q` or `--failures-only` so the harness
reports which suites failed without flooding the terminal. Run individual
suites with full output only when you need the per-test detail.

```bash
# Run all suites (use -q or --failures-only to keep output manageable)
tests/run-tests -q
tests/run-tests --failures-only

# Run a specific suite
tests/run-tests test-zfsretain

# Full output for a single suite or a small subset
tests/run-tests test-zfsretain test-zfsbuildfsarray
```

### Test Suite Files

| Suite                          | Tests | Description                                                                                                   |
| ------------------------------ | ----- | ------------------------------------------------------------------------------------------------------------- |
| `test-deploy-version`          | 21    | Root-level script selection, exclusions, retention-policy file filtering, critical-script validation, and no production wiring |
| `test-installer-checks`        | 29    | Installer prerequisite checks and desktop-launcher helper functions                                           |
| `test-installer-retention`     | 3     | Installer default retention profile initialization and preservation of existing user profiles                 |
| `test-move-vm-disk`            | 14    | `move-vm-disk` helper functions: disk-key parsing, manifest add/remove, validation helpers, state round-trip, heredoc bootstrap |
| `test-restart-iscsi-services`  | 13     | VM running-state detection before iSCSI target restart and main() helper invocation                           |
| `test-safe-iscsi-save`         | 6     | Degraded-config guard for iSCSI saveconfig and encrypted-backstore boot-config stripping                    |
| `test-startdocserver`          | 13    | Server health checks, PID discovery, CWD mismatch, restart logic                                              |
| `test-iscsi-add-encrypted-luns`| 3     | Encrypted-LUN config path resolution (modern + legacy fallback) and targetcli invocation                      |
| `test-switch-version`          | 8     | Version switching, production wiring, prior-version uninstall, rollback, `--uninstall`, `--list`, and obsolete systemd artifact cleanup |
| `test-zfsbuildfsarray`         | 10    | Dataset array building with includes/excludes/depth/sorting                                                   |
| `test-zfscommsnap`             | 6     | Common snapshot detection by GUID, most-recent/oldest modes                                                   |
| `test-zfscleanup`              | 9     | Pool selection: config pools, explicit argument, fallback to online pools, offline skip                       |
| `test-zfs-diagnose-busy`       | 8     | Diagnostic output from `zfs-diagnose-busy` — busy dataset causes                                              |
| `test-zfsdelfs`                | 10     | iSCSI teardown/rebuild manifest cleanup for `zfsdelfs`                                                        |
| `test-zfsdelsnap`              | 6     | Snapshot deletion safety checks, hold release, `zfscheckagainst` dependency sourcing, user-hold blocking        |
| `test-zfsfullcopy`             | 9     | `zfsfullcopy` full-copy wrapper: overrides, required parameters, single `send-receive` invocation, parameter forwarding |
| `test-ensure-restored-vm-iscsi` | 24    | `ensure-restored-vm-iscsi` parsing: zvol basename/pool extraction, by-path LUN extraction, VM-config LUN lookup, EFI disk detection by size, fallback LUN assignment when zvol disk numbers do not match config slots, and storage-side script forwarding |
| `test-zfslockmanager`          | 43    | Lock acquire/release, conflict detection, hierarchy, stale cleanup, headless abort, wait/retry, multi-lock acquisition, headless timed wait |
| `test-zfsretain`               | 17    | Retention policy phases (offsite dedup, same-day dedup, oldest-first bucket pruning, empty logging, retain=0) |
| `test-zfs-send-receive-dryrun` | 39    | Dry-run logging, space checks, resume-token helpers (including non-existent destination), clone messages, pv quiet in headless mode, full-copy lock hand-off, two-step full transfers, pool-root full-copy fallback |
| `test-zfssnapbuild`            | 13     | Snapshot name generation, bucket logic, snapfile handling                                                     |
| `test-lock-coverage`           | 1     | Static checks that locked scripts source zfslockmanager, initialize it, and acquire locks                    |
| `test-unarchive-vm`            | 6     | `--new-vmid` rewriting, UUID regeneration, conflict handling                                                  |
| `test-zfsdelallholds`          | 6     | Selective hold release by tag patterns                                                                        |
| `test-zfsdelallsnaps`          | 5     | Return-code behavior and lock acquisition around snapshot deletion                                            |
| `test-zfsmassdelsnaps`         | 16    | Mass snapshot deletion: ignore/respect retention, dry-run, approval, releaseholds forwarding                  |
| `test-zfsmount`                | 2     | Lock acquisition before mount/unmount per dataset                                                             |
| `test-zfsreapplyholds`         | 11    | Capture/apply snapshot holds, CLI argument parsing, dry-run apply                                             |
| `test-zfsrestore`              | 10    | `zfsrestore` full-copy wrapper: overrides, legacy second overrides, required parameters, single `send-receive` invocation, parameter forwarding |
| `test-zfsrestoresendstream`    | 1     | Lock acquisition before each zfs receive destination                                                          |
| `test-zfsresume`               | 1     | Lock acquisition before reading resume token                                                                  |
| `test-zfsunmount`              | 1     | Lock acquisition before unmount per dataset                                                                   |
| `test-module-dependencies`     | 2     | Static analysis: root-level bash modules source the modules whose functions they call                         |

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
- `rootcheck` is mocked to a no-op so tests run as non-root.  Any suite that legitimately requires root should check `$EUID` and emit `test_skip` when non-root.
- The `zfs` mock handles combined short options (e.g. `-Hp`) and per-dataset snapshot lists.
- Inner functions defined inside a function (e.g. `send-receive`) become available for direct testing **after** the outer function has been executed once.

### Python Tests

A Python test harness lives in `tests/python/` and uses Python's built-in `unittest` module. The only optional dependency is `pyyaml`, required by `test_docs_integrity` for parsing `mkdocs.yml`.

#### Running Python Tests

When running many suites, start with `-q` or `--failures-only` so the harness
reports which suites failed without flooding the terminal. Run individual
suites with full output only when you need the per-test detail.

```bash
# Run all Python test suites (use -q or --failures-only to keep output manageable)
./tests/run-python-tests -q
./tests/run-python-tests --failures-only

# Run a specific Python suite
./tests/run-python-tests test_backup_config

# Full output for a single suite or a small subset
./tests/run-python-tests test_backup_config test_backup_runner

# Run via the unified harness (bash + Python)
tests/run-tests -q
tests/run-tests --failures-only
tests/run-tests test_backup_config
tests/run-tests test-zfsretain test_backup_config
```

#### Test Suite Files

| Suite                     | Tests | Description                                                                                                    |
| ------------------------- | ----- | -------------------------------------------------------------------------------------------------------------- |
| `test_action_dispatch`    | 39     | Page button specs, action dispatch table, and Logs tab button wiring                                           |
| `test_backup_config`      | 32    | Config load/save, defaults, pools, retention, UI state, snapshot name generation, log pruning, message level   |
| `test_backup_history`     | 36    | History entry schema, load/save/prune, success-rate calculation, human-size parsing, duration formatting       |
| `test_backup_page`        | 23     | Backup tab UI labels (including pre/post command labels), config load/collect helpers, and frame header widget support |
| `test_backup_runner`      | 59    | Session log creation, subprocess output parsing, byte counting, trailer formatting, fatal step messages, and log size cap |
| `test_command_builders`   | 51    | Rsync/ZFS command builders, retention step descriptions, endpoint parsing, dry-run assignments, host detection |
| `test_config_migrations`  | 51    | Schema migrations 1→12, idempotency, missing migration errors                                                  |
| `test_cron_manager`       | 41    | Cron line generation, condition support, human-readable interpretation, next-run computation                     |
| `test_dashboard_page`     | 185   | Dashboard layout, task handling, pool/VM/scrub/history queries, warning indicators, async refresh loading state |
| `test_docs_integrity`     | 14    | MkDocs nav consistency, orphan-file detection, internal link resolution, anchor existence, hook importability  |
| `test_gui_infrastructure` | 144    | GTK mock setup, GUI module imports, docs viewer zoom/navigation/state persistence, anchor scrolling            |
| `test_installer_retention` | 6     | Installer retention profile initialization: default-only on new install and preservation of existing profiles |
| `test_legacy_retention`   | 7     | Legacy `zfsretainpol-*` file parsing and pool scanning                                                         |
| `test_logging_config`     | 42    | Message levels, GUI sink, session log env helpers, and session log truncation                                  |
| `test_logs_page`          | 50    | Log list scanning, filtering, deletion, status parsing, tail-only viewer for large files, column-header label tooltips, and pop-out reparenting |
| `test_main`               | 40    | GUI entry point: PID-file single-instance, auto-replace, transient wait dialog, event pumping, retry-after-remote registration, pkexec logic, initial dashboard refresh |
| `test_page_runners`       | 10     | Backup/offsite/restore run handlers, session log preparation, auto-destination, pull-step activation           |
| `test_profile_manager`    | 20    | Profile CRUD, update, name validation, listing, existence checks, lifecycle logging, condition defaults          |
| `test_profile_dialogs`    | 14    | Add/Recall profile dialogs, duplicate-name overwrite handling                                                  |
| `test_profile_runner`     | 71    | Backup/offsite/restore/retention profile step building, rsync failure diagnosis in headless runs               |
| `test_profile_runner_concurrency` | 10 | Per-profile advisory locks, duplicate-invocation suppression, and metadata                                  |
| `test_profile_integration` | 3    | Concurrent profile execution: disjoint datasets, same-dataset conflict, backup+prune serialization             |
| `test_restore_page`       | 15    | Restore tab UI widgets, config load/collect, auto-destination, advanced variables                            |
| `test_restore_runner`     | 22    | Restore destination computation and zfs-send-receive parameter mapping                                         |
| `test_schedule_page`      | 66    | Schedule page path resolution, dirty tracking, condition field, run-now child-watch handling, fatal-fallback logging, async refresh, and next-run caching |
| `test_scrub_manager`      | 91    | Scrub state parsing, queue/target management, priority ordering, tick logic, systemd timers                      |
| `test_scrub_page`         | 8     | Scrub page store schema, flicker-free refresh logic, and drag-and-drop priority ordering                         |
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
- **Single-call-site helpers**: Functions should generally have at least two calling sites. Small readability helpers or functions created for direct unit testing may have a single call site; avoid splitting out a helper when it only wraps a single expression used once.
- **Never use absolute line numbers when editing files** Instead, use surrounding context to locate the editing target location.

**Project-specific patterns:**

- Start scripts with the standard initialization:

  ```bash
  _local_bashinit=$(dirname "$(realpath "${BASH_SOURCE[0]}")")/bashinit
  if [[ -f "$_local_bashinit" ]]; then
      source "$_local_bashinit"
  else
      source ~/bashinit
  fi
  bashinit
  unset _local_bashinit

  source_helper rootcheck
  rootcheck
  ```

- Use `source_helper <name>` (provided by `bashinit`) to load sibling helpers
  (e.g. `rootcheck`, `zfslockmanager`) via `find_zfsutility_script`, rather than
  `source $mydir/<name>`.

- Use the control-flow primitive that matches the context:

  1. **Inside a function** — use `return` (with an explicit code when not 0).
     Functions must not use `exit`, because `exit` inside a function kills the
     whole process and is hazardous when the function is sourced and called from
     a test or another script.

  2. **Top level of a script executed directly** — use `exit`. This is safe
     because the dual-mode guard `if calledbybash; then main "$@"; fi` prevents
     top-level code from running when the script is sourced.

  3. **Top level of a dual-mode script** (designed to be sourced or executed, or
     lacking a `calledbybash` guard) — use
     `source "$(find_zfsutility_script bashreturn)" <code>` so a sourcing caller
     regains control and a direct execution exits cleanly.

  4. **Fatal termination from a sourced helper/function** where returning an
     error code is impractical — use
     `source "$(find_zfsutility_script bashfatal)" <code>` or the `die` helper.
     This terminates the entire process even when the caller is sourced, so
     reserve it for truly unrecoverable errors.

- `bashreturn` is not a general replacement for `return` inside functions.
  `bashfatal` is not a general replacement for `exit` at the top level of an
  executed script.

- Use `usage()` for argument errors, showing help and exiting.

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

The GTK GUI code in `python/` follows standard Python conventions:

- **PEP 8**: 4 spaces, 100-character line limit.
- **Naming**: `lowercase_with_underscores` for variables/functions, `CapWords` for classes, `UPPERCASE_WITH_UNDERSCORES` for constants.
- **Imports**: One per line, grouped as standard library, third-party, local modules.
- **Docstrings**: Triple quotes (`"""`) for modules, classes, and functions.
- **Avoid mutable defaults** in function parameters.
- **Comparisons to `None`**: Use `is None` / `is not None`.
- **Single-call-site helpers**: Functions should generally have at least two calling sites. Small readability helpers or functions created for direct unit testing may have a single call site; avoid splitting out a helper when it only wraps a single expression used once.
- **Never use absolute line numbers when editing files** Instead, use surrounding context to locate the editing target location.

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

## Recent Session Notes (2026-08-23)

- **Release 0.86.0 wrap-up** — Added a `--long-prefix` option to the bash
  (`log_msg`, `warn`, `die`, `msg_prefix`) and Python (`log_msg`) logging helpers.
  Terminal output now uses a short prefix by default; session logs and GUI sinks
  continue to use the long `file:line:` prefix. Updated the Messages reference,
  Coding Policies, test suites (`test-logging`, `test_logging_config.py`), and
  refreshed AGENTS.md test-suite counts.

## Recent Session Notes (2026-07-23)

- Replaced the all-or-nothing `$releaseholds` behavior with tag-pattern hold
  release. A new array, `$releaseholds_tags`, defaults to `('offsite-*')` and
  accepts bash glob patterns using the same syntax as `$includes`/`$excludes`.
  `zfsdelsnap` now releases only matching holds; snapshots that still have
  unmatched user holds are skipped with a warning instead of failing the job.
  The default is applied across `zfsretain`, `zfscleanup`, `zfsoffsiteretain`,
  `zfs-send-receive`, `zfsdelallsnaps`, `zfsrestore`, and `zfsfullcopy`, and
  the Python GUI emits `releaseholds_tags=("offsite-*")` whenever it enables
  hold release. Added `tests/test-zfsdelallholds` and extended
  `tests/test-zfsdelsnap` to cover the new semantics. All bash and Python
  suites pass.

## Recent Session Notes (2026-07-16)

- Removed the obsolete `bin/install-scripts` script. It was already
  marked deprecated and superseded by `bin/install-two-node`, but it
  was still being deployed by `deploy-version` and referenced by
  `two-node-lib.sh`. Updated those references to point to the current installer.

## Recent Session Notes (2026-07-15)

- Renamed `retire-vm` to `archive-vm` and `unretire-vm` to `unarchive-vm` to
  better describe their purpose.
- Added `remove-vm`: scans pools for `vm-<VMID>-disk-*` zvols, lists iSCSI
  target/LUN mappings, asks for confirmation, destroys the zvols with
  `zfsdelfs`, and removes the Proxmox VM definition.
- Added `uninstall-zfsutilities`: a single interactive uninstall script that
  removes the deployed software and production wiring, with an optional
  `--purge` mode for configuration/logs/history and `--all-nodes` for two-node
  deployments. The install scripts now detect partial-uninstall remnants and
  offer to run `uninstall-zfsutilities` first.

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
- Updated `bin/install-scripts` to deploy `repair-iscsi-luns` on the
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

- Phase 4 file-locking: Added `python/file_locking.py` to serialize
  access to shared JSON/state files (`/var/lib/zfsutilities/config.json`,
  `/var/lib/zfsutilities/history.json`, `/var/lib/zfsutilities/scrub_state.json`,
  and the session-log index).
  Python modules use `fcntl.flock` context managers; the bash `zfsconfig`
  helper uses the system `flock` command on the same lock files. Lock paths are
  overridable via environment variables for testing. `add_history_entry()` now
  performs its read-modify-write under a single exclusive lock so concurrent
  runners cannot lose history entries.
- Phase 5 profile-level concurrency: Added per-profile advisory locks in
  `profile_runner.py` under `/run/lock/zfsutilities/profiles/<profile>.lock`. A second
  invocation of the same profile exits 0 without running, so cron does not mail
  on the expected duplicate-run case. The Dashboard Running Tasks list now shows
  "Profile" entries and warns when a profile is active. The lock directory is
  overridable via `ZFSUTILITIES_PROFILE_LOCK_DIR` for testing.

## Recent Session Notes (2026-06-29)

- Phase 6 integration testing and documentation: Added
  `tests/python/test_profile_integration.py`, which runs concurrent profiles in
  separate subprocesses and verifies that disjoint datasets run in parallel,
  same-dataset conflicts fail safely, and backup+prune operations serialize.
  Created `docs/docs/user-guide/profiles.md` to explain profiles, scheduling,
  concurrent execution, and conflict resolution. Updated
  `docs/docs/developer-guide/concurrency-collisions.md` to mark the
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
- Encrypted zvol lifecycle: `/etc/zfsutilities/iscsi-encrypted-luns.conf` is single source of truth; `new-vm-disk --encrypted` and `remove-vm-disk` maintain it
- Python `log_msg()`: All Python scripts now use priority-filtered logging via `backup_config.log_msg()`, mirroring the bash `log_msg()` behavior with `file:line:` prefixes and GUI sink support

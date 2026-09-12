# AGENTS.md

This file provides guidance to AI coding assistants when working with code in this repository.

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
11. If you run across pre-existing errors or bugs that are unrelated to the immediate task, identify them with a clear message so that I can put them on my TODO list.
12. When I give you a plan file to execute, as in "Please execute the plan file ...," that means that I just want you to execute the plan. Do not modify the plan. Do not enter plan mode. Just execute the plan.
13. You may see uncommitted changed files that you did not change. Do not be alarmed by this. They are either the user's manual changes or were changed by Kimi in an earlier session. These changes will be included when I instruct you to perform a commit.
14. ACTIVE NOTICE (until further notice): The user is editing the documentation
    (`docs/`) by hand. If you come across documentation changes you did not
    make, do not be alarmed and leave them alone — do not revert, reword, or
    "fix" them. You should continue to update documentation. Just don't revert my changes.
15. Avoid ad hoc workarounds. Make the existing architecture work and use it.
16. Do not limit or reduce the scope of a task just because it "might take a long time" or "might be tedious."
17. Always remember to update the documentaion before you finish.

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

ZFS Utilities is a collection of bash and Python scripts and a GUI for managing ZFS backup, snapshot, and retention operations across multiple ZFS pools. All scripts require root privileges and operate on live ZFS datasets.

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
`zfsdelfs` and `zfs-send-receive`. It declares the `iscsi_teardown`
associative array, sources `node-lib.sh` for remote resolution, and provides
`iscsi_teardown_zvol` and `iscsi_rebuild_torn_down`. Both callers locate it
via `find_zfsutility_script iscsi-lib.sh`.

`transfer-lib.sh` contains the shared ZFS transfer helpers used by
`zfs-send-receive` and `zfs-migrate-send` (the Migrate Pool copy steps):
`transfer_abort_resume_token`, `transfer_resume_token_stale`,
`transfer_validate_resume_token`, `transfer_pv_args`, `transfer_do`, and
`transfer_check_space`. It is a mechanical extraction of the former
`do_transfer`/`check_space_available`/resume-token leaf operations, so the
production backup path and the migration path share one resumable,
`pv`-instrumented, rate-limited pipeline implementation. Both callers locate
it via `find_zfsutility_script transfer-lib.sh`.

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

The Disks tab inventory comes from `python/disk_repository.py`
(`DiskRepository.list_disks()`, cached by `DiskInventoryCache` in
`disks_page.py`). `list_disks()` always removes the system boot disk — the
disk hosting the root filesystem, found by resolving the root source with
findmnt (handles plain partitions, LVM, and BTRFS subvolumes) and walking the
lsblk PKNAME chain to the top-level disk, with an lsblk MOUNTPOINT-scan
fallback for ZFS roots — and all of its partitions, so no Disks-page list
(inventory tree or any action-dialog disk picker) ever offers them.

Pool creation lives in `pool_create.py` (pure logic: eligibility, name
validation, capacity estimator) and `pool_create_wizard.py` (GTK wizard on the
Disks page). The wizard executes `zpool create` as one `BashStep` through
`app.dataset_runner` (session-logged) under a pool-name `zlm` write lock, and
only on the storage host in two-node configurations.

Pool growth and maintenance live in `pool_growth.py` (pure logic:
attach/replace/detach classification, infra-vdev validation, scrub-block check)
and `pool_growth_dialogs.py` (GTK dialogs + Disks-page handlers for Add Data
Vdev, Attach, Replace, Detach, and Add Infra Vdev; shared review scaffold with
confirmation matched to each operation's danger). The pure argv builders
`build_add_vdev_command` (also infrastructure vdevs via `kind=`),
`build_attach_command`, `build_replace_command`, and `build_detach_command`
live in `zfs_repository.py` next to `build_create_pool_command`.

Copy-based pool migration (Migrate Pool) lives in `pool_migrate.py` (pure
logic: migration snapshot/temp-pool naming, step planning, capacity checks,
tree verification) and `pool_migrate_dialogs.py` (GTK wizard + Disks-page
handler). It copies a pool to new disks or via a holding pool when ZFS
cannot expand in place: recursive `@migrate-…` snapshot, one resumable
`zfs-migrate-send` step per top-level dataset (`zfs send -Rw` received with
`zfs receive -u -F -s`, `pv` in the pipeline, optional bandwidth limit), tree
verification, then a typed-confirmation-gated cutover that exports the
source pool and re-imports the migrated pool under the source pool's name
(holding mode rebuilds on the freed disks first). The migration argv
builders (`build_recursive_snapshot_command`,
`build_migration_send_receive_command`, `build_pool_export_command`,
`build_pool_import_rename_command`, `build_pool_destroy_command`,
`build_destroy_dataset_command`) live in `zfs_repository.py`; the root-boot
pool is never offered for migration.

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

## Test Framework

For detailed information about writing and running tests, please see docs/docs/developer-guide/testing.md in the repository.

## Coding Standards

For detailed coding policies, please refer to @docs/docs/developer-guide/coding-policies.md in the repository.

---

## Recent Session Notes (2026-09-11)

- **Disks page dataset-tuning host gating** — Apply Profile and Rewrite Data
  now follow the same "storage host only" policy as the other Disks-page
  buttons: `update_disks_button_sensitivity` (`python/disks_page.py`) disables
  both on the compute host in two-node mode (with an explanatory tooltip,
  taking precedence over the capability/selection tooltips), and
  `on_disks_apply_profile` / `on_disks_rewrite_data` log a WARN and return as
  defense in depth. Covered by new tests in `tests/python/test_disks_page_phase2.py`.
- **Automated two-node iSCSI enrollment** — New `bin/enroll-iscsi-pool`
  idempotently enrolls a pool in iSCSI export: adds its `POOL_TARGET` entry to
  `node.conf` on both nodes (peer first via SSH, so a peer failure aborts
  before the nodes diverge), runs `setup-iscsi-targets` on the storage host,
  and runs `rescan-storage` for the compute host. The Create Pool wizard
  (`python/pool_create_wizard.py`) offers enrollment through the new shared
  `python/iscsi_enroll.py` module after a successful create, and the Migrate
  Pool cutover (`python/pool_migrate_dialogs.py`) chains a `repair-iscsi-luns`
  step for iSCSI-managed pools. New suites: `tests/test-enroll-iscsi-pool`
  (21 tests) and `tests/python/test_iscsi_enroll.py` (25 tests).

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

## Disks Page Project Notes (active)

- Design brief: `/NFS1/dan(NFS1)/zfsutilities-plan/Disks page/README.md`
- Per-phase briefs: `/NFS1/dan(NFS1)/zfsutilities-plan/Disks page/`
- Working progress notes: `python/.disks_page_progress.md`
- Branch: `Disks-Page` (git does not allow spaces in branch names; the originally requested name "Disks Page" was adjusted to "Disks-Page").

# AGENTS.md

This file provides guidance to AI coding assistants when working with code in this repository.

# Development Agent

You are a meticulous and expert coding agent. For every task:

1. Enter plan mode and analyze the codebase. You do not need to ask permission to enter plan
mode.
2. Propose a clear implementation plan with steps. Include steps for
- linting/coding standards,
- testing
- updating documentation.
3. Wait for user approval or revision.
4. Execute only the approved plan.
5. During iteration, run only the affected test suites (see tests/AGENTS.md). Run the full suite
once, at the end, before responding.
6. Use concise, professional language.
7. Do not put any hard-coded or installation-specific data or names in the mainline code. These
must be entered by the user at runtime using text-based and GUI dialogs, or dynamically by the
code, and will usually be saved in a saved configuration file.
8. Look for and correct any deprecated code and features. Do not implement any deprecated code or
features.
9. Don't be lazy. Take the approach that is correct even though it may be more difficult to
implement.
10. If you run across pre-existing errors or bugs that are unrelated to the immediate task,
identify them with a clear message so that I can put them on my TODO list.
11. When I give you a plan file to execute, as in "Please execute the plan file ...," that means
that I just want you to execute the plan. Do not modify the plan. Do not enter plan mode. Just
execute the plan.
12. You may see uncommitted changed files that you did not change. Do not be alarmed by this.
They are either the user's manual changes or were changed by Kimi in an earlier session. These
changes will be included when I instruct you to perform a commit.
13. ACTIVE NOTICE (until further notice): The user is editing the documentation
     (`docs/`) by hand. If you come across documentation changes you did not
     make, do not be alarmed and leave them alone — do not revert, reword, or
     "fix" them. You should continue to update documentation. Just don't revert my changes.
14. Avoid ad hoc workarounds. Make the existing architecture work and use it.
15. Do not limit or reduce the scope of a task just because it "might take a long time" or "might
be tedious."
16. Update narrative documentation as you work, while context is fresh. Never record test counts
in documentation. VERSION and changelog remain off-limits per the Hard Rules.

## Hard Rules

- **Git mutations require explicit confirmation, every time.** Before running
  `git commit`, `git push`, `git reset`, `git rebase`, or any other git
  mutation, ask the user for confirmation. Do not skip this step even if
  the user previously said "commit it," "bump the version," or similar.
- Do not automatically bump the version.
- Do not automatically commit.
- You may not modify anything except what is in the current working directory and its
subdirectories.
- Do not automatically update the VERSION file unless I specifically tell you to.
- Do not automatically update the change log unless I specifically tell you to.
- Do not try to use the deploy-version script.
- Do not try to use the switch-version script.
- Do not attempt to do what the deploy-version or switch-version scripts do.
- AGENTS.md is user-owned. Never edit, reorganize, or append to it (including session notes).
- Session, progress notes, and notes to yourself are to be kept in SESSION_NOTES.md in the project root, never in AGENTS.md.
- If you skip, defer, or reduce any part of an approved plan or requested task, you MUST disclose
it explicitly in your final report, with the reason. Silent scope reduction is a rule violation.
- Never record test counts in documentation or comments.
- Re-read this file if a rule seems to conflict with a task; the file is short.

## Pre-existing (Out-of-Scope) Issues

There are times during development activities when you will encounter issues or bugs that happen to be out-of-scope for the immediate task. The following rules apply to those occasions.

+ When a pre-existing (out-of-scope) issue is discovered, document it as a new entry in the PREEXISTING.md file in the project root -- if it is not already there.
+ Whenever you address a pre-existing issue, remove it from the PREEXISTING.md file.
  - In your next response, note how many pre-existing issues were discovered and addressed during the turn. Also, read the file and note the number of entries remaining in the PREEXISTING.md file.
  - There is no need to recite or describe the issues in the response, unless it is critical to the health of the system or the project.
+ You may be prompted at any time (between turns) to address one or more of the issues.
+ This response is an example of a pre-existing issue that was ignored. Do not do this.
> Two ruff format nits remain in zfs_repository.py/test_zfs_repository.py — they sit in code from
     your uncommitted changes that I didn't touch, so I left them alone.

## Project Overview

ZFS Utilities is a collection of bash and Python scripts and a GUI for managing ZFS backup,
snapshot, and retention operations across multiple ZFS pools. All scripts require root privileges
and operate on live ZFS datasets.

## Running Scripts

All scripts must be run as root:

```bash
sudo scriptname
```

Scripts are deployed to /usr/local/lib/zfsutilities/current/bin/ and made
available via the PATH environment variable (set in /etc/profile.d/ and
/etc/sudoers.d/). You can still run ./scriptname directly from the repo
checkout for development.

Architecture

Script Sourcing Pattern

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

source_helper <name> is provided by bashinit.  It resolves the named
sibling script or library through find_zfsutility_script and sources it,
logging a fatal message and exiting if the helper cannot be found.

Scripts prefer the bashinit in their own directory so a checkout or
deployed version always bootstraps itself with its matching helpers. The
fallback to ~/bashinit preserves test layouts that only provide a fake
bashinit in $HOME.

• bashinit is wired as a symlink at /root/bashinit →
/usr/local/lib/zfsutilities/current/bin/bashinit by switch-version (tracks
the active version)
• $mydir is set by bashinit to the calling script's directory
• Function scripts are sourced (not executed) and call functions by name

Node-Aware Scripts

Scripts that interact with the storage/compute hosts (in bin/) add
node-lib.sh (in lib/) to the standard header:

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

NODE_LIB is optional; it lets tests (and unusual layouts) point at the
library explicitly while production deployments fall back to
find_zfsutility_script node-lib.sh.

bashinit provides find_zfsutility_script for locating sibling scripts
and libraries across the repo or deployed bin/ directory (e.g.
find_zfsutility_script promote-vm-clone).  node-lib.sh consumes this
helper rather than defining its own copy; it provides mode-aware
configuration, pool helpers (pool_to_target, pool_list,
is_known_pool), remote resolution (remote_zfsutility_script), and
clone/archive helpers (gen_mac, get_json_archive_path).
Remote bash -s heredocs use
mydir=$(realpath /usr/local/lib/zfsutilities/current/bin) so the code
running on the remote side locates its own installed copy.

iscsi-lib.sh contains the shared iSCSI teardown/rebuild helpers used by
zfsdelfs and zfs-send-receive. It declares the iscsi_teardown
associative array, sources node-lib.sh for remote resolution, and provides
iscsi_teardown_zvol and iscsi_rebuild_torn_down. Both callers locate it
via find_zfsutility_script iscsi-lib.sh.

transfer-lib.sh contains the shared ZFS transfer helpers used by
zfs-send-receive and zfs-migrate-send (the Migrate Pool copy steps):
transfer_abort_resume_token, transfer_resume_token_stale,
transfer_validate_resume_token, transfer_pv_args, transfer_do, and
transfer_check_space. It is a mechanical extraction of the former
do_transfer/check_space_available/resume-token leaf operations, so the
production backup path and the migration path share one resumable,
pv-instrumented, rate-limited pipeline implementation. Both callers locate
it via find_zfsutility_script transfer-lib.sh.

Core Components

zfs-send-receive - Main workhorse for copying ZFS data. Key parameters:

• $sourcefs - Source dataset
• $destfs - Destination pool/dataset
• $sourcefsremovequalifiers - Number of leading path segments to strip from source when
 constructing destination path
• $doincrementals - 'Y' for incremental, 'N' for full copy
• $includes / $excludes - Arrays for dataset filtering
• $autoproceed - 'Y' to suppress interactive prompts

zfsbuildfsarray - Builds filtered dataset arrays. Uses:

• $includes - Array of substrings to include (prefix with = for exact match)
• $excludes - Array of substrings to exclude
• $startwith - Skip datasets before this match
• $depth - Limit recursion depth
• $bottomup - 'Y' for descending sort

zfsretain - Applies retention policies in three phases:

1. For @offsite snapshots, remove all but the most recent per month per dataset
2. Remove same-day duplicate snapshots
3. Prune by bucket retention counts (prefers deleting empty snapshots with written=0; protects most
  recent snapshot as incremental base)

Snapshots with label clone or bucket c are skipped entirely in all phases.

Python ZFS Repository

All direct zfs/zpool subprocess calls from the GTK/Python GUI layer are
isolated in python/zfs_repository.py via the ZfsRepository class.
GUI pages and action handlers receive the repository from app.ctx.zfs_repository
(or fall back to get_default_repository()). This keeps subprocess mocking
straightforward: Python tests patch subprocess.run and the repository methods
pass the mocked calls through.

The Disks tab inventory comes from python/disk_repository.py
(DiskRepository.list_disks(), cached by DiskInventoryCache in
disks_page.py). list_disks() always removes the system boot disk — the
disk hosting the root filesystem, found by resolving the root source with
findmnt (handles plain partitions, LVM, and BTRFS subvolumes) and walking the
lsblk PKNAME chain to the top-level disk, with an lsblk MOUNTPOINT-scan
fallback for ZFS roots — and all of its partitions, so no Disks-page list
(inventory tree or any action-dialog disk picker) ever offers them.

Pool creation lives in pool_create.py (pure logic: eligibility, name
validation, capacity estimator) and pool_create_wizard.py (GTK wizard on the
Disks page). The wizard executes zpool create as one BashStep through
app.dataset_runner (session-logged) under a pool-name zlm write lock, and
only on the storage host in two-node configurations.

Pool growth and maintenance live in pool_growth.py (pure logic:
attach/replace/detach classification, infra-vdev validation, scrub-block check)
and pool_growth_dialogs.py (GTK dialogs + Disks-page handlers for Add Data
Vdev, Attach, Replace, Detach, and Add Infra Vdev; shared review scaffold with
confirmation matched to each operation's danger). The pure argv builders
build_add_vdev_command (also infrastructure vdevs via kind=),
build_attach_command, build_replace_command, and build_detach_command
live in zfs_repository.py next to build_create_pool_command.

Copy-based pool migration (Migrate Pool) lives in pool_migrate.py (pure
logic: migration snapshot/temp-pool naming, step planning, capacity checks,
tree verification) and pool_migrate_dialogs.py (GTK wizard + Disks-page
handler). It copies a pool to new disks or via a holding pool when ZFS
cannot expand in place: recursive @migrate-… snapshot, one resumable
zfs-migrate-send step per top-level dataset (zfs send -Rw received with
zfs receive -u -F -s, pv in the pipeline, optional bandwidth limit), tree
verification, then a typed-confirmation-gated cutover that exports the
source pool and re-imports the migrated pool under the source pool's name
(holding mode rebuilds on the freed disks first). The migration argv
builders (build_recursive_snapshot_command,
build_migration_send_receive_command, build_pool_export_command,
build_pool_import_rename_command, build_pool_destroy_command,
build_destroy_dataset_command) live in zfs_repository.py; the root-boot
pool is never offered for migration.

Session Log Utilities

Per-run session log helpers live in python/session_log.py.
BackupRunner (GUI) and profile_runner.py (headless/cron) both use these
stateless functions to create log files, append raw subprocess output, write
trailers, and enforce the session-log size cap.

Snapshot Naming Convention

Format: @<label>-<yyyy-mm-dd>T<hh:mm><tz>-<bucket>

Buckets: d (daily), w (weekly), m (monthly), s (offsite), c (clone origin)

Retention Policies

Live per-pool retention policies are stored in the shared JSON config at
/var/lib/zfsutilities/config.json (legacy fallback /root/.config/zfsutilities.json)
under the retention key. Each pool has a
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

Legacy project-root files zfsretainpol-<poolname> or zfsretainpol-default
are imported once into the JSON config and then ignored. On a new install, only
zfsretainpol-default is kept; any pool-specific legacy policies are cleared
so the Retention tab starts with a single default policy. The installers
(install-single-node and install-two-node) initialize the JSON config
retention section with only the default policy when the config does not yet
exist, leaving any existing user-entered per-pool policies untouched. Only
share/retention/zfsretainpol-default is kept under version control; pool-specific
sample policy files are not shipped so they cannot be re-imported later.
deploy-version copies the entire share/ tree into the deployed version, so any
pool-specific files accidentally added to share/retention/ would also be
deployed. Use the GUI Retention tab or backup_config.get_retention /
save_retention to add or edit per-pool policies. The Prune list matches the
pool selection semantics of zfscleanup: it uses the pools registered in the
JSON config (config.pools) when that list is non-empty, and falls back to all
online pools when it is empty. Offline configured pools are omitted. Pools
without an explicit retention policy are pruned using the default policy, so
they are still listed when they would be pruned by zfscleanup.

Parameter Override System

zfsoverrides enables runtime parameter changes via command line:

```bash
./zfsdailybackup "backup_NVME1='N'; prune='N'"
```

Key Directories

• Root directory: Active utilities and scripts
• bin/ - Executable scripts
• lib/ - Sourced shell libraries
• python/ - GTK/Python GUI source
• docs/docs/ - Documentation source (MkDocs)
• docs/site/ - Generated documentation site (not tracked; run mkdocs build in docs/)
• share/ - Static resources, templates, and sample configurations
• tests/ - Bash and Python test suites

System Dependencies

• pv - Progress visualization for large transfers
• zfsutils-linux - ZFS userspace utilities
• rsync - File synchronization for pull operations
• smartmontools - SMART disk health and SSD/NVMe wear data (smartctl)

Common Workflows

Daily backup (zfsdailybackup):

1. Pull rsync backups from remote hosts
2. Snapshot and copy threeamigos/proxmox → fivebays
3. Snapshot and copy NVME1 → fivebays
4. Apply retention policies

Two-step restore (zfsfullcopy or zfs-send-receive with doincrementals='N'):

zfs-send-receive performs both steps internally when asked to do a full copy:

1. Full copy of the oldest available snapshot (doincrementals='N', commsnap_mostrecent='OLDEST')
2. Incremental copy with intermediates from that oldest snapshot to the target

zfsfullcopy and zfsrestore make a single send-receive call; the two-step behavior is now internal
to zfs-send-receive.

Clone handling: Cloned datasets are backed up as regular datasets.
zfs-send-receive treats them as independent datasets because ZFS clones cannot be
incrementally replicated while preserving their clone relationship. This is the correct
and expected behavior. Do not enable $skipclones in production backup scripts — it
causes data loss.

bashinit Helper Functions

The bashinit script provides these functions:

• bashinit - Sets $mydir to the calling script's directory; auto-creates a session log file for
 directly-executed scripts
• log_msg [--long-prefix] "message" - Logs to stderr and to $ZFSUTILITIES_LOG_FILE if set. The
 file:line: prefix is omitted on terminals by default; pass --long-prefix to force it. All
 messages are always emitted; filtering by message level is done in the GUI log viewers.
• ask_yn "prompt" ["Y"|"N"] - Prompts for y/n with input validation; optional second argument is
 the default answer (N if omitted); returns 0 for yes, 1 for no
• die [--long-prefix] "message" - Logs a FATAL message and terminates the process via bashfatal;
 --long-prefix forces the file:line: prefix
• warn [--long-prefix] "message" - Logs a WARN message; --long-prefix forces the file:line: prefix

A small number of scripts are intentional exceptions to the log_msg/warn/die requirement (for
example, pure data wrappers, test harnesses, and scripts that must format interactive tables).
Those exceptions are recorded in docs/docs/developer-guide/bash-logging-exceptions.md.

• calledbybash - Returns 0 if script was executed directly (not sourced)
• find_zfsutility_script <name> - Searches the repo or deployed layout for a sibling script or
library and prints its absolute path. Used to locate node-lib.sh, rootcheck, and other siblings
from scripts in bin/ without hard-coding paths. The absolute deployment directories can be
overridden with ZFSUTILITIES_BIN_DIR, ZFSUTILITIES_CURRENT_BIN_DIR, and
ZFSUTILITIES_SYSTEM_LIB_DIR.

Deployment: deploy-version places software under
/usr/local/lib/zfsutilities/versions/<version>/ without touching active
production. switch-version creates and updates production wiring, including
/root/bashinit, PATH configuration, library symlinks (node-lib.sh,
two-node-lib.sh as a deprecated compatibility wrapper, and rootcheck),
and desktop shortcuts. When switch-version changes the active version, /root/bashinit
tracks automatically — no manual copying needed.

For development (running scripts from the repo without sudo), use a symlink:

```bash
ln -sfn /path/to/repo/bin/bashinit ~
```

Versioned Deployment

Scripts are installed to /usr/local/lib/zfsutilities/versions/<version>/ and activated
via symlink. This allows instant rollback.

• deploy-version [version] — Deploy current repo state as a new version (run from repo root)
• switch-version <version>|previous|--list|--uninstall — Wire a deployed version into active
 production, roll back, list versions, or remove a version's wiring
• uninstall-version <version> — Remove an old version

Directory structure:

```
/usr/local/lib/zfsutilities/versions/v1.1.0/bin/   # scripts
/usr/local/lib/zfsutilities/versions/v1.1.0/lib/   # libraries
/usr/local/lib/zfsutilities/current -> versions/v1.1.0
/usr/local/lib/zfsutilities/bin -> current/bin     # PATH entry
```

Test Framework

For detailed information about writing and running tests, please see
docs/docs/developer-guide/testing.md in the repository.

Coding Standards

For detailed coding policies, please refer to @docs/docs/developer-guide/coding-policies.md in the
repository.

Project history lives in docs/docs/changelog.md.

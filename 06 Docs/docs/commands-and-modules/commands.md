# Commands

Scripts intended to be run directly from the shell (as root).

!!! note "Scripts are on PATH after deployment"
    After running [`deploy-version`](two-node.md#deploy-version-repo-root) and `switch-version`,
    scripts are available on `PATH` via `/usr/local/lib/zfsutilities/bin`.
    Run them by name (e.g., `sudo zfsdailybackup`). Use `./scriptname`
    only when running directly from a repository checkout.

Cross-references: globals mentioned per entry are documented in full on the
[Global Variables](../developer-guide/global-variables.md) page; shared
arrays and on-disk tables are on [Data Structures](../developer-guide/data-structures.md).

## Jump to

- [`backup-installed-programs`](#backup-installed-programs)
- [`check-prerequisites`](#check-prerequisites)
- [`datesubtract`](#datesubtract)
- [`deploy-version`](#deploy-version)
- [`getlinecount`](#getlinecount)
- [`git-release`](#git-release)
- [`PVE-send-to-archive`](#pve-send-to-archive)
- [`archive-vm`](#archive-vm)
- [`remove-vm`](#remove-vm)
- [`run-tests`](#run-tests)
- [`startdocserver`](#startdocserver)
- [`switch-version`](#switch-version)
- [`uninstall-version`](#uninstall-version)
- [`unarchive-vm`](#unarchive-vm)
- [`unroot`](#unroot)
- [`watchit`](#watchit)
- [`zfs-diagnose-busy`](#zfs-diagnose-busy)
- [`zfsaddisk`](#zfsaddisk)
- [`zfsallthepools`](#zfsallthepools)
- [`zfscleanup`](#zfscleanup)
- [`zfscleanupbadoffsiteholds`](#zfscleanupbadoffsiteholds)
- [`zfsdailybackup`](#zfsdailybackup)
- [`zfsdelallsnaps`](#zfsdelallsnaps)
- [`zfsdelfs`](#zfsdelfs)
- [`zfsdelholds`](#zfsdelholds)
- [`zfsfullcopy`](#zfsfullcopy)
- [`zfsgetashift`](#zfsgetashift)
- [`zfsgetsendsize`](#zfsgetsendsize)
- [`zfsgetsnapage`](#zfsgetsnapage)
- [`zfsholds`](#zfsholds)
- [`zfslistkeys`](#zfslistkeys)
- [`zfsloadkeys`](#zfsloadkeys)
- [`zfslockctl`](#zfslockctl)
- [`zfslockmanager-test`](#zfslockmanager-test)
- [`zfsmaketest`](#zfsmaketest-archived)
- [`zfsmassdelsnaps`](#zfsmassdelsnaps)
- [`zfsmount`](#zfsmount)
- [`zfsmountsnapshot`](#zfsmountsnapshot)
- [`zfsoffsiteretain`](#zfsoffsiteretain)
- [`zfsreadthru`](#zfsreadthru)
- [`zfsrecurse`](#zfsrecurse)
- [`zfsresizevol`](#zfsresizevol)
- [`zfsrestore`](#zfsrestore)
- [`zfsrestoresendstream`](#zfsrestoresendstream)
- [`zfsresume`](#zfsresume)
- [`zfsscruball`](#zfsscruball)
- [`zfssend`](#zfssend)
- [`zfssendoffsite`](#zfssendoffsite)
- [`zfssendrepo`](#zfssendrepo)
- [`zfssetarcsize`](#zfssetarcsize)
- [`zfsshowbigstuff`](#zfsshowbigstuff)
- [`zfsshowholds`](#zfsshowholds)
- [`zfsshowtuneables`](#zfsshowtuneables)
- [`zfsshowzpooldevices`](#zfsshowzpooldevices)
- [`zfsstatus`](#zfsstatus)
- [`zfsunmount`](#zfsunmount)
- [`zfswatcharc`](#zfswatcharc)

---

### `backup-installed-programs`

Saves a list of manually-installed apt packages to a file called
`installed-programs` in the current directory.

```bash
sudo backup-installed-programs
```

**Arguments:** none.

**Globals:** none.

Uses `apt-mark showmanual` to generate the list. Logs success or failure.
On failure, removes the partial output file.

**Called modules:** none.

**Data structures consumed / produced:** none.

**Return codes:** non-zero if `apt-mark` or output writing fails; partial output is removed.

---

### `check-prerequisites`

Validate that the host environment meets ZFS Utilities requirements.

```bash
sudo check-prerequisites [--single-node|--two-node] [--list-failures]
```

**Arguments:**

| Argument | Description |
| -------- | ----------- |
| `--single-node` | Check only prerequisites needed for single-node operation |
| `--two-node` | Check prerequisites for two-node (storage+compute) operation |
| `--list-failures` | Print machine-readable failures and exit |

**Globals:** none.

Checks the following categories: core ZFS utilities (`bash`, `zfs`, `zpool`,
`pv`, `rsync`), optional Proxmox VE, GTK GUI packages, two-node tools (`ssh`,
`scp`, `iscsiadm`), and documentation tools (`pip3`, `mkdocs`,
`mkdocs-material`).

**Called modules:** none.

**Data structures consumed / produced:** none.

**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | All required prerequisites are present |
| `1` | One or more required prerequisites are missing |

---

### `datesubtract`

Calculates the number of days, months, and years between two dates.

```bash
datesubtract "2025-01-01" "2026-01-01"
```

**Arguments:**

| Argument | Description                                   |
| -------- | --------------------------------------------- |
| `$1`     | Start date (any format accepted by `date -d`) |
| `$2`     | End date                                      |

**Globals:** none.

Outputs days, months (decimal), and years (decimal).

**Called modules:** none.

**Data structures consumed / produced:** none.


**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |

---

### `deploy-version`

Deploys the current repository state as a new versioned installation under
`/usr/local/lib/zfsutilities/versions/<version>/`. Does not activate the
version; use [`switch-version`](#switch-version) for that.

```bash
sudo ./deploy-version [version] [group ...]
```

**Arguments:**

| Argument | Default | Description |
| -------- | ------- | ----------- |
| `version` | contents of `./VERSION` | Version string to deploy |
| `group` | all groups in deploy.conf | Deployment group names from `/etc/zfsutilities-deploy.conf` |

**Globals:**

| Variable | Role | Reference |
| -------- | ---- | --------- |
| `NODE_MODE`, `STORAGE_HOST`, `COMPUTE_HOST` | Legacy remote-host fallback when no deploy.conf exists | [Node Configuration](../developer-guide/global-variables.md#node-configuration) |

**Called modules:**

| Script | Purpose |
| ------ | ------- |
| `10 Installers/desktop-launcher-lib.sh` | Desktop shortcut helpers |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `/etc/zfsutilities-deploy.conf` | Deployment group definitions | — |
| Node config | Legacy remote host list | [Node config](../developer-guide/data-structures.md#node-configuration-file-etczfsutilities-nodeconf) |
| `/usr/local/lib/zfsutilities/versions/<version>/` | Deployed version directory | — |

**Internal flow:**

1. Parse arguments; read `./VERSION` if no version is supplied.
2. Load `/etc/zfsutilities-deploy.conf` groups, or fall back to the node config for remote hosts.
3. Build the version directory, copy root-level scripts, and symlink two-node,
   clone, installer, and versioning scripts.
4. Copy project subdirectories (`06 Docs`, `07 GTK + Python`, etc.) and rebuild
   static docs.
5. Verify that critical scripts are present in the deployed `bin/` directory.
6. `rsync` the version directory to each remote host in the selected groups.

**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Deployment completed |
| `1` | Fatal error (wrong directory, missing version, unknown group, etc.) |

---

### `getlinecount`

Counts files and total lines in the project root directory (non-recursive).
Hard-coded to `/NFS1/dan(NFS1)/zfsutilities-dev`. Intended as a development
utility.

**Arguments:** none.

**Globals:** none.

**Called modules:** none.

**Data structures consumed / produced:** none.


**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |

---

### `git-release`

Bumps `VERSION`, commits all staged changes, and creates a git tag. Must be
run from a git repository.

```bash
./git-release <version> <commit-message>
```

**Arguments:**

| Argument | Description |
| -------- | ----------- |
| `version` | New version string (e.g. `1.2.0`) |
| `commit-message` | Message used for both the commit and the annotated tag |

**Globals:** none.

The script writes the new version to the `VERSION` file, runs `git add -A`,
`git commit`, and `git tag -a v<version>`. Pushing the result is left to the
caller.

**Called modules:** none.

**Data structures consumed / produced:**

| Structure | Role |
| --------- | ---- |
| `VERSION` | Updated with the new release version |
| Git repository | Commit and annotated tag are created |

**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Version bumped, committed, and tagged |
| `1` | Not a git repository or git operation failed |

---

### `PVE-send-to-archive`

Sends a single ZFS dataset to an archive file on disk using
`zfs send`. This creates a \*.zfssendstream file in the host's filesystem. Intended for long-term cold storage.

**Arguments:** none (configured via in-script variables).

**In-script variables** (set before running):

| Variable          | Description                                                                                                | Reference                                                                          |
| ----------------- | ---------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `$subtrees`       | List of ZFS pools/filesystems where the source dataset(s) resides                                          | —                                                                                  |
| `$includes`       | Substring list to match dataset names                                                                      | [Selection](../developer-guide/global-variables.md#dataset-and-snapshot-selection) |
| `$destinationdir` | Directory where the archive file will be placed                                                            | —                                                                                  |
| `$archivename`    | Short name of the output archive file                                                                      | —                                                                                  |
| `$proxmoxconfig`  | Path to the Proxmox VM configuration file. If specified, this file is stored along with the archive files. | —                                                                                  |

**Called modules:**

| Module | Purpose in this command |
| ------ | ----------------------- |
| [zfsbuildfsarray](modules.md#zfsbuildfsarray) | Build filtered dataset list from `$subtrees` and `$includes` |
| [zfscommsnap](modules.md#zfscommsnap) | Select the most recent common snapshot for each dataset |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `$fsarray` / `$fsarraylen` | Filtered datasets to archive | [$fsarray](../developer-guide/data-structures.md#fsarray-fsarraylen) |
| `$commsnap` | Most recent common snapshot name | [$commsnap](../developer-guide/global-variables.md#zfs-sendreceive) |

**Internal flow:**

1. For each subtree in `$subtrees`, call `buildfsarray`.
2. For each dataset in `$fsarray`, call `getcommonsnap` to select the snapshot to send.
3. Create the destination directory hierarchy if needed.
4. Run `zfs send -cw <dataset>@<snap> | pv | cat - > <archive>.zfssendstream`.
5. Copy the Proxmox VM config file into the same archive tree.


**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |
| non-zero | Invalid input or command failure. |

---

### `run-tests`

Discovers and executes the bash test suites in `tests/`.

```bash
./run-tests [-v|-q] [suite-name]
```

**Arguments:**

| Argument | Description |
| -------- | ----------- |
| `-v` / `--verbose` | Show all test output |
| `-q` / `--quiet` | Show only the summary |
| `suite-name` | Run a single suite (e.g. `test-zfsretain`) |

**Globals:** none. Sets `ZFSUTILITIES_TEST_RESULTS` internally for suite coordination.

**Called modules:** none.

**Data structures consumed / produced:**

| Structure | Role |
| --------- | ---- |
| `tests/test-*` | Test suite files discovered and executed |
| `/tmp/zfsutilities_test_results_*` | Per-suite result summaries aggregated by the harness |

**Internal flow:**

1. Parse options and optional suite name.
2. Discover test files or use the requested suite.
3. Run each suite as a separate `bash` process and capture its result record.
4. Print a pass/fail/skip summary and exit with the overall result.

**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | All tests passed |
| `1` | One or more tests failed |
| `2` | Unknown option or suite not found |

---

### `startdocserver`

Starts the documentation server on port `8000`. Serves the MkDocs
live-reload site; MkDocs is required.

```bash
./startdocserver [--restart] [path]
```

**Arguments:**

| Argument | Description |
| -------- | ----------- |
| `--restart` | Stop any existing server on port 8000 and start fresh |
| `path` | Accepted for compatibility; ignored by the server |

**Globals:** none.

**Called modules:**

| Module | Purpose |
| ------ | ------- |
| `bashinit` | Session log setup and `calledbybash` guard |

**Data structures consumed / produced:**

| Structure | Role |
| --------- | ---- |
| `~/docserver.log` | Server stdout/stderr |
| `06 Docs/site/` | Built static documentation site |
| `http://localhost:8000` | Documentation URL |

**Internal flow:**

1. Locate the docs directory relative to the script (`06 Docs` or `../06 Docs`).
2. Probe `localhost:8000` to see if a server is already running.
3. If the running server serves the wrong directory, stop it.
4. Start `mkdocs serve --livereload`.

**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Server started or already running |
| `1` | Docs directory not found or server could not start |

---

### `switch-version`

Activates a deployed version by updating production wiring: symlinks, `PATH`,
sudoers, `/root/bashinit`, library links, and desktop shortcuts.

```bash
sudo switch-version <version>|previous|--list|--uninstall
```

**Arguments:**

| Argument | Description |
| -------- | ----------- |
| `version` | Version string to activate |
| `previous` | Roll back to the previously active version |
| `--list` | List installed versions |
| `--uninstall` | Remove this version's production wiring |

**Globals:**

| Variable | Role |
| -------- | ---- |
| `ZFSUTILITIES_VERSION_BASE` | Override `/usr/local/lib/zfsutilities` (used by tests) |
| `ZFSUTILITIES_BASHINIT_LINK` | Override `/root/bashinit` target (used by tests) |
| `ZFSUTILITIES_PROFILE_FILE` | Override `/etc/profile.d/zfsutilities.sh` (used by tests) |
| `ZFSUTILITIES_SUDOERS_FILE` | Override `/etc/sudoers.d/zfsutilities` (used by tests) |
| `ZFSUTILITIES_NODE_LIB_LINK` | Override `/usr/local/lib/node-lib.sh` (used by tests) |
| `ZFSUTILITIES_TWO_NODE_LIB_LINK` | Override `/usr/local/lib/two-node-lib.sh` (used by tests) |
| `ZFSUTILITIES_LOCAL_BIN_DIR` | Override `/usr/local/bin` (used by tests) |

**Called modules:**

| Module / Script | Purpose |
| --------------- | ------- |
| [rootcheck](modules.md#rootcheck) | Verify root privileges |
| `10 Installers/desktop-launcher-lib.sh` | Desktop shortcut helpers |

**Data structures consumed / produced:**

| Structure | Role |
| --------- | ---- |
| `/usr/local/lib/zfsutilities/current` | Symlink to the active version |
| `/usr/local/lib/zfsutilities/previous` | Symlink to the prior version for rollback |
| `/root/bashinit` | Symlink to the active version's `bashinit` |
| `/etc/profile.d/zfsutilities.sh` | Adds the versioned `bin/` to `PATH` |
| `/etc/sudoers.d/zfsutilities` | Adds the versioned `bin/` to `secure_path` |
| `/usr/local/lib/node-lib.sh` | Symlink to the active version's node library |
| `/usr/local/lib/two-node-lib.sh` | Compatibility symlink to the node library |

**Internal flow:**

1. Parse the subcommand (`version`, `previous`, `--list`, `--uninstall`).
2. For `--list`, print installed versions and exit.
3. For `--uninstall`, remove wiring symlinks and desktop shortcuts.
4. For a version switch, call the prior version's `switch-version --uninstall`,
   record the current version as `previous`, and update the `current` symlink.
5. Re-execute the target version's `switch-version` so it installs its own wiring.
6. `install_wiring()` creates `bin/`, `PATH`, sudoers, `bashinit`, library, and desktop shortcuts.

**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Version activated, listed, or unwired |
| `1` | Version not found, missing previous version, or wiring error |

---

### `uninstall-version`

Removes a deployed version directory. Refuses to remove the currently active version.

```bash
sudo uninstall-version <version>
```

**Arguments:**

| Argument | Description |
| -------- | ----------- |
| `version` | Version string to remove |

**Globals:** none.

**Called modules:** none.

**Data structures consumed / produced:**

| Structure | Role |
| --------- | ---- |
| `/usr/local/lib/zfsutilities/versions/<version>/` | Removed if not the active version |
| `/usr/local/lib/zfsutilities/current` | Checked to prevent removing the active version |

**Internal flow:**

1. Validate root privileges and the version argument.
2. Refuse if the requested version is the current active version.
3. Prompt for confirmation.
4. `rm -rf` the version directory.

**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Version removed or operation aborted |
| `1` | Missing argument, version not found, or version is active |

---

### `unroot`

Relinquishes root privileges by switching to a normal user.

```bash
unroot username
```

**Arguments:**

| Argument | Default   | Description       |
| -------- | --------- | ----------------- |
| `$1`     | `$suuser` | User to switch to |

**Globals:**

| Variable  | Role                                 |
| --------- | ------------------------------------ |
| `$suuser` | Default user if `$1` is not provided |

Has no effect if not currently running as root.

**Called modules:** none.

**Data structures consumed / produced:** none.


**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |

---

### `watchit`

Displays a periodically-refreshing terminal-based view of ZFS pool and dataset status for a
given subtree. Refreshes every 30 seconds.

```bash
watchit pool-or-dataset
```

**Arguments:**

| Argument | Description              |
| -------- | ------------------------ |
| `$1`     | Pool or dataset to watch |

**Globals:** none.

Uses `Watchall/watchall` with `zpool list` and `zfs list` output.

**Called modules:**

| Script | Purpose |
| ------ | ------- |
| `Watchall/watchall` | Periodically display pool/dataset status |

**Data structures consumed / produced:** none.


**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |

---

### `zfsaddisk`

Adds a virtual disk to a Proxmox VM. Works around a Proxmox GUI issue where
incorrect disk numbers are sometimes assigned.

```bash
sudo zfsaddisk <vmid> <disk-number> <storage-name> <size-GiB>
```

**Arguments:**

| Argument | Description                                                          |
| -------- | -------------------------------------------------------------------- |
| `$1`     | Proxmox VM ID (numeric)                                              |
| `$2`     | Disk number for the new disk (must be higher than any existing disk) |
| `$3`     | Proxmox storage name where the disk will reside                      |
| `$4`     | Size of the new disk in GiB                                          |

**Globals:** none.

Prompts for confirmation before issuing the `qm set` command.

**Called modules:** none.

**Data structures consumed / produced:** none.


**Internal flow:**

1. Validate the VM ID, disk number, storage name, and size.
2. Prompt for confirmation before issuing the `qm set` command.
3. Run `qm set <vmid> --scsi<disk-number> <storage>:<size-GiB>`.

**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |

---

### `zfsallthepools`

Compatibility shim that fills `$zfspoolarray` from the JSON config. New scripts
should source `zfsconfig` directly and call `poolarray()`.

```bash
source zfsallthepools
# $zfspoolarray is now populated
```

**Arguments:** none.

**Globals:** none.

**Called modules:**

| Module | Purpose |
| ------ | ------- |
| [zfsconfig](modules.md#zfsconfig) | Read the pool list from the JSON config |

**Data structures produced:**

| Structure | Reference |
| --------- | --------- |
| `$zfspoolarray` | [$zfspoolarray](../developer-guide/data-structures.md#zfspoolarray) |

**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Pool array loaded successfully |

---

### `zfscleanup`

Applies retention policies to one pool, to the pools registered in the JSON
config, or — when no pools are configured — to all online pools.

```bash
sudo zfscleanup <pool> only <label> [overrides]
```

**Arguments:**

| Argument | Default                                                   | Description                                                     |
| -------- | --------------------------------------------------------- | --------------------------------------------------------------- |
| `$1`     | pools from JSON config, or all online pools if none exist | Pool or subtree to clean up                                     |
| `$2`     | recurse                                                   | `'only'` = do not recurse                                       |
| `$3`     | —                                                         | Snapshot label that must match (required)                       |
| `$4`     | —                                                         | Override string (see [`zfsoverrides`](modules.md#zfsoverrides)) |

**Behavior:**

- If `$1` is given, only that pool/subtree is processed.
- Otherwise, `zfscleanup` reads `config.pools` via [`poolarray`](modules.md#zfsconfig).
  If the configured pool list is empty, it falls back to `zpool list -Ho name`
  so retention is not silently skipped.
- Pools in the list that are not currently online are skipped.
- If `retain` returns a non-zero code for a dataset (lock conflict, missing
  policy, or other error), `zfscleanup` logs a warning and continues with the
  next dataset/pool instead of aborting the run.

**Globals:**

| Variable                    | Role                                                              | Reference                                                                     |
| --------------------------- | ----------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| `$autoproceed`              | `'Y'` = skip prompts                                              | [Execution Control](../developer-guide/global-variables.md#execution-control) |
| `$dryrun`                   | `'Y'` = report without deleting                                   | [Execution Control](../developer-guide/global-variables.md#execution-control) |
| `$releaseholds`             | `'Y'` = release holds before deletion                             | [Execution Control](../developer-guide/global-variables.md#execution-control) |
| `$leadingqualifiestodelete` | Passed to `zfsretain` for `checkagainst` counterpart construction | [Retention](../developer-guide/global-variables.md#retention)                 |

Calls [`zfsretain`](modules.md#zfsretain) for each pool.

**Called modules:**

| Module | Purpose in this command |
| ------ | ----------------------- |
| [zfsconfig](modules.md#zfsconfig) | Read registered pools via `poolarray()` |
| [zfsbuildfsarray](modules.md#zfsbuildfsarray) | Build the per-pool dataset list |
| [zfsretain](modules.md#zfsretain) | Apply retention policy to each dataset |
| [zfsoverrides](modules.md#zfsoverrides) | Apply command-line parameter overrides |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `$zfspoolarray` | Pool names to process | [$zfspoolarray](../developer-guide/data-structures.md#zfspoolarray) |
| `$fsarray` / `$fsarraylen` | Datasets within each pool | [$fsarray](../developer-guide/data-structures.md#fsarray-fsarraylen) |
| JSON config `pools` | Source for `poolarray()` | [JSON config](../developer-guide/data-structures.md#json-config-rootconfigzfsutilitiesjson) |

**Internal flow:**

1. Apply defaults for `$autoproceed`, `$dryrun`, `$releaseholds`.
2. If `$1` is given, use it as the only pool; otherwise call `poolarray()` to read `config.pools`.
3. If the configured pool list is empty, fall back to `zpool list -Ho name` so retention is not silently skipped.
4. For each online pool, build `fsarray` and call `retain` for every dataset.
5. Pools that are not online are skipped.

**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed normally. |
| `8` | No label was provided in `$3`. |

---

### `zfs-diagnose-busy`

Diagnoses why a ZFS dataset or snapshot cannot be destroyed. Called
automatically by `zfsdelsnap`, `zfsdelfs`, `remove-vm-disk`, `archive-vm`, and
`clone-vm` whenever `zfs destroy` fails with a "dataset is busy" error.

```bash
source $mydir/zfs-diagnose-busy
diagnose_dataset_busy <dataset_or_snapshot> [stderr_from_failed_destroy]
```

**Checks performed (in order):**

| Check                | What it looks for                                             |
| -------------------- | ------------------------------------------------------------- |
| Clone dependents     | `zfs list -o clones` shows non-`-` values                     |
| ZFS holds            | `zfs holds` lists tags on the snapshot                        |
| Mounted / open files | `mounted=yes` plus `fuser`/`lsof` on the mountpoint           |
| Active send/receive  | `receive_resume_token` present, or `zfs send` process running |
| Bookmarks            | `zfs list -t bookmark` shows references to the snapshot       |
| iSCSI LUN            | `targetcli` shows the zvol as a backstore/LUN                 |
| Running VM           | `qm status` reports `running` for the VM ID                   |
| NFS/SMB share        | `sharenfs` or `sharesmb` is not `off`                         |

If no specific cause is found, a fallback message suggests checking for open
files via `fuser` or `lsof`, or verifying whether a pool scrub/resilver is in
progress.

The Python GUI equivalent is `gui_helpers.diagnose_dataset_busy()`, used by
dataset and snapshot delete actions.

**Called modules:** none.

**Data structures consumed / produced:** none.

**Internal flow:**

Checks are performed in order until a likely cause is found:

1. Clone dependents (`zfs list -o clones`).
2. ZFS holds (`zfs holds`).
3. Mounted filesystem with open files (`fuser`/`lsof`).
4. Active send/receive (`receive_resume_token` or running `zfs send`).
5. Bookmarks referencing the snapshot.
6. iSCSI LUN backstore.
7. Running Proxmox VM (`qm status`).
8. NFS/SMB share (`sharenfs`/`sharesmb`).

If no cause is identified, a fallback message suggests further manual investigation.


**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |

---

### `zfscleanupbadoffsiteholds`

Removes incorrectly self-referencing holds from an offsite pool. A
self-referencing hold is one where the hold name is `offsite-<pool>` on a
snapshot that already resides in `<pool>` — a bug from earlier versions of
`applyholds`.

```bash
sudo zfscleanupbadoffsiteholds <pool> [dryrun]
```

**Arguments:**

| Argument | Description                                            |
| -------- | ------------------------------------------------------ |
| `$1`     | Pool to inspect                                        |
| `$2`     | `dryrun` = show what would be removed without removing |

**Globals:** none.

Lists snapshot holds via `zfs list -Hrt snapshot ... | xargs zfs holds -H`,
then releases any hold whose name matches `offsite-<pool>` on a snapshot within
that same pool.

**Called modules:** none.

**Data structures consumed / produced:** none.

**Internal flow:**

1. Validate that `$1` names an existing pool.
2. List every snapshot in the pool and query its holds.
3. For each hold matching `offsite-*`, compare the pool embedded in the hold tag with the snapshot's own pool.
4. If they match (self-referencing hold), release the hold unless `dryrun` was requested.

**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Scan completed. |
| `1` | Pool name missing or pool not found. |

---

### `zfsdailybackup`

Main daily backup orchestrator. Runs the full backup sequence:

1. Pull rsync backups from remote hosts (`rocky`, `COMPUTE_HOST`, `STORAGE_HOST`)
2. Snapshot `threeamigos/proxmox` and copy to `fivebays`
3. Snapshot `NVME1` and copy to `fivebays`
4. Apply retention policies to all affected pools

```bash
sudo zfsdailybackup [overrides]
```

**Arguments:**

| Argument | Description                                                                                                     |
| -------- | --------------------------------------------------------------------------------------------------------------- |
| `$1`     | Optional override string passed to [`zfsoverrides`](modules.md#zfsoverrides) as `name='value'; name='value'; …` |

**In-script defaults (overridable):**

| Variable                     | Default | Purpose                                                          |
| ---------------------------- | ------- | ---------------------------------------------------------------- |
| `pull_rocky`                 | `'Y'`   | Pull rsync backup from host `rocky`                              |
| `pull_tweety`                | `'Y'`   | Pull rsync backup from `$COMPUTE_HOST` (two-node only)           |
| `pull_stewie`                | `'Y'`   | Pull rsync backup from `$STORAGE_HOST`                           |
| `backup_threeamigos_proxmox` | `'Y'`   | Snapshot and copy `threeamigos/proxmox` → `fivebays`             |
| `backup_NVME1`               | `'Y'`   | Snapshot and copy `NVME1` → `fivebays`                           |
| `prune`                      | `'Y'`   | Run retention via `zfscleanup` on affected pools after the sends |
| `autoresume`                 | `'Y'`   | Allow resumable-receive tokens to be picked up                   |
| `receive_F_option`           | `'F'`   | Force rollback of destination modifications on receive           |

**Global variables read:**

| Variable                                    | Role                                                                               | Reference                                                                          |
| ------------------------------------------- | ---------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `$dryrun`                                   | `'Y'` = simulate without writing (skips rsync, sends, prune, and snapfile cleanup) | [Execution Control](../developer-guide/global-variables.md#execution-control)      |
| `$nextsnap`                                 | Generated by `zfssnapbuild` at start of run; shared across all sends               | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)             |
| `$releaseholds`                             | Passed to `zfscleanup` during prune                                                | [Execution Control](../developer-guide/global-variables.md#execution-control)      |
| `$includes`, `$excludes`, `$startwith`      | Dataset filters forwarded to `zfs-send-receive`                                    | [Selection](../developer-guide/global-variables.md#dataset-and-snapshot-selection) |
| `NODE_MODE`, `STORAGE_HOST`, `COMPUTE_HOST` | Node-config vars that gate the two-node rsync-pull steps                           | [Node Configuration](../developer-guide/global-variables.md#node-configuration)    |

Example overrides:

```bash
sudo zfsdailybackup "backup_NVME1='N'; prune='N'"
sudo zfsdailybackup "dryrun='Y'"
```

**Called modules:**

| Module / Script | Purpose in this command |
| --------------- | ----------------------- |
| [zfssnapbuild](modules.md#zfssnapbuild) | Generate the shared snapshot name `$nextsnap` |
| [zfs-send-receive](modules.md#zfs-send-receive) | Copy `threeamigos/proxmox` → `fivebays` and `NVME1` → `fivebays` |
| [zfsoverrides](modules.md#zfsoverrides) | Apply command-line parameter overrides |
| [zfscleanup](commands.md#zfscleanup) | Prune snapshots after sends |
| `backup-installed-programs` | Save package list on remote/local hosts |
| `rsync-dailybackup` | Perform rsync pulls from remote/local hosts |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `$nextsnap` | Shared snapshot name used for both send steps | [$nextsnap](../developer-guide/global-variables.md#zfs-sendreceive) |
| `/tmp/zfsnextsnap_*` | Persisted snapshot name, reused if run again | [snapfile](../developer-guide/data-structures.md#snapshot-name-persistence) |
| JSON config `backup` | Source of override values from the GUI | [JSON config](../developer-guide/data-structures.md#json-config-rootconfigzfsutilitiesjson) |
| Node config | Gates two-node rsync pulls | [Node config](../developer-guide/data-structures.md#node-configuration-file-etczfsutilities-nodeconf) |

**Internal flow:**

1. Generate `$nextsnap` via `zfssnapbuild`.
2. Apply overrides from `$1`.
3. Optionally pull rsync backups from `rocky`, `$COMPUTE_HOST` (two-node only), and `$STORAGE_HOST`.
4. Snapshot and copy `threeamigos/proxmox` → `fivebays`.
5. Snapshot and copy `NVME1` → `fivebays`.
6. Remove the snapfile unless in dry-run mode.
7. If `$prune='Y'`, run `cleanup '' '' 'dailybackup'` to apply retention policies.


**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |
| non-zero | Invalid input or command failure. |

---

### `zfsdelallsnaps`

Deletes all snapshots of a dataset, with safety checks via [`zfsdelsnap`](modules.md#zfsdelsnap).

```bash
sudo zfsdelallsnaps <dataset> [overrides]
```

**Arguments:**

| Argument | Description                                            |
| -------- | ------------------------------------------------------ |
| `$1`     | Dataset (or subtree) whose snapshots should be deleted |
| `$2`     | Optional override string                               |

**Globals:**

| Variable                           | Role                                                                | Reference                                                                          |
| ---------------------------------- | ------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `$includes`, `$excludes`, `$depth` | Forwarded to `zfsbuildfsarray` (with `buildfsarraytype='snapshot'`) | [Selection](../developer-guide/global-variables.md#dataset-and-snapshot-selection) |
| `$releaseholds`                    | `'Y'` = release holds before deletion                               | [Execution Control](../developer-guide/global-variables.md#execution-control)      |
| `$autoproceed`                     | `'Y'` = skip per-deletion prompts                                   | [Execution Control](../developer-guide/global-variables.md#execution-control)      |
| `$dryrun`                          | `'Y'` = report without deleting                                     | [Execution Control](../developer-guide/global-variables.md#execution-control)      |

Each snapshot is individually verified via [`zfscheckagainst`](modules.md#zfscheckagainst)
before deletion.

If a snapshot cannot be destroyed, [`zfs-diagnose-busy`](modules.md#zfs-diagnose-busy)
is automatically called to diagnose the specific cause.

**Return code:**

- `0` — all snapshots were deleted successfully, or there were no snapshots to delete.
- `1` — one or more snapshots could not be deleted.

**Called modules:**

| Module | Purpose in this command |
| ------ | ----------------------- |
| [zfsdelsnap](modules.md#zfsdelsnap) | Delete each snapshot with safety checks |
| [zfsoverrides](modules.md#zfsoverrides) | Apply command-line parameter overrides |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `$snaparray` | Local snapshot list built by this script | [$snaparray](../developer-guide/data-structures.md#snaparray-bktsnaparray-zfsretain) |

**Internal flow:**

1. Build a local `$snaparray` from `zfs list -t snapshot` for the target dataset.
2. Optionally filter by the substring in `$2`.
3. Prompt for confirmation (unless `$autoproceed='Y'`).
4. Call `delsnap` for each snapshot, passing `minage=0` and `'nocheckagainst'` so the explicit deletion is not blocked by age or counterpart checks.

**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | All snapshots deleted, or none existed. |
| `1` | One or more snapshots could not be deleted. |

---

### `zfsdelfs`

Deletes a dataset along with all of its snapshots and holds.

```bash
sudo zfsdelfs <subtree> [includes] [excludes] [startwith] [overrides]
```

This is the ordinary way to destroy a ZFS dataset (or a filtered subtree of
datasets). For non-VM datasets the operation is a straightforward
`zfs destroy`; the iSCSI handling described below only applies to zvols that
follow the `vm-<N>-disk-<N>` naming convention in a two-node configuration.

**Arguments:**

| Argument | Description                                   |
| -------- | --------------------------------------------- |
| `$1`     | Subtree to delete                             |
| `$2`     | Optional includes filter (sets `$includes`)   |
| `$3`     | Optional excludes filter (sets `$excludes`)   |
| `$4`     | Optional startwith filter (sets `$startwith`) |
| `$5`     | Optional overrides                            |

**Globals:**

| Variable                                         | Role                                                                                   | Reference                                                                          |
| ------------------------------------------------ | -------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `$includes`, `$excludes`, `$startwith`, `$depth` | Forwarded to `zfsbuildfsarray`                                                         | [Selection](../developer-guide/global-variables.md#dataset-and-snapshot-selection) |
| `$autoproceed`, `$dryrun`, `$releaseholds`       | Execution control passed through to `zfsdelallsnaps`                                   | [Execution Control](../developer-guide/global-variables.md#execution-control)      |
| `NODE_MODE`, `COMPUTE_HOST`                      | Determines whether iSCSI teardown/rebuild is attempted, and how `qm status` is queried | [Node Configuration](../developer-guide/global-variables.md#node-configuration)    |

**Data structures produced:**

| Structure                                                                                  | Reference                                                                                                          |
| ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| [`ISCSI_TEARDOWN`](../developer-guide/data-structures.md#iscsi_teardown-associative-array) | Populated before `zfs destroy`; consumed by `zfs-send-receive` to rebuild LUNs after the replacement `zfs receive` |

Calls `zfsdelallsnaps` first to clear snapshots, then destroys the dataset.
For VM-disk zvols in two-node mode it automatically tears down the matching
iSCSI LUN/backstore before `zfs destroy` and records the teardown so that
`zfs-send-receive` can rebuild the LUN afterwards. During teardown it removes
the backstore from `/etc/rtslib-fb-target/expected-backstores.txt` and, if the
zvol is encrypted, from `/etc/iscsi-encrypted-luns.conf`. The `zfs-send-receive`
rebuild path re-adds those entries after the replacement `zfs receive` so the
manifests remain consistent.

**Clone dependency check:** If any dataset in the deletion list has ZFS clone
dependents (another zvol was created from one of its snapshots), `zfsdelfs`
aborts before touching anything and displays a `[ZFS clone dependents — cannot
delete]` annotation. Run [`promote-vm-clone`](two-node.md#promote-vm-clone-both)
on a dependent VM first to cut the dependency, then retry.

**Destroy diagnostics:** If `zfs destroy` fails (e.g. "dataset is busy"),
`zfsdelfs` automatically calls [`zfs-diagnose-busy`](#zfs-diagnose-busy) to
report the specific cause — holds, open files, iSCSI LUNs, running VMs, etc.

**Called modules:**

| Module | Purpose in this command |
| ------ | ----------------------- |
| [zfsbuildfsarray](modules.md#zfsbuildfsarray) | Build bottom-up dataset list for deletion |
| [zfsdelallsnaps](commands.md#zfsdelallsnaps) | Remove all snapshots before destroying each dataset |
| [zfsoverrides](modules.md#zfsoverrides) | Apply command-line parameter overrides |
| [zfs-diagnose-busy](modules.md#zfs-diagnose-busy) | Diagnose `zfs destroy` failures |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `$fsarray` / `$fsarraylen` | Datasets selected for deletion | [$fsarray](../developer-guide/data-structures.md#fsarray-fsarraylen) |
| `ISCSI_TEARDOWN` | Records iSCSI LUNs torn down so `zfs-send-receive` can rebuild them | [ISCSI_TEARDOWN](../developer-guide/data-structures.md#iscsi_teardown-associative-array) |
| Node config | Determines single-node vs two-node iSCSI behavior | [Node config](../developer-guide/data-structures.md#node-configuration-file-etczfsutilities-nodeconf) |

**Internal flow:**

1. Source the node config and determine `NODE_MODE`.
2. Save the caller's filter state, then set `$includes`, `$excludes`, `$startwith` from arguments.
3. Build `fsarray` bottom-up so descendants are destroyed before parents.
4. For each dataset:
   - Abort if any snapshot has clone dependents.
   - In two-node mode, tear down matching iSCSI LUN/backstore for `vm-<N>-disk-<N>` zvols and record the teardown in `ISCSI_TEARDOWN`.
   - Call `delallsnaps` with `releaseholds`.
   - Run `zfs destroy`; on failure call `diagnose_dataset_busy` and abort.
5. Restore the caller's filter state.

**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | All datasets deleted successfully. |
| `4` | No qualifying datasets found. |
| `8` | Missing subtree, clone dependents, running VM, or destroy failure. |

---

### `zfsdelholds`

Releases ZFS snapshot holds matching an optional pattern across a subtree.

```bash
sudo zfsdelholds <subtree> [snap-prefix] [depth]
```

**Arguments:**

| Argument | Description                                            |
| -------- | ------------------------------------------------------ |
| `$1`     | Subtree to process                                     |
| `$2`     | Optional leading substring of snapshot names to filter |
| `$3`     | Optional recursion depth (overrides `$depth`)          |

**Globals:**

| Variable       | Role                                            | Reference                                                                          |
| -------------- | ----------------------------------------------- | ---------------------------------------------------------------------------------- |
| `$depth`       | Default recursion depth if `$3` is not supplied | [Selection](../developer-guide/global-variables.md#dataset-and-snapshot-selection) |
| `$autoproceed` | `'Y'` = skip per-hold prompts                   | [Execution Control](../developer-guide/global-variables.md#execution-control)      |

**Called modules:**

| Module | Purpose in this command |
| ------ | ----------------------- |
| [zfsdelallholds](modules.md#zfsdelallholds) | Release all holds on a snapshot |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `$snaparray` | Local snapshot list | [$snaparray](../developer-guide/data-structures.md#snaparray-bktsnaparray-zfsretain) |

**Internal flow:**

1. Build `$snaparray` from `zfs list -rt snapshot` for the subtree.
2. Optionally filter snapshots whose names start with `$2`.
3. Call `delallholds` for each matching snapshot.


**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |

---

### `zfsfullcopy`

Performs a two-step full dataset restore. Intended to be called by other
scripts (not run directly — use [`zfsrestore`](#zfsrestore) for interactive use).

Step 1: Full copy from the oldest available snapshot

Step 2: Incremental copy to pull in all remaining snapshots

**Arguments:** none (configured via globals).

**Globals:**

| Variable                            | Required | Role                                                                     | Reference                                                                     |
| ----------------------------------- | -------- | ------------------------------------------------------------------------ | ----------------------------------------------------------------------------- |
| `$restorefs`                        | yes      | Dataset to restore (source)                                              | —                                                                             |
| `$destfs`                           | yes      | Destination pool/subpool                                                 | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)        |
| `$sourcefsremovequalifiers`         | no       | Leading qualifiers to strip from `$restorefs`before prepending `$destfs` | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)        |
| `$nextsnap`                         | no       | If set, limits copy to this snapshot                                     | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)        |
| `$label`                            | no       | Snapshot label to match                                                  | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)        |
| `$autoproceed`, `$force`, `$dryrun` | no       | Forwarded to `zfs-send-receive`                                          | [Execution Control](../developer-guide/global-variables.md#execution-control) |

**Called modules:**

| Module | Purpose in this command |
| ------ | ----------------------- |
| [zfs-send-receive](modules.md#zfs-send-receive) | Perform full then incremental copy |
| [zfsoverrides](modules.md#zfsoverrides) | Apply command-line parameter overrides |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `$nextsnap` | Optional upper snapshot bound | [$nextsnap](../developer-guide/global-variables.md#zfs-sendreceive) |

**Internal flow:**

1. If `$nextsnap` is empty, generate one with `zfssnapbuild`.
2. **Part 1** — full copy from the oldest snapshot (`doincrementals='N'`, `commsnap_mostrecent='OLDEST'`, `force='Y'`, `releaseholds='Y'`).
3. **Part 2** — incremental copy with intermediates to catch up to the newest snapshot (`doincrementals='Y'`, `dointermediates='Y'`).
4. Re-apply caller overrides between parts so Part 1 defaults do not leak into Part 2.


**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |
| non-zero | Invalid input or command failure. |

---

### `zfsgetashift`

Displays the ashift value and corresponding block size for a disk partition.

```bash
sudo zfsgetashift /dev/sdd1
```

**Arguments:**

| Argument | Description                |
| -------- | -------------------------- |
| `$1`     | Disk partition device path |

**Globals:** none.

| ashift | Block size |
| ------ | ---------- |
| 9      | 512 B      |
| 12     | 4 KiB      |
| 13     | 8 KiB      |

Useful when creating a new pool. `ashift` is the power of 2 that will be the pool's basic block size. (2^ashift)

**Called modules:** none.

**Data structures consumed / produced:** none.


**Internal flow:**

1. Validate that `$1` is a block device path.
2. Run `zdb -l <device>` to read the vdev label.
3. Extract the `ashift` value and print it with the corresponding block size.

**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |
| non-zero | Invalid input or command failure. |

---

### `zfsgetsnapage`

Returns the age of a ZFS snapshot in days.

```bash
zfsgetsnapage pool/dataset@snapshot
```

**Arguments:**

| Argument | Description   |
| -------- | ------------- |
| `$1`     | Snapshot name |

**Globals:** none.

Uses `zfs get creation` (epoch seconds) and calculates the difference from
the current time. Can be sourced by other scripts (`source $mydir/zfsgetsnapage`)
and called as `getsnapage <snapshot>`.

**Called modules:** none.

**Data structures consumed / produced:** none.


**Internal flow:**

1. Parse the snapshot name from `$1`.
2. Query `zfs get creation -Hp <snapshot>` for the creation epoch.
3. Compute the difference from the current time and print the age in days.

**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |
| non-zero | Invalid input or command failure. |

---

### `zfsgetsendsize`

Calculates the size of a ZFS send stream for a given snapshot.

```bash
zfsgetsendsize pool/dataset@snapshot
```

**Arguments:**

| Argument | Description   |
| -------- | ------------- |
| `$1`     | Snapshot name |

**Globals:** none.

Outputs both raw bytes and human-readable size (e.g., `8925341712 8.3G`).
Returns an empty string if the size cannot be determined.

**Called modules:** none.

**Data structures consumed / produced:** none.


**Internal flow:**

1. Run `zfs send -nPc <snapshot>` to request the send size.
2. Parse the raw byte count from the dry-run output.
3. Print the raw size and a human-readable equivalent.

**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Size printed successfully. |
| non-zero | `zfs send` failed or snapshot not found. |

---

### `zfsholds`

Lists all snapshot holds in a subtree.

```bash
zfsholds <subtree> [depth]
```

**Arguments:**

| Argument | Description                               |
| -------- | ----------------------------------------- |
| `$1`     | Subtree to inspect                        |
| `$2`     | Optional depth limit (overrides `$depth`) |

**Globals:**

| Variable | Role                    | Reference                                                                          |
| -------- | ----------------------- | ---------------------------------------------------------------------------------- |
| `$depth` | Default recursion depth | [Selection](../developer-guide/global-variables.md#dataset-and-snapshot-selection) |

See also: [`zfsshowholds`](#zfsshowholds) for a simpler version without depth support.

**Called modules:** none.

**Data structures consumed / produced:** none.

**Internal flow:**

1. Run `zfs list -rt snapshot <subtree>` to enumerate snapshots.
2. Pipe the snapshot names through `xargs zfs holds -H`.
3. Print the resulting hold tags.


**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |

---

### `zfslistkeys`

Lists ZFS datasets with available encryption keys (keystatus = available,
keylocation != prompt).

```bash
sudo zfslistkeys [dataset]
```

**Arguments:**

| Argument | Description                                |
| -------- | ------------------------------------------ |
| `$1`     | Optional dataset or pool to limit the scan |

**Globals:** none. If `$1` is omitted, iterates over all imported pools.

**Called modules:** none.

**Data structures consumed / produced:** none.


**Internal flow:**

1. If `$1` is supplied, scan only that dataset or pool.
2. Otherwise iterate over every imported pool.
3. List datasets whose `keystatus` is `available` and whose `keylocation` is not `prompt`.

**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |
| non-zero | Invalid input or command failure. |

---

### `zfsloadkeys`

Loads ZFS encryption keys from a USB key device labeled `ZFSkeys`.

```bash
sudo zfsloadkeys
```

**Arguments:** none.

**Globals:** none.

Mounts `/dev/disk/by-label/ZFSkeys` at `/mnt/ZFSkeys`, runs `zfs load-key -a`
and `zfs mount -a`, then unmounts and LUKS-closes the key device.

**Called modules:** none.

**Data structures consumed / produced:** none.

**Internal flow:**

1. Mount the USB key device labeled `ZFSkeys` at `/mnt/ZFSkeys`.
2. Run `zfs load-key -a` and `zfs mount -a`.
3. Unmount the key device and close the LUKS mapping.


**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |

---

### `zfslockctl`

Command-line tool for inspecting and managing ZFS dataset locks.

```bash
sudo zfslockctl <command> [args]
```

**Subcommands:**

| Command   | Arguments          | Description                                        |
| --------- | ------------------ | -------------------------------------------------- |
| `list`    | `[dataset]`        | List active locks (optionally filtered by dataset) |
| `status`  | `<dataset>`        | Check lock status for a dataset                    |
| `release` | `<lock-id>`        | Force-release a lock                               |
| `cleanup` | —                  | Remove stale locks (held by dead processes)        |
| `wait`    | `<dataset> <type>` | Wait until a dataset becomes available             |

Lock types: `r` (shared read), `w` (exclusive write), `x` (exclusive destroy).

**Globals:** none.

**Data structures:**

| Structure                                                      | Reference                         |
| -------------------------------------------------------------- | --------------------------------- |
| [Lock files](../developer-guide/data-structures.md#lock-files) | Read from `/run/lock/zfs/.locks/` |

See also: [`zfslockmanager`](modules.md#zfslockmanager).

**Called modules:**

| Module | Purpose in this command |
| ------ | ----------------------- |
| [zfslockmanager](modules.md#zfslockmanager) | Acquire, release, and inspect ZFS dataset locks |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| Lock files | Read from and removed under `/run/lock/zfs/.locks/` | [Lock files](../developer-guide/data-structures.md#lock-files) |


**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |

---

### `zfslockmanager-test`

Automated test suite for [`zfslockmanager`](modules.md#zfslockmanager). Runs 33 tests covering:

- Basic acquire/release
- Same-dataset conflicts (r/w/x combinations)
- Hierarchy conflicts (ancestor/descendant)
- Stale lock detection and cleanup
- Re-entrant locking (same PID)
- Concurrent access blocking
- Path encoding (`%2F`, `%40`)
- `zfslockctl` CLI commands
- Headless/non-interactive abort behavior
- Retry and wait polling behavior

```bash
sudo zfslockmanager-test
```

**Arguments:** none.

**Globals:** none.

**Called modules:**

| Module | Purpose in this command |
| ------ | ----------------------- |
| [zfslockmanager](modules.md#zfslockmanager) | Exercises lock acquire, release, conflict detection, and stale cleanup |
| [zfslockctl](../developer-guide/lock-manager.md#zfslockctl) | Tests the lock-manager CLI subcommands |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| Lock files | Created, read, and removed under `/run/lock/zfs/.locks/` during tests | [Lock files](../developer-guide/data-structures.md#lock-files) |

All 33 tests should pass.

---

### `zfsmaketest` (Archived)

> **Inactive.** This script has been moved to `03 Stash/zfsmaketest` and is not
> currently in use. It will be revisited when work on the automated test
> framework resumes.

Creates test datasets and runs copy scenarios to validate
[`zfs-send-receive`](modules.md#zfs-send-receive). Creates `nvme/test` and
`nvme/test2`.

```bash
sudo zfsmaketest
```

**Arguments:** none (in-script variables).

**In-script variables** (set before running):

| Variable               | Values            | Role                                                                                     | Reference                                                              |
| ---------------------- | ----------------- | ---------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `$doincrementals`      | `'Y'` / `'N'`     | Full vs incremental copies                                                               | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive) |
| `$dointermediates`     | `'Y'` / `'N'`     | Include intermediate snapshots                                                           | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive) |
| `$commsnap_mostrecent` | `'OLDEST'` / `''` | `'OLDEST'` = start from oldest snapshot on source; otherwise most recent common snapshot | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive) |

**Called modules:**

| Module | Purpose in this command |
| ------ | ----------------------- |
| [zfslockmanager](modules.md#zfslockmanager) | Exercise all lock-manager operations |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| Lock files | Created and removed under `/run/lock/zfs/.locks/` | [Lock files](../developer-guide/data-structures.md#lock-files) |

**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | All tests passed. |
| non-zero | One or more tests failed. |

---

### `zfsmassdelsnaps`

Mass-delete snapshots across one or more pools. This is the backend for the
Retention tab's **Mass Delete** button; it can also be run directly from the
command line.

```bash
sudo zfsmassdelsnaps <pool> [pool ...]
```

**Arguments:**

| Argument | Description                |
| -------- | -------------------------- |
| `$1 ...` | One or more pool names     |

**Globals:**

| Variable                    | Role                                                                          | Reference                                                                          |
| --------------------------- | ----------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `snapshot_label`            | Snapshot label that must match (required)                                     | —                                                                                  |
| `includes[]`                | Optional dataset include filters                                              | [Selection](../developer-guide/global-variables.md#dataset-and-snapshot-selection) |
| `excludes[]`                | Optional dataset exclude filters                                              | [Selection](../developer-guide/global-variables.md#dataset-and-snapshot-selection) |
| `startwith`                 | Optional dataset start-with filter                                            | [Selection](../developer-guide/global-variables.md#dataset-and-snapshot-selection) |
| `endwith`                   | Optional dataset end-with filter                                              | [Selection](../developer-guide/global-variables.md#dataset-and-snapshot-selection) |
| `snapshot_has`              | Optional substring that must appear in the full snapshot name                 | —                                                                                  |
| `ignore_retention_policies` | `'Y'` = delete all matching snapshots regardless of retention policy          | —                                                                                  |
| `releaseholds`              | `'Y'` = release holds before deletion (ignore mode only)                      | [Execution Control](../developer-guide/global-variables.md#execution-control)      |
| `dryrun`                    | `'Y'` = report without deleting                                               | [Execution Control](../developer-guide/global-variables.md#execution-control)      |
| `autoproceed`               | `'Y'` = skip per-snapshot hold-release prompts (ignore mode) and approval prompts in underlying `zfscleanup` (respect mode) | [Execution Control](../developer-guide/global-variables.md#execution-control)      |

**Modes:**

- **Ignore retention policies** (`ignore_retention_policies='Y'`) — Lists every
  snapshot whose label matches `snapshot_label` and any include/exclude/startwith/endwith
  filters, optionally filtered by `snapshot_has`. The list is followed by an
  estimate of the disk space that would be freed (sum of each snapshot's `used`
  property). After approval, each snapshot is destroyed with
  `zfsdelsnap ... nocheckagainst`, bypassing the usual `zfscheckagainst` safety
  check. This mode is dangerous: it can delete the last common snapshot needed
  for an incremental backup. Holds are released automatically when
  `releaseholds='Y'` is set, without a prompt per snapshot.
- **Respect retention policies** (`ignore_retention_policies='N'`, the default) —
  Runs `zfscleanup` in dry-run mode for each pool, parses the candidate list,
  prints a space estimate, asks for approval, then runs `zfscleanup` for real.
  This is equivalent to a normal prune, just batched across the selected pools.

In both modes, **Dry Run** lists the affected snapshots and the estimated space
without deleting them.

**Called modules:**

| Module | Purpose in this command |
| ------ | ----------------------- |
| [zfsbuildfsarray](modules.md#zfsbuildfsarray) | Build the per-pool dataset list |
| [zfsdelsnap](modules.md#zfsdelsnap) | Delete individual snapshots in ignore mode |
| [zfscleanup](commands.md#zfscleanup) | Apply retention policy in respect mode |

**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0`  | Completed successfully, was cancelled, or no snapshots matched |
| `8`  | Fatal error (no pool or no label specified) |

---

### `zfsmount`

Mounts or unmounts all filesystems in a subtree.

```bash
sudo zfsmount <mount|unmount> <subtree>
```

**Arguments:**

| Argument | Description          |
| -------- | -------------------- |
| `$1`     | `mount` or `unmount` |
| `$2`     | Subtree to process   |

**Globals:**

| Variable       | Role                            | Reference                                                                     |
| -------------- | ------------------------------- | ----------------------------------------------------------------------------- |
| `$autoproceed` | `'Y'` = skip per-dataset prompt | [Execution Control](../developer-guide/global-variables.md#execution-control) |

When mounting: targets unmounted (`mounted=no`) filesystems.
When unmounting: targets mounted filesystems and volumes.

**Called modules:** none.

**Data structures consumed / produced:** none.

**Internal flow:**

1. Build a list of filesystems (or volumes) in the subtree via `zfs list`.
2. For `mount`, target datasets with `mounted=no`.
3. For `unmount`, target datasets with `mounted=yes` and volumes.


**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |

---

### `zfsmountsnapshot`

Example transcript showing how to browse ZFS snapshots through a dataset's `.zfs/snapshot` directory. This file is **not an executable command**; it is included as documentation.

```bash
cat /usr/local/lib/zfsutilities/current/bin/zfsmountsnapshot
```

**Arguments:** none.

**Globals:** none.

**Called modules:** none.

**Data structures consumed / produced:** none.

**Return codes:** not applicable.

---

### `zfsreadthru`

Reads all snapshots in a dataset tree, forcing ZFS to verify every block.
Useful for locating unrecovered data errors when `zpool status -v` is
uninformative.

```bash
sudo zfsreadthru <dataset> [overrides] [first-snapshot] [last-snapshot]
```

**Arguments:**

| Argument | Description                                                     |
| -------- | --------------------------------------------------------------- |
| `$1`     | Head of tree to read (required)                                 |
| `$2`     | Override string (see [`zfsoverrides`](modules.md#zfsoverrides)) |
| `$3`     | First snapshot to read (default: oldest)                        |
| `$4`     | Last snapshot to read (default: newest)                         |

**Globals:**

| Variable                                                     | Role                           | Reference                                                                          |
| ------------------------------------------------------------ | ------------------------------ | ---------------------------------------------------------------------------------- |
| `$includes`, `$excludes`, `$startwith`, `$endwith`, `$depth` | Forwarded to `zfsbuildfsarray` | [Selection](../developer-guide/global-variables.md#dataset-and-snapshot-selection) |

**Called modules:**

| Module | Purpose in this command |
| ------ | ----------------------- |
| [zfsbuildfsarray](modules.md#zfsbuildfsarray) | Build ordered snapshot list |
| [zfsoverrides](modules.md#zfsoverrides) | Apply command-line parameter overrides |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `$fsarray` / `$fsarraylen` | Snapshots ordered by creation | [$fsarray](../developer-guide/data-structures.md#fsarray-fsarraylen) |

**Internal flow:**

1. Set `buildfsarraytype='snapshot'` and `sortby='creation'`.
2. Build `fsarray` for the requested dataset tree.
3. Determine `$firstsnap` (oldest) and `$lastsnap` (newest).
4. Part 1: full `zfs send -wc $firstsnap | pv | cat > /dev/null`.
5. Part 2: incremental `zfs send -wc -I $firstsnap $lastsnap | pv | cat > /dev/null`.


**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |
| non-zero | Invalid input or command failure. |

---

### `zfsrecurse`

Runs any ZFS command recursively over a dataset tree. **Work in progress —
exits immediately with an error message if run.**

**Called modules:** (intended) `zfsbuildfsarray`.

**Data structures consumed / produced:** none — script is a stub.


**Internal flow:**

Exits immediately with an error message. The intended implementation would build a dataset list with `zfsbuildfsarray` and run the supplied ZFS command for each dataset.

**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |
| non-zero | Invalid input or command failure. |

---

### `zfsrestore`

Interactive two-step full dataset restore. Configured by editing variables
inside the script.

```bash
sudo zfsrestore [overrides-part1]
```

**Arguments:**

| Argument | Description                                    |
| -------- | ---------------------------------------------- |
| `$1`     | Optional override string applied before Step 1 |

**In-script variables** (edit before running):

| Variable                    | Role                                                                      | Reference                                                                          |
| --------------------------- | ------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `$restoresourcefs`          | Source dataset (backup location)                                          | —                                                                                  |
| `$sourcefsremovequalifiers` | Leading qualifiers to strip                                               | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)             |
| `$destfs`                   | Pool/subpool to prepend after stripping leading qualifiers.               | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)             |
| `$label`                    | Snapshot label to restore                                                 | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)             |
| `$includes`, `$excludes`    | Dataset filters                                                           | [Selection](../developer-guide/global-variables.md#dataset-and-snapshot-selection) |
| `$nextsnap`                 | Snapshot name limit (optional; `'notneeded'` to look up newest on source) | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)             |

Step 1 does a full copy from the oldest snapshot. 

Step 2 does an incremental-with-intermediates
to catch up to the newest.

**Called modules:**

| Module | Purpose in this command |
| ------ | ----------------------- |
| [zfssnapbuild](modules.md#zfssnapbuild) | Inhibited (`$nextsnap='notneeded'`) |
| [zfs-send-receive](modules.md#zfs-send-receive) | Perform full then incremental copy |
| [zfsoverrides](modules.md#zfsoverrides) | Apply Part 1 / Part 2 overrides |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `$nextsnap` | Set to `'notneeded'` so `zfs-send-receive` uses existing snapshots | [$nextsnap](../developer-guide/global-variables.md#zfs-sendreceive) |

**Internal flow:**

1. Apply Part 1 overrides from `$1`.
2. **Part 1** — full copy from oldest snapshot (`doincrementals='N'`, `force='Y'`, `releaseholds='Y'`, `commsnap_mostrecent='OLDEST'`).
3. Re-apply `$1` and apply `$2` overrides for Part 2.
4. **Part 2** — incremental copy with intermediates to newest snapshot (`doincrementals='Y'`, `dointermediates='Y'`).
5. Prompt before Part 2 unless `$autoproceed='Y'`.


**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |
| non-zero | Invalid input or command failure. |

---

### `zfsrestoresendstream`

Restores a ZFS dataset from a send stream saved to disk (a `.zfssendstream`
file). Configured by editing variables inside the script.

**Arguments:** none (in-script variables).

**In-script variables:**

| Variable     | Role                                              |
| ------------ | ------------------------------------------------- |
| `$vm`        | Proxmox VM ID string (e.g., `vm-205`)             |
| `$vmname`    | VM name (used to construct source directory path) |
| `$destfs`    | Destination dataset                               |
| `$sourcedir` | Directory containing the `.zfssendstream` files   |

**Globals:**

| Variable       | Role                                       | Reference                                                                     |
| -------------- | ------------------------------------------ | ----------------------------------------------------------------------------- |
| `$force`       | `'Y'` = destroy destination before receive | [Execution Control](../developer-guide/global-variables.md#execution-control) |
| `$autoproceed` | `'Y'` = skip confirmations                 | [Execution Control](../developer-guide/global-variables.md#execution-control) |

**Called modules:** none.

**Data structures consumed / produced:** none.

**Internal flow:**

1. Locate `.zfssendstream` files matching `$filepattern` in `$sourcedir`.
2. Optionally destroy the destination if `$force='Y'`.
3. Pipe each stream through `pv` into `zfs receive`.


**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |
| non-zero | Invalid input or command failure. |

---

### `zfsresizevol`

Resizes a ZFS volume. **Work in progress — exits immediately with an error
message if run.**

**Called modules:** none.

**Data structures consumed / produced:** none — script is a stub.


**Internal flow:**

Exits immediately with an error message. The intended implementation would resize a ZFS volume after validating the new size.

**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |
| non-zero | Invalid input or command failure. |

---

### `zfsresume`

Resumes an interrupted ZFS receive that has a `receive_resume_token`.

```bash
sudo zfsresume <destination-dataset>
```

**Arguments:**

| Argument | Description                                           |
| -------- | ----------------------------------------------------- |
| `$1`     | Destination dataset carrying a `receive_resume_token` |

**Globals:** none.

Retrieves the resume token, validates it, and either resumes the transfer or
reports that the token is stale (and clears it with `zfs receive -A`).

**Called modules:** none.

**Data structures consumed / produced:** none.

**Internal flow:**

1. Validate that `$1` names a dataset.
2. Extract the `receive_resume_token` from the destination dataset.
3. Run `zfs send -nP -t <token>` to validate the token.
4. If validation fails with `no longer exists`, `@--head--`, or `Invalid argument`, clear the stale token with `zfs receive -A`.
5. Otherwise report that the token appears valid.

**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Token validated or cleared. |
| `8` | Missing dataset argument or token retrieval failed. |

---

### `zfsscruball`

Scrubs all known ZFS pools. Supports pause and resume.

```bash
sudo zfsscruball [start|pause|resume]
```

**Arguments:**

| Argument | Default | Description                  |
| -------- | ------- | ---------------------------- |
| `$1`     | `start` | `start` / `pause` / `resume` |

**Globals:** none.

State is tracked in `/tmp/zfsscruball.state` during a run.

**Called modules:**

| Module | Purpose in this command |
| ------ | ----------------------- |
| [zfsoverrides](modules.md#zfsoverrides) | Apply command-line parameter overrides |
| [zfsfindoffsitepool](modules.md#zfsfindoffsitepool) | Include the online offsite pool in the scrub list |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `/tmp/zfsscruball.state` | Tracks completed pools during resume | [scrub state file](../developer-guide/data-structures.md#zfsscruball-state-file) |

**Internal flow:**

1. Parse mode (`start`, `pause`, `resume`, or a pool list).
2. **start**: clear state file, build pool list from `zpool list` plus offsite pool, run up to `$parallel` scrubs concurrently.
3. **pause**: run `zpool scrub -p` on every pool with a scrub in progress.
4. **resume**: load completed pools from state file, prioritize paused scrubs, then scrub remaining pools while skipping completed ones.

**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Mode handled. |

---

### `zfssend`

Snapshots and copies a dataset. Configured by editing variables inside the
script. Primarily used for ad-hoc sends during development and testing.

**Arguments:** none (in-script variables).

**In-script variables:**

| Variable          | Role                                   | Reference                                                                     |
| ----------------- | -------------------------------------- | ----------------------------------------------------------------------------- |
| `$sourcefs`       | Source dataset                         | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)        |
| `$destfs`         | Destination pool                       | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)        |
| `$doincrementals` | `'Y'` = incremental, `'N'` = full copy | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)        |
| `$autoproceed`    | `'Y'` = no prompts                     | [Execution Control](../developer-guide/global-variables.md#execution-control) |

**Called modules:**

| Module | Purpose in this command |
| ------ | ----------------------- |
| [zfssnapbuild](modules.md#zfssnapbuild) | Generate the snapshot name to send |
| [zfs-send-receive](modules.md#zfs-send-receive) | Perform the actual copy |
| [zfsoverrides](modules.md#zfsoverrides) | Apply command-line parameter overrides |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `$nextsnap` | New snapshot created before send | [$nextsnap](../developer-guide/global-variables.md#zfs-sendreceive) |

**Internal flow:**

1. Generate `$nextsnap` via `zfssnapbuild`.
2. Apply overrides from `$1`.
3. Call `send-receive` to copy `$sourcefs` to `$destfs`.


**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |
| non-zero | Invalid input or command failure. |

---

### `zfssendoffsite`

Copies datasets to the currently-online offsite pool (`z22tb` or `z40tb`).
Runs multiple steps depending on configuration.

```bash
sudo zfssendoffsite [overrides]
```

**Arguments:**

| Argument | Description                                                              |
| -------- | ------------------------------------------------------------------------ |
| `$1`     | Optional override string (see [`zfsoverrides`](modules.md#zfsoverrides)) |

**In-script defaults (overridable):**

| Variable     | Default | Purpose                                      |
| ------------ | ------- | -------------------------------------------- |
| `step1`      | `'Y'`   | Copy `temp` → offsite                        |
| `step2`      | `'Y'`   | Copy `threeamigos` → `fivebays`              |
| `step3`      | `'Y'`   | Copy `NVME1` → `fivebays`                    |
| `step4`      | `'Y'`   | Copy `fivebays` → offsite                    |
| `applyholds` | `'Y'`   | Apply `offsite-<pool>` holds after each step |

**Globals:**

| Variable                                 | Role                               | Reference                                                                     |
| ---------------------------------------- | ---------------------------------- | ----------------------------------------------------------------------------- |
| `$autoproceed`, `$dryrun`, `$force`      | Forwarded to `zfs-send-receive`    | [Execution Control](../developer-guide/global-variables.md#execution-control) |
| `$label`, `$originlabel`, `$targetlabel` | Set to `offsite` for this workflow | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)        |

| Step | Source        | Destination |
| ---- | ------------- | ----------- |
| 1    | `temp`        | `<offsite>` |
| 2    | `threeamigos` | `fivebays`  |
| 3    | `NVME1`       | `fivebays`  |
| 4    | `fivebays`    | `<offsite>` |

After each step, applies named holds to source and destination snapshots to help
prevent accidental deletion.

When `$dryrun='Y'`, send/receive is simulated and hold application is skipped.

```bash
sudo zfssendoffsite "dryrun='Y'"
```

**Called modules:**

| Module | Purpose in this command |
| ------ | ----------------------- |
| [zfshold](modules.md#zfshold) | Apply source/destination snapshot holds |
| [zfs-send-receive](modules.md#zfs-send-receive) | Copy datasets across the backup chain |
| [zfssnapbuild](modules.md#zfssnapbuild) | Generate the shared `@offsite` snapshot name |
| [zfsoverrides](modules.md#zfsoverrides) | Apply command-line parameter overrides |
| [zfsfindoffsitepool](modules.md#zfsfindoffsitepool) | Determine which offsite pool is online |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `$nextsnap` | Shared `@offsite` snapshot name | [$nextsnap](../developer-guide/global-variables.md#zfs-sendreceive) |
| `$fsarray` / `$fsarraylen` | Datasets copied in each step, used by `applyholds` | [$fsarray](../developer-guide/data-structures.md#fsarray-fsarraylen) |
| `/tmp/zfsnextsnap_*` | Persisted snapshot name for reruns | [snapfile](../developer-guide/data-structures.md#snapshot-name-persistence) |

**Internal flow:**

1. Set `label='@offsite'` and generate `$nextsnap`.
2. Call `findoffsitepool` to select `z22tb` or `z40tb`.
3. Apply overrides from `$1`.
4. Execute enabled steps:
   - Step 1: `temp` → `<offsite>`
   - Step 2: `threeamigos` → `fivebays` (filtered to `proxmox`)
   - Step 3: `NVME1` → `fivebays`
   - Step 4: `fivebays` → `<offsite>` (filtered to `threeamigos/proxmox` and `NVME1/proxmox`)
5. After each successful step, call `applyholds` to place `offsite-<pool>` holds on source and destination snapshots.

**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed. |
| `8` | No offsite pool is online. |

---

### `zfsoffsiteretain`

Prunes `@offsite` snapshots from source pools, respecting retention policies
and protecting snapshots that offline offsite pools still need as incremental
bases.

```bash
sudo zfsoffsiteretain [overrides]
```

**Arguments:**

| Argument | Description              |
| -------- | ------------------------ |
| `$1`     | Optional override string |

**Globals:**

| Variable        | Role                                               | Reference                                                                     |
| --------------- | -------------------------------------------------- | ----------------------------------------------------------------------------- |
| `$dryrun`       | `'Y'` = report only                                | [Execution Control](../developer-guide/global-variables.md#execution-control) |
| `$autoproceed`  | `'Y'` = skip prompts                               | [Execution Control](../developer-guide/global-variables.md#execution-control) |
| `$releaseholds` | Set to `'Y'` internally when invoking `zfscleanup` | [Execution Control](../developer-guide/global-variables.md#execution-control) |

Dynamically discovers all online pools that contain `@offsite` snapshots,
then runs `zfscleanup` with label `offsite` and `releaseholds='Y'` against
each one. No pool names are hardcoded — any pool with offsite snapshots is
included automatically.

Safety is provided by [`zfscheckagainst`](modules.md#zfscheckagainst): when a
counterpart pool is offline, hold-tag verification determines whether
deletion is safe. Retention counts come from each pool's retention policy
(`s` bucket) in the JSON config. Supports a dry run:

```bash
sudo zfsoffsiteretain "dryrun='Y'"
```

**Called modules:**

| Module | Purpose in this command |
| ------ | ----------------------- |
| [zfscleanup](commands.md#zfscleanup) | Prune `@offsite` snapshots per pool |
| [zfsoverrides](modules.md#zfsoverrides) | Apply command-line parameter overrides |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| `$offsite_pools` | Online pools discovered to contain `@offsite` snapshots | — |
| JSON config `retention` | Per-pool `s` bucket policy used by `zfscleanup` | [JSON config](../developer-guide/data-structures.md#json-config-rootconfigzfsutilitiesjson) |

**Internal flow:**

1. Set `$releaseholds='Y'` by default.
2. Discover all online pools that contain snapshots matching `@offsite-*`.
3. For each such pool, call `cleanup '<pool>' '' 'offsite'`.
4. Offline pools are logged and skipped.

---

### `zfssendrepo`

Example script that `rsync`s the local repository to a remote host. Edit the default paths inside the script or pass them on the command line.

```bash
./zfssendrepo <host> [<source-dir> [<dest-dir>]]
```

**Arguments:**

| Argument | Default | Description |
| -------- | ------- | ----------- |
| `host` | — | Remote host to receive the rsync |
| `source-dir` | `/path/to/local/zfsutilities` | Local repository path |
| `dest-dir` | `/home/admin/ZFSutilities` | Remote destination path |

**Globals:** none.

**Called modules:** none.

**Data structures consumed / produced:** none.

**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Rsync completed successfully |
| non-zero | `rsync` exit code on failure |

---

### `zfssetarcsize`

Sets the ZFS ARC maximum size both immediately (sysfs) and persistently
(`/etc/modprobe.d/zfs.conf` + `update-initramfs`). Edit the `GiB` variable
inside the script before running.

**Arguments:** none (in-script variable).

**In-script variables:**

| Variable | Role                      |
| -------- | ------------------------- |
| `$GiB`   | ARC max size in gibibytes |

**Called modules:** none.

**Data structures consumed / produced:** none.


**Internal flow:**

1. Validate that the `GiB` variable is set.
2. Write the ARC max size in bytes to `/sys/module/zfs/parameters/zfs_arc_max`.
3. Persist the setting in `/etc/modprobe.d/zfs.conf`.
4. Run `update-initramfs` so the limit applies at boot.

**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |
| non-zero | Invalid input or command failure. |

---

### `zfsshowbigstuff`

Shows the largest (or smallest) datasets within a pool or dataset, sorted by
multiple metrics.

```bash
zfsshowbigstuff <pool-or-dataset> [largest|smallest] [count]
```

**Arguments:**

| Argument | Default   | Description                |
| -------- | --------- | -------------------------- |
| `$1`     | —         | Pool or dataset to inspect |
| `$2`     | `largest` | `largest` or `smallest`    |
| `$3`     | `5`       | Number of results to show  |

**Globals:** none.

Sorts by: `used`, `usedds`, `usedsnap`, `written`, `quota`, `refer`,
`refquota`, `reservation`.

**Called modules:** none.

**Data structures consumed / produced:** none.

**Internal flow:**

1. Run `zfs list` for the target pool or dataset.
2. For each dataset, read `used`, `usedds`, `usedsnap`, `written`, `quota`,
   `refer`, `refquota`, and `reservation`.
3. Sort by each property and report the largest or smallest datasets.


**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |

---

### `zfsshowholds`

Lists all snapshot holds for a dataset or subtree.

```bash
zfsshowholds <dataset>
```

**Arguments:**

| Argument | Description        |
| -------- | ------------------ |
| `$1`     | Dataset or subtree |

**Globals:** none.

Simple wrapper around `zfs list ... | xargs zfs holds`. For depth control,
use [`zfsholds`](#zfsholds) instead.

**Called modules:** none.

**Data structures consumed / produced:** none.

**Internal flow:**

Simple wrapper: `zfs list -rt snapshot <dataset> | xargs zfs holds -H`. For depth control see [`zfsholds`](#zfsholds).


**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |

---

### `zfsshowtuneables`

Verifies that `/etc/modprobe.d/zfs.conf` is present, correctly formatted, and
embedded in the initramfs. Shows current ZFS module parameters.

```bash
zfsshowtuneables
```

**Arguments:** none.

**Globals:** none.

**Called modules:** none.

**Data structures consumed / produced:** none.


**Internal flow:**

1. Verify that `/etc/modprobe.d/zfs.conf` exists and is non-empty.
2. Confirm the file is embedded in the initramfs.
3. Display current ZFS module parameters from `/sys/module/zfs/parameters/`.

**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |
| non-zero | Invalid input or command failure. |

---

### `zfsshowzpooldevices`

Lists the physical devices in a ZFS pool with vendor, model, size, and serial
number.

```bash
sudo zfsshowzpooldevices <pool>
```

**Arguments:**

| Argument | Description |
| -------- | ----------- |
| `$1`     | Pool name   |

**Globals:** none.

**Called modules:** none.

**Data structures consumed / produced:** none.


**Internal flow:**

1. Validate that `$1` names an imported pool.
2. Run `zpool status -LPs <pool>` to list physical devices.
3. Print vendor, model, size, and serial number for each device.

**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |
| non-zero | Invalid input or command failure. |

---

### `zfsstatus`

Auto-refreshing ZFS status display (pool list + pool status). Refreshes
every 60 seconds. Implemented as a one-liner that calls `Watchall/watchall`.

```bash
zfsstatus
```

**Arguments:** none.

**Globals:** none.

**Called modules:**

| Script | Purpose |
| ------ | ------- |
| `Watchall/watchall` | Auto-refresh pool list and status |

**Data structures consumed / produced:** none.


**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |

---

### `zfsunmount`

Unmounts all filesystems in a subtree.

```bash
zfsunmount <subtree>
```

**Arguments:**

| Argument | Description        |
| -------- | ------------------ |
| `$1`     | Subtree to unmount |

**Globals:** none.

Simpler than `zfsmount unmount` — no interactivity.

**Called modules:** none.

**Data structures consumed / produced:** none.


**Internal flow:**

1. List filesystems under the given subtree with `zfs list`.
2. Run `zfs unmount` on each mounted filesystem.

**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |
| non-zero | Invalid input or command failure. |

---

### `zfswatcharc`

Monitors ZFS ARC statistics with hit rates and throughput, updated at a
configurable interval.

```bash
zfswatcharc [interval-seconds]
```

**Arguments:**

| Argument | Default | Description                 |
| -------- | ------- | --------------------------- |
| `$1`     | `2`     | Refresh interval in seconds |

**Globals:** none.

Displays ARC size, target, hit rate, miss rate, and hits/misses per second.

**Called modules:** none.

**Data structures consumed / produced:** none.

**Internal flow:**

Reads `/proc/spl/kstat/zfs/arcstats` at the configured interval and prints ARC size, target, hit rate, miss rate, and hits/misses per second.


**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |

---

### `archive-vm`

Archives a VM before destruction. Discovers clone dependencies, optionally
promotes them, archives zvols and Proxmox config, verifies archive integrity,
and optionally removes the VM.

```bash
sudo archive-vm <vmid>
```

**Arguments:**

| Argument | Description                         |
| -------- | ----------------------------------- |
| `$1`     | VM ID of the template VM to archive |

**Flow:**

1. **Discover clones** — Finds all VMs whose zvols depend on snapshots of the VM's zvols
2. **Promote clones** — If any clones exist, asks whether to promote each one (calls
   `promote-vm-clone`), severing the dependency so the VM can be removed
3. **Discover referenced zvols** — Reads `/etc/pve/qemu-server/<vmid>.conf` and resolves each
   referenced disk to its zvol. In single-node mode this parses the local ZFS disk lines; in
   two-node mode it resolves iSCSI target/LUN pairs on the storage host. Any orphaned zvols
   that match the VM ID but are not referenced in the config are reported as warnings and
   are not archived.
4. **Archive zvols** — For each referenced disk, runs `zfs send -cw <snapshot>` into a new ZFS
   dataset under the archive base, setting `volblocksize=1M` for space efficiency. Saves the
   original `volblocksize` to a `.original_volblocksize` sidecar and the disk's Proxmox config
   info (disk key, LUN, target) to a `.disk_info` sidecar.
5. **Archive config** — Copies `/etc/pve/qemu-server/<vmid>.conf` into the archive mount
6. **Verify** — Confirms all archived datasets and the config file exist and have expected sizes
7. **Remove VM** — Asks whether to remove the VM; if yes, removes the Proxmox config
   and destroys each referenced zvol (including iSCSI teardown via `remove-vm-disk` in
   two-node mode)

**Globals:** node-config globals only (see [Two-Node Infrastructure Commands](two-node.md)).

**Called modules:**

| Script | Purpose in this command |
| ------ | ----------------------- |
| `promote-vm-clone` | Sever clone dependencies before removal |
| `remove-vm-disk` | Remove VM disks in two-node mode |
| [zfs-diagnose-busy](modules.md#zfs-diagnose-busy) | Diagnose destroy failures in single-node mode |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| Node config | Determines single-node vs two-node paths | [Node config](../developer-guide/data-structures.md#node-configuration-file-etczfsutilities-nodeconf) |
| JSON config `archive_path` | Default archive base | [JSON config](../developer-guide/data-structures.md#json-config-rootconfigzfsutilitiesjson) |
| `/etc/pve/qemu-server/<vmid>.conf` | Proxmox VM config archived and optionally removed | — |

**Internal flow:**

1. Discover VMs whose zvols depend on snapshots of the target VM's zvols.
2. Prompt to promote each dependent clone.
3. Read `/etc/pve/qemu-server/<vmid>.conf` and resolve only the referenced disks to zvols,
   warning about any orphaned zvols that are skipped.
4. Archive each referenced zvol with `zfs send -cw` into a dataset under the archive base,
   preserving original `volblocksize` in sidecars.
5. Copy the Proxmox config into the archive.
6. Verify archive integrity.
7. Optionally remove the VM (iSCSI teardown in two-node mode, direct destroy in single-node
   mode).


**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |
| non-zero | Invalid input or command failure. |

---

### `unarchive-vm`

Restores an archived VM from archive: recreates zvols with their original
`volblocksize`, rebuilds iSCSI infrastructure (two-node), and restores the Proxmox
config with updated disk lines.

```bash
sudo unarchive-vm <vmid> [archive_base] [--new-vmid <new_vmid>]
```

**Arguments:**

| Argument         | Description                                                                       |
| ---------------- | --------------------------------------------------------------------------------- |
| `vmid`           | VM ID of the archived VM to restore                                                |
| `archive_base`   | Optional ZFS dataset that contains the archive (defaults to JSON-configured path)  |
| `--new-vmid`     | Optional new VM ID to use for restored zvols, iSCSI resources, and Proxmox config  |

**Flow:**

1. **Discover archive** — Finds archived zvol datasets and the Proxmox config under the archive base
2. **Validate** — Checks that destination zvols and Proxmox config do not already exist; verifies
   `.original_volblocksize` and `.disk_info` sidecar files are present. If the original `vmid` is
   already in use and `--new-vmid` was not supplied, the script prompts for a new VM ID or lets
   you cancel.
3. **Restore zvols** — Sends each archived zvol back to its path, restoring the original
   `volblocksize` from the sidecar. When `--new-vmid` is used, the destination zvol path uses the
   new VM ID.
4. **Rebuild iSCSI** (two-node) — Creates backstores and LUNs for each restored zvol using the
   chosen VM ID, updates the expected-backstores manifest and encrypted-luns config
5. **Restore config** — Copies the archived Proxmox config to `/etc/pve/qemu-server/<vmid>.conf`
   (or `<new_vmid>.conf` when applicable). In two-node mode, rewrites each disk line with the new
   LUN number using the `.disk_info` sidecar mapping. When restoring under a new VM ID, single-node
   disk lines are rewritten to reference the new VM ID and `vmgenid`/`smbios1` UUIDs are regenerated
   to avoid duplicate identifiers.
6. **Rescan** (two-node) — Triggers iSCSI rescan on the compute host

**Globals:** node-config globals only.

**Called modules:**

| Script | Purpose in this command |
| ------ | ----------------------- |
| `rescan-storage` | Trigger compute-host iSCSI rescan |
| `safe-iscsi-save` | Persist restored iSCSI configuration |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| Node config | Determines two-node iSCSI behavior | [Node config](../developer-guide/data-structures.md#node-configuration-file-etczfsutilities-nodeconf) |
| JSON config `archive_path` | Default archive base | [JSON config](../developer-guide/data-structures.md#json-config-rootconfigzfsutilitiesjson) |
| `/etc/rtslib-fb-target/expected-backstores.txt` | Updated with restored backstores | [expected-backstores manifest](../developer-guide/data-structures.md#iscsi-expected-backstores-manifest) |
| `/etc/iscsi-encrypted-luns.conf` | Updated for restored encrypted LUNs | [encrypted-LUNs config](../developer-guide/data-structures.md#iscsi-encrypted-luns-config) |

**Internal flow:**

1. Discover archived zvol datasets and Proxmox config under the archive base.
2. Validate that destination zvols/config do not already exist; read sidecars.
3. Send archived zvols back to their original (or new VM ID) paths, restoring original `volblocksize`.
4. In two-node mode, recreate backstores/LUNs and update iSCSI manifests.
5. Restore/rewrite Proxmox config with updated disk lines.
6. Trigger iSCSI rescan on the compute host.



**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully. |
| non-zero | Invalid input or command failure. |


### `remove-vm`

Removes a VM's zvols and Proxmox config without archiving. Scans all pools for
`vm-<vmid>-disk-*` zvols, lists them along with any iSCSI target/LUN mappings,
stops the VM if it is running, asks for confirmation, then destroys each zvol
using `zfsdelfs`. Finally removes the Proxmox VM definition.

```bash
sudo remove-vm <vmid>
```

**Arguments:**

| Argument | Description                |
| -------- | -------------------------- |
| `$1`     | VM ID to remove            |

**Flow:**

1. **Discover zvols** — Scans all pools for zvols matching `vm-<vmid>-disk-<N>`.
   In two-node mode this runs on the storage host.
2. **Collect iSCSI info** (two-node) — Looks up the target and LUN for each
   backstore derived from the zvol name.
3. **Stop VM** — If a Proxmox config exists and the VM is running, it is stopped.
4. **Confirm** — Lists the zvols (with sizes and iSCSI info) and asks whether to
   proceed.
5. **Destroy zvols** — Calls `zfsdelfs` on each zvol with `autoproceed='Y'` so
   only one confirmation is required. `zfsdelfs` handles snapshots, holds, clone
   dependents, and iSCSI teardown.
6. **Save iSCSI config / rescan** (two-node) — Persists the updated targetcli
   configuration and rescans the compute host.
7. **Remove config** — Deletes `/etc/pve/qemu-server/<vmid>.conf`.

**Globals:** node-config globals only.

**Called modules:**

| Script | Purpose in this command |
| ------ | ----------------------- |
| `zfsdelfs` | Destroy each zvol and its snapshots/holds, handling iSCSI teardown |
| `safe-iscsi-save` (two-node) | Persist iSCSI configuration after teardown |
| `rescan-storage` (two-node) | Refresh compute-host device view |

**Data structures consumed / produced:**

| Structure | Role | Reference |
| --------- | ---- | --------- |
| Node config | Determines single-node vs two-node paths | [Node config](../developer-guide/data-structures.md#node-configuration-file-etczfsutilities-nodeconf) |
| `/etc/pve/qemu-server/<vmid>.conf` | Removed if present | — |

**Return codes:**

| Code | Meaning |
| ---- | ------- |
| `0` | Completed successfully (or nothing to remove). |
| non-zero | Invalid input or command failure. |

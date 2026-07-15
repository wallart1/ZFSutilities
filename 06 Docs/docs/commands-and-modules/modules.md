# Modules

Scripts intended to be `source`d by other scripts. They define functions or data used by callers. Most can still be run directly for testing thanks to the `if calledbybash` pattern.

Cross-references: globals mentioned per entry are documented in full on the
[Global Variables](../developer-guide/global-variables.md) page; shared
arrays and on-disk tables are on [Data Structures](../developer-guide/data-structures.md).

## Jump to

- [`bashinit`](#bashinit)
- [`bashdebug`](#bashdebug)
- [`bashfatal`](#bashfatal)
- [`bashreturn`](#bashreturn)
- [`bashsetx`](#bashsetx)
- [`rootcheck`](#rootcheck)
- [`zfsconfig`](#zfsconfig)
- [`zfsbuildfsarray`](#zfsbuildfsarray)
- [`zfscheckagainst`](#zfscheckagainst)
- [`zfscheckrunningvms`](#zfscheckrunningvms)
- [`zfscommsnap`](#zfscommsnap)
- [`zfs-diagnose-busy`](#zfs-diagnose-busy)
- [`zfsdelallholds`](#zfsdelallholds)
- [`zfsdelallholdssubtree`](#zfsdelallholdssubtree)
- [`zfsdelsnap`](#zfsdelsnap)
- [`zfsfindoffsitepool`](#zfsfindoffsitepool)
- [`zfshold`](#zfshold)
- [`zfslockmanager`](#zfslockmanager)
- [`zfsoverrides`](#zfsoverrides)
- [`zfsremoveleadingqualifiers`](#zfsremoveleadingqualifiers)
- [`zfsretain`](#zfsretain)
- [`zfs-send-receive`](#zfs-send-receive)
- [`zfssnapbuild`](#zfssnapbuild)

---

### `bashinit`

Initialization and logging helper sourced by nearly every bash script and
module in the project. It is normally loaded as `source ~/bashinit` followed by
a call to `bashinit()`.

```bash
source ~/bashinit
bashinit
source $mydir/rootcheck
rootcheck
```

**Functions:**

| Function      | Purpose                                                                                 |
| ------------- | --------------------------------------------------------------------------------------- |
| `bashinit`              | Sets `$mydir` to the caller's directory and auto-creates a session log for CLI scripts |
| `log_msg`               | Logs messages with `file:line:` prefix to stderr and to the session log                 |
| `msg_prefix`            | Emits the same `file:line:` prefix without the message body                             |
| `calledbybash`          | Returns true when the current file was executed directly (not sourced)                  |
| `ask_yn`                | Prompts for yes/no and validates the response                                           |
| `find_zfsutility_script`| Locates a sibling script/library across repo or deployed layouts; prints absolute path  |

**Globals / environment:**

| Variable                         | Role                                                              | Reference                                                                 |
| -------------------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------- |
| `$mydir`                         | Directory of the currently-running script                         | [Infrastructure](../developer-guide/global-variables.md#infrastructure)   |
| `$ZFSUTILITIES_LOG_DIR`          | Directory for session log files (default `/var/log/zfsutilities/sessions`) | [Infrastructure](../developer-guide/global-variables.md#infrastructure)   |
| `$ZFSUTILITIES_LOG_FILE`         | Path of the active session log (set by `bashinit`)                | [Session log index](../developer-guide/data-structures.md#session-log-index-varlogzfsutilitiessessionslog_indexjson) |
| `$ZFSUTILITIES_LOG_INHERIT`      | `'Y'` to reuse a parent runner's log instead of creating a new one | [Session log index](../developer-guide/data-structures.md#session-log-index-varlogzfsutilitiessessionslog_indexjson) |
| `$ZFSUTILITIES_HEADLESS`         | When `'Y'`, suppresses interactive prompts in lock-manager code   | [Execution Control](../developer-guide/global-variables.md#execution-control) |

**Data structures produced:**

| Structure                                              | Reference                                                                                                  |
| ------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------- |
| [Session log files](../developer-guide/data-structures.md#session-log-index-varlogzfsutilitiessessionslog_indexjson) | One log file per directly-executed script; reused by child sourced modules via `$ZFSUTILITIES_LOG_INHERIT` |

**Called modules:** none. `bashinit` is the lowest-level helper; it does not source other project modules.

**Internal flow:**

1. `bashinit` derives `$mydir` from `BASH_SOURCE[1]` only when it is not already set.
2. If the script is executed directly and log inheritance is not enabled, it creates a timestamped log file under `$ZFSUTILITIES_LOG_DIR` and exports `$ZFSUTILITIES_LOG_FILE`.
3. `log_msg` builds a `realpath(file):line:` prefix, writes the message to stderr (with color when connected to a terminal), and appends a timestamped copy to the session log when one is owned by the process.
4. `ask_yn` loops until the user enters `y`, `yes`, `n`, or `no`.

---

### `bashdebug`

Provides a debug trap (`_trap_DEBUG`) that runs before every command, enabling
single-step debugging with a pre-execution prompt showing the command, source
file, line number, and call stack. Also installs an ERR trap for post-failure
interactive debugging.

```bash
source $mydir/bashdebug
bashdebugon    # enable
bashdebugoff   # disable
```

**Arguments:** none.

**Globals:** none.

**Called modules:** none.

**Data structures consumed / produced:** none.

**Return codes:** none (traps are installed; pre/post commands return the
underlying command's status).

---

### `bashfatal`

Sources at the point of a fatal error to terminate the script unconditionally.
Always calls `exit` regardless of whether the script was sourced or executed.

```bash
source $mydir/bashfatal        # exits with code 8
source $mydir/bashfatal 4      # exits with specified code
```

| Argument | Default | Description |
| -------- | ------- | ----------- |
| `$1`     | `8`     | Exit code   |

Must be sourced at the point of execution, not at the top of the file.

**Called modules:** none.

**Data structures consumed / produced:** none.

**Return codes:** does not return; terminates the process with the supplied code.

---

### `bashreturn`

Sources at the point of a non-fatal early exit. Uses `return` if the script
was sourced, `exit` if executed directly.

```bash
source $mydir/bashreturn       # returns/exits with code 0
source $mydir/bashreturn 4     # returns/exits with specified code
```

| Argument | Default | Description      |
| -------- | ------- | ---------------- |
| `$1`     | `0`     | Return/exit code |

Must be sourced at the point of execution, not at the top of the file.

**Called modules:** none.

**Data structures consumed / produced:** none.

**Return codes:** returns or exits with the supplied code.

---

### `bashsetx`

Provides the `setx` function for temporarily enabling `set -x` tracing.

```bash
source $mydir/bashsetx
setx       # enable tracing with custom PS4
```

Sets `PS4` to `>${BASH_SOURCE}:${LINENO}-->` for informative trace output.
Sends trace output to stderr via `BASH_XTRACEFD=2`.

**Arguments:** none.

**Globals:**

| Variable      | Role                                              | Reference |
| ------------- | ------------------------------------------------- | --------- |
| `$bashrestorex`| Set by `setx` to the command needed to restore the original `set -x` state | —         |

**Called modules:** none.

**Data structures consumed / produced:** none.

**Return codes:** `0` on success.

---

### `rootcheck`

Verifies the script is running as root. Sources at the top of any script that
requires root privileges.

```bash
source $mydir/rootcheck
rootcheck
```

**Arguments:** none.

**Globals:** none (reads `$EUID`).

**Called modules:** none.

**Data structures consumed / produced:** none.

**Return codes:**

| Code | Meaning                  |
| ---- | ------------------------ |
| 0    | Running as root          |
| 1    | Not running as root      |

Exits with a clear message if not running as root.

---

### `zfsconfig`

Sourceable helper that reads from and writes to the shared JSON config at
`/root/.config/zfsutilities.json`. This is the bash-side counterpart to the
GUI's Python config modules (`config_core.py` and `feature_config.py`); they
share the same file.

No `jq` dependency — the helper uses inline `python3` heredocs so it works
anywhere Python 3 is available. Results are cached in environment variables
within one bash process, so repeated calls don't re-spawn Python. Call
`zfsconfig_invalidate` to force a re-read if the config file has been
changed externally.

```bash
source $mydir/zfsconfig

# Pool list
poolarray                                   # fills $zfspoolarray from JSON
zfsconfig_get_pools                         # one pool name per line
zfsconfig_set_pools threeamigos fivebays    # replace the list
# Pool entries may be plain strings or {"name": "...", "offsite_candidate": true}
# objects. String entries are accepted for backward compatibility.

# Offsite candidate pools
zfsconfig_get_offsite_candidates            # one candidate pool name per line

# Checkagainst table
zfsconfig_get_checkagainst                  # "<dataset> <quals> <counterpart> <label>" per line
zfsconfig_set_checkagainst_file table.conf  # import a whitespace-formatted file (comment field ignored)

# Retention policy (sourceable bash fragment)
eval "$(zfsconfig_get_retention threeamigos)"
# now $bktname[i], $bktretain[i], $minage[i] are set

# Force re-read after external modification
zfsconfig_invalidate
```

**Functions and their arguments:**

| Function                          | Arguments | Description                                                                                                                         |
| --------------------------------- | --------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `zfsconfig_get_pools`             | —         | Print one pool name per line from `config.pools`. Accepts string entries or `{"name", "offsite_candidate"}` objects                 |
| `zfsconfig_set_pools`             | `POOL...` | Replace the pool list (always stores objects internally via the GUI helpers)                                                        |
| `zfsconfig_get_offsite_candidates`| —         | Print one offsite-candidate pool name per line (pools with `offsite_candidate: true`)                                               |
| `zfsconfig_get_checkagainst`      | —         | Print entries: `<dataset> <quals> <counterpart> <label>` (the JSON `comment` field is not emitted)                                 |
| `zfsconfig_set_checkagainst_file` | `<path>`  | Replace from a whitespace-formatted file (comment field is not imported)                                                            |
| `zfsconfig_get_retention`         | `<pool>`  | Emit `bktname[i]/bktretain[i]/minage[i]` fragment for `<pool>` (falls back to `default`, then to legacy `zfsretainpol-<pool>` file) |
| `zfsconfig_invalidate`            | —         | Drop the in-shell cache                                                                                                             |
| `poolarray`                       | —         | Fills `$zfspoolarray` from `config.pools`                                                                                           |

**Globals:**

| Variable                | Role                                                             | Reference                                                               |
| ----------------------- | ---------------------------------------------------------------- | ----------------------------------------------------------------------- |
| `$ZFSCONFIG_PATH`       | Override config path (default `/root/.config/zfsutilities.json`) | [Infrastructure](../developer-guide/global-variables.md#infrastructure) |
| `$ZFSCONFIG_LEGACY_DIR` | Directory searched for legacy `zfsretainpol-*` files             | [Infrastructure](../developer-guide/global-variables.md#infrastructure) |

**Data structures produced:**

| Structure                                                                                   | Reference                                                                                                 |
| ------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `$zfspoolarray`                                                                             | [Data Structures](../developer-guide/data-structures.md#zfspoolarray)                                     |
| Retention arrays (`$bktname`, `$bktretain`, `$minage`)                                      | [Data Structures](../developer-guide/data-structures.md#retention-policy-arrays-bktname-bktretain-minage) |
| [JSON config](../developer-guide/data-structures.md#json-config-rootconfigzfsutilitiesjson) | All reads/writes target this file                                                                         |

**Called modules:** none. `zfsconfig` uses inline `python3` heredocs rather than
sourcing other project modules.

---

### `zfsbuildfsarray`

Builds a filtered list of ZFS datasets into `$fsarray`. The primary filtering
mechanism used throughout the codebase.

```bash
source $mydir/zfsbuildfsarray
buildfsarray <root-dataset>
# $fsarray now contains matching datasets
```

**Arguments:**

| Argument | Description                                                                         |
| -------- | ----------------------------------------------------------------------------------- |
| `$1`     | Root dataset to list (required). Overrides `$sourcefs` if set                       |
| `$2`     | `bottomup` to sort descending (equivalent to `$bottomup='Y'`)                       |
| `$3`     | `pool` = list pools rather than datasets (equivalent to `$buildfsarraytype='pool'`) |

**Filtering variables** (set before calling):

| Variable            | Description                                                                                                                                                              | Reference                                                                          |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------- |
| `$depth`            | Limit recursion depth (`0` = root only, `1` = one level, `""` = unlimited)                                                                                               | [Selection](../developer-guide/global-variables.md#dataset-and-snapshot-selection) |
| `$buildfsarraytype` | Dataset types to list (default `filesystem,volume`)                                                                                                                      | [Selection](../developer-guide/global-variables.md#dataset-and-snapshot-selection) |
| `$sortby`           | ZFS property to sort by (default `name`; `creation` for chronological)                                                                                                   | [Selection](../developer-guide/global-variables.md#dataset-and-snapshot-selection) |
| `$bottomup`         | `'Y'` for descending sort                                                                                                                                                | [Selection](../developer-guide/global-variables.md#dataset-and-snapshot-selection) |
| `$includes`         | Bash list of substrings datasets must contain to be kept (prefix `=` for exact match) E.g., \$includes=("string1", "string2")  If not specified, everything is included. | [Selection](../developer-guide/global-variables.md#dataset-and-snapshot-selection) |
| `$excludes`         | Substrings that cause datasets to be dropped (prefix `=` for exact match). E.g., \$excludes=("string1", "string2")  If not specified, nothing is excluded.               | [Selection](../developer-guide/global-variables.md#dataset-and-snapshot-selection) |
| `$startwith`        | Trim the front until the first match. Aborts if no match                                                                                                                 | [Selection](../developer-guide/global-variables.md#dataset-and-snapshot-selection) |
| `$endwith`          | Trim the back after the first match. Aborts if no match                                                                                                                  | [Selection](../developer-guide/global-variables.md#dataset-and-snapshot-selection) |

**Filter sequence** (applied in this order):

1. Initial list from `zfs list -r` on `<root-dataset>`, constrained by
   `$depth`, typed by `$buildfsarraytype`, and sorted by `$sortby`
   (ascending unless `$bottomup='Y'`).
2. `$includes` — keep only datasets matching at least one include entry.
3. `$excludes` — drop datasets matching any exclude entry.
4. `$startwith` — trim the front until the first match (the match is kept).
5. `$endwith` — trim the back after the first match (the match is kept).

**Data structures produced:**

| Structure                                                                              | Reference                                     |
| -------------------------------------------------------------------------------------- | --------------------------------------------- |
| [`$fsarray` / `$fsarraylen`](../developer-guide/data-structures.md#fsarray-fsarraylen) | Filtered dataset list (persists after return) |

**Called modules:**

| Module      | Purpose in this entry                            |
| ----------- | ------------------------------------------------ |
| `bashinit`  | Logging and `$mydir` initialization              |
| `bashreturn`| Clean non-fatal return for the `pool` list path  |

**Data structures consumed:**

| Structure | Reference |
| --------- | --------- |
| `$includes`, `$excludes`, `$startwith`, `$endwith`, `$depth`, `$bottomup`, `$buildfsarraytype`, `$sortby`, `$skipclones` | [Selection globals](../developer-guide/global-variables.md#dataset-and-snapshot-selection) |

---

### `zfscheckagainst`

Verifies a snapshot is safe to delete by confirming it is not the last common
snapshot shared with a counterpart dataset. The counterpart is derived from
the **fss table**.

```bash
source $mydir/zfscheckagainst
checkagainst <snapshot>
```

**Arguments:**

| Argument | Description                                               |
| -------- | --------------------------------------------------------- |
| `$1`     | Snapshot to check (e.g. `pool/dataset@label-date-bucket`) |

**Globals:** none required. Reads the fss table via `zfsconfig_get_checkagainst`.

**Called modules:**

| Module                     | Purpose in this entry                            |
| -------------------------- | ------------------------------------------------ |
| `bashinit`                 | Logging and `$mydir` initialization              |
| `bashdebug`                | Optional debug traps (conditionally enabled)     |
| `zfscommsnap`              | Find common snapshots with counterpart datasets  |
| `zfsremoveleadingqualifiers`| Strip leading qualifiers from dataset names     |
| `zfsconfig`                | Load the fss table from JSON config              |

**Data structures consumed:**

| Structure                                                                                             | Reference                                |
| ----------------------------------------------------------------------------------------------------- | ---------------------------------------- |
| [fss table](../developer-guide/data-structures.md#fss-table-in-memory-rows-from-zfscheckagainst-json) | Rules for mapping snapshot → counterpart |
| [JSON config](../developer-guide/data-structures.md#json-config-rootconfigzfsutilitiesjson)           | `checkagainst` and `pools` keys            |

#### The fss table

The fss table tells `checkagainst` how to transform a snapshot name into the
counterpart dataset name that must still share a common snapshot with it. It
is loaded from the JSON config's `checkagainst` key via
[`zfsconfig_get_checkagainst`](#zfsconfig). Each entry is a single line of
four whitespace-separated fields. An optional `comment` is stored in the JSON
config and shown in the GUI, but it is not emitted by `zfsconfig_get_checkagainst`:

| Field | Name in code                            | Purpose                                                                                                                                   |
| ----- | --------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| 1     | apply-to dataset (`$fs`)                | The source dataset tree this entry applies to. The snapshot being checked must belong to this dataset or one of its descendants. May contain `<offsite>` anywhere; every occurrence is replaced with each offsite-candidate pool name at run-time |
| 2     | qualifiers to delete (`$delquals`)      | Number of leading path components to strip from the source dataset name before constructing the counterpart name. `0` means strip nothing |
| 3     | qualifiers to prepend (`$checkagainst`) | Path prefix to prepend to the stripped dataset name. A literal `-` means "null prepend" — use the stripped name as-is                     |
| 4     | label                                   | Snapshot label to match (`dailybackup`, `offsite`, etc.). Only snapshots carrying this label are checked against this entry               |
| 5     | comment                                 | Optional note stored in JSON / shown in GUI; ignored by `zfscheckagainst`                                                                  |

**Example fss table:**

```
# Apply-to dataset   Del  Prepend                Label
threeamigos          0    fivebays               dailybackup
NVME1                0    fivebays               dailybackup
temp                 0    z22tb                  dailybackup
temp                 0    z40tb                  offsite
fivebays             0    z22tb                  offsite
<offsite>/temp       1    -                      offsite
```

The last entry expands at run-time to one row per offsite-candidate pool
(e.g. `z22tb/temp` and `z40tb/temp`), allowing `zfscheckagainst` to verify
offsite snapshots against their local counterpart. The `<offsite>` token may
appear anywhere in the Dataset or Counterpart value; every occurrence is
replaced with the candidate pool name.

#### How an entry is used

For a snapshot like `threeamigos/proxmox/vm-101-disk-0@dailybackup-…-d` and
the first entry above:

1. The snapshot's dataset (`threeamigos/proxmox/vm-101-disk-0`) is under the
   apply-to dataset (`threeamigos`) — entry matches.
2. The snapshot's label (`dailybackup`) matches the entry's label — entry
   applies.
3. Strip the snapshot suffix, giving `dstocheck = threeamigos/proxmox/vm-101-disk-0`.
4. Delete the first `$delquals` leading qualifiers from `dstocheck`. With
   `delquals = 0`, nothing is stripped.
5. Prepend `$checkagainst`: `dstocheck` becomes
   `fivebays/threeamigos/proxmox/vm-101-disk-0`.
6. The counterpart pool (`checkagainstpool`) is the first segment of the
   prepend value (`fivebays`). If the prepend is `-`, the counterpart pool
   is instead the first segment of the transformed `dstocheck`.
7. If the counterpart pool is online, look for a common snapshot between
   the source and `dstocheck`. If offline, fall through to hold-tag
   verification (below).

Multiple fss entries may match one snapshot. `checkagainst` evaluates every
matching entry and only returns "safe to delete" when all counterparts can
be verified.

#### Hold-tag verification for offline pools (offsite label only)

When a counterpart pool is offline and the snapshot's label is `offsite`,
`checkagainst` scans other `@offsite` snapshots on the same source dataset
for a hold named `offsite-<counterpart_pool>`. If another snapshot carries
that hold, the counterpart received it too — a second common snapshot is
confirmed and deletion is safe (returns 0). If no other snapshot has the
hold, the current snapshot may be the only shared point; deletion is
blocked (returns 6). Non-offsite labels always block when the counterpart
is offline (no holds to check).

#### Return codes

| Code | Meaning                                                           |
| ---- | ----------------------------------------------------------------- |
| 0    | Safe to delete (includes hold-verified offline counterpart)       |
| 4    | No counterpart snapshots found — candidate is not common          |
| 5    | No entry in `fss` table matched the snapshot — no check performed |
| 6    | Counterpart pool offline and no hold tag — blocked for safety     |
| 7    | Last remaining common snapshot — deletion blocked                 |
| 8    | Fatal error                                                       |

---

### `zfscheckrunningvms`

Checks whether any running Proxmox VMs have disks on a given ZFS dataset.
Prevents accidental restores over live VMs.

```bash
source $mydir/zfscheckrunningvms
checkrunningvms <dataset>
```

**Arguments:**

| Argument | Description      |
| -------- | ---------------- |
| `$1`     | Dataset to check |

**Globals:**

| Variable                    | Role                                                   | Reference                                                                       |
| --------------------------- | ------------------------------------------------------ | ------------------------------------------------------------------------------- |
| `NODE_MODE`, `COMPUTE_HOST` | Determines whether `qm config` runs locally or via SSH | [Node Configuration](../developer-guide/global-variables.md#node-configuration) |

**Return codes:**

| Code | Meaning                                            |
| ---- | -------------------------------------------------- |
| 0    | No running VMs found on this dataset               |
| 1    | Running VMs detected — operation blocked           |
| 2    | Proxmox tools not available (`qm`/`pct` not found) |

Uses `qm config` and `pct config` to confirm that running VMs actually have
disks on the target pool (avoids false positives from name-matching alone).

**Called modules:** none (uses external Proxmox tools).

**Data structures consumed / produced:** none.

---

### `zfs-diagnose-busy`

Diagnoses why a ZFS dataset or snapshot cannot be destroyed.

```bash
source $mydir/zfs-diagnose-busy
diagnose_dataset_busy <dataset_or_snapshot> [stderr_text]
```

**Checks performed:**

1. **Clone dependents** — `zfs list -H -o clones` (snapshots) or recursive snapshot clone scan (datasets)
2. **Holds** — `zfs holds -H`
3. **Mounted / open files** — `zfs get mounted` plus `fuser -m` / `lsof +D`
4. **Active send/receive** — `zfs get receive_resume_token`; `pgrep` for running `zfs send`
5. **Bookmarks** — `zfs list -t bookmark -r`
6. **iSCSI LUN** — `targetcli` backstore/LUN lookup (zvols matching `vm-<N>-disk-<N>`)
7. **Running VM** — `qm status` (zvols)
8. **NFS / SMB shares** — `zfs get sharenfs,sharesmb`

If nothing specific is found, a fallback message lists common remaining causes
and suggests `fuser` / `lsof` commands.

**Integration:**

| Caller                | When called                             |
| --------------------- | --------------------------------------- |
| `zfsdelsnap`          | After `zfs destroy` fails               |
| `zfsdelfs`            | After `zfs destroy` fails               |
| `remove-vm-disk`      | After `zfs destroy` fails               |
| `retire-vm`           | After `zfs destroy` fails               |
| `clone-vm`            | After cleanup `zfs destroy` fails       |
| `dataset_actions.py`  | From `_run_zfs_sudo` when destroy fails |
| `snapshot_manager.py` | After `zfs destroy` fails               |

**Called modules:** none. `diagnose_dataset_busy` runs external commands
(`zfs`, `zpool`, `fuser`, `lsof`, `targetcli`, `qm`, `pct`) directly.

**Data structures consumed / produced:** none.

**Return codes:**

| Code | Meaning                              |
| ---- | ------------------------------------ |
| 0    | Diagnosis completed (cause may or may not have been found) |

---

### `zfscommsnap`

Finds the most recent (or oldest) common snapshot between a source and
destination dataset.

```bash
source $mydir/zfscommsnap
getcommonsnap <source> <destination> [OLDEST]
```

**Arguments:**

| Argument | Description                                                                                                    |
| -------- | -------------------------------------------------------------------------------------------------------------- |
| `$1`     | Source dataset                                                                                                 |
| `$2`     | Destination dataset                                                                                            |
| `$3`     | `OLDEST` to find oldest common snapshot instead of most recent (equivalent to `$commsnap_mostrecent='OLDEST'`) |

**Globals:**

| Variable                                 | Role                                                 | Reference                                                              |
| ---------------------------------------- | ---------------------------------------------------- | ---------------------------------------------------------------------- |
| `$commsnap_mostrecent`                   | `'OLDEST'` to prefer the oldest common snapshot      | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive) |
| `$label`, `$originlabel`, `$targetlabel` | Restrict the common-snapshot scan to matching labels | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive) |
| `$maxcommsnapperiod`                     | Maximum acceptable age of a common snapshot, in days | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive) |

Sets `$commsnap` to the matching snapshot suffix (without dataset prefix).
Returns non-zero if no common snapshot exists.

**Called modules:**

| Module      | Purpose in this entry                            |
| ----------- | ------------------------------------------------ |
| `bashinit`  | Logging and `$mydir` initialization              |

**Data structures consumed / produced:** none.

**Return codes:**

| Code | Meaning                                                         |
| ---- | --------------------------------------------------------------- |
| 0    | Common snapshot found and is the newest in destination          |
| 4    | No common snapshot found; most recent source snapshot returned  |
| 8    | No snapshots on source dataset                                  |
| 16   | Common snapshot found but destination has newer snapshots       |
| 32   | Another common snapshot found (used by `checkagainst`)          |
| 64   | No other common snapshot found (used by `checkagainst`)         |

---

### `zfsdelallholds`

Releases all holds (or a specific hold) on a single ZFS snapshot.

```bash
source $mydir/zfsdelallholds
delallholds <snapshot> [hold-tag]
```

**Arguments:**

| Argument | Description                                   |
| -------- | --------------------------------------------- |
| `$1`     | Snapshot name                                 |
| `$2`     | Optional: only release this specific hold tag |

**Globals:** none.

**Called modules:** none.

**Data structures consumed / produced:** none.

**Return codes:**

| Code | Meaning                              |
| ---- | ------------------------------------ |
| 0    | Holds released (or none existed)     |
| 8    | Fatal error releasing a hold         |

---

### `zfsdelallholdssubtree`

Releases holds across all snapshots in a subtree.

```bash
sudo ./zfsdelallholdssubtree <dataset> [hold-tag]
```

**Arguments:**

| Argument | Description                    |
| -------- | ------------------------------ |
| `$1`     | Subtree to process             |
| `$2`     | Optional hold tag to filter on |

**Globals:**

| Variable              | Role                                                                | Reference                                                                          |
| --------------------- | ------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `$depth`, `$includes` | Forwarded to `zfsbuildfsarray` (with `buildfsarraytype='snapshot'`) | [Selection](../developer-guide/global-variables.md#dataset-and-snapshot-selection) |
| `$autoproceed`        | `'Y'` to skip confirmation prompts                                  | [Execution Control](../developer-guide/global-variables.md#execution-control)      |

**Called modules:**

| Module             | Purpose in this entry                          |
| ------------------ | ---------------------------------------------- |
| `bashinit`         | Logging and `$mydir` initialization            |
| `rootcheck`        | Verify root privileges                         |
| `zfsbuildfsarray`  | Build the list of snapshots to process         |
| `zfsdelallholds`   | Release holds on each snapshot in the subtree  |

**Data structures produced:**

| Structure                                                                                   | Reference                                                                 |
| ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| [`$fsarray`](../developer-guide/data-structures.md#fsarray-fsarraylen)                     | Snapshot list built by `zfsbuildfsarray`                                  |

---

### `zfsdelsnap`

Deletes a single snapshot after running `zfscheckagainst` as a safety check.

```bash
source $mydir/zfsdelsnap
delsnap <snapshot> [minage] [releaseholds]
```

**Arguments:**

| Argument | Default | Description                                                  |
| -------- | ------- | ------------------------------------------------------------ |
| `$1`     | —       | Snapshot to delete                                           |
| `$2`     | `0`     | Minimum age in days; snapshots younger than this are skipped |
| `$3`     | `N`     | `'releaseholds'` or `'Y'` to release holds before destroying |

**Globals:**

| Variable        | Role                                               | Reference                                                                     |
| --------------- | -------------------------------------------------- | ----------------------------------------------------------------------------- |
| `$dryrun`       | `'Y'` = report only                                | [Execution Control](../developer-guide/global-variables.md#execution-control) |
| `$autoproceed`  | `'Y'` = skip prompt before each deletion           | [Execution Control](../developer-guide/global-variables.md#execution-control) |
| `$releaseholds` | `'Y'` = release holds even if third arg is not set | [Execution Control](../developer-guide/global-variables.md#execution-control) |

Delegates the safety check to [`zfscheckagainst`](#zfscheckagainst) — if the
snapshot is the last common snapshot with a counterpart, deletion is blocked.

If `zfs destroy` fails (e.g. "dataset is busy"), [`zfs-diagnose-busy`](#zfs-diagnose-busy)
is automatically called to report the specific cause before the script decides
whether to warn/continue (when `$skipbusy='Y'`) or exit fatally.

**Called modules:**

| Module             | Purpose in this entry                                      |
| ------------------ | ---------------------------------------------------------- |
| `bashinit`         | Logging and `$mydir` initialization                        |
| `zfscheckagainst`  | Verify the snapshot is not the last common snapshot        |
| `zfsdelallholds`   | Release holds when `$releaseholds='Y'`                     |
| `zfslockmanager`   | Acquire/release a write lock on the parent dataset         |
| `zfs-diagnose-busy`| Report why `zfs destroy` failed                            |

**Data structures consumed / produced:**

| Structure                                                                  | Reference                                                           |
| -------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| [Lock files](../developer-guide/data-structures.md#lock-files)             | Write lock on parent dataset written by `zfslockmanager`            |
| [fss table](../developer-guide/data-structures.md#fss-table-in-memory-rows-from-zfscheckagainst-json) | Consumed by `zfscheckagainst`                                       |

**Return codes:**

| Code | Meaning                                                        |
| ---- | -------------------------------------------------------------- |
| 0    | Snapshot deleted successfully                                  |
| 1    | Lock aborted by user, snapshot too young, or busy/held skipped |
| 5    | No checkagainst entry matched (with user prompt)               |
| 6    | Counterpart pool offline — deletion blocked                    |
| 7    | Last remaining common snapshot — deletion blocked              |
| 8    | Fatal error                                                    |

---

### `zfsfindoffsitepool`

Finds the first online offsite pool (`z22tb` or `z40tb`).

```bash
source $mydir/zfsfindoffsitepool
pool=$(findoffsitepool)
```

**Arguments:** none.

**Globals:** none (compares imported pool names against the hardcoded offsite pool list).

Returns the pool name, or empty string if none are online.

**Called modules:** none.

**Data structures consumed / produced:** none.

**Return codes:**

| Code | Meaning                              |
| ---- | ------------------------------------ |
| 0    | Always; prints pool name or empty    |

---

### `zfshold`

Applies a named hold to a snapshot (or all snapshots matching a suffix across
a subtree).

```bash
source $mydir/zfshold
zfshold <hold-tag> <dataset> <snapshot-suffix>
```

**Arguments:**

| Argument | Description                                   |
| -------- | --------------------------------------------- |
| `$1`     | Hold tag to apply                             |
| `$2`     | Dataset (or subtree root)                     |
| `$3`     | Snapshot suffix to match (the part after `@`) |

**Globals:** none.

Suppresses "tag already exists" errors — safe to call repeatedly.

**Called modules:** none.

**Data structures consumed / produced:** none.

**Return codes:**

| Code | Meaning                              |
| ---- | ------------------------------------ |
| 0    | Tag applied (or already present)     |
| 1    | Missing required snapshot pattern    |

---

### `zfslockmanager`

Core dataset lock management. Provides acquire, release, and conflict-checking
functions. Used by `zfs-send-receive`, `zfsdelsnap`, and others.

```bash
source $mydir/zfslockmanager
zfslock_init
zfslock_acquire <dataset> <type> [description]   # 0=ok, 1=conflict, 2=error
zfslock_acquire_multiple <type> <dataset> ...    # acquire several locks safely
zfslock_release <lock-id>
zfslock_release_all                               # release all locks for current PID
zfslock_check <dataset> <type>                    # 0=no conflict, 1=conflict
```

**Function arguments:**

| Function              | Arguments                        | Purpose                                   |
| --------------------- | -------------------------------- | ----------------------------------------- |
| `zfslock_init`        | —                                | Create the lock directory if missing      |
| `zfslock_acquire`           | `<dataset> <type> [description]` | Acquire a lock; prints lock-id on success |
| `zfslock_acquire_multiple`  | `<type> <dataset> ...`           | Acquire several locks in sorted order     |
| `zfslock_release`           | `<lock-id>`                      | Release a specific lock                   |
| `zfslock_release_all` | —                                | Release all locks for the current PID     |
| `zfslock_check`       | `<dataset> <type>`               | Report whether a lock would conflict      |

Lock types: `r` (shared read), `w` (exclusive write), `x` (exclusive destroy).

Lock files are stored in `/run/lock/zfs/.locks/` (cleared on reboot).

**Globals:** none.

**Hierarchy rules:**

| Existing lock     | Conflicts with          |
| ----------------- | ----------------------- |
| `r` on ancestor   | `x` on descendants      |
| `w` on ancestor   | `w`, `x` on descendants |
| `x` on ancestor   | any lock on descendants |
| Any lock on child | `x` on ancestors        |

**Re-entrant locking:** If the current PID already holds a lock on a dataset
(or its ancestor/descendant), subsequent acquire attempts succeed without
creating a new lock file. The lock is released only when the original holder
releases it.

**Internal flow / algorithm:**

1. `zfslock_init` creates `/run/lock/zfs/.locks/` and `/run/lock/zfs/.pids/`
   and installs an `EXIT` trap that calls `zfslock_release_all`.
2. Each lock is stored as a JSON file named
   `<path-encoded-dataset>.<type>.<pid>.<lock-id>.lock` under `.locks/`.
   Dataset path separators (`/`) are encoded as `%2F` and `@` as `%40`.
3. `zfslock_check` scans the target dataset, all ancestors, and all descendants
   for existing locks. It returns conflict if the requested type and the
   existing type collide per the hierarchy rules above.
4. `zfslock_acquire` first calls `zfslock_check`. If no conflict exists, it
   writes the lock file and appends its path to the per-PID tracking file under
   `.pids/`.
5. `zfslock_is_stale` considers a lock stale if the file is missing, the owning
   PID is gone, or `/proc/<pid>/cmdline` no longer contains the script named in
   the lock file. `zfslock_cleanup_stale` removes stale locks and dead PID files.
6. `zfslock_wait_or_resolve` repeatedly attempts acquisition. On conflict, it
   offers interactive choices: wait, retry now, skip, abort, or force-release.
   In non-interactive/headless mode it aborts immediately.
7. `zfslock_release` removes the lock file and the corresponding entry from the
   PID file. `zfslock_release_all` removes every lock owned by the current PID
   (used by the `EXIT` trap).

**Data structures produced:**

| Structure                                                      | Reference                             |
| -------------------------------------------------------------- | ------------------------------------- |
| [Lock files](../developer-guide/data-structures.md#lock-files) | On-disk under `/run/lock/zfs/.locks/` |

**Return codes:**

| Code | Meaning                              |
| ---- | ------------------------------------ |
| 0    | Lock acquired / no conflict          |
| 1    | Conflict or release denied           |
| 2    | Error (bad arguments, I/O failure)   |

See also: [`zfslockctl`](commands.md#zfslockctl).

---

### `zfsoverrides`

Applies runtime parameter overrides passed as a semicolon-separated string of
bash assignments.

```bash
source $mydir/zfsoverrides
overrides "$1"
```

**Arguments:**

| Argument | Description                                                                                             |
| -------- | ------------------------------------------------------------------------------------------------------- |
| `$1`     | String of `name='value'` assignments separated by `;`. Parsed via `eval`, so any valid bash is accepted |

**Globals:** none directly — the caller defines which names are meaningful,
and any global listed on [Global Variables](../developer-guide/global-variables.md)
can be overridden.

```bash
sudo ./zfsdailybackup "backup_NVME1='N'; prune='N'"
```

**Called modules:** none.

**Data structures consumed / produced:** none.

**Internal flow / parse semantics:**

1. All positional arguments are joined into a single string with `$*`.
2. The joined string is logged and then evaluated with `eval` in the current
   shell context.
3. Any valid bash is accepted; the usual pattern is one or more assignments
   separated by semicolons.
4. Because the string runs as root, callers should avoid unquoted user input.
5. Last assignment wins if the same variable is set more than once.

**Return codes:**

| Code | Meaning                              |
| ---- | ------------------------------------ |
| 0    | Overrides applied (or none provided) |

---

### `zfsremoveleadingqualifiers`

Strips the first N path components from a ZFS dataset name. The pool name
counts as the first qualifier.

```bash
source $mydir/zfsremoveleadingqualifiers
result=$(remove_leading_qualifiers <n> <dataset>)
```

**Arguments:**

| Argument | Description                                |
| -------- | ------------------------------------------ |
| `$1`     | Number of leading path components to strip |
| `$2`     | Dataset name                               |

**Globals:** none.

| n   | Input                          | Output                |
| --- | ------------------------------ | --------------------- |
| 0   | `threeamigos/proxmox`          | `threeamigos/proxmox` |
| 1   | `threeamigos/proxmox`          | `proxmox`             |
| 2   | `fivebays/threeamigos/proxmox` | `proxmox`             |

Used by `zfs-send-receive` to construct destination paths from source paths,
and by `zfsretain` with `$leadingqualifiestodelete`.

**Called modules:**

| Module       | Purpose in this entry                            |
| ------------ | ------------------------------------------------ |
| `bashinit`   | Logging and `$mydir` initialization              |
| `bashreturn` | Non-fatal return on argument errors (via `exit`) |

**Data structures consumed / produced:** none.

**Return codes:**

| Code | Meaning                              |
| ---- | ------------------------------------ |
| 0    | Success; stripped name printed       |
| 1    | Fatal argument error                 |

---

### `zfsretain`

Applies retention policies to a pool or dataset in three phases:

1. **Phase 0** — For `@offsite` snapshots, remove all but the most recent
   offsite snapshot per month per dataset
2. **Phase 1** — Remove same-day duplicate snapshots within each bucket
3. **Phase 2** — Prune by bucket retention count (keep N most recent). Deletes
   the oldest snapshots first until only the retain count remains. Empty
   snapshots (`written=0`) are logged as `(empty)` but are not preferred over
   older snapshots with unique data. When `retain > 0`, the most recent snapshot
   in each bucket is protected (incremental base). When `retain = 0`, the most
   recent is eligible for deletion like the rest.

!!! note "Clone snapshots are protected"
    Snapshots with label `clone` or bucket `c` are **never touched** by retention. They are skipped in all phases because clone-origin snapshots cannot be deleted while dependent clones exist.

```bash
source $mydir/zfsretain
retain <pool> [label]
```

**Arguments:**

| Argument | Default       | Description                                                                                   |
| -------- | ------------- | --------------------------------------------------------------------------------------------- |
| `$1`     | —             | Pool or dataset to retain. May include `<fs> <leadingqualifiestodelete>` as a whitespace pair |
| `$2`     | `dailybackup` | Snapshot label to retain against. Leading `@` optional                                        |

**Globals:**

| Variable                       | Role                                                                          | Reference                                                                     |
| ------------------------------ | ----------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| `$dryrun`                      | `'Y'` (or anything not `'N'`) = report only                                   | [Execution Control](../developer-guide/global-variables.md#execution-control) |
| `$autoproceed`                 | `'Y'` = skip per-deletion prompt                                              | [Execution Control](../developer-guide/global-variables.md#execution-control) |
| `$releaseholds`                | `'Y'` = release holds before `zfsdelsnap`                                     | [Execution Control](../developer-guide/global-variables.md#execution-control) |
| `$skipbusy`                    | `'Y'` = warn and continue on held/busy snapshots; `'N'` = fatal               | [Execution Control](../developer-guide/global-variables.md#execution-control) |
| `$originlabel`, `$targetlabel` | Override label per side                                                       | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)        |
| `$leadingqualifiestodelete`    | Leading components to strip when building counterpart name for `checkagainst` | [Retention](../developer-guide/global-variables.md#retention)                 |

**Data structures consumed/produced:**

| Structure                                                                                                  | Reference                                                                  |
| ---------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| [Retention arrays](../developer-guide/data-structures.md#retention-policy-arrays-bktname-bktretain-minage) | `$bktname` / `$bktretain` / `$minage` filled via `zfsconfig_get_retention` |
| [`snaparray` / `bktsnaparray`](../developer-guide/data-structures.md#snaparray-bktsnaparray-zfsretain)     | Working arrays built per-run                                               |
| [JSON config](../developer-guide/data-structures.md#json-config-rootconfigzfsutilitiesjson)                | `retention` key read; falls back to legacy `zfsretainpol-<pool>` files     |

Delegates each deletion to [`zfsdelsnap`](#zfsdelsnap), which runs
[`zfscheckagainst`](#zfscheckagainst) as a safety check before every delete.

**Internal flow / algorithm:**

1. Parse `$1` as "`<dataset> [leadingqualifiestodelete]`" and normalize `$2`
   into a leading-`@` label.
2. Load the retention policy for the target pool via
   `zfsconfig_get_retention`. Falls back to the `default` policy, then to
   legacy `zfsretainpol-<pool>` files. Abort if no policy is found.
3. Build `$snaparray` from `zfs list -Ht snapshot -o name,creation -s creation`
   for the target dataset.
4. **Phase 0** (only when `$label = @offsite`). For each `@offsite` snapshot,
   keep only the newest snapshot per `dataset|Year-Month` key. Older snapshots
   in the same month are removed.
5. **Phase 1**. Walk snapshots in creation order and remove earlier snapshots
   that share the same dataset, label, bucket, and calendar day as the next
   snapshot.
6. **Phase 2**. Build per-bucket arrays (`snapbucket_d`, `snapbucket_w`, etc.)
   from the remaining snapshots. For each bucket that contains more snapshots
   than its retention count, delete the oldest snapshots first. The most recent
   snapshot in each bucket is protected when `retain > 0` so it remains
   available as an incremental base.
7. Empty snapshots (`written=0`) are flagged as `(empty)` in log messages but
   receive no deletion preference.
8. Snapshots with label `clone` or bucket `c` are skipped in all phases.

**Called modules:**

| Module                     | Purpose in this entry                            |
| -------------------------- | ------------------------------------------------ |
| `bashinit`                 | Logging and `$mydir` initialization              |
| `zfsconfig`                | Load pool retention policy and offsite candidates|
| `zfsdelsnap`               | Delete individual snapshots safely               |
| `zfsremoveleadingqualifiers`| Strip leading qualifiers for `checkagainst`     |
| `zfslockmanager`           | Acquire a write lock on the dataset being pruned |

**Return codes:**

| Code | Meaning                              |
| ---- | ------------------------------------ |
| 0    | Retention applied                    |
| 8    | Fatal error (no policy, bad eval)    |

---

### `zfs-send-receive`

The core ZFS send/receive engine. Handles full copies, incremental transfers,
resume tokens, space validation, VM checks, and dataset locking.  Locks are
acquired on the source and destination datasets before a snapshot is created
or selected, so concurrent jobs cannot insert a newer snapshot after the
common snapshot has been chosen.

```bash
source $mydir/zfs-send-receive
# Set parameters, then:
send-receive
```

This module is driven entirely by global variables — it takes no positional
arguments. Callers set the variables below, then invoke `send-receive`.

**Required input variables:**

| Variable          | Description                                                                                  | Reference                                                              |
| ----------------- | -------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `$sourcefs`       | Source dataset                                                                               | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive) |
| `$destfs`         | Destination pool/dataset                                                                     | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive) |
| `$nextsnap`       | Snapshot name to create on source, or `'notneeded'` to use the most recent existing snapshot | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive) |
| `$doincrementals` | `'Y'` = incremental from common snap; `'N'` = full copy                                      | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive) |

**Optional tuning variables:**

| Variable                                                         | Default       | Role                                                                                                                                                                                                    | Reference                                                                          |
| ---------------------------------------------------------------- | ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `$dointermediates`                                               | `'N'`         | `'Y'` = include intermediates with `-I`                                                                                                                                                                 | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)             |
| `$commsnap_mostrecent`                                           | most-recent   | `'OLDEST'` to use the oldest common snap                                                                                                                                                                | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)             |
| `$sourcefsremovequalifiers`                                      | `0`           | Leading qualifiers to strip from source                                                                                                                                                                 | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)             |
| `$label`, `$originlabel`, `$targetlabel`                         | `dailybackup` | Snapshot label matching                                                                                                                                                                                 | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)             |
| `$force`                                                         | `''`          | `'Y'` = same as `allow_destructive='Y'` (full copy destroys destination + children)                                                                                                                     | [Execution Control](../developer-guide/global-variables.md#execution-control)      |
| `$allow_destructive`                                             | `'N'`         | `'N'` = `delallsnaps` on destination only (child datasets preserved); `'Y'` = `delfs` the destination (destroys dataset + all children). Required for raw-mode full copies into an existing destination | [Execution Control](../developer-guide/global-variables.md#execution-control)      |
| `$autoproceed`                                                   | `'N'`         | `'Y'` = no interactive prompts                                                                                                                                                                          | [Execution Control](../developer-guide/global-variables.md#execution-control)      |
| `$dryrun`                                                        | `'N'`         | `'Y'` = report without writing                                                                                                                                                                          | [Execution Control](../developer-guide/global-variables.md#execution-control)      |
| `$receive_F_option`                                              | `''`          | `'F'` = roll back destination modifications                                                                                                                                                             | —                                                                                  |
| `$receive_s_option`                                              | `''`          | `'s'` = enable resumable receives                                                                                                                                                                       | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)             |
| `$verify_after_transfer`                                         | `'Y'`         | `'Y'` = verify destination snapshot GUID matches source after receive                                                                                                                                   | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)             |
| `$resumablethreshold`                                            | 50 GB         | Size above which resumable receive is used                                                                                                                                                              | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)             |
| `$maxcommsnapperiod`                                             | `130`         | Max age (days) of an acceptable common snapshot                                                                                                                                                         | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)             |
| `$pv_rate_limit`                                                 | `''`          | Max transfer rate for `pv -L` (e.g. `200M`, `1G`). Empty = no limit                                                                                                                                     | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)             |
| `$pvthreshold`                                                   | 300 MB        | Size above which `pv` progress display is used                                                                                                                                                          | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive)             |
| `$includes` / `$excludes` / `$startwith` / `$endwith` / `$depth` | varies        | Dataset filters (delegated to `zfsbuildfsarray`)                                                                                                                                                        | [Selection](../developer-guide/global-variables.md#dataset-and-snapshot-selection) |

**Data structures consumed/produced:**

| Structure                                                                                  | Direction                        | Purpose                                                                                         |
| ------------------------------------------------------------------------------------------ | -------------------------------- | ----------------------------------------------------------------------------------------------- |
| [`$fsarray`](../developer-guide/data-structures.md#fsarray-fsarraylen)                     | produced (via `zfsbuildfsarray`) | Filtered source dataset list                                                                    |
| [`ISCSI_TEARDOWN`](../developer-guide/data-structures.md#iscsi_teardown-associative-array) | read                             | Per-dataset teardown records that drive `iscsi_rebuild_torn_down` after each successful receive |

**Return codes:**

| Code | Meaning                                       |
| ---- | --------------------------------------------- |
| 0    | Success                                       |
| 1    | User aborted (lock conflict or prompt)        |
| 4    | No common snapshot found (full copy declined) |
| 8    | Fatal error                                   |

When the destination is newer than the common snapshot (`zfscommsnap` returns
16), `send-receive` normally prompts to roll back. With `$autoproceed='Y'` the
rollback is performed automatically and logged as a warning. In
non-interactive mode (stdin is not a TTY) the dataset is skipped with a warning
instead of waiting for input. The same rules apply when a resume token cannot
be validated and the user would otherwise be asked whether to abort the token
and retry.

`$sourcefs`, `$destfs`, `$doincrementals`, and `$nextsnap` are saved on entry
and restored on exit so callers do not need to save/restore them between
steps.

**Internal flow / algorithm:**

1. Source all dependent modules and apply defaults for globals such as
   `$doincrementals`, `$dointermediates`, `$autoproceed`, `$dryrun`, and
   `$resumablethreshold`.
2. Apply any `$overrides` via `zfsoverrides`.
3. Call `buildfsarray` to produce `$fsarray`, the filtered list of source
   datasets to copy.
4. Initialize the lock manager and acquire a write (`w`) lock on both the
   source dataset and the destination dataset for each item in `$fsarray`.
5. For each source dataset:
   a. Resolve `$nextsnap`. If it is `'notneeded'`, use the newest existing
      snapshot; otherwise create the snapshot if it does not exist.
   b. Compute the destination path with `remove_leading_qualifiers`.
   c. Check for a `receive_resume_token` on the destination. If present and
      valid, resume the transfer; if invalid and `$autoproceed='Y'` or
      non-interactive, abort the token and retry in the next loop iteration.
   d. Call `getcommonsnap` to select the incremental base. Handle return codes:
      `0` (common snap is newest on dest), `4` (no common snap → offer full
      copy), `16` (destination has newer snapshots → offer rollback), `32`
      (another common snap found for `checkagainst` logic).
   e. For full copies (`$doincrementals='N'`), check for running VMs on the
      destination and either delete destination snapshots (`allow_destructive`)
      or the whole destination dataset (`force`).
   f. Estimate stream size with `zfs send -nP`. If the destination pool has
      insufficient space, prompt or skip (depending on `$autoproceed`).
   g. Build send options (`-cw`, plus `-i`/`-I` for incrementals) and receive
      options (`-uv`, plus `-F` and/or `-s` as configured). Large transfers
      automatically enable resumable receives (`-s`).
   h. Execute `zfs send | [pv] | zfs receive`. On failure, release locks and
      exit fatally.
   i. If `$verify_after_transfer='Y'`, compare source and destination snapshot
      GUIDs.
   j. If this is a live (non-dry-run) full copy into an existing destination,
      call `iscsi_rebuild_torn_down` to restore any iSCSI LUNs recorded in
      `ISCSI_TEARDOWN`.
   k. Release source and destination locks.
6. Restore original `$sourcefs`, `$destfs`, `$doincrementals`, and `$nextsnap`
   before returning.

**Called modules:**

| Module                     | Purpose in this entry                            |
| -------------------------- | ------------------------------------------------ |
| `bashinit`                 | Logging and `$mydir` initialization              |
| `rootcheck`                | Verify root privileges                           |
| `bashsetx`                 | Optional tracing helper                          |
| `zfssnapbuild`             | Generate the snapshot name to send               |
| `zfsbuildfsarray`          | Build filtered source dataset list               |
| `zfsremoveleadingqualifiers`| Build destination dataset paths                 |
| `zfscommsnap`              | Find common snapshot for incremental sends       |
| `zfsdelallsnaps`           | Clear destination snapshots before full copy     |
| `zfsdelallholds`           | Release holds during rollback                    |
| `zfsholds`                 | List holds for diagnostic output                 |
| `zfsdelfs`                 | Destroy destination dataset when destructive     |
| `zfsoverrides`             | Apply runtime parameter overrides                |
| `zfslockmanager`           | Acquire/release per-dataset write locks          |
| `zfscheckrunningvms`       | Block restores over live VMs                     |

**Return codes:**

| Code | Meaning                                       |
| ---- | --------------------------------------------- |
| 0    | Success                                       |
| 1    | User aborted (lock conflict or prompt)        |
| 4    | No common snapshot found (full copy declined) |
| 8    | Fatal error                                   |
| 9    | Operation aborted from lock manager           |

---

### `zfssnapbuild`

Generates a snapshot name in the standard format.

```bash
source $mydir/zfssnapbuild
nextsnap=$(zfssnapbuild)
# Returns e.g. "@dailybackup-2026-02-24T02:00-05:00-d"
```

Format: `@<label>-<yyyy-mm-dd>T<hh:mm><tz>-<bucket>`

**Arguments:** none.

**Globals:**

| Variable  | Default       | Role                                        | Reference                                                              |
| --------- | ------------- | ------------------------------------------- | ---------------------------------------------------------------------- |
| `$label`  | `dailybackup` | Leading label component                     | [Send/Receive](../developer-guide/global-variables.md#zfs-sendreceive) |
| `$bucket` | computed      | `d` (daily), `w` (weekly), or `m` (monthly) | [Retention](../developer-guide/global-variables.md#retention)          |

**Internal flow / algorithm:**

1. Derive a per-caller snapfile path from `BASH_SOURCE[1]`. The file is named
   `/tmp/zfsnextsnap_<sanitized_caller>`.
2. If the snapfile exists and contains a snapshot name, prompt the user to
   reuse it. Reusing keeps incremental chains stable across interrupted runs.
3. If reuse is declined, delete the snapfile and generate a new name.
4. Acquire the global snapshot-name lock (`/run/lock/zfs/.snapname.lock`). The
   lock is held only while the name is being generated and recorded.
5. Normalize `$label`: default to `@dailybackup`, ensure it starts with `@`.
6. Compute the bucket if `$bucket` is unset:
   - `m` if the current day is the 1st of the month (takes precedence over Sunday).
   - `w` if the current day is Sunday.
   - `d` otherwise.
   - Hard-code `s` when the label is `@offsite`.
7. Build the name as `@<label>-<ISO-8601-minutes>-<bucket>`, record it in the
   one-minute reservation file (`/run/lock/zfs/.snapname.reserved`), release the
   lock, write the name to the snapfile, and print it.
8. `removesnapfile` deletes the snapfile; orchestrators such as
   `zfsdailybackup` call it after a successful run.

**Called modules:** none.

**Data structures consumed / produced:**

| Structure | Reference |
| --------- | --------- |
| [Snapshot name persistence](../developer-guide/data-structures.md#snapshot-name-persistence) | `/tmp/zfsnextsnap_<caller>` files |

**Return codes:**

| Code | Meaning                              |
| ---- | ------------------------------------ |
| 0    | Snapshot name printed                |


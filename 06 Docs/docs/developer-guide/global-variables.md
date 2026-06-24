# Global Variables

ZFSutilities is bash-based. Scripts are `source`d rather than executed in
subshells, so the variables one script sets are visible to the scripts it
calls. This page documents the globals that are read by more than one
script, grouped by purpose.

Within a single script, conventions:

- A variable with no prefix is a global — any caller can set it before
  calling, and any child script can read or modify it.
- Variables declared with `local` inside a function are scoped to that
  function and do not propagate.
- Callers that want to avoid being affected by a child's side effects
  typically save and restore the value themselves (e.g. `save_nextsnap`
  patterns).

## Execution Control

| Variable        | Values        | Default                                                                                       | Purpose                                                                                                                                                                                                                                                                                                                                                               |
| --------------- | ------------- | --------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `$dryrun`       | `'Y'` / `'N'` | varies                                                                                        | When `'Y'`, the script reports what it would do without taking destructive action. [zfsretain](../commands-and-modules/modules.md#zfsretain) treats any value other than `'N'` as dry-run when called directly; [zfscleanup](../commands-and-modules/commands.md#zfscleanup) and [zfsdailybackup](../commands-and-modules/commands.md#zfsdailybackup) default to live |
| `$autoproceed`  | `'Y'` / `'N'` | `'N'`                                                                                         | When `'Y'`, suppresses the interactive "press enter" confirmations that gate destructive steps                                                                                                                                                                                                                                                                        |
| `$force`        | `'Y'` / `''`  | `''`                                                                                          | When `'Y'`, [zfs-send-receive](../commands-and-modules/modules.md#zfs-send-receive) destroys the destination dataset before a full copy (`doincrementals='N'`). Does not apply to incremental copies                                                                                                                                                                  |
| `$releaseholds` | `'Y'` / `'N'` | `'N'`                                                                                         | When `'Y'`, [zfsdelsnap](../commands-and-modules/modules.md#zfsdelsnap) releases holds on a snapshot before destroying it rather than refusing. Also accepted as the literal string `'releaseholds'` at the third argument to `delsnap`                                                                                                                               |
| `$skipbusy`     | `'Y'` / `'N'` | `'Y'` in [zfsretain](../commands-and-modules/modules.md#zfsretain), `'N'` in direct `delsnap` | When `'Y'`, a `zfs destroy` failure (e.g. snapshot is busy or held) is logged as `WARN` and the script continues. When `'N'`, the failure is fatal. In both cases, [zfs-diagnose-busy](../commands-and-modules/commands.md#zfs-diagnose-busy) is called first to report the specific cause                                                                            |

## Dataset and Snapshot Selection

These drive [`zfsbuildfsarray`](../commands-and-modules/modules.md#zfsbuildfsarray),
which is used by virtually every multi-dataset command.

| Variable            | Type          | Purpose                                                                                                                 |
| ------------------- | ------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `$includes`         | array         | Substrings datasets must contain to be kept. Prefix `=` for exact match. Empty array = keep all                         |
| `$excludes`         | array         | Substrings that cause datasets to be dropped. Prefix `=` for exact match                                                |
| `$startwith`        | string        | Trim datasets from the front until one matches. Prefix `=` for exact match                                              |
| `$endwith`          | string        | Trim datasets from the back after the first match (inclusive). Prefix `=` for exact match                               |
| `$depth`            | integer       | Recursion depth passed to `zfs list -d`. `0` = root only, `""` = unlimited                                              |
| `$bottomup`         | `'Y'` / `'N'` | When `'Y'`, sort the dataset list descending                                                                            |
| `$buildfsarraytype` | string        | Dataset types to include. Default `filesystem,volume`. Any combination of `filesystem`, `volume`, `snapshot`, or `pool` |
| `$sortby`           | string        | ZFS property to sort by. Default `name`; `creation` is the other common choice                                          |

## ZFS Send/Receive

These drive [`zfs-send-receive`](../commands-and-modules/modules.md#zfs-send-receive)
and its wrappers ([`zfsdailybackup`](../commands-and-modules/commands.md#zfsdailybackup), [zfssendoffsite](../commands-and-modules/commands.md#zfssendoffsite), [zfsrestore](../commands-and-modules/commands.md#zfsrestore),
[`zfsfullcopy`](../commands-and-modules/commands.md#zfsfullcopy)).

| Variable                        | Purpose                                                                                                                                                                                                                                                                                                                |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `$sourcefs`                     | Source dataset (typically a pool or top-level dataset)                                                                                                                                                                                                                                                                 |
| `$destfs`                       | Destination pool or dataset                                                                                                                                                                                                                                                                                            |
| `$sourcefsremovequalifiers`     | Number of leading path components to strip from the source when constructing the destination path                                                                                                                                                                                                                      |
| `$doincrementals`               | `'Y'` = send incrementally from the most recent common snapshot; `'N'` = full send                                                                                                                                                                                                                                     |
| `$dointermediates`              | `'Y'` = include all intermediate snapshots in an incremental send (`-I`); `'N'` = skip them (`-i`)                                                                                                                                                                                                                     |
| `$commsnap_mostrecent`          | `'OLDEST'` = use the oldest snapshot on the source as the incremental base (destination is ignored); otherwise use the most recent common snapshot                                                                                                                                                                                                                     |
| `$verify_after_transfer`        | `'Y'` = after each successful receive, compare destination snapshot GUID with source; treat mismatch as fatal                                                                                                                                                                                                          |
| `$nextsnap`                     | Name of the new snapshot to create before sending. The literal `'notneeded'` tells [zfs-send-receive](../commands-and-modules/modules.md#zfs-send-receive) to look up the most recent existing snapshot on the source instead of creating one (used by [`zfsrestore`](../commands-and-modules/commands.md#zfsrestore)) |
| `$label`                        | Snapshot label (e.g., `dailybackup`, `offsite`) used for matching and for bucket assignment                                                                                                                                                                                                                            |
| `$originlabel` / `$targetlabel` | Override the label used on the source and destination sides independently                                                                                                                                                                                                                                              |
| `$receive_s_option`             | Set to `'s'` to enable resumable receives (`zfs receive -s`)                                                                                                                                                                                                                                                           |
| `$resumablethreshold`           | Size in bytes above which resumable receives are used. Default 50 GB                                                                                                                                                                                                                                                   |
| `$maxcommsnapperiod`            | Maximum age (days) of an acceptable common snapshot. Default `130`                                                                                                                                                                                                                                                     |
| `$pv_rate_limit`                | Maximum transfer rate passed to `pv -L` (e.g. `200M`, `1G`). Leave empty to disable rate limiting. In headless mode `pv` is used only for rate limiting (no progress display)                                                                                                                                          |
| `$pvthreshold`                  | Size in bytes above which `pv` progress display is used. Default 300 MB                                                                                                                                                                                                                                                |

## Retention

Set by [`zfsretain`](../commands-and-modules/modules.md#zfsretain) after
reading a policy via `zfsconfig_get_retention`:

| Variable                     | Type    | Purpose                                                                                                                                                     |
| ---------------------------- | ------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `$bktname[i]`                | string  | Bucket letter (`d`, `w`, `m`, `s`)                                                                                                                          |
| `$bktretain[i]`              | integer | Number of snapshots to keep in that bucket                                                                                                                  |
| `$minage[i]`                 | integer | Minimum age (days) before a snapshot in that bucket is eligible for deletion                                                                                |
| `$leadingqualifierstodelete` | integer | Number of leading path components to strip when computing the counterpart dataset for [zfscheckagainst](../commands-and-modules/modules.md#zfscheckagainst) |

## Node Configuration

Sourced from `/etc/zfsutilities-node.conf` by `node-lib.sh` and the
repo-root scripts.

| Variable       | Purpose                                                                                                                                           |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `NODE_MODE`    | `single-node` or `two-node`                                                                                                                       |
| `THIS_HOST`    | Short hostname of the current node (single-node)                                                                                                  |
| `STORAGE_HOST` | Short hostname of the storage node (two-node). In single-node mode set to `$THIS_HOST`                                                            |
| `COMPUTE_HOST` | Short hostname of the compute node (two-node). In single-node mode set to `$THIS_HOST`                                                            |
| `STORAGE_IP`   | IP address of the storage network interface on the storage node (two-node)                                                                        |
| `IQN_PREFIX`   | iSCSI IQN prefix for targets on the storage node (two-node)                                                                                       |
| `POOL_TARGET`  | Associative array mapping pool name → iSCSI target short name (two-node). See [Data Structures](data-structures.md#pool_target-associative-array) |

## Infrastructure

| Variable                | Set by     | Purpose                                                                                                      |
| ----------------------- | ---------- | ------------------------------------------------------------------------------------------------------------ |
| `$mydir`                | `bashinit` | Directory of the currently-running script. Every script uses `source $mydir/<helper>` to locate its siblings |
| `$ZFSCONFIG_PATH`       | caller env | Override the JSON config path (`/root/.config/zfsutilities.json` by default). Useful for testing             |
| `$ZFSCONFIG_LEGACY_DIR` | caller env | Directory searched for legacy `zfsretainpol-*` files when the JSON config has no retention data              |

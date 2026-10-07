# Messages Reference

This section catalogs messages that may be issued by ZFS Utilities scripts
and GUI modules, organized by functional group and then by the script or
module that issues them. Each entry is a table whose columns describe:

- **Message prefix** — the message text, with variable parts elided as `...`; the `LEVEL:` token is part of the text
- **Meaning** — what the message indicates and what conditions lead to it
- **Response** — what happens after the message is issued, and what action (if any) is appropriate

!!! note "Coverage"
    This section catalogs every script and GUI module that issues messages,
    organized by functional group. Rows cover the actionable messages of each
    source: every `WARN:`/`FATAL:`/`ERROR:` plus the informational messages
    that mark a decision, gate, prompt, or outcome. Routine per-item progress
    lines are omitted. New entries are added as scripts and modules evolve.

!!! note "Answering prompts"
    In a terminal, answer a prompt by typing at it. When the same script runs
    as a GUI job, its prompts are held on screen as numbered input requests
    and are answered in the Input entry as `N response` — see
    [the GUI bottom panel](../user-guide/gtk-gui.md#bottom-panel). Rows below
    describe the answer itself (for example "y proceeds") either way.

---


## Priority prefixes

Messages may begin with one of the following priority tokens (lowest to
highest):

```
DEBUG:  VERB:  INFO:  WARN:  FATAL:  [none]
```

---

## Backup and Send/Receive

### [zfs-send-receive](../commands-and-modules/modules.md#zfs-send-receive)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: sourcefs ($1) must be specified.` | No source dataset argument | Script aborts (exit 8) |
| `FATAL: destfs ($2) must be specified.` | No destination dataset argument | Script aborts (exit 8) |
| `FATAL: Could not capture existing holds on .... Aborting to avoid losing target hold tags. Set preserve_target_holds='N' to skip hold preservation.` | Before a full-copy run that will wipe the destination, the holds capture failed; nothing has been mutated yet | Script aborts (exit 8); fix the hold listing or set the suggested override |
| `VERB: Dataset ... is a ZFS clone. It will be backed up as a regular dataset.` | The source has a clone origin, so it is sent as a plain dataset copy | Informational |
| `INFO: About to copy the following datasets to ...:` | Plan summary; the dataset list follows, then a press-enter prompt when autoproceed != 'Y' (after which autoproceed is forced to 'Y' for the rest of the run) | Press Enter to proceed to the per-dataset loop |
| `WARN: Backup operation aborted by user due to lock conflict on source '...'.` / `... on destination '...'.` | The operator chose to abort the whole operation while resolving a dataset lock | Script aborts (exit 9) |
| `INFO: Skipping dataset ... (lock conflict on source).` / `... (lock conflict on destination).` / `... (lock conflict on destination after preparation).` | The operator chose to skip this dataset while resolving a lock | Dataset skipped, run continues |
| `WARN: No snapshots found on ... (nextsnap=notneeded). Skipping.` | A run that did not need a new snapshot found the source has no snapshots at all | Dataset skipped, run continues |
| `INFO: Dry-run: Would create snapshot ...` | Dry-run replacement for creating the new source snapshot | Informational; nothing created |
| `FATAL: Unable to create the required snapshot .....` | `zfs snapshot` failed in a real run | Script aborts (exit 8) |
| `WARN: No snapshots were found for .....` | The source dataset has no snapshots; a full copy is offered instead | Prompt: y switches to full copy, n skips the dataset |
| `WARN: No common snapshot found between ... and .....` | The destination exists but shares no snapshot with the source — the incremental base is lost | Prompt: y/n for a full copy (autoproceed='Y' auto-answers yes); investigate why the destination diverged |
| `INFO: Destination ... does not exist; creating new dataset from .....` | The destination dataset does not exist, so a full copy creates it | Prompt: y/n for the full copy (autoproceed='Y' auto-answers yes); confirm the destination path is correct |
| `INFO: Skipping ....` | The operator declined a full copy, chose [S] at the resume-token menu, or declined a rollback | Dataset skipped, run continues |
| `INFO: A common snapshot between ... and ... was found. However, the destination snapshot is not the most recent one. ...` | A common base exists but the destination has newer snapshots; the listed snapshots would be rolled back, bypassing holds | Prompt: y rolls back and transfers, n skips the dataset |
| `INFO: This rollback is caused by a scope mismatch: ...` | The newer destination snapshots carry a different label than the one being sent — overlapping backup/offsite profile scopes | Align the source scopes of the overlapping profiles; the y/n rollback prompt still decides this run |
| `WARN: autoproceed=Y — rolling back ... to ... and proceeding with transfer` | Non-interactive runs take the rollback branch automatically | Informational; holds are released and the rollback executes |
| `WARN: Non-interactive mode — skipping ... (rollback required for ...)` / `WARN: No interactive input — skipping ... (rollback required)` | A rollback decision is needed but stdin is not a terminal (cron/GUI), or three reads returned nothing | Dataset skipped, run continues |
| `INFO: Skipping ... (rollback declined).` | The operator answered n at the rollback prompt | Dataset skipped, run continues |
| `INFO: Dry-run: Would release matching holds and rollback ... to ...` | Dry-run replacement for the rollback branch | Informational; nothing rolled back |
| `WARN: Cannot roll back ... to ... — snapshot(s) still have user holds: .... Skipping .....` | After releasing the offsite holds, other user holds still block `zfs rollback` | Dataset skipped; release the listed holds or re-examine why they are set |
| `FATAL: Unable to roll back to snapshot .....` | `zfs rollback -r` itself failed | Script aborts (exit 8) |
| `FATAL: Failed to determine common snapshot for .....` | Common-snapshot handling returned an unexpected result (rollback failure or an unhandled `zfscommsnap` return code — see also the `WARN: Unhandled return code=... from zfscommsnap` line just above) | Script aborts (exit 8) |
| `INFO: Found resume token for .... Preparing to resume transfer.` | The destination has a live receive resume token; an interrupted transfer resumes instead of restarting | Informational; the token is validated next |
| `WARN: Resume token is invalid or stale. Aborting resume token.` | The token probe matched a known stale pattern | The token is discarded (`zfs receive -A`) and the dataset is retried fresh |
| `WARN: Resume token validation failed with unexpected error: ...` | The token probe failed with an unrecognized error | autoproceed aborts the token and retries; non-interactive runs skip the dataset; interactive runs get the [A]/[S]/[Q] menu |
| `INFO: Options: [A] Abort resume token and retry (may trigger full copy) [S] Skip this dataset [Q] Quit` | Interactive menu for the resume-token error | A aborts the token and retries, S skips the dataset, Q exits 8 |
| `INFO: Aborting resume token...` | The operator chose [A] | Token discarded, dataset retried fresh |
| `WARN: Non-interactive mode — skipping ... (resume token error for ...)` / `WARN: No interactive input — skipping ... (resume token error)` | Token error and no interactive input | Dataset skipped, run continues |
| `INFO: Remaining data to transfer: ....` | Human-readable size of the resumed receive | Informational; the resume transfer follows |
| `INFO: Approximately ... bytes to transfer.` | Per-step size plan, printed when the estimate exceeds the `pvthreshold` (default 300 MB), which also enables `pv` progress display | Informational; confirm the destination has room |
| `INFO: Small transfer.` | The estimate is at or below `pvthreshold`, so `pv` is disabled for this step | Informational |
| `VERB: Data to send is more than ... bytes. Making transfer of ... resumeable.` | The estimate exceeds the resumable threshold (default 50 GB), so the receive is upgraded to resumable (`zfs receive -s`) | Informational |
| `VERB: Full copy — transfer of ... will be resumable.` | Full-copy mode forces a resumable receive | Informational; visible in the GUI log viewers when the level filter is `VERB` or `DEBUG` |
| `WARN: Insufficient space on destination pool '...'.` | The estimated transfer (plus a 10% margin) does not fit the destination pool (issued by the shared transfer library) | Prompt: y attempts the transfer anyway, n skips; autoproceed='Y' skips the dataset |
| `INFO: Skipping ... (insufficient space).` | The space check failed and the run is non-interactive or the operator declined | Dataset skipped, run continues |
| `WARN: Proceeding despite insufficient space.` | The operator answered y at the space prompt | Transfer attempted anyway |
| `DEBUG: Proxmox tools not available - cannot check for running VMs.` | The running-VM safety gate cannot run on this system and is bypassed | Run continues without the check |
| `WARN: Running VMs detected on destination dataset ...!` | Destructive preparation is imminent and VMs are running on the destination (list follows) | Prompt: y proceeds (DANGEROUS), n skips the dataset; autoproceed='Y' skips |
| `INFO: Skipping ... (running VMs).` | Running VMs found and the run is non-interactive or the operator declined | Dataset skipped, run continues |
| `WARN: Proceeding despite running VMs - data corruption may occur!` | The operator answered y at the DANGEROUS prompt | Destructive preparation proceeds |
| `INFO: Dry-run: Would ... (~...)` | Dry-run replacement for every real transfer step (send/receive or resume), with the size when known | Informational; nothing executed |
| `INFO: Dry-run: Would send ... -> ... (incremental|full copy, ~...)` | Dry-run plan for the current step, including transfer type and size; a following `Options:` line shows force-receive/resumable flags | Informational; nothing executed |
| `Are there holds on ... snapshots?` | A real send/receive pipeline just failed; held destination snapshots are the suggested cause, and the holds are dumped | Script aborts (exit 8); release the listed holds or investigate |
| `FATAL: Verification failed — destination snapshot ... does not exist.` | Post-transfer verification: the expected snapshot never appeared on the destination | Script aborts (exit 8) |
| `FATAL: Verification failed — GUID mismatch for .....` | Source and destination snapshot GUIDs differ after the receive (source/dest GUIDs on the next lines) | Script aborts (exit 8) |
| `VERB: Verified ... — GUID matches source.` | Post-transfer verification passed | Informational |
| `INFO: Destination snapshot ... already exists.` / `INFO: Destination snapshot ... already exists. Skipping full copy of .....` | The target snapshot is already present and force mode is off — the dataset is up to date | Dataset skipped, run continues |
| `INFO: Doing a full copy of ... to .....` | Full-copy mode entered (receive `-F` follows); press-enter prompt when autoproceed != 'Y' | Press Enter to proceed to destination preparation and the two-step transfer |
| `INFO: Destination ... is a pool root; deleting snapshots only (pool cannot be destroyed).` | Destructive full-copy preparation targets a pool root, so it is scaled down to snapshot deletion | Informational; snapshots are deleted, the pool itself is kept |
| `INFO: Dry-run: Would destroy destination dataset ... and all children` | Dry-run preview of destructive destination preparation | Informational; nothing destroyed |
| `WARN: About to destroy destination dataset ... AND all of its child datasets and snapshots, ignoring holds, in preparation for a full transfer from ....` | Destructive preparation (dataset subtree wipe) is imminent; press-enter prompt when autoproceed != 'Y' | Press Enter to proceed, or interrupt to stop the run |
| `WARN: Dataset deletion failed.` / `WARN: Snapshot deletion failed for .....` | Destination preparation (subtree wipe or snapshot wipe) failed | Followed by `FATAL: Failed to prepare destination ... for full copy.` and exit 8 |
| `INFO: Dry-run: Would delete all snapshots of ...` | Dry-run preview of the non-destructive preparation (snapshot wipe) | Informational |
| `WARN: About to delete all snapshots of destination dataset ..., ignoring holds, in preparation for a full transfer from .... (Child datasets will NOT be touched.)` | Snapshot-wipe preparation is imminent; press-enter prompt when autoproceed != 'Y' | Press Enter to proceed, or interrupt to stop the run |
| `FATAL: Failed to prepare destination ... for full copy.` | Destination preparation failed (the failing step logged its own WARN just above) | Script aborts (exit 8) |
| `WARN: No source snapshots available for full copy of .....` | Full copy requested but the source has no snapshots | Dataset skipped, run continues |
| `WARN: Unable to get stream size estimate of ... .....` | The `zfs send -nPc` size estimate failed; the transfer proceeds without a space check | Informational; verify destination space manually |
| `INFO: Dry-run: stream size estimate not available for ... ... (snapshot not created)` | Dry-run only: the estimate dry-run cannot run because dry-run never created the snapshot | Informational |
| `INFO: Dry-run: Would create destination dataset ...` | Dry-run replacement for `zfs create -pu` of the destination | Informational |
| `INFO: Dry-run: Would rebuild iSCSI LUNs for ...` | Dry-run preview of the iSCSI rebuild step after a destructive full copy | Informational |
| `WARN: Hold reapply on ... incomplete; see messages above.` | End of run: restoring the destination holds captured before a full copy failed for at least one hold | Check the destination's holds manually |

### [zfsdailybackup](../commands-and-modules/commands.md#zfsdailybackup)

Runs from cron or the GUI. Phases are gated by the configuration flags (`pull_*`, `backup_*`, `prune`).

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: New snapshot: ...` | The snapshot name the whole run will use | Informational; a press-enter prompt follows (falls through under cron) |
| `INFO: Dry-run: Would run pre-backup script` | Dry-run: the pre-backup hook is skipped | Informational |
| `INFO: Running pre-backup script...` | The configured pre-backup hook is executing | Informational; the result follows |
| `INFO: Pre-backup script completed successfully.` | The hook returned 0 | Informational |
| `FATAL: Pre-backup script failed (rc=...). Aborting backup.` | The hook returned non-zero | Backup aborts; fix the hook |
| `WARN: Failed to push scripts to ...` | `scp` of rsync-dailybackup to the remote host failed; the remote pull is not attempted | The pull surfaces as `Pull from ... failed` below; check SSH access |
| `WARN: could not push bashinit to ...` / `WARN: could not push node config to ...` | Pushing a support file to the remote host failed; the remote run may not initialize or find its storage host | Check SSH access and rerun |
| `WARN: Pull from ... failed (rc=...); continuing to next step.` | The remote pull (script push + remote rsync-dailybackup) returned non-zero | Run continues with the next phase; investigate the remote failure |
| `WARN: Local pull failed (rc=...); continuing to next step.` | The local rsync-dailybackup run returned non-zero | Run continues with the next phase; the rsync messages above show the failing job |
| `INFO: *** Pulling rsync backup from ... ***` | Phase banner for a configured remote pull | Informational |
| `INFO: Dry-run: Would push rsync scripts to ... and run remote backup` | Dry-run replacement for a remote pull phase | Informational |
| `INFO: Dry-run: Would run local rsync and package backup` | Dry-run replacement for the local pull phase | Informational |
| `INFO: *** Backing up ... to ... ***` | Phase banner for a configured send/receive pair | Informational |
| `INFO: Dry-run: Skipping snapfile cleanup (preserved for real run)` | Dry-run: snapfile cleanup is deliberately not executed | Informational |
| `INFO: Dry-run: Would prune snapshots.` | Dry-run replacement for the prune phase | Informational |
| `INFO: *** Pruning snapshots. ***` | The retention prune phase is running | Informational |
| `INFO: *** zfsdailybackup completed. ***` | All phases finished | Informational |

### [rsync-dailybackup](../commands-and-modules/modules.md#rsync-dailybackup)

Both sourced by `zfsdailybackup` and executed standalone on remote hosts.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: rsync-dailybackup: missing ... — skipping rsync pulls` | Neither the node config nor the legacy two-node config is readable at script load | Script skips all jobs (returns/exits 0); install or fix the node config |
| `INFO: rsync-dailybackup has no configured jobs; skipping.` | The `rsync_dailybackup_jobs` array is empty | Informational; nothing to do |
| `WARN: rsync-dailybackup: skipping malformed job: ...` | A job entry has an empty source/destination or the source equals the destination | Job skipped; fix the job entry |
| `WARN: rsync-dailybackup: ... -> ... failed (rc=...)` | `rsync` returned non-zero for this job | Other jobs continue; the failure is returned to the caller at the end |

### [zfssend](../commands-and-modules/commands.md#zfssend)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: Next snap: ...` | The snapshot name the send will use | Informational; press-enter prompt when autoproceed != 'Y' |
| `INFO: *** Copy completed. ***` | The send/receive finished | Informational |

### [zfssendrepo](../commands-and-modules/commands.md#zfssendrepo)

Emits no log messages; it is a plain `set -x` script that rsyncs the repository to a remote host. Failures surface only as rsync's own output and exit code.

### [zfsfullcopy](../commands-and-modules/modules.md#zfsfullcopy)

Sourceable helper that forces a full copy (used by restore and migrate flows).

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: $restoresourcefs was not specified.` | The required source variable is empty before send/receive starts | Script aborts (exit 8) |
| `FATAL: $destfs was not specified.` | The required destination variable is empty | Script aborts (exit 8) |

### [zfscommsnap](../commands-and-modules/modules.md#zfscommsnap)

Communicates almost entirely via return codes; callers such as `zfs-send-receive` turn them into the common-snapshot messages listed above.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: ... is ... days old. The maximum is .... Ignoring.` | "Find another common snap" mode: a candidate base snapshot exceeds the maximum common-snapshot age | Candidate skipped; the search continues |

### [zfsgetsendsize](../commands-and-modules/commands.md#zfsgetsendsize)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: A snapshot must be given.` | No snapshot argument; the probe runs anyway and fails | Supply a snapshot argument |
| `WARN: Unable to get send size for ....` | The `zfs send -nPc` dry-run failed | Check the snapshot name; an empty size is printed |

### [zfsresume](../commands-and-modules/commands.md#zfsresume)

Diagnostic/repair tool for receive resume tokens; it never performs the resume send itself.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: A resumable destination dataset must be given in $1.` | No argument | Script aborts (exit 8) |
| `FATAL: Could not acquire write lock on resumable destination ...` | The dataset's write lock is unavailable | Script aborts (exit 8); resolve the lock and rerun |
| `FATAL: Unable to retrive receive_resume_token for ....` (message spelling) | The token lookup over the dataset and its descendants failed | Script aborts (exit 8); check the dataset name |
| `WARN: Resume token is invalid or stale. Deleting resume token.` | The token probe matched a known stale pattern | The token is discarded with `zfs receive -A`, rolling back the partial receive |
| `INFO: Resume token for ... seems valid.` | The probe failed with an unrecognized (non-stale) error — the token was not positively validated | Inspect the token manually; it is left in place |

### [zfs-migrate-send](../commands-and-modules/commands.md#zfs-migrate-send)

Executed by the GUI Migrate Pool wizard, not for direct CLI use. On failure it keeps the receive resume token so the migration can resume.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: zfs-migrate-send requires sourcefs, destfs, and snapname to be set.` | The wizard variables were not assigned | Script aborts (exit 8) |
| `INFO: Found resume token for .... Preparing to resume transfer.` | The destination has a live token from a previous attempt | Informational; the token is validated next |
| `WARN: Resume token is invalid or stale. Aborting resume token.` | The token probe matched a stale pattern | Token discarded; a fresh send follows |
| `WARN: Resume token validation failed with unexpected error: ...` | The probe failed with an unrecognized error | Token discarded and retried as a fresh send |
| `VERB: datatosend=...` / `INFO: Remaining data to transfer: ....` | Size of the resumed transfer | Informational |
| `WARN: Size estimate dry-run of ... failed.` / `WARN: Unable to get stream size estimate of .....` | The `zfs send -n` size estimate failed; the transfer proceeds without a space check | Informational; verify destination space manually |
| `INFO: Approximately ... bytes to transfer.` | Size plan for the fresh (full or catch-up) send | Informational |
| `WARN: Proceeding despite insufficient space.` | The shared space check failed; the wizard pre-validated capacity, so this is warn-only | Informational; the transfer is attempted |
| `FATAL: Migrate Pool transfer interrupted; re-run Migrate Pool to resume from the receive resume token on ....` | The transfer failed; the resume token is intentionally kept | Re-run Migrate Pool to resume |

### [PVE-send-to-archive](../commands-and-modules/commands.md#pve-send-to-archive)

Example script that archives Proxmox VM datasets to `.zfssendstream` files.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: Could not acquire write lock on ...` | The dataset's write lock is unavailable | Script aborts (exit 8); resolve the lock |
| `FATAL: Could not get name of most recent snapshot for .....` | The common-snapshot helper returned nothing | Script aborts (exit 8); check the dataset's snapshots |
| `INFO: About to send ... to .../.../....zfssendstream` | Per-dataset send target; press-enter prompt when autoproceed != 'Y' | Press Enter to proceed |
| `FATAL: Directory creation for .../... failed.` | `mkdir -p` of the archive directory failed | Script aborts (exit 8); check permissions/path |
| `INFO: zfs send -cw ... \| pv \| cat - > .../.../....zfssendstream` | Preview of the pipeline about to run | Informational |
| `FATAL: Failed to send ... to ....zfssendstream.` | The send pipeline returned non-zero | Script aborts (exit 8); check space in the archive dataset |
| `FATAL: Could not create the VM config archive directory ....` | `mkdir -p` for the Proxmox config copy failed | Script aborts (exit 8) |
| `FATAL: Failed to copy ... to .....` | Copying the Proxmox VM config failed | Script aborts (exit 8) |
| `INFO: Archive of ... completed.` | Final outcome; the archived datasets and config file are listed | Informational |

### [backup_page](../commands-and-modules/python-modules.md#backup_pagepy)

GUI Backup tab. Builds and launches the backup run; also owns the snapfile (previous-snapshot name) and the tab's Save/Revert of its config. The same run launched from the Schedule tab is logged by [profile_runner](#profile_runner) instead.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: Previous snapshot name found: ...` | Snapfile on disk contained a saved snapshot name, preloaded into the entry | Informational; reused unless regenerated |
| `INFO: New snapshot name: ...` | A fresh snapshot name was generated into the entry | Informational |
| `WARN: Generate or enter a snapshot name first` | Run Backup pressed with empty snapshot name | Run aborted |
| `INFO: Backup cancelled` | User cancelled the pre-run confirmation dialog | Run aborted |
| `INFO: Dry run mode enabled — no changes will be made` | Global dry-run toggle active for this run | Steps become "Would ..." messages; nothing executes |
| `INFO: Dry-run: Would run pre-backup script` | Pre-backup script enabled but dry-run is active | Step skipped |
| `INFO: Pull steps disabled by user; skipping` | Pull-steps toggle off | No rsync pull steps built |
| `WARN: Skipping ... -> ...: ... is not mounted` | Safety gate — a local mount source for a pull step is not mounted | That pull step skipped |
| `WARN: Skipping ... -> ...: ... is not accessible` | Safety gate — reading the mount path failed | That pull step skipped |
| `INFO: Dry-run: Would rsync ... -> ...` | Dry-run variant of a pull or ZFS-keys rsync step | Step skipped |
| `WARN: Skipping ZFS keys ... -> ...: ... is not mounted` / `... is not accessible` | Keys-path mount/accessibility gate failed | Keys backup skipped |
| `WARN: Skipping ZFS keys backup — destination is not encrypted. Set zfs_keys_dest to an encrypted dataset.` | Safety gate — the keys destination dataset is not encrypted, so raw keys are refused | Keys backup skipped; set an encrypted destination |
| `VERB: Prune step restricted to the ... send/receive step(s)' source and destination datasets (derived at prune time).` | Decision — prune scope narrowed to the active send/receive datasets | Prune step built with that scope |
| `INFO: No active send/receive steps; skipping prune step (no new snapshots to prune).` | Retention-after-backup requested but no send/receive steps are active | Prune step not built |
| `INFO: Dry-run: Would run post-backup script` | Post-backup script requested but dry-run is active | No post-backup step |
| `WARN: No active steps to run` | The step list (including the post-backup step) is empty | Run aborted before start |
| `INFO: Snapshot: ...` | Final record of the snapshot name the run will use | Runner starts |
| `INFO: Dry-run: Skipping snapfile cleanup (preserved for real run)` | Run finished in dry-run with snapfile cleanup enabled | Snapfile left in place |
| `INFO: Backup config saved to /var/lib/zfsutilities/config.json` | Save Config succeeded (a warning dialog may have shown scope mismatches first) | Dirty tracker marked clean |
| `WARN: Error saving config: ...` | OSError during config save | Save aborted; UI stays dirty |
| `INFO: Nothing to revert` | No saved-state tracker exists yet | Revert aborted |
| `INFO: Backup config reverted to last saved state` | Revert applied | Informational |
| `INFO: All steps selected` / `All steps deselected` | Mass toggle applied to all step checkboxes and script toggles | Informational |

### [backup_runner](../commands-and-modules/python-modules.md#backup_runnerpy)

Executes a built step list (backup, offsite, restore, prune) in the GUI. Messages are issued through a runner-local log function that binds them to this run's own session log file, so concurrent runs keep separate logs; they also appear in the GUI log panel.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: Starting ...: ... step(s)` | Run start record (label plus step count) after session-log creation and rsync-log truncation | First step spawns |
| `INFO: Interrupting lock wait` | Cancel requested while the child is waiting for a dataset lock | SIGINT sent to the child to break the wait |
| `WARN: Post-step callback failed during cancel: ...` | A step post-callback raised during cancellation | Cancel path continues |
| `INFO: ... cancelled` | Cancel completed; trailer written with cancelled status | Runner torn down; completion callback fires with cancelled=True |
| `WARN: Error launching: ...` | Spawning a step failed (OSError/FileNotFoundError) | Step skipped; runner advances to the next step |
| `WARN: Pre-step callback failed: ...` | Step pre-callback raised before spawn | Step still runs |
| `WARN: Post-step callback failed: ...` | Step post-callback raised after spawn failure or exit | Continue to the next step |
| `WARN: Unexpected error while starting next step: ...` / `Unexpected error while checking process: ...` | Unhandled exception in the step-advance or process-poll path | Run aborted with rc=1 |
| `WARN: Post-backup script exited with rc=...` | The post-backup script finished non-zero after an earlier fatal step | Run finishes with the original fatal rc |
| `INFO: ... ... done (rc=...)` | Rsync step completion record including rc | Informational |
| `INFO: Rsync log: /var/log/zfsutilities/rsync-backup.log` | Pointer to the dedicated rsync output log | Operator can inspect the file |
| `WARN: Step exited with rc=...` | Any step finished non-zero | Failure handling follows (rc=9 user abort, fatal abort, or continue) |
| `WARN: ... failed: ...` | Rsync-specific diagnosis for the failed step | Diagnostic |
| `INFO: ... aborted by user` | Step rc=9 (user abort) | Run ends cancelled; trailer rc=9 |
| `FATAL: Aborting ... because step failed` | A step marked fatal failed | Post-backup step runs first (if any), then the run finishes with the step's rc |
| `WARN: ... failed (rc=...)` | Final summary when the run finishes non-zero | History entry recorded as failed |
| `INFO: ... complete` | Final summary on success | History entry recorded as success |
| `WARN: Error during finish UI cleanup: ...` | Exception in the finish/progress cleanup block | Finishing continues |
| `WARN: Could not add history entry: ...` | Appending to the run history failed | Run missing from history |
| `WARN: Could not write session trailer: ...` | Session-log trailer/index status update failed | Log shows no `# END` trailer |
| `WARN: Could not restore previous session log: ...` | Restoring the pre-run session-log target failed | Session-log target may still point at the finished run's file |
| `WARN: on_complete callback failed: ...` | Page-level completion callback raised | Runner already finished; error logged only |
| `DEBUG: Could not remove stdout source: ...` / `Could not remove stderr source: ...` / `Could not access main context for cleanup: ...` | GLib source cleanup failures during I/O teardown | Teardown continues |

### [command_builders](../commands-and-modules/python-modules.md#command_builderspy)

Builds the bash scripts the runners execute. The messages below are emitted by the generated prune script (embedded `log_msg` strings), so they appear in the GUI log and that run's session log.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: No datasets found for ...; skipping prune mapping.` | The buildfsarray found no datasets for a send/receive source, so no prune targets were mapped | That source contributes nothing to the prune; script continues |
| `WARN: No backup datasets to prune; skipping prune step.` | The aggregated prune list across all steps is empty | Script exits 0 — prune treated as success/no-op |

## Offsite Backup

### [zfssendoffsite](../commands-and-modules/commands.md#zfssendoffsite)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: No offsite pools are currently online. ...` | None of the pools marked `offsite_candidate` in the JSON config is imported (the continuation lines list the candidates looked for and the pools found) | Script exits 8 before any copy runs; import a configured offsite-candidate pool and rerun |
| `INFO: Will be sending to pool ... The snapshot will be ...` | An online offsite pool and the `@offsite` snapshot were selected | Informational; a press-enter prompt follows only when autoproceed != 'Y' |
| `INFO: Dry-run: Would apply holds to ... and ... snapshots.` | Dry-run: the post-copy hold step is suppressed | Informational; holds not applied |
| `INFO: Applying holds to ... and ... snapshots.` | A copy step succeeded, so `zfshold` protects the source and destination snapshots | Informational |
| `INFO: ***  Step ...: Sending ... to ...  ***` | Copy-step banner; each step is gated by its `stepN` configuration flag | Informational |

### [zfsfindoffsitepool](../commands-and-modules/modules.md#zfsfindoffsitepool)

Emits no log messages; it only prints the matching online offsite pool name (or nothing) to stdout for the calling script.

### [zfsoffsiteretain](../commands-and-modules/commands.md#zfsoffsiteretain)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: Pruning offsite snapshots from ....` | A pool containing `@offsite-` snapshots was found and is online; retention pruning follows | Informational |
| `INFO: Pool ... is offline — skipping.` | The pool is not imported; skipping protects snapshots an offline offsite pool still needs | Informational; import the pool to prune it |
| `INFO: zfsoffsiteretain completed.` | Every discovered pool was pruned or skipped | Informational |

### [offsite_page](../commands-and-modules/python-modules.md#offsite_pagepy)

GUI Offsite tab. Builds and launches the offsite run and owns the tab's Save/Revert. The same run launched from the Schedule tab is logged by [profile_runner](#profile_runner) instead; the generated send step's messages are listed under [offsite_runner](#offsite_runner) and [command_builders](#command_builders).

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: Offsite: previous snapshot name found: ...` | The offsite snapfile had a saved name, preloaded | Informational |
| `INFO: Offsite: new snapshot name: ...` | A fresh offsite snapshot name was generated | Informational |
| `WARN: Generate or enter a snapshot name first` | Run Offsite pressed with empty snapshot name | Run aborted |
| `FATAL: No offsite pool online.` | None of the registry's offsite candidates is currently importable/online | Run aborted before the confirmation dialog |
| `INFO: Offsite backup cancelled` | User cancelled the pre-run confirmation dialog | Run aborted |
| `INFO: Dry run mode enabled — no changes will be made` | Dry-run active | Dry-run behavior pushed into the step builder |
| `FATAL: No active steps to run` | No active offsite steps | Run aborted |
| `INFO: Snapshot: ...` | Final snapshot-name record before the runner starts | Runner starts |
| `INFO: Offsite config saved to /var/lib/zfsutilities/config.json` | Save Config succeeded after the optional mismatch warning dialog | Dirty tracker marked clean |
| `WARN: Error saving config: ...` | OSError during save | Save aborted |
| `INFO: Nothing to revert` | No saved-state tracker | Revert aborted |
| `INFO: Offsite config reverted to last saved state` | Revert applied | Informational |
| `INFO: All offsite steps selected` / `All offsite steps deselected` | Mass toggle of step Active checkboxes | Informational |

### [offsite_runner](../commands-and-modules/python-modules.md#offsite_runnerpy)

Builds the offsite send step. The messages below are emitted inside the generated offsite script (embedded `log_msg` strings), so they appear in the GUI log and that run's session log.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `Applying holds to $sourcefspool and $destfspool snapshots.` | Send/receive succeeded, applyholds is set, and this is not a dry-run — holds now protect the copied datasets on both pools | The hold loop runs for each dataset in the fsarray |
| `Dry-run: Would apply holds to source and destination snapshots.` | Dry-run variant — the send "succeeded" but holds are suppressed | No holds applied; script exits with its rc |

## Restore

### [zfsrestore](../commands-and-modules/commands.md#zfsrestore)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: Restoring with full copy using the oldest available snapshot.` | Restore mode selection: full copy from the oldest snapshot, then incrementals | Informational |
| `INFO: Ensuring iSCSI LUNs for restored VM disks...` | Post-restore hook: `ensure-restored-vm-iscsi` is about to run for the restored destinations (suppressed in dry-run; no-op in single-node) | Informational |
| `FATAL: $restoresourcefs was not specified.` | The required restore source was not given | Script aborts (exit 8) |
| `FATAL: $destfs was not specified.` | The required destination was not given | Script aborts (exit 8) |
| `INFO: zfsrestore completed.` | The send/receive and the iSCSI hook both succeeded | Informational |

### [zfsrestoresendstream](../commands-and-modules/commands.md#zfsrestoresendstream)

Restores `.zfssendstream` archive files back into datasets. Files already restored in earlier iterations remain restored if a later file fails.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: No matching files found.` | No `.zfssendstream` files matched the pattern in the source directory | Script aborts (exit 8); check the source path |
| `INFO: Preparing to process these files:` | Plan header; one `Restore ...` line per file, then a press-enter prompt when autoproceed != 'Y' | Press Enter to proceed |
| `INFO: cat ... \| zfs receive -v ...` | The exact receive command for the next file; press-enter prompt per file when autoproceed != 'Y' | Press Enter to proceed with this file |
| `FATAL: Could not acquire write lock on ...` | The destination dataset's write lock is unavailable | Script aborts (exit 8); resolve the lock |
| `FATAL: Unable to restore file.` | The `pv | zfs receive` pipeline returned non-zero (the lock is released first) | Script aborts (exit 8); check the stream file and destination space |

### [ensure-restored-vm-iscsi](../commands-and-modules/commands.md#ensure-restored-vm-iscsi)

Rebuilds iSCSI LUNs for restored VM-disk zvols (two-node only; silently no-ops in single-node mode).

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: Usage: ensure-restored-vm-iscsi <zvol>...` | No usable arguments given | Script returns/exits 1; supply zvols |
| `INFO: Skipping non-VM-disk zvol: ...` | The zvol name is not `vm-<vmid>-disk-<num>` form | Informational; zvol skipped |
| `WARN: ... is not in a known iSCSI pool; skipping` | The zvol's pool is not in the node config's pool list | Zvol skipped; check the node config |
| `WARN: Could not map pool ... to iSCSI target; skipping ...` | No iSCSI target mapping exists for the pool | Zvol skipped; add the mapping to the node config |
| `WARN: No VM config entry found for ... (VM ... disk ...); skipping` | The expected LUN could not be resolved — missing target mapping, unreadable VM config, or no matching by-path entry | Zvol skipped; verify the VM config and rescan |
| `INFO: Will ensure ... -> ... LUN ...` | Per-zvol plan: the target IQN and expected LUN | Informational |
| `INFO: No VM disk zvols to ensure` | After filtering, no work items remain | Informational; nothing to do |
| `INFO: Ensuring iSCSI LUNs for ... restored zvol(s)` | Work summary before the ensure loop | Informational |
| `WARN: ... already mapped to a different LUN than VM config expects` | The backstore is mapped at a LUN that differs from the VM config's by-path LUN | No remapping was made; check the VM config's disk entries |
| `WARN: Expected LUN for ... is occupied by a different backstore` | The expected LUN index is taken by another backstore | The LUN was not created; free the LUN index or adjust the VM config |
| `INFO: Saving iSCSI configuration...` / `INFO: Rescanning compute host...` | Post-ensure steps: persist targetcli config, then rescan | Informational |
| `INFO: Ensure iSCSI complete` | All work items processed | Informational |

### [restore_page](../commands-and-modules/python-modules.md#restore_pagepy)

GUI Restore tab. Validates source/destination and launches the restore. The same run launched from the Schedule tab is logged by [profile_runner](#profile_runner) instead; the generated script's messages are listed under [restore_runner](#restore_runner) and [command_builders](#command_builders).

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: ...` (while editing destination) | Live recomputation of the auto-destination raised (the message names the bad source form) | Destination entry cleared; recompute aborted |
| `WARN: Source dataset must be specified` | Run gate — empty source | Run aborted |
| `WARN: Specify datasets, not snapshots (no '@' allowed)` | Source or destination contains a snapshot qualifier | Run aborted |
| `WARN: Error: ...` (at run time) | Destination/parameter computation raised | Run aborted |
| `WARN: Destination dataset must be specified, or enable auto-determine destination` | No destination given and auto-destination off | Run aborted |
| `WARN: At least one restore part must be selected` | Both Part 1 and Part 2 unchecked | Run aborted |
| `INFO: Restore cancelled` | User cancelled the warning/confirmation dialog (which spells out Part 1 destructiveness) | Run aborted |
| `INFO: Dry run mode enabled — no changes will be made` | Dry-run active | Passed into the command builder |
| `INFO: Starting restore: ... -> ...` | Final start record after confirmation | Restore runner starts |
| `INFO: Restore config saved` | Save Config succeeded | Saved state updated |
| `WARN: Error saving config: ...` | OSError during save | Save aborted |
| `INFO: Nothing to revert` | No saved state | Revert aborted |
| `INFO: Restore config reverted` | Revert applied from saved state | Informational |

### [restore_runner](../commands-and-modules/python-modules.md#restore_runnerpy)

Builds the two-part restore script. The messages below are emitted inside the generated script (embedded `log_msg`/echo strings), so they appear in the GUI log and that run's session log.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: Ensuring iSCSI LUNs for restored VM disks...` | Post-restore hook firing; gated on a non-dry-run and a non-empty destination list | `ensure-restored-vm-iscsi` runs on the restored datasets; skipped entirely in dry-run |
| `Part one: Full copy using the oldest available snapshot.` | Phase marker — Part 1 selected; force/releaseholds set, incrementals off, commsnap OLDEST, autoproceed N | Send/receive runs with confirmation prompts; non-zero rc exits |
| `Part two: Incremental copy of remaining snapshots.` | Phase marker — Part 2 selected; incrementals and intermediates on, autoproceed Y; reuses the fsarray saved by Part 1 | Incremental send/receive runs, then iSCSI ensure and temp-file cleanup |

## Retention and Snapshot/Hold Cleanup

### [zfscheckagainst](../commands-and-modules/modules.md#zfscheckagainst)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: Snapshot ... does not exist.` | The snapshot passed to checkagainst was not found | Check snapshot name; script aborts (exit 8) |
| `WARN: No eligible enteries in the checkagainst array for ...` (message spelling) | The snapshot's dataset and label have no entry in the fss lookup table | Deletion prompts "Do you want to remove this snapshot?" — y proceeds without the counterpart check, n keeps the snapshot; add an fss entry if counterparts should be checked |
| `WARN: This is the last remaining common snap. Snapshot: ... Other dataset: ...` | Destroying this snapshot would remove the only common snapshot with a counterpart dataset | Deletion blocked (return 7) |
| `WARN: Deletion blocked — ... is the last remaining common snapshot.` | Summary form of the same block after all fss rows were checked | Deletion blocked (return 7) |
| `INFO: No counterpart snapshot for ... on ...` | The candidate snapshot's GUID is not on the counterpart, so it is not a common snapshot | Counts as verified; deletion may proceed |
| `WARN: Cannot verify counterpart - pool(s) offline: ...` | Every counterpart pool for the matched fss rows is offline and no hold-based verification succeeded | Deletion blocked for safety (return 6); bring the counterpart pool(s) online and rerun |
| `WARN: Dataset to check ... does not exist or is offline.` | The counterpart dataset cannot be listed | That destination root is skipped; other fss rows are still checked |
| `VERB: Offline pool ...: another snapshot carries hold '...' — incremental chain intact.` | The counterpart pool is offline, but the `offsite-<pool>` hold on another snapshot proves the chain is intact | Counts as verified; deletion may proceed |
| `WARN: <offsite> used in source root but no offsite candidate pools are configured. Skipping fss row: ...` / `WARN: <offsite> placeholder used but no offsite candidate pools are configured. Snapshot: ...` | The fss table uses the `<offsite>` placeholder while the JSON config lists no offsite-candidate pools | The fss row is skipped, or the snapshot counts as unverifiable (deletion may be blocked) |
| `FATAL: Unexpected RC=... from .../zfscommsnap.` / `FATAL: Internal error = ...` | An unexpected return code from the common-snapshot helper or an internal inconsistency | Script aborts (exit 8) |

### [zfsretain](../commands-and-modules/modules.md#zfsretain)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: Skipping ... (lock conflict).` | Another operation holds this dataset's write lock | Dataset skipped; retain returns 1 |
| `WARN: Cannot prune ... — locked by another operation; skipping.` | Lock wait/resolution returned an unexpected code | Dataset skipped; retain returns 1 |
| `WARN: No retention policy found for pool '...' (JSON config or legacy zfsretainpol-* file). Skipping.` | No JSON retention entry for the pool, `<offsite>`, or `default`, and no legacy policy file matched | Pruning aborted for this dataset (return 8); configure a policy for the pool |
| `WARN: Unable to evaluate retention policy fragment for '...'. Skipping.` | Evaluating the retention policy fragment failed | Pruning aborted for this dataset (return 8); check the policy syntax |
| `INFO: Removing ... --- Offsite same-month.` / `INFO: Would remove ... --- Offsite same-month.` | Phase 0 (offsite label only): an older same-month offsite snapshot is superseded by a newer one | Real runs delete it after a press-enter prompt (when autoproceed != 'Y'); the "Would remove" form is the dry-run report |
| `INFO: Removing ... --- Same-day.` / `INFO: Would remove ... ---Same-day.` | Phase 1: the older of two same-day snapshots is removed | Real runs delete it after a press-enter prompt; "Would remove" is the dry-run report |
| `INFO: Removing ... --- Bucket[ (empty)].` / `INFO: Would: Remove ... --- Bucket[ (empty)].` | Phase 2: a bucket exceeds its retention count and the oldest snapshots are removed (" (empty)" marks snapshots with no written data) | Real runs delete it after a press-enter prompt; "Would: Remove" is the dry-run report |
| `WARN: No bucket was found for .... Skipping.` | The snapshot's bucket letter is not defined in the retention policy | Snapshot kept; add the bucket to the policy or rename the snapshot |
| `VERB: Keeping ... — clone label or bucket 'c' is excluded from retention.` | Safety gate: clone-labeled snapshots and bucket `c` snapshots are never pruned | Informational; snapshot kept |
| `VERB: Keeping ... — most recent snapshot in bucket '...' is protected as incremental base.` | Safety gate: the newest snapshot in each bucket is kept as the incremental send base | Informational; snapshot kept |

### [zfscleanup](../commands-and-modules/commands.md#zfscleanup)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: About to apply snapshot retention policies to the following datasets:` | Plan header before retention runs over every dataset; press-enter prompt when autoproceed != 'Y' | Press Enter to proceed |
| `WARN: Skipped ... (rc=...); continuing with next dataset.` | Retention returned non-zero for this dataset (e.g. 8 = no policy, 1 = lock conflict) | Dataset skipped; the run continues |
| `WARN: No pools configured in JSON config; falling back to all online pools.` | The JSON pool list is empty, so every online pool is processed | Informational; configure the pool list to limit scope |
| `FATAL: Please provide a label in $3 to specify which snapshots to process.` | The required label argument is missing | Script aborts (exit 8) |
| `INFO: zfscleanup completed.` | The prune run finished | Informational |

### [zfsmassdelsnaps](../commands-and-modules/commands.md#zfsmassdelsnaps)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: At least one pool must be specified.` / `FATAL: A snapshot label must be specified.` | Required arguments missing | Script aborts (exit 8) |
| `WARN: Could not acquire write lock on ...; skipping.` | The dataset's write lock is unavailable during enumeration | Dataset skipped |
| `INFO: No snapshots would be removed by retention policies.` | Retention-respecting dry run found no candidates | Informational; nothing to do |
| `INFO: The following ... snapshots would be removed:` | Retention-respecting plan; continues to the approval prompt unless dry-run | Review the list, then answer the prompt |
| `INFO: Dry run - no snapshots were deleted.` | Dry-run final marker | Informational |
| `INFO: Approve deletion of ... snapshots?` / `Approve deletion of ... snapshots? [y/N]: ` (held input request) | Approval prompt (both modes) | y proceeds with deletion (reply to the held request, e.g. `3 y`); anything else cancels |
| `INFO: Deletion cancelled by user.` | The operator declined at the approval prompt | Nothing is deleted |
| `INFO: No snapshots matched the criteria.` | Ignore-retention mode found no snapshots | Informational; nothing to do |
| `INFO: About to delete the following ... snapshots.` | Ignore-retention plan summary | Review before approving |
| `INFO: This disregards holds, incremental bases, and snapshot age.` | Safety disclaimer for ignore-retention mode | Heed the warning before approving |
| `INFO: Estimated disk space that would be freed: ~...` | Sum of the matched snapshots' used space | Informational |

### [zfsdelsnap](../commands-and-modules/modules.md#zfsdelsnap)

Single-snapshot delete with age, hold, clone, and counterpart protections. Called by the retention scripts with busy-skip enabled.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: A snapshot to be removed must be given.` | No snapshot argument | Script aborts (exit 8) |
| `WARN: Lock acquisition aborted by user.` | The operator aborted the lock wait | Snapshot kept (return 1) |
| `INFO: Skipping ... (lock conflict).` | Lock resolution chose skip | Snapshot kept; returns 0 |
| `FATAL: A minimum age (in days) must be specified. Use 0 to skip age check.` | The age argument is missing | Script aborts (exit 8) |
| `FATAL: Snapshot ... does not exist.` | The snapshot is not listed | Script aborts (exit 8); check the name |
| `WARN: Snapshot ... is only ... days old. Minimum age is ... days.` | Age gate: the snapshot is younger than the policy's minimum | Snapshot kept |
| `WARN: Deletion blocked - counterpart pool(s) offline.` | `zfscheckagainst` could not verify the counterpart chain | Snapshot kept; import the counterpart pool and rerun |
| `WARN: Deletion blocked - this is the last remaining common snapshot.` | `zfscheckagainst` found this is the only common snapshot | Snapshot kept |
| `WARN: Snapshot ... still has holds (...); skipping deletion.` | After releasing the matching tags, other user holds remain | Snapshot kept; release the listed holds |
| `WARN: Snapshot ... has clone dependents. Skipping deletion.` | The snapshot is a clone origin | Snapshot kept; promote or destroy the clones |
| `WARN: Unable to remove snapshot ... (rc=...). Skipping.` | `zfs destroy` failed with busy-skip enabled (diagnostics were printed first) | Snapshot kept; address the busy cause |
| `FATAL: Unable to remove snapshot .... rc=....` | `zfs destroy` failed without busy-skip (direct invocations) | Script aborts (exit 8); address the busy cause |

### [zfsdelfs](../commands-and-modules/commands.md#zfsdelfs)

Destroys a dataset subtree, ignoring holds. Refuses datasets with clone dependents and tears down iSCSI LUNs first.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: Missing ... — install via: bin/install-single-node` | Neither the node config nor the legacy two-node config is readable | Script aborts; install the config |
| `FATAL: A subtree must be specified.` | No dataset argument | Script aborts (exit 8) |
| `FATAL: Cannot acquire destroy lock on ...; aborting.` | The exclusive subtree lock is unavailable | Script aborts (exit 8); resolve the lock |
| `WARN: There are no qualifying datasets to delete.` | The subtree enumeration produced nothing | Nothing to do (exit 4) |
| `INFO: About to delete the following datasets and all their snapshots, ignoring holds.` | Interactive plan (entries may be annotated `[ZFS clone dependents — cannot delete]` or `[iSCSI LUN — will be removed from targetcli]`); press-enter prompt follows | Press Enter to proceed |
| `FATAL: One or more datasets have ZFS clone dependents and cannot be deleted. Use promote-vm-clone to cut dependencies first.` | Interactive pre-check found clone dependents | Script aborts (exit 8); promote the clones first |
| `FATAL: ... has ZFS clone dependents — cannot delete. Use promote-vm-clone to cut dependencies first.` | Per-dataset clone gate during deletion | Script aborts (exit 8); promote the clones first |
| `FATAL: ... NOT deleted (running VM).` | iSCSI teardown failed (running VM or LUN teardown failure) | Script aborts (exit 8); stop the VM and rerun |
| `FATAL: ... was NOT deleted.` | `zfs destroy` failed (diagnostics were printed first) | Script aborts (exit 8); address the busy cause |
| `FATAL: ... was NOT deleted because delallsnaps could not delete all of its snapshots.` | Snapshot cleanup incomplete, so the dataset destroy was skipped deliberately | Script aborts (exit 8); see the delallsnaps messages above |
| `INFO: ... was deleted.` | Per-dataset success | Informational |

### [zfsdelallsnaps](../commands-and-modules/commands.md#zfsdelallsnaps)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: A dataset must be specified.` | No dataset argument | Script aborts (exit 1) |
| `WARN: Could not acquire write lock on ...; aborting.` | The dataset's write lock is unavailable | Aborts (return 1); resolve the lock |
| `INFO: There are no snapshots of ... to delete.` | The dataset has no snapshots | Nothing to do |
| `INFO: There are no snapshots of ... with string .....` | The substring filter left no matches | Nothing to do; check the filter |
| `INFO: About to delete the following ... snapshots from .... ... disregards system offsite-* holds and snapshot age; user holds will block individual snapshots from being deleted.` | Plan summary; press-enter prompt when autoproceed != 'Y' (recursive mode forces the prompt) | Press Enter to proceed |

### [zfsdelholds](../commands-and-modules/commands.md#zfsdelholds)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: A subtree must be specified.` | No dataset argument | Script aborts (exit 8) |
| `WARN: Could not acquire write lock on ...; aborting.` | The subtree's write lock is unavailable | Aborts (return 1); resolve the lock |
| `INFO: ... has no snapshots and therefore no holds.` | Nothing to release | Informational |
| `INFO: No snapshots matched pattern '...' in .....` | The leading-substring filter removed all candidates | Informational; check the pattern |
| `INFO: About to release holds for the following ... snapshots in .....` | Confirmation before releasing all holds in the subtree | Press Enter to proceed |

### [zfsdelallholds](../commands-and-modules/modules.md#zfsdelallholds)

Releases holds matching tag patterns (used by the offsite release pipeline), or all holds when called manually without patterns.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: Could not acquire write lock on ...; aborting.` | The parent dataset's write lock is unavailable | Aborts (return 1); resolve the lock |
| `INFO: About to release the following ... holds from .....` | Manual mode: no tag patterns were given, so all holds will be released; press-enter prompt when autoproceed != 'Y' | Press Enter to proceed |
| `FATAL: Release of hold ... on ... failed rc=....` | `zfs release` returned non-zero | Script aborts (exit 8) |

### [zfsdelallholdssubtree](../commands-and-modules/modules.md#zfsdelallholdssubtree)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: A dataset must be provided as $1.` | No dataset argument | Script aborts (exit 8) |
| `WARN: Could not acquire write lock on ...; aborting.` | The subtree's write lock is unavailable | Aborts (return 1); resolve the lock |
| `INFO: Will release ... holds on these snapshots:` | Interactive confirmation before releasing holds across the subtree; press-enter prompt follows | Press Enter to proceed |

### [zfshold](../commands-and-modules/modules.md#zfshold)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: zfshold requires a snapshot pattern ($3). Skipping.` | The snapshot-name pattern is missing | Skips (return 1); supply a pattern |
| `WARN: Could not acquire write lock on ...; aborting.` | The subtree's write lock is unavailable | Aborts (return 1); resolve the lock |

### [zfsholds](../commands-and-modules/commands.md#zfsholds)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: Snapshot holds for .....` | Header; the `zfs holds` listing follows | Informational |
| `WARN: Could not acquire read lock on ...; aborting.` | The read lock is unavailable | Aborts (return 1); resolve the lock |

### [zfsshowholds](../commands-and-modules/commands.md#zfsshowholds)

Emits no log messages; it is a single `zfs list | xargs zfs holds` pipeline.

### [zfsreapplyholds](../commands-and-modules/commands.md#zfsreapplyholds)

Captures holds before a destructive operation and reapplies them afterwards (used around full-copy transfers).

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: Dataset ... does not exist; no target holds to capture.` / `INFO: Dataset ... does not exist; no holds to release.` | The target dataset is absent (e.g. after a migration) | Nothing to do |
| `WARN: Could not acquire read lock on ...; aborting hold capture.` / `WARN: Could not acquire write lock on ...; aborting hold release.` / `WARN: Could not acquire write lock on ...; aborting hold reapply.` | The needed lock is unavailable | Operation aborts (return 1); resolve the lock |
| `INFO: Dry-run: Would release hold ... on ....` / `INFO: Dry-run: Would apply hold ... to ....` | Dry-run: the release/apply is only reported | Informational |
| `WARN: Failed to release hold ... on ....` / `WARN: Failed to apply hold ... to ....` | The `zfs release`/`zfs hold` command failed | Hold skipped; the counts below total the failures |
| `INFO: Released ... holds on ... (... failed).` / `INFO: Reapplied ... holds on ... (... skipped).` | Final count summary | Informational |
| `WARN: Restored snapshot ... no longer exists; skipping hold .....` | A snapshot named in the captured set is missing on the restored dataset | Hold skipped; re-create the snapshot or drop the hold from the set |
| `FATAL: Unknown option: ...` / `FATAL: Unexpected argument: ...` / `FATAL: Must specify --capture or --apply and a dataset.` / `FATAL: --release does not take an input file.` | CLI usage errors | Usage is printed; script exits 8 |

### [zfsgetsnapage](../commands-and-modules/commands.md#zfsgetsnapage)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: Usage: zfsgetsnapage <snapshot>` | No snapshot argument | Script aborts (exit 8) |
| `FATAL: Snapshot not found: ...` | The snapshot has no creation property | Script aborts (exit 8); check the name |

### [zfsconfig](../commands-and-modules/modules.md#zfsconfig)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: zfsconfig: config not found at ...; using legacy path ...` | The JSON config is missing but a legacy config exists | Informational; migrate the legacy config |
| `FATAL: Could not locate feature_config.py` | The Python support module was not found; JSON-backed queries fail and callers fall back to legacy config files | Install the full scripts directory or set `ZFSUTILITIES_PYLIB` |

### [zfssnapbuild](../commands-and-modules/modules.md#zfssnapbuild)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: A prior nextsnap was found: ... (from ...).` | A snapshot name saved by an earlier incomplete run of the same job exists | Prompt: y reuses the saved name, n/Enter discards it and builds a fresh one |

### [retention_page](../commands-and-modules/python-modules.md#retention_pagepy)

GUI Retention tab: per-pool bucket tables, prune-pool list, and the new-install/legacy-import paths. The prune run itself is launched by [retention_actions](#retention_actions); a scheduled prune is logged by [profile_runner](#profile_runner) instead.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: New install — kept pool-specific retention policies: ...` | User answered "Keep" to the new-install clear dialog | Policies retained; new-install flag cleared |
| `INFO: New install — clearing retention policy for '...': ...` | User answered "Clear"; the pool's buckets are being dropped | Policy deleted from the in-memory config |
| `INFO: New install — cleared pool-specific retention policies: ...` | Save of the cleared config succeeded | Continue with only the `default` policy |
| `WARN: Could not save cleared retention policies: ...` | OSError saving after the clear | Clear is in-memory only |
| `INFO: Imported legacy retention policies into JSON: ...` | Legacy retention was imported into the config at page build | Informational |
| `WARN: Could not save imported retention policies: ...` | OSError saving the import | Import not persisted |
| `WARN: Could not save prune pool order: ...` | Drag-and-drop reorder of prune pools failed to persist | Order kept in the UI only |
| `INFO: Created new retention policy for pool: ...` | User answered Yes to the create-missing-policy dialog when switching pools | Default retention saved for the pool |
| `VERB: Retention policy saved for pool: ...` / `Retention policies saved for pools: ..., ...` | Save persisted one pool's (or several pools') buckets | Informational |

### [retention_actions](../commands-and-modules/python-modules.md#retention_actionspy)

GUI Retention tab actions: policy add/remove and the prune run (launched through the shared runner; the generated prune script's messages are listed under [command_builders](#command_builders), runner messages under [backup_runner](#backup_runner)).

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: Retention policy for '...' already exists` | Add-policy duplicate gate | Add aborted |
| `VERB: Created retention policy for pool: ...` | Policy seeded from `default` and saved | Prune list refreshed |
| `INFO: Removed retention policy for pool: ...` | Policy deleted after Yes/No confirm (the pool falls back to `default`) | Prune list refreshed |
| `WARN: Retention page not initialized` | Prune view widget missing | Prune aborted |
| `WARN: Select one or more pools in the Prune list` | Empty prune selection | Prune aborted |
| `WARN: No offsite pool online; skipping <offsite> prune` | The `<offsite>` placeholder expanded to zero pools | Placeholder skipped; other pools continue |
| `WARN: No online pools selected for pruning` | Expansion left no pools | Prune aborted |
| `WARN: Retention runner not available` | No retention runner on the app | Prune aborted |
| `WARN: A prune operation is already running` | Runner busy guard | Prune aborted |
| `INFO: Dry run mode enabled — no changes will be made` | Dry-run toggle active for the prune run | Continue in no-change mode |
| `WARN: cannot prune ...: pool is locked by another operation` | Pre-flight write-lock check on the pool failed | Whole prune aborted |
| `WARN: Bucket '...' already exists` | Add-bucket duplicate gate | Add aborted |
| `INFO: Added bucket '...' (unsaved)` | Bucket row appended, not yet saved | Save persists |
| `WARN: Select a bucket to remove` | No bucket row selected (or page widget missing) | Remove aborted |
| `INFO: Removed bucket '...' (unsaved)` | Bucket row removed, pending save | Save persists |

### [checkagainst_page](../commands-and-modules/python-modules.md#checkagainst_pagepy)

GUI Checkagainst tab (the table editor for [zfscheckagainst](#zfscheckagainst)).

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: Checkagainst table saved to JSON config` | Save passed row validation | Original-state snapshot updated |
| `INFO: Derived ... backup and ... offsite checkagainst entries` | Get Entries re-derived the backup/offsite-derived rows from current configs | Derived stores refreshed |
| `INFO: Added checkagainst pair for ... ↔ ... (label ...)` | Add-pair assistant confirmed; forward and reverse rows appended | Save still needed |

## VM Archive and Lifecycle

Scripts in this group share several templates: `FATAL: This script requires Proxmox VE (qm command not found).` (the `qm` tool is missing), `FATAL: Must run as root (use sudo)`, and `FATAL: vmid must be a number, got: ...` — all abort the script. `INFO: Aborted.` always means the operator answered no at a confirmation prompt and the script exits 0 without changes.

### [archive-vm](../commands-and-modules/commands.md#archive-vm)

Never stops a running VM itself; the stopped-VM gate aborts instead.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: VM ... is not stopped (status: ...).` | The stopped-VM gate refused to continue (the script never stops the VM itself) | Run `qm stop <vmid>`, then rerun |
| `FATAL: Could not acquire write lock on ... for snapshot creation` | The lock for auto-creating the retire snapshot is unavailable | Script aborts; resolve the lock |
| `FATAL: Failed to create snapshot ...` | The retire snapshot could not be created | Script aborts; check the pool state |
| `FATAL: Failed to determine snapshot for ... on ...` | Remote snapshot discovery failed (two-node) | Script aborts; check SSH and the storage host |
| `WARN: Config references vm-...-disk-... but no zvol was found` | A Proxmox config disk reference has no matching zvol | Disk skipped; the archive will lack it |
| `WARN: Config references target ... LUN ... but no backstore was found` | A two-node iSCSI reference could not be resolved via targetcli | Disk skipped |
| `WARN: Backstore ... has no zvol` | The backstore has no `/dev/zvol` mapping | Disk skipped |
| `WARN: Orphaned zvol not referenced in config: ...` | A zvol named for this VM exists but the config does not reference it | Warning only; the orphan is not archived |
| `FATAL: SSH to ... failed` | Two-node discovery could not reach the storage host | Script aborts; check SSH |
| `INFO: --- Step 1: Discovering dependent clones ---` | Phase milestone | Informational |
| `INFO: Found disks with dependent clones:` | Dependent ZFS clones exist on this VM's zvols | The promote prompt follows |
| `INFO: No dependent clones found.` | Nothing depends on this VM | Informational |
| `INFO: Skipping clone promotion.` | The operator declined promotion | Run continues; see the warning below |
| `WARN: VM removal may fail while snapshots are held by clones.` | Consequence of declining promotion | Promote the clones first with [promote-vm-clone](#promote-vm-clone) |
| `FATAL: Promotion failed for VM ...` | `promote-vm-clone` exited non-zero after the operator approved | Script aborts; see its messages |
| `INFO: --- Step 2: Archiving VM ... ---` | Phase milestone | Informational |
| `FATAL: Archive base path is required` | No path given and no saved default exists | Supply the archive base path |
| `FATAL: Not a ZFS dataset: ...` / `FATAL: Not a ZFS dataset on ...: ...` | The archive base is not a ZFS dataset (local or storage host) | Use a ZFS dataset as the archive base |
| `INFO: ✓ Saved archive path to JSON config` | The entered path differs from the saved default and was persisted | Informational |
| `FATAL: Proxmox config not found: ...` | `/etc/pve/qemu-server/<vmid>.conf` is missing | Check the VM ID |
| `FATAL: Failed to discover referenced zvols` / `FATAL: No referenced zvols found for VM ...` | Disk discovery failed or found nothing | Script aborts; check the VM config |
| `INFO: Zvols to archive:` | Pre-confirmation summary | Review, then answer the archive prompt |
| `INFO: --- Step 3: Verifying archive ---` | Phase milestone; the verification gate begins | Informational |
| `FATAL: MISSING dataset: ...` | Verification found an archive dataset absent (counted; the run aborts at the end of verification) | Check the send/receive messages above |
| `FATAL: Config archive missing or empty` | The archived Proxmox config is absent or zero-length | Check the config copy step |
| `INFO: ✓ Config archive OK` | Config verification passed | Informational |
| `FATAL: Archive verification failed (... errors). VM NOT removed.` | One or more verification errors — the removal gate blocked Step 4 | Fix the archive before rerunning; the VM is intact |
| `INFO: Archive verified.` | Verification passed | Informational |
| `INFO: --- Step 4: VM removal ---` | Phase milestone | Informational |
| `INFO: VM ... preserved. Archive is under: ...` | The operator declined VM removal | VM kept; the archive remains |
| `WARN: Could not destroy ...` | `zfs destroy` failed after busy diagnostics (single-node removal) | Continue to the next zvol; address the busy cause |
| `WARN: Could not remove disk ...` | Remote `remove-vm-disk` failed (two-node removal) | Continue; see its messages |
| `INFO: VM ... has been archived.` / `INFO: Archive: ...` | Final outcome: zvols destroyed, config removed, archive location listed | Informational |

### [unarchive-vm](../commands-and-modules/commands.md#unarchive-vm)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: new-vmid must be a number, got: ...` / `FATAL: new-vmid must differ from vmid` | `--new-vmid` validation | Script aborts |
| `INFO: vmid ... is already in use (config or zvols exist).` | Destination collision; the interactive new-vmid prompt follows | Enter a different numeric vmid (blank aborts) |
| `INFO: vmid ... is also in use.` | The interactively proposed vmid also collides | Enter another vmid |
| `FATAL: Requested new vmid ... is already in use` | The `--new-vmid` value collides (non-interactive) | Script aborts; choose a free vmid |
| `FATAL: new vmid must be a number, got: ...` / `FATAL: new vmid must differ from the original vmid` | Interactive prompt input validation | Script aborts |
| `FATAL: Archive base path is required (provide as argument or save in JSON config)` | No path argument and no saved default | Supply the archive base path |
| `FATAL: Not a ZFS dataset: ...` / `FATAL: Not a ZFS dataset on ...: ...` | The archive base is not a ZFS dataset | Use a ZFS dataset as the archive base |
| `FATAL: SSH to ... failed` | Two-node archive discovery failed | Script aborts; check SSH |
| `FATAL: No archived zvols found for VM ... under ...` | The archive holds nothing for this vmid | Check the vmid and archive base |
| `FATAL: Missing sidecar files:` | The `.original_volblocksize` or `.disk_info` sidecars are absent (list printed) | Script aborts; the archive is incomplete |
| `FATAL: Destination zvols already exist:` | Target zvol collision (list printed) | Script aborts; remove the zvols or use a new vmid |
| `FATAL: Archived config not found: ...` / `FATAL: Archived config not found on ...: ...` | The archived Proxmox config is missing | Script aborts; check the archive |
| `FATAL: Destination Proxmox config already exists: ...` | Destination config collision | Script aborts; use a new vmid |
| `INFO: Zvols to restore:` | Pre-confirmation summary (with volblocksize and rename mapping) | Review, then answer the restore prompt |
| `INFO: --- Step 1: Restoring zvols ---` | Phase milestone | Informational |
| `FATAL: No snapshots found on archive dataset: ...` | The archive dataset has no snapshot to send | Script aborts; the archive is damaged |
| `FATAL: Could not acquire write lock on ...` | The destination zvol's write lock is unavailable | Script aborts; resolve the lock |
| `FATAL: Failed to restore ...` / `FATAL: Zvol restoration failed on ...` | The send/receive into the destination zvol failed (local or remote) | Script aborts; check space and the messages above |
| `INFO: --- Step 2: Rebuilding iSCSI infrastructure ---` | Phase milestone (two-node only) | Informational |
| `FATAL: Cannot map pool ... to target` | No iSCSI target mapping for a restored zvol's pool | Script aborts; fix the node config mapping |
| `FATAL: iSCSI reconstruction failed on ...` | The remote iSCSI rebuild failed | Script aborts; see the remote messages |
| `INFO: ✓ iSCSI configuration saved` | The storage host's targetcli config was persisted | Informational |
| `INFO: --- Step 3: Restoring Proxmox config ---` | Phase milestone | Informational |
| `FATAL: Failed to read archived config` | The archived config read returned nothing | Script aborts |
| `INFO: ✓ Config restored: ...` | The config was written (copied or path-rewritten) | Informational |
| `WARN: Could not map ..., keeping original line` | A disk line's LUN/target could not be remapped during the rewrite | The original line is kept; verify the disk in the Proxmox GUI |
| `INFO: --- Step 4: Rescanning iSCSI ---` | Phase milestone (two-node only) | Informational |
| `WARN: iSCSI rescan failed; run 'sudo rescan-storage' on ... manually` | The compute-host rescan failed | Rescan manually before starting the VM |
| `INFO: VM ... has been unarchived as VM ....` / `INFO: VM ... has been unarchived.` | Final outcome (new vmid or original vmid) | Informational |
| `INFO: Review hardware in the Proxmox GUI before starting the VM.` | Restored hardware may need re-checking | Review before starting |

### [remove-vm](../commands-and-modules/commands.md#remove-vm)

Unlike `archive-vm`, this script stops a running VM after confirmation.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: No zvols or Proxmox config found for VM ....` | Nothing exists to remove | Clean exit 0 |
| `INFO: Mode: --cleanup-orphans (orphaned matching zvols will be removed)` | Flag-gated mode: orphans are promoted into the removal set | Informational |
| `INFO: Config: ...` / `INFO: Config: not found` | Whether the Proxmox config exists | Informational |
| `INFO: Zvols to remove:` | Pre-confirmation summary of the destruction set | Review, then answer the removal prompt |
| `WARN: Reassigned zvols (referenced by another VM, will NOT be removed):` | Safety classification: zvols referenced by another VM's config are never destroyed | Informational |
| `WARN: Orphaned zvols (not referenced by any VM config, will NOT be removed):` | Safety classification: orphans are spared unless `--cleanup-orphans` is set | Rerun with `--cleanup-orphans` to remove them |
| `INFO: Pass --cleanup-orphans to remove these as well.` | Guidance printed when orphans exist and the flag is not set | Rerun with the flag if desired |
| `INFO: No zvols will be removed (only reassigned zvols were found).` | The removal set is empty | Only config cleanup remains |
| `INFO: VM ... is currently running and will be stopped before removal.` | Running-VM notice; the script stops the VM after confirmation | Informational |
| `INFO: Stopping VM ...` | `qm stop` is executing | Informational |
| `INFO: Removing zvols...` | Destruction phase begins | Informational |
| `FATAL: Failed to remove ...` / `FATAL: Failed to remove ... on ...` | `zfsdelfs` failed (local or remote) | Script aborts; see the zfsdelfs messages |
| `INFO: Saving iSCSI configuration...` / `INFO: Rescanning iSCSI...` | Two-node post-removal phases | Informational |
| `WARN: Could not save iSCSI config on ...` | The remote targetcli save failed | Save manually on the storage host |
| `WARN: iSCSI rescan failed; run rescan-storage manually` | The compute-host rescan failed | Rescan manually |
| `INFO: Removing Proxmox config...` | Config deletion phase | Informational |
| `INFO: VM ... has been removed.` | Final outcome | Informational |

### [clone-vm](../commands-and-modules/two-node.md#clone-vm-both)

Full-copy clone (send/receive on single-node, iSCSI clone on two-node).

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: Source VM config not found: ...` / `FATAL: Destination VM config already exists: ...` | Source missing or destination collision | Script aborts; check the VM IDs |
| `FATAL: VM ... must be stopped before cloning (status: ...)` | The source VM is running | Stop the VM and rerun |
| `FATAL: No ZFS disk zvols found for VM ...` / `FATAL: No iSCSI disks found in source VM config` | No clonable disks found (single-node / two-node) | Script aborts; check the VM's disk backing |
| `INFO: === clone-vm (single-node, full copy) ===` / `INFO: === clone-vm ===` | Mode marker | Informational |
| `FATAL: Destination zvol already exists: ...` | Destination zvol collision | Script aborts; choose another dst vmid |
| `FATAL: Could not acquire write lock on source zvol ...` / `FATAL: Could not acquire write lock on destination zvol ...` | Lock gates | Script aborts; resolve the locks |
| `FATAL: Could not determine disk number for ... (LUN ...)` / `FATAL: Could not determine disk number for ...` | The remote backstore lookup yielded no disk number | Script aborts; check targetcli state |
| `FATAL: Source zvol not found: ...` | The source zvol is absent on the storage host | Script aborts |
| `FATAL: Backstore already exists: ...` | Destination backstore collision | Script aborts |
| `FATAL: Device node did not appear: ...` | The `/dev/zvol` node did not appear within the udev wait | Script aborts; check udev/the storage host |
| `INFO: ✓ Added to expected-backstores manifest` | The clone was registered for repair tooling (only when the manifest exists) | Informational |
| `FATAL: Failed to clone ...` | The remote clone step failed | Script aborts; see the remote messages |
| `FATAL: Could not determine new LUN number for ...` | The new LUN could not be parsed after cloning | Script aborts; check targetcli |
| `INFO: Saving iSCSI configuration...` / `INFO: ✓ Configuration saved` | targetcli config persisted | Informational |
| `INFO: Writing VM ... config...` / `INFO: ✓ Config written: ...` | New config generated (fresh vmgenid/MAC/name) | Informational |
| `INFO: Rescanning iSCSI...` | Compute-host rescan | Informational |
| `INFO: VM ... (...) is ready in Proxmox.` / `INFO: Review hardware in the GUI before starting.` | Final outcome | Review before starting |

### [zfsclone-vm](../commands-and-modules/two-node.md#zfsclone-vm-both)

Instant ZFS clone (shares the origin snapshot `@clone-...-c`, retained on the source).

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: Source VM config not found: ...` / `FATAL: Destination VM config already exists: ...` | Source missing or destination collision | Script aborts; check the VM IDs |
| `FATAL: VM ... must be stopped before cloning (status: ...)` | The source VM is running | Stop the VM and rerun |
| `FATAL: No ZFS disk zvols found for VM ...` / `FATAL: No iSCSI disks found in source VM config` | No clonable disks found | Script aborts; check the VM's disk backing |
| `INFO: Snapshot: ...` | Names the clone-origin snapshot deliberately retained on the source | Do not delete this snapshot while clones exist |
| `FATAL: Destination zvol already exists: ...` | Destination zvol collision | Script aborts |
| `FATAL: Could not acquire write lock on source zvol ...` / `FATAL: Could not acquire write lock on destination zvol ...` | Lock gates | Script aborts; resolve the locks |
| `INFO: ✓ Snapshot created: ...` / `INFO: ✓ Snapshot exists: ...` | The shared origin snapshot was created, or already existed and is reused | Informational |
| `FATAL: No backstore found for LUN ... in ...` | LUN could not be resolved to a backstore | Script aborts; check targetcli |
| `FATAL: Cannot extract disk number from '...'` / `FATAL: Cannot determine pool for backstore ...` | Backstore name or mapping not in expected form | Script aborts; check targetcli |
| `FATAL: Source zvol not found: ...` / `FATAL: Backstore already exists: ...` | Source absent or destination collision | Script aborts |
| `FATAL: Device node did not appear: ...` | The `/dev/zvol` node did not appear within the udev wait | Script aborts; check udev/the storage host |
| `FATAL: Failed to clone ...` | The remote clone step failed | Script aborts; see the remote messages |
| `FATAL: Could not determine new LUN number for ...` | The new LUN could not be parsed | Script aborts; check targetcli |
| `INFO: Saving iSCSI configuration...` / `INFO: ✓ Configuration saved` | targetcli config persisted | Informational |
| `INFO: Writing VM ... config...` / `INFO: ✓ Config written: ...` | New config generated (fresh vmgenid/UUID/MAC/name; protection/meta lines dropped) | Informational |
| `WARN: iSCSI rescan failed; run 'sudo rescan-storage' on ... manually` | The compute-host rescan failed | Rescan manually |
| `INFO: Clone origin: ... (retained on source VM ... zvols)` | The origin snapshot stays on the source | Do not delete it while the clone exists |
| `INFO: To cut dependency before retiring VM ...: promote-vm-clone ...` | Remediation for the retained origin | Run [promote-vm-clone](#promote-vm-clone) before retiring the source |
| `INFO: VM ... (...) is ready in Proxmox.` | Final outcome | Informational |

### [promote-vm-clone](../commands-and-modules/two-node.md#promote-vm-clone-both)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: SSH to ... failed` | Two-node clone discovery failed | Script aborts; check SSH |
| `FATAL: No clone zvols found for VM ... — already promoted or not a ZFS clone` | The VM's zvols have no clone origin | Nothing to promote; no action needed |
| `INFO: Zvols to promote:` | Pre-confirmation summary (with origins) | Review, then answer the promotion prompt |
| `FATAL: Could not acquire write lock on ...` | A zvol's write lock is unavailable | Script aborts; resolve the lock |
| `FATAL: Promotion failed: ...` / `FATAL: Promotion failed on ...` | `zfs promote` failed (local or remote) | Script aborts; see the messages above |
| `INFO: VM ... zvols are now independent.` | Promotion complete | Informational |
| `INFO: Other clones of the same snapshots have been re-parented to VM ....` | Side effect of `zfs promote` | Informational |
| `INFO: The former source VM can be destroyed when ready: ...` | Final guidance (stop source, remove disks from config, zfsdelfs each zvol) | Follow the numbered steps |

### [zfscheckrunningvms](../commands-and-modules/modules.md#zfscheckrunningvms)

Sourced library; callers act on its return codes (0 safe, 1 running VMs found in `$running_vms`, 2 cannot check).

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: checkrunningvms requires a dataset argument` | The caller passed an empty target | Returns 2 (cannot check); callers must treat the gate as unverifiable |
| `DEBUG: Proxmox tools (qm/pct) not found; cannot check for running VMs` | Non-Proxmox system | Returns 2 (cannot check) |

### [enroll-efi-keys-vm](../commands-and-modules/two-node.md#enroll-efi-keys-vm-compute-node)

Grows the EFI zvol to 4M and writes the Microsoft-cert EFI vars; shuts a running VM down gracefully first.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: VM config not found: ...` | The VM config is missing | Script aborts; check the VM ID |
| `INFO: VM ... is running. Shutting down gracefully...` | The script issues `qm shutdown` and polls | Informational |
| `FATAL: VM ... did not shut down in time` | Still running after the shutdown poll | Script aborts; stop the VM manually and rerun |
| `INFO: ✓ VM ... is stopped` | Stopped-VM gate passed | Informational |
| `FATAL: VM ... has no efidisk0 entry` / `FATAL: Could not extract efidisk0 volume ID` / `FATAL: Could not extract efidisk0 size` | EFI disk missing or unparseable in the config | Script aborts; fix the efidisk0 entry |
| `FATAL: Could not parse iSCSI by-path volume ID: ...` / `FATAL: Unsupported efidisk0 volume ID format: ...` | The EFI disk reference is not in a supported shape | Script aborts; the hint line recommends this script over `qm enroll-efi-keys` |
| `FATAL: Single-node by-path EFI disk resolution is not supported: ...` | by-path disks are only resolvable in two-node mode | Script aborts |
| `INFO: Resolving iSCSI LUN ... in target ... on ...` | Two-node LUN→backstore→zvol resolution | Informational |
| `FATAL: No iSCSI backstore found for LUN ... in ...` / `FATAL: No zvol found for backstore ...` / `FATAL: No zvol found for storage reference: ...` | The EFI zvol could not be resolved | Script aborts; check targetcli/the storage reference |
| `INFO: Backing zvol: ...` | Resolution result | Informational |
| `FATAL: Could not read zvol size` | The volsize lookup failed | Script aborts |
| `INFO: Growing EFI zvol from ... bytes to 4M...` | The zvol is smaller than 4M and will be grown | Informational |
| `INFO: EFI zvol is already ... bytes (>= 4M)` | No grow needed | Informational |
| `FATAL: Failed to grow zvol` | `zfs set volsize=4M` failed | Script aborts |
| `INFO: Rescanning iSCSI...` | Compute-host rescan so the new size is visible | Informational |
| `FATAL: iSCSI rescan failed` | The rescan failed (fatal in this script) | Script aborts; rescan manually and rerun |
| `FATAL: EFI device not found: ...` / `FATAL: EFI device size is ... bytes, expected >= 4194304` | The by-path device never appeared or did not grow | Script aborts; check the iSCSI session |
| `FATAL: Firmware file not found: ...` | The OVMF vars file is missing | Script aborts; install the OVMF package |
| `INFO: Writing ... to EFI disk...` | The destructive EFI vars rewrite begins | Informational |
| `FATAL: Failed to write EFI vars` | The write failed | Script aborts |
| `INFO: Updating VM ... config...` / `INFO: ✓ VM ... config updated` | Applying ms-cert=2023k and size=4M to efidisk0 | Informational |
| `INFO: VM ... is stopped. Start it manually and watch the console.` | Final outcome; the VM is deliberately left stopped | Start manually and watch the console |
| `INFO: The UEFI boot order may have been reset; ...` | The vars rewrite may clear the boot order | Re-select the boot device in the UEFI setup if the VM drops to a shell |

See also [PVE-send-to-archive](#pve-send-to-archive) under Backup and Send/Receive.

## Two-Node iSCSI and VM Disks

Scripts in this group share the `FATAL: This script requires Proxmox VE (qm command not found).` environment gate and several `Pool must be one of: ...` / `vmid must be a number` validation fatals (all abort). The shared non-fatal rescan degradation is `WARN: Could not rescan ... — run 'sudo rescan-storage' on ... manually` / `WARN: Could not reach ...` (the compute host must be rescanned manually).

See also [ensure-restored-vm-iscsi](#ensure-restored-vm-iscsi) under Restore and [zfscheckrunningvms](#zfscheckrunningvms) under VM Archive and Lifecycle.

### [new-vm-disk](../commands-and-modules/two-node.md#new-vm-disk-both)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: Pool must be one of: ... . Got: ...` / `FATAL: Pool '...' not found. Available pools: ...` | The pool argument is unknown (two-node list or `zpool list`) | Script aborts; use a listed pool |
| `FATAL: Size must be like 50G or 2T (or the special value EFI), got: ...` | Size syntax validation | Script aborts |
| `FATAL: Failed to map pool to target: ...` | No iSCSI target mapping for the pool (two-node) | Script aborts; fix the node config |
| `FATAL: Storage operations failed on ...` | The delegated SSH run on the storage host failed | Script aborts; see the remote messages |
| `FATAL: Zvol already exists: ...` / `FATAL: iSCSI backstore already exists: ...` | Pre-create collision checks | Script aborts; remove the existing zvol/backstore or choose another disk number |
| `FATAL: Key file ...` (path not absolute / not found / not readable) / `FATAL: Key file permissions are too permissive: ...` | `--encrypted` key-file validation | Script aborts; fix the key file path and permissions (owner-only) |
| `FATAL: Key file must not reside on the pool being encrypted: ...` / `FATAL: Key file must not reside on the zvol being created.` | Lockout guard: the key would live on the storage it encrypts | Script aborts; move the key outside that pool/zvol |
| `FATAL: Could not acquire write lock on ...` | The `<pool>/proxmox` write lock is unavailable | Script aborts; resolve the lock |
| `FATAL: Device node ... did not appear after 10s` | The `/dev/zvol` node never appeared after creation | Script aborts; check udev and the pool state |
| `WARN: OVMF firmware file not found: ...` | The EFI-vars firmware file is missing; a manual `dd` command is printed | EFI init skipped; install `pve-edk2-firmware` or run the printed command |
| `WARN: Device not found: ...` | The by-path iSCSI device did not appear within 10s; manual `dd` instructions printed | EFI init skipped; follow the instructions |
| `WARN: VM ... already has an efidisk0 entry — not replacing:` | An existing efidisk0 is preserved | Informational |
| `WARN: VM ... does not exist yet.` / `WARN: VM ... config not found — create the VM in Proxmox GUI (no disk), then run:` | No VM config to edit; the config lines/`qm set` command are printed for manual addition | Create the VM, then apply the printed lines |
| `WARN: Could not determine LUN number — find it with: sudo list-vm-disks` | The targetcli query for the new backstore returned nothing | Identify the LUN with `list-vm-disks` and finish manually |
| `WARN: EFI disk initialization must be run from the compute host.` | The script ran on a third host; the `dd` must happen on the compute host | Run the printed command on the compute host |
| `INFO: EFI disk requested (4M — stores UEFI firmware variables)` | The special EFI size branch was taken | Informational; the Secure Boot prompt follows |
| `INFO: Secure Boot pre-enrolls Microsoft + distro certificate keys.` | Annotation for the Secure Boot prompt | y enables pre-enrolled keys (needed for Windows 11); N uses plain OVMF vars |
| `INFO: Encrypted zvol creation requires an already-accessible key file.` | `--encrypted` gate before the key-path prompt | Enter the key path (empty accepts the conventional default) |
| `INFO: Encryption settings:` | Resolved algorithm/key format/key location (auto-detected from existing encrypted zvols) | Informational |
| `INFO: === EFI config lines for VM ... ===` | The `bios: ovmf` + efidisk0 lines to add manually when the VM was missing | Add them to the VM config |
| `INFO: === Done ===` | Final outcome: zvol, device, target, and LUN listed | Informational |

### [remove-vm-disk](../commands-and-modules/two-node.md#remove-vm-disk-both)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: Zvol does not exist: ...` | Nothing to destroy | Script aborts |
| `FATAL: Could not acquire destroy lock on ...` | The destroy-class lock is unavailable | Script aborts; resolve the lock |
| `FATAL: Could not destroy zvol ...` | `zfs destroy` failed after the busy diagnosis was printed | Script aborts; address the busy cause |
| `WARN: This will PERMANENTLY DESTROY the following:` | Safety preamble before two confirmation prompts (VM stopped/disk removed, then sure-to-destroy) | y to both proceeds; anything else exits 0 with nothing destroyed |
| `WARN: LUN not found in target — skipping LUN removal` / `WARN: Backstore ... not found — skipping` | The iSCSI pieces are already absent | Informational; the zvol destroy continues |
| `INFO: ✓ Zvol destroyed` | Main outcome | Informational |
| `INFO: === Done ===` | Final outcome summary | Informational |

### [attach-vm-disk](../commands-and-modules/two-node.md#attach-vm-disk-both)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: Zvol path must be <pool>/proxmox/vm-<vmid>-disk-<num>, got: ...` | Zvol path shape validation | Script aborts |
| `FATAL: Zvol does not exist: ...` | The zvol to attach is missing (local check: single-node or storage-host invocation) | Script aborts |
| `FATAL: Zvol does not exist on <storage host> (or the storage host is unreachable): ...` | Two-node compute-host invocation: the remote existence/volsize query returned nothing | Script aborts; verify the zvol on the storage host and SSH reachability |
| `FATAL: VM config not found: ...` | The destination VM has no config | Script aborts; create the VM first |
| `FATAL: Destination key ... already exists in VM ... config` | The requested slot is occupied | Script aborts; choose a free slot |
| `FATAL: Could not determine LUN number from storage host` | The remote ensure step returned neither marker | Script aborts; check targetcli on the storage host |
| `WARN: VM ... is currently ...` | The destination VM is not stopped (a guest SCSI rescan may be needed); a continue-anyway prompt follows | y proceeds, anything else aborts cleanly |
| `INFO: Will add the following line to VM ... config:` | Confirmation gate: the exact disk line, then the Proceed prompt | y appends the line; anything else aborts cleanly |
| `INFO: ✓ LUN ... already mapped` / `INFO: ✓ LUN ... created and mapped` | The LUN was reused or freshly created | Informational |
| `INFO: === Done ===` | Final outcome (attached zvol → VM as key) | Informational |

### [detach-vm-disk](../commands-and-modules/two-node.md#detach-vm-disk-both)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: Disk key ... not found in VM ... config` | Nothing to detach under that key | Script aborts |
| `WARN: VM ... is currently ...` | The VM is not stopped (possible guest I/O errors); a continue-anyway prompt follows | y proceeds, anything else aborts cleanly |
| `WARN: Disk line does not look like iSCSI — skipping iSCSI teardown` | The disk line could not be parsed as iSCSI; only the config line is removed | Informational |
| `WARN: Could not remove LUN (may already be removed)` / `WARN: Backstore not found — skipping` | iSCSI pieces already absent or best-effort removal failed | Informational |
| `INFO: This will detach ... from VM ...:` | Confirmation gate; the Proceed prompt follows | y detaches; anything else aborts cleanly |
| `INFO: Two-node: iSCSI LUN and backstore will also be removed:` | Scope notice: iSCSI teardown will run | Informational |
| `INFO: The underlying zvol will be left intact.` | Scope notice: the zvol is preserved | Informational |
| `INFO: === Done ===` | Final outcome (detached key from VM; zvol intact) | Informational |

### [move-vm-disk](../commands-and-modules/two-node.md#move-vm-disk-both)

Resumable: a state file (`/tmp/move-vm-disk-...state`) records the last completed phase; `--continue <state-file>` resumes remaining phases and `--rollback <state-file>` undoes them. The phase boundaries are emitted as `phase=teardown_done`, `phase=rename_done`, `phase=backstore_done`, `phase=lun_done`, `phase=saved`, plus `dstlun=...`, by the storage-side script.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: State file not found: ...` | `--continue`/`--rollback` cannot find the state file | Script aborts; re-run cannot resume |
| `FATAL: --... must be run directly on ... (state file is local).` | Recovery mode was invoked on the wrong host | Rerun on the compute host |
| `FATAL: Source VM ... must be stopped (status: ...)` / `FATAL: Destination VM ... must be stopped (status: ...)` | Hard safety gates (no prompt) | Stop the VMs and rerun |
| `FATAL: Disk line for ... does not look like an iSCSI disk in VM ...:` / `FATAL: Disk line for ... does not look like a ZFS-backed disk in VM ...:` | The disk reference could not be parsed (two-node / single-node) | Script aborts; check the VM config disk line |
| `FATAL: Destination zvol already exists: ...` / `FATAL: Destination key ... already exists in VM ... config` | Collision gates | Script aborts; free the destination |
| `FATAL: Could not acquire destroy lock on source zvol ...` / `FATAL: Could not acquire destroy lock on destination zvol ...` | Lock gates (also on rollback) | Script aborts; resolve the locks |
| `FATAL: zfs rename failed` / `FATAL: device node not found: ...` | The rename step failed (node never appeared after rename) | Script aborts; the state file allows `--continue`/`--rollback` |
| `FATAL: Storage-node move failed` / `FATAL: Storage-side rename failed on ...` | The SSH'd storage-side script failed; its output is echoed | Rerun with `--continue <state-file>` or `--rollback <state-file>` |
| `FATAL: Storage verification failed on ...` | Pre-move verification failed (markers `BACKSTORE_NOT_FOUND` / `ZVOL_NOT_FOUND` identify which) | Script aborts; check targetcli and the zvol |
| `FATAL:BACKSTORE_NOT_FOUND` / `FATAL:ZVOL_NOT_FOUND` | Remote verification protocol markers (storage-side) | See `Storage verification failed` above |
| `FATAL: Could not determine new lun number for ...` | The post-move LUN lookup returned nothing | Script aborts; check targetcli |
| `WARN: This will move the disk reference to VM ...` | Pre-confirm warning in `--no-rename` mode | Proceed prompt follows |
| `WARN: Both VMs must be stopped. This will rename the underlying zvol` | Pre-confirm warning in rename mode (backstore/LUN will be recreated) | Proceed prompt follows |
| `INFO: --no-rename set; leaving zvol/backstore/lun unchanged` | Decision marker: the storage phase is skipped entirely | Informational |
| `INFO: === Rolling back move-vm-disk ===` | Rollback mode started; the state file path and recorded phase are printed | The undo steps for the recorded phase run |
| `INFO: --no-rename was set; no storage-side changes to roll back` | Rollback decision: only the config is reverted | Informational |
| `INFO: ✓ Restored ... to VM ... config` / `INFO: ✓ Renamed zvol back to ...` | Rollback milestones | Informational |
| `INFO: === Rollback complete ===` | Rollback finished; the state file is deleted | Informational |
| `INFO: State file: ...` | The recovery state file path | Keep for `--continue`/`--rollback` |
| `INFO: === Done ===` | Final outcome (disk moved between VMs) | Informational |

### [resize-vm-disk](../commands-and-modules/two-node.md#resize-vm-disk-both)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: new-size must be a total size like 200G or 1T (not an increment), got: ...` | Size validation (grow-only, total size) | Script aborts |
| `FATAL: Zvol does not exist: ...` | Nothing to resize | Script aborts |
| `FATAL: Could not acquire write lock on ...` | The zvol's write lock is unavailable | Script aborts; resolve the lock |
| `INFO: ✓ Zvol resized` | The volsize was grown | Informational |
| `INFO: === Done ===` | Final outcome with verified before → after sizes | Informational |
| `INFO: Next steps inside the VM:` | The guest partition/filesystem still needs growing | Run the guest-side grow steps |

### [rename-vm-disk](../commands-and-modules/commands.md#rename-vm-disk)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: old-zvol-path must include a pool and dataset, got: ...` / `FATAL: new-zvol-path must include a pool and dataset, got: ...` | Path shape validation | Script aborts |
| `FATAL: old and new zvol paths must be under the same pool.` | Cross-pool rename refused | Script aborts; use a migration flow instead |
| `FATAL: Source zvol does not exist: ...` / `FATAL: Destination zvol already exists: ...` / `FATAL: Destination parent dataset does not exist: ...` | Existence/collision gates | Script aborts |
| `WARN: New basename '...' does not match the VM disk naming convention.` | The old name matched `vm-N-disk-M` but the new one does not | Warning only; some tools will not treat it as a VM disk |
| `FATAL: iSCSI discovery failed on ...` | The SSH enumeration of targets/backstores failed | Script aborts; check SSH and targetcli |
| `FATAL: VM ... must be stopped before renaming its disk (status: ...)` | Every referencing VM is checked; the first non-stopped VM aborts | Stop the VM and rerun |
| `FATAL: Storage-side rename failed on ...` / `FATAL: zfs rename failed` / `FATAL: device node not found: ...` | The rename failed (remote or single-node) | Script aborts; see the echoed output |
| `FATAL: could not determine new lun` | Neither LUN reuse nor auto-assign yielded a number | Script aborts; check targetcli |
| `INFO: iSCSI: ... lun ... backstore ...` / `INFO: iSCSI: not exported` | Decision markers: the iSCSI wiring will be rebuilt, or there is none | Informational |
| `INFO: Not referenced by any VM config (detached/orphaned zvol).` | Decision marker: no VM config rewrites or stopped-VM checks | Informational |
| `INFO: ✓ Zvol renamed` / `INFO: ✓ Updated ... in VM ... config` | Milestones | Informational |
| `INFO: === Done ===` | Final outcome (old → new) | Informational |

### [list-vm-disks](../commands-and-modules/two-node.md#list-vm-disks-both)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: Unknown argument: ...` | Only `--with-devices` (backward-compat no-op), `--gather-vm-info`, and `--gather-lun-info` are accepted | Script aborts |
| `FATAL: Failed to gather VM info from ...` / `FATAL: Failed to gather LUN info from ...` | The compute/storage-host gathering step failed | Script aborts; check SSH and targetcli |
| `INFO: === VM Disk Inventory ===` / `INFO: === VM Disk Inventory (single-node) ===` | Report headers; the per-target/per-pool tables follow | Read-only report |

### [repair-vm-disk-sizes](../commands-and-modules/two-node.md#repair-vm-disk-sizes-compute-node)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: --vmid must be a number, got: ...` / `FATAL: VM config not found: ...` | Filter validation | Script aborts |
| `WARN: VM ... ...: cannot resolve size for ...; leaving size=...` | The real size could not be determined (device missing, LUN not logged in, or volsize unavailable); the config line is left untouched | Fix the underlying visibility issue and rerun |
| `INFO: Mode: dry-run (no changes)` | Dry-run marker | Informational |
| `INFO: VM ... ...: would change size=... to size=... (...)` | Dry-run decision record | Review, then rerun without `--dry-run` |
| `INFO: ✓ VM ... ...: size=... -> size=...` | The config line was fixed | Informational |
| `INFO: Checked: ... Fixed: ... Skipped: ...` | Final summary counts | Informational |
| `INFO: Dry-run: no configs were modified` | Dry-run outcome confirmation | Informational |

### [setup-iscsi-targets](../commands-and-modules/two-node.md#setup-iscsi-targets-storage-node)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: Must run on the storage host (...), not ...` | Hostname check failed against the node config | Run on the storage host |
| `FATAL: targetcli not found. Install rtslib-fb-targetctl first.` | The LIO target stack is missing | Install targetcli and rerun |
| `INFO: ✓ Target already exists` | Idempotence gate for this pool's IQN | Skipped for this pool |
| `FATAL: Failed to create target` | `targetcli /iscsi create` failed for this pool | The loop continues with the next pool; fix targetcli and rerun |
| `INFO: ✓ Portal ...:3260 already exists` | Portal presence gate passed | Informational |
| `WARN: Could not add portal ...:3260` | Portal creation failed | Non-fatal; the target lacks a portal — rerun after fixing targetcli |
| `INFO: ✓ iSCSI configuration saved` | Changes were made and persisted | Informational |
| `INFO: ✓ No changes needed (all targets already configured)` | Nothing was created or added | Informational |
| `INFO: Targets created: ... / Targets existing: ... / Portals added: ...` | Final summary counters | Informational |

### [iscsi-add-encrypted-luns](../commands-and-modules/two-node.md#iscsi-add-encrypted-luns-storage-node)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: ✓ Added ... (LUN ...)` | Backstore created and mapped at its original LUN index (recovered from the saved config), preserving the compute host's by-path symlinks | Informational |
| `INFO: ✓ Added ... (auto LUN)` | No original index was found, so targetcli auto-assigned one (device-path stability not guaranteed) | Check the VM config's by-path references |

### [iscsi-restore-luns](../commands-and-modules/two-node.md#iscsi-restore-luns-storage-node)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: saveconfig.json not found: ...` | The authoritative restore source is missing | Script aborts; restore the saved targetcli config |
| `WARN: ... — device not available (...)` | The backstore's zvol device node does not exist (key not loaded or pool not imported) | Backstore skipped; load keys/import the pool and rerun |
| `INFO: ✓ All LUNs present — nothing to restore` | Nothing was missing | Informational |
| `INFO: ✓ Restored ... backstore(s), ... LUN mapping(s)` | Missing pieces were recreated | Informational; a compute-host rescan follows |
| `INFO: === Rescanning compute host ===` | Newly restored LUNs need discovery | Informational |

### [repair-iscsi-luns](../commands-and-modules/two-node.md#repair-iscsi-luns-storage-node)

Reconciles targetcli state against the expected-backstores manifest; `--dry-run` reports without changing.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: Must run as root (use sudo)` / `FATAL: Must run on the storage host (...), not ...` / `FATAL: targetcli not found...` | Environment gates | Run as root on the storage host with targetcli installed |
| `INFO: Backstore ... already exists` / `INFO: LUN mapping for ... already exists (...): ...` | Idempotence gates | Informational |
| `INFO: [dry-run] Would ...` | Dry-run variants: create backstore, map LUN, regenerate manifest, rescan, re-log sessions, back up + save config | Rerun without `--dry-run` to apply |
| `FATAL: Failed to create backstore ...` / `FATAL: Failed to map ... to .../tpg1/lun...` | The targetcli step failed for this entry | The loop continues; fix targetcli and rerun |
| `INFO: Backed up saveconfig.json to ...` | Safety backup taken before mutation | Informational |
| `INFO: ✓ Regenerated ...` | The expected-backstores manifest was rewritten from current state | Informational |
| `FATAL: Regenerated manifest is empty; keeping ... unchanged.` / `FATAL: Could not install regenerated manifest at .... Check permissions on the destination directory.` | The rewritten manifest could not be produced or installed (failed write, unwritable destination) | Temp file removed; the previous manifest is left in place. Script aborts (exit 8) |
| `WARN: rescan-storage not available at ...` / `WARN: Compute host rescan returned non-zero` | The compute-host rescan failed or is unavailable | Rescan manually |
| `WARN: Re-logging iSCSI sessions on ... (all LUNs will briefly disconnect)` | The `--force-relogin` path is about to log out/in all sessions | Expected disruption; VM disks disconnect briefly |
| `WARN: Manifest missing; falling back to discovered zvols` | The manifest is absent; expected set derived from the pool's zvols instead | Recreate the manifest (run `safe-iscsi-save`) |
| `WARN: Expected backstore ... has no corresponding zvol (skipping)` | A manifest entry has no matching zvol | Entry skipped; check the pool |
| `WARN: Device not available: ... (skipping ...)` | The zvol device node does not exist (e.g. keys not loaded) | Load ZFS keys and rerun |
| `WARN: The following zvols exist but are not in the expected manifest:` / `INFO: (They will not be exported. Use attach-vm-disk or new-vm-disk when you want to use them.)` | Policy: unlisted zvols are treated as intentionally detached | Enroll them manually if wanted |
| `FATAL: safe-iscsi-save failed — configuration may not be persistent` / `FATAL: safe-iscsi-save not available at ... — configuration may not be persistent` | The config save failed; changes exist in memory only and may not survive reboot | Resolve the save failure and rerun the save |
| `INFO: No target-side changes needed` | Every expected backstore/LUN is already in place | Informational |
| `INFO: Visible iSCSI devices on ... before/after rescan: ...` | Device counts gating the re-login decision | Informational |
| `WARN: Device count did not increase after rescan; attempting re-login` | `--force-relogin`: the rescan alone was insufficient | The re-login runs; watch for the new count |
| `INFO: ✓ Backstores added/verified: ... / INFO: ✓ LUN mappings added/verified: ...` | Summary counters | Informational |
| `WARN: Unexported zvols: ...` | Count of zvols deliberately left unexported | Attach them manually if wanted |
| `INFO: ✓ Done` | Repair completed | Informational |

### [rescan-storage](../commands-and-modules/two-node.md#rescan-storage-both)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: rescan-storage: not applicable in single-node mode (no iSCSI)` | Single-node deployments have no iSCSI | Informational; nothing to do |
| `FATAL: No active iSCSI sessions — storage network may be down` | `iscsiadm -m session` found no sessions | Run `sudo diagnose-storage` as suggested; check the storage network |
| `INFO: Total iSCSI devices visible: ...` | Device count after the rescan | Informational |
| `WARN: Expected at least ... devices (per node.conf)` / `WARN: Current count (...) is low — some LUNs may be missing` | The visible device count is below the operator-declared `EXPECTED_ISCSI_DEVICES` minimum from `node.conf` (no warning when it is unset) | Investigate missing LUNs (see `show-lun-map`) |

### [restart-iscsi-services](../commands-and-modules/two-node.md#restart-iscsi-services-storage-node)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: targetcli not found...` / `FATAL: rtslib-fb-targetctl.service not found...` | The LIO target stack is missing | Install the suggested packages and rerun |
| `FATAL: The following VMs are currently running on ...:` | Safety gate: running VMs are backed by exported zvols; the restart would sever their disks (consequence and remediation lines follow) | Stop the listed VMs, then rerun |
| `WARN: iscsi-add-encrypted-luns returned non-zero` / `WARN: iscsi-add-encrypted-luns not found; encrypted LUNs were not added` | The encrypted-LUN re-add step failed or is unavailable | Run `iscsi-add-encrypted-luns` manually |
| `WARN: ... — device not available (keys not loaded?)` | An encrypted LUN's backing zvol is missing | Load the ZFS keys |
| `WARN: ... — missing from iSCSI target` | The device exists but its backstore is not registered | Re-run `iscsi-add-encrypted-luns` or `repair-iscsi-luns` |
| `INFO: (no encrypted LUNs config at ...)` | No encrypted LUNs are configured | Informational |
| `INFO: === Complete ===` | Stop, start, re-add, save, and status all finished | Informational |

### [safe-iscsi-save](../commands-and-modules/two-node.md#safe-iscsi-save-storage-node)

Refuses to overwrite a good saved config while the target is degraded.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: ✓ Regenerated expected-backstores manifest` | The manifest was rewritten from loaded backstores | Informational |
| `WARN: Could not regenerate expected-backstores manifest (no backstores found)` | No backstores are loaded; the old manifest is kept | Check why targetcli is empty; the manifest may be stale |
| `FATAL: safe-iscsi-save: Could not install regenerated manifest at ...` | The regenerated manifest could not be moved into place (permissions/filesystem); the temp file is removed and the old manifest is kept | Check permissions on the manifest directory and rerun |
| `INFO: ✓ Boot config generated (... encrypted backstores excluded)` | The boot-time config was written without encrypted references | Informational |
| `WARN: Failed to generate boot config` | The boot-config filter failed | Boot restore may reference missing encrypted devices |
| `FATAL: safe-iscsi-save: Config not found: ...` / `FATAL: safe-iscsi-save: Manifest not found: ...` / `FATAL: safe-iscsi-save: Manifest is empty or has no valid entries` | The saved config or manifest is absent/invalid (a hint line suggests the manifest format) | Create/repair the expected-backstores manifest |
| `FATAL: safe-iscsi-save: iSCSI target is degraded (... of ... LUNs active)` | Core safety gate: fewer active backstores than the manifest expects (keys not loaded, pool not imported) — the good saved config is deliberately not overwritten | Restore the missing LUNs (load keys/import pools); to force a save anyway, run `targetcli saveconfig` manually |
| `WARN: safe-iscsi-save: More backstores (...) than manifest (...)` | More active backstores than expected (orphans or a stale manifest) | Save proceeds; reconcile the manifest |
| `INFO: ✓ iSCSI configuration saved (.../... LUNs active)` | All gates passed and the config was persisted | Informational |

### [show-lun-map](../commands-and-modules/two-node.md#show-lun-map-compute-node)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: show-lun-map: not applicable in single-node mode (no iSCSI)` | Single-node deployments have no iSCSI | Informational |
| `FATAL: No iSCSI devices found. Is the storage network up?` | No validated by-path iSCSI devices | Check the storage network and iSCSI sessions |
| `INFO: Total iSCSI LUNs visible: ...` | Final count of mapped target:LUN entries | Informational |

### [enroll-iscsi-pool](../commands-and-modules/two-node.md#enroll-iscsi-pool-storage-node)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: Must run on the storage host (...), not ...` | Full enrollment must run on the storage host | Rerun on the storage host |
| `FATAL: Pool name '...' has no IQN-safe characters (allowed: a-z 0-9 . -)` | The derived IQN short name would be empty | Rename the pool or choose another |
| `INFO: Pool ... is already enrolled in ...` | Idempotence gate: the pool-target mapping exists | Informational; nothing to do |
| `WARN: Could not back up ... to ... — continuing without a backup` | The pre-edit backup copy failed; the edit still proceeds | Check permissions if you need the backup |
| `INFO: Backed up ... to ...` | Timestamped backup created before the first modification | Informational |
| `FATAL: Failed to build updated ...` / `FATAL: Failed to install updated ...` | The node-config rewrite failed | Script aborts; check the config file |
| `INFO: Added POOL_TARGET[...]="..." to ...` | The node config was updated | Informational |
| `INFO: Updating peer node.conf on ... before local changes...` | Ordering: the peer is updated first so a failure cannot desynchronize the nodes | Informational |
| `FATAL: Failed to update node.conf on ...` / `FATAL: Nodes may be out of sync — check POOL_TARGET on both nodes before re-running` | The peer update failed; local changes were not made | Check `POOL_TARGET` on both nodes, then rerun |
| `INFO: ✓ Peer node.conf updated` | Peer update succeeded | Informational |
| `FATAL: setup-iscsi-targets not available at ...` / `FATAL: setup-iscsi-targets failed` | The target-creation step is missing or failed | Enrollment stops after the config edits; fix and rerun |
| `WARN: rescan-storage not available at ...` / `WARN: rescan-storage failed — run 'sudo rescan-storage' manually on ...` | The final rescan failed or is unavailable | Run `sudo rescan-storage` on the compute host manually |
| `INFO: enroll-iscsi-pool: not applicable in single-node mode (no iSCSI)` | Single-node deployments have no iSCSI | Informational |
| `INFO: DRY-RUN: would ...` | Dry-run plan: peer update, local `POOL_TARGET` addition, setup-iscsi-targets, rescan-storage | Rerun without `--dry-run` to apply |
| `FATAL: Failed to update local node.conf ...` | The local conf edit failed after the peer succeeded | Nodes may be out of sync; check both configs |
| `INFO: === enroll-iscsi-pool complete: ... → ... ===` | Peer conf, local conf, targets, and rescan all done | Informational |

### [enroll-proxmox-pool](../commands-and-modules/commands.md#enroll-proxmox-pool)

Registers a pool as a Proxmox storage (zfspool single-node, iSCSI two-node); `--dry-run` reports without changing.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: This script requires Proxmox VE (pvesm command not found).` | Single-node mode requires local `pvesm` (with continuation lines) | Run on a Proxmox node |
| `FATAL: Pool '...' not found (zfs list)` | The pool is not visible locally | Check the pool name; import if needed |
| `INFO: DRY-RUN: would create dataset .../proxmox` | The VM-disk dataset is missing and would be created | Rerun without `--dry-run` |
| `FATAL: Could not create dataset .../proxmox` | `zfs create` failed | Script aborts; check pool state |
| `INFO: Dataset .../proxmox already exists` | Dataset-presence gate passed | Informational |
| `INFO: Storage '...' is already registered in Proxmox[ on ...]` | Idempotence gate: the storage id is present in `pvesm status` | Informational; nothing to do |
| `INFO: DRY-RUN: would run: pvesm add ...` / `INFO: DRY-RUN: would run on ...:` | The exact registration command (single-node or two-node) that would run | Rerun without `--dry-run` |
| `FATAL: pvesm add failed for storage '...'` / `FATAL: pvesm add failed on ... for storage '...'` | The `pvesm add` failed (a hint line suggests checking target reachability for iSCSI) | Check the storage id, portal, and target |
| `INFO: ✓ Storage '...' registered in Proxmox[ on ...]` | Post-add verification passed | Informational |
| `WARN: Storage '...' not visible in pvesm status [on ...] — verify in the Proxmox GUI (Datacenter → Storage)` | Verification failed despite `pvesm add` succeeding | Check the Proxmox GUI manually |
| `FATAL: Pool '...' is not enrolled in two-node iSCSI (no POOL_TARGET entry).` | Prerequisite: the iSCSI enrollment must exist first | Run `sudo enroll-iscsi-pool <pool>` first, then rerun |
| `FATAL: STORAGE_IP is empty in node.conf (iSCSI portal unknown)` | The portal for `pvesm add iscsi` is unset | Fix the node config |
| `FATAL: Proxmox VE not found on compute host ... (pvesm missing).` | The ssh check found no `pvesm` on the compute host | Install Proxmox VE on the compute host |
| `FATAL: Invalid Proxmox storage ID '...' (allowed: letters, digits, dot, underscore, hyphen; must start with a letter or digit)` | Storage-id validation | Choose a valid id |
| `INFO: Pool: ... → Proxmox ZFS storage '...' (.../proxmox)` / `INFO: Pool: ... → Proxmox iSCSI storage '...' (short name: ...)` | Mode decision: single-node zfspool or two-node iscsi path | Informational |
| `INFO: === enroll-proxmox-pool complete: ... ===` | The chosen enrollment path finished | Informational |

### [zfslockctl](../commands-and-modules/commands.md#zfslockctl)

Inspects and manages dataset locks (list/status/release/cleanup/wait).

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: No active locks found.` / `INFO: ... active lock(s)` | List outcome | Informational |
| `INFO: Dataset '...' is not locked[ on ...]` | Status outcome: no lock | Informational |
| `INFO: Dataset '...' is LOCKED[ on ...]` | A lock exists (conflict details follow) | Resolve via the holder or `release` |
| `INFO: Type '...': available` / `INFO: Type '...': BLOCKED by ... (...)` | Per-type conflict pre-check (r/w/x) | Informational |
| `INFO: About to force-release lock:` | Pre-release disclosure (dataset/PID/script follow) before the destructive release | Review the holder before answering the prompt |
| `WARN: Force-releasing a lock held by an active process may cause data corruption!` | Safety warning before the release prompt | Prefer stopping the holder |
| `WARN: PID ... is still running!` / `INFO: PID ... is no longer running (safe to release)` | Liveness gate on the lock holder | Still-running releases are dangerous |
| `INFO: Lock released.` / `WARN: Force-released lock on ... (was held by ... PID ...)` | The lock file was removed (audit note follows for force releases) | Informational |
| `INFO: Release cancelled.` | The confirmation was declined | The lock is untouched |
| `INFO: Removing stale lock: ... (was ... PID ...)` | Cleanup: the holder is dead, so the stale lock is removed | Informational |
| `INFO: Cleanup complete: / Stale locks removed: ... / Active locks: ... / Stale PID files removed: ...` | Cleanup summary | Informational |
| `INFO: Waiting for lock availability on '...' (type=...)...` / `INFO: Press Ctrl+C to cancel.` | The wait loop is polling | Ctrl+C cancels |
| `INFO: Lock is now available! (after ... attempt(s))` | The wait succeeded | Informational |
| `INFO: [...] Blocked by: ... (...) - ... (PID ...)` / `INFO: Retrying in ... seconds...` | Per-attempt conflict report | Wait, or resolve the blocker |
| `WARN: Dataset required. / WARN: Lock ID or dataset required. / WARN: Dataset and type required. / WARN: Invalid lock type '...'. Must be r, w, or x. / WARN: Unknown command: ...` | Subcommand usage errors | See the usage text |

### [zfslockmanager](../commands-and-modules/modules.md#zfslockmanager)

Sourced library providing lock acquire/check/release. On conflict, interactive callers get the W/R/S/A/F menu (Wait / Retry / Skip dataset / Abort operation / Force release — force requires typing exactly `yes`); return codes drive callers: 0 acquired, 1 aborted, 2 skipped.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: Unable to create directory ...` | The locks/PIDs directory could not be created | Locking fails to initialize; check permissions |
| `INFO: Removed ... stale lock(s)` | Startup cleanup removed stale locks | Informational |
| `WARN: Remote lock acquisition timed out for ...` / `WARN: Unexpected response from remote lock agent: ...` | The storage-node lock agent did not answer in time or answered garbage | Treated as an error (not a conflict); check SSH and the agent |
| `WARN: zfslock_check/acquire/release ... requires ...` / `WARN: Invalid lock type '...'. Must be r, w, or x.` | Argument validation | Caller bug; check the call site |
| `WARN: Failed to create lock file ...` / `WARN: Failed to install lock file ...` | The lock file could not be written | Check the locks directory |
| `WARN: Cannot release lock owned by PID ... (we are ...)` | Ownership gate: another process holds the lock id | Release from the owning process or use force |
| `FATAL: Lock conflict on '...' in non-interactive mode[; waited ...s]. Aborting.` | Headless gate: a conflict persists and no interactive resolution is possible | The operation aborts; resolve the lock and rerun |
| `INFO`/`WARN: Lock conflict on '...': held by dataset='...' type=... pid=... script='...' acquired='...' description='...' [host='...']` | Holder details for the lock(s) blocking a headless acquisition — logged once at INFO when the headless wait starts, and again at WARN immediately before the abort | Diagnostic: identifies the blocking holder(s) in the session log; remote conflicts carry `host=` and may omit `acquired`/`description` |
| `INFO: Removed stale lock on ...; retrying acquisition.` | The conflicting lock's holder is dead; removed without asking | Informational |
| `WARN: Force-released [remote ]lock on ... (was held by ... PID ...[ on ...])` | The operator force-released a lock via the F menu choice | Audit note; the acquisition retries |

### [zfslockmanager-remote](../commands-and-modules/modules.md#zfslockmanager-remote)

Emits no log messages; it speaks a wire protocol (`LOCKED ...`, `CONFLICT ...`, `{"available": true/false}`, `ERROR: ...`) over SSH, parsed by `zfslockmanager` on the compute node. Errors are argument-validation failures; `CONFLICT` lines carry the conflicting lock's fields for the caller's resolution menu.

### [zfs_lock_manager](../commands-and-modules/python-modules.md#zfs_lock_managerpy)

Python module both the GUI and the bash scripts use for dataset locks (read/write/exclusive); in two-node mode it also queries the peer node's locks.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: zfs_lock_manager.check requires dataset and valid type` | Misuse guard — empty dataset or type not r/w/x | Check returns False |
| `WARN: could not list remote locks: ...` | The two-node compute host could not fetch the storage host's locks | Continue with local locks only |
| `WARN: failed to update pidfile ...: ...` | Best-effort PID tracking write failed during acquire/release | Continue; the lock itself is unaffected |
| `WARN: zfs_lock_manager.release requires a lock_id` | Release called with an empty id | Release returns False |
| `WARN: cannot release lock owned by PID ... (we are ...)` | Safety check — the lock file belongs to another live process | Release refused; returns False |
| `WARN: failed to remove lock file ...: ...` | Removing the lock file raised | Release returns False; a stale lock may remain |

### [iscsi_enroll](../commands-and-modules/python-modules.md#iscsi_enrollpy)

GUI enrollment of a newly created pool into two-node iSCSI (offered after pool creation; see [enroll-iscsi-pool](#enroll-iscsi-pool)).

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: 1. add [...]="..." to POOL_TARGET in node.conf on both nodes` / `2. run 'sudo setup-iscsi-targets' on the storage host` / `3. run 'sudo rescan-storage' on the compute host` | Manual-step guidance when auto-enrollment was not taken | Operator performs the manual steps |
| `INFO: iSCSI enrollment for pool '...' skipped because a dataset action is not available or already running. Manual steps:` | Runner missing/busy gate | Auto-enrollment skipped; manual steps follow |
| `INFO: iSCSI enrollment for pool '...' declined. Manual steps:` | User answered No to the enrollment dialog | Enrollment skipped; manual steps follow |
| `WARN: Invalid iSCSI short name '...' for pool '...' — falling back to '...'` | The entered short name failed character validation | Continue with the derived default |
| `INFO: iSCSI enrollment for pool '...' cancelled` | The enrollment step was cancelled mid-run | Skipped; pages refreshed |
| `WARN: iSCSI enrollment for pool '...' failed (rc=...)` | `enroll-iscsi-pool` exited non-zero (the step is non-fatal) | Failure reported; pool creation itself still counts as success |
| `INFO: Pool '...' enrolled in two-node iSCSI` | The enrollment script completed | Pages refreshed |

### [proxmox_enroll](../commands-and-modules/python-modules.md#proxmox_enrollpy)

GUI registration of a pool with Proxmox (offered after pool creation or migration; see [enroll-proxmox-pool](#enroll-proxmox-pool)).

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: 1. run 'sudo enroll-iscsi-pool ...' on the storage host` (and the numbered/continuation guidance lines that follow, for the two-node and single-node variants) | Manual-step guidance when the pool is not iSCSI-enrolled or registration was not taken | Operator performs the manual steps |
| `INFO: Proxmox storage enrollment for pool '...' skipped: the pool is not enrolled in two-node iSCSI. Manual steps:` | Gate — a two-node pool must be iSCSI-enrolled first | Skipped; manual steps follow |
| `WARN: Proxmox (pvesm) not reachable on compute host ... — pool '...' was not registered. Manual steps:` | The SSH probe for `pvesm` failed on the compute host (two-node only) | Skipped; manual steps follow |
| `WARN: Could not read pvesm status — cannot tell whether pool '...' is already registered with Proxmox. Manual steps:` | The `pvesm status` query failed | Skipped; manual steps follow |
| `INFO: Pool '...' is already registered with Proxmox as storage '...'` | The derived storage ID is present in the `pvesm` output | Enrollment skipped (already done) |
| `INFO: Proxmox storage enrollment for pool '...' skipped because a dataset action is not available or already running. Manual steps:` | Runner missing/busy gate | Skipped; manual steps follow |
| `INFO: Proxmox storage enrollment for pool '...' declined. Manual steps:` | User answered No to the register dialog | Skipped; manual steps follow |
| `WARN: Invalid Proxmox storage ID '...' for pool '...' — falling back to '...'` | The entered ID failed the storage-ID validation | Continue with the derived default |
| `INFO: Proxmox storage enrollment for pool '...' cancelled` | The BashStep was cancelled | Skipped; pages refreshed |
| `WARN: Proxmox storage enrollment for pool '...' failed (rc=...)` | `enroll-proxmox-pool` exited non-zero (the step is non-fatal) | Failure reported |
| `INFO: Pool '...' registered with Proxmox as storage '...'` | The enrollment script completed | Informational |
| `WARN: No pool selected for Proxmox enrollment` | Disks page pool selector empty | Aborted |
| `WARN: Proxmox enrollment is available only on the storage host` | Two-node gate on the Disks page action | Aborted |
| `WARN: A dataset action is already running` | Runner busy guard | Aborted |

## Pool and System Maintenance

See also [zfs-migrate-send](#zfs-migrate-send) under Backup and Send/Receive for pool-migration transfer messages, and [zfslockctl](#zfslockctl) / [zfslockmanager](#zfslockmanager) under Two-Node iSCSI and VM Disks for dataset-lock messages.

### [zfsscruball](../commands-and-modules/commands.md#zfsscruball)

Parallel scrub scheduler with pause/resume modes tracked in a state file.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: Pausing all running scrubs.` | Pause mode selected; every pool is scanned for a scrub in progress | Informational |
| `INFO: Pausing scrub on ...` | This pool has a scrub in progress; `zpool scrub -p` is issued | Informational |
| `INFO: No scrubs in progress to pause.` | The pause scan found nothing | Informational |
| `INFO: Skipping ... (already completed).` | Resume mode: the state file lists this pool as already scrubbed | Pool skipped |
| `INFO: No pools to scrub.` | Resume mode: no paused or pending pools remain | Informational |
| `INFO: Resuming scrub (... at a time): ...` / `INFO: Scrubbing (... at a time): ...` | Resume/start decision: the pool list about to be scrubbed in parallel | Informational |
| `WARN: ✗ Failed to scrub ...` | `zpool scrub -w` returned non-zero; the pool is not recorded as done, so a later resume retries it | Check the pool status; rerun |
| `INFO: All scrubs complete.` | Final outcome; the state file is removed | Informational |

### [zfsaddisk](../commands-and-modules/commands.md#zfsaddisk)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: This script requires Proxmox VE (qm command not found).` | The `qm` tool is missing (with continuation lines) | Script aborts; run on a Proxmox node |
| `INFO: Command to be issued: ...` | Safety gate: the constructed `qm set ... --scsiN` command is shown before running | Press Enter to issue it |

### [zfsallthepools](../commands-and-modules/commands.md#zfsallthepools)

Emits no log messages; it is a deprecated compatibility shim that sources `zfsconfig` (the pool list now lives in the JSON config).

### [zfsbuildfsarray](../commands-and-modules/modules.md#zfsbuildfsarray)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: A dataset must be specified.` | No dataset argument | Script aborts (exit 8) |
| `FATAL: Invalid depth = ...` | The depth argument is not a non-negative integer | Script aborts (exit 8) |
| `FATAL: startwith: "..." was not found in any of the eligible dataset names.` / `FATAL: endwith: "..." was not found in any of the eligible dataset names.` | The start/end filter removed every dataset from the array | Script aborts (exit 8); widen the filter |

### [zfs-diagnose-busy](../commands-and-modules/modules.md#zfs-diagnose-busy)

Issued automatically when `zfs destroy` fails. Each `WARN:` line names a
specific cause and suggests the fix. The process scan requires `fuser` or
`lsof`, the iSCSI check requires `targetcli`, and the VM check requires `qm` —
each check silently skips when its tool is absent.

| Message prefix | Meaning | Response |
| ------------- | ------- | -------- |
| `WARN: ZFS reported: ...` | Raw stderr captured from the failed `zfs destroy` | Read alongside the diagnosis below |
| `→ Snapshot has clone dependents: ...` | One or more clones were created from this snapshot | Promote or destroy the dependent clones first |
| `→ One or more snapshots of ... have clone dependents.` | Dataset target: some snapshot under it is a clone origin | Promote or destroy the dependent clones first |
| `→ Snapshot has holds: ...` | ZFS hold tags are present | Use the `releaseholds` option or `zfs release <tag> <snap>` |
| `→ Dataset is mounted at ...` | The dataset is mounted; a process scan follows | See the `Open processes:` line that follows |
| `Open processes: ...` | `fuser` (or `lsof`) found processes with the mountpoint open | Stop the listed processes or unmount first |
| `No open processes detected (try unmounting first).` | The dataset is mounted but no process was found using it | Try unmounting anyway |
| `→ Dataset has an active or interrupted receive (resume token present)` | A `zfs receive` is in progress or was interrupted | Allow it to complete, or abort with `zfs receive -A <dataset>` |
| `→ An active 'zfs send' involving ... is running` | A `zfs send` process appears to be using the dataset/snapshot (best-effort match) | Wait for it to finish |
| `→ Zvol is exposed as an iSCSI LUN on ...` | The zvol is mapped to an iSCSI target/LUN | Use [remove-vm-disk](../commands-and-modules/two-node.md#remove-vm-disk-both) or targetcli to tear down |
| `→ Zvol has an iSCSI backstore (...) but no LUN mapping.` | A targetcli backstore exists for the zvol but no LUN maps it | Tear down the backstore before destroying |
| `→ VM ... is RUNNING and may be using ...` | A Proxmox VM is active on this zvol | Stop the VM before destroying |
| `→ Dataset is shared via NFS (...)` | The dataset is exported via `sharenfs` | Unshare with `zfs set sharenfs=off` before destroying |
| `→ Dataset is shared via SMB (...)` | The dataset is exported via `sharesmb` | Unshare with `zfs set sharesmb=off` before destroying |
| `→ No specific cause identified. Common remaining reasons:` | None of the checks matched; three hint bullets follow (busy child snapshot, process via a different path, pool scrub/resilver) | Try `fuser -m <mountpoint>` or `lsof +D <mountpoint>` manually; check for pool scrub/resilver |

### [zfsgetashift](../commands-and-modules/commands.md#zfsgetashift)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: The ashift value for ... is ..., which is ... bytes per zpool block.` | The script's single result (ashift read via `zdb -l`) | Informational |

### [zfsmount](../commands-and-modules/commands.md#zfsmount)

Mounts or unmounts a subtree per the first argument (`mount`/`unmount`).

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: $1 must be either "mount" or "unmount"` | Mode argument invalid | Script aborts (exit 8) |
| `FATAL: A subtree must be specified.` | No subtree argument | Script aborts (exit 8) |
| `INFO: About to ... the following datasets:` | Safety gate: the eligible dataset list follows, then a press-enter prompt | Press Enter to proceed |
| `WARN: No eligible datasets were found in ...` | The subtree exists but no dataset matches the mount condition for this mode | Nothing to do (exit 4) |
| `WARN: No elibigle datasets found in ...` (message spelling) | The subtree listing returned no datasets at all | Nothing to do (exit 4); check the subtree name |
| `WARN: Skipping ... (user skipped lock acquisition).` | The operator declined this dataset's lock prompt | Dataset skipped, the rest continue |
| `FATAL: Could not acquire write lock on ...; aborting.` | Lock acquisition failed outright | Script aborts (exit 8); resolve the lock |

### [zfsmountsnapshot](../commands-and-modules/commands.md#zfsmountsnapshot)

Emits no log messages; it is a commented example transcript for browsing a dataset's `.zfs/snapshot` directory.

### [zfsunmount](../commands-and-modules/commands.md#zfsunmount)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: Skipping ... (user skipped lock acquisition).` | The operator declined this filesystem's lock prompt | Filesystem skipped, the rest continue |
| `FATAL: Could not acquire write lock on ...; aborting.` | Lock acquisition failed outright | Script aborts (exit 8); resolve the lock |
| `WARN: Unable to unmount ...` | `zfs unmount` returned non-zero | Next filesystem is attempted; check what holds the mount |

### [zfsrecurse](../commands-and-modules/commands.md#zfsrecurse)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: WIP!` | The script is deliberately disabled at the top | Nothing runs; do not use |

### [zfssetarcsize](../commands-and-modules/commands.md#zfssetarcsize)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: Setting zfs_arc_max to ... on the fly` | The runtime ARC max is being written | Informational |
| `INFO: Updating /etc/modprobe.d/zfs.conf for persistence` | The modprobe config is being updated and the initramfs rebuilt | Informational |

### [zfsshowbigstuff](../commands-and-modules/commands.md#zfsshowbigstuff)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: A dataset must be specified.` | No dataset argument | Script aborts (exit 1) |
| `FATAL: Sort option must be either 'largest' or 'smallest'.` | Invalid sort argument | Script aborts (exit 1) |

### [zfsshowtuneables](../commands-and-modules/commands.md#zfsshowtuneables)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: [OK] Found ...` | `/etc/modprobe.d/zfs.conf` exists; its `options zfs` lines follow | Informational |
| `INFO:   (no 'options zfs' lines found)` | The conf file exists but has no active option lines | Informational |
| `WARN: ... not found.` | `/etc/modprobe.d/zfs.conf` is missing | Script aborts; create the tuning config |
| `INFO: [OK] zfs.conf is included in initramfs image (...)` | The conf is embedded in the current initrd | Informational |
| `FATAL: [FAIL] zfs.conf not found in initramfs! Run: sudo update-initramfs -u -k all` | The conf exists on disk but is not in the initramfs | Run the suggested command, then rerun |
| `INFO:   (No matching ... parameters found — possibly renamed or unsupported)` | The checked runtime parameters do not exist in this ZFS version | Informational |
| `WARN: No ZFS load messages found in dmesg.` | The optional dmesg check found no ZFS lines | Informational |
| `INFO: === Verification Complete ===` | All checks ran to the end | Informational |

### [zfsshowzpooldevices](../commands-and-modules/commands.md#zfsshowzpooldevices)

Emits no log messages; it is a one-line `zpool status -LPs -c vendor,model,size,serial` wrapper.

### [zfsstatus](../commands-and-modules/commands.md#zfsstatus)

Emits no log messages; it runs `watchall` around `zpool list`/`zpool status`.

### [zfswatcharc](../commands-and-modules/commands.md#zfswatcharc)

Emits no log messages; the ARC display loop uses plain `echo`/`printf` output.

### [zfswipe](../commands-and-modules/commands.md#zfswipe)

Wipes labels/signatures from an inactive disk (Disks page **Wipe Labels…**,
or standalone). Ladder: `zpool labelclear -f` → `wipefs -a` → `dd`, stopping
as soon as the device probes clean.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: A device path must be specified.` | No device argument | Script aborts (exit 8) |
| `FATAL: ... is not a block device.` | The argument does not resolve to a block device | Script aborts (exit 8) |
| `FATAL: Could not determine the backing disk of ...` | lsblk could not classify the device as disk/partition | Script aborts (exit 8) |
| `FATAL: zpool is not available; cannot verify the disk is inactive.` / `FATAL: zpool list failed (rc=...); cannot verify the disk is inactive.` | The inactivity check cannot run | Script aborts (exit 8) |
| `FATAL: ... is a member of imported pool '...'. Only inactive disks can be wiped.` | The device (or a partition of its backing disk) belongs to a live pool | Script aborts (exit 8); import/destroy the pool or pick another disk |
| `FATAL: ... is mounted or in use as swap (...). Only inactive disks can be wiped.` | Something on the backing disk is mounted (or swap) | Script aborts (exit 8) |
| `INFO: Wipe plan for ... (...)` | The ladder about to run, with the device's node list and per-step availability | Informational |
| `INFO: Type the device name to confirm the wipe.` | Typed-confirmation prompt (skipped with `--confirmed`); the device name must be typed exactly | Type the kernel device name to proceed; a mismatch cancels |
| `INFO: Wipe cancelled — no changes were made.` / `INFO: Wipe cancelled — confirmation did not match. Expected '...', got '...'.` | The typed confirmation was declined or wrong | Run ends (exit 0); nothing was touched |
| `INFO: ... has no detectable signatures; nothing to do.` | The initial probe found no signatures | Run ends (exit 0) |
| `INFO: ... verified clean after zpool labelclear.` / `INFO: ... verified clean after wipefs.` / `INFO: ... verified clean after dd.` | A ladder step sufficed; later steps are skipped | Informational |
| `WARN: wipefs is not available; falling back to dd.` | `wipefs` is missing from the system | The ladder jumps to `dd` |
| `WARN: Signatures remain on ...; falling back to dd.` | The probe still lists signatures after `labelclear`/`wipefs` | The ladder continues with `dd` |
| `WARN: Could not determine a usable size for ...; skipping dd on it.` | The node's size could not be read (or is under 2 MiB) | That node is skipped; others continue |
| `WARN: Could not re-read the partition table of ... Run partprobe ... (or rescan-storage, or reboot) before reusing the disk.` | No partition-table re-read tool could run after the `dd` wipe | Run `partprobe` manually; stale partition nodes may linger |
| `WARN: ... still shows signatures after dd; it may be in use or faulty.` | The post-`dd` probe still lists signatures | Script aborts (exit 8); inspect the device |
| `INFO: ... wiped by dd; verification is unavailable (no wipefs) — re-check the device before reuse.` | `dd` completed but no probe tool exists to confirm cleanliness | Informational |
| `INFO: Wipe complete on ... (methods: ...).` | Final outcome naming every method that ran | Informational |

### [zfsreadthru](../commands-and-modules/commands.md#zfsreadthru)

Reads a dataset's data back from disk (scrub-like read pass through the oldest snapshot, then incrementals).

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: A dataset must be given as $1.` / `FATAL: A dataset must be given as $1 or $sourcefs.` | Source dataset missing | Script aborts (exit 8) |
| `FATAL: Unable to find <size> in the input: ...` | The size estimate output could not be parsed | Script aborts (exit 8) |
| `INFO: About to read the following:` | Safety gate: the snapshot list follows, then a press-enter prompt (skipped when autoproceed=Y) | Press Enter to proceed |
| `INFO: Part one: Full read-through to then $firstsnap/oldest snapshot.` | Phase marker for the oldest-snapshot read pass | Informational |
| `INFO: Reading .... Estimated amount of data to read: ... bytes.` | Size estimate for the current pass; press-enter prompt unless autoproceed=Y | Press Enter to start the read |
| `INFO: Part two: Read-through from the above snapshot to the $lastsnap/newest snapshot.` | Phase marker for the incremental pass (no further prompts) | Informational |

### [zfslistkeys](../commands-and-modules/commands.md#zfslistkeys)

Emits no log messages; it prints a plain header plus `zfs list` output for the pool's encryption keys.

### [zfsoverrides](../commands-and-modules/modules.md#zfsoverrides)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: Running with overrides: ...` | At least one override argument was passed and is about to be applied to the caller's variables | Informational |

### [zfsremoveleadingqualifiers](../commands-and-modules/modules.md#zfsremoveleadingqualifiers)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: Usage: ... <number_of_qualifiers_to_remove> <dataset_name>` | Wrong argument count | Script aborts (exit 1) |
| `FATAL: Number of qualifiers to remove must be a non-negative integer` | The count argument failed validation | Script aborts (exit 1) |
| `FATAL: Dataset name cannot be empty` | Empty dataset argument | Script aborts (exit 1) |

### [pools_page](../commands-and-modules/python-modules.md#pools_pagepy)

GUI Pools tab: pool registry table, import/export actions, scrub toggles, and the gated "send details to log" action.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: Error running zpool list: ...` | Full pool listing failed during page refresh | Continue with an empty online-pool map |
| `VERB: Pool '...' is online but not in the pool registry` | ZFS knows a pool the GUI registry does not; the row is flagged unregistered | Register the pool in the Pools tab |
| `VERB: Pool '...' is importable but not in the pool registry` | An importable-but-unimported, unregistered pool is listed as IMPORTABLE | Import/register it if intended |
| `INFO: System weekly scrub enabled` / `disabled` | The weekly system-scrub toggle was applied to the config and synced to all known pools | Informational |
| `INFO: System monthly scrub enabled` / `disabled` | The monthly system-scrub toggle was applied and synced | Informational |
| `WARN: Select a pool to send details to log` | Details action with empty selection | Action aborted |
| `WARN: Send details to log requires a single selection` | Multiple pools selected | Action aborted |
| `WARN: Error reading details for ...` | The property query returned empty | Details dump aborted |
| `INFO: Details for ... (pool)` | Header of the gated details dump (the property lines follow) | Informational |

### [pool_actions](../commands-and-modules/python-modules.md#pool_actionspy)

GUI Pools tab actions: watch windows, details dump, registry add/remove/save/revert, import/export (with blocker recovery), and scrub queue selection.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: Select at least one pool to watch` / `to view details` / `to export` / `to scrub` / `to pause` / `to resume` / `to stop` / `registered pool to remove` | Selection guard for the corresponding action | Action aborted |
| `WARN: Pool '...' is offline — cannot watch` | The selected pool's health is OFFLINE | That pool skipped; others still opened |
| `INFO: Opened watch window(s) for ... pool(s)` | Summary of watch windows opened | Informational |
| `WARN: Error getting status for '...'` / `Error reading properties for '...'` | The status/property query returned empty | Details dump aborted |
| `INFO: Pool details for ...:` / `INFO: zpool get all output for ...:` | Headers of the gated status/property dumps | Informational |
| `WARN: Pool '...' is already in the registry` | Add-pool gate — duplicate name | Add aborted |
| `INFO: Added '...' to pool registry (unsaved)` | Registry list updated, not yet saved to JSON | Use Save to persist |
| `INFO: Pool '...' imported successfully` | `zpool import` succeeded | Pages refreshed |
| `WARN: Error importing pool '...'` | Import failed | That import aborted; others continue |
| `INFO: Pool '...' exported successfully` | Export succeeded after the Yes/No confirm | Informational |
| `WARN: Error exporting pool '...'` | Export failed; the blocker-diagnosis/recovery path is entered | Recovery continues |
| `INFO: Pool '...' exported successfully after resolving blockers` | Export succeeded on retry after VM/LUN/share/process teardown | Informational |
| `INFO: Removed '...' from pool registry (unsaved)` | Pool dropped from the known list after Yes/No confirm (the pool itself is not destroyed) | Save persists |
| `INFO: No changes to save` | The dirty flag is false | Save skipped |
| `WARN: Error saving pool registry: ...` | Saving the registry JSON raised | Save aborted; changes stay unsaved |
| `INFO: Pool registry saved to JSON config` | Save succeeded | Informational |
| `INFO: Pool registry reverted` | Registry restored from the last-saved state | Informational |
| `WARN: Selected pools are not paused` | None of the selected pools is in the paused bucket | Resume aborted |
| `WARN: Failed to stop VM ...: ...` | `qm stop` returned non-zero after the per-VM approval dialog | Export recovery aborted |
| `INFO: Stopped VM ...` | An approved VM was stopped to unblock export | Recovery continues |
| `WARN: Failed to remove LUN ... from ...: ...` | targetcli LUN delete failed after approval | Export recovery aborted |
| `INFO: Removed LUN ... from ...` | An approved LUN mapping was deleted | Backstore removal continues |
| `WARN: Failed to remove iSCSI backstore ...: ...` | targetcli backstore delete failed (and no LUN removed) | Export recovery aborted |
| `INFO: Removed iSCSI backstore ...` | An approved backstore was deleted | Recovery continues |
| `WARN: Failed to disable ... share on ...` | `zfs set sharenfs/smb=off` failed after approval | Export recovery aborted |
| `INFO: Disabled ... share on ...` | An approved NFS/SMB share was disabled | Recovery continues |
| `WARN: Could not signal PID ...: ...` / `Could not kill PID ...: ...` | TERM/KILL of an approved busy process failed | Continue with other PIDs |
| `INFO: Terminated processes using ...` | Approved busy processes were terminated | Recovery continues |
| `WARN: Could not determine which dataset blocked export of '...'` | A "cannot unmount" mountpoint could not be mapped to a dataset | Generic blocker collection continues |
| `WARN: zpool export stderr: ...` | Raw export stderr logged when the dataset is unknown | Informational; recovery continues |
| `WARN: No specific blockers identified. Common causes are active sends/receives, scrubs, or processes holding the pool through a different path.` | Blocker collection came up empty | Recovery aborted; export stays failed |
| `WARN: Auto-unmount of filesystems failed: ...` | Safe unmount of non-blocked filesystems failed | Approval-driven recovery continues anyway |
| `INFO: Export of '...' cancelled by user` | An approval dialog (VM/LUN/share/process/force-kill) was answered No | Export recovery aborted |
| `WARN: Export of '...' still failed after recovery: ...` | The export retry failed after resolving blockers | Pool remains imported |

### [pool_create_wizard](../commands-and-modules/python-modules.md#pool_createpy)

GUI Create Pool wizard (storage host only); offers registry, iSCSI, and Proxmox enrollment after success.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: No pool profiles configured` | No pool profiles exist in the config, so the wizard cannot proceed | Wizard aborted before opening; use Advanced: Manage Pool Profiles on the Disks page |
| `INFO: Added '...' to pool registry (unsaved)` | The register-pool offer was accepted and the pool appended to the known list | Save in the Pools tab to persist |
| `WARN: Pool creation is available only on the storage host` | Two-node gate — invoked on the compute node | Action aborted |
| `WARN: Dataset runner not available` / `A dataset action is already running` | Runner missing / busy guard | Action aborted |
| `WARN: Could not scan importable pools: ...` | The importable-devices scan failed during eligibility | Continue with an empty importable map |
| `INFO: Create Pool cancelled for ...` | The run completed with cancelled=True | Lock released; pages refreshed; enrollment offers skipped |
| `WARN: Create Pool failed for '...' (rc=...)` | The create step exited non-zero | Lock released; no register/iSCSI/Proxmox offers |
| `INFO: Pool '...' created` | Final success | Register and enrollment offers may follow |

### [pool_growth](../commands-and-modules/python-modules.md#pool_growthpy)

Helpers for the pool-growth operations; only one message of its own (the scrub gate's refusal text is shown as a dialog, not logged).

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: could not read scrub state for pool '...': ...` | The scrub-state read failed while checking the pre-operation scrub gate | The operation is not blocked — ZFS itself is the final arbiter |

### [pool_growth_dialogs](../commands-and-modules/python-modules.md#pool_growth_dialogspy)

GUI dialogs for growing and maintaining pools: add data vdev, expand vdev (attach), RAIDZ expansion, special/log/cache vdevs, detach, and replace.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: Pool growth is available only on the storage host` / `Pool maintenance is available only on the storage host` | Two-node gates — invoked on the compute node | Action aborted |
| `WARN: Dataset runner not available` / `A dataset action is already running` | Runner missing / busy guard | Action aborted |
| `WARN: No imported pools to grow` / `No imported pools to maintain` | The inventory cache has no imported pools | Action aborted |
| `WARN: Could not scan importable pools: ...` | The importable-devices scan failed | Continue with an empty importable set (eligibility may be stricter) |
| `INFO: Add vdev cancelled for ...` / `Detach cancelled for ...` / `Replace cancelled for ...` / `Expand vdev cancelled for ...` / `Add ... vdev cancelled for ...` | The corresponding step was cancelled before completing | Skipped; state refreshed |
| `WARN: Add vdev failed for pool '...' (rc=...)` / `Detach failed ...` / `Replace failed ...` / `Expand vdev failed ...` / `Add ... vdev failed ...` | The corresponding `zpool add/attach/replace/detach` step exited non-zero | Operation aborted; refresh anyway |
| `INFO: Added vdev to pool '...'` / `Detached device from pool '...'` / `Replaced device in pool '...'` / `Expanded vdev in pool '...'` / `Added ... vdev to pool '...'` | The operation completed (typed pool-name confirmations and scrub-state gates passed as applicable) | Pages refreshed |
| `INFO: Resilver of pool '...' underway — watch live progress in the Pools tab Watch window` | Post-replace follow-up guidance | Watch the resilver in the Watch window |
| `INFO: RAIDZ expansion of pool '...' underway — use the Rewrite Data action on the Disks page per filesystem dataset to restripe existing data at the new ratio` | Emitted only when the attach kind was RAIDZ expansion | Optional per-dataset Rewrite Data to restripe |

### [pool_migrate_dialogs](../commands-and-modules/python-modules.md#pool_migrate_dialogspy)

GUI Migrate Pool wizard (storage host only): copy phase, then a destructive cutover phase gated by typed confirmation, layout re-checks, and a running-VM warning.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: Could not list zvols of pool '...': ...` | Zvol listing failed while finding VMs on the source pool | No running-VM check possible; cutover still gated by confirm/export |
| `WARN: Could not read the node configuration: ...` | Node config unreadable during the VM check | Continue as single-node (local `qm` used) |
| `WARN: No compute host configured; skipping the running check for VM ...` | Two-node mode but no compute host is set | That VM's status check skipped (non-fatal by design) |
| `WARN: Could not check the status of VM ...: ...` | `qm status` (local or via SSH) failed | That VM skipped |
| `WARN: Could not scan dataset mountpoints: ...` | The dataset scan for root-pool detection failed | The root pool is not excluded from holding pools |
| `INFO: Snapshot holds captured from '...' are preserved in ...; once the pool is imported, reapply them with: zfsreapplyholds --apply ... ...` | After a failed/cancelled cutover, the captured-holds TSV is kept and the recovery command is spelled out | Re-apply holds manually after import |
| `WARN: Pool migration is available only on the storage host` | Two-node gate — invoked on the compute node | Action aborted |
| `WARN: Dataset runner not available` / `A dataset action is already running` | Runner missing / busy guard | Action aborted |
| `WARN: No imported pools to migrate` | No imported pools found | Action aborted |
| `WARN: Could not list datasets of pool '...': ...` | Per-pool dataset listing failed during setup | Continue with an empty list for that pool |
| `WARN: Could not read pool properties of '...': ...` | The curated pool-property read for the origin-derived defaults failed | The "Match origin pool" pseudo-profile falls back to empty pool properties; the wizard stays usable |
| `WARN: Could not read root dataset properties of '...': ...` | The origin root dataset's live-property read failed | The "Match origin pool" pseudo-profile falls back to empty filesystem properties; the wizard stays usable |
| `WARN: Could not read the non-default pool properties of '...': ...` | The SOURCE-aware pool-property read for the replay list failed | The replay checkbox list is empty; set any such properties manually after the cutover |
| `WARN: Could not scan importable pools: ...` | The importable-devices scan failed during eligibility | Continue with an empty map |
| `WARN: Migrate Pool aborted for '...': pool changed after the review (...)` | Safety gate — the live dataset layout differs from the reviewed plan before copy starts | Aborted; re-review the plan; nothing runs |
| `INFO: Migrate pool cancelled for ...` | The copy phase was cancelled | Lock released; holds file discarded; refresh |
| `WARN: Migrate pool copy failed for '...' (rc=...); no destructive step was run` | The copy phase exited non-zero | Aborted before cutover; lock released; holds file discarded |
| `WARN: Migrate pool start failed for '...' (...); captured-holds file discarded` | Starting the run itself failed (step build, lock acquisition, runner start) after the holds TSV was reserved | Nothing ran; lock released if taken; the error is re-raised — address it and rerun |
| `INFO: Migrate pool copy complete for '...'; waiting for cutover confirmation` | Copy phase finished; the destructive phase is now gated | Layout re-check and running-VM warning, then the cutover dialog |
| `WARN: Migrate Pool aborted for '...': pool changed at cutover time (...)` | Safety gate — the layout changed since review at the cutover moment | Cutover aborted; snapshot/copies remain; re-review |
| `INFO: Cutover deferred for '...' (running VMs declined); the migration snapshot and copies remain in place — rerun Migrate Pool to finish` | The running-VMs warning was declined at cutover | Cutover not run; state preserved for a later rerun |
| `INFO: Cutover deferred for '...'; the migration snapshot and copies remain in place — rerun Migrate Pool to finish` | The typed cutover confirmation was cancelled | Cutover not run; state preserved |
| `INFO: Migrate pool cutover cancelled for ...` | The cutover phase was cancelled mid-run | Holds-preservation info logged next |
| `WARN: Migrate pool cutover failed for '...' (rc=...) — the pool may be left exported; investigate before retrying` | The cutover phase exited non-zero | Holds file preserved; investigate the export state before retrying |
| `INFO: Pool '...' migrated successfully (mode: ...)` | Final success | Holds file discarded; iSCSI repair or Proxmox offer follows |
| `INFO: Reminder: pool '...' had ... vdev(s) before the migration and the new pool does not; re-add them with Add Infrastructure Vdev` | The source pool had infrastructure vdevs (special/log/cache/spare), which are never recreated by the migration | Re-add them after the cutover with Add Infrastructure Vdev (and remove the old ones from the source disks if they were reused) |
| `INFO: iSCSI LUN re-registration for '...' cancelled` | The post-migration `repair-iscsi-luns` step was cancelled (iSCSI-managed pool) | Refresh; the Proxmox offer still follows |
| `WARN: iSCSI LUN re-registration for '...' failed (rc=...)` | The repair step exited non-zero | Refresh; the Proxmox offer still follows |
| `INFO: iSCSI LUNs re-registered for '...'` | The repair step succeeded for an iSCSI-managed pool | Refresh; the Proxmox offer follows |
| `INFO: Pool '...' is not enrolled in two-node iSCSI, so VM disks on it are not available over iSCSI. Manual enrollment steps:` | Two-node mode but the pool is not iSCSI-managed | Manual enrollment instructions follow |

### [pool_profile_dialogs](../commands-and-modules/python-modules.md#pool_profile_dialogspy)

Pool-profile manager and editor dialogs (Advanced: Manage Pool Profiles on the Disks page). Pool profiles bundle the creation-time pool shape — blocksize, curated pool properties, and root filesystem properties — for Create Pool and Migrate Pool.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: Select a pool profile to edit` / `WARN: Select a pool profile to delete` | No pool-profile row selected | Action aborted |
| `WARN: Pool profile ... no longer exists` | The selected name vanished from the saved profiles | Edit aborted; list refreshed |
| `WARN: Pool profile '...' is built in and cannot be deleted` | Built-in pool-profile delete guard | Delete aborted |

### [zfs_repository](../commands-and-modules/python-modules.md#zfs_repositorypy)

Repository layer that wraps the `zfs`/`zpool` commands for the GUI.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: creating pool: ...` | The `zpool create` command is about to execute | Informational |
| `WARN: zpool create failed (rc=...): ...` | `zpool create` returned non-zero | Caller aborts pool creation |
| `INFO: pool operation: ...` | A pre-built `zpool add/attach/replace/detach` command is about to execute | Informational |
| `WARN: zpool ... failed (rc=...): ...` | That pool command failed | Caller informed of failure |
| `DEBUG: zpool scrub ... failed: rc=...` | A scrub pause/resume command returned non-zero | Caller informed of failure |
| `VERB: zpool scrub ... completed` | The scrub pause/resume command returned 0 | Informational |
| `WARN: Failed to set ...=... on ...: ...` | `zfs set` returned non-zero (e.g. disabling a share during export recovery) | Caller informed of failure |
| `WARN: Error scanning importable pools: ...` | The background importable-pool cache refresh raised | Continue with an empty name set |

### [datasets_page](../commands-and-modules/python-modules.md#datasets_pagepy)

GUI Datasets tab tree and the gated details/send-to-log actions.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: Could not load root dataset for pool ...: ...` | The root-dataset row failed to load | A minimal fallback row keeps the pool expandable |
| `WARN: Error listing pools: ...` | Pool listing failed during page refresh | Refresh aborted |
| `WARN: Applying profiles is available only on the storage host` | Two-node gate — action attempted on the compute node | Apply-profile aborted |
| `WARN: Select at least one dataset to apply a profile` / `Apply Profile requires a single dataset selection` | Selection guards for Apply Profile | Action aborted |
| `WARN: Select an item to send details to log` / `Send details to log requires a single selection` | Selection guards for the details action | Action aborted |
| `INFO: Details for hold '...' on ...@... (hold) ...` | Gated details dump for a hold row (tag, snapshot, dataset) | Informational |
| `WARN: Error reading details for ...: ...` | The property query failed for the item | Details dump aborted |
| `INFO: Details for ... (...)   ...: ...` | Gated details dump for a pool/dataset/snapshot: header plus sorted property lines | Informational |

### [dataset_actions](../commands-and-modules/python-modules.md#dataset_actionspy)

GUI Datasets tab actions: snapshot, delete (with hold gate), holds, rollback, browse, mount/unmount (including zvol loop-mounts and orphaned-mount recovery).

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: Select ...` (one or more datasets to snapshot / something to delete / one or more snapshots to hold / exactly one snapshot to roll back to / exactly one pool to show big stuff / exactly one item to browse / an item to mount / filesystems, snapshots, or volumes to mount / an item to unmount / filesystems, snapshots, or volumes to unmount / a filesystem, snapshot, or mounted volume partition to browse) | Selection guard for the corresponding action | Action aborted |
| `WARN: Snapshot name cannot contain spaces or slashes` | Snapshot-name validation failed | Re-enter the name |
| `INFO: Creating snapshot: ...` | Single-selection name validated and dialog confirmed; the snapshot command runs under a dataset lock | Continue to create |
| `INFO: Creating snapshot '...' on N datasets` | Multi-selection dialog confirmed; each dataset is snapshotted in turn under one locks set | Continue to create |
| `INFO: Snapshot created: ...` | The snapshot command succeeded for that dataset | Page refreshed once anything was created |
| `WARN: Error creating snapshot` | Single-selection snapshot command returned failure | Inspect the ZFS error |
| `WARN: Error creating snapshot: ...` | The snapshot command failed for that dataset in a multi-selection batch | Remaining datasets still attempted |
| `WARN: Created snapshot on N of M datasets` | Multi-selection summary — at least one dataset failed | Check the per-dataset warnings above |
| `WARN: cannot snapshot ... / cannot destroy ... / cannot delete snapshots: ... / cannot release holds: ... / cannot set holds: ... / cannot rollback ...: ...` (ending with the lock error) | A dataset lock could not be acquired for that action | Action aborted; another operation holds the dataset |
| `WARN: Error: zfs command not found` | The `zfs binary is missing from PATH | Action aborted |
| `WARN: cannot destroy ...: dataset is locked by another operation` | Pre-flight lock check failed before the destroy dialog | Delete of all selected datasets aborted |
| `WARN: Dataset runner not available` / `A dataset action is already running` | Runner missing / busy guard | Action aborted |
| `WARN: Cannot delete: the following snapshots have holds that were not selected:\n ...` | Safety gate — selected snapshots carry holds the user did not select for release | Batch delete aborted; select the holds too |
| `INFO: Deleted ... snapshot(s)` | Final summary — all selected snapshots destroyed with zero errors after Yes/No confirm | Page refreshed |
| `WARN: Error deleting ...` | Destroying one snapshot failed (busy diagnosis appended) | Error counted; other snapshots still attempted |
| `WARN: Error releasing '...' on ...` / `Error setting hold '...' on ...` | The release/hold command failed for one item | Continue with the remaining items; that hold stays |
| `INFO: Rolled back to ...` | Rollback succeeded after the destructive Yes/No confirm | Page refreshed |
| `WARN: Error rolling back to ...` | The rollback command failed | Dataset unchanged |
| `WARN: Cannot open ...: mountpoint is ...` | The dataset mountpoint property is not a path (legacy/none) | Browse aborted |
| `WARN: Error opening file manager: ...` / `Error browsing snapshot ...: ...` | Launching the file manager failed (mountpoint resolution or xdg-open) | Browse aborted |
| `VERB: Opened ...` / `Browsing snapshot ...` | The file manager was launched for the dataset/snapshot path | Browse succeeded |
| `WARN: Error resolving mountpoint for ...: ...` / `FATAL: Error resolving mountpoint for ...: ...` | The mountpoint lookup raised while browsing (WARN) or while unmounting a dataset, snapshot, or loop partition (FATAL) | That item's browse/unmount aborted |
| `WARN: ... is not mounted; mount the partition first` | A loop partition has no mountpoint | Mount the partition, then browse |
| `INFO: Skipping ... (canmount=off)` | Gated skip — the ancestor can never be mounted, excluded from the parent-mount plan | That ancestor skipped; target still handled |
| `WARN: Error mounting ...: ...` | `zfs mount` / read-only `mount` returned non-zero | That mount batch aborted |
| `VERB: Mounted ...` | Dataset mounted via `zfs mount` under a dataset lock | Continue |
| `WARN: Error checking mount state for ...: ...` | The mounted/canmount property lookup raised while planning mounts | That snapshot's parent-mount offer/recovery skipped |
| `WARN: Cannot mount ...: snapshots of ZFS volumes cannot be mounted` | The selected snapshot's parent is a zvol | That snapshot's mount aborted |
| `WARN: Cannot mount ...: parent dataset ... is not mounted. Mount the parent first.` | The parent filesystem is unmounted | Mount the parent, then retry |
| `WARN: Cannot mount ...: parent mountpoint ... is missing. A child dataset was mounted before its parent; remount the parent dataset to restore access.` | The parent's mountpoint directory is absent (shadowed namespace) | Remount the parent dataset |
| `WARN: Cannot mount ...: snapshot path ... is not accessible.` | Listing the `.zfs/snapshot` path failed | That snapshot's mount aborted |
| `WARN: Cannot mount ...: snapshot did not automount. Verify the parent dataset is healthy and try again.` | Listing the path did not produce a mounted snapshot | Verify parent health and retry |
| `VERB: Mounted snapshot ...` | Snapshot automount verified | Continue |
| `WARN: Error mounting snapshot ...: ...` | Unexpected exception resolving/mounting the snapshot | Aborted |
| `WARN: Not all parent datasets mounted; selected snapshots that remain blocked will report warnings below.` | After the Mount All dialog, some parent mounts failed | Blocked snapshots warn individually |
| `WARN: Error attaching ... to a loop device` / `Error attaching loop device for ...: ...` / `cannot attach loop device for ...: ...` | Loop attach failed (no device, subprocess error, or lock conflict) | Volume loop-mount aborted |
| `INFO: Attached ... to read-only loop device ...` | The zvol was attached to a loop device | Row children reloaded |
| `WARN: Cannot mount ...: no filesystem detected` | The loop partition has no detectable filesystem | Partition mount aborted |
| `WARN: Error creating mountpoint ...: ...` | Creating the partition mountpoint directory failed | Partition mount aborted |
| `INFO: Mounted ... at ... (read-only)` | Read-only mount of the loop partition succeeded | Continue |
| `WARN: Error remounting ... while recovering ...: ...` | Orphaned-mount recovery could not remount an ancestor | Recovery aborted; mount stays orphaned |
| `INFO: Remounted ... to recover orphaned mount` | An ancestor was mounted before retrying the unmount | Recovery continues |
| `WARN: Could not restore unmounted state of ...: ...` | The rollback unmount of a recovery-mounted ancestor failed | Best-effort; the ancestor stays mounted |
| `WARN: Could not unmount ... after remounting its parents: ...` | The retry unmount after recovery still failed | Recovery aborted |
| `WARN: cannot recover orphaned mount of ...: ...` | Lock conflict during recovery | Recovery aborted |
| `WARN: Could not list descendants of ...: ...` | Listing children for the child-first unmount order failed | Only the dataset itself is unmounted |
| `FATAL: ... looks mounted but its mountpoint is not reachable (orphaned mount) and could not be recovered by remounting its parents. Remount the parent dataset(s) manually and retry; if that fails the mount is detached from the namespace and a reboot is required.` | The unmount failed with "no such pool or dataset" and recovery also failed | Stop; remount parents manually or reboot |
| `FATAL: Dataset ... is busy. Please close any file manager windows and try again.` / `FATAL: Snapshot ... is busy. ...` / `FATAL: Partition ... is busy. ...` | The unmount stderr contained "busy" | Stop at first failure; close the users and retry |
| `FATAL: Dataset ... is busy; unmount aborted` / `FATAL: Snapshot ... is busy; unmount aborted` / `FATAL: Partition ... is busy; unmount aborted` | The pre-unmount busy check found holder processes; a dialog lists them | That item's unmount aborted |
| `FATAL: Error unmounting ...: ...` | Unmount failed with unrecognized stderr | Stop at first failure |
| `FATAL: cannot unmount ...: ...` | Lock conflict for dataset/snapshot unmount | That unmount aborted |
| `VERB: Unmounted ...` | Dataset unmounted (selected dataset or child-first descendant; also emitted after orphaned-mount recovery) | Continue |
| `VERB: Unmounted snapshot ...` | Unmounting the snapshot path succeeded | Continue |
| `INFO: Detached ... from loop device ...` | Volume detach completed | Row children reloaded |
| `FATAL: Error finding loop device for ...: ...` / `FATAL: Error listing partitions on ...: ...` | Loop device/partition lookup raised | Volume detach aborted |
| `FATAL: Error detaching ... from ...` | Loop detach returned failure | The loop device stays attached |

### [disks_page](../commands-and-modules/python-modules.md#disks_pagepy)

GUI Disks tab (disk inventory).

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: Error refreshing disk inventory: ...` | The background inventory cache load raised | Refresh aborted; the page keeps prior data |
| `VERB: Disks refreshed` | Manual Refresh invalidated the cache and reloaded the page | Informational |

### [disk_repository](../commands-and-modules/python-modules.md#disk_repositorypy)

Repository layer for the disk inventory (lsblk parsing and boot-disk hiding).

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: lsblk failed: ...` / `WARN: Failed to parse lsblk JSON: ...` | The lsblk inventory command failed or its output was unparseable | Empty disk list returned |
| `WARN: could not probe for the boot disk: ...` / `boot-disk probe failed` / `could not resolve the boot disk: ...` / `boot-disk resolution failed` / `could not parse boot-disk ... output: ...` / `could not resolve boot disk from ...` / `could not resolve a boot-disk path from ...` | The boot-disk detection probe failed at some stage (findmnt, PKNAME chain, or mountpoint fallback) | Boot disk not hidden; all disks shown |
| `DEBUG: root source ... is not a block-device path` | The findmnt SOURCE is a dataset/subvolume (e.g. ZFS root) — the fallback path is taken | Detection continues via mountpoint |
| `DEBUG: no root-filesystem device found; boot disk not hidden` | The fallback found no device mounted at / | All disks shown |
| `VERB: hiding system boot disk ... (... partitions) from the disk inventory` | Safety decision — the boot disk and its partitions are excluded from the inventory | Boot disk not offered for pool use |

### [disk_actions](../commands-and-modules/python-modules.md#disk_actionspy)

GUI Disks tab SMART actions and the Wipe Labels handler.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: Select a disk to view SMART details` | No disk row selected | Action aborted |
| `WARN: SMART details unavailable for ...` | The details query returned empty or n/a | Dump aborted |
| `INFO: SMART details for ...:` | Header of the smartctl output dump | Informational |
| `WARN: Disk wipe is available only on the storage host` | Wipe Labels invoked on a two-node compute host | Action aborted |
| `WARN: Dataset runner not available` / `WARN: A dataset action is already running` | Shared gate wording (also used by pool-growth handlers) | Action aborted |
| `WARN: Select a disk to wipe` | No disk row selected | Action aborted |
| `WARN: ... is not in the disk inventory; refresh and retry` | The selected row is not in the cached inventory | Action aborted |
| `WARN: ... cannot be wiped: ...` | The selection is not inactive (itself, its parent, or a sibling belongs to an imported pool) | Action aborted |
| `WARN: Could not scan importable pools: ...` | `list_importable_pool_devices` raised; the wipe dialog opens with no importable-pool warning | Informational |
| `INFO: Wipe cancelled for ...` / `WARN: Wipe failed for ... (rc=...)` / `INFO: Wipe complete on ...` | Runner step outcome for the `zfswipe` BashStep | Informational / inspect the step log |

### [disk_surface_test](../commands-and-modules/python-modules.md#disk_surface_testpy)

GUI Disks tab SMART surface tests, with state persisted to disk.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: Could not load surface test state: ...` | The state file is unreadable/malformed | Continue with empty state |
| `WARN: Could not save surface test state: ...` | Persisting the state JSON failed | Continue; state may be stale |
| `WARN: Could not poll surface test on ...: ...` | The per-disk smartctl poll raised | That disk's update skipped this cycle |
| `INFO: Surface test (...) started on ...` | A SMART self-test launched (short/long chosen in dialog) and state recorded | The Disk Inventory cell tracks progress |
| `INFO: Surface test canceled on ...` | The `smartctl -X` abort succeeded; entry marked canceled | Informational |

### [scrub_manager](../commands-and-modules/python-modules.md#scrub_managerpy)

GUI scrub engine: queue/state machine for start/pause/resume/stop, backup-coordinated pause/resume, external-scrub adoption, and systemd timer toggles.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: Could not list pools for scrub status: ...` | Pool listing failed while building all-pool scrub states | Continue with an empty state map |
| `INFO: Skipping scrub action on '...': current state is ..., allowed states are ...` | State-machine gate — the requested transition is invalid for the live state | Action skipped |
| `INFO: Starting scrub on pool '...'` / `Pausing scrub on pool '...'` / `Resuming scrub on pool '...'` / `Stopping scrub on pool '...'` | The transition passed its state gate and the command follows | Continue |
| `INFO: Scrub started on '...'` / `Scrub paused on '...'` / `Scrub resumed on '...'` / `Scrub stopped on '...'` | The corresponding command succeeded | Continue |
| `WARN: cannot start/pause/resume/stop scrub on '...': ...` | Subprocess timeout/OSError during the transition | That transition aborted |
| `WARN: Failed to start/pause/resume/stop scrub on '...'` | The zpool scrub command returned non-zero | Transition aborted; the queue may retry |
| `DEBUG: Pool '...' is not online; skipping scrub pause` / `... scrub resume` | The pool vanished from the live states | That pool skipped |
| `DEBUG: Scrub on '...' is ...; not pausing` | The pool is online but not SCANNING | Pause skipped |
| `INFO: Dry-run: would pause scrub on '...'` / `would resume scrub on '...'` | Dry-run mode — no state change | Continue without pausing/resuming |
| `VERB: Scrub paused on '...'` / `Scrub resumed on '...'` | Backup-coordinated pause/resume confirmed by state poll | Continue |
| `WARN: Scrub on '...' did not pause (state: ...); scan line: ...; raw status: ...` / `WARN: Scrub on '...' did not resume (state: ...); ...` | The state did not reach PAUSED/SCANNING after the command succeeded | Pool not counted as paused/resumed; the backup step proceeds |
| `WARN: Failed to pause scrub on '...'` / `WARN: Failed to resume scrub on '...'` | The pause/resume returned failure in the coordinated path | Pool not counted |
| `INFO: Scrubs paused: ...` / `INFO: Scrubs resumed: ...` | Final summary of pools paused/resumed | Informational |
| `VERB: Scrub on '...' is already running; no resume needed` | Externally resumed or never paused | Cleared from paused buckets |
| `INFO: Scrub on '...' finished while paused; no resume needed` | State FINISHED/NONE while paused | Moved to finished |
| `WARN: Scrub on '...' is in unexpected state ...; leaving it alone` | State not in the expected set | Left as-is on the system |
| `INFO: No paused scrubs required resuming (handled: ...)` | Resume finished with nothing to do | Informational |
| `INFO: Scrub target changed from ... to ...` | The simultaneous-scrub target was reconfigured and persisted | The queue reconciles |
| `INFO: Scrub queue order updated` | The user's scrub priority order was persisted | Informational |
| `INFO: Pools added to scrub queue: ...` / `INFO: Pools removed from scrub queue: ...` | Start/stop enqueued/cleared pools (paused re-queued, finished cleared) | The tick loop starts/stops them |
| `WARN: Giving up on scrub for '...' after ... failed start attempts` | Three consecutive failed start/resume attempts | Pool dropped to given-up for this run; investigate |
| `VERB: External scrub detected on '...'` | The queue observed a scrub it did not start (once per episode) | Pool adopted into the active bucket |
| `INFO: Scrub finished on '...'` / `Scrub canceled on '...'` / `Scrub completed on '...'` | Active pool reached FINISHED/CANCELED, or state NONE after the grace period | Moved to finished bucket |
| `INFO: Paused scrub finished on '...'` / `Paused scrub canceled on '...'` | A paused pool shows FINISHED/CANCELED | Cleared from paused; added to finished |
| `INFO: New scrub detected on '...'` | A finished-bucket pool is SCANNING again | Moved back to active |
| `WARN: systemctl ... ...@....timer failed: ...` / `error: ...` | Enabling/disabling the systemd scrub timer failed (non-zero rc or timeout/OSError) | Failure returned; check systemctl |
| `INFO: ...@....timer ...d` | The systemd scrub timer enable/disable succeeded | Informational |

### [zfsinfo](../commands-and-modules/python-modules.md#zfsinfopy)

Standalone CLI report of pools/datasets/snapshots (table formatting not listed).

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: Filtering by pool: ...` | The CLI argument restricts the report to one pool | Informational |
| `INFO: No pools found.` / `No datasets found.` | The corresponding list came back empty | That section ends early |
| `INFO: Pools: ... total (... online, ... degraded/offline)` | Final summary — pool counts by health | Informational |
| `INFO: Datasets: ...` / `INFO: Snapshots: ...` | Final summary counts | Informational |

### [zfs_capabilities](../commands-and-modules/python-modules.md#zfs_capabilitiespy)

OpenZFS feature gating for the GUI (versions parsed once, cached).

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: OpenZFS userland ... differs from kernel module ...` | Userland and kmod versions mismatch; feature gating uses the kmod version | Consider reconciling packages |
| `WARN: Unable to determine OpenZFS version` | `zfs version` output was empty | All versioned features evaluate unsupported |
| `WARN: Unable to parse OpenZFS userland version` | No userland line matched the version pattern | Userland treated as 0.0.0 |
| `WARN: Unable to parse OpenZFS kernel-module version; using userland version for feature checks` | The kmod line is missing from `zfs version` | Userland used for gating |

### [migration](../commands-and-modules/python-modules.md#migrationpy)

One-time state migration to the FHS layout at GUI startup (legacy paths get rollback symlinks).

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: Could not migrate ... to ...: ...` | Moving a legacy state file failed | That item skipped; the legacy path stays |
| `INFO: Migrated ... -> ... (legacy symlink left for rollback compatibility)` | The state file moved with a legacy symlink | Informational |
| `WARN: Migrated ... -> ... but could not create legacy symlink: ...` | The move succeeded but the symlink failed — older versions cannot find the data | Link manually if needed |
| `INFO: Migrated ... -> ...` | Move succeeded with no symlink requested (system config files) | Informational |
| `WARN: Both ... and ... exist; legacy path backed up to .... Using ....` | Conflict resolution — the legacy path was preserved as `.bak` and the new path wins | The `.bak` can be inspected |
| `WARN: Both ... and ... exist but could not back up legacy path: ...` | Conflict with a failed backup move | Legacy path left in place |
| `INFO: ZFS Utilities state migration complete (...)` | The sentinel was written; migration will not run again | Informational |
| `WARN: Could not write migration sentinel ...: ...` | The sentinel write failed | Migration re-runs next start (idempotent) |

## Installation, Deployment, and Removal

`check-prerequisites` and the two installers are echo-based (no `log_msg`): their output goes to stdout, and their fatal errors use `die` (rendered as `FATAL:`). The remaining scripts log normally.

### [check-prerequisites](../commands-and-modules/commands.md#check-prerequisites)

Output uses `✓`/`⚠`/`✗` markers for pass/warn/fail.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `✗: ... — ... (install: ...)` | A required prerequisite failed its check (command/package/module/service missing); the parenthetical names the package to install | Install the listed packages; the script exits 1 at the end if any failure was recorded |
| `✗: mkdocs — mkdocs 2.x is incompatible with this project; pin to mkdocs<2` | The installed mkdocs major version is 2 or newer | Install `mkdocs<2` |
| `Note: on Debian, zfsutils-linux is in the contrib archive — ...` | The ZFS tools are missing AND apt has no installation candidate for `zfsutils-linux` (the probe runs only in that case) | Enable the `contrib` archive in `/etc/apt/sources.list` (or the equivalent `.sources` file), then rerun |
| `✗: zfs-kernel-module — kernel module not built (zfs-dkms needs the matching headers)` | The `modinfo zfs` probe found no built module (checked whenever kmod is available) | Install the matching headers so `zfs-dkms` builds (`apt-get install linux-headers-$(uname -r)`); installing the headers triggers the dkms build |
| `⚠: pveversion not found — ...` | Proxmox VE is optional for this host class (required only on a two-node compute host) | Informational; installation can continue |
| `⚠: mkdocs not installed — the installer's documentation-server step installs it (pip 'mkdocs<2')` | MkDocs is absent; the installer pip-installs it after the prerequisite gate | Informational; installation can continue |
| `⚠: mkdocs-material not installed — the installer's documentation-server step installs it (pip)` | The Material theme is absent; the installer pip-installs it after the prerequisite gate | Informational; installation can continue |
| `⚠: DISPLAY not set — GUI requires an X11 or Wayland session` | No graphical session | Informational; the GUI will not run until started from a session |
| `✗: ... required prerequisite(s) missing. Install them before proceeding.` | Final tally with at least one failure | Install the prerequisites and rerun |
| `⚠: ... optional item(s) missing — installation can continue but some features may be unavailable.` | Final tally with warnings only | Informational |
| `✓: All required prerequisites are present.` | All required checks passed | Informational |

### [cleanup-zfsutilities-legacy](../commands-and-modules/commands.md#cleanup-zfsutilities-legacy)

Removes legacy symlinks and deployed versions; every removal mode asks for confirmation first.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: ... is not a symlink; leaving it in place` | Safety rule: legacy paths are removed only when they are symlinks | Path skipped |
| `WARN: ... is not empty; leaving it in place` | The legacy directory still has contents | Path skipped; migrate the files first |
| `WARN: Refusing to remove the currently active version: ...` | The requested version is the active deployment | Version skipped |
| `WARN: Version not found: ...` | No such deployed version | Version skipped |
| `WARN: uninstall-version helper not found; cannot remove ...` / `WARN: uninstall-version failed for ...` | The per-version removal helper is missing or failed | Script aborts; check the deployment |
| `INFO: === Cleaning up legacy symlinks ===` / `INFO: === Removing specified versions ===` / `INFO: === Removing versions older than ... ===` / `INFO: === Removing all deployed versions except the active one ===` | Selected mode marker (with the affected items listed before the confirmation prompt) | Confirm with y, or decline to cancel |
| `INFO: Cancelled.` | The operator declined a confirmation | Exit 0; nothing removed |
| `INFO: === DRY RUN — no changes will be made ===` | `--dry-run` active | Actions are printed only |
| `INFO:   Legacy symlinks removed: ... / INFO:   Deployed versions removed: ... / INFO:   Active version preserved: ...` | Final outcome counters | Informational |
| `FATAL: --remove-versions requires at least one version` / `FATAL: --remove-older-than requires a version argument` / `FATAL: Unknown option: ...` | Usage errors | Script aborts |

### [deploy-version](../commands-and-modules/commands.md#deploy-version)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN:   Missing: ...` | A critical script is absent from the deployed `bin/` after the sync (the deployment was probably run from a deployed copy) | Rerun `deploy-version` from the repository root |
| `FATAL: mkdocs is not installed. Cannot build documentation.` | The docs build step cannot run | Install `mkdocs<2` and rerun |
| `FATAL: Documentation build failed.` | `mkdocs build` in the version directory failed | See the mkdocs error output |
| `INFO:   ✓ ... files synced (run switch-version on ... to activate)` | The version directory reached the host but is not active yet | Run `switch-version <version>` on that host |
| `INFO: To activate:   sudo switch-version ...` | Final summary includes the activation step | Run the suggested command |
| `FATAL: deploy-version must be run from the repository root. Wrong: ... Right: ...` | Running from a deployed path would rsync a deployment onto itself | `cd` to the repository root as suggested |
| `FATAL: Unknown deployment group: '...'. Run with --help to list groups.` | The group name matches no deployment group | See the help text |

### [install-single-node](../commands-and-modules/commands.md#install-single-node)

Echo-based installer.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARNING: ZFS root filesystem detected` | The root filesystem is on ZFS (unsupported); a proceed-at-your-own-risk prompt follows | Enter continues, Ctrl-C aborts |
| `INFO: Existing single-node configuration found.` | A reconfiguration prompt follows | y regenerates the config, N/Enter keeps it |
| `⚠ Existing TWO-NODE configuration found.` | Installing single-node mode will rewrite the node config and skip iSCSI steps (consequences listed) | y switches modes, anything else aborts cleanly |
| `⚠ Legacy ... found.` | A legacy config exists; the new config is created alongside it | Informational |
| `✓ Configuration saved to ...` | The node config was written (an edit-now prompt is offered first) | Informational |
| `Installation Complete` summary | Deploy, activation, and retention profiles all succeeded | Follow the listed next steps |

### [install-two-node](../commands-and-modules/commands.md#install-two-node)

Echo-based installer; must run on the storage host.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARNING: ZFS root filesystem detected` | The root filesystem is on ZFS (unsupported) | Enter continues, Ctrl-C aborts |
| `INFO: Existing two-node configuration found.` | A reconfiguration prompt follows | y regenerates, N/Enter keeps and proceeds |
| `INFO: Existing SINGLE-NODE configuration found.` / `Upgrading to two-node mode.` | Single-node → two-node upgrade (no skip offered) | Answer the additional prompts |
| `FATAL: Compute host name is required` | Empty input at the compute-host prompt | Rerun and provide the host name |
| `⚠ No pools configured. You can add them to ... later.` | No pools were entered | Edit the node config later |
| `⚠ setup-iscsi-targets not found — you must create iSCSI targets manually` | The helper is absent from the repository | Create the targets with targetcli manually |
| `FATAL: Run this script on the storage host (...), not ...` | Hostname check failed | Rerun on the storage host |
| `FATAL: Cannot SSH from ... to root@...` | Passwordless SSH between the nodes failed (a fix line suggests `ssh-copy-id`) | Set up SSH keys as suggested and rerun |
| `⚠ Could not initialize retention profiles on ...` | The remote retention-profile init failed | Initialize the profiles on the compute host |
| `INFO: Removing obsolete automatic LUKS-key systemd artifacts...` | Old zfs-keys systemd units from earlier versions exist and are removed | Informational |
| `⚠ ... uses old bash array format.` / `Replace with: ...` | The encrypted-LUNs conf predates the current format | Rewrite the file as suggested |
| `INFO: ✓ Patched ... (86400 s rate limit)` | The Proxmox iSCSI rescan-rate patch was applied to ISCSIPlugin.pm | Informational |
| `⚠ Patch may already be applied or file differs from expected` | The patch verification failed | Check ISCSIPlugin.pm manually |
| `⚠ Could not restart pvestatd on ...` | The remote service restart failed | Restart pvestatd manually |
| `Installation Complete` summary | All steps succeeded on both hosts | Follow the post-install steps (e.g. `safe-iscsi-save`) |

### [switch-version](../commands-and-modules/commands.md#switch-version)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN:   desktop-launcher-lib.sh not found; desktop shortcuts will not be managed.` | The launcher library is absent; shortcuts are skipped | Informational; install the lib directory |
| `WARN:   sudoers validation failed — ... not updated` | `visudo -c` rejected the generated sudoers fragment | The sudoers file is left unchanged; inspect it manually |
| `INFO:   Backed up existing /root/bashinit to /root/bashinit.bak` | A real file occupied the bashinit link path and was moved aside | Informational |
| `INFO:   Unwiring previous version ...` | The prior version's wiring is removed before the switch | Informational |
| `WARN:   previous version uninstall returned non-zero; continuing` / `WARN:   previous version switch-version not found at ...` | The prior version's uninstall failed or is missing | The switch proceeds; old wiring may remain |
| `INFO:   Stopped documentation server (will restart on next access)` | A doc server on port 8000 was killed for the switch | Informational |
| `INFO:   Active: ... / Previous: ... / New invocations will use ... immediately. / Already-running scripts are unaffected.` | Final outcome of the switch | Informational |
| `FATAL: No previous version recorded` | `previous` requested but no previous link exists | Switch to an explicit version |
| `FATAL: Version not found: ...` | No such deployed version | Check `switch-version --list` |

### [uninstall-version](../commands-and-modules/commands.md#uninstall-version)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: Cannot uninstall the currently active version (...)` | Safety refusal: the target is the active deployment | Switch to another version first |
| `Remove ...? (y/N):` | Final confirmation (skipped by `-y`/`--yes`) | Only a bare y proceeds; anything else aborts cleanly |
| `INFO: Aborted.` | The confirmation was declined | Exit 0; nothing removed |
| `INFO: Removed: ...` | The version directory was removed | Informational |

### [uninstall-some-versions](../commands-and-modules/commands.md#uninstall-some-versions)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: Version list not found: ...` | The version-list file is missing | Create the list file |
| `FATAL: uninstall-version not found: ...` | The helper script could not be located | Check the installation |

Each listed version is removed via `uninstall-version -y`; per-version messages come from that script.

### [uninstall-zfsutilities](../commands-and-modules/commands.md#uninstall-zfsutilities)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: bashinit not found` | The logging runtime is gone (partial uninstall) | Restore the installation or finish manually |
| `Choose 1 (software only) or 2 (clean up everything), or c to cancel [1/2/c]:` | Interactive mode selection (state detection block precedes it) | 1 keeps configs/logs; 2 purges everything; c cancels |
| `INFO: Cancelled.` | The mode dialog or the final confirmation was declined | Exit 0; nothing removed |
| `Also run the uninstall on the peer node (...)? [y/N]` | Two-node mode detected | y uninstalls the peer too |
| `INFO: The following will be removed:` / `INFO: The following will be preserved:` | The destruction scope for the chosen mode | Review before confirming |
| `INFO: ZFS pools, datasets, snapshots, and iSCSI targets will NOT be touched.` | Safety assurance: the uninstall is software-level only | Informational |
| `INFO: Note: The Proxmox iSCSI rescan-rate patch on ... will NOT be reversed automatically.` | The installer's ISCSIPlugin.pm patch persists (a sed command to reverse it is printed) | Run the printed command to reverse the patch |
| `Proceed with uninstall? [y/N]` | Final confirmation | y uninstalls; N/Enter cancels |
| `WARN:   switch-version --uninstall returned non-zero; continuing` | Unwiring the active version failed | Removal continues; some wiring may remain |
| `INFO:   Peer has no deployed uninstall script; running local copy via ssh...` | The peer lacks the script; the local copy is piped over SSH | Informational |
| `INFO: === DRY RUN — no changes will be made ===` / `INFO: This was a dry run; no changes were made.` | `--dry-run` mode | Actions are printed only |
| `INFO: Configuration, logs, and history were preserved. / Run with --purge to remove them as well.` | Software-only mode outcome | Rerun with `--purge` to remove them |

### [startdocserver](../commands-and-modules/commands.md#startdocserver)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: Could not find docs directory.` | The docs tree is not where expected | Run from the repository or an installed layout |
| `WARN: Server did not stop gracefully, forcing...` | The old server survived SIGTERM | SIGKILL fallback, then restart |
| `WARN: Static site build failed (see ...); the live server is unaffected.` | The `mkdocs build` refresh failed (log path printed) | The live server still starts; check the build log |
| `FATAL: mkdocs is not installed. The documentation server requires MkDocs.` | mkdocs is missing | Install `mkdocs<2` |
| `INFO: Documentation server already running at ...` | Idempotent no-op: the server answers and serves the right directory | Informational |
| `WARN: Documentation server running from wrong directory; restarting...` | The running server serves a different docs directory | It is stopped and restarted |
| `WARN: Server responding but PID not found; attempting restart...` | HTTP answers but no PID was found | Restart attempted |
| `INFO: Documentation server started in background (pid ...)` | `mkdocs serve` launched on port 8000 (log path printed) | Informational |

### [git-release](../commands-and-modules/commands.md#git-release)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: Not a git repository` | No `.git` at the root | Run from the repository |
| `INFO: Changes detected:` | Uncommitted changes existed before the VERSION bump (`git status --short` printed) | Everything is included in the release commit |
| `INFO: Bumping VERSION to ...` | The VERSION file was written | Informational |
| `INFO: To push:   git push && git push --tags` | Final summary: commit and tag were created; pushing is left to the operator | Push when ready |

### [installer_retention](../commands-and-modules/python-modules.md#installer_retentionpy)

Python helper the installers invoke to seed retention policies into the JSON config (`--new-install` clears pool-specific policies; used by [retention_page](#retention_page) on first GUI start).

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: New install — cleared pool-specific retention policies: ...` | `--new-install` removed all non-default policies | Config saved |
| `INFO: Added default retention policy` | The config had no `retention/default`; one was created | Config saved |
| `INFO: Retention profiles already initialized` | No changes needed | Save skipped |
| `WARN: Could not initialize retention profiles: ...` | OSError loading/saving the config | Exception re-raised; the installer exits 1 |

## Developer and Diagnostics Tooling

### [run-tests](../commands-and-modules/commands.md#run-tests)

Emits no log messages; test output comes from the suites themselves. A missing unified test runner prints a bare stderr note and exits 2.

### [bashdebug](../commands-and-modules/modules.md#bashdebug)

Emits no log messages; its ERR/DEBUG traps print bare echo markers (`--- ERROR DETECTED ---`, command/RC details) for interactive debugging.

### [bashfatal](../commands-and-modules/modules.md#bashfatal)

Emits no log messages; it is the exit mechanism invoked after `FATAL:` messages.

### [bashreturn](../commands-and-modules/modules.md#bashreturn)

Emits no log messages; it returns (sourced) or exits (direct) with the given code.

### [bashsetx](../commands-and-modules/modules.md#bashsetx)

Emits no log messages; it enables `set -x` tracing.

### [rootcheck](../commands-and-modules/modules.md#rootcheck)

Emits no log messages. `rootcheck()` prints a bare "Please run as root." and returns 1 when not root.

### [unroot](../commands-and-modules/commands.md#unroot)

Emits no log messages; `unroot()` re-runs a command as the non-root user.

### [watchall](../commands-and-modules/commands.md#watchall)

Emits no log messages. It is a curses `watch(1)` reimplementation (bare error prints only).

### [watchit](../commands-and-modules/commands.md#watchit)

Emits no log messages; it wraps `watchall` around `zpool list`/`zfs list`.

### [bashinit](../commands-and-modules/modules.md#bashinit)

The shared runtime sourced by every bash script; its helpers can emit messages of their own.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: Could not find sibling script: ...` | A helper script was not found in any candidate directory | Check the installation; sourcing escalates to the FATAL below |
| `FATAL: Could not locate ...` | A required library/helper could not be resolved for sourcing | Script exits 8 (or returns 8 when sourced); reinstall the scripts directory |
| `FATAL: ...` | The `die()` wrapper: the text is the calling script's fatal error | The script exits 1 |
| `WARN: ...` | The `warn()` wrapper: the text is the calling script's warning | Informational; execution continues |

## GUI (Python)

Application shell, logging plumbing, and the schedule/profile cluster. The functional GUI modules (backup/offsite/restore/retention pages, pools/disks/datasets pages, enrollment and locking) are documented in their functional groups above; `log_msg` itself is defined in [logging_config](#logging_config) and re-exported by [backup_config](#backup_config).

Python `log_msg` emission differs from the bash scripts in one way: every message always reaches the GUI log sink (or colorized stderr); it is appended to a session log file only while a runner has one open. Messages embedded in bash scripts generated by Python (command_builders, restore_runner, offsite_runner) are inherited by the runner's environment and land in the GUI log and that run's session log. Level filtering happens only in the GUI log viewers.

### [zfsutilities_gui](../commands-and-modules/python-modules.md#zfsutilities_guipy)

The GUI application shell: startup config checks, close confirmation, docs anchors, and action dispatch.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: No pools registered — add pools in the Pools tab` / `No backup steps configured — configure in the Backup tab` / `No offsite steps configured — configure in the Offsite tab` / `Checkagainst table is empty — configure in the Checkagainst tab` | Startup config checks found an empty area | Configure the named tab |
| `WARN: Could not collect running tasks: ...` | Exception while building the close-confirmation task list | Close dialog proceeds with an empty list |
| `INFO: Documentation editor set to: ...` | The editor-choice dialog was confirmed and the command persisted | Future edit links use this editor |
| `WARN: No documentation anchor for page '...'` | Help-with-page has no docs anchor mapping for the current page | Docs viewer not opened |
| `VERB: Action: ...` | An action button was clicked but no handler exists for that page+label (dispatch miss) | Nothing executed |
| `VERB: > ...` | The user sent text via the stdin entry; it is echoed under the runner the input-hold ladder routed it to | Answer forwarded to that runner's subprocess |
| `WARN: No outstanding input message numbered ...` | The reply named an action number that is not currently held | Input rejected; check the held-message strip for live numbers |
| `WARN: Input ignored - nothing is asking; reply to a held message as 'N response' (e.g. '3 y')` | Bare input arrived while no question is held and no single job is live (or several are) | Input rejected with a hint; input is never routed by a fixed priority order |
| `INFO: [Input N][task] ...` | A job's question was held as numbered input request N | Answer it in the Input entry as `N response` |
| `VERB: [Input N] closed` | The held question N was answered and released | Informational |
| `VERB: [Input N] withdrawn (task ended)` | The task that held question N exited or was cancelled, releasing the hold | Informational |
| `INFO: Memory stats refreshed` | The menu **Refresh** ran on the Performance page | Informational; charts/values already updated |

### [main](../commands-and-modules/python-modules.md#mainpy)

Single-instance startup and PID-file handling.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: could not write PID file ...: ...` | OSError creating/writing the single-instance PID file | Startup continues; stale-instance detection degraded |
| `INFO: replacing stale GUI instance ... (...)` | The PID file names a dead process, with reason | PID file removed; this instance takes over |
| `INFO: replacing existing GUI instance ...` | The PID file names a live prior GUI that will be replaced | Old instance terminated; startup continues |
| `INFO: terminating existing GUI instance ...` | Another process matching the GUI signature still owns the D-Bus name | That PID is terminated, then registration proceeds |
| `INFO: another GUI instance is still registered; retrying after cleanup` | Registration reported a remote owner after the first cleanup pass | One retry with fresh PIDs/app instance |
| `WARN: another GUI instance is still registered; startup aborted` | The retry also found a remote owner | GUI exits without running |

### [gui_helpers](../commands-and-modules/python-modules.md#gui_helperspy)

Shared GUI widgets and helpers: tree-row loading, destroy-busy diagnosis, width reset, and the startup banner.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: Could not load loop partitions for ...: ...` | Zvol loop-device partition listing failed | The zvol shows without partitions |
| `WARN: Could not load snapshots for ...: ...` / `Could not load children for ...: ...` | Snapshot/child listing failed for the row | Those children stay unloaded |
| `WARN: ZFS reported: ...` | Raw ZFS stderr from a failed destroy, replayed for diagnosis | Diagnosis output follows |
| `WARN: Diagnosing why ... cannot be destroyed...` | Header of the busy-dataset diagnosis after a destroy failure | Diagnostic output follows |
| `WARN:   → ...` | One detected specific cause why the target is busy | Resolve per the paired action line |
| `WARN:     ...` | Remediation action paired with a cause | Suggested operator action |
| `WARN:   → No specific cause identified. Common remaining reasons:` | The diagnosis found no concrete hold/clone/origin reason | Generic checklist follows |
| `WARN:       • The dataset is referenced by a child snapshot that is busy.` / `• A process has the dataset open through a different path.` / `• The pool is undergoing a scrub or resilver.` | Checklist items when no specific cause was found | Investigate; wait for scrub/resilver to finish |
| `WARN:     Try: fuser -m <mountpoint>  or  lsof +D <mountpoint>` | Suggested commands to find the holder | Run manually |
| `VERB: Minimize width cancelled` | Cancel was answered to the reset-widths dialog | Width reset skipped |
| `INFO: Reset ... column width(s) to minimum and minimized window width` | Confirmed; columns reset and saved widths cleared | Window resized; config saved |
| `INFO: Welcome to ZFS Utilities` | Banner emitted right after the GUI log sink is installed at startup | GUI-only startup event; no session log yet |
| `INFO: Select a category from the sidebar to get started.` | Startup hint following the banner | Informational |
| `VERB: Copied: ...` | Row-activated clipboard copy succeeded | Text on the clipboard |

### [dashboard_page](../commands-and-modules/python-modules.md#dashboard_pagepy)

Dashboard tab: status overview, peer-node version check, and task cancellation.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: Could not read disk wear data: ...` | The disk inventory call failed during wear refresh | Continue with cached inventory |
| `WARN: Could not load log index: ...` / `Could not save log index: ...` | The log index load/save raised while enriching recent operations | Continue without index data / rewritten next time |
| `WARN: Could not scan log file ...: ...` | A per-entry index update failed | That entry falls back to result-based display |
| `WARN: Could not determine ZFSutilities version on peer node ...` | The SSH version probe of the two-node peer returned unknown | Version parity unverified |
| `WARN: Peer node ... is running ZFSutilities ...; this node is running ...` | Two-node version mismatch detected at startup | Align versions |
| `INFO: Peer node ... is running the same ZFSutilities version (...)` | Version parity confirmed | Informational |
| `WARN: Dashboard data gathering failed: ...` | The background gather thread raised | UI not updated this cycle |
| `INFO: Running repair-iscsi-luns...` | "Fix this" clicked on an iSCSI warning row | Repair script runs with a timeout, then refresh |
| `INFO: repair-iscsi-luns completed successfully` / `WARN: repair-iscsi-luns exited ...` / `WARN: repair-iscsi-luns failed: ...` | The repair script's rc=0 / non-zero rc / launch failure outcome | Refresh follows |
| `INFO: Removed ... stale lock file(s)` | The Fix Locks cleanup ran; count removed | Dashboard refreshed |
| `INFO: Cancelled ...` | A GUI runner was cancelled via the task list | The runner's own cancel messages follow |
| `WARN: Runner ... is not running` | Cancel requested for an idle runner | No-op |
| `INFO: Stopped scrub on '...'` | A scrub stop was issued for the pool | Scrub stop requested |
| `INFO: ZFS-native operations cannot be cancelled from the GUI` | Cancel requested for a `zfsop:` task (resilver/expand/remove) | The operation continues in ZFS |
| `INFO: To cancel profile '...', use Cancel Selected Tasks and then clean up its process if it does not stop` | Cancel requested for a profile task not started by this GUI | Guidance only |
| `INFO: Sent SIGTERM to scheduled task PID ...` | Cancel of a scheduled task delivered SIGTERM | Process signaled |
| `WARN: Failed to cancel scheduled task ...: ...` | Signaling the PID failed | The task keeps running |
| `WARN: Unknown task key: ...` | The task key prefix is not recognized by the canceller | No-op |
| `WARN: No tasks selected` | Cancel Selected Tasks pressed with empty selection | Action aborted |
| `WARN: No task or recent operation selected` / `WARN: No log file recorded for the selected operation` / `WARN: Log entry not found: ...` | View Log gates: nothing selected, no log path recorded, or the file vanished | Navigation aborted |

### [docs_viewer](../commands-and-modules/python-modules.md#docs_viewerpy)

Embedded documentation viewer (WebKit with a plain-text fallback).

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: Could not read system config ...: ...` | Unprivileged read of the system JSON config failed | Continue with an empty dict |
| `WARN: Could not load docs viewer user state from ...: ...` | The per-user state JSON is unreadable/corrupt | Continue with defaults |
| `WARN: Could not save docs viewer user state to ...: ...` | Persisting viewer state failed | State lost |
| `WARN: Failed to load docs viewer toolbar CSS: ...` | The toolbar stylesheet failed to parse | Toolbar styling skipped |
| `WARN: Documentation viewer blocked ... link: ...` | Security gate — the link's scheme is outside the allow-list | Navigation denied |
| `WARN: Documentation viewer failed to load ...: ...` | WebKit load-failed event for a docs URI | Click Home to reset |
| `INFO: Launched editor for ...: ...` | An `openmd://` edit link spawned the configured editor (privileges dropped when root) | Editor opens |
| `WARN: Failed to launch editor: ...` | Spawning the editor failed | Status shows the failure |
| `WARN: Documentation viewer fallback: ...` | WebKit or docs unavailable | Plain-text fallback window shown |

### [logs_page](../commands-and-modules/python-modules.md#logs_pagepy)

Logs tab: session-log viewer, live tail, deletion, and retention setting.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: Could not tail log file: ...` | The incremental live-tail read failed | Tail timer stays alive; retries next tick |
| `WARN: Log viewer buffer truncated to prevent excessive memory use` | Safety cap — the live tail buffer exceeded its maximum; the older half was dropped | Tailing continues |
| `INFO: Copied log path to clipboard: ...` | Context-menu copy of the log path | Path on the clipboard |
| `WARN: Could not seek log file: ...` | Tail-only mode seek for a huge file failed | Viewer load aborted |
| `WARN: Could not read log file: ...` | A chunked "Show More" read failed | Chunk load aborted |
| `WARN: No log selected` | Delete Selected with empty selection | Delete aborted |
| `INFO: Deleted log: ...` | A per-file delete succeeded after the Yes/No confirmation | List resynced |
| `WARN: Could not delete log '...': ...` | Removing one file failed | Remaining files continue |
| `WARN: Could not compute success rate: ...` | History load/statistics raised | Label shows "Success rate: unavailable" |
| `WARN: ...` (retention spin change) | The retention-days value failed validation | Retention days not persisted |

### [session_log](../commands-and-modules/python-modules.md#session_logpy)

Session-log writer used by the runners (per-run log files with `# END:` trailers; size-capped).

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: Could not update log index: ...` | Persisting the final status after the `# END:` trailer failed | The Logs tab rescans instead |
| `WARN: Session log exceeded size cap and was truncated` | The size-cap safety fired while a runner is active | Run continues; index entry removed so the Logs tab rescans |
| `WARN: Could not reset log index after truncation: ...` | Removing the stale index entry failed | Index may be stale until the next rescan |

### [log_index](../commands-and-modules/python-modules.md#log_indexpy)

Persistent index of session logs (highest level, status) used by the Logs and Dashboard tabs.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: Could not load log index: ...` | Reading the index JSON/lock failed | Continue with an empty index (cold rescan) |
| `WARN: Could not save log index: ...` | The atomic write (temp file + replace) failed | Temp file unlinked; index not persisted |

### [logging_config](../commands-and-modules/python-modules.md#logging_configpy)

Defines `log_msg` and the GUI log sink/level plumbing used by every Python module; emits no messages of its own. Session-log truncation helpers live here (their messages are listed under [session_log](#session_log)).

### [backup_config](../commands-and-modules/python-modules.md#backup_configpy)

Re-exports `log_msg` (with the message-level set and sink accessors) from [logging_config](#logging_config); emits no messages of its own.

### [config_core](../commands-and-modules/python-modules.md#config_corepy)

JSON config load/save with versioning, plus session-log retention pruning.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: Config version ... is newer than software expects (...). Some features may not work correctly.` | The config was written by a newer build (downgrade detected) | Load proceeds with the newer config as-is |
| `VERB: Pruned old log: ...` | A session log older than the retention days was removed | Pruning continues |
| `INFO: Pruned ... old log file(s)` | Final summary of the prune pass | Count reported to the caller |

### [feature_config](../commands-and-modules/python-modules.md#feature_configpy)

Workload-profile seeding and scrub-state persistence.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: Workload profile ... is built in and cannot be deleted` | Delete gate — the name is a seeded built-in profile | Delete refused |
| `WARN: Could not load scrub state: ...` | The scrub-state JSON is corrupt/unreadable | Continue with defaults |
| `WARN: Could not save scrub state: ...` | OSError persisting the scrub queue state | State in memory only |

### [action_dispatch](../commands-and-modules/python-modules.md#action_dispatchpy)

Routes the GUI's action buttons to page handlers; emits one refresh-completion marker.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `VERB: Datasets refreshed` | The Datasets-page Refresh handler completed | Informational |

### [profile_runner](../commands-and-modules/python-modules.md#profile_runnerpy)

Headless runner for scheduled profiles (cron): loads a profile JSON, builds its steps (backup, offsite, restore, retention, or scrub), and runs them — the same runs the tabs launch interactively are logged here when started from the Schedule tab.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: Profile '...' is already running; waiting for it to finish...` | The profile advisory lock is busy; the runner waits up to the timeout | Wait; a waiting-file is written for the Dashboard |
| `WARN: Pre-step callback failed: ...` / `WARN: Post-step callback failed: ...` | The scrub-pause/resume callback raised | The step still runs |
| `WARN: Step exited with rc=...` | A step returned non-zero | Fatal steps abort the run; non-fatal continue |
| `FATAL: Aborting run because step failed` | A fatal step failed; the remaining steps are skipped | The run aborts with the step's rc |
| `WARN: ... failed: ...` | Rsync failure diagnosis appended to the step | Informational; run continues per fatality |
| `WARN: Error running step: ...` | Spawning the step raised | Step counted as rc=1 |
| `FATAL: Operation aborted due to lock conflict in headless mode.` | Step rc=9 — the bash side hit the headless dataset-lock wait limit | The whole run aborts immediately |
| `VERB: Could not list profiles for scope validation: ...` | Profile listing failed; scope checks skipped | Run continues without scope warnings |
| `WARN: ...` (scope validation) | A profile-scope warning naming this profile (source/destination overlap across profiles) | Informational; run continues |
| `INFO: Dry run mode enabled — no changes will be made` | The profile is flagged dry-run | Continue in no-change mode |
| `INFO: Backup snapshot: ...` / `INFO: Offsite snapshot: ...` | The snapshot name generated for this run | Informational |
| `INFO: Dry-run: Would run pre-backup command` / `Dry-run: Would run post-backup command` / `Dry-run: Would rsync ... -> ...` | Dry-run variants of the pre/post-backup scripts and rsync steps | Step skipped |
| `INFO: Pull steps disabled by user; skipping` | The pull-steps config is off | All rsync pull steps skipped |
| `WARN: Skipping ... -> ...: ... is not mounted` / `... is not accessible` | Safety gate — a mount source for a pull or keys step is unusable | That step skipped |
| `WARN: Skipping ZFS keys ... -> ...: ... is not mounted` / `... is not accessible` | Keys-path mount/accessibility gate failed | Keys backup skipped |
| `WARN: Skipping ZFS keys backup — destination is not encrypted. Set zfs_keys_dest to an encrypted dataset.` | Safety gate — keys would land on an unencrypted dataset | Keys backup skipped; set an encrypted destination |
| `VERB: Prune step restricted to the ... send/receive step(s)' source and destination datasets (derived at prune time).` | Prune scope narrowed to the active send/receive datasets | Informational |
| `INFO: No active send/receive steps; skipping prune step (no new snapshots to prune).` | Retention-after-backup requested but no send/receive steps are active | Prune skipped |
| `FATAL: No active steps to run` | The profile produced zero executable steps | Profile aborts with rc=1 |
| `INFO: Dry-run: Skipping snapfile cleanup (preserved for real run)` | Dry-run keeps the snapfile for the real run | Cleanup skipped |
| `INFO: Removed snapshot file` | The snapfile was removed after a successful (non-dry-run) run | Informational |
| `WARN: Post-backup command exited with rc=...` | The post-backup script failed (runs even after fatal errors) | Informational; rc recorded |
| `FATAL: No offsite pool online.` | No offsite-candidate pool is online | Offsite profile aborts with rc=1 |
| `INFO: Offsite pool: ...` | The target pool detected for `<offsite>` substitution | Informational |
| `FATAL: Source and destination must be specified` | Restore profile missing source/destination | Aborts with rc=1 |
| `FATAL: Aborting restore because step failed` | The restore step returned non-zero | The run aborts with the step's rc |
| `FATAL: No pools selected for pruning` | Retention profile has an empty prune-pools list | Aborts with rc=1 |
| `WARN: <offsite> selected but no offsite pool is online` | `<offsite>` expanded to nothing | Continue with the remaining pools |
| `FATAL: No pools selected for pruning after resolving <offsite>` | The expansion left no pools | Aborts with rc=1 |
| `FATAL: Prune of ... failed (rc=...)` | A retention prune step failed for that pool | That pool's prune aborted; the remaining pools still run |
| `FATAL: No pools specified for scrub profile` | The scrub profile's pool list is empty | Aborts with rc=1 |
| `INFO: Scrub profile started on ... pool(s), target=...` | The scrub profile begins with the given concurrency | Informational |
| `INFO: Scrub queue — active=... pending=... paused=... finished=...` | Queue summary, emitted only when it changes | Informational while polling |
| `WARN: Scrub profile timed out with paused pools` | Idle with only paused pools remaining (about ten minutes) | Polling loop aborts |
| `FATAL: Scrub profile gave up on: ...` | The queue gave up on pools after repeated start failures | Profile aborts with rc=1 |
| `INFO: Scrub profile complete` | All queued scrubs finished | Success, rc=0 |
| `FATAL: Profile not found: ...` | The profile JSON could not be loaded | Session trailer rc=1; exit 1 |
| `WARN: Profile '...' is already running and did not finish within ... seconds; skipping duplicate invocation` | The lock wait timed out (timeout > 0) | Skipped; exit 0 so cron does not retry-fail |
| `INFO: Profile '...' is already running; skipping duplicate invocation` | Zero-timeout lock contention | Skipped; exit 0 |
| `INFO: Running profile: ... (type=...)` | Lock acquired; dispatching to the tab-type runner | Informational |
| `INFO: Skipping profile ...: today does not match weekday ordinal '...'` | The cron weekday #n/#L guard failed at runtime | Skipped; exit 0 |
| `VERB: Ignoring weekday ordinal '...' for profile ... (--ignore-schedule)` | Immediate run requested (GUI Run Now or CLI `--ignore-schedule`); ordinal guard bypassed | Profile runs regardless of the day |
| `FATAL: Unknown tab type: ...` | No runner is registered for the profile's tab type | rc=1 |
| `INFO: Profile ... finished (rc=...)` | Final summary before the history entry and session trailer | Exits with rc |

### [profile_manager](../commands-and-modules/python-modules.md#profile_managerpy)

Loads/saves/deletes the profile JSON files.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: Could not read profile ....json: ...` | A profile JSON failed to parse/read during listing | That file skipped; others listed |
| `VERB: Deleted profile: ...` | The profile file was removed | Informational |
| `INFO: Updated profile: ...` | An existing profile's config was replaced (cron/active preserved) | Informational |
| `INFO: Created profile: ...` | A new profile JSON was written (default cron `0 2 * * *`, inactive) | Informational |

### [profile_dialogs](../commands-and-modules/python-modules.md#profile_dialogspy)

Workload-profile dialogs: Rewrite Data (zfs rewrite restripe) and Apply Profile, plus profile edit/delete guards. The two rewrite messages are embedded in the generated bash script.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: could not mount ... to rewrite data` | The temporary mount for `zfs rewrite` failed (bash-embedded) | Script exits 1; the Rewrite Data step fails |
| `WARN: could not unmount ... after rewrite` | The temporary mount could not be restored to unmounted (bash-embedded) | Rewrite rc still reported; dataset stays mounted |
| `WARN: Rewrite Data is available only on the storage host` / `WARN: Applying profiles is available only on the storage host` | Two-node gates — invoked on the compute node | Action aborted |
| `WARN: Select at least one dataset to rewrite data` | Empty dataset list | Action aborted |
| `WARN: Rewrite Data supports filesystem datasets only; zfs rewrite cannot act on a volume's block device (...)` | The selection contains volumes | Action aborted |
| `WARN: Rewrite Data requires OpenZFS 2.3+` | Capability gate — zfs rewrite unsupported | Action aborted |
| `WARN: Dataset runner not available` / `A dataset action is already running` | Runner missing / busy guard | Action aborted |
| `WARN: Could not read properties for ...: ...` | The mountpoint/apply property query failed (plain-language explanation appended) | Rewrite preflight aborted / that dataset skipped in Apply |
| `WARN: Cannot rewrite data for ...: mountpoint is '...'` | Mountpoint none/legacy/- cannot be rewritten via path | Aborted |
| `WARN: Rewrite Data requires the physical_rewrite pool feature on ... (zpool set feature@physical_rewrite=enabled ...)` | Per-pool feature-flag gate | Aborted; enable the feature to proceed |
| `INFO: Rewrite Data cancelled for ...` | The step was cancelled after the Yes/No confirm | Skipped; locks released; refresh |
| `WARN: Rewrite Data failed for ... (rc=...)` | A rewrite step exited non-zero | Operation aborted; locks released |
| `INFO: Rewrite Data complete for ...` | All rewrite steps finished rc=0 | Informational |
| `WARN: Select a profile to edit` / `WARN: Select a profile to delete` | No workload-profile row selected | Action aborted |
| `WARN: Profile ... no longer exists` | The selected name vanished from the saved profiles | Edit aborted; list refreshed |
| `WARN: Workload profile '...' is built in and cannot be deleted` | Built-in profile delete guard | Delete aborted |
| `WARN: No workload profiles apply to ... datasets` | Picker gate — no profile's applies_to matches the dataset type | Apply dialog aborted |
| `INFO: Apply Profile cancelled` | The apply step was cancelled | Skipped; locks released |
| `WARN: Apply Profile failed (rc=...)` | One or more `zfs set` steps exited non-zero (steps are non-fatal) | Failure reported; locks released |
| `INFO: Apply Profile complete: ... command(s)` | All planned `zfs set` commands ran | Pages refreshed |

### [schedule_page](../commands-and-modules/python-modules.md#schedule_pagepy)

Schedule tab: profile list with Active toggles, Run Now, cron consistency checks, and regeneration of the cron file.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: Cron file does not exist; active profiles are not scheduled` | Active profiles exist but the `/etc/cron.d` file is missing | Use the Schedule tab Save button to regenerate |
| `WARN: Could not read cron file ...: ...` | OSError reading the cron file for the consistency check | Check skipped |
| `WARN: Cron file is out of sync with active profiles; use the Schedule tab Save button to regenerate it` | Mismatch between active profiles and crontab job lines | Use Save to resync |
| `WARN: Active profile missing from crontab: ...` / `WARN: Crontab contains profile not marked active: ...` | One-sided drift between profiles and the cron file | Regenerate via Save |
| `WARN: Schedule refresh failed: ...` | The background refresh worker raised | Refresh application skipped |
| `WARN: Profile not found: ...` | The profile JSON is missing when toggling Active or saving | That profile's change skipped |
| `[profile] ...` (no level) | Relay — each output line of a Run Now profile run is prefixed into the GUI log (progress bars go to the status bar) | Informational pass-through |
| `INFO: Profile finished: ...` | The Run Now child exited | Buttons re-enabled |
| `INFO: Running profile now: ...` | Immediate run triggered regardless of Active status | Subprocess launched |
| `WARN: Could not start profile ...: ...` | Spawning the profile runner failed | Run-now aborted |
| `WARN: Could not watch profile ... output: ...` | Output-watch setup failed | The process is terminated; run aborted |
| `WARN: No profile selected` | Run Now / Delete with empty selection | Action aborted |
| `INFO: Updated schedule profiles` | Pending active/cron/comment changes saved and the cron file regenerated | Informational |
| `INFO: Reverted schedule changes` | Pending edits discarded; UI restored to the saved state | Informational |
| `VERB: Deleted profile: ...` | The profile and its cron entry were removed after the Yes/No confirm | List refreshed |

### [cron_manager](../commands-and-modules/python-modules.md#cron_managerpy)

Writes the `/etc/cron.d` file from the active profiles.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `VERB: Cron file updated: ...` | The cron file was successfully rewritten | Informational |
| `FATAL: Could not write cron file ...: ...` | OSError writing the cron file | Exception re-raised; the caller shows an error dialog |

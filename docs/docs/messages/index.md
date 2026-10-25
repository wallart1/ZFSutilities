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
| `FATAL: Rate limit set but pace_stream.py not found` | A transfer rate limit is configured but the pacer helper cannot be resolved beside the library (broken or partial deployment) | Script aborts before any bytes move — restore `lib/pace_stream.py` or clear the rate limit |
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
| `INFO: ... is a clone of ... — copying origin-free (plain full of the oldest snapshot, then -w -I incrementals).` | The source is a ZFS clone: a replication stream would let a receive onto a pool holding the origin link the destination straight back to it, so the engine copies with plain sends | Informational |
| `INFO: Destination already holds @... — skipping the full-copy step.` | A re-run found the oldest snapshot already staged by an earlier attempt | Informational |
| `WARN: Proceeding despite insufficient space.` | The shared space check failed; the wizard pre-validated capacity, so this is warn-only | Informational; the transfer is attempted |
| `FATAL: <operation> transfer interrupted; re-run <operation> to resume from the receive resume token on ....` | The transfer failed; the resume token is intentionally kept. `<operation>` is the caller's re-run hint (`$restart_hint`): `Migrate Pool` from the wizard, `sever-vm-clone` when the severance transfer or catch-up drives the engine, `sever-vm-clone --continue <state-file>` for the cutover copy-back | Re-run the named operation to resume |

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
| `WARN: Error launching: ...` | Spawning a step failed (OSError/FileNotFoundError) | Paired with the FATAL below — the run no longer reports success for a step that never launched |
| `FATAL: Could not launch step: ...` | A main-list step could not be spawned; the step is treated as failed (its post-callback stays unrun) | Run finishes rc=1 (the post-backup/finally step, if any, still runs first) |
| `WARN: Pre-step callback failed: ...` | Step pre-callback raised before spawn | Step still runs |
| `WARN: Post-step callback failed: ...` | Step post-callback raised after spawn failure or exit | Continue to the next step |
| `WARN: Unexpected error while starting next step: ...` / `Unexpected error while checking process: ...` | Unhandled exception in the step-advance or process-poll path | Run aborted with rc=1 |
| `WARN: Post-backup script exited with rc=...` | The post-backup script finished non-zero after an earlier fatal step | Run finishes with the original fatal rc |
| `INFO: ... ... done (rc=...)` | Rsync step completion record including rc | Informational |
| `INFO: Rsync log: /var/log/zfsutilities/rsync-backup.log` | Pointer to the dedicated rsync output log | Operator can inspect the file |
| `WARN: Step exited with rc=...` | Any step finished non-zero | Failure handling follows (rc=9 user abort, fatal abort, or continue) |
| `WARN: ... failed: ...` | Rsync-specific diagnosis for the failed step; for log-wrapped pull steps it ends with `(full rsync output: host:/var/log/zfsutilities/rsync-pull.log)` naming where the complete transfer record lives, and the wrapper's failure tail (header plus the last output lines) appears just above it in the log | Diagnostic |
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
| `INFO: Removing ... --- Offsite same-month.` / `INFO: Would remove ... --- Offsite same-month.` | Phase 0 (offsite label only): an older same-month offsite snapshot is superseded by a newer one | Real runs delete it after a press-enter prompt (when autoproceed != 'Y'); the "Would remove" form is the dry-run report, gated by `_delsnap_preview_gate` |
| `INFO: Removing ... --- Same-day.` / `INFO: Would remove ... --- Same-day.` | Phase 1: the older of two same-day snapshots is removed | Real runs delete it after a press-enter prompt; "Would remove" is the dry-run report, gated by `_delsnap_preview_gate` |
| `INFO: Removing ... --- Bucket[ (empty)].` / `INFO: Would: Remove ... --- Bucket[ (empty)].` | Phase 2: a bucket exceeds its retention count and the oldest snapshots are removed (" (empty)" marks snapshots with no written data) | Real runs delete it after a press-enter prompt; "Would: Remove" is the dry-run report, gated by `_delsnap_preview_gate` |
| `INFO: Would: Keep ... --- <phase>; only ... days old (minimum age is ... days).` | Dry run: the candidate is younger than the minimum age `zfsdelsnap` would enforce (Phase 0/1 pass 0; Phase 2 the bucket's policy value) | Informational; the preview matches the refusal `zfsdelsnap` would raise (see the `zfsdelsnap` age-gate warning) |
| `INFO: Would: Keep ... --- <phase>; last remaining common snapshot with a counterpart.` | Dry run: `zfscheckagainst` reports this candidate is the last snapshot common with a counterpart dataset, so deletion would be blocked (rc 7) | Informational; the preview matches the block the real run's deletion step raises |
| `INFO: Would: Keep ... --- <phase>; counterpart pool(s) offline.` | Dry run: `zfscheckagainst` could not verify a counterpart because its pool is offline, so deletion would be blocked (rc 6) | Informational; bring the counterpart pool online to verify, then re-run the preview |
| `INFO: Would: Keep ... --- <phase>; no eligible checkagainst entries (an interactive run would confirm).` | Dry run: no fss-table row matched this snapshot (rc 5); a real `zfsdelsnap` asks for confirmation there, and non-interactive runs get the default "no" | Informational; add a checkagainst entry or confirm interactively in a real run |
| `INFO: Would: Keep ... --- <phase>; held (...).` | Dry run with `releaseholds='N'`: the snapshot carries holds, so the real run's `zfs destroy` would fail busy and skip | Informational; release the holds or run with `releaseholds='Y'` |
| `INFO: Would: Keep ... --- <phase>; holds remain (...); a real run releases only matching tags.` | Dry run with `releaseholds='Y'`: holds outside `releaseholds_tags` survive the release, so `zfsdelsnap` would skip the deletion | Informational; extend `releaseholds_tags` or release the remaining holds manually |
| `INFO: Would: Keep ... --- <phase>; clone dependents.` | Dry run: the snapshot has clone dependents, so `zfsdelsnap` would skip the deletion | Informational; destroy or promote the clones first |
| `INFO: Would: Keep ... --- <phase>; unexpected checkagainst rc=....` | Dry run: the paired keep report after `WARN: checkagainst returned rc=...` — the preview keeps the snapshot rather than guess at an out-of-contract code | Informational; investigate the checkagainst output named in the WARN |
| `WARN: checkagainst returned rc=... for ...; keeping it in the preview to stay conservative.` | Dry run: `zfscheckagainst` returned a code outside its documented contract (its WARN detail names the snapshot and counterpart) | Investigate the checkagainst output; the preview keeps the snapshot rather than guessing |
| `INFO: Dry-run preview: candidates pass the same read-only gates as deletion time (checkagainst counterparts, holds, clone dependents, minimum age). Not modeled: lock contention, destroy failures, and the interactive confirm for snapshots with no checkagainst entries.` | Emitted once per dataset at the start of a dry-run preview: the deletion-time gates run read-only via `_delsnap_preview_gate`; only what cannot be probed ahead of time is unmodeled | Informational; "Would: Remove"/"Would remove" candidates now match what a real run deletes, modulo the named residuals |
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
| `WARN: Snapshot ... has clone dependents. Skipping deletion.` | The snapshot is a clone origin | Snapshot kept; sever ([sever-vm-clone](#sever-vm-clone)) or destroy the clones |
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
| `FATAL: One or more datasets have ZFS clone dependents and cannot be deleted. Use sever-vm-clone to sever the dependencies first.` | Interactive pre-check found clone dependents | Script aborts (exit 8); sever the clones first |
| `FATAL: ... has ZFS clone dependents — cannot delete. Use sever-vm-clone to sever the dependencies first.` | Per-dataset clone gate during deletion | Script aborts (exit 8); sever the clones first |
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
| `INFO: Hold <tag> already present on <snap>` | The tag is already held on that snapshot — normal when nested datasets are matched by both their own call and their parent subtree call | Informational; treated as success |
| `WARN: Could not apply hold <tag> to <snap>` | A hold failed for a reason other than the tag already being present | Return 1; check the pool and dataset state |

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
| `INFO: Found disks with dependent clones:` | Dependent ZFS clones exist on this VM's zvols | The severance prompt follows |
| `INFO: No dependent clones found.` | Nothing depends on this VM | Informational |
| `FATAL: Clone VM ... is not stopped (status: ...).` | Severance gate: severance copies the clone zvols in full and swaps them in under the same names, so the clone VM must be stopped first | Stop the clone VM (`qm stop` or the Proxmox GUI), then re-run archive-vm |
| `INFO: Severing VM ......` | Per-clone-VM milestone: [sever-vm-clone](#sever-vm-clone) runs for the clone VM | Informational; see its messages |
| `INFO: Skipping clone severance.` | The operator declined severance | Run continues; see the warning below |
| `WARN: VM removal may fail while snapshots are held by clones; sever them first with sever-vm-clone.` | Consequence of declining severance | Sever the clones first with [sever-vm-clone](#sever-vm-clone) |
| `FATAL: Severance failed for VM ...` | `sever-vm-clone` exited non-zero after the operator approved | Script aborts; see its messages |
| `INFO: --- Step 2: Archiving VM ... ---` | Phase milestone | Informational |
| `FATAL: Archive base path is required` | No path given and no saved default exists | Supply the archive base path |
| `FATAL: Not a ZFS dataset: ...` / `FATAL: Not a ZFS dataset on ...: ...` | The archive base is not a ZFS dataset (local or storage host) | Use a ZFS dataset as the archive base |
| `INFO: ✓ Saved archive path to JSON config` | The entered path differs from the saved default and was persisted | Informational |
| `FATAL: Proxmox config not found: ...` | `/etc/pve/qemu-server/<vmid>.conf` is missing | Check the VM ID |
| `FATAL: Failed to discover referenced zvols` / `FATAL: No referenced zvols found for VM ...` | Disk discovery failed or found nothing | Script aborts; check the VM config |
| `INFO: Zvols to archive:` | Pre-confirmation summary | Review, then answer the archive prompt |
| `INFO: Snapshot to archive: ...` | The zvol's newest (or newly created retire) snapshot chosen for archiving | Informational |
| `INFO: Archiving ... → ...` | Per-zvol transfer begins (shared engine, `lib/archive-engine.sh`) | Informational |
| `INFO: Original volblocksize: ...` | The source zvol's volblocksize, recorded to the sidecar | Informational |
| `INFO: Archive method: device copy (reblock to 1M)` | Unencrypted zvol: the archive zvol is created thin at `volblocksize=1M` and the snapshot device is copied onto it — the only reblocking mechanism that works, since volblocksize travels in every stream and cannot be overridden at receive | Informational |
| `INFO: Archive method: raw send/receive (encrypted)` | Encrypted zvol: raw stream received as-is (a device copy would read plaintext); original volblocksize kept | Informational |
| `FATAL: Failed to create parent dataset ...` | The archive parent chain could not be created | Script aborts; check the archive pool |
| `FATAL: Failed to expose snapshot device on ...` | `snapdev=visible` could not be set on the source zvol | Script aborts; check the pool state |
| `FATAL: Archive dataset already exists: ...` | A previous archive of this zvol already exists under the base | Destroy it first (`zfs destroy -r ...`) to re-archive |
| `FATAL: Snapshot device did not appear: ...` / `FATAL: Archive device did not appear: ...` | The `/dev/zvol` node did not settle within the wait window | Script aborts; check udev and the pool state |
| `FATAL: Failed to create archive zvol ...` | The thin 1M archive zvol could not be created | Script aborts; this run's datasets are rolled back |
| `FATAL: Device copy failed (... → ...)` | The device-copy pipeline (or its in-flight hash stage) failed | Script aborts; this run's datasets are rolled back |
| `FATAL: Failed to hash source during copy` | The in-flight source-hash stage of the copy pipeline failed | Script aborts; this run's datasets are rolled back |
| `INFO: Verifying copy integrity (sha256)...` | The destination is being read back to compare against the source hash captured during the copy (device copies carry no stream checksums) | Informational |
| `INFO: ✓ Copy verified (sha256 match)` | The copy matches the source snapshot | Informational |
| `FATAL: Failed to hash devices` | A hash read failed | Script aborts; this run's datasets are rolled back |
| `FATAL: Rate limit set but pace_stream.py not found` | A transfer rate limit is configured but the pacer helper cannot be resolved beside the library (broken or partial deployment) | Script aborts before any bytes move — restore `lib/pace_stream.py` or clear the rate limit |
| `FATAL: Hash mismatch between ... and ...` | The copied archive differs from the source snapshot | The copy is corrupt; this run's datasets are rolled back — re-run after investigating |
| `FATAL: Failed to snapshot archived zvol ...@archive` | The point-in-time marker on the archive zvol failed | Script aborts; this run's datasets are rolled back |
| `WARN: Removed partial archive dataset ...` / `WARN: Removed created parent ...` | A failed transfer undid exactly the datasets this run created | Informational; re-run after fixing the cause |
| `INFO: ✓ Archived: ...` | The zvol's archive completed | Informational |
| `FATAL: Failed to archive ...` | The per-zvol transfer failed (details above) | Script aborts |
| `INFO: ✓ Saved transfer rate limit to JSON config` | The entered rate limit differs from the saved default and was persisted | Informational |
| `FATAL: Invalid rate limit '...' — use a rate value ...` | The entered rate limit is not a digits-plus-suffix rate value (and not empty) | Script aborts; re-run with e.g. 100M or leave empty |
| `WARN: Incomplete archive dataset from an interrupted run:` / `WARN: ... removing and re-archiving ...` | The dataset exists without its post-verification @archive snapshot — unverified leftover | Informational; it is destroyed and re-made automatically |
| `INFO: ✓ Already archived (verified) — skipping: ...` | Re-run skip: the dataset carries @archive, a METHOD= sidecar, and the volblocksize its method implies | Informational |
| `INFO: --- Step 3: Verifying archive ---` | Phase milestone; the verification gate begins | Informational |
| `FATAL: MISSING dataset: ...` | Verification found an archive dataset absent (counted; the run aborts at the end of verification) | Check the transfer messages above |
| `FATAL: Volblocksize mismatch on ...: expected ..., got ...` | The archived zvol's volblocksize does not match its method (1M for copy archives, the sidecar original for raw) | Treat the archive as suspect; re-archive |
| `FATAL: Config archive missing or empty` | The archived Proxmox config is absent or zero-length | Check the config copy step |
| `INFO: ✓ Config archive OK` | Config verification passed | Informational |
| `FATAL: Archive verification failed (... errors). VM NOT removed.` | One or more verification errors — the removal gate blocked Step 4 | Fix the archive before rerunning; the VM is intact |
| `INFO: Archive verified.` | Verification passed | Informational |
| `INFO: --- Step 4: VM removal ---` | Phase milestone | Informational |
| `INFO: VM ... preserved. Archive is under: ...` | The operator declined VM removal | VM kept; the archive remains |
| `INFO: Removing disk ... from pool ...` / `INFO: Destroying ...` | Per-disk removal begins — two-node delegates to `remove-vm-disk` over a TTY-allocating ssh (its confirm prompts appear on this terminal), single-node destroys via `zfsdelfs` | Informational; answer the delegated prompts |
| `WARN: ... was not removed` / `WARN: Could not destroy ...` | A disk survived removal — a declined confirm, a remote failure, or a destroy failure; judged by outcome (the zvol must be gone), never by exit code | Continue to the next disk; the run stops before config removal |
| `WARN: iSCSI rescan failed; run 'rescan-storage' manually` / `WARN: Could not locate rescan-storage; run it manually` | The post-removal compute-host rescan could not run | Run `sudo rescan-storage` manually |
| `FATAL: VM removal incomplete — the following zvols remain:` | At least one disk survived; each survivor is listed below this line | Follow the recovery guidance in the FATAL block |
| `FATAL: The Proxmox config was NOT removed: ...` / `FATAL: The verified archive is safe under: ...` | Partial-removal safety gates: the config is kept so the VM remains defined until every disk is gone | Informational |
| `FATAL: Run 'remove-vm-disk <pool> ... <disk-num>' on this host for each disk above, then delete ...` | Exact recovery commands for the surviving disks | Run them on the compute host, then delete the config |
| `INFO: VM ... has been archived.` / `INFO: Archive: ...` | Final outcome: all zvols destroyed, config removed, archive location listed | Informational |

### [unarchive-vm](../commands-and-modules/commands.md#unarchive-vm)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: new-vmid must be a number, got: ...` / `FATAL: new-vmid must differ from vmid` | `--new-vmid` validation | Script aborts |
| `INFO: vmid ... is already in use (a Proxmox config exists).` | A Proxmox config for the vmid exists on the compute host — zvols elsewhere never trigger this; the interactive new-vmid prompt follows | Enter a different numeric vmid (blank aborts) |
| `INFO: vmid ... is also in use.` | The interactively proposed vmid also collides | Enter another vmid |
| `FATAL: Requested new vmid ... is already in use` | The `--new-vmid` value collides (non-interactive) | Script aborts; choose a free vmid |
| `FATAL: new vmid must be a number, got: ...` / `FATAL: new vmid must differ from the original vmid` | Interactive prompt input validation | Script aborts |
| `FATAL: Archive base path is required (provide as argument or save in JSON config)` | No path argument and no saved default | Supply the archive base path |
| `FATAL: Not a ZFS dataset: ...` / `FATAL: Not a ZFS dataset on ...: ...` | The archive base is not a ZFS dataset | Use a ZFS dataset as the archive base |
| `FATAL: SSH to ... failed` | Two-node archive discovery failed | Script aborts; check SSH |
| `FATAL: No archived zvols found for VM ... under ...` | The archive holds nothing for this vmid | Check the vmid and archive base |
| `FATAL: Missing .disk_info sidecar file(s):` | The `.disk_info` sidecar is absent (list printed); it is load-bearing for config/iSCSI rebuild | Script aborts; the archive is incomplete |
| `FATAL: Every disk in an archive must carry a .disk_info sidecar. An archive without them predates the sidecar format — ...` | Continuation of the missing-sidecar FATAL: an archive with no sidecars anywhere predates the sidecar format, so there is no recorded disk key, config text, or iSCSI layout to rebuild from | Script aborts; pre-sidecar archives need the manual restore procedure (see the unarchive-vm documentation) |
| `WARN: Missing volblocksize sidecar (informational): ...` | No `.original_volblocksize` sidecar; harmless for raw-method restores (the stream carries volblocksize) | Informational unless the archive's method is copy |
| `INFO: ✓ Saved transfer rate limit to JSON config` / `FATAL: Invalid rate limit '...'` | Restore-side rate prompt (shared JSON default with archive-vm) | Informational / re-run with a rate value or empty |
| `INFO: Restore of VM ... is already complete — nothing to do.` | Re-run after a finished restore: every destination zvol carries the RESTORED_AS marker and the config exists | Informational; the run exits cleanly |
| `INFO: ✓ Already restored (verified) — skipping: ...` | Re-run skip: this disk's restore carries the completion marker | Informational |
| `INFO: Removing unmarked leftover ...` | A confirmed destroy-and-redo: the destination zvol existed without the completion marker and the operator approved re-restoring it | Informational |
| `FATAL: Refusing to destroy ... — aborting.` | The operator declined destroying an unmarked destination zvol (interrupted run's leftover or a foreign orphan) | Script aborts; resolve the zvol manually and re-run |
| `FATAL: Archived config not found: ...` / `FATAL: Archived config not found on ...: ...` | The archived Proxmox config is missing | Script aborts; check the archive |
| `FATAL: Destination Proxmox config already exists: ...` | Destination config collision while some disks are not completed restores | Script aborts; remove the config or the leftover zvols manually, then re-run |
| `INFO: Zvols to restore:` | Pre-confirmation summary (with volblocksize and rename mapping) | Review, then answer the restore prompt |
| `INFO: --- Step 1: Restoring zvols ---` | Phase milestone | Informational |
| `INFO: Restore method: copy (reblock to ...)` | The destination zvol is created thin at the sidecar's original volblocksize and the archive snapshot is device-copied onto it | Informational |
| `INFO: Restore method: raw send/receive` | The archive is streamed back as-is (encrypted or legacy); the stream carries volblocksize | Informational |
| `FATAL: Unknown archive method '...' in ...` | The `.disk_info` `METHOD=` marker is neither `copy` nor `raw` | Script aborts; the archive is damaged |
| `FATAL: Missing volblocksize sidecar for copy-method restore:` | A copy-method restore needs the original volblocksize to create the destination zvol | Script aborts; restore the sidecar from backup or re-archive |
| `FATAL: Snapshot device did not appear: ...` / `FATAL: Restore device did not appear: ...` | The `/dev/zvol` node did not settle within the wait window | Script aborts; check udev and the pool state |
| `FATAL: Failed to create zvol ...` | The destination zvol could not be created | Script aborts; rolled back |
| Copy-integrity messages | `INFO: Verifying copy integrity (sha256)...`, `INFO: ✓ Copy verified (sha256 match)`, and the hash FATAL/WARN rollback messages are shared with [archive-vm](#archive-vm) via the transfer engine | See archive-vm |
| `FATAL: No snapshots found on archive dataset: ...` | The archive dataset has no snapshot to restore from | Script aborts; the archive is damaged |
| `FATAL: Could not acquire write lock on ...` | The destination zvol's write lock is unavailable | Script aborts; resolve the lock |
| `FATAL: Failed to restore ...` / `FATAL: Zvol restoration failed on ...` | The per-zvol restore failed under either method (local or remote) | Script aborts; check space and the messages above |
| `INFO: --- Step 2: Rebuilding iSCSI infrastructure ---` | Phase milestone (two-node only) | Informational |
| `WARN: Unknown pool: ... (not in POOL_TARGET in ...)` | node-lib's pool lookup cannot find the restored zvol's pool in the node config's `POOL_TARGET` map; it precedes the FATAL below | Add the pool to `POOL_TARGET` in the node config on both nodes |
| `WARN: pool_to_target: target ... does not exist in the local LIO target tree` (+ the `IQN_PREFIX has drifted` lines) | IQN-prefix drift fence in node-lib: the constructed target is absent from the live LIO tree while other targets exist (typically `IQN_PREFIX` in the node config differs from the live targets after a reinstall) — LUN mapping would target a fresh/empty target while Proxmox logs in to the old one | Compare `targetcli /iscsi ls` with `IQN_PREFIX` in the node config; fix the prefix or remove orphan targets |
| `INFO: ...: IQN_PREFIX=... (prior copy: ...)` | node-lib's convergence write: every live pool target shares one IQN prefix and the node config's `IQN_PREFIX` disagreed, so the config is the regressed side; emitted once per host — the storage payload and then the compute host each converge their own `node.conf` | Informational; the prior value is kept in the timestamped `node.conf.bak-*` beside the conf |
| `INFO: ✓ ... node.conf IQN_PREFIX already ...` | The compute host's node config already carried the converged prefix when the storage host reported convergence | Informational |
| `WARN: could not converge IQN_PREFIX in ...'s node.conf` | The compute host's convergence write was refused or failed (unwritable conf, or no `IQN_PREFIX` line to rewrite) | The storage host stands converged; correct the compute host's node.conf from its backup and re-run |
| `INFO: pool ...: node.conf target ... is absent from the live tree; mapping into ... instead` | The constructed target is missing but exactly one live target already carries the pool's short name (drift without an unambiguous prefix to converge onto); this run maps into the live target | Informational; the by-path rewrite follows the live target |
| `INFO: ✓ Pool ...: mapped onto live target ...` | Orchestrator confirmation of the substitution above | Informational |
| `INFO: ✓ Created iSCSI target ...` | No live target carried the pool's short name, so the target was created with the setup-iscsi-targets recipe (authentication off, write-protect off, storage-network portal, demo-mode ACLs when the TPG has no explicit ACLs) | Informational; the compute host discovers and logs in to it in Step 4 |
| `FATAL: pool ...: multiple live targets share the short name '...':` (+ the candidate list and `FATAL: remove the stale duplicate target(s), then re-run`) | Two or more live targets carry the pool's short name under different prefixes; which one is real cannot be decided automatically | Script aborts BEFORE any iSCSI mutation; remove the stale duplicate, then re-run |
| `FATAL: could not create iSCSI target ...` / `FATAL: could not disable authentication on ...` / `FATAL: could not clear write-protect on ...` / `FATAL: could not add portal ... to ...` / `FATAL: could not enable demo-mode ACLs on ...` | A step of the target-creation recipe failed on the storage host (the portal FATAL fires only when the TPG ended up with no portal at all) | Script aborts; see the targetcli error above the message, resolve, and re-run |
| `WARN: ...: kept its existing portal (could not add ...:3260)` | Target creation rides along with a default 0.0.0.0:3260 portal that blocks binding the same port on a specific address; the existing portal still serves the storage network | Informational |
| `FATAL: Cannot map pool ... to target` | No iSCSI target mapping for a restored zvol's pool (`pool_to_target` failed; the WARN above names the node config) | Script aborts; fix the node config mapping |
| `FATAL: iSCSI reconstruction failed on ...` | The remote iSCSI rebuild failed | Script aborts; see the remote messages |
| `INFO: ✓ iSCSI configuration saved` | The storage host's targetcli config was persisted | Informational |
| `SAVE_FAILED` | The remote `safe-iscsi-save` failed; `CONFIG_SAVED` is only emitted after a successful save | Reconstruction aborts; resolve the save failure and re-run |
| `INFO: --- Step 3: Restoring Proxmox config ---` | Phase milestone | Informational |
| `FATAL: Failed to read archived config` | The archived config read returned nothing | Script aborts |
| `FATAL: Could not write ... on ...` | The rewritten config could not be placed on the compute host | Script aborts; the zvols and iSCSI state stand — re-run to finish |
| `INFO: ✓ Config restored: ...` | The config was written (copied or path-rewritten) | Informational |
| `WARN: Could not map ..., keeping original line` | A disk line's LUN/target could not be remapped during the rewrite | The original line is kept; verify the disk in the Proxmox GUI |
| `INFO: --- Step 4: Rescanning iSCSI ---` | Phase milestone (two-node only) | Informational |
| `WARN: iSCSI discovery against ...:3260 failed` | The compute host could not query the storage portal's target list before logging in | Freshly created targets may stay invisible; check the storage network and re-run |
| `WARN: could not log in to ... (iscsiadm rc ...)` | A targeted login to a target this run mapped failed (rc 15, already logged in, is not warned) | The VM may miss that disk; check the target and re-run |
| `WARN: iSCSI rescan failed on ... (see warnings above)` | The compute-host rescan failed | Resolve the warnings above and re-run before starting the VM |
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
| `INFO: To sever the clone dependency before retiring VM ...: sever-vm-clone ...` | Remediation for the retained origin | Run [sever-vm-clone](#sever-vm-clone) before retiring the source |
| `INFO: VM ... (...) is ready in Proxmox.` | Final outcome | Informational |

### [sever-vm-clone](../commands-and-modules/two-node.md#sever-vm-clone-both)

Severs a ZFS-cloned VM's disk zvols from their origin snapshots: each clone
zvol is copied in full into a fresh, origin-free zvol that is swapped in under
the same name, so Proxmox configs and iSCSI references keep working. Phase 1
stages the copies (the VMs may keep running); Phase 2 is the cutover swap (the
owning VMs must be stopped) with `--continue`/`--rollback` recovery from a
state file; the origin-snapshot report at the end offers to destroy unpinned
origins — where the pinned space actually comes back. Tight-space runs stage
the copies in a user-named intermediate holding pool and copy them back after
the originals are destroyed. Invoked on the storage host, the script silently
re-execs itself on the compute host (the canonical entry) before any
environment guard runs. Every cutover step is idempotent, so recovery resumes
from the last phase the state file records.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: ... requires exactly one <state-file> argument.` | `--continue`/`--rollback` without exactly one non-option argument | Usage follows; script exits |
| `FATAL: Unknown option: ...` | Any other option was given | Usage follows; script exits |
| `FATAL: A VM ID accepts no further arguments (VM IDs and named datasets are mutually exclusive).` | A vmid argument was followed by more arguments | Usage follows; script exits |
| `FATAL: Not a valid dataset name: ...` | An argument is not a plausible dataset name (validated before the two-node delegation embeds it in the SSH command) | Usage follows; script exits |
| `FATAL: Failed to gather zvol information from ...` | The discovery gather over the storage host (SSH in two-node mode) failed | Script aborts; check SSH/zfs on the storage host |
| `INFO: Skipping ...: not a clone (no origin snapshot).` / `INFO: Skipping ...: exists but is not a zvol.` / `INFO: Skipping ...: already selected for severance.` | Dataset mode: a named dataset is not a clonable zvol or repeats an earlier one | Dataset skipped; run continues |
| `FATAL: Dataset not found: ...` | A named dataset does not exist | Script aborts |
| `FATAL: No clone zvols found for VM ... — already severed or not a ZFS clone.` / `FATAL: None of the given datasets is a clone zvol — nothing to sever.` | Discovery found nothing to sever | Usage follows; nothing to do |
| `INFO: === sever-vm-clone ===` | Plan header; the node mode and each zvol with its origin, owning VM, and copy size follow | Review the plan and the space verdicts below |
| `INFO: Source pool space (same-pool mode needs largest-disk x 1.1 free):` | Space-verdict header; one `INFO: ...: free ..., need ... — enough` / `... — NOT enough` line per source pool | A NOT-enough pool forces the holding-pool ask below |
| `WARN: Could not read free space for pool ...; assuming no room.` | The pool's free space could not be read at plan time | The pool is treated as tight; the holding-pool ask follows |
| `INFO: Recommended transfer mode: same-pool temporary namespace` | Every source pool can hold its largest disk plus margin; each copy is swapped in and its old zvol destroyed before the next disk starts | Answer the `Proceed with severance?` prompt |
| `INFO: Recommended transfer mode: intermediate holding pool` | No room in the listed pools; the copy lands in a holding pool first and is pulled back after the old zvol is destroyed | The holding-pool ask follows |
| `WARN: The owning VMs must be stopped during transfer and cutover.` | Pre-confirmation reminder: the transfer tolerates running VMs, the cutover does not | Stop the VMs before the cutover begins |
| `INFO: Tight-space mode: pool(s) ... cannot hold a same-pool copy. An intermediate holding pool is needed...` | Explanation block for the holding-pool ask (copies stage in `<holding>/sever_<vmid>/` and are copied back after the destructions) | Read; the candidate list and the name prompt follow |
| `FATAL: No imported pool has the ... free this run needs to stage the copies (all copied disks x 1.1 headroom).` | No imported pool outside the tight sources can hold every staged copy | Script aborts; free space on another pool — or in the tight pools so the same-pool mode fits — and re-run |
| `INFO: Candidate holding pools (imported, free >= ...):` | The imported pools that could hold the copies, each with its free space | Answer `Holding pool name (Enter to abort): ` with one of them |
| `INFO: Aborted.` / `INFO: No holding pool given — aborted (nothing was changed).` | The Enter-to-abort path of the holding-pool ask | Script exits 0 without changes |
| `WARN: ... is one of the tight source pools — it has no room for the copies. Pick another pool.` / `WARN: '...' is not an imported pool on ....` | The typed holding-pool name is invalid | The ask repeats |
| `WARN: ... has ... free — below the ... this run stages there. If the pool fills, the receive suspends with a resume token; re-running sever-vm-clone resumes it.` | A below-need holding pool was chosen anyway | Proceed; a full pool suspends the receive resumably |
| `WARN: The zvols being severed are encrypted and the holding pool's key is NOT loaded (keystatus=unavailable on ...). Load it first (zfs key -l) — receives into ... may fail otherwise.` | Key check on the holding pool (encrypted sources only) | Load the key before proceeding |
| `INFO: The copies stay encrypted: the transfer is raw (-w), so the copy-back and the swapped-in zvol keep the original encryption setup.` | Encryption note for holding mode | Informational |
| `FATAL: Failed to gather origin-snapshot information from ...` | The origin-stats gather (SSH in two-node mode) failed | Script aborts; check SSH/zfs on the storage host |
| `INFO: Copy-back room: destroying each original frees only its diverged data; the origin snapshots' pinned space frees with them...` | Holding-plan header; one verdict line per origin of the holding-staged disks | Read the verdicts, then answer the destroy confirmation |
| `INFO: ... — ... pinned, but still cloned by ...: NOT destroyable here; its space is not counted.` / `INFO: ... — ... pinned, destroyable once its clones are.` | Per-origin plan verdict; sibling clones keep a snapshot pinned | Still-cloned origins stay uncounted; the rest feeds the estimate |
| `Destroy these origin snapshots after the severance to make room for the copy-back?` | Holding-plan confirmation (default y) | y marks the destroyable origins for destruction at each disk's cutover; n keeps them (next row) |
| `INFO: Origin snapshots stay — their pinned space is not counted for the copy-back.` | The confirmation was declined | The estimate below ignores the pinned space |
| `INFO: Copy-back space estimate per tight pool (re-checked with fresh numbers at the cutover, before anything is destroyed):` | Estimate header | Read the per-pool estimate lines |
| `INFO: ...: free ... + originals' diverged data ... + origin snapshots ... = ... >= ... — feasible on estimate` | The plan-time estimate says the copy-back fits | Proceed to the mode summary and the severance prompt |
| `FATAL: ...: free ... + originals' diverged data ... + origin snapshots ... = ... < ... the copy-back needs.` | The plan-time estimate says the copy-back cannot fit; the continuation lines explain that a lightly-diverged clone frees little | Script aborts; free space in the pool, or confirm the destroyable origin snapshots, and re-run — nothing was changed yet |
| `INFO: Chosen transfer mode: holding pool ...` / `INFO: Confirmed: the destroyable origin snapshots of the holding-staged disks are destroyed at their cutover, before the copy-back.` | Holding-mode summary: each disk's staging path and copy-back destination, and the confirmed origin destructions | Review, then answer the `Proceed with severance?` prompt |
| `Proceed with severance?` | The main confirmation gate; a decline logs `INFO: Aborted.` and exits 0 without changes | y starts Phase 1 |
| `INFO: === Phase 1: transfer (full copy; the VMs may keep running) ===` | Phase milestone; the transfer-time space lines follow | Informational |
| `INFO: Pool ... is tight — its disks' copies stage in the holding pool ....` | Transfer-time note for a tight pool in holding mode | Informational |
| `WARN: Pool ...: free ..., need ... for the same-pool copy (largest disk ... x 1.1 headroom).` | Transfer-time same-pool space warning; the copy still proceeds | A full pool suspends the receive with a resume token a re-run resumes |
| `FATAL: Could not acquire write lock on ...` | Transfer/copy-back lock gates: the namespace root, the source zvol, or the temp-namespace parent | Script aborts; resolve the lock and re-run (a resume token covers the partial copy) |
| `INFO: Creating temp namespace ....` / `FATAL: Could not create ....` | The deterministic staging namespace (`<pool>/proxmox/sever_<key>/`, or `<holding>/sever_<key>/`) is created — or its `zfs create` failed (copy-back path) | Informational / the disk's cutover aborts |
| `INFO: Reusing existing snapshot ...` / `INFO: Creating snapshot ... (bucket-less: retention never prunes it).` | The `@sever-<ts>` transfer snapshot on the source zvol; a re-run finds the earlier one | Informational |
| `INFO: Copying ... in full to ......` | The full copy through the migration engine begins (a receive resume token is resumed when present) | Informational; engine failures appear as [zfs-migrate-send](#zfs-migrate-send) messages |
| `WARN: ... completed under resumed snapshot @... (taken before this run).` | A resumed interrupted receive completed under its original snapshot name | Informational; that snapshot name is carried through the cutover |
| `FATAL: No sever snapshot found on ... after the transfer.` | The received copy carries no `@sever-*` snapshot | Script aborts; inspect the staged copy |
| `INFO: ✓ ...: fresh copy at ... (snapshot @..., GUID ...).` | Per-disk transfer outcome | Informational |
| `FATAL: The staged copy ... is still a clone of ... — the receive linked to the existing origin instead of copying data.` / `FATAL: Nothing was destroyed. Clone sources must be copied with plain (non-replication) sends — engine defect.` | The origin gate refused the staged copy (an engine defect: a replication stream of a clone re-linked the origin on the same pool) | Nothing was destroyed; fix the engine, then re-run sever-vm-clone |
| `FATAL: Severance verification failed: ... is still a clone of ... after the swap — the staged copy was not origin-free. The VM is usable, but nothing was severed.` | The post-swap backstop found the swapped-in zvol still a clone | The zvol works under its own name; re-run sever-vm-clone once the copy engine is fixed |
| `FATAL: Transfer phase failed (rc=...).` | The storage-side transfer worker failed | Script aborts; beyond the `@sever-*` snapshots no source data was touched — re-run sever-vm-clone to resume from the receive resume token |
| `FATAL: No transfer record for ....` | The worker's results file has no line for a selected zvol | Script aborts; re-run |
| `INFO: === Phase 1 complete: fresh copies staged in the temp namespace ===` | Phase milestone; each zvol's staging path, snapshot, and GUID follow | Informational |
| `INFO: === Phase 2: cutover (name-preserving swap; the owning VMs must be stopped) ===` | Phase milestone; the cutover state file is written before any gate that can abort | Informational |
| `WARN: ...: no owning VM in its name — cannot gate on qm status; the swap aborts safely (zfs destroy fails) if the zvol is busy.` | The zvol's basename carries no `vm-<id>-disk-<n>` id, so the stopped-VM gate cannot run for it | Informational; the destroy itself still refuses a busy zvol |
| `FATAL: The owning VMs must be stopped for the cutover: ...` | The stopped-VM gate found running owners (with statuses) | Stop the VM(s), then swap without re-copying: `sever-vm-clone --continue <state-file>`; the fresh copies stay staged and nothing was destroyed |
| `INFO: Skipping ...: already severed (phase done).` | A resumed cutover found this disk finished | Informational |
| `FATAL: Cutover aborted at ... (phase ...); the remaining disks are untouched.` | A disk's cutover worker failed at the recorded phase — the umbrella abort every per-disk FATAL below funnels into | Resolve the cause, then re-run: `sever-vm-clone --continue <state-file>` |
| `INFO: --- Cutover: ... ---` | Per-disk cutover milestone (holding-pool disks name their holding pool) | Informational |
| `INFO: iSCSI: target ..., LUN ..., backstore ....` / `INFO: iSCSI: ... is not exported (no backstore); no LUN rewire needed.` | Two-node cutover-time discovery decision markers; the discovered target/LUN/backstore are recorded in the state file so a resumed run re-exports them even after the original zvol is destroyed | Informational |
| `FATAL: Could not acquire destroy lock on ....` | The cutover's destroy-class locks: the original zvol, the staged copy, the copy-back temp, or the origin snapshot's parent | The disk's cutover aborts (see below); resolve the lock and `--continue` |
| `INFO: Reusing existing cutover snapshot ...` / `INFO: Creating cutover snapshot ... (bucket-less: retention never prunes it).` | The `@sever-<ts>-cutover` snapshot on the source; a replay finds the earlier one | Informational |
| `FATAL: Could not create ...@...; nothing was destroyed.` | `zfs snapshot` of the cutover snapshot failed | The disk's cutover aborts with nothing destroyed |
| `FATAL: Transfer snapshot ... is missing on the source; the staged copy cannot be caught up.` | The `@sever-*` send base vanished between the phases | Re-run sever-vm-clone with the original arguments to make a fresh full copy |
| `INFO: Cutover snapshot already received on ...; skipping the catch-up send.` / `INFO: Catch-up incremental ...@... → ...@... into ......` | The catch-up step: a receive that finished before its phase marker is reused; otherwise the incremental lands every change made during the transfer | Informational |
| `FATAL: ...@... exists with GUID ... but the source has ... — aborting with nothing destroyed.` | The staged copy's cutover snapshot is not the source's (a foreign receive) | The disk's cutover aborts; investigate the staged copy |
| `FATAL: Catch-up transfer failed (rc=...); nothing was destroyed.` | The catch-up send/receive failed | Re-run `sever-vm-clone --continue <state-file>` — it resumes from the receive resume token |
| `FATAL: Cannot read the cutover snapshot GUID on ...; aborting with nothing destroyed.` / `FATAL: No cutover snapshot on the staged copy ...; aborting with nothing destroyed.` | The pre-destroy verify could not read one side | The disk's cutover aborts; check both datasets |
| `FATAL: Cutover snapshot GUID mismatch for ...: source ... vs copy ... — aborting with nothing destroyed.` | The pre-destroy verify failed: the staged copy is not the source | The disk's cutover aborts; investigate before retrying |
| `INFO: Verified ...@...: GUID ... on source and copy.` | Pre-destroy verify passed | Informational |
| `INFO: Copy-back space pre-check for ...: ... — feasible.` | Holding mode: the fresh-number gate that runs before any destruction of the disk | Informational |
| `FATAL: Cannot read the free space of pool ... — aborting BEFORE destroying anything.` | The pre-check could not read the pool's free space | Check the pool, then re-run `sever-vm-clone --continue <state-file>` |
| `WARN: Origin snapshot ... is ... — its space will not be freed and is not counted.` | The pre-check found the origin not destroyable (cloned or held), so its bytes stay out of the arithmetic | Informational |
| `FATAL: The copy-back of ... would not fit in pool ... — aborting BEFORE destroying anything.` | The pre-check arithmetic (free now + the original's diverged data + the destroyable origin snapshot) falls short of the copy-back need; the continuation lines give the numbers and the lightly-diverged-clone explanation | Nothing was destroyed and the fresh copies are safe in the holding pool; make room (or make the origin destroyable) and `--continue`, or `--rollback` everything |
| `FATAL: Could not capture the snapshot holds of ...; aborting with nothing destroyed.` / `FATAL: Could not release the snapshot holds of ...; aborting with nothing destroyed.` | The hold lifecycle around the destroy failed (held snapshots cannot be destroyed) | The disk's cutover aborts; resolve the holds and `--continue` |
| `INFO: Detaching iSCSI LUN ... / backstore ... (target ...) before the swap...` | Two-node: a live backstore pins the zvol's device node open, so the LUN and backstore come down before the destroy | Informational; both are re-created after the swap |
| `INFO: Destroying the original clone zvol ......` | The destroy side of the name-preserving swap | Informational |
| `INFO: Destroying .......` / `WARN: Could not destroy ....` (per snapshot, ahead of the original's dataset destroy) | Children-first sweep: every snapshot on the original — including replicated non-`@sever-*` ones — must be destroyed before the dataset itself, because `zfs destroy <dataset>` refuses while any child snapshot lives; the swapped-in copy re-creates them all | A `WARN` aborts the disk's cutover before the dataset destroy; resolve the snapshot (held? busy?) and `--continue` |
| `FATAL: zfs destroy ... failed — nothing else was touched.` | The original's destroy failed (busy) | Stop whatever holds it open, then re-run `sever-vm-clone --continue <state-file>` |
| `WARN: ... is already gone (crash between the destroy and the state write); continuing at the rename.` | Idempotent replay found the destroy already done | Informational |
| `INFO: Origin snapshot ... was not confirmed for destruction — kept; its space stays allocated.` / `INFO: Origin snapshot ... is already gone.` / `WARN: Origin snapshot ... is ... — kept; its space stays allocated and was not counted.` | Holding mode, per-disk origin handling: unconfirmed, already destroyed, or not destroyable | Informational |
| `INFO: Destroying the confirmed origin snapshot ... (its space makes room for the copy-back)...` / `INFO: ✓ ... destroyed — its pinned space is released for the copy-back.` | The destruction the pre-check counted on, run under a destroy lock with the destroyability re-checked | Informational |
| `FATAL: Origin snapshot ... became ... since the pre-check counted its space.` | A reference re-appeared under the lock | Make it destroyable again (or free other space), then re-run `--continue` |
| `FATAL: zfs destroy ... failed — aborting before the copy-back (its freed space was counted on).` | The counted-on origin destroy failed | Resolve (busy? held?), then re-run `--continue` |
| `INFO: Copy-back already landed on ...; skipping the send.` | A copy-back that finished before its phase marker is reused | Informational |
| `INFO: Copying ...@... back into ... (full engine copy)...` | Holding mode: the staged copy is pulled back into the source pool, only after the destructions that made the room | Informational |
| `FATAL: Copy-back transfer failed (rc=...); the original was already destroyed — the copy must complete.` | The copy-back send/receive failed | Re-run `sever-vm-clone --continue <state-file>` — it resumes from the receive resume token |
| `WARN: Could not set refreservation=none on ...; it keeps its volsize reserved.` | The post-receive sparse-zvol fix-up failed | Remove the reservation manually |
| `FATAL: No cutover snapshot on the copy-back ....` / `FATAL: ...@... exists with GUID ..., expected ... — not the verified copy.` / `FATAL: Copy-back GUID mismatch for ...: ...@... has ..., expected ... — not the verified copy.` | The copy-back verification failed | Investigate, then re-run `sever-vm-clone --continue <state-file>` |
| `INFO: Swapping ... into ......` | The rename into the original name — the swap itself | Informational |
| `FATAL: zfs rename ... → ... failed.` | The swap rename failed | Re-run `sever-vm-clone --continue <state-file>` |
| `WARN: The swap already happened (crash after the rename); continuing.` | Idempotent replay found the rename already done | Informational |
| `FATAL: Neither ... nor ... exists — there is nothing to swap in.` | Both the original name and the rename source are absent | Investigate the datasets; a fresh run re-copies |
| `FATAL: /dev/zvol/... did not come back via udev after the swap.` | The device node did not reappear within the udev wait | Check udev, then re-run `sever-vm-clone --continue <state-file>` |
| `INFO: Re-creating backstore ... on /dev/zvol/......` | Two-node: the backstore named for the zvol is rebuilt on the swapped-in device | Informational |
| `INFO: LUN for ... already exists (LUN ...); keeping it.` | Idempotent replay found the LUN already exported | Informational |
| `WARN: LUN ... was taken — letting targetcli assign a new one.` / `WARN: ... moved from LUN ... to LUN ... — the PVE config's by-path reference (…-lun-...) may need attention.` | The original LUN slot was occupied between the teardown and the re-export, so targetcli auto-assigned a new id | The swap itself is complete; update the PVE config's `by-path` disk reference to the new LUN id |
| `FATAL: Could not determine the LUN id of the re-created backstore ....` | The re-created LUN could not be parsed back from targetcli | Finish the re-export manually (targetcli) |
| `WARN: safe-iscsi-save skipped or failed — run it on ... once every expected LUN is active.` | safe-iscsi-save returned degraded (an expected LUN inactive), so the targetcli config was not saved | The severance stands; run safe-iscsi-save on the storage host once every expected LUN is active |
| `INFO: ✓ ... re-exported: target ..., LUN ..., backstore ....` | Milestone: the zvol is back on iSCSI at (normally) its original LUN id, so the compute host's by-path names are unchanged | Informational |
| `FATAL: Could not re-export ... over iSCSI — the zvol swap itself is done; finish the re-export manually (targetcli), then re-run: sever-vm-clone --continue <state-file>` | The re-export step of the two-node cutover failed | The name-preserving swap completed; recreate the backstore/LUN manually (or fix the cause) and re-run `--continue` to finish from the recorded phase |
| `FATAL: Cannot read the GUID of ...@... after the swap.` / `FATAL: Post-swap GUID mismatch on ...@...: ..., expected ... — the swapped-in zvol is not the verified copy.` | The post-swap GUID check failed | Investigate, then re-run `sever-vm-clone --continue <state-file>` |
| `WARN: Reapplying the captured holds on ... reported failures; the swap itself is complete.` | Re-applying the captured holds on the swapped-in zvol failed for at least one hold | Check the zvol's holds manually |
| `INFO: Destroying the holding-pool copy ......` / `INFO: The holding-pool copy ... is already gone.` | Holding mode: the staged copy's job is done once the copy-back is swapped in | Informational |
| `WARN: Could not destroy ...; remove it manually once nothing needs it.` | The holding-pool copy's destroy failed | Manual cleanup item; the severance itself is complete |
| `INFO: Destroying scaffolding snapshot ......` / `WARN: Could not destroy ....` | This tool's `@sever-*` snapshots are removed from the swapped-in zvol; a held or busy one is left in place and reported | Informational; the severance is complete either way |
| `INFO: ✓ ...: severed — origin-free under its own name (@..., GUID ...).` | Per-disk cutover outcome; the locks are released and the holds file removed | Informational |
| `INFO: Rescanning iSCSI on ... so the re-exported LUN(s) appear...` / `WARN: rescan-storage failed; run it on ... manually.` | End of a two-node cutover: the compute host's iSCSI sessions are rescanned so the re-exported LUN(s) reappear | On failure run `rescan-storage` on the compute host manually |
| `INFO: Removed the now-empty temp namespace ....` / `INFO: Temp namespace ... is not empty; left in place.` / `WARN: Could not lock ... for cleanup; left in place.` | Post-cutover namespace cleanup (same-pool, copy-back, and holding namespaces; a plain destroy only succeeds on an empty dataset) | Informational; anything else that landed there is left alone |
| `WARN: Temp namespace cleanup reported failures; remove leftovers manually.` | The cleanup worker returned non-zero | Remove the leftovers manually |
| `INFO: === Severance complete ===` | Final outcome; one `✓ ... — origin-free` line per zvol names its former origin | Informational |
| `INFO: State file removed — nothing left to continue or roll back.` | The run finished; the recovery handle is gone | Informational |
| `INFO: === Origin snapshot report ===` | Post-severance report header: the live clone list of every origin snapshot is re-read | Read the per-origin verdicts below |
| `INFO: ... (origin of ...) — already destroyed; nothing pinned.` | The origin snapshot is gone | Informational |
| `INFO: ... — still pinned (...): cloned by ...; left in place.` | Another clone keeps the snapshot alive | Informational; sever or destroy those clones to release the space |
| `INFO: ... — unpinned but held (... stays pinned); release the hold(s) to make it destroyable:` | No clone references it, but hold tags block destruction (each tag is listed on its own `hold:` line) | Release the listed holds to make it destroyable |
| `INFO: ... — unpinned: no clones, no holds; destroying it releases ....` | The origin is destroyable and its reclaimable size is named | Answer the destroy offer |
| `INFO: 0B is expected, not a defect: a snapshot's 'used' counts only its unique data, and every block here is still shared with the live dataset or its other snapshots. Destroying removes this snapshot's reference; the shared space returns as those references are destroyed.` | Continuation of the `releases 0B.` verdict: ZFS snapshot accounting counts a snapshot's unique delta only, so a fully-shared origin releases nothing immediately — normal after a severance whose blocks the live dataset still references | Informational; destroy anyway to remove the snapshot's reference, or keep it |
| `Destroy ...?` / `Type '...' to destroy it: ` | Typed destruction offer: a declined offer, an unreadable confirmation, or a non-matching answer leaves the snapshot untouched (`INFO: Left in place.` — with the reason) | y plus the exact snapshot name destroys it under a write lock, with the clone/hold checks repeated under the lock |
| `INFO: ✓ destroyed — its space is released.` | The offered origin snapshot was destroyed | Informational — the pinned space came back |
| `WARN: Could not lock ...; ... left in place.` / `WARN: ... is cloned again (...); left in place.` / `WARN: ... is held again; left in place.` / `WARN: The storage-side destroy of ... could not run; left in place.` | The under-lock re-checks (or the two-node arm) refused the destroy | The snapshot is untouched; retry later |
| `WARN: Could not destroy .....` | The locked destroy itself failed; a busy diagnosis follows | Address the busy cause |
| `INFO: === Rolling back sever-vm-clone ===` | `--rollback` header; the state file path is printed | Informational |
| `FATAL: Rollback impossible for ...: the original zvol was already destroyed (phase ...).` | Past the destroy there is no way back | Complete the swap instead: `sever-vm-clone --continue <state-file>` |
| `WARN: VM ... is ...; rolling back the storage anyway.` | A running owner does not block rollback (removing snapshots from a live zvol is safe in ZFS) | Informational |
| `INFO: --- Rollback: ... ---` / `INFO: Destroying the staged copy ......` / `INFO: No staged copy at ...; nothing to destroy.` | Per-disk rollback: the staged copy is destroyed, the `@sever-*` scaffolding removed, the released holds reapplied | Informational |
| `FATAL: zfs destroy ... failed.` | The staged copy's destroy failed during rollback | Resolve the cause, then re-run `sever-vm-clone --rollback <state-file>` |
| `WARN: Reapplying the holds on ... reported failures.` | Restoring the released holds failed for at least one hold | Check the zvol's holds manually |
| `FATAL: Rollback of ... failed.` | A disk's rollback worker failed | Resolve the cause, then re-run `sever-vm-clone --rollback <state-file>` |
| `INFO: === Rollback complete ===` | Rollback finished; the state file is removed | Informational |
| `FATAL: State file not found: ...` | `--continue`/`--rollback` named a missing file | Check the state file path the interrupted run printed |
| `FATAL: State file ... is malformed (...)` | The state file fails validation (missing diskcount/cutover_snap, a missing disk record, missing temp/fromsnap, or a verified phase without a GUID) | Re-run the severance with the original arguments |
| `WARN: State file ...: holding copy and copy-back of ... are in the same pool — treating as same-pool.` | A damaged state file lost the holding distinction | Informational; the cutover replays as same-pool |
| `FATAL: ... is not in the cutover state file ....` / `FATAL: Unknown worker command: ...` | The storage-side worker was invoked with a disk or command outside the state file | Internal-error class; re-run from the canonical entry |

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

## Two-Node iSCSI and VM Disks

Scripts in this group share the `FATAL: This script requires Proxmox VE (qm command not found).` environment gate and several `Pool must be one of: ...` / `vmid must be a number` validation fatals (all abort). The shared non-fatal rescan degradation is `WARN: Could not rescan ... — run 'sudo rescan-storage' on ... manually` / `WARN: Could not reach ...` (the compute host must be rescanned manually). The shared persistence failure is `FATAL: safe-iscsi-save failed — iSCSI configuration NOT saved` (new-vm-disk, remove-vm-disk, detach-vm-disk, restart-iscsi-services): the targetcli changes exist in memory only and may not survive a reboot — resolve the save failure and rerun the save.

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
| `INFO: ✓ Added to expected-backstores manifest` | The backstore was recorded in the manifest `safe-iscsi-save` requires; the manifest is created on first use when absent | Informational |
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
| `FATAL: Could not locate zfsdelfs` / `FATAL: Could not locate safe-iscsi-save` | A required helper script was not found | Script aborts; check the installation |
| `FATAL: Could not destroy zvol ...` | `zfsdelfs` failed — its own diagnostics precede this line; the destroy covers the zvol plus its snapshot children and their holds | Script aborts; address the reported cause |
| `WARN: This will PERMANENTLY DESTROY the following:` | Safety preamble before two confirmation prompts (VM stopped/disk removed, then sure-to-destroy); a delegated run over `ssh -t` shows both prompts on the calling terminal | y to both proceeds; anything else exits 0 with nothing destroyed |
| `WARN: LUN not found in target — skipping LUN removal` / `WARN: Backstore ... not found — skipping` | The iSCSI pieces are already absent | Informational; the zvol destroy continues |
| `WARN: Could not rescan ... — run 'sudo rescan-storage' manually` / `WARN: Could not locate rescan-storage ...` | The compute-host rescan after removal (or after a failed remote run — the LUN may already be gone) could not run | Run `sudo rescan-storage` manually |
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
| `WARN: Existing target(s) use the short name '...' under a different IQN prefix:` / `WARN: These are orphans (IQN prefix drift — the default prefix is date-derived).` | IQN-prefix drift guard: live targets carry this pool's target short name under another prefix (typically an earlier install in a different month) | The script probes each orphan's usage (see the `probe:` lines) before any action |
| `INFO: probe: ... — ACL initiators: ...` | Usage-probe context: the explicit ACL initiators configured on the target | Informational |
| `INFO: probe: ... — demo-mode ACLs (any initiator may log in; an empty ACL list is normal)` | Usage-probe context: the target runs demo-mode ACLs, so an empty ACL list is not evidence of being unused — the verdict comes from the compute-host check | Informational |
| `WARN: probe: ... — guest configs on ... still reference this target:` (+ the listed `.conf` files) | Usage probe: VM/container configs on the compute host still reference this target | The target is in use; it is never offered for deletion |
| `WARN: probe: ... — N live iSCSI session(s) attached` | Usage probe: an initiator is logged in to the target right now | The target is in use; it is never offered for deletion |
| `WARN: probe: could not verify ... — ... unreachable via SSH; treating as in use` | Usage probe: the compute host could not be reached, so usage cannot be verified | Restore compute-host reachability (or verify manually), then re-run |
| `INFO: probe: ... — no guest config on ... references this target and no live session exists (verified unused)` | Usage probe: the target is verified unused | Deletion may be offered |
| `Delete orphan target ...? (verified unused) (y/N):` | Confirmation prompt before `targetcli /iscsi delete` of a drifted target the script itself verified unused (no guest config references it, no live session) | Confirm to delete; anything in use or unverifiable is refused instead of prompted |
| `FATAL: Refusing to delete ... — it is in use or could not be verified.` | The usage probe found the target in use (or unverifiable), so deletion is not offered | Move the guest disks that reference it (or fix `IQN_PREFIX` in the node config), then re-run |
| `INFO: ✓ Deleted orphan target ...` | The confirmed orphan was removed | Informational |
| `WARN: Keeping orphan target ...` | The orphan was not deleted | The new target will be skipped for this pool |
| `FATAL: Skipping target creation for pool ... — remove the orphan target(s)` | A kept orphan keeps the LUN tree split, so the configured target is deliberately not created (the run exits 1) | Delete the orphan or fix `IQN_PREFIX` in node.conf, then re-run |
| `FATAL: Failed to create target` | `targetcli /iscsi create` failed for this pool | The loop continues with the next pool; fix targetcli and rerun |
| `INFO: ✓ Portal ...:3260 already exists` | Portal presence gate passed | Informational |
| `WARN: Could not add portal ...:3260` | Portal creation failed | Non-fatal; the target lacks a portal — rerun after fixing targetcli |
| `INFO: ✓ Demo-mode ACLs enabled (no explicit ACLs present)` | A TPG carrying no explicit ACLs was switched to demo mode (`generate_node_acls=1`) so initiators may log in; the dedicated storage network is the isolation boundary | Informational (persisted with the next save) |
| `WARN: Could not enable demo-mode ACLs on ...` | The `generate_node_acls` attribute could not be set | Initiator logins may be refused (`iscsiadm` error 24); set the attribute manually |
| `INFO: ✓ iSCSI configuration saved` | Changes were made and persisted | Informational |
| `INFO: ✓ No changes needed (all targets already configured)` | Nothing was created or added | Informational |
| `INFO: Targets created: ... / Targets existing: ... / Portals added: ...` | Final summary counters | Informational |

### [iscsi-add-encrypted-luns](../commands-and-modules/two-node.md#iscsi-add-encrypted-luns-storage-node)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: ✓ Added ... (LUN ...)` | Backstore created and mapped at its original LUN index (recovered from the saved config, scoped to the configured target), preserving the compute host's by-path symlinks | Informational |
| `INFO: ✓ Added ... (auto LUN)` | No original index was found for this target, so targetcli auto-assigned one (device-path stability not guaranteed) | Check the VM config's by-path references |

### [iscsi-recover-encrypted-luns](../commands-and-modules/two-node.md#iscsi-recover-encrypted-luns-storage-node)

Post-key-load recovery of encrypted LUNs (see the Proxmox integration guide's recovery section).

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: iscsi-recover-encrypted-luns: not applicable in single-node mode (no iSCSI)` | Single-node deployments have no iSCSI | Informational; nothing to do |
| `WARN: ... — device not available (keys not loaded?): ...` | The entry's zvol device node does not exist yet | Load ZFS keys (`zfs load-key`) and re-run |
| `INFO: ✓ ... already present on ...` | Idempotence gate: backstore and LUN mapping exist | Informational |
| `FATAL: ... has no recorded LUN index under ... in saveconfig.json` / `FATAL: Not guessing an index ...` | No recorded index exists for this backstore on the configured target; auto-assignment is deliberately refused (it can collide or pick the wrong slot when orphan targets exist) | Inspect `show-lun-map` and saveconfig.json, fix the conf entry, re-run |
| `FATAL: ... — could not create backstore for ...` / `FATAL: ... — could not map LUN ... on ...` | The targetcli step failed for this entry | The loop continues; fix targetcli and re-run |
| `FATAL: ... — LUN ... create reported success but mapping is absent` | Post-create verification failed | Inspect the target state with `show-lun-map` |
| `WARN: Load the missing ZFS keys (zfs load-key), then re-run this script.` | One or more entries were unavailable | Load keys and re-run |
| `INFO: Recovered: ... / Already OK: ... / Unavailable: ... / Failed: ...` | Per-run summary counters | Informational |
| `FATAL: safe-iscsi-save failed — configuration NOT saved` | The persistence step failed after changes | Changes exist in memory only; resolve and re-run |
| `INFO: === Recovery finished with unresolved entries — see lines above ===` | At least one entry failed or was unavailable (exit 1) | Resolve the listed entries and re-run |

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
| `FATAL: safe-iscsi-save: Config not found: ...` / `FATAL: safe-iscsi-save: Manifest not found: ...` | The saved config or manifest is absent | Create the manifest (one backstore name per line) |
| `FATAL: safe-iscsi-save: Manifest is empty or has no valid entries` (+ `... block backstore(s) are active — the manifest is broken.`) | The manifest holds no valid entries while block backstores are live — saving would drop those LUNs from the persisted config | Repair the manifest before saving |
| `INFO: safe-iscsi-save: manifest empty and no block backstores active — saving the target-only config` | The last VM disk was just removed: an empty manifest with zero active backstores is the legitimate target-only state, and the save proceeds | Informational |
| `FATAL: safe-iscsi-save: iSCSI target is degraded (... of ... LUNs active)` | Core safety gate: fewer active backstores than the manifest expects (keys not loaded, pool not imported) — the good saved config is deliberately not overwritten | Restore the missing LUNs (load keys/import pools); to force a save anyway, run `targetcli saveconfig` manually |
| `WARN: safe-iscsi-save: More backstores (...) than manifest (...)` | More active backstores than expected (orphans or a stale manifest) | Save proceeds; reconcile the manifest |
| `INFO: ✓ iSCSI configuration saved (.../... LUNs active)` | All gates passed and the config was persisted | Informational |
| `INFO: ✓ Pool LUN map refreshed` | The post-save [export-iscsi-state](#export-iscsi-state) hook recorded the LUN map on every online pool | Informational |
| `INFO: ✓ Pool LUN map refresh suppressed by caller` | The save ran with `SAFE_ISCSI_SAVE_SKIP_EXPORT_ISCSI_STATE=1` (set by [reconcile-iscsi-state](#reconcile-iscsi-state), which owns the refresh decision after a reconcile) | Informational; the caller refreshes the map itself |
| `WARN: export-iscsi-state failed — pool LUN map not refreshed` | The post-save hook ran but returned non-zero | The save itself stands; run `sudo export-iscsi-state` on the storage host and address its messages |
| `WARN: export-iscsi-state not available at ... — pool LUN map not refreshed` | The post-save hook script was not found at the expected path | The save itself stands; check the installation, then run `sudo export-iscsi-state` |

### [export-iscsi-state](../commands-and-modules/two-node.md#export-iscsi-state-storage-node)

Records the live iSCSI LUN topology as a pool-resident state map on every
online pool (two-node only; silently no-ops in single-node mode).

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: Unknown option: ...` | Unrecognized command-line argument | Usage shown; rerun with valid arguments |
| `FATAL: Must run on the storage host (...), not ...` / `FATAL: Must run as root (use sudo)` | Environment gate: wrong host or not root | Run via `sudo` on the storage host |
| `FATAL: targetcli not found. ...` | The LIO target stack is not installed on this storage host | Install `targetcli-fb` |
| `INFO: Targets: ..., backstores: ...` | Live-topology summary before rendering the map | Informational |
| `WARN: Pool ... is offline — state map not written there` | A configured pool is not imported; the map is still written to every online pool | Expected for deliberately offline pools; no action needed unless the pool should be online |
| `INFO: ✓ Created dataset ... (first use)` / `WARN: Could not create dataset ... — pool ... skipped` | The `<pool>/zfsutilities` dataset was created, or creation failed | On failure, check pool health/permissions and rerun |
| `WARN: Dataset ... has no usable mountpoint (...) — pool ... skipped` | The state dataset exists but is not mounted | Remount the dataset and rerun |
| `WARN: Could not create a temp file next to ...` / `WARN: Could not stage ...` / `WARN: Could not install ...` | An atomic install step failed for one pool's map | That pool keeps its previous map; check free space/permissions and rerun |
| `INFO: ✓ State map written to .../zfsutilities` / `INFO: ✓ State map written to ... pool(s)` | Per-pool and final write confirmations | Informational |
| `FATAL: Live state is degraded (... of ... expected backstores active)` | Safety gate: fewer backstores are active than the manifest (or the newest pool map) expects — recording this state would overwrite the recovery authority with a partial topology | The pool map was NOT overwritten; restore the missing LUNs (load keys/import pools), or rerun with `--force` to record the degraded state deliberately |
| `WARN: Live backstores (...) below expected (...) — recording anyway (--force)` | The degraded-state gate was overridden | The map now records the partial topology; re-export once the system is healthy |
| `INFO: Comparing live state against ...` | `--check` located the newest map and started the comparison | Informational |
| `INFO: ✓ No drift — live state matches the newest pool map` | `--check` found the live topology identical to the recorded map | Informational |
| `DRIFT: ...` (stdout lines) / `WARN: Drift detected between live state and the pool map (see DRIFT lines)` | `--check` found differences: moved LUNs, missing/extra backstores, ACL changes, or node-identity (`iqn_prefix`/`storage_ip`) drift — typically manual `targetcli` edits since the last export | Review the lines; run `sudo export-iscsi-state` to record the now-intended state |
| `FATAL: No iscsi-state.json found on any online pool — run export-iscsi-state first` | `--check` found no map to compare against | Run `sudo export-iscsi-state` once, then retry |
| `FATAL: Could not create a temp file for the state map` / `FATAL: State map was not written to any pool` | No temp file could be staged, or every configured pool was skipped (offline/unwritable) | Check pool availability and permissions; at least one online pool is required |

### [reconcile-iscsi-state](../commands-and-modules/two-node.md#reconcile-iscsi-state-storage-node)

Rebuilds the iSCSI LUN topology from the pool-resident state map after a
storage-host bare-metal restore (two-node only; silently no-ops in single-node
mode). Create-only; identity conflicts are refused per item.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: Unknown option: ...` / `FATAL: --from requires a file path` | Unrecognized command-line argument or a valueless `--from` | Usage shown; rerun with valid arguments |
| `FATAL: Must run on the storage host (...), not ...` / `FATAL: Must run as root (use sudo)` / `FATAL: targetcli not found. ...` | Environment gate: wrong host, not root, or the LIO target stack is missing | Run via `sudo` on the storage host; install `targetcli-fb` |
| `FATAL: Map file not found: ...` | The `--from` snapshot does not exist | Check the path (pool snapshots expose the map under `<pool>/zfsutilities/iscsi-state.json`) |
| `FATAL: No iscsi-state.json found on any online pool — run export-iscsi-state first` | No pool holds a recovery map | Run `sudo export-iscsi-state` once, then retry |
| `FATAL: ... contains no valid backstore records` / `FATAL: Map was generated on ..., not this host (...) — refusing to reconcile from it` | The map is empty/corrupt, or describes a different site's topology | Re-export the map on this host, or reconcile from a snapshot this host wrote |
| `INFO: Map: ... (generated ...)` / `INFO: Map records N backstore(s) on M target(s); live backstores: N` / `INFO: Live backstores: ..., discovered VM zvols: ...` | Run header: which map is the authority and the live-state summary | Informational |
| `INFO: Backstores to create:` / `INFO: LUN mappings to create (at recorded numbers):` / `INFO: ACL bindings to create:` (+ per-item lines) | The planned recovery actions, shown before the `y/N` confirmation | Review, then confirm (or rerun with `--dry-run` first) |
| `WARN: Skipped (zvol missing — entry kept in the pool map):` (+ `... zvol ... does not exist (offline pool or deleted)` / `... device ... not available (keys not loaded?)`) | A map entry's zvol is gone, so it cannot be recreated; the entry stays in the pool map for when the zvol returns | Import the pool / load keys / restore the dataset, then re-run; deliberately deleted disks need no action |
| `FATAL: Refused (identity conflict — resolve manually):` (+ `... backstore exists but points at ... (map: ...)` / `... mapped live at ... LUN ..., map records ... — never remapped` / `... LUN ... on ... is held by ...` / `... target ... does not exist live — run setup-iscsi-targets first` / `... map records disagree ...`) | Safety gate: recreating this entry could attach the wrong disk or split the LUN tree, so the item is refused and the run continues with the rest | Resolve by hand (delete the conflicting live object or restore the recorded layout), then re-run; never auto-remapped |
| `INFO: Live backstores not in the map (left untouched):` | Live objects the map does not know (typical with `--from` older than live state) | Informational; they merge into the map at the next export |
| `INFO: ...: demo-mode ACLs (...) self-generate on initiator login — not created` | The TPG admits every initiator (demo mode), so recorded ACL nodes are not recreated | Informational |
| `INFO: ✓ Created backstore ... -> ...` / `INFO: ✓ Mapped ... to .../lun...` / `INFO: ✓ Created ACL ... on ...` / `INFO: ✓ Granted N LUN(s) to ACL ...` | Per-item apply confirmations (backstores get `emulate_tpu=1`; LUNs at the recorded numbers) | Informational |
| `FATAL: Failed to create backstore ...` / `FATAL: Failed to map ... to .../lun...` / `FATAL: Failed to create ACL ... on ...` | A targetcli create call returned non-zero; the run continues with the remaining items | Check the targetcli error (device missing, target state); the summary counts failed actions and the run exits 1 |
| `INFO: ... is encrypted but unmapped in the map — not added to the encrypted LUNs config` | An encrypted backstore the map records as unmapped; the conf entry needs a target | Informational; the attach flow re-flags it when mapped |
| `INFO: ✓ Re-flagged N encrypted backstore(s)` | Ensured backstores whose zvol is encrypted were re-added to `iscsi-encrypted-luns.conf` (it regresses with the OS disk) | Informational; `safe-iscsi-save` regenerates a consistent boot config from it |
| `INFO: ✓ Regenerated ... from the map` / `WARN: Regenerated manifest is empty; keeping ... unchanged` / `FATAL: Could not install regenerated manifest at ...` | The expected-backstores manifest was rebuilt from the ensured set (or the rewrite was refused) | On the FATAL, check permissions on the manifest directory and rerun |
| `WARN: Nothing was ensured — skipping safe-iscsi-save` | No map entry could be ensured, so there is nothing to persist | Address the skip/refuse lines first |
| `INFO: ✓ iSCSI configuration saved` / `FATAL: safe-iscsi-save failed — configuration may not be persistent` / `FATAL: safe-iscsi-save not available at ...` | Persistence result (the save runs with its map hook suppressed — reconcile owns the refresh) | On FATAL, run `sudo safe-iscsi-save` manually after resolving its messages |
| `INFO: ✓ Pool LUN map refreshed` | The reconcile completed and the pool map now records the rebuilt topology | Informational |
| `WARN: Pool LUN map left unchanged — skipped/refused entries are preserved in it for recovery` | Safety gate: the reconcile was partial, so refreshing would overwrite the recovery authority and drop the skipped entries | Resolve the skipped/refused items (import pools, fix conflicts) and re-run; the map refreshes then |
| `WARN: export-iscsi-state not available at ... — pool LUN map not refreshed` / `WARN: export-iscsi-state failed — pool LUN map not refreshed` | The refresh step could not run | Check the installation, then run `sudo export-iscsi-state` |
| `WARN: Could not gather VM disk references from ... — VM-config cross-check skipped` | The compute host was unreachable over ssh; the target-side reconcile still stands | Informational; rerun `--dry-run` later to see the cross-check |
| `WARN: VM ... (...) ... references ... LUN ... — still missing (map: ...; refused/skipped/...)` | A VM disk reference the map knows about could not be restored (its item was refused or skipped) | Resolve that item's reason above; the run exits 1 while any ref remains missing |
| `WARN: VM ... (...) ... references ... LUN ... — no map entry for it` (+ `INFO: candidate unexported zvol: ...`) | A VM references a LUN the map never recorded (map older than the attach, or compute-host config drift) | Candidates are informational only — nothing is guessed; re-attach deliberately or repair the config |
| `INFO: [dry-run] VM ...: ... LUN ... would be restored by the planned mapping (...)` | `--dry-run` cross-check note for a ref the plan would restore | Informational |
| `INFO: [dry-run] Would regenerate the manifest, run safe-iscsi-save, refresh the pool map, and rescan ...` / `FATAL: ... identity conflict(s) must be resolved first` | `--dry-run` close-out | Apply with `--yes`/confirmation once the plan is acceptable |
| `INFO: No target-side changes needed` | Live topology already matches the map; only the finishes (manifest regen, save, refresh, rescan) ran | Informational |
| `WARN: Aborted — no changes made` | The `y/N` confirmation was declined (or stdin was empty) | Re-run and confirm, or use `--yes` |
| `INFO: === Summary ===` (+ created/ensured counts, `WARN: Skipped (zvol missing): N`, `FATAL: Refused (identity conflict): N`, `FATAL: Actions failed during apply`, `FATAL: safe-iscsi-save did not persist the rebuilt tree`, `INFO: VM refs unresolved: ...`) | End-of-run tally | `INFO: ✓ Done` (exit 0) when complete; `FATAL: Reconcile incomplete — resolve the reported items and re-run` (exit 1) otherwise |

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
| `→ Snapshot has clone dependents: ...` | One or more clones were created from this snapshot (the fix hint names `sever-vm-clone`) | Sever or destroy the dependent clones first |
| `→ One or more snapshots of ... have clone dependents.` | Dataset target: some snapshot under it is a clone origin (the fix hint names `sever-vm-clone`) | Sever or destroy the dependent clones first |
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
| `WARN: Could not re-read the partition table of ... Run partprobe ... (or rescan-storage, or reboot) before reusing the disk.` | Every partition-table re-read attempt failed after a wiping step (`partprobe`/`blockdev --rereadpt` missing or failed; the wipe itself stands) | Run `partprobe` manually; stale partition nodes may linger |
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
| `INFO: Skipping ... (canmount=off)` | Gated skip — the dataset can never be mounted: excluded from the parent-mount plan as an ancestor, or skipped as a directly selected filesystem | That dataset skipped; other selected targets still handled |
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

GUI scrub engine: queue/state machine for start/pause/resume/stop, backup-coordinated pause/resume, external-scrub adoption, and systemd timer toggles. All messages from this module are also appended to the persistent event log `/var/log/zfsutilities/scrub-manager.log` regardless of which process issued them.

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
| `INFO: Scrub on '...' paused and requeued as pending (active scrubs at target)` | Displacement — active scrubs exceeded the target, so the lowest-priority live scrub was paused and its pool requeued | Resumes from existing progress when a slot frees |
| `INFO: Scrub queue order updated` | The user's scrub priority order was persisted | Informational |
| `INFO: Pools added to scrub queue: ...` / `INFO: Pools removed from scrub queue: ...` | Start/stop enqueued/cleared pools (paused re-queued, finished cleared) | The tick loop starts/stops them |
| `WARN: Giving up on scrub for '...' after ... failed start attempts` | Three consecutive failed start/resume attempts | Pool dropped to given-up for this run; investigate |
| `VERB: External scrub detected on '...'` | The queue observed a scrub it did not start (once per episode) | Pool adopted into the active bucket |
| `VERB: External pause detected on '...'` | A pool's scrub was paused outside the queue (tracked active pool, or an untracked paused pool adopted) — treated as user-paused | Pool moved to the paused bucket; no auto-resume |
| `VERB: External resume detected on '...'` | A paused pool's scrub was resumed outside the queue | Pool moved back to the active bucket |
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
| `INFO: ZFSUTILITIES_STATE_DIR is redirected; legacy state migration skipped ...` | The state dir is env-redirected away from the default, so the sweep is fenced (it would move real home-directory legacy files into the redirected directory); `ZFSUTILITIES_ALLOW_REDIRECTED_MIGRATION=1` opts in deliberately (the bash `migrate_zfsutilities_state` carries the same fence) | Informational; export the opt-in only for deliberate redirected migrations |
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
| `⚠: matplotlib not installed — Performance-page charts fall back to the built-in Cairo renderer. Install the system package python3-matplotlib (a pip --user install is invisible to a root-run GUI).` | The optional chart renderer's import failed for this user; the GUI keeps working on its Cairo fallback | Install `python3-matplotlib` system-wide if the matplotlib charts are wanted |
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
| `INFO: No ...; using legacy /etc/zfsutilities-deploy.conf` | The modern deploy.conf is absent; the legacy flat file is honored instead | Informational |
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
| `Existing iSCSI targets on this host all use the prefix below — keep the default so tooling and targets stay in one namespace.` | IQN-prefix prompt annotation: every live target shares one prefix, so that prefix (not the date-derived default) is offered — a recovery install can no longer silently fork the target namespace | Keep the default (empty answer); mixed live prefixes fall back to the date-derived default without this note |
| `⚠  WARNING: IQN prefix mismatch` / `Proceed with the new IQN prefix anyway? (y/N):` | The live LIO target tree holds targets for the configured short names under a different IQN prefix (reinstall in a different month, or carried-over saveconfig.json); proceeding would leave orphan targets while LUN tooling maps to the new prefix. The installer probes each drifted target's usage first (see the `probe:` lines) and only offers to continue when every one is verified unused | Answer N and fix `IQN_PREFIX` in the node config (or delete the orphan targets); y continues at your explicit request |
| `FATAL: Aborting: a drifted target is still in use or could not be verified ...` | The usage probe found a drifted target in use (guest config reference or live session) or the compute host was unreachable, so continuing is not offered | Move the guest disks that reference it, delete the orphan manually, or fix `IQN_PREFIX`, then re-run |
| `FATAL: Aborting: resolve the IQN prefix mismatch, then re-run the installer.` | The drift confirmation was declined | Fix the prefix mismatch and re-run |
| `⚠ No pools configured. You can add them to ... later.` | No pools were entered | Edit the node config later |
| `⚠ setup-iscsi-targets not found — you must create iSCSI targets manually` | The helper is absent from the repository | Create the targets with targetcli manually |
| `✓ targetcli found` / `✓ rtslib-fb-targetctl.service found` | The LIO target stack is present on the storage host | Informational |
| `✗ ... not found` (targetcli / rtslib-fb-targetctl.service) | A target-stack piece is missing; an install offer follows (why-it-matters lines precede it) | y installs `targetcli-fb`; anything else aborts with manual-install guidance |
| `Install the LIO target stack now (apt-get install targetcli-fb)?` | The target-stack install offer | y installs; anything else aborts cleanly |
| `✗ Could not install targetcli-fb.` | The package installation failed (manual command printed) | Install manually and re-run the installer |
| `✓ rtslib-fb-targetctl.service enabled` / `⚠ Could not enable rtslib-fb-targetctl.service` | Post-install service enablement outcome | Verify the service manually if warned |
| `✓ open-iscsi (iscsiadm) found on ...` / `✓ open-iscsi installed on ...` | The initiator is present (or was installed) on the compute host | Informational |
| `✗ open-iscsi (iscsiadm) not found on ...` | The initiator is missing; an install offer follows (why-it-matters lines precede it) | y installs via apt; anything else aborts with manual-install guidance |
| `Install open-iscsi on ... now?` | The initiator install offer | y installs; anything else aborts cleanly |
| `✗ Could not install open-iscsi on ...` | The apt install failed (manual command printed) | Install manually and re-run the installer |
| `Ensuring iscsid.socket is active on ...` / `✓ iscsid.socket active on ... (socket-activated iscsid)` | Initiator readiness: Debian socket-activates iscsid, so the listening socket is the state `iscsiadm` (and PVE storage) rely on; checked on both the found and installed paths | Informational |
| `⚠ Could not verify iscsid.socket on ...` | The socket could not be enabled or verified | Check `systemctl status iscsid.socket` on the compute host |
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

### [upgrade-zfsutilities](../commands-and-modules/commands.md#upgrade-zfsutilities)

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: No active version is deployed under ...` | No `current` symlink in the version base | Install first with install-single-node or install-two-node |
| `FATAL: curl is required but not installed.` | The upgrade needs curl to reach GitHub | Install curl and re-run |
| `FATAL: Cannot reach GitHub (...)` | Network failure against the release API | Check connectivity and re-run |
| `FATAL: GitHub returned an HTTP error for ...` / `FATAL: GitHub response is missing tag_name` | No releases or an unexpected API response | Verify the repository has published releases |
| `INFO: Nothing to upgrade — the active version is not older than the latest release.` | The deployed version matches or exceeds the latest release (also blocks re-deploying over the active version) | Informational; exit 0 |
| `Download <version> and deploy it to every deployment target? [y/N]` | Deploy consent before anything is fetched or changed | y proceeds to the change scan; N aborts with nothing touched |
| `FATAL: Download failed: ...` / `FATAL: Could not extract the downloaded release tarball.` / `FATAL: The downloaded release is not a ZFSutilities tree (...)` | The release tarball could not be staged | Check the release assets and re-run |
| `WARN:   Downloaded tree VERSION (...) does not match release tag ...` | Tag and VERSION disagree in the release | Verify the release was tagged correctly before continuing |
| `FATAL: Cannot reach root@<host> over SSH. Aborting before any changes.` | A deployment target is unreachable | Fix access to the host and re-run; nothing was modified |
| `FATAL: Scan failed on <host> — aborting before any changes.` | The remote change scan failed mid-flight | Investigate the host; nothing was modified |
| `INFO: --- <host> ---` ... `INFO:   modified:/added:/removed:` listings | The pre-approval change report for one deployment target | Review, including the printed unified diffs |
| `WARN:   Active version <v> has no MANIFEST.sha256 and no release tarball is available for it — local modifications ... CANNOT be detected.` | That host's tree cannot be verified and no baseline could be captured | Confirm you are willing to proceed without verification |
| `INFO:   Active version <v> has no MANIFEST.sha256 and no release tarball is available for it. A baseline manifest was captured from the current tree: ... every future upgrade scans against the captured baseline.` | Trust-on-first-upgrade: no baseline was obtainable (pre-manifest version, untagged release), so a manifest of the current tree was captured on that host | Informational; modifications predating this upgrade can no longer be distinguished from pristine content |
| `WARN:   Diff unavailable: no pristine source for version <v> (untagged release?) — modification hashes only.` | Detection worked from hashes, but no original exists to diff against | Compare the salvaged copies manually if needed |
| `Archive the changes listed above on their hosts and continue the upgrade? [y/N]` | Salvage consent — approving archives then supersedes the changes | y archives under `salvaged-changes/` and continues; N aborts with nothing touched |
| `FATAL: Salvage failed on <host> — aborting before deployment.` | Archiving failed mid-consent | Nothing was deployed; re-run after investigating |
| `INFO:   Salvaged on <host>: N file(s) -> salvaged-changes/<v>/<ts>/` / `INFO:   Combined diff saved: ...` | Where the archived edits and their diff live | Re-apply any change you still want, then re-deploy |
| `FATAL: deploy-version failed. The deployment is incomplete — investigate before activating anything.` | The deployment step failed after salvage | Run deploy-version manually and investigate |
| `INFO: === upgrade-zfsutilities complete ===` ... `INFO:   Deployed version: <v> — NOT activated` ... `INFO:     this host:  sudo switch-version <v>` / `INFO:     <host>:  ssh root@<host> switch-version <v>` | Final report: deployed version, unchanged active version, salvage locations, and the per-host activation commands | Run the printed commands when you are ready to activate |
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

Emits no log messages. `rootcheck()` prints a bare "Please run as root." and terminates the process (exit 1) when not root.

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
| `INFO: Edit link re-anchored to ...` | The edit link's baked path was remapped onto the tree whose `docs/site/` the viewer is serving | Editor opens the served tree's markdown |
| `INFO: Launched editor for ...: ...` | An `openmd://` edit link spawned the configured editor (privileges dropped when root) | Editor opens |
| `WARN: Documentation edit target not found: ...` | Neither the re-anchored nor the baked edit-link target exists on disk | Editor opens the re-anchored path; status shows the miss |
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
| `WARN: Scheduler drop-in convergence skipped: ...` | OSError during launch-time drop-in convergence (config/profile read failure) | Best-effort skip; the run continues without the cron-log fd fallback |
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
| `FATAL: Unhandled exception in profile runner:` (followed by the traceback) | Top-of-run catch-all: an unexpected exception escaped the tab-type runner | Traceback and rc=1 session trailer written to the session log; exit 1 |
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

Workload-profile dialogs: Rewrite Data (zfs rewrite restripe) and Apply Profile, plus profile edit/delete guards. The rewrite script's messages are embedded in the generated bash script; the completion summary reports what `zfs rewrite -v` actually rewrote (one output line per successfully rewritten file, captured through `tee`), because rc=0 alone covers both "rewrote files" and "nothing to rewrite".

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `FATAL: could not mount ... to rewrite data` | The temporary mount for `zfs rewrite` failed (bash-embedded) | Script exits 1; the Rewrite Data step fails |
| `WARN: could not unmount ... after rewrite` | The temporary mount could not be restored to unmounted (bash-embedded) | Rewrite rc still reported; dataset stays mounted |
| `INFO: Rewrite Data: N files rewritten on ...` (bash-embedded) | This dataset's rewrite finished; the captured `-v` output counted N successfully rewritten files | Informational |
| `INFO: Rewrite Data: nothing to rewrite on ... (zfs rewrite rewrote 0 files)` (bash-embedded) | `zfs rewrite` exited 0 having rewritten no files (empty or already-conformant dataset) | Informational |
| `WARN: Rewrite Data: could not count rewritten files on ...` (bash-embedded) | The captured output could not be counted (count recorded as -1) | The rewrite rc still governs the step; the summary reports the count as incomplete |
| `WARN: Rewrite Data is available only on the storage host` / `WARN: Applying profiles is available only on the storage host` | Two-node gates — invoked on the compute node | Action aborted |
| `WARN: Select at least one dataset to rewrite data` | Empty dataset list | Action aborted |
| `WARN: Rewrite Data supports filesystem datasets only; zfs rewrite cannot act on a volume's block device (...)` | The selection contains volumes | Action aborted |
| `WARN: Rewrite Data requires OpenZFS 2.3.4+` | Capability gate — zfs rewrite unsupported | Action aborted |
| `WARN: Dataset runner not available` / `A dataset action is already running` | Runner missing / busy guard | Action aborted |
| `WARN: Could not read properties for ...: ...` | The mountpoint/apply property query failed (plain-language explanation appended) | Rewrite preflight aborted / that dataset skipped in Apply |
| `WARN: Cannot rewrite data for ...: mountpoint is '...'` | Mountpoint none/legacy/- cannot be rewritten via path | Aborted |
| `WARN: Rewrite Data requires the physical_rewrite pool feature on ... (zpool set feature@physical_rewrite=enabled ...)` | Per-pool feature-flag gate | Aborted; enable the feature to proceed |
| `INFO: Rewrite Data cancelled for ...` | The step was cancelled after the Yes/No confirm | Skipped; locks released; refresh |
| `WARN: Rewrite Data failed for ... (rc=...)` | A rewrite step exited non-zero | Operation aborted; locks released |
| `INFO: Rewrite Data complete for ... (N files rewritten)` | All rewrite steps finished rc=0; the captured per-dataset counts sum to N | Informational |
| `INFO: Rewrite Data rewrote nothing for ... — zfs rewrite reported 0 files` | All steps finished rc=0 and every dataset recorded zero rewritten files — the summary never claims completion of work that did not happen | Informational |
| `INFO: Rewrite Data finished for ... (rc=0; rewrite summary unavailable)` | Steps finished rc=0 but the results file could not be read | Informational; see the session log for the per-dataset lines |
| `INFO: Rewrite Data finished for ... (rewrite summary incomplete — see log)` | At least one dataset's count could not be determined | Informational |
| `INFO: Rewrite Data finished for ... (no summary for N dataset(s) — see log)` | Datasets whose step recorded no line (e.g. an early mount failure); not folded into success | Informational |
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

Writes the `/etc/cron.d` file from the active profiles and converges the cron/logrotate drop-ins to the current format at GUI startup and at the start of every scheduled run.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `VERB: Cron file updated: ...` | The cron file was successfully rewritten | Informational |
| `FATAL: Could not write cron file ...: ...` | OSError writing the cron file | Exception re-raised; the caller shows an error dialog (convergence catches it and continues) |
| `WARN: Could not read drop-in ...: ...` | A persisted drop-in could not be read during convergence | The drop-in is left untouched; convergence skips it |
| `WARN: Cron drop-in not converged: ...` / `WARN: Logrotate drop-in not converged: ...` | OSError rewriting a drop-in during convergence | Best-effort skip; the run or GUI startup continues |

### [logrotate_manager](../commands-and-modules/python-modules.md#logrotate_managerpy)

Writes the logrotate drop-in that rotates the persistent cron and scrub-manager logs.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `VERB: Logrotate file updated: ...` | The logrotate drop-in was successfully (re)written | Informational |
| `FATAL: Could not write logrotate file ...: ...` | OSError writing the drop-in | Exception re-raised; the caller shows an error dialog (convergence catches it and continues) |

### [alignment_page](../commands-and-modules/python-modules.md#alignment_pagepy)

Alignment view of the Performance tab: off-thread sample collection and rendering.

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `WARN: Alignment sample gathering failed: ...` | The background collection thread hit an unexpected exception | The refresh is skipped and the pending flag cleared (the view keeps its last sample); the next scheduled refresh retries |

### [alignment_dialogs](../commands-and-modules/python-modules.md#alignment_dialogspy)

Workload-survey dialog on the Performance tab (Alignment view).

| Message prefix | Meaning | Response |
| -------------- | ------- | -------- |
| `INFO: Workload survey saved for ... (...)` | The survey entry was persisted and the Alignment view refreshes in place | Informational |

# Profiles

A **profile** is a saved set of tab settings that can be run on demand or
scheduled.  Profiles let you turn a carefully configured Backup,
Offsite, Restore, Retention, or Scrub tab into a repeatable, automatable job
without re-entering the settings each time.

## Profile types

| Type      | GUI tab   | What it runs                                                                                                                                                                                                                 |
| --------- | --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Backup    | Backup    | rsync pulls, ZFS send/receive, retention (prunes only the datasets the active send/receive steps back up, on both the source and destination sides; skipped when no send/receive steps are active), pre/post scripts |
| Offsite   | Offsite   | Copy snapshots to an offsite pool                                                                                                                                                                                            |
| Restore   | Restore   | Full dataset restore                                                                                                                                                                                                         |
| Retention | Retention | Prune snapshots by retention policy                                                                                                                                                                                          |
| Scrub     | Pools     | Start and monitor pool scrubs                                                                                                                                                                                                |

Profile names are built from the username, tab type, and a custom suffix, for
example `root-backup-daily` or `root-retention-weekly`.

## Creating and editing profiles

1. Open the GUI tab you want to save (Backup, Offsite, Restore, Retention, or Pools->Scrub).
2. Configure the settings the way you want them.
3. Click **Add Profile to Schedule** and enter a unique suffix.
4. The profile is written to `~/.config/zfsutilities/profiles/` as a JSON file.

To edit a profile, recall it from the tab where it was created, change the
settings, and Add Profile to Schedule using the original name.

## Scheduling profiles

Profiles can be scheduled through the GUI's scheduler or by editing cron
entries directly.  The GUI generates cron lines that run
`profile_runner.py run <profile_name>`.

When a scheduled profile is still running and cron tries to start it again,
the second invocation waits up to 10 minutes for the first run to finish.
If the first run finishes in time, the second run proceeds normally.
If the first profile is still running after 10 minutes, the second invocation exits
cleanly with code `0` and logs an informative message.  This prevents cron
from sending duplicate-run email spam.  Cron stdout/stderr for every
scheduled profile is piped through a timestamp stamper into
`/var/log/zfsutilities/cron.log` (each line is prefixed with its write time)
so that errors occurring before the profile creates its own log remain
visible.  Every `%` written into a job line — the stamper's format string, a
profile name, or a schedule condition — is backslash-escaped, because cron
terminates a job's command at the first unescaped `%` and would otherwise
kill the run with a shell error that `MAILTO=""` discards.  Once the session
log exists it is the run's record: cron job lines
launch the runner with `ZFSUTILITIES_FROM_CRON=Y`, and the runner silences
its own output streams from that point on, so the cron log holds only the
pre-log failures (a failed session-log creation keeps full output there as
the fallback record).  Each cron firing also leaves two breadcrumb lines in
the cron log — a stamped `Scheduled run started (cron)` line when the runner
starts and a `Scheduled run finished (cron) ... rc=N` line when it exits —
so a schedule that has stopped firing shows up as missing breadcrumbs rather
than an empty log.  An unhandled runner crash is recorded in the session
log — traceback plus a failed trailer — instead of the silenced streams.
The scheduler drop-ins (the cron file and its logrotate configuration) are
converged automatically: every GUI startup and every scheduled-run start
regenerates them whenever their content no longer matches what the
installed version generates, so an upgrade can never leave an outdated
cron line in place.  As a further guard, the runner recognizes a pre-fence
cron line by its redirect into the cron log itself and silences its output
even without the marker.
The cron log is rotated weekly by logrotate with compressed, non-root-
readable generations, and it — plus every rotated copy — is listed on the
GUI's **Logs** tab.

The Dashboard **Tasks** list shows a waiting profile with the status
`Waiting since <time>`; cancel it there like any other task.

## Running profiles from the command line

```bash
sudo python3 /usr/local/lib/zfsutilities/current/bin/profile_runner.py run root-backup-daily
```

Append `--ignore-schedule` to run immediately even when today does not match
the profile's cron day-of-week ordinal (for example `6#2`, second Saturday);
without it, a manual run on a non-matching day is skipped exactly like a
scheduled run.  The GUI's **Run Now** button uses the same flag.

The runner operates in headless mode.  By default it waits up to 10 minutes
when a ZFS step encounters a dataset lock conflict, then aborts if the lock is still held.  

## Concurrent execution

Multiple profiles can run at the same time when they touch **disjoint**
datasets or pools.  For example:

- A backup of `tank/vm-100` can run at the same time as a backup of
  `tank/vm-200`.

ZFS Utilities does not use a global "one job at a time" restriction.  Instead, each
operation acquires a short-term lock on only the datasets or pools it needs.
This maximizes parallelism while preventing dangerous collisions.

## Conflict resolution

When two jobs need the same dataset or pool, the second one either waits or
fails safely.  In interactive/GUI mode you are prompted.  In headless/cron
mode the runner waits up to 10 minutes by default, then fails safely if the
lock is still held.  Examples:

- Two backup profiles targeting `tank/share` cannot run simultaneously.  The
  second waits; if the first finishes within the timeout, the second runs.
- A prune job on `tank` cannot run while a backup of `tank/share` is in
  progress.  The prune waits, then proceeds once the backup releases the lock.
- A dataset destroy cannot run while a backup is sending or receiving that
  dataset.  The destroy waits, then proceeds once the backup step finishes.

No data corruption occurs in these cases.  If the timeout expires, the blocked
job logs a warning and exits, and the scheduler does not treat a duplicate-run suppression as an error.

## Scope alignment

When two profiles send overlapping dataset trees to the
same destination, they must send the same trees. 

For example, if the offsite job snapshots only `NVME1/proxmox` and sends it to
`fivebays`, but the daily backup sends all of `NVME1` to `fivebays`, the
destination `fivebays/NVME1` will end up with `@offsite` snapshots that the
source `NVME1` does not have.  The next daily backup must roll those `@offsite`
snapshots back before it can receive the `@dailybackup` snapshot.

ZFS Utilities warns about this mismatch in three places:

1. When you save the Backup tab or Offsite tab settings in the GUI.
2. When you save a profile.
3. When a profile runs.

**Action:** Align the source scopes.  Either change the backup source to match
the offsite source/includes (for example, back up `NVME1/proxmox` instead of
`NVME1`), or change the offsite job to snapshot the same tree the backup sends.

## Operational guidance

- Avoid scheduling the same profile so frequently that runs overlap, unless you
  intentionally want the duplicate-run suppression to keep one running while the
  other is skipped.
- Do not run `zfsscruball` from the command line while scrub profiles are
  actively managed by the GUI or the scheduler.
- Do not edit retention policies or pool lists while a profile is
  running.
- If a scheduled profile fails with `rc=9`, another job was holding a dataset
  lock at that moment.  Check the session log for the conflicting operation.
- A scrub profile finishes with `rc=1` when a pool's scrub could not be started
  or resumed after a few retries (the pool is reported as "gave up on" in the
  session log). The remaining pools in the profile are still scrubbed normally.
- Every rsync pull step verifies its destination's ZFS mount chain before
  running. A dataset on the destination path that is unmounted — or that
  reports itself mounted while its path is unreachable because a later mount
  covers an ancestor (a *shadowed* mount) — refuses that step with a WARN
  naming the dataset, and the run finishes with `rc=11`. Shadowing typically
  appears on pools whose root has `canmount=noauto`: at boot the children
  mount onto directories in the root filesystem before the pool root is
  mounted, and a later manual mount of the pool root covers them. Restore the
  parent-first mount order (unmount the affected filesystems, then remount
  top-down or via `zfs mount -a`) before re-running the profile. A missing
  destination directory on a *clean* chain is created automatically below the
  deepest dataset mountpoint, so a fresh destination needs no manual setup.
  The Dashboard detects unreachable mounts on its own and enables **Repair
  Mount Order**, so fixing the condition is one approved action rather than a
  shell session.
- A run cancelled from the Dashboard (or by SIGTERM/SIGINT to the runner)
  finishes with `rc=125`, a `cancelled` history entry, and a `# END: cancelled`
  session trailer — distinct from a failure. The in-flight step is terminated
  and no further steps run.

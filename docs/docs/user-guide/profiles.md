# Profiles

A **profile** is a saved set of tab settings that can be run on demand or
scheduled.  Profiles let you turn a carefully configured Backup,
Offsite, Restore, Retention, or Scrub tab into a repeatable, automatable job
without re-entering the settings each time.

## Profile types

| Type      | GUI tab   | What it runs                                                                                                                                                                                                                 |
| --------- | --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Backup    | Backup    | rsync pulls, ZFS send/receive, retention (prunes only the datasets the active send/receive steps back up, on both the source and destination sides; falls back to whole-pool pruning when none are active), pre/post scripts |
| Offsite   | Offsite   | Copy snapshots to an offsite pool                                                                                                                                                                                            |
| Restore   | Restore   | Full dataset restore                                                                                                                                                                                                         |
| Retention | Retention | Prune snapshots by retention policy                                                                                                                                                                                          |
| Scrub     | Pools     | Start and monitor pool scrubs                                                                                                                                                                                                |

Profile names are built from the username, tab type, and a custom suffix, for
example `root-backup-daily` or `root-retention-weekly`.

## Creating and editing profiles

1. Open the GUI tab you want to save (Backup, Offsite, Restore, Retention, or Pools->Scrub).
2. Configure the settings the way you want them.
3. Click **Save Profile** and enter a unique suffix.
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
scheduled profile is appended to `/var/log/zfsutilities/cron.log` so that
errors occurring before the profile creates its own log remain visible.

The Dashboard **Running Tasks** list shows a waiting profile with the status
"Waiting for profile lock".

## Running profiles from the command line

```bash
sudo python3 /usr/local/lib/zfsutilities/current/bin/profile_runner.py run root-backup-daily
```

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

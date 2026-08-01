# Profiles

A **profile** is a saved set of tab settings that can be run on demand or
scheduled through cron.  Profiles let you turn a carefully configured Backup,
Offsite, Restore, Retention, or Scrub tab into a repeatable, automatable job
without re-entering the settings each time.

## Profile types

| Type      | GUI tab      | What it runs                                            |
| --------- | ------------ | ------------------------------------------------------- |
| Backup    | Backup       | rsync pulls, ZFS send/receive, retention, pre/post scripts |
| Offsite   | Offsite      | Copy snapshots to an offsite pool                       |
| Restore   | Restore      | Two-step full/incremental restore                       |
| Retention | Retention    | Prune snapshots by retention policy                     |
| Scrub     | Pools        | Start and monitor pool scrubs                           |

Profile names are built from the username, tab type, and a custom suffix, for
example `root-backup-daily` or `root-retention-weekly`.

## Creating and editing profiles

1. Open the GUI tab you want to save (Backup, Offsite, Restore, Retention, or
   Scrub).
2. Configure the settings the way you want them.
3. Click **Save Profile** and enter a unique suffix.
4. The profile is written to `~/.config/zfsutilities/profiles/` as a JSON file.

To edit a profile, load it from the **Profiles** menu or dialog, change the
settings, and save again.

## Scheduling profiles

Profiles can be scheduled through the GUI's scheduler or by editing cron
entries directly.  The GUI generates cron lines that run
`profile_runner.py run <profile_name>`.

When a scheduled profile is still running and cron tries to start it again,
the second invocation exits cleanly with code `0` and logs an informative
message.  This prevents cron from sending duplicate-run email spam.  Cron
stdout/stderr for every scheduled profile is appended to
`/var/log/zfsutilities/cron.log` so that errors occurring before the runner
creates its own session log remain visible.

## Running profiles from the command line

```bash
sudo python3 /usr/local/lib/zfsutilities/current/bin/profile_runner.py run root-backup-daily
```

The runner operates in headless mode, so it aborts immediately if it encounters
a dataset lock conflict rather than prompting interactively.

## Concurrent execution

Multiple profiles can run at the same time when they touch **disjoint**
datasets or pools.  For example:

- A backup of `tank/vm-100` can run at the same time as a backup of
  `tank/vm-200`.
- A scrub of `pool-a` can run at the same time as a backup of `pool-b`.

ZFS Utilities does not use a global "one job at a time" mutex.  Instead, each
operation acquires a short-term lock on only the datasets or pools it needs.
This maximizes parallelism while preventing dangerous collisions.

## Conflict resolution

When two jobs need the same dataset or pool, the second one either waits (in
interactive/GUI mode) or fails safely (in headless/cron mode).  Examples:

- Two backup profiles targeting `tank/share` cannot run simultaneously.  The
  second fails with a lock-conflict message.
- A prune job on `tank` cannot run while a backup of `tank/share` is in
  progress.  The prune is skipped safely; no snapshots are lost.
- A dataset destroy cannot run while a backup is sending or receiving that
  dataset.

No data corruption occurs in these cases.  The blocked job logs a warning and
exits, and cron does not treat a duplicate-run suppression as an error.

## Scope alignment

A backup profile and an offsite profile that send overlapping datasets to the
same destination must agree on which datasets receive `@offsite` snapshots.

For example, if the offsite job snapshots only `NVME1/proxmox` and sends it to
`fivebays`, but the daily backup sends all of `NVME1` to `fivebays`, the
destination `fivebays/NVME1` will end up with `@offsite` snapshots that the
source `NVME1` does not have.  The next daily backup must roll those `@offsite`
snapshots back before it can receive the `@dailybackup` snapshot.

ZFS Utilities warns about this mismatch in three places:

1. When you save the Backup tab or Offsite tab settings in the GUI.
2. When you save a profile that creates or overwrites a profile.
3. When `profile_runner.py` runs a backup or offsite profile headlessly.

**Action:** Align the source scopes.  Either change the backup source to match
the offsite source/includes (for example, back up `NVME1/proxmox` instead of
`NVME1`), or change the offsite job to snapshot the same tree the backup sends.

## Operational guidance

- Avoid scheduling the same profile so frequently that runs overlap, unless you
  intentionally want the duplicate-run suppression to keep one running while the
  other is skipped.
- Do not run `zfsscruball` from the command line while scrub profiles are
  actively managed by the GUI or cron.
- Do not edit retention policies or pool lists while a headless profile is
  running.
- If a scheduled profile fails with `rc=9`, another job was holding a dataset
  lock at that moment.  Check the session log for the conflicting operation.

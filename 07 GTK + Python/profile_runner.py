#!/usr/bin/env python3
"""Headless profile runner for cron execution.

Usage:
    python3 profile_runner.py run <profile_name>
"""

import fcntl
import json
import os
import re
import shlex
import subprocess
import sys
import time
from contextlib import nullcontext

from datetime import datetime

_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from logging_config import log_msg, session_log_context, truncate_session_log
from log_index import LogIndex
from config_core import load_config, prune_old_logs, SESSION_LOG_DIR
from feature_config import (
    generate_snapshot_name,
    generate_offsite_snapshot_name,
    remove_snapfile,
    get_pool_names,
)
from backup_history import _parse_human_size, build_entry, add_history_entry
from command_builders import (
    BashStep,
    _dryrun_assignments,
    parse_rsync_endpoint as _parse_rsync_endpoint,
    build_rsync_command as _build_rsync_command,
    build_send_receive_command as _build_send_receive_command,
    build_pre_backup_command as _build_pre_backup_command,
    build_post_backup_command as _build_post_backup_command,
    build_retention_command as _build_retention_command,
)
from offsite_runner import detect_offsite_pool, build_offsite_step_command
from restore_runner import compute_restore_params, build_restore_command
from profile_manager import load_profile
from scrub_manager import (
    ScrubQueue, get_all_pool_scrub_states, ScrubState,
    start_scrub, pause_scrub, resume_scrub, stop_scrub,
    attach_step_scrub_callbacks,
)
from cron_manager import _parse_weekday, _match_weekday_ordinal

# Directory for per-profile advisory locks. Override for testing.
PROFILE_LOCK_DIR = os.environ.get(
    "ZFSUTILITIES_PROFILE_LOCK_DIR", "/run/lock/zfs/profiles"
)

# Regex: received\s+(\S+)\s+stream\s+in\s+([\d.]+)\s+seconds
# Purpose: Match the final summary line emitted by `zfs receive` on stderr,
#          which reports actual bytes received and elapsed time.
# Group 1: Human-readable size  e.g. "312B", "1.23GiB", "5.00M"
# Group 2: Elapsed seconds      e.g. "0.25", "1234.56"
# Examples:
#   "received 312B stream in 0.25 seconds (1.20K/sec)" -> match
#   "received 1.23GiB stream in 45.67 seconds" -> match
#   "sending tank/data@snap" -> no match
_ZFS_RECEIVED_RE = re.compile(r'received\s+(\S+)\s+stream\s+in\s+([\d.]+)\s+seconds')


def _parse_bytes_from_log(path):
    """Read a session log and sum all `zfs receive` byte counts.

    Returns total bytes as an int.  Returns 0 if the file is missing
    or unreadable.
    """
    if not path or not os.path.isfile(path):
        return 0
    total = 0
    try:
        with open(path, "r", errors="replace") as fh:
            for line in fh:
                m = _ZFS_RECEIVED_RE.search(line)
                if m:
                    total += _parse_human_size(m.group(1))
    except OSError:
        pass
    return total


def _check_weekday_ordinal(weekday_field):
    """Return True if today matches the weekday field, including any #n/#L suffix.

    Standard cron ignores weekday ordinals, so profile_runner.py applies this
    guard at runtime. A plain weekday value (no '#') always matches.
    """
    if "#" not in weekday_field:
        return True
    try:
        base, specs = _parse_weekday(weekday_field)
    except ValueError:
        return False
    today = datetime.now()
    wd = today.weekday() + 1  # cron: 0=Sun, 1=Mon; python: 0=Mon
    if today.weekday() == 6:
        wd = 0
    if int(base) != wd:
        return False
    return _match_weekday_ordinal(today, wd, specs)


def _profile_lock_path(profile_name):
    """Return the lock file path for *profile_name*.

    The profile name is sanitized so it can be used safely as a filename.
    """
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", profile_name)
    return os.path.join(PROFILE_LOCK_DIR, f"{safe}.lock")


def acquire_profile_lock(profile_name, timeout=1.0):
    """Acquire an exclusive advisory lock for *profile_name*.

    Creates the lock directory and lock file if needed. Returns a tuple
    (fd, lock_path) on success, or (None, lock_path) if the lock is already
    held by another process. With *timeout* > 0, retry briefly with a short
    sleep before giving up.
    """
    os.makedirs(PROFILE_LOCK_DIR, exist_ok=True)
    lock_path = _profile_lock_path(profile_name)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    flags = fcntl.LOCK_EX | fcntl.LOCK_NB

    if timeout is None:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
        except OSError as exc:
            os.close(fd)
            raise
        return fd, lock_path

    deadline = time.time() + max(0.0, float(timeout))
    acquired = False
    while True:
        try:
            fcntl.flock(fd, flags)
            acquired = True
            break
        except (BlockingIOError, OSError):
            if time.time() >= deadline:
                break
            time.sleep(0.05)

    if not acquired:
        os.close(fd)
        return None, lock_path

    # Record metadata so the Dashboard can identify the owning profile and PID.
    timestamp = datetime.now().isoformat(timespec="seconds")
    try:
        with open(lock_path, "w") as f:
            f.write(
                json.dumps(
                    {
                        "profile": profile_name,
                        "pid": os.getpid(),
                        "started": timestamp,
                    }
                )
                + "\n"
            )
    except OSError:
        pass

    return fd, lock_path


def release_profile_lock(fd, lock_path):
    """Release a profile lock and close its file descriptor."""
    if fd is None:
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        os.close(fd)
    except OSError:
        pass
    # Best-effort cleanup of the lock file; failure is harmless.
    try:
        if os.path.exists(lock_path):
            os.unlink(lock_path)
    except OSError:
        pass


def _is_dataset_encrypted(path):
    """Check whether *path* resides inside an encrypted ZFS dataset.

    Walks up the directory tree until `zfs list` succeeds, then checks
    the `encryption` property. Returns True only if the dataset is
    actually encrypted (not '-', 'off', or empty).
    """
    candidate = os.path.normpath(path)
    while candidate and candidate != "/":
        result = subprocess.run(
            ["zfs", "list", "-H", "-o", "name", candidate],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            dataset = result.stdout.strip()
            enc_result = subprocess.run(
                ["zfs", "get", "-H", "-o", "value", "encryption", dataset],
                capture_output=True, text=True,
            )
            if enc_result.returncode == 0:
                val = enc_result.stdout.strip()
                return val not in ("", "-", "off")
            return False
        candidate = os.path.dirname(candidate)
    return False


_session_log_file = None
_session_start_time = None
_last_log_size_check = 0.0

# How often to check the session log size while a profile is running.
_PROFILE_LOG_SIZE_CHECK_INTERVAL = 5  # seconds

# Log path used on the source host for pull-step rsync output in headless mode.
_REMOTE_RSYNC_LOG_PATH = "/var/log/zfsutilities/rsync-pull.log"


def _create_session_log_file(tab_type, profile_name):
    global _session_log_file
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    # Regex: [^A-Za-z0-9_-]
    # Purpose: Sanitize tab_type and profile_name for safe use in log filenames.
    #          Strips any character that is not a letter, digit, hyphen, or underscore.
    # Example: "Backup Profile #1" -> "BackupProfile1"
    safe_type = re.sub(r"[^A-Za-z0-9_-]", "", tab_type)
    safe_name = re.sub(r"[^A-Za-z0-9_-]", "", profile_name)
    path = os.path.join(
        SESSION_LOG_DIR, f"{ts}_{safe_type}_profile-{safe_name}.log"
    )
    os.makedirs(SESSION_LOG_DIR, exist_ok=True)
    try:
        open(path, "a").close()
    except OSError:
        path = None
    _session_log_file = path
    return path


def _write_session_trailer(rc=None, bytes_transferred=0):
    global _session_log_file, _session_start_time
    if not _session_log_file:
        return
    duration = time.time() - _session_start_time if _session_start_time else 0.0
    status = f"rc={rc}" if rc is not None else "done"
    trailer = f"# END: {status}, duration={duration:.1f}s"
    if bytes_transferred:
        trailer += f", bytes={bytes_transferred}"
    try:
        with open(_session_log_file, "a") as fh:
            fh.write(trailer + "\n")
    except OSError:
        pass

    # Persist final metadata so the Logs tab does not need to rescan.
    try:
        index = LogIndex.load()
        index.set_status(
            _session_log_file,
            status="Done" if rc == 0 else "Failed",
            duration=duration,
            bytes_transferred=bytes_transferred,
        )
        index.save()
    except Exception as e:
        log_msg(f"WARN: Could not update log index: {e}")


def _write_raw_line(session_log_file, line):
    """Append a raw subprocess line to the session log file with a timestamp."""
    if not session_log_file:
        return
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(session_log_file, "a") as fh:
            fh.write(f"{ts}  {line}\n")
    except OSError:
        pass


def _maybe_truncate_session_log(session_log_file):
    """Truncate the session log if it has grown beyond the cap.

    Called periodically while a profile is running.  Returns True if truncation
    occurred.
    """
    global _last_log_size_check
    if not session_log_file:
        return False
    if truncate_session_log(session_log_file):
        log_msg("WARN: Session log exceeded size cap and was truncated")
        try:
            index = LogIndex.load()
            index.remove(session_log_file)
            index.save()
        except Exception as e:
            log_msg(f"WARN: Could not reset log index after truncation: {e}")
        return True
    return False


def _run_command(step, session_log_file=None):
    global _last_log_size_check
    if step.pre_callback is not None:
        try:
            step.pre_callback()
        except Exception as exc:
            log_msg(f"WARN: Pre-step callback failed: {exc}")
    try:
        log_msg(f"INFO: {step.description}")
        log_msg(f"DEBUG: {' '.join(shlex.quote(str(c)) for c in step.command)}")
        env = os.environ.copy()
        env["ZFSUTILITIES_HEADLESS"] = "Y"
        if session_log_file:
            env["ZFSUTILITIES_LOG_FILE"] = session_log_file
            env["ZFSUTILITIES_LOG_INHERIT"] = "Y"
        try:
            process = subprocess.Popen(
                step.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
            )
            try:
                with process.stdout:
                    for line in process.stdout:
                        line = line.rstrip("\n")
                        print(line, file=sys.stderr)
                        _write_raw_line(session_log_file, line)
                        now = time.time()
                        if now - _last_log_size_check >= _PROFILE_LOG_SIZE_CHECK_INTERVAL:
                            _last_log_size_check = now
                            _maybe_truncate_session_log(session_log_file)
            finally:
                returncode = process.wait()
            if returncode != 0:
                log_msg(f"WARN: Step exited with rc={returncode}")
            return returncode
        except Exception as e:
            log_msg(f"FATAL: Error running step: {e}")
            return 1
    finally:
        if step.post_callback is not None:
            try:
                step.post_callback()
            except Exception as exc:
                log_msg(f"WARN: Post-step callback failed: {exc}")


def _run_step_list(steps, session_log_file=None):
    max_rc = 0
    for step in steps:
        rc = _run_command(step, session_log_file=session_log_file)
        if rc == 9:
            log_msg("FATAL: Operation aborted due to lock conflict in headless mode.")
            return rc
        if rc != 0:
            if step.fatal:
                return rc
            if rc > max_rc:
                max_rc = rc
    return max_rc


def run_backup_profile(profile, config, parent_dir, session_log_file=None):
    cfg = profile["config"]
    dryrun = profile.get("dry_run", False)
    if dryrun:
        log_msg("INFO: Dry run mode enabled — no changes will be made")
    variables = cfg["variables"]
    label = variables.get("label", "dailybackup").strip() or "dailybackup"
    nextsnap = generate_snapshot_name(label)
    log_msg(f"INFO: Backup snapshot: {nextsnap}")
    steps = []

    if cfg.get("pre_backup_script_enabled", False):
        script = cfg.get("pre_backup_script", "").strip()
        if script:
            if dryrun:
                log_msg(f"INFO: Dry-run: Would run pre-backup command")
            else:
                steps.append(_build_pre_backup_command(script))

    if cfg.get("pull_steps_active", True):
        active_pulls = [
            (s["source"], s["dest"])
            for s in cfg.get("pull_steps", []) if s.get("active")
        ]
    else:
        active_pulls = []
        log_msg("INFO: Pull steps disabled by user; skipping")

    done_hosts = set()

    for source, dest in active_pulls:
        src_host, src_path = _parse_rsync_endpoint(source)
        if src_host is None and src_path.startswith("/mnt/"):
            mount_path = src_path.rstrip("/")
            if not os.path.ismount(mount_path):
                log_msg(f"WARN: Skipping {source} -> {dest}: {mount_path} is not mounted")
                continue
            try:
                os.listdir(mount_path)
            except OSError:
                log_msg(f"WARN: Skipping {source} -> {dest}: {mount_path} is not accessible")
                continue
        if dryrun:
            log_msg(f"INFO: Dry-run: Would rsync {source} -> {dest}")
        else:
            steps.append(_build_rsync_command(source, dest, remote_log_path=_REMOTE_RSYNC_LOG_PATH))

    # Optional ZFS keys backup
    zfs_keys_path = cfg.get("zfs_keys_path", "").strip()
    zfs_keys_dest = cfg.get("zfs_keys_dest", "").strip()
    if zfs_keys_path and zfs_keys_dest:
        src_host, src_path = _parse_rsync_endpoint(zfs_keys_path)
        if src_host not in done_hosts:
            done_hosts.add(src_host)
        if src_host is None and src_path.startswith("/mnt/"):
            mount_path = src_path.rstrip("/")
            if not os.path.ismount(mount_path):
                log_msg(f"WARN: Skipping ZFS keys {zfs_keys_path} -> {zfs_keys_dest}: {mount_path} is not mounted")
            else:
                try:
                    os.listdir(mount_path)
                except OSError:
                    log_msg(f"WARN: Skipping ZFS keys {zfs_keys_path} -> {zfs_keys_dest}: {mount_path} is not accessible")
                else:
                    if not _is_dataset_encrypted(zfs_keys_dest):
                        log_msg(
                            "WARN: Skipping ZFS keys backup — destination is not "
                            "encrypted. Set zfs_keys_dest to an encrypted dataset."
                        )
                    elif dryrun:
                        log_msg(
                            f"INFO: Dry-run: Would rsync {zfs_keys_path} -> "
                            f"{zfs_keys_dest}"
                        )
                    else:
                        steps.append(_build_rsync_command(
                            zfs_keys_path, zfs_keys_dest,
                            remote_log_path=_REMOTE_RSYNC_LOG_PATH,
                        ))
        else:
            if not _is_dataset_encrypted(zfs_keys_dest):
                log_msg(
                    "WARN: Skipping ZFS keys backup — destination is not "
                    "encrypted. Set zfs_keys_dest to an encrypted dataset."
                )
            elif dryrun:
                log_msg(
                    f"INFO: Dry-run: Would rsync {zfs_keys_path} -> {zfs_keys_dest}"
                )
            else:
                steps.append(_build_rsync_command(
                    zfs_keys_path, zfs_keys_dest,
                    remote_log_path=_REMOTE_RSYNC_LOG_PATH,
                ))

    pause_scrubs = cfg.get("pause_scrubs", False)
    for step in cfg.get("send_receive_steps", []):
        if step.get("active"):
            sr_step = _build_send_receive_command(
                step["source"], step["dest"],
                variables, parent_dir, nextsnap,
                dryrun=dryrun,
            )
            attach_step_scrub_callbacks(
                sr_step, step["source"], step["dest"],
                enabled=pause_scrubs, dry_run=dryrun,
            )
            steps.append(sr_step)

    post = cfg.get("post_steps", {})
    if post.get("run_retention", False):
        pools = get_pool_names(config) or None
        steps.append(_build_retention_command(
            parent_dir, label, pools=pools, dryrun=dryrun
        ))

    if not steps:
        log_msg("WARN: No active steps to run")
        return 1

    fatal_rc = _run_step_list(steps, session_log_file=session_log_file)

    # If the only failures were non-fatal warnings, still remove snapfile.
    if post.get("remove_snapfile", True) and fatal_rc == 0:
        if dryrun:
            log_msg("INFO: Dry-run: Skipping snapfile cleanup (preserved for real run)")
        else:
            remove_snapfile()
            log_msg("INFO: Removed snapshot file")

    # Post-backup script (always runs if enabled, even after a fatal error)
    if cfg.get("post_backup_script_enabled", False):
        script = cfg.get("post_backup_script", "").strip()
        if script:
            if dryrun:
                log_msg("INFO: Dry-run: Would run post-backup command")
            else:
                rc = _run_command(
                    _build_post_backup_command(script),
                    session_log_file=session_log_file,
                )
                if rc != 0:
                    log_msg(f"WARN: Post-backup command exited with rc={rc}")

    return fatal_rc


def run_offsite_profile(profile, config, parent_dir, session_log_file=None):
    cfg = profile["config"]
    dryrun = profile.get("dry_run", False)
    if dryrun:
        log_msg("INFO: Dry run mode enabled — no changes will be made")
    variables = cfg["variables"]
    nextsnap = generate_offsite_snapshot_name()
    log_msg(f"INFO: Offsite snapshot: {nextsnap}")
    candidates = cfg.get("offsite_pools", [])
    offsite_pool = detect_offsite_pool(candidates)
    if offsite_pool is None:
        log_msg("FATAL: No offsite pool online. Cannot proceed.")
        return 1
    log_msg(f"INFO: Offsite pool: {offsite_pool}")
    steps = []

    pause_scrubs = cfg.get("pause_scrubs", False)
    for step in cfg.get("steps", []):
        if not step.get("active"):
            continue
        source = step["source"]
        dest = step["dest"].replace("<offsite>", offsite_pool)
        offsite_step = build_offsite_step_command(
            source, dest, variables, parent_dir, nextsnap,
            step.get("includes", ""), step.get("excludes", ""),
            dryrun=dryrun,
        )
        attach_step_scrub_callbacks(
            offsite_step, source, dest,
            enabled=pause_scrubs, dry_run=dryrun,
        )
        steps.append(offsite_step)

    if not steps:
        log_msg("WARN: No active steps to run")
        return 1
    return _run_step_list(steps, session_log_file=session_log_file)


def run_restore_profile(profile, config, parent_dir, session_log_file=None):
    cfg = profile["config"]
    dryrun = profile.get("dry_run", False)
    if dryrun:
        log_msg("INFO: Dry run mode enabled — no changes will be made")
    source = cfg.get("source", "").strip()
    dest = cfg.get("dest", "").strip()
    do_part1 = cfg.get("do_part1", True)
    do_part2 = cfg.get("do_part2", True)
    if not source or not dest:
        log_msg("FATAL: Source and destination must be specified")
        return 1
    removequalifiers, destfs = compute_restore_params(source, dest)
    restore_step = build_restore_command(
        source, removequalifiers, destfs, parent_dir,
        cfg.get("variables", {}), do_part1, do_part2,
        dryrun=dryrun,
    )
    attach_step_scrub_callbacks(
        restore_step, source, dest,
        enabled=cfg.get("pause_scrubs", False), dry_run=dryrun,
    )
    return _run_command(
        restore_step,
        session_log_file=session_log_file,
    )


def run_retention_profile(profile, config, parent_dir, session_log_file=None):
    cfg = profile["config"]
    dryrun = profile.get("dry_run", False)
    if dryrun:
        log_msg("INFO: Dry run mode enabled — no changes will be made")
    label = cfg.get("prune_label", "dailybackup").strip() or "dailybackup"
    pools = cfg.get("prune_pools", [])
    if not pools:
        log_msg("WARN: No pools selected for pruning")
        return 1
    fatal_rc = 0
    for pool in pools:
        bash_cmd = (
            f'source ~/bashinit; bashinit; mydir="{parent_dir}"; '
            f'source "$mydir/zfscleanup"; '
            f'{_dryrun_assignments(dryrun)}'
            f'autoproceed="Y"; '
            f'releaseholds="Y"; '
            f'cleanup "{pool}" "" "{label}"'
        )
        rc = _run_command(
            BashStep(
                ["bash", "-c", bash_cmd],
                f"Prune {pool} (label={label})",
                is_rsync=False,
                fatal=True,
            ),
            session_log_file=session_log_file,
        )
        if rc != 0:
            fatal_rc = rc
    return fatal_rc


def run_scrub_profile(profile, config, parent_dir, session_log_file=None):
    """Run a scrub profile: start scrubs on specified pools and poll until done."""
    cfg = profile["config"]
    pool_names = cfg.get("pools", [])
    simultaneous = cfg.get("simultaneous", 1)
    if not pool_names:
        log_msg("WARN: No pools specified for scrub profile")
        return 1

    def _scrub_log(msg):
        log_msg(msg)
        if session_log_file:
            _write_raw_line(session_log_file, msg)

    queue = ScrubQueue(target=simultaneous)
    queue.add_pending(pool_names)
    _scrub_log(f"INFO: Scrub profile started on {len(pool_names)} pool(s), target={simultaneous}")

    max_idle_ticks = 60  # ~10 minutes at 10s interval before giving up
    idle_ticks = 0

    while True:
        states = get_all_pool_scrub_states()
        queue.tick(states)
        summary = queue.summary()
        _scrub_log(
            f"INFO: Scrub queue — active={summary['active']} "
            f"pending={summary['pending']} paused={summary['paused']} "
            f"finished={summary['finished']}"
        )

        if summary["active"] == 0 and summary["pending"] == 0:
            if summary["paused"] > 0:
                # All remaining are paused — wait a bit then bail
                idle_ticks += 1
                if idle_ticks >= max_idle_ticks:
                    _scrub_log("WARN: Scrub profile timed out with paused pools")
                    break
            else:
                # All done
                break
        else:
            idle_ticks = 0

        import time
        time.sleep(10)

    _scrub_log("INFO: Scrub profile complete")
    return 0


def main():
    if len(sys.argv) < 3 or sys.argv[1] != "run":
        print("Usage: profile_runner.py run <profile_name>", file=sys.stderr)
        sys.exit(1)

    profile_name = sys.argv[2]

    lock_fd, lock_path = acquire_profile_lock(profile_name, timeout=1.0)
    if lock_fd is None:
        log_msg(
            f"INFO: Profile '{profile_name}' is already running; "
            "skipping duplicate invocation"
        )
        sys.exit(0)

    try:
        profile = load_profile(profile_name)
        if profile is None:
            log_msg(f"FATAL: Profile not found: {profile_name}")
            sys.exit(1)

        config = load_config()
        prune_old_logs(config.get("log_retention_days", 30))

        script_dir = os.path.dirname(os.path.realpath(__file__))
        version_root = os.path.dirname(script_dir)
        bin_dir = os.path.join(version_root, "bin")
        parent_dir = bin_dir if os.path.isfile(os.path.join(bin_dir, "zfsdailybackup")) else version_root

        tab_type = profile.get("tab_type", "")

        global _session_start_time, _last_log_size_check
        _session_start_time = time.time()
        _last_log_size_check = time.time()
        _create_session_log_file(tab_type, profile_name)

        ctx = session_log_context(_session_log_file) if _session_log_file else nullcontext()
        with ctx:
            log_msg(f"INFO: Running profile: {profile_name} (type={tab_type})")

            weekday_field = profile.get("cron", {}).get("weekday", "*")
            if not _check_weekday_ordinal(weekday_field):
                log_msg(
                    f"INFO: Skipping profile {profile_name}: today does not match "
                    f"weekday ordinal '{weekday_field}'"
                )
                _write_session_trailer(rc=0)
                sys.exit(0)

            runners = {
                "backup": run_backup_profile,
                "offsite": run_offsite_profile,
                "restore": run_restore_profile,
                "retention": run_retention_profile,
                "scrub": run_scrub_profile,
            }
            runner = runners.get(tab_type)
            if runner is None:
                log_msg(f"FATAL: Unknown tab type: {tab_type}")
                rc = 1
            else:
                rc = runner(profile, config, parent_dir, _session_log_file)

            log_msg(f"INFO: Profile {profile_name} finished (rc={rc})")
            _maybe_truncate_session_log(_session_log_file)
            bytes_transferred = _parse_bytes_from_log(_session_log_file)
            duration = time.time() - _session_start_time if _session_start_time else 0.0
            result = "success" if rc == 0 else "failed"
            entry = build_entry(
                timestamp=datetime.now().isoformat(),
                run_type=tab_type if tab_type else "backup",
                name=profile_name,
                duration=duration,
                result=result,
                bytes_transferred=bytes_transferred,
                log_file=_session_log_file,
            )
            add_history_entry(entry)
            _write_session_trailer(rc=rc, bytes_transferred=bytes_transferred)
            sys.exit(rc)
    finally:
        release_profile_lock(lock_fd, lock_path)


if __name__ == "__main__":
    main()

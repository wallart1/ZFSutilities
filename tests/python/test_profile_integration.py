"""Integration tests for concurrent profile execution.

These tests verify that the Phase 0--5 locking pieces cooperate when two
profile_runner.py executions overlap.  They run each profile in a separate
subprocess so the dataset lock manager sees different PIDs, just like real
concurrent cron jobs or GUI runs.
"""

import io
import multiprocessing
import os
import re
import sys
import time
import unittest
from unittest.mock import patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

import profile_runner
import zfs_lock_manager as zlm
from test_support import temp_config_dir, temp_lock_dir


# ---------------------------------------------------------------------------
# Bash-script parsing helpers for the mock Popen implementation.
# ---------------------------------------------------------------------------


def _extract_send_receive_datasets(script):
    """Return (sourcefs, destfs) from a send-receive bash script, or (None, None)."""
    source_match = re.search(r'sourcefs="([^"]+)"', script)
    dest_match = re.search(r'destfs="([^"]+)"', script)
    if source_match and dest_match:
        return source_match.group(1), dest_match.group(1)
    return None, None


def _extract_cleanup_pool(script):
    """Return the pool name being pruned by a cleanup script, or None."""
    # Direct: cleanup "pool" "" "label"
    m = re.search(r'cleanup\s+"([^"]+)"\s+""', script)
    if m:
        return m.group(1)
    # Loop: for pool in "tank" "archive"; do cleanup "$pool" ...
    m = re.search(r'for pool in ([^;]+); do', script)
    if m:
        first = m.group(1).split()[0]
        return first.strip('"')
    return None


# ---------------------------------------------------------------------------
# Mock Popen that simulates per-dataset locking inside bash steps.
# ---------------------------------------------------------------------------


class _LockingPopen:
    """Popen stand-in that acquires zfs_lock_manager locks while "running".

    The lock type and datasets are inferred from the bash script content so
    the test exercises the same hierarchical conflict rules used by the real
    bash scripts.
    """

    def __init__(self, delay=0.5):
        self.delay = delay

    def __call__(self, cmd, **kwargs):
        if not (isinstance(cmd, list) and len(cmd) >= 3 and cmd[0] == "bash" and cmd[1] == "-c"):
            return self._completed("", rc=0)

        script = cmd[2]
        datasets = []

        source, dest = _extract_send_receive_datasets(script)
        if source and dest:
            datasets.extend([source, dest])

        pool = _extract_cleanup_pool(script)
        if pool:
            datasets.append(pool)

        if not datasets:
            # Pre/post scripts or other non-ZFS steps succeed immediately.
            return self._completed("", rc=0)

        # Acquire locks in deterministic order to avoid deadlocks.
        datasets = sorted(set(datasets))
        lock_ids = []
        try:
            for ds in datasets:
                lock_id = zlm.acquire(ds, "w", f"mock step for {ds}")
                lock_ids.append(lock_id)
        except RuntimeError as exc:
            for lock_id in lock_ids:
                zlm.release(lock_id)
            return self._completed(str(exc), rc=1)

        # Hold the locks for the simulated duration of the step.
        time.sleep(self.delay)

        for lock_id in lock_ids:
            zlm.release(lock_id)

        return self._completed("", rc=0)

    @staticmethod
    def _completed(stdout, rc=0):
        class _MockProc:
            def __init__(self, stdout, rc):
                self.stdout = io.StringIO(stdout)
                self.returncode = rc

            def wait(self):
                return self.returncode

        return _MockProc(stdout, rc)


# ---------------------------------------------------------------------------
# Profile fixtures.
# ---------------------------------------------------------------------------


def _backup_profile(source, dest, label="dailybackup"):
    return {
        "config": {
            "variables": {"label": label},
            "pull_steps": [],
            "send_receive_steps": [
                {"source": source, "dest": dest, "active": True},
            ],
            "post_steps": {"run_retention": False, "remove_snapfile": False},
            "pre_backup_script_enabled": False,
            "post_backup_script_enabled": False,
        }
    }


def _retention_profile(pool, label="dailybackup"):
    return {
        "config": {
            "prune_label": label,
            "prune_pools": [pool],
        }
    }


# ---------------------------------------------------------------------------
# Subprocess worker.
# ---------------------------------------------------------------------------


def _run_profile_worker(profile, runner_name, result_queue):
    """Run a profile in a child process and report the result.

    The temp directory overrides from the parent process are inherited via
    fork, so the child uses the same isolated lock/config directories.
    """
    runner = getattr(profile_runner, runner_name)
    with patch("profile_runner.subprocess.Popen", side_effect=_LockingPopen(delay=0.5)):
        rc = runner(profile, {}, "/bin")
    result_queue.put(rc)


# ---------------------------------------------------------------------------
# Test cases.
# ---------------------------------------------------------------------------


class TestConcurrentProfiles(unittest.TestCase):
    """Concurrent profile execution scenarios using separate subprocesses."""

    @staticmethod
    def _wait_for_lock(dataset, locked=True, timeout=3.0):
        """Poll until *dataset* is locked or unlocked.

        Uses zfs_lock_manager.check, which returns False when a w lock is
        already held.  This avoids timing races when coordinating processes.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            can_acquire = zlm.check(dataset, "w")
            if locked:
                if not can_acquire:
                    return
            else:
                if can_acquire:
                    return
            time.sleep(0.01)
        raise RuntimeError(
            f"timed out waiting for {dataset} lock state locked={locked}"
        )

    def _run_two_profiles(self, profile_a, profile_b, runner_a, runner_b,
                          wait_dataset=None):
        """Run two profiles in separate processes and return (rc_a, rc_b).

        If *wait_dataset* is set, process B is not started until process A has
        acquired a w lock on that dataset.
        """
        ctx = multiprocessing.get_context("fork")
        result_a = ctx.Queue()
        result_b = ctx.Queue()

        p1 = ctx.Process(
            target=_run_profile_worker,
            args=(profile_a, runner_a, result_a),
        )
        p1.start()
        if wait_dataset:
            self._wait_for_lock(wait_dataset, locked=True)
        p2 = ctx.Process(
            target=_run_profile_worker,
            args=(profile_b, runner_b, result_b),
        )
        p2.start()

        p1.join(timeout=15)
        p2.join(timeout=15)

        rc_a = result_a.get(timeout=1) if p1.exitcode == 0 else p1.exitcode
        rc_b = result_b.get(timeout=1) if p2.exitcode == 0 else p2.exitcode

        if p1.is_alive():
            p1.terminate()
            p1.join()
        if p2.is_alive():
            p2.terminate()
            p2.join()

        return rc_a, rc_b

    def test_disjoint_datasets_both_succeed(self):
        """Two profiles touching disjoint datasets run to completion."""
        with temp_config_dir():
            with temp_lock_dir():
                profile_a = _backup_profile("tank/a", "backup/a")
                profile_b = _backup_profile("tank/b", "backup/b")

                rc_a, rc_b = self._run_two_profiles(
                    profile_a, profile_b,
                    "run_backup_profile",
                    "run_backup_profile",
                )

        self.assertEqual(rc_a, 0)
        self.assertEqual(rc_b, 0)

    def test_same_dataset_one_blocked(self):
        """Two profiles targeting the same dataset cannot both hold the lock."""
        with temp_config_dir():
            with temp_lock_dir():
                # Use different labels so snapshot-name generation does not
                # serialize the two profiles before the dataset lock test.
                profile_a = _backup_profile(
                    "tank/share", "backup/share", label="dailybackup"
                )
                profile_b = _backup_profile(
                    "tank/share", "backup/share", label="weeklybackup"
                )

                rc_a, rc_b = self._run_two_profiles(
                    profile_a, profile_b,
                    "run_backup_profile",
                    "run_backup_profile",
                    wait_dataset="tank/share",
                )

        # Exactly one should succeed; the other must fail safely.
        self.assertIn(0, (rc_a, rc_b), "expected one profile to succeed")
        self.assertNotEqual(rc_a, rc_b, "expected one profile to fail")

    def test_backup_and_prune_serialize(self):
        """A prune step fails safely while a backup holds the dataset.

        The hierarchical lock rules block a w lock on pool "tank" when a
        descendant dataset "tank/share" is already locked for the backup.
        """
        with temp_config_dir():
            with temp_lock_dir():
                profile_backup = _backup_profile("tank/share", "backup/share")
                profile_prune = _retention_profile("tank")

                rc_backup, rc_prune = self._run_two_profiles(
                    profile_backup, profile_prune,
                    "run_backup_profile",
                    "run_retention_profile",
                    wait_dataset="tank/share",
                )

        # The backup should complete normally.
        self.assertEqual(rc_backup, 0)
        # The prune must not corrupt anything; because headless mode aborts on
        # lock conflict, it fails safely with rc=1.
        self.assertEqual(rc_prune, 1)


if __name__ == "__main__":
    unittest.main()

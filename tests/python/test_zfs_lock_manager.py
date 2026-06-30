"""Tests for zfs_lock_manager.py — Python client for ZFS dataset locks."""

import json
import os
import subprocess
import sys
import unittest

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

import zfs_lock_manager as zlm
from test_support import temp_lock_dir


class TestEncoding(unittest.TestCase):
    """Dataset path encoding for lock filenames."""

    def test_encode_slash_and_at(self):
        self.assertEqual(zlm._encode("pool/dataset@snap"), "pool%2Fdataset%40snap")

    def test_decode_round_trip(self):
        self.assertEqual(zlm._decode("pool%2Fdataset%40snap"), "pool/dataset@snap")

    def test_lock_file_path(self):
        with temp_lock_dir():
            self.assertEqual(
                zlm._lock_file("pool/dataset"),
                os.path.join(zlm.ZFSLOCK_LOCKS_DIR, "pool%2Fdataset.lock"),
            )


class TestAcquireAndRelease(unittest.TestCase):
    """Basic single-lock lifecycle."""

    def setUp(self):
        zlm._lock_refcounts.clear()

    def test_acquire_creates_lock_file(self):
        with temp_lock_dir():
            lock_id = zlm.acquire("tank", "w", "test lock")
            self.assertTrue(os.path.isfile(lock_id))
            data = json.loads(open(lock_id).read())
            self.assertEqual(data["dataset"], "tank")
            self.assertEqual(data["type"], "w")
            self.assertEqual(data["pid"], os.getpid())
            self.assertEqual(data["description"], "test lock")

    def test_release_removes_lock_file(self):
        with temp_lock_dir():
            lock_id = zlm.acquire("tank", "w")
            self.assertTrue(zlm.release(lock_id))
            self.assertFalse(os.path.isfile(lock_id))

    def test_release_missing_returns_true(self):
        with temp_lock_dir():
            self.assertTrue(zlm.release(os.path.join(zlm.ZFSLOCK_LOCKS_DIR, "missing.lock")))

    def test_reentry_increments_refcount(self):
        with temp_lock_dir():
            lock_id1 = zlm.acquire("tank", "w")
            lock_id2 = zlm.acquire("tank", "w")
            self.assertEqual(lock_id1, lock_id2)
            self.assertTrue(os.path.isfile(lock_id1))
            self.assertTrue(zlm.release(lock_id1))
            self.assertTrue(os.path.isfile(lock_id1))
            self.assertTrue(zlm.release(lock_id1))
            self.assertFalse(os.path.isfile(lock_id1))

    def test_release_owned_by_other_pid_fails(self):
        with temp_lock_dir():
            lockfile = zlm._lock_file("tank")
            os.makedirs(os.path.dirname(lockfile), exist_ok=True)
            with open(lockfile, "w") as f:
                json.dump({
                    "dataset": "tank",
                    "type": "w",
                    "pid": 999999,
                    "script": "other",
                    "acquired": "2026-01-01T00:00:00",
                    "description": "",
                }, f)
            self.assertFalse(zlm.release(lockfile))


def _conflicting_lock(dataset, lock_type="w"):
    """Start a real process and write a lock file owned by it."""
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
    lockfile = zlm._lock_file(dataset)
    os.makedirs(os.path.dirname(lockfile), exist_ok=True)
    with open(lockfile, "w") as f:
        json.dump({
            "dataset": dataset,
            "type": lock_type,
            "pid": proc.pid,
            "script": os.path.basename(sys.executable),
            "acquired": "2026-01-01T00:00:00",
            "description": "",
        }, f)
    return proc


class TestAcquireMultiple(unittest.TestCase):
    """Deadlock-free multi-lock acquisition."""

    def setUp(self):
        zlm._lock_refcounts.clear()

    def test_sorts_by_depth_then_lexicographically(self):
        with temp_lock_dir():
            lock_ids = zlm.acquire_multiple("w", [
                "tank/c", "tank/a/b", "tank", "tank/a"
            ])
            datasets = [json.loads(open(lid).read())["dataset"] for lid in lock_ids]
            # Ancestors with requested descendants are dropped, leaving only
            # the deepest nodes, sorted by depth then lexicographically.
            self.assertEqual(datasets, ["tank/c", "tank/a/b"])

    def test_removes_redundant_ancestors(self):
        with temp_lock_dir():
            lock_ids = zlm.acquire_multiple("w", ["tank", "tank/a", "tank/a/b"])
            datasets = {json.loads(open(lid).read())["dataset"] for lid in lock_ids}
            self.assertEqual(datasets, {"tank/a/b"})

    def test_rolls_back_on_conflict(self):
        with temp_lock_dir():
            # Pre-create a lock owned by a real external process.
            proc = _conflicting_lock("data")
            try:
                with self.assertRaises(RuntimeError):
                    zlm.acquire_multiple("w", ["tank", "data"])
                # tank lock should not have been created.
                self.assertFalse(os.path.isfile(zlm._lock_file("tank")))
            finally:
                proc.terminate()
                proc.wait(timeout=2)


class TestConflictDetection(unittest.TestCase):
    """Same-dataset and hierarchy conflict rules."""

    def setUp(self):
        zlm._lock_refcounts.clear()

    def test_same_dataset_write_blocks_write(self):
        with temp_lock_dir():
            zlm.acquire("tank", "w")
            self.assertFalse(zlm.check("tank", "w"))

    def test_same_dataset_read_allows_read(self):
        with temp_lock_dir():
            zlm.acquire("tank", "r")
            self.assertTrue(zlm.check("tank", "r"))

    def test_same_dataset_read_blocks_write(self):
        with temp_lock_dir():
            zlm.acquire("tank", "r")
            self.assertFalse(zlm.check("tank", "w"))

    def test_ancestor_x_blocks_descendant_w(self):
        with temp_lock_dir():
            zlm.acquire("tank", "x")
            self.assertFalse(zlm.check("tank/a", "w"))

    def test_ancestor_w_blocks_descendant_w(self):
        with temp_lock_dir():
            zlm.acquire("tank", "w")
            self.assertFalse(zlm.check("tank/a", "w"))

    def test_ancestor_w_allows_descendant_r(self):
        with temp_lock_dir():
            zlm.acquire("tank", "w")
            self.assertTrue(zlm.check("tank/a", "r"))

    def test_descendant_w_blocks_ancestor_w(self):
        with temp_lock_dir():
            zlm.acquire("tank/a", "w")
            self.assertFalse(zlm.check("tank", "w"))

    def test_descendant_r_allows_ancestor_w(self):
        with temp_lock_dir():
            zlm.acquire("tank/a", "r")
            self.assertTrue(zlm.check("tank", "w"))

    def test_descendant_x_blocks_ancestor_r(self):
        with temp_lock_dir():
            zlm.acquire("tank/a", "x")
            self.assertFalse(zlm.check("tank", "r"))


class TestStaleCleanup(unittest.TestCase):
    """Stale lock detection and cleanup."""

    def setUp(self):
        zlm._lock_refcounts.clear()

    def _write_lock(self, dataset, pid, script="python"):
        lockfile = zlm._lock_file(dataset)
        os.makedirs(os.path.dirname(lockfile), exist_ok=True)
        with open(lockfile, "w") as f:
            json.dump({
                "dataset": dataset,
                "type": "w",
                "pid": pid,
                "script": script,
                "acquired": "2026-01-01T00:00:00",
                "description": "",
            }, f)
        return lockfile

    def test_is_stale_for_nonexistent_pid(self):
        with temp_lock_dir():
            lockfile = self._write_lock("tank", 999999)
            self.assertTrue(zlm._is_stale(lockfile))

    def test_is_not_stale_for_current_process(self):
        with temp_lock_dir():
            lockfile = self._write_lock("tank", os.getpid())
            self.assertFalse(zlm._is_stale(lockfile))

    def test_cleanup_stale_removes_files(self):
        with temp_lock_dir():
            stale = self._write_lock("tank", 999999)
            active = self._write_lock("data", os.getpid())
            removed = zlm._cleanup_stale()
            self.assertEqual(removed, 1)
            self.assertFalse(os.path.isfile(stale))
            self.assertTrue(os.path.isfile(active))


class TestContextManagers(unittest.TestCase):
    """Lock and locks context managers."""

    def setUp(self):
        zlm._lock_refcounts.clear()

    def test_single_lock_context_manager_releases(self):
        with temp_lock_dir():
            with zlm.lock("tank", "w") as lock_id:
                self.assertTrue(os.path.isfile(lock_id))
            self.assertFalse(os.path.isfile(lock_id))

    def test_single_lock_context_manager_releases_on_exception(self):
        with temp_lock_dir():
            try:
                with zlm.lock("tank", "w") as lock_id:
                    self.assertTrue(os.path.isfile(lock_id))
                    raise RuntimeError("boom")
            except RuntimeError:
                pass
            self.assertFalse(os.path.isfile(lock_id))

    def test_multi_lock_context_manager_releases(self):
        with temp_lock_dir():
            with zlm.locks("w", ["tank", "data"]) as lock_ids:
                for lid in lock_ids:
                    self.assertTrue(os.path.isfile(lid))
            for lid in lock_ids:
                self.assertFalse(os.path.isfile(lid))


class TestReleaseAll(unittest.TestCase):
    """release_all cleans up every lock held by this process."""

    def setUp(self):
        zlm._lock_refcounts.clear()

    def test_release_all_releases_held_locks(self):
        with temp_lock_dir():
            lid1 = zlm.acquire("tank", "w")
            lid2 = zlm.acquire("data", "r")
            self.assertEqual(zlm.release_all(), 2)
            self.assertFalse(os.path.isfile(lid1))
            self.assertFalse(os.path.isfile(lid2))


if __name__ == "__main__":
    unittest.main()

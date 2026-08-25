"""Tests for python/zfs_lock_manager.py two-node behavior."""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import zfs_lock_manager as zlm

_TWO_NODE_CFG = {
    "mode": "two-node",
    "this_host": "tweety",
    "storage_host": "stewie",
    "compute_host": "tweety",
    "storage_ip": "10.0.0.1",
    "pools": {"threeamigos"},
}


class TestRemoteAcquire(unittest.TestCase):
    def setUp(self):
        self.lock_dir = tempfile.mkdtemp()
        self._orig_dir = zlm.ZFSLOCK_DIR
        zlm.ZFSLOCK_DIR = self.lock_dir
        zlm.ZFSLOCK_LOCKS_DIR = os.path.join(self.lock_dir, ".locks")
        zlm.ZFSLOCK_PIDS_DIR = os.path.join(self.lock_dir, ".pids")
        os.makedirs(zlm.ZFSLOCK_LOCKS_DIR, exist_ok=True)
        os.makedirs(zlm.ZFSLOCK_PIDS_DIR, exist_ok=True)
        zlm._node_config_cache = _TWO_NODE_CFG
        zlm._remote_holds.clear()
        zlm._lock_refcounts.clear()

    def tearDown(self):
        zlm.ZFSLOCK_DIR = self._orig_dir
        zlm.ZFSLOCK_LOCKS_DIR = os.path.join(self._orig_dir, ".locks")
        zlm.ZFSLOCK_PIDS_DIR = os.path.join(self._orig_dir, ".pids")
        zlm._node_config_cache = None
        zlm._remote_holds.clear()
        zlm._lock_refcounts.clear()

    def _make_popen(self, line="LOCKED /run/lock/zfsutilities/.locks/threeamigos%2Fpve.lock"):
        proc = MagicMock()
        proc.stdout.readline.return_value = line + "\n"
        proc.stdout.fileno.return_value = 3
        return proc

    @patch.dict(os.environ, {"ZFSLOCK_REMOTE_BIN": "/usr/local/lib/zfsutilities/current/bin"})
    def test_remote_acquire_returns_remote_id(self):
        proc = self._make_popen()
        with patch("zfs_lock_manager.subprocess.Popen", return_value=proc):
            with patch("zfs_lock_manager.select.select", return_value=([proc.stdout], [], [])):
                lock_id = zlm.acquire("threeamigos/pve", "w", "test")

        self.assertTrue(lock_id.startswith("REMOTE:"))
        self.assertIn("threeamigos%2Fpve.lock", lock_id)
        self.assertIn("/run/lock/zfsutilities/.locks/threeamigos%2Fpve.lock", zlm._remote_holds)

    @patch.dict(os.environ, {"ZFSLOCK_REMOTE_BIN": "/usr/local/lib/zfsutilities/current/bin"})
    def test_remote_acquire_conflict_raises(self):
        proc = self._make_popen("CONFLICT dataset=threeamigos/pve type=w pid=123 script=test")
        with patch("zfs_lock_manager.subprocess.Popen", return_value=proc):
            with patch("zfs_lock_manager.select.select", return_value=([proc.stdout], [], [])):
                with self.assertRaises(RuntimeError):
                    zlm.acquire("threeamigos/pve", "w")
        proc.kill.assert_called()

    @patch.dict(os.environ, {"ZFSLOCK_REMOTE_BIN": "/usr/local/lib/zfsutilities/current/bin"})
    def test_remote_release_terminates_holder(self):
        proc = self._make_popen()
        with patch("zfs_lock_manager.subprocess.Popen", return_value=proc):
            with patch("zfs_lock_manager.select.select", return_value=([proc.stdout], [], [])):
                lock_id = zlm.acquire("threeamigos/pve", "w")
        self.assertTrue(zlm.release(lock_id))
        proc.terminate.assert_called()


class TestRemoteCheckAndList(unittest.TestCase):
    def setUp(self):
        zlm._node_config_cache = _TWO_NODE_CFG
        zlm._remote_holds.clear()
        zlm._lock_refcounts.clear()

    def tearDown(self):
        zlm._node_config_cache = None
        zlm._remote_holds.clear()
        zlm._lock_refcounts.clear()

    def test_remote_check_returns_true_when_available(self):
        result = MagicMock()
        result.returncode = 0
        result.stdout = '{"available": true}\n'
        with patch("zfs_lock_manager.subprocess.run", return_value=result):
            self.assertTrue(zlm.check("threeamigos/pve", "w"))

    def test_remote_check_returns_false_when_locked(self):
        result = MagicMock()
        result.returncode = 0
        result.stdout = '{"available": false, "conflict": {"dataset":"threeamigos/pve","type":"w","pid":"123","script":"test","acquired":"","description":""}}\n'
        with patch("zfs_lock_manager.subprocess.run", return_value=result):
            self.assertFalse(zlm.check("threeamigos/pve", "w"))

    def test_remote_list_merges_with_local(self):
        result = MagicMock()
        result.returncode = 0
        result.stdout = '[\n  {"dataset":"threeamigos/pve","type":"w","pid":"123","script":"test","acquired":"2026-01-01T00:00:00","description":""}\n]\n'
        with patch("zfs_lock_manager.subprocess.run", return_value=result):
            locks = zlm.list_active_locks()

        datasets = {lock["dataset"] for lock in locks}
        self.assertIn("threeamigos/pve", datasets)
        remote_lock = next(lock for lock in locks if lock["dataset"] == "threeamigos/pve")
        self.assertEqual(remote_lock["host"], "stewie")


if __name__ == "__main__":
    unittest.main()

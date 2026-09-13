"""Tests for python/zfs_lock_manager.py two-node behavior and script naming."""

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

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


class TestScriptName(unittest.TestCase):
    """_script_name() must produce a name that appears in /proc cmdlines."""

    def test_plain_script_returns_basename(self):
        with patch.object(
            sys, "argv", ["/usr/local/lib/zfsutilities/current/bin/zfsdailybackup"]
        ):
            self.assertEqual(zlm._script_name(), "zfsdailybackup")

    def test_python_dash_m_package_returns_package_name(self):
        # python -m pytest sets argv[0] to .../pytest/__main__.py, which
        # never appears in the process cmdline; the package name does.
        spec = MagicMock()
        spec.name = "pytest.__main__"
        main = sys.modules["__main__"]
        with patch.object(sys, "argv", ["/usr/lib/python3/dist-packages/pytest/__main__.py"]):
            with patch.object(main, "__spec__", spec, create=True):
                self.assertEqual(zlm._script_name(), "pytest")

    def test_python_dash_m_without_spec_falls_back_to_basename(self):
        main = sys.modules["__main__"]
        with patch.object(sys, "argv", ["/opt/somepkg/__main__.py"]):
            with patch.object(main, "__spec__", None, create=True):
                self.assertEqual(zlm._script_name(), "__main__.py")

    def test_empty_argv_returns_python(self):
        with patch.object(sys, "argv", []):
            self.assertEqual(zlm._script_name(), "python")


if __name__ == "__main__":
    unittest.main()

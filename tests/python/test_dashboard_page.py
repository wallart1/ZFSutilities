"""Tests for dashboard_page.py — data gathering and warning logic."""

import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime
from contextlib import ExitStack
from unittest.mock import MagicMock, Mock, patch

import sys

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import (
    capture_logs, mock_gtk, mock_subprocess, temp_config_dir, write_config,
)

import dashboard_page as dp


def _write_lock_file(path, dataset, pid, lock_type="w"):
    """Write a lock file in the format produced by zfslockmanager."""
    content = json.dumps({
        "dataset": dataset,
        "type": lock_type,
        "pid": pid,
        "script": "test",
        "acquired": "2026-01-01T00:00:00-05:00",
        "description": "test lock",
    })
    with open(path, "w") as f:
        f.write(content)


class _WidgetRecorder(MagicMock):
    """MagicMock that records children added via pack_start/add."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.children = []

    def pack_start(self, child, *args, **kwargs):
        self.children.append(child)

    def add(self, child):
        self.children.append(child)


def _frame_title(frame):
    """Return the markup title set on a section frame."""
    label = frame.set_label_widget.call_args[0][0]
    return label.set_markup.call_args[0][0]


class TestGetPoolHealth(unittest.TestCase):

    def test_empty_zpool_list(self):
        with mock_subprocess() as m:
            m.add_zpool_list([])
            pools = dp._get_pool_health()
        self.assertEqual(pools, [])

    def test_returns_none_on_timeout(self):
        repo = MagicMock()
        repo.list_pools.side_effect = subprocess.TimeoutExpired("zpool list", 5)
        pools = dp._get_pool_health(repo=repo)
        self.assertIsNone(pools)

    def test_pools_returned_with_cap_parsed(self):
        with mock_subprocess() as m:
            # The default mock only outputs 5 columns; override for 6 columns
            m.set_command_handler(
                r"zpool list -H -o name,health,size,alloc,free,cap",
                lambda *_a, **_k: m._completed("tank\tONLINE\t10T\t5T\t5T\t75%\n"),
            )
            m.set_command_handler(r"zpool status", lambda *_a, **_k: m._completed(""))
            pools = dp._get_pool_health()
        self.assertEqual(len(pools), 1)
        self.assertEqual(pools[0]["name"], "tank")
        self.assertEqual(pools[0]["health"], "ONLINE")
        self.assertEqual(pools[0]["cap"], "75%")
        self.assertEqual(pools[0]["cap_int"], 75)

    def test_scrub_date_parsed(self):
        with mock_subprocess() as m:
            m.set_command_handler(
                r"zpool list -H -o name,health,size,alloc,free,cap",
                lambda *_a, **_k: m._completed("tank\tONLINE\t10T\t5T\t5T\t50%\n"),
            )
            status = (
                "  scan: scrub repaired 0B in 00:00:02 with 0 errors on Sun May 10 00:24:03 2026\n"
            )
            m.set_command_handler(r"zpool status", lambda *_a, **_k: m._completed(status))
            pools = dp._get_pool_health()
        self.assertEqual(pools[0]["scrub_date"], "Sun May 10 00:24:03 2026")

    def test_scrub_in_progress(self):
        with mock_subprocess() as m:
            m.set_command_handler(
                r"zpool list -H -o name,health,size,alloc,free,cap",
                lambda *_a, **_k: m._completed("tank\tONLINE\t10T\t5T\t5T\t50%\n"),
            )
            status = (
                "  scan: scrub in progress since Sun May 10 00:24:03 2026\n"
            )
            m.set_command_handler(r"zpool status", lambda *_a, **_k: m._completed(status))
            pools = dp._get_pool_health()
        self.assertEqual(pools[0]["scrub_date"], "In progress")

    def test_scrub_date_parsed_with_days_duration(self):
        with mock_subprocess() as m:
            m.set_command_handler(
                r"zpool list -H -o name,health,size,alloc,free,cap",
                lambda *_a, **_k: m._completed("tank\tONLINE\t10T\t5T\t5T\t50%\n"),
            )
            status = (
                "  scan: scrub repaired 0B in 1 days 01:35:48 with 0 errors on Wed Jun  3 20:50:19 2026\n"
            )
            m.set_command_handler(r"zpool status", lambda *_a, **_k: m._completed(status))
            pools = dp._get_pool_health()
        self.assertEqual(pools[0]["scrub_date"], "Wed Jun  3 20:50:19 2026")

    def test_scrub_date_canceled(self):
        with mock_subprocess() as m:
            m.set_command_handler(
                r"zpool list -H -o name,health,size,alloc,free,cap",
                lambda *_a, **_k: m._completed("tank\tONLINE\t10T\t5T\t5T\t50%\n"),
            )
            status = "  scan: scrub canceled on Fri Jun 12 12:00:13 2026\n"
            m.set_command_handler(r"zpool status", lambda *_a, **_k: m._completed(status))
            pools = dp._get_pool_health()
        self.assertEqual(pools[0]["scrub_date"], "Fri Jun 12 12:00:13 2026")


class TestGetRecentEntries(unittest.TestCase):

    @patch("dashboard_page.load_history")
    def test_returns_newest_entries(self, mock_load):
        mock_load.return_value = [
            {"timestamp": "2026-05-28T14:32:00", "type": "backup", "result": "success"},
            {"timestamp": "2026-05-27T02:00:00", "type": "offsite", "result": "success"},
            {"timestamp": "2026-05-26T10:00:00", "type": "backup", "result": "failure"},
        ]
        recent = dp._get_recent_entries(10)
        self.assertEqual(len(recent), 3)
        self.assertEqual(recent[0]["timestamp"], "2026-05-28T14:32:00")
        self.assertEqual(recent[1]["timestamp"], "2026-05-27T02:00:00")
        self.assertEqual(recent[2]["timestamp"], "2026-05-26T10:00:00")

    @patch("dashboard_page.load_history")
    def test_empty_history(self, mock_load):
        mock_load.return_value = []
        recent = dp._get_recent_entries(10)
        self.assertEqual(recent, [])

    @patch("dashboard_page.load_history")
    def test_limit_respected(self, mock_load):
        mock_load.return_value = [
            {"timestamp": f"2026-05-{day:02d}T00:00:00", "type": "backup", "result": "success"}
            for day in range(1, 21)
        ]
        recent = dp._get_recent_entries(10)
        self.assertEqual(len(recent), 10)
        self.assertEqual(recent[0]["timestamp"], "2026-05-01T00:00:00")

    @patch("dashboard_page.load_history")
    def test_prune_type_included(self, mock_load):
        """Prune operations write type='prune' (not 'retention') to history."""
        mock_load.return_value = [
            {"timestamp": "2026-05-28T14:32:00", "type": "prune", "result": "success"},
        ]
        recent = dp._get_recent_entries(10)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["timestamp"], "2026-05-28T14:32:00")


class TestIsTwoNode(unittest.TestCase):

    def test_single_node_conf(self):
        with patch.object(dp.os.path, "exists", return_value=True):
            with patch("builtins.open", create=True) as mock_open:
                mock_open.return_value.__enter__.return_value = iter(['NODE_MODE="single-node"\n'])
                result = dp._is_two_node()
                self.assertFalse(result)

    def test_two_node_conf(self):
        with patch.object(dp.os.path, "exists", return_value=True):
            with patch("builtins.open", create=True) as mock_open:
                mock_open.return_value.__enter__.return_value = iter(['NODE_MODE="two-node"\n'])
                result = dp._is_two_node()
                self.assertTrue(result)

    def test_legacy_conf_no_node_mode_defaults_two_node(self):
        """Legacy /etc/two-node.conf without NODE_MODE= defaults to two-node."""
        with patch.object(dp.os.path, "exists", return_value=True):
            with patch("builtins.open", create=True) as mock_open:
                mock_open.return_value.__enter__.return_value = iter([
                    'STORAGE_HOST="storage1"\n',
                    'COMPUTE_HOST="compute1"\n',
                ])
                result = dp._is_two_node()
                self.assertTrue(result)

    def test_no_conf(self):
        with patch.object(dp.os.path, "exists", return_value=False):
            result = dp._is_two_node()
            self.assertFalse(result)


class TestGetNodeConfig(unittest.TestCase):

    @patch("dashboard_page._local_hostname", return_value="myhost")
    def test_no_conf_defaults_single_node(self, _mock):
        with patch.object(dp.os.path, "exists", return_value=False):
            cfg = dp._get_node_config()
        self.assertEqual(cfg["mode"], "single-node")
        self.assertEqual(cfg["this_host"], "myhost")
        self.assertEqual(cfg["storage_host"], "myhost")
        self.assertEqual(cfg["compute_host"], "myhost")

    @patch("dashboard_page._local_hostname", return_value="myhost")
    def test_single_node_conf(self, _mock):
        with patch.object(dp.os.path, "exists", return_value=True):
            with patch("builtins.open", create=True) as mock_open:
                mock_open.return_value.__enter__.return_value = iter([
                    'NODE_MODE="single-node"\n',
                    'THIS_HOST="myhost"\n',
                ])
                cfg = dp._get_node_config()
        self.assertEqual(cfg["mode"], "single-node")
        self.assertEqual(cfg["storage_host"], "myhost")
        self.assertEqual(cfg["compute_host"], "myhost")

    @patch("dashboard_page._local_hostname", return_value="myhost")
    def test_two_node_conf(self, _mock):
        with patch.object(dp.os.path, "exists", return_value=True):
            with patch("builtins.open", create=True) as mock_open:
                mock_open.return_value.__enter__.return_value = iter([
                    'NODE_MODE="two-node"\n',
                    'THIS_HOST="storage1"\n',
                    'STORAGE_HOST="storage1"\n',
                    'COMPUTE_HOST="compute1"\n',
                    'STORAGE_IP="192.168.1.10"\n',
                ])
                cfg = dp._get_node_config()
        self.assertEqual(cfg["mode"], "two-node")
        self.assertEqual(cfg["storage_host"], "storage1")
        self.assertEqual(cfg["compute_host"], "compute1")
        self.assertEqual(cfg["storage_ip"], "192.168.1.10")

    @patch("dashboard_page._local_hostname", return_value="myhost")
    def test_legacy_conf_defaults_two_node(self, _mock):
        with patch.object(dp.os.path, "exists", return_value=True):
            with patch("builtins.open", create=True) as mock_open:
                mock_open.return_value.__enter__.return_value = iter([
                    'STORAGE_HOST="storage1"\n',
                    'COMPUTE_HOST="compute1"\n',
                ])
                cfg = dp._get_node_config()
        self.assertEqual(cfg["mode"], "two-node")
        self.assertEqual(cfg["storage_host"], "storage1")
        self.assertEqual(cfg["compute_host"], "compute1")


class TestGetPeerHost(unittest.TestCase):

    @patch("dashboard_page._local_hostname", return_value="storage1")
    def test_storage_peer_is_compute(self, _mock):
        with patch.object(dp.os.path, "exists", return_value=True):
            with patch("builtins.open", create=True) as mock_open:
                mock_open.return_value.__enter__.return_value = iter([
                    'NODE_MODE="two-node"\n',
                    'STORAGE_HOST="storage1"\n',
                    'COMPUTE_HOST="compute1"\n',
                ])
                self.assertEqual(dp._get_peer_host(), "compute1")

    @patch("dashboard_page._local_hostname", return_value="compute1")
    def test_compute_peer_is_storage(self, _mock):
        with patch.object(dp.os.path, "exists", return_value=True):
            with patch("builtins.open", create=True) as mock_open:
                mock_open.return_value.__enter__.return_value = iter([
                    'NODE_MODE="two-node"\n',
                    'STORAGE_HOST="storage1"\n',
                    'COMPUTE_HOST="compute1"\n',
                ])
                self.assertEqual(dp._get_peer_host(), "storage1")

    @patch("dashboard_page._local_hostname", return_value="myhost")
    def test_single_node_returns_none(self, _mock):
        with patch.object(dp.os.path, "exists", return_value=True):
            with patch("builtins.open", create=True) as mock_open:
                mock_open.return_value.__enter__.return_value = iter([
                    'NODE_MODE="single-node"\n',
                    'THIS_HOST="myhost"\n',
                ])
                self.assertIsNone(dp._get_peer_host())

    @patch("dashboard_page._local_hostname", return_value="myhost")
    def test_no_conf_returns_none(self, _mock):
        with patch.object(dp.os.path, "exists", return_value=False):
            self.assertIsNone(dp._get_peer_host())

    @patch("dashboard_page._local_hostname", return_value="unexpected")
    def test_unknown_local_returns_non_local_host(self, _mock):
        """If the local host matches neither role, return a non-local host."""
        with patch.object(dp.os.path, "exists", return_value=True):
            with patch("builtins.open", create=True) as mock_open:
                mock_open.return_value.__enter__.return_value = iter([
                    'NODE_MODE="two-node"\n',
                    'STORAGE_HOST="storage1"\n',
                    'COMPUTE_HOST="compute1"\n',
                ])
                self.assertEqual(dp._get_peer_host(), "storage1")

    @patch("dashboard_page._local_hostname", return_value="storage1")
    def test_both_roles_local_returns_none(self, _mock):
        with patch.object(dp.os.path, "exists", return_value=True):
            with patch("builtins.open", create=True) as mock_open:
                mock_open.return_value.__enter__.return_value = iter([
                    'NODE_MODE="two-node"\n',
                    'STORAGE_HOST="storage1"\n',
                    'COMPUTE_HOST="storage1"\n',
                ])
                self.assertIsNone(dp._get_peer_host())


class TestLogPeerVersionResult(unittest.TestCase):

    def test_matching_versions_log_info(self):
        with capture_logs() as logs:
            dp._log_peer_version_result("1.2.3", "compute1", "1.2.3")
        self.assertEqual(len(logs), 1)
        self.assertIn("INFO:", logs[0])
        self.assertIn("compute1", logs[0])
        self.assertIn("1.2.3", logs[0])

    def test_mismatching_versions_log_warn(self):
        with capture_logs() as logs:
            dp._log_peer_version_result("1.2.3", "compute1", "1.2.4")
        self.assertEqual(len(logs), 1)
        self.assertIn("WARN:", logs[0])
        self.assertIn("compute1", logs[0])
        self.assertIn("1.2.4", logs[0])
        self.assertIn("1.2.3", logs[0])

    def test_unknown_peer_version_log_warn(self):
        with capture_logs() as logs:
            dp._log_peer_version_result("1.2.3", "compute1", "unknown")
        self.assertEqual(len(logs), 1)
        self.assertIn("WARN:", logs[0])
        self.assertIn("compute1", logs[0])


class TestGetHostVersion(unittest.TestCase):

    @patch("dashboard_page._local_hostname", return_value="myhost")
    @patch("os.path.exists", return_value=True)
    @patch("builtins.open", create=True)
    def test_local_repo_version(self, mock_open, _mock_exists, _mock_host):
        mock_open.return_value.__enter__.return_value.read.return_value = "1.2.3"
        ver = dp._get_host_version("myhost")
        self.assertEqual(ver, "1.2.3")

    @patch("dashboard_page._local_hostname", return_value="myhost")
    @patch("os.path.exists", return_value=False)
    def test_local_no_version_file(self, _mock_exists, _mock_host):
        ver = dp._get_host_version("myhost")
        self.assertEqual(ver, "unknown")

    @patch("dashboard_page._local_hostname", return_value="myhost")
    def test_remote_version(self, _mock_host):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "2.0.0\n"
            ver = dp._get_host_version("remote1")
        self.assertEqual(ver, "2.0.0")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertIn("root@remote1", args)

    @patch("dashboard_page._local_hostname", return_value="myhost")
    def test_remote_ssh_failure(self, _mock_host):
        with patch("subprocess.run", side_effect=OSError("no route")):
            ver = dp._get_host_version("remote1")
        self.assertEqual(ver, "unknown")


class TestGetIscsiMissingLuns(unittest.TestCase):

    @patch("dashboard_page._is_two_node", return_value=False)
    def test_single_node_returns_empty(self, _mock):
        self.assertEqual(dp._get_iscsi_missing_luns(), [])

    @patch("dashboard_page._is_two_node", return_value=True)
    def test_missing_encrypted_lun(self, _mock):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write("vm-300-disk-1:/dev/zvol/tank/vm-300-disk-1:threeamigos\n")
            path = f.name
        try:
            with patch("dashboard_page._run_cmd") as mock_run:
                # targetcli returns empty — no backstores loaded
                mock_run.return_value = ""
                with patch("dashboard_page._ISCSI_CONF", path):
                    missing = dp._get_iscsi_missing_luns()
        finally:
            os.unlink(path)
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["name"], "vm-300-disk-1")
        self.assertEqual(missing[0]["target"], "threeamigos")

    @patch("dashboard_page._is_two_node", return_value=True)
    def test_returns_none_on_timeout(self, _mock):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write("vm-300-disk-1:/dev/zvol/tank/vm-300-disk-1:threeamigos\n")
            path = f.name
        try:
            with patch("dashboard_page._run_cmd", return_value=None):
                with patch("dashboard_page._ISCSI_CONF", path):
                    missing = dp._get_iscsi_missing_luns()
        finally:
            os.unlink(path)
        self.assertIsNone(missing)


class TestLockPid(unittest.TestCase):
    """_lock_pid() extracts PIDs from lock files."""

    def test_reads_pid_from_json_lock_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            locks_dir = os.path.join(tmpdir, ".locks")
            os.makedirs(locks_dir)
            lock_file = os.path.join(locks_dir, "pool%2Fdataset.lock")
            _write_lock_file(lock_file, "pool/dataset", 12345)

            with patch.object(dp, "ZFSLOCK_LOCKS_DIR", locks_dir):
                with patch.object(dp, "ZFSLOCK_PIDS_DIR",
                                  os.path.join(tmpdir, ".pids")):
                    pid = dp._lock_pid("pool%2Fdataset.lock")
            self.assertEqual(pid, 12345)

    def test_returns_none_for_malformed_lock_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            locks_dir = os.path.join(tmpdir, ".locks")
            os.makedirs(locks_dir)
            lock_file = os.path.join(locks_dir, "bad.lock")
            with open(lock_file, "w") as f:
                f.write("not json")

            with patch.object(dp, "ZFSLOCK_LOCKS_DIR", locks_dir):
                with patch.object(dp, "ZFSLOCK_PIDS_DIR",
                                  os.path.join(tmpdir, ".pids")):
                    pid = dp._lock_pid("bad.lock")
            self.assertIsNone(pid)

    def test_returns_none_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            locks_dir = os.path.join(tmpdir, ".locks")
            os.makedirs(locks_dir)

            with patch.object(dp, "ZFSLOCK_LOCKS_DIR", locks_dir):
                with patch.object(dp, "ZFSLOCK_PIDS_DIR",
                                  os.path.join(tmpdir, ".pids")):
                    pid = dp._lock_pid("missing.lock")
            self.assertIsNone(pid)

    def test_fallback_to_pid_embedded_in_filename(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            locks_dir = os.path.join(tmpdir, ".locks")
            os.makedirs(locks_dir)

            with patch.object(dp, "ZFSLOCK_LOCKS_DIR", locks_dir):
                with patch.object(dp, "ZFSLOCK_PIDS_DIR",
                                  os.path.join(tmpdir, ".pids")):
                    pid = dp._lock_pid("pool%2Fdataset.pid.6789")
            self.assertEqual(pid, 6789)


class TestCountStaleLocks(unittest.TestCase):

    def test_no_lock_dir(self):
        with patch.object(dp.os.path, "isdir", return_value=False):
            self.assertEqual(dp._count_stale_locks(), 0)

    def test_stale_lock_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            locks_dir = os.path.join(tmpdir, ".locks")
            os.makedirs(locks_dir)
            # Create a lock file in the real zfslockmanager format
            lock_file = os.path.join(locks_dir, "pool%2Fdataset.lock")
            _write_lock_file(lock_file, "pool/dataset", 999999)

            with patch.object(dp, "ZFSLOCK_LOCKS_DIR", locks_dir):
                count = dp._count_stale_locks()
            self.assertEqual(count, 1)

    def test_active_lock_not_counted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            locks_dir = os.path.join(tmpdir, ".locks")
            os.makedirs(locks_dir)
            # Use current process PID (definitely alive)
            lock_file = os.path.join(locks_dir, "pool%2Fdataset.lock")
            _write_lock_file(lock_file, "pool/dataset", os.getpid())

            with patch.object(dp, "ZFSLOCK_LOCKS_DIR", locks_dir):
                count = dp._count_stale_locks()
            self.assertEqual(count, 0)

    def test_real_format_live_lock_not_stale(self):
        """Regression: locks written by zfslockmanager must not be flagged stale."""
        with tempfile.TemporaryDirectory() as tmpdir:
            locks_dir = os.path.join(tmpdir, ".locks")
            os.makedirs(locks_dir)
            lock_file = os.path.join(locks_dir, "fivebays%2FNVME1.lock")
            _write_lock_file(lock_file, "fivebays/NVME1", os.getpid(), lock_type="w")

            with patch.object(dp, "ZFSLOCK_LOCKS_DIR", locks_dir):
                count = dp._count_stale_locks()
            self.assertEqual(count, 0)


class TestCleanupStaleLocks(unittest.TestCase):

    def test_removes_stale_lock(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            locks_dir = os.path.join(tmpdir, ".locks")
            pids_dir = os.path.join(tmpdir, ".pids")
            os.makedirs(locks_dir)
            os.makedirs(pids_dir)
            lock_file = os.path.join(locks_dir, "stale.lock")
            pid_file = os.path.join(pids_dir, "stale.lock.pid")
            _write_lock_file(lock_file, "stale", 999999)
            with open(pid_file, "w") as f:
                f.write("999999\n")

            with patch.object(dp, "ZFSLOCK_LOCKS_DIR", locks_dir):
                with patch.object(dp, "ZFSLOCK_PIDS_DIR", pids_dir):
                    removed = dp._cleanup_stale_locks()
            self.assertEqual(removed, 1)
            self.assertFalse(os.path.exists(lock_file))
            self.assertFalse(os.path.exists(pid_file))


class TestGetWarnings(unittest.TestCase):

    def test_no_warnings(self):
        pools = [{"name": "tank", "health": "ONLINE", "cap": "50%", "cap_int": 50}]
        warnings = dp._get_warnings(pools, {}, threshold=80)
        self.assertEqual(warnings, [])

    def test_degraded_pool(self):
        pools = [{"name": "tank", "health": "DEGRADED", "cap": "50%", "cap_int": 50}]
        warnings = dp._get_warnings(pools, {}, threshold=80)
        self.assertEqual(warnings, ['Pool "tank" is DEGRADED'])

    def test_low_space(self):
        pools = [{"name": "tank", "health": "ONLINE", "cap": "85%", "cap_int": 85}]
        warnings = dp._get_warnings(pools, {}, threshold=80)
        self.assertEqual(warnings, ['Pool "tank" capacity at 85% (threshold: 80%)'])

    def test_multiple_warnings(self):
        pools = [
            {"name": "tank", "health": "DEGRADED", "cap": "85%", "cap_int": 85},
        ]
        warnings = dp._get_warnings(pools, {}, threshold=80)
        self.assertEqual(len(warnings), 2)

    def test_status_errors_summary(self):
        pools = [
            {
                "name": "tank",
                "health": "ONLINE",
                "cap": "50%",
                "cap_int": 50,
                "status_errors": {
                    "has_errors": True,
                    "errors_summary": "vdev errors: sda (cksum=5)",
                },
            },
        ]
        warnings = dp._get_warnings(pools, {}, threshold=80)
        self.assertEqual(
            warnings,
            ['Pool "tank" has ZFS errors: vdev errors: sda (cksum=5)'],
        )

    def test_status_errors_no_errors_ignored(self):
        pools = [
            {
                "name": "tank",
                "health": "ONLINE",
                "cap": "50%",
                "cap_int": 50,
                "status_errors": {"has_errors": False},
            },
        ]
        warnings = dp._get_warnings(pools, {}, threshold=80)
        self.assertEqual(warnings, [])


class TestHealthIcon(unittest.TestCase):

    def test_online(self):
        self.assertIn("#00AA00", dp._health_icon("ONLINE"))

    def test_degraded(self):
        self.assertIn("#CC0000", dp._health_icon("DEGRADED"))

    def test_unknown(self):
        self.assertIn("#FF8C00", dp._health_icon("UNKNOWN"))


class TestResultIcon(unittest.TestCase):

    def test_success(self):
        self.assertIn("#00AA00", dp._result_icon("success"))

    def test_failure(self):
        self.assertIn("#CC0000", dp._result_icon("failure"))


class TestCapRe(unittest.TestCase):
    """Verify the _CAP_RE regex behaves as documented."""

    def test_matches_percent(self):
        m = dp._CAP_RE.match("75%")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "75")

    def test_matches_with_whitespace(self):
        m = dp._CAP_RE.match("  80%")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "80")

    def test_no_match_without_percent(self):
        self.assertIsNone(dp._CAP_RE.match("100"))


class TestEncryptedLunRe(unittest.TestCase):
    """Verify the _ENCRYPTED_LUN_RE regex behaves as documented."""

    def test_valid_line(self):
        m = dp._ENCRYPTED_LUN_RE.match("vm-300-disk-1:/dev/zvol/tank/vm-300-disk-1:threeamigos")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "vm-300-disk-1")
        self.assertEqual(m.group(2), "/dev/zvol/tank/vm-300-disk-1")
        self.assertEqual(m.group(3), "threeamigos")

    def test_comment_skipped(self):
        self.assertIsNone(dp._ENCRYPTED_LUN_RE.match("# this is a comment"))

    def test_blank_line_skipped(self):
        self.assertIsNone(dp._ENCRYPTED_LUN_RE.match(""))


class TestScrubDateRe(unittest.TestCase):
    """Verify the _SCRUB_DATE_RE regex behaves as documented."""

    def test_completed_scrub(self):
        text = "scan: scrub repaired 0B in 00:00:02 with 0 errors on Sun May 10 00:24:03 2026"
        m = dp._SCRUB_DATE_RE.search(text)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(2), "Sun May 10 00:24:03 2026")

    def test_in_progress_not_matched(self):
        text = "scan: scrub in progress since Sun May 10 00:24:03 2026"
        self.assertIsNone(dp._SCRUB_DATE_RE.search(text))

    def test_canceled_scrub(self):
        text = "scan: scrub canceled on Fri Jun 12 12:00:13 2026"
        m = dp._SCRUB_CANCELED_RE.search(text)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "Fri Jun 12 12:00:13 2026")


class TestParseCap(unittest.TestCase):

    def test_parse_75_percent(self):
        self.assertEqual(dp._parse_cap("75%"), 75)

    def test_parse_zero(self):
        self.assertEqual(dp._parse_cap("0%"), 0)

    def test_parse_invalid(self):
        self.assertEqual(dp._parse_cap("???"), 0)


class TestFormatHistoryTimestamp(unittest.TestCase):

    def test_naive_iso_timestamp(self):
        result = dp._format_history_timestamp("2026-05-28T14:32:00")
        self.assertTrue(result.startswith("2026-05-28T14:32"))

    def test_with_microseconds(self):
        result = dp._format_history_timestamp("2026-05-28T14:32:00.123456")
        self.assertTrue(result.startswith("2026-05-28T14:32"))

    def test_returns_question_mark(self):
        self.assertEqual(dp._format_history_timestamp("?"), "?")

    def test_returns_original_on_invalid(self):
        self.assertEqual(dp._format_history_timestamp("not-a-date"), "not-a-date")


class TestCollectRunningTasks(unittest.TestCase):

    def test_no_tasks_when_everything_idle(self):
        app = MagicMock()
        app.backup_runner = None
        app.offsite_runner = None
        app.restore_runner = None
        app.retention_runner = None
        app.scrub_queue = None
        tasks = dp._collect_running_tasks(app)
        self.assertEqual(tasks, [])

    def test_gui_runner_task(self):
        app = MagicMock()
        runner = MagicMock()
        runner.running = True
        runner.label = "Backup"
        runner.steps = [("step1", [], False, False), ("step2", [], False, False)]
        runner._finally_step = None
        runner.current_step = 0
        app.backup_runner = runner
        app.offsite_runner = None
        app.restore_runner = None
        app.retention_runner = None
        app.scrub_queue = None
        tasks = dp._collect_running_tasks(app)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["name"], "Backup")
        self.assertEqual(tasks[0]["type"], "GUI")
        self.assertEqual(tasks[0]["task_key"], "runner:backup_runner")

    def test_scrub_task(self):
        app = MagicMock()
        app.backup_runner = None
        app.offsite_runner = None
        app.restore_runner = None
        app.retention_runner = None
        queue = MagicMock()
        queue.active = {"fivebays"}
        app.scrub_queue = queue
        fixed_eta = datetime(2026, 6, 28, 12, 0, 0)
        with patch("scrub_manager.get_all_pool_scrub_states") as mock_states:
            with patch("scrub_manager.ScrubState") as MockState:
                MockState.SCANNING = MagicMock()
                mock_states.return_value = {
                    "fivebays": MagicMock(
                        state=MockState.SCANNING,
                        progress_percent=45.5,
                        eta=fixed_eta,
                    ),
                }
                tasks = dp._collect_running_tasks(app)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["name"], "Scrub: fivebays")
        self.assertEqual(tasks[0]["type"], "Scrub")
        self.assertEqual(
            tasks[0]["status"],
            "45.5% complete (ETA 2026-06-28 12:00)",
        )
        self.assertEqual(tasks[0]["task_key"], "scrub:fivebays")

    def test_scrub_task_no_eta(self):
        app = MagicMock()
        app.backup_runner = None
        app.offsite_runner = None
        app.restore_runner = None
        app.retention_runner = None
        queue = MagicMock()
        queue.active = {"fivebays"}
        app.scrub_queue = queue
        with patch("scrub_manager.get_all_pool_scrub_states") as mock_states:
            with patch("scrub_manager.ScrubState") as MockState:
                MockState.SCANNING = MagicMock()
                mock_states.return_value = {
                    "fivebays": MagicMock(
                        state=MockState.SCANNING,
                        progress_percent=45.5,
                        eta=None,
                    ),
                }
                tasks = dp._collect_running_tasks(app)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["status"], "45.5% complete")

    def test_running_profile_task(self):
        app = MagicMock()
        app.backup_runner = None
        app.offsite_runner = None
        app.restore_runner = None
        app.retention_runner = None
        app.scrub_queue = None
        with patch.object(
            dp, "list_running_profiles", return_value=[{"name": "Daily", "pid": 1234, "started": "2026-06-29T10:00:00"}]
        ):
            tasks = dp._collect_running_tasks(app)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["name"], "Daily")
        self.assertEqual(tasks[0]["type"], "Profile")
        self.assertEqual(tasks[0]["status"], "PID 1234")
        self.assertEqual(tasks[0]["task_key"], "profile:Daily")


class TestListRunningProfiles(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.orig_dir = dp.PROFILE_LOCK_DIR
        dp.PROFILE_LOCK_DIR = self.tmpdir

    def tearDown(self):
        dp.PROFILE_LOCK_DIR = self.orig_dir

    def test_empty_when_no_locks(self):
        self.assertEqual(dp.list_running_profiles(), [])

    def test_returns_running_profile(self):
        lock_path = os.path.join(self.tmpdir, "Daily.lock")
        with open(lock_path, "w") as f:
            import json
            json.dump({"profile": "Daily", "pid": os.getpid(), "started": "2026-06-29T10:00:00"}, f)
        profiles = dp.list_running_profiles()
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["name"], "Daily")
        self.assertEqual(profiles[0]["pid"], os.getpid())

    def test_skips_stale_lock(self):
        lock_path = os.path.join(self.tmpdir, "Old.lock")
        with open(lock_path, "w") as f:
            import json
            json.dump({"profile": "Old", "pid": 999999, "started": "2026-06-29T10:00:00"}, f)
        self.assertEqual(dp.list_running_profiles(), [])


class TestProfileConflictWarnings(unittest.TestCase):

    def test_adds_warning_when_profiles_running(self):
        pools = []
        profiles = [{"name": "Daily", "pid": 1234, "started": "?"}]
        warnings = dp._get_warnings(pools, [], 80, profiles)
        self.assertEqual(len(warnings), 1)
        self.assertIn("Daily", warnings[0])
        self.assertIn("concurrent GUI operations", warnings[0])

    def test_no_warning_when_no_profiles_running(self):
        pools = []
        warnings = dp._get_warnings(pools, [], 80, [])
        self.assertEqual(warnings, [])


class TestCancelTask(unittest.TestCase):

    def test_cancel_runner(self):
        app = MagicMock()
        runner = MagicMock()
        runner.running = True
        runner.label = "Backup"
        app.backup_runner = runner
        dp._cancel_task(app, "runner:backup_runner")
        runner.cancel.assert_called_once()

    def test_cancel_runner_not_running(self):
        app = MagicMock()
        runner = MagicMock()
        runner.running = False
        app.backup_runner = runner
        dp._cancel_task(app, "runner:backup_runner")
        runner.cancel.assert_not_called()

    def test_cancel_scrub(self):
        app = MagicMock()
        with patch("scrub_manager.stop_scrub") as mock_stop:
            dp._cancel_task(app, "scrub:tank")
        mock_stop.assert_called_once_with("tank")

    def test_cancel_scheduled(self):
        app = MagicMock()
        with patch("dashboard_page.os.kill") as mock_kill:
            dp._cancel_task(app, "scheduled:12345")
        mock_kill.assert_called_once_with(12345, dp.signal.SIGTERM)

    def test_cancel_unknown_key(self):
        app = MagicMock()
        dp._cancel_task(app, "unknown:thing")
        # Should not raise; just log a warning


class TestCachedOrFresh(unittest.TestCase):

    def test_stores_and_returns_fresh_value(self):
        app = MagicMock()
        value, stale = dp._get_cached_or_fresh(app, "_test_cache", ["a"])
        self.assertEqual(value, ["a"])
        self.assertFalse(stale)
        self.assertEqual(app._test_cache, ["a"])
        self.assertFalse(app._test_cache_stale)

    def test_returns_cached_when_fresh_is_none(self):
        app = MagicMock()
        app._test_cache = ["cached"]
        value, stale = dp._get_cached_or_fresh(app, "_test_cache", None)
        self.assertEqual(value, ["cached"])
        self.assertTrue(stale)

    def test_returns_none_when_no_cache(self):
        app = Mock(spec=[])
        value, stale = dp._get_cached_or_fresh(app, "_test_cache", None)
        self.assertIsNone(value)
        self.assertFalse(stale)


class TestRefreshPoolSection(unittest.TestCase):

    def test_stale_indicator_shown_when_stale(self):
        with mock_gtk() as gtk_mock:
            with patch.object(dp, "Gtk", gtk_mock):
                app = MagicMock()
                grid = MagicMock()
                app.dashboard_pool_grid = grid
                pools = [{
                    "name": "tank",
                    "health": "ONLINE",
                    "cap": "50%",
                    "cap_int": 50,
                    "scrub_date": "Sun May 10 00:24:03 2026",
                }]
                dp._refresh_pool_section(app, pools, scrub_states={}, stale=True)

        attach_calls = grid.attach.call_args_list
        self.assertTrue(len(attach_calls) > 0)
        # Stale label is attached at row 0, column 0, spanning 4 columns.
        first_call = attach_calls[0]
        self.assertEqual(first_call[0][1], 0)  # column
        self.assertEqual(first_call[0][2], 0)  # row
        self.assertEqual(first_call[0][3], 4)  # columnspan

    def test_no_stale_indicator_when_fresh(self):
        with mock_gtk() as gtk_mock:
            with patch.object(dp, "Gtk", gtk_mock):
                app = MagicMock()
                grid = MagicMock()
                app.dashboard_pool_grid = grid
                pools = [{
                    "name": "tank",
                    "health": "ONLINE",
                    "cap": "50%",
                    "cap_int": 50,
                    "scrub_date": "Sun May 10 00:24:03 2026",
                }]
                dp._refresh_pool_section(app, pools, scrub_states={}, stale=False)

        attach_calls = grid.attach.call_args_list
        # Stale label would span 4 columns at row 0; ensure no such call exists.
        stale_calls = [
            c for c in attach_calls
            if c[0][2] == 0 and c[0][3] == 4
        ]
        self.assertEqual(stale_calls, [])

    def test_scrub_date_label_is_monospace(self):
        with mock_gtk() as gtk_mock:
            # Give each Gtk.Label a distinct mock so the header and value can
            # be told apart.
            gtk_mock.Label.side_effect = lambda *args, **kwargs: MagicMock()
            with patch.object(dp, "Gtk", gtk_mock):
                app = MagicMock()
                grid = MagicMock()
                app.dashboard_pool_grid = grid
                pools = [{
                    "name": "tank",
                    "health": "ONLINE",
                    "cap": "50%",
                    "cap_int": 50,
                    "scrub_date": "Sun May 10 00:24:03 2026",
                }]
                dp._refresh_pool_section(app, pools, scrub_states={}, stale=False)

        # Column 2 contains both the "Last Scrub" header and the per-pool
        # value label; find the label that was styled as monospace.
        scrub_labels = [c[0][0] for c in grid.attach.call_args_list if c[0][1] == 2]
        styled = [
            lbl for lbl in scrub_labels
            if lbl.get_style_context.return_value.add_class.called
        ]
        self.assertEqual(len(styled), 1)
        scrub_label = styled[0]
        scrub_label.get_style_context.return_value.add_class.assert_called_once_with(
            "monospace"
        )


class TestRefreshDashboardCache(unittest.TestCase):

    def _refresh_patches(self):
        """Return a stack of patches for refresh_dashboard_page dependencies."""
        return [
            patch.object(dp, "_get_pool_health", return_value=None),
            patch.object(dp, "_get_iscsi_missing_luns", return_value=[]),
            patch.object(dp, "_count_stale_locks", return_value=0),
            patch("scrub_manager.get_all_pool_scrub_states", return_value={}),
            patch.object(dp, "_get_recent_entries", return_value=[]),
            patch.object(dp, "_get_warnings", return_value=[]),
            patch.object(dp, "_refresh_config_section"),
            patch.object(dp, "_refresh_pool_section"),
            patch.object(dp, "_refresh_ops_section"),
            patch.object(dp, "_refresh_iscsi_section"),
            patch.object(dp, "_refresh_warnings_section"),
            patch.object(dp, "_refresh_processes_section"),
            patch.object(dp, "_update_fix_locks_button"),
            patch.object(dp, "_is_two_node", return_value=False),
        ]

    def test_uses_cached_pools_when_zpool_list_fails(self):
        app = MagicMock()
        app.config = {}
        cached = [{
            "name": "tank",
            "health": "ONLINE",
            "cap": "50%",
            "cap_int": 50,
            "scrub_date": "Sun May 10 00:24:03 2026",
        }]
        app._dashboard_pools = cached

        patches = self._refresh_patches()
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            dp._get_pool_health.return_value = None
            dp.refresh_dashboard_page(app)
            mock_pool = dp._refresh_pool_section

        mock_pool.assert_called_once()
        self.assertEqual(mock_pool.call_args[0][1], cached)
        self.assertTrue(mock_pool.call_args[1]["stale"])

    def test_clears_stale_flag_after_successful_fetch(self):
        app = MagicMock()
        app.config = {}
        app._dashboard_pools = [{"name": "old"}]
        app._dashboard_pools_stale = True
        fresh = [{
            "name": "tank",
            "health": "ONLINE",
            "cap": "50%",
            "cap_int": 50,
            "scrub_date": "Sun May 10 00:24:03 2026",
        }]

        patches = self._refresh_patches()
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            dp._get_pool_health.return_value = fresh
            dp.refresh_dashboard_page(app)
            mock_pool = dp._refresh_pool_section

        self.assertEqual(app._dashboard_pools, fresh)
        self.assertFalse(app._dashboard_pools_stale)
        mock_pool.assert_called_once()
        self.assertEqual(mock_pool.call_args[0][1], fresh)
        self.assertFalse(mock_pool.call_args[1]["stale"])


class TestUpdateFixLocksButton(unittest.TestCase):

    def test_enables_when_stale_present(self):
        app = MagicMock()
        btn = MagicMock()
        app._fix_locks_button = btn
        dp._update_fix_locks_button(app, 3)
        btn.set_sensitive.assert_called_once_with(True)

    def test_disables_when_no_stale(self):
        app = MagicMock()
        btn = MagicMock()
        app._fix_locks_button = btn
        dp._update_fix_locks_button(app, 0)
        btn.set_sensitive.assert_called_once_with(False)

    def test_no_button_attr_does_not_crash(self):
        app = MagicMock()
        del app._fix_locks_button
        dp._update_fix_locks_button(app, 5)
        # Should not raise


class TestViewLogButton(unittest.TestCase):
    """Dashboard View Log button tracks recent operations selection."""

    def _make_app_and_selection(self, selected_iter):
        app = MagicMock()
        app._view_log_button = MagicMock()
        ops_selection = MagicMock()
        ops_selection.get_selected.return_value = (MagicMock(), selected_iter)
        app.dashboard_ops_view.get_selection.return_value = ops_selection

        tasks_selection = MagicMock()
        tasks_selection.get_selected_rows.return_value = (MagicMock(), [])
        app.dashboard_tasks_view.get_selection.return_value = tasks_selection
        return app, ops_selection

    def test_starts_disabled_when_no_operation_selected(self):
        app, selection = self._make_app_and_selection(None)
        dp.setup_dashboard_actions(app)
        selection.connect.assert_called()
        app._view_log_button.set_sensitive.assert_called_with(False)

    def test_enables_when_operation_selected(self):
        app, selection = self._make_app_and_selection(MagicMock())
        dp.setup_dashboard_actions(app)
        app._view_log_button.set_sensitive.assert_called_with(True)

    def test_toggles_with_selection_changes(self):
        app, selection = self._make_app_and_selection(None)
        dp.setup_dashboard_actions(app)
        app._view_log_button.reset_mock()

        selection.get_selected.return_value = (MagicMock(), MagicMock())
        callback = selection.connect.call_args_list[0][0][1]
        callback(selection, app)
        app._view_log_button.set_sensitive.assert_called_once_with(True)

    def test_no_button_attr_does_not_crash(self):
        app, selection = self._make_app_and_selection(None)
        del app._view_log_button
        dp.setup_dashboard_actions(app)


class TestOnDashboardViewLog(unittest.TestCase):

    def _make_app(self, log_path):
        app = MagicMock()
        model = MagicMock()
        tree_iter = MagicMock()
        model.get_value.return_value = log_path
        selection = MagicMock()
        selection.get_selected.return_value = (model, tree_iter)
        app.dashboard_ops_view.get_selection.return_value = selection
        return app, model

    @patch("dashboard_page.select_log_by_path", return_value=True)
    def test_switches_to_logs_and_selects_path(self, mock_select):
        app, model = self._make_app("/var/log/zfsutilities/sessions/test.log")
        dp.on_dashboard_view_log(app)
        app.stack.set_visible_child_name.assert_called_once_with("logs")
        tree_iter = app.dashboard_ops_view.get_selection.return_value.get_selected.return_value[1]
        model.get_value.assert_called_once_with(tree_iter, 4)
        mock_select.assert_called_once_with(app, "/var/log/zfsutilities/sessions/test.log")

    @patch("dashboard_page.select_log_by_path")
    def test_warns_when_no_selection(self, mock_select):
        app, _model = self._make_app("")
        app.dashboard_ops_view.get_selection.return_value.get_selected.return_value = (
            MagicMock(), None,
        )
        with capture_logs() as logs:
            dp.on_dashboard_view_log(app)
        self.assertTrue(any("No recent operation selected" in msg for msg in logs))
        mock_select.assert_not_called()

    @patch("dashboard_page.select_log_by_path")
    def test_warns_when_no_log_file(self, mock_select):
        app, _model = self._make_app("")
        with capture_logs() as logs:
            dp.on_dashboard_view_log(app)
        self.assertTrue(any("No log file recorded" in msg for msg in logs))
        mock_select.assert_not_called()

    @patch("dashboard_page.select_log_by_path", return_value=False)
    def test_warns_when_log_not_found(self, mock_select):
        app, _model = self._make_app("/missing.log")
        with capture_logs() as logs:
            dp.on_dashboard_view_log(app)
        self.assertTrue(any("Log entry not found" in msg for msg in logs))


class TestRefreshOpsSection(unittest.TestCase):

    def test_log_file_stored_in_hidden_column(self):
        with mock_gtk() as gtk_mock:
            with patch.object(dp, "Gtk", gtk_mock):
                app = MagicMock()
                store = MagicMock()
                app.dashboard_ops_store = store
                recent = [{
                    "timestamp": "2026-05-28T14:32:00",
                    "type": "backup",
                    "name": "Daily",
                    "result": "success",
                    "log_file": "/var/log/zfsutilities/sessions/daily.log",
                }]
                dp._refresh_ops_section(app, recent)
        store.append.assert_called_once()
        appended = store.append.call_args[0][0]
        self.assertEqual(appended[4], "/var/log/zfsutilities/sessions/daily.log")


class TestCreateDashboardPage(unittest.TestCase):
    """Dashboard page layout and widget creation."""

    def _create_app(self):
        app = MagicMock()
        app.config = {}
        app._ui_state = MagicMock()
        app.enable_treeview_copy = MagicMock()
        return app

    def _run_create(self, app, two_node=False):
        with mock_gtk() as gtk_mock:
            # Use factory classes so each widget is a distinct instance.
            gtk_mock.Box = _WidgetRecorder
            gtk_mock.Frame = _WidgetRecorder
            gtk_mock.ScrolledWindow = _WidgetRecorder
            gtk_mock.Label = MagicMock
            with patch.object(dp, "Gtk", gtk_mock):
                with patch.object(dp, "refresh_dashboard_page"):
                    with patch.object(dp, "_is_two_node", return_value=two_node):
                        page = dp.create_dashboard_page(app)
        return page

    def test_creates_expected_frames_and_widgets(self):
        app = self._create_app()
        self._run_create(app)
        self.assertIsNotNone(app.dashboard_warn_frame)
        self.assertIsNotNone(app.dashboard_pool_frame)
        self.assertIsNotNone(app.dashboard_proc_frame)
        self.assertIsNotNone(app.dashboard_ops_frame)
        self.assertIsNotNone(app.dashboard_iscsi_frame)
        self.assertIsNotNone(app.dashboard_config_frame)
        self.assertIsNotNone(app.dashboard_pool_grid)
        self.assertIsNotNone(app.dashboard_threshold_spin)
        self.assertIsNotNone(app.dashboard_tasks_view)
        self.assertIsNotNone(app.dashboard_ops_view)
        self.assertIsNotNone(app.dashboard_ops_store)
        self.assertIsNotNone(app.dashboard_tasks_store)

    def test_section_order_in_top_level_box(self):
        app = self._create_app()
        page = self._run_create(app)
        top_box = page.children[0]
        expected_titles = [
            "<b>Warnings</b>",
            "<b>Pool Health</b>",
            "<b>Running Tasks</b>",
            "<b>Recent Operations</b>",
            "<b>iSCSI Issues</b>",
            "<b>Configuration</b>",
        ]
        frame_children = top_box.children[1:]
        self.assertEqual(len(frame_children), 6)
        self.assertEqual([_frame_title(f) for f in frame_children], expected_titles)

    def test_threshold_spinner_inside_pool_health(self):
        app = self._create_app()
        self._run_create(app)
        pool_box = app.dashboard_pool_frame.children[0]
        self.assertEqual(len(pool_box.children), 2)
        threshold_box = pool_box.children[0]
        self.assertIn(app.dashboard_threshold_spin, threshold_box.children)
        pool_grid_sw = pool_box.children[1]
        self.assertIsInstance(pool_grid_sw, _WidgetRecorder)
        self.assertIn(app.dashboard_pool_grid, pool_grid_sw.children)

    def test_pool_health_grid_is_horizontally_scrollable(self):
        app = self._create_app()
        self._run_create(app)
        pool_box = app.dashboard_pool_frame.children[0]
        pool_grid_sw = pool_box.children[1]
        self.assertIsInstance(pool_grid_sw, _WidgetRecorder)
        pool_grid_sw.set_policy.assert_called_once()
        pool_grid_sw.set_propagate_natural_height.assert_called_once_with(True)
        self.assertIn(app.dashboard_pool_grid, pool_grid_sw.children)

    def test_threshold_spinner_configuration(self):
        app = self._create_app()
        self._run_create(app)
        spin = app.dashboard_threshold_spin
        spin.set_range.assert_called_once_with(50, 95)
        spin.set_increments.assert_called_once_with(5, 5)
        spin.set_value.assert_called_once_with(80)
        args = spin.connect.call_args[0]
        self.assertEqual(args[0], "value-changed")
        self.assertTrue(callable(args[1]))
        self.assertIs(args[2], app)

    def test_iscsi_frame_hidden_in_single_node_mode(self):
        app = self._create_app()
        self._run_create(app, two_node=False)
        app.dashboard_iscsi_frame.hide.assert_called_once()

    def test_iscsi_frame_not_hidden_in_two_node_mode(self):
        app = self._create_app()
        self._run_create(app, two_node=True)
        app.dashboard_iscsi_frame.hide.assert_not_called()


class TestCancelSelectedButton(unittest.TestCase):
    """Dashboard Cancel Selected Tasks button tracks task selection."""

    def _make_app_and_selection(self, pathlist, task_keys=None):
        app = MagicMock()
        app._cancel_selected_button = MagicMock()
        tasks_selection = MagicMock()
        model = MagicMock()
        task_keys = task_keys if task_keys is not None else [""] * len(pathlist)

        model.get_iter.return_value = MagicMock()
        model.get_value.side_effect = task_keys
        tasks_selection.get_selected_rows.return_value = (model, pathlist)
        app.dashboard_tasks_view.get_selection.return_value = tasks_selection

        ops_selection = MagicMock()
        ops_selection.get_selected.return_value = (MagicMock(), None)
        app.dashboard_ops_view.get_selection.return_value = ops_selection
        return app, tasks_selection

    def test_starts_disabled_when_no_tasks_selected(self):
        app, selection = self._make_app_and_selection([])
        dp.setup_dashboard_actions(app)
        selection.connect.assert_called()
        app._cancel_selected_button.set_sensitive.assert_called_once_with(False)

    def test_enables_when_tasks_are_selected(self):
        app, selection = self._make_app_and_selection(
            [MagicMock()], task_keys=["runner:backup_runner"]
        )
        dp.setup_dashboard_actions(app)
        app._cancel_selected_button.set_sensitive.assert_called_once_with(True)

    def test_toggles_with_selection_changes(self):
        app, selection = self._make_app_and_selection([])
        dp.setup_dashboard_actions(app)
        # reset after initial call
        app._cancel_selected_button.reset_mock()

        # Simulate a selection-change callback with a task selected
        path = MagicMock()
        model = selection.get_selected_rows.return_value[0]
        model.get_value.side_effect = ["runner:backup_runner"]
        selection.get_selected_rows.return_value = (model, [path])
        callback = selection.connect.call_args[0][1]
        callback(selection, app)
        app._cancel_selected_button.set_sensitive.assert_called_once_with(True)

    def test_disabled_when_only_placeholder_selected(self):
        """Selecting the 'No running tasks' placeholder keeps Cancel disabled."""
        app, selection = self._make_app_and_selection(
            [MagicMock()], task_keys=[""]
        )
        dp.setup_dashboard_actions(app)
        app._cancel_selected_button.set_sensitive.assert_called_once_with(False)

    def test_enabled_with_mixed_placeholder_and_real_task(self):
        """A mixed selection containing a real task enables Cancel."""
        app, selection = self._make_app_and_selection(
            [MagicMock(), MagicMock()], task_keys=["", "profile:Daily"]
        )
        dp.setup_dashboard_actions(app)
        app._cancel_selected_button.set_sensitive.assert_called_once_with(True)

    def test_no_button_attr_does_not_crash(self):
        app, selection = self._make_app_and_selection([])
        del app._cancel_selected_button
        dp.setup_dashboard_actions(app)
        # Should not raise


class TestGetHostZfsVersion(unittest.TestCase):
    """_get_host_zfs_version() runs ``zfs version`` locally or via SSH."""

    @patch("dashboard_page._local_hostname", return_value="myhost")
    def test_local_returns_zfs_version_output(self, _mock_host):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "zfs-2.2.2\nzfs-kmod-2.2.2\n"
            ver = dp._get_host_zfs_version("myhost")
        self.assertEqual(ver, "zfs-2.2.2\nzfs-kmod-2.2.2")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertEqual(args, ["zfs", "version"])

    @patch("dashboard_page._local_hostname", return_value="myhost")
    def test_local_failure_returns_unknown(self, _mock_host):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            ver = dp._get_host_zfs_version("myhost")
        self.assertEqual(ver, "unknown")

    @patch("dashboard_page._local_hostname", return_value="myhost")
    def test_remote_returns_zfs_version_output(self, _mock_host):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "zfs-2.1.5\nzfs-kmod-2.1.5\n"
            ver = dp._get_host_zfs_version("remote1")
        self.assertEqual(ver, "zfs-2.1.5\nzfs-kmod-2.1.5")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertIn("root@remote1", args)
        self.assertIn("zfs version", args)

    @patch("dashboard_page._local_hostname", return_value="myhost")
    def test_remote_ssh_failure_returns_unknown(self, _mock_host):
        with patch("subprocess.run", side_effect=OSError("no route")):
            ver = dp._get_host_zfs_version("remote1")
        self.assertEqual(ver, "unknown")


class TestRefreshConfigSection(unittest.TestCase):
    """_refresh_config_section() populates the Configuration card grid."""

    def _run_refresh(self, cfg, versions, zfs_versions):
        """Call _refresh_config_section with mocked dependencies.

        Returns the app mock and the mock Gtk object so callers can inspect
        the labels that were created.
        """
        with mock_gtk() as gtk_mock:
            gtk_mock.Label.side_effect = lambda *args, **kwargs: MagicMock()
            with patch.object(dp, "Gtk", gtk_mock):
                with patch.object(dp, "_get_node_config", return_value=cfg):
                    with patch.object(
                        dp, "_get_host_version", side_effect=versions.get
                    ):
                        with patch.object(
                            dp,
                            "_get_host_zfs_version",
                            side_effect=zfs_versions.get,
                        ):
                            app = MagicMock()
                            app.dashboard_config_grid = MagicMock()
                            dp._refresh_config_section(app)
        return app, gtk_mock

    def _find_label_with_text(self, gtk_mock, text):
        """Return True if any Gtk.Label call created a label with the text."""
        for call in gtk_mock.Label.call_args_list:
            if call.kwargs.get("label") == text:
                return True
        return False

    def test_single_node_shows_local_zfs_version(self):
        cfg = {
            "mode": "single-node",
            "this_host": "myhost",
            "storage_host": "",
            "compute_host": "",
        }
        _app, gtk_mock = self._run_refresh(
            cfg,
            versions={"myhost": "1.2.3"},
            zfs_versions={"myhost": "zfs-2.2.2"},
        )
        # The grid attach method should have been called for the ZFS value.
        self.assertTrue(self._find_label_with_text(gtk_mock, "zfs-2.2.2"))

    def test_two_node_shows_zfs_version_per_unique_host(self):
        cfg = {
            "mode": "two-node",
            "this_host": "host-a",
            "storage_host": "host-b",
            "compute_host": "host-c",
        }
        _app, gtk_mock = self._run_refresh(
            cfg,
            versions={"host-a": "1.0", "host-b": "1.0", "host-c": "1.0"},
            zfs_versions={
                "host-a": "zfs-2.2.2",
                "host-b": "zfs-2.2.3",
                "host-c": "zfs-2.2.4",
            },
        )
        expected = (
            "host-a (this):\n"
            "zfs-2.2.2\n\n"
            "host-b (storage):\n"
            "zfs-2.2.3\n\n"
            "host-c (compute):\n"
            "zfs-2.2.4"
        )
        self.assertTrue(self._find_label_with_text(gtk_mock, expected))

    def test_two_node_deduplicates_same_host_across_roles(self):
        cfg = {
            "mode": "two-node",
            "this_host": "host-a",
            "storage_host": "host-a",
            "compute_host": "host-b",
        }
        _app, gtk_mock = self._run_refresh(
            cfg,
            versions={"host-a": "1.0", "host-b": "1.0"},
            zfs_versions={"host-a": "zfs-2.2.2", "host-b": "zfs-2.2.3"},
        )
        expected = (
            "host-a (this,storage):\n"
            "zfs-2.2.2\n\n"
            "host-b (compute):\n"
            "zfs-2.2.3"
        )
        self.assertTrue(self._find_label_with_text(gtk_mock, expected))


class TestFixIscsiButton(unittest.TestCase):
    """Tests for the Dashboard "Fix this" iSCSI repair button."""

    def _create_app(self):
        app = MagicMock()
        app.config = {}
        return app

    def test_fix_iscsi_runs_repair_script(self):
        app = self._create_app()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "rescan complete\n"
            mock_run.return_value.stderr = ""
            with patch.object(dp, "refresh_dashboard_page") as mock_refresh:
                dp._on_fix_iscsi_clicked(None, app)

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertEqual(args[0], "/usr/local/lib/zfsutilities/bin/repair-iscsi-luns")
        mock_refresh.assert_called_once_with(app)

    def test_fix_iscsi_logs_nonzero_exit(self):
        app = self._create_app()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = "something failed"
            with patch.object(dp, "refresh_dashboard_page"):
                with capture_logs() as logs:
                    dp._on_fix_iscsi_clicked(None, app)

        self.assertTrue(
            any("repair-iscsi-luns exited 1" in msg for msg in logs)
        )

    def test_fix_iscsi_logs_failure(self):
        app = self._create_app()
        with patch("subprocess.run", side_effect=OSError("no such file")):
            with patch.object(dp, "refresh_dashboard_page"):
                with capture_logs() as logs:
                    dp._on_fix_iscsi_clicked(None, app)

        self.assertTrue(
            any("repair-iscsi-luns failed" in msg for msg in logs)
        )


if __name__ == "__main__":
    unittest.main()

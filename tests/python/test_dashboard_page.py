"""Tests for dashboard_page.py — data gathering and warning logic."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

import feature_config
from logging_config import parse_msg_level
from test_support import (
    capture_logs,
    import_or_skip_gi,
    mock_gtk,
    mock_subprocess,
    requires_gi,
    temp_config_dir,
)

pytestmark = requires_gi

dp = import_or_skip_gi("dashboard_page")
gh = import_or_skip_gi("gui_helpers")


def _write_lock_file(path, dataset, pid, lock_type="w"):
    """Write a lock file in the format produced by zfslockmanager."""
    content = json.dumps(
        {
            "dataset": dataset,
            "type": lock_type,
            "pid": pid,
            "script": "test",
            "acquired": "2026-01-01T00:00:00-05:00",
            "description": "test lock",
        }
    )
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


def _make_tasks_selection_app(rows):
    """Build an app whose Tasks selection exposes per-row hidden columns.

    ``rows`` is a list of dicts whose task_key / state / log_file keys
    mirror the merged Tasks store's hidden columns (5 / 4 / 6).  Row
    dicts stay live, so tests can mutate a row and re-invoke the
    selection callback to simulate a selection change.
    """
    app = MagicMock()
    model = MagicMock()
    iters = [MagicMock() for _ in rows]
    paths = [MagicMock() for _ in rows]

    def get_value(tree_iter, col):
        row = rows[iters.index(tree_iter)]
        if col == 4:
            return row.get("state", "")
        if col == 5:
            return row.get("task_key", "")
        if col == 6:
            return row.get("log_file", "")
        if col == 7:
            return row.get("completed_key", row.get("log_file", ""))
        return ""

    model.get_value.side_effect = get_value

    def get_iter(path):
        return iters[paths.index(path)]

    model.get_iter.side_effect = get_iter

    selection = MagicMock()
    selection.get_selected_rows.return_value = (model, paths)
    app.dashboard_tasks_view.get_selection.return_value = selection
    return app, selection


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
            # The default mock only outputs default columns; override for 7 columns
            m.set_command_handler(
                r"zpool list -H -o name,health,size,alloc,free,cap",
                lambda *_a, **_k: m._completed("tank\tONLINE\t10T\t5T\t5T\t75%\t-\n"),
            )
            m.set_command_handler(r"zpool status", lambda *_a, **_k: m._completed(""))
            pools = dp._get_pool_health()
        self.assertEqual(len(pools), 1)
        self.assertEqual(pools[0]["name"], "tank")
        self.assertEqual(pools[0]["health"], "ONLINE")
        self.assertEqual(pools[0]["cap"], "75%")
        self.assertEqual(pools[0]["cap_int"], 75)
        self.assertEqual(pools[0]["ckpoint"], "-")

    def test_scrub_date_parsed(self):
        with mock_subprocess() as m:
            m.set_command_handler(
                r"zpool list -H -o name,health,size,alloc,free,cap",
                lambda *_a, **_k: m._completed("tank\tONLINE\t10T\t5T\t5T\t50%\t-\n"),
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
                lambda *_a, **_k: m._completed("tank\tONLINE\t10T\t5T\t5T\t50%\t-\n"),
            )
            status = "  scan: scrub in progress since Sun May 10 00:24:03 2026\n"
            m.set_command_handler(r"zpool status", lambda *_a, **_k: m._completed(status))
            pools = dp._get_pool_health()
        self.assertEqual(pools[0]["scrub_date"], "In progress")

    def test_scrub_date_parsed_with_days_duration(self):
        with mock_subprocess() as m:
            m.set_command_handler(
                r"zpool list -H -o name,health,size,alloc,free,cap",
                lambda *_a, **_k: m._completed("tank\tONLINE\t10T\t5T\t5T\t50%\t-\n"),
            )
            status = (
                "  scan: scrub repaired 0B in 1 days 01:35:48 with 0 errors on "
                "Wed Jun  3 20:50:19 2026\n"
            )
            m.set_command_handler(r"zpool status", lambda *_a, **_k: m._completed(status))
            pools = dp._get_pool_health()
        self.assertEqual(pools[0]["scrub_date"], "Wed Jun  3 20:50:19 2026")

    def test_scrub_date_canceled(self):
        with mock_subprocess() as m:
            m.set_command_handler(
                r"zpool list -H -o name,health,size,alloc,free,cap",
                lambda *_a, **_k: m._completed("tank\tONLINE\t10T\t5T\t5T\t50%\t-\n"),
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
        with patch.object(dp.node_config, "load_node_config", return_value={"mode": "single-node"}):
            result = dp._is_two_node()
            self.assertFalse(result)

    def test_two_node_conf(self):
        with patch.object(dp.node_config, "load_node_config", return_value={"mode": "two-node"}):
            result = dp._is_two_node()
            self.assertTrue(result)

    def test_no_conf(self):
        with patch.object(dp.node_config, "load_node_config", return_value={"mode": "single-node"}):
            result = dp._is_two_node()
            self.assertFalse(result)


class TestGetNodeConfig(unittest.TestCase):
    @patch("dashboard_page._local_hostname", return_value="myhost")
    def test_no_conf_defaults_single_node(self, _mock):
        with patch.object(
            dp.node_config,
            "load_node_config",
            return_value={
                "mode": "single-node",
                "storage_host": "myhost",
                "compute_host": "myhost",
                "storage_ip": "",
                "pools": set(),
            },
        ):
            cfg = dp._get_node_config()
        self.assertEqual(cfg["mode"], "single-node")
        self.assertEqual(cfg["this_host"], "myhost")
        self.assertEqual(cfg["storage_host"], "myhost")
        self.assertEqual(cfg["compute_host"], "myhost")

    @patch("dashboard_page._local_hostname", return_value="myhost")
    def test_single_node_conf(self, _mock):
        with patch.object(
            dp.node_config,
            "load_node_config",
            return_value={
                "mode": "single-node",
                "storage_host": "myhost",
                "compute_host": "myhost",
                "storage_ip": "",
                "pools": set(),
            },
        ):
            cfg = dp._get_node_config()
        self.assertEqual(cfg["mode"], "single-node")
        self.assertEqual(cfg["storage_host"], "myhost")
        self.assertEqual(cfg["compute_host"], "myhost")

    @patch("dashboard_page._local_hostname", return_value="myhost")
    def test_two_node_conf(self, _mock):
        with patch.object(
            dp.node_config,
            "load_node_config",
            return_value={
                "mode": "two-node",
                "storage_host": "storage1",
                "compute_host": "compute1",
                "storage_ip": "192.168.1.10",
                "pools": {"threeamigos", "fivebays"},
            },
        ):
            cfg = dp._get_node_config()
        self.assertEqual(cfg["mode"], "two-node")
        self.assertEqual(cfg["storage_host"], "storage1")
        self.assertEqual(cfg["compute_host"], "compute1")
        self.assertEqual(cfg["storage_ip"], "192.168.1.10")


class TestGetPeerHost(unittest.TestCase):
    def test_storage_peer_is_compute(self):
        with patch.object(
            dp.node_config,
            "load_node_config",
            return_value={
                "mode": "two-node",
                "this_host": "storage1",
                "storage_host": "storage1",
                "compute_host": "compute1",
            },
        ):
            self.assertEqual(dp._get_peer_host(), "compute1")

    def test_compute_peer_is_storage(self):
        with patch.object(
            dp.node_config,
            "load_node_config",
            return_value={
                "mode": "two-node",
                "this_host": "compute1",
                "storage_host": "storage1",
                "compute_host": "compute1",
            },
        ):
            self.assertEqual(dp._get_peer_host(), "storage1")

    def test_single_node_returns_none(self):
        with patch.object(
            dp.node_config,
            "load_node_config",
            return_value={
                "mode": "single-node",
                "this_host": "myhost",
                "storage_host": "myhost",
                "compute_host": "myhost",
            },
        ):
            self.assertIsNone(dp._get_peer_host())

    def test_no_conf_returns_none(self):
        with patch.object(
            dp.node_config,
            "load_node_config",
            return_value={
                "mode": "single-node",
                "this_host": "myhost",
                "storage_host": "myhost",
                "compute_host": "myhost",
            },
        ):
            self.assertIsNone(dp._get_peer_host())

    def test_unknown_local_returns_non_local_host(self):
        """If the local host matches neither role, return a non-local host."""
        with patch.object(
            dp.node_config,
            "load_node_config",
            return_value={
                "mode": "two-node",
                "this_host": "unexpected",
                "storage_host": "storage1",
                "compute_host": "compute1",
            },
        ):
            self.assertEqual(dp._get_peer_host(), "storage1")

    def test_both_roles_local_returns_none(self):
        with patch.object(
            dp.node_config,
            "load_node_config",
            return_value={
                "mode": "two-node",
                "this_host": "storage1",
                "storage_host": "storage1",
                "compute_host": "storage1",
            },
        ):
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
    @patch("dashboard_page.get_version", return_value="1.2.3")
    def test_local_repo_version(self, _mock_version, _mock_host):
        ver = dp._get_host_version("myhost")
        self.assertEqual(ver, "1.2.3")

    @patch("dashboard_page._local_hostname", return_value="myhost")
    @patch("dashboard_page.get_version", return_value="unknown")
    def test_local_no_version_file(self, _mock_version, _mock_host):
        ver = dp._get_host_version("myhost")
        self.assertEqual(ver, "unknown")

    @patch("dashboard_page._local_hostname", return_value="myhost")
    @patch("dashboard_page.resolve_remote_version")
    def test_remote_version(self, mock_remote, _mock_host):
        mock_remote.return_value = "2.0.0"
        ver = dp._get_host_version("remote1")
        self.assertEqual(ver, "2.0.0")
        mock_remote.assert_called_once_with("remote1")

    @patch("dashboard_page._local_hostname", return_value="myhost")
    @patch("dashboard_page.resolve_remote_version", return_value="unknown")
    def test_remote_ssh_failure(self, _mock_remote, _mock_host):
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


class TestFormatIscsiMissingMessage(unittest.TestCase):
    """_format_iscsi_missing_message() produces user-friendly text."""

    def test_standard_backstore_name(self):
        lun = {"name": "vm-207-disk-2", "target": "threeamigos"}
        msg = dp._format_iscsi_missing_message(lun)
        self.assertIn("VM 207 disk 2", msg)
        self.assertIn("vm-207-disk-2", msg)
        self.assertIn("threeamigos", msg)
        self.assertIn("not exported", msg)

    def test_unexpected_backstore_name(self):
        lun = {"name": "custom-disk-1", "target": "threeamigos"}
        msg = dp._format_iscsi_missing_message(lun)
        self.assertIn("Disk custom-disk-1", msg)
        self.assertIn("threeamigos", msg)

    def test_missing_name_defaults_to_placeholder(self):
        lun = {"target": "threeamigos"}
        msg = dp._format_iscsi_missing_message(lun)
        self.assertIn("Disk ?", msg)


class TestRefreshIscsiSection(unittest.TestCase):
    """_refresh_iscsi_section() renders user-friendly iSCSI warnings."""

    def _run_refresh(self, missing_luns):
        labels = []
        label_kwargs = []
        buttons = []
        button_kwargs = []

        def make_label(*args, **kwargs):
            label_kwargs.append(kwargs)
            lbl = MagicMock()
            labels.append(lbl)
            return lbl

        def make_button(*args, **kwargs):
            button_kwargs.append(kwargs)
            btn = MagicMock()
            buttons.append(btn)
            return btn

        with mock_gtk() as gtk_mock:
            gtk_mock.Label.side_effect = make_label
            gtk_mock.Button.side_effect = make_button
            with patch.object(dp, "Gtk", gtk_mock):
                app = MagicMock()
                app.dashboard_iscsi_box.get_children.return_value = []
                dp._refresh_iscsi_section(app, missing_luns)
        return app, labels, label_kwargs, buttons, button_kwargs

    def test_healthy_message(self):
        _app, labels, label_kwargs, _buttons, _button_kwargs = self._run_refresh([])
        label_texts = [kwargs.get("label") for kwargs in label_kwargs if kwargs.get("label")]
        label_texts.extend(call.args[0] for lbl in labels for call in lbl.set_markup.call_args_list)
        self.assertTrue(
            any("All VM disks are exported" in text for text in label_texts),
            f"Expected healthy message in {label_texts}",
        )

    def test_missing_lun_label_is_user_friendly(self):
        _app, labels, _label_kwargs, _buttons, _button_kwargs = self._run_refresh(
            [{"name": "vm-207-disk-2", "target": "threeamigos"}]
        )
        markup_texts = [call.args[0] for lbl in labels for call in lbl.set_markup.call_args_list]
        self.assertTrue(
            any("VM 207 disk 2" in text for text in markup_texts),
            f"Expected user-friendly markup in {markup_texts}",
        )
        self.assertTrue(
            any("vm-207-disk-2" in text for text in markup_texts),
            f"Expected backstore name in {markup_texts}",
        )

    def test_tooltip_set_on_label_and_button(self):
        _app, labels, _label_kwargs, buttons, _button_kwargs = self._run_refresh(
            [{"name": "vm-207-disk-2", "target": "threeamigos"}]
        )
        label_tooltips = [
            call.args[0] for lbl in labels for call in lbl.set_tooltip_text.call_args_list
        ]
        button_tooltips = [
            call.args[0] for btn in buttons for call in btn.set_tooltip_text.call_args_list
        ]
        self.assertTrue(
            any("Each VM disk is a ZFS zvol" in t for t in label_tooltips),
            "Expected tooltip text on a label",
        )
        self.assertTrue(
            any("Each VM disk is a ZFS zvol" in t for t in button_tooltips),
            "Expected tooltip text on the Fix this button",
        )


class TestLockPid(unittest.TestCase):
    """_lock_pid() extracts PIDs from lock files."""

    def test_reads_pid_from_json_lock_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            locks_dir = os.path.join(tmpdir, ".locks")
            os.makedirs(locks_dir)
            lock_file = os.path.join(locks_dir, "pool%2Fdataset.lock")
            _write_lock_file(lock_file, "pool/dataset", 12345)

            with patch.object(dp, "ZFSLOCK_LOCKS_DIR", locks_dir):
                with patch.object(dp, "ZFSLOCK_PIDS_DIR", os.path.join(tmpdir, ".pids")):
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
                with patch.object(dp, "ZFSLOCK_PIDS_DIR", os.path.join(tmpdir, ".pids")):
                    pid = dp._lock_pid("bad.lock")
            self.assertIsNone(pid)

    def test_returns_none_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            locks_dir = os.path.join(tmpdir, ".locks")
            os.makedirs(locks_dir)

            with patch.object(dp, "ZFSLOCK_LOCKS_DIR", locks_dir):
                with patch.object(dp, "ZFSLOCK_PIDS_DIR", os.path.join(tmpdir, ".pids")):
                    pid = dp._lock_pid("missing.lock")
            self.assertIsNone(pid)

    def test_fallback_to_pid_embedded_in_filename(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            locks_dir = os.path.join(tmpdir, ".locks")
            os.makedirs(locks_dir)

            with patch.object(dp, "ZFSLOCK_LOCKS_DIR", locks_dir):
                with patch.object(dp, "ZFSLOCK_PIDS_DIR", os.path.join(tmpdir, ".pids")):
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


class TestDiskWearWarnings(unittest.TestCase):
    """SSD/NVMe wear at or above 80% produces a dashboard warning."""

    def _disk(self, path, wear, model="", parent=None):
        import types

        return types.SimpleNamespace(path=path, model=model, wear_percent=wear, parent_path=parent)

    def setUp(self):
        dp._disk_wear_cache["time"] = 0.0
        dp._disk_wear_cache["inventory"] = None

    def test_below_threshold_no_warning(self):
        disks = [self._disk("/dev/sda", 79)]
        self.assertEqual(dp._format_disk_wear_warnings(disks), [])

    def test_at_threshold_warns(self):
        disks = [self._disk("/dev/sda", 80, model="Samsung SSD 870 QVO 1TB")]
        self.assertEqual(
            dp._format_disk_wear_warnings(disks),
            ['SSD "/dev/sda" (Samsung SSD 870 QVO 1TB) wear at 80%'],
        )

    def test_missing_wear_skipped(self):
        disks = [self._disk("/dev/sda", None)]
        self.assertEqual(dp._format_disk_wear_warnings(disks), [])

    def test_partitions_warn_once_per_disk(self):
        disks = [
            self._disk("/dev/sda", 92, model="SSD A"),
            self._disk("/dev/sda1", 92, parent="/dev/sda"),
            self._disk("/dev/sda2", 92, parent="/dev/sda"),
        ]
        self.assertEqual(
            dp._format_disk_wear_warnings(disks),
            ['SSD "/dev/sda" (SSD A) wear at 92%'],
        )

    def test_no_model_omits_parens(self):
        disks = [self._disk("/dev/nvme0n1", 95)]
        self.assertEqual(
            dp._format_disk_wear_warnings(disks),
            ['SSD "/dev/nvme0n1" wear at 95%'],
        )

    def test_get_disk_wear_warnings_caches_inventory(self):
        import types

        disk = self._disk("/dev/sda", 85, model="SSD A")
        inventory = types.SimpleNamespace(disks=[disk])
        repo = MagicMock()
        repo.disk_inventory.return_value = inventory
        app = MagicMock()
        app.ctx.disk_repository = repo

        self.assertEqual(len(dp._get_disk_wear_warnings(app)), 1)
        self.assertEqual(len(dp._get_disk_wear_warnings(app)), 1)
        repo.disk_inventory.assert_called_once()

    def test_get_disk_wear_warnings_failure_keeps_cache(self):
        import types

        disk = self._disk("/dev/sda", 88, model="SSD A")
        dp._disk_wear_cache["inventory"] = types.SimpleNamespace(disks=[disk])
        dp._disk_wear_cache["time"] = 0.0  # stale, forcing a refresh attempt
        repo = MagicMock()
        repo.disk_inventory.side_effect = OSError("smartctl exploded")
        app = MagicMock()
        app.ctx.disk_repository = repo

        self.assertEqual(
            dp._get_disk_wear_warnings(app),
            ['SSD "/dev/sda" (SSD A) wear at 88%'],
        )

    def test_active_checkpoint_warning(self):
        pools = [
            {
                "name": "tank",
                "health": "ONLINE",
                "cap": "50%",
                "cap_int": 50,
                "ckpoint": "50G",
            },
        ]
        warnings = dp._get_warnings(pools, {}, threshold=80)
        self.assertEqual(
            warnings,
            ['Pool "tank" has an active ZFS checkpoint (50G)'],
        )

    def test_no_checkpoint_no_warning(self):
        pools = [
            {
                "name": "tank",
                "health": "ONLINE",
                "cap": "50%",
                "cap_int": 50,
                "ckpoint": "-",
            },
        ]
        warnings = dp._get_warnings(pools, {}, threshold=80)
        self.assertEqual(warnings, [])

    def test_missing_checkpoint_field_no_warning(self):
        pools = [
            {
                "name": "tank",
                "health": "ONLINE",
                "cap": "50%",
                "cap_int": 50,
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


class TestOutcomeMarkup(unittest.TestCase):
    """_outcome_markup shows the highest message level, not just failed/✗."""

    def test_fatal_is_red(self):
        markup = dp._outcome_markup({"result": "failed", "highest_level": "FATAL"})
        self.assertIn("#CC0000", markup)
        self.assertIn("FATAL", markup)

    def test_warn_is_amber(self):
        markup = dp._outcome_markup({"result": "failed", "highest_level": "WARN"})
        self.assertIn("#FF8C00", markup)
        self.assertIn("WARN", markup)

    def test_warn_is_not_failed(self):
        markup = dp._outcome_markup({"result": "failed", "highest_level": "WARN"})
        self.assertNotIn("✗", markup)
        self.assertNotIn("failed", markup)

    def test_info_is_green(self):
        markup = dp._outcome_markup({"result": "success", "highest_level": "INFO"})
        self.assertIn("#00AA00", markup)
        self.assertIn("INFO", markup)

    def test_no_level_falls_back_to_success(self):
        markup = dp._outcome_markup({"result": "success"})
        self.assertIn("#00AA00", markup)
        self.assertIn("success", markup)

    def test_no_level_falls_back_to_failure(self):
        markup = dp._outcome_markup({"result": "failed"})
        self.assertIn("#CC0000", markup)
        self.assertIn("failed", markup)

    def test_cancelled_is_amber_not_red(self):
        markup = dp._outcome_markup({"result": "cancelled"})
        self.assertIn("#FF8C00", markup)
        self.assertIn("cancelled", markup)
        self.assertNotIn("#CC0000", markup)
        self.assertNotIn("✗", markup)


class TestAttachHighestLevels(unittest.TestCase):
    """_attach_highest_levels annotates recent entries from the log index."""

    def test_attaches_level_and_saves_index(self):
        recent = [
            {"result": "success", "log_file": "/var/log/zfsutilities/sessions/a.log"},
            {"result": "failed", "log_file": "/var/log/zfsutilities/sessions/b.log"},
            {"result": "success"},
        ]
        index = MagicMock()
        index.update.side_effect = [
            {"highest_level": "WARN"},
            {"highest_level": "FATAL"},
        ]
        with patch.object(dp, "LogIndex") as mock_log_index:
            mock_log_index.load.return_value = index
            dp._attach_highest_levels(recent)
        mock_log_index.load.assert_called_once()
        self.assertEqual(recent[0]["highest_level"], "WARN")
        self.assertEqual(recent[1]["highest_level"], "FATAL")
        self.assertIsNone(recent[2]["highest_level"])
        index.save.assert_called_once()

    def test_load_failure_still_annotates_none(self):
        recent = [{"result": "success", "log_file": "/x.log"}]
        with patch.object(dp, "LogIndex") as mock_log_index:
            mock_log_index.load.side_effect = OSError("no index")
            with capture_logs() as logs:
                dp._attach_highest_levels(recent)
        self.assertIsNone(recent[0]["highest_level"])
        self.assertTrue(any("Could not load log index" in m for m in logs))

    def test_scan_failure_annotates_none_and_continues(self):
        recent = [
            {"result": "success", "log_file": "/bad.log"},
            {"result": "success", "log_file": "/good.log"},
        ]
        index = MagicMock()
        index.update.side_effect = [OSError("bad log"), {"highest_level": "INFO"}]
        with patch.object(dp, "LogIndex") as mock_log_index:
            mock_log_index.load.return_value = index
            with capture_logs() as logs:
                dp._attach_highest_levels(recent)
        self.assertIsNone(recent[0]["highest_level"])
        self.assertEqual(recent[1]["highest_level"], "INFO")
        self.assertTrue(any("Could not scan log file" in m for m in logs))


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


class CollectRunningTasksIdleHostMixin(unittest.TestCase):
    """Pin _collect_running_tasks' host-state reads to an idle host.

    Sections 4-6 of the collector read live state: profile lock files
    (list_running_profiles), the SMART surface-test state file, and a real
    `pgrep -f profile_runner.py` / `ps` scan. Unpinned, any concurrently
    matching process breaks the exact task-list assertions — including the
    pytest runner itself when its command line contains the literal
    `test_profile_runner.py` path, or a genuine profile run on the host.
    Tests that exercise those sections with their own mocks (e.g.
    TestCollectScheduledTasks) override or skip this mixin.
    """

    def setUp(self):
        super().setUp()
        # Enter the patches on a stack owned by addCleanup: a `with` block
        # here would pop them the moment setUp returns.
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(dp, "list_running_profiles", return_value=[]))
        stack.enter_context(
            patch(
                "disk_surface_test.load_surface_test_state",
                return_value={"tests": {}},
            )
        )
        idle_pgrep = stack.enter_context(patch("subprocess.run"))
        idle_pgrep.return_value = MagicMock(returncode=1, stdout="")


class TestCollectRunningTasks(CollectRunningTasksIdleHostMixin):
    def test_no_tasks_when_everything_idle(self):
        app = MagicMock()
        app.backup_runner = None
        app.offsite_runner = None
        app.restore_runner = None
        app.retention_runner = None
        app.dataset_runner = None
        app.scrub_queue = None
        tasks = dp._collect_running_tasks(app)
        self.assertEqual(tasks, [])

    def test_gui_runner_task(self):
        app = MagicMock()
        runner = MagicMock()
        runner.running = True
        runner.label = "Backup"
        runner.operation_detail = None
        runner.steps = [("step1", [], False, False), ("step2", [], False, False)]
        runner._finally_step = None
        runner.current_step = 0
        runner._in_lock_wait = False
        runner._session_log_file = "/var/log/zfsutilities/sessions/backup.log"
        app.backup_runner = runner
        app.offsite_runner = None
        app.restore_runner = None
        app.retention_runner = None
        app.dataset_runner = None
        app.scrub_queue = None
        tasks = dp._collect_running_tasks(app)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["name"], "Backup")
        self.assertEqual(tasks[0]["type"], "GUI")
        self.assertEqual(tasks[0]["task_key"], "runner:backup_runner")
        self.assertEqual(
            tasks[0]["log_file"],
            "/var/log/zfsutilities/sessions/backup.log",
        )

    def test_scrub_task(self):
        app = MagicMock()
        app.backup_runner = None
        app.offsite_runner = None
        app.restore_runner = None
        app.retention_runner = None
        app.dataset_runner = None
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
        app.dataset_runner = None
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
        app.dataset_runner = None
        app.scrub_queue = None
        with patch.object(
            dp,
            "list_running_profiles",
            return_value=[
                {
                    "name": "Daily",
                    "pid": 1234,
                    "started": "2026-06-29T10:00:00",
                    "log_file": "/var/log/zfsutilities/sessions/profile-daily.log",
                }
            ],
        ):
            tasks = dp._collect_running_tasks(app)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["name"], "Daily")
        self.assertEqual(tasks[0]["type"], "Profile")
        self.assertEqual(tasks[0]["status"], "PID 1234")
        self.assertEqual(tasks[0]["task_key"], "profile:Daily")
        self.assertEqual(
            tasks[0]["log_file"],
            "/var/log/zfsutilities/sessions/profile-daily.log",
        )

    def test_waiting_profile_task(self):
        app = MagicMock()
        app.backup_runner = None
        app.offsite_runner = None
        app.restore_runner = None
        app.retention_runner = None
        app.dataset_runner = None
        app.scrub_queue = None
        with patch.object(
            dp,
            "list_running_profiles",
            return_value=[
                {
                    "name": "Daily",
                    "pid": 1235,
                    "started": "2026-06-29T10:00:00",
                    "log_file": "/var/log/zfsutilities/sessions/profile-daily-wait.log",
                    "waiting": True,
                }
            ],
        ):
            tasks = dp._collect_running_tasks(app)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["name"], "Daily")
        self.assertEqual(tasks[0]["type"], "Profile")
        self.assertEqual(tasks[0]["status"], "Waiting for profile lock")
        self.assertEqual(tasks[0]["task_key"], "profile-wait:Daily")
        self.assertTrue(tasks[0]["waiting_for_lock"])
        self.assertEqual(
            tasks[0]["log_file"],
            "/var/log/zfsutilities/sessions/profile-daily-wait.log",
        )

    def test_gui_runner_waiting_for_lock(self):
        app = MagicMock()
        runner = MagicMock()
        runner.running = True
        runner.label = "Backup"
        runner.operation_detail = None
        runner.steps = [("step1", [], False, False)]
        runner._finally_step = None
        runner.current_step = 0
        runner._in_lock_wait = True
        runner._session_log_file = "/var/log/zfsutilities/sessions/backup.log"
        app.backup_runner = runner
        app.offsite_runner = None
        app.restore_runner = None
        app.retention_runner = None
        app.dataset_runner = None
        app.scrub_queue = None
        tasks = dp._collect_running_tasks(app)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["status"], "Waiting for dataset lock")
        self.assertTrue(tasks[0]["waiting_for_lock"])

    @patch("scrub_manager.get_all_pool_scrub_states")
    def test_finished_scrub_removed_from_running_tasks(self, mock_states):
        """A stale queue.active entry whose live state is FINISHED is not shown."""
        import tempfile

        from scrub_manager import ScrubQueue, ScrubState

        app = MagicMock()
        app.backup_runner = None
        app.offsite_runner = None
        app.restore_runner = None
        app.retention_runner = None
        app.dataset_runner = None

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fh:
            fh.write("{}")
            state_path = fh.name
        try:
            with patch.object(feature_config, "SCRUB_STATE_PATH", state_path):
                queue = ScrubQueue(target=1)
                queue.active.add("fivebays")
                queue._save()

                mock_states.return_value = {
                    "fivebays": MagicMock(
                        state=ScrubState.FINISHED,
                        progress_percent=None,
                        eta=None,
                    ),
                }

                app.scrub_queue = queue
                tasks = dp._collect_running_tasks(app)
        finally:
            try:
                os.unlink(state_path)
            except OSError:
                pass

        self.assertEqual(tasks, [])
        self.assertNotIn("fivebays", queue.active)
        self.assertIn("fivebays", queue.finished)

    @patch("scrub_manager.get_all_pool_scrub_states")
    def test_running_tasks_matches_live_state_after_stale_queue(self, mock_states):
        """Mixed live state reconciles stale queue.active: only scanning shown."""
        import tempfile

        from scrub_manager import ScrubQueue, ScrubState

        app = MagicMock()
        app.backup_runner = None
        app.offsite_runner = None
        app.restore_runner = None
        app.retention_runner = None
        app.dataset_runner = None

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fh:
            fh.write("{}")
            state_path = fh.name
        try:
            with patch.object(feature_config, "SCRUB_STATE_PATH", state_path):
                queue = ScrubQueue(target=1)
                # Stale in-memory state: both were active when the backup started.
                queue.active.update({"fivebays", "threeamigos"})
                queue._save()

                fixed_eta = datetime(2026, 7, 13, 10, 0, 0)
                mock_states.return_value = {
                    "fivebays": MagicMock(
                        state=ScrubState.FINISHED,
                        progress_percent=None,
                        eta=None,
                    ),
                    "threeamigos": MagicMock(
                        state=ScrubState.SCANNING,
                        progress_percent=62.5,
                        eta=fixed_eta,
                    ),
                }

                app.scrub_queue = queue
                tasks = dp._collect_running_tasks(app)
        finally:
            try:
                os.unlink(state_path)
            except OSError:
                pass

        scrub_tasks = [t for t in tasks if t["type"] == "Scrub"]
        self.assertEqual(len(scrub_tasks), 1)
        self.assertEqual(scrub_tasks[0]["name"], "Scrub: threeamigos")
        self.assertEqual(
            scrub_tasks[0]["status"],
            "62.5% complete (ETA 2026-07-13 10:00)",
        )
        self.assertNotIn("fivebays", queue.active)
        self.assertIn("fivebays", queue.finished)
        self.assertIn("threeamigos", queue.active)


class TestCollectRunningTasksDatasetRunner(CollectRunningTasksIdleHostMixin):
    """dataset_runner tasks in _collect_running_tasks (plan section 2)."""

    def _dataset_app(self, operation_detail=None):
        app = MagicMock()
        app.backup_runner = None
        app.offsite_runner = None
        app.restore_runner = None
        app.retention_runner = None
        app.scrub_queue = None
        runner = MagicMock()
        runner.running = True
        runner.label = "Dataset action"
        runner.operation_detail = operation_detail
        runner.steps = [
            ("s1", [], False, False),
            ("s2", [], False, False),
            ("s3", [], False, False),
        ]
        runner._finally_step = None
        runner.current_step = 1
        runner._in_lock_wait = False
        runner._session_log_file = "/var/log/zfsutilities/sessions/dataset.log"
        app.dataset_runner = runner
        return app, runner

    def test_dataset_runner_task_uses_operation_detail(self):
        app, _runner = self._dataset_app(operation_detail="Migrate Pool: tank")
        tasks = dp._collect_running_tasks(app)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["name"], "Migrate Pool: tank")
        self.assertEqual(tasks[0]["type"], "GUI")
        self.assertEqual(tasks[0]["status"], "Step 2/3")
        self.assertEqual(tasks[0]["task_key"], "runner:dataset_runner")
        self.assertEqual(
            tasks[0]["log_file"],
            "/var/log/zfsutilities/sessions/dataset.log",
        )
        self.assertFalse(tasks[0]["waiting_for_lock"])

    def test_dataset_runner_task_falls_back_to_label(self):
        app, _runner = self._dataset_app(operation_detail=None)
        tasks = dp._collect_running_tasks(app)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["name"], "Dataset action")

    def test_dataset_runner_not_running_no_task(self):
        app = MagicMock()
        app.backup_runner = None
        app.offsite_runner = None
        app.restore_runner = None
        app.retention_runner = None
        app.scrub_queue = None
        runner = MagicMock()
        runner.running = False
        app.dataset_runner = runner
        tasks = dp._collect_running_tasks(app)
        self.assertEqual(tasks, [])


class TestCollectRunningTasksZfsOperations(CollectRunningTasksIdleHostMixin):
    """ZFS-native operation tasks (resilver/expand/remove) in _collect_running_tasks."""

    RESILVER_RAW = """\
  pool: tank
 state: DEGRADED
  scan: resilver in progress since Thu Sep 10 22:00:00 2026
    45.20% done, 0 days 02:10:00 to go
"""

    EXPAND_RAW = """\
  pool: tank
 state: ONLINE
  expand: expansion of raidz1-0 in progress since Thu Sep 10 22:00:00 2026
    12.30% done
"""

    REMOVE_RAW = """\
  pool: tank
 state: ONLINE
  remove: Removal of vdev 3 copied 12.5G in 0h5m, 42.50% done, 0B memory used
"""

    MIXED_RAW = """\
  pool: tank
 state: DEGRADED
  scan: resilver in progress since Thu Sep 10 22:00:00 2026
    45.20% done, 0 days 02:10:00 to go
  pool: cleanpool
 state: ONLINE
  scan: scrub repaired 0B in 00:00:04 with 0 errors on Wed Aug 19 22:07:47 2026
"""

    NO_PERCENT_RAW = """\
  pool: tank
 state: ONLINE
  expand: expansion of raidz1-0 in progress since Thu Sep 10 22:00:00 2026
"""

    def _idle_app(self):
        app = MagicMock()
        app.backup_runner = None
        app.offsite_runner = None
        app.restore_runner = None
        app.retention_runner = None
        app.dataset_runner = None
        app.scrub_queue = None
        return app

    def _collect_with_status(self, raw):
        app = self._idle_app()
        repo = MagicMock()
        repo.all_pool_status_text.return_value = raw
        app.ctx.zfs_repository = repo
        with patch.object(dp, "get_default_repository", return_value=repo):
            return dp._collect_running_tasks(app)

    def test_resilver_yields_zfs_task(self):
        tasks = self._collect_with_status(self.RESILVER_RAW)
        zfs_tasks = [t for t in tasks if t["type"] == "ZFS"]
        self.assertEqual(len(zfs_tasks), 1)
        self.assertEqual(zfs_tasks[0]["name"], "Resilver: tank")
        self.assertEqual(zfs_tasks[0]["status"], "45.2% done")
        self.assertEqual(zfs_tasks[0]["task_key"], "zfsop:tank")
        self.assertNotIn("log_file", zfs_tasks[0])

    def test_expand_yields_zfs_task_with_vdev(self):
        tasks = self._collect_with_status(self.EXPAND_RAW)
        zfs_tasks = [t for t in tasks if t["type"] == "ZFS"]
        self.assertEqual(len(zfs_tasks), 1)
        self.assertEqual(zfs_tasks[0]["name"], "Expand raidz1-0: tank")
        self.assertEqual(zfs_tasks[0]["status"], "12.3% done")

    def test_remove_yields_zfs_task_with_vdev_number(self):
        tasks = self._collect_with_status(self.REMOVE_RAW)
        zfs_tasks = [t for t in tasks if t["type"] == "ZFS"]
        self.assertEqual(len(zfs_tasks), 1)
        self.assertEqual(zfs_tasks[0]["name"], "Remove vdev 3: tank")
        self.assertEqual(zfs_tasks[0]["status"], "42.5% done")

    def test_mixed_pools_only_busy_pool_yields_task(self):
        tasks = self._collect_with_status(self.MIXED_RAW)
        zfs_tasks = [t for t in tasks if t["type"] == "ZFS"]
        self.assertEqual(len(zfs_tasks), 1)
        self.assertEqual(zfs_tasks[0]["task_key"], "zfsop:tank")

    def test_no_pool_operations_no_zfs_task(self):
        clean_raw = """\
  pool: tank
 state: ONLINE
  scan: scrub repaired 0B in 00:00:04 with 0 errors on Wed Aug 19 22:07:47 2026
"""
        tasks = self._collect_with_status(clean_raw)
        self.assertEqual(tasks, [])

    def test_missing_percent_yields_in_progress_status(self):
        tasks = self._collect_with_status(self.NO_PERCENT_RAW)
        zfs_tasks = [t for t in tasks if t["type"] == "ZFS"]
        self.assertEqual(len(zfs_tasks), 1)
        self.assertEqual(zfs_tasks[0]["status"], "In progress")

    def test_empty_status_text_no_zfs_task(self):
        tasks = self._collect_with_status("")
        self.assertEqual(tasks, [])


class TestProfileNameFromRunnerArgs(unittest.TestCase):
    """_profile_name_from_runner_args must keep resolving names with flags.

    profile_runner.py accepts `run <name> --ignore-schedule` (GUI Run Now);
    the flag must sit after the profile name so this parser still finds it.
    """

    def test_direct_invocation(self):
        args = "python3 /usr/local/lib/zfsutilities/current/python/profile_runner.py run daily"
        self.assertEqual(dp._profile_name_from_runner_args(args), "daily")

    def test_direct_invocation_with_ignore_schedule_flag(self):
        args = (
            "python3 /usr/local/lib/zfsutilities/current/python/profile_runner.py "
            "run daily --ignore-schedule"
        )
        self.assertEqual(dp._profile_name_from_runner_args(args), "daily")

    def test_cron_wrapper_with_ignore_schedule_flag(self):
        args = (
            "/bin/sh -c root mkdir -p /var/log/zfsutilities "
            "/run/lock/zfsutilities/profiles && "
            "python3 /usr/local/lib/zfsutilities/current/python/profile_runner.py "
            "run root-scrub-monthly --ignore-schedule >> /var/log/zfsutilities/cron.log 2>&1"
        )
        self.assertEqual(dp._profile_name_from_runner_args(args), "root-scrub-monthly")

    def test_flag_before_name_is_rejected(self):
        args = "python3 profile_runner.py run --ignore-schedule daily"
        self.assertIsNone(dp._profile_name_from_runner_args(args))

    def test_no_run_token_returns_none(self):
        self.assertIsNone(dp._profile_name_from_runner_args("python3 profile_runner.py daily"))
        self.assertIsNone(dp._profile_name_from_runner_args(""))


class TestCollectRunningTaskTimes(CollectRunningTasksIdleHostMixin):
    """started / wait_started keys across the collector's sources."""

    RESILVER_RAW = """\
  pool: tank
 state: DEGRADED
  scan: resilver in progress since Thu Sep 10 22:00:00 2026
    45.20% done, 0 days 02:10:00 to go
"""

    def _idle_app(self):
        app = MagicMock()
        app.backup_runner = None
        app.offsite_runner = None
        app.restore_runner = None
        app.retention_runner = None
        app.dataset_runner = None
        app.scrub_queue = None
        return app

    def test_gui_runner_started_from_session_start_time(self):
        app = self._idle_app()
        runner = MagicMock()
        runner.running = True
        runner.label = "Backup"
        runner.operation_detail = None
        runner.steps = [("step1", [], False, False)]
        runner._finally_step = None
        runner.current_step = 0
        runner._in_lock_wait = False
        runner._session_start_time = 1_780_000_000.0
        app.backup_runner = runner
        tasks = dp._collect_running_tasks(app)
        self.assertEqual(len(tasks), 1)
        self.assertAlmostEqual(dp._iso_to_epoch(tasks[0]["started"]), 1_780_000_000.0, delta=1.0)
        self.assertIsNone(tasks[0]["wait_started"])

    def test_waiting_gui_runner_wait_started(self):
        app = self._idle_app()
        runner = MagicMock()
        runner.running = True
        runner.label = "Backup"
        runner.operation_detail = None
        runner.steps = [("step1", [], False, False)]
        runner._finally_step = None
        runner.current_step = 0
        runner._in_lock_wait = True
        runner._session_start_time = 1_780_000_000.0
        runner._lock_wait_started = 1_780_003_600.0
        app.backup_runner = runner
        tasks = dp._collect_running_tasks(app)
        self.assertEqual(len(tasks), 1)
        self.assertTrue(tasks[0]["waiting_for_lock"])
        self.assertAlmostEqual(
            dp._iso_to_epoch(tasks[0]["wait_started"]), 1_780_003_600.0, delta=1.0
        )

    def test_scrub_started_from_as_of(self):
        from scrub_manager import ScrubState

        app = self._idle_app()
        queue = MagicMock()
        queue.active = {"fivebays"}
        app.scrub_queue = queue
        with patch(
            "scrub_manager.get_all_pool_scrub_states",
            return_value={
                "fivebays": MagicMock(
                    state=ScrubState.SCANNING,
                    progress_percent=10.0,
                    eta=None,
                    as_of="Sun May 10 00:24:03 2026",
                )
            },
        ):
            tasks = dp._collect_running_tasks(app)
        self.assertEqual(len(tasks), 1)
        self.assertIsNotNone(dp._iso_to_epoch(tasks[0]["started"]))

    def test_zfs_op_started_from_since_line(self):
        app = self._idle_app()
        repo = MagicMock()
        repo.all_pool_status_text.return_value = self.RESILVER_RAW
        app.ctx.zfs_repository = repo
        with patch.object(dp, "get_default_repository", return_value=repo):
            tasks = dp._collect_running_tasks(app)
        self.assertEqual(len(tasks), 1)
        started = dp._iso_to_epoch(tasks[0]["started"])
        self.assertIsNotNone(started)
        expected = dp._zfs_time_to_iso("Thu Sep 10 22:00:00 2026")
        self.assertAlmostEqual(started, dp._iso_to_epoch(expected), delta=1.0)

    def test_profile_started_keys(self):
        app = self._idle_app()
        with patch.object(
            dp,
            "list_running_profiles",
            return_value=[
                {"name": "Daily", "pid": 1234, "started": "2026-06-29T10:00:00"},
                {
                    "name": "Weekly",
                    "pid": 1235,
                    "started": "2026-06-29T10:05:00",
                    "waiting": True,
                },
            ],
        ):
            tasks = dp._collect_running_tasks(app)
        by_name = {t["name"]: t for t in tasks}
        self.assertEqual(by_name["Daily"]["started"], "2026-06-29T10:00:00")
        self.assertIsNone(by_name["Daily"]["wait_started"])
        # A waiting invocation's start is also when its wait began.
        self.assertEqual(by_name["Weekly"]["started"], "2026-06-29T10:05:00")
        self.assertEqual(by_name["Weekly"]["wait_started"], "2026-06-29T10:05:00")

    def test_scheduled_started_from_lstart(self):
        app = self._idle_app()

        def _run(cmd, *a, **kw):
            result = MagicMock()
            if cmd[0] == "pgrep":
                result.returncode = 0
                result.stdout = "2040788\n"
            elif cmd[-1] == "lstart=":
                result.returncode = 0
                result.stdout = "Thu Oct 23 22:10:31 2026\n"
            else:
                result.returncode = 0
                result.stdout = (
                    "python3 /usr/local/lib/zfsutilities/current/python/profile_runner.py "
                    "run root-backup-dailybackup"
                )
            return result

        with patch("subprocess.run", side_effect=_run):
            tasks = dp._collect_running_tasks(app)
        self.assertEqual(len(tasks), 1)
        self.assertIsNotNone(dp._iso_to_epoch(tasks[0]["started"]))

    def test_scheduled_lstart_failure_leaves_started_none(self):
        app = self._idle_app()

        def _run(cmd, *a, **kw):
            result = MagicMock()
            if cmd[0] == "pgrep":
                result.returncode = 0
                result.stdout = "2040788\n"
            elif cmd[-1] == "lstart=":
                result.returncode = 1
                result.stdout = ""
            else:
                result.returncode = 0
                result.stdout = (
                    "python3 /usr/local/lib/zfsutilities/current/python/profile_runner.py "
                    "run root-backup-dailybackup"
                )
            return result

        with patch("subprocess.run", side_effect=_run):
            tasks = dp._collect_running_tasks(app)
        self.assertEqual(len(tasks), 1)
        self.assertIsNone(tasks[0]["started"])

    def test_surface_test_started_from_state(self):
        entry = {"status": "running", "started_at": "2026-06-29T09:30:00", "progress_percent": 5}
        with patch(
            "disk_surface_test.load_surface_test_state",
            return_value={"tests": {"/dev/sda": entry}},
        ):
            with patch("disk_surface_test.surface_cell_text", return_value="5%"):
                app = self._idle_app()
                tasks = dp._collect_running_tasks(app)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["started"], "2026-06-29T09:30:00")


class TestTaskTimeHelpers(unittest.TestCase):
    """Timestamp conversions behind the merged Tasks rows."""

    def test_zfs_time_to_iso_parses(self):
        iso = dp._zfs_time_to_iso("Sun May 10 00:24:03 2026")
        self.assertIsNotNone(dp._iso_to_epoch(iso))

    def test_zfs_time_to_iso_handles_padded_day(self):
        iso = dp._zfs_time_to_iso("Mon Oct  5 09:05:02 2026")
        self.assertIsNotNone(dp._iso_to_epoch(iso))

    def test_zfs_time_to_iso_rejects_bad_input(self):
        self.assertIsNone(dp._zfs_time_to_iso(""))
        self.assertIsNone(dp._zfs_time_to_iso(None))
        self.assertIsNone(dp._zfs_time_to_iso(MagicMock()))
        self.assertIsNone(dp._zfs_time_to_iso("not a date"))

    def test_epoch_to_local_iso_roundtrip(self):
        iso = dp._epoch_to_local_iso(1_780_000_000.0)
        self.assertAlmostEqual(dp._iso_to_epoch(iso), 1_780_000_000.0, delta=1.0)

    def test_epoch_to_local_iso_rejects_bad_input(self):
        self.assertIsNone(dp._epoch_to_local_iso(None))
        self.assertIsNone(dp._epoch_to_local_iso(0))
        self.assertIsNone(dp._epoch_to_local_iso(MagicMock()))

    def test_iso_to_epoch_rejects_bad_input(self):
        self.assertIsNone(dp._iso_to_epoch(""))
        self.assertIsNone(dp._iso_to_epoch("?"))
        self.assertIsNone(dp._iso_to_epoch("not-a-date"))
        self.assertIsNone(dp._iso_to_epoch(MagicMock()))


class TestRunningProgressText(unittest.TestCase):
    """The parenthetical progress kept on running rows."""

    def test_step_text_is_progress(self):
        self.assertEqual(dp._running_progress_text({"status": "Step 2/3"}), "Step 2/3")

    def test_scrub_percent_is_progress(self):
        status = "42.1% complete (ETA 2026-07-13 10:00)"
        self.assertEqual(dp._running_progress_text({"status": status}), status)

    def test_generic_statuses_are_empty(self):
        for status in ("", "Running", "In progress"):
            self.assertEqual(dp._running_progress_text({"status": status}), "")

    def test_pid_statuses_are_empty(self):
        self.assertEqual(dp._running_progress_text({"status": "PID 1234"}), "")

    def test_waiting_statuses_are_empty(self):
        self.assertEqual(dp._running_progress_text({"status": "Waiting for profile lock"}), "")

    def test_surface_percent_is_progress(self):
        self.assertEqual(dp._running_progress_text({"status": "5% (1h 20m)"}), "5% (1h 20m)")


class TestCollectScheduledTasks(unittest.TestCase):
    """Section 5 of _collect_running_tasks: legacy pgrep/ps profile detection."""

    def _idle_app(self):
        app = MagicMock()
        app.backup_runner = None
        app.offsite_runner = None
        app.restore_runner = None
        app.retention_runner = None
        app.dataset_runner = None
        app.scrub_queue = None
        return app

    def _pgrep_side_effect(self, pid, args):
        """Mock subprocess.run answering pgrep and ps for one PID."""

        def _run(cmd, *a, **kw):
            result = MagicMock()
            if cmd[0] == "pgrep":
                result.returncode = 0
                result.stdout = f"{pid}\n"
            elif cmd[0] == "ps":
                result.returncode = 0
                result.stdout = args
            return result

        return _run

    def test_cron_wrapper_is_folded_into_profile_row(self):
        """A cron sh -c wrapper resolves its profile name and is deduped."""
        app = self._idle_app()
        wrapper_args = (
            "/bin/sh -c root mkdir -p /var/log/zfsutilities "
            "/run/lock/zfsutilities/profiles && "
            "python3 /usr/local/lib/zfsutilities/current/python/profile_runner.py "
            "run root-backup-dailybackup >> /var/log/zfsutilities/cron.log 2>&1"
        )
        with patch.object(
            dp,
            "list_running_profiles",
            return_value=[
                {
                    "name": "root-backup-dailybackup",
                    "pid": 2040790,
                    "started": "2026-09-02T06:00:00",
                    "log_file": None,
                }
            ],
        ):
            with patch(
                "subprocess.run", side_effect=self._pgrep_side_effect(2040788, wrapper_args)
            ):
                tasks = dp._collect_running_tasks(app)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["type"], "Profile")
        self.assertEqual(tasks[0]["name"], "root-backup-dailybackup")

    def test_legacy_runner_shows_real_profile_name(self):
        """A runner without a lock file is listed with its resolved name."""
        app = self._idle_app()
        runner_args = (
            "python3 /usr/local/lib/zfsutilities/current/python/profile_runner.py "
            "run root-backup-dailybackup"
        )
        with patch.object(dp, "list_running_profiles", return_value=[]):
            with patch("subprocess.run", side_effect=self._pgrep_side_effect(2040788, runner_args)):
                tasks = dp._collect_running_tasks(app)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["type"], "Scheduled")
        self.assertEqual(tasks[0]["name"], "Scheduled: root-backup-dailybackup")
        self.assertEqual(tasks[0]["status"], "PID 2040788")

    def test_unparseable_args_get_informative_fallback(self):
        """When the profile name cannot be resolved, the row still says what ran."""
        app = self._idle_app()
        weird_args = "python3 /usr/local/lib/zfsutilities/current/python/profile_runner.py"
        with patch.object(dp, "list_running_profiles", return_value=[]):
            with patch("subprocess.run", side_effect=self._pgrep_side_effect(2040788, weird_args)):
                tasks = dp._collect_running_tasks(app)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["type"], "Scheduled")
        self.assertEqual(tasks[0]["name"], "Scheduled: profile_runner.py (PID 2040788)")


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

            json.dump(
                {
                    "profile": "Daily",
                    "pid": os.getpid(),
                    "started": "2026-06-29T10:00:00",
                    "log_file": "/var/log/zfsutilities/sessions/daily.log",
                },
                f,
            )
        profiles = dp.list_running_profiles()
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["name"], "Daily")
        self.assertEqual(profiles[0]["pid"], os.getpid())
        self.assertEqual(
            profiles[0]["log_file"],
            "/var/log/zfsutilities/sessions/daily.log",
        )

    def test_skips_stale_lock(self):
        lock_path = os.path.join(self.tmpdir, "Old.lock")
        with open(lock_path, "w") as f:
            import json

            json.dump({"profile": "Old", "pid": 999999, "started": "2026-06-29T10:00:00"}, f)
        self.assertEqual(dp.list_running_profiles(), [])

    def test_returns_waiting_profile(self):
        waiting_path = os.path.join(self.tmpdir, "Daily.waiting")
        with open(waiting_path, "w") as f:
            import json

            json.dump(
                {
                    "profile": "Daily",
                    "pid": os.getpid(),
                    "started": "2026-06-29T10:00:00",
                    "log_file": "/var/log/zfsutilities/sessions/daily.log",
                },
                f,
            )
        profiles = dp.list_running_profiles()
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["name"], "Daily")
        self.assertEqual(profiles[0]["pid"], os.getpid())
        self.assertTrue(profiles[0].get("waiting"))
        self.assertEqual(
            profiles[0]["log_file"],
            "/var/log/zfsutilities/sessions/daily.log",
        )


class TestWaitingTaskWarnings(unittest.TestCase):
    def test_no_warning_for_running_profiles(self):
        pools = []
        warnings = dp._get_warnings(pools, [], 80, [])
        self.assertEqual(warnings, [])

    def test_warning_for_waiting_task(self):
        pools = []
        waiting = [{"name": "Backup", "waiting_for_lock": True}]
        warnings = dp._get_warnings(pools, [], 80, waiting)
        self.assertEqual(len(warnings), 1)
        self.assertIn("Backup", warnings[0])
        self.assertIn("waiting for a lock", warnings[0])

    def test_warning_for_waiting_profile(self):
        pools = []
        waiting = [{"name": "Daily", "waiting_for_lock": True}]
        warnings = dp._get_warnings(pools, [], 80, waiting)
        self.assertEqual(len(warnings), 1)
        self.assertIn("Daily", warnings[0])
        self.assertIn("waiting for a lock", warnings[0])

    def test_no_warning_when_no_tasks_waiting(self):
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

    def test_cancel_dataset_runner(self):
        app = MagicMock()
        runner = MagicMock()
        runner.running = True
        runner.label = "Dataset action"
        app.dataset_runner = runner
        dp._cancel_task(app, "runner:dataset_runner")
        runner.cancel.assert_called_once()

    def test_cancel_zfsop_key_not_cancellable(self):
        app = MagicMock()
        with patch("dashboard_page.log_msg") as mock_log:
            dp._cancel_task(app, "zfsop:tank")
        mock_log.assert_called_once()
        self.assertIn("cannot be cancelled", mock_log.call_args[0][0])
        app.backup_runner.cancel.assert_not_called()
        app.offsite_runner.cancel.assert_not_called()
        app.restore_runner.cancel.assert_not_called()
        app.retention_runner.cancel.assert_not_called()
        app.dataset_runner.cancel.assert_not_called()

    def test_cancel_waiting_profile_sends_sigterm(self):
        """Cancelling a waiting profile signals the live waiting process."""
        app = MagicMock()
        with patch.object(
            dp,
            "list_running_profiles",
            return_value=[
                {
                    "name": "Daily",
                    "pid": 4321,
                    "started": "2026-06-29T10:00:00",
                    "waiting": True,
                }
            ],
        ):
            with patch("dashboard_page.os.kill") as mock_kill:
                dp._cancel_task(app, "profile-wait:Daily")
        mock_kill.assert_called_once_with(4321, dp.signal.SIGTERM)

    def test_cancel_waiting_profile_no_longer_running(self):
        """A waiting entry that vanished since the click warns instead."""
        app = MagicMock()
        with patch.object(dp, "list_running_profiles", return_value=[]):
            with patch("dashboard_page.os.kill") as mock_kill, capture_logs() as logs:
                dp._cancel_task(app, "profile-wait:Daily")
        mock_kill.assert_not_called()
        self.assertTrue(any("no longer running" in msg for msg in logs))

    def test_cancel_running_profile_sends_sigterm(self):
        """Cancelling a running profile signals the runner process."""
        app = MagicMock()
        with patch.object(
            dp,
            "list_running_profiles",
            return_value=[
                {
                    "name": "Daily",
                    "pid": 4321,
                    "started": "2026-06-29T10:00:00",
                }
            ],
        ):
            with patch("dashboard_page.os.kill") as mock_kill:
                dp._cancel_task(app, "profile:Daily")
        mock_kill.assert_called_once_with(4321, dp.signal.SIGTERM)

    def test_cancel_running_profile_ignores_waiting_entries(self):
        """A waiting duplicate must not be signalled as the running profile."""
        app = MagicMock()
        with patch.object(
            dp,
            "list_running_profiles",
            return_value=[
                {
                    "name": "Daily",
                    "pid": 4321,
                    "started": "2026-06-29T10:00:00",
                    "waiting": True,
                }
            ],
        ):
            with patch("dashboard_page.os.kill") as mock_kill, capture_logs() as logs:
                dp._cancel_task(app, "profile:Daily")
        mock_kill.assert_not_called()
        self.assertTrue(any("no longer running" in msg for msg in logs))

    def test_cancel_running_profile_no_longer_running(self):
        """A running entry that vanished since the click warns instead."""
        app = MagicMock()
        with patch.object(dp, "list_running_profiles", return_value=[]):
            with patch("dashboard_page.os.kill") as mock_kill, capture_logs() as logs:
                dp._cancel_task(app, "profile:Daily")
        mock_kill.assert_not_called()
        self.assertTrue(any("no longer running" in msg for msg in logs))


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
        with mock_gtk() as gtk_mock, patch.object(dp, "Gtk", gtk_mock):
            app = MagicMock()
            grid = MagicMock()
            app.dashboard_pool_grid = grid
            pools = [
                {
                    "name": "tank",
                    "health": "ONLINE",
                    "cap": "50%",
                    "cap_int": 50,
                    "scrub_date": "Sun May 10 00:24:03 2026",
                }
            ]
            dp._refresh_pool_section(app, pools, scrub_states={}, stale=True)

        attach_calls = grid.attach.call_args_list
        self.assertTrue(len(attach_calls) > 0)
        # Stale label is attached at row 0, column 0, spanning 4 columns.
        first_call = attach_calls[0]
        self.assertEqual(first_call[0][1], 0)  # column
        self.assertEqual(first_call[0][2], 0)  # row
        self.assertEqual(first_call[0][3], 4)  # columnspan

    def test_no_stale_indicator_when_fresh(self):
        with mock_gtk() as gtk_mock, patch.object(dp, "Gtk", gtk_mock):
            app = MagicMock()
            grid = MagicMock()
            app.dashboard_pool_grid = grid
            pools = [
                {
                    "name": "tank",
                    "health": "ONLINE",
                    "cap": "50%",
                    "cap_int": 50,
                    "scrub_date": "Sun May 10 00:24:03 2026",
                }
            ]
            dp._refresh_pool_section(app, pools, scrub_states={}, stale=False)

        attach_calls = grid.attach.call_args_list
        # Stale label would span 4 columns at row 0; ensure no such call exists.
        stale_calls = [c for c in attach_calls if c[0][2] == 0 and c[0][3] == 4]
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
                pools = [
                    {
                        "name": "tank",
                        "health": "ONLINE",
                        "cap": "50%",
                        "cap_int": 50,
                        "scrub_date": "Sun May 10 00:24:03 2026",
                    }
                ]
                dp._refresh_pool_section(app, pools, scrub_states={}, stale=False)

        # Column 2 contains both the "Last Scrub" header and the per-pool
        # value label; find the label that was styled as monospace.
        scrub_labels = [c[0][0] for c in grid.attach.call_args_list if c[0][1] == 2]
        styled = [
            lbl for lbl in scrub_labels if lbl.get_style_context.return_value.add_class.called
        ]
        self.assertEqual(len(styled), 1)
        scrub_label = styled[0]
        scrub_label.get_style_context.return_value.add_class.assert_called_once_with("monospace")


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
            patch.object(
                dp,
                "_gather_config_section_data",
                return_value={
                    "cfg": {"mode": "single-node", "this_host": "test"},
                    "mode": "single-node",
                    "hosts": [("Hostname", "test")],
                    "os_info_map": {"test": ("TestOS", "1")},
                    "versions": "dev",
                    "zfs_versions": "zfs-1",
                },
            ),
            patch.object(dp, "_refresh_pool_section"),
            patch.object(dp, "_refresh_tasks_section"),
            patch.object(dp, "_refresh_iscsi_section"),
            patch.object(dp, "_refresh_warnings_section"),
            patch.object(dp, "_update_fix_locks_button"),
            patch.object(dp, "_is_two_node", return_value=False),
        ]

    def test_uses_cached_pools_when_zpool_list_fails(self):
        app = MagicMock()
        app.config = {}
        cached = [
            {
                "name": "tank",
                "health": "ONLINE",
                "cap": "50%",
                "cap_int": 50,
                "scrub_date": "Sun May 10 00:24:03 2026",
            }
        ]
        app._dashboard_pools = cached

        patches = self._refresh_patches()
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            dp._get_pool_health.return_value = None
            dp.refresh_dashboard_page(app, sync=True)
            mock_pool = dp._refresh_pool_section

        mock_pool.assert_called_once()
        self.assertEqual(mock_pool.call_args[0][1], cached)
        self.assertTrue(mock_pool.call_args[1]["stale"])

    def test_clears_stale_flag_after_successful_fetch(self):
        app = MagicMock()
        app.config = {}
        app._dashboard_pools = [{"name": "old"}]
        app._dashboard_pools_stale = True
        fresh = [
            {
                "name": "tank",
                "health": "ONLINE",
                "cap": "50%",
                "cap_int": 50,
                "scrub_date": "Sun May 10 00:24:03 2026",
            }
        ]

        patches = self._refresh_patches()
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            dp._get_pool_health.return_value = fresh
            dp.refresh_dashboard_page(app, sync=True)
            mock_pool = dp._refresh_pool_section

        self.assertEqual(app._dashboard_pools, fresh)
        self.assertFalse(app._dashboard_pools_stale)
        mock_pool.assert_called_once()
        self.assertEqual(mock_pool.call_args[0][1], fresh)
        self.assertFalse(mock_pool.call_args[1]["stale"])


class TestRefreshDashboardAsync(unittest.TestCase):
    """Verify the default async refresh path does not block the main thread."""

    def test_async_refresh_shows_refreshing_indicator(self):
        app = MagicMock()
        app.config = {}
        app._dashboard_refresh_in_progress = False
        with patch.object(dp, "threading") as mock_threading:
            with patch.object(dp, "_show_dashboard_refreshing") as mock_show:
                dp.refresh_dashboard_page(app, sync=False)

        mock_show.assert_called_once_with(app)
        mock_threading.Thread.assert_called_once()
        _, kwargs = mock_threading.Thread.call_args
        self.assertTrue(kwargs.get("daemon"))
        self.assertEqual(kwargs["target"], dp._dashboard_refresh_worker)
        self.assertEqual(kwargs["args"], (app,))

    def test_async_refresh_coalesces_overlapping_requests(self):
        app = MagicMock()
        app.config = {}
        app._dashboard_refresh_in_progress = True
        with patch.object(dp, "threading") as mock_threading:
            dp.refresh_dashboard_page(app, sync=False)

        self.assertTrue(app._dashboard_refresh_pending)
        mock_threading.Thread.assert_not_called()


class TestDashboardRefreshingIndicator(unittest.TestCase):
    """Verify the 'Refreshing' label visibility helpers."""

    def test_show_refreshing_makes_label_visible(self):
        app = MagicMock()
        dp._show_dashboard_refreshing(app)
        app.dashboard_refreshing_label.show.assert_called_once_with()

    def test_hide_refreshing_hides_label(self):
        app = MagicMock()
        dp._hide_dashboard_refreshing(app)
        app.dashboard_refreshing_label.hide.assert_called_once_with()

    def test_show_refreshing_skips_missing_label(self):
        app = MagicMock()
        del app.dashboard_refreshing_label
        # Should not raise.
        dp._show_dashboard_refreshing(app)

    def test_hide_refreshing_skips_missing_label(self):
        app = MagicMock()
        del app.dashboard_refreshing_label
        # Should not raise.
        dp._hide_dashboard_refreshing(app)


class TestDashboardRefreshDone(unittest.TestCase):
    """Verify the async refresh completion callback behaves correctly."""

    def test_applies_data_via_update_dashboard_ui(self):
        app = MagicMock()
        app.config = {}
        app._dashboard_refresh_in_progress = True
        app._dashboard_refresh_pending = False
        data = {"pools": []}

        with patch.object(dp, "_update_dashboard_ui") as mock_update:
            dp._on_dashboard_refresh_done(app, data)

        mock_update.assert_called_once_with(app, data)
        self.assertFalse(app._dashboard_refresh_in_progress)

    def test_schedules_pending_refresh(self):
        app = MagicMock()
        app.config = {}
        app._dashboard_refresh_in_progress = True
        app._dashboard_refresh_pending = True
        data = {"pools": []}

        with (
            patch.object(dp, "_update_dashboard_ui"),
            patch.object(dp, "_hide_dashboard_refreshing") as mock_hide,
            patch.object(dp, "GLib") as mock_glib,
            patch.object(dp, "refresh_dashboard_page") as mock_refresh,
        ):
            dp._on_dashboard_refresh_done(app, data)
            mock_glib.timeout_add_seconds.assert_called_once()
            callback = mock_glib.timeout_add_seconds.call_args[0][1]
            callback()

        mock_refresh.assert_called_once_with(app)
        self.assertFalse(app._dashboard_refresh_pending)
        # Label stays visible while a pending refresh is queued.
        mock_hide.assert_not_called()

    def test_worker_exception_logs_and_hides_refreshing(self):
        app = MagicMock()
        app.config = {}
        app._dashboard_refresh_in_progress = True
        app._dashboard_refresh_pending = False

        with (
            patch.object(dp, "_gather_dashboard_data", side_effect=RuntimeError("boom")),
            patch("dashboard_page.log_msg") as mock_log,
            patch.object(dp, "GLib") as mock_glib,
            patch.object(dp, "_hide_dashboard_refreshing") as mock_hide,
        ):
            dp._dashboard_refresh_worker(app)
            idle_callback = mock_glib.idle_add.call_args[0][0]
            idle_args = mock_glib.idle_add.call_args[0][1:]
            self.assertEqual(idle_args, (app, None))
            # Simulate the idle callback running while patches are still active.
            idle_callback(*idle_args)

        mock_hide.assert_called_once_with(app)
        self.assertFalse(app._dashboard_refresh_in_progress)
        self.assertTrue(any("boom" in str(call) for call in mock_log.call_args_list))

    def test_hides_refreshing_when_done_without_pending(self):
        app = MagicMock()
        app.config = {}
        app._dashboard_refresh_in_progress = True
        app._dashboard_refresh_pending = False
        data = {"pools": []}

        with (
            patch.object(dp, "_update_dashboard_ui"),
            patch.object(dp, "_hide_dashboard_refreshing") as mock_hide,
        ):
            dp._on_dashboard_refresh_done(app, data)

        mock_hide.assert_called_once_with(app)


class TestRefreshIntervalChanged(unittest.TestCase):
    """Dashboard refresh interval spinner persists and restarts the timer."""

    def test_saves_new_interval_to_config(self):
        with temp_config_dir():
            app = MagicMock()
            app.config = {"dashboard": {"low_space_threshold": 80, "refresh_seconds": 30}}
            spin = MagicMock()
            spin.get_value.return_value = 45
            dp._on_refresh_interval_changed(spin, app)
            self.assertEqual(app.config["dashboard"]["refresh_seconds"], 45)

    def test_restarts_dashboard_timer(self):
        with temp_config_dir():
            app = MagicMock()
            app.config = {"dashboard": {"low_space_threshold": 80, "refresh_seconds": 30}}
            spin = MagicMock()
            spin.get_value.return_value = 45
            dp._on_refresh_interval_changed(spin, app)
            app._start_stop_dashboard_timer.assert_called_once_with("dashboard")

    def test_no_restart_when_value_unchanged(self):
        app = MagicMock()
        app.config = {"dashboard": {"low_space_threshold": 80, "refresh_seconds": 30}}
        spin = MagicMock()
        spin.get_value.return_value = 30
        dp._on_refresh_interval_changed(spin, app)
        app._start_stop_dashboard_timer.assert_not_called()


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
    """Dashboard View Log button tracks the merged Tasks selection."""

    def _make_app(self, rows=None):
        app, selection = _make_tasks_selection_app(rows or [])
        app._cancel_selected_button = MagicMock()
        app._remove_button = MagicMock()
        app._view_log_button = MagicMock()
        return app, selection

    def test_starts_disabled_when_nothing_selected(self):
        app, _selection = self._make_app()
        dp.setup_dashboard_actions(app)
        app._view_log_button.set_sensitive.assert_called_with(False)

    def test_enables_when_completed_row_with_log_selected(self):
        app, _selection = self._make_app(
            [{"state": "completed", "log_file": "/var/log/zfsutilities/sessions/ops.log"}]
        )
        dp.setup_dashboard_actions(app)
        app._view_log_button.set_sensitive.assert_called_with(True)
        self.assertEqual(app._dashboard_view_log_path, "/var/log/zfsutilities/sessions/ops.log")

    def test_enables_when_running_task_with_log_selected(self):
        app, _selection = self._make_app(
            [
                {
                    "state": "running",
                    "task_key": "runner:backup_runner",
                    "log_file": "/var/log/zfsutilities/sessions/gui.log",
                }
            ]
        )
        dp.setup_dashboard_actions(app)
        app._view_log_button.set_sensitive.assert_called_with(True)
        self.assertEqual(app._dashboard_view_log_path, "/var/log/zfsutilities/sessions/gui.log")

    def test_disabled_when_row_without_log_selected(self):
        app, _selection = self._make_app(
            [{"state": "running", "task_key": "scrub:fivebays", "log_file": ""}]
        )
        dp.setup_dashboard_actions(app)
        app._view_log_button.set_sensitive.assert_called_with(False)
        self.assertIsNone(app._dashboard_view_log_path)

    def test_toggles_with_selection_changes(self):
        row = {"state": "completed", "log_file": ""}
        app, selection = self._make_app([row])
        dp.setup_dashboard_actions(app)
        app._view_log_button.reset_mock()

        row["log_file"] = "/var/log/zfsutilities/sessions/ops.log"
        callback = selection.connect.call_args[0][1]
        callback(selection, app)
        app._view_log_button.set_sensitive.assert_called_once_with(True)
        self.assertEqual(app._dashboard_view_log_path, "/var/log/zfsutilities/sessions/ops.log")

    def test_uses_cached_path_when_selection_lost(self):
        app, _selection = self._make_app()
        app._dashboard_view_log_path = "/var/log/zfsutilities/sessions/cached.log"
        with patch("dashboard_page.select_log_by_path", return_value=True) as mock_select:
            dp.on_dashboard_view_log(app)
        app.stack.set_visible_child_name.assert_called_once_with("logs")
        mock_select.assert_called_once_with(app, "/var/log/zfsutilities/sessions/cached.log")

    def test_no_button_attr_does_not_crash(self):
        app, _selection = self._make_app()
        del app._view_log_button
        dp.setup_dashboard_actions(app)
        # Should not raise


class TestOnDashboardViewLog(unittest.TestCase):
    def _make_app(self, rows):
        app, _selection = _make_tasks_selection_app(rows)
        # Ensure the handler falls back to reading the current selection.
        app._dashboard_view_log_path = None
        return app

    @patch("dashboard_page.select_log_by_path", return_value=True)
    def test_switches_to_logs_for_selected_row(self, mock_select):
        app = self._make_app(
            [
                {
                    "state": "running",
                    "task_key": "runner:backup_runner",
                    "log_file": "/var/log/zfsutilities/sessions/current.log",
                }
            ]
        )
        dp.on_dashboard_view_log(app)
        app.stack.set_visible_child_name.assert_called_once_with("logs")
        mock_select.assert_called_once_with(app, "/var/log/zfsutilities/sessions/current.log")

    @patch("dashboard_page.select_log_by_path")
    def test_warns_when_no_row_with_log_selected(self, mock_select):
        app = self._make_app([{"state": "completed", "log_file": ""}])
        with capture_logs() as logs:
            dp.on_dashboard_view_log(app)
        self.assertTrue(any("No task row with a log file selected" in msg for msg in logs))
        mock_select.assert_not_called()

    @patch("dashboard_page.select_log_by_path", return_value=False)
    def test_warns_when_log_not_found(self, mock_select):
        app = self._make_app([{"state": "completed", "log_file": "/missing.log"}])
        with capture_logs() as logs:
            dp.on_dashboard_view_log(app)
        self.assertTrue(any("Log entry not found" in msg for msg in logs))


class TestRefreshTasksSection(unittest.TestCase):
    """_refresh_tasks_section builds the merged waiting/running/completed list."""

    def _make_app(self, selected_rows=None):
        """Build an app with a mocked Tasks store and selection.

        ``selected_rows`` lists the hidden-column dicts of the rows the
        selection reports as selected before the refresh, mirroring what
        a live refresh would read from the store being rebuilt.
        """
        app = MagicMock()
        app.config = {}
        store = MagicMock()
        app.dashboard_tasks_store = store
        selection = MagicMock()
        model = MagicMock()

        selected_rows = selected_rows or []
        sel_iters = [MagicMock() for _ in selected_rows]
        sel_paths = [MagicMock() for _ in selected_rows]

        def sel_get_value(tree_iter, col):
            row = selected_rows[sel_iters.index(tree_iter)]
            if col == 5:
                return row.get("task_key", "")
            if col == 6:
                return row.get("log_file", "")
            return ""

        model.get_value.side_effect = sel_get_value

        def sel_get_iter(path):
            return sel_iters[sel_paths.index(path)]

        model.get_iter.side_effect = sel_get_iter
        selection.get_selected_rows.return_value = (model, sel_paths)
        app.dashboard_tasks_view.get_selection.return_value = selection
        return app, store, selection

    def _run_refresh(self, app, tasks=(), recent=()):
        with mock_gtk() as gtk_mock, patch.object(dp, "Gtk", gtk_mock):
            dp._refresh_tasks_section(app, tasks=list(tasks), recent=list(recent))

    def test_empty_placeholder_has_eight_columns(self):
        app, store, _selection = self._make_app()
        self._run_refresh(app)
        store.append.assert_called_once()
        appended = store.append.call_args[0][0]
        self.assertEqual(len(appended), 8)
        self.assertEqual(appended[0], "No tasks")

    def test_completed_row_columns(self):
        app, store, _selection = self._make_app()
        recent = [
            {
                "timestamp": "2026-05-28T14:32:00",
                "type": "backup",
                "name": "Daily",
                "result": "success",
                "log_file": "/var/log/zfsutilities/sessions/daily.log",
            }
        ]
        self._run_refresh(app, recent=recent)
        store.append.assert_called_once()
        appended = store.append.call_args[0][0]
        self.assertTrue(appended[0].startswith("2026-05-28T14:32"))
        self.assertEqual(appended[1], "backup")
        self.assertEqual(appended[2], "Daily")
        self.assertIn("success", appended[3])
        self.assertEqual(appended[4], "completed")
        self.assertEqual(appended[5], "")
        self.assertEqual(appended[6], "/var/log/zfsutilities/sessions/daily.log")
        self.assertEqual(appended[7], "/var/log/zfsutilities/sessions/daily.log")

    def test_completed_row_without_log_uses_timestamp_key(self):
        app, store, _selection = self._make_app()
        recent = [
            {
                "timestamp": "2026-05-28T14:32:00",
                "type": "backup",
                "name": "Daily",
                "result": "success",
            }
        ]
        self._run_refresh(app, recent=recent)
        appended = store.append.call_args[0][0]
        self.assertEqual(appended[7], "2026-05-28T14:32:00|Daily")

    def test_waiting_row_status_text(self):
        app, store, _selection = self._make_app()
        tasks = [
            {
                "name": "Daily",
                "type": "Profile",
                "status": "Waiting for profile lock",
                "task_key": "profile-wait:Daily",
                "waiting_for_lock": True,
                "started": "2026-06-29T10:00:00",
                "wait_started": "2026-06-29T10:05:00",
            }
        ]
        self._run_refresh(app, tasks=tasks)
        appended = store.append.call_args[0][0]
        self.assertEqual(appended[4], "waiting")
        self.assertTrue(appended[3].startswith("Waiting since 2026-06-29T10:05"))
        # The row's date/time is the task start, not the wait start.
        self.assertTrue(appended[0].startswith("2026-06-29T10:00"))

    def test_waiting_row_without_times(self):
        app, store, _selection = self._make_app()
        tasks = [
            {
                "name": "Backup",
                "type": "GUI",
                "status": "Waiting for dataset lock",
                "task_key": "runner:backup_runner",
                "waiting_for_lock": True,
                "started": None,
                "wait_started": None,
            }
        ]
        self._run_refresh(app, tasks=tasks)
        appended = store.append.call_args[0][0]
        self.assertEqual(appended[3], "Waiting")
        self.assertEqual(appended[0], "?")

    def test_running_row_status_with_progress(self):
        app, store, _selection = self._make_app()
        tasks = [
            {
                "name": "Backup",
                "type": "GUI",
                "status": "Step 2/3",
                "task_key": "runner:backup_runner",
                "waiting_for_lock": False,
                "started": "2026-06-29T09:00:00",
            }
        ]
        self._run_refresh(app, tasks=tasks)
        appended = store.append.call_args[0][0]
        self.assertEqual(appended[4], "running")
        self.assertTrue(appended[3].startswith("Running since 2026-06-29T09:00"))
        self.assertTrue(appended[3].endswith("(Step 2/3)"))

    def test_running_row_omits_pid_and_generic_status(self):
        app, store, _selection = self._make_app()
        tasks = [
            {
                "name": "Daily",
                "type": "Profile",
                "status": "PID 1234",
                "task_key": "profile:Daily",
                "waiting_for_lock": False,
                "started": "2026-06-29T09:00:00",
            }
        ]
        self._run_refresh(app, tasks=tasks)
        appended = store.append.call_args[0][0]
        self.assertTrue(appended[3].startswith("Running since 2026-06-29T09:00"))
        self.assertNotIn("PID", appended[3])
        self.assertNotIn("(", appended[3])

    def test_reverse_chronological_order_mixed_rows(self):
        app, store, _selection = self._make_app()
        tasks = [
            {
                "name": "Running task",
                "type": "GUI",
                "status": "Step 1/2",
                "task_key": "runner:backup_runner",
                "waiting_for_lock": False,
                "started": "2026-06-29T12:00:00",
            }
        ]
        recent = [
            {
                "timestamp": "2026-06-29T13:00:00",
                "type": "backup",
                "name": "Newest completed",
                "result": "success",
            },
            {
                "timestamp": "2026-06-28T10:00:00",
                "type": "backup",
                "name": "Older completed",
                "result": "success",
            },
        ]
        self._run_refresh(app, tasks=tasks, recent=recent)
        names = [call[0][0][2] for call in store.append.call_args_list]
        self.assertEqual(names, ["Newest completed", "Running task", "Older completed"])

    def test_timeless_rows_sort_first(self):
        app, store, _selection = self._make_app()
        tasks = [
            {
                "name": "ZFS op",
                "type": "ZFS",
                "status": "42.0% done",
                "task_key": "zfsop:fivebays",
                "waiting_for_lock": False,
                "started": None,
            }
        ]
        recent = [
            {
                "timestamp": "2026-06-29T13:00:00",
                "type": "backup",
                "name": "Completed",
                "result": "success",
            }
        ]
        self._run_refresh(app, tasks=tasks, recent=recent)
        names = [call[0][0][2] for call in store.append.call_args_list]
        self.assertEqual(names, ["ZFS op", "Completed"])

    def test_preserves_selection_by_task_key_and_log_file(self):
        app, store, selection = self._make_app(
            selected_rows=[
                {"task_key": "runner:backup_runner", "log_file": ""},
                {"task_key": "", "log_file": "/var/log/zfsutilities/sessions/keep.log"},
            ]
        )
        first_iter, second_iter, third_iter = MagicMock(), MagicMock(), MagicMock()
        store.append.side_effect = [first_iter, second_iter, third_iter]
        expected_paths = [MagicMock(), MagicMock()]
        store.get_path.side_effect = expected_paths

        tasks = [
            {
                "name": "Backup",
                "type": "GUI",
                "status": "Step 1/2",
                "task_key": "runner:backup_runner",
                "waiting_for_lock": False,
                "started": "2026-06-29T12:00:00",
            }
        ]
        recent = [
            {
                "timestamp": "2026-06-29T13:00:00",
                "type": "backup",
                "name": "Other",
                "result": "success",
                "log_file": "/var/log/zfsutilities/sessions/other.log",
            },
            {
                "timestamp": "2026-06-29T11:00:00",
                "type": "backup",
                "name": "Keep",
                "result": "success",
                "log_file": "/var/log/zfsutilities/sessions/keep.log",
            },
        ]
        self._run_refresh(app, tasks=tasks, recent=recent)

        self.assertEqual(store.append.call_count, 3)
        self.assertEqual(selection.select_path.call_count, 2)
        select_paths = [call[0][0] for call in selection.select_path.call_args_list]
        self.assertEqual(select_paths, expected_paths)

    def test_dismissed_entries_hidden(self):
        app, store, _selection = self._make_app()
        app.config = {"dashboard": {"dismissed_tasks": ["/var/log/zfsutilities/sessions/gone.log"]}}
        recent = [
            {
                "timestamp": "2026-06-29T13:00:00",
                "type": "backup",
                "name": "Dismissed",
                "result": "success",
                "log_file": "/var/log/zfsutilities/sessions/gone.log",
            },
            {
                "timestamp": "2026-06-29T12:00:00",
                "type": "backup",
                "name": "Kept",
                "result": "success",
                "log_file": "/var/log/zfsutilities/sessions/kept.log",
            },
        ]
        with patch.object(dp, "save_dashboard_config") as mock_save:
            self._run_refresh(app, recent=recent)
            # The dismissal key still matches the window, so nothing is pruned
            # and nothing needs saving.
            mock_save.assert_not_called()
        names = [call[0][0][2] for call in store.append.call_args_list]
        self.assertEqual(names, ["Kept"])

    def test_dismissal_keys_pruned_to_window(self):
        app, store, _selection = self._make_app()
        app.config = {
            "dashboard": {
                "dismissed_tasks": [
                    "/var/log/zfsutilities/sessions/gone.log",
                    "/var/log/zfsutilities/sessions/ancient.log",
                ]
            }
        }
        recent = [
            {
                "timestamp": "2026-06-29T13:00:00",
                "type": "backup",
                "name": "Dismissed",
                "result": "success",
                "log_file": "/var/log/zfsutilities/sessions/gone.log",
            }
        ]
        with patch.object(dp, "save_dashboard_config") as mock_save:
            self._run_refresh(app, recent=recent)
            mock_save.assert_called_once()
            saved = mock_save.call_args[0][1]
            self.assertEqual(saved["dismissed_tasks"], ["/var/log/zfsutilities/sessions/gone.log"])
        # The only window entry is dismissed, so the placeholder shows.
        store.append.assert_called_once()
        self.assertEqual(store.append.call_args[0][0][0], "No tasks")


class TestRefreshActiveLocksSection(unittest.TestCase):
    """_refresh_active_locks_section populates the Active Locks list."""

    def test_empty_locks_placeholder_has_seven_columns(self):
        with mock_gtk() as gtk_mock, patch.object(dp, "Gtk", gtk_mock):
            app = MagicMock()
            store = MagicMock()
            app.dashboard_locks_store = store
            dp._refresh_active_locks_section(app, [])

        store.append.assert_called_once()
        appended = store.append.call_args[0][0]
        self.assertEqual(len(appended), 7)
        self.assertEqual(appended[0], "No active locks")

    def test_populates_store_from_lock_dicts(self):
        with mock_gtk() as gtk_mock, patch.object(dp, "Gtk", gtk_mock):
            app = MagicMock()
            store = MagicMock()
            app.dashboard_locks_store = store
            locks = [
                {
                    "dataset": "tank/data",
                    "type": "w",
                    "pid": 1234,
                    "script": "zfsdailybackup",
                    "host": "storage1",
                    "acquired": "2026-06-01T12:00:00",
                    "description": "daily backup",
                }
            ]
            dp._refresh_active_locks_section(app, locks)

        store.append.assert_called_once()
        appended = store.append.call_args[0][0]
        self.assertEqual(
            appended,
            [
                "tank/data",
                "w",
                "1234",
                "zfsdailybackup",
                "storage1",
                "2026-06-01T12:00:00",
                "daily backup",
            ],
        )


class TestGatherDashboardData(unittest.TestCase):
    """_gather_dashboard_data includes active locks and other dashboard state."""

    def test_includes_active_locks_key(self):
        app = MagicMock()
        app.config = {}
        with (
            patch.object(dp, "_get_pool_health", return_value=[]),
            patch.object(dp, "_get_recent_entries", return_value=[]),
            patch.object(dp, "_get_iscsi_missing_luns", return_value=([], False)),
            patch.object(dp, "_count_stale_locks", return_value=0),
            patch.object(dp, "_collect_running_tasks", return_value=[]),
            patch.object(dp, "list_active_locks", return_value=[]),
            patch.object(dp, "_gather_config_section_data", return_value={}),
            patch.object(dp, "get_dashboard_config", return_value={"low_space_threshold": 80}),
        ):
            data = dp._gather_dashboard_data(app)
        self.assertIn("active_locks", data)
        self.assertEqual(data["active_locks"], [])


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
            gtk_mock.SpinButton = MagicMock
            # gui_helpers stays real-Gtk-bound here (no fresh re-import),
            # and the shared capped_treeview_scroll builds its windows
            # through gui_helpers' Gtk — patch it too or real widgets get
            # constructed headless.
            with patch.object(dp, "Gtk", gtk_mock), patch.object(gh, "Gtk", gtk_mock):
                with patch.object(dp, "refresh_dashboard_page"):
                    with patch.object(dp, "_is_two_node", return_value=two_node):
                        page = dp.create_dashboard_page(app)
        return page

    def test_creates_expected_frames_and_widgets(self):
        app = self._create_app()
        self._run_create(app)
        self.assertIsNotNone(app.dashboard_warn_frame)
        self.assertIsNotNone(app.dashboard_pool_frame)
        self.assertIsNotNone(app.dashboard_tasks_frame)
        self.assertIsNotNone(app.dashboard_iscsi_frame)
        self.assertIsNotNone(app.dashboard_config_frame)
        self.assertIsNotNone(app.dashboard_pool_grid)
        self.assertIsNotNone(app.dashboard_threshold_spin)
        self.assertIsNotNone(app.dashboard_refresh_spin)
        self.assertIsNotNone(app.dashboard_refreshing_label)
        self.assertIsNotNone(app.dashboard_tasks_view)
        self.assertIsNotNone(app.dashboard_tasks_store)
        self.assertIsNotNone(app.dashboard_locks_frame)
        self.assertIsNotNone(app.dashboard_locks_view)
        self.assertIsNotNone(app.dashboard_locks_store)

    def test_dashboard_tasks_view_is_bound_for_width_persistence(self):
        """Tasks columns should be saved and restored."""
        app = self._create_app()
        self._run_create(app)
        app._ui_state.bind_treeview.assert_any_call(
            app.dashboard_tasks_view, "dashboard_tasks_view"
        )

    def test_section_order_in_top_level_box(self):
        app = self._create_app()
        page = self._run_create(app)
        top_box = page.children[0]
        expected_titles = [
            "<b>Warnings</b>",
            "<b>Pool Health</b>",
            "<b>Tasks</b>",
            "<b>Active Locks</b>",
            "<b>iSCSI Issues</b>",
            "<b>Configuration</b>",
        ]
        # children[0] is the title label; children[1] is the refresh controls;
        # the remaining children are the section frames.
        frame_children = top_box.children[2:]
        self.assertEqual(len(frame_children), 6)
        self.assertEqual([_frame_title(f) for f in frame_children], expected_titles)

    def test_refresh_spinner_configuration(self):
        app = self._create_app()
        self._run_create(app)
        spin = app.dashboard_refresh_spin
        spin.set_range.assert_called_once_with(1, 300)
        spin.set_increments.assert_called_once_with(1, 10)
        spin.set_value.assert_called_once_with(30)
        args = spin.connect.call_args[0]
        self.assertEqual(args[0], "value-changed")
        self.assertTrue(callable(args[1]))
        self.assertIs(args[2], app)

    def test_refreshing_indicator_initially_hidden(self):
        app = self._create_app()
        self._run_create(app)
        lbl = app.dashboard_refreshing_label
        lbl.set_no_show_all.assert_called_once_with(True)
        lbl.hide.assert_called_once_with()

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
        pool_grid_sw.set_min_content_width.assert_called_once_with(300)
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

    def test_outer_scrolled_window_can_shrink_horizontally(self):
        """The dashboard outer ScrolledWindow must allow horizontal shrinking."""
        app = self._create_app()
        page = self._run_create(app)
        self.assertIsInstance(page, _WidgetRecorder)
        page.set_policy.assert_called_once()
        page.set_min_content_width.assert_called_once_with(400)

    def test_configuration_grid_is_horizontally_scrollable(self):
        """Configuration grid lives in a horizontally-scrollable ScrolledWindow."""
        app = self._create_app()
        self._run_create(app)
        config_sw = app.dashboard_config_frame.children[0]
        self.assertIsInstance(config_sw, _WidgetRecorder)
        config_sw.set_policy.assert_called_once()
        config_sw.set_min_content_width.assert_called_once_with(300)
        config_sw.set_propagate_natural_height.assert_called_once_with(True)
        self.assertIn(app.dashboard_config_grid, config_sw.children)

    def test_table_windows_are_capped_scrolls(self):
        """Tasks / Active Locks sit in the shared capped scrolled windows;
        the Tasks window keeps a constant ten-row footprint (fixed_rows),
        while Active Locks keeps the Dashboard's natural-height convention.
        The page viewport sizes its content by natural height so the box is
        never clamped to the window height."""
        with mock_gtk(fresh=True) as gtk:
            scrolls = []
            views = []

            def _make_scroll(*args, **kwargs):
                scroll = MagicMock()
                scrolls.append(scroll)
                return scroll

            def _make_view(*args, **kwargs):
                view = MagicMock()
                views.append(view)
                return view

            gtk.ScrolledWindow = MagicMock(side_effect=_make_scroll)
            gtk.TreeView = MagicMock(side_effect=_make_view)
            import dashboard_page as dp_fresh

            app = self._create_app()
            real_capped = dp_fresh.capped_treeview_scroll
            capped_choices = []

            def _record_capped(view, *args, **kwargs):
                capped_choices.append(
                    (kwargs.get("row_target", "default"), kwargs.get("fixed_rows", "default"))
                )
                return real_capped(view, *args, **kwargs)

            with patch.object(dp_fresh, "capped_treeview_scroll", side_effect=_record_capped):
                with patch.object(dp_fresh, "refresh_dashboard_page"):
                    with patch.object(dp_fresh, "_is_two_node", return_value=False):
                        page = dp_fresh.create_dashboard_page(app)
            # The Tasks table pins a ten-row window; Active Locks keeps the
            # natural-height convention.
            self.assertEqual(capped_choices, [(10, True), ("default", False)])

            # ScrolledWindow creation order: the page window, the pool
            # grid, the two table windows, then the config grid.
            tasks_sw, locks_sw = scrolls[2], scrolls[3]
            for scroll, view in (
                (tasks_sw, app.dashboard_tasks_view),
                (locks_sw, app.dashboard_locks_view),
            ):
                scroll.add.assert_called_once_with(view)
                scroll.set_propagate_natural_height.assert_called_once_with(True)
                scroll.set_min_content_height.assert_called_once()
                scroll.set_max_content_height.assert_called_once()
            # The fixed ten-row Tasks window sizes above the natural-height
            # floor Active Locks falls back to.
            tasks_min = tasks_sw.set_min_content_height.call_args[0][0]
            self.assertGreater(tasks_min, 60)
            locks_sw.set_min_content_height.assert_called_once_with(60)
            viewport = page.get_child()
            viewport.set_vscroll_policy.assert_called_once_with(
                dp_fresh.Gtk.ScrollablePolicy.NATURAL
            )

    def test_iscsi_frame_hidden_in_single_node_mode(self):
        app = self._create_app()
        self._run_create(app, two_node=False)
        app.dashboard_iscsi_frame.hide.assert_called_once()

    def test_iscsi_frame_not_hidden_in_two_node_mode(self):
        app = self._create_app()
        self._run_create(app, two_node=True)
        app.dashboard_iscsi_frame.hide.assert_not_called()


class TestTaskActionButtons(unittest.TestCase):
    """Cancel / Remove button gating over the merged Tasks selection."""

    def _make_app(self, rows):
        app, selection = _make_tasks_selection_app(rows)
        app._cancel_selected_button = MagicMock()
        app._remove_button = MagicMock()
        app._view_log_button = MagicMock()
        return app, selection

    def test_starts_disabled_when_no_tasks_selected(self):
        app, selection = self._make_app([])
        dp.setup_dashboard_actions(app)
        selection.connect.assert_called()
        app._cancel_selected_button.set_sensitive.assert_called_once_with(False)
        app._remove_button.set_sensitive.assert_called_once_with(False)

    def test_enables_when_running_task_selected(self):
        app, _selection = self._make_app([{"state": "running", "task_key": "runner:backup_runner"}])
        dp.setup_dashboard_actions(app)
        app._cancel_selected_button.set_sensitive.assert_called_once_with(True)
        app._remove_button.set_sensitive.assert_called_once_with(False)

    def test_enables_when_waiting_task_selected(self):
        """Waiting rows are cancellable too."""
        app, _selection = self._make_app([{"state": "waiting", "task_key": "profile-wait:Daily"}])
        dp.setup_dashboard_actions(app)
        app._cancel_selected_button.set_sensitive.assert_called_once_with(True)

    def test_remove_enabled_only_for_completed_row(self):
        app, _selection = self._make_app(
            [{"state": "completed", "log_file": "/var/log/zfsutilities/sessions/x.log"}]
        )
        dp.setup_dashboard_actions(app)
        app._remove_button.set_sensitive.assert_called_once_with(True)
        app._cancel_selected_button.set_sensitive.assert_called_once_with(False)

    def test_mixed_selection_enables_both(self):
        app, _selection = self._make_app(
            [
                {"state": "running", "task_key": "scrub:fivebays"},
                {"state": "completed", "log_file": "/var/log/zfsutilities/sessions/x.log"},
            ]
        )
        dp.setup_dashboard_actions(app)
        app._cancel_selected_button.set_sensitive.assert_called_once_with(True)
        app._remove_button.set_sensitive.assert_called_once_with(True)

    def test_placeholder_keeps_both_disabled(self):
        """Selecting the 'No tasks' placeholder keeps both buttons disabled."""
        app, _selection = self._make_app([{}])
        dp.setup_dashboard_actions(app)
        app._cancel_selected_button.set_sensitive.assert_called_once_with(False)
        app._remove_button.set_sensitive.assert_called_once_with(False)

    def test_toggles_with_selection_changes(self):
        row = {"state": "running", "task_key": ""}
        app, selection = self._make_app([row])
        dp.setup_dashboard_actions(app)
        # reset after initial call
        app._remove_button.reset_mock()
        app._cancel_selected_button.reset_mock()

        row["task_key"] = "runner:backup_runner"
        callback = selection.connect.call_args[0][1]
        callback(selection, app)
        app._remove_button.set_sensitive.assert_called_once_with(False)
        app._cancel_selected_button.set_sensitive.assert_called_with(True)

    def test_no_button_attr_does_not_crash(self):
        app, _selection = self._make_app([])
        del app._cancel_selected_button
        del app._remove_button
        dp.setup_dashboard_actions(app)
        # Should not raise


class TestOnDashboardCancelSelected(unittest.TestCase):
    """on_dashboard_cancel_selected cancels rows with a task key (col 5)."""

    def _make_app(self, rows):
        app, _selection = _make_tasks_selection_app(rows)
        return app

    def test_cancels_waiting_and_running_rows(self):
        rows = [
            {"state": "waiting", "task_key": "profile-wait:Daily"},
            {"state": "completed", "log_file": "/var/log/zfsutilities/sessions/a.log"},
            {"state": "running", "task_key": "runner:backup_runner"},
        ]
        app = self._make_app(rows)
        with (
            patch.object(dp, "_cancel_task") as mock_cancel,
            patch.object(dp, "GLib") as mock_glib,
        ):
            dp.on_dashboard_cancel_selected(app)
        # The completed row carries no task key and is skipped.
        self.assertEqual(
            [call[0][1] for call in mock_cancel.call_args_list],
            ["profile-wait:Daily", "runner:backup_runner"],
        )
        mock_glib.timeout_add_seconds.assert_called_once()

    def test_warns_when_nothing_selected(self):
        app = self._make_app([])
        with (
            patch.object(dp, "_cancel_task") as mock_cancel,
            patch.object(dp, "GLib") as mock_glib,
            capture_logs() as logs,
        ):
            dp.on_dashboard_cancel_selected(app)
        mock_cancel.assert_not_called()
        mock_glib.timeout_add_seconds.assert_not_called()
        self.assertTrue(any("No tasks selected" in msg for msg in logs))

    def test_no_timeout_when_nothing_cancellable(self):
        app = self._make_app(
            [{"state": "completed", "log_file": "/var/log/zfsutilities/sessions/a.log"}]
        )
        with (
            patch.object(dp, "_cancel_task") as mock_cancel,
            patch.object(dp, "GLib") as mock_glib,
        ):
            dp.on_dashboard_cancel_selected(app)
        mock_cancel.assert_not_called()
        mock_glib.timeout_add_seconds.assert_not_called()


class TestRemoveSelected(unittest.TestCase):
    """on_dashboard_remove_selected dismisses only completed rows."""

    def _make_app(self, rows):
        app, _selection = _make_tasks_selection_app(rows)
        app.config = {}
        return app

    def test_removes_only_completed_rows(self):
        rows = [
            {"state": "completed", "log_file": "/var/log/zfsutilities/sessions/a.log"},
            {"state": "running", "task_key": "runner:backup_runner"},
            {"state": "completed", "log_file": "/var/log/zfsutilities/sessions/b.log"},
        ]
        app = self._make_app(rows)
        model = app.dashboard_tasks_view.get_selection.return_value.get_selected_rows.return_value[
            0
        ]
        paths = app.dashboard_tasks_view.get_selection.return_value.get_selected_rows.return_value[
            1
        ]

        with patch.object(dp, "save_dashboard_config") as mock_save:
            with capture_logs() as logs:
                dp.on_dashboard_remove_selected(app)

        # Only the two completed rows are removed.
        self.assertEqual(model.remove.call_count, 2)
        removed_iters = [call[0][0] for call in model.remove.call_args_list]
        self.assertEqual(removed_iters, [model.get_iter(paths[2]), model.get_iter(paths[0])])
        mock_save.assert_called_once()
        saved = mock_save.call_args[0][1]
        self.assertEqual(
            saved["dismissed_tasks"],
            ["/var/log/zfsutilities/sessions/a.log", "/var/log/zfsutilities/sessions/b.log"],
        )
        self.assertTrue(any("Removed 2 completed task" in msg for msg in logs))

    def test_existing_dismissals_are_kept(self):
        rows = [{"state": "completed", "log_file": "/var/log/zfsutilities/sessions/new.log"}]
        app = self._make_app(rows)
        app.config = {"dashboard": {"dismissed_tasks": ["/var/log/zfsutilities/sessions/old.log"]}}
        with patch.object(dp, "save_dashboard_config") as mock_save:
            dp.on_dashboard_remove_selected(app)
        saved = mock_save.call_args[0][1]
        self.assertEqual(
            sorted(saved["dismissed_tasks"]),
            ["/var/log/zfsutilities/sessions/new.log", "/var/log/zfsutilities/sessions/old.log"],
        )

    def test_warns_when_no_completed_row_selected(self):
        rows = [{"state": "running", "task_key": "runner:backup_runner"}]
        app = self._make_app(rows)
        model = app.dashboard_tasks_view.get_selection.return_value.get_selected_rows.return_value[
            0
        ]
        with patch.object(dp, "save_dashboard_config") as mock_save:
            with capture_logs() as logs:
                dp.on_dashboard_remove_selected(app)
        model.remove.assert_not_called()
        mock_save.assert_not_called()
        self.assertTrue(any("No completed tasks selected" in msg for msg in logs))


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

    def _run_refresh(self, cfg, versions, zfs_versions, os_infos=None):
        """Call _refresh_config_section with mocked dependencies.

        Returns the app mock and the mock Gtk object so callers can inspect
        the labels that were created.
        """
        os_infos = os_infos or {}
        created_labels = []

        def _make_label(*args, **kwargs):
            lbl = MagicMock()
            created_labels.append((lbl, kwargs.get("label")))
            return lbl

        with mock_gtk() as gtk_mock:
            gtk_mock.Label.side_effect = _make_label
            gtk_mock._created_labels = created_labels
            with patch.object(dp, "Gtk", gtk_mock):
                with patch.object(dp, "_get_node_config", return_value=cfg):
                    with patch.object(dp, "_get_host_version", side_effect=versions.get):
                        with patch.object(
                            dp,
                            "_get_host_zfs_version",
                            side_effect=zfs_versions.get,
                        ):
                            with patch.object(
                                dp,
                                "_get_host_os_info",
                                side_effect=os_infos.get,
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
            os_infos={"myhost": ("Debian GNU/Linux", "12 (bookworm)")},
        )
        # The grid attach method should have been called for the ZFS value.
        self.assertTrue(self._find_label_with_text(gtk_mock, "zfs-2.2.2"))

    def test_versions_row_precedes_operating_systems_row(self):
        """The Version(s) item renders immediately before Operating system(s)."""
        cfg = {
            "mode": "single-node",
            "this_host": "myhost",
            "storage_host": "",
            "compute_host": "",
        }
        app, gtk_mock = self._run_refresh(
            cfg,
            versions={"myhost": "1.2.3"},
            zfs_versions={"myhost": "zfs-2.2.2"},
            os_infos={"myhost": ("Debian GNU/Linux", "12 (bookworm)")},
        )
        rows = {}
        attach_calls = app.dashboard_config_grid.attach.call_args_list
        for lbl_mock, text in gtk_mock._created_labels:
            if text is not None or not lbl_mock.set_markup.called:
                continue
            markup = lbl_mock.set_markup.call_args[0][0]
            for name in ("Version(s)", "Operating system(s)"):
                if markup == f"<b>{name}:</b>":
                    for call in attach_calls:
                        if call[0][0] is lbl_mock and call[0][1] == 0:
                            rows[name] = call[0][2]
        self.assertEqual(
            rows.get("Version(s)"),
            rows.get("Operating system(s)", 0) - 1,
            f"Version(s) row must immediately precede Operating system(s) row, got {rows}",
        )

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
            os_infos={
                "host-a": ("Debian GNU/Linux", "12 (bookworm)"),
                "host-b": ("Debian GNU/Linux", "12 (bookworm)"),
                "host-c": ("Debian GNU/Linux", "12 (bookworm)"),
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
            os_infos={
                "host-a": ("Debian GNU/Linux", "12 (bookworm)"),
                "host-b": ("Debian GNU/Linux", "12 (bookworm)"),
            },
        )
        expected = "host-a (this,storage):\nzfs-2.2.2\n\nhost-b (compute):\nzfs-2.2.3"
        self.assertTrue(self._find_label_with_text(gtk_mock, expected))

    def test_single_node_shows_local_os_info(self):
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
            os_infos={"myhost": ("Debian GNU/Linux", "13 (trixie)")},
        )
        self.assertTrue(self._find_label_with_text(gtk_mock, "Debian GNU/Linux 13 (trixie)"))

    def test_two_node_shows_os_info_per_unique_host(self):
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
            os_infos={
                "host-a": ("Proxmox VE", "8.2.4"),
                "host-b": ("Debian GNU/Linux", "12 (bookworm)"),
                "host-c": ("Linux Mint", "22 (Wilma)"),
            },
        )
        expected_name = (
            "host-a (this):\n"
            "Proxmox VE 8.2.4\n\n"
            "host-b (storage):\n"
            "Debian GNU/Linux 12 (bookworm)\n\n"
            "host-c (compute):\n"
            "Linux Mint 22 (Wilma)"
        )
        self.assertTrue(self._find_label_with_text(gtk_mock, expected_name))

    def test_two_node_deduplicates_same_host_across_roles_for_os(self):
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
            os_infos={
                "host-a": ("Proxmox VE", "8.2.4"),
                "host-b": ("Debian GNU/Linux", "12 (bookworm)"),
            },
        )
        expected_name = (
            "host-a (this,storage):\n"
            "Proxmox VE 8.2.4\n\n"
            "host-b (compute):\n"
            "Debian GNU/Linux 12 (bookworm)"
        )
        self.assertTrue(self._find_label_with_text(gtk_mock, expected_name))

    def test_config_labels_align_to_top_of_values(self):
        """Column-0 Configuration labels are top-aligned to match value first line."""
        cfg = {
            "mode": "two-node",
            "this_host": "host-a",
            "storage_host": "host-b",
            "compute_host": "host-c",
        }
        app, gtk_mock = self._run_refresh(
            cfg,
            versions={"host-a": "1.0", "host-b": "1.0", "host-c": "1.0"},
            zfs_versions={
                "host-a": "zfs-2.2.2",
                "host-b": "zfs-2.2.3",
                "host-c": "zfs-2.2.4",
            },
            os_infos={
                "host-a": ("Debian GNU/Linux", "12 (bookworm)"),
                "host-b": ("Debian GNU/Linux", "12 (bookworm)"),
                "host-c": ("Debian GNU/Linux", "12 (bookworm)"),
            },
        )
        col0_labels = []
        for call in app.dashboard_config_grid.attach.call_args_list:
            widget, left, _top, _width, _height = call.args
            if left == 0:
                col0_labels.append(widget)

        self.assertGreater(len(col0_labels), 0)
        for widget in col0_labels:
            self.assertTrue(
                widget.set_valign.called,
                "column-0 Configuration label should set vertical alignment",
            )
            self.assertEqual(
                widget.set_valign.call_args[0][0],
                gtk_mock.Align.START,
            )


class TestGetHostOsInfo(unittest.TestCase):
    """_get_host_os_info() detects OS name and version per host."""

    @patch("dashboard_page._local_hostname", return_value="myhost")
    @patch("subprocess.run")
    def test_local_proxmox_detected_via_pveversion(self, mock_run, _mock_local):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "pve-manager/8.2.4/2a4a85a15c2b3986\n"
        name, version = dp._get_host_os_info("myhost")
        self.assertEqual(name, "Proxmox VE")
        self.assertEqual(version, "8.2.4")

    @patch("dashboard_page._local_hostname", return_value="myhost")
    @patch("subprocess.run")
    def test_local_debian_from_os_release(self, mock_run, _mock_local):
        def side_effect(cmd, **kwargs):
            result = MagicMock()
            if cmd[:2] == ["cat", "/etc/os-release"]:
                result.returncode = 0
                result.stdout = (
                    'PRETTY_NAME="Debian GNU/Linux 13 (trixie)"\n'
                    'NAME="Debian GNU/Linux"\n'
                    'VERSION_ID="13"\n'
                    'VERSION="13 (trixie)"\n'
                    "ID=debian\n"
                )
            else:
                result.returncode = 127
                result.stdout = ""
            return result

        mock_run.side_effect = side_effect
        name, version = dp._get_host_os_info("myhost")
        self.assertEqual(name, "Debian GNU/Linux")
        self.assertEqual(version, "13 (trixie)")

    @patch("dashboard_page._local_hostname", return_value="myhost")
    @patch("subprocess.run")
    def test_local_linux_mint_from_os_release(self, mock_run, _mock_local):
        def side_effect(cmd, **kwargs):
            result = MagicMock()
            if cmd[:2] == ["cat", "/etc/os-release"]:
                result.returncode = 0
                result.stdout = (
                    'NAME="Linux Mint"\n'
                    'VERSION="22 (Wilma)"\n'
                    "ID=linuxmint\n"
                    'ID_LIKE="ubuntu debian"\n'
                )
            else:
                result.returncode = 127
                result.stdout = ""
            return result

        mock_run.side_effect = side_effect
        name, version = dp._get_host_os_info("myhost")
        self.assertEqual(name, "Linux Mint")
        self.assertEqual(version, "22 (Wilma)")

    @patch("dashboard_page._local_hostname", return_value="myhost")
    @patch("subprocess.run")
    def test_local_ubuntu_when_pveversion_absent(self, mock_run, _mock_local):
        """pveversion returning 127 (command not found) falls back to /etc/os-release."""

        def side_effect(cmd, **kwargs):
            result = MagicMock()
            if cmd[:2] == ["cat", "/etc/os-release"]:
                result.returncode = 0
                result.stdout = (
                    'PRETTY_NAME="Ubuntu 24.04.1 LTS"\n'
                    'NAME="Ubuntu"\n'
                    'VERSION_ID="24.04"\n'
                    'VERSION="24.04.1 LTS (Noble Numbat)"\n'
                    "ID=ubuntu\n"
                    'ID_LIKE="debian"\n'
                )
            else:
                # Simulate pveversion not being installed.
                result.returncode = 127
                result.stdout = ""
            return result

        mock_run.side_effect = side_effect
        name, version = dp._get_host_os_info("myhost")
        self.assertEqual(name, "Ubuntu")
        self.assertEqual(version, "24.04.1 LTS (Noble Numbat)")

    @patch("dashboard_page._local_hostname", return_value="myhost")
    @patch("subprocess.run")
    def test_remote_proxmox_detected_via_ssh(self, mock_run, _mock_local):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "pve-manager/8.1.0/abcdef1234567890\n"
        name, version = dp._get_host_os_info("remote1")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertEqual(args[:3], ["ssh", "root@remote1", "pveversion"])
        self.assertEqual(name, "Proxmox VE")
        self.assertEqual(version, "8.1.0")

    @patch("dashboard_page._local_hostname", return_value="myhost")
    @patch("subprocess.run")
    def test_inxi_fallback_parses_distro(self, mock_run, _mock_local):
        def side_effect(cmd, **kwargs):
            result = MagicMock()
            if cmd[:2] == ["cat", "/etc/os-release"]:
                result.returncode = 1
                result.stdout = ""
            elif cmd[:2] == ["inxi", "-S"]:
                result.returncode = 0
                result.stdout = (
                    "System:\n"
                    "  Host: myhost Kernel: 6.8.0 x86_64 bits: 64\n"
                    "  Desktop: Cinnamon 6.2 Distro: Linux Mint 22 Wilma\n"
                )
            else:
                result.returncode = 127
                result.stdout = ""
            return result

        mock_run.side_effect = side_effect
        name, version = dp._get_host_os_info("myhost")
        self.assertEqual(name, "Linux Mint")
        self.assertEqual(version, "22 Wilma")

    @patch("dashboard_page._local_hostname", return_value="myhost")
    @patch("subprocess.run", side_effect=OSError("command not found"))
    def test_returns_unknown_on_failure(self, mock_run, _mock_local):
        name, version = dp._get_host_os_info("myhost")
        self.assertEqual(name, "unknown")
        self.assertEqual(version, "unknown")


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
                with patch.object(
                    dp, "resolve_local_bin", return_value="/test/bin/repair-iscsi-luns"
                ):
                    dp._on_fix_iscsi_clicked(None, app)

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertEqual(args[0], "/test/bin/repair-iscsi-luns")
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

        self.assertTrue(any("repair-iscsi-luns exited 1" in msg for msg in logs))

    def test_fix_iscsi_logs_failure(self):
        app = self._create_app()
        with patch("subprocess.run", side_effect=OSError("no such file")):
            with patch.object(dp, "refresh_dashboard_page"):
                with capture_logs() as logs:
                    dp._on_fix_iscsi_clicked(None, app)

        self.assertTrue(any("repair-iscsi-luns failed" in msg for msg in logs))

    def test_fix_iscsi_preserves_inner_log_level(self):
        """Bash log_msg lines on stderr must not be reclassified as WARN."""
        app = self._create_app()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "=== repair-iscsi-luns ===\n"
            mock_run.return_value.stderr = (
                "/test/bin/repair-iscsi-luns:370: INFO: Loaded backstores: 33\n"
                "/test/bin/repair-iscsi-luns:414: WARN: Device not available: "
                "/dev/zvol/threeamigos/proxmox/vm-215-disk-1 (skipping vm-215-disk-1)\n"
            )
            with (
                patch.object(dp, "refresh_dashboard_page"),
                patch.object(dp, "resolve_local_bin", return_value="/test/bin/repair-iscsi-luns"),
                capture_logs() as logs,
            ):
                dp._on_fix_iscsi_clicked(None, app)

        levels = [parse_msg_level(msg) for msg in logs]
        self.assertIn("INFO", levels)
        self.assertIn("WARN", levels)

        info_msgs = [msg for msg in logs if parse_msg_level(msg) == "INFO"]
        self.assertTrue(
            any("Loaded backstores: 33" in msg for msg in info_msgs),
            f"Expected INFO message about backstores in {info_msgs!r}",
        )

        warn_msgs = [msg for msg in logs if parse_msg_level(msg) == "WARN"]
        self.assertTrue(
            any("vm-215-disk-1" in msg for msg in warn_msgs),
            f"Expected WARN message about vm-215-disk-1 in {warn_msgs!r}",
        )


class TestDashboardMountOrderRepair(unittest.TestCase):
    """The Dashboard flags unreachable mounts and offers the repair."""

    def test_repair_button_sensitivity_follows_findings(self):
        app = MagicMock()
        dp._update_repair_mount_order_button(app, [{"name": "tank/a"}])
        app._repair_mount_order_button.set_sensitive.assert_called_once_with(True)

        app_empty = MagicMock()
        dp._update_repair_mount_order_button(app_empty, [])
        app_empty._repair_mount_order_button.set_sensitive.assert_called_once_with(False)

    def test_repair_button_missing_is_tolerated(self):
        import types

        app = types.SimpleNamespace()
        dp._update_repair_mount_order_button(app, [{"name": "tank/a"}])  # must not raise

    def test_repair_handler_runs_full_scope_repair(self):
        app = MagicMock()
        with patch("dataset_actions.run_mount_repair") as mock_run:
            with patch.object(dp, "refresh_dashboard_page") as mock_refresh:
                dp.on_dashboard_repair_mount_order(app)
        mock_run.assert_called_once_with(app, scope=None)
        mock_refresh.assert_called_once()

    def test_gather_reports_unreachable_mounts_as_warnings(self):
        app = MagicMock()
        app.config = {"backup": {"pull_steps": ["x"]}, "offsite": {"steps": ["x"]}}
        rows = [{"name": "tank/proxmox", "mountpoint": "/tank/proxmox"}]
        with patch.object(dp, "_get_pool_health", return_value=[]):
            with patch.object(dp, "_get_recent_entries", return_value=[]):
                with patch.object(dp, "_attach_highest_levels"):
                    with patch.object(dp, "_get_iscsi_missing_luns", return_value=[]):
                        with patch.object(dp, "_count_stale_locks", return_value=0):
                            with patch("scrub_manager.get_all_pool_scrub_states", return_value={}):
                                with patch.object(dp, "_collect_running_tasks", return_value=[]):
                                    with patch.object(dp, "list_active_locks", return_value=[]):
                                        with patch(
                                            "zfs_repository.find_unreachable_mounts",
                                            return_value=rows,
                                        ):
                                            with patch.object(dp, "_get_warnings", return_value=[]):
                                                with patch(
                                                    "feature_config.get_pools",
                                                    return_value=["tank"],
                                                ):
                                                    with patch(
                                                        "feature_config.get_checkagainst",
                                                        return_value={"pool": "*"},
                                                    ):
                                                        with patch.object(
                                                            dp,
                                                            "_get_disk_wear_warnings",
                                                            return_value=[],
                                                        ):
                                                            with patch.object(
                                                                dp,
                                                                "_gather_config_section_data",
                                                                return_value={},
                                                            ):
                                                                data = dp._gather_dashboard_data(
                                                                    app
                                                                )
        self.assertEqual(data["unreachable_mounts"], rows)
        self.assertTrue(
            any(
                "tank/proxmox is mounted at /tank/proxmox" in warning
                for warning in data["warnings"]
            )
        )


if __name__ == "__main__":
    unittest.main()

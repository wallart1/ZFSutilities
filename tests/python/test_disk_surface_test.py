"""Tests for disk_surface_test.py and the DiskRepository self-test wrappers."""

import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import mock_gtk, mock_subprocess

NOW = datetime(2026, 9, 13, 12, 0, 0).astimezone()


def _import_surface_module():
    """Import disk_surface_test under a fresh mocked GTK context."""
    for name in ("disk_surface_test", "disk_repository"):
        sys.modules.pop(name, None)
    with mock_gtk():
        import disk_surface_test

        return disk_surface_test


class TestSelftestParsers(unittest.TestCase):
    """Text parsers for smartctl self-test output."""

    def setUp(self):
        import disk_repository

        self.dr = disk_repository

    def test_progress_in_progress(self):
        out = (
            "SMART Self-test log structure revision number 1\n"
            "Self-test routine in progress...  40% of test remaining\n"
        )
        self.assertEqual(self.dr._parse_selftest_progress(out), 40)

    def test_progress_idle(self):
        out = "# 1  Short offline  Completed without error  00%  1234  -\n"
        self.assertIsNone(self.dr._parse_selftest_progress(out))

    def test_test_minutes_short_and_extended(self):
        out = (
            "Short self-test routine recommended polling time:        (   2) minutes.\n"
            "Extended self-test routine recommended polling time:     ( 240) minutes.\n"
        )
        self.assertEqual(self.dr._parse_test_minutes(out, "short"), 2)
        self.assertEqual(self.dr._parse_test_minutes(out, "long"), 240)

    def test_test_minutes_missing(self):
        self.assertIsNone(self.dr._parse_test_minutes("no data here", "short"))

    def test_status_newest_row(self):
        out = (
            "SMART Self-test log structure revision number 1\n"
            "Num  Test_Description  Status  Remaining  LifeTime(hours)  LBA_of_first_error\n"
            "# 1  Extended offline  Completed: read failure  90%  100  12345\n"
            "# 2  Short offline  Completed without error  00%  50  -\n"
        )
        self.assertEqual(self.dr._parse_selftest_status(out), "Completed: read failure")

    def test_status_no_rows(self):
        out = "SMART Self-test log structure revision number 1\n"
        self.assertIsNone(self.dr._parse_selftest_status(out))

    def test_classify(self):
        c = self.dr.classify_selftest_status
        self.assertEqual(c("Completed without error"), "passed")
        self.assertEqual(c("Completed: read failure"), "failed")
        self.assertEqual(c("Fatal or unknown error"), "failed")
        self.assertEqual(c("Interrupted (host reset)"), "aborted")
        self.assertEqual(c("Aborted (device reset)"), "aborted")
        self.assertEqual(c(None), "aborted")


class TestRepositorySelfTestWrappers(unittest.TestCase):
    """DiskRepository start/abort/estimate/poll wrappers via mock_subprocess."""

    def _repo(self):
        from disk_repository import DiskRepository

        return DiskRepository(sudo=False)

    def test_start_self_test(self):
        calls = []

        def handler(cmd, **_kw):
            calls.append(cmd)
            return subprocess.CompletedProcess(args=[], returncode=0, stdout=" begun")

        with mock_subprocess() as m:
            m.set_command_handler(r"smartctl -t", handler)
            self.assertTrue(self._repo().start_self_test("/dev/sdb", "long"))
        self.assertIn("-t", calls[0])
        self.assertIn("long", calls[0])
        self.assertIn("/dev/sdb", calls[0])

    def test_start_self_test_bad_mode(self):
        self.assertFalse(self._repo().start_self_test("/dev/sdb", "sideways"))

    def test_start_self_test_failure(self):
        with mock_subprocess() as m:
            m.set_command_handler(
                r"smartctl -t",
                lambda _cmd, **_kw: subprocess.CompletedProcess(args=[], returncode=2, stdout=""),
            )
            self.assertFalse(self._repo().start_self_test("/dev/sdb", "short"))

    def test_abort_self_test(self):
        with mock_subprocess() as m:
            m.set_command_handler(
                r"smartctl -X",
                lambda _cmd, **_kw: subprocess.CompletedProcess(args=[], returncode=0, stdout=""),
            )
            self.assertTrue(self._repo().abort_self_test("/dev/sdb"))

    def test_estimate_test_minutes(self):
        out = "Extended self-test routine recommended polling time:     ( 240) minutes.\n"
        with mock_subprocess() as m:
            m.set_command_handler(
                r"smartctl -c",
                lambda _cmd, **_kw: subprocess.CompletedProcess(args=[], returncode=0, stdout=out),
            )
            self.assertEqual(self._repo().estimate_test_minutes("/dev/sdb", "long"), 240)

    def test_poll_running(self):
        out = "Self-test routine in progress...  40% of test remaining\n"
        with mock_subprocess() as m:
            m.set_command_handler(
                r"smartctl -l selftest",
                lambda _cmd, **_kw: subprocess.CompletedProcess(args=[], returncode=0, stdout=out),
            )
            poll = self._repo().poll_self_test("/dev/sdb")
        self.assertEqual(poll, {"running": True, "remaining_percent": 40})

    def test_poll_finished(self):
        out = "# 1  Extended offline  Completed without error  00%  100  -\n"
        with mock_subprocess() as m:
            m.set_command_handler(
                r"smartctl -l selftest",
                lambda _cmd, **_kw: subprocess.CompletedProcess(args=[], returncode=0, stdout=out),
            )
            poll = self._repo().poll_self_test("/dev/sdb")
        self.assertEqual(poll, {"running": False, "status_text": "Completed without error"})

    def test_poll_error_never_raises(self):
        with mock_subprocess() as m:
            m.set_command_handler(
                r"smartctl -l selftest",
                lambda _cmd, **_kw: (_ for _ in ()).throw(FileNotFoundError("smartctl")),
            )
            self.assertEqual(
                self._repo().poll_self_test("/dev/sdb"),
                {"running": False, "status_text": None},
            )


class TestSurfaceStateMachine(unittest.TestCase):
    """build_entry / update_entry_from_poll / update_entries_from_polls."""

    def _entry(self, **kwargs):
        dst = _import_surface_module()
        entry = {
            "status": "running",
            "mode": "long",
            "model": "WD10EZEX",
            "started_at": NOW.isoformat(),
            "estimated_minutes": 240,
            "progress_percent": 0,
            "eta": None,
            "result": None,
            "finished_at": None,
        }
        entry.update(kwargs)
        return dst, entry

    def test_running_poll_updates_progress_and_eta(self):
        dst, entry = self._entry()
        changed = dst.update_entry_from_poll(
            entry, {"running": True, "remaining_percent": 40}, NOW
        )
        self.assertTrue(changed)
        self.assertEqual(entry["progress_percent"], 60)
        self.assertEqual(
            datetime.fromisoformat(entry["eta"]),
            NOW + timedelta(minutes=240 * 0.4),
        )

    def test_finished_poll_marks_passed(self):
        dst, entry = self._entry()
        changed = dst.update_entry_from_poll(
            entry,
            {"running": False, "status_text": "Completed without error"},
            NOW,
        )
        self.assertTrue(changed)
        self.assertEqual(entry["status"], "passed")
        self.assertEqual(entry["progress_percent"], 100)
        self.assertIsNone(entry["eta"])
        self.assertEqual(entry["finished_at"], NOW.isoformat())

    def test_finished_poll_failure(self):
        dst, entry = self._entry()
        dst.update_entry_from_poll(
            entry,
            {"running": False, "status_text": "Completed: read failure"},
            NOW,
        )
        self.assertEqual(entry["status"], "failed")
        self.assertEqual(entry["result"], "Completed: read failure")

    def test_no_inprogress_and_no_log_row_is_aborted(self):
        dst, entry = self._entry()
        dst.update_entry_from_poll(entry, {"running": False, "status_text": None}, NOW)
        self.assertEqual(entry["status"], "aborted")

    def test_finished_entry_unchanged(self):
        dst, entry = self._entry(status="passed", finished_at=NOW.isoformat())
        self.assertFalse(
            dst.update_entry_from_poll(
                entry, {"running": True, "remaining_percent": 10}, NOW
            )
        )

    def test_update_entries_concurrent_per_disk(self):
        dst = _import_surface_module()
        state = {
            "tests": {
                "/dev/sdb": self._entry()[1],
                "/dev/sdc": self._entry()[1],
            }
        }
        polls = {
            "/dev/sdb": {"running": True, "remaining_percent": 50},
            "/dev/sdc": {"running": False, "status_text": "Completed without error"},
        }
        changed = dst.update_entries_from_polls(state, lambda p: polls[p], NOW)
        self.assertEqual(changed, 2)
        self.assertEqual(state["tests"]["/dev/sdb"]["progress_percent"], 50)
        self.assertEqual(state["tests"]["/dev/sdc"]["status"], "passed")


class TestSurfaceStatePersistence(unittest.TestCase):
    """State file round-trip, corruption handling, and module-level path."""

    def test_round_trip(self):
        dst = _import_surface_module()
        with tempfile.TemporaryDirectory() as tmp:
            dst.SURFACE_TEST_STATE_PATH = os.path.join(tmp, "surface_test_state.json")
            state = {
                "tests": {
                    "/dev/sdb": {
                        "status": "running",
                        "mode": "long",
                        "model": "WD",
                        "started_at": NOW.isoformat(),
                        "estimated_minutes": 240,
                        "progress_percent": 10,
                        "eta": None,
                        "result": None,
                        "finished_at": None,
                    }
                }
            }
            dst.save_surface_test_state(state)
            loaded = dst.load_surface_test_state()
        self.assertEqual(loaded, state)

    def test_missing_file_is_empty(self):
        dst = _import_surface_module()
        with tempfile.TemporaryDirectory() as tmp:
            dst.SURFACE_TEST_STATE_PATH = os.path.join(tmp, "nope.json")
            self.assertEqual(dst.load_surface_test_state(), {"tests": {}})

    def test_corrupt_file_is_empty(self):
        dst = _import_surface_module()
        with tempfile.TemporaryDirectory() as tmp:
            dst.SURFACE_TEST_STATE_PATH = os.path.join(tmp, "surface.json")
            with open(dst.SURFACE_TEST_STATE_PATH, "w") as f:
                f.write("{ not json")
            self.assertEqual(dst.load_surface_test_state(), {"tests": {}})

    def test_wrong_shape_is_empty(self):
        dst = _import_surface_module()
        with tempfile.TemporaryDirectory() as tmp:
            dst.SURFACE_TEST_STATE_PATH = os.path.join(tmp, "surface.json")
            with open(dst.SURFACE_TEST_STATE_PATH, "w") as f:
                f.write('["a", "b"]')
            self.assertEqual(dst.load_surface_test_state(), {"tests": {}})


class TestCellText(unittest.TestCase):
    """surface_cell_text and format_minutes rendering."""

    def test_no_entry(self):
        dst = _import_surface_module()
        self.assertEqual(dst.surface_cell_text(None), "-")

    def test_running_with_eta(self):
        dst = _import_surface_module()
        entry = {
            "status": "running",
            "progress_percent": 60,
            "eta": (NOW + timedelta(minutes=83)).isoformat(),
        }
        self.assertEqual(dst.surface_cell_text(entry, NOW), "60% (1h 23m)")

    def test_running_without_eta(self):
        dst = _import_surface_module()
        self.assertEqual(
            dst.surface_cell_text({"status": "running", "progress_percent": 5}, NOW),
            "5%",
        )

    def test_finished_labels(self):
        dst = _import_surface_module()
        for status, label in (
            ("passed", "Passed"),
            ("failed", "Failed"),
            ("aborted", "Aborted"),
            ("canceled", "Canceled"),
        ):
            self.assertEqual(dst.surface_cell_text({"status": status}), label)

    def test_format_minutes(self):
        dst = _import_surface_module()
        self.assertEqual(dst.format_minutes(0.4), "<1m")
        self.assertEqual(dst.format_minutes(45), "45m")
        self.assertEqual(dst.format_minutes(125), "2h 05m")
        self.assertEqual(dst.format_minutes(None), "")
        self.assertEqual(dst.format_minutes("junk"), "")


class TestStartCancelHelpers(unittest.TestCase):
    """start_surface_test / cancel_surface_test with a mocked app."""

    def _app(self):
        app = MagicMock()
        app.ctx.disk_repository.poll_self_test = MagicMock()
        return app

    def test_start_records_state(self):
        dst = _import_surface_module()
        with tempfile.TemporaryDirectory() as tmp:
            dst.SURFACE_TEST_STATE_PATH = os.path.join(tmp, "surface.json")
            app = self._app()
            app.ctx.disk_repository.start_self_test.return_value = True
            app.ctx.disk_repository.estimate_test_minutes.return_value = 2
            disk = SimpleNamespace(path="/dev/sdb", model="WD10EZEX")
            self.assertTrue(dst.start_surface_test(app, disk, "short"))
            state = dst.load_surface_test_state()
            entry = state["tests"]["/dev/sdb"]
            self.assertEqual(entry["status"], "running")
            self.assertEqual(entry["mode"], "short")
            self.assertEqual(entry["estimated_minutes"], 2)

    def test_start_failure_does_not_record(self):
        dst = _import_surface_module()
        with tempfile.TemporaryDirectory() as tmp:
            dst.SURFACE_TEST_STATE_PATH = os.path.join(tmp, "surface.json")
            app = self._app()
            app.ctx.disk_repository.start_self_test.return_value = False
            disk = SimpleNamespace(path="/dev/sdb", model="WD")
            self.assertFalse(dst.start_surface_test(app, disk, "short"))
            self.assertEqual(dst.load_surface_test_state(), {"tests": {}})

    def test_cancel_marks_canceled(self):
        dst = _import_surface_module()
        with tempfile.TemporaryDirectory() as tmp:
            dst.SURFACE_TEST_STATE_PATH = os.path.join(tmp, "surface.json")
            dst.save_surface_test_state(
                {
                    "tests": {
                        "/dev/sdb": {
                            "status": "running",
                            "mode": "long",
                            "model": "WD",
                            "started_at": NOW.isoformat(),
                            "estimated_minutes": 240,
                            "progress_percent": 10,
                            "eta": None,
                            "result": None,
                            "finished_at": None,
                        }
                    }
                }
            )
            app = self._app()
            app.ctx.disk_repository.abort_self_test.return_value = True
            self.assertTrue(dst.cancel_surface_test(app, "/dev/sdb"))
            self.assertEqual(dst.load_surface_test_state()["tests"]["/dev/sdb"]["status"], "canceled")


class TestSurfaceTestDialog(unittest.TestCase):
    """show_surface_test_dialog start and running/cancel modes."""

    def _app(self):
        app = MagicMock()
        app.window = MagicMock()
        return app

    def _repo(self, short_minutes=2, long_minutes=240):
        repo = MagicMock()
        repo.estimate_test_minutes.side_effect = lambda _p, mode: (
            short_minutes if mode == "short" else long_minutes
        )
        return repo

    def test_start_short(self):
        dst = _import_surface_module()
        dialogs = []

        def fake_create_dialog(title, parent, buttons, default_response=None, size=None):
            dialog = MagicMock()
            dialog.run.return_value = dst.Gtk.ResponseType.OK
            dialogs.append(dialog)
            return dialog

        radios = []

        def fake_radio(label=None):
            btn = MagicMock()
            btn.get_active.return_value = len(radios) == 0  # first radio active
            radios.append(btn)
            return btn

        disk = SimpleNamespace(path="/dev/sdb", model="WD")
        with (
            patch.object(dst, "create_dialog", side_effect=fake_create_dialog),
            patch.object(dst.Gtk, "RadioButton", side_effect=fake_radio),
            patch.object(dst.Gtk, "Label", MagicMock()),
        ):
            result = dst.show_surface_test_dialog(self._app(), disk, None, self._repo())
        self.assertEqual(result, "short")

    def test_start_long_when_second_radio_active(self):
        dst = _import_surface_module()
        dialog = MagicMock()
        dialog.run.return_value = dst.Gtk.ResponseType.OK
        radios = []

        def fake_radio(label=None):
            btn = MagicMock()
            btn.get_active.return_value = len(radios) == 1  # second radio active
            radios.append(btn)
            return btn

        disk = SimpleNamespace(path="/dev/sdb", model="WD")
        with (
            patch.object(dst, "create_dialog", return_value=dialog),
            patch.object(dst.Gtk, "RadioButton", side_effect=fake_radio),
            patch.object(dst.Gtk, "Label", MagicMock()),
        ):
            result = dst.show_surface_test_dialog(self._app(), disk, None, self._repo())
        self.assertEqual(result, "long")

    def test_cancel_response_returns_none(self):
        dst = _import_surface_module()
        dialog = MagicMock()
        dialog.run.return_value = dst.Gtk.ResponseType.CANCEL
        with (
            patch.object(dst, "create_dialog", return_value=dialog),
            patch.object(dst.Gtk, "RadioButton", MagicMock()),
            patch.object(dst.Gtk, "Label", MagicMock()),
        ):
            result = dst.show_surface_test_dialog(
                self._app(), SimpleNamespace(path="/dev/sdb", model="WD"), None, self._repo()
            )
        self.assertIsNone(result)

    def test_running_entry_abort(self):
        dst = _import_surface_module()
        dialog = MagicMock()
        dialog.run.return_value = dst._RESPONSE_CANCEL_TEST
        entry = {"status": "running", "mode": "long", "progress_percent": 40, "eta": None}
        with patch.object(dst, "create_dialog", return_value=dialog):
            result = dst.show_surface_test_dialog(
                self._app(), SimpleNamespace(path="/dev/sdb", model="WD"), entry, self._repo()
            )
        self.assertEqual(result, "abort")

    def test_running_entry_close(self):
        dst = _import_surface_module()
        dialog = MagicMock()
        dialog.run.return_value = dst.Gtk.ResponseType.CLOSE
        entry = {"status": "running", "mode": "short", "progress_percent": 40, "eta": None}
        with patch.object(dst, "create_dialog", return_value=dialog):
            result = dst.show_surface_test_dialog(
                self._app(), SimpleNamespace(path="/dev/sdb", model="WD"), entry, self._repo()
            )
        self.assertIsNone(result)


class _Iter:
    def __init__(self, index):
        self.index = index


class _FakeStore:
    """Minimal 13-column ListStore stand-in for disks_page integration tests."""

    NCOLS = 13

    def __init__(self, rows=None):
        self.rows = rows or []

    def get_iter(self, path):
        return _Iter(int(path))

    def get_iter_first(self):
        return _Iter(0) if self.rows else None

    def iter_next(self, it):
        nxt = it.index + 1
        return _Iter(nxt) if nxt < len(self.rows) else None

    def get_value(self, it, col):
        return self.rows[it.index][col]

    def set_value(self, it, col, value):
        self.rows[it.index][col] = value


def _store_row(path, disk_type, model="WD"):
    row = [""] * _FakeStore.NCOLS
    row[0] = path
    row[2] = model
    row[5] = disk_type
    return row


def _import_disks_page():
    sys.modules.pop("disks_page", None)
    with mock_gtk():
        import disks_page

        return disks_page


def _app_with_selection(store, selected_paths):
    app = MagicMock()
    app.disks_view.get_selection.return_value.get_selected_rows.return_value = (
        store,
        selected_paths,
    )
    app.disks_store = store
    # No dataset view/runner activity for these tests.
    app.disks_dataset_view = None
    app.dataset_runner = None
    return app


class TestDisksPageSurfaceIntegration(unittest.TestCase):
    """disks_page: sensitivity gating, handler, and in-place status refresh."""

    def test_sensitivity_enables_only_for_single_hdd(self):
        dp = _import_disks_page()
        btn = MagicMock()
        for rows, selected, expected in (
            ([_store_row("/dev/sdb", "HDD")], [0], True),
            ([_store_row("/dev/sdb", "SSD")], [0], False),
            ([_store_row("/dev/sdb", "HDD"), _store_row("/dev/sdc", "HDD")], [0, 1], False),
            ([], [], False),
        ):
            store = _FakeStore(rows)
            app = _app_with_selection(store, selected)
            app._disks_surface_test_btn = btn
            dp.update_disks_button_sensitivity(app)
            btn.set_sensitive.assert_called_with(expected)
            btn.reset_mock()

    def test_sensitivity_disabled_on_compute_host(self):
        dp = _import_disks_page()
        store = _FakeStore([_store_row("/dev/sdb", "HDD")])
        app = _app_with_selection(store, [0])
        app._disks_surface_test_btn = MagicMock()
        with patch.object(dp.node_config, "is_two_node", return_value=True), patch.object(
            dp.node_config, "is_storage_host", return_value=False
        ):
            dp.update_disks_button_sensitivity(app)
        app._disks_surface_test_btn.set_sensitive.assert_called_with(False)

    def test_refresh_updates_running_rows_and_saves(self):
        dp = _import_disks_page()
        dst = _import_surface_module()
        store = _FakeStore([_store_row("/dev/sdb", "HDD")])
        app = _app_with_selection(store, [])
        app.ctx.disk_repository.poll_self_test = lambda p: {
            "running": True,
            "remaining_percent": 50,
        }
        state = {
            "tests": {
                "/dev/sdb": {
                    "status": "running",
                    "mode": "long",
                    "model": "WD",
                    "started_at": NOW.isoformat(),
                    "estimated_minutes": 240,
                    "progress_percent": 0,
                    "eta": None,
                    "result": None,
                    "finished_at": None,
                }
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            dst.SURFACE_TEST_STATE_PATH = os.path.join(tmp, "surface.json")
            dst.save_surface_test_state(state)
            with patch.object(dst, "SURFACE_TEST_STATE_PATH", dst.SURFACE_TEST_STATE_PATH):
                dp.refresh_surface_test_status(app)
            saved = dst.load_surface_test_state()
        self.assertEqual(saved["tests"]["/dev/sdb"]["progress_percent"], 50)
        self.assertIsNotNone(saved["tests"]["/dev/sdb"]["eta"])

    def test_handler_starts_test_for_selected_hdd(self):
        dp = _import_disks_page()
        dst = _import_surface_module()
        store = _FakeStore([_store_row("/dev/sdb", "HDD", model="WD10EZEX")])
        app = _app_with_selection(store, [0])
        with (
            patch.object(dst, "show_surface_test_dialog", return_value="short") as dialog,
            patch.object(dst, "start_surface_test") as starter,
            patch.object(dst, "load_surface_test_state", return_value={"tests": {}}),
            patch.object(dp, "refresh_surface_test_status"),
        ):
            dp.on_disks_surface_test(app)
        dialog.assert_called_once()
        starter.assert_called_once()
        self.assertEqual(starter.call_args[0][1].path, "/dev/sdb")

    def test_handler_ignores_non_hdd(self):
        dp = _import_disks_page()
        dst = _import_surface_module()
        store = _FakeStore([_store_row("/dev/sdb", "SSD")])
        app = _app_with_selection(store, [0])
        with patch.object(dst, "show_surface_test_dialog") as dialog:
            dp.on_disks_surface_test(app)
        dialog.assert_not_called()


class TestDashboardSurfaceTask(unittest.TestCase):
    """Dashboard cancel dispatch for surface tests."""

    def test_cancel_task_surfacetest(self):
        import dashboard_page as dp

        dst = _import_surface_module()
        app = MagicMock()
        with patch.object(dst, "cancel_surface_test") as cancel:
            dp._cancel_task(app, "surfacetest:/dev/sdb")
        cancel.assert_called_once_with(app, "/dev/sdb")


if __name__ == "__main__":
    unittest.main()

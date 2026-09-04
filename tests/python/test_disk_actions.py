"""Tests for disk_actions.py — Disks tab action handlers."""

import os
import sys
import unittest
from unittest.mock import MagicMock

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import capture_logs, mock_gtk


def _import_disk_actions():
    """Import disk_actions under a fresh mocked GTK context."""
    sys.modules.pop("disk_actions", None)
    sys.modules.pop("disks_page", None)
    with mock_gtk():
        import disk_actions

        return disk_actions


def _assert_log_contains(logs, needle):
    """Assert that *needle* appears as a substring in one captured log line."""
    assert any(needle in line for line in logs), f"{needle!r} not found in {logs}"


class _Iter:
    """Truth-y iterator stand-in for _FakeListStore."""

    def __init__(self, index):
        self.index = index


class _FakeListStore:
    """Minimal ListStore stand-in for selection/value lookups."""

    def __init__(self, rows=None):
        self.rows = rows or []

    def get_iter(self, path):
        return _Iter(path if isinstance(path, int) else 0)

    def get_value(self, it, col):
        return self.rows[it.index][col]


def _disk_row(path, by_id=""):
    """Return a disk ListStore row with *path* in the name and by-id columns."""
    row = [""] * 12
    row[0] = path
    row[1] = by_id
    return row


def _make_app():
    """Return a mocked app object with an empty disk selection."""
    app = MagicMock()
    app.disks_store = _FakeListStore()
    app.disks_view.get_selection.return_value.get_selected_rows.return_value = (
        app.disks_store,
        [],
    )
    app.ctx = MagicMock()
    return app


def _select_first_disk(app, row):
    """Prime app.disks_store and selection for a single selected disk row."""
    app.disks_store = _FakeListStore([row])
    selection = app.disks_view.get_selection.return_value
    selection.get_selected_rows.return_value = (app.disks_store, [0])


class TestGetSelectedDiskPath(unittest.TestCase):
    """_get_selected_disk_path() selection and column fallback behavior."""

    def test_returns_none_when_nothing_selected(self):
        da = _import_disk_actions()
        app = _make_app()
        self.assertIsNone(da._get_selected_disk_path(app))

    def test_returns_name_column_value(self):
        da = _import_disk_actions()
        app = _make_app()
        _select_first_disk(app, _disk_row("/dev/sda", "ata-FOO"))

        self.assertEqual("/dev/sda", da._get_selected_disk_path(app))

    def test_falls_back_to_byid_when_name_empty(self):
        da = _import_disk_actions()
        app = _make_app()
        _select_first_disk(app, _disk_row("", "ata-FOO"))

        self.assertEqual("ata-FOO", da._get_selected_disk_path(app))


class TestDiskActions(unittest.TestCase):
    """Disk tab action handlers."""

    def test_smart_details_logs_output(self):
        da = _import_disk_actions()
        app = _make_app()
        app.ctx.disk_repository.smart_details.return_value = "line one\nline two\n"
        _select_first_disk(app, _disk_row("/dev/sda"))

        with capture_logs() as logs:
            da.on_disks_smart_details(app)

        _assert_log_contains(logs, "INFO: SMART details for /dev/sda:")
        _assert_log_contains(logs, "INFO: line one")
        _assert_log_contains(logs, "INFO: line two")

    def test_smart_details_warns_when_nothing_selected(self):
        da = _import_disk_actions()
        app = _make_app()
        app.disks_view.get_selection.return_value.get_selected_rows.return_value = (
            app.disks_store,
            [],
        )

        with capture_logs() as logs:
            da.on_disks_smart_details(app)

        _assert_log_contains(logs, "WARN: Select a disk to view SMART details")

    def test_smart_details_warns_when_unavailable(self):
        da = _import_disk_actions()
        app = _make_app()
        app.ctx.disk_repository.smart_details.return_value = "n/a"
        _select_first_disk(app, _disk_row("/dev/sda"))

        with capture_logs() as logs:
            da.on_disks_smart_details(app)

        _assert_log_contains(logs, "WARN: SMART details unavailable for /dev/sda")


if __name__ == "__main__":
    unittest.main()

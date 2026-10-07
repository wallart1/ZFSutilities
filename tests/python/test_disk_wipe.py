"""Tests for disk_wipe.py — wipe helpers, dialog gating, and handler flow."""

import os
import sys
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import capture_logs, mock_gtk


def _import_disk_wipe():
    """Import disk_wipe under a fresh mocked GTK context."""
    sys.modules.pop("disk_wipe", None)
    with mock_gtk(fresh=True):
        import disk_wipe

        return disk_wipe


def _import_disk_actions():
    """Import disk_actions under a fresh mocked GTK context."""
    sys.modules.pop("disk_actions", None)
    sys.modules.pop("disks_page", None)
    sys.modules.pop("disk_wipe", None)
    with mock_gtk(fresh=True):
        import disk_actions

        return disk_actions


def _disk(path="/dev/sdb", by_id="", pools=None, parent=None, disk_type="HDD"):
    """Return a DiskInfo-like object with only the fields disk_wipe reads."""
    return SimpleNamespace(
        path=path,
        by_id=by_id,
        model="MODEL-X",
        serial="SER-Y",
        size_human="8.00 TiB",
        disk_type=disk_type,
        pools=list(pools or []),
        parent_path=parent,
    )


def _assert_log_contains(logs, needle):
    assert any(needle in line for line in logs), f"{needle!r} not found in {logs}"


class _Iter:
    def __init__(self, index):
        self.index = index


class _FakeListStore:
    def __init__(self, rows=None):
        self.rows = rows or []

    def get_iter(self, path):
        return _Iter(path if isinstance(path, int) else 0)

    def get_value(self, it, col):
        return self.rows[it.index][col]


def _make_app(disk=None, importable=None):
    """Return a mocked app with one selected inventory disk."""
    app = MagicMock()
    disks = [disk] if disk is not None else []
    app._disks_inventory_cache.get.return_value = SimpleNamespace(disks=disks)
    app.ctx.zfs_repository.list_importable_pool_devices.return_value = importable or {}
    row = [""] * 12
    if disk is not None:
        row[0] = disk.path
    app.disks_store = _FakeListStore([row] if disk is not None else [])
    selection = app.disks_view.get_selection.return_value
    selection.get_selected_rows.return_value = (
        app.disks_store,
        [0] if disk is not None else [],
    )
    app.dataset_runner = MagicMock()
    app.dataset_runner.running = False
    return app


class TestTypedTarget(unittest.TestCase):
    def test_typed_target_is_kernel_basename(self):
        dw = _import_disk_wipe()
        self.assertEqual(dw.typed_target(_disk("/dev/sdb")), "sdb")
        self.assertEqual(dw.typed_target(_disk("/dev/nvme0n1p2")), "nvme0n1p2")


class TestWipeBlockReason(unittest.TestCase):
    def test_pool_member_disk_is_blocked(self):
        dw = _import_disk_wipe()
        reason = dw.wipe_block_reason(_disk("/dev/sdb", pools=["tank"]), [])
        self.assertIsNotNone(reason)
        self.assertIn("tank", reason)

    def test_partition_whose_sibling_is_a_member_is_blocked(self):
        dw = _import_disk_wipe()
        disk = _disk("/dev/sdb1", parent="/dev/sdb")
        sibling = _disk("/dev/sdb2", parent="/dev/sdb", pools=["tank"])
        parent = _disk("/dev/sdb")
        reason = dw.wipe_block_reason(disk, [disk, sibling, parent])
        self.assertIsNotNone(reason)
        self.assertIn("tank", reason)

    def test_partition_whose_parent_is_a_member_is_blocked(self):
        dw = _import_disk_wipe()
        disk = _disk("/dev/sdb1", parent="/dev/sdb")
        parent = _disk("/dev/sdb", pools=["tank"])
        self.assertIsNotNone(dw.wipe_block_reason(disk, [disk, parent]))

    def test_inactive_disk_and_partitions_are_eligible(self):
        dw = _import_disk_wipe()
        disk = _disk("/dev/sdb")
        p1 = _disk("/dev/sdb1", parent="/dev/sdb")
        p2 = _disk("/dev/sdb2", parent="/dev/sdb")
        self.assertIsNone(dw.wipe_block_reason(disk, [disk, p1, p2]))
        self.assertIsNone(dw.wipe_block_reason(p1, [disk, p1, p2]))


class TestImportablePoolFor(unittest.TestCase):
    def test_matches_by_dev_path(self):
        dw = _import_disk_wipe()
        disk = _disk("/dev/sdb")
        self.assertEqual(
            dw._importable_pool_for(disk, {"oldpool": ["/dev/sdb"]}),
            "oldpool",
        )

    def test_matches_by_id_symlink(self):
        dw = _import_disk_wipe()
        disk = _disk("/dev/sdb", by_id="ata-FOO")
        self.assertEqual(
            dw._importable_pool_for(disk, {"oldpool": ["/dev/disk/by-id/ata-FOO"]}),
            "oldpool",
        )

    def test_no_match_returns_none(self):
        dw = _import_disk_wipe()
        self.assertIsNone(dw._importable_pool_for(_disk("/dev/sdb"), {"oldpool": ["/dev/sdc"]}))


class TestWipeWarnings(unittest.TestCase):
    def test_importable_pool_destruction_is_warned(self):
        dw = _import_disk_wipe()
        disk = _disk("/dev/sdb")
        warnings = dw.wipe_warnings(disk, [disk], {"oldpool": ["/dev/sdb"]})
        self.assertTrue(
            any("oldpool" in warning and "never be imported" in warning for warning in warnings)
        )

    def test_partitions_on_whole_disk_are_warned(self):
        dw = _import_disk_wipe()
        disk = _disk("/dev/sdb")
        p1 = _disk("/dev/sdb1", parent="/dev/sdb")
        warnings = dw.wipe_warnings(disk, [disk, p1], {})
        self.assertTrue(any("1 partition(s)" in warning for warning in warnings))

    def test_partition_target_does_not_warn_about_partitions(self):
        dw = _import_disk_wipe()
        parent = _disk("/dev/sdb")
        p1 = _disk("/dev/sdb1", parent="/dev/sdb")
        warnings = dw.wipe_warnings(p1, [parent, p1], {})
        self.assertFalse(any("partition(s) on this disk" in warning for warning in warnings))

    def test_dd_and_secure_erase_disclosures_always_present(self):
        dw = _import_disk_wipe()
        for disk in (_disk("/dev/sdb"), _disk("/dev/sdb1", parent="/dev/sdb")):
            warnings = dw.wipe_warnings(disk, [disk], {})
            self.assertTrue(any("dd fallback" in warning for warning in warnings))
            self.assertTrue(any("not a secure erase" in warning for warning in warnings))


class TestBuildWipeCommand(unittest.TestCase):
    def test_command_names_script_path_and_confirmed(self):
        dw = _import_disk_wipe()
        with patch.object(dw, "resolve_local_bin", return_value="/usr/local/bin/zfswipe"):
            cmd = dw.build_wipe_command(_disk("/dev/sdb"))
        self.assertEqual(cmd, ["/usr/local/bin/zfswipe", "/dev/sdb", "--confirmed"])

    def test_command_falls_back_to_bare_name(self):
        dw = _import_disk_wipe()
        with patch.object(dw, "resolve_local_bin", return_value=None):
            cmd = dw.build_wipe_command(_disk("/dev/sdb"))
        self.assertEqual(cmd, ["zfswipe", "/dev/sdb", "--confirmed"])


@contextmanager
def _wipe_dialog(dw, response, typed_text):
    """Patch the dialog scaffolding; yield (dialog, wipe_btn, entry)."""
    dialog = MagicMock()
    wipe_btn = MagicMock()
    entry = MagicMock()
    entry.get_text.return_value = typed_text
    dialog.run.return_value = response
    dialog.add_button.return_value = wipe_btn
    with patch.object(dw, "create_scrolled_dialog", return_value=(dialog, MagicMock())):
        with patch.object(dw.Gtk, "Entry", return_value=entry):
            yield dialog, wipe_btn, entry


class TestShowWipeDialog(unittest.TestCase):
    def test_confirmed_returns_true_when_typed_exactly(self):
        dw = _import_disk_wipe()
        with _wipe_dialog(dw, dw._RESPONSE_WIPE, "sdb") as (_dialog, _btn, _entry):
            self.assertTrue(dw.show_wipe_dialog(MagicMock(), _disk("/dev/sdb"), []))

    def test_wrong_text_returns_false_even_on_wipe_response(self):
        dw = _import_disk_wipe()
        with _wipe_dialog(dw, dw._RESPONSE_WIPE, "sdc") as (_dialog, _btn, _entry):
            self.assertFalse(dw.show_wipe_dialog(MagicMock(), _disk("/dev/sdb"), []))

    def test_cancel_returns_false(self):
        dw = _import_disk_wipe()
        with _wipe_dialog(dw, dw.Gtk.ResponseType.CANCEL, "sdb") as (_dialog, _btn, _entry):
            self.assertFalse(dw.show_wipe_dialog(MagicMock(), _disk("/dev/sdb"), []))

    def test_wipe_button_starts_insensitive(self):
        dw = _import_disk_wipe()
        with _wipe_dialog(dw, dw.Gtk.ResponseType.CANCEL, "") as (_dialog, wipe_btn, entry):
            dw.show_wipe_dialog(MagicMock(), _disk("/dev/sdb"), [])
            wipe_btn.set_sensitive.assert_called_once_with(False)
            # Typing the exact name re-enables the button.
            entry.get_text.return_value = "sdb"
            entry.connect.call_args[0][1](entry)
            wipe_btn.set_sensitive.assert_called_with(True)
            # Anything else keeps it disabled.
            entry.get_text.return_value = "sdc"
            entry.connect.call_args[0][1](entry)
            wipe_btn.set_sensitive.assert_called_with(False)


class TestOnDisksWipeLabels(unittest.TestCase):
    """Handler gating and execution wiring in disk_actions."""

    def test_compute_host_refuses(self):
        da = _import_disk_actions()
        app = _make_app(_disk("/dev/sdb"))
        with (
            patch.object(da.node_config, "is_two_node", return_value=True),
            patch.object(da.node_config, "is_storage_host", return_value=False),
            capture_logs() as logs,
        ):
            da.on_disks_wipe_labels(app)
        _assert_log_contains(logs, "WARN: Disk wipe is available only on the storage host")
        app.dataset_runner.set_steps.assert_not_called()

    def test_busy_runner_refuses(self):
        da = _import_disk_actions()
        app = _make_app(_disk("/dev/sdb"))
        app.dataset_runner.running = True
        with capture_logs() as logs:
            da.on_disks_wipe_labels(app)
        _assert_log_contains(logs, "WARN: A dataset action is already running")
        app.dataset_runner.set_steps.assert_not_called()

    def test_pool_member_selection_refuses(self):
        da = _import_disk_actions()
        app = _make_app(_disk("/dev/sdb", pools=["tank"]))
        with capture_logs() as logs:
            da.on_disks_wipe_labels(app)
        _assert_log_contains(logs, "WARN: /dev/sdb cannot be wiped")
        _assert_log_contains(logs, "member of imported pool 'tank'")
        app.dataset_runner.set_steps.assert_not_called()

    def test_dialog_cancel_starts_nothing(self):
        da = _import_disk_actions()
        app = _make_app(_disk("/dev/sdb"))
        with patch.object(da, "show_wipe_dialog", return_value=False):
            da.on_disks_wipe_labels(app)
        app.dataset_runner.set_steps.assert_not_called()

    def test_confirmed_dialog_starts_runner_step_with_lock(self):
        da = _import_disk_actions()
        disk = _disk("/dev/sdb", by_id="ata-FOO")
        app = _make_app(disk)
        with (
            patch.object(da, "show_wipe_dialog", return_value=True) as dialog,
            patch.object(da, "zlm") as zlm,
            patch.object(da, "refresh_disks_page") as refresh_disks,
            patch.object(da, "update_disks_button_sensitivity") as sens,
            patch.object(da, "on_pools_refresh") as pools_refresh,
            patch.object(
                da, "build_wipe_command", return_value=["zfswipe", "/dev/sdb", "--confirmed"]
            ),
        ):
            da.on_disks_wipe_labels(app)

            zlm.acquire.assert_called_once()
            self.assertEqual(zlm.acquire.call_args[0][0], "/dev/sdb")
            dialog.assert_called_once()
            app.dataset_runner.set_steps.assert_called_once()
            step = app.dataset_runner.set_steps.call_args[0][0][0]
            self.assertEqual(step.command, ["zfswipe", "/dev/sdb", "--confirmed"])
            self.assertTrue(step.fatal)
            app.dataset_runner.start.assert_called_once()
            on_complete = app.dataset_runner.start.call_args.kwargs["on_complete"]

            on_complete(cancelled=False, rc=0)
            zlm.release.assert_called_once_with(zlm.acquire.return_value)
            app._disks_inventory_cache.invalidate.assert_called_once()
            refresh_disks.assert_called_once_with(app)
            pools_refresh.assert_called_once_with(app)
            sens.assert_called_with(app)
            with capture_logs() as logs:
                on_complete(cancelled=False, rc=0)
        _assert_log_contains(logs, "INFO: Wipe complete on /dev/sdb")

    def test_failure_rc_logs_warning(self):
        da = _import_disk_actions()
        app = _make_app(_disk("/dev/sdb"))
        with (
            patch.object(da, "show_wipe_dialog", return_value=True),
            patch.object(da, "zlm"),
            patch.object(da, "refresh_disks_page"),
            patch.object(da, "update_disks_button_sensitivity"),
            patch.object(da, "on_pools_refresh"),
        ):
            da.on_disks_wipe_labels(app)
            on_complete = app.dataset_runner.start.call_args.kwargs["on_complete"]
            with capture_logs() as logs:
                on_complete(cancelled=False, rc=8)
        _assert_log_contains(logs, "WARN: Wipe failed for /dev/sdb (rc=8)")

    def test_missing_runner_refuses(self):
        da = _import_disk_actions()
        app = _make_app(_disk("/dev/sdb"))
        app.dataset_runner = None
        with capture_logs() as logs:
            da.on_disks_wipe_labels(app)
        _assert_log_contains(logs, "WARN: Dataset runner not available")

    def test_unknown_disk_in_selection_refuses(self):
        da = _import_disk_actions()
        app = _make_app(None)
        with capture_logs() as logs:
            da.on_disks_wipe_labels(app)
        _assert_log_contains(logs, "WARN: Select a disk to wipe")


if __name__ == "__main__":
    unittest.main()

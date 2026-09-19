"""Tests for iscsi_enroll — two-node iSCSI enrollment offer."""

import contextlib
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import capture_logs, mock_gtk

ENROLL_BIN = "/usr/local/lib/zfsutilities/current/bin/enroll-iscsi-pool"


def _import_enroll():
    """Import iscsi_enroll under a fresh mocked GTK context."""
    sys.modules.pop("iscsi_enroll", None)
    with mock_gtk(fresh=True):
        import iscsi_enroll

        return iscsi_enroll


class FakeDatasetRunner:
    """BackupRunner stand-in for enrollment tests."""

    def __init__(self):
        self.running = False
        self.steps = []
        self._on_complete = None

    def set_steps(self, steps):
        self.steps = steps

    def start(self, on_complete=None):
        self.running = True
        self._on_complete = on_complete

    def finish(self, cancelled=False, rc=0):
        self.running = False
        if self._on_complete:
            self._on_complete(cancelled=cancelled, rc=rc)


def _node_config(two_node=True, storage=True, pools=()):
    """Return a MagicMock node_config with a real two-node-ish config dict."""
    ie_config = {
        "mode": "two-node" if two_node else "single-node",
        "this_host": "stor" if storage else "comp",
        "storage_host": "stor",
        "compute_host": "comp",
        "pools": set(pools),
    }
    nc = MagicMock()
    nc.load_node_config.return_value = ie_config
    nc.is_two_node.side_effect = lambda config=None: (config or ie_config)["mode"] == "two-node"
    nc.is_storage_host.side_effect = (
        lambda config=None: (config or ie_config)["this_host"]
        == (config or ie_config)["storage_host"]
    )
    return nc


def _make_app(runner=None):
    app = MagicMock()
    app.dataset_runner = runner if runner is not None else FakeDatasetRunner()
    return app


class TestDeriveTargetShort(unittest.TestCase):
    def test_lowercase_passthrough(self):
        ie = _import_enroll()
        self.assertEqual(ie.derive_target_short("fivebays"), "fivebays")

    def test_uppercase_is_lowered(self):
        ie = _import_enroll()
        self.assertEqual(ie.derive_target_short("NVME1"), "nvme1")

    def test_invalid_chars_are_stripped(self):
        ie = _import_enroll()
        self.assertEqual(ie.derive_target_short("NVME 1_SSD!"), "nvme1ssd")

    def test_dots_and_hyphens_preserved(self):
        ie = _import_enroll()
        self.assertEqual(ie.derive_target_short("My.Pool-Name"), "my.pool-name")

    def test_all_invalid_yields_empty(self):
        ie = _import_enroll()
        self.assertEqual(ie.derive_target_short("___"), "")


class TestIsIscsiManagedPool(unittest.TestCase):
    def test_single_node_is_not_managed(self):
        ie = _import_enroll()
        config = {"mode": "single-node", "pools": set()}
        self.assertFalse(ie.is_iscsi_managed_pool("pool1", config))

    def test_two_node_pool_present_is_managed(self):
        ie = _import_enroll()
        config = {"mode": "two-node", "pools": {"pool1"}}
        self.assertTrue(ie.is_iscsi_managed_pool("pool1", config))

    def test_two_node_pool_absent_is_not_managed(self):
        ie = _import_enroll()
        config = {"mode": "two-node", "pools": {"pool2"}}
        self.assertFalse(ie.is_iscsi_managed_pool("pool1", config))

    def test_explicit_config_is_used_without_loading(self):
        ie = _import_enroll()
        config = {"mode": "two-node", "pools": {"pool1"}}
        with patch.object(ie.node_config, "load_node_config") as load:
            self.assertTrue(ie.is_iscsi_managed_pool("pool1", config))
        load.assert_not_called()

    def test_config_loaded_by_default(self):
        ie = _import_enroll()
        config = {"mode": "two-node", "pools": {"pool1"}}
        with patch.object(ie.node_config, "load_node_config", return_value=config) as load:
            self.assertTrue(ie.is_iscsi_managed_pool("pool1"))
        load.assert_called_once_with()


class TestBuildEnrollCommand(unittest.TestCase):
    def test_argv_with_short_name(self):
        ie = _import_enroll()
        with patch.object(ie, "resolve_local_bin", return_value=ENROLL_BIN):
            argv = ie.build_enroll_command("newpool", "new1")
        self.assertEqual(argv, [ENROLL_BIN, "newpool", "new1"])

    def test_argv_without_short_name(self):
        ie = _import_enroll()
        with patch.object(ie, "resolve_local_bin", return_value=ENROLL_BIN):
            argv = ie.build_enroll_command("newpool")
        self.assertEqual(argv, [ENROLL_BIN, "newpool"])

    def test_none_short_name_is_omitted(self):
        ie = _import_enroll()
        with patch.object(ie, "resolve_local_bin", return_value=ENROLL_BIN):
            argv = ie.build_enroll_command("newpool", None)
        self.assertEqual(argv, [ENROLL_BIN, "newpool"])

    def test_dry_run_flag_precedes_pool_name(self):
        ie = _import_enroll()
        with patch.object(ie, "resolve_local_bin", return_value=ENROLL_BIN):
            argv = ie.build_enroll_command("newpool", "new1", dry_run=True)
        self.assertEqual(argv, [ENROLL_BIN, "--dry-run", "newpool", "new1"])

    def test_unresolved_script_falls_back_to_name(self):
        ie = _import_enroll()
        with patch.object(ie, "resolve_local_bin", return_value=None):
            argv = ie.build_enroll_command("newpool")
        self.assertEqual(argv, ["enroll-iscsi-pool", "newpool"])


class TestOfferGating(unittest.TestCase):
    def _assert_declined_silently(self, ie, nc, pool_name="newpool"):
        app = _make_app()
        with (
            patch.object(ie, "node_config", nc),
            patch.object(ie.Gtk, "MessageDialog") as dialog,
            capture_logs() as logs,
        ):
            result = ie.offer_iscsi_enrollment(app, pool_name)
        self.assertFalse(result)
        dialog.assert_not_called()
        self.assertEqual(logs, [])

    def test_single_node_declined_silently(self):
        ie = _import_enroll()
        self._assert_declined_silently(ie, _node_config(two_node=False))

    def test_compute_host_declined_silently(self):
        ie = _import_enroll()
        self._assert_declined_silently(ie, _node_config(storage=False))

    def test_already_managed_pool_declined_silently(self):
        ie = _import_enroll()
        self._assert_declined_silently(ie, _node_config(pools={"newpool"}))


class TestOfferRunnerBusy(unittest.TestCase):
    def test_runner_busy_skips_with_manual_steps(self):
        ie = _import_enroll()
        runner = FakeDatasetRunner()
        runner.running = True
        app = _make_app(runner=runner)
        with (
            patch.object(ie, "node_config", _node_config()),
            capture_logs() as logs,
        ):
            result = ie.offer_iscsi_enrollment(app, "newpool")
        self.assertFalse(result)
        self.assertEqual(runner.steps, [])
        self.assertTrue(any("skipped" in line for line in logs), logs)
        self.assertTrue(any("setup-iscsi-targets" in line for line in logs), logs)
        self.assertTrue(any("rescan-storage" in line for line in logs), logs)

    def test_runner_missing_skips_with_manual_steps(self):
        ie = _import_enroll()
        app = _make_app(runner=None)
        app.dataset_runner = None
        with (
            patch.object(ie, "node_config", _node_config()),
            capture_logs() as logs,
        ):
            result = ie.offer_iscsi_enrollment(app, "newpool")
        self.assertFalse(result)
        self.assertTrue(any("skipped" in line for line in logs), logs)
        self.assertTrue(any("rescan-storage" in line for line in logs), logs)


class TestOfferDialog(unittest.TestCase):
    def _patch_offer(self, ie, short_name, nc=None):
        """Common patchers: node config, dialog helper, refresh functions."""
        stack = contextlib.ExitStack()
        stack.enter_context(patch.object(ie, "node_config", nc or _node_config()))
        stack.enter_context(patch.object(ie, "_show_enroll_dialog", return_value=short_name))
        stack.enter_context(patch.object(ie, "update_disks_button_sensitivity"))
        stack.enter_context(patch.object(ie, "refresh_disks_page"))
        stack.enter_context(patch.object(ie, "on_pools_refresh"))
        return stack

    def test_yes_enrolls_with_entry_short_name(self):
        ie = _import_enroll()
        app = _make_app()
        done_calls = []
        with (
            self._patch_offer(ie, "custom1"),
            patch.object(ie, "resolve_local_bin", return_value=ENROLL_BIN),
            capture_logs(),
        ):
            result = ie.offer_iscsi_enrollment(app, "newpool", on_done=lambda: done_calls.append(1))
            self.assertTrue(result)
            self.assertEqual(len(app.dataset_runner.steps), 1)
            step = app.dataset_runner.steps[0]
            self.assertEqual(step.command, [ENROLL_BIN, "newpool", "custom1"])
            self.assertEqual(step.description, "Enroll pool newpool in iSCSI")
            self.assertFalse(step.is_rsync)
            self.assertFalse(step.fatal)
            app.dataset_runner.finish(rc=0)
        self.assertEqual(done_calls, [1])
        self.assertTrue(app._disks_inventory_cache.invalidate.called)

    def test_yes_uses_derived_short_name_by_default(self):
        ie = _import_enroll()
        app = _make_app()
        with (
            self._patch_offer(ie, "nvme1"),
            patch.object(ie, "resolve_local_bin", return_value=ENROLL_BIN),
            capture_logs(),
        ):
            result = ie.offer_iscsi_enrollment(app, "NVME1")
            self.assertTrue(result)
            step = app.dataset_runner.steps[0]
            self.assertEqual(step.command, [ENROLL_BIN, "NVME1", "nvme1"])

    def test_invalid_entry_falls_back_to_derived_name(self):
        ie = _import_enroll()
        app = _make_app()
        with (
            self._patch_offer(ie, "BAD NAME!"),
            patch.object(ie, "resolve_local_bin", return_value=ENROLL_BIN),
            capture_logs() as logs,
        ):
            result = ie.offer_iscsi_enrollment(app, "NVME1")
            self.assertTrue(result)
            step = app.dataset_runner.steps[0]
            self.assertEqual(step.command, [ENROLL_BIN, "NVME1", "nvme1"])
        self.assertTrue(any("WARN" in line and "falling back" in line for line in logs), logs)

    def test_no_declines_with_manual_steps(self):
        ie = _import_enroll()
        app = _make_app()
        with (
            self._patch_offer(ie, None),
            capture_logs() as logs,
        ):
            result = ie.offer_iscsi_enrollment(app, "newpool")
        self.assertFalse(result)
        self.assertEqual(app.dataset_runner.steps, [])
        self.assertTrue(any("declined" in line for line in logs), logs)
        self.assertTrue(any("setup-iscsi-targets" in line for line in logs), logs)
        self.assertTrue(any("rescan-storage" in line for line in logs), logs)

    def test_enrollment_failure_logs_warn_and_calls_on_done(self):
        ie = _import_enroll()
        app = _make_app()
        done_calls = []
        with (
            self._patch_offer(ie, "custom1"),
            patch.object(ie, "resolve_local_bin", return_value=ENROLL_BIN),
            capture_logs() as logs,
        ):
            result = ie.offer_iscsi_enrollment(app, "newpool", on_done=lambda: done_calls.append(1))
            self.assertTrue(result)
            app.dataset_runner.finish(rc=3)
        self.assertTrue(
            any("WARN" in line and "failed (rc=3)" in line for line in logs), logs
        )
        self.assertEqual(done_calls, [1])


if __name__ == "__main__":
    unittest.main()

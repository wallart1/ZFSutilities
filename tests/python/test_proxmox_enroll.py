"""Tests for proxmox_enroll — Proxmox storage enrollment offer."""

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

ENROLL_BIN = "/usr/local/lib/zfsutilities/current/bin/enroll-proxmox-pool"


def _import_enroll():
    """Import proxmox_enroll under a fresh mocked GTK context."""
    sys.modules.pop("proxmox_enroll", None)
    with mock_gtk(fresh=True):
        import proxmox_enroll

        return proxmox_enroll


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
    """Return a MagicMock node_config with a real config dict."""
    pe_config = {
        "mode": "two-node" if two_node else "single-node",
        "this_host": "stor" if storage else "comp",
        "storage_host": "stor",
        "compute_host": "comp",
        "storage_ip": "192.168.100.1",
        "pools": set(pools),
    }
    nc = MagicMock()
    nc.load_node_config.return_value = pe_config
    nc.is_two_node.side_effect = lambda config=None: (config or pe_config)["mode"] == "two-node"
    nc.is_storage_host.side_effect = lambda config=None: (
        (config or pe_config)["this_host"] == (config or pe_config)["storage_host"]
    )
    return nc


def _make_app(runner=None):
    app = MagicMock()
    app.dataset_runner = runner if runner is not None else FakeDatasetRunner()
    return app


class TestPureHelpers(unittest.TestCase):
    def test_derive_storage_id_single_node_uses_pool_name(self):
        pe = _import_enroll()
        self.assertEqual(pe.derive_storage_id("MyPool", False), "MyPool")

    def test_derive_storage_id_two_node_prefixes_short_name(self):
        pe = _import_enroll()
        self.assertEqual(pe.derive_storage_id("NVME1", True), "iscsi-nvme1")

    def test_storage_id_validation(self):
        pe = _import_enroll()
        for good in ("threeamigos", "iscsi-nvme1", "MyPool_2.0"):
            self.assertTrue(pe.storage_id_is_valid(good), good)
        for bad in ("", "bad id", "-lead", "with:colon"):
            self.assertFalse(pe.storage_id_is_valid(bad), bad)

    def test_parse_storage_ids_skips_header(self):
        pe = _import_enroll()
        status = (
            "Name Type Status Total Used\n"
            "local dir active N/A N/A\n"
            "threeamigos zfspool active 100 50\n"
        )
        self.assertEqual(pe.parse_storage_ids(status), {"local", "threeamigos"})

    def test_parse_storage_ids_empty_text(self):
        pe = _import_enroll()
        self.assertEqual(pe.parse_storage_ids(""), set())
        self.assertEqual(pe.parse_storage_ids(None), set())

    def test_pvesm_status_argv_single_node_is_local(self):
        pe = _import_enroll()
        self.assertEqual(pe.pvesm_status_argv({"mode": "single-node"}), ["pvesm", "status"])

    def test_pvesm_status_argv_two_node_uses_compute_host(self):
        pe = _import_enroll()
        argv = pe.pvesm_status_argv({"mode": "two-node", "compute_host": "comp"})
        self.assertEqual(argv[:4], ["ssh", "-o", "ConnectTimeout=5", "-o"])
        self.assertEqual(argv[-2:], ["pvesm", "status"])
        self.assertIn("root@comp", argv)

    def test_pvesm_presence_argv_single_node_is_none(self):
        pe = _import_enroll()
        self.assertIsNone(pe.pvesm_presence_argv({"mode": "single-node"}))

    def test_pvesm_presence_argv_two_node_probes_compute_host(self):
        pe = _import_enroll()
        argv = pe.pvesm_presence_argv({"mode": "two-node", "compute_host": "comp"})
        self.assertEqual(argv[-3:], ["command", "-v", "pvesm"])
        self.assertIn("root@comp", argv)

    def test_build_enroll_command_shapes(self):
        pe = _import_enroll()
        with patch.object(pe, "resolve_local_bin", return_value=ENROLL_BIN):
            self.assertEqual(pe.build_enroll_command("newpool"), [ENROLL_BIN, "newpool"])
            self.assertEqual(
                pe.build_enroll_command("newpool", "custom1"), [ENROLL_BIN, "newpool", "custom1"]
            )
            self.assertEqual(pe.build_enroll_command("newpool", None), [ENROLL_BIN, "newpool"])
            self.assertEqual(
                pe.build_enroll_command("newpool", "custom1", dry_run=True),
                [ENROLL_BIN, "--dry-run", "newpool", "custom1"],
            )

    def test_build_enroll_command_unresolved_falls_back(self):
        pe = _import_enroll()
        with patch.object(pe, "resolve_local_bin", return_value=None):
            self.assertEqual(pe.build_enroll_command("newpool"), ["enroll-proxmox-pool", "newpool"])

    def test_query_storage_ids_parses_status(self):
        pe = _import_enroll()

        def fake_run(argv):
            return 0, "Name Type Status\nmyvol zfspool active\n"

        self.assertEqual(pe.query_storage_ids({"mode": "single-node"}, run=fake_run), {"myvol"})

    def test_query_storage_ids_none_on_failure(self):
        pe = _import_enroll()
        self.assertIsNone(pe.query_storage_ids({"mode": "single-node"}, run=lambda argv: (1, "")))

    def test_proxmox_present_single_node_uses_which(self):
        pe = _import_enroll()
        with patch.object(pe.shutil, "which", return_value="/usr/sbin/pvesm"):
            self.assertTrue(pe.proxmox_present({"mode": "single-node"}))
        with patch.object(pe.shutil, "which", return_value=None):
            self.assertFalse(pe.proxmox_present({"mode": "single-node"}))

    def test_proxmox_present_two_node_probes_compute_host(self):
        pe = _import_enroll()
        config = {"mode": "two-node", "this_host": "stor", "storage_host": "stor"}
        self.assertTrue(pe.proxmox_present(config, run=lambda argv: (0, "")))
        self.assertFalse(pe.proxmox_present(config, run=lambda argv: (255, "")))

    def test_proxmox_present_two_node_compute_host_is_false(self):
        pe = _import_enroll()
        config = {"mode": "two-node", "this_host": "comp", "storage_host": "stor"}
        self.assertFalse(pe.proxmox_present(config, run=lambda argv: (0, "")))


class TestManualSteps(unittest.TestCase):
    def test_single_node_mentions_dataset_and_script(self):
        pe = _import_enroll()
        nc = _node_config(two_node=False)
        with (
            patch.object(pe, "node_config", nc),
            capture_logs() as logs,
        ):
            pe.log_manual_enrollment_steps("newpool")
        self.assertTrue(any("enroll-proxmox-pool newpool" in line for line in logs), logs)
        self.assertTrue(any("newpool/proxmox" in line for line in logs), logs)

    def test_two_node_mentions_compute_host_script(self):
        pe = _import_enroll()
        with (
            patch.object(pe, "node_config", _node_config()),
            capture_logs() as logs,
        ):
            pe.log_manual_enrollment_steps("newpool")
        self.assertTrue(any("enroll-proxmox-pool newpool" in line for line in logs), logs)

    def test_include_iscsi_lists_the_prerequisite(self):
        pe = _import_enroll()
        with capture_logs() as logs:
            pe.log_manual_enrollment_steps("newpool", include_iscsi=True)
        self.assertTrue(any("enroll-iscsi-pool newpool" in line for line in logs), logs)
        self.assertTrue(any("enroll-proxmox-pool newpool" in line for line in logs), logs)


class TestOfferGating(unittest.TestCase):
    def _offer(self, ie, nc, pool_name="newpool", app=None):
        app = app or _make_app()
        with (
            patch.object(ie, "node_config", nc),
            patch.object(ie.Gtk, "MessageDialog") as dialog,
            capture_logs() as logs,
        ):
            result = ie.offer_proxmox_enrollment(app, pool_name)
        return result, dialog, logs

    def test_compute_host_declined_silently(self):
        ie = _import_enroll()
        result, dialog, logs = self._offer(ie, _node_config(storage=False))
        self.assertFalse(result)
        dialog.assert_not_called()
        self.assertEqual(logs, [])

    def test_two_node_unenrolled_pool_skips_with_manual_chain(self):
        ie = _import_enroll()
        result, dialog, logs = self._offer(ie, _node_config(pools=set()))
        self.assertFalse(result)
        dialog.assert_not_called()
        self.assertTrue(any("skipped" in line and "not enrolled" in line for line in logs), logs)
        self.assertTrue(any("enroll-iscsi-pool newpool" in line for line in logs), logs)
        self.assertTrue(any("enroll-proxmox-pool newpool" in line for line in logs), logs)

    def test_two_node_without_pvesm_skips_with_manual_steps(self):
        ie = _import_enroll()
        app = _make_app()
        with (
            patch.object(ie, "node_config", _node_config(pools={"newpool"})),
            patch.object(ie, "proxmox_present", return_value=False),
            patch.object(ie.Gtk, "MessageDialog") as dialog,
            capture_logs() as logs,
        ):
            result = ie.offer_proxmox_enrollment(app, "newpool")
        self.assertFalse(result)
        dialog.assert_not_called()
        self.assertTrue(any("not reachable" in line and "WARN" in line for line in logs), logs)
        self.assertTrue(any("enroll-proxmox-pool newpool" in line for line in logs), logs)

    def test_single_node_without_pvesm_declined_silently(self):
        ie = _import_enroll()
        app = _make_app()
        with (
            patch.object(ie, "node_config", _node_config(two_node=False)),
            patch.object(ie, "proxmox_present", return_value=False),
            patch.object(ie.Gtk, "MessageDialog") as dialog,
            capture_logs() as logs,
        ):
            result = ie.offer_proxmox_enrollment(app, "newpool")
        self.assertFalse(result)
        dialog.assert_not_called()
        self.assertEqual(logs, [])

    def test_already_registered_skips(self):
        ie = _import_enroll()
        app = _make_app()
        with (
            patch.object(ie, "node_config", _node_config(two_node=False)),
            patch.object(ie, "proxmox_present", return_value=True),
            patch.object(ie, "query_storage_ids", return_value={"newpool", "local"}),
            patch.object(ie.Gtk, "MessageDialog") as dialog,
            capture_logs() as logs,
        ):
            result = ie.offer_proxmox_enrollment(app, "newpool")
        self.assertFalse(result)
        dialog.assert_not_called()
        self.assertTrue(any("already registered" in line for line in logs), logs)

    def test_unreadable_status_skips_with_manual_steps(self):
        ie = _import_enroll()
        app = _make_app()
        with (
            patch.object(ie, "node_config", _node_config(two_node=False)),
            patch.object(ie, "proxmox_present", return_value=True),
            patch.object(ie, "query_storage_ids", return_value=None),
            patch.object(ie.Gtk, "MessageDialog") as dialog,
            capture_logs() as logs,
        ):
            result = ie.offer_proxmox_enrollment(app, "newpool")
        self.assertFalse(result)
        dialog.assert_not_called()
        self.assertTrue(any("Could not read pvesm status" in line for line in logs), logs)
        self.assertTrue(any("enroll-proxmox-pool newpool" in line for line in logs), logs)


class TestOfferRunnerBusy(unittest.TestCase):
    def _offer(self, ie, app, two_node=True, pools=("newpool",)):
        with (
            patch.object(ie, "node_config", _node_config(two_node=two_node, pools=pools)),
            patch.object(ie, "proxmox_present", return_value=True),
            patch.object(ie, "query_storage_ids", return_value=set()),
            capture_logs() as logs,
        ):
            result = ie.offer_proxmox_enrollment(app, "newpool")
        return result, logs

    def test_runner_busy_skips_with_manual_steps(self):
        ie = _import_enroll()
        runner = FakeDatasetRunner()
        runner.running = True
        app = _make_app(runner=runner)
        result, logs = self._offer(ie, app)
        self.assertFalse(result)
        self.assertEqual(runner.steps, [])
        self.assertTrue(any("skipped" in line for line in logs), logs)
        self.assertTrue(any("enroll-proxmox-pool newpool" in line for line in logs), logs)

    def test_runner_missing_skips_with_manual_steps(self):
        ie = _import_enroll()
        app = _make_app(runner=None)
        app.dataset_runner = None
        result, logs = self._offer(ie, app)
        self.assertFalse(result)
        self.assertTrue(any("skipped" in line for line in logs), logs)


class TestOfferDialog(unittest.TestCase):
    def _patch_offer(self, ie, storage_id, two_node=False, pools=("newpool",)):
        """Common patchers: node config, dialog helper, probes, refresh."""
        stack = contextlib.ExitStack()
        stack.enter_context(
            patch.object(ie, "node_config", _node_config(two_node=two_node, pools=pools))
        )
        stack.enter_context(patch.object(ie, "_show_enroll_dialog", return_value=storage_id))
        stack.enter_context(patch.object(ie, "proxmox_present", return_value=True))
        stack.enter_context(patch.object(ie, "query_storage_ids", return_value=set()))
        stack.enter_context(patch.object(ie, "update_disks_button_sensitivity"))
        stack.enter_context(patch.object(ie, "refresh_disks_page"))
        stack.enter_context(patch.object(ie, "on_pools_refresh"))
        return stack

    def test_yes_enrolls_with_entry_storage_id(self):
        ie = _import_enroll()
        app = _make_app()
        done_calls = []
        with (
            self._patch_offer(ie, "custom1"),
            patch.object(ie, "resolve_local_bin", return_value=ENROLL_BIN),
            capture_logs(),
        ):
            result = ie.offer_proxmox_enrollment(
                app, "newpool", on_done=lambda: done_calls.append(1)
            )
            self.assertTrue(result)
            self.assertEqual(len(app.dataset_runner.steps), 1)
            step = app.dataset_runner.steps[0]
            self.assertEqual(step.command, [ENROLL_BIN, "newpool", "custom1"])
            self.assertEqual(step.description, "Enroll pool newpool in Proxmox")
            self.assertFalse(step.is_rsync)
            self.assertFalse(step.fatal)
            app.dataset_runner.finish(rc=0)
        self.assertEqual(done_calls, [1])
        self.assertTrue(app._disks_inventory_cache.invalidate.called)

    def test_yes_uses_derived_storage_id_by_default(self):
        ie = _import_enroll()
        app = _make_app()
        with (
            self._patch_offer(ie, ""),
            patch.object(ie, "resolve_local_bin", return_value=ENROLL_BIN),
            capture_logs(),
        ):
            result = ie.offer_proxmox_enrollment(app, "newpool")
            self.assertTrue(result)
            step = app.dataset_runner.steps[0]
            self.assertEqual(step.command, [ENROLL_BIN, "newpool", "newpool"])

    def test_two_node_uses_iscsi_prefixed_id(self):
        ie = _import_enroll()
        app = _make_app()
        with (
            self._patch_offer(ie, "iscsi-nvme1", two_node=True, pools=("NVME1",)),
            patch.object(ie, "resolve_local_bin", return_value=ENROLL_BIN),
            capture_logs(),
        ):
            result = ie.offer_proxmox_enrollment(app, "NVME1")
            self.assertTrue(result)
            step = app.dataset_runner.steps[0]
            self.assertEqual(step.command, [ENROLL_BIN, "NVME1", "iscsi-nvme1"])

    def test_invalid_entry_falls_back_to_derived_id(self):
        ie = _import_enroll()
        app = _make_app()
        with (
            self._patch_offer(ie, "BAD ID!"),
            patch.object(ie, "resolve_local_bin", return_value=ENROLL_BIN),
            capture_logs() as logs,
        ):
            result = ie.offer_proxmox_enrollment(app, "newpool")
            self.assertTrue(result)
            step = app.dataset_runner.steps[0]
            self.assertEqual(step.command, [ENROLL_BIN, "newpool", "newpool"])
        self.assertTrue(any("WARN" in line and "falling back" in line for line in logs), logs)

    def test_no_declines_with_manual_steps(self):
        ie = _import_enroll()
        app = _make_app()
        with (
            self._patch_offer(ie, None),
            capture_logs() as logs,
        ):
            result = ie.offer_proxmox_enrollment(app, "newpool")
        self.assertFalse(result)
        self.assertEqual(app.dataset_runner.steps, [])
        self.assertTrue(any("declined" in line for line in logs), logs)
        self.assertTrue(any("enroll-proxmox-pool newpool" in line for line in logs), logs)

    def test_enrollment_failure_logs_warn_and_calls_on_done(self):
        ie = _import_enroll()
        app = _make_app()
        done_calls = []
        with (
            self._patch_offer(ie, "custom1"),
            patch.object(ie, "resolve_local_bin", return_value=ENROLL_BIN),
            capture_logs() as logs,
        ):
            result = ie.offer_proxmox_enrollment(
                app, "newpool", on_done=lambda: done_calls.append(1)
            )
            self.assertTrue(result)
            app.dataset_runner.finish(rc=3)
        self.assertTrue(any("WARN" in line and "failed (rc=3)" in line for line in logs), logs)
        self.assertEqual(done_calls, [1])


class TestDisksAction(unittest.TestCase):
    def _make_app_with_pool(self, pool_name):
        app = _make_app()
        selector = MagicMock()
        selector.get_active_text.return_value = pool_name
        app._disks_pool_selector = selector
        return app

    def test_no_pool_selected_warns(self):
        ie = _import_enroll()
        app = self._make_app_with_pool("")
        with (
            capture_logs() as logs,
            patch.object(ie, "offer_proxmox_enrollment") as offer,
        ):
            ie.on_disks_enroll_proxmox(app)
        offer.assert_not_called()
        self.assertTrue(any("No pool selected" in line for line in logs), logs)

    def test_compute_host_warns(self):
        ie = _import_enroll()
        app = self._make_app_with_pool("newpool")
        with (
            patch.object(ie, "node_config", _node_config(storage=False)),
            capture_logs() as logs,
            patch.object(ie, "offer_proxmox_enrollment") as offer,
        ):
            ie.on_disks_enroll_proxmox(app)
        offer.assert_not_called()
        self.assertTrue(any("storage host" in line for line in logs), logs)

    def test_runner_busy_warns(self):
        ie = _import_enroll()
        runner = FakeDatasetRunner()
        runner.running = True
        app = self._make_app_with_pool("newpool")
        app.dataset_runner = runner
        with (
            patch.object(ie, "node_config", _node_config()),
            capture_logs() as logs,
            patch.object(ie, "offer_proxmox_enrollment") as offer,
        ):
            ie.on_disks_enroll_proxmox(app)
        offer.assert_not_called()
        self.assertTrue(any("already running" in line for line in logs), logs)

    def test_happy_path_offers_for_selected_pool(self):
        ie = _import_enroll()
        app = self._make_app_with_pool("newpool")
        with (
            patch.object(ie, "node_config", _node_config()),
            patch.object(ie, "offer_proxmox_enrollment") as offer,
        ):
            ie.on_disks_enroll_proxmox(app)
        offer.assert_called_once()
        self.assertEqual(offer.call_args[0][1], "newpool")


if __name__ == "__main__":
    unittest.main()

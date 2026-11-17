"""Tests for Disks page Phase 4 — pool-growth button sensitivity gating."""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import mock_gtk


def _import_disks_page():
    """Import disks_page under a fresh mocked GTK context."""
    sys.modules.pop("disks_page", None)
    with mock_gtk(fresh=True):
        import disks_page

        return disks_page


class FakeTreeSelection:
    """TreeSelection stand-in that reports a configurable path list."""

    def __init__(self, model, paths=None):
        self.model = model
        self.paths = paths or []

    def get_selected_rows(self):
        return (self.model, self.paths)

    def select_path(self, path):
        pass


class FakeTreeView:
    """TreeView stand-in with a FakeTreeSelection."""

    def __init__(self, model=None, paths=None):
        self.model = model
        self._selection = FakeTreeSelection(model, paths)

    def get_selection(self):
        return self._selection


class FakeDatasetRunner:
    """BackupRunner stand-in for dataset action tests."""

    def __init__(self):
        self.running = False
        self.steps = []


def _make_app():
    """Return a mocked app object with the six growth buttons attached.

    Each button carries a distinct stored static tooltip (what
    set_action_tooltip restores when a gating reason clears)."""
    app = MagicMock()
    app.config = {"pools": []}
    app.disks_view = FakeTreeView(None, [])
    app.disks_dataset_view = FakeTreeView(None, [])
    app.dataset_runner = FakeDatasetRunner()
    app.ctx = MagicMock()
    app.ctx.zfs_caps.supports.return_value = True
    for attr in (
        "_disks_add_vdev_btn",
        "_disks_attach_btn",
        "_disks_replace_btn",
        "_disks_detach_btn",
        "_disks_add_infra_vdev_btn",
        "_disks_migrate_pool_btn",
    ):
        btn = MagicMock()
        btn._action_tooltip = f"static tooltip for {attr}"
        setattr(app, attr, btn)
    return app


_GROWTH_TOOLTIP = "Pool growth is available only on the storage host"
_MAINT_TOOLTIP = "Pool maintenance is available only on the storage host"
_MIGRATE_TOOLTIP = "Pool migration is available only on the storage host"

_GROWTH_ATTRS = (
    "_disks_add_vdev_btn",
    "_disks_attach_btn",
    "_disks_add_infra_vdev_btn",
)
_MAINT_ATTRS = ("_disks_replace_btn", "_disks_detach_btn")
_MIGRATE_ATTRS = ("_disks_migrate_pool_btn",)


def _single_host(pgd):
    nc = MagicMock()
    nc.is_two_node.return_value = False
    return patch.object(pgd, "node_config", nc)


def _compute_host(pgd):
    nc = MagicMock()
    nc.is_two_node.return_value = True
    nc.is_storage_host.return_value = False
    return patch.object(pgd, "node_config", nc)


def _storage_host(pgd):
    nc = MagicMock()
    nc.is_two_node.return_value = True
    nc.is_storage_host.return_value = True
    return patch.object(pgd, "node_config", nc)


class TestGrowthButtonSensitivity(unittest.TestCase):
    """update_disks_button_sensitivity gates the Phase 4 growth buttons."""

    def _make(self):
        dp = _import_disks_page()
        app = _make_app()
        return dp, app

    def test_enabled_on_single_host(self):
        dp, app = self._make()
        with _single_host(dp):
            dp.update_disks_button_sensitivity(app)
        for attr in _GROWTH_ATTRS + _MAINT_ATTRS + _MIGRATE_ATTRS:
            with self.subTest(attr=attr):
                btn = getattr(app, attr)
                btn.set_sensitive.assert_called_with(True)
                btn.set_tooltip_text.assert_called_with(btn._action_tooltip)

    def test_disabled_on_two_node_compute_host(self):
        dp, app = self._make()
        with _compute_host(dp):
            dp.update_disks_button_sensitivity(app)
        for attr in _GROWTH_ATTRS:
            with self.subTest(attr=attr):
                getattr(app, attr).set_tooltip_text.assert_called_with(_GROWTH_TOOLTIP)
        for attr in _MAINT_ATTRS:
            with self.subTest(attr=attr):
                getattr(app, attr).set_tooltip_text.assert_called_with(_MAINT_TOOLTIP)
        for attr in _MIGRATE_ATTRS:
            with self.subTest(attr=attr):
                getattr(app, attr).set_tooltip_text.assert_called_with(_MIGRATE_TOOLTIP)
        for attr in _GROWTH_ATTRS + _MAINT_ATTRS + _MIGRATE_ATTRS:
            getattr(app, attr).set_sensitive.assert_called_with(False)

    def test_enabled_on_two_node_storage_host(self):
        dp, app = self._make()
        with _storage_host(dp):
            dp.update_disks_button_sensitivity(app)
        for attr in _GROWTH_ATTRS + _MAINT_ATTRS + _MIGRATE_ATTRS:
            getattr(app, attr).set_sensitive.assert_called_with(True)

    def test_stays_enabled_while_dataset_action_runs(self):
        """No global gate: buttons stay clickable while dataset actions run;
        genuine lock conflicts refuse at confirmation time instead."""
        dp, app = self._make()
        app.dataset_runner.running = True
        with _single_host(dp):
            dp.update_disks_button_sensitivity(app)
        for attr in _GROWTH_ATTRS + _MAINT_ATTRS + _MIGRATE_ATTRS:
            with self.subTest(attr=attr):
                btn = getattr(app, attr)
                btn.set_sensitive.assert_called_with(True)
                btn.set_tooltip_text.assert_called_with(btn._action_tooltip)

    def test_compute_host_tooltip_takes_precedence(self):
        dp, app = self._make()
        with _compute_host(dp):
            dp.update_disks_button_sensitivity(app)
        for attr in _GROWTH_ATTRS:
            getattr(app, attr).set_tooltip_text.assert_called_with(_GROWTH_TOOLTIP)
        for attr in _MAINT_ATTRS:
            getattr(app, attr).set_tooltip_text.assert_called_with(_MAINT_TOOLTIP)
        for attr in _MIGRATE_ATTRS:
            getattr(app, attr).set_tooltip_text.assert_called_with(_MIGRATE_TOOLTIP)

    def test_works_before_buttons_exist(self):
        """Regression: page creation runs before the action buttons exist."""
        dp = _import_disks_page()
        app = SimpleNamespace(
            disks_view=FakeTreeView(None, []),
            dataset_runner=FakeDatasetRunner(),
        )
        with _single_host(dp):
            dp.update_disks_button_sensitivity(app)

    def test_create_pool_uses_shared_compute_host_check(self):
        """The hoisted compute_host local must not change Create Pool gating."""
        dp, app = self._make()
        app._disks_create_pool_btn = MagicMock()
        with _compute_host(dp):
            dp.update_disks_button_sensitivity(app)
        app._disks_create_pool_btn.set_sensitive.assert_called_with(False)
        app._disks_create_pool_btn.set_tooltip_text.assert_called_with(
            "Pool creation is available only on the storage host"
        )


class TestProxmoxButtonSensitivity(unittest.TestCase):
    """update_disks_button_sensitivity gates the Proxmox enrollment button."""

    _ATTR = "_disks_proxmox_enroll_btn"
    _HOST_TOOLTIP = "Proxmox enrollment is available only on the storage host"

    def _make(self, pool_name="pool1"):
        dp = _import_disks_page()
        app = _make_app()
        btn = MagicMock()
        btn._action_tooltip = "static tooltip for the enroll button"
        setattr(app, self._ATTR, btn)
        selector = MagicMock()
        selector.get_active_text.return_value = pool_name
        app._disks_pool_selector = selector
        app.dataset_runner.running = False
        return dp, app, btn

    def test_enabled_with_selected_pool_on_single_host(self):
        dp, app, btn = self._make()
        with _single_host(dp):
            dp.update_disks_button_sensitivity(app)
        btn.set_sensitive.assert_called_with(True)
        btn.set_tooltip_text.assert_called_with(btn._action_tooltip)

    def test_disabled_without_selected_pool(self):
        dp, app, btn = self._make(pool_name="")
        with _single_host(dp):
            dp.update_disks_button_sensitivity(app)
        btn.set_sensitive.assert_called_with(False)
        btn.set_tooltip_text.assert_called_with("Select a pool to enroll in Proxmox")

    def test_disabled_on_two_node_compute_host(self):
        dp, app, btn = self._make()
        with _compute_host(dp):
            dp.update_disks_button_sensitivity(app)
        btn.set_sensitive.assert_called_with(False)
        btn.set_tooltip_text.assert_called_with(self._HOST_TOOLTIP)

    def test_enabled_on_two_node_storage_host(self):
        dp, app, btn = self._make()
        with _storage_host(dp):
            dp.update_disks_button_sensitivity(app)
        btn.set_sensitive.assert_called_with(True)

    def test_stays_enabled_while_dataset_action_runs(self):
        """No global gate: enrollment stays clickable while actions run."""
        dp, app, btn = self._make()
        app.dataset_runner.running = True
        with _single_host(dp):
            dp.update_disks_button_sensitivity(app)
        btn.set_sensitive.assert_called_with(True)


class FakeTopologyStore:
    """TreeStore stand-in mapping path tuples to [name, vdev_type] rows."""

    def __init__(self, rows):
        self.rows = rows

    def get_iter(self, path):
        return path

    def get_value(self, it, col):
        return self.rows[it][col]

    def iter_parent(self, it):
        return it[:-1] if len(it) > 1 else None


def _gate_topology_store():
    """Three managed pools: a mirror, a raidz1, and a single-disk stripe."""
    return FakeTopologyStore(
        {
            (0,): ["tank-mirror", "pool"],
            (0, 0): ["mirror-0", "mirror"],
            (0, 0, 0): ["/dev/sda", "disk"],
            (0, 0, 1): ["/dev/sdb", "disk"],
            (1,): ["tank-raidz", "pool"],
            (1, 0): ["raidz1-0", "raidz1"],
            (1, 0, 0): ["/dev/sdc", "disk"],
            (2,): ["tank-stripe", "pool"],
            (2, 0): ["/dev/sdd", "disk"],
        }
    )


class TestDetachButtonMirrorGate(unittest.TestCase):
    """update_disks_button_sensitivity gates Detach on mirror-vdev membership."""

    _ATTR = "_disks_detach_btn"
    _HOST_TOOLTIP = "Pool maintenance is available only on the storage host"
    _REASON = "Only mirror members can be detached"

    def _make(self, selected):
        dp = _import_disks_page()
        app = _make_app()
        app.disks_topology_view = FakeTreeView(_gate_topology_store(), selected)
        return dp, app, getattr(app, self._ATTR)

    def test_enabled_for_mirror_member(self):
        dp, app, btn = self._make([(0, 0, 0)])
        with _single_host(dp):
            dp.update_disks_button_sensitivity(app)
        btn.set_sensitive.assert_called_with(True)
        btn.set_tooltip_text.assert_called_with(btn._action_tooltip)

    def test_enabled_for_mirror_group_row(self):
        dp, app, btn = self._make([(0, 0)])
        with _single_host(dp):
            dp.update_disks_button_sensitivity(app)
        btn.set_sensitive.assert_called_with(True)
        btn.set_tooltip_text.assert_called_with(btn._action_tooltip)

    def test_disabled_for_raidz_member(self):
        dp, app, btn = self._make([(1, 0, 0)])
        with _single_host(dp):
            dp.update_disks_button_sensitivity(app)
        btn.set_sensitive.assert_called_with(False)
        btn.set_tooltip_text.assert_called_with(self._REASON)
        # The shared host-only gate is untouched: Replace stays enabled.
        app._disks_replace_btn.set_sensitive.assert_called_with(True)

    def test_disabled_for_raidz_group_row(self):
        dp, app, btn = self._make([(1, 0)])
        with _single_host(dp):
            dp.update_disks_button_sensitivity(app)
        btn.set_sensitive.assert_called_with(False)
        btn.set_tooltip_text.assert_called_with(self._REASON)

    def test_disabled_for_stripe_disk(self):
        dp, app, btn = self._make([(2, 0)])
        with _single_host(dp):
            dp.update_disks_button_sensitivity(app)
        btn.set_sensitive.assert_called_with(False)
        btn.set_tooltip_text.assert_called_with(self._REASON)

    def test_disabled_for_pool_root(self):
        dp, app, btn = self._make([(0,)])
        with _single_host(dp):
            dp.update_disks_button_sensitivity(app)
        btn.set_sensitive.assert_called_with(False)
        btn.set_tooltip_text.assert_called_with(self._REASON)

    def test_enabled_without_selection(self):
        dp, app, btn = self._make([])
        with _single_host(dp):
            dp.update_disks_button_sensitivity(app)
        btn.set_sensitive.assert_called_with(True)
        btn.set_tooltip_text.assert_called_with(btn._action_tooltip)

    def test_enabled_without_topology_view(self):
        dp, app, btn = self._make([])
        app.disks_topology_view = None
        with _single_host(dp):
            dp.update_disks_button_sensitivity(app)
        btn.set_sensitive.assert_called_with(True)
        btn.set_tooltip_text.assert_called_with(btn._action_tooltip)

    def test_compute_host_gate_wins(self):
        dp, app, btn = self._make([(0, 0, 0)])
        with _compute_host(dp):
            dp.update_disks_button_sensitivity(app)
        btn.set_sensitive.assert_called_with(False)
        btn.set_tooltip_text.assert_called_with(self._HOST_TOOLTIP)


if __name__ == "__main__":
    unittest.main()

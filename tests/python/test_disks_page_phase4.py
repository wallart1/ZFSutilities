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
    with mock_gtk():
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
    """Return a mocked app object with the five growth buttons attached."""
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
    ):
        setattr(app, attr, MagicMock())
    return app


_GROWTH_TOOLTIP = "Pool growth is available only on the storage host"
_MAINT_TOOLTIP = "Pool maintenance is available only on the storage host"
_BUSY_TOOLTIP = "A dataset action is already running"

_GROWTH_ATTRS = (
    "_disks_add_vdev_btn",
    "_disks_attach_btn",
    "_disks_add_infra_vdev_btn",
)
_MAINT_ATTRS = ("_disks_replace_btn", "_disks_detach_btn")


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
        for attr in _GROWTH_ATTRS + _MAINT_ATTRS:
            with self.subTest(attr=attr):
                btn = getattr(app, attr)
                btn.set_sensitive.assert_called_with(True)
                btn.set_tooltip_text.assert_called_with("")

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
        for attr in _GROWTH_ATTRS + _MAINT_ATTRS:
            getattr(app, attr).set_sensitive.assert_called_with(False)

    def test_enabled_on_two_node_storage_host(self):
        dp, app = self._make()
        with _storage_host(dp):
            dp.update_disks_button_sensitivity(app)
        for attr in _GROWTH_ATTRS + _MAINT_ATTRS:
            getattr(app, attr).set_sensitive.assert_called_with(True)

    def test_disabled_while_runner_busy(self):
        dp, app = self._make()
        app.dataset_runner.running = True
        with _single_host(dp):
            dp.update_disks_button_sensitivity(app)
        for attr in _GROWTH_ATTRS + _MAINT_ATTRS:
            with self.subTest(attr=attr):
                btn = getattr(app, attr)
                btn.set_sensitive.assert_called_with(False)
                btn.set_tooltip_text.assert_called_with(_BUSY_TOOLTIP)

    def test_compute_host_tooltip_takes_precedence_over_runner_busy(self):
        dp, app = self._make()
        app.dataset_runner.running = True
        with _compute_host(dp):
            dp.update_disks_button_sensitivity(app)
        for attr in _GROWTH_ATTRS:
            getattr(app, attr).set_tooltip_text.assert_called_with(_GROWTH_TOOLTIP)
        for attr in _MAINT_ATTRS:
            getattr(app, attr).set_tooltip_text.assert_called_with(_MAINT_TOOLTIP)

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


if __name__ == "__main__":
    unittest.main()

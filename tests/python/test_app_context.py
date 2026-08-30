"""Tests for app_context.py — shared operational state for GUI pages."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from app_context import AppContext
from disk_repository import DiskRepository
from zfs_capabilities import ZfsCapabilities
from zfs_repository import ZfsRepository


def _noop_zfs_caps_init(self, repository):
    """Lightweight stand-in for ZfsCapabilities.__init__ that avoids subprocess."""
    self.repository = repository
    self.version = MagicMock()


class TestAppContext(unittest.TestCase):
    """AppContext exposes config, paths, version, and repository access."""

    def test_fields_are_stored(self):
        ctx = AppContext(
            config={"pools": []},
            script_dir="/repo/python",
            parent_dir="/repo",
            version="0.45.4",
        )
        self.assertEqual(ctx.config["pools"], [])
        self.assertEqual(ctx.script_dir, "/repo/python")
        self.assertEqual(ctx.parent_dir, "/repo")
        self.assertEqual(ctx.version, "0.45.4")

    def test_is_new_install_defaults_to_false(self):
        ctx = AppContext(
            config={"pools": []},
            script_dir="/repo/python",
            parent_dir="/repo",
            version="0.45.4",
        )
        self.assertFalse(ctx.is_new_install)

    def test_is_new_install_can_be_true(self):
        ctx = AppContext(
            config={"pools": []},
            script_dir="/repo/python",
            parent_dir="/repo",
            version="0.45.4",
            is_new_install=True,
        )
        self.assertTrue(ctx.is_new_install)

    @patch.object(ZfsCapabilities, "__init__", _noop_zfs_caps_init)
    def test_default_repository_is_created(self):
        ctx = AppContext(
            config={"pools": []},
            script_dir="/repo/python",
            parent_dir="/repo",
            version="0.45.4",
        )
        self.assertIsInstance(ctx.zfs_repository, ZfsRepository)
        self.assertTrue(ctx.zfs_repository.sudo)

    @patch.object(ZfsCapabilities, "__init__", _noop_zfs_caps_init)
    def test_custom_repository_is_accepted(self):
        repo = ZfsRepository(sudo=False)
        ctx = AppContext(
            config={"pools": []},
            script_dir="/repo/python",
            parent_dir="/repo",
            version="0.45.4",
            zfs_repository=repo,
        )
        self.assertIs(ctx.zfs_repository, repo)

    @patch.object(ZfsCapabilities, "__init__", _noop_zfs_caps_init)
    def test_default_disk_repository_is_created(self):
        ctx = AppContext(
            config={"pools": []},
            script_dir="/repo/python",
            parent_dir="/repo",
            version="0.45.4",
        )
        self.assertIsInstance(ctx.disk_repository, DiskRepository)
        self.assertTrue(ctx.disk_repository.sudo)

    @patch.object(ZfsCapabilities, "__init__", _noop_zfs_caps_init)
    def test_custom_disk_repository_is_accepted(self):
        repo = DiskRepository(sudo=False)
        ctx = AppContext(
            config={"pools": []},
            script_dir="/repo/python",
            parent_dir="/repo",
            version="0.45.4",
            disk_repository=repo,
        )
        self.assertIs(ctx.disk_repository, repo)

    @patch.object(ZfsCapabilities, "__init__", _noop_zfs_caps_init)
    def test_zfs_caps_is_created_from_zfs_repository(self):
        repo = ZfsRepository(sudo=False)
        ctx = AppContext(
            config={"pools": []},
            script_dir="/repo/python",
            parent_dir="/repo",
            version="0.45.4",
            zfs_repository=repo,
        )
        self.assertIsInstance(ctx.zfs_caps, ZfsCapabilities)
        self.assertIs(ctx.zfs_caps.repository, repo)

    def test_zfs_caps_can_be_injected(self):
        mock_caps = MagicMock()
        with patch.object(ZfsCapabilities, "__init__") as mock_init:
            ctx = AppContext(
                config={"pools": []},
                script_dir="/repo/python",
                parent_dir="/repo",
                version="0.45.4",
                zfs_caps=mock_caps,
            )
            mock_init.assert_not_called()
            self.assertIs(ctx.zfs_caps, mock_caps)


if __name__ == "__main__":
    unittest.main()

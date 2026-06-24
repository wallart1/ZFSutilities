"""Tests for app_context.py — shared operational state for GUI pages."""

import os
import sys
import unittest
from unittest.mock import MagicMock

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from app_context import AppContext
from zfs_repository import ZfsRepository


class TestAppContext(unittest.TestCase):
    """AppContext exposes config, paths, version, and repository access."""

    def test_fields_are_stored(self):
        ctx = AppContext(
            config={"pools": []},
            script_dir="/repo/07 GTK + Python",
            parent_dir="/repo",
            version="0.45.4",
        )
        self.assertEqual(ctx.config["pools"], [])
        self.assertEqual(ctx.script_dir, "/repo/07 GTK + Python")
        self.assertEqual(ctx.parent_dir, "/repo")
        self.assertEqual(ctx.version, "0.45.4")

    def test_is_new_install_defaults_to_false(self):
        ctx = AppContext(
            config={"pools": []},
            script_dir="/repo/07 GTK + Python",
            parent_dir="/repo",
            version="0.45.4",
        )
        self.assertFalse(ctx.is_new_install)

    def test_is_new_install_can_be_true(self):
        ctx = AppContext(
            config={"pools": []},
            script_dir="/repo/07 GTK + Python",
            parent_dir="/repo",
            version="0.45.4",
            is_new_install=True,
        )
        self.assertTrue(ctx.is_new_install)

    def test_default_repository_is_created(self):
        ctx = AppContext(
            config={"pools": []},
            script_dir="/repo/07 GTK + Python",
            parent_dir="/repo",
            version="0.45.4",
        )
        self.assertIsInstance(ctx.zfs_repository, ZfsRepository)
        self.assertTrue(ctx.zfs_repository.sudo)

    def test_custom_repository_is_accepted(self):
        repo = ZfsRepository(sudo=False)
        ctx = AppContext(
            config={"pools": []},
            script_dir="/repo/07 GTK + Python",
            parent_dir="/repo",
            version="0.45.4",
            zfs_repository=repo,
        )
        self.assertIs(ctx.zfs_repository, repo)


if __name__ == "__main__":
    unittest.main()

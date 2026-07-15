"""Tests for path_utils.py shared path helpers."""

import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from test_support import mock_subprocess, patch_environ, REPO_ROOT

import path_utils


class TestGetScriptDir(unittest.TestCase):
    """Tests for get_script_dir()."""

    def test_get_script_dir_returns_directory(self):
        """get_script_dir returns the directory of the immediate caller."""
        result = path_utils.get_script_dir()
        self.assertEqual(result, os.path.dirname(os.path.realpath(__file__)))

    def test_get_script_dir_with_depth(self):
        """Larger depth values walk up the call stack."""
        def inner():
            return path_utils.get_script_dir(depth=2)

        result = inner()
        self.assertEqual(result, os.path.dirname(os.path.realpath(__file__)))


class TestFindScript(unittest.TestCase):
    """Tests for find_script() and resolve_local_bin()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.script_dir = os.path.join(self.tmpdir, "07 GTK + Python")
        os.makedirs(self.script_dir)
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _touch(self, *parts):
        path = os.path.join(self.tmpdir, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("#!/bin/sh\n")
        return path

    def test_find_script_in_same_directory(self):
        """Script in the same directory is found first."""
        expected = self._touch("07 GTK + Python", "profile_runner.py")
        result = path_utils.find_script(
            "profile_runner.py", script_dir=self.script_dir
        )
        self.assertEqual(result, os.path.realpath(expected))

    def test_find_script_in_parent_directory(self):
        """Script in the parent directory is found when not in same dir."""
        expected = self._touch("zfsutilities_gui.py")
        result = path_utils.find_script(
            "zfsutilities_gui.py", script_dir=self.script_dir
        )
        self.assertEqual(result, os.path.realpath(expected))

    def test_find_script_in_two_node_directory(self):
        """Script in 08 Two-node is found from repo root."""
        expected = self._touch("08 Two-node", "rescan-storage")
        result = path_utils.find_script(
            "rescan-storage", script_dir=self.script_dir
        )
        self.assertEqual(result, os.path.realpath(expected))

    def test_find_script_in_clone_support_directory(self):
        """Script in 09 ZFS clone support is found from repo root."""
        expected = self._touch("09 ZFS clone support", "retire-vm")
        result = path_utils.find_script("retire-vm", script_dir=self.script_dir)
        self.assertEqual(result, os.path.realpath(expected))

    def test_find_script_across_subdirectories(self):
        """Script in 09 ZFS clone support is found from 08 Two-node."""
        two_node_dir = os.path.join(self.tmpdir, "08 Two-node")
        os.makedirs(two_node_dir)
        expected = self._touch("09 ZFS clone support", "retire-vm")
        result = path_utils.find_script("retire-vm", script_dir=two_node_dir)
        self.assertEqual(result, os.path.realpath(expected))

    def test_find_script_missing_returns_none(self):
        """Missing scripts return None."""
        result = path_utils.find_script(
            "does-not-exist", script_dir=self.script_dir
        )
        self.assertIsNone(result)

    def test_resolve_local_bin_uses_find_script(self):
        """resolve_local_bin delegates to find_script."""
        expected = self._touch("07 GTK + Python", "profile_runner.py")
        result = path_utils.resolve_local_bin(
            "profile_runner.py", script_dir=self.script_dir
        )
        self.assertEqual(result, os.path.realpath(expected))

    def test_resolve_local_bin_missing_returns_none(self):
        """resolve_local_bin returns None for missing scripts."""
        result = path_utils.resolve_local_bin(
            "missing", script_dir=self.script_dir
        )
        self.assertIsNone(result)


class TestDeployedLayout(unittest.TestCase):
    """Tests for is_deployed_layout and profile_runner resolution."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.deployed_script_dir = os.path.join(
            self.tmpdir, "versions", "v1.0.0", "07 GTK + Python"
        )
        os.makedirs(self.deployed_script_dir)
        self.repo_script_dir = os.path.join(self.tmpdir, "07 GTK + Python")
        os.makedirs(self.repo_script_dir)
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_is_deployed_layout_true(self):
        """is_deployed_layout returns True inside versions/vX.Y.Z."""
        with patch.object(path_utils, "_DEPLOYMENT_BASE", self.tmpdir):
            self.assertTrue(path_utils.is_deployed_layout(self.deployed_script_dir))

    def test_is_deployed_layout_false(self):
        """is_deployed_layout returns False in the repo layout."""
        with patch.object(path_utils, "_DEPLOYMENT_BASE", self.tmpdir):
            self.assertFalse(path_utils.is_deployed_layout(self.repo_script_dir))

    def test_get_profile_runner_path_deployed(self):
        """Deployed layout uses current symlink path."""
        with patch.object(path_utils, "_DEPLOYMENT_BASE", self.tmpdir):
            result = path_utils.get_profile_runner_path(self.deployed_script_dir)
            expected = os.path.join(
                self.tmpdir, "current", "07 GTK + Python", "profile_runner.py"
            )
            self.assertEqual(result, expected)

    def test_get_profile_runner_path_repo(self):
        """Repo layout uses sibling path."""
        result = path_utils.get_profile_runner_path(self.repo_script_dir)
        expected = os.path.join(self.repo_script_dir, "profile_runner.py")
        self.assertEqual(result, expected)


class TestGetVersion(unittest.TestCase):
    """Tests for get_version()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.repo_dir = os.path.join(self.tmpdir, "07 GTK + Python")
        os.makedirs(self.repo_dir)
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_get_version_from_repo_root(self):
        """Version is read from the repo root VERSION file."""
        version_path = os.path.join(self.tmpdir, "VERSION")
        with open(version_path, "w") as f:
            f.write("v1.2.3\n")
        result = path_utils.get_version(self.repo_dir)
        self.assertEqual(result, "v1.2.3")

    def test_get_version_from_deployed_current(self):
        """Version is read from deployed current/VERSION."""
        current_dir = os.path.join(self.tmpdir, "current")
        os.makedirs(current_dir)
        version_path = os.path.join(current_dir, "VERSION")
        with open(version_path, "w") as f:
            f.write("v2.0.0\n")
        with patch.object(path_utils, "_DEPLOYMENT_BASE", self.tmpdir):
            result = path_utils.get_version(self.repo_dir)
            self.assertEqual(result, "v2.0.0")

    def test_get_version_defaults_to_dev(self):
        """get_version returns 'dev' when no VERSION file exists."""
        with patch.object(path_utils, "_DEPLOYMENT_BASE", os.path.join(self.tmpdir, "nowhere")):
            result = path_utils.get_version(self.repo_dir)
            self.assertEqual(result, "dev")


class TestGetDocsPath(unittest.TestCase):
    """Tests for get_docs_path()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.repo_dir = os.path.join(self.tmpdir, "07 GTK + Python")
        os.makedirs(self.repo_dir)
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_get_docs_path_repo(self):
        """Docs path is found in repo layout."""
        docs_path = os.path.join(self.tmpdir, "06 Docs", "site", "index.html")
        os.makedirs(os.path.dirname(docs_path))
        with open(docs_path, "w") as f:
            f.write("<html></html>\n")
        result = path_utils.get_docs_path(self.repo_dir)
        self.assertEqual(result, docs_path)

    def test_get_docs_path_deployed(self):
        """Docs path is found in deployed layout."""
        docs_path = os.path.join(
            self.tmpdir, "current", "06 Docs", "site", "index.html"
        )
        os.makedirs(os.path.dirname(docs_path))
        with open(docs_path, "w") as f:
            f.write("<html></html>\n")
        with patch.object(path_utils, "_DEPLOYMENT_BASE", self.tmpdir):
            result = path_utils.get_docs_path(self.repo_dir)
            self.assertEqual(result, docs_path)

    def test_get_docs_path_missing_returns_none(self):
        """get_docs_path returns None when docs are not built."""
        with patch.object(path_utils, "_DEPLOYMENT_BASE", os.path.join(self.tmpdir, "nowhere")):
            result = path_utils.get_docs_path(self.repo_dir)
            self.assertIsNone(result)


class TestRemoteResolution(unittest.TestCase):
    """Tests for remote path/version resolution."""

    def test_resolve_remote_bin_success(self):
        """resolve_remote_bin returns the resolved remote bin path."""
        with mock_subprocess() as m:
            m.set_command_handler(
                r"ssh.*realpath.*zfsutilities/current/bin",
                lambda _cmd, **_kw: subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout="/usr/local/lib/zfsutilities/versions/v1.0.0/bin\n",
                    stderr="",
                ),
            )
            result = path_utils.resolve_remote_bin("stewie")
            self.assertEqual(
                result, "/usr/local/lib/zfsutilities/versions/v1.0.0/bin"
            )

    def test_resolve_remote_bin_failure(self):
        """resolve_remote_bin returns None when SSH fails."""
        with mock_subprocess() as m:
            m.set_command_handler(
                r"ssh.*realpath.*zfsutilities/current/bin",
                lambda _cmd, **_kw: subprocess.CompletedProcess(
                    args=[], returncode=1, stdout="", stderr=""
                ),
            )
            result = path_utils.resolve_remote_bin("stewie")
            self.assertIsNone(result)

    def test_resolve_remote_bin_timeout(self):
        """resolve_remote_bin returns None on timeout."""
        with mock_subprocess() as m:

            def _raise(*_args, **_kwargs):
                raise subprocess.TimeoutExpired("ssh", 15)

            m.set_command_handler(
                r"ssh.*realpath.*zfsutilities/current/bin", _raise
            )
            result = path_utils.resolve_remote_bin("stewie")
            self.assertIsNone(result)

    def test_resolve_remote_script_success(self):
        """resolve_remote_script returns full path when bin resolves."""
        with mock_subprocess() as m:
            m.set_command_handler(
                r"ssh.*realpath.*zfsutilities/current/bin",
                lambda _cmd, **_kw: subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout="/remote/bin\n",
                    stderr="",
                ),
            )
            result = path_utils.resolve_remote_script("stewie", "repair-iscsi-luns")
            self.assertEqual(result, "/remote/bin/repair-iscsi-luns")

    def test_resolve_remote_script_fallback(self):
        """resolve_remote_script returns bare name when bin fails."""
        with mock_subprocess() as m:
            m.set_command_handler(
                r"ssh.*realpath.*zfsutilities/current/bin",
                lambda _cmd, **_kw: subprocess.CompletedProcess(
                    args=[], returncode=1, stdout="", stderr=""
                ),
            )
            result = path_utils.resolve_remote_script("stewie", "repair-iscsi-luns")
            self.assertEqual(result, "repair-iscsi-luns")

    def test_resolve_remote_version_success(self):
        """resolve_remote_version returns the remote VERSION content."""
        with mock_subprocess() as m:
            m.set_command_handler(
                r"ssh.*cat.*/VERSION",
                lambda _cmd, **_kw: subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="v3.0.0\n", stderr=""
                ),
            )
            result = path_utils.resolve_remote_version("stewie")
            self.assertEqual(result, "v3.0.0")

    def test_resolve_remote_version_failure(self):
        """resolve_remote_version returns 'unknown' on failure."""
        with mock_subprocess() as m:
            m.set_command_handler(
                r"ssh.*cat.*/VERSION",
                lambda _cmd, **_kw: subprocess.CompletedProcess(
                    args=[], returncode=1, stdout="", stderr=""
                ),
            )
            result = path_utils.resolve_remote_version("stewie")
            self.assertEqual(result, "unknown")

    def test_resolve_remote_version_timeout(self):
        """resolve_remote_version returns 'unknown' on timeout."""
        with mock_subprocess() as m:

            def _raise(*_args, **_kwargs):
                raise subprocess.TimeoutExpired("ssh", 15)

            m.set_command_handler(r"ssh.*cat.*/VERSION", _raise)
            result = path_utils.resolve_remote_version("stewie")
            self.assertEqual(result, "unknown")


class TestEnvironmentOverrides(unittest.TestCase):
    """Tests for environment-variable overrides."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.deployed_script_dir = os.path.join(
            self.tmpdir, "versions", "v9.9.9", "07 GTK + Python"
        )
        os.makedirs(self.deployed_script_dir)
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _reload_with_env(self, **env):
        """Reload path_utils with the given environment variables set."""
        import importlib

        with patch_environ(**env):
            importlib.reload(path_utils)
        self.addCleanup(importlib.reload, path_utils)

    def test_version_base_changes_deployment_base(self):
        """ZFSUTILITIES_VERSION_BASE changes the deployment base used by helpers."""
        current_dir = os.path.join(self.tmpdir, "current")
        os.makedirs(current_dir)
        version_path = os.path.join(current_dir, "VERSION")
        with open(version_path, "w") as f:
            f.write("v9.9.9\n")
        docs_path = os.path.join(current_dir, "06 Docs", "site", "index.html")
        os.makedirs(os.path.dirname(docs_path))
        with open(docs_path, "w") as f:
            f.write("<html></html>\n")

        self._reload_with_env(ZFSUTILITIES_VERSION_BASE=self.tmpdir)

        self.assertTrue(path_utils.is_deployed_layout(self.deployed_script_dir))
        self.assertEqual(path_utils.get_version(self.deployed_script_dir), "v9.9.9")
        self.assertEqual(path_utils.get_docs_path(self.deployed_script_dir), docs_path)
        self.assertEqual(
            path_utils.get_profile_runner_path(self.deployed_script_dir),
            os.path.join(
                self.tmpdir, "current", "07 GTK + Python", "profile_runner.py"
            ),
        )

    def test_remote_bin_env_override(self):
        """ZFSUTILITIES_REMOTE_BIN changes the path resolved by resolve_remote_bin."""
        custom_bin = "/opt/custom/zfsutilities/current/bin"
        self._reload_with_env(ZFSUTILITIES_REMOTE_BIN=custom_bin)

        with mock_subprocess() as m:
            m.set_command_handler(
                r"ssh.*realpath /opt/custom/zfsutilities/current/bin",
                lambda _cmd, **_kw: subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout="/opt/custom/zfsutilities/versions/v5.0.0/bin\n",
                    stderr="",
                ),
            )
            result = path_utils.resolve_remote_bin("stewie")
            self.assertEqual(
                result, "/opt/custom/zfsutilities/versions/v5.0.0/bin"
            )


if __name__ == "__main__":
    unittest.main()

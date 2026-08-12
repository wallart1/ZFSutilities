"""Tests for the centralized path-resolution module."""

import os
import tempfile
import unittest

import paths
from test_support import patch_environ


class TestPathDefaults(unittest.TestCase):
    """Verify default FHS-aligned paths."""

    def test_system_config_dir_default(self):
        self.assertEqual(paths.get_system_config_dir(), "/etc/zfsutilities")

    def test_config_dir_default(self):
        self.assertEqual(paths.get_config_dir(), "/etc/zfsutilities")

    def test_state_dir_default(self):
        self.assertEqual(paths.get_state_dir(), "/var/lib/zfsutilities")

    def test_log_dir_default(self):
        self.assertEqual(paths.get_log_dir(), "/var/log/zfsutilities")

    def test_run_dir_default(self):
        self.assertEqual(paths.get_run_dir(), "/run/zfsutilities")

    def test_lock_dir_default(self):
        self.assertEqual(paths.get_lock_dir(), "/run/lock/zfs")

    def test_config_path_default(self):
        self.assertEqual(paths.get_config_path(), "/var/lib/zfsutilities/config.json")

    def test_profiles_dir_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch_environ(ZFSUTILITIES_STATE_DIR=tmpdir):
                self.assertEqual(
                    paths.get_profiles_dir(),
                    os.path.join(tmpdir, "profiles"),
                )

    def test_history_path_default(self):
        self.assertEqual(paths.get_history_path(), "/var/lib/zfsutilities/history.json")

    def test_scrub_state_path_default(self):
        self.assertEqual(
            paths.get_scrub_state_path(),
            "/var/lib/zfsutilities/scrub_state.json",
        )

    def test_snapfile_path_default(self):
        self.assertEqual(paths.get_snapfile_path(), "/var/lib/zfsutilities/nextsnap")

    def test_offsite_snapfile_path_default(self):
        self.assertEqual(
            paths.get_offsite_snapfile_path(),
            "/var/lib/zfsutilities/nextsnap_offsite",
        )
        self.assertEqual(
            paths.get_snapfile_path("offsite"),
            "/var/lib/zfsutilities/nextsnap_offsite",
        )

    def test_run_snapfile_prefix_default(self):
        self.assertEqual(paths.get_run_snapfile_prefix(), "/run/zfsutilities/nextsnap_")

    def test_pid_file_path_default(self):
        self.assertEqual(paths.get_pid_file_path(), "/run/zfsutilities/main.pid")

    def test_session_log_dir_default(self):
        self.assertEqual(paths.get_session_log_dir(), "/var/log/zfsutilities/sessions")

    def test_log_index_path_default(self):
        self.assertEqual(
            paths.get_log_index_path(),
            "/var/log/zfsutilities/sessions/.log_index.json",
        )

    def test_cron_file_path_default(self):
        self.assertEqual(paths.get_cron_file_path(), "/etc/cron.d/zfsutilities")

    def test_profile_lock_dir_default(self):
        self.assertEqual(paths.get_profile_lock_dir(), "/run/lock/zfs/profiles")


class TestUserPaths(unittest.TestCase):
    """Verify per-user path helpers for non-root GUI components."""

    def test_user_config_dir_default(self):
        with patch_environ(XDG_CONFIG_HOME=None, HOME="/home/testuser"):
            self.assertEqual(
                paths.get_user_config_dir(),
                "/home/testuser/.config",
            )

    def test_user_config_dir_xdg(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch_environ(XDG_CONFIG_HOME=tmpdir):
                self.assertEqual(paths.get_user_config_dir(), tmpdir)

    def test_docs_viewer_state_path_default(self):
        with patch_environ(XDG_CONFIG_HOME=None, HOME="/home/testuser"):
            self.assertEqual(
                paths.get_docs_viewer_state_path(),
                "/home/testuser/.config/zfsutilities/docs_viewer_state.json",
            )

    def test_docs_viewer_state_path_xdg(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch_environ(XDG_CONFIG_HOME=tmpdir):
                self.assertEqual(
                    paths.get_docs_viewer_state_path(),
                    os.path.join(tmpdir, "zfsutilities", "docs_viewer_state.json"),
                )


class TestPathOverrides(unittest.TestCase):
    """Verify environment-variable overrides propagate to derived paths."""

    def test_state_dir_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch_environ(ZFSUTILITIES_STATE_DIR=tmpdir):
                self.assertEqual(paths.get_state_dir(), tmpdir)
                self.assertEqual(
                    paths.get_config_path(),
                    os.path.join(tmpdir, "config.json"),
                )
                self.assertEqual(
                    paths.get_profiles_dir(),
                    os.path.join(tmpdir, "profiles"),
                )

    def test_log_dir_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch_environ(ZFSUTILITIES_LOG_DIR=tmpdir):
                self.assertEqual(paths.get_log_dir(), tmpdir)
                self.assertEqual(
                    paths.get_session_log_dir(),
                    os.path.join(tmpdir, "sessions"),
                )

    def test_run_dir_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch_environ(ZFSUTILITIES_RUN_DIR=tmpdir):
                self.assertEqual(paths.get_run_dir(), tmpdir)
                self.assertEqual(
                    paths.get_pid_file_path(),
                    os.path.join(tmpdir, "main.pid"),
                )

    def test_lock_dir_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch_environ(ZFSUTILITIES_LOCK_DIR=tmpdir):
                self.assertEqual(paths.get_lock_dir(), tmpdir)
                self.assertEqual(
                    paths.get_profile_lock_dir(),
                    os.path.join(tmpdir, "profiles"),
                )

    def test_system_config_dir_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch_environ(ZFSUTILITIES_SYSTEM_CONFIG_DIR=tmpdir):
                self.assertEqual(paths.get_system_config_dir(), tmpdir)
                legacy_map = paths.get_legacy_system_config_paths()
                self.assertIn(os.path.join(tmpdir, "node.conf"), legacy_map)

    def test_cron_file_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cron_path = os.path.join(tmpdir, "zfsutilities.cron")
            with patch_environ(ZFSUTILITIES_CRON_FILE=cron_path):
                self.assertEqual(paths.get_cron_file_path(), cron_path)


class TestDirectoryCreation(unittest.TestCase):
    """Verify helpers that create directories on demand."""

    def test_profiles_dir_is_created(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            profiles_dir = os.path.join(tmpdir, "profiles")
            self.assertFalse(os.path.isdir(profiles_dir))
            with patch_environ(ZFSUTILITIES_STATE_DIR=tmpdir):
                returned = paths.get_profiles_dir()
            self.assertEqual(returned, profiles_dir)
            self.assertTrue(os.path.isdir(profiles_dir))


class TestLegacyPaths(unittest.TestCase):
    """Verify legacy path helpers return the old scattered locations."""

    def test_legacy_config_path(self):
        with patch_environ(HOME="/root"):
            self.assertEqual(paths.get_legacy_config_path(), "/root/.config/zfsutilities.json")

    def test_legacy_history_path(self):
        with patch_environ(HOME="/root"):
            self.assertEqual(
                paths.get_legacy_history_path(),
                "/root/.config/zfsutilities-history.json",
            )

    def test_legacy_profiles_dir(self):
        with patch_environ(HOME="/root"):
            self.assertEqual(paths.get_legacy_profiles_dir(), "/root/.config/profiles")

    def test_legacy_scrub_state_path(self):
        with patch_environ(HOME="/root"):
            self.assertEqual(
                paths.get_legacy_scrub_state_path(),
                "/root/.config/zfsutilities/scrub_state.json",
            )

    def test_legacy_snapfile_paths(self):
        with patch_environ(HOME="/root"):
            self.assertEqual(
                paths.get_legacy_snapfile_path(),
                "/root/.config/zfsutilities_nextsnap",
            )
            self.assertEqual(
                paths.get_legacy_snapfile_path("offsite"),
                "/root/.config/zfsutilities_offsite_nextsnap",
            )

    def test_legacy_system_config_paths(self):
        legacy_map = paths.get_legacy_system_config_paths()
        expected = {
            "/etc/zfsutilities/node.conf": "/etc/zfsutilities-node.conf",
            "/etc/zfsutilities/deploy.conf": "/etc/zfsutilities-deploy.conf",
            "/etc/zfsutilities/iscsi-encrypted-luns.conf": "/etc/iscsi-encrypted-luns.conf",
            "/etc/zfsutilities/two-node.conf": "/etc/two-node.conf",
        }
        self.assertEqual(legacy_map, expected)


if __name__ == "__main__":
    unittest.main()

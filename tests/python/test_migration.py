"""Tests for the one-time state-file migration helper."""

import os
import tempfile
import unittest

# Import migration after test_support has disabled automatic migration.
import migration
import paths
from test_support import patch_environ


class TestMigration(unittest.TestCase):
    """Verify state files are migrated from legacy to new paths."""

    def test_migrate_config_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = os.path.join(tmpdir, "state")
            home_dir = os.path.join(tmpdir, "root")
            with patch_environ(
                ZFSUTILITIES_STATE_DIR=state_dir,
                ZFSUTILITIES_DISABLE_MIGRATION=None,
                HOME=home_dir,
            ):
                legacy = paths.get_legacy_config_path()
                new = paths.get_config_path()
                os.makedirs(os.path.dirname(legacy), exist_ok=True)
                with open(legacy, "w") as f:
                    f.write('{"pools": []}')

                migration.run_migration()

                self.assertTrue(os.path.islink(legacy))
                self.assertTrue(os.path.isfile(new))
                with open(new) as f:
                    self.assertEqual(f.read(), '{"pools": []}')

    def test_migrate_history_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = os.path.join(tmpdir, "state")
            home_dir = os.path.join(tmpdir, "root")
            with patch_environ(
                ZFSUTILITIES_STATE_DIR=state_dir,
                ZFSUTILITIES_DISABLE_MIGRATION=None,
                HOME=home_dir,
            ):
                legacy = paths.get_legacy_history_path()
                new = paths.get_history_path()
                os.makedirs(os.path.dirname(legacy), exist_ok=True)
                with open(legacy, "w") as f:
                    f.write("[]")

                migration.run_migration()

                self.assertTrue(os.path.islink(legacy))
                self.assertTrue(os.path.isfile(new))

    def test_migrate_profiles_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = os.path.join(tmpdir, "state")
            home_dir = os.path.join(tmpdir, "root")
            with patch_environ(
                ZFSUTILITIES_STATE_DIR=state_dir,
                ZFSUTILITIES_DISABLE_MIGRATION=None,
                HOME=home_dir,
            ):
                legacy = paths.get_legacy_profiles_dir()
                new = os.path.join(state_dir, "profiles")
                os.makedirs(legacy, exist_ok=True)
                with open(os.path.join(legacy, "daily.json"), "w") as f:
                    f.write("{}")

                migration.run_migration()

                self.assertTrue(os.path.islink(legacy))
                self.assertTrue(os.path.isdir(new))
                self.assertTrue(os.path.isfile(os.path.join(new, "daily.json")))

    def test_migrate_scrub_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = os.path.join(tmpdir, "state")
            home_dir = os.path.join(tmpdir, "root")
            with patch_environ(
                ZFSUTILITIES_STATE_DIR=state_dir,
                ZFSUTILITIES_DISABLE_MIGRATION=None,
                HOME=home_dir,
            ):
                legacy = paths.get_legacy_scrub_state_path()
                new = paths.get_scrub_state_path()
                os.makedirs(os.path.dirname(legacy), exist_ok=True)
                with open(legacy, "w") as f:
                    f.write('{"pending": []}')

                migration.run_migration()

                self.assertTrue(os.path.islink(legacy))
                self.assertTrue(os.path.isfile(new))

    def test_migrate_snapfiles(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = os.path.join(tmpdir, "state")
            home_dir = os.path.join(tmpdir, "root")
            with patch_environ(
                ZFSUTILITIES_STATE_DIR=state_dir,
                ZFSUTILITIES_DISABLE_MIGRATION=None,
                HOME=home_dir,
            ):
                legacy = paths.get_legacy_snapfile_path()
                legacy_offsite = paths.get_legacy_snapfile_path("offsite")
                new = paths.get_snapfile_path()
                new_offsite = paths.get_snapfile_path("offsite")
                os.makedirs(os.path.dirname(legacy), exist_ok=True)
                with open(legacy, "w") as f:
                    f.write("@dailybackup-2025-01-01T00:00-05:00-d")
                with open(legacy_offsite, "w") as f:
                    f.write("@offsite-2025-01-01T00:00-05:00-s")

                migration.run_migration()

                self.assertTrue(os.path.islink(legacy))
                self.assertTrue(os.path.islink(legacy_offsite))
                self.assertTrue(os.path.isfile(new))
                self.assertTrue(os.path.isfile(new_offsite))

    def test_sentinel_prevents_rerun(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = os.path.join(tmpdir, "state")
            home_dir = os.path.join(tmpdir, "root")
            with patch_environ(
                ZFSUTILITIES_STATE_DIR=state_dir,
                ZFSUTILITIES_DISABLE_MIGRATION=None,
                HOME=home_dir,
            ):
                legacy = paths.get_legacy_config_path()
                new = paths.get_config_path()
                os.makedirs(os.path.dirname(legacy), exist_ok=True)
                with open(legacy, "w") as f:
                    f.write("{}")

                migration.run_migration()
                self.assertTrue(os.path.islink(legacy))

                # Remove the symlink and recreate the legacy file.
                os.remove(legacy)
                with open(legacy, "w") as f:
                    f.write("second")

                migration.run_migration()

                # Sentinel should prevent a second migration, so the recreated
                # legacy file remains and the previously migrated new file is
                # still present.
                self.assertTrue(os.path.isfile(legacy))
                self.assertFalse(os.path.islink(legacy))
                self.assertTrue(os.path.isfile(new))

    def test_disabled_by_environment_variable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = os.path.join(tmpdir, "state")
            home_dir = os.path.join(tmpdir, "root")
            with patch_environ(
                ZFSUTILITIES_STATE_DIR=state_dir,
                ZFSUTILITIES_DISABLE_MIGRATION="1",
                HOME=home_dir,
            ):
                legacy = paths.get_legacy_config_path()
                new = paths.get_config_path()
                os.makedirs(os.path.dirname(legacy), exist_ok=True)
                with open(legacy, "w") as f:
                    f.write("{}")

                migration.run_migration()

                self.assertTrue(os.path.isfile(legacy))
                self.assertFalse(os.path.exists(new))

    def test_conflict_backs_up_legacy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = os.path.join(tmpdir, "state")
            home_dir = os.path.join(tmpdir, "root")
            with patch_environ(
                ZFSUTILITIES_STATE_DIR=state_dir,
                ZFSUTILITIES_DISABLE_MIGRATION=None,
                HOME=home_dir,
            ):
                legacy = paths.get_legacy_config_path()
                new = paths.get_config_path()
                os.makedirs(os.path.dirname(legacy), exist_ok=True)
                with open(legacy, "w") as f:
                    f.write("legacy")
                os.makedirs(os.path.dirname(new), exist_ok=True)
                with open(new, "w") as f:
                    f.write("new")

                migration.run_migration()

                self.assertFalse(os.path.islink(legacy))
                self.assertFalse(os.path.exists(legacy))
                self.assertTrue(os.path.isfile(new))
                with open(new) as f:
                    self.assertEqual(f.read(), "new")

                # A timestamped backup should exist.
                backup_found = False
                for name in os.listdir(os.path.dirname(legacy)):
                    if name.startswith(os.path.basename(legacy)) and name.endswith(".bak"):
                        backup_found = True
                        with open(os.path.join(os.path.dirname(legacy), name)) as f:
                            self.assertEqual(f.read(), "legacy")
                        break
                self.assertTrue(backup_found)


if __name__ == "__main__":
    unittest.main()

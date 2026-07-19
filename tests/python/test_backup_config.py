"""Tests for backup_config.py — compatibility shim re-exports."""

import json
import os
import unittest

from test_support import temp_config_dir, write_config, read_config, capture_logs, patch_environ

import backup_config


class TestLoadConfig(unittest.TestCase):

    def test_load_config_returns_defaults_when_missing(self):
        with temp_config_dir():
            config = backup_config.load_config()
            self.assertIn("backup", config)
            self.assertEqual(config["config_version"], backup_config.CONFIG_VERSION)
            self.assertEqual(config["backup"]["variables"]["label"], "dailybackup")

    def test_load_config_reads_existing_file(self):
        with temp_config_dir():
            write_config({"backup": {"variables": {"label": "custom"}}, "config_version": backup_config.CONFIG_VERSION})
            config = backup_config.load_config()
            self.assertEqual(config["backup"]["variables"]["label"], "custom")

    def test_load_config_fixes_missing_config_version(self):
        with temp_config_dir():
            write_config({"backup": {}})
            config = backup_config.load_config()
            self.assertEqual(config.get("config_version"), backup_config.CONFIG_VERSION)

    def test_load_config_ignores_invalid_json(self):
        with temp_config_dir() as tmpdir:
            path = os.path.join(tmpdir, "zfsutilities.json")
            with open(path, "w") as f:
                f.write("not json")
            config = backup_config.load_config()
            self.assertIn("backup", config)


class TestSaveConfig(unittest.TestCase):

    def test_save_config_writes_file(self):
        with temp_config_dir():
            backup_config.save_config({"foo": "bar"})
            with open(backup_config.CONFIG_PATH) as f:
                data = json.load(f)
            self.assertEqual(data["foo"], "bar")


class TestSnapshotNameGeneration(unittest.TestCase):

    def test_daily_bucket_weekday(self):
        with patch_environ():
            name = backup_config._build_snapshot_name("dailybackup")
            self.assertIn("@dailybackup-", name)

    def test_offsite_bucket_is_s(self):
        with patch_environ():
            name = backup_config._build_snapshot_name("offsite")
            self.assertTrue(name.endswith("-s"))

    def test_snapfile_roundtrip(self):
        with temp_config_dir():
            backup_config.save_snapshot_name("@test-2025-01-01T00:00-04:00-d")
            self.assertEqual(backup_config._read_snapfile(backup_config.SNAPFILE), "@test-2025-01-01T00:00-04:00-d")
            backup_config.remove_snapfile()
            self.assertIsNone(backup_config._read_snapfile(backup_config.SNAPFILE))

    def test_generate_snapshot_name_saves_file(self):
        with temp_config_dir():
            name = backup_config.generate_snapshot_name("dailybackup")
            self.assertTrue(name.startswith("@dailybackup-"))
            self.assertEqual(backup_config._read_snapfile(backup_config.SNAPFILE), name)


class TestShimReExports(unittest.TestCase):
    """backup_config.py re-exports the public API from the split modules."""

    def test_log_msg_re_export_works(self):
        with capture_logs() as logs:
            backup_config.log_msg("INFO: shim test")
        self.assertTrue(any("shim test" in m for m in logs))

    def test_config_version_matches_core(self):
        import config_migrations
        self.assertEqual(backup_config.CONFIG_VERSION, config_migrations.CONFIG_VERSION)


class TestMsgLevelHelpers(unittest.TestCase):

    def test_get_msg_level_defaults_to_info(self):
        config = {}
        self.assertEqual(backup_config.get_msg_level(config), "INFO")

    def test_save_msg_level_rejects_invalid(self):
        config = {}
        with self.assertRaises(ValueError):
            backup_config.save_msg_level(config, "BOGUS")


class TestUiState(unittest.TestCase):

    def test_get_ui_state_returns_defaults(self):
        config = {}
        state = backup_config.get_ui_state(config)
        self.assertIn("main_window", state)
        self.assertFalse(state["main_window"]["maximized"])

    def test_save_ui_state_merges(self):
        with temp_config_dir():
            config = {}
            backup_config.save_ui_state(config, {"main_window": {"width": 800}})
            self.assertEqual(config["ui_state"]["main_window"]["width"], 800)


class TestLogRetention(unittest.TestCase):

    def test_get_log_retention_days_default(self):
        config = {}
        self.assertEqual(backup_config.get_log_retention_days(config), 30)

    def test_save_log_retention_days(self):
        with temp_config_dir():
            config = {}
            backup_config.save_log_retention_days(config, 7)
            self.assertEqual(config["log_retention_days"], 7)

    def test_prune_old_logs_removes_stale(self):
        import tempfile
        import time
        with tempfile.TemporaryDirectory() as tmpdir:
            old_file = os.path.join(tmpdir, "old.log")
            new_file = os.path.join(tmpdir, "new.log")
            with open(old_file, "w") as f:
                f.write("old")
            with open(new_file, "w") as f:
                f.write("new")
            # Set old file mtime to 10 days ago
            os.utime(old_file, (time.time() - 864000, time.time() - 864000))
            # Monkey-patch SESSION_LOG_DIR
            import config_core
            orig_dir = config_core.SESSION_LOG_DIR
            backup_config.SESSION_LOG_DIR = tmpdir
            config_core.SESSION_LOG_DIR = tmpdir
            try:
                removed = backup_config.prune_old_logs(5)
                self.assertEqual(removed, 1)
                self.assertFalse(os.path.exists(old_file))
                self.assertTrue(os.path.exists(new_file))
            finally:
                backup_config.SESSION_LOG_DIR = orig_dir
                config_core.SESSION_LOG_DIR = orig_dir


class TestBackupConfig(unittest.TestCase):

    def test_get_backup_config_merges_defaults(self):
        config = {"backup": {"variables": {"label": "special"}}}
        backup = backup_config.get_backup_config(config)
        self.assertEqual(backup["variables"]["label"], "special")
        self.assertEqual(backup["variables"]["autoresume"], "Y")
        self.assertTrue(backup["pull_steps_active"])

    def test_get_backup_config_preserves_pull_steps_active(self):
        config = {"backup": {"pull_steps_active": False}}
        backup = backup_config.get_backup_config(config)
        self.assertFalse(backup["pull_steps_active"])

    def test_save_backup_config(self):
        with temp_config_dir():
            config = {}
            backup_config.save_backup_config(config, {"foo": "bar"})
            self.assertEqual(config["backup"]["foo"], "bar")


class TestOffsiteConfig(unittest.TestCase):

    def test_get_offsite_config_merges_defaults(self):
        config = {}
        offsite = backup_config.get_offsite_config(config)
        self.assertEqual(offsite["variables"]["applyholds"], "Y")

    def test_generate_offsite_snapshot_name(self):
        with temp_config_dir():
            name = backup_config.generate_offsite_snapshot_name()
            self.assertTrue(name.startswith("@offsite-"))
            self.assertTrue(name.endswith("-s"))
            self.assertEqual(backup_config._read_snapfile(backup_config.OFFSITE_SNAPFILE), name)


class TestRestoreConfig(unittest.TestCase):

    def test_get_restore_config_defaults(self):
        config = {}
        restore = backup_config.get_restore_config(config)
        self.assertTrue(restore["do_part1"])
        self.assertTrue(restore["do_part2"])
        self.assertFalse(restore["auto_dest"])


class TestPoolsAndCheckagainst(unittest.TestCase):

    def test_get_pools_creates_empty_list(self):
        config = {}
        self.assertEqual(backup_config.get_pools(config), [])

    def test_save_pools(self):
        with temp_config_dir():
            config = {}
            backup_config.save_pools(config, ["tank", "pool2"])
            self.assertEqual(
                config["pools"],
                [
                    {"name": "tank", "offsite_candidate": False},
                    {"name": "pool2", "offsite_candidate": False},
                ],
            )

    def test_get_checkagainst_creates_nested_defaults(self):
        config = {}
        data = backup_config.get_checkagainst(config)
        self.assertTrue(data["backup_derived_active"])
        self.assertTrue(data["offsite_derived_active"])
        self.assertEqual(data["backup_derived"], [])
        self.assertEqual(data["offsite_derived"], [])
        self.assertEqual(data["user_entries"], [])


class TestRetentionConfig(unittest.TestCase):

    def test_get_all_retention_creates_default(self):
        config = {}
        retention = backup_config.get_all_retention(config)
        self.assertIn("default", retention)
        self.assertEqual(retention["default"][0]["name"], "d")

    def test_get_retention_uses_pool_specific(self):
        config = {"retention": {"tank": [{"name": "d", "retain": 7, "minage": 0}]}}
        buckets = backup_config.get_retention(config, "tank")
        self.assertEqual(buckets[0]["retain"], 7)

    def test_get_retention_falls_back_to_default(self):
        config = {}
        buckets = backup_config.get_retention(config, "tank")
        self.assertEqual(buckets[0]["retain"], 3)

    def test_save_retention(self):
        with temp_config_dir():
            config = {}
            backup_config.save_retention(config, "tank", [{"name": "d", "retain": 5, "minage": 0}])
            self.assertEqual(config["retention"]["tank"][0]["retain"], 5)


class TestDeepCopy(unittest.TestCase):

    def test_deep_copy_dict(self):
        original = {"a": [1, 2, {"b": 3}]}
        copy = backup_config._deep_copy(original)
        self.assertEqual(original, copy)
        copy["a"][0] = 99
        self.assertEqual(original["a"][0], 1)


if __name__ == "__main__":
    unittest.main()

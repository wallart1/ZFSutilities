"""Tests for feature_config.py — per-feature getters/setters and snapshot naming."""

import os
import sys
import threading
import time
import unittest

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import temp_config_dir, patch_environ

import feature_config


class TestBackupConfig(unittest.TestCase):
    """Backup tab configuration defaults and save."""

    def test_get_backup_config_merges_defaults(self):
        config = {"backup": {"variables": {"label": "special"}}}
        backup = feature_config.get_backup_config(config)
        self.assertEqual(backup["variables"]["label"], "special")
        self.assertEqual(backup["variables"]["autoresume"], "Y")
        self.assertIn("pull_steps", backup)
        self.assertTrue(backup["pull_steps_active"])

    def test_save_backup_config(self):
        with temp_config_dir():
            config = {}
            feature_config.save_backup_config(config, {"foo": "bar"})
            self.assertEqual(config["backup"]["foo"], "bar")


class TestOffsiteConfig(unittest.TestCase):
    """Offsite tab configuration defaults and snapshot naming."""

    def test_get_offsite_config_merges_defaults(self):
        config = {}
        offsite = feature_config.get_offsite_config(config)
        self.assertEqual(offsite["variables"]["applyholds"], "Y")

    def test_generate_offsite_snapshot_name(self):
        with temp_config_dir():
            name = feature_config.generate_offsite_snapshot_name()
            self.assertTrue(name.startswith("@offsite-"))
            self.assertTrue(name.endswith("-s"))
            self.assertEqual(feature_config._read_snapfile(feature_config.OFFSITE_SNAPFILE), name)


class TestRestoreConfig(unittest.TestCase):
    """Restore tab configuration defaults."""

    def test_get_restore_config_defaults(self):
        config = {}
        restore = feature_config.get_restore_config(config)
        self.assertTrue(restore["do_part1"])
        self.assertTrue(restore["do_part2"])
        self.assertFalse(restore["auto_dest"])


class TestPoolsAndCheckagainst(unittest.TestCase):
    """Pools list and checkagainst list helpers."""

    def test_get_pools_creates_empty_list(self):
        config = {}
        self.assertEqual(feature_config.get_pools(config), [])

    def test_save_pools(self):
        with temp_config_dir():
            config = {}
            feature_config.save_pools(config, ["tank", "pool2"])
            self.assertEqual(
                config["pools"],
                [
                    {"name": "tank", "offsite_candidate": False},
                    {"name": "pool2", "offsite_candidate": False},
                ],
            )

    def test_get_pools_normalizes_legacy_strings(self):
        config = {"pools": ["tank", "pool2"]}
        pools = feature_config.get_pools(config)
        self.assertEqual(
            pools,
            [
                {"name": "tank", "offsite_candidate": False},
                {"name": "pool2", "offsite_candidate": False},
            ],
        )

    def test_get_pool_names(self):
        config = {
            "pools": [
                {"name": "tank", "offsite_candidate": False},
                {"name": "z40tb", "offsite_candidate": True},
            ]
        }
        self.assertEqual(feature_config.get_pool_names(config), ["tank", "z40tb"])

    def test_get_offsite_candidate_names(self):
        config = {
            "pools": [
                {"name": "tank", "offsite_candidate": False},
                {"name": "z40tb", "offsite_candidate": True},
            ]
        }
        self.assertEqual(feature_config.get_offsite_candidate_names(config), ["z40tb"])

    def test_save_pools_syncs_offsite_pools(self):
        with temp_config_dir():
            config = {}
            feature_config.save_pools(
                config,
                [
                    {"name": "tank", "offsite_candidate": False},
                    {"name": "z40tb", "offsite_candidate": True},
                ],
            )
            self.assertEqual(config["offsite"]["offsite_pools"], ["z40tb"])

    def test_get_checkagainst_creates_empty_list(self):
        config = {}
        self.assertEqual(feature_config.get_checkagainst(config), [])


class TestArchivePath(unittest.TestCase):
    """Archive path helper."""

    def test_get_archive_path_default(self):
        config = {}
        self.assertEqual(feature_config.get_archive_path(config), "")

    def test_save_archive_path(self):
        with temp_config_dir():
            config = {}
            feature_config.save_archive_path(config, "/archive")
            self.assertEqual(config["archive_path"], "/archive")


class TestRetentionConfig(unittest.TestCase):
    """Retention policy helpers."""

    def test_get_all_retention_creates_default(self):
        config = {}
        retention = feature_config.get_all_retention(config)
        self.assertIn("default", retention)
        self.assertEqual(retention["default"][0]["name"], "d")

    def test_get_retention_uses_pool_specific(self):
        config = {"retention": {"tank": [{"name": "d", "retain": 7, "minage": 0}]}}
        buckets = feature_config.get_retention(config, "tank")
        self.assertEqual(buckets[0]["retain"], 7)

    def test_get_retention_falls_back_to_default(self):
        config = {}
        buckets = feature_config.get_retention(config, "tank")
        self.assertEqual(buckets[0]["retain"], 3)

    def test_save_retention(self):
        with temp_config_dir():
            config = {}
            feature_config.save_retention(config, "tank", [{"name": "d", "retain": 5, "minage": 0}])
            self.assertEqual(config["retention"]["tank"][0]["retain"], 5)


class TestPruneLabelConfig(unittest.TestCase):
    """Global retention prune label helpers."""

    def test_get_prune_label_default(self):
        config = {}
        self.assertEqual(feature_config.get_prune_label(config), "dailybackup")

    def test_get_prune_label_existing(self):
        config = {"prune_label": "weekly"}
        self.assertEqual(feature_config.get_prune_label(config), "weekly")

    def test_save_prune_label(self):
        with temp_config_dir():
            config = {}
            feature_config.save_prune_label(config, "monthly")
            self.assertEqual(config["prune_label"], "monthly")


class TestSnapshotNameGeneration(unittest.TestCase):
    """Snapshot name generation and snapfile I/O."""

    def test_daily_bucket_weekday(self):
        with patch_environ():
            name = feature_config._build_snapshot_name("dailybackup")
            self.assertIn("@dailybackup-", name)

    def test_offsite_bucket_is_s(self):
        with patch_environ():
            name = feature_config._build_snapshot_name("offsite")
            self.assertTrue(name.endswith("-s"))

    def test_snapfile_roundtrip(self):
        with temp_config_dir():
            feature_config._write_snapfile(feature_config.SNAPFILE, "@test-2025-01-01T00:00-04:00-d")
            self.assertEqual(feature_config._read_snapfile(feature_config.SNAPFILE), "@test-2025-01-01T00:00-04:00-d")
            feature_config._remove_snapfile(feature_config.SNAPFILE)
            self.assertIsNone(feature_config._read_snapfile(feature_config.SNAPFILE))

    def test_generate_snapshot_name_saves_file(self):
        with temp_config_dir():
            name = feature_config.generate_snapshot_name("dailybackup")
            self.assertTrue(name.startswith("@dailybackup-"))
            self.assertEqual(feature_config._read_snapfile(feature_config.SNAPFILE), name)

    def test_generate_snapshot_name_records_reservation(self):
        with temp_config_dir():
            name = feature_config.generate_snapshot_name("dailybackup")
            self.assertTrue(feature_config._is_snapshot_name_reserved(name))
            reservations = feature_config._load_reservations()
            self.assertIn(name, reservations)

    def test_generate_offsite_snapshot_name_records_reservation(self):
        with temp_config_dir():
            name = feature_config.generate_offsite_snapshot_name()
            self.assertTrue(name.startswith("@offsite-"))
            self.assertTrue(feature_config._is_snapshot_name_reserved(name))

    def test_reservation_expires_after_one_minute(self):
        with temp_config_dir():
            name = "@dailybackup-2025-01-01T00:00-04:00-d"
            feature_config._reserve_snapshot_name(name)
            self.assertTrue(feature_config._is_snapshot_name_reserved(name))
            # Forge a stale timestamp.
            feature_config._save_reservations({name: int(time.time()) - 120})
            self.assertFalse(feature_config._is_snapshot_name_reserved(name))
            self.assertEqual(feature_config._load_reservations(), {})

    def test_reservation_file_is_line_based(self):
        with temp_config_dir():
            name = "@dailybackup-2025-01-01T00:00-04:00-d"
            feature_config._reserve_snapshot_name(name)
            with open(feature_config.SNAPNAME_RESERVED, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertTrue(content.startswith(name + " "))

    def test_concurrent_generation_completes_safely(self):
        with temp_config_dir():
            names = []
            errors = []

            def run(label):
                try:
                    names.append(feature_config.generate_snapshot_name(label))
                except Exception as exc:
                    errors.append(exc)

            t1 = threading.Thread(target=run, args=("dailybackup",))
            t2 = threading.Thread(target=run, args=("offsite",))
            t1.start()
            t2.start()
            t1.join(timeout=10)
            t2.join(timeout=10)

            self.assertEqual(errors, [])
            self.assertEqual(len(names), 2)
            reservations = feature_config._load_reservations()
            for name in names:
                self.assertIn(name, reservations)


class TestScrubManagerConfig(unittest.TestCase):
    """Scrub manager config helper."""

    def test_get_scrub_manager_config_default(self):
        config = {}
        sm = feature_config.get_scrub_manager_config(config)
        self.assertIn("simultaneous", sm)

    def test_save_scrub_manager_config(self):
        with temp_config_dir():
            config = {}
            feature_config.save_scrub_manager_config(config, {"target": 2})
            self.assertEqual(config["scrub_manager"]["target"], 2)


class TestPrunePoolsOrder(unittest.TestCase):
    """Persistence of the Retention tab prune pool order."""

    def test_get_prune_pools_order_defaults_to_empty_list(self):
        self.assertEqual(feature_config.get_prune_pools_order({}), [])
        self.assertEqual(feature_config.get_prune_pools_order({"prune_pools_order": None}), [])

    def test_get_prune_pools_order_returns_strings(self):
        config = {"prune_pools_order": ["tank", "archive"]}
        self.assertEqual(feature_config.get_prune_pools_order(config), ["tank", "archive"])

    def test_save_prune_pools_order_persists_strings(self):
        with temp_config_dir():
            config = {}
            feature_config.save_prune_pools_order(config, ["archive", "tank"])
            self.assertEqual(config["prune_pools_order"], ["archive", "tank"])


if __name__ == "__main__":
    unittest.main()

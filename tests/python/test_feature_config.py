"""Tests for feature_config.py — per-feature getters/setters and snapshot naming."""

import os
import sys
import threading
import time
import unittest

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import feature_config
from snapshot_naming import bucket_for
from test_support import patch_environ, temp_config_dir


class TestBackupConfig(unittest.TestCase):
    """Backup tab configuration defaults and save."""

    def test_get_backup_config_merges_defaults(self):
        config = {"backup": {"variables": {"label": "special"}}}
        backup = feature_config.get_backup_config(config)
        self.assertEqual(backup["variables"]["label"], "special")
        self.assertEqual(backup["variables"]["autoresume"], "Y")
        self.assertIn("pull_steps", backup)
        self.assertTrue(backup["pull_steps_active"])

    def test_get_backup_config_adds_excludes_to_pull_steps(self):
        config = {
            "backup": {
                "pull_steps": [
                    {"active": True, "source": "host:/src", "dest": "/dst"},
                ],
            },
        }
        backup = feature_config.get_backup_config(config)
        self.assertEqual(backup["pull_steps"][0]["excludes"], [])

    def test_get_backup_config_preserves_existing_excludes(self):
        config = {
            "backup": {
                "pull_steps": [
                    {
                        "active": True,
                        "source": "host:/src",
                        "dest": "/dst",
                        "excludes": ["*.tmp", "cache/"],
                    },
                ],
            },
        }
        backup = feature_config.get_backup_config(config)
        self.assertEqual(backup["pull_steps"][0]["excludes"], ["*.tmp", "cache/"])

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
        self.assertFalse(restore["auto_dest"])
        self.assertEqual(restore["variables"]["verify_after_transfer"], "Y")
        self.assertEqual(restore["variables"]["transfer_rate_limit"], "")


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

    def test_save_pools_does_not_sync_offsite_pools(self):
        with temp_config_dir():
            config = {}
            feature_config.save_pools(
                config,
                [
                    {"name": "tank", "offsite_candidate": False},
                    {"name": "z40tb", "offsite_candidate": True},
                ],
            )
            self.assertNotIn("offsite_pools", config.get("offsite", {}))

    def test_get_checkagainst_creates_nested_defaults(self):
        config = {}
        data = feature_config.get_checkagainst(config)
        self.assertTrue(data["backup_derived_active"])
        self.assertTrue(data["offsite_derived_active"])
        self.assertEqual(data["backup_derived"], [])
        self.assertEqual(data["offsite_derived"], [])
        self.assertEqual(data["user_entries"], [])


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


class TestMassDeleteConfig(unittest.TestCase):
    """Advanced Prune Options card configuration defaults and merge."""

    def test_get_retention_mass_delete_config_defaults(self):
        config = {}
        md = feature_config.get_retention_mass_delete_config(config)
        self.assertEqual(md["releaseholds"], "Y")
        self.assertEqual(md["releaseholds_tags"], "offsite-*")
        self.assertFalse(md["ignore_retention_policies"])
        self.assertEqual(md["includes"], "")
        self.assertEqual(md["snapshot_has"], "")

    def test_get_retention_mass_delete_config_merges_saved_values(self):
        config = {
            "retention_mass_delete": {
                "releaseholds": "N",
                "releaseholds_tags": "custom-*",
                "ignore_retention_policies": True,
                "snapshot_has": "weekly",
            }
        }
        md = feature_config.get_retention_mass_delete_config(config)
        self.assertEqual(md["releaseholds"], "N")
        self.assertEqual(md["releaseholds_tags"], "custom-*")
        self.assertTrue(md["ignore_retention_policies"])
        self.assertEqual(md["snapshot_has"], "weekly")


class TestEnclosuresConfig(unittest.TestCase):
    """Enclosures section ({id: {name, max_rate}}) getters and setters."""

    def test_get_enclosures_config_creates_empty_section(self):
        config = {}
        data = feature_config.get_enclosures_config(config)
        self.assertEqual(data, {})
        self.assertIn("enclosures", config)

    def test_get_enclosures_config_preserves_values(self):
        config = {"enclosures": {"a1b2c3d4e5": {"name": "fivebays", "max_rate": "100M"}}}
        data = feature_config.get_enclosures_config(config)
        self.assertEqual(data, {"a1b2c3d4e5": {"name": "fivebays", "max_rate": "100M"}})

    def test_get_enclosures_config_normalizes_entries(self):
        config = {
            "enclosures": {
                "abc123": {"name": "Three Amigos"},  # missing max_rate
                "def456": {"max_rate": "50M"},  # missing name
                "notadict": "garbage",
            }
        }
        data = feature_config.get_enclosures_config(config)
        self.assertEqual(data["abc123"], {"name": "Three Amigos", "max_rate": ""})
        self.assertEqual(data["def456"], {"name": "", "max_rate": "50M"})
        self.assertEqual(data["notadict"], {"name": "", "max_rate": ""})

    def test_save_enclosures_config(self):
        with temp_config_dir():
            config = {}
            feature_config.save_enclosures_config(
                config, {"a1b2c3d4e5": {"name": "fivebays", "max_rate": ""}}
            )
            self.assertEqual(
                config["enclosures"],
                {"a1b2c3d4e5": {"name": "fivebays", "max_rate": ""}},
            )
            self.assertEqual(
                feature_config.get_enclosures_config(config),
                {"a1b2c3d4e5": {"name": "fivebays", "max_rate": ""}},
            )


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

    def test_name_renders_canonical_utc_z(self):
        with patch_environ():
            name = feature_config._build_snapshot_name("dailybackup")
            self.assertRegex(name, r"^@dailybackup-\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z-[dwms]$")

    def test_bucket_matrix_follows_utc_instant(self):
        new_york = timezone(timedelta(hours=-4))
        cases = [
            # UTC 1st of month → monthly, Sunday or not.
            (datetime(2026, 10, 1, 3, 0, tzinfo=timezone.utc), "dailybackup", "m"),
            (datetime(2026, 11, 1, 3, 0, tzinfo=timezone.utc), "dailybackup", "m"),
            # UTC Sunday (not the 1st) → weekly.
            (datetime(2026, 10, 11, 0, 30, tzinfo=timezone.utc), "dailybackup", "w"),
            # Ordinary UTC weekday → daily.
            (datetime(2026, 10, 7, 1, 46, tzinfo=timezone.utc), "dailybackup", "d"),
            # Local Sat 23:30 New York is already UTC Sunday → weekly: one
            # clock, the bucket follows the UTC instant in the name.
            (datetime(2026, 10, 10, 23, 30, tzinfo=new_york), "dailybackup", "w"),
            # Offsite label always lands in the offsite bucket.
            (datetime(2026, 10, 7, 1, 46, tzinfo=timezone.utc), "offsite", "s"),
        ]
        for when, label, expected in cases:
            self.assertEqual(bucket_for(when, label), expected, f"{when.isoformat()} {label}")

    def test_offsite_bucket_is_s(self):
        with patch_environ():
            name = feature_config._build_snapshot_name("offsite")
            self.assertTrue(name.endswith("-s"))

    def test_snapfile_roundtrip(self):
        with temp_config_dir():
            feature_config._write_snapfile(
                feature_config.SNAPFILE, "@test-2025-01-01T00:00-04:00-d"
            )
            self.assertEqual(
                feature_config._read_snapfile(feature_config.SNAPFILE),
                "@test-2025-01-01T00:00-04:00-d",
            )
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
                except (OSError, RuntimeError) as exc:
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


class TestScrubStatePersistence(unittest.TestCase):
    """load_scrub_state / save_scrub_state round trips."""

    def test_load_missing_returns_defaults(self):
        with temp_config_dir() as tmpdir:
            path = os.path.join(tmpdir, "scrub_state.json")
            with patch.object(feature_config, "SCRUB_STATE_PATH", path):
                data = feature_config.load_scrub_state()
        self.assertEqual(data["pending"], [])
        self.assertEqual(data["active"], [])
        self.assertEqual(data["paused"], [])
        self.assertEqual(data["finished"], [])
        self.assertEqual(data["target"], 1)

    def test_save_then_load_round_trips(self):
        with temp_config_dir() as tmpdir:
            path = os.path.join(tmpdir, "scrub_state.json")
            with patch.object(feature_config, "SCRUB_STATE_PATH", path):
                feature_config.save_scrub_state(
                    {
                        "pending": ["tank"],
                        "active": ["fivebays"],
                        "paused": [],
                        "finished": ["threeamigos"],
                        "target": 3,
                    }
                )
                data = feature_config.load_scrub_state()
        self.assertEqual(data["pending"], ["tank"])
        self.assertEqual(data["active"], ["fivebays"])
        self.assertEqual(data["finished"], ["threeamigos"])
        self.assertEqual(data["target"], 3)

    def test_load_corrupt_file_returns_defaults(self):
        with temp_config_dir() as tmpdir:
            path = os.path.join(tmpdir, "scrub_state.json")
            with open(path, "w") as fh:
                fh.write("not json")
            with patch.object(feature_config, "SCRUB_STATE_PATH", path):
                data = feature_config.load_scrub_state()
        self.assertEqual(data["pending"], [])

    def test_load_non_list_buckets_default_to_empty_lists(self):
        with temp_config_dir() as tmpdir:
            path = os.path.join(tmpdir, "scrub_state.json")
            with open(path, "w") as fh:
                import json

                json.dump({"pending": "oops", "target": 2}, fh)
            with patch.object(feature_config, "SCRUB_STATE_PATH", path):
                data = feature_config.load_scrub_state()
        self.assertEqual(data["pending"], [])
        self.assertEqual(data["target"], 2)


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


class TestRetentionVerbMessages(unittest.TestCase):
    """Retention VERB message toggle helpers."""

    def test_get_retention_verb_messages_default_false(self):
        self.assertFalse(feature_config.get_retention_verb_messages({}))
        self.assertFalse(
            feature_config.get_retention_verb_messages({"retention_verb_messages": False})
        )

    def test_get_retention_verb_messages_true(self):
        self.assertTrue(
            feature_config.get_retention_verb_messages({"retention_verb_messages": True})
        )

    def test_save_retention_verb_messages_persists_bool(self):
        with temp_config_dir():
            config = {}
            feature_config.save_retention_verb_messages(config, True)
            self.assertIs(config["retention_verb_messages"], True)
            feature_config.save_retention_verb_messages(config, False)
            self.assertIs(config["retention_verb_messages"], False)


class TestWorkloadProfiles(unittest.TestCase):
    """Workload profile config helpers."""

    def test_get_workload_profiles_seeds_defaults(self):
        config = {}
        profiles = feature_config.get_workload_profiles(config)
        self.assertIn("general", profiles)
        self.assertIn("scratch", profiles)
        self.assertEqual(len(profiles), 10)

    def test_get_workload_profiles_preserves_user_edits(self):
        config = {
            "workload_profiles": {
                "general": {
                    "description": "Overridden",
                    "applies_to": ["filesystem"],
                    "properties": {"compression": "off"},
                    "notes": "User override",
                }
            }
        }
        profiles = feature_config.get_workload_profiles(config)
        self.assertEqual(profiles["general"]["description"], "Overridden")

    def test_get_workload_profiles_returns_deep_copy(self):
        config = {}
        profiles = feature_config.get_workload_profiles(config)
        profiles["general"]["description"] = "mutated"
        self.assertNotEqual(
            feature_config.get_workload_profiles(config)["general"]["description"],
            "mutated",
        )

    def test_save_workload_profiles(self):
        with temp_config_dir():
            config = {}
            feature_config.save_workload_profiles(config, {"custom": {}})
            self.assertIn("custom", config["workload_profiles"])

    def test_save_workload_profiles_rejects_non_dict(self):
        with temp_config_dir():
            config = {}
            with self.assertRaises(TypeError):
                feature_config.save_workload_profiles(config, ["not", "a", "dict"])

    def test_delete_workload_profile(self):
        with temp_config_dir():
            config = {}
            feature_config.get_workload_profiles(config)
            feature_config.save_workload_profiles(
                config, {**feature_config.get_workload_profiles(config), "custom": {}}
            )
            self.assertTrue(feature_config.delete_workload_profile(config, "custom"))
            self.assertFalse(feature_config.delete_workload_profile(config, "custom"))

    def test_builtin_profiles_are_immutable(self):
        self.assertTrue(feature_config.is_builtin_workload_profile("general"))
        self.assertFalse(feature_config.is_builtin_workload_profile("custom"))

    def test_delete_builtin_profile_is_refused(self):
        with temp_config_dir():
            config = {}
            feature_config.get_workload_profiles(config)
            self.assertFalse(feature_config.delete_workload_profile(config, "general"))
            self.assertIn("general", feature_config.get_workload_profiles(config))

    def test_reset_workload_profiles(self):
        with temp_config_dir():
            config = {}
            feature_config.get_workload_profiles(config)
            feature_config.save_workload_profiles(config, {"custom": {"description": "x"}})
            feature_config.reset_workload_profiles(config)
            self.assertIn("general", config["workload_profiles"])
            self.assertNotIn("custom", config["workload_profiles"])


class TestAlignmentSurvey(unittest.TestCase):
    """Alignment-view workload survey config helpers."""

    def test_get_alignment_survey_empty_by_default(self):
        self.assertEqual(feature_config.get_alignment_survey({}), {})

    def test_get_alignment_survey_returns_copy(self):
        config = {"alignment_survey": {"fivebays/db": "database-postgresql"}}
        survey = feature_config.get_alignment_survey(config)
        survey["fivebays/db"] = "mutated"
        self.assertEqual(
            feature_config.get_alignment_survey(config)["fivebays/db"],
            "database-postgresql",
        )

    def test_save_alignment_survey(self):
        with temp_config_dir():
            config = {}
            survey = {"fivebays/db": "database-postgresql", "fivebays/media": "media"}
            feature_config.save_alignment_survey(config, survey)
            self.assertEqual(feature_config.get_alignment_survey(config), survey)

    def test_save_alignment_survey_rejects_non_dict(self):
        with temp_config_dir():
            config = {}
            with self.assertRaises(TypeError):
                feature_config.save_alignment_survey(config, ["not", "a", "dict"])


class TestPoolProfiles(unittest.TestCase):
    """Pool profile config helpers."""

    def test_get_pool_profiles_seeds_defaults(self):
        config = {}
        profiles = feature_config.get_pool_profiles(config)
        self.assertIn("general", profiles)
        self.assertIn("archival", profiles)
        self.assertEqual(len(profiles), 2)

    def test_seeded_profiles_pass_validation(self):
        from pool_profiles import validate_profile

        for profile in feature_config.get_pool_profiles({}).values():
            self.assertEqual(validate_profile(profile), [])

    def test_get_pool_profiles_preserves_user_edits(self):
        config = {
            "pool_profiles": {
                "general": {
                    "description": "Overridden",
                    "blocksize": "4096 bytes",
                    "pool_properties": {"autotrim": "off"},
                    "filesystem_properties": {"compression": "zstd"},
                    "notes": "User override",
                }
            }
        }
        profiles = feature_config.get_pool_profiles(config)
        self.assertEqual(profiles["general"]["description"], "Overridden")
        self.assertEqual(profiles["general"]["blocksize"], "4096 bytes")

    def test_get_pool_profiles_returns_deep_copy(self):
        config = {}
        profiles = feature_config.get_pool_profiles(config)
        profiles["general"]["description"] = "mutated"
        self.assertNotEqual(
            feature_config.get_pool_profiles(config)["general"]["description"],
            "mutated",
        )

    def test_save_pool_profiles(self):
        with temp_config_dir():
            config = {}
            feature_config.save_pool_profiles(config, {"custom": {}})
            self.assertIn("custom", config["pool_profiles"])

    def test_save_pool_profiles_rejects_non_dict(self):
        with temp_config_dir():
            config = {}
            with self.assertRaises(TypeError):
                feature_config.save_pool_profiles(config, ["not", "a", "dict"])

    def test_delete_pool_profile(self):
        with temp_config_dir():
            config = {}
            feature_config.get_pool_profiles(config)
            feature_config.save_pool_profiles(
                config, {**feature_config.get_pool_profiles(config), "custom": {}}
            )
            self.assertTrue(feature_config.delete_pool_profile(config, "custom"))
            self.assertFalse(feature_config.delete_pool_profile(config, "custom"))

    def test_builtin_pool_profiles_are_immutable(self):
        self.assertTrue(feature_config.is_builtin_pool_profile("general"))
        self.assertTrue(feature_config.is_builtin_pool_profile("archival"))
        self.assertFalse(feature_config.is_builtin_pool_profile("custom"))

    def test_delete_builtin_pool_profile_is_refused(self):
        with temp_config_dir():
            config = {}
            feature_config.get_pool_profiles(config)
            self.assertFalse(feature_config.delete_pool_profile(config, "general"))
            self.assertIn("general", feature_config.get_pool_profiles(config))

    def test_reset_pool_profiles(self):
        with temp_config_dir():
            config = {}
            feature_config.get_pool_profiles(config)
            feature_config.save_pool_profiles(config, {"custom": {"description": "x"}})
            feature_config.reset_pool_profiles(config)
            self.assertIn("general", config["pool_profiles"])
            self.assertIn("archival", config["pool_profiles"])
            self.assertNotIn("custom", config["pool_profiles"])


class TestComputeDestinationRoot(unittest.TestCase):
    """Checkagainst destination-root helper."""

    def test_no_common_suffix_appends_source_to_destination(self):
        self.assertEqual(
            feature_config._compute_destination_root("tank/a", "backup/b"),
            "backup/b/tank/a",
        )

    def test_common_suffix_returns_destination(self):
        self.assertEqual(
            feature_config._compute_destination_root(
                "threeamigos/proxmox", "fivebays/threeamigos/proxmox"
            ),
            "fivebays/threeamigos/proxmox",
        )

    def test_offsite_wildcard_matches_common_suffix(self):
        self.assertEqual(
            feature_config._compute_destination_root(
                "threeamigos/proxmox", "<offsite>/threeamigos/proxmox"
            ),
            "<offsite>/threeamigos/proxmox",
        )

    def test_offsite_pool_root_appends_source(self):
        """A destination of just <offsite> is a pool root, not a suffix match."""
        self.assertEqual(
            feature_config._compute_destination_root("fivebays", "<offsite>"),
            "<offsite>/fivebays",
        )

    def test_offsite_pool_root_appends_nested_source(self):
        self.assertEqual(
            feature_config._compute_destination_root("fivebays/threeamigos/proxmox", "<offsite>"),
            "<offsite>/fivebays/threeamigos/proxmox",
        )

    def test_offsite_pool_root_appends_temp_source(self):
        self.assertEqual(
            feature_config._compute_destination_root("temp", "<offsite>"),
            "<offsite>/temp",
        )


class TestNotificationsConfig(unittest.TestCase):
    """Notifications section defaults, normalization, and save."""

    def test_absent_section_defaults_to_off_with_all_types_on(self):
        config = {}
        data = feature_config.get_notifications_config(config)
        self.assertEqual(data["desktop"]["mode"], "off")
        self.assertEqual(data["email"]["mode"], "off")
        for channel in ("desktop", "email"):
            for run_type in feature_config.NOTIFICATION_TYPES:
                self.assertTrue(data[channel]["types"][run_type])
        self.assertEqual(data["email"]["smtp_port"], 587)
        self.assertEqual(data["email"]["smtp_security"], "starttls")
        self.assertEqual(data["email"]["smtp_to"], [])
        # get_ normalizes in place so callers see a stable shape.
        self.assertEqual(config["notifications"], data)

    def test_invalid_mode_falls_back_to_off(self):
        config = {"notifications": {"desktop": {"mode": "loud"}}}
        data = feature_config.get_notifications_config(config)
        self.assertEqual(data["desktop"]["mode"], "off")

    def test_partial_type_toggles_keep_defaults_for_the_rest(self):
        config = {"notifications": {"email": {"mode": "all", "types": {"backup": False}}}}
        data = feature_config.get_notifications_config(config)
        self.assertFalse(data["email"]["types"]["backup"])
        for run_type in feature_config.NOTIFICATION_TYPES:
            if run_type != "backup":
                self.assertTrue(data["email"]["types"][run_type])

    def test_non_boolean_type_entries_coerced_to_truthiness(self):
        # The dialog writes real booleans; hand-edited values coerce by
        # truthiness (an empty string or 0 disables, anything else enables).
        config = {
            "notifications": {
                "desktop": {"mode": "all", "types": {"scrub": "", "backup": 0, "restore": "yes"}}
            }
        }
        data = feature_config.get_notifications_config(config)
        self.assertIs(data["desktop"]["types"]["scrub"], False)
        self.assertIs(data["desktop"]["types"]["backup"], False)
        self.assertIs(data["desktop"]["types"]["restore"], True)

    def test_smtp_to_string_splits_on_commas(self):
        config = {"notifications": {"email": {"smtp_to": "a@example.com, b@example.com"}}}
        data = feature_config.get_notifications_config(config)
        self.assertEqual(data["email"]["smtp_to"], ["a@example.com", "b@example.com"])

    def test_smtp_to_list_strips_blanks(self):
        config = {"notifications": {"email": {"smtp_to": [" a@b.c ", "", "c@d.e"]}}}
        data = feature_config.get_notifications_config(config)
        self.assertEqual(data["email"]["smtp_to"], ["a@b.c", "c@d.e"])

    def test_bad_port_and_security_fall_back(self):
        config = {
            "notifications": {
                "email": {"smtp_port": "not-a-port", "smtp_security": "carrier-pigeon"}
            }
        }
        data = feature_config.get_notifications_config(config)
        self.assertEqual(data["email"]["smtp_port"], 587)
        self.assertEqual(data["email"]["smtp_security"], "starttls")

    def test_valid_settings_survive_round_trip(self):
        settings = {
            "desktop": {"mode": "failures", "types": {"backup": True, "offsite": False}},
            "email": {
                "mode": "all",
                "types": {},
                "smtp_host": "smtp.example.com",
                "smtp_port": 465,
                "smtp_security": "ssl",
                "smtp_username": "user",
                "smtp_from": "zfs@example.com",
                "smtp_to": "a@example.com",
            },
        }
        with temp_config_dir():
            config = {}
            feature_config.save_notifications_config(config, settings)
        saved = config["notifications"]
        self.assertEqual(saved["desktop"]["mode"], "failures")
        self.assertFalse(saved["desktop"]["types"]["offsite"])
        self.assertEqual(saved["email"]["smtp_port"], 465)
        self.assertEqual(saved["email"]["smtp_security"], "ssl")
        self.assertEqual(saved["email"]["smtp_to"], ["a@example.com"])
        # Types normalize to the full set on save.
        for run_type in feature_config.NOTIFICATION_TYPES:
            self.assertIn(run_type, saved["email"]["types"])
            self.assertIn(run_type, saved["desktop"]["types"])


if __name__ == "__main__":
    unittest.main()

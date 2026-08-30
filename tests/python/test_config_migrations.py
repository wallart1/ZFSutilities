"""Tests for config_migrations.py — schema migrations."""

import unittest

import config_migrations


class TestIndividualMigrations(unittest.TestCase):
    def test_migrate_1_to_2_adds_archive_path(self):
        config = {"config_version": 1}
        result = config_migrations._migrate_1_to_2(config)
        self.assertEqual(result["config_version"], 2)
        self.assertEqual(result["archive_path"], "")

    def test_migrate_2_to_3_removes_project_and_home_dir(self):
        config = {"config_version": 2, "project_dir": "/foo", "home_dir": "/bar"}
        result = config_migrations._migrate_2_to_3(config)
        self.assertNotIn("project_dir", result)
        self.assertNotIn("home_dir", result)
        self.assertEqual(result["config_version"], 3)

    def test_migrate_3_to_4_adds_pre_backup_fields(self):
        config = {"config_version": 3}
        result = config_migrations._migrate_3_to_4(config)
        self.assertIn("pre_backup_script_enabled", result)
        self.assertFalse(result["pre_backup_script_enabled"])
        self.assertEqual(result["config_version"], 4)

    def test_migrate_4_to_5_adds_log_retention(self):
        config = {"config_version": 4}
        result = config_migrations._migrate_4_to_5(config)
        self.assertEqual(result["log_retention_days"], 30)
        self.assertEqual(result["config_version"], 5)

    def test_migrate_5_to_6_adds_post_backup_fields(self):
        config = {"config_version": 5}
        result = config_migrations._migrate_5_to_6(config)
        self.assertIn("post_backup_script_enabled", result)
        self.assertFalse(result["post_backup_script_enabled"])
        self.assertEqual(result["config_version"], 6)

    def test_migrate_6_to_7_adds_verify_after_transfer(self):
        config = {"config_version": 6, "backup": {"variables": {}}, "offsite": {"variables": {}}}
        result = config_migrations._migrate_6_to_7(config)
        self.assertEqual(result["backup"]["variables"]["verify_after_transfer"], "Y")
        self.assertEqual(result["offsite"]["variables"]["verify_after_transfer"], "Y")
        self.assertEqual(result["config_version"], 7)

    def test_migrate_6_to_7_skips_missing_sections(self):
        config = {"config_version": 6}
        result = config_migrations._migrate_6_to_7(config)
        self.assertEqual(result["config_version"], 7)

    def test_migrate_7_to_8_adds_history_retention(self):
        config = {"config_version": 7}
        result = config_migrations._migrate_7_to_8(config)
        self.assertEqual(result["history_retention_days"], 90)
        self.assertEqual(result["config_version"], 8)

    def test_migrate_8_to_9_adds_dashboard(self):
        config = {"config_version": 8}
        result = config_migrations._migrate_8_to_9(config)
        self.assertEqual(result["dashboard"]["low_space_threshold"], 80)
        self.assertEqual(result["config_version"], 9)

    def test_migrate_9_to_10_adds_scrub_manager(self):
        config = {"config_version": 9}
        result = config_migrations._migrate_9_to_10(config)
        self.assertEqual(result["scrub_manager"]["simultaneous"], 1)
        self.assertEqual(result["scrub_manager"]["refresh_seconds"], 10)
        self.assertFalse(result["scrub_manager"]["system_scrub_weekly"])
        self.assertFalse(result["scrub_manager"]["system_scrub_monthly"])
        self.assertEqual(result["config_version"], 10)

    def test_migrate_11_to_12_adds_pull_steps_active(self):
        config = {"config_version": 11}
        result = config_migrations._migrate_11_to_12(config)
        self.assertTrue(result["backup"]["pull_steps_active"])
        self.assertEqual(result["config_version"], 12)

    def test_migrate_11_to_12_preserves_existing_value(self):
        config = {"config_version": 11, "backup": {"pull_steps_active": False}}
        result = config_migrations._migrate_11_to_12(config)
        self.assertFalse(result["backup"]["pull_steps_active"])

    def test_migrate_12_to_13_adds_prune_label(self):
        config = {"config_version": 12}
        result = config_migrations._migrate_12_to_13(config)
        self.assertEqual(result["prune_label"], "dailybackup")
        self.assertEqual(result["config_version"], 13)

    def test_migrate_12_to_13_preserves_existing_value(self):
        config = {"config_version": 12, "prune_label": "weekly"}
        result = config_migrations._migrate_12_to_13(config)
        self.assertEqual(result["prune_label"], "weekly")
        self.assertEqual(result["config_version"], 13)

    def test_migrate_13_to_14_converts_string_pools(self):
        config = {"config_version": 13, "pools": ["tank", "pool2"]}
        result = config_migrations._migrate_13_to_14(config)
        self.assertEqual(
            result["pools"],
            [
                {"name": "tank", "offsite_candidate": False},
                {"name": "pool2", "offsite_candidate": False},
            ],
        )
        self.assertEqual(result["config_version"], 14)

    def test_migrate_13_to_14_preserves_dict_pools(self):
        config = {
            "config_version": 13,
            "pools": [
                {"name": "tank", "offsite_candidate": True},
            ],
        }
        result = config_migrations._migrate_13_to_14(config)
        self.assertEqual(
            result["pools"],
            [{"name": "tank", "offsite_candidate": True}],
        )

    def test_migrate_13_to_14_handles_missing_pools(self):
        config = {"config_version": 13}
        result = config_migrations._migrate_13_to_14(config)
        self.assertNotIn("pools", result)
        self.assertEqual(result["config_version"], 14)

    def test_migrate_14_to_15_adds_comment_to_checkagainst(self):
        config = {
            "config_version": 14,
            "checkagainst": [
                {"dataset": "tank/a", "quals": "0", "counterpart": "backup/a", "label": "offsite"},
                {"dataset": "tank/b", "comment": "existing"},
            ],
        }
        result = config_migrations._migrate_14_to_15(config)
        self.assertEqual(result["config_version"], 15)
        self.assertEqual(result["checkagainst"][0]["comment"], "")
        self.assertEqual(result["checkagainst"][1]["comment"], "existing")

    def test_migrate_14_to_15_handles_missing_checkagainst(self):
        config = {"config_version": 14}
        result = config_migrations._migrate_14_to_15(config)
        self.assertEqual(result["config_version"], 15)
        self.assertNotIn("checkagainst", result)

    def test_migrate_14_to_15_is_idempotent(self):
        config = {
            "config_version": 14,
            "checkagainst": [
                {"dataset": "tank/a", "quals": "0", "counterpart": "backup/a", "label": "offsite"},
            ],
        }
        result1 = config_migrations._migrate_14_to_15(dict(config))
        result2 = config_migrations._migrate_14_to_15(result1)
        self.assertEqual(result1, result2)

    def test_migrate_14_to_15_skips_non_dict_entries(self):
        config = {
            "config_version": 14,
            "checkagainst": [
                {"dataset": "tank/a", "quals": "0", "counterpart": "backup/a", "label": "offsite"},
                None,
                "not-a-dict",
                {"dataset": "tank/b", "comment": "existing"},
            ],
        }
        result = config_migrations._migrate_14_to_15(config)
        self.assertEqual(result["config_version"], 15)
        self.assertEqual(result["checkagainst"][0]["comment"], "")
        self.assertIsNone(result["checkagainst"][1])
        self.assertEqual(result["checkagainst"][2], "not-a-dict")
        self.assertEqual(result["checkagainst"][3]["comment"], "existing")

    def test_config_version_is_24(self):
        self.assertEqual(config_migrations.CONFIG_VERSION, 24)

    def test_migrate_19_to_20_drops_offsite_pools(self):
        config = {
            "config_version": 19,
            "offsite": {
                "offsite_pools": ["z40tb", "z22tb"],
                "variables": {},
                "steps": [],
            },
        }
        result = config_migrations._migrate_19_to_20(config)
        self.assertEqual(result["config_version"], 20)
        self.assertNotIn("offsite_pools", result.get("offsite", {}))

    def test_migrate_19_to_20_handles_missing_offsite(self):
        config = {"config_version": 19}
        result = config_migrations._migrate_19_to_20(config)
        self.assertEqual(result["config_version"], 20)
        self.assertNotIn("offsite", result)

    def test_migrate_19_to_20_idempotent(self):
        config = {
            "config_version": 19,
            "offsite": {"offsite_pools": ["z40tb"]},
        }
        result1 = config_migrations._migrate_19_to_20(dict(config))
        result2 = config_migrations._migrate_19_to_20(result1)
        self.assertEqual(result1, result2)

    def test_migrate_20_to_21_adds_retention_verb_messages(self):
        config = {"config_version": 20}
        result = config_migrations._migrate_20_to_21(config)
        self.assertEqual(result["config_version"], 21)
        self.assertIs(result["retention_verb_messages"], False)

    def test_migrate_20_to_21_preserves_existing_value(self):
        config = {"config_version": 20, "retention_verb_messages": True}
        result = config_migrations._migrate_20_to_21(config)
        self.assertEqual(result["config_version"], 21)
        self.assertIs(result["retention_verb_messages"], True)

    def test_migrate_20_to_21_idempotent(self):
        config = {"config_version": 20}
        result1 = config_migrations._migrate_20_to_21(dict(config))
        result2 = config_migrations._migrate_20_to_21(result1)
        self.assertEqual(result1, result2)

    def test_migrate_21_to_22_adds_dashboard_refresh_seconds(self):
        config = {"config_version": 21}
        result = config_migrations._migrate_21_to_22(config)
        self.assertEqual(result["config_version"], 22)
        self.assertEqual(result["dashboard"]["refresh_seconds"], 30)

    def test_migrate_21_to_22_preserves_existing_refresh_seconds(self):
        config = {
            "config_version": 21,
            "dashboard": {"low_space_threshold": 75, "refresh_seconds": 120},
        }
        result = config_migrations._migrate_21_to_22(config)
        self.assertEqual(result["config_version"], 22)
        self.assertEqual(result["dashboard"]["refresh_seconds"], 120)
        self.assertEqual(result["dashboard"]["low_space_threshold"], 75)

    def test_migrate_21_to_22_idempotent(self):
        config = {"config_version": 21}
        result1 = config_migrations._migrate_21_to_22(dict(config))
        result2 = config_migrations._migrate_21_to_22(result1)
        self.assertEqual(result1, result2)

    def test_migrate_22_to_23_adds_excludes_to_pull_steps(self):
        config = {
            "config_version": 22,
            "backup": {
                "pull_steps": [
                    {"active": True, "source": "host:/src", "dest": "/dst"},
                ],
            },
        }
        result = config_migrations._migrate_22_to_23(config)
        self.assertEqual(result["config_version"], 23)
        self.assertEqual(result["backup"]["pull_steps"][0]["excludes"], [])

    def test_migrate_22_to_23_preserves_existing_excludes(self):
        config = {
            "config_version": 22,
            "backup": {
                "pull_steps": [
                    {
                        "active": True,
                        "source": "host:/src",
                        "dest": "/dst",
                        "excludes": ["*.tmp"],
                    },
                ],
            },
        }
        result = config_migrations._migrate_22_to_23(config)
        self.assertEqual(result["config_version"], 23)
        self.assertEqual(result["backup"]["pull_steps"][0]["excludes"], ["*.tmp"])

    def test_migrate_22_to_23_handles_missing_backup(self):
        config = {"config_version": 22}
        result = config_migrations._migrate_22_to_23(config)
        self.assertEqual(result["config_version"], 23)
        self.assertNotIn("backup", result)

    def test_migrate_22_to_23_idempotent(self):
        config = {
            "config_version": 22,
            "backup": {"pull_steps": [{"active": True, "source": "a", "dest": "b"}]},
        }
        result1 = config_migrations._migrate_22_to_23(dict(config))
        result2 = config_migrations._migrate_22_to_23(result1)
        self.assertEqual(result1, result2)

    def test_migrate_15_to_16_adds_prune_pools_order(self):
        config = {"config_version": 15}
        result = config_migrations._migrate_15_to_16(config)
        self.assertEqual(result["prune_pools_order"], [])
        self.assertEqual(result["config_version"], 16)

    def test_migrate_15_to_16_preserves_existing_order(self):
        config = {"config_version": 15, "prune_pools_order": ["tank", "archive"]}
        result = config_migrations._migrate_15_to_16(config)
        self.assertEqual(result["prune_pools_order"], ["tank", "archive"])
        self.assertEqual(result["config_version"], 16)


class TestRunMigrations(unittest.TestCase):
    def test_run_migrations_from_version_1(self):
        config = {"config_version": 1}
        result = config_migrations.run_migrations(config)
        self.assertEqual(result["config_version"], config_migrations.CONFIG_VERSION)
        self.assertEqual(result["archive_path"], "")

    def test_run_migrations_already_current(self):
        config = {"config_version": config_migrations.CONFIG_VERSION}
        result = config_migrations.run_migrations(config)
        self.assertEqual(result["config_version"], config_migrations.CONFIG_VERSION)

    def test_run_migrations_calls_save_func(self):
        saves = []
        config = {"config_version": 1}
        config_migrations.run_migrations(
            config, save_func=lambda c: saves.append(c["config_version"])
        )
        self.assertIn(2, saves)
        self.assertEqual(saves[-1], config_migrations.CONFIG_VERSION)

    def test_run_migrations_missing_migration_raises(self):
        orig = config_migrations.MIGRATIONS[:]
        try:
            # Truncate migrations so version 1 has no defined path forward
            config_migrations.MIGRATIONS = []
            config = {"config_version": 1}
            with self.assertRaises(RuntimeError):
                config_migrations.run_migrations(config)
        finally:
            config_migrations.MIGRATIONS = orig

    def test_run_migrations_idempotency(self):
        config = {"config_version": 3}
        result1 = config_migrations.run_migrations(config)
        result2 = config_migrations.run_migrations(result1)
        self.assertEqual(result1["config_version"], result2["config_version"])

    def test_migrate_16_to_17_adds_pause_scrubs(self):
        config = {"config_version": 16}
        result = config_migrations._migrate_16_to_17(config)
        self.assertEqual(result["config_version"], 17)
        self.assertFalse(result["backup"]["pause_scrubs"])
        self.assertFalse(result["offsite"]["pause_scrubs"])
        self.assertFalse(result["restore"]["pause_scrubs"])

    def test_migrate_16_to_17_preserves_existing_value(self):
        config = {
            "config_version": 16,
            "backup": {"pause_scrubs": True},
            "offsite": {"pause_scrubs": True},
            "restore": {"pause_scrubs": True},
        }
        result = config_migrations._migrate_16_to_17(config)
        self.assertTrue(result["backup"]["pause_scrubs"])
        self.assertTrue(result["offsite"]["pause_scrubs"])
        self.assertTrue(result["restore"]["pause_scrubs"])

    def test_migrate_17_to_18_moves_flat_list(self):
        config = {
            "config_version": 17,
            "checkagainst": [
                {"dataset": "tank/a", "quals": "0", "counterpart": "backup/a", "label": "offsite"},
                {"dataset": "tank/b", "comment": "existing"},
            ],
        }
        result = config_migrations._migrate_17_to_18(config)
        self.assertEqual(result["config_version"], 18)
        self.assertEqual(len(result["checkagainst"]["user_entries"]), 2)
        self.assertEqual(result["checkagainst"]["user_entries"][0]["dataset"], "tank/a")
        self.assertEqual(result["checkagainst"]["user_entries"][1]["comment"], "existing")
        self.assertTrue(result["checkagainst"]["backup_derived_active"])
        self.assertTrue(result["checkagainst"]["offsite_derived_active"])
        self.assertEqual(result["checkagainst"]["backup_derived"], [])
        self.assertEqual(result["checkagainst"]["offsite_derived"], [])

    def test_migrate_17_to_18_idempotent_for_nested_dict(self):
        config = {
            "config_version": 17,
            "checkagainst": {
                "backup_derived_active": False,
                "offsite_derived_active": False,
                "backup_derived": [
                    {"dataset": "src", "quals": "0", "counterpart": "dst", "label": "dailybackup"}
                ],
                "offsite_derived": [],
                "user_entries": [
                    {
                        "dataset": "tank/a",
                        "quals": "0",
                        "counterpart": "backup/a",
                        "label": "offsite",
                    }
                ],
            },
        }
        result = config_migrations._migrate_17_to_18(dict(config))
        self.assertEqual(result["config_version"], 18)
        self.assertEqual(result["checkagainst"], config["checkagainst"])

    def test_migrate_17_to_18_initializes_defaults_when_missing(self):
        config = {"config_version": 17}
        result = config_migrations._migrate_17_to_18(config)
        self.assertEqual(result["config_version"], 18)
        self.assertTrue(result["checkagainst"]["backup_derived_active"])
        self.assertTrue(result["checkagainst"]["offsite_derived_active"])
        self.assertEqual(result["checkagainst"]["backup_derived"], [])
        self.assertEqual(result["checkagainst"]["offsite_derived"], [])
        self.assertEqual(result["checkagainst"]["user_entries"], [])

    def test_migrate_18_to_19_converts_legacy_checkagainst_rows(self):
        config = {
            "config_version": 18,
            "checkagainst": {
                "backup_derived": [
                    {
                        "dataset": "tank/a",
                        "quals": "0",
                        "counterpart": "backup/a",
                        "label": "daily",
                    },
                ],
                "offsite_derived": [],
                "user_entries": [
                    {
                        "dataset": "fivebays/src",
                        "quals": "1",
                        "counterpart": "-",
                        "label": "offsite",
                    },
                ],
            },
        }
        result = config_migrations._migrate_18_to_19(config)
        self.assertEqual(result["config_version"], 19)
        self.assertEqual(result["checkagainst"]["backup_derived"][0]["source_root"], "tank/a")
        self.assertEqual(
            result["checkagainst"]["backup_derived"][0]["dest_root"], "backup/a/tank/a"
        )
        self.assertEqual(result["checkagainst"]["user_entries"][0]["source_root"], "fivebays/src")
        self.assertEqual(result["checkagainst"]["user_entries"][0]["dest_root"], "src")

    def test_migrate_18_to_19_idempotent_for_new_rows(self):
        config = {
            "config_version": 18,
            "checkagainst": {
                "user_entries": [
                    {"source_root": "tank/a", "dest_root": "backup/a", "label": "daily"},
                ],
            },
        }
        result = config_migrations._migrate_18_to_19(config)
        self.assertEqual(result["config_version"], 19)
        row = result["checkagainst"]["user_entries"][0]
        self.assertEqual(row["source_root"], "tank/a")
        self.assertEqual(row["dest_root"], "backup/a")
        self.assertEqual(row["label"], "daily")

    def test_migrate_23_to_24_regenerates_checkagainst_derived_rows(self):
        config = {
            "config_version": 23,
            "backup": {
                "variables": {"label": "dailybackup"},
                "send_receive_steps": [
                    {"active": True, "source": "threeamigos/proxmox", "dest": "fivebays"},
                ],
            },
            "offsite": {
                "steps": [
                    {"active": True, "source": "fivebays", "dest": "<offsite>"},
                ],
            },
            "checkagainst": {
                "backup_derived_active": True,
                "offsite_derived_active": True,
                "backup_derived": [
                    {"source_root": "stale", "dest_root": "stale", "label": "dailybackup"}
                ],
                "offsite_derived": [
                    {"source_root": "<offsite>", "dest_root": "fivebays", "label": "offsite"}
                ],
                "user_entries": [
                    {"source_root": "user/a", "dest_root": "user/b", "label": "offsite"}
                ],
            },
        }
        result = config_migrations._migrate_23_to_24(config)
        self.assertEqual(result["config_version"], 24)
        self.assertEqual(
            result["checkagainst"]["backup_derived"],
            [
                {
                    "source_root": "threeamigos/proxmox",
                    "dest_root": "fivebays/threeamigos/proxmox",
                    "label": "dailybackup",
                },
                {
                    "source_root": "fivebays/threeamigos/proxmox",
                    "dest_root": "threeamigos/proxmox",
                    "label": "dailybackup",
                },
            ],
        )
        self.assertEqual(
            result["checkagainst"]["offsite_derived"],
            [
                {
                    "source_root": "fivebays",
                    "dest_root": "<offsite>/fivebays",
                    "label": "offsite",
                },
                {
                    "source_root": "<offsite>/fivebays",
                    "dest_root": "fivebays",
                    "label": "offsite",
                },
            ],
        )
        self.assertEqual(
            result["checkagainst"]["user_entries"],
            [{"source_root": "user/a", "dest_root": "user/b", "label": "offsite"}],
        )
        self.assertTrue(result["checkagainst"]["backup_derived_active"])
        self.assertTrue(result["checkagainst"]["offsite_derived_active"])

    def test_run_migrations_from_version_14(self):
        config = {
            "config_version": 14,
            "checkagainst": [
                {"dataset": "tank/a", "quals": "0", "counterpart": "backup/a", "label": "offsite"},
            ],
            "offsite": {"offsite_pools": ["z40tb"]},
        }
        result = config_migrations.run_migrations(config)
        self.assertEqual(result["config_version"], 24)
        self.assertNotIn("offsite_pools", result.get("offsite", {}))
        self.assertEqual(result["dashboard"]["refresh_seconds"], 30)
        row = result["checkagainst"]["user_entries"][0]
        self.assertEqual(row["source_root"], "tank/a")
        self.assertEqual(row["dest_root"], "backup/a/tank/a")
        self.assertEqual(row["label"], "offsite")
        self.assertEqual(row["comment"], "")
        self.assertTrue(result["checkagainst"]["backup_derived_active"])
        self.assertTrue(result["checkagainst"]["offsite_derived_active"])
        self.assertEqual(result["checkagainst"]["backup_derived"], [])
        self.assertEqual(result["checkagainst"]["offsite_derived"], [])
        self.assertEqual(result["prune_pools_order"], [])
        self.assertFalse(result["backup"]["pause_scrubs"])
        self.assertFalse(result["offsite"]["pause_scrubs"])
        self.assertFalse(result["restore"]["pause_scrubs"])
        self.assertEqual(result["backup"]["pull_steps"], [])

    def test_run_migrations_from_version_19(self):
        config = {
            "config_version": 19,
            "offsite": {
                "offsite_pools": ["z40tb", "z22tb"],
                "variables": {},
                "steps": [],
            },
        }
        result = config_migrations.run_migrations(config)
        self.assertEqual(result["config_version"], 24)
        self.assertIn("retention_verb_messages", result)
        self.assertIs(result["retention_verb_messages"], False)
        self.assertNotIn("offsite_pools", result.get("offsite", {}))
        self.assertEqual(result["dashboard"]["refresh_seconds"], 30)


if __name__ == "__main__":
    unittest.main()

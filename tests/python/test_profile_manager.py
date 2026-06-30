"""Tests for profile_manager.py — profile CRUD operations."""

import os
import unittest

from test_support import temp_config_dir, capture_logs

import profile_manager


class TestValidateCustomName(unittest.TestCase):

    def test_valid_name(self):
        profile_manager.validate_custom_name("daily_backup")
        profile_manager.validate_custom_name("backup-123")

    def test_empty_name_raises(self):
        with self.assertRaises(ValueError):
            profile_manager.validate_custom_name("")

    def test_space_raises(self):
        with self.assertRaises(ValueError):
            profile_manager.validate_custom_name("daily backup")

    def test_special_char_raises(self):
        with self.assertRaises(ValueError):
            profile_manager.validate_custom_name("backup@home")


class TestBuildProfileName(unittest.TestCase):

    def test_builds_correctly(self):
        name = profile_manager.build_profile_name("root", "backup", "daily")
        self.assertEqual(name, "root-backup-daily")

    def test_builds_scrub_type(self):
        name = profile_manager.build_profile_name("root", "scrub", "weekly")
        self.assertEqual(name, "root-scrub-weekly")


class TestProfileCrud(unittest.TestCase):

    def test_create_and_load(self):
        with temp_config_dir():
            with capture_logs() as logs:
                profile = profile_manager.create_profile("backup", "test1", {"variables": {"label": "x"}})
            self.assertEqual(profile["profile_name"], f"{profile_manager.get_user()}-backup-test1")
            loaded = profile_manager.load_profile(profile["profile_name"])
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["tab_type"], "backup")
            self.assertTrue(
                any(f"Created profile: {profile['profile_name']}" in msg for msg in logs)
            )

    def test_list_profiles_sorted(self):
        with temp_config_dir():
            p1 = profile_manager.create_profile("backup", "alpha", {"foo": 1})
            p2 = profile_manager.create_profile("backup", "beta", {"foo": 2})
            profiles = profile_manager.list_profiles()
            names = [p["profile_name"] for p in profiles]
            self.assertEqual(names, sorted(names))

    def test_delete_profile(self):
        with temp_config_dir():
            profile = profile_manager.create_profile("backup", "delme", {})
            name = profile["profile_name"]
            self.assertTrue(profile_manager.profile_exists(name))
            result = profile_manager.delete_profile(name)
            self.assertTrue(result)
            self.assertFalse(profile_manager.profile_exists(name))

    def test_delete_missing_returns_false(self):
        with temp_config_dir():
            result = profile_manager.delete_profile("nonexistent")
            self.assertFalse(result)

    def test_duplicate_name_raises(self):
        with temp_config_dir():
            profile_manager.create_profile("backup", "dup", {})
            with self.assertRaises(ValueError):
                profile_manager.create_profile("backup", "dup", {})

    def test_dry_run_default_false(self):
        with temp_config_dir():
            profile = profile_manager.create_profile("backup", "dry", {})
            self.assertFalse(profile.get("dry_run", True))
            loaded = profile_manager.load_profile(profile["profile_name"])
            self.assertFalse(loaded.get("dry_run", True))

    def test_dry_run_stored_true(self):
        with temp_config_dir():
            profile = profile_manager.create_profile(
                "backup", "dry", {}, dry_run=True
            )
            self.assertTrue(profile.get("dry_run", False))
            loaded = profile_manager.load_profile(profile["profile_name"])
            self.assertTrue(loaded.get("dry_run", False))

    def test_save_profile(self):
        with temp_config_dir():
            profile = profile_manager.create_profile("backup", "saveme", {})
            profile["extra"] = "data"
            profile_manager.save_profile(profile)
            loaded = profile_manager.load_profile(profile["profile_name"])
            self.assertEqual(loaded["extra"], "data")

    def test_update_profile(self):
        with temp_config_dir():
            original = profile_manager.create_profile(
                "backup", "updatable", {"variables": {"label": "old"}}
            )
            original["cron"] = {"minute": "30"}
            original["active"] = True
            profile_manager.save_profile(original)

            updated = profile_manager.update_profile(
                "backup", "updatable", {"variables": {"label": "new"}}, dry_run=True
            )

            self.assertEqual(updated["config"], {"variables": {"label": "new"}})
            self.assertTrue(updated["dry_run"])
            self.assertEqual(updated["cron"], {"minute": "30"})
            self.assertTrue(updated["active"])
            self.assertIn("updated_at", updated)
            loaded = profile_manager.load_profile(updated["profile_name"])
            self.assertEqual(loaded["config"]["variables"]["label"], "new")

    def test_update_missing_profile_raises(self):
        with temp_config_dir():
            with self.assertRaises(ValueError):
                profile_manager.update_profile("backup", "missing", {})

    def test_delete_profile_logs(self):
        with temp_config_dir():
            profile = profile_manager.create_profile("backup", "deleteme", {})
            name = profile["profile_name"]
            with capture_logs() as logs:
                profile_manager.delete_profile(name)
            self.assertTrue(any(f"Deleted profile: {name}" in msg for msg in logs))


class TestGetUser(unittest.TestCase):

    def test_returns_string(self):
        user = profile_manager.get_user()
        self.assertIsInstance(user, str)
        self.assertTrue(user)


if __name__ == "__main__":
    unittest.main()

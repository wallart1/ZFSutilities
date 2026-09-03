"""Tests for workload_profiles.py — pure-logic profile helpers."""

import os
import sys
import unittest

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from workload_profiles import (
    ALL_KNOWN_PROPERTIES,
    CREATION_ONLY_PROPERTIES,
    LIVE_PROPERTIES,
    ZFS_GET_PROPERTIES,
    build_apply_plan,
    build_zfs_set_commands,
    match_profile,
    profile_has_warning,
    properties_for_profile,
    warning_text,
)


class TestPropertiesForProfile(unittest.TestCase):
    """properties_for_profile filters by dataset type."""

    def test_filters_by_type(self):
        profile = {
            "applies_to": ["filesystem"],
            "properties": {
                "recordsize": "128K",
                "volblocksize": "16K",
            },
        }
        self.assertEqual(
            properties_for_profile(profile, "filesystem"),
            {"recordsize": "128K"},
        )
        self.assertEqual(properties_for_profile(profile, "volume"), {})

    def test_volume_skips_recordsize_and_atime(self):
        profile = {
            "applies_to": ["volume"],
            "properties": {
                "recordsize": "128K",
                "atime": "off",
                "compression": "zstd",
                "volblocksize": "16K",
            },
        }
        self.assertEqual(
            properties_for_profile(profile, "volume"),
            {"compression": "zstd", "volblocksize": "16K"},
        )

    def test_unknown_properties_ignored(self):
        profile = {
            "applies_to": ["filesystem"],
            "properties": {"recordsize": "128K", "custom_prop": "x"},
        }
        self.assertEqual(
            properties_for_profile(profile, "filesystem"),
            {"recordsize": "128K"},
        )

    def test_missing_applies_to_returns_empty(self):
        profile = {"properties": {"recordsize": "128K"}}
        self.assertEqual(properties_for_profile(profile, "filesystem"), {})

    def test_ashift_returned_as_informational_property(self):
        profile = {
            "applies_to": ["filesystem"],
            "properties": {"ashift": "12"},
        }
        self.assertEqual(properties_for_profile(profile, "filesystem"), {"ashift": "12"})

    def test_filesystem_skips_volblocksize(self):
        profile = {
            "applies_to": ["filesystem"],
            "properties": {"recordsize": "128K", "volblocksize": "16K"},
        }
        self.assertEqual(
            properties_for_profile(profile, "filesystem"),
            {"recordsize": "128K"},
        )


class TestMatchProfile(unittest.TestCase):
    """match_profile selects the first fully-matching profile."""

    def test_match_profile_exact_filesystem(self):
        profiles = {
            "general": {
                "applies_to": ["filesystem"],
                "properties": {
                    "recordsize": "128K",
                    "compression": "zstd",
                    "atime": "on",
                },
            }
        }
        live = {"recordsize": "128K", "compression": "zstd", "atime": "on"}
        self.assertEqual(match_profile(profiles, "filesystem", live), "general")

    def test_match_profile_exact_volume(self):
        profiles = {
            "vm-chaindata-ext4": {
                "applies_to": ["volume"],
                "properties": {
                    "compression": "zstd",
                    "volblocksize": "4K",
                },
            }
        }
        live = {"compression": "zstd", "volblocksize": "4K"}
        self.assertEqual(match_profile(profiles, "volume", live), "vm-chaindata-ext4")

    def test_match_profile_single_mismatch_returns_custom(self):
        profiles = {
            "general": {
                "applies_to": ["filesystem"],
                "properties": {
                    "recordsize": "128K",
                    "compression": "zstd",
                },
            }
        }
        live = {"recordsize": "128K", "compression": "lz4"}
        self.assertEqual(match_profile(profiles, "filesystem", live), "custom")

    def test_match_profile_ignores_creation_only_mismatch(self):
        profiles = {
            "vm-chaindata-ext4": {
                "applies_to": ["volume"],
                "properties": {
                    "compression": "zstd",
                    "volblocksize": "4K",
                },
            }
        }
        live = {"compression": "zstd", "volblocksize": "8K"}
        self.assertEqual(match_profile(profiles, "volume", live), "vm-chaindata-ext4")

    def test_match_profile_skips_properties_incompatible_with_type(self):
        profiles = {
            "general": {
                "applies_to": ["filesystem", "volume"],
                "properties": {
                    "recordsize": "128K",
                    "compression": "zstd",
                },
            }
        }
        live = {"compression": "zstd"}
        self.assertEqual(match_profile(profiles, "volume", live), "general")

    def test_match_profile_empty_profiles_returns_custom(self):
        self.assertEqual(match_profile({}, "filesystem", {"compression": "zstd"}), "custom")


class TestBuildApplyPlan(unittest.TestCase):
    """build_apply_plan marks which properties will be applied."""

    def _profile(self):
        return {
            "applies_to": ["filesystem", "volume"],
            "properties": {
                "recordsize": "128K",
                "compression": "zstd",
                "volblocksize": "16K",
            },
        }

    def test_marks_live_properties_applyable(self):
        plan = build_apply_plan(self._profile(), "tank/data", "filesystem", {"compression": "lz4"})
        by_prop = {e["property"]: e for e in plan}
        self.assertTrue(by_prop["compression"]["will_apply"])
        self.assertIn("will change", by_prop["compression"]["explanation"])

    def test_marks_creation_only_non_applyable(self):
        plan = build_apply_plan(self._profile(), "tank/data", "volume", {"compression": "zstd"})
        by_prop = {e["property"]: e for e in plan}
        self.assertFalse(by_prop["volblocksize"]["will_apply"])
        self.assertIn("fixed at dataset creation", by_prop["volblocksize"]["explanation"])

    def test_skips_type_incompatible_properties(self):
        plan = build_apply_plan(self._profile(), "tank/data", "volume", {"compression": "zstd"})
        by_prop = {e["property"]: e for e in plan}
        self.assertFalse(by_prop["recordsize"]["will_apply"])
        self.assertIn("does not apply to volume", by_prop["recordsize"]["explanation"])

    def test_notes_already_set(self):
        plan = build_apply_plan(self._profile(), "tank/data", "filesystem", {"compression": "zstd"})
        by_prop = {e["property"]: e for e in plan}
        self.assertFalse(by_prop["compression"]["will_apply"])
        self.assertIn("already set", by_prop["compression"]["explanation"])

    def test_skips_all_properties_when_type_not_applicable(self):
        profile = {
            "applies_to": ["filesystem"],
            "properties": {"recordsize": "128K"},
        }
        plan = build_apply_plan(profile, "tank/data", "volume", {})
        for entry in plan:
            self.assertFalse(entry["will_apply"])
            self.assertIn("does not apply", entry["explanation"])


class TestBuildZfsSetCommands(unittest.TestCase):
    """build_zfs_set_commands emits commands only for will_apply entries."""

    def test_includes_only_will_apply(self):
        plan = [
            {
                "property": "compression",
                "value": "zstd",
                "dataset": "tank/data",
                "will_apply": True,
            },
            {
                "property": "recordsize",
                "value": "128K",
                "dataset": "tank/data",
                "will_apply": False,
            },
        ]
        commands = build_zfs_set_commands(plan)
        self.assertEqual(commands, ["zfs set compression=zstd tank/data"])


class TestWarnings(unittest.TestCase):
    """profile_has_warning and warning_text."""

    def test_profile_has_warning_scratch(self):
        profile = {"notes": "Can lose data."}
        self.assertTrue(profile_has_warning("scratch", profile, True))
        self.assertTrue(profile_has_warning("scratch", profile, False))

    def test_profile_has_warning_small_files_without_special(self):
        profile = {"notes": "Needs special vdev."}
        self.assertTrue(profile_has_warning("small-files", profile, False))
        self.assertFalse(profile_has_warning("small-files", profile, True))

    def test_profile_has_warning_general(self):
        profile = {}
        self.assertFalse(profile_has_warning("general", profile, False))

    def test_warning_text_returns_notes_for_scratch(self):
        profile = {"notes": "Can lose data."}
        self.assertEqual(warning_text("scratch", profile, False), "Can lose data.")

    def test_warning_text_returns_notes_for_small_files_without_special(self):
        profile = {"notes": "Needs special vdev."}
        self.assertEqual(warning_text("small-files", profile, False), "Needs special vdev.")

    def test_warning_text_returns_none_when_no_warning(self):
        profile = {}
        self.assertIsNone(warning_text("general", profile, False))


class TestConstants(unittest.TestCase):
    """Module constants group properties correctly."""

    def test_creation_only_not_in_live(self):
        for prop in CREATION_ONLY_PROPERTIES:
            self.assertNotIn(prop, LIVE_PROPERTIES)

    def test_all_known_is_union(self):
        self.assertEqual(
            set(ALL_KNOWN_PROPERTIES),
            set(LIVE_PROPERTIES) | set(CREATION_ONLY_PROPERTIES),
        )

    def test_zfs_get_properties_excludes_ashift(self):
        """ZFS_GET_PROPERTIES contains only properties valid for zfs get."""
        self.assertIn("recordsize", ZFS_GET_PROPERTIES)
        self.assertIn("volblocksize", ZFS_GET_PROPERTIES)
        self.assertIn("ashift", ALL_KNOWN_PROPERTIES)
        self.assertNotIn("ashift", ZFS_GET_PROPERTIES)


if __name__ == "__main__":
    unittest.main()

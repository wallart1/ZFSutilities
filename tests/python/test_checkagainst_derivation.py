"""Tests for checkagainst derivation, merge, and strip helpers."""

import unittest

from feature_config import (
    _compute_strip_segments,
    add_checkagainst_entry,
    derive_checkagainst_entries,
    get_checkagainst,
    merge_checkagainst_entries,
)


class TestComputeStripSegments(unittest.TestCase):

    def test_no_common_suffix_returns_zero_and_destination(self):
        self.assertEqual(
            _compute_strip_segments("poolA/data", "poolB/other"),
            (0, "poolB/other"),
        )

    def test_common_suffix_gives_zero_strip_and_prefix(self):
        self.assertEqual(
            _compute_strip_segments(
                "threeamigos/proxmox", "fivebays/threeamigos/proxmox"
            ),
            (0, "fivebays"),
        )

    def test_nested_source_gives_one_strip_and_null_prefix(self):
        self.assertEqual(
            _compute_strip_segments(
                "fivebays/threeamigos/proxmox", "threeamigos/proxmox"
            ),
            (1, "-"),
        )


class TestDeriveCheckagainstEntries(unittest.TestCase):

    def test_backup_forward_and_reverse_rows(self):
        config = {
            "backup": {
                "variables": {"label": "dailybackup"},
                "send_receive_steps": [
                    {"active": True, "source": "threeamigos/proxmox", "dest": "fivebays/threeamigos/proxmox"},
                ],
            },
            "offsite": {"steps": []},
        }
        backup_derived, offsite_derived = derive_checkagainst_entries(config)
        self.assertEqual(offsite_derived, [])
        self.assertEqual(backup_derived, [
            {"dataset": "threeamigos/proxmox", "quals": "0", "counterpart": "fivebays/threeamigos/proxmox", "label": "dailybackup"},
            {"dataset": "fivebays/threeamigos/proxmox", "quals": "1", "counterpart": "-", "label": "dailybackup"},
        ])

    def test_offsite_rows_use_offsite_label(self):
        config = {
            "backup": {"variables": {"label": "dailybackup"}, "send_receive_steps": []},
            "offsite": {
                "steps": [
                    {"active": True, "source": "fivebays/threeamigos/proxmox", "dest": "<offsite>/threeamigos/proxmox"},
                ],
            },
        }
        backup_derived, offsite_derived = derive_checkagainst_entries(config)
        self.assertEqual(backup_derived, [])
        self.assertEqual(offsite_derived, [
            {"dataset": "fivebays/threeamigos/proxmox", "quals": "0", "counterpart": "<offsite>/threeamigos/proxmox", "label": "offsite"},
            {"dataset": "<offsite>/threeamigos/proxmox/fivebays/threeamigos/proxmox", "quals": "3", "counterpart": "-", "label": "offsite"},
        ])

    def test_inactive_and_empty_steps_are_skipped(self):
        config = {
            "backup": {
                "variables": {"label": "dailybackup"},
                "send_receive_steps": [
                    {"active": False, "source": "poolA/a", "dest": "poolB/a"},
                    {"active": True, "source": "", "dest": "poolB/b"},
                    {"active": True, "source": "poolC/c", "dest": "  "},
                ],
            },
            "offsite": {"steps": []},
        }
        backup_derived, _ = derive_checkagainst_entries(config)
        self.assertEqual(backup_derived, [])

    def test_deduplication_within_section(self):
        config = {
            "backup": {
                "variables": {"label": "dailybackup"},
                "send_receive_steps": [
                    {"active": True, "source": "poolA/a", "dest": "poolB/a"},
                    {"active": True, "source": "poolA/a", "dest": "poolB/a"},
                ],
            },
            "offsite": {"steps": []},
        }
        backup_derived, _ = derive_checkagainst_entries(config)
        self.assertEqual(len(backup_derived), 2)

    def test_reverse_row_computes_non_null_counterpart(self):
        """When dest is just a pool root, reverse row still yields a valid path."""
        config = {
            "backup": {
                "variables": {"label": "dailybackup"},
                "send_receive_steps": [
                    {"active": True, "source": "threeamigos/proxmox", "dest": "fivebays"},
                ],
            },
            "offsite": {"steps": []},
        }
        backup_derived, _ = derive_checkagainst_entries(config)
        self.assertEqual(backup_derived, [
            {"dataset": "threeamigos/proxmox", "quals": "0", "counterpart": "fivebays", "label": "dailybackup"},
            {"dataset": "fivebays/threeamigos/proxmox", "quals": "1", "counterpart": "-", "label": "dailybackup"},
        ])


class TestMergeCheckagainstEntries(unittest.TestCase):

    def _make_config(self, backup_derived=None, offsite_derived=None, user_entries=None,
                     backup_active=True, offsite_active=True):
        return {
            "checkagainst": {
                "backup_derived_active": backup_active,
                "offsite_derived_active": offsite_active,
                "backup_derived": backup_derived or [],
                "offsite_derived": offsite_derived or [],
                "user_entries": user_entries or [],
            },
        }

    def test_user_overrides_offsite_overrides_backup(self):
        config = self._make_config(
            backup_derived=[
                {"dataset": "tank/a", "quals": "0", "counterpart": "backup/a", "label": "dailybackup"},
            ],
            offsite_derived=[
                {"dataset": "tank/a", "quals": "0", "counterpart": "offsite/a", "label": "dailybackup"},
            ],
            user_entries=[
                {"dataset": "tank/a", "quals": "0", "counterpart": "user/a", "label": "dailybackup"},
            ],
        )
        merged = merge_checkagainst_entries(config)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["counterpart"], "user/a")

    def test_offsite_overrides_backup(self):
        config = self._make_config(
            backup_derived=[
                {"dataset": "tank/a", "quals": "0", "counterpart": "backup/a", "label": "dailybackup"},
            ],
            offsite_derived=[
                {"dataset": "tank/a", "quals": "0", "counterpart": "offsite/a", "label": "dailybackup"},
            ],
        )
        merged = merge_checkagainst_entries(config)
        self.assertEqual(merged[0]["counterpart"], "offsite/a")

    def test_inactive_flags_exclude_sections(self):
        config = self._make_config(
            backup_derived=[
                {"dataset": "tank/a", "quals": "0", "counterpart": "backup/a", "label": "dailybackup"},
            ],
            offsite_derived=[
                {"dataset": "tank/b", "quals": "0", "counterpart": "offsite/b", "label": "offsite"},
            ],
            backup_active=False,
            offsite_active=False,
        )
        merged = merge_checkagainst_entries(config)
        self.assertEqual(merged, [])


class TestGetCheckagainst(unittest.TestCase):

    def test_creates_defaults_when_missing(self):
        config = {}
        data = get_checkagainst(config)
        self.assertTrue(data["backup_derived_active"])
        self.assertTrue(data["offsite_derived_active"])
        self.assertEqual(data["backup_derived"], [])
        self.assertEqual(data["offsite_derived"], [])
        self.assertEqual(data["user_entries"], [])

    def test_wraps_flat_list_backward_compatible(self):
        config = {"checkagainst": [{"dataset": "tank/a", "label": "offsite"}]}
        data = get_checkagainst(config)
        self.assertEqual(data["user_entries"], [{"dataset": "tank/a", "label": "offsite"}])


class TestAddCheckagainstEntry(unittest.TestCase):

    def test_adds_new_row(self):
        config = {"checkagainst": {"user_entries": []}}
        added = add_checkagainst_entry(
            config,
            {"dataset": "tank/a", "quals": "0", "counterpart": "backup/a", "label": "offsite"},
        )
        self.assertTrue(added)
        self.assertEqual(len(config["checkagainst"]["user_entries"]), 1)

    def test_skips_duplicate(self):
        config = {"checkagainst": {"user_entries": [
            {"dataset": "tank/a", "quals": "0", "counterpart": "backup/a", "label": "offsite"},
        ]}}
        added = add_checkagainst_entry(
            config,
            {"dataset": "tank/a", "quals": "1", "counterpart": "backup/a", "label": "offsite"},
        )
        self.assertFalse(added)
        self.assertEqual(len(config["checkagainst"]["user_entries"]), 1)


if __name__ == "__main__":
    unittest.main()

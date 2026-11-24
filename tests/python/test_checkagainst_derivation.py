"""Tests for checkagainst derivation, merge, and source/dest-root helpers."""

import unittest

from feature_config import (
    _compute_destination_root,
    _normalize_checkagainst_row,
    add_checkagainst_entry,
    derive_checkagainst_entries,
    get_checkagainst,
    merge_checkagainst_entries,
    refresh_checkagainst_derived,
)
from test_support import temp_config_dir


class TestComputeDestinationRoot(unittest.TestCase):
    def test_pool_root_destination_appends_source(self):
        self.assertEqual(
            _compute_destination_root("threeamigos/proxmox", "fivebays"),
            "fivebays/threeamigos/proxmox",
        )

    def test_destination_already_ends_with_source_suffix(self):
        self.assertEqual(
            _compute_destination_root("threeamigos/proxmox", "fivebays/threeamigos/proxmox"),
            "fivebays/threeamigos/proxmox",
        )

    def test_offsite_wildcard_matches_source_suffix(self):
        self.assertEqual(
            _compute_destination_root(
                "fivebays/threeamigos/proxmox", "<offsite>/threeamigos/proxmox"
            ),
            "<offsite>/threeamigos/proxmox",
        )

    def test_no_common_suffix_appends_source(self):
        self.assertEqual(
            _compute_destination_root("poolA/data", "poolB/other"),
            "poolB/other/poolA/data",
        )


class TestNormalizeCheckagainstRow(unittest.TestCase):
    def test_new_format_row_passes_through(self):
        row = {"source_root": "a", "dest_root": "b", "label": "offsite"}
        self.assertEqual(_normalize_checkagainst_row(row), row)

    def test_legacy_strip_zero_counterpart(self):
        self.assertEqual(
            _normalize_checkagainst_row(
                {
                    "dataset": "threeamigos/proxmox",
                    "quals": "0",
                    "counterpart": "fivebays",
                    "label": "dailybackup",
                }
            ),
            {
                "source_root": "threeamigos/proxmox",
                "dest_root": "fivebays/threeamigos/proxmox",
                "label": "dailybackup",
            },
        )

    def test_legacy_strip_two_null_prepend(self):
        self.assertEqual(
            _normalize_checkagainst_row(
                {
                    "dataset": "fivebays/threeamigos/proxmox",
                    "quals": "2",
                    "counterpart": "threeamigos",
                    "label": "dailybackup",
                }
            ),
            {
                "source_root": "fivebays/threeamigos/proxmox",
                "dest_root": "threeamigos/proxmox",
                "label": "dailybackup",
            },
        )

    def test_legacy_strip_pool_root(self):
        self.assertEqual(
            _normalize_checkagainst_row(
                {
                    "dataset": "threeamigos",
                    "quals": "0",
                    "counterpart": "fivebays",
                    "label": "dailybackup",
                }
            ),
            {
                "source_root": "threeamigos",
                "dest_root": "fivebays/threeamigos",
                "label": "dailybackup",
            },
        )

    def test_legacy_null_prepend_counterpart_dash(self):
        self.assertEqual(
            _normalize_checkagainst_row(
                {
                    "dataset": "fivebays/threeamigos/proxmox",
                    "quals": "1",
                    "counterpart": "-",
                    "label": "dailybackup",
                }
            ),
            {
                "source_root": "fivebays/threeamigos/proxmox",
                "dest_root": "threeamigos/proxmox",
                "label": "dailybackup",
            },
        )


class TestDeriveCheckagainstEntries(unittest.TestCase):
    def test_backup_forward_and_reverse_rows(self):
        config = {
            "backup": {
                "variables": {"label": "dailybackup"},
                "send_receive_steps": [
                    {
                        "active": True,
                        "source": "threeamigos/proxmox",
                        "dest": "fivebays/threeamigos/proxmox",
                    },
                ],
            },
            "offsite": {"steps": []},
        }
        backup_derived, offsite_derived = derive_checkagainst_entries(config)
        self.assertEqual(offsite_derived, [])
        self.assertEqual(
            backup_derived,
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

    def test_offsite_rows_use_offsite_label(self):
        config = {
            "backup": {"variables": {"label": "dailybackup"}, "send_receive_steps": []},
            "offsite": {
                "steps": [
                    {
                        "active": True,
                        "source": "fivebays/threeamigos/proxmox",
                        "dest": "<offsite>/threeamigos/proxmox",
                    },
                ],
            },
        }
        backup_derived, offsite_derived = derive_checkagainst_entries(config)
        self.assertEqual(backup_derived, [])
        self.assertEqual(
            offsite_derived,
            [
                {
                    "source_root": "fivebays/threeamigos/proxmox",
                    "dest_root": "<offsite>/threeamigos/proxmox",
                    "label": "offsite",
                },
                {
                    "source_root": "<offsite>/threeamigos/proxmox",
                    "dest_root": "fivebays/threeamigos/proxmox",
                    "label": "offsite",
                },
            ],
        )

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
        # Three unique rows (forward, reverse, and the manifest store —
        # poolB/a/poolA/a does not cover poolB/a/poolA/zfsutilities-manifests)
        # from six raw emissions proves the dedup.
        self.assertEqual(len(backup_derived), 3)

    def test_reverse_row_computes_non_null_counterpart(self):
        """When dest is just a pool root, reverse row still yields a valid path.

        The step's manifest store is a sibling of the mapped dataset, so it
        gets its own row naming the never-existing source-side counterpart.
        """
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
        self.assertEqual(
            backup_derived,
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
                {
                    "source_root": "fivebays/threeamigos/zfsutilities-manifests",
                    "dest_root": "threeamigos/zfsutilities-manifests",
                    "label": "dailybackup",
                },
            ],
        )

    def test_manifest_store_row_for_sub_pool_steps(self):
        """Sub-pool steps emit a store row; pool-level steps need none.

        Production shape: the reverse row of a pool-level step (NVME1)
        already covers its store, while leaf-mapped steps leave the store
        (a sibling of the mapped datasets) uncovered without its own row.
        """
        config = {
            "backup": {
                "variables": {"label": "dailybackup"},
                "send_receive_steps": [
                    {"active": True, "source": "threeamigos/proxmox", "dest": "fivebays"},
                    {"active": True, "source": "threeamigos/zfsutilities", "dest": "fivebays"},
                    {"active": True, "source": "NVME1", "dest": "fivebays"},
                ],
            },
            "offsite": {"steps": []},
        }
        backup_derived, _ = derive_checkagainst_entries(config)
        store_rows = [
            row for row in backup_derived if row["source_root"].endswith("/zfsutilities-manifests")
        ]
        self.assertEqual(
            store_rows,
            [
                {
                    "source_root": "fivebays/threeamigos/zfsutilities-manifests",
                    "dest_root": "threeamigos/zfsutilities-manifests",
                    "label": "dailybackup",
                },
            ],
        )

    def test_store_under_dest_root_needs_no_row(self):
        """A store already covered by the reverse row's source root is skipped."""
        config = {
            "backup": {
                "variables": {"label": "dailybackup"},
                "send_receive_steps": [
                    {"active": True, "source": "NVME1", "dest": "fivebays"},
                ],
            },
            "offsite": {"steps": []},
        }
        backup_derived, _ = derive_checkagainst_entries(config)
        self.assertEqual(
            backup_derived,
            [
                {
                    "source_root": "NVME1",
                    "dest_root": "fivebays/NVME1",
                    "label": "dailybackup",
                },
                {
                    "source_root": "fivebays/NVME1",
                    "dest_root": "NVME1",
                    "label": "dailybackup",
                },
            ],
        )

    def test_offsite_pool_root_step_appends_source(self):
        """Offsite step to bare <offsite> must produce <offsite>/source paths."""
        config = {
            "backup": {"variables": {"label": "dailybackup"}, "send_receive_steps": []},
            "offsite": {
                "steps": [
                    {"active": True, "source": "fivebays", "dest": "<offsite>"},
                ],
            },
        }
        _, offsite_derived = derive_checkagainst_entries(config)
        self.assertEqual(
            offsite_derived,
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


class TestRefreshCheckagainstDerived(unittest.TestCase):
    def test_refreshes_derived_rows_and_preserves_user_entries(self):
        config = {
            "backup": {
                "variables": {"label": "dailybackup"},
                "send_receive_steps": [
                    {"active": True, "source": "threeamigos/proxmox", "dest": "fivebays"},
                ],
            },
            "offsite": {"steps": []},
            "checkagainst": {
                "backup_derived_active": True,
                "offsite_derived_active": True,
                "backup_derived": [
                    {"source_root": "stale", "dest_root": "stale", "label": "dailybackup"}
                ],
                "offsite_derived": [{"source_root": "old", "dest_root": "old", "label": "offsite"}],
                "user_entries": [
                    {"source_root": "user/a", "dest_root": "user/b", "label": "dailybackup"}
                ],
            },
        }
        refresh_checkagainst_derived(config)
        self.assertEqual(
            config["checkagainst"]["backup_derived"],
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
                {
                    "source_root": "fivebays/threeamigos/zfsutilities-manifests",
                    "dest_root": "threeamigos/zfsutilities-manifests",
                    "label": "dailybackup",
                },
            ],
        )
        self.assertEqual(config["checkagainst"]["offsite_derived"], [])
        self.assertEqual(
            config["checkagainst"]["user_entries"],
            [{"source_root": "user/a", "dest_root": "user/b", "label": "dailybackup"}],
        )


class TestMergeCheckagainstEntries(unittest.TestCase):
    def _make_config(
        self,
        backup_derived=None,
        offsite_derived=None,
        user_entries=None,
        backup_active=True,
        offsite_active=True,
    ):
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
                {"source_root": "tank/a", "dest_root": "backup/a", "label": "dailybackup"},
            ],
            offsite_derived=[
                {"source_root": "tank/a", "dest_root": "offsite/a", "label": "dailybackup"},
            ],
            user_entries=[
                {"source_root": "tank/a", "dest_root": "user/a", "label": "dailybackup"},
            ],
        )
        merged = merge_checkagainst_entries(config)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["dest_root"], "user/a")

    def test_offsite_overrides_backup(self):
        config = self._make_config(
            backup_derived=[
                {"source_root": "tank/a", "dest_root": "backup/a", "label": "dailybackup"},
            ],
            offsite_derived=[
                {"source_root": "tank/a", "dest_root": "offsite/a", "label": "dailybackup"},
            ],
        )
        merged = merge_checkagainst_entries(config)
        self.assertEqual(merged[0]["dest_root"], "offsite/a")

    def test_inactive_flags_exclude_sections(self):
        config = self._make_config(
            backup_derived=[
                {"source_root": "tank/a", "dest_root": "backup/a", "label": "dailybackup"},
            ],
            offsite_derived=[
                {"source_root": "tank/b", "dest_root": "offsite/b", "label": "offsite"},
            ],
            backup_active=False,
            offsite_active=False,
        )
        merged = merge_checkagainst_entries(config)
        self.assertEqual(merged, [])

    def test_legacy_rows_are_normalized(self):
        config = self._make_config(
            backup_derived=[
                {
                    "dataset": "tank/a",
                    "quals": "0",
                    "counterpart": "backup",
                    "label": "dailybackup",
                },
            ],
        )
        merged = merge_checkagainst_entries(config)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["source_root"], "tank/a")
        self.assertEqual(merged[0]["dest_root"], "backup/tank/a")


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
        config = {"checkagainst": [{"source_root": "tank/a", "label": "offsite"}]}
        data = get_checkagainst(config)
        self.assertEqual(data["user_entries"], [{"source_root": "tank/a", "label": "offsite"}])


class TestAddCheckagainstEntry(unittest.TestCase):
    def test_adds_new_row(self):
        with temp_config_dir():
            config = {"checkagainst": {"user_entries": []}}
            added = add_checkagainst_entry(
                config,
                {"source_root": "tank/a", "dest_root": "backup/a", "label": "offsite"},
            )
            self.assertTrue(added)
            self.assertEqual(len(config["checkagainst"]["user_entries"]), 1)

    def test_skips_duplicate(self):
        config = {
            "checkagainst": {
                "user_entries": [
                    {"source_root": "tank/a", "dest_root": "backup/a", "label": "offsite"},
                ]
            }
        }
        added = add_checkagainst_entry(
            config,
            {"source_root": "tank/a", "dest_root": "backup/a", "label": "offsite"},
        )
        self.assertFalse(added)
        self.assertEqual(len(config["checkagainst"]["user_entries"]), 1)


if __name__ == "__main__":
    unittest.main()

"""Tests for checkagainst derivation, merge, and source/dest-root helpers."""

import os
import subprocess
import unittest

from feature_config import (
    _compute_destination_root,
    _normalize_checkagainst_row,
    _propmanifest_store,
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

    def test_section_of_wrong_type_reads_as_no_steps(self):
        """A malformed section derives nothing, for that section only.

        Config migrations run this function at load time, ahead of any GUI
        validation, so a hand-edited config must not be able to abort a load.
        The other section still derives its rows.
        """
        for section in ("backup", "offsite"):
            for bad in (None, [], "steps", 7):
                with self.subTest(section=section, value=bad):
                    config = {
                        "backup": {
                            "variables": {"label": "dailybackup"},
                            "send_receive_steps": [
                                {"active": True, "source": "poolA/a", "dest": "poolB"}
                            ],
                        },
                        "offsite": {
                            "steps": [{"active": True, "source": "poolA/a", "dest": "<offsite>"}]
                        },
                    }
                    config[section] = bad
                    backup_derived, offsite_derived = derive_checkagainst_entries(config)
                    # Forward, reverse, and manifest-store rows.
                    self.assertEqual(len(backup_derived), 0 if section == "backup" else 3)
                    self.assertEqual(len(offsite_derived), 0 if section == "offsite" else 2)

    def test_step_list_of_wrong_type_reads_as_no_steps(self):
        for bad in (None, {}, "poolA/a"):
            with self.subTest(value=bad):
                config = {
                    "backup": {"variables": {}, "send_receive_steps": bad},
                    "offsite": {"steps": bad},
                }
                self.assertEqual(derive_checkagainst_entries(config), ([], []))

    def test_malformed_step_costs_only_that_step(self):
        """A bad row in the list is skipped; its valid neighbors still derive."""
        config = {
            "backup": {
                "variables": {"label": "dailybackup"},
                "send_receive_steps": [
                    "poolA/a",
                    None,
                    {"active": True, "source": None, "dest": "poolB"},
                    {"active": True, "source": "poolA/ok", "dest": 5},
                    {"active": True, "source": " poolA/a ", "dest": "poolB"},
                ],
            },
            "offsite": {
                "steps": ["bad", {"active": True, "source": "poolA/a", "dest": "<offsite>"}]
            },
        }
        backup_derived, offsite_derived = derive_checkagainst_entries(config)
        self.assertEqual(
            [row["source_root"] for row in backup_derived],
            ["poolA/a", "poolB/poolA/a", "poolB/poolA/zfsutilities-manifests"],
        )
        self.assertEqual(
            [row["source_root"] for row in offsite_derived], ["poolA/a", "<offsite>/poolA/a"]
        )

    def test_label_defaults_when_variables_are_malformed(self):
        for bad in (None, [], "label"):
            with self.subTest(variables=bad):
                config = {
                    "backup": {
                        "variables": bad,
                        "send_receive_steps": [{"active": True, "source": "poolA/a", "dest": "y"}],
                    },
                    "offsite": {"steps": []},
                }
                backup_derived, _ = derive_checkagainst_entries(config)
                self.assertEqual({row["label"] for row in backup_derived}, {"dailybackup"})

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


REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))


class TestManifestStoreMatchesBash(unittest.TestCase):
    """The derived store row must name the dataset the backup really writes.

    ``feature_config._propmanifest_store`` mirrors ``propmanifest_dataset``
    (lib/property-manifest-lib.sh), the function the backup's capture uses to
    place the store. They are two implementations of one formula, so they are
    pinned against each other; a divergence would point the row at a dataset
    that does not exist and leave the real store uncovered.
    """

    CASES = (
        ("fivebays", "threeamigos/proxmox"),
        ("fivebays", "threeamigos/zfsutilities"),
        ("fivebays", "NVME1"),
        ("backup", "tank/src/data"),
        ("offsite", "fivebays/vms/disk1"),
        ("tank/backup", "tank/a/b"),
        # A trailing slash is left alone by both; parity includes the quirk.
        ("fivebays/", "threeamigos/proxmox"),
    )

    def test_store_matches_propmanifest_dataset(self):
        # The library sources bashinit only when log_msg is undefined.
        script = (
            "log_msg() { :; }\n"
            f'source "{REPO_ROOT}/lib/property-manifest-lib.sh"\n'
            'propmanifest_dataset "$1" "$2"\n'
        )
        for dest, source in self.CASES:
            with self.subTest(dest=dest, source=source):
                result = subprocess.run(
                    ["bash", "-c", script, "propmanifest_dataset", dest, source],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                self.assertEqual(_propmanifest_store(dest, source), result.stdout.strip())


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

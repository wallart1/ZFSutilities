"""Tests for profile_validation.py scope-alignment checks."""

import unittest

import profile_validation as pv


class TestParseFilters(unittest.TestCase):

    def test_empty_string_returns_empty_list(self):
        self.assertEqual(pv._parse_filters(""), [])
        self.assertEqual(pv._parse_filters("   "), [])
        self.assertEqual(pv._parse_filters(None), [])

    def test_list_passed_through(self):
        self.assertEqual(pv._parse_filters(["a", "b"]), ["a", "b"])

    def test_string_split_with_quotes(self):
        self.assertEqual(
            pv._parse_filters('=NVME1 proxmox'),
            ["=NVME1", "proxmox"]
        )


class TestMatchesFilter(unittest.TestCase):

    def test_exact_match(self):
        self.assertTrue(pv._matches_filter("NVME1", "=NVME1"))
        self.assertFalse(pv._matches_filter("NVME1/proxmox", "=NVME1"))

    def test_substring_match(self):
        self.assertTrue(pv._matches_filter("NVME1/proxmox", "proxmox"))
        self.assertFalse(pv._matches_filter("NVME1", "proxmox"))


class TestIsUnder(unittest.TestCase):

    def test_same_is_under(self):
        self.assertTrue(pv._is_under("NVME1", "NVME1"))

    def test_child_is_under(self):
        self.assertTrue(pv._is_under("NVME1/proxmox", "NVME1"))
        self.assertTrue(
            pv._is_under("NVME1/proxmox/vm-201-disk-3", "NVME1")
        )

    def test_unrelated_is_not_under(self):
        self.assertFalse(pv._is_under("threeamigos", "NVME1"))


class TestDestinationDataset(unittest.TestCase):

    def test_appends_source_to_dest(self):
        self.assertEqual(
            pv._destination_dataset("NVME1", "fivebays"),
            "fivebays/NVME1"
        )

    def test_dest_already_suffixed(self):
        self.assertEqual(
            pv._destination_dataset("NVME1/proxmox", "fivebays/NVME1/proxmox"),
            "fivebays/NVME1/proxmox"
        )

    def test_partial_suffix(self):
        self.assertEqual(
            pv._destination_dataset("NVME1/proxmox", "fivebays/NVME1"),
            "fivebays/NVME1/NVME1/proxmox"
        )


class TestValidateEffectiveSteps(unittest.TestCase):

    def _backup_step(self, source, dest, includes=None, excludes=None,
                     profile_name="daily"):
        return {
            "profile_type": "backup",
            "profile_name": profile_name,
            "source": source,
            "dest": dest,
            "includes": includes or [],
            "excludes": excludes or [],
            "active": True,
            "label": "dailybackup",
        }

    def _offsite_step(self, source, dest, includes=None, excludes=None,
                      profile_name="offsite"):
        return {
            "profile_type": "offsite",
            "profile_name": profile_name,
            "source": source,
            "dest": dest,
            "includes": includes or [],
            "excludes": excludes or [],
            "active": True,
            "label": "offsite",
        }

    def test_aligned_sources_no_warning(self):
        items = [
            self._backup_step("threeamigos/proxmox", "fivebays"),
            self._offsite_step(
                "threeamigos", "fivebays", includes=["proxmox"]
            ),
            self._offsite_step("fivebays", "z40tb"),
        ]
        self.assertEqual(pv.validate_effective_steps(items), [])

    def test_nvme1_mismatch_detected(self):
        """Reproduce the stewie NVME1 rollback scenario."""
        items = [
            self._backup_step("NVME1", "fivebays"),
            self._offsite_step(
                "NVME1", "fivebays", includes=["proxmox"]
            ),
            self._offsite_step("fivebays", "z40tb"),
        ]
        warnings = pv.validate_effective_steps(items)
        self.assertEqual(len(warnings), 1)
        self.assertIn("NVME1", warnings[0])
        self.assertIn("fivebays/NVME1", warnings[0])
        self.assertIn("roll back", warnings[0])

    def test_inactive_steps_ignored(self):
        items = [
            self._backup_step("NVME1", "fivebays"),
            {
                **self._offsite_step(
                    "NVME1", "fivebays", includes=["proxmox"]
                ),
                "active": False,
            },
            self._offsite_step("fivebays", "z40tb"),
        ]
        # Without the NVME1->fivebays offsite step, fivebays/NVME1 is still
        # covered by the fivebays->z40tb step, so the mismatch remains.
        warnings = pv.validate_effective_steps(items)
        self.assertEqual(len(warnings), 1)

    def test_backup_source_excluded_by_its_own_includes(self):
        """If the backup root is not backed up, it cannot conflict."""
        items = [
            self._backup_step("NVME1", "fivebays", includes=["proxmox"]),
            self._offsite_step("NVME1", "fivebays", includes=["proxmox"]),
            self._offsite_step("fivebays", "z40tb"),
        ]
        self.assertEqual(pv.validate_effective_steps(items), [])

    def test_no_overlap_different_destinations(self):
        items = [
            self._backup_step("NVME1", "fivebays"),
            self._offsite_step("NVME1", "z40tb"),
        ]
        self.assertEqual(pv.validate_effective_steps(items), [])

    def test_offsite_includes_root_exact_match(self):
        """Including =NVME1 in the offsite step covers the root."""
        items = [
            self._backup_step("NVME1", "fivebays"),
            self._offsite_step(
                "NVME1", "fivebays", includes=["=NVME1", "proxmox"]
            ),
            self._offsite_step("fivebays", "z40tb"),
        ]
        self.assertEqual(pv.validate_effective_steps(items), [])

    def test_offsite_excludes_backup_root(self):
        items = [
            self._backup_step("NVME1", "fivebays"),
            self._offsite_step(
                "NVME1", "fivebays", includes=[], excludes=["=NVME1"]
            ),
            self._offsite_step("fivebays", "z40tb"),
        ]
        warnings = pv.validate_effective_steps(items)
        self.assertEqual(len(warnings), 1)


class TestValidateGuiSettings(unittest.TestCase):

    def test_gui_settings_aligned(self):
        backup_cfg = {
            "variables": {"label": "dailybackup", "includes": "", "excludes": ""},
            "send_receive_steps": [
                {"active": True, "source": "threeamigos/proxmox", "dest": "fivebays"},
            ],
        }
        offsite_cfg = {
            "variables": {"includes": "", "excludes": ""},
            "steps": [
                {"active": True, "source": "threeamigos", "dest": "fivebays",
                 "includes": "proxmox", "excludes": ""},
                {"active": True, "source": "fivebays", "dest": "z40tb",
                 "includes": "", "excludes": ""},
            ],
        }
        self.assertEqual(pv.validate_gui_settings(backup_cfg, offsite_cfg), [])

    def test_gui_settings_nvme1_mismatch(self):
        backup_cfg = {
            "variables": {"label": "dailybackup", "includes": "", "excludes": ""},
            "send_receive_steps": [
                {"active": True, "source": "NVME1", "dest": "fivebays"},
            ],
        }
        offsite_cfg = {
            "variables": {"includes": "", "excludes": ""},
            "steps": [
                {"active": True, "source": "NVME1", "dest": "fivebays",
                 "includes": "proxmox", "excludes": ""},
                {"active": True, "source": "fivebays", "dest": "z40tb",
                 "includes": "", "excludes": ""},
            ],
        }
        warnings = pv.validate_gui_settings(backup_cfg, offsite_cfg)
        self.assertEqual(len(warnings), 1)
        self.assertIn("current backup settings", warnings[0])


class TestValidateProfiles(unittest.TestCase):

    def test_profiles_aligned(self):
        profiles = [
            {
                "profile_name": "root-backup-dailybackup",
                "tab_type": "backup",
                "config": {
                    "variables": {"label": "dailybackup"},
                    "send_receive_steps": [
                        {"active": True, "source": "threeamigos/proxmox", "dest": "fivebays"},
                    ],
                },
            },
            {
                "profile_name": "root-offsite-offsitebackup",
                "tab_type": "offsite",
                "config": {
                    "variables": {},
                    "steps": [
                        {"active": True, "source": "threeamigos", "dest": "fivebays",
                         "includes": "proxmox", "excludes": ""},
                        {"active": True, "source": "fivebays", "dest": "z40tb",
                         "includes": "", "excludes": ""},
                    ],
                },
            },
        ]
        self.assertEqual(pv.validate_profiles(profiles), [])

    def test_profiles_nvme1_mismatch(self):
        profiles = [
            {
                "profile_name": "root-backup-dailybackup",
                "tab_type": "backup",
                "config": {
                    "variables": {"label": "dailybackup"},
                    "send_receive_steps": [
                        {"active": True, "source": "NVME1", "dest": "fivebays"},
                    ],
                },
            },
            {
                "profile_name": "root-offsite-offsitebackup",
                "tab_type": "offsite",
                "config": {
                    "variables": {},
                    "steps": [
                        {"active": True, "source": "NVME1", "dest": "fivebays",
                         "includes": "proxmox", "excludes": ""},
                        {"active": True, "source": "fivebays", "dest": "z40tb",
                         "includes": "", "excludes": ""},
                    ],
                },
            },
        ]
        warnings = pv.validate_profiles(profiles)
        self.assertEqual(len(warnings), 1)
        self.assertIn("root-backup-dailybackup", warnings[0])
        self.assertIn("root-offsite-offsitebackup", warnings[0])
        self.assertIn("fivebays/NVME1", warnings[0])

    def test_concurrent_aligned_backup_offsite_no_warning(self):
        """Backup and offsite profiles that may run concurrently must have
        aligned source scopes to avoid rollbacks.

        This covers the case where a daily backup and an offsite backup overlap
        in wall-clock time.  When the offsite job snapshots the same source
        tree as the daily backup, the destination receives @offsite snapshots
        that the source also has, so no rollback is required.
        """
        profiles = [
            {
                "profile_name": "daily-backup",
                "tab_type": "backup",
                "config": {
                    "variables": {"label": "dailybackup"},
                    "send_receive_steps": [
                        {"active": True, "source": "threeamigos/proxmox",
                         "dest": "fivebays"},
                        {"active": True, "source": "NVME1", "dest": "fivebays"},
                    ],
                },
            },
            {
                "profile_name": "offsite-backup",
                "tab_type": "offsite",
                "config": {
                    "variables": {},
                    "steps": [
                        {"active": True, "source": "threeamigos",
                         "dest": "z40tb", "includes": "proxmox",
                         "excludes": ""},
                        {"active": True, "source": "NVME1", "dest": "z40tb",
                         "includes": "", "excludes": ""},
                        {"active": True, "source": "fivebays", "dest": "z40tb",
                         "includes": "", "excludes": ""},
                    ],
                },
            },
        ]
        self.assertEqual(pv.validate_profiles(profiles), [])


if __name__ == "__main__":
    unittest.main()

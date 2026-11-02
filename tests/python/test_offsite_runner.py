"""Tests for offsite_runner.py — offsite pool detection and command builders."""

import os
import sys
import unittest

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

import offsite_runner
from command_builders import BashStep
from test_support import mock_subprocess


class TestDetectOffsitePool(unittest.TestCase):
    """detect_offsite_pool returns the first online candidate pool."""

    def test_returns_first_online_candidate(self):
        with mock_subprocess() as m:
            m.add_zpool_list(
                [
                    {"name": "tank", "health": "ONLINE"},
                    {"name": "z40tb", "health": "ONLINE"},
                    {"name": "z22tb", "health": "OFFLINE"},
                ]
            )
            result = offsite_runner.detect_offsite_pool(["z22tb", "z40tb"])
        self.assertEqual(result, "z40tb")

    def test_returns_none_when_all_offline(self):
        with mock_subprocess() as m:
            m.add_zpool_list(
                [
                    {"name": "z40tb", "health": "OFFLINE"},
                ]
            )
            result = offsite_runner.detect_offsite_pool(["z40tb"])
        self.assertIsNone(result)

    def test_returns_none_when_no_candidates(self):
        with mock_subprocess() as m:
            m.add_zpool_list([{"name": "tank", "health": "ONLINE"}])
            result = offsite_runner.detect_offsite_pool([])
        self.assertIsNone(result)

    def test_returns_none_on_subprocess_error(self):
        with mock_subprocess() as m:
            m.set_command_handler(
                r"zpool list",
                lambda _cmd, **_kw: m._completed("", rc=1),
            )
            result = offsite_runner.detect_offsite_pool(["z40tb"])
        self.assertIsNone(result)


class TestDetectOffsitePools(unittest.TestCase):
    """detect_offsite_pools returns every online candidate pool."""

    def test_returns_all_online_candidates_in_order(self):
        with mock_subprocess() as m:
            m.add_zpool_list(
                [
                    {"name": "tank", "health": "ONLINE"},
                    {"name": "z40tb", "health": "ONLINE"},
                    {"name": "z22tb", "health": "ONLINE"},
                ]
            )
            result = offsite_runner.detect_offsite_pools(["z22tb", "z40tb"])
        self.assertEqual(result, ["z22tb", "z40tb"])

    def test_skips_offline_candidates(self):
        with mock_subprocess() as m:
            m.add_zpool_list(
                [
                    {"name": "z40tb", "health": "ONLINE"},
                    {"name": "z22tb", "health": "OFFLINE"},
                ]
            )
            result = offsite_runner.detect_offsite_pools(["z22tb", "z40tb"])
        self.assertEqual(result, ["z40tb"])

    def test_returns_empty_list_when_none_online(self):
        with mock_subprocess() as m:
            m.add_zpool_list(
                [
                    {"name": "z40tb", "health": "OFFLINE"},
                ]
            )
            result = offsite_runner.detect_offsite_pools(["z40tb"])
        self.assertEqual(result, [])

    def test_returns_empty_list_on_subprocess_error(self):
        with mock_subprocess() as m:
            m.set_command_handler(
                r"zpool list",
                lambda _cmd, **_kw: m._completed("", rc=1),
            )
            result = offsite_runner.detect_offsite_pools(["z40tb"])
        self.assertEqual(result, [])


class TestIsOnwardLeg(unittest.TestCase):
    """is_onward_leg detects steps whose source is a backup destination."""

    def test_matches_sibling_step_dest(self):
        steps = [
            {"active": True, "source": "tank", "dest": "fivebays"},
            {"active": True, "source": "fivebays", "dest": "z40tb"},
        ]
        self.assertTrue(offsite_runner.is_onward_leg("fivebays", steps))

    def test_matches_backup_dest(self):
        steps = [{"active": True, "source": "z40tb", "dest": "elsewhere"}]
        self.assertTrue(offsite_runner.is_onward_leg("fivebays", steps, backup_dests=("fivebays",)))

    def test_live_source_is_not_onward(self):
        steps = [
            {"active": True, "source": "tank", "dest": "fivebays"},
            {"active": True, "source": "temp", "dest": "z40tb"},
        ]
        self.assertFalse(offsite_runner.is_onward_leg("tank", steps))

    def test_inactive_sibling_counts(self):
        # Any configured step writing to the source proves it is a backup
        # destination, active tonight or not.
        steps = [
            {"active": False, "source": "tank", "dest": "fivebays"},
        ]
        self.assertTrue(offsite_runner.is_onward_leg("fivebays", steps))

    def test_empty_dests_ignored(self):
        steps = [{"active": True, "source": "tank", "dest": ""}]
        self.assertFalse(offsite_runner.is_onward_leg("fivebays", steps))


class TestDiscoverManifestStores(unittest.TestCase):
    """discover_manifest_stores finds depth-2 stores under a source."""

    def test_returns_pool_anchored_stores(self):
        with mock_subprocess() as m:
            m.add_zfs_list(
                [
                    {"name": "fivebays"},
                    {"name": "fivebays/threeamigos"},
                    {"name": "fivebays/threeamigos/zfsutilities-manifests"},
                    {"name": "fivebays/NVME1"},
                    {"name": "fivebays/NVME1/zfsutilities-manifests"},
                    {"name": "fivebays/threeamigos/proxmox/vm-100-disk-0"},
                ]
            )
            result = offsite_runner.discover_manifest_stores("fivebays")
        self.assertEqual(
            result,
            ["threeamigos/zfsutilities-manifests", "NVME1/zfsutilities-manifests"],
        )

    def test_empty_when_no_stores_exist(self):
        with mock_subprocess() as m:
            m.add_zfs_list([{"name": "fivebays"}, {"name": "fivebays/tank/src"}])
            result = offsite_runner.discover_manifest_stores("fivebays")
        self.assertEqual(result, [])

    def test_empty_on_subprocess_error(self):
        with mock_subprocess() as m:
            m.set_command_handler(
                r"zfs list",
                lambda _cmd, **_kw: m._completed("", rc=1),
            )
            result = offsite_runner.discover_manifest_stores("fivebays")
        self.assertEqual(result, [])


class TestManifestsIncludePatterns(unittest.TestCase):
    """manifests_include_patterns picks the stores that must ride along."""

    STORES = ("threeamigos/zfsutilities-manifests", "NVME1/zfsutilities-manifests")

    def test_empty_includes_add_nothing(self):
        self.assertEqual(
            offsite_runner.manifests_include_patterns("", self.STORES, "fivebays"),
            [],
        )

    def test_anchored_pattern_adds_its_pool_store(self):
        self.assertEqual(
            offsite_runner.manifests_include_patterns(
                "threeamigos/proxmox", self.STORES, "fivebays"
            ),
            ["threeamigos/zfsutilities-manifests"],
        )

    def test_exact_pattern_with_source_prefix_adds_its_pool_store(self):
        self.assertEqual(
            offsite_runner.manifests_include_patterns(
                "=fivebays/threeamigos/proxmox/vm-100-disk-0",
                self.STORES,
                "fivebays",
            ),
            ["threeamigos/zfsutilities-manifests"],
        )

    def test_unanchored_pattern_adds_all_stores(self):
        self.assertEqual(
            offsite_runner.manifests_include_patterns("proxmox", self.STORES, "fivebays"),
            list(self.STORES),
        )


class TestBuildOnwardStepCommand(unittest.TestCase):
    """build_offsite_step_command derives onward-leg behavior from context."""

    def _build(self, *, sibling_steps=None, backup_dests=(), includes="", variables=None):
        return offsite_runner.build_offsite_step_command(
            source="fivebays",
            dest="z40tb/fivebays",
            variables=variables or {},
            parent_dir="/usr/local/lib/zfsutilities/current/bin",
            nextsnap="@offsite-2026-06-21T12:00-s",
            includes_str=includes,
            excludes_str="",
            sibling_steps=sibling_steps,
            backup_dests=backup_dests,
        )

    def test_onward_leg_forces_manifest_off_and_carries_stores(self):
        with mock_subprocess() as m:
            m.add_zfs_list(
                [
                    {"name": "fivebays/threeamigos/zfsutilities-manifests"},
                    {"name": "fivebays/NVME1/zfsutilities-manifests"},
                ]
            )
            step = self._build(
                sibling_steps=[{"active": True, "source": "tank", "dest": "fivebays"}],
                includes="threeamigos/proxmox NVME1/proxmox",
            )
        script = step.command[2]
        self.assertIn('property_manifest="N"', script)
        self.assertIn(
            'includes=("threeamigos/proxmox" "NVME1/proxmox" '
            '"threeamigos/zfsutilities-manifests" "NVME1/zfsutilities-manifests")',
            script,
        )
        self.assertIn(
            "INFO: Onward leg fivebays -> z40tb/fivebays: property manifests "
            "travel via threeamigos/zfsutilities-manifests NVME1/zfsutilities-manifests.",
            script,
        )
        self.assertTrue(step.metadata["onward"])
        self.assertEqual(
            step.metadata["manifests"],
            ["threeamigos/zfsutilities-manifests", "NVME1/zfsutilities-manifests"],
        )

    def test_onward_leg_with_empty_includes_adds_nothing(self):
        with mock_subprocess() as m:
            m.add_zfs_list([{"name": "fivebays/threeamigos/zfsutilities-manifests"}])
            step = self._build(
                sibling_steps=[{"active": True, "source": "tank", "dest": "fivebays"}],
            )
        script = step.command[2]
        self.assertIn('property_manifest="N"', script)
        self.assertIn("includes=(); ", script)
        self.assertIn(
            "property manifest capture disabled (copies hold no local properties)",
            script,
        )
        self.assertEqual(step.metadata["manifests"], [])

    def test_live_step_keeps_default_and_variables_override(self):
        step = self._build(sibling_steps=[{"active": True, "source": "a", "dest": "b"}])
        self.assertIn('property_manifest="Y"', step.command[2])
        self.assertFalse(step.metadata["onward"])
        step = self._build(
            sibling_steps=[{"active": True, "source": "a", "dest": "b"}],
            variables={"property_manifest": "N"},
        )
        self.assertIn('property_manifest="N"', step.command[2])
        self.assertFalse(step.metadata["onward"])

    def test_backup_dests_make_the_leg_onward(self):
        step = self._build(
            sibling_steps=[{"active": True, "source": "a", "dest": "b"}],
            backup_dests=("fivebays",),
        )
        self.assertIn('property_manifest="N"', step.command[2])
        self.assertTrue(step.metadata["onward"])


class TestBuildOffsiteStepCommand(unittest.TestCase):
    """build_offsite_step_command produces a BashStep for offsite send/receive."""

    def _build(self, variables, includes="", excludes="", dryrun=False):
        return offsite_runner.build_offsite_step_command(
            source="tank/src",
            dest="z40tb/src",
            variables=variables,
            parent_dir="/usr/local/lib/zfsutilities/current/bin",
            nextsnap="@offsite-2026-06-21T12:00-s",
            includes_str=includes,
            excludes_str=excludes,
            dryrun=dryrun,
        )

    def test_returns_bash_step(self):
        step = self._build({})
        self.assertIsInstance(step, BashStep)
        self.assertEqual(step.command[0], "bash")
        self.assertEqual(step.command[1], "-c")
        self.assertIn("offsite: tank/src -> z40tb/src", step.description)
        self.assertTrue(step.fatal)
        self.assertFalse(step.is_rsync)

    def test_step_has_metadata(self):
        step = self._build({})
        self.assertIsNotNone(step.metadata)
        self.assertEqual(step.metadata["source"], "tank/src")
        self.assertEqual(step.metadata["dest"], "z40tb/src")
        self.assertEqual(step.metadata["label"], "offsite")

    def test_includes_core_variables(self):
        step = self._build({})
        script = step.command[2]
        self.assertIn('sourcefs="tank/src"', script)
        self.assertIn('destfs="z40tb/src"', script)
        self.assertIn('nextsnap="@offsite-2026-06-21T12:00-s"', script)
        self.assertIn('label="@offsite"', script)
        self.assertIn('doincrementals="Y"', script)
        self.assertIn('dointermediates="N"', script)
        self.assertIn('autoproceed="Y"', script)
        self.assertIn('allow_destructive="N"', script)
        self.assertIn('receive_F_option="F"', script)
        self.assertIn('verify_after_transfer="Y"', script)
        self.assertIn('applyholds="Y"', script)

    def test_custom_variables_override_defaults(self):
        step = self._build(
            {
                "doincrementals": "N",
                "dointermediates": "Y",
                "allow_destructive": "Y",
                "receive_F_option": "",
                "verify_after_transfer": "N",
                "transfer_rate_limit": "100M",
                "applyholds": "N",
            }
        )
        script = step.command[2]
        self.assertIn('doincrementals="N"', script)
        self.assertIn('dointermediates="Y"', script)
        self.assertIn('allow_destructive="Y"', script)
        self.assertIn('receive_F_option=""', script)
        self.assertIn('verify_after_transfer="N"', script)
        self.assertIn('transfer_rate_limit="100M"', script)
        self.assertIn('applyholds="N"', script)

    def test_includes_startwith_and_endwith(self):
        step = self._build({"startwith": "vm", "endwith": "disk"})
        script = step.command[2]
        self.assertIn('startwith="vm"', script)
        self.assertIn('endwith="disk"', script)

    def test_merges_global_and_step_includes_excludes(self):
        step = self._build(
            {"includes": "proxmox vm", "excludes": "temp"},
            includes="disk-0",
            excludes="scratch",
        )
        script = step.command[2]
        self.assertIn('includes=("proxmox" "vm" "disk-0")', script)
        self.assertIn('excludes=("temp" "scratch")', script)
        self.assertIn("(includes: proxmox vm disk-0)", step.description)
        self.assertIn("(excludes: temp scratch)", step.description)

    def test_empty_includes_excludes_become_empty_arrays(self):
        step = self._build({})
        script = step.command[2]
        self.assertIn("includes=(); ", script)
        self.assertIn("excludes=(); ", script)

    def test_hold_logic_present(self):
        step = self._build({})
        script = step.command[2]
        self.assertIn('source "$mydir/zfshold"', script)
        self.assertIn('if [[ $rc -eq 0 && $applyholds = "Y" && $dryrun != "Y" ]]; then', script)
        self.assertIn('zfshold "${label:1}-$sourcefspool"', script)
        self.assertIn('zfshold "${label:1}-$destfspool"', script)

    def test_dryrun_flag_propagated(self):
        step = self._build({}, dryrun=True)
        script = step.command[2]
        self.assertIn("dryrun='Y'", script)
        self.assertIn('elif [[ $rc -eq 0 && $applyholds = "Y" && $dryrun = "Y" ]]; then', script)
        self.assertIn("Dry-run: Would apply holds", script)


if __name__ == "__main__":
    unittest.main()

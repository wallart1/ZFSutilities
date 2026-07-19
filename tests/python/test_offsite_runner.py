"""Tests for offsite_runner.py — offsite pool detection and command builders."""

import os
import sys
import unittest

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from command_builders import BashStep
from test_support import mock_subprocess

import offsite_runner


class TestDetectOffsitePool(unittest.TestCase):
    """detect_offsite_pool returns the first online candidate pool."""

    def test_returns_first_online_candidate(self):
        with mock_subprocess() as m:
            m.add_zpool_list([
                {"name": "tank", "health": "ONLINE"},
                {"name": "z40tb", "health": "ONLINE"},
                {"name": "z22tb", "health": "OFFLINE"},
            ])
            result = offsite_runner.detect_offsite_pool(["z22tb", "z40tb"])
        self.assertEqual(result, "z40tb")

    def test_returns_none_when_all_offline(self):
        with mock_subprocess() as m:
            m.add_zpool_list([
                {"name": "z40tb", "health": "OFFLINE"},
            ])
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
        step = self._build({
            "doincrementals": "N",
            "dointermediates": "Y",
            "allow_destructive": "Y",
            "receive_F_option": "",
            "verify_after_transfer": "N",
            "pv_rate_limit": "100M",
            "applyholds": "N",
        })
        script = step.command[2]
        self.assertIn('doincrementals="N"', script)
        self.assertIn('dointermediates="Y"', script)
        self.assertIn('allow_destructive="Y"', script)
        self.assertIn('receive_F_option=""', script)
        self.assertIn('verify_after_transfer="N"', script)
        self.assertIn('pv_rate_limit="100M"', script)
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
        self.assertIn('includes=(); ', script)
        self.assertIn('excludes=(); ', script)

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

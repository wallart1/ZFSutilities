"""Tests for restore_runner.py — restore command builders and helpers."""

import os
import sys
import unittest

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

import restore_runner as rr


class TestComputeAutoDestination(unittest.TestCase):
    """compute_auto_destination strips leading qualifiers until a pool matches."""

    def test_strips_single_backup_prefix(self):
        dest = rr.compute_auto_destination(
            "backuppool/threeamigos/proxmox/vm-209-disk-0",
            ["threeamigos", "fivebays"],
        )
        self.assertEqual(dest, "threeamigos/proxmox/vm-209-disk-0")

    def test_strips_multiple_prefixes_until_pool_matches(self):
        dest = rr.compute_auto_destination(
            "archive/backuppool/threeamigos/data",
            ["threeamigos", "fivebays"],
        )
        self.assertEqual(dest, "threeamigos/data")

    def test_first_qualifier_is_already_pool(self):
        # The algorithm always strips the first qualifier. Here the source
        # already begins with a known pool, but after stripping it the next
        # qualifier is not a pool, so we keep stripping until we find one.
        dest = rr.compute_auto_destination(
            "threeamigos/fivebays/proxmox/vm-209-disk-0",
            ["threeamigos", "fivebays"],
        )
        self.assertEqual(dest, "fivebays/proxmox/vm-209-disk-0")

    def test_raises_when_no_pool_matches(self):
        with self.assertRaises(ValueError) as cm:
            rr.compute_auto_destination(
                "backuppool/unknownpool/data",
                ["threeamigos", "fivebays"],
            )
        self.assertIn("Cannot auto-determine destination", str(cm.exception))

    def test_raises_when_only_one_qualifier_and_not_pool(self):
        with self.assertRaises(ValueError):
            rr.compute_auto_destination("unknownpool", ["threeamigos"])

    def test_ignores_leading_slash(self):
        dest = rr.compute_auto_destination(
            "/backuppool/threeamigos/proxmox/vm-209-disk-0",
            ["threeamigos", "fivebays"],
        )
        self.assertEqual(dest, "threeamigos/proxmox/vm-209-disk-0")

    def test_raises_when_source_is_exactly_a_known_pool(self):
        with self.assertRaises(ValueError) as cm:
            rr.compute_auto_destination("threeamigos", ["threeamigos"])
        self.assertIn("threeamigos", str(cm.exception))

    def test_raises_when_known_pools_empty(self):
        with self.assertRaises(ValueError):
            rr.compute_auto_destination("pool/data", [])

    def test_accepts_any_iterable_for_known_pools(self):
        dest = rr.compute_auto_destination(
            "backuppool/threeamigos/data",
            ("threeamigos", "fivebays"),
        )
        self.assertEqual(dest, "threeamigos/data")


class TestComputeRestoreParams(unittest.TestCase):
    """compute_restore_params maps source/dest to removequalifiers/destfs."""

    def test_simple_pool_prefix(self):
        n, destfs = rr.compute_restore_params("poolA/data", "poolB/data")
        self.assertEqual(n, 1)
        self.assertEqual(destfs, "poolB")

    def test_multi_qualifier_mapping(self):
        n, destfs = rr.compute_restore_params(
            "poolB/poolA/data", "poolA/data"
        )
        self.assertEqual(n, 2)
        self.assertEqual(destfs, "poolA")


if __name__ == "__main__":
    unittest.main()

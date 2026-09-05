"""Tests for pool_create.py — pure-logic create-pool helpers."""

import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from disk_repository import DiskInfo
from pool_create import (
    MAX_POOL_NAME_LEN,
    TOPOLOGIES,
    CapacityEstimate,
    EligibilityResult,
    disk_eligibility,
    estimate_effective_capacity,
    pool_filesystem_options,
    suggest_ashift,
    validate_pool_name,
    validate_vdev_selection,
)
from workload_profiles import LIVE_PROPERTIES

TB = 10**12


def _disk(path, **kwargs):
    """Build a DiskInfo with sane defaults for a clean whole disk."""
    defaults = {
        "name": os.path.basename(path),
        "path": path,
        "by_id": "ata-TEST" + os.path.basename(path),
        "size_bytes": TB,
        "disk_type": "HDD",
        "physical_sector": 4096,
        "transport": "sata",
    }
    defaults.update(kwargs)
    return DiskInfo(**defaults)


def _eligibility(disks, imported=None, importable=None):
    return disk_eligibility(disks, imported or {}, importable or {})


class TestTopologies(unittest.TestCase):
    """The TOPOLOGIES table matches the Phase 3 brief minimums."""

    def test_parity_and_minimums(self):
        expected = {
            "stripe": (0, 1),
            "mirror": (0, 2),
            "raidz1": (1, 3),
            "raidz2": (2, 4),
            "raidz3": (3, 5),
        }
        for name, (parity, min_disks) in expected.items():
            with self.subTest(topology=name):
                spec = TOPOLOGIES[name]
                self.assertEqual(spec.name, name)
                self.assertEqual(spec.parity, parity)
                self.assertEqual(spec.min_disks, min_disks)


class TestDiskEligibility(unittest.TestCase):
    """disk_eligibility verdicts for the full rule matrix."""

    def test_clean_disk_is_eligible(self):
        results = _eligibility([_disk("/dev/sda")])
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertIsInstance(result, EligibilityResult)
        self.assertTrue(result.eligible)
        self.assertEqual(result.reasons, [])
        self.assertEqual(result.warnings, [])

    def test_usb_disk_is_eligible_with_warning(self):
        result = _eligibility([_disk("/dev/sda", transport="usb")])[0]
        self.assertTrue(result.eligible)
        self.assertEqual(result.reasons, [])
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("USB", result.warnings[0])

    def test_missing_by_id_is_ineligible(self):
        result = _eligibility([_disk("/dev/sda", by_id="")])[0]
        self.assertFalse(result.eligible)
        self.assertIn("no /dev/disk/by-id path", result.reasons)

    def test_unknown_disk_type_is_ineligible(self):
        result = _eligibility([_disk("/dev/sda", disk_type="unknown")])[0]
        self.assertFalse(result.eligible)
        self.assertIn("unknown disk type", result.reasons)

    def test_zvol_backed_device_is_ineligible(self):
        result = _eligibility([_disk("/dev/zd0", by_id="")])[0]
        self.assertFalse(result.eligible)
        self.assertIn("zvol-backed device", result.reasons)

    def test_imported_pool_member_is_ineligible(self):
        result = _eligibility(
            [_disk("/dev/sda")],
            imported={"fivebays": ["/dev/disk/by-id/ata-TESTsda"]},
        )[0]
        self.assertFalse(result.eligible)
        self.assertIn("member of imported pool 'fivebays'", result.reasons)

    def test_importable_pool_member_is_ineligible(self):
        result = _eligibility(
            [_disk("/dev/sda")],
            importable={"z22tb": ["/dev/disk/by-id/ata-TESTsda"]},
        )[0]
        self.assertFalse(result.eligible)
        self.assertTrue(
            any("member of importable pool 'z22tb'" in r for r in result.reasons)
        )

    def test_basename_fallback_match(self):
        result = _eligibility(
            [_disk("/dev/sdz9", by_id="ata-QEMU-HARDDISK")],
            importable={"oldpool": ["/dev/disk/by-id/ata-QEMU-HARDDISK"]},
        )[0]
        self.assertFalse(result.eligible)
        self.assertTrue(any("oldpool" in reason for reason in result.reasons))

    def test_realpath_symlink_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            kernel_dir = os.path.join(tmp, "kernel")
            by_id_dir = os.path.join(tmp, "by-id")
            os.makedirs(kernel_dir)
            os.makedirs(by_id_dir)
            kernel_path = os.path.join(kernel_dir, "sda")
            open(kernel_path, "w", encoding="utf-8").close()
            by_id_path = os.path.join(by_id_dir, "wwn-0xTEST")
            os.symlink(kernel_path, by_id_path)
            disk = _disk(kernel_path, by_id="wwn-0xTEST")
            with self.subTest(source="imported"):
                result = _eligibility(
                    [disk], imported={"poola": [by_id_path]}
                )[0]
                self.assertFalse(result.eligible)
                self.assertIn("member of imported pool 'poola'", result.reasons)
            with self.subTest(source="importable"):
                result = _eligibility(
                    [disk], importable={"poolb": [by_id_path]}
                )[0]
                self.assertFalse(result.eligible)
                self.assertTrue(
                    any("member of importable pool 'poolb'" in r for r in result.reasons)
                )

    def test_results_preserve_input_order(self):
        disks = [_disk("/dev/sda"), _disk("/dev/sdb", by_id=""), _disk("/dev/sdc")]
        results = _eligibility(disks)
        self.assertEqual([r.disk.path for r in results], [d.path for d in disks])


class TestPartitionPolicy(unittest.TestCase):
    """Partition policy: SSD partitions are candidates, HDD are not."""

    def _layout(self, parent_type="NVMe"):
        parent = _disk("/dev/nvme0n1", disk_type=parent_type, by_id="nvme-TEST1")
        part1 = _disk(
            "/dev/nvme0n1p1", disk_type="part", parent_path="/dev/nvme0n1",
            by_id="nvme-TEST1-part1",
        )
        part2 = _disk(
            "/dev/nvme0n1p2", disk_type="part", parent_path="/dev/nvme0n1",
            by_id="nvme-TEST1-part2",
        )
        return [parent, part1, part2]

    def test_ssd_partition_is_eligible_with_destroy_warning(self):
        results = _eligibility(self._layout())
        parts = [r for r in results if r.disk.disk_type == "part"]
        self.assertEqual(len(parts), 2)
        for part in parts:
            self.assertTrue(part.eligible, part.reasons)
            self.assertEqual(part.reasons, [])
            self.assertEqual(len(part.warnings), 1)
            self.assertIn("destroyed", part.warnings[0])

    def test_partitioned_whole_disk_is_not_selectable(self):
        result = next(r for r in _eligibility(self._layout()) if r.disk.path == "/dev/nvme0n1")
        self.assertFalse(result.eligible)
        self.assertTrue(any("select individual partitions" in r for r in result.reasons))

    def test_partitioned_hdd_whole_disk_is_not_selectable(self):
        result = next(r for r in _eligibility(self._layout("HDD")) if r.disk.path == "/dev/nvme0n1")
        self.assertFalse(result.eligible)
        self.assertTrue(any("rotating" in r for r in result.reasons))

    def test_hdd_partition_is_ineligible(self):
        results = _eligibility(self._layout("HDD"))
        parts = [r for r in results if r.disk.disk_type == "part"]
        for part in parts:
            self.assertFalse(part.eligible)
            self.assertTrue(any("rotating" in r for r in part.reasons))

    def test_partition_with_unknown_parent_is_ineligible(self):
        part = _disk("/dev/sda1", disk_type="part", parent_path="/dev/sda",
                     by_id="ata-TESTsda-part1")
        result = _eligibility([part])[0]
        self.assertFalse(result.eligible)
        self.assertIn("partition with unknown parent disk", result.reasons)


class TestValidateVdevSelection(unittest.TestCase):
    """validate_vdev_selection enforces device separation within a vdev."""

    def test_two_partitions_of_one_disk_rejected(self):
        part1 = _disk("/dev/nvme0n1p1", disk_type="part", parent_path="/dev/nvme0n1")
        part2 = _disk("/dev/nvme0n1p2", disk_type="part", parent_path="/dev/nvme0n1")
        problems = validate_vdev_selection([part1, part2])
        self.assertEqual(len(problems), 1)
        self.assertIn("same physical device", problems[0])

    def test_whole_disk_and_its_partition_rejected(self):
        disk = _disk("/dev/nvme0n1")
        part = _disk("/dev/nvme0n1p1", disk_type="part", parent_path="/dev/nvme0n1")
        problems = validate_vdev_selection([disk, part])
        self.assertEqual(len(problems), 1)

    def test_independent_disks_accepted(self):
        part1 = _disk("/dev/nvme0n1p1", disk_type="part", parent_path="/dev/nvme0n1")
        part2 = _disk("/dev/nvme1n1p1", disk_type="part", parent_path="/dev/nvme1n1")
        self.assertEqual(validate_vdev_selection([part1, part2]), [])

    def test_single_or_empty_selection_accepted(self):
        self.assertEqual(validate_vdev_selection([]), [])
        self.assertEqual(validate_vdev_selection([_disk("/dev/sda")]), [])


class TestValidatePoolName(unittest.TestCase):
    """Name validation matrix per the verified OpenZFS 2.4.4 libzfs rules."""

    def assert_valid(self, name, existing=None):
        ok, error = validate_pool_name(name, existing or [])
        self.assertTrue(ok, f"{name!r} should be valid: {error}")
        self.assertEqual(error, "")

    def assert_invalid(self, name, existing=None):
        ok, error = validate_pool_name(name, existing or [])
        self.assertFalse(ok, f"{name!r} should be invalid")
        self.assertNotEqual(error, "")

    def test_valid_names(self):
        for name in ("mypool", "pool_1", "a.b-c", "NVME1", "MIRROR", "cache",
                     "special", "c0", "c12t0d0", "loggy", "my:pool", "my pool",
                     "x" * MAX_POOL_NAME_LEN):
            with self.subTest(name=name):
                self.assert_valid(name)

    def test_empty_names_rejected(self):
        for name in ("", "   "):
            with self.subTest(name=name):
                self.assert_invalid(name)

    def test_first_character_must_be_letter(self):
        for name in ("1pool", "_pool", "-x", " x", ".x"):
            with self.subTest(name=name):
                self.assert_invalid(name)

    def test_exact_reserved_names_rejected(self):
        for name in ("mirror", "raidz", "draid", "log"):
            with self.subTest(name=name):
                self.assert_invalid(name)

    def test_reserved_prefixes_rejected(self):
        for name in ("raidz2", "raidz3", "spare", "spare1", "mirrorpool", "draid2"):
            with self.subTest(name=name):
                self.assert_invalid(name)

    def test_illegal_characters_rejected(self):
        for name in ("pool%dot", "pool@x", "ta\tb", "pool/x", "pool#x"):
            with self.subTest(name=name):
                self.assert_invalid(name)

    def test_length_cap_enforced(self):
        self.assert_valid("y" * MAX_POOL_NAME_LEN)
        self.assert_invalid("z" * (MAX_POOL_NAME_LEN + 1))

    def test_collision_rejected(self):
        self.assert_invalid("fivebays", existing=["fivebays"])
        self.assert_invalid("fivebays", existing=["fivebays", "NVME1"])
        self.assert_valid("NVME1", existing=["fivebays"])
        self.assert_valid("FIVEBAYS", existing=["fivebays"])


class TestSuggestAshift(unittest.TestCase):
    """suggest_ashift from the worst-case physical sector size."""

    def test_512n_disk_suggests_9(self):
        self.assertEqual(suggest_ashift([_disk("/dev/sda", physical_sector=512)]), 9)

    def test_4kn_disk_suggests_12(self):
        self.assertEqual(suggest_ashift([_disk("/dev/sda", physical_sector=4096)]), 12)

    def test_mixed_disks_suggest_12(self):
        disks = [
            _disk("/dev/sda", physical_sector=512),
            _disk("/dev/sdb", physical_sector=4096),
        ]
        self.assertEqual(suggest_ashift(disks), 12)

    def test_no_sector_info_returns_none(self):
        self.assertIsNone(suggest_ashift([_disk("/dev/sda", physical_sector=None)]))
        self.assertIsNone(suggest_ashift([]))


class TestEstimateEffectiveCapacity(unittest.TestCase):
    """Table-driven capacity estimator against the brief's reference anchors."""

    def test_stripe_and_mirror_have_no_padding_loss(self):
        stripe = estimate_effective_capacity("stripe", 3, TB, 128 * 1024)
        self.assertEqual(stripe, CapacityEstimate(3 * TB, 3 * TB, 1.0))
        mirror = estimate_effective_capacity("mirror", 2, TB, 128 * 1024)
        self.assertEqual(mirror, CapacityEstimate(TB, TB, 1.0))

    def test_raidz2_8k_is_33_percent_of_total(self):
        # Brief anchor: raidz2 ashift=12, 8K block ≈ 33% efficient.
        # D=2 sectors, U=3, rows=1, cost=2+2=4 rounded up to 6 -> 2/6.
        est = estimate_effective_capacity("raidz2", 5, TB, 8 * 1024)
        total_raw = 5 * TB
        self.assertEqual(est.raw_usable_bytes, 3 * TB)
        self.assertAlmostEqual(est.effective_bytes, total_raw / 3, delta=total_raw / 1e6)
        self.assertAlmostEqual(est.efficiency_fraction, 5 / 9, places=4)

    def test_raidz2_1m_matches_production_pool_anchor(self):
        # Brief anchor: 5 x 10 TB raidz2, large blocks ≈ 30 TB usable.
        # D=256, U=3, rows=86, cost=256+172=428 rounded up to 429 -> 256/429.
        est = estimate_effective_capacity("raidz2", 5, 10 * TB, 1024 * 1024)
        self.assertAlmostEqual(est.effective_bytes, 30 * TB, delta=0.5 * TB)
        self.assertAlmostEqual(est.efficiency_fraction, (256 / 429) / 0.6, places=3)

    def test_raidz2_64k_approaches_asymptote(self):
        # D=16, U=3, rows=6, cost=16+12=28 rounded up to 30 -> 16/30.
        est = estimate_effective_capacity("raidz2", 5, TB, 64 * 1024)
        self.assertAlmostEqual(est.efficiency_fraction, (16 / 30) / 0.6, places=4)

    def test_large_blocks_reach_n_minus_p_over_n(self):
        for topology, num_disks, parity in (("raidz1", 3, 1), ("raidz2", 5, 2),
                                            ("raidz3", 5, 3)):
            with self.subTest(topology=topology):
                est = estimate_effective_capacity(topology, num_disks, TB, 1024 * 1024)
                asymptote = (num_disks - parity) / num_disks
                self.assertAlmostEqual(
                    est.effective_bytes / (num_disks * TB), asymptote, places=2
                )
                self.assertLessEqual(est.effective_bytes, est.raw_usable_bytes)
                self.assertAlmostEqual(est.efficiency_fraction, 1.0, delta=0.01)

    def test_sector_size_parameter_is_honored(self):
        est_4k = estimate_effective_capacity("raidz2", 5, TB, 8 * 1024, 4096)
        est_512 = estimate_effective_capacity("raidz2", 5, TB, 8 * 1024, 512)
        # 8K at 512B sectors is D=16 (not 2), so padding differs.
        self.assertNotEqual(est_4k.effective_bytes, est_512.effective_bytes)

    def test_effective_never_exceeds_raw_usable(self):
        for block_k in (4, 8, 16, 64, 128, 1024):
            with self.subTest(block_k=block_k):
                est = estimate_effective_capacity("raidz2", 5, TB, block_k * 1024)
                self.assertLessEqual(est.effective_bytes, est.raw_usable_bytes)

    def test_invalid_inputs_raise(self):
        with self.assertRaises(ValueError):
            estimate_effective_capacity("bogus", 3, TB, 1024)
        with self.assertRaises(ValueError):
            estimate_effective_capacity("raidz2", 3, TB, 1024)
        with self.assertRaises(ValueError):
            estimate_effective_capacity("stripe", 1, 0, 1024)
        with self.assertRaises(ValueError):
            estimate_effective_capacity("stripe", 1, TB, 0)


GENERAL_PROFILE = {
    "applies_to": ["filesystem"],
    "properties": {
        "recordsize": "128K",
        "compression": "lz4",
        "atime": "off",
        "logbias": "latency",
        "sync": "standard",
        "primarycache": "all",
        "special_small_blocks": "0",
        "volblocksize": "16K",  # creation-only + volume-only: skipped
    },
}


class TestPoolFilesystemOptions(unittest.TestCase):
    """pool_filesystem_options maps a profile to explicit -O options."""

    def test_general_profile_emits_all_live_properties_in_canonical_order(self):
        options = pool_filesystem_options(GENERAL_PROFILE)
        self.assertEqual(
            options,
            [(prop, GENERAL_PROFILE["properties"][prop]) for prop in LIVE_PROPERTIES],
        )
        self.assertEqual(options[0], ("recordsize", "128K"))

    def test_volume_only_profile_yields_nothing(self):
        profile = {
            "applies_to": ["volume"],
            "properties": {"volblocksize": "16K", "compression": "lz4"},
        }
        self.assertEqual(pool_filesystem_options(profile), [])

    def test_unknown_properties_skipped(self):
        profile = {
            "applies_to": ["filesystem"],
            "properties": {"recordsize": "128K", "bogus_prop": "x"},
        }
        self.assertEqual(pool_filesystem_options(profile), [("recordsize", "128K")])

    def test_none_or_empty_profile_yields_nothing(self):
        self.assertEqual(pool_filesystem_options(None), [])
        self.assertEqual(pool_filesystem_options({}), [])


if __name__ == "__main__":
    unittest.main()

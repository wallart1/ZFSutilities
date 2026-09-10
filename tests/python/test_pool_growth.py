"""Tests for pool_growth.py — pure-logic pool-growth helpers."""

import os
import sys
import unittest

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from disk_repository import DiskInfo
from pool_growth import (
    ATTACH_MIRROR_GROW,
    ATTACH_RAIDZ_EXPANSION,
    ATTACH_STRIPE_TO_MIRROR,
    assess_detach,
    classify_attach_target,
    classify_replace_source,
    count_mirror_members,
    has_mirror_member,
    infra_vdev_notes,
    mixed_size_warning,
    raidz_expansion_notes,
    resolve_member_by_id,
    scrub_blocks_pool_op,
    validate_growth_vdev_selection,
    validate_infra_vdev,
    validate_replace_pair,
)
from zfs_repository import TopologyNode

TB = 10**12

BY_ID_A = "/dev/disk/by-id/ata-TESTa"
BY_ID_B = "/dev/disk/by-id/ata-TESTb"
BY_ID_C = "/dev/disk/by-id/ata-TESTc"
BY_ID_D = "/dev/disk/by-id/ata-TESTd"
BY_ID_E = "/dev/disk/by-id/ata-TESTe"


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


def _node(name, vdev_type, children=(), state="ONLINE"):
    """Build a TopologyNode with zeroed error counters."""
    return TopologyNode(
        name=name,
        vdev_type=vdev_type,
        state=state,
        read=0,
        write=0,
        cksum=0,
        ashift=None,
        children=list(children),
    )


def _leaf(path):
    return _node(path, "disk")


def stripe_pool():
    """Single-disk stripe pool: pool root with one disk leaf."""
    root = _node("tank", "pool")
    leaf = _leaf(BY_ID_A)
    root.children.append(leaf)
    return root, leaf


def two_way_mirror():
    root = _node("tank", "pool")
    group = _node("mirror-0", "mirror")
    first, second = _leaf(BY_ID_A), _leaf(BY_ID_B)
    group.children.extend([first, second])
    root.children.append(group)
    return root, group, first, second


def three_way_mirror():
    root = _node("tank", "pool")
    group = _node("mirror-0", "mirror")
    leaves = [_leaf(p) for p in (BY_ID_A, BY_ID_B, BY_ID_C)]
    group.children.extend(leaves)
    root.children.append(group)
    return root, group, leaves


def raidz2_pool():
    root = _node("tank", "pool")
    group = _node("raidz2-0", "raidz2")
    leaves = [_leaf(p) for p in (BY_ID_A, BY_ID_B, BY_ID_C, BY_ID_D)]
    group.children.extend(leaves)
    root.children.append(group)
    return root, group, leaves


def infra_pool():
    """Pool with log, cache, spare, special, and replacing sections."""
    root = _node("tank", "pool")
    mirror_group = _node("mirror-0", "mirror")
    mirror_leaves = [_leaf(BY_ID_A), _leaf(BY_ID_B)]
    mirror_group.children.extend(mirror_leaves)
    root.children.append(mirror_group)
    log_group = _node("log", "log")
    log_leaf = _leaf(BY_ID_C)
    log_group.children.append(log_leaf)
    cache_group = _node("cache", "cache")
    cache_leaf = _leaf(BY_ID_D)
    cache_group.children.append(cache_leaf)
    spare_group = _node("spares", "spare")
    spare_leaf = _leaf(BY_ID_E)
    spare_group.children.append(spare_leaf)
    special_group = _node("special", "special")
    special_leaf = _leaf("/dev/disk/by-id/ata-TESTf")
    special_group.children.append(special_leaf)
    replacing_group = _node("replacing-0", "unknown")
    replacing_leaf = _leaf("/dev/disk/by-id/ata-TESTg")
    replacing_group.children.append(replacing_leaf)
    root.children.extend([log_group, cache_group, spare_group, special_group, replacing_group])
    sections = {
        "log": (log_group, log_leaf),
        "cache": (cache_group, cache_leaf),
        "spare": (spare_group, spare_leaf),
        "special": (special_group, special_leaf),
        "replacing": (replacing_group, replacing_leaf),
    }
    return root, mirror_group, mirror_leaves, sections


class TestResolveMemberById(unittest.TestCase):
    """Leaf paths map to by-id forms for command building."""

    def test_by_id_path_passes_through(self):
        self.assertEqual(resolve_member_by_id(BY_ID_A, None), BY_ID_A)

    def test_path_resolves_via_inventory(self):
        disks = [_disk("/dev/sda", by_id="ata-TESTa")]
        self.assertEqual(resolve_member_by_id("/dev/sda", disks), BY_ID_A)

    def test_basename_fallback(self):
        disks = [_disk("/dev/sda", by_id="ata-TESTa")]
        self.assertEqual(resolve_member_by_id("sda", disks), BY_ID_A)

    def test_no_inventory_returns_none(self):
        self.assertIsNone(resolve_member_by_id("/dev/sda", None))

    def test_unknown_path_returns_none(self):
        self.assertIsNone(resolve_member_by_id("/dev/sdz", [_disk("/dev/sda")]))

    def test_disk_without_by_id_returns_none(self):
        disks = [_disk("/dev/sda", by_id="")]
        self.assertIsNone(resolve_member_by_id("/dev/sda", disks))

    def test_empty_path_returns_none(self):
        self.assertIsNone(resolve_member_by_id("", []))


class TestClassifyAttachTarget(unittest.TestCase):
    """Attach-target classification across the topology matrix."""

    def test_stripe_member_converts_to_mirror(self):
        root, leaf = stripe_pool()
        result = classify_attach_target(root, leaf)
        self.assertEqual(result.kind, ATTACH_STRIPE_TO_MIRROR)
        self.assertEqual(result.target_arg, BY_ID_A)
        self.assertEqual(result.error, "")

    def test_mirror_member_grows_mirror(self):
        root, _group, first, _second = two_way_mirror()
        result = classify_attach_target(root, first)
        self.assertEqual(result.kind, ATTACH_MIRROR_GROW)
        self.assertEqual(result.target_arg, BY_ID_A)

    def test_raidz_group_is_expansion(self):
        root, group, _leaves = raidz2_pool()
        result = classify_attach_target(root, group)
        self.assertEqual(result.kind, ATTACH_RAIDZ_EXPANSION)
        self.assertEqual(result.target_arg, "raidz2-0")

    def test_raidz_member_refused_with_hint(self):
        root, _group, leaves = raidz2_pool()
        result = classify_attach_target(root, leaves[0])
        self.assertTrue(result.error)
        self.assertEqual(result.kind, "")
        self.assertIn("raidz group itself", result.error)

    def test_pool_root_refused(self):
        root, _leaf = stripe_pool()
        result = classify_attach_target(root, root)
        self.assertTrue(result.error)

    def test_group_node_refused(self):
        root, group, _first, _second = two_way_mirror()
        result = classify_attach_target(root, group)
        self.assertTrue(result.error)
        self.assertIn("stripe member", result.error)

    def test_foreign_node_refused(self):
        root, _leaf = stripe_pool()
        _other, other_leaf = stripe_pool()
        result = classify_attach_target(root, other_leaf)
        self.assertTrue(result.error)
        self.assertEqual(result.kind, "")

    def test_infra_and_spare_and_replacing_leaves_refused(self):
        root, _mirror, _leaves, sections = infra_pool()
        for name in ("log", "cache", "spare", "special", "replacing"):
            with self.subTest(section=name):
                result = classify_attach_target(root, sections[name][1])
                self.assertTrue(result.error)
                self.assertEqual(result.kind, "")

    def test_leaf_resolves_through_inventory(self):
        root, leaf = stripe_pool()
        leaf.name = "/dev/sda"
        disks = [_disk("/dev/sda", by_id="ata-TESTa")]
        result = classify_attach_target(root, leaf, disks=disks)
        self.assertEqual(result.kind, ATTACH_STRIPE_TO_MIRROR)
        self.assertEqual(result.target_arg, BY_ID_A)

    def test_leaf_without_by_id_refused(self):
        root, leaf = stripe_pool()
        leaf.name = "/dev/sdz"
        result = classify_attach_target(root, leaf, disks=[])
        self.assertTrue(result.error)
        self.assertIn("by-id", result.error)


class TestCountMirrorMembers(unittest.TestCase):
    """Mirror member counts for the attach grow-mirror warning text."""

    def test_two_way_mirror_counts_two(self):
        root, _group, first, _second = two_way_mirror()
        self.assertEqual(count_mirror_members(root, first), 2)

    def test_three_way_mirror_counts_three(self):
        root, _group, leaves = three_way_mirror()
        self.assertEqual(count_mirror_members(root, leaves[2]), 3)

    def test_stripe_leaf_has_no_mirror(self):
        root, leaf = stripe_pool()
        self.assertEqual(count_mirror_members(root, leaf), 0)

    def test_mirror_group_itself_has_no_mirror(self):
        root, group, _first, _second = two_way_mirror()
        self.assertEqual(count_mirror_members(root, group), 0)

    def test_foreign_node_counts_zero(self):
        root, _leaf = stripe_pool()
        _other, other_leaf = stripe_pool()
        self.assertEqual(count_mirror_members(root, other_leaf), 0)


class TestHasMirrorMember(unittest.TestCase):
    """Pool-wide scan for a detach-eligible mirror member."""

    def test_mirror_pool_true(self):
        root, _group, _first, _second = two_way_mirror()
        self.assertTrue(has_mirror_member(root))

    def test_stripe_pool_false(self):
        root, _leaf = stripe_pool()
        self.assertFalse(has_mirror_member(root))

    def test_raidz_pool_false(self):
        root = _node(
            "tank",
            "pool",
            [_node("raidz2-0", "raidz2", [_leaf(c) for c in (BY_ID_A, BY_ID_B, BY_ID_C)])],
        )
        self.assertFalse(has_mirror_member(root))

    def test_empty_pool_false(self):
        self.assertFalse(has_mirror_member(_node("tank", "pool")))


class TestAssessDetach(unittest.TestCase):
    """Mirror-only detach policy and redundancy warnings."""

    def test_mirror_member_ok(self):
        root, _group, first, _second = two_way_mirror()
        error, warnings = assess_detach(root, first)
        self.assertEqual(error, "")
        self.assertTrue(any("redundancy" in w for w in warnings))

    def test_two_member_mirror_warns_about_stripe(self):
        root, _group, first, _second = two_way_mirror()
        error, warnings = assess_detach(root, first)
        self.assertEqual(error, "")
        self.assertTrue(any("non-redundant disk" in w for w in warnings))

    def test_three_member_mirror_no_stripe_warning(self):
        root, _group, leaves = three_way_mirror()
        error, warnings = assess_detach(root, leaves[0])
        self.assertEqual(error, "")
        self.assertFalse(any("non-redundant disk" in w for w in warnings))

    def test_raidz_member_refused(self):
        root, _group, leaves = raidz2_pool()
        error, _warnings = assess_detach(root, leaves[0])
        self.assertIn("raidz", error)

    def test_top_level_stripe_refused(self):
        root, leaf = stripe_pool()
        error, _warnings = assess_detach(root, leaf)
        self.assertTrue(error)

    def test_infra_spare_replacing_leaves_refused(self):
        root, _mirror, _leaves, sections = infra_pool()
        for name in ("log", "cache", "spare", "special", "replacing"):
            with self.subTest(section=name):
                error, _warnings = assess_detach(root, sections[name][1])
                self.assertTrue(error)

    def test_group_node_and_root_refused(self):
        root, group, _first, _second = two_way_mirror()
        error, _warnings = assess_detach(root, group)
        self.assertTrue(error)
        error, _warnings = assess_detach(root, root)
        self.assertTrue(error)

    def test_foreign_node_refused(self):
        root, _leaf = stripe_pool()
        _other, other_leaf = stripe_pool()
        error, _warnings = assess_detach(root, other_leaf)
        self.assertTrue(error)


class TestValidateReplacePair(unittest.TestCase):
    """Replace-pair validation: same-device, by-id, and size rules."""

    def _source(self, **kwargs):
        return _disk("/dev/sda", by_id="ata-TESTa", size_bytes=10 * TB, **kwargs)

    def test_smaller_replacement_warns_only(self):
        disks = [self._source()]
        replacement = _disk("/dev/sdb", by_id="ata-TESTb", size_bytes=5 * TB, size_human="5T")
        problems, warnings = validate_replace_pair(BY_ID_A, replacement, disks)
        self.assertEqual(problems, [])
        self.assertTrue(any("smaller" in w for w in warnings))

    def test_equal_or_larger_no_warning(self):
        disks = [self._source()]
        for size in (10 * TB, 12 * TB):
            with self.subTest(size=size):
                replacement = _disk("/dev/sdb", by_id="ata-TESTb", size_bytes=size)
                problems, warnings = validate_replace_pair(BY_ID_A, replacement, disks)
                self.assertEqual(problems, [])
                self.assertEqual(warnings, [])

    def test_same_path_is_problem(self):
        disks = [self._source()]
        replacement = _disk("/dev/sda", by_id="ata-TESTb")
        problems, _warnings = validate_replace_pair(BY_ID_A, replacement, disks)
        self.assertTrue(any("same device" in p for p in problems))

    def test_same_by_id_basename_is_problem(self):
        disks = [self._source()]
        replacement = _disk("/dev/sdb", by_id="ata-TESTa")
        problems, _warnings = validate_replace_pair(BY_ID_A, replacement, disks)
        self.assertTrue(any("same device" in p for p in problems))

    def test_partition_of_source_is_problem(self):
        disks = [self._source()]
        replacement = _disk("/dev/sda1", by_id="ata-TESTb", parent_path="/dev/sda")
        problems, _warnings = validate_replace_pair(BY_ID_A, replacement, disks)
        self.assertTrue(any("same device" in p for p in problems))

    def test_missing_by_id_is_problem(self):
        disks = [self._source()]
        replacement = _disk("/dev/sdb", by_id="")
        problems, _warnings = validate_replace_pair(BY_ID_A, replacement, disks)
        self.assertTrue(any("by-id" in p for p in problems))

    def test_source_not_in_inventory_is_problem(self):
        replacement = _disk("/dev/sdb", by_id="ata-TESTb")
        unknown = "/dev/disk/by-id/ata-TESTz"
        problems, _warnings = validate_replace_pair(unknown, replacement, [])
        self.assertTrue(any("not found" in p for p in problems))


class TestClassifyReplaceSource(unittest.TestCase):
    """Replace-source policy: disk leaves only, no groups, no re-replace."""

    def _disks(self):
        return [_disk(p) for p in (BY_ID_A, BY_ID_B, BY_ID_C, BY_ID_D)]

    def test_pool_root_refused(self):
        root, _leaf = stripe_pool()
        result = classify_replace_source(root, root, self._disks())
        self.assertIn("pool itself", result.error)
        self.assertEqual(result.by_id, "")

    def test_vdev_group_refused(self):
        root, group, _leaves = raidz2_pool()
        result = classify_replace_source(root, group, self._disks())
        self.assertIn("vdev group", result.error)

    def test_replacing_member_refused(self):
        root, _mirror, _leaves, sections = infra_pool()
        result = classify_replace_source(root, sections["replacing"][1], self._disks())
        self.assertIn("already being replaced", result.error)

    def test_stripe_member_resolves_by_id(self):
        root, leaf = stripe_pool()
        result = classify_replace_source(root, leaf, self._disks())
        self.assertEqual(result.error, "")
        self.assertEqual(result.by_id, BY_ID_A)

    def test_mirror_member_resolves_by_id(self):
        root, _group, _first, second = two_way_mirror()
        result = classify_replace_source(root, second, self._disks())
        self.assertEqual(result.error, "")
        self.assertEqual(result.by_id, BY_ID_B)

    def test_raidz_member_resolves_by_id(self):
        root, _group, leaves = raidz2_pool()
        result = classify_replace_source(root, leaves[2], self._disks())
        self.assertEqual(result.error, "")
        self.assertEqual(result.by_id, BY_ID_C)

    def test_member_without_by_id_refused(self):
        root = _node("tank", "pool")
        leaf = _leaf("/dev/sdz")  # no by-id identity, not in inventory
        root.children.append(leaf)
        result = classify_replace_source(root, leaf, [])
        self.assertIn("by-id", result.error)

    def test_member_resolves_via_inventory_alias(self):
        root, leaf = stripe_pool()
        disks = [_disk("/dev/sda", by_id="ata-TESTa")]
        result = classify_replace_source(root, leaf, disks)
        self.assertEqual(result.error, "")
        self.assertEqual(result.by_id, BY_ID_A)

    def test_foreign_node_refused(self):
        root, _leaf = stripe_pool()
        _other, other_leaf = stripe_pool()
        result = classify_replace_source(root, other_leaf, self._disks())
        self.assertIn("not part of this pool", result.error)


class TestValidateInfraVdev(unittest.TestCase):
    """Infra-vdev rules: special mirror-required, log mirror-recommended,
    cache never mirrored, device separation reused."""

    def test_special_stripe_refused(self):
        problems, warnings = validate_infra_vdev("special", "stripe", [_disk("/dev/sda")])
        self.assertTrue(any("must be a mirror" in p for p in problems))
        self.assertTrue(any("entire pool" in w for w in warnings))

    def test_special_mirror_ok_with_pool_loss_warning(self):
        problems, warnings = validate_infra_vdev(
            "special", "mirror", [_disk("/dev/sda"), _disk("/dev/sdb")]
        )
        self.assertEqual(problems, [])
        self.assertTrue(any("entire pool" in w for w in warnings))

    def test_special_mirror_min_count_enforced(self):
        problems, _warnings = validate_infra_vdev("special", "mirror", [_disk("/dev/sda")])
        self.assertTrue(any("at least 2" in p for p in problems))

    def test_log_stripe_warned_not_refused(self):
        problems, warnings = validate_infra_vdev("log", "stripe", [_disk("/dev/sda")])
        self.assertEqual(problems, [])
        self.assertTrue(any("mirrored log is recommended" in w for w in warnings))

    def test_log_mirror_ok(self):
        problems, warnings = validate_infra_vdev(
            "log", "mirror", [_disk("/dev/sda"), _disk("/dev/sdb")]
        )
        self.assertEqual(problems, [])
        self.assertEqual(warnings, [])

    def test_cache_mirror_refused(self):
        problems, _warnings = validate_infra_vdev(
            "cache", "mirror", [_disk("/dev/sda"), _disk("/dev/sdb")]
        )
        self.assertTrue(any("cannot be mirrored" in p for p in problems))

    def test_cache_stripe_ok(self):
        problems, warnings = validate_infra_vdev("cache", "stripe", [_disk("/dev/sda")])
        self.assertEqual(problems, [])
        self.assertEqual(warnings, [])

    def test_unknown_kind_refused(self):
        problems, _warnings = validate_infra_vdev("dedup", "mirror", [_disk("/dev/sda")])
        self.assertTrue(problems)

    def test_same_parent_partitions_refused(self):
        first = _disk("/dev/sda1", parent_path="/dev/sda")
        second = _disk("/dev/sda2", parent_path="/dev/sda")
        problems, _warnings = validate_infra_vdev("special", "mirror", [first, second])
        self.assertTrue(any("same physical device" in p for p in problems))

    def test_notes_are_tailored_per_kind(self):
        special = infra_vdev_notes("special")
        log = infra_vdev_notes("log")
        cache = infra_vdev_notes("cache")
        self.assertTrue(any("entire pool" in line for line in special))
        self.assertTrue(any("sync" in line for line in log))
        self.assertTrue(any("read cache" in line for line in cache))
        self.assertNotEqual(special, log)
        self.assertNotEqual(log, cache)

    def test_notes_unknown_kind_raises(self):
        with self.assertRaises(ValueError):
            infra_vdev_notes("dedup")


class TestGrowthVdevSelection(unittest.TestCase):
    """Add-Data-Vdev membership delegation and mixed-size warnings."""

    def test_clean_selection_no_problems(self):
        selected = [_disk("/dev/sda"), _disk("/dev/sdb")]
        self.assertEqual(validate_growth_vdev_selection(selected), [])

    def test_same_parent_partitions_problem(self):
        selected = [
            _disk("/dev/sda1", parent_path="/dev/sda"),
            _disk("/dev/sda2", parent_path="/dev/sda"),
        ]
        problems = validate_growth_vdev_selection(selected)
        self.assertTrue(any("same physical device" in p for p in problems))

    def test_mixed_sizes_warn(self):
        selected = [_disk("/dev/sda", size_bytes=10 * TB), _disk("/dev/sdb", size_bytes=5 * TB)]
        warning = mixed_size_warning(selected)
        self.assertIsNotNone(warning)
        self.assertIn("smallest", warning)

    def test_uniform_sizes_no_warning(self):
        selected = [_disk("/dev/sda"), _disk("/dev/sdb")]
        self.assertIsNone(mixed_size_warning(selected))

    def test_unknown_sizes_no_warning(self):
        selected = [_disk("/dev/sda", size_bytes=0), _disk("/dev/sdb", size_bytes=0)]
        self.assertIsNone(mixed_size_warning(selected))


class TestScrubBlocksPoolOp(unittest.TestCase):
    """Scrub-state coordination for pool operations."""

    _SCANNING = "  scan: scrub in progress since Sun Sep  1 00:00:00 2024\n    12.5% done"
    _PAUSED = "  scan: scrub paused since Sun Sep  1 00:00:00 2024\n    12.5% done"
    _FINISHED = (
        "  scan: scrub repaired 0B in 0 days 01:00:00 with 0 errors on Sun Sep  1 01:00:00 2024"
    )
    _CANCELED = "  scan: scrub canceled on Sun Sep  1 00:30:00 2024"
    _NONE = "  scan: none requested"

    class _FakeRepo:
        def __init__(self, raw="", exc=None):
            self._raw = raw
            self._exc = exc

        def pool_status(self, pool, timeout=None):
            if self._exc is not None:
                raise self._exc
            return self._raw

    def test_scanning_blocks(self):
        message = scrub_blocks_pool_op("tank", self._FakeRepo(self._SCANNING))
        self.assertIsNotNone(message)
        self.assertIn("tank", message)
        self.assertIn("scanning", message)

    def test_paused_blocks(self):
        message = scrub_blocks_pool_op("tank", self._FakeRepo(self._PAUSED))
        self.assertIsNotNone(message)
        self.assertIn("paused", message)

    def test_finished_does_not_block(self):
        self.assertIsNone(scrub_blocks_pool_op("tank", self._FakeRepo(self._FINISHED)))

    def test_canceled_does_not_block(self):
        self.assertIsNone(scrub_blocks_pool_op("tank", self._FakeRepo(self._CANCELED)))

    def test_none_does_not_block(self):
        self.assertIsNone(scrub_blocks_pool_op("tank", self._FakeRepo(self._NONE)))

    def test_empty_status_does_not_block(self):
        self.assertIsNone(scrub_blocks_pool_op("tank", self._FakeRepo("")))

    def test_repo_error_does_not_block(self):
        repo = self._FakeRepo(exc=OSError("boom"))
        self.assertIsNone(scrub_blocks_pool_op("tank", repo))


class TestRaidzExpansionNotes(unittest.TestCase):
    """RAIDZ-expansion warning text covers parity ratio and rewrite follow-up."""

    def test_notes_cover_ratio_and_rewrite(self):
        notes = raidz_expansion_notes()
        self.assertEqual(len(notes), 2)
        self.assertTrue(any("data:parity ratio" in note for note in notes))
        self.assertTrue(any("Rewrite Data" in note for note in notes))


class TestInfraVdevNotes(unittest.TestCase):
    """Per-kind explainer lines shown in the Add Infra Vdev warnings section."""

    def test_log_notes_cover_write_loss_window_and_sizing(self):
        notes = infra_vdev_notes("log")
        self.assertEqual(len(notes), 3)
        self.assertTrue(any("acknowledged" in note for note in notes))
        self.assertTrue(any("application data, not metadata" in note for note in notes))
        self.assertTrue(any("mirror the SLOG" in note for note in notes))
        self.assertTrue(any("5 seconds" in note for note in notes))

    def test_unknown_kind_raises(self):
        with self.assertRaises(ValueError):
            infra_vdev_notes("dedup")


if __name__ == "__main__":
    unittest.main()

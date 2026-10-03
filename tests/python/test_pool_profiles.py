"""Tests for pool_profiles.py — pure pool-profile helpers."""

import os
import sys
import unittest

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from pool_profiles import (
    ASHIFT_BY_LABEL,
    BLOCKSIZE_AUTO,
    BLOCKSIZE_CHOICES,
    BLOCKSIZE_RECOMMENDED,
    LABEL_BY_ASHIFT,
    MATCH_ORIGIN_PROFILE,
    POOL_PROPERTIES,
    POOL_PROPERTY_VALUES,
    blocksize_below_recommendation,
    blocksize_label_for_ashift,
    data_vdev_leaves,
    filesystem_options_for_profile,
    filesystem_properties_for_profile,
    infra_vdev_classes,
    origin_profile,
    pool_options_for_profile,
    pool_properties_for_profile,
    replayable_pool_properties,
    resolve_blocksize,
    validate_profile,
)
from workload_profiles import LIVE_PROPERTIES
from zfs_repository import TopologyNode


def _disk(name):
    return TopologyNode(
        name=name,
        vdev_type="disk",
        state="ONLINE",
        read=0,
        write=0,
        cksum=0,
        ashift=None,
        children=[],
    )


def _vdev(vdev_type, name, children):
    return TopologyNode(
        name=name,
        vdev_type=vdev_type,
        state="ONLINE",
        read=0,
        write=0,
        cksum=0,
        ashift=None,
        children=children,
    )


def _pool(children):
    return TopologyNode(
        name="tank",
        vdev_type="pool",
        state="ONLINE",
        read=0,
        write=0,
        cksum=0,
        ashift=12,
        children=children,
    )


class TestSchemaConstants(unittest.TestCase):
    """Constant sanity: every curated property has allowed values."""

    def test_every_pool_property_has_values(self):
        for prop in POOL_PROPERTIES:
            self.assertIn(prop, POOL_PROPERTY_VALUES)
            self.assertTrue(POOL_PROPERTY_VALUES[prop])

    def test_label_maps_are_inverse(self):
        for label, ashift in ASHIFT_BY_LABEL.items():
            self.assertEqual(LABEL_BY_ASHIFT[ashift], label)
        self.assertEqual(len(ASHIFT_BY_LABEL), len(LABEL_BY_ASHIFT))

    def test_blocksize_choices_vocabulary(self):
        self.assertEqual(BLOCKSIZE_CHOICES[0], BLOCKSIZE_RECOMMENDED)
        self.assertIn(BLOCKSIZE_AUTO, BLOCKSIZE_CHOICES)
        for label in ASHIFT_BY_LABEL:
            self.assertIn(label, BLOCKSIZE_CHOICES)

    def test_match_origin_sentinel_is_not_a_choice(self):
        # The pseudo-profile is a dialog entry, never a stored blocksize value.
        self.assertNotIn(MATCH_ORIGIN_PROFILE, BLOCKSIZE_CHOICES)


class TestPropertiesForProfile(unittest.TestCase):
    """Property extraction and schema restriction."""

    def test_pool_properties_for_profile_filters_unknown(self):
        profile = {"pool_properties": {"autotrim": "on", "bogus": "x"}}
        self.assertEqual(pool_properties_for_profile(profile), {"autotrim": "on"})

    def test_pool_properties_for_profile_none_and_empty(self):
        self.assertEqual(pool_properties_for_profile(None), {})
        self.assertEqual(pool_properties_for_profile({}), {})

    def test_filesystem_properties_for_profile_filters_unknown(self):
        profile = {"filesystem_properties": {"compression": "zstd", "bogus": "1"}}
        self.assertEqual(filesystem_properties_for_profile(profile), {"compression": "zstd"})

    def test_filesystem_properties_for_profile_none_and_empty(self):
        self.assertEqual(filesystem_properties_for_profile(None), {})
        self.assertEqual(filesystem_properties_for_profile({}), {})


class TestOptionBuilders(unittest.TestCase):
    """Canonical -o / -O ordering regardless of dict order."""

    def test_pool_options_follow_canonical_order(self):
        profile = {
            "pool_properties": {
                "delegation": "on",
                "autotrim": "on",
                "failmode": "wait",
            }
        }
        pairs = pool_options_for_profile(profile)
        self.assertEqual(pairs, [("autotrim", "on"), ("failmode", "wait"), ("delegation", "on")])

    def test_filesystem_options_follow_live_order(self):
        profile = {
            "filesystem_properties": {
                "compression": "lz4",
                "recordsize": "128K",
            }
        }
        pairs = filesystem_options_for_profile(profile)
        self.assertEqual(
            pairs,
            [("recordsize", "128K"), ("compression", "lz4")],
        )
        self.assertEqual(
            [prop for prop, _ in pairs],
            [p for p in LIVE_PROPERTIES if p in ("recordsize", "compression")],
        )

    def test_option_builders_empty_profile(self):
        self.assertEqual(pool_options_for_profile(None), [])
        self.assertEqual(filesystem_options_for_profile(None), [])


class TestBlocksizeHelpers(unittest.TestCase):
    """Blocksize resolution, labels, and the below-recommendation check."""

    def test_resolve_recommended_adopts_recommendation(self):
        self.assertEqual(resolve_blocksize("recommended", 13), 13)

    def test_resolve_recommended_without_recommendation_is_auto(self):
        self.assertIsNone(resolve_blocksize("recommended", None))

    def test_resolve_auto_is_none(self):
        self.assertIsNone(resolve_blocksize("auto", 13))

    def test_resolve_label_maps_to_ashift(self):
        self.assertEqual(resolve_blocksize("512 bytes", 13), 9)
        self.assertEqual(resolve_blocksize("4096 bytes", 13), 12)
        self.assertEqual(resolve_blocksize("8192 bytes", 13), 13)

    def test_resolve_unknown_is_none(self):
        self.assertIsNone(resolve_blocksize("1048576 bytes", 13))

    def test_label_for_ashift(self):
        self.assertEqual(blocksize_label_for_ashift(None), "auto")
        self.assertEqual(blocksize_label_for_ashift(9), "512 bytes")
        self.assertEqual(blocksize_label_for_ashift(12), "4096 bytes")
        self.assertEqual(blocksize_label_for_ashift(13), "8192 bytes")
        self.assertEqual(blocksize_label_for_ashift(14), "16384 bytes")

    def test_below_recommendation(self):
        self.assertTrue(blocksize_below_recommendation(9, 12))
        self.assertFalse(blocksize_below_recommendation(12, 12))
        self.assertFalse(blocksize_below_recommendation(13, 12))
        self.assertFalse(blocksize_below_recommendation(None, 12))
        self.assertFalse(blocksize_below_recommendation(9, None))


class TestValidateProfile(unittest.TestCase):
    """Structural validation."""

    def _profile(self, **overrides):
        profile = {
            "description": "test",
            "blocksize": "recommended",
            "pool_properties": {"autotrim": "on"},
            "filesystem_properties": {"compression": "lz4"},
            "notes": "",
        }
        profile.update(overrides)
        return profile

    def test_valid_profile_has_no_problems(self):
        self.assertEqual(validate_profile(self._profile()), [])

    def test_missing_blocksize_defaults_to_recommended(self):
        profile = self._profile()
        del profile["blocksize"]
        self.assertEqual(validate_profile(profile), [])

    def test_unknown_blocksize(self):
        problems = validate_profile(self._profile(blocksize="tiny"))
        self.assertEqual(len(problems), 1)
        self.assertIn("blocksize", problems[0])

    def test_unknown_pool_property(self):
        problems = validate_profile(self._profile(pool_properties={"dedupditto": "1"}))
        self.assertEqual(len(problems), 1)
        self.assertIn("unknown pool property", problems[0])

    def test_bad_pool_property_value(self):
        problems = validate_profile(self._profile(pool_properties={"autotrim": "1"}))
        self.assertEqual(len(problems), 1)
        self.assertIn("must be one of", problems[0])

    def test_unknown_filesystem_property(self):
        problems = validate_profile(self._profile(filesystem_properties={"volblocksize": "16K"}))
        self.assertEqual(len(problems), 1)
        self.assertIn("unknown filesystem property", problems[0])


class TestOriginProfile(unittest.TestCase):
    """The "Match origin pool" pseudo-profile builder."""

    def test_origin_profile_carries_settings(self):
        profile = origin_profile(
            12,
            {"autotrim": "on", "bogus": "x"},
            {"compression": "zstd", "volblocksize": "16K"},
        )
        self.assertEqual(profile["blocksize"], "4096 bytes")
        self.assertEqual(profile["pool_properties"], {"autotrim": "on"})
        self.assertEqual(profile["filesystem_properties"], {"compression": "zstd"})
        self.assertTrue(profile["description"])
        self.assertTrue(profile["notes"])

    def test_origin_profile_unprobeable_ashift_is_auto(self):
        profile = origin_profile(None, {}, {})
        self.assertEqual(profile["blocksize"], "auto")
        self.assertEqual(profile["pool_properties"], {})
        self.assertEqual(profile["filesystem_properties"], {})

    def test_origin_profile_never_named_as_a_choice(self):
        profile = origin_profile(12, {}, {})
        self.assertNotEqual(profile["blocksize"], MATCH_ORIGIN_PROFILE)


class TestInfraVdevClasses(unittest.TestCase):
    """Infra-vdev classification for the migration warning."""

    def test_data_only_topology_has_no_infra(self):
        topology = _pool([_vdev("raidz", "raidz1-0", [_disk("a"), _disk("b")])])
        self.assertEqual(infra_vdev_classes(topology), [])

    def test_infra_classes_and_leaves_are_reported(self):
        topology = _pool(
            [
                _vdev("mirror", "mirror-0", [_disk("a"), _disk("b")]),
                _vdev(
                    "special", "special", [_vdev("mirror", "mirror-1", [_disk("s1"), _disk("s2")])]
                ),
                _vdev("log", "logs", [_disk("l1")]),
                _vdev("cache", "cache", [_disk("c1"), _disk("c2")]),
                _vdev("spare", "spares", [_disk("sp1")]),
            ]
        )
        classes = infra_vdev_classes(topology)
        self.assertEqual(
            classes,
            [
                ("special", ["s1", "s2"]),
                ("log", ["l1"]),
                ("cache", ["c1", "c2"]),
                ("spare", ["sp1"]),
            ],
        )

    def test_missing_topology_is_empty(self):
        self.assertEqual(infra_vdev_classes(None), [])


class TestReplayablePoolProperties(unittest.TestCase):
    """Filtering zpool get all results down to the replayable set."""

    def test_keeps_local_properties_outside_the_curated_set(self):
        raw = {
            "comment": ("migration source", "local"),
            "compatibility": ("off", "local"),
            "dedup_table_quota": ("25%", "local"),
        }
        self.assertEqual(
            replayable_pool_properties(raw),
            {
                "comment": "migration source",
                "compatibility": "off",
                "dedup_table_quota": "25%",
            },
        )

    def test_drops_non_local_sources(self):
        raw = {
            "comment": ("-", "default"),
            "autotrim": ("off", "-"),
            "size": ("10T", "-"),
            "capacity": ("3%", "-"),
        }
        self.assertEqual(replayable_pool_properties(raw), {})

    def test_drops_curated_properties(self):
        # The curated seven travel through the chosen pool profile's -o
        # options; replaying origin values would clobber a saved profile.
        raw = {prop: ("on", "local") for prop in POOL_PROPERTIES}
        self.assertEqual(replayable_pool_properties(raw), {})

    def test_drops_features_and_create_only_properties(self):
        raw = {
            "feature@async_destroy": ("active", "local"),
            "feature@encryption": ("enabled", "local"),
            "ashift": ("12", "local"),
            "altroot": ("/mnt/x", "local"),
            "cachefile": ("-", "local"),
            "version": ("5000", "local"),
            "comment": ("kept", "local"),
        }
        self.assertEqual(replayable_pool_properties(raw), {"comment": "kept"})

    def test_empty_input(self):
        self.assertEqual(replayable_pool_properties({}), {})


class TestDataVdevLeaves(unittest.TestCase):
    """Data-vdev leaf extraction (the complement of infra_vdev_classes)."""

    def test_data_only_pool_returns_all_leaves(self):
        topology = _pool(
            [
                _vdev("raidz", "raidz1-0", [_disk("a"), _disk("b")]),
                _vdev("disk", "c", []),
            ]
        )
        self.assertEqual(data_vdev_leaves(topology), ["a", "b", "c"])

    def test_infra_leaves_are_excluded(self):
        topology = _pool(
            [
                _vdev("mirror", "mirror-0", [_disk("a"), _disk("b")]),
                _vdev(
                    "special", "special", [_vdev("mirror", "mirror-1", [_disk("s1"), _disk("s2")])]
                ),
                _vdev("log", "logs", [_disk("l1")]),
                _vdev("cache", "cache", [_disk("c1"), _disk("c2")]),
                _vdev("spare", "spares", [_disk("sp1")]),
            ]
        )
        self.assertEqual(data_vdev_leaves(topology), ["a", "b"])

    def test_missing_topology_is_empty(self):
        self.assertEqual(data_vdev_leaves(None), [])

    def test_bare_disk_pool_returns_the_disk(self):
        topology = _pool([_disk("solo")])
        self.assertEqual(data_vdev_leaves(topology), ["solo"])


if __name__ == "__main__":
    unittest.main()

"""Tests for alignment_analysis.py — every advisory rule, red and green."""

import os
import sys
import unittest

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

import alignment_analysis as ana
import alignment_stats as als
from zfs_repository import TopologyNode


def _topo_node(name, vdev_type, children=None):
    return TopologyNode(
        name=name,
        vdev_type=vdev_type,
        state="ONLINE" if vdev_type == "disk" else "-",
        read=0,
        write=0,
        cksum=0,
        ashift=None,
        children=children or [],
    )


def _pool(name="fivebays", ashift=12, members=None, has_cache=False, topology=None):
    member_rows = [
        als.MemberDisk(path=path, logical_sector=logical, physical_sector=physical)
        for path, logical, physical in (members or [])
    ]
    return als.PoolAlignment(
        name=name,
        ashift_configured=str(ashift) if ashift is not None else "0",
        ashift_effective=ashift,
        topology=topology,
        members=member_rows,
        has_cache=has_cache,
    )


def _objset(reads=0, nread=0, writes=0, nwritten=0):
    """One dataset's since-boot objset counters."""
    return {"reads": reads, "nread": nread, "writes": writes, "nwritten": nwritten}


def _fs(name, recordsize="128K", source="local"):
    return als.DatasetBlocks(
        name=name,
        kind="filesystem",
        recordsize=recordsize,
        recordsize_source=source,
    )


def _vol(name, volblocksize="16K"):
    return als.DatasetBlocks(
        name=name,
        kind="volume",
        volblocksize=volblocksize,
        volblocksize_source="-",
    )


def _hist(sync_ind=None, sync_agg=None, async_ind=None, async_agg=None):
    """Build a histogram from {bucket: count} maps on the write columns."""
    hist = als.ReqHistogram(pool="fivebays")
    for column, kind, counts in (
        ("sync_write", "ind", sync_ind),
        ("sync_write", "agg", sync_agg),
        ("async_write", "ind", async_ind),
        ("async_write", "agg", async_agg),
    ):
        for bucket, count in (counts or {}).items():
            hist.add(bucket, kind, column, count)
    return hist


def _sample(
    pools=None,
    datasets=None,
    histograms=None,
    arc=None,
    prefetch=None,
    vm_disks=None,
    pve=False,
    objset=None,
    monotonic=0.0,
):
    return als.AlignmentSample(
        monotonic=monotonic,
        pools=pools if pools is not None else [],
        datasets=datasets or [],
        histograms=histograms if histograms is not None else {},
        vm_disks=vm_disks or {},
        arc=arc if arc is not None else {},
        prefetch=prefetch if prefetch is not None else {},
        objset=objset if objset is not None else {},
        objset_available=objset is not None,
        pools_available=pools is not None,
        datasets_available=pools is not None,
        iostat_r_available=histograms is not None,
        arcstats_available=arc is not None,
        prefetch_available=prefetch is not None,
        pve_available=pve,
    )


def _findings_for(sample, survey=None, profiles=None, prev_sample=None, layer=None, subject=None):
    rows = ana.analyse(sample, survey=survey, profiles=profiles, prev_sample=prev_sample)
    return [
        row
        for row in rows
        if (layer is None or row.layer == layer) and (subject is None or row.subject == subject)
    ]


class TestClassifyWorkload(unittest.TestCase):
    def test_random_sync_without_prefetch(self):
        verdict = ana.classify_workload(_hist(sync_ind={8192: 5000}, async_agg={65536: 500}))
        self.assertEqual(verdict.label, "random-sync")
        self.assertEqual(verdict.confidence, "low")
        self.assertGreaterEqual(verdict.sync_share, 0.5)

    def test_random_sync_with_prefetch(self):
        verdict = ana.classify_workload(_hist(sync_ind={8192: 5000}), {"hits": 10, "misses": 990})
        self.assertEqual(verdict.label, "random-sync")
        self.assertEqual(verdict.confidence, "high")
        self.assertLess(verdict.prefetch_rate, ana.PREFETCH_EFFECTIVE)

    def test_sequential_via_prefetch(self):
        verdict = ana.classify_workload(
            _hist(sync_ind={8192: 2000}, async_ind={65536: 2000}),
            {"hits": 90, "misses": 10},
        )
        self.assertEqual(verdict.label, "sequential")
        self.assertEqual(verdict.confidence, "high")

    def test_sequential_via_aggregation(self):
        verdict = ana.classify_workload(_hist(sync_agg={65536: 500}, async_agg={1048576: 9000}))
        self.assertEqual(verdict.label, "sequential")
        self.assertEqual(verdict.confidence, "low")

    def test_insufficient_traffic(self):
        verdict = ana.classify_workload(_hist(sync_ind={512: 999}), {"hits": 1, "misses": 9})
        self.assertEqual(verdict.label, "insufficient")
        self.assertEqual(verdict.confidence, "high")

    def test_no_histogram(self):
        self.assertEqual(ana.classify_workload(None).label, "unknown")


class TestPoolDeviceFindings(unittest.TestCase):
    def test_ashift_below_physical_sector_warns(self):
        sample = _sample(
            pools=[_pool(ashift=9, members=[("/dev/sdb", 512, 4096), ("/dev/sdc", 512, 4096)])]
        )
        rows = _findings_for(sample, layer="Pool")
        self.assertEqual(rows[0].severity, ana.SEV_WARN)
        self.assertIn("below the 4K physical sector", rows[0].message)
        self.assertIn("read-modify-write", rows[0].recommendation)
        self.assertIn("Migrate Pool", rows[0].recommendation)

    def test_ashift_covers_physical_sector_ok(self):
        sample = _sample(pools=[_pool(ashift=12, members=[("/dev/sdb", 512, 4096)])])
        rows = _findings_for(sample, layer="Pool")
        self.assertEqual(rows[0].severity, ana.SEV_OK)
        self.assertIn("covers the largest member physical sector", rows[0].message)

    def test_mixed_geometry_info(self):
        sample = _sample(
            pools=[_pool(ashift=12, members=[("/dev/sdb", 512, 512), ("/dev/sdc", 512, 4096)])]
        )
        rows = _findings_for(sample, layer="Pool")
        self.assertTrue(
            any(
                row.severity == ana.SEV_INFO and "mixed member geometry" in row.message
                for row in rows
            )
        )

    def test_effective_ashift_unavailable(self):
        sample = _sample(pools=[_pool(ashift=None)])
        rows = _findings_for(sample, layer="Pool")
        self.assertEqual(rows[0].severity, ana.SEV_INFO)
        self.assertIn("effective ashift unavailable", rows[0].message)

    def test_member_without_sector_data_noted(self):
        sample = _sample(
            pools=[_pool(ashift=12, members=[("/dev/sdb", 512, 4096), ("/dev/sdc", None, None)])]
        )
        rows = _findings_for(sample, layer="Pool")
        self.assertIn("1 members without sector data", rows[0].message)


class TestDatasetFindings(unittest.TestCase):
    def test_recordsize_below_ashift_block_warns(self):
        sample = _sample(pools=[_pool(ashift=12)], datasets=[_fs("fivebays/db", recordsize="512")])
        rows = _findings_for(sample, layer="Dataset", subject="fivebays/db")
        self.assertEqual(rows[0].severity, ana.SEV_WARN)
        self.assertIn("padded to the ashift block", rows[0].recommendation)

    def test_volblocksize_below_ashift_block_warns(self):
        sample = _sample(
            pools=[_pool(ashift=12)],
            datasets=[_vol("fivebays/vm-201-disk-0", volblocksize="512")],
        )
        rows = _findings_for(sample, layer="Dataset", subject="fivebays/vm-201-disk-0")
        self.assertEqual(rows[0].severity, ana.SEV_WARN)
        self.assertIn("fixed at zvol creation", rows[0].recommendation)

    def test_survey_mismatch_info(self):
        sample = _sample(
            pools=[_pool(ashift=12)],
            datasets=[_fs("fivebays/db", recordsize="128K", source="inherited from fivebays")],
        )
        profiles = {
            "database-postgresql": {
                "applies_to": ["filesystem"],
                "properties": {"recordsize": "8K"},
            }
        }
        rows = _findings_for(
            sample,
            survey={"fivebays/db": "database-postgresql"},
            profiles=profiles,
            layer="Dataset",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].severity, ana.SEV_INFO)
        self.assertIn("database-postgresql", rows[0].message)
        self.assertIn("8K", rows[0].message)

    def test_survey_match_is_silent(self):
        sample = _sample(pools=[_pool(ashift=12)], datasets=[_fs("fivebays/db", recordsize="8K")])
        rows = _findings_for(
            sample,
            survey={"fivebays/db": "database-postgresql"},
            profiles={
                "database-postgresql": {
                    "applies_to": ["filesystem"],
                    "properties": {"recordsize": "8K"},
                }
            },
            layer="Dataset",
        )
        self.assertEqual(rows, [])


class TestObservationFindings(unittest.TestCase):
    def test_histograms_unavailable(self):
        sample = _sample(pools=[_pool(ashift=12)])
        sample.iostat_r_available = False
        rows = _findings_for(sample, layer="Pool", subject="(all)")
        self.assertEqual(rows[0].severity, ana.SEV_INFO)
        self.assertIn("histograms unavailable", rows[0].message)

    def test_insufficient_traffic(self):
        sample = _sample(
            pools=[_pool(ashift=12)], histograms={"fivebays": _hist(sync_ind={512: 50})}
        )
        rows = _findings_for(sample, layer="Pool")
        self.assertTrue(any("insufficient observed traffic" in row.message for row in rows))

    def test_random_sync_recordsize_advice(self):
        sample = _sample(
            pools=[_pool(ashift=12)],
            datasets=[_fs("fivebays/db", recordsize="128K")],
            histograms={"fivebays": _hist(sync_ind={8192: 5000})},
        )
        rows = _findings_for(sample, layer="Dataset", subject="fivebays")
        self.assertEqual(len(rows), 1)
        self.assertIn("sync traffic is dominated by 8K requests", rows[0].message)
        self.assertIn("fivebays/db", rows[0].message)
        self.assertIn("read-modify-write amplification", rows[0].recommendation)

    def test_random_sync_no_advice_when_close(self):
        sample = _sample(
            pools=[_pool(ashift=12)],
            datasets=[_fs("fivebays/db", recordsize="8K")],
            histograms={"fivebays": _hist(sync_ind={8192: 5000})},
        )
        self.assertEqual(_findings_for(sample, layer="Dataset", subject="fivebays"), [])

    def test_random_sync_zvol_partial_block_advice(self):
        sample = _sample(
            pools=[_pool(ashift=12)],
            datasets=[_vol("fivebays/vm-201-disk-0", volblocksize="16K")],
            histograms={"fivebays": _hist(sync_ind={4096: 5000})},
        )
        rows = _findings_for(sample, layer="VM", subject="fivebays")
        self.assertEqual(len(rows), 1)
        self.assertIn("partial-block", rows[0].recommendation)
        self.assertIn("fixed at creation", rows[0].recommendation)

    def test_sequential_larger_recordsize_advice(self):
        sample = _sample(
            pools=[_pool(ashift=12)],
            datasets=[_fs("fivebays/media", recordsize="128K")],
            histograms={"fivebays": _hist(async_agg={1048576: 9000}, sync_agg={65536: 100})},
        )
        rows = _findings_for(sample, layer="Dataset", subject="fivebays")
        self.assertEqual(len(rows), 1)
        self.assertIn("sequential traffic aggregates into 1M requests", rows[0].message)
        self.assertIn("larger recordsize", rows[0].recommendation)

    def test_low_confidence_noted_without_prefetch(self):
        sample = _sample(
            pools=[_pool(ashift=12)],
            datasets=[_fs("fivebays/db", recordsize="128K")],
            histograms={"fivebays": _hist(sync_ind={8192: 5000})},
        )
        rows = _findings_for(sample, layer="Dataset", subject="fivebays")
        self.assertIn("histogram-only, low confidence", rows[0].message)


class TestDatasetObservationFindings(unittest.TestCase):
    """Per-dataset observed request sizes (objset kstats) as an advice basis."""

    def test_objset_unavailable_notes_the_per_pool_limit(self):
        """Histogram advice stays per-pool and a finding states that limit."""
        sample = _sample(
            pools=[_pool(ashift=12)],
            datasets=[_fs("fivebays/db", recordsize="128K")],
            histograms={"fivebays": _hist(sync_ind={8192: 5000})},
        )
        rows = _findings_for(sample, layer="Dataset", subject="(all)")
        self.assertEqual(
            [(row.key, row.severity) for row in rows],
            [("objset-unavailable", ana.SEV_INFO)],
        )
        self.assertIn("falls back to the per-pool histogram", rows[0].message)
        self.assertIn("survey answers remain", rows[0].recommendation)
        # The per-pool histogram advice still fires (the fallback basis).
        pool_subject = _findings_for(sample, layer="Dataset", subject="fivebays")
        self.assertTrue(any(row.key == "obs-rmw-recordsize" for row in pool_subject))
        # No per-dataset observed-size findings without the counters.
        self.assertFalse(any(row.key.startswith("obs-dataset-") for row in pool_subject))

    def test_write_size_below_recordsize_advises_shrink(self):
        sample = _sample(
            pools=[_pool(ashift=12)],
            datasets=[_fs("fivebays/db", recordsize="128K")],
            objset={"fivebays/db": _objset(writes=5000, nwritten=5000 * 4096)},
        )
        rows = _findings_for(sample, layer="Dataset", subject="fivebays/db")
        self.assertEqual(
            [(row.key, row.severity) for row in rows],
            [("obs-dataset-recordsize-rmw", ana.SEV_INFO)],
        )
        self.assertIn("average 4K (since boot)", rows[0].message)
        self.assertIn("recordsize is 128K", rows[0].message)
        self.assertIn("read-modify-write", rows[0].recommendation)

    def test_interval_basis_preferred_when_window_carried_traffic(self):
        """A live interval overrides the since-boot cumulative average."""
        prev = _sample(
            pools=[_pool(ashift=12)],
            datasets=[_fs("fivebays/db", recordsize="128K")],
            objset={
                "fivebays/db": _objset(reads=900, nread=7_372_800, writes=900, nwritten=7_372_800)
            },
            monotonic=90.0,
        )
        cur = _sample(
            pools=prev.pools,
            datasets=prev.datasets,
            objset={
                # Boot averages are 6048 B/op; the interval added 4K/op.
                "fivebays/db": _objset(
                    reads=1000, nread=7_372_800 + 409_600, writes=1000, nwritten=7_372_800 + 409_600
                )
            },
            monotonic=100.0,
        )
        rows = _findings_for(cur, prev_sample=prev, layer="Dataset", subject="fivebays/db")
        self.assertEqual(len(rows), 1)
        self.assertIn("average 4K (over the last refresh interval)", rows[0].message)

    def test_below_op_floor_stays_silent(self):
        sample = _sample(
            pools=[_pool(ashift=12)],
            datasets=[_fs("fivebays/db", recordsize="128K")],
            objset={"fivebays/db": _objset(writes=10, nwritten=40_960)},
        )
        rows = _findings_for(sample, layer="Dataset", subject="fivebays/db")
        self.assertEqual(rows, [])

    def test_read_size_above_recordsize_advises_grow(self):
        sample = _sample(
            pools=[_pool(ashift=12)],
            datasets=[_fs("fivebays/media", recordsize="128K")],
            objset={"fivebays/media": _objset(reads=2000, nread=2000 * 1024**2)},
        )
        rows = _findings_for(sample, layer="Dataset", subject="fivebays/media")
        self.assertEqual(
            [(row.key, row.severity) for row in rows],
            [("obs-dataset-recordsize-grow", ana.SEV_INFO)],
        )
        self.assertIn("average 1M (since boot)", rows[0].message)
        self.assertIn("spans several records", rows[0].message)

    def test_zvol_observed_write_size_partial_block_advice(self):
        sample = _sample(
            pools=[_pool(ashift=12)],
            datasets=[_vol("fivebays/vm-201-disk-0", volblocksize="16K")],
            objset={"fivebays/vm-201-disk-0": _objset(writes=4000, nwritten=4000 * 4096)},
        )
        rows = _findings_for(sample, layer="VM", subject="fivebays/vm-201-disk-0")
        self.assertEqual(
            [(row.key, row.severity) for row in rows],
            [("obs-dataset-volblocksize-rmw", ana.SEV_INFO)],
        )
        self.assertIn("guest writes to vm-201-disk-0 average 4K", rows[0].message)
        self.assertIn("volblocksize is 16K", rows[0].message)
        self.assertIn("fixed at creation", rows[0].recommendation)

    def test_survey_declaration_noted_in_the_message(self):
        sample = _sample(
            pools=[_pool(ashift=12)],
            datasets=[_fs("fivebays/db", recordsize="128K", source="local")],
            objset={"fivebays/db": _objset(writes=5000, nwritten=5000 * 4096)},
        )
        rows = _findings_for(sample, survey={"fivebays/db": "media-library"})
        row = next(row for row in rows if row.key == "obs-dataset-recordsize-rmw")
        self.assertIn("survey declares 'media-library'", row.message)
        self.assertIn("may be stale", row.recommendation)

    def test_pool_level_histogram_advice_stands_down_when_objset_available(self):
        """With per-dataset counters the histogram advice is not duplicated."""
        sample = _sample(
            pools=[_pool(ashift=12)],
            datasets=[_fs("fivebays/db", recordsize="128K")],
            histograms={"fivebays": _hist(sync_ind={8192: 5000})},
            objset={"fivebays/db": _objset(writes=5000, nwritten=5000 * 4096)},
        )
        pool_subject = _findings_for(sample, layer="Dataset", subject="fivebays")
        self.assertEqual(pool_subject, [])
        rows = _findings_for(sample, layer="Dataset", subject="fivebays/db")
        self.assertEqual([row.key for row in rows], ["obs-dataset-recordsize-rmw"])


class TestTopologyGroupFindings(unittest.TestCase):
    """Mixed member geometry judged per vdev group when topology exists."""

    def _mixed_mirror_pool(self):
        return _pool(
            ashift=12,
            members=[
                ("/dev/sdb", 512, 4096),
                ("/dev/sdc", 512, 512),
                ("/dev/sdd", 512, 4096),
                ("/dev/sde", 512, 4096),
            ],
            topology=_topo_node(
                "fivebays",
                "pool",
                [
                    _topo_node(
                        "mirror-0",
                        "mirror",
                        [_topo_node("/dev/sdb", "disk"), _topo_node("/dev/sdc", "disk")],
                    ),
                    _topo_node(
                        "mirror-1",
                        "mirror",
                        [_topo_node("/dev/sdd", "disk"), _topo_node("/dev/sde", "disk")],
                    ),
                ],
            ),
        )

    def test_mixed_group_named_with_class_and_members(self):
        sample = _sample(pools=[self._mixed_mirror_pool()])
        rows = _findings_for(sample, layer="Pool")
        mixed = [row for row in rows if row.key == "pool-group-mixed-geometry"]
        self.assertEqual(len(mixed), 1)
        self.assertEqual(mixed[0].subject, "fivebays mirror-0")
        self.assertEqual(mixed[0].severity, ana.SEV_INFO)
        self.assertIn("data vdev mirror-0 mixes member geometry", mixed[0].message)
        self.assertIn("sdb 4K", mixed[0].message)
        self.assertIn("sdc 512", mixed[0].message)
        self.assertIn("replacement disks", mixed[0].recommendation)

    def test_cross_group_mixing_is_silent_with_topology(self):
        """4K data vdevs beside a 512-native cache disk stay silent."""
        pool = _pool(
            ashift=12,
            members=[("/dev/sdb", 512, 4096), ("/dev/sdd", 512, 4096), ("/dev/nvme0", 512, 512)],
            topology=_topo_node(
                "fivebays",
                "pool",
                [
                    _topo_node(
                        "mirror-0",
                        "mirror",
                        [_topo_node("/dev/sdb", "disk"), _topo_node("/dev/sdd", "disk")],
                    ),
                    _topo_node("cache", "cache", [_topo_node("/dev/nvme0", "disk")]),
                ],
            ),
        )
        sample = _sample(pools=[pool])
        rows = _findings_for(sample, layer="Pool")
        self.assertFalse(
            any(row.key in ("pool-group-mixed-geometry", "pool-mixed-geometry") for row in rows)
        )

    def test_pool_wide_finding_only_without_topology(self):
        """No vdev tree: the pool-wide range finding stays the fallback."""
        sample = _sample(
            pools=[
                _pool(
                    ashift=12,
                    members=[("/dev/sdb", 512, 512), ("/dev/sdc", 512, 4096)],
                )
            ]
        )
        rows = _findings_for(sample, layer="Pool")
        pool_wide = [row for row in rows if row.key == "pool-mixed-geometry"]
        self.assertEqual(len(pool_wide), 1)
        self.assertEqual(pool_wide[0].subject, "fivebays")
        self.assertIn("vdev tree unavailable", pool_wide[0].recommendation)
        self.assertFalse(any(row.key == "pool-group-mixed-geometry" for row in rows))

    def test_unreadable_topology_keeps_pool_wide_finding(self):
        """A failed status read degrades to the pool-wide judgement."""
        pool = _pool(
            ashift=12,
            members=[("/dev/sdb", 512, 512), ("/dev/sdc", 512, 4096)],
            topology=None,
        )
        sample = _sample(pools=[pool])
        rows = _findings_for(sample, layer="Pool")
        self.assertTrue(any(row.key == "pool-mixed-geometry" for row in rows))


class TestVMFindings(unittest.TestCase):
    def test_pve_unavailable_degrades(self):
        sample = _sample(
            pools=[_pool(ashift=12)],
            datasets=[_vol("fivebays/vm-201-disk-0")],
            pve=False,
        )
        rows = _findings_for(sample, layer="VM", subject="(all)")
        self.assertEqual(len(rows), 1)
        self.assertIn("not readable on this host", rows[0].message)

    def test_missing_discard_info(self):
        sample = _sample(
            pools=[_pool(ashift=12)],
            datasets=[_vol("fivebays/vm-201-disk-0")],
            vm_disks={
                "vm-201-disk-0": als.VMOption(
                    vmid="201", disknum="0", bus="scsi0", options={"size": "32G"}
                )
            },
            pve=True,
        )
        rows = _findings_for(sample, layer="VM", subject="fivebays/vm-201-disk-0")
        self.assertTrue(any("no discard=" in row.message for row in rows))

    def test_guest_sector_note_without_secs(self):
        sample = _sample(
            pools=[_pool(ashift=12)],
            datasets=[_vol("fivebays/vm-201-disk-0", volblocksize="16K")],
            vm_disks={
                "vm-201-disk-0": als.VMOption(
                    vmid="201", disknum="0", bus="scsi0", options={"discard": "on"}
                )
            },
            pve=True,
        )
        rows = _findings_for(sample, layer="VM", subject="fivebays/vm-201-disk-0")
        sector_rows = [row for row in rows if "512-byte sectors" in row.message]
        self.assertEqual(len(sector_rows), 1)
        self.assertIn("secs=4096", sector_rows[0].recommendation)

    def test_secs_set_is_silent(self):
        sample = _sample(
            pools=[_pool(ashift=12)],
            datasets=[_vol("fivebays/vm-201-disk-0", volblocksize="16K")],
            vm_disks={
                "vm-201-disk-0": als.VMOption(
                    vmid="201",
                    disknum="0",
                    bus="scsi0",
                    options={"discard": "on", "secs": "4096"},
                )
            },
            pve=True,
        )
        self.assertEqual(_findings_for(sample, layer="VM", subject="fivebays/vm-201-disk-0"), [])


class TestMemoryFindings(unittest.TestCase):
    def test_low_demand_hit_rate(self):
        sample = _sample(pools=[], arc={"demand_data_hits": 200, "demand_data_misses": 800})
        rows = _findings_for(sample, layer="Memory")
        self.assertTrue(any("demand-data hit rate is low" in row.message for row in rows))

    def test_good_demand_hit_rate(self):
        sample = _sample(pools=[], arc={"demand_data_hits": 950, "demand_data_misses": 50})
        rows = _findings_for(sample, layer="Memory")
        self.assertTrue(
            any(
                row.severity == ana.SEV_OK and "demand-data hit rate" in row.message for row in rows
            )
        )

    def test_mid_band_is_silent(self):
        sample = _sample(pools=[], arc={"demand_data_hits": 500, "demand_data_misses": 500})
        self.assertEqual(_findings_for(sample, layer="Memory"), [])

    def test_ghost_hits(self):
        sample = _sample(
            pools=[],
            arc={
                "mru_hits": 1000,
                "mfu_hits": 1000,
                "mru_ghost_hits": 150,
                "mfu_ghost_hits": 150,
            },
        )
        rows = _findings_for(sample, layer="Memory")
        self.assertTrue(any("ghost hits" in row.message for row in rows))

    def test_l2_candidate_without_cache_vdevs(self):
        sample = _sample(
            pools=[_pool(ashift=12)],
            arc={"evict_l2_eligible": 600, "evict_l2_ineligible": 400},
        )
        rows = _findings_for(sample, layer="Memory")
        self.assertTrue(any("no pool has cache vdevs" in row.recommendation for row in rows))

    def test_l2_eligible_with_cache_vdevs(self):
        sample = _sample(
            pools=[_pool(ashift=12, has_cache=True)],
            arc={"evict_l2_eligible": 600, "evict_l2_ineligible": 400},
        )
        rows = _findings_for(sample, layer="Memory")
        self.assertTrue(any("cache vdevs already exist" in row.recommendation for row in rows))

    def test_prefetch_low_expected_for_random(self):
        sample = _sample(
            pools=[_pool(ashift=12)],
            histograms={"fivebays": _hist(sync_ind={8192: 5000})},
            prefetch={"hits": 10, "misses": 990},
        )
        rows = _findings_for(sample, layer="Memory")
        self.assertTrue(any("expected for random workloads" in row.recommendation for row in rows))

    def test_prefetch_low_with_sequential_traffic(self):
        sample = _sample(
            pools=[_pool(ashift=12)],
            histograms={"fivebays": _hist(async_agg={1048576: 9000})},
            prefetch={"hits": 10, "misses": 990},
        )
        rows = _findings_for(sample, layer="Memory")
        self.assertTrue(any("despite sequential traffic" in row.message for row in rows))


class TestArcReadouts(unittest.TestCase):
    def test_readouts(self):
        arc = {
            "demand_data_hits": 800,
            "demand_data_misses": 200,
            "demand_metadata_hits": 90,
            "demand_metadata_misses": 10,
            "prefetch_data_hits": 10,
            "prefetch_data_misses": 90,
            "mru_hits": 600,
            "mfu_hits": 400,
            "mru_ghost_hits": 30,
            "mfu_ghost_hits": 30,
            "evict_l2_eligible": 700,
            "evict_l2_ineligible": 300,
            "l2_hits": 100,
            "l2_read_bytes": 12800,
        }
        readouts = ana.arc_readouts(arc, has_l2arc=True)
        self.assertAlmostEqual(readouts["Demand data hit rate"], 0.8)
        self.assertAlmostEqual(readouts["Demand metadata hit rate"], 0.9)
        self.assertAlmostEqual(readouts["Prefetch data hit rate"], 0.1)
        self.assertAlmostEqual(readouts["Ghost hits (share of real)"], 0.06)
        self.assertAlmostEqual(readouts["Evictions eligible for L2ARC"], 0.7)
        self.assertEqual(readouts["Average L2 hit size"], 128)

    def test_average_l2_size_requires_l2arc(self):
        arc = {"l2_hits": 100, "l2_read_bytes": 12800}
        self.assertIsNone(ana.arc_readouts(arc, has_l2arc=False)["Average L2 hit size"])

    def test_empty_arc(self):
        readouts = ana.arc_readouts({}, has_l2arc=False)
        self.assertIsNone(readouts["Demand data hit rate"])
        self.assertIsNone(readouts["Ghost hits (share of real)"])


class TestAnalyseDegrade(unittest.TestCase):
    def test_pools_unavailable_banner(self):
        sample = _sample(pools=None)
        rows = [
            row
            for row in _findings_for(sample, layer="Pool", subject="(all)")
            if "pool and device data unavailable" in row.message
        ]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].key, "pools-unavailable")

    def test_dataset_read_failure_names_pool(self):
        """A per-pool zfs read failure suspends only that pool's rows."""
        sample = _sample(pools=[_pool(ashift=12), _pool(name="scratch", ashift=12)])
        sample.dataset_read_failures = ["scratch"]
        rows = _findings_for(sample, layer="Dataset", subject="scratch")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].severity, ana.SEV_INFO)
        self.assertEqual(rows[0].key, "datasets-unreadable")
        self.assertIn("other pools are unaffected", rows[0].message)
        # The healthy pool still gets its device-side findings.
        self.assertTrue(_findings_for(sample, layer="Pool", subject="fivebays"))

    def test_findings_carry_stable_rule_keys(self):
        """(key, subject) identifies a finding across refreshes."""
        sample = _sample(
            pools=[_pool(ashift=12, members=[("/dev/sdb", 512, 4096)], has_cache=True)],
            datasets=[
                _fs("fivebays/db", recordsize="128K"),
                _vol("fivebays/vm-201-disk-0", volblocksize="16K"),
            ],
            histograms={"fivebays": _hist(async_agg={1048576: 9000})},
            arc={
                "demand_data_hits": 950,
                "demand_data_misses": 50,
                "evict_l2_eligible": 600,
                "evict_l2_ineligible": 400,
            },
            vm_disks={
                "vm-201-disk-0": als.VMOption(
                    vmid="201", disknum="0", bus="scsi0", options={"size": "32G"}
                )
            },
            pve=True,
            objset={
                "fivebays/db": _objset(writes=4000, nwritten=4000 * 4096),
                "fivebays/vm-201-disk-0": _objset(writes=4000, nwritten=4000 * 4096),
            },
        )
        rows = ana.analyse(sample)
        self.assertTrue(rows)
        identities = [(row.key, row.subject) for row in rows]
        self.assertEqual(len(identities), len(set(identities)))
        self.assertTrue(all(row.key for row in rows))
        # Two INFO findings on the same VM share layer and subject but
        # stay distinct through their rule keys — now joined by the
        # per-dataset observed-size rule.
        vm_rows = [row for row in rows if row.subject == "fivebays/vm-201-disk-0"]
        self.assertEqual(
            {row.key for row in vm_rows},
            {
                "vm-discard-missing",
                "vm-guest-sectors-implicit",
                "obs-dataset-volblocksize-rmw",
            },
        )


class TestBlocksizeLadder(unittest.TestCase):
    """blocksize_ladder: the Alignment visual's per-pool data inputs."""

    def test_full_stack_order_labels_and_states(self):
        """Rungs follow the stack, group by size, and carry verdict states."""
        pool = _pool(
            ashift=12,
            members=[
                ("/dev/sdb", 512, 4096),
                ("/dev/sdc", 512, 4096),
                ("/dev/sdd", 512, 4096),
            ],
        )
        sample = _sample(
            pools=[pool],
            datasets=[
                _fs("fivebays/backups", recordsize="128K"),
                _fs("fivebays/media", recordsize="128K"),
                _vol("fivebays/vm-201-disk-0", volblocksize="16K"),
            ],
            vm_disks={
                "vm-201-disk-0": als.VMOption(
                    vmid="201", disknum="0", bus="scsi0", options={"discard": "1"}
                )
            },
            pve=True,
        )
        ladder = ana.blocksize_ladder(sample)
        self.assertEqual(len(ladder), 1)
        entry = ladder[0]
        self.assertEqual((entry.pool, entry.ashift, entry.block), ("fivebays", 12, 4096))
        self.assertEqual(
            [(bar.layer, bar.label, bar.size, bar.state) for bar in entry.bars],
            [
                ("Device", "device · physical sector 4K ×3", 4096, ana.SEV_OK),
                ("Pool", "pool · ashift 12 · 4K block", 4096, ana.SEV_OK),
                ("Dataset", "dataset · volblocksize 16K", 16384, ana.SEV_OK),
                ("Dataset", "dataset · recordsize 128K ×2", 131072, ana.SEV_OK),
                ("VM", "vm · guest sector 512", 512, ana.SEV_INFO),
            ],
        )

    def test_pool_below_device_sector_warns_both_rungs(self):
        pool = _pool(ashift=9, members=[("/dev/sdb", 512, 4096)])
        ladder = ana.blocksize_ladder(_sample(pools=[pool]))
        states = {bar.layer: bar.state for bar in ladder[0].bars}
        self.assertEqual(states["Device"], ana.SEV_WARN)
        self.assertEqual(states["Pool"], ana.SEV_WARN)

    def test_dataset_below_ashift_block_warns(self):
        pool = _pool(ashift=12, members=[("/dev/sdb", 512, 4096)])
        sample = _sample(
            pools=[pool],
            datasets=[
                _fs("fivebays/db", recordsize="512"),
                _vol("fivebays/vm-201-disk-0", volblocksize="1K"),
            ],
        )
        ladder = ana.blocksize_ladder(_sample(pools=sample.pools, datasets=sample.datasets))
        dataset_states = [bar.state for bar in ladder[0].bars if bar.layer == "Dataset"]
        self.assertEqual(dataset_states, [ana.SEV_WARN, ana.SEV_WARN])

    def test_unresolved_ashift_drops_reference_and_downgrades_states(self):
        pool = _pool(ashift=None, members=[("/dev/sdb", 512, 4096)])
        ladder = ana.blocksize_ladder(_sample(pools=[pool]))
        entry = ladder[0]
        self.assertIsNone(entry.block)
        self.assertFalse(any(bar.layer == "Pool" for bar in entry.bars))
        self.assertEqual([bar.state for bar in entry.bars], [ana.SEV_INFO])

    def test_members_without_sector_data_drop_device_rungs(self):
        pool = _pool(ashift=12, members=[("/dev/sdb", None, None)])
        ladder = ana.blocksize_ladder(_sample(pools=[pool]))
        entry = ladder[0]
        self.assertEqual([bar.layer for bar in entry.bars], ["Pool"])
        # No sector data to judge the block against: the reference rung
        # itself renders as info.
        self.assertEqual(entry.bars[0].state, ana.SEV_INFO)

    def test_vm_rungs_follow_secs_option_and_drop_without_pve(self):
        pool = _pool(ashift=12, members=[("/dev/sdb", 512, 4096)])
        datasets = [
            _vol("fivebays/vm-201-disk-0", volblocksize="16K"),
            _vol("fivebays/vm-202-disk-0", volblocksize="16K"),
        ]
        vm_disks = {
            "vm-201-disk-0": als.VMOption(vmid="201", disknum="0", bus="scsi0", options={}),
            "vm-202-disk-0": als.VMOption(
                vmid="202", disknum="0", bus="virtio0", options={"secs": "16384"}
            ),
        }
        ladder = ana.blocksize_ladder(
            _sample(pools=[pool], datasets=datasets, pve=True, vm_disks=vm_disks)
        )
        vm_rungs = [bar for bar in ladder[0].bars if bar.layer == "VM"]
        self.assertEqual(
            [(bar.label, bar.state) for bar in vm_rungs],
            [
                ("vm · guest sector 512", ana.SEV_INFO),  # below its zvol's volblocksize
                ("vm · guest sector 16K", ana.SEV_OK),  # secs= matches the volblocksize
            ],
        )
        # Without local PVE configs there are no VM rungs at all.
        ladder = ana.blocksize_ladder(_sample(pools=[pool], datasets=datasets))
        self.assertFalse([bar for bar in ladder[0].bars if bar.layer == "VM"])

    def test_rungs_stay_within_their_pool_and_degrade_per_pool(self):
        """A pool's datasets never leak rungs into another pool's ladder."""
        pools = [
            _pool(name="fivebays", ashift=12, members=[("/dev/sdb", 512, 4096)]),
            _pool(name="scratch", ashift=12, members=[("/dev/sdc", 512, 4096)]),
        ]
        datasets = [_fs("scratch/iso", recordsize="64K")]
        ladder = ana.blocksize_ladder(_sample(pools=pools, datasets=datasets))
        by_pool = {entry.pool: entry for entry in ladder}
        self.assertEqual(
            [bar.label for bar in by_pool["fivebays"].bars if bar.layer == "Dataset"], []
        )
        self.assertEqual(
            [bar.label for bar in by_pool["scratch"].bars if bar.layer == "Dataset"],
            ["dataset · recordsize 64K"],
        )

    def test_non_power_of_two_sizes_render_exact_labels(self):
        """OpenZFS 2.2+ decimal volblocksize (12.0K) parses and labels as 12K."""
        pool = _pool(ashift=12, members=[("/dev/sdb", 512, 4096)])
        sample = _sample(
            pools=[pool], datasets=[_vol("fivebays/vm-203-disk-0", volblocksize="12.0K")]
        )
        ladder = ana.blocksize_ladder(sample)
        rung = next(bar for bar in ladder[0].bars if bar.layer == "Dataset")
        self.assertEqual(rung.size, 12288)
        self.assertEqual(rung.label, "dataset · volblocksize 12K")


if __name__ == "__main__":
    unittest.main()

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


def _pool(name="fivebays", ashift=12, members=None, has_cache=False):
    member_rows = [
        als.MemberDisk(path=path, logical_sector=logical, physical_sector=physical)
        for path, logical, physical in (members or [])
    ]
    return als.PoolAlignment(
        name=name,
        ashift_configured=str(ashift) if ashift is not None else "0",
        ashift_effective=ashift,
        members=member_rows,
        has_cache=has_cache,
    )


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
):
    return als.AlignmentSample(
        monotonic=0.0,
        pools=pools if pools is not None else [],
        datasets=datasets or [],
        histograms=histograms if histograms is not None else {},
        vm_disks=vm_disks or {},
        arc=arc if arc is not None else {},
        prefetch=prefetch if prefetch is not None else {},
        pools_available=pools is not None,
        datasets_available=pools is not None,
        iostat_r_available=histograms is not None,
        arcstats_available=arc is not None,
        prefetch_available=prefetch is not None,
        pve_available=pve,
    )


def _findings_for(sample, survey=None, profiles=None, layer=None, subject=None):
    rows = ana.analyse(sample, survey=survey, profiles=profiles)
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


if __name__ == "__main__":
    unittest.main()

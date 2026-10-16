"""Tests for alignment_stats.py — parsers, PVE reader, and collection."""

import os
import subprocess
import sys
import tempfile
import unittest
from typing import ClassVar
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

import alignment_stats as als
from disk_repository import DiskInfo
from zfs_repository import AshiftInfo, DatasetBlockRow, TopologyNode

# Captured verbatim (whitespace-trimmed) from stewie's zfs 2.4.4
# `zpool iostat -r NVME1`: since-boot request-size histogram.
IOSTAT_R_NVME1 = """
NVME1         sync_read    sync_write    async_read    async_write      scrub         trim         rebuild
req_size      ind    agg    ind    agg    ind    agg    ind    agg    ind    agg    ind    agg    ind    agg
----------  -----  -----  -----  -----  -----  -----  -----  -----  -----  -----  -----  -----  -----  -----
512         1.68M      0  4.84K      0  13.9K      0  2.04M      0      1      0      0      0      0      0
1K           261K      0   630K      3  77.5K     81  3.24M   153K      4      0      0      0      0      0
2K           566K     11   306K     43   107K  1.42K  4.36M  1.16M      4      3      0      0      0      0
4K           730K    318   549K  3.03K   138K  29.7K  1.15M  1.67M      0      1      0      0      0      0
8K          13.5M    846  2.52M  20.4K   744K  55.2K  4.07M  1.76M      1      3      0      0      0      0
16K         25.6M  4.99K   434K   172K   915K  78.7K  2.42M  1.83M      0      5      0      0      0      0
32K          167K  5.63K   353K  68.3K   29.3K   223K  11.1M  2.33M      0      6  1.15M      0      0      0
64K         3.13K    659   129K  11.7K      0   197K   132K  1.07M      0      0   231K      0      0      0
128K            0     10   120K    126      0  10.5K  8.28K  4.96K      0      0  13.4K      0      0      0
256K            0      0      0      0      0      0      0      0      0      0    625      0      0      0
512K            0      0      0      0      0      0      0      0      0      0     29      0      0      0
1M              0      0      0      0      0      0      0      0      0      0      2      0      0      0
2M              0      0      0      0      0      0      0      0      0      0      0      0      0      0
4M              0      0      0      0      0      0      0      0      0      0      0      0      0      0
8M              0      0      0      0      0      0      0      0      0      0      0      0      0      0
16M             0      0      0      0      0      0      0      0      0      0     32      0      0      0
----------------------------------------------------------------------------------------------------------------
"""

# A second, idle pool block — the parser must handle concatenated blocks.
IOSTAT_R_IDLE_BLOCK = """
fivebays      sync_read    sync_write    async_read    async_write      scrub         trim         rebuild
req_size      ind    agg    ind    agg    ind    agg    ind    agg    ind    agg    ind    agg    ind    agg
----------  -----  -----  -----  -----  -----  -----  -----  -----  -----  -----  -----  -----  -----  -----
512             0      0      0      0      0      0      0      0      0      0      0      0      0      0
1K              0      0      0      0      0      0      0      0      0      0      0      0      0      0
2K              0      0      0      0      0      0      0      0      0      0      0      0      0      0
4K              2      0      5      0      1      0      3      0      0      0      0      0      0      0
----------------------------------------------------------------------------------------------------------------
"""

# Captured verbatim (whitespace-trimmed) from stewie's zfs 2.4.4
# /proc/spl/kstat/zfs/NVME1/objset-0x705 — since-boot per-dataset counters
# for a busy VM zvol (the average write size works out to exactly 4096).
OBJSET_KSTAT_STEWIE = """
321 1 0x01 28 7872 11537763416 1502890516504441
name                            type data
dataset_name                    7    NVME1/proxmox/vm-201-disk-3
writes                          4    13744000
nwritten                        4    59685613568
reads                           4    84005793
nread                           4    344117798912
nunlinks                        4    0
nunlinked                       4    0
zil_commit_count                4    2400273
zil_commit_writer_count         4    2400117
zil_commit_error_count          4    0
zil_commit_stall_count          4    0
zil_commit_suspend_count        4    0
zil_commit_crash_count          4    0
zil_itx_count                   4    13797073
zil_itx_indirect_count          4    129059
zil_itx_indirect_bytes          4    2010800128
zil_itx_copied_count            4    190459
zil_itx_copied_bytes            4    780120064
zil_itx_needcopy_count          4    13477555
zil_itx_needcopy_bytes          4    56549777408
zil_itx_metaslab_normal_count   4    2549669
zil_itx_metaslab_normal_bytes   4    60447935000
zil_itx_metaslab_normal_write   4    68559785984
zil_itx_metaslab_normal_alloc   4    117329211392
zil_itx_metaslab_slog_count     4    0
zil_itx_metaslab_slog_bytes     4    0
zil_itx_metaslab_slog_write     4    0
zil_itx_metaslab_slog_alloc     4    0
"""

# Same grammar on the 2.2.2 dev host (all-zero counters on an idle pool):
# /proc/spl/kstat/zfs/zfstest2/objset-0xc5 — dataset_name self-identifies.
OBJSET_KSTAT_222 = """
45 1 0x01 24 6784 18833492147 364265329033290
name                            type data
dataset_name                    7    zfstest2/zfstest1
writes                          4    0
nwritten                        4    0
reads                           4    0
nread                           4    0
nunlinks                        4    0
nunlinked                       4    0
"""

PVE_CONF = """# comment line
boot: order=scsi0
ide2: local:iso/debian-13-netinst.iso,media=cdrom
scsi0: local-lvm:vm-201-disk-0,size=32G
scsi1: /dev/disk/by-path/ip-10.0.0.5:3260-iscsi-iqn.example-lun-0,format=raw,discard=on,iothread=1,size=10G
virtio0: NVME1:vm-205-disk-1,format=raw,discard=on,iothread=1,secs=4096,size=8G
unused0: local-lvm:vm-201-disk-2
"""


def _kstat_text(fields):
    body = "\n".join(f"{name} 4 {value}" for name, value in fields.items())
    return f"9 1 0x01 4 1234 1234 5678\nname type data\n{body}\n"


def _node(name, vdev_type, children=None):
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


def _topology():
    return _node(
        "fivebays",
        "pool",
        [
            _node("raidz2-0", "raidz2", [_node("/dev/sdb", "disk"), _node("/dev/sdc", "disk")]),
            _node("logs", "log", [_node("/dev/sdd", "disk")]),
            _node("cache", "cache", [_node("/dev/sde", "disk")]),
        ],
    )


class _FakeZfsRepo:
    def __init__(
        self,
        fail=False,
        topology_fail=False,
        topology_none=False,
        ashift_fail=False,
        dataset_fail_pools=(),
        pools=("fivebays",),
    ):
        self._fail = fail
        self._topology_fail = topology_fail
        self._topology_none = topology_none
        self._ashift_fail = ashift_fail
        self._dataset_fail_pools = tuple(dataset_fail_pools)
        self._pools = tuple(pools)

    def list_pools_full(self):
        if self._fail:
            raise subprocess.CalledProcessError(1, ["zpool", "list"])
        return [{"name": name} for name in self._pools]

    def get_ashift(self, pool):
        if self._ashift_fail:
            raise subprocess.CalledProcessError(1, ["zpool", "get"])
        return AshiftInfo(configured="12", effective=12)

    def pool_topology(self, pool):
        if self._topology_fail:
            raise subprocess.CalledProcessError(1, ["zpool", "status"])
        if self._topology_none:
            return None
        return _topology()

    def dataset_block_properties(self, pool):
        if self._fail or pool in self._dataset_fail_pools:
            raise subprocess.CalledProcessError(1, ["zfs", "get"])
        return [
            DatasetBlockRow(pool, "recordsize", "1M", "local"),
            DatasetBlockRow(pool, "volblocksize", "-", "-"),
            DatasetBlockRow(f"{pool}/proxmox", "recordsize", "128K", f"inherited from {pool}"),
            DatasetBlockRow(f"{pool}/proxmox/vm-201-disk-0", "recordsize", "-", "-"),
            DatasetBlockRow(f"{pool}/proxmox/vm-201-disk-0", "volblocksize", "16K", "-"),
        ]


class _FakeDiskRepo:
    def list_disks(self):
        return [
            DiskInfo(name="sdb", path="/dev/sdb", logical_sector=512, physical_sector=4096),
            DiskInfo(name="sdc", path="/dev/sdc", logical_sector=512, physical_sector=4096),
            DiskInfo(name="sdd", path="/dev/sdd", logical_sector=512, physical_sector=512),
            DiskInfo(name="sdz", path="/dev/sdz", logical_sector=512, physical_sector=512),
        ]


class TestValueParsers(unittest.TestCase):
    def test_parse_zfs_size(self):
        self.assertEqual(als.parse_zfs_size("128K"), 131072)
        self.assertEqual(als.parse_zfs_size("1M"), 1048576)
        self.assertEqual(als.parse_zfs_size("512"), 512)
        self.assertEqual(als.parse_zfs_size("12.5K"), 12800)
        self.assertIsNone(als.parse_zfs_size("-"))
        self.assertIsNone(als.parse_zfs_size(""))
        self.assertIsNone(als.parse_zfs_size(None))

    def test_parse_bucket_label(self):
        self.assertEqual(als.parse_bucket_label("512"), 512)
        self.assertEqual(als.parse_bucket_label("1K"), 1024)
        self.assertEqual(als.parse_bucket_label("16M"), 16 * 1024**2)
        self.assertIsNone(als.parse_bucket_label("1.5M"))


class TestIostatRParser(unittest.TestCase):
    def test_stewie_fixture(self):
        histograms = als.parse_zpool_iostat_r(IOSTAT_R_NVME1)
        self.assertEqual(list(histograms), ["NVME1"])
        hist = histograms["NVME1"]
        self.assertEqual(len(hist.buckets), 16)
        self.assertEqual(hist.buckets[8192]["ind"]["sync_read"], int(13.5 * 1024**2))
        self.assertEqual(hist.buckets[512]["ind"]["sync_write"], int(4.84 * 1024))
        self.assertEqual(hist.buckets[16384]["agg"]["async_write"], int(1.83 * 1024**2))
        self.assertEqual(hist.buckets[32768]["ind"]["trim"], int(1.15 * 1024**2))
        self.assertEqual(hist.buckets[32768]["agg"]["scrub"], 6)

    def test_multi_pool_blocks(self):
        histograms = als.parse_zpool_iostat_r(IOSTAT_R_NVME1 + IOSTAT_R_IDLE_BLOCK)
        self.assertEqual(sorted(histograms), ["NVME1", "fivebays"])
        idle = histograms["fivebays"]
        self.assertEqual(idle.ops(("sync_read",)), 2)
        self.assertEqual(idle.ops(("async_write",)), 3)

    def test_garbage_lines_ignored(self):
        text = "noise\n\n1K 1 2 3 4 5 6 7 8 9 10 11 12 13 14 without-pool-header\n"
        self.assertEqual(als.parse_zpool_iostat_r(text), {})


class TestHistogramHelpers(unittest.TestCase):
    def _stewie(self):
        return als.parse_zpool_iostat_r(IOSTAT_R_NVME1)["NVME1"]

    def test_ops_totals(self):
        hist = self._stewie()
        sync_read_ind = int(1.68 * 1024**2) + 261 * 1024 + (566 * 1024) + 730 * 1024
        sync_read_ind += int(13.5 * 1024**2) + int(25.6 * 1024**2) + 167 * 1024
        sync_read_ind += int(3.13 * 1024)
        self.assertEqual(hist.ops(("sync_read",), kinds=("ind",)), sync_read_ind)

    def test_dominant_sync_bucket(self):
        bucket, share = self._stewie().dominant_bucket(("sync_read", "sync_write"))
        self.assertEqual(bucket, 16384)
        self.assertGreater(share, 0.2)

    def test_top_buckets_ranked(self):
        top = self._stewie().top_buckets(
            ("sync_read", "sync_write", "async_read", "async_write"), limit=3
        )
        self.assertEqual(len(top), 3)
        shares = [share for _bucket, share in top]
        self.assertEqual(shares, sorted(shares, reverse=True))
        self.assertLessEqual(sum(shares), 1.0)

    def test_empty_histogram(self):
        hist = als.ReqHistogram(pool="idle")
        self.assertEqual(hist.ops(("sync_read",)), 0)
        self.assertIsNone(hist.dominant_bucket(("sync_read",)))
        self.assertEqual(hist.top_buckets(("sync_read",)), [])


class TestObjsetKstatParser(unittest.TestCase):
    def test_stewie_fixture(self):
        parsed = als.parse_objset_kstat(OBJSET_KSTAT_STEWIE)
        self.assertIsNotNone(parsed)
        name, counters = parsed
        self.assertEqual(name, "NVME1/proxmox/vm-201-disk-3")
        self.assertEqual(counters["reads"], 84005793)
        self.assertEqual(counters["nread"], 344117798912)
        self.assertEqual(counters["writes"], 13744000)
        self.assertEqual(counters["nwritten"], 59685613568)
        # Per-dataset ZIL counters ride along in the same numeric parse.
        self.assertEqual(counters["zil_commit_count"], 2400273)
        # dataset_name is string-typed and stays out of the numeric counters.
        self.assertNotIn("dataset_name", counters)

    def test_222_fixture_zero_counters(self):
        name, counters = als.parse_objset_kstat(OBJSET_KSTAT_222)
        self.assertEqual(name, "zfstest2/zfstest1")
        self.assertEqual(counters["reads"], 0)
        self.assertEqual(counters["nwritten"], 0)

    def test_not_an_objset_kstat(self):
        # Numeric-only kstat body (e.g. arcstats): no dataset_name row.
        self.assertIsNone(als.parse_objset_kstat(_kstat_text({"hits": 5})))
        self.assertIsNone(als.parse_objset_kstat(""))


class TestReadObjsetKstats(unittest.TestCase):
    def test_reads_pool_subdirectories(self):
        with tempfile.TemporaryDirectory() as root:
            pool = os.path.join(root, "NVME1")
            os.makedirs(pool)
            with open(os.path.join(pool, "objset-0x705"), "w") as f:
                f.write(OBJSET_KSTAT_STEWIE)
            other = os.path.join(root, "zfstest2")
            os.makedirs(other)
            with open(os.path.join(other, "objset-0xc5"), "w") as f:
                f.write(OBJSET_KSTAT_222)
            with open(os.path.join(other, "objset-0xZZ"), "w") as f:
                f.write("not a kstat at all\n")
            stats = als.read_objset_kstats(root)
        self.assertEqual(sorted(stats), ["NVME1/proxmox/vm-201-disk-3", "zfstest2/zfstest1"])
        self.assertEqual(stats["NVME1/proxmox/vm-201-disk-3"]["writes"], 13744000)
        self.assertEqual(stats["zfstest2/zfstest1"]["reads"], 0)

    def test_missing_dir_degrades(self):
        self.assertEqual(als.read_objset_kstats("/nonexistent-kstat-dir"), {})


class TestObjsetRates(unittest.TestCase):
    BASE: ClassVar[dict] = {
        "reads": 84005793,
        "nread": 344117798912,
        "writes": 13744000,
        "nwritten": 59685613568,
    }

    def _sample(self, monotonic, objset):
        return als.AlignmentSample(monotonic=monotonic, objset=objset)

    def test_interval_rates_and_average_sizes(self):
        # 120 reads / 400000 bytes and 30 writes / 216000 bytes in 60 s.
        cur_counters = {
            "reads": self.BASE["reads"] + 120,
            "nread": self.BASE["nread"] + 400000,
            "writes": self.BASE["writes"] + 30,
            "nwritten": self.BASE["nwritten"] + 216000,
        }
        rates = als.compute_objset_rates(
            self._sample(100.0, {"NVME1/proxmox/vm-201-disk-3": self.BASE}),
            self._sample(160.0, {"NVME1/proxmox/vm-201-disk-3": cur_counters}),
        )
        self.assertEqual(list(rates), ["NVME1/proxmox/vm-201-disk-3"])
        rate = rates["NVME1/proxmox/vm-201-disk-3"]
        self.assertAlmostEqual(rate.reads_ps, 2.0)
        self.assertAlmostEqual(rate.writes_ps, 0.5)
        self.assertAlmostEqual(rate.read_bps, 400000 / 60)
        self.assertAlmostEqual(rate.write_bps, 216000 / 60)
        # Average request sizes come from the deltas, distinct from the
        # per-second rates: 400000/120 read, 216000/30 written.
        self.assertAlmostEqual(rate.avg_read_size, 400000 / 120)
        self.assertAlmostEqual(rate.avg_write_size, 7200.0)

    def test_zero_traffic_window(self):
        rates = als.compute_objset_rates(
            self._sample(100.0, {"ds": dict(self.BASE)}),
            self._sample(160.0, {"ds": dict(self.BASE)}),
        )
        rate = rates["ds"]
        self.assertEqual(rate.reads_ps, 0.0)
        self.assertEqual(rate.writes_ps, 0.0)
        # No operations means no observable request size.
        self.assertIsNone(rate.avg_read_size)
        self.assertIsNone(rate.avg_write_size)

    def test_counter_reset_drops_interval(self):
        # A re-import resets counters backwards; the interval is unreadable.
        reset = {key: value // 2 for key, value in self.BASE.items()}
        rates = als.compute_objset_rates(
            self._sample(100.0, {"ds": self.BASE}),
            self._sample(160.0, {"ds": reset}),
        )
        rate = rates["ds"]
        self.assertIsNone(rate.reads_ps)
        self.assertIsNone(rate.avg_read_size)
        self.assertIsNone(rate.avg_write_size)

    def test_dataset_churn_and_missing_baseline(self):
        prev = self._sample(100.0, {"ds": dict(self.BASE)})
        cur = self._sample(160.0, {"ds": dict(self.BASE), "newds": dict(self.BASE)})
        # A dataset with no previous baseline has no valid delta.
        self.assertEqual(sorted(als.compute_objset_rates(prev, cur)), ["ds"])
        self.assertEqual(als.compute_objset_rates(None, cur), {})
        self.assertEqual(als.compute_objset_rates(prev, None), {})
        # Non-advancing clocks cannot rate anything.
        self.assertEqual(als.compute_objset_rates(prev, self._sample(100.0, {"ds": self.BASE})), {})

    def test_since_boot_average_sizes(self):
        # stewie's vm-205-disk-3 counters: 4096-byte writes, ~1.6M reads.
        avg_read, avg_write = als.average_request_sizes(
            {
                "reads": 227289,
                "nread": 382872641536,
                "writes": 63774720,
                "nwritten": 261221253120,
            }
        )
        self.assertAlmostEqual(avg_write, 4096.0)
        self.assertGreater(avg_read, 1024 * 1024)
        # No traffic or missing counters mean no average.
        self.assertEqual(als.average_request_sizes({}), (None, None))
        self.assertEqual(
            als.average_request_sizes({"reads": 0, "nread": 0, "writes": 5, "nwritten": 20480}),
            (None, 4096.0),
        )


class TestPveParsing(unittest.TestCase):
    def test_parse_vm_conf(self):
        options = als.parse_pve_vm_conf(PVE_CONF, vmid="201")
        self.assertEqual(sorted(options), ["vm-201-disk-0", "vm-205-disk-1"])
        scsi0 = options["vm-201-disk-0"]
        self.assertEqual(scsi0.bus, "scsi0")
        self.assertEqual(scsi0.options, {"size": "32G"})
        # vm-205-disk-1 in the 201 config is a moved disk: the short name
        # keeps its origin VM, but the owning VM is the config's (201).
        virtio0 = options["vm-205-disk-1"]
        self.assertEqual(virtio0.vmid, "201")
        self.assertEqual(virtio0.disknum, "1")
        self.assertEqual(virtio0.options["secs"], "4096")
        self.assertEqual(virtio0.options["discard"], "on")

    def test_read_pve_vm_options_from_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "201.conf"), "w") as f:
                f.write(PVE_CONF)
            with open(os.path.join(tmp, "notanumber.conf"), "w") as f:
                f.write(PVE_CONF)
            options = als.read_pve_vm_options(tmp)
            self.assertEqual(sorted(options), ["vm-201-disk-0", "vm-205-disk-1"])

    def test_read_pve_missing_dir(self):
        self.assertEqual(als.read_pve_vm_options("/nonexistent-pve-dir"), {})


class TestCollectAlignmentSample(unittest.TestCase):
    def _kstats_dir(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        arc_path = os.path.join(tmp.name, "arcstats")
        prefetch_path = os.path.join(tmp.name, "zfetchstats")
        with open(arc_path, "w") as f:
            f.write(_kstat_text({"hits": 1000, "misses": 100, "demand_data_hits": 800}))
        with open(prefetch_path, "w") as f:
            f.write(_kstat_text({"hits": 90, "misses": 10}))
        return arc_path, prefetch_path, tmp.name

    def _collect(self, zfs_repo=None, disk_repo=None, iostat_stdout=IOSTAT_R_NVME1):
        arc_path, prefetch_path, kstat_root = self._kstats_dir()
        pool_dir = os.path.join(kstat_root, "fivebays")
        os.makedirs(pool_dir)
        with open(os.path.join(pool_dir, "objset-0x705"), "w") as f:
            f.write(OBJSET_KSTAT_STEWIE)
        result = MagicMock(returncode=0, stdout=iostat_stdout)
        with patch("alignment_stats.subprocess.run", return_value=result) as run:
            sample = als.collect_alignment_sample(
                zfs_repo=zfs_repo if zfs_repo is not None else _FakeZfsRepo(),
                disk_repo=disk_repo if disk_repo is not None else _FakeDiskRepo(),
                arcstats_path=arc_path,
                zfetchstats_path=prefetch_path,
                pve_conf_dir="/nonexistent-pve-dir",
                kstat_dir=kstat_root,
            )
        return sample, run

    def test_happy_path(self):
        sample, _run = self._collect()
        self.assertTrue(sample.pools_available)
        self.assertTrue(sample.datasets_available)
        self.assertTrue(sample.iostat_r_available)
        self.assertTrue(sample.arcstats_available)
        self.assertTrue(sample.prefetch_available)
        self.assertTrue(sample.objset_available)
        self.assertFalse(sample.pve_available)
        pool = sample.pools[0]
        self.assertEqual(pool.name, "fivebays")
        self.assertEqual(pool.ashift_effective, 12)
        self.assertTrue(pool.has_cache)
        by_path = {member.path: member for member in pool.members}
        self.assertEqual(by_path["/dev/sdb"].physical_sector, 4096)
        self.assertEqual(by_path["/dev/sdd"].physical_sector, 512)
        names = {ds.name: ds for ds in sample.datasets}
        self.assertEqual(names["fivebays"].kind, "filesystem")
        self.assertEqual(names["fivebays"].recordsize, "1M")
        self.assertIsNone(names["fivebays"].volblocksize)
        vol = names["fivebays/proxmox/vm-201-disk-0"]
        self.assertEqual(vol.kind, "volume")
        self.assertEqual(vol.volblocksize, "16K")
        self.assertIsNone(vol.recordsize)
        self.assertIn("NVME1", sample.histograms)
        self.assertEqual(sample.arc["hits"], 1000)
        self.assertEqual(sample.prefetch["misses"], 10)
        objset = sample.objset["NVME1/proxmox/vm-201-disk-3"]
        self.assertEqual(objset["writes"], 13744000)
        self.assertEqual(objset["zil_commit_count"], 2400273)

    def test_topology_retained_with_root_ashift(self):
        sample, _run = self._collect()
        pool = sample.pools[0]
        topology = pool.topology
        self.assertIsNotNone(topology)
        self.assertEqual(topology.name, "fivebays")
        self.assertEqual(topology.vdev_type, "pool")
        # Disks-page pattern: the effective ashift is annotated on the root.
        self.assertEqual(topology.ashift, 12)
        by_type = {child.vdev_type: child for child in topology.children}
        self.assertEqual(sorted(by_type), ["cache", "log", "raidz2"])
        raidz = by_type["raidz2"]
        self.assertEqual(raidz.name, "raidz2-0")
        self.assertEqual([leaf.name for leaf in raidz.children], ["/dev/sdb", "/dev/sdc"])
        self.assertEqual([leaf.name for leaf in by_type["log"].children], ["/dev/sdd"])
        self.assertEqual([leaf.name for leaf in by_type["cache"].children], ["/dev/sde"])
        # The flattened members come from the same tree.
        self.assertEqual(
            sorted(member.path for member in pool.members),
            sorted(["/dev/sdb", "/dev/sdc", "/dev/sdd", "/dev/sde"]),
        )

    def test_topology_unreadable_degrades_per_pool(self):
        sample, _run = self._collect(zfs_repo=_FakeZfsRepo(topology_none=True))
        self.assertTrue(sample.pools_available)
        pool = sample.pools[0]
        self.assertIsNone(pool.topology)
        self.assertEqual(pool.members, [])
        self.assertFalse(pool.has_cache)
        # The pool row itself survives with its ashift and datasets.
        self.assertEqual(pool.ashift_effective, 12)
        self.assertTrue(sample.datasets_available)

    def test_topology_failure_degrades_per_pool(self):
        sample, _run = self._collect(zfs_repo=_FakeZfsRepo(topology_fail=True))
        self.assertTrue(sample.pools_available)
        pool = sample.pools[0]
        self.assertIsNone(pool.topology)
        self.assertEqual(pool.members, [])
        self.assertFalse(pool.has_cache)
        self.assertEqual(pool.ashift_effective, 12)

    def test_ashift_failure_degrades_per_pool(self):
        sample, _run = self._collect(zfs_repo=_FakeZfsRepo(ashift_fail=True))
        self.assertTrue(sample.pools_available)
        pool = sample.pools[0]
        self.assertIsNone(pool.ashift_configured)
        self.assertIsNone(pool.ashift_effective)
        # The tree is still retained, with no ashift annotated on its root.
        self.assertIsNotNone(pool.topology)
        self.assertIsNone(pool.topology.ashift)
        self.assertEqual(len(pool.members), 4)

    def test_iostat_r_command(self):
        _sample, run = self._collect()
        run.assert_called_once_with(
            als.IOSTAT_R_ARGS,
            capture_output=True,
            text=True,
            timeout=als.IOSTAT_R_TIMEOUT,
            check=False,
        )

    def test_iostat_r_failure_degrades(self):
        result = MagicMock(returncode=1, stdout="")
        with (
            patch("alignment_stats.subprocess.run", return_value=result),
            tempfile.TemporaryDirectory() as tmp,
        ):
            sample = als.collect_alignment_sample(
                zfs_repo=_FakeZfsRepo(),
                disk_repo=_FakeDiskRepo(),
                arcstats_path=os.path.join(tmp, "missing-arc"),
                zfetchstats_path=os.path.join(tmp, "missing-fetch"),
                pve_conf_dir="/nonexistent-pve-dir",
                kstat_dir=os.path.join(tmp, "missing-kstat-dir"),
            )
        self.assertFalse(sample.iostat_r_available)
        self.assertEqual(sample.histograms, {})
        self.assertFalse(sample.arcstats_available)
        self.assertFalse(sample.prefetch_available)
        # No pool subdirectories with objset files: per-dataset counters
        # are unavailable and the survey stays the per-dataset basis.
        self.assertFalse(sample.objset_available)
        self.assertEqual(sample.objset, {})

    def test_repo_failure_degrades(self):
        sample, _run = self._collect(zfs_repo=_FakeZfsRepo(fail=True))
        self.assertFalse(sample.pools_available)
        self.assertFalse(sample.datasets_available)
        self.assertEqual(sample.pools, [])
        self.assertEqual(sample.datasets, [])
        # Wholesale failure names no individual pool (the source is down,
        # not one pool's read).
        self.assertEqual(sample.dataset_read_failures, [])

    def test_dataset_read_failure_degrades_per_pool(self):
        """One pool's failed zfs read costs only that pool's datasets."""
        repo = _FakeZfsRepo(pools=("fivebays", "scratch"), dataset_fail_pools=("scratch",))
        sample, _run = self._collect(zfs_repo=repo)
        self.assertTrue(sample.pools_available)
        self.assertEqual([pool.name for pool in sample.pools], ["fivebays", "scratch"])
        self.assertTrue(sample.datasets_available)
        names = {ds.name for ds in sample.datasets}
        self.assertIn("fivebays/proxmox/vm-201-disk-0", names)
        self.assertFalse(any(name.startswith("scratch") for name in names))
        self.assertEqual(sample.dataset_read_failures, ["scratch"])

    def test_all_dataset_reads_failed_names_every_pool(self):
        """A zfs get failure on every pool keeps the pool rows alive."""
        repo = _FakeZfsRepo(dataset_fail_pools=("fivebays",))
        sample, _run = self._collect(zfs_repo=repo)
        self.assertTrue(sample.pools_available)
        self.assertFalse(sample.datasets_available)
        self.assertEqual(sample.datasets, [])
        self.assertEqual(sample.dataset_read_failures, ["fivebays"])


if __name__ == "__main__":
    unittest.main()

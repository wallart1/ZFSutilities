"""Tests for alignment_stats.py — parsers, PVE reader, and collection."""

import os
import subprocess
import sys
import tempfile
import unittest
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
    def __init__(self, fail=False):
        self._fail = fail

    def list_pools_full(self):
        if self._fail:
            raise subprocess.CalledProcessError(1, ["zpool", "list"])
        return [{"name": "fivebays"}]

    def get_ashift(self, pool):
        return AshiftInfo(configured="12", effective=12)

    def pool_topology(self, pool):
        return _topology()

    def dataset_block_properties(self, pool):
        if self._fail:
            raise subprocess.CalledProcessError(1, ["zfs", "get"])
        return [
            DatasetBlockRow("fivebays", "recordsize", "1M", "local"),
            DatasetBlockRow("fivebays", "volblocksize", "-", "-"),
            DatasetBlockRow("fivebays/proxmox", "recordsize", "128K", "inherited from fivebays"),
            DatasetBlockRow("fivebays/proxmox/vm-201-disk-0", "recordsize", "-", "-"),
            DatasetBlockRow("fivebays/proxmox/vm-201-disk-0", "volblocksize", "16K", "-"),
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
        return arc_path, prefetch_path

    def _collect(self, zfs_repo=None, disk_repo=None, iostat_stdout=IOSTAT_R_NVME1):
        arc_path, prefetch_path = self._kstats_dir()
        result = MagicMock(returncode=0, stdout=iostat_stdout)
        with patch("alignment_stats.subprocess.run", return_value=result) as run:
            sample = als.collect_alignment_sample(
                zfs_repo=zfs_repo if zfs_repo is not None else _FakeZfsRepo(),
                disk_repo=disk_repo if disk_repo is not None else _FakeDiskRepo(),
                arcstats_path=arc_path,
                zfetchstats_path=prefetch_path,
                pve_conf_dir="/nonexistent-pve-dir",
            )
        return sample, run

    def test_happy_path(self):
        sample, _run = self._collect()
        self.assertTrue(sample.pools_available)
        self.assertTrue(sample.datasets_available)
        self.assertTrue(sample.iostat_r_available)
        self.assertTrue(sample.arcstats_available)
        self.assertTrue(sample.prefetch_available)
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
            )
        self.assertFalse(sample.iostat_r_available)
        self.assertEqual(sample.histograms, {})
        self.assertFalse(sample.arcstats_available)
        self.assertFalse(sample.prefetch_available)

    def test_repo_failure_degrades(self):
        sample, _run = self._collect(zfs_repo=_FakeZfsRepo(fail=True))
        self.assertFalse(sample.pools_available)
        self.assertFalse(sample.datasets_available)
        self.assertEqual(sample.pools, [])
        self.assertEqual(sample.datasets, [])


if __name__ == "__main__":
    unittest.main()

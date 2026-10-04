"""Tests for memory_stats.py — ARC/L2ARC/SLOG data collection and rates."""

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

import memory_stats as ms


def _kstat_text(fields):
    """Render a fake /proc/spl/kstat/zfs file body from {name: value}."""
    lines = [
        "23 1 0x01 148 40256 145361334011 394890391511196",
        "name                            type data",
    ]
    for name, value in fields.items():
        lines.append(f"{name:<32} 4    {value}")
    return "\n".join(lines) + "\n"


ARC_FULL = {
    "hits": 829481077,
    "misses": 156679486,
    "size": 32648235840,
    "c": 32818317552,
    "c_max": 48318382080,
    "c_min": 2099009152,
    "hdr_size": 453382368,
    "data_size": 15163942400,
    "metadata_size": 6813288960,
    "l2_hits": 46921727,
    "l2_misses": 83160143,
    "l2_size": 1810888740352,
    "l2_asize": 1643495105536,
    "l2_read_bytes": 1_000_000,
    "l2_write_bytes": 2_000_000,
    "l2_feeds": 368802,
    "memory_throttle_count": 0,
}

ZIL_FULL = {
    "zil_commit_count": 4304721,
    "zil_itx_count": 40049432,
    "zil_itx_metaslab_normal_count": 1080725,
    "zil_itx_metaslab_slog_count": 9557603,
    "zil_itx_metaslab_slog_bytes": 1000929753184,
    "zil_itx_metaslab_slog_write": 1010176118784,
}

# Reduced field set: older OpenZFS releases do not expose data_size /
# metadata_size; every field must stay optional.
ARC_REDUCED = {
    "hits": 100,
    "misses": 10,
    "size": 1048576,
    "c_max": 2097152,
    "l2_hits": 0,
    "l2_misses": 0,
}

# What plain `zpool iostat -v` prints: per-second averages since boot.
# The Performance tab must NOT read these as traffic (they barely move).
IOSTAT_SINCE_BOOT = """              capacity     operations     bandwidth
pool        alloc   free   read  write   read  write
----------  -----  -----  -----  -----  -----  -----
fivebays    7.02T  7.82T    122    88   214M  54.2M
  raidz2-0  7.02T  7.82T    122    88   214M  54.2M
    sda1       -      -     61    44   107M  27.1M
logs               -      -      -      -      -      -
  mirror-2     15.5M  7.48G      0     48     14  4.90M
    SLOG1        -      -      0     24      7  2.45M
    SLOG2        -      -      0     24      7  2.45M
cache              -      -      -      -      -      -
  CACHE1      766G   158G     56     44   904K  2.38M
  CACHE2      767G   157G     56     39   900K  2.38M
----------  -----  -----  -----  -----  -----  -----
threeamigos 1.02T  2.50T      5      3  1.20M   600K
  mirror-1  1.02T  2.50T      5      3  1.20M   600K
    sdb1        -      -      5      3  1.20M   600K
"""

# The single per-interval report `zpool iostat -v -y 1 1` emits after its
# 1-second measurement window — the format the Performance tab consumes.
IOSTAT_INTERVAL = """              capacity     operations     bandwidth
pool        alloc   free   read  write   read  write
----------  -----  -----  -----  -----  -----  -----
fivebays    7.02T  7.82T    512    231   804K  47.1M
  raidz2-0  7.02T  7.82T    512    231   804K  47.1M
    sda1       -      -    102     46   160K  9.42M
logs               -      -      -      -      -      -
  mirror-2     15.5M  7.48G      0     89     14  4.66M
    SLOG1        -      -      0     44      7  2.33M
    SLOG2        -      -      0     45      7  2.33M
cache              -      -      -      -      -      -
  CACHE1      766G   158G     61     12  12.5M   513K
  CACHE2      767G   157G     58     11  11.9M   496K
----------  -----  -----  -----  -----  -----  -----
threeamigos 1.02T  2.50T      5      3  1.20M   600K
  mirror-1  1.02T  2.50T      5      3  1.20M   600K
    sdb1        -      -      5      3  1.20M   600K
"""

# What the no-`-y` fallback emits: since-boot report, then the interval
# report; the parser must keep the last report per vdev.
IOSTAT_FALLBACK = IOSTAT_SINCE_BOOT + "\n" + IOSTAT_INTERVAL

IOSTAT_NO_INFRA = """              capacity     operations     bandwidth
pool        alloc   free   read  write   read  write
----------  -----  -----  -----  -----  -----  -----
zfstest1     865K  24.5G      0      0     32     60
  raidz1-0   865K  24.5G      0      0     32     60
    sdb1        -      -      0      0      6     12
"""


class TestKstatParsers(unittest.TestCase):
    def test_parse_arcstats_full(self):
        stats = ms.parse_arcstats(_kstat_text(ARC_FULL))
        self.assertEqual(stats["size"], 32648235840)
        self.assertEqual(stats["l2_hits"], 46921727)
        self.assertEqual(len(stats), len(ARC_FULL))

    def test_parse_arcstats_reduced_field_set(self):
        """Fields absent from the file must be absent from the result."""
        stats = ms.parse_arcstats(_kstat_text(ARC_REDUCED))
        self.assertEqual(stats["size"], 1048576)
        self.assertNotIn("data_size", stats)
        self.assertNotIn("metadata_size", stats)

    def test_parse_skips_malformed_lines(self):
        text = (
            "9 1 0x01 147 39984 11433093148 86960218996134\n"
            "name                            type data\n"
            "hits                            4    277001\n"
            "garbage line\n"
            "iohits notanumber x\n"
        )
        stats = ms.parse_kstats(text)
        self.assertEqual(stats, {"hits": 277001})

    def test_parse_zil_kstats(self):
        stats = ms.parse_zil_kstats(_kstat_text(ZIL_FULL))
        self.assertEqual(stats["zil_itx_metaslab_slog_write"], 1010176118784)


class TestIostatParser(unittest.TestCase):
    def test_interval_report_layout(self):
        vdevs = ms.parse_zpool_iostat_v(IOSTAT_INTERVAL)
        self.assertEqual(len(vdevs), 5)
        logs = [v for v in vdevs if v.section == "logs"]
        caches = [v for v in vdevs if v.section == "cache"]
        self.assertEqual(len(logs), 3)
        self.assertEqual(len(caches), 2)

        mirror = next(v for v in logs if v.vdev == "mirror-2")
        self.assertEqual(mirror.pool, "fivebays")
        self.assertEqual(mirror.alloc, int(15.5 * 1024**2))
        self.assertEqual(mirror.free, int(7.48 * 1024**3))
        self.assertEqual(mirror.writes_ps, 89)
        self.assertEqual(mirror.write_bps, int(4.66 * 1024**2))

        leaf = next(v for v in logs if v.vdev == "SLOG1")
        self.assertIsNone(leaf.alloc)
        self.assertIsNone(leaf.free)
        self.assertEqual(leaf.writes_ps, 44)

        cache = next(v for v in caches if v.vdev == "CACHE1")
        self.assertEqual(cache.alloc, (766 * 1024**3))
        self.assertEqual(cache.read_bps, int(12.5 * 1024**2))

    def test_last_report_wins(self):
        """The fallback's trailing interval report supersedes since-boot."""
        vdevs = ms.parse_zpool_iostat_v(IOSTAT_FALLBACK)
        self.assertEqual(len(vdevs), 5)  # no duplicated vdevs
        mirror = next(v for v in vdevs if v.vdev == "mirror-2")
        self.assertEqual(mirror.writes_ps, 89)  # interval, not since-boot 48
        self.assertEqual(mirror.write_bps, int(4.66 * 1024**2))
        cache = next(v for v in vdevs if v.vdev == "CACHE1")
        self.assertEqual(cache.read_bps, int(12.5 * 1024**2))

    def test_data_vdevs_excluded(self):
        """Only logs/cache sections are tracked, never data vdevs."""
        vdevs = ms.parse_zpool_iostat_v(IOSTAT_FALLBACK)
        for vdev in vdevs:
            self.assertIn(vdev.section, ("logs", "cache"))
        names = {vdev.vdev for vdev in vdevs}
        self.assertNotIn("raidz2-0", names)
        self.assertNotIn("sda1", names)

    def test_no_infrastructure_vdevs(self):
        self.assertEqual(ms.parse_zpool_iostat_v(IOSTAT_NO_INFRA), [])

    def test_section_resets_between_pools(self):
        """A logs section must not leak into the next pool's data vdevs."""
        vdevs = ms.parse_zpool_iostat_v(IOSTAT_FALLBACK)
        threeamigos = [v for v in vdevs if v.pool == "threeamigos"]
        self.assertEqual(threeamigos, [])


class TestComputeRates(unittest.TestCase):
    def _sample(self, mono, arc, zil=None, vdevs=None):
        return ms.MemorySample(
            monotonic=mono,
            arc=dict(arc),
            zil=dict(zil or {}),
            vdevs=list(vdevs or []),
            arcstats_available=True,
            zil_available=bool(zil),
            iostat_available=True,
        )

    def test_rates_from_two_samples(self):
        prev = self._sample(100.0, ARC_FULL, ZIL_FULL)
        arc2 = dict(ARC_FULL)
        arc2["hits"] += 500
        arc2["misses"] += 100
        arc2["l2_read_bytes"] += 2048
        arc2["l2_write_bytes"] += 4096
        zil2 = dict(ZIL_FULL)
        zil2["zil_commit_count"] += 20
        zil2["zil_itx_metaslab_slog_count"] += 8
        zil2["zil_itx_metaslab_slog_write"] += 8192
        cur = self._sample(105.0, arc2, zil2)

        rates = ms.compute_rates(prev, cur)
        self.assertAlmostEqual(rates.arc_hits_ps, 100.0)
        self.assertAlmostEqual(rates.arc_misses_ps, 20.0)
        self.assertAlmostEqual(rates.arc_hit_rate, 100.0 * 500 / 600)
        self.assertAlmostEqual(rates.l2_read_bps, 2048 / 5)
        self.assertAlmostEqual(rates.l2_write_bps, 4096 / 5)
        self.assertAlmostEqual(rates.slog_commits_ps, 4.0)
        self.assertAlmostEqual(rates.slog_writes_ps, 1.6)
        self.assertAlmostEqual(rates.slog_write_bps, 8192 / 5)

    def test_first_sample_has_no_rates(self):
        cur = self._sample(100.0, ARC_FULL, ZIL_FULL)
        rates = ms.compute_rates(None, cur)
        self.assertIsNone(rates.arc_hits_ps)
        self.assertIsNone(rates.arc_hit_rate)
        self.assertIsNone(rates.slog_write_bps)

    def test_counter_reset_suppresses_rate(self):
        """A rebooted counter must not produce a negative rate."""
        prev = self._sample(100.0, ARC_FULL, ZIL_FULL)
        arc2 = dict(ARC_FULL)
        arc2["hits"] = 10
        cur = self._sample(110.0, arc2, ZIL_FULL)
        rates = ms.compute_rates(prev, cur)
        self.assertIsNone(rates.arc_hits_ps)
        self.assertIsNone(rates.arc_hit_rate)

    def test_zero_traffic_hit_rate_is_none(self):
        prev = self._sample(100.0, ARC_FULL, ZIL_FULL)
        cur = self._sample(105.0, ARC_FULL, ZIL_FULL)
        rates = ms.compute_rates(prev, cur)
        self.assertIsNone(rates.arc_hit_rate)

    def test_vdev_rates_pass_through_current_sample(self):
        """Vdev rows carry per-window rates already — no deltas, no prev."""
        vdev = ms.VdevSample(
            pool="fivebays",
            vdev="CACHE1",
            section="cache",
            alloc=None,
            free=None,
            reads_ps=25.0,
            writes_ps=50.0,
            read_bps=5120.0,
            write_bps=8192.0,
        )
        cur = self._sample(100.0, ARC_FULL, {}, vdevs=[vdev])
        rates = ms.compute_rates(None, cur)
        vr = rates.vdevs[("fivebays", "CACHE1")]
        self.assertAlmostEqual(vr.reads_ps, 25.0)
        self.assertAlmostEqual(vr.writes_ps, 50.0)
        self.assertAlmostEqual(vr.read_bps, 5120.0)
        self.assertAlmostEqual(vr.write_bps, 8192.0)

    def test_vdev_rates_replaced_by_newer_sample(self):
        """Each sample's table reflects that sample's own window."""
        vdev = ms.VdevSample(
            pool="fivebays",
            vdev="CACHE1",
            section="cache",
            alloc=None,
            free=None,
            reads_ps=25.0,
            writes_ps=50.0,
            read_bps=5120.0,
            write_bps=8192.0,
        )
        vdev2 = ms.VdevSample(
            pool="fivebays",
            vdev="CACHE1",
            section="cache",
            alloc=None,
            free=None,
            reads_ps=0.0,
            writes_ps=12.0,
            read_bps=0.0,
            write_bps=1024.0,
        )
        prev = self._sample(100.0, ARC_FULL, {}, vdevs=[vdev])
        cur = self._sample(102.0, ARC_FULL, {}, vdevs=[vdev2])
        rates = ms.compute_rates(prev, cur)
        vr = rates.vdevs[("fivebays", "CACHE1")]
        self.assertAlmostEqual(vr.writes_ps, 12.0)
        self.assertAlmostEqual(vr.write_bps, 1024.0)

        # A vdev that disappears leaves no stale entry behind.
        gone = self._sample(104.0, ARC_FULL, {}, vdevs=[])
        self.assertEqual(ms.compute_rates(cur, gone).vdevs, {})

    def test_nonpositive_elapsed(self):
        prev = self._sample(100.0, ARC_FULL, ZIL_FULL)
        cur = self._sample(100.0, ARC_FULL, ZIL_FULL)
        rates = ms.compute_rates(prev, cur)
        self.assertIsNone(rates.arc_hits_ps)


class TestCollectMemorySample(unittest.TestCase):
    def test_all_sources_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            arc_path = os.path.join(tmp, "arcstats")
            zil_path = os.path.join(tmp, "zil")
            with open(arc_path, "w") as f:
                f.write(_kstat_text(ARC_FULL))
            with open(zil_path, "w") as f:
                f.write(_kstat_text(ZIL_FULL))
            result = MagicMock(returncode=0, stdout=IOSTAT_INTERVAL)
            with patch.object(ms.subprocess, "run", return_value=result) as run:
                sample = ms.collect_memory_sample(arcstats_path=arc_path, zil_path=zil_path)
            run.assert_called_once_with(
                ms.IOSTAT_ARGS,
                capture_output=True,
                text=True,
                timeout=ms.IOSTAT_TIMEOUT,
                check=False,
            )
            self.assertTrue(sample.arcstats_available)
            self.assertTrue(sample.zil_available)
            self.assertTrue(sample.iostat_available)
            self.assertEqual(len(sample.vdevs), 5)

    def test_missing_zil_degrades_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            arc_path = os.path.join(tmp, "arcstats")
            with open(arc_path, "w") as f:
                f.write(_kstat_text(ARC_FULL))
            result = MagicMock(returncode=0, stdout=IOSTAT_INTERVAL)
            with patch.object(ms.subprocess, "run", return_value=result):
                sample = ms.collect_memory_sample(
                    arcstats_path=arc_path,
                    zil_path=os.path.join(tmp, "missing-zil"),
                )
            self.assertTrue(sample.arcstats_available)
            self.assertFalse(sample.zil_available)
            self.assertTrue(sample.iostat_available)

    def test_iostat_without_y_falls_back(self):
        """A pre-0.8 zpool rejects `-y`; the retry parses its last report."""
        with tempfile.TemporaryDirectory() as tmp:
            arc_path = os.path.join(tmp, "arcstats")
            zil_path = os.path.join(tmp, "zil")
            with open(arc_path, "w") as f:
                f.write(_kstat_text(ARC_FULL))
            with open(zil_path, "w") as f:
                f.write(_kstat_text(ZIL_FULL))
            rejected = MagicMock(returncode=1, stdout="")
            legacy = MagicMock(returncode=0, stdout=IOSTAT_FALLBACK)
            with patch.object(ms.subprocess, "run", side_effect=[rejected, legacy]) as run:
                sample = ms.collect_memory_sample(arcstats_path=arc_path, zil_path=zil_path)
            commands = [c.args[0] for c in run.call_args_list]
            self.assertEqual(commands, [ms.IOSTAT_ARGS, ms.IOSTAT_ARGS_FALLBACK])
            self.assertTrue(sample.iostat_available)
            self.assertEqual(len(sample.vdevs), 5)
            mirror = next(v for v in sample.vdevs if v.vdev == "mirror-2")
            self.assertEqual(mirror.writes_ps, 89)  # interval, not since-boot 48

    def test_iostat_failure_degrades_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            arc_path = os.path.join(tmp, "arcstats")
            zil_path = os.path.join(tmp, "zil")
            with open(arc_path, "w") as f:
                f.write(_kstat_text(ARC_FULL))
            with open(zil_path, "w") as f:
                f.write(_kstat_text(ZIL_FULL))
            result = MagicMock(returncode=1, stdout="")
            with patch.object(ms.subprocess, "run", return_value=result):
                sample = ms.collect_memory_sample(arcstats_path=arc_path, zil_path=zil_path)
            self.assertTrue(sample.arcstats_available)
            self.assertTrue(sample.zil_available)
            self.assertFalse(sample.iostat_available)
            self.assertEqual(sample.vdevs, [])

    def test_iostat_timeout_degrades_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            arc_path = os.path.join(tmp, "arcstats")
            with open(arc_path, "w") as f:
                f.write(_kstat_text(ARC_FULL))
            with patch.object(
                ms.subprocess, "run", side_effect=subprocess.TimeoutExpired("zpool", 10)
            ):
                sample = ms.collect_memory_sample(
                    arcstats_path=arc_path,
                    zil_path=os.path.join(tmp, "missing-zil"),
                )
            self.assertTrue(sample.arcstats_available)
            self.assertFalse(sample.iostat_available)

    def test_all_sources_missing(self):
        """A host with no kstats and no zpool yields an all-unavailable sample."""
        with patch.object(ms.subprocess, "run", side_effect=OSError("no zpool")):
            sample = ms.collect_memory_sample(
                arcstats_path="/nonexistent/arcstats",
                zil_path="/nonexistent/zil",
            )
        self.assertFalse(sample.arcstats_available)
        self.assertFalse(sample.zil_available)
        self.assertFalse(sample.iostat_available)


class TestFormatters(unittest.TestCase):
    def test_format_rate(self):
        self.assertEqual(ms.format_rate(None), "—")
        self.assertEqual(ms.format_rate(1024), "1.00 KiB/s")

    def test_format_percent(self):
        self.assertEqual(ms.format_percent(None), "—")
        self.assertEqual(ms.format_percent(83.46), "83.5%")
        self.assertEqual(ms.format_percent(83.46, 2), "83.46%")

    def test_format_per_second(self):
        self.assertEqual(ms.format_per_second(None), "—")
        self.assertEqual(ms.format_per_second(1234.5), "1,234")

    def test_cumulative_hit_rate(self):
        self.assertIsNone(ms.cumulative_hit_rate(None, 5))
        self.assertIsNone(ms.cumulative_hit_rate(0, 0))
        self.assertAlmostEqual(ms.cumulative_hit_rate(75, 25), 75.0)

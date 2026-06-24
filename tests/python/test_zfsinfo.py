"""Tests for zfsinfo.py — ZFS info gathering with mocked subprocess."""

import unittest

from test_support import mock_subprocess

import zfsinfo


class TestGetPools(unittest.TestCase):

    def test_get_pools_parses_output(self):
        with mock_subprocess() as m:
            m.add_zpool_list([
                {"name": "tank", "size": "10T", "alloc": "5T", "free": "5T", "health": "ONLINE"},
                {"name": "backup", "size": "4T", "alloc": "1T", "free": "3T", "health": "DEGRADED"},
            ])
            pools = zfsinfo.get_pools()
        self.assertEqual(len(pools), 2)
        self.assertEqual(pools[0]["name"], "tank")
        self.assertEqual(pools[0]["health"], "ONLINE")
        self.assertEqual(pools[1]["health"], "DEGRADED")

    def test_get_pools_returns_empty_on_error(self):
        with mock_subprocess() as m:
            m.set_command_handler("zpool list", lambda cmd, **kwargs: m._completed("", rc=1))
            pools = zfsinfo.get_pools()
        self.assertEqual(pools, [])


class TestGetDatasets(unittest.TestCase):

    def test_get_datasets_parses_output(self):
        with mock_subprocess() as m:
            m.add_zfs_list([
                {"name": "tank/data", "used": "100G", "avail": "500G", "refer": "50G", "mountpoint": "/data"},
                {"name": "tank/data/sub", "used": "10G", "avail": "500G", "refer": "5G", "mountpoint": "/data/sub"},
            ])
            datasets = zfsinfo.get_datasets("tank")
        self.assertEqual(len(datasets), 2)
        self.assertEqual(datasets[0]["name"], "tank/data")
        self.assertEqual(datasets[0]["mountpoint"], "/data")

    def test_get_datasets_no_pool(self):
        with mock_subprocess() as m:
            m.add_zfs_list([
                {"name": "tank", "used": "1T", "avail": "2T", "refer": "100G", "mountpoint": "/tank"},
            ])
            datasets = zfsinfo.get_datasets()
        self.assertEqual(len(datasets), 1)


class TestGetSnapshotCounts(unittest.TestCase):

    def test_counts_snapshots(self):
        with mock_subprocess() as m:
            m.add_zfs_snaps("tank", [
                "tank/data@snap1\t2025-01-01\t100K\t50G",
                "tank/data@snap2\t2025-01-02\t200K\t50G",
                "tank/other@snap1\t2025-01-01\t50K\t10G",
            ])
            counts = zfsinfo.get_snapshot_counts("tank")
        self.assertEqual(counts["tank/data"], 2)
        self.assertEqual(counts["tank/other"], 1)

    def test_empty_on_error(self):
        with mock_subprocess() as m:
            m.set_command_handler("zfs list.*snapshot", lambda cmd, **kwargs: m._completed("", rc=1))
            counts = zfsinfo.get_snapshot_counts("tank")
        self.assertEqual(counts, {})


class TestPrintFunctions(unittest.TestCase):

    def test_print_pools_with_data(self):
        pools = [{"name": "tank", "size": "10T", "alloc": "5T", "free": "5T", "health": "ONLINE"}]
        zfsinfo.print_pools(pools)

    def test_print_pools_empty(self):
        zfsinfo.print_pools([])

    def test_print_datasets_with_counts(self):
        datasets = [{"name": "tank/data", "used": "100G"}]
        counts = {"tank/data": 5}
        zfsinfo.print_datasets(datasets, counts)

    def test_print_summary(self):
        pools = [{"name": "tank", "health": "ONLINE"}]
        datasets = [{"name": "tank/data"}]
        counts = {"tank/data": 3}
        zfsinfo.print_summary(pools, datasets, counts)


if __name__ == "__main__":
    unittest.main()

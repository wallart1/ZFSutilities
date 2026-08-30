"""Tests for disk_repository.py — lsblk, by-id, and smartctl isolation."""

import os
import subprocess
import sys
import unittest
from unittest.mock import patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from disk_repository import DiskRepository
from test_support import mock_subprocess


class TestDiskRepositoryListDisks(unittest.TestCase):
    """lsblk JSON parsing, filtering, and type classification."""

    def _make_lsblk_json(self):
        return {
            "blockdevices": [
                {
                    "name": "sda",
                    "path": "/dev/sda",
                    "size": 1000204886016,
                    "type": "disk",
                    "rota": True,
                    "tran": "sata",
                    "model": "WD10EZEX-00BN5A0",
                    "serial": "WD-WCC3F1SP",
                    "log-sec": 512,
                    "phy-sec": 4096,
                },
                {
                    "name": "sdb",
                    "path": "/dev/sdb",
                    "size": 500107862016,
                    "type": "disk",
                    "rota": False,
                    "tran": "sata",
                    "model": "Samsung SSD 860",
                    "serial": "S3Z1NB0K",
                    "log-sec": 512,
                    "phy-sec": 512,
                },
                {
                    "name": "nvme0n1",
                    "path": "/dev/nvme0n1",
                    "size": 1024209543168,
                    "type": "disk",
                    "rota": False,
                    "tran": "nvme",
                    "model": "Samsung SSD 980",
                    "serial": "S5P2NS0W",
                    "log-sec": 512,
                    "phy-sec": 512,
                },
                {
                    "name": "sda1",
                    "path": "/dev/sda1",
                    "size": 536870912000,
                    "type": "part",
                    "rota": True,
                    "tran": "sata",
                    "model": None,
                    "serial": None,
                    "log-sec": 512,
                    "phy-sec": 4096,
                },
                {
                    "name": "zd0",
                    "path": "/dev/zd0",
                    "size": 10737418240,
                    "type": "disk",
                    "rota": False,
                    "tran": None,
                    "model": None,
                    "serial": None,
                },
                {
                    "name": "loop0",
                    "path": "/dev/loop0",
                    "size": 0,
                    "type": "disk",
                    "rota": False,
                    "tran": None,
                    "model": None,
                    "serial": None,
                },
            ]
        }

    def test_list_disks_filters_and_classifies(self):
        import json

        with mock_subprocess() as m:
            m.set_command_handler(
                r"^lsblk",
                lambda _cmd, **_kw: subprocess.CompletedProcess(
                    args=[], returncode=0, stdout=json.dumps(self._make_lsblk_json())
                ),
            )
            repo = DiskRepository(sudo=False)
            disks = repo.list_disks()

        self.assertEqual(len(disks), 3)
        by_path = {d.path: d for d in disks}
        self.assertEqual(by_path["/dev/sda"].disk_type, "HDD")
        self.assertEqual(by_path["/dev/sdb"].disk_type, "SSD")
        self.assertEqual(by_path["/dev/nvme0n1"].disk_type, "NVMe")
        self.assertEqual(by_path["/dev/sda"].size_human, "931.51 GiB")
        self.assertEqual(by_path["/dev/sda"].logical_sector, 512)
        self.assertEqual(by_path["/dev/sda"].physical_sector, 4096)

    def test_list_disks_returns_empty_on_failure(self):
        with mock_subprocess() as m:
            m.set_command_handler(
                r"^lsblk",
                lambda _cmd, **_kw: subprocess.CompletedProcess(
                    args=[], returncode=1, stdout="", stderr="boom"
                ),
            )
            repo = DiskRepository(sudo=False)
            self.assertEqual(repo.list_disks(), [])


class TestDiskRepositoryResolveById(unittest.TestCase):
    """by-id resolution selects whole-disk symlinks and prefers wwn."""

    def test_resolve_by_id_maps_targets(self):
        find_output = (
            "/dev/disk/by-id/wwn-0x5000cca768\n"
            "/dev/disk/by-id/ata-WDC_WD10EZEX\n"
            "/dev/disk/by-id/wwn-0x5000cca768-part1\n"
        )

        def _realpath(link):
            if "-part" in link:
                return "/dev/sda1"
            if "wwn" in link or "ata" in link:
                return "/dev/sda"
            return link

        with mock_subprocess() as m:
            m.set_command_handler(
                r"^find",
                lambda _cmd, **_kw: subprocess.CompletedProcess(
                    args=[], returncode=0, stdout=find_output
                ),
            )
            with patch("disk_repository.os.path.realpath", side_effect=_realpath):
                repo = DiskRepository(sudo=False)
                mapping = repo.resolve_by_id()

        self.assertEqual(mapping["/dev/sda"], "wwn-0x5000cca768")
        self.assertNotIn("/dev/sda1", mapping)


class TestDiskRepositorySmart(unittest.TestCase):
    """smartctl health/details return PASSED/FAILED/n/a and never raise."""

    def test_smart_health_passed(self):
        with mock_subprocess() as m:
            m.set_command_handler(
                r"smartctl -H",
                lambda _cmd, **_kw: subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout="SMART overall-health self-assessment test result: PASSED\n",
                ),
            )
            repo = DiskRepository(sudo=False)
            self.assertEqual(repo.smart_health("/dev/sda"), "PASSED")

    def test_smart_health_failed(self):
        with mock_subprocess() as m:
            m.set_command_handler(
                r"smartctl -H",
                lambda _cmd, **_kw: subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout="SMART overall-health self-assessment test result: FAILED\n",
                ),
            )
            repo = DiskRepository(sudo=False)
            self.assertEqual(repo.smart_health("/dev/sda"), "FAILED")

    def test_smart_health_missing_binary(self):
        with mock_subprocess() as m:
            m.set_command_handler(
                r"smartctl -H",
                lambda _cmd, **_kw: (_ for _ in ()).throw(FileNotFoundError("smartctl")),
            )
            repo = DiskRepository(sudo=False)
            self.assertEqual(repo.smart_health("/dev/sda"), "n/a")

    def test_smart_details_raw(self):
        with mock_subprocess() as m:
            m.set_command_handler(
                r"smartctl -a",
                lambda _cmd, **_kw: subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="=== START OF INFORMATION SECTION ===\n"
                ),
            )
            repo = DiskRepository(sudo=False)
            self.assertIn("START OF INFORMATION", repo.smart_details("/dev/sda"))

    def test_smart_details_missing_binary(self):
        with mock_subprocess() as m:
            m.set_command_handler(
                r"smartctl -a",
                lambda _cmd, **_kw: (_ for _ in ()).throw(FileNotFoundError("smartctl")),
            )
            repo = DiskRepository(sudo=False)
            self.assertEqual(repo.smart_details("/dev/sda"), "n/a")


class TestDiskRepositoryInventory(unittest.TestCase):
    """disk_inventory combines disks, by-id mapping, and SMART health."""

    def test_disk_inventory(self):
        import json

        lsblk_data = {
            "blockdevices": [
                {
                    "name": "sda",
                    "path": "/dev/sda",
                    "size": 1000204886016,
                    "type": "disk",
                    "rota": True,
                    "tran": "sata",
                    "model": "WD10EZEX",
                    "serial": "WD-WCC",
                    "log-sec": 512,
                    "phy-sec": 4096,
                }
            ]
        }

        def _handler(cmd, **_kw):
            cmd_str = " ".join(str(c) for c in cmd)
            if cmd_str.startswith("lsblk"):
                return subprocess.CompletedProcess(
                    args=[], returncode=0, stdout=json.dumps(lsblk_data)
                )
            if cmd_str.startswith("find"):
                return subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="/dev/disk/by-id/wwn-abc\n"
                )
            if "smartctl" in cmd_str and "-H" in cmd_str:
                return subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout="SMART overall-health self-assessment test result: PASSED\n",
                )
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="")

        with mock_subprocess() as m:
            m.set_command_handler(r".*", _handler)
            with patch("disk_repository.os.path.realpath", return_value="/dev/sda"):
                repo = DiskRepository(sudo=False)
                inventory = repo.disk_inventory()

        self.assertEqual(len(inventory.disks), 1)
        disk = inventory.disks[0]
        self.assertEqual(disk.by_id, "wwn-abc")
        self.assertEqual(disk.smart_health, "PASSED")
        self.assertEqual(inventory.by_path["/dev/sda"], disk)


if __name__ == "__main__":
    unittest.main()

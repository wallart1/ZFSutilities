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
                    "children": [
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
                            "name": "sda2",
                            "path": "/dev/sda2",
                            "size": 536870912000,
                            "type": "part",
                            "rota": True,
                            "tran": "sata",
                            "model": None,
                            "serial": None,
                            "log-sec": 512,
                            "phy-sec": 4096,
                        },
                    ],
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
                    "name": "sda2",
                    "path": "/dev/sda2",
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

        self.assertEqual(len(disks), 5)
        by_path = {d.path: d for d in disks}
        self.assertEqual(by_path["/dev/sda"].disk_type, "HDD")
        self.assertEqual(by_path["/dev/sdb"].disk_type, "SSD")
        self.assertEqual(by_path["/dev/nvme0n1"].disk_type, "NVMe")
        self.assertEqual(by_path["/dev/sda"].size_human, "931.51 GiB")
        self.assertEqual(by_path["/dev/sda"].logical_sector, 512)
        self.assertEqual(by_path["/dev/sda"].physical_sector, 4096)
        self.assertEqual(by_path["/dev/sda1"].disk_type, "part")
        self.assertEqual(by_path["/dev/sda1"].parent_path, "/dev/sda")
        self.assertEqual(by_path["/dev/sda1"].transport, "sata")
        self.assertEqual(by_path["/dev/sda2"].disk_type, "part")
        self.assertEqual(by_path["/dev/sda2"].parent_path, "/dev/sda")

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
        self.assertEqual(mapping["/dev/sda1"], "wwn-0x5000cca768-part1")


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
                    "children": [
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
                        }
                    ],
                }
            ]
        }

        smartctl_calls = []

        def _handler(cmd, **_kw):
            cmd_str = " ".join(str(c) for c in cmd)
            if cmd_str.startswith("lsblk"):
                return subprocess.CompletedProcess(
                    args=[], returncode=0, stdout=json.dumps(lsblk_data)
                )
            if cmd_str.startswith("find"):
                return subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout=("/dev/disk/by-id/wwn-abc\n/dev/disk/by-id/wwn-abc-part1\n"),
                )
            if "smartctl" in cmd_str and "-H" in cmd_str:
                smartctl_calls.append(cmd_str)
                return subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout="SMART overall-health self-assessment test result: PASSED\n",
                )
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="")

        def _realpath(link):
            if "-part1" in link:
                return "/dev/sda1"
            return "/dev/sda"

        with mock_subprocess() as m:
            m.set_command_handler(r".*", _handler)
            with patch("disk_repository.os.path.realpath", side_effect=_realpath):
                repo = DiskRepository(sudo=False)
                inventory = repo.disk_inventory()

        self.assertEqual(len(inventory.disks), 2)
        disk = inventory.by_path["/dev/sda"]
        part = inventory.by_path["/dev/sda1"]
        self.assertEqual(disk.by_id, "wwn-abc")
        self.assertEqual(disk.smart_health, "PASSED")
        self.assertEqual(part.by_id, "wwn-abc-part1")
        self.assertEqual(part.smart_health, "PASSED")
        self.assertEqual(part.parent_path, "/dev/sda")
        self.assertNotIn("/dev/sda1", smartctl_calls)


class TestBootDiskFiltering(unittest.TestCase):
    """The system boot disk and its partitions never appear in list_disks()."""

    def _base_lsblk_json(self):
        """Inventory: sda (2 parts), sdb, sdc (1 part), sdd (3 parts)."""

        def _part(name, parent_size=100000):
            return {
                "name": name,
                "path": f"/dev/{name}",
                "size": parent_size,
                "type": "part",
                "rota": True,
                "tran": "sata",
                "model": None,
                "serial": None,
                "log-sec": 512,
                "phy-sec": 512,
            }

        def _disk(name, parts=()):
            dev = {
                "name": name,
                "path": f"/dev/{name}",
                "size": 1000000,
                "type": "disk",
                "rota": True,
                "tran": "sata",
                "model": "TESTDISK",
                "serial": "XYZ",
                "log-sec": 512,
                "phy-sec": 512,
            }
            if parts:
                dev["children"] = [_part(p) for p in parts]
            return dev

        return {
            "blockdevices": [
                _disk("sda", ("sda1", "sda2")),
                _disk("sdb"),
                _disk("sdc", ("sdc1",)),
                _disk("sdd", ("sdd1", "sdd2", "sdd3")),
            ]
        }

    def _probe_json(self, blockdevices):
        return {"blockdevices": blockdevices}

    def _pk_chain(self, disk, *parts_and_pk):
        """Build a nested NAME,PATH,PKNAME probe: one disk plus child rows.

        *parts_and_pk* is alternating child dicts; each child's "pkname" is
        preset to *disk* and children may nest their own "children" list.
        """
        disk_row = {"name": disk, "path": f"/dev/{disk}", "pkname": None}
        children = []
        for row in parts_and_pk:
            row = dict(row)
            row.setdefault("pkname", disk)
            children.append(row)
        if children:
            disk_row["children"] = children
        return self._probe_json([disk_row])

    def _list_with_mocks(
        self,
        findmnt_source="",
        findmnt_rc=0,
        pk_probe=None,
        pk_rc=0,
        mp_probe=None,
    ):
        import json

        with mock_subprocess() as m:

            def _findmnt(_cmd, **_kw):
                if findmnt_rc != 0:
                    return subprocess.CompletedProcess(
                        args=[], returncode=findmnt_rc, stdout="", stderr="boom"
                    )
                return subprocess.CompletedProcess(
                    args=[], returncode=0, stdout=findmnt_source + "\n"
                )

            m.set_command_handler(r"findmnt", _findmnt)
            if pk_probe is not None:
                m.set_command_handler(
                    r"PKNAME",
                    lambda _cmd, **_kw: subprocess.CompletedProcess(
                        args=[],
                        returncode=pk_rc,
                        stdout=json.dumps(pk_probe) if pk_rc == 0 else "",
                        stderr="" if pk_rc == 0 else "boom",
                    ),
                )
            if mp_probe is not None:
                m.set_command_handler(
                    r"MOUNTPOINT",
                    lambda _cmd, **_kw: subprocess.CompletedProcess(
                        args=[], returncode=0, stdout=json.dumps(mp_probe)
                    ),
                )
            m.set_command_handler(
                r"^lsblk",
                lambda _cmd, **_kw: subprocess.CompletedProcess(
                    args=[], returncode=0, stdout=json.dumps(self._base_lsblk_json())
                ),
            )
            repo = DiskRepository(sudo=False)
            return repo.list_disks()

    def _paths(self, disks):
        return sorted(d.path for d in disks)

    def test_plain_partition_root_hides_disk_and_partitions(self):
        probe = self._pk_chain(
            "sda",
            {"name": "sda1", "path": "/dev/sda1", "type": "part"},
            {"name": "sda2", "path": "/dev/sda2", "type": "part"},
        )
        disks = self._list_with_mocks(findmnt_source="/dev/sda2", pk_probe=probe)
        self.assertEqual(
            self._paths(disks),
            [
                "/dev/sdb",
                "/dev/sdc",
                "/dev/sdc1",
                "/dev/sdd",
                "/dev/sdd1",
                "/dev/sdd2",
                "/dev/sdd3",
            ],
        )

    def test_btrfs_root_strips_subvolume_suffix(self):
        """findmnt prints /dev/sda3[/@]; the suffix must be stripped (dev VM)."""
        probe = self._pk_chain(
            "sda",
            {"name": "sda3", "path": "/dev/sda3", "type": "part"},
        )
        disks = self._list_with_mocks(findmnt_source="/dev/sda3[/@]", pk_probe=probe)
        self.assertEqual(
            self._paths(disks),
            [
                "/dev/sdb",
                "/dev/sdc",
                "/dev/sdc1",
                "/dev/sdd",
                "/dev/sdd1",
                "/dev/sdd2",
                "/dev/sdd3",
            ],
        )

    def test_lvm_root_walks_pkname_chain_to_disk(self):
        """Root on /dev/mapper/pve-root (pve-root -> sdd3 -> sdd) hides sdd."""
        probe = self._pk_chain(
            "sdd",
            {
                "name": "sdd3",
                "path": "/dev/sdd3",
                "type": "part",
                "children": [
                    {
                        "name": "pve-root",
                        "path": "/dev/mapper/pve-root",
                        "type": "lvm",
                        "pkname": "sdd3",
                    }
                ],
            },
        )
        disks = self._list_with_mocks(findmnt_source="/dev/mapper/pve-root", pk_probe=probe)
        self.assertEqual(
            self._paths(disks),
            ["/dev/sda", "/dev/sda1", "/dev/sda2", "/dev/sdb", "/dev/sdc", "/dev/sdc1"],
        )

    def test_zfs_dataset_root_falls_back_to_mountpoint_scan(self):
        """findmnt reports a dataset name, not a /dev path; lsblk MOUNTPOINT wins."""
        probe = self._probe_json(
            [
                {"name": "sdc", "path": "/dev/sdc", "type": "disk", "pkname": None},
                {
                    "name": "sdc1",
                    "path": "/dev/sdc1",
                    "type": "part",
                    "pkname": "sdc",
                    "mountpoint": "/",
                },
            ]
        )
        disks = self._list_with_mocks(findmnt_source="rpool/ROOT/pve", mp_probe=probe)
        self.assertEqual(
            self._paths(disks),
            [
                "/dev/sda",
                "/dev/sda1",
                "/dev/sda2",
                "/dev/sdb",
                "/dev/sdd",
                "/dev/sdd1",
                "/dev/sdd2",
                "/dev/sdd3",
            ],
        )

    def test_findmnt_failure_falls_back_to_mountpoint_scan(self):
        probe = self._probe_json(
            [
                {"name": "sda", "path": "/dev/sda", "type": "disk", "pkname": None},
                {
                    "name": "sda1",
                    "path": "/dev/sda1",
                    "type": "part",
                    "pkname": "sda",
                    "mountpoint": "/",
                },
            ]
        )
        disks = self._list_with_mocks(findmnt_rc=1, mp_probe=probe)
        self.assertEqual(
            self._paths(disks),
            [
                "/dev/sdb",
                "/dev/sdc",
                "/dev/sdc1",
                "/dev/sdd",
                "/dev/sdd1",
                "/dev/sdd2",
                "/dev/sdd3",
            ],
        )

    def test_no_root_found_hides_nothing(self):
        probe = self._probe_json(
            [
                {"name": "sda", "path": "/dev/sda", "type": "disk", "pkname": None},
                {"name": "sdb", "path": "/dev/sdb", "type": "disk", "pkname": None},
            ]
        )
        disks = self._list_with_mocks(mp_probe=probe)
        self.assertEqual(
            self._paths(disks),
            [
                "/dev/sda",
                "/dev/sda1",
                "/dev/sda2",
                "/dev/sdb",
                "/dev/sdc",
                "/dev/sdc1",
                "/dev/sdd",
                "/dev/sdd1",
                "/dev/sdd2",
                "/dev/sdd3",
            ],
        )

    def test_failed_pkname_probe_hides_nothing(self):
        disks = self._list_with_mocks(
            findmnt_source="/dev/sda2", pk_probe={"blockdevices": []}, pk_rc=1
        )
        self.assertEqual(len(disks), 10)


if __name__ == "__main__":
    unittest.main()

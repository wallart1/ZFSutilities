"""Tests for enclosure_inventory.py — grouping, identity, pool join, cache."""

import hashlib
import json
import os
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from disk_repository import DiskRepository
from enclosure_inventory import (
    EnclosureInventory,
    _normalize_wwn,
    enclosure_id,
    pci_controller,
    usb_hub_location,
)
from test_support import capture_logs, mock_subprocess
from zfs_repository import TopologyNode


def _completed(stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


def _lsblk_json(*disks):
    """Build lsblk --json output from (name, transport) pairs; paths /dev/<name>."""
    return json.dumps(
        {
            "blockdevices": [
                {"name": name, "path": f"/dev/{name}", "type": "disk", "tran": tran}
                for name, tran in disks
            ]
        }
    )


def _udev_output(devpath, wwn=None):
    lines = [f"P: {devpath}", "N: x", "E: DEVTYPE=disk"]
    if wwn:
        lines.append(f"E: ID_WWN=0x{wwn}")
    return "\n".join(lines) + "\n"


def _usb_devpath(root, hub, port, name):
    return (
        f"/devices/pci0000:00/0000:00:14.0/usb{root}/{hub}/{hub}.{port}/"
        f"{hub}.{port}:1.0/host6/target6:0:0/6:0:0:0/block/{name}"
    )


def _sata_devpath(controller, name, bridge=None):
    prefix = f"/devices/pci0000:00/{bridge}/" if bridge else "/devices/pci0000:00/"
    return f"{prefix}{controller}/ata5/host9/target9:0:0/9:0:0:0/block/{name}"


def _nvme_devpath(name):
    return f"/devices/pci0000:00/0000:00:1d.0/nvme/nvme0/{name}"


def _leaf(path):
    return TopologyNode(
        name=path,
        vdev_type="disk",
        state="ONLINE",
        read=0,
        write=0,
        cksum=0,
        ashift=None,
        children=[],
    )


def _pool_root(pool, leaves):
    return TopologyNode(
        name=pool,
        vdev_type="pool",
        state="ONLINE",
        read=0,
        write=0,
        cksum=0,
        ashift=None,
        children=[_leaf(path) for path in leaves],
    )


class _FakeZfsRepository:
    """Duck-typed ZfsRepository serving fixed pool topologies."""

    def __init__(self, topology_by_pool):
        self._topology_by_pool = topology_by_pool

    def list_pools(self):
        return [SimpleNamespace(name=name) for name in self._topology_by_pool]

    def pool_topology(self, pool):
        return self._topology_by_pool.get(pool)


class TestLocationHelpers(unittest.TestCase):
    """Pure DEVPATH parsing helpers."""

    def test_usb_hub_location_reports_root_and_hub(self):
        devpath = "/devices/pci0000:00/0000:00:14.0/usb2/2-2/2-2.4/2-2.4:1.0/host6/block/sdb"
        self.assertEqual(usb_hub_location(devpath), "usb2/2-2")

    def test_usb_hub_location_direct_disk_on_root_port(self):
        devpath = "/devices/pci0000:00/usb1/1-4/1-4:1.0/host3/block/sda"
        self.assertEqual(usb_hub_location(devpath), "usb1/1-4")

    def test_usb_hub_location_distinguishes_root_hubs(self):
        first = "/devices/pci0000:00/usb2/2-2/2-2:1.0/host1/block/sda"
        second = "/devices/pci0000:00/usb3/2-2/2-2:1.0/host2/block/sdb"
        self.assertEqual(usb_hub_location(first), "usb2/2-2")
        self.assertEqual(usb_hub_location(second), "usb3/2-2")

    def test_usb_hub_location_without_root_hub(self):
        self.assertIsNone(usb_hub_location("/devices/pci0000:00/0000:00:1f.2/ata1/host1/block/sda"))

    def test_pci_controller_picks_deepest_function(self):
        devpath = "/devices/pci0000:00/0000:00:1c.4/0000:03:00.0/ata4/host3/block/sdc"
        self.assertEqual(pci_controller(devpath), "0000:03:00.0")

    def test_pci_controller_without_pci_segment(self):
        self.assertIsNone(pci_controller("/devices/virtual/block/loop0"))

    def test_normalize_wwn_strips_prefixes(self):
        self.assertEqual(_normalize_wwn("0x5000c500a4b2c3d1"), "5000c500a4b2c3d1")
        self.assertEqual(_normalize_wwn("naa.5000c500a4b2c3d1"), "5000c500a4b2c3d1")
        self.assertEqual(_normalize_wwn("5000C500A4B2C3D1"), "5000c500a4b2c3d1")

    def test_enclosure_id_is_sha256_prefix_of_sorted_wwns(self):
        expected = hashlib.sha256(b"aaaa\nbbbb").hexdigest()[:10]
        self.assertEqual(enclosure_id(["bbbb", "aaaa", "aaaa"]), expected)


class TestEnclosureInventoryScan(unittest.TestCase):
    """Grouping, identity, boot-controller exclusion, and pool union."""

    def _scan(self, lsblk_disks, udev_by_path, topology_by_pool=None, boot_path="/dev/nvme0n1"):
        def lsblk_handler(cmd, **kwargs):
            return _completed(_lsblk_json(*lsblk_disks))

        def udev_handler(cmd, **kwargs):
            output = udev_by_path.get(cmd[-1])
            if output is None:
                return _completed("", returncode=2)
            return _completed(output)

        with mock_subprocess() as sub:
            sub.set_command_handler(r"^lsblk", lsblk_handler)
            sub.set_command_handler(r"^udevadm", udev_handler)
            with patch.object(DiskRepository, "_find_boot_disk_path", return_value=boot_path):
                inventory = EnclosureInventory(
                    zfs_repository=_FakeZfsRepository(topology_by_pool or {})
                )
                result = inventory.scan()
        return result

    def test_usb_enclosures_group_by_hub(self):
        udev = {
            "/dev/nvme0n1": _udev_output(_nvme_devpath("nvme0n1"), "wwnboot"),
            "/dev/nvme1n1": _udev_output(_nvme_devpath("nvme1n1"), "wwnnvme2"),
        }
        disks = [("nvme0n1", "nvme"), ("nvme1n1", "nvme")]
        # fivebays-like: sdb..sdf on hub 2-2; threeamigos-like: sdg..sdi on 2-6.
        for port, suffix in enumerate("bcdef", start=1):
            name = f"sd{suffix}"
            disks.append((name, "usb"))
            udev[f"/dev/{name}"] = _udev_output(_usb_devpath(2, "2-2", port, name), f"wwnfb{port}")
        for port, suffix in enumerate("ghi", start=1):
            name = f"sd{suffix}"
            disks.append((name, "usb"))
            udev[f"/dev/{name}"] = _udev_output(_usb_devpath(2, "2-6", port, name), f"wwnta{port}")

        enclosures = self._scan(disks, udev)

        self.assertEqual(len(enclosures), 2)
        fivebays, threeamigos = enclosures
        self.assertEqual((fivebays.kind, fivebays.location), ("usb", "usb2/2-2"))
        self.assertEqual(fivebays.members, ["sdb", "sdc", "sdd", "sde", "sdf"])
        self.assertEqual((threeamigos.kind, threeamigos.location), ("usb", "usb2/2-6"))
        self.assertEqual(threeamigos.members, ["sdg", "sdh", "sdi"])
        self.assertEqual(
            fivebays.id,
            hashlib.sha256(
                "\n".join(sorted(f"wwnfb{i}" for i in range(1, 6))).encode()
            ).hexdigest()[:10],
        )

    def test_esata_groups_by_controller_with_boot_controller_excluded(self):
        # sda (boot) and sdb share the internal controller; sdc/sdd sit on a
        # controller behind a PCI bridge.
        udev = {
            "/dev/sda": _udev_output(_sata_devpath("0000:00:1f.2", "sda"), "wwnboot"),
            "/dev/sdb": _udev_output(_sata_devpath("0000:00:1f.2", "sdb"), "wwnint"),
            "/dev/sdc": _udev_output(
                _sata_devpath("0000:03:00.0", "sdc", bridge="0000:00:1c.4"), "wwnes1"
            ),
            "/dev/sdd": _udev_output(
                _sata_devpath("0000:03:00.0", "sdd", bridge="0000:00:1c.4"), "wwnes2"
            ),
        }
        disks = [("sda", "sata"), ("sdb", "sata"), ("sdc", "sata"), ("sdd", "sata")]

        enclosures = self._scan(disks, udev, boot_path="/dev/sda")

        self.assertEqual(len(enclosures), 1)
        enclosure = enclosures[0]
        self.assertEqual((enclosure.kind, enclosure.location), ("esata", "0000:03:00.0"))
        self.assertEqual(enclosure.members, ["sdc", "sdd"])
        self.assertEqual(enclosure.id, hashlib.sha256(b"wwnes1\nwwnes2").hexdigest()[:10])

    def test_boot_disk_on_nvme_leaves_sata_controllers_as_candidates(self):
        # Boot disk's controller hosts no SATA disk, so nothing is excluded
        # and an internal SATA controller is reported as a candidate.
        udev = {
            "/dev/nvme0n1": _udev_output(_nvme_devpath("nvme0n1"), "wwnboot"),
            "/dev/sda": _udev_output(_sata_devpath("0000:00:1f.2", "sda"), "wwnsata"),
        }
        enclosures = self._scan(
            [("nvme0n1", "nvme"), ("sda", "sata")], udev, boot_path="/dev/nvme0n1"
        )
        self.assertEqual(len(enclosures), 1)
        self.assertEqual((enclosures[0].kind, enclosures[0].location), ("esata", "0000:00:1f.2"))

    def test_boot_disk_probe_failure_fails_open(self):
        # Unknown boot disk must not block discovery: the SATA disk is still
        # reported, and the failure is logged.
        udev = {"/dev/sda": _udev_output(_sata_devpath("0000:00:1f.2", "sda"), "wwnsata")}

        def lsblk_handler(cmd, **kwargs):
            return _completed(_lsblk_json(("sda", "sata")))

        def udev_handler(cmd, **kwargs):
            output = udev.get(cmd[-1])
            return _completed(output) if output else _completed("", returncode=2)

        with mock_subprocess() as sub:
            sub.set_command_handler(r"^lsblk", lsblk_handler)
            sub.set_command_handler(r"^udevadm", udev_handler)
            with patch.object(
                DiskRepository, "_find_boot_disk_path", side_effect=RuntimeError("probe died")
            ):
                inventory = EnclosureInventory(zfs_repository=_FakeZfsRepository({}))
                with capture_logs() as logs:
                    enclosures = inventory.scan()
        self.assertEqual(len(enclosures), 1)
        self.assertEqual(enclosures[0].kind, "esata")
        self.assertTrue(any("boot-disk probe failed" in msg for msg in logs))

    def test_identity_is_stable_across_port_and_name_changes(self):
        first_udev = {
            "/dev/sdb": _udev_output(_usb_devpath(2, "2-2", 1, "sdb"), "wwncommon1"),
            "/dev/sdc": _udev_output(_usb_devpath(2, "2-2", 2, "sdc"), "wwncommon2"),
        }
        second_udev = {
            # Same WWNs, replugged to another root hub and reshuffled names.
            "/dev/sdg": _udev_output(_usb_devpath(3, "1-1", 4, "sdg"), "wwncommon2"),
            "/dev/sdh": _udev_output(_usb_devpath(3, "1-1", 2, "sdh"), "wwncommon1"),
        }
        first = self._scan([("sdb", "usb"), ("sdc", "usb")], first_udev)
        second = self._scan([("sdg", "usb"), ("sdh", "usb")], second_udev)
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertEqual(first[0].id, second[0].id)
        self.assertNotEqual(first[0].location, second[0].location)

    def test_identity_differs_for_different_member_sets(self):
        first = self._scan(
            [("sdb", "usb")],
            {"/dev/sdb": _udev_output(_usb_devpath(2, "2-2", 1, "sdb"), "wwna")},
        )
        second = self._scan(
            [("sdb", "usb")],
            {"/dev/sdb": _udev_output(_usb_devpath(2, "2-2", 1, "sdb"), "wwnb")},
        )
        self.assertNotEqual(first[0].id, second[0].id)

    def test_pools_union_across_members_and_pools_span_enclosures(self):
        # Hub 2-2 holds disks of two pools; poola also has a disk on hub 2-6.
        udev = {
            "/dev/sdb": _udev_output(_usb_devpath(2, "2-2", 1, "sdb"), "wwnpoola1"),
            "/dev/sdc": _udev_output(_usb_devpath(2, "2-2", 2, "sdc"), "wwnpoolb"),
            "/dev/sdd": _udev_output(_usb_devpath(2, "2-6", 1, "sdd"), "wwnpoola2"),
        }
        topology = {
            "poola": _pool_root("poola", ["/dev/sdb", "/dev/sdd"]),
            "poolb": _pool_root("poolb", ["/dev/sdc"]),
        }
        enclosures = self._scan(
            [("sdb", "usb"), ("sdc", "usb"), ("sdd", "usb")],
            udev,
            topology_by_pool=topology,
        )
        by_location = {e.location: e for e in enclosures}
        self.assertEqual(by_location["usb2/2-2"].pools, ["poola", "poolb"])
        self.assertEqual(by_location["usb2/2-6"].pools, ["poola"])

    def test_members_without_any_pool_report_no_pools(self):
        udev = {"/dev/sdb": _udev_output(_usb_devpath(2, "2-2", 1, "sdb"), "wwnspare")}
        enclosures = self._scan([("sdb", "usb")], udev)
        self.assertEqual(len(enclosures), 1)
        self.assertEqual(enclosures[0].pools, [])

    def test_pool_on_partition_leaf_attributes_to_whole_disk(self):
        # stewie shape: pools built on partition leaves while members are
        # whole disks.
        udev = {"/dev/sdb": _udev_output(_usb_devpath(2, "2-2", 1, "sdb"), "wwnpart")}
        topology = {"fivebays": _pool_root("fivebays", ["/dev/sdb1"])}
        enclosures = self._scan([("sdb", "usb")], udev, topology_by_pool=topology)
        self.assertEqual(enclosures[0].pools, ["fivebays"])

    def test_pools_for_disk_partition_suffix_grammar(self):
        # sd-style names: bare digit suffix is a partition.
        self.assertEqual(
            EnclosureInventory._pools_for_disk("/dev/sde", {"sde1": ["p"], "sde10": ["q"]}),
            ["p", "q"],
        )
        # Digit-ending names: only p<N> counts; nvme0n11 is a sibling disk.
        self.assertEqual(
            EnclosureInventory._pools_for_disk(
                "/dev/nvme0n1", {"nvme0n1p2": ["p"], "nvme0n11": ["other"]}
            ),
            ["p"],
        )
        # No suffix bleed between adjacent disk names.
        self.assertEqual(EnclosureInventory._pools_for_disk("/dev/sdf", {"sde1": ["p"]}), [])
        # Exact whole-disk leaf still matches.
        self.assertEqual(EnclosureInventory._pools_for_disk("/dev/sdg", {"sdg": ["p"]}), ["p"])

    def test_group_without_any_wwn_is_skipped_with_warning(self):
        udev = {"/dev/sdb": _udev_output(_usb_devpath(2, "2-2", 1, "sdb"), None)}
        with capture_logs() as logs:
            enclosures = self._scan([("sdb", "usb")], udev)
        self.assertEqual(enclosures, [])
        self.assertTrue(any("no stable identity" in msg for msg in logs))

    def test_disk_with_missing_udev_entry_is_skipped_but_others_group(self):
        udev = {"/dev/sdb": _udev_output(_usb_devpath(2, "2-2", 1, "sdb"), "wwnkeep")}
        # /dev/sdc deliberately absent → udev exit 2.
        enclosures = self._scan([("sdb", "usb"), ("sdc", "usb")], udev)
        self.assertEqual(len(enclosures), 1)
        self.assertEqual(enclosures[0].members, ["sdb"])

    def test_lsblk_failure_returns_no_enclosures(self):
        def udev_handler(cmd, **kwargs):
            return _completed("", returncode=2)

        with mock_subprocess() as sub:
            sub.set_command_handler(r"^udevadm", udev_handler)
            sub.set_command_handler(
                r"^lsblk", lambda cmd, **kw: _completed("", returncode=1, stderr="boom")
            )
            inventory = EnclosureInventory(zfs_repository=_FakeZfsRepository({}))
            self.assertEqual(inventory.scan(), [])

    def test_partitions_zvols_and_loops_are_not_members(self):
        blockdevices = {
            "blockdevices": [
                {"name": "sdb", "path": "/dev/sdb", "type": "disk", "tran": "usb"},
                # Top-level part/zd/loop rows must all be ignored.
                {"name": "sdb1", "path": "/dev/sdb1", "type": "part", "tran": "usb"},
                {"name": "zd16", "path": "/dev/zd16", "type": "disk", "tran": ""},
                {"name": "loop0", "path": "/dev/loop0", "type": "loop", "tran": ""},
            ]
        }
        udev = {"/dev/sdb": _udev_output(_usb_devpath(2, "2-2", 1, "sdb"), "wwnonly")}

        def lsblk_handler(cmd, **kwargs):
            return _completed(json.dumps(blockdevices))

        def udev_handler(cmd, **kwargs):
            output = udev.get(cmd[-1])
            return _completed(output) if output else _completed("", returncode=2)

        with mock_subprocess() as sub:
            sub.set_command_handler(r"^lsblk", lsblk_handler)
            sub.set_command_handler(r"^udevadm", udev_handler)
            with patch.object(DiskRepository, "_find_boot_disk_path", return_value=None):
                inventory = EnclosureInventory(zfs_repository=_FakeZfsRepository({}))
                enclosures = inventory.scan()
        self.assertEqual(len(enclosures), 1)
        self.assertEqual(enclosures[0].members, ["sdb"])


class TestEnclosureInventoryCache(unittest.TestCase):
    """TTL behavior of discover()."""

    def _make_inventory(self, lsblk_calls):
        udev = {"/dev/sdb": _udev_output(_usb_devpath(2, "2-2", 1, "sdb"), "wwnc")}

        def lsblk_handler(cmd, **kwargs):
            lsblk_calls.append(1)
            return _completed(_lsblk_json(("sdb", "usb")))

        def udev_handler(cmd, **kwargs):
            output = udev.get(cmd[-1])
            return _completed(output) if output else _completed("", returncode=2)

        context = mock_subprocess()
        sub = context.__enter__()
        sub.set_command_handler(r"^lsblk", lsblk_handler)
        sub.set_command_handler(r"^udevadm", udev_handler)
        patcher = patch.object(DiskRepository, "_find_boot_disk_path", return_value="/dev/nvme0n1")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(context.__exit__, None, None, None)
        return EnclosureInventory(zfs_repository=_FakeZfsRepository({}))

    def test_discover_uses_cache_within_ttl(self):
        lsblk_calls = []
        inventory = self._make_inventory(lsblk_calls)
        first = inventory.discover()
        second = inventory.discover()
        self.assertEqual(first, second)
        self.assertEqual(len(lsblk_calls), 1)

    def test_invalidate_forces_rescan(self):
        lsblk_calls = []
        inventory = self._make_inventory(lsblk_calls)
        inventory.discover()
        inventory.invalidate()
        inventory.discover()
        self.assertEqual(len(lsblk_calls), 2)

    def test_zero_ttl_always_rescans(self):
        lsblk_calls = []
        inventory = self._make_inventory(lsblk_calls)
        inventory.ttl = 0.0
        inventory.discover()
        inventory.discover()
        self.assertEqual(len(lsblk_calls), 2)


if __name__ == "__main__":
    unittest.main()

"""Enclosure inventory — USB-hub and eSATA-controller grouping of disks.

Discovers multi-bay enclosures as disk groups: USB disks group by the hub
directly under a root USB hub, SATA disks group by PCI controller with the
boot disk's controller excluded (internal boot storage is not an enclosure).
Enclosure identity is a short hash of the sorted member WWNs, so it survives
replug and port moves even though hub/bridge serials repeat across enclosures.

All subprocess access (lsblk transport scan, udevadm DEVPATH/WWN lookup,
zpool topology via ZfsRepository, boot-disk resolution via DiskRepository)
is injectable so tests can fake collectors. Consumed by
lib/enclosure_rate.py (the shared resolver) and, through it, every paced
transfer pipeline and the GUI's rate seam.
"""

import hashlib
import json
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import NamedTuple

from disk_repository import DiskRepository
from logging_config import log_msg

# Regex: ^usb\d+$
# Purpose: a root USB hub segment in a udev DEVPATH (e.g. `usb2`).
_USB_ROOT_RE = re.compile(r"^usb\d+$")

# Regex: ^\d+-\d+(\.\d+)*(:[^/]+)?$
# Purpose: a USB device-path segment below the root hub — `2-2` (a hub or
# disk plugged into root-hub port 2), `2-2.4` (port 4 on that hub), with an
# optional `:1.0`-style interface suffix.
_USB_DEVICE_RE = re.compile(r"^\d+-\d+(\.\d+)*(:[^/]+)?$")

# Regex: ^[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-9a-f]$
# Purpose: a PCI function segment in a DEVPATH (e.g. `0000:00:1f.2` — PCI
# segments are hexadecimal, so letters are normal in slots and functions).
_PCI_FUNC_RE = re.compile(r"^[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-9a-f]$")


def usb_hub_location(devpath: str) -> str | None:
    """Return the hub directly under a root USB hub for *devpath*, or None.

    The location is `<roothub>/<port-path>` (e.g. `usb2/2-2`): every disk
    whose DEVPATH descends from that segment — plugged into the hub itself
    or into a hub behind it — shares the location. The root hub is part of
    the key because hosts expose several root hubs and port numbers repeat
    across them.
    """
    parts = devpath.strip("/").split("/")
    for i, part in enumerate(parts):
        if _USB_ROOT_RE.match(part):
            if i + 1 < len(parts) and _USB_DEVICE_RE.match(parts[i + 1]):
                return f"{part}/{parts[i + 1].split(':', 1)[0]}"
            return None
    return None


def pci_controller(devpath: str) -> str | None:
    """Return the endpoint PCI controller segment of *devpath*, or None.

    The deepest PCI function wins so a controller behind a PCI bridge keys
    by its own function, not the upstream bridge shared with other devices.
    """
    for part in reversed(devpath.strip("/").split("/")):
        if _PCI_FUNC_RE.match(part):
            return part
    return None


def _normalize_wwn(value: str) -> str:
    """Normalize a udev WWN property to a bare lowercase hex string."""
    value = value.strip().lower()
    for prefix in ("naa.", "0x"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
            break
    return value


def enclosure_id(wwns) -> str:
    """Return the stable short identity for a member-WWN set."""
    digest = hashlib.sha256("\n".join(sorted(set(wwns))).encode()).hexdigest()
    return digest[:10]


class _TransportDisk(NamedTuple):
    """One whole disk from the lsblk transport scan."""

    name: str
    path: str
    transport: str


@dataclass
class EnclosureInfo:
    """One discovered enclosure."""

    id: str
    kind: str  # "usb" or "esata"
    location: str  # "<roothub>/<hub>" or PCI controller ("0000:03:00.0")
    members: list[str] = field(default_factory=list)  # kernel disk names, sorted
    pools: list[str] = field(default_factory=list)  # union of member pools, sorted


class EnclosureInventory:
    """Discover disk enclosures with a TTL cache around the device scan.

    USB disks group by root-hub port (the hub directly under a root USB
    hub); SATA disks group by PCI controller, excluding the boot disk's
    controller so internal boot storage never forms an enclosure. Pool
    membership comes from `zpool status -P` topology leaves, joined to disks
    the same way DiskInventoryCache does it (realpath first, basename
    fallback).
    """

    def __init__(
        self,
        disk_repository: DiskRepository | None = None,
        zfs_repository=None,
        udevadm_bin: str = "udevadm",
        ttl_seconds: float = 30.0,
    ):
        # The boot-disk path finder lives on DiskRepository (findmnt + lsblk
        # PKNAME walk with the mountpoint fallback); reuse it rather than
        # duplicating that chain here.
        self.disk_repository = disk_repository if disk_repository is not None else DiskRepository()
        if zfs_repository is None:
            from zfs_repository import ZfsRepository

            zfs_repository = ZfsRepository()
        self.zfs_repository = zfs_repository
        self.udevadm_bin = udevadm_bin
        self.ttl = ttl_seconds
        self._lock = threading.Lock()
        self._enclosures: list[EnclosureInfo] | None = None
        self._last_scan = 0.0

    # ------------------------------------------------------------------
    # Cached entry point
    # ------------------------------------------------------------------

    def discover(self) -> list[EnclosureInfo]:
        """Return enclosures, rescanning only when the TTL has expired."""
        with self._lock:
            if self._enclosures is not None and time.monotonic() - self._last_scan < self.ttl:
                return list(self._enclosures)
        enclosures = self.scan()
        with self._lock:
            self._enclosures = enclosures
            self._last_scan = time.monotonic()
        return list(enclosures)

    def invalidate(self) -> None:
        """Force a fresh scan on the next discover() call."""
        with self._lock:
            self._last_scan = 0.0

    # ------------------------------------------------------------------
    # Subprocess collectors (injectable via constructor/binary names)
    # ------------------------------------------------------------------

    def _run(self, cmd: list[str], check: bool = True, timeout: int | None = None):
        return subprocess.run(cmd, capture_output=True, text=True, check=check, timeout=timeout)

    def _list_transport_disks(self) -> list[_TransportDisk]:
        """Whole disks with their transport from `lsblk --json`.

        Partitions, zvols (zd*), and loop devices are dropped; only whole
        disks can be enclosure members.
        """
        result = self._run(["lsblk", "--json", "-o", "NAME,PATH,TYPE,TRAN"], check=False)
        if result.returncode != 0:
            log_msg(f"WARN: lsblk transport scan failed: {result.stderr.strip()}")
            return []
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            log_msg(f"WARN: Failed to parse lsblk transport JSON: {exc}")
            return []
        disks = []
        for dev in data.get("blockdevices", []):
            if dev.get("type") != "disk":
                continue
            name = str(dev.get("name") or "")
            path = str(dev.get("path") or "")
            if not name or not path:
                continue
            if name.startswith(("zd", "loop")) or path.startswith("/dev/zd"):
                continue
            disks.append(_TransportDisk(name, path, str(dev.get("tran") or "").lower()))
        return disks

    def _udev_lookup(self, path: str) -> tuple[str | None, str | None]:
        """Return (DEVPATH, WWN) for a disk path from `udevadm info --query=all`.

        Both values are None when udev cannot answer — a disk may vanish
        between the lsblk and udevadm calls, and discovery skips it rather
        than failing the whole scan.
        """
        try:
            result = self._run(
                [self.udevadm_bin, "info", "--query=all", path],
                check=False,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            log_msg(f"WARN: udevadm lookup failed for {path}: {exc}")
            return None, None
        if result.returncode != 0 or not result.stdout:
            log_msg(f"VERB: no udev database entry for {path}")
            return None, None

        devpath = None
        wwn_extension = None
        wwn_plain = None
        for line in result.stdout.splitlines():
            if devpath is None and line.startswith("P: "):
                devpath = line[3:].strip()
            elif line.startswith("E: ID_WWN_WITH_EXTENSION="):
                wwn_extension = _normalize_wwn(line.split("=", 1)[1])
            elif line.startswith("E: ID_WWN="):
                wwn_plain = _normalize_wwn(line.split("=", 1)[1])
        return devpath, wwn_extension or wwn_plain

    # ------------------------------------------------------------------
    # Pool membership
    # ------------------------------------------------------------------

    def _pool_leaves(self) -> dict[str, list[str]]:
        """Map topology leaf device paths to pool names for every pool."""
        mapping: dict[str, list[str]] = {}
        try:
            pools = self.zfs_repository.list_pools()
        except Exception as exc:
            log_msg(f"WARN: could not list pools for enclosure discovery: {exc}")
            return mapping
        for row in pools:
            pool_name = getattr(row, "name", None)
            if not pool_name:
                continue
            try:
                topology = self.zfs_repository.pool_topology(pool_name)
            except Exception as exc:
                log_msg(f"WARN: topology read failed for pool {pool_name}: {exc}")
                topology = None
            if topology is None:
                continue
            self._collect_leaves(topology, pool_name, mapping)
        return mapping

    @staticmethod
    def _collect_leaves(node, pool_name: str, mapping: dict[str, list[str]]) -> None:
        """Record leaf disk paths for pool membership lookups."""
        if getattr(node, "vdev_type", None) == "disk" and node.name:
            mapping.setdefault(node.name, []).append(pool_name)
            real = os.path.realpath(node.name)
            if real != node.name:
                mapping.setdefault(real, []).append(pool_name)
        for child in node.children:
            EnclosureInventory._collect_leaves(child, pool_name, mapping)

    # Regexes for the kernel partition suffix of a leaf basename relative
    # to its parent disk: `sde1` -> `1` after `sde`; `nvme0n1p1` -> `p1`
    # after `nvme0n1`. Names ending in a digit (nvme0n1, md0) always use
    # the `p` separator, so a bare digit after them is a sibling device
    # (nvme0n11), not a partition.
    _PART_SUFFIX_PLAIN_RE = re.compile(r"^\d+$")
    _PART_SUFFIX_P_RE = re.compile(r"^p\d+$")

    @classmethod
    def _pools_for_disk(cls, path: str, mapping: dict[str, list[str]]) -> list[str]:
        """Return sorted pool names for *path* (realpath, basename fallback).

        Pools are frequently built on partitions (`sde1`, by-id `-part1`),
        while enclosure members are whole disks, so a leaf counts when its
        basename is the disk's basename plus a kernel partition suffix.
        """
        pools = set(mapping.get(os.path.realpath(path), []))
        base = path.rsplit("/", 1)[-1]
        if not pools:
            suffix_re = (
                cls._PART_SUFFIX_P_RE if base and base[-1].isdigit() else cls._PART_SUFFIX_PLAIN_RE
            )
            for leaf_path, pool_names in mapping.items():
                leaf_base = leaf_path.rsplit("/", 1)[-1]
                suffix = leaf_base[len(base) :] if leaf_base.startswith(base) else None
                if leaf_base == base or (suffix is not None and suffix_re.match(suffix)):
                    pools.update(pool_names)
        return sorted(pools)

    # ------------------------------------------------------------------
    # Scan
    # ------------------------------------------------------------------

    def scan(self) -> list[EnclosureInfo]:
        """Discover enclosures now, bypassing the cache."""
        disks = self._list_transport_disks()
        if not disks:
            return []

        udev: dict[str, tuple[str | None, str | None]] = {
            disk.path: self._udev_lookup(disk.path) for disk in disks
        }
        boot_controller = self._boot_disk_controller(disks, udev)
        path_to_pools = self._pool_leaves()

        groups: dict[tuple[str, str], list[_TransportDisk]] = {}
        for disk in disks:
            devpath, _wwn = udev[disk.path]
            if not devpath:
                continue
            if disk.transport == "usb":
                location = usb_hub_location(devpath)
                if location:
                    groups.setdefault(("usb", location), []).append(disk)
            elif disk.transport == "sata":
                controller = pci_controller(devpath)
                if controller and controller != boot_controller:
                    groups.setdefault(("esata", controller), []).append(disk)

        enclosures: list[EnclosureInfo] = []
        for (kind, location), members in groups.items():
            known = [udev[disk.path][1] for disk in members if udev[disk.path][1]]
            if not known:
                log_msg(
                    f"WARN: enclosure at {kind} {location} has disks with no "
                    "WWN; skipped (no stable identity)"
                )
                continue
            pools: set[str] = set()
            for disk in members:
                pools.update(self._pools_for_disk(disk.path, path_to_pools))
            enclosures.append(
                EnclosureInfo(
                    id=enclosure_id(known),
                    kind=kind,
                    location=location,
                    members=sorted(disk.name for disk in members),
                    pools=sorted(pools),
                )
            )
        enclosures.sort(key=lambda e: (e.kind, e.location))
        return enclosures

    def _boot_disk_controller(
        self,
        disks: list[_TransportDisk],
        udev: dict[str, tuple[str | None, str | None]],
    ) -> str | None:
        """Return the PCI controller hosting the boot disk, or None.

        None (unknown boot disk, or a boot disk whose controller hosts no
        SATA disk, e.g. NVMe) excludes nothing — discovery then reports
        every SATA controller as a candidate enclosure, which is the
        fail-open direction: a possibly-spurious enclosure is better than
        silently hiding a real one.
        """
        try:
            boot_path = self.disk_repository._find_boot_disk_path()
        except Exception as exc:
            log_msg(f"WARN: boot-disk probe failed during enclosure discovery: {exc}")
            return None
        if not boot_path:
            return None
        devpath = udev.get(boot_path, (None, None))[0]
        if devpath is None:
            devpath = self._udev_lookup(boot_path)[0]
        controller = pci_controller(devpath) if devpath else None
        if controller:
            log_msg(f"VERB: excluding boot-disk controller {controller} from eSATA grouping")
        return controller


if __name__ == "__main__":
    found = EnclosureInventory().scan()
    if not found:
        print("No enclosures discovered")
    for enclosure in found:
        pools = ",".join(enclosure.pools) if enclosure.pools else "-"
        print(
            f"{enclosure.id}  {enclosure.kind:<5} {enclosure.location:<14} "
            f"members={','.join(enclosure.members)} pools={pools}"
        )

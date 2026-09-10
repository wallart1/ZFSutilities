"""Block-device repository — isolates lsblk, /dev/disk/by-id, and smartctl calls.

All direct non-ZFS block-device access from the GUI layer lives here so tests
can mock subprocess responses. Methods return typed dataclasses and never raise
for optional dependencies such as smartctl.
"""

import json
import os
import re
import subprocess
from dataclasses import dataclass, field

from backup_config import log_msg


@dataclass
class DiskInfo:
    """One physical disk or partition from `lsblk`."""

    name: str
    path: str
    by_id: str = ""
    model: str = ""
    serial: str = ""
    size_bytes: int = 0
    size_human: str = "-"
    disk_type: str = "unknown"
    logical_sector: int | None = None
    physical_sector: int | None = None
    transport: str = ""
    pools: list[str] = field(default_factory=list)
    smart_health: str = "n/a"
    parent_path: str | None = None


@dataclass
class DiskInventory:
    """A full disk inventory plus a path -> DiskInfo index."""

    disks: list[DiskInfo] = field(default_factory=list)
    by_path: dict[str, DiskInfo] = field(default_factory=dict)


# Regex: ^\s*SMART overall-health self-assessment test result:\s*(\S+).*$
# Purpose: Extract the pass/fail result from `smartctl -H` output.
# Group 1: the result word, e.g. PASSED or FAILED.
_SMART_HEALTH_RE = re.compile(r"^\s*SMART overall-health self-assessment test result:\s*(\S+).*$")


def _flatten_blockdevices(devices) -> dict:
    """Index lsblk JSON rows by name, recursing through nested "children".

    Some lsblk column sets flatten the tree, others nest it; index both
    shapes so PKNAME chains of any depth (e.g. lvm on a partition) resolve.
    """
    by_name = {}
    stack = list(devices)
    while stack:
        dev = stack.pop()
        name = dev.get("name")
        if name:
            by_name[name] = dev
        stack.extend(dev.get("children") or [])
    return by_name


def _format_bytes(size: int) -> str:
    """Return a compact human-readable representation of *size* bytes."""
    if size <= 0:
        return "0 B"
    units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
    value = float(size)
    unit = units[0]
    for next_unit in units[1:]:
        if value < 1024.0:
            break
        value /= 1024.0
        unit = next_unit
    if unit == "B":
        return f"{int(value)} B"
    return f"{value:.2f} {unit}"


class DiskRepository:
    """Wrap lsblk/by-id/smartctl subprocess calls for testability."""

    def __init__(
        self,
        sudo: bool = False,
        lsblk_bin: str = "lsblk",
        smartctl_bin: str = "smartctl",
        find_bin: str = "find",
        findmnt_bin: str = "findmnt",
        udevadm_bin: str = "udevadm",
    ):
        self.sudo = sudo
        self.lsblk_bin = lsblk_bin
        self.smartctl_bin = smartctl_bin
        self.find_bin = find_bin
        self.findmnt_bin = findmnt_bin
        self.udevadm_bin = udevadm_bin

    def _run(self, cmd: list[str], check: bool = True, timeout: int | None = None):
        return subprocess.run(cmd, capture_output=True, text=True, check=check, timeout=timeout)

    def _prefix(self, cmd: list[str]) -> list[str]:
        """Prepend sudo to *cmd* when the repository was created with sudo=True."""
        return (["sudo"] + cmd) if self.sudo else cmd

    def list_disks(self) -> list[DiskInfo]:
        """Return physical disks and their partitions from `lsblk --json`.

        Whole disks are classified as HDD/SSD/NVMe; partitions are typed
        ``part`` and carry ``parent_path`` so callers can relate them to
        their underlying device. The system boot disk (the disk hosting the
        root filesystem) and all of its partitions are always removed, so no
        Disks-page list ever offers them.
        """
        cmd = self._prefix(
            [
                self.lsblk_bin,
                "--json",
                "--bytes",
                "-o",
                "NAME,PATH,SIZE,TYPE,ROTA,TRAN,MODEL,SERIAL,LOG-SEC,PHY-SEC",
            ]
        )
        result = self._run(cmd, check=False)
        if result.returncode != 0:
            log_msg(f"WARN: lsblk failed: {result.stderr.strip()}")
            return []

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            log_msg(f"WARN: Failed to parse lsblk JSON: {exc}")
            return []

        def _int(value):
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        def _disk_type(dev):
            rota = dev.get("rota")
            tran = (dev.get("tran") or "").lower()
            if rota == 1:
                return "HDD"
            if tran == "nvme":
                return "NVMe"
            if rota == 0:
                return "SSD"
            return "unknown"

        def _process_device(dev, parent=None):
            dev_type = dev.get("type")
            if dev_type == "disk":
                name = dev.get("name", "")
                path = dev.get("path", "")
                if name.startswith(("zd", "loop")) or path.startswith("/dev/zd"):
                    return None
            elif dev_type == "part" and parent is not None:
                name = dev.get("name", "")
                path = dev.get("path", "")
            else:
                return None

            size_bytes = dev.get("size") or 0
            try:
                size_bytes = int(size_bytes)
            except (TypeError, ValueError):
                size_bytes = 0

            if parent is None:
                disk_type = _disk_type(dev)
                model = (dev.get("model") or "").strip()
                serial = (dev.get("serial") or "").strip()
                transport = (dev.get("tran") or "").lower()
                parent_path = None
            else:
                disk_type = "part"
                model = ""
                serial = ""
                transport = parent.transport
                parent_path = parent.path

            disk = DiskInfo(
                name=name,
                path=path,
                model=model,
                serial=serial,
                size_bytes=size_bytes,
                size_human=_format_bytes(size_bytes),
                disk_type=disk_type,
                logical_sector=_int(dev.get("log-sec")),
                physical_sector=_int(dev.get("phy-sec")),
                transport=transport,
                parent_path=parent_path,
            )
            return disk

        disks: list[DiskInfo] = []
        for dev in data.get("blockdevices", []):
            disk = _process_device(dev)
            if disk is None:
                continue
            disks.append(disk)
            for child in dev.get("children", []):
                if child.get("type") != "part":
                    continue
                part = _process_device(child, parent=disk)
                if part is not None:
                    disks.append(part)
        return self._without_boot_disk(disks)

    def _find_boot_disk_path(self) -> str | None:
        """Return the /dev path of the disk hosting the root filesystem, or None.

        The root may sit on a plain partition, an LVM/dm volume, a BTRFS
        subvolume, or a ZFS dataset, so the block-device source from findmnt(8)
        is walked up its lsblk PKNAME chain to the top-level disk. Every
        failure mode returns None — the caller then does not filter anything.
        """
        source = self._root_source()
        if source is None:
            return self._boot_disk_from_mountpoints()
        return self._toplevel_disk_path(source)

    def _root_source(self) -> str | None:
        """Return the block-device path behind the root mount, or None.

        findmnt(8) prints e.g. ``/dev/sda2``, ``/dev/mapper/pve-root`` or, for
        BTRFS, ``/dev/sda3[/@]`` — the subvolume suffix is stripped here.
        ZFS datasets come back as a dataset name rather than a /dev path and
        return None so the caller can fall back to the mountpoint scan.
        """
        cmd = self._prefix([self.findmnt_bin, "-n", "-o", "SOURCE", "/"])
        try:
            result = self._run(cmd, check=False)
        except (FileNotFoundError, OSError) as exc:
            log_msg(f"WARN: could not probe for the boot disk: {exc}")
            return None
        if result.returncode != 0:
            log_msg(f"WARN: boot-disk probe failed: {result.stderr.strip()}")
            return None
        source = ""
        if result.stdout.strip():
            source = result.stdout.splitlines()[0].strip().split("[", 1)[0]
        if not source.startswith("/dev/"):
            log_msg(f"DEBUG: root source {source!r} is not a block-device path")
            return None
        return source

    def _toplevel_disk_path(self, source: str) -> str | None:
        """Walk *source* up its lsblk PKNAME chain; return the top disk path."""
        cmd = self._prefix([self.lsblk_bin, "--json", "-n", "-o", "NAME,PATH,PKNAME"])
        try:
            result = self._run(cmd, check=False)
        except (FileNotFoundError, OSError) as exc:
            log_msg(f"WARN: could not resolve the boot disk: {exc}")
            return None
        if result.returncode != 0:
            log_msg(f"WARN: boot-disk resolution failed: {result.stderr.strip()}")
            return None
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            log_msg(f"WARN: could not parse boot-disk resolution output: {exc}")
            return None
        by_name = _flatten_blockdevices(data.get("blockdevices", []))
        name = os.path.basename(source)
        if name not in by_name:
            log_msg(f"WARN: could not resolve boot disk from {source!r}")
            return None
        top = by_name[name]
        while top.get("pkname"):
            parent = by_name.get(top["pkname"])
            if parent is None:
                break
            top = parent
        path = top.get("path") or ""
        if not path.startswith("/dev/"):
            log_msg(f"WARN: could not resolve a boot-disk path from {top.get('name')!r}")
            return None
        return path

    def _boot_disk_from_mountpoints(self) -> str | None:
        """Fallback: find the disk holding ``/`` via lsblk MOUNTPOINT rows.

        BTRFS systems may report a different subvolume's mountpoint per
        device (findmnt is preferred there); this fallback covers ZFS roots,
        where findmnt reports the dataset instead of a /dev path.
        """
        cmd = self._prefix([self.lsblk_bin, "--json", "-n", "-o", "PATH,TYPE,PKNAME,MOUNTPOINT"])
        try:
            result = self._run(cmd, check=False)
        except (FileNotFoundError, OSError) as exc:
            log_msg(f"WARN: could not probe for the boot disk: {exc}")
            return None
        if result.returncode != 0:
            log_msg(f"WARN: boot-disk probe failed: {result.stderr.strip()}")
            return None
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            log_msg(f"WARN: could not parse boot-disk probe output: {exc}")
            return None

        by_name = _flatten_blockdevices(data.get("blockdevices", []))
        root = next((dev for dev in by_name.values() if dev.get("mountpoint") == "/"), None)
        if root is None:
            log_msg("DEBUG: no root-filesystem device found; boot disk not hidden")
            return None
        top = root
        while top.get("pkname"):
            parent = by_name.get(top["pkname"])
            if parent is None:
                break
            top = parent
        path = top.get("path") or ""
        if not path.startswith("/dev/"):
            log_msg(f"WARN: could not resolve a boot-disk path from {top.get('name')!r}")
            return None
        return path

    def _without_boot_disk(self, disks: list[DiskInfo]) -> list[DiskInfo]:
        """Drop the system boot disk and all of its partitions from *disks*."""
        boot_path = self._find_boot_disk_path()
        if not boot_path:
            return disks
        boot_real = os.path.realpath(boot_path)
        kept: list[DiskInfo] = []
        hidden_parts = 0
        for disk in disks:
            if os.path.realpath(disk.path) == boot_real:
                continue  # the boot disk itself
            if disk.parent_path is not None and os.path.realpath(disk.parent_path) == boot_real:
                hidden_parts += 1
                continue
            kept.append(disk)
        if len(kept) == len(disks):
            return disks
        log_msg(
            f"INFO: hiding system boot disk {boot_path} "
            f"({hidden_parts} partitions) from the disk inventory"
        )
        return kept

    def resolve_by_id(self) -> dict[str, str]:
        """Map kernel device paths to the best `/dev/disk/by-id` symlink name."""
        by_id: dict[str, str] = {}
        cmd = self._prefix([self.find_bin, "/dev/disk/by-id", "-type", "l"])
        result = self._run(cmd, check=False)
        if result.returncode != 0:
            return by_id

        def _score(name: str) -> int:
            if name.startswith("wwn-"):
                return 3
            if name.startswith("ata-"):
                return 2
            if name.startswith("scsi-"):
                return 1
            return 0

        for line in result.stdout.splitlines():
            link = line.strip()
            if not link:
                continue
            basename = os.path.basename(link)
            try:
                target = os.path.realpath(link)
            except OSError:
                continue
            existing = by_id.get(target)
            if existing is None or _score(basename) > _score(existing):
                by_id[target] = basename
        return by_id

    def smart_health(self, path: str) -> str:
        """Return SMART health for *path* as PASSED, FAILED, or n/a."""
        if not path:
            return "n/a"
        cmd = self._prefix([self.smartctl_bin, "-H", path])
        try:
            result = self._run(cmd, check=False)
        except (FileNotFoundError, OSError):
            return "n/a"
        if result.returncode != 0:
            return "n/a"
        for line in result.stdout.splitlines():
            match = _SMART_HEALTH_RE.match(line)
            if match:
                result_word = match.group(1).upper()
                if result_word == "PASSED":
                    return "PASSED"
                if result_word == "FAILED":
                    return "FAILED"
                return result_word
        return "n/a"

    def smart_details(self, path: str) -> str:
        """Return raw `smartctl -a` output for *path*, or n/a if unavailable."""
        if not path:
            return "n/a"
        cmd = self._prefix([self.smartctl_bin, "-a", path])
        try:
            result = self._run(cmd, check=False)
        except (FileNotFoundError, OSError):
            return "n/a"
        if result.returncode != 0:
            return "n/a"
        return result.stdout or "n/a"

    def disk_inventory(self) -> DiskInventory:
        """Combine lsblk, by-id resolution, and SMART health into an inventory."""
        disks = self.list_disks()
        by_id_map = self.resolve_by_id()

        parent_health: dict[str, str] = {}
        for disk in disks:
            disk.by_id = by_id_map.get(disk.path, "")
            if disk.parent_path is None:
                disk.smart_health = self.smart_health(disk.path)
                parent_health[disk.path] = disk.smart_health
            else:
                disk.smart_health = parent_health.get(disk.parent_path, "n/a")

        by_path: dict[str, DiskInfo] = {}
        for disk in disks:
            by_path[disk.path] = disk
        return DiskInventory(disks=disks, by_path=by_path)

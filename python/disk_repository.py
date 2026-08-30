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
    """One physical disk from `lsblk`."""

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


@dataclass
class DiskInventory:
    """A full disk inventory plus a path -> DiskInfo index."""

    disks: list[DiskInfo] = field(default_factory=list)
    by_path: dict[str, DiskInfo] = field(default_factory=dict)


# Regex: ^\s*SMART overall-health self-assessment test result:\s*(\S+).*$
# Purpose: Extract the pass/fail result from `smartctl -H` output.
# Group 1: the result word, e.g. PASSED or FAILED.
_SMART_HEALTH_RE = re.compile(r"^\s*SMART overall-health self-assessment test result:\s*(\S+).*$")


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
        udevadm_bin: str = "udevadm",
    ):
        self.sudo = sudo
        self.lsblk_bin = lsblk_bin
        self.smartctl_bin = smartctl_bin
        self.find_bin = find_bin
        self.udevadm_bin = udevadm_bin

    def _run(self, cmd: list[str], check: bool = True, timeout: int | None = None):
        return subprocess.run(cmd, capture_output=True, text=True, check=check, timeout=timeout)

    def _prefix(self, cmd: list[str]) -> list[str]:
        """Prepend sudo to *cmd* when the repository was created with sudo=True."""
        return (["sudo"] + cmd) if self.sudo else cmd

    def list_disks(self) -> list[DiskInfo]:
        """Return physical disks from `lsblk --json`, excluding partitions and zvols."""
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

        disks: list[DiskInfo] = []
        for dev in data.get("blockdevices", []):
            if dev.get("type") != "disk":
                continue
            name = dev.get("name", "")
            path = dev.get("path", "")
            if name.startswith(("zd", "loop")) or path.startswith("/dev/zd"):
                continue

            rota = dev.get("rota")
            tran = (dev.get("tran") or "").lower()
            if rota == 1:
                disk_type = "HDD"
            elif tran == "nvme":
                disk_type = "NVMe"
            elif rota == 0:
                disk_type = "SSD"
            else:
                disk_type = "unknown"

            size_bytes = dev.get("size") or 0
            try:
                size_bytes = int(size_bytes)
            except (TypeError, ValueError):
                size_bytes = 0

            def _int(value):
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return None

            disks.append(
                DiskInfo(
                    name=name,
                    path=path,
                    model=(dev.get("model") or "").strip(),
                    serial=(dev.get("serial") or "").strip(),
                    size_bytes=size_bytes,
                    size_human=_format_bytes(size_bytes),
                    disk_type=disk_type,
                    logical_sector=_int(dev.get("log-sec")),
                    physical_sector=_int(dev.get("phy-sec")),
                    transport=tran,
                )
            )
        return disks

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
            # Skip partition symlinks; whole-disk mappings are sufficient here.
            if "-part" in basename:
                continue
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
        by_path: dict[str, DiskInfo] = {}
        for disk in disks:
            disk.by_id = by_id_map.get(disk.path, "")
            disk.smart_health = self.smart_health(disk.path)
            by_path[disk.path] = disk
        return DiskInventory(disks=disks, by_path=by_path)

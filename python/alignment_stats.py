"""Blocksize-alignment and workload statistics for the Alignment view.

Pure data layer with no GTK dependencies, mirroring memory_stats: every
source is probed independently and degrades on its own with an explanatory
flag, so the view can render per-source notes instead of failing outright.

Sources and their availability flags:

- ``zfs_repo`` (pool list, effective ashift, vdev topology, dataset block
  properties) and ``disk_repo`` (lsblk logical/physical sectors) ->
  ``pools_available`` / ``datasets_available``
- ``zpool iostat -r`` — per-pool request-size histograms since boot ->
  ``iostat_r_available``
- ``/proc/spl/kstat/zfs/arcstats`` and ``.../zfetchstats`` — ARC and
  prefetcher counters (same kstat grammar memory_stats parses) ->
  ``arcstats_available`` / ``prefetch_available``
- ``/etc/pve/qemu-server/*.conf`` — PVE VM disk options when the GUI host
  is also the PVE node (single-node installs) -> ``pve_available``

The alignment view refreshes independently of the Live Charts view, so it
collects its own copy of the kstats rather than sharing the charts sample.
"""

import glob
import os
import re
import subprocess
import time
from dataclasses import dataclass, field

from memory_stats import (
    ARCSTATS_PATH,
    _parse_iostat_cell,
    parse_arcstats,
    parse_kstats,
)

ZFETCHSTATS_PATH = "/proc/spl/kstat/zfs/zfetchstats"

# PVE VM configuration directory; present only when this host runs PVE.
PVE_QEMU_CONF_DIR = "/etc/pve/qemu-server"

# Subprocess timeout for the iostat -r invocation (seconds). Since-boot
# histograms print instantly — no interval window is measured.
IOSTAT_R_TIMEOUT = 10
IOSTAT_R_ARGS = ["zpool", "iostat", "-r"]

# Histogram columns of `zpool iostat -r`, in print order. The four traffic
# columns drive tuning advice; scrub/trim/rebuild are parsed for completeness.
HIST_COLUMNS = (
    "sync_read",
    "sync_write",
    "async_read",
    "async_write",
    "scrub",
    "trim",
    "rebuild",
)
HIST_KINDS = ("ind", "agg")

# Regex: ^(\d+)([KMGTPE]?)$
# Purpose: Parse one `zpool iostat -r` bucket label (the request-size class).
# Group 1: the numeric part       e.g. "512", "16"
# Group 2: the suffix             e.g. "", "K", "M" (scale 1024**n)
# Examples:
#   "512" -> ("512", "")   "1K" -> ("1", "K")   "16M" -> ("16", "M")
# Rationale: bucket labels are integer-only, unlike the count cells, which
# carry decimals and share the `zpool iostat -v` cell grammar instead.
_BUCKET_LABEL_RE = re.compile(r"^(\d+)([KMGTPE]?)$")

# Suffix scale table shared by bucket labels and zfs-get size values.
_SIZE_SUFFIXES = {"": 0, "K": 1, "M": 2, "G": 3, "T": 4, "P": 5, "E": 6}

# Regex: ^(scsi|virtio|sata|ide)(\d+):\s*(.+)$
# Purpose: Parse one PVE VM-config disk line into bus, index, and payload.
# Group 1: the bus family    e.g. "scsi", "virtio"
# Group 2: the bus index     e.g. "0"
# Group 3: the payload       e.g. "local-lvm:vm-201-disk-0,size=32G"
_PVE_DISK_LINE_RE = re.compile(r"^(scsi|virtio|sata|ide)(\d+):\s*(.+)$")

# Regex: vm-(\d+)-disk-(\d+)
# Purpose: Identify the zvol short name inside a PVE disk-line payload.
# Group 1: the VM id         e.g. "201"
# Group 2: the disk number   e.g. "0"
_VM_DISK_TOKEN_RE = re.compile(r"vm-(\d+)-disk-(\d+)")


def parse_zfs_size(text):
    """Return the byte value of a zfs-get size value ("128K", "16K", "1M").

    Returns None for "-", "", and anything unparseable. Unlike bucket
    labels, property values may carry decimals (non-power-of-two
    volblocksize on OpenZFS 2.2+: "12.0K" style rendering).
    """
    if text is None:
        return None
    text = text.strip()
    match = re.match(r"^(\d+(?:\.\d+)?)([KMGTPE]?)$", text)
    if match is None:
        return None
    return int(float(match.group(1)) * 1024 ** _SIZE_SUFFIXES[match.group(2)])


def parse_bucket_label(label):
    """Return the byte size of one histogram bucket label, or None."""
    match = _BUCKET_LABEL_RE.match(label)
    if match is None:
        return None
    return int(match.group(1)) * 1024 ** _SIZE_SUFFIXES[match.group(2)]


@dataclass
class ReqHistogram:
    """One pool's `zpool iostat -r` request-size histogram.

    ``buckets`` maps bucket size in bytes to ``{kind: {column: count}}``
    where kind is "ind" (individual, unmerged requests) or "agg" (requests
    aggregated by the IO scheduler). Counts are since-boot cumulative.
    """

    pool: str
    buckets: dict[int, dict[str, dict[str, int]]] = field(default_factory=dict)

    def add(self, bucket, kind, column, count):
        self.buckets.setdefault(bucket, {}).setdefault(kind, {})[column] = count

    def _bucket_totals(self, columns, kinds):
        """Return {bucket: operation count} over the given columns/kinds."""
        totals = {}
        for bucket, by_kind in self.buckets.items():
            total = 0
            for kind in kinds:
                counts = by_kind.get(kind, {})
                for column in columns:
                    total += counts.get(column, 0)
            totals[bucket] = total
        return totals

    def ops(self, columns, kinds=HIST_KINDS):
        """Total operation count over the given columns and kinds."""
        return sum(self._bucket_totals(columns, kinds).values())

    def dominant_bucket(self, columns, kinds=HIST_KINDS):
        """Return ``(bucket_bytes, share)`` of the ops-heaviest bucket.

        Share is the fraction of operations in the given columns/kinds that
        fall in the dominant bucket. Returns None when there is no traffic.
        """
        totals = self._bucket_totals(columns, kinds)
        total = sum(totals.values())
        if total <= 0:
            return None
        bucket = max(totals, key=lambda b: (totals[b], b))
        return bucket, totals[bucket] / total

    def top_buckets(self, columns, limit=3, kinds=HIST_KINDS):
        """Return the ops-heaviest buckets as ``(bucket, share)`` pairs."""
        totals = self._bucket_totals(columns, kinds)
        total = sum(totals.values())
        if total <= 0:
            return []
        ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
        return [(bucket, count / total) for bucket, count in ranked[:limit] if count > 0]


@dataclass
class MemberDisk:
    """One pool member leaf and its reported sector geometry."""

    path: str
    logical_sector: int | None = None
    physical_sector: int | None = None


@dataclass
class PoolAlignment:
    """One pool's device-side alignment inputs."""

    name: str
    ashift_configured: str | None = None
    ashift_effective: int | None = None
    members: list[MemberDisk] = field(default_factory=list)
    has_cache: bool = False


@dataclass
class DatasetBlocks:
    """One dataset's blocksize properties from `zfs get`.

    Values are the raw zfs-get strings; use parse_zfs_size for byte values.
    ``source`` is the zfs-get source column ("local", "inherited from ...",
    "default", "-"); None when the property does not apply to the kind.
    """

    name: str
    kind: str  # "filesystem" | "volume"
    recordsize: str | None = None
    recordsize_source: str | None = None
    volblocksize: str | None = None
    volblocksize_source: str | None = None


@dataclass
class VMOption:
    """One PVE VM disk line that references a zvol by short name."""

    vmid: str
    disknum: str
    bus: str
    options: dict[str, str] = field(default_factory=dict)


@dataclass
class AlignmentSample:
    """A single collection of all alignment-view inputs.

    The ``*_available`` flags record which sources this host exposes; the
    corresponding collections stay empty when a source is unavailable.
    """

    monotonic: float
    pools: list[PoolAlignment] = field(default_factory=list)
    datasets: list[DatasetBlocks] = field(default_factory=list)
    histograms: dict[str, ReqHistogram] = field(default_factory=dict)
    vm_disks: dict[str, VMOption] = field(default_factory=dict)
    arc: dict[str, int] = field(default_factory=dict)
    prefetch: dict[str, int] = field(default_factory=dict)
    pools_available: bool = False
    datasets_available: bool = False
    iostat_r_available: bool = False
    arcstats_available: bool = False
    prefetch_available: bool = False
    pve_available: bool = False


# ---------------------------------------------------------------------------
# zpool iostat -r parser
# ---------------------------------------------------------------------------


def parse_zpool_iostat_r(text):
    """Parse `zpool iostat -r` output into {pool: ReqHistogram}.

    Layout per pool block: a header line naming the pool and the seven
    columns; a ``req_size ind agg ...`` column-header line; a dashed
    separator; one row per bucket with 14 count cells; then a full-width
    dashed rule before the next pool. Rows are matched by structure, so
    output from any OpenZFS release that supports ``-r`` parses the same
    way. Count cells share the ``zpool iostat -v`` value grammar
    (``memory_stats._parse_iostat_cell``): base-1024 with single-letter
    suffixes.
    """
    histograms: dict[str, ReqHistogram] = {}
    pool = None
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        if all(set(token) == {"-"} for token in parts):
            # Dashed separator rows (column rule and pool boundary rule).
            continue
        if len(parts) == len(HIST_COLUMNS) + 1 and parts[1:] == list(HIST_COLUMNS):
            pool = parts[0]
            histograms.setdefault(pool, ReqHistogram(pool=pool))
            continue
        if len(parts) == len(HIST_COLUMNS) * len(HIST_KINDS) + 1:
            bucket = parse_bucket_label(parts[0])
            if pool is None or bucket is None:
                # The req_size column-header line or an unreadable row.
                continue
            cells = parts[1:]
            for column_index, column in enumerate(HIST_COLUMNS):
                for kind_index, kind in enumerate(HIST_KINDS):
                    cell_index = column_index * len(HIST_KINDS) + kind_index
                    count = _parse_iostat_cell(cells[cell_index])
                    if count is not None:
                        histograms[pool].add(bucket, kind, column, count)
    return histograms


# ---------------------------------------------------------------------------
# PVE VM-config reader
# ---------------------------------------------------------------------------


def parse_pve_vm_conf(text, vmid):
    """Parse one qemu-server config body into {short_name: VMOption}.

    Only disk lines whose payload names a zvol by its short name
    (``vm-<id>-disk-<n>``, the storage-reference form) are returned;
    by-path references used by two-node iSCSI setups cannot be mapped to
    zvols without backstore knowledge and are skipped.

    *vmid* is the config file's VM (the filename): the authoritative
    owner of every disk line in the file. It can differ from the id
    embedded in a short name when a disk created for one VM was later
    moved to another — the name keeps its origin, the config states the
    current owner — so the two are never mixed.
    """
    result: dict[str, VMOption] = {}
    for line in text.splitlines():
        match = _PVE_DISK_LINE_RE.match(line.strip())
        if match is None:
            continue
        bus_family, bus_index, payload = match.groups()
        if "media=cdrom" in payload:
            continue
        token = _VM_DISK_TOKEN_RE.search(payload)
        if token is None:
            continue
        options: dict[str, str] = {}
        for entry in payload.split(",")[1:]:
            if "=" in entry:
                key, value = entry.split("=", 1)
                options[key] = value
            elif entry:
                options[entry] = "1"
        short_name = token.group(0)
        result[short_name] = VMOption(
            vmid=str(vmid),
            disknum=token.group(2),
            bus=f"{bus_family}{bus_index}",
            options=options,
        )
    return result


def read_pve_vm_options(conf_dir=PVE_QEMU_CONF_DIR):
    """Read every qemu-server config into {short_name: VMOption}.

    Returns an empty dict when the directory is absent or unreadable (the
    storage node of a two-node install keeps VM configs on the compute
    node, not here).
    """
    vm_disks: dict[str, VMOption] = {}
    try:
        paths = sorted(glob.glob(os.path.join(conf_dir, "*.conf")))
    except OSError:
        return vm_disks
    for path in paths:
        vmid = os.path.basename(path).removesuffix(".conf")
        if not vmid.isdigit():
            continue
        try:
            with open(path) as f:
                vm_disks.update(parse_pve_vm_conf(f.read(), vmid))
        except OSError:
            continue
    return vm_disks


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------


def _topology_leaf_paths(node):
    """Yield the device paths of all disk leaves under a TopologyNode."""
    if node.vdev_type == "disk":
        yield node.name
    for child in node.children:
        yield from _topology_leaf_paths(child)


def _topology_has_cache(node):
    """Return True when any cache vdev appears in the topology tree."""
    if node.vdev_type == "cache":
        return True
    return any(_topology_has_cache(child) for child in node.children)


def _collect_pools(zfs_repo):
    """Build PoolAlignment rows: ashift plus member sector geometry."""
    pools = []
    for row in zfs_repo.list_pools_full():
        name = row["name"]
        ashift = zfs_repo.get_ashift(name)
        members = []
        has_cache = False
        topology = zfs_repo.pool_topology(name)
        if topology is not None:
            members = [MemberDisk(path=path) for path in _topology_leaf_paths(topology)]
            has_cache = _topology_has_cache(topology)
        pools.append(
            PoolAlignment(
                name=name,
                ashift_configured=ashift.configured,
                ashift_effective=ashift.effective,
                members=members,
                has_cache=has_cache,
            )
        )
    return pools


def _match_member_sectors(pools, disk_repo):
    """Fill each member's sector sizes by realpath-matching lsblk entries."""
    by_realpath = {}
    try:
        for disk in disk_repo.list_disks():
            by_realpath[os.path.realpath(disk.path)] = disk
    except (OSError, subprocess.SubprocessError):
        return
    for pool in pools:
        for member in pool.members:
            disk = by_realpath.get(os.path.realpath(member.path))
            if disk is not None:
                member.logical_sector = disk.logical_sector
                member.physical_sector = disk.physical_sector


def _dataset_blocks_from_rows(rows):
    """Group property-level DatasetBlockRow items into DatasetBlocks rows.

    Kind inference: a dataset reporting a real volblocksize is a volume;
    one reporting a real recordsize is a filesystem. ``zfs get`` renders
    non-applicable properties as ``-``, and datasets whose every property
    is ``-`` are skipped.
    """
    props = {}
    for row in rows:
        props.setdefault(row.name, {})[row.prop] = (row.value, row.source)
    datasets = []
    for name in sorted(props):
        recordsize, recordsize_source = props[name].get("recordsize", ("-", "-"))
        volblocksize, volblocksize_source = props[name].get("volblocksize", ("-", "-"))
        if volblocksize != "-":
            kind = "volume"
        elif recordsize != "-":
            kind = "filesystem"
        else:
            continue
        datasets.append(
            DatasetBlocks(
                name=name,
                kind=kind,
                recordsize=recordsize if recordsize != "-" else None,
                recordsize_source=recordsize_source if recordsize != "-" else None,
                volblocksize=volblocksize if volblocksize != "-" else None,
                volblocksize_source=volblocksize_source if volblocksize != "-" else None,
            )
        )
    return datasets


def collect_alignment_sample(
    zfs_repo=None,
    disk_repo=None,
    timeout=IOSTAT_R_TIMEOUT,
    arcstats_path=ARCSTATS_PATH,
    zfetchstats_path=ZFETCHSTATS_PATH,
    pve_conf_dir=PVE_QEMU_CONF_DIR,
):
    """Collect one AlignmentSample, degrading per-source on failure."""
    sample = AlignmentSample(monotonic=time.monotonic())
    try:
        sample.pools = _collect_pools(zfs_repo)
        _match_member_sectors(sample.pools, disk_repo)
        sample.pools_available = True
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
        pass
    try:
        for pool in sample.pools:
            sample.datasets.extend(
                _dataset_blocks_from_rows(zfs_repo.dataset_block_properties(pool.name))
            )
        if sample.pools:
            sample.datasets_available = True
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
        pass
    try:
        result = subprocess.run(
            IOSTAT_R_ARGS, capture_output=True, text=True, timeout=timeout, check=False
        )
        if result.returncode == 0:
            sample.histograms = parse_zpool_iostat_r(result.stdout)
            sample.iostat_r_available = True
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        with open(arcstats_path) as f:
            sample.arc = parse_arcstats(f.read())
        sample.arcstats_available = True
    except OSError:
        pass
    try:
        with open(zfetchstats_path) as f:
            sample.prefetch = parse_kstats(f.read())
        sample.prefetch_available = True
    except OSError:
        pass
    vm_disks = read_pve_vm_options(pve_conf_dir)
    if vm_disks:
        sample.vm_disks = vm_disks
        sample.pve_available = True
    return sample

"""Blocksize-alignment and workload statistics for the Alignment view.

Pure data layer with no GTK dependencies, mirroring memory_stats: every
source is probed independently and degrades on its own with an explanatory
flag, so the view can render per-source notes instead of failing outright.

Sources and their availability flags:

- ``zfs_repo`` (pool list, effective ashift, vdev topology, dataset block
  properties) and ``disk_repo`` (lsblk logical/physical sectors) ->
  ``pools_available`` / ``datasets_available``; dataset properties are
  collected per pool, so one pool's failed read lands in
  ``dataset_read_failures`` while the other pools keep their rows
- ``zpool iostat -r`` — per-pool request-size histograms since boot ->
  ``iostat_r_available``
- ``/proc/spl/kstat/zfs/<pool>/objset-*`` — per-dataset objset kstats
  since boot (``nread``/``nwritten``/``reads``/``writes`` plus per-dataset
  ZIL counters; each file names its dataset in ``dataset_name``) ->
  ``objset_available``; ``compute_objset_rates`` deltas two samples into
  per-dataset average request sizes
- ``/proc/spl/kstat/zfs/arcstats`` and ``.../zfetchstats`` — ARC and
  prefetcher counters (same kstat grammar memory_stats parses) ->
  ``arcstats_available`` / ``prefetch_available``
- ``/etc/pve/qemu-server/*.conf`` — PVE VM disk options: read from the
  local directory when this host runs PVE, otherwise fetched from the
  compute node over ssh on two-node installs (the same read-only channel
  the dashboard uses) -> ``pve_available``
- ``alignment_guestfs.GuestFsProber`` — guest filesystem blocksizes for
  VM volumes, asked through the QEMU guest agent on the compute node ->
  ``guest_fs`` / ``guest_fs_failures`` / ``guest_fs_probed``

The alignment view refreshes independently of the Live Charts view, so it
collects its own copy of the kstats rather than sharing the charts sample.
"""

import glob
import os
import re
import subprocess
import time
from dataclasses import dataclass, field

from alignment_guestfs import GuestFsEntry, GuestFsProber, collect_zvol_signatures
from memory_stats import (
    ARCSTATS_PATH,
    _delta_rate,
    _parse_iostat_cell,
    parse_arcstats,
    parse_kstats,
)
from node_config import load_node_config
from zfs_repository import TopologyNode

ZFETCHSTATS_PATH = "/proc/spl/kstat/zfs/zfetchstats"

# Per-dataset objset kstats root. Each pool exposes its datasets as
# <root>/<pool>/objset-0x<objsetid> (OpenZFS 2.2+); the file names its
# dataset in the dataset_name field, so no objsetid mapping is needed.
OBJSET_KSTAT_DIR = "/proc/spl/kstat/zfs"

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
class ObjsetRates:
    """Per-interval traffic rates for one dataset's objset kstats.

    ``avg_read_size`` / ``avg_write_size`` are bytes per operation over
    the interval — the workload's observed request sizes at dataset
    granularity (the pool-level counterpart of the ``-r`` histogram).
    They are None when the interval carried no operations of that kind;
    every field is None when a counter reset between the samples.
    """

    reads_ps: float | None = None
    writes_ps: float | None = None
    read_bps: float | None = None
    write_bps: float | None = None
    avg_read_size: float | None = None
    avg_write_size: float | None = None


@dataclass
class MemberDisk:
    """One pool member leaf and its reported sector geometry."""

    path: str
    logical_sector: int | None = None
    physical_sector: int | None = None


@dataclass
class PoolAlignment:
    """One pool's device-side alignment inputs.

    ``topology`` is the pool's typed vdev tree (``TopologyNode`` from
    `zpool status -P`) with the effective ashift annotated on its root —
    the same shape the Disks-page inventory carries. It is None when the
    status output is unreadable for that pool. ``members`` and
    ``has_cache`` flatten that same tree and stay meaningful for leaf /
    sector matching; they are empty/False when the tree is absent.
    """

    name: str
    ashift_configured: str | None = None
    ashift_effective: int | None = None
    topology: TopologyNode | None = None
    members: list[MemberDisk] = field(default_factory=list)
    has_cache: bool = False


@dataclass
class DatasetBlocks:
    """One dataset's blocksize properties from `zfs get`.

    Values are the raw zfs-get strings; use parse_zfs_size for byte values.
    ``source`` is the zfs-get source column ("local", "inherited from ...",
    "default", "-"); None when the property does not apply to the kind.
    ``volsize`` (volume byte size, "-" on filesystems) feeds the guest
    prober's disk matching — QEMU exposes the zvol at exactly this size.
    """

    name: str
    kind: str  # "filesystem" | "volume"
    recordsize: str | None = None
    recordsize_source: str | None = None
    volblocksize: str | None = None
    volblocksize_source: str | None = None
    volsize: str | None = None


@dataclass
class VMOption:
    """One PVE VM disk line that references a zvol by short name."""

    vmid: str
    disknum: str
    bus: str
    options: dict[str, str] = field(default_factory=dict)
    # VM-level qemu-guest-agent switch (the config's ``agent:`` line) —
    # lets guest probing say "agent disabled" instead of "unreachable".
    agent: bool = False


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
    objset: dict[str, dict[str, int]] = field(default_factory=dict)
    # Guest filesystem blocksizes per zvol short name (alignment_guestfs).
    guest_fs: dict[str, list[GuestFsEntry]] = field(default_factory=dict)
    # Per-volume probe degrades: zvol short name -> short reason string.
    guest_fs_failures: dict[str, str] = field(default_factory=dict)
    # Pool names whose per-pool dataset-property read failed while other
    # pools were collected (per-pool degrade; wholesale zfs/zpool failure
    # instead clears pools_available/datasets_available outright).
    dataset_read_failures: list[str] = field(default_factory=list)
    pools_available: bool = False
    datasets_available: bool = False
    iostat_r_available: bool = False
    arcstats_available: bool = False
    prefetch_available: bool = False
    objset_available: bool = False
    pve_available: bool = False
    guest_fs_probed: bool = False


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
# Per-dataset objset kstats
# ---------------------------------------------------------------------------


def parse_objset_kstat(text):
    """Parse one objset kstat body into ``(dataset_name, counters)``.

    The numeric rows share the standard kstat grammar
    (``memory_stats.parse_kstats``), so counters contain every field the
    running kernel exposes — the four workload counters plus the
    per-dataset ZIL rows. ``dataset_name`` is string-typed (kstat type 7)
    and therefore absent from that numeric parse; it is picked out here
    and returned as the dataset key. Returns None when the file carries
    no dataset_name row (not an objset kstat, or an unparsable read).
    """
    stats = parse_kstats(text)
    for line in text.splitlines()[2:]:
        parts = line.split()
        if len(parts) == 3 and parts[0] == "dataset_name" and parts[1] == "7":
            # ZFS dataset names cannot contain whitespace, so the third
            # column is the whole name.
            return parts[2], stats
    return None


def read_objset_kstats(kstat_dir=OBJSET_KSTAT_DIR):
    """Read every per-dataset objset kstat into ``{dataset_name: counters}``.

    Objset files live one level down, under each pool's directory; hosts
    without them (OpenZFS older than 2.2, or a non-Linux port) yield an
    empty dict and the Alignment view falls back to the survey.
    """
    result: dict[str, dict[str, int]] = {}
    try:
        paths = sorted(glob.glob(os.path.join(kstat_dir, "*", "objset-*")))
    except OSError:
        return result
    for path in paths:
        try:
            with open(path) as f:
                parsed = parse_objset_kstat(f.read())
        except OSError:
            continue
        if parsed is not None:
            name, counters = parsed
            result[name] = counters
    return result


def average_request_sizes(counters):
    """Since-boot ``(avg_read_size, avg_write_size)`` for one dataset.

    Bytes per operation directly from the cumulative counters — the
    single-sample case; interval observations come from
    ``compute_objset_rates`` instead. Either size is None when that
    direction has seen no operations.
    """
    if not counters:
        return None, None
    reads = counters.get("reads")
    writes = counters.get("writes")
    nread = counters.get("nread")
    nwritten = counters.get("nwritten")
    avg_read = nread / reads if reads and nread is not None else None
    avg_write = nwritten / writes if writes and nwritten is not None else None
    return avg_read, avg_write


def _delta_avg(bytes_prev, bytes_cur, ops_prev, ops_cur):
    """Return (Δbytes / Δops), or None on reset, missing counters, no ops."""
    if None in (bytes_prev, bytes_cur, ops_prev, ops_cur):
        return None
    if bytes_cur < bytes_prev or ops_cur < ops_prev:
        # Counter reset between the samples (re-import, module reload).
        return None
    ops = ops_cur - ops_prev
    if ops == 0:
        return None
    return (bytes_cur - bytes_prev) / ops


def compute_objset_rates(prev, cur):
    """Derive per-dataset ObjsetRates from two consecutive samples.

    Same contract as ``memory_stats.compute_rates``: the kstat counters
    are cumulative, so per-dataset rates and average request sizes need
    the previous sample's baseline. Datasets present in only one of the
    two samples (created or destroyed in between) have no valid delta
    and are skipped; no previous sample yields no rates.
    """
    rates: dict[str, ObjsetRates] = {}
    if prev is None or cur is None:
        return rates
    elapsed = cur.monotonic - prev.monotonic
    if elapsed <= 0:
        return rates
    for name, cur_counters in cur.objset.items():
        prev_counters = prev.objset.get(name)
        if prev_counters is None:
            continue
        rates[name] = ObjsetRates(
            reads_ps=_delta_rate(prev_counters.get("reads"), cur_counters.get("reads"), elapsed),
            writes_ps=_delta_rate(prev_counters.get("writes"), cur_counters.get("writes"), elapsed),
            read_bps=_delta_rate(prev_counters.get("nread"), cur_counters.get("nread"), elapsed),
            write_bps=_delta_rate(
                prev_counters.get("nwritten"), cur_counters.get("nwritten"), elapsed
            ),
            avg_read_size=_delta_avg(
                prev_counters.get("nread"),
                cur_counters.get("nread"),
                prev_counters.get("reads"),
                cur_counters.get("reads"),
            ),
            avg_write_size=_delta_avg(
                prev_counters.get("nwritten"),
                cur_counters.get("nwritten"),
                prev_counters.get("writes"),
                cur_counters.get("writes"),
            ),
        )
    return rates


# ---------------------------------------------------------------------------
# PVE VM-config reader
# ---------------------------------------------------------------------------

# Regex: ^agent:\s*(\S+)
# Purpose: Read the VM-level qemu-guest-agent switch from a config body.
# Group 1: the value   e.g. "1", "0", "enabled=1,fstrim_cloned"
_AGENT_LINE_RE = re.compile(r"^agent:\s*(\S+)")

# Timeout for the ssh fetch of the compute node's qemu-server configs.
PVE_FETCH_TIMEOUT = 15


def _agent_enabled(value):
    """Interpret an ``agent:`` config value: enabled, or not."""
    return value == "1" or value.startswith("enabled=1")


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
    current owner — so the two are never mixed. The VM-level ``agent:``
    line (qemu-guest-agent switch) is recorded per disk as ``agent`` so
    guest probing can tell "agent disabled" from "agent unreachable".
    """
    agent = False
    for line in text.splitlines():
        match = _AGENT_LINE_RE.match(line.strip())
        if match is not None:
            agent = _agent_enabled(match.group(1))
            break
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
            agent=agent,
        )
    return result


def read_pve_vm_options(conf_dir=PVE_QEMU_CONF_DIR):
    """Read the local qemu-server config dir into {short_name: VMOption}.

    Returns an empty dict when the directory is absent or unreadable —
    the storage node of a two-node install has no local configs, and the
    remote fetch (``fetch_pve_vm_options``) takes over from there.
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


def parse_pve_conf_dump(text):
    """Parse a marker-delimited config dump into {short_name: VMOption}.

    The dump format is the fetch script's: one ``== <filename>`` marker
    line before each config body (see ``fetch_pve_vm_options``). Bodies
    before any marker are ignored.
    """
    vm_disks: dict[str, VMOption] = {}
    vmid = None
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("== "):
            if vmid is not None:
                vm_disks.update(parse_pve_vm_conf("\n".join(body), vmid))
            # The marker carries the full remote path; the vmid is its
            # numeric basename.
            name = line[3:].strip().rsplit("/", 1)[-1].removesuffix(".conf")
            vmid = name if name.isdigit() else None
            body = []
        elif vmid is not None:
            body.append(line)
    if vmid is not None:
        vm_disks.update(parse_pve_vm_conf("\n".join(body), vmid))
    return vm_disks


def fetch_pve_vm_options(host, conf_dir=PVE_QEMU_CONF_DIR, runner=None):
    """Fetch the compute node's qemu-server configs over ssh.

    One ``ssh root@<host>`` round-trip cats every config with an
    ``== <filename>`` marker before each body (parsed by
    ``parse_pve_conf_dump``); BatchMode and a ConnectTimeout keep a
    missing key or an unreachable host from hanging the refresh. Returns
    an empty dict on any failure — the caller degrades per-source.
    """
    if runner is None:

        def runner(argv, timeout):
            return subprocess.run(
                argv, capture_output=True, text=True, timeout=timeout, check=False
            )

    script = f'for f in {conf_dir}/*.conf; do echo "== $f"; cat "$f"; done'
    try:
        result = runner(
            ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes", f"root@{host}", script],
            timeout=PVE_FETCH_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if result.returncode != 0:
        return {}
    return parse_pve_conf_dump(result.stdout or "")


def read_pve_vm_configs(conf_dir=PVE_QEMU_CONF_DIR, config=None):
    """Read PVE VM configs wherever they live: local dir, then the compute node.

    Single-node installs (and the GUI running on the compute node) find
    the configs locally; two-node installs fall back to the ssh fetch
    against the configured compute host. Returns ``{short_name: VMOption}``
    — empty when neither source is readable, which the caller reports
    through ``pve_available``.
    """
    vm_disks = read_pve_vm_options(conf_dir)
    if vm_disks:
        return vm_disks
    config = load_node_config() if config is None else config
    host = config.get("compute_host") or ""
    if config.get("mode") == "two-node" and host and config.get("this_host") != host:
        vm_disks = fetch_pve_vm_options(host, conf_dir=conf_dir)
    return vm_disks


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------


def topology_leaf_paths(node):
    """Yield the device paths of all disk leaves under a TopologyNode.

    Public because the analysis rules walk the same trees the sample
    flattened into ``PoolAlignment.members`` — per-vdev-group findings
    match group leaves against member sector geometry by path.
    """
    if node.vdev_type == "disk":
        yield node.name
    for child in node.children:
        yield from topology_leaf_paths(child)


def _topology_has_cache(node):
    """Return True when any cache vdev appears in the topology tree."""
    if node.vdev_type == "cache":
        return True
    return any(_topology_has_cache(child) for child in node.children)


def _collect_pools(zfs_repo):
    """Build PoolAlignment rows: typed topology plus flattened leaf data.

    Disks-page inventory pattern (python/disks_page.py): each pool's
    topology and ashift are probed independently and degrade to None on
    failure, so one unreadable pool keeps its row while the rest of the
    source stays up. When both succeed, the effective ashift is annotated
    onto the tree root so topology consumers see one typed tree.
    """
    pools = []
    for row in zfs_repo.list_pools_full():
        name = row["name"]
        try:
            topology = zfs_repo.pool_topology(name)
        except Exception:
            topology = None
        try:
            ashift = zfs_repo.get_ashift(name)
        except Exception:
            ashift = None
        members = []
        has_cache = False
        if topology is not None:
            topology.ashift = ashift.effective if ashift is not None else None
            members = [MemberDisk(path=path) for path in topology_leaf_paths(topology)]
            has_cache = _topology_has_cache(topology)
        pools.append(
            PoolAlignment(
                name=name,
                ashift_configured=ashift.configured if ashift is not None else None,
                ashift_effective=ashift.effective if ashift is not None else None,
                topology=topology,
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
        volsize, _volsize_source = props[name].get("volsize", ("-", "-"))
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
                volsize=volsize if volsize != "-" else None,
            )
        )
    return datasets


def _guest_probe_targets(datasets, vm_disks, signature_runner=None):
    """Volumes worth probing, with their match-chain evidence attached.

    Each target is ``(vmid, short, bus, volsize_bytes, serial, signatures)``
    — only zvols referenced by a PVE disk line carry a VM to ask; the
    volsize byte value is None when the property read failed; *serial* is
    the disk line's ``serial=`` option when the operator pinned one (tier-1
    match evidence); *signatures* is the storage-side UUID/PARTUUID set
    read from ``/dev/zvol/<name>`` (tier 2 — empty for blank zvols, for a
    missing /dev/zvol node, or when the read fails, all of which fall to
    the prober's size+bus tier).
    """
    volumes = []
    for ds in datasets:
        if ds.kind != "volume":
            continue
        option = vm_disks.get(ds.name.rsplit("/", 1)[-1])
        if option is not None:
            volumes.append((ds, option))
    signatures = collect_zvol_signatures(
        sorted(f"/dev/zvol/{ds.name}" for ds, _option in volumes),
        runner=signature_runner,
    )
    return [
        (
            option.vmid,
            ds.name.rsplit("/", 1)[-1],
            option.bus,
            parse_zfs_size(ds.volsize or ""),
            option.options.get("serial"),
            signatures.get(f"/dev/zvol/{ds.name}", set()),
        )
        for ds, option in volumes
    ]


def collect_alignment_sample(
    zfs_repo=None,
    disk_repo=None,
    timeout=IOSTAT_R_TIMEOUT,
    arcstats_path=ARCSTATS_PATH,
    zfetchstats_path=ZFETCHSTATS_PATH,
    pve_conf_dir=PVE_QEMU_CONF_DIR,
    kstat_dir=OBJSET_KSTAT_DIR,
    node_config_data=None,
    guest_prober=None,
):
    """Collect one AlignmentSample, degrading per-source on failure.

    *node_config_data* overrides the node-config lookup (tests); the PVE
    configs then come from the local directory or the compute node per
    that config. *guest_prober* is the alignment_guestfs.GuestFsProber
    for guest filesystem blocksizes; None (the default) builds one from
    the ambient node config, and tests inject a stub.
    """
    sample = AlignmentSample(monotonic=time.monotonic())
    try:
        sample.pools = _collect_pools(zfs_repo)
        _match_member_sectors(sample.pools, disk_repo)
        sample.pools_available = True
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
        pass
    # Dataset properties are read per pool so a transient zfs failure on
    # one pool costs only that pool's rows: surviving pools keep their
    # datasets, the failed pool is named in dataset_read_failures, and the
    # chain/dataset tables never blank wholesale.
    for pool in sample.pools:
        try:
            sample.datasets.extend(
                _dataset_blocks_from_rows(zfs_repo.dataset_block_properties(pool.name))
            )
            sample.datasets_available = True
        except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
            sample.dataset_read_failures.append(pool.name)
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
    objset = read_objset_kstats(kstat_dir)
    if objset:
        sample.objset = objset
        sample.objset_available = True
    vm_disks = read_pve_vm_configs(pve_conf_dir, config=node_config_data)
    if vm_disks:
        sample.vm_disks = vm_disks
        sample.pve_available = True
    if sample.pve_available:
        prober = GuestFsProber(config=node_config_data) if guest_prober is None else guest_prober
        results = prober.probe_volumes(_guest_probe_targets(sample.datasets, sample.vm_disks))
        for short, probe in results.items():
            if probe.entries:
                sample.guest_fs[short] = probe.entries
                sample.guest_fs_probed = True
            elif probe.reason:
                sample.guest_fs_failures[short] = probe.reason
    return sample

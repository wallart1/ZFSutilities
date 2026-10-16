"""Blocksize alignment analysis and tuning recommendations.

Pure logic, no GTK and no subprocess: consumes an AlignmentSample plus the
user's workload survey and emits Finding rows for the Alignment view. The
recommendation basis is deliberately three-sided — observed request sizes
at pool granularity (`zpool iostat -r` histograms) and at dataset
granularity (objset kstats, delta-sampled against the previous sample
when one exists), the pool's vdev topology for device-side structure,
and the user-declared workload survey — and every finding is advisory
only: ashift and volblocksize are creation-only, and recordsize changes
happen through Workload profiles on the Datasets page. No rule acts or
emits a command.

Thresholds are named module constants, a pattern borrowed from Richard
Elling's kstat-analyzer (zfs-linux-tools); the values and rules here are
this project's own.
"""

from dataclasses import dataclass, field

from alignment_stats import (
    average_request_sizes,
    compute_objset_rates,
    parse_zfs_size,
    topology_leaf_paths,
)
from disk_repository import format_blocksize

# Severity ladder for findings: OK confirms alignment, info suggests a
# look, WARN marks real misalignment (read-modify-write somewhere).
SEV_OK = "OK"
SEV_INFO = "info"
SEV_WARN = "WARN"

# Minimum since-boot operations before histogram-based advice is trusted.
OBSERVATION_MIN_OPS = 1000

# Minimum operations (reads plus writes, over the interval or since boot)
# before one dataset's average request sizes are trusted for advice. Far
# below the pool-histogram floor because the objset counters are already
# per dataset.
OBSERVATION_MIN_DATASET_OPS = 100

# Prefetcher hit rate at/above which the prefetcher counts as effective.
PREFETCH_EFFECTIVE = 0.5

# Sync share of all traffic at/above which the workload counts as
# sync-dominated (databases, VM zvols with cache=none semantics).
RANDOM_SYNC_SHARE = 0.5

# ARC demand-data hit-rate ladder (fractions, kstat-analyzer convention).
CACHE_RATIO_OK = 0.25
CACHE_RATIO_GOOD = 0.9

# Ghost hits above this share of real hits hint at working-set churn.
GHOST_RATIO_OK = 0.1

# Evictions eligible for L2 above this share hint at an L2ARC candidate.
EVICT_L2_ELIGIBLE_HINT = 0.5

# A blocksize must exceed the observed dominant request size by this factor
# before a shrink recommendation fires (avoids noise from 2x neighbours).
RMW_AMPLIFICATION_FACTOR = 4

# Histogram column groups used by the classifier and the advice rules.
TRAFFIC_COLUMNS = ("sync_read", "sync_write", "async_read", "async_write")
SYNC_COLUMNS = ("sync_read", "sync_write")

# zvol short-name shape used by new-vm-disk/attach-vm-disk.
_VM_DISK_SHAPE = "vm-"

# Vdev-class vocabulary shared by the analysis rules and the view's
# topology table.  Root-level children of a `zpool status` tree are the
# data-class vdev groups; the named classes appear as heading nodes
# (classified by name in zfs_repository).  The order matches `zpool
# status` print order.
_TOPOLOGY_CLASS_ORDER = ("data", "special", "log", "cache", "spare")
_TOPOLOGY_HEADING_TYPES = frozenset(_TOPOLOGY_CLASS_ORDER) - {"data"}


@dataclass
class Finding:
    """One advisory row for the Alignment view.

    ``layer`` names the stack level (Device / Pool / Dataset / VM /
    Memory); ``subject`` is the pool, dataset, or host the finding is
    about; ``recommendation`` is advisory text, never an action.
    ``key`` is the emitting rule's stable identity: the view reconciles
    findings rows on (key, subject) so a refresh updates a surviving
    finding in place even while its message numbers drift, instead of
    rebuilding the table.
    """

    layer: str
    subject: str
    severity: str
    message: str
    recommendation: str = ""
    key: str = ""


@dataclass
class WorkloadVerdict:
    """Classification of one pool's observed workload."""

    label: str  # "sequential" | "random-sync" | "mixed" | "insufficient" | "unknown"
    prefetch_rate: float | None = None
    sync_share: float | None = None
    confidence: str = "low"  # "high" when the prefetcher vote is available


@dataclass
class LadderBar:
    """One rung of a pool's blocksize ladder (the Alignment view visual).

    ``label`` is the full display label including the layer prefix
    (``"dataset · recordsize 128K ×3"``); ``size`` is the rung's byte
    position on the log2 axis; ``state`` is a Finding severity and maps to
    the ladder's colour vocabulary — OK aligned, WARN mismatched against
    the pool block, info advisory or unresolved.
    """

    layer: str  # "Device" | "Pool" | "Dataset" | "VM"
    label: str
    size: int
    state: str


@dataclass
class LadderPool:
    """One pool's ladder: its rungs plus the ashift reference line.

    ``block`` is the pool's effective-ashift block in bytes — the dashed
    reference line every other rung is judged against — and is None when
    the ashift probe failed (the pool keeps its other rungs, all rendered
    as info, exactly like the chain table keeps the pool row).
    """

    pool: str
    ashift: int | None = None
    block: int | None = None
    bars: list[LadderBar] = field(default_factory=list)


def _rate(hits, misses):
    """Return hits/(hits+misses), or None without traffic/counters."""
    if hits is None or misses is None:
        return None
    total = hits + misses
    if total <= 0:
        return None
    return hits / total


def classify_workload(hist, prefetch_stats=None):
    """Classify one pool's workload from its histogram and prefetcher vote.

    The prefetcher is the strongest sequential signal (a hit means the
    read-ahead was useful); sync-dominant traffic with unmerged individual
    requests is the random-sync signal (databases, VM disks). Without
    zfetchstats the verdict rests on the histogram alone and carries low
    confidence.
    """
    if hist is None:
        return WorkloadVerdict("unknown")
    total = hist.ops(TRAFFIC_COLUMNS)
    prefetch_rate = (
        _rate(prefetch_stats.get("hits"), prefetch_stats.get("misses")) if prefetch_stats else None
    )
    confidence = "high" if prefetch_rate is not None else "low"
    if total < OBSERVATION_MIN_OPS:
        return WorkloadVerdict("insufficient", prefetch_rate, None, confidence)
    sync_share = hist.ops(SYNC_COLUMNS) / total
    ind_sync = hist.ops(SYNC_COLUMNS, kinds=("ind",))
    agg_sync = hist.ops(SYNC_COLUMNS, kinds=("agg",))
    ind_total = hist.ops(TRAFFIC_COLUMNS, kinds=("ind",))
    agg_total = hist.ops(TRAFFIC_COLUMNS, kinds=("agg",))
    if prefetch_rate is not None and prefetch_rate >= PREFETCH_EFFECTIVE:
        label = "sequential"
    elif sync_share >= RANDOM_SYNC_SHARE and ind_sync > agg_sync:
        label = "random-sync"
    elif agg_total > ind_total and sync_share < RANDOM_SYNC_SHARE:
        label = "sequential"
    else:
        label = "mixed"
    return WorkloadVerdict(label, prefetch_rate, sync_share, confidence)


def _pool_block(sample, pool_name):
    """Return the pool's ashift block size in bytes, or None."""
    for pool in sample.pools:
        if pool.name == pool_name and pool.ashift_effective is not None:
            return 1 << pool.ashift_effective
    return None


def _datasets_of(sample, pool_name, kind):
    return [
        ds for ds in sample.datasets if ds.name.split("/", 1)[0] == pool_name and ds.kind == kind
    ]


def _size(ds, attr):
    """Parsed byte size of a dataset property, or None."""
    return parse_zfs_size(getattr(ds, attr) or "")


def _at_least(datasets, attr, floor):
    """Datasets whose parsed property size exists and is >= *floor*."""
    result = []
    for ds in datasets:
        size = _size(ds, attr)
        if size is not None and size >= floor:
            result.append(ds)
    return result


def _below(datasets, attr, ceiling):
    """Datasets whose parsed property size exists and is < *ceiling*."""
    result = []
    for ds in datasets:
        size = _size(ds, attr)
        if size is not None and size < ceiling:
            result.append(ds)
    return result


def vdev_groups(root):
    """Yield ``(class_label, group_node)`` for a topology tree, in order.

    Root-level children of the `zpool status` tree are the data-class
    groups (mirror/raidz/stripe/disk); the named classes hang off class
    heading nodes, whose children are the groups.  Emission order is
    fixed — class order above, then tree order within each class — so
    both the rules here and the view's topology table (which renders
    through the same helper) see a deterministic sequence.
    """
    groups = {label: [] for label in _TOPOLOGY_CLASS_ORDER}
    for child in root.children:
        if child.vdev_type in _TOPOLOGY_HEADING_TYPES:
            groups[child.vdev_type].extend(child.children)
        else:
            groups["data"].append(child)
    for label in _TOPOLOGY_CLASS_ORDER:
        for group in groups[label]:
            yield label, group


def _group_geometry_findings(pool):
    """Per-vdev-group mixed-geometry findings (rule 1, topology half).

    With the pool's vdev tree available, "members disagree on physical
    sector size" is judged per redundancy group — the unit that matters
    operationally, because a replacement disk is picked for one group.
    Mixing across groups (4K data mirror beside a 512-native cache SSD)
    is benign and stays silent as long as the ashift covers the maximum,
    which the pool-wide rule above already judges.
    """
    findings = []
    sectors_by_path = {member.path: member.physical_sector for member in pool.members}
    for class_label, group in vdev_groups(pool.topology):
        members = {
            path.rsplit("/", 1)[-1]: sector
            for path in topology_leaf_paths(group)
            if (sector := sectors_by_path.get(path)) is not None
        }
        distinct = sorted(set(members.values()))
        if len(distinct) < 2:
            continue
        listing = ", ".join(
            f"{name} {format_blocksize(sector)}" for name, sector in members.items()
        )
        findings.append(
            Finding(
                "Pool",
                f"{pool.name} {group.name}",
                SEV_INFO,
                f"{class_label} vdev {group.name} mixes member geometry: physical sectors span "
                f"{format_blocksize(distinct[0])}–{format_blocksize(distinct[-1])} ({listing})",
                "replacement disks for this group should match at least its largest member "
                "sector, so every write stays a single device block",
                key="pool-group-mixed-geometry",
            )
        )
    return findings


def _pool_device_findings(sample):
    """Device-to-pool alignment findings (rule 1)."""
    findings = []
    for pool in sample.pools:
        block = None if pool.ashift_effective is None else 1 << pool.ashift_effective
        sectors = [m.physical_sector for m in pool.members if m.physical_sector]
        unknown = sum(1 for m in pool.members if m.physical_sector is None)
        unknown_note = f" ({unknown} members without sector data)" if unknown else ""
        if block is None:
            configured = (
                pool.ashift_configured if pool.ashift_configured not in (None, "") else "unknown"
            )
            findings.append(
                Finding(
                    "Pool",
                    pool.name,
                    SEV_INFO,
                    f"effective ashift unavailable (configured: {configured}){unknown_note}",
                    "the pool's ashift could not be resolved; alignment not assessed",
                    key="pool-ashift-unresolved",
                )
            )
            continue
        if not sectors:
            findings.append(
                Finding(
                    "Pool",
                    pool.name,
                    SEV_INFO,
                    f"member sector geometry unavailable (ashift {pool.ashift_effective}, "
                    f"{format_blocksize(block)} blocks){unknown_note}",
                    "device-side alignment not assessed",
                    key="pool-sectors-unavailable",
                )
            )
            continue
        max_sector = max(sectors)
        if block < max_sector:
            hot = [m.path for m in pool.members if m.physical_sector == max_sector]
            hot_list = ", ".join(hot[:4]) + ("…" if len(hot) > 4 else "")
            findings.append(
                Finding(
                    "Pool",
                    pool.name,
                    SEV_WARN,
                    f"ashift {pool.ashift_effective} ({format_blocksize(block)}) is below the "
                    f"{format_blocksize(max_sector)} physical sector of: {hot_list}{unknown_note}",
                    "every device block write becomes read-modify-write; ashift is "
                    "creation-only — plan a Migrate Pool window with a blocksize of at "
                    "least the physical sector",
                    key="pool-ashift-below-sector",
                )
            )
        else:
            findings.append(
                Finding(
                    "Pool",
                    pool.name,
                    SEV_OK,
                    f"ashift {pool.ashift_effective} ({format_blocksize(block)}) covers the largest "
                    f"member physical sector ({format_blocksize(max_sector)}){unknown_note}",
                    key="pool-ashift-covers",
                )
            )
        if pool.topology is not None:
            # Topology-aware: judge mixing per vdev group (see
            # _group_geometry_findings); cross-group mixing is benign.
            findings.extend(_group_geometry_findings(pool))
        elif max(sectors) != min(sectors):
            findings.append(
                Finding(
                    "Pool",
                    pool.name,
                    SEV_INFO,
                    f"mixed member geometry: physical sectors range "
                    f"{format_blocksize(min(sectors))}–{format_blocksize(max(sectors))}",
                    "future zvols and migrations should assume the largest sector "
                    "(vdev tree unavailable, so the groups are not judged individually)",
                    key="pool-mixed-geometry",
                )
            )
    return findings


def _dataset_findings(sample, survey, profiles):
    """Dataset-level alignment findings (rules 2-3, survey half)."""
    findings = []
    for ds in sample.datasets:
        block = _pool_block(sample, ds.name.split("/", 1)[0])
        if ds.kind == "filesystem" and ds.recordsize:
            size = parse_zfs_size(ds.recordsize)
            if size is not None and block is not None and size < block:
                findings.append(
                    Finding(
                        "Dataset",
                        ds.name,
                        SEV_WARN,
                        f"recordsize {ds.recordsize} is below the pool's ashift block "
                        f"({format_blocksize(block)})",
                        "every record is padded to the ashift block, wasting space; raise "
                        "recordsize to at least the ashift block",
                        key="dataset-recordsize-below-ashift",
                    )
                )
            profile_name = (survey or {}).get(ds.name)
            profile = (profiles or {}).get(profile_name) if profile_name else None
            expected = None
            if profile and ds.kind in profile.get("applies_to", ["filesystem", "volume"]):
                expected = profile.get("properties", {}).get("recordsize")
            if expected and ds.recordsize and expected != ds.recordsize:
                findings.append(
                    Finding(
                        "Dataset",
                        ds.name,
                        SEV_INFO,
                        f"survey declares workload profile {profile_name!r} "
                        f"(recordsize {expected}) but effective recordsize is "
                        f"{ds.recordsize} ({ds.recordsize_source or 'unknown source'})",
                        "apply the profile from the Datasets page, or update the survey",
                        key="dataset-survey-mismatch",
                    )
                )
        if ds.kind == "volume" and ds.volblocksize:
            size = parse_zfs_size(ds.volblocksize)
            if size is not None and block is not None and size < block:
                findings.append(
                    Finding(
                        "Dataset",
                        ds.name,
                        SEV_WARN,
                        f"volblocksize {ds.volblocksize} is below the pool's ashift block "
                        f"({format_blocksize(block)})",
                        "ZFS pads every volblock to the ashift block; volblocksize is fixed "
                        "at zvol creation",
                        key="dataset-volblocksize-below-ashift",
                    )
                )
    return findings


def _observation_findings(sample):
    """Histogram-driven tuning advice (rules 2-3, pool-level observation half).

    The histogram is per pool, so the dataset-naming findings here name
    whole pools.  When the per-dataset objset counters are available they
    take over dataset granularity (see ``_dataset_observation_findings``)
    and these pool-subject findings stand down — the two would otherwise
    say the same thing twice, once precisely and once bluntly.
    """
    findings = []
    if not sample.iostat_r_available:
        findings.append(
            Finding(
                "Pool",
                "(all)",
                SEV_INFO,
                "request-size histograms unavailable (`zpool iostat -r` failed or "
                "unsupported on this host)",
                "observation-based advice is suspended; survey answers still apply",
                key="histograms-unavailable",
            )
        )
        return findings
    per_dataset = sample.objset_available
    for pool_name, hist in sample.histograms.items():
        verdict = classify_workload(hist, sample.prefetch if sample.prefetch_available else None)
        confidence = "" if verdict.confidence == "high" else " (histogram-only, low confidence)"
        filesystems = _datasets_of(sample, pool_name, "filesystem")
        volumes = _datasets_of(sample, pool_name, "volume")
        if verdict.label == "insufficient":
            findings.append(
                Finding(
                    "Pool",
                    pool_name,
                    SEV_INFO,
                    f"insufficient observed traffic since boot "
                    f"({hist.ops(TRAFFIC_COLUMNS):,} ops below the "
                    f"{OBSERVATION_MIN_OPS:,}-op floor)",
                    "observation-based advice is suspended until traffic accumulates",
                    key="obs-insufficient-traffic",
                )
            )
            continue
        if verdict.label == "random-sync" and not per_dataset:
            dominant = hist.dominant_bucket(SYNC_COLUMNS)
            if dominant is not None:
                bucket, share = dominant
                shrink = _at_least(filesystems, "recordsize", RMW_AMPLIFICATION_FACTOR * bucket)
                if shrink:
                    names = ", ".join(ds.name for ds in shrink[:3])
                    more = f" +{len(shrink) - 3} more" if len(shrink) > 3 else ""
                    findings.append(
                        Finding(
                            "Dataset",
                            pool_name,
                            SEV_INFO,
                            f"sync traffic is dominated by {format_blocksize(bucket)} requests "
                            f"({share:.0%} of sync ops){confidence}; recordsize on {names}{more} "
                            f"is ≥{RMW_AMPLIFICATION_FACTOR}× that size",
                            "smaller recordsize (or a matching workload profile) reduces "
                            "read-modify-write amplification on random-sync workloads",
                            key="obs-rmw-recordsize",
                        )
                    )
                hot_vols = _at_least(volumes, "volblocksize", RMW_AMPLIFICATION_FACTOR * bucket)
                if hot_vols:
                    findings.append(
                        Finding(
                            "VM",
                            pool_name,
                            SEV_INFO,
                            f"sync traffic is dominated by {format_blocksize(bucket)} requests "
                            f"({share:.0%} of sync ops){confidence}; "
                            f"{len(hot_vols)} zvol(s) use volblocksize "
                            f"{hot_vols[0].volblocksize}",
                            "guest writes smaller than the volblock cause partial-block "
                            "sync writes; volblocksize is fixed at creation — consider the "
                            "observed size for future zvols",
                            key="obs-rmw-volblocksize",
                        )
                    )
        elif verdict.label == "sequential" and not per_dataset:
            dominant = hist.dominant_bucket(TRAFFIC_COLUMNS)
            if dominant is not None:
                bucket, share = dominant
                grow = _below(filesystems, "recordsize", bucket)
                if grow:
                    findings.append(
                        Finding(
                            "Dataset",
                            pool_name,
                            SEV_INFO,
                            f"sequential traffic aggregates into {format_blocksize(bucket)} requests "
                            f"({share:.0%} of ops){confidence}; recordsize on "
                            f"{len(grow)} dataset(s) is smaller",
                            "a larger recordsize improves sequential throughput and "
                            "compression ratio",
                            key="obs-sequential-recordsize",
                        )
                    )
    return findings


def _fmt_observed(size):
    """Render an observed average request size; None for no traffic."""
    return None if size is None else format_blocksize(round(size))


def _observed_request_sizes(sample, prev_sample):
    """Per-dataset observed average request sizes: ``{name: observation}``.

    Each observation is ``(basis, avg_read_size, avg_write_size)`` where
    basis is the human-facing provenance sentence ("since boot" or "over
    the last refresh interval"). The interval basis — Δbytes/Δops from
    ``compute_objset_rates`` against the previous sample — is preferred
    when the window carried enough operations, because it reflects the
    workload as it runs now; otherwise the since-boot cumulative average
    (``average_request_sizes``) stands in, matching the rest of the
    view's since-boot vocabulary. Either size is None when that
    direction saw no traffic on the chosen basis.
    """
    if not sample.objset_available:
        return {}
    rates = compute_objset_rates(prev_sample, sample) if prev_sample is not None else {}
    observed = {}
    for name, counters in sample.objset.items():
        reads, writes = counters.get("reads"), counters.get("writes")
        if reads is None or writes is None:
            continue
        interval = rates.get(name)
        prev_counters = prev_sample.objset.get(name) if prev_sample is not None else None
        if interval is not None and prev_counters is not None:
            prev_ops = (prev_counters.get("reads") or 0) + (prev_counters.get("writes") or 0)
            if reads + writes - prev_ops >= OBSERVATION_MIN_DATASET_OPS and (
                interval.avg_read_size is not None or interval.avg_write_size is not None
            ):
                observed[name] = (
                    "over the last refresh interval",
                    interval.avg_read_size,
                    interval.avg_write_size,
                )
                continue
        if reads + writes < OBSERVATION_MIN_DATASET_OPS:
            continue
        avg_read, avg_write = average_request_sizes(counters)
        if avg_read is not None or avg_write is not None:
            observed[name] = ("since boot", avg_read, avg_write)
    return observed


def _dataset_observation_findings(sample, prev_sample, survey):
    """Per-dataset observed-size advice (rules 2-3, dataset observation half).

    The objset kstats attribute every read and write to one dataset, so
    these findings name datasets — the refinement the per-pool histogram
    cannot deliver. When the counters are missing entirely (OpenZFS
    older than 2.2, or a non-Linux port) one info finding states the
    limit instead: observed-size advice then stays per-pool, and the
    survey answers remain the only per-dataset basis. Advisory only, as
    everywhere here: recommendations point at Workload profiles and
    future creations, never at an action to run.
    """
    findings = []
    observed = _observed_request_sizes(sample, prev_sample)
    if not sample.objset_available:
        if sample.iostat_r_available:
            findings.append(
                Finding(
                    "Dataset",
                    "(all)",
                    SEV_INFO,
                    "per-dataset request sizes unavailable (objset kstats need OpenZFS 2.2+ "
                    "on Linux); observed-size advice falls back to the per-pool histogram",
                    "histogram advice then names pools, not datasets; survey answers remain "
                    "the per-dataset basis",
                    key="objset-unavailable",
                )
            )
        return findings
    for ds in sample.datasets:
        observation = observed.get(ds.name)
        if observation is None:
            continue
        basis, avg_read, avg_write = observation
        declared = (survey or {}).get(ds.name)
        if ds.kind == "filesystem" and ds.recordsize:
            size = parse_zfs_size(ds.recordsize)
            if (
                size is not None
                and avg_write is not None
                and size >= (RMW_AMPLIFICATION_FACTOR * avg_write)
            ):
                survey_note = f" (survey declares {declared!r})" if declared else ""
                stale = " the survey answer for this dataset may be stale" if declared else ""
                findings.append(
                    Finding(
                        "Dataset",
                        ds.name,
                        SEV_INFO,
                        f"observed writes to {ds.name} average "
                        f"{_fmt_observed(avg_write)} ({basis}) while recordsize is "
                        f"{ds.recordsize} — at least {RMW_AMPLIFICATION_FACTOR}× the observed "
                        f"size{survey_note}",
                        "a smaller recordsize — or a workload profile matching the observed "
                        "size — reduces read-modify-write amplification" + stale,
                        key="obs-dataset-recordsize-rmw",
                    )
                )
            if size is not None and avg_read is not None and avg_read > size:
                findings.append(
                    Finding(
                        "Dataset",
                        ds.name,
                        SEV_INFO,
                        f"observed reads from {ds.name} average {_fmt_observed(avg_read)} "
                        f"({basis}), above its recordsize {ds.recordsize} — every read spans "
                        "several records",
                        "a larger recordsize (or a sequential workload profile) raises read "
                        "throughput and compression on datasets read in big chunks",
                        key="obs-dataset-recordsize-grow",
                    )
                )
        if ds.kind == "volume" and ds.volblocksize:
            size = parse_zfs_size(ds.volblocksize)
            if (
                size is not None
                and avg_write is not None
                and size >= (RMW_AMPLIFICATION_FACTOR * avg_write)
            ):
                findings.append(
                    Finding(
                        "VM",
                        ds.name,
                        SEV_INFO,
                        f"guest writes to {ds.name.rsplit('/', 1)[-1]} average "
                        f"{_fmt_observed(avg_write)} ({basis}) while volblocksize is "
                        f"{ds.volblocksize}",
                        "sub-volblock writes cost partial-block work; volblocksize is fixed "
                        "at creation — size future zvols from the observed request size",
                        key="obs-dataset-volblocksize-rmw",
                    )
                )
    return findings


def _vm_findings(sample):
    """VM-layer findings (rule 4)."""
    findings = []
    if not sample.pve_available:
        if any(
            ds.kind == "volume" and _VM_DISK_SHAPE in ds.name.rsplit("/", 1)[-1]
            for ds in sample.datasets
        ):
            findings.append(
                Finding(
                    "VM",
                    "(all)",
                    SEV_INFO,
                    "PVE VM configs are not readable on this host (two-node installs keep "
                    "them on the compute node)",
                    "guest-visible sector and disk-option checks are suspended",
                    key="pve-configs-unreadable",
                )
            )
        return findings
    for ds in sample.datasets:
        if ds.kind != "volume":
            continue
        short = ds.name.rsplit("/", 1)[-1]
        if _VM_DISK_SHAPE not in short:
            continue
        option = sample.vm_disks.get(short)
        if option is None:
            continue
        if "discard" not in option.options:
            findings.append(
                Finding(
                    "VM",
                    ds.name,
                    SEV_INFO,
                    f"VM disk line {option.bus} carries no discard= option",
                    "guest TRIM cannot reach the zvol; space is never reclaimed",
                    key="vm-discard-missing",
                )
            )
        secs = option.options.get("secs")
        volblock = parse_zfs_size(ds.volblocksize or "")
        if secs is None and volblock is not None and volblock > 4096:
            findings.append(
                Finding(
                    "VM",
                    ds.name,
                    SEV_INFO,
                    f"guest sees 512-byte sectors (no secs= on {option.bus}) while the zvol "
                    f"uses {format_blocksize(volblock)} volblocks",
                    "a 4K-aligned guest filesystem divides evenly, but sub-volblock random "
                    "writes still pay partial-block cost; secs=4096 makes the guest "
                    "geometry explicit",
                    key="vm-guest-sectors-implicit",
                )
            )
    return findings


def _memory_findings(sample):
    """Memory-tier advisories (rule 6), kstat-analyzer-inspired."""
    findings = []
    if not sample.arcstats_available:
        return findings
    arc = sample.arc
    demand_rate = _rate(arc.get("demand_data_hits"), arc.get("demand_data_misses"))
    if demand_rate is not None:
        if demand_rate < CACHE_RATIO_OK:
            findings.append(
                Finding(
                    "Memory",
                    "(host)",
                    SEV_INFO,
                    f"ARC demand-data hit rate is low ({demand_rate:.1%})",
                    "the working set may exceed the ARC; compare size and target on the "
                    "Live Charts view",
                    key="arc-demand-low",
                )
            )
        elif demand_rate >= CACHE_RATIO_GOOD:
            findings.append(
                Finding(
                    "Memory",
                    "(host)",
                    SEV_OK,
                    f"ARC demand-data hit rate {demand_rate:.1%}",
                    key="arc-demand-good",
                )
            )
    real_hits = None
    if arc.get("mru_hits") is not None and arc.get("mfu_hits") is not None:
        real_hits = arc.get("mru_hits", 0) + arc.get("mfu_hits", 0)
        ghosts = (arc.get("mru_ghost_hits") or 0) + (arc.get("mfu_ghost_hits") or 0)
        if real_hits > 0 and ghosts > GHOST_RATIO_OK * real_hits:
            findings.append(
                Finding(
                    "Memory",
                    "(host)",
                    SEV_INFO,
                    f"ghost hits are {ghosts / real_hits:.0%} of real hits "
                    f"(above the {GHOST_RATIO_OK:.0%} floor)",
                    "recently-evicted blocks are being re-requested — working-set churn; "
                    "more RAM or a larger ARC target would help",
                    key="arc-ghost-churn",
                )
            )
    evict_total = sum(
        arc.get(key) or 0 for key in ("evict_l2_cached", "evict_l2_ineligible", "evict_l2_eligible")
    )
    eligible = arc.get("evict_l2_eligible") or 0
    has_l2arc = any(pool.has_cache for pool in sample.pools)
    if evict_total > 0 and eligible / evict_total > EVICT_L2_ELIGIBLE_HINT:
        context = (
            "cache vdevs already exist — check the L2ARC hit rate on the Live Charts view"
            if has_l2arc
            else "no pool has cache vdevs — an L2ARC candidate"
        )
        findings.append(
            Finding(
                "Memory",
                "(host)",
                SEV_INFO,
                f"{eligible / evict_total:.0%} of ARC evictions were eligible for L2ARC",
                context,
                key="arc-evict-l2-eligible",
            )
        )
    return findings


def _prefetch_finding(sample, verdicts):
    """One host-level prefetcher advisory, framed by the pool verdicts."""
    if not sample.prefetch_available:
        return []
    rate = _rate(sample.prefetch.get("hits"), sample.prefetch.get("misses"))
    if rate is None or rate >= PREFETCH_EFFECTIVE:
        return []
    any_sequential = any(v.label == "sequential" for v in verdicts)
    message = f"prefetcher hit rate is {rate:.1%} (below the {PREFETCH_EFFECTIVE:.0%} floor)"
    if any_sequential:
        return [
            Finding(
                "Memory",
                "(host)",
                SEV_INFO,
                message + " despite sequential traffic",
                "read-ahead is being discarded; prefetch strategy may merit review",
                key="prefetch-ineffective-sequential",
            )
        ]
    return [
        Finding(
            "Memory",
            "(host)",
            SEV_INFO,
            message,
            "expected for random workloads; no action required",
            key="prefetch-ineffective-random",
        )
    ]


def analyse(sample, survey=None, profiles=None, prev_sample=None):
    """Return every Finding for the Alignment view, grouped by layer.

    *prev_sample* is the previous refresh's sample; the per-dataset
    observed sizes prefer the interval between it and *sample* over the
    since-boot cumulative averages. It may be None (first refresh).
    """
    verdicts = [
        classify_workload(hist, sample.prefetch if sample.prefetch_available else None)
        for hist in sample.histograms.values()
    ]
    findings = []
    if not sample.pools_available:
        findings.append(
            Finding(
                "Pool",
                "(all)",
                SEV_INFO,
                "pool and device data unavailable (zfs/zpool commands failed)",
                "alignment-chain findings are suspended",
                key="pools-unavailable",
            )
        )
    for pool_name in sample.dataset_read_failures:
        # Per-pool degrade (alignment_stats): the pool keeps its chain rows,
        # but its dataset/VM layers could not be read this refresh.
        findings.append(
            Finding(
                "Dataset",
                pool_name,
                SEV_INFO,
                "dataset block properties unreadable for this pool "
                "(the zfs read failed; other pools are unaffected)",
                "dataset and VM findings are suspended for this pool until the read succeeds again",
                key="datasets-unreadable",
            )
        )
    findings.extend(_pool_device_findings(sample))
    findings.extend(_dataset_findings(sample, survey, profiles))
    findings.extend(_observation_findings(sample))
    findings.extend(_dataset_observation_findings(sample, prev_sample, survey))
    findings.extend(_vm_findings(sample))
    findings.extend(_memory_findings(sample))
    findings.extend(_prefetch_finding(sample, verdicts))
    return findings


def _rung_label(layer, prop, size, count):
    """Ladder rung label: layer prefix, property, size, and group count."""
    label = f"{layer.lower()} · {prop} {format_blocksize(size)}"
    return f"{label} ×{count}" if count > 1 else label


def _guest_sector(option):
    """Guest-visible sector size of one PVE disk line (secs= or 512)."""
    secs = option.options.get("secs")
    return int(secs) if secs and secs.isdigit() else 512


def blocksize_ladder(sample):
    """Build the per-pool blocksize ladder for the Alignment view visual.

    One LadderPool per pool carrying the rungs the chart draws, in stack
    order: device physical sectors (grouped by size), the pool's ashift
    block, dataset recordsize/volblocksize groups, and VM guest sectors.
    Sources degrade exactly like the tables beside the chart: members
    without sector data lose their device rungs, a pool whose ashift is
    unresolved loses the reference rung (and its other rungs render as
    info), a pool's dataset rungs drop with its per-pool dataset read,
    and VM rungs appear only for zvols referenced in local PVE configs.
    Rung states follow the analysis rules: WARN below the ashift block
    (padded) or — for device rungs — above it (read-modify-write), info
    when the verdict rests on a smaller neighbour (guest sector below
    its zvol's volblocksize) or cannot be judged.
    """
    ladders = []
    for pool in sample.pools:
        block = None if pool.ashift_effective is None else 1 << pool.ashift_effective
        bars = []
        sectors: dict[int, int] = {}
        for member in pool.members:
            if member.physical_sector:
                sectors[member.physical_sector] = sectors.get(member.physical_sector, 0) + 1
        for sector, count in sorted(sectors.items()):
            state = SEV_INFO if block is None else (SEV_WARN if block < sector else SEV_OK)
            bars.append(
                LadderBar(
                    "Device", _rung_label("Device", "physical sector", sector, count), sector, state
                )
            )
        if block is not None:
            if sectors:
                state = SEV_WARN if max(sectors) > block else SEV_OK
            else:
                state = SEV_INFO  # no sector data to judge the block against
            bars.append(
                LadderBar(
                    "Pool",
                    f"pool · ashift {pool.ashift_effective} · {format_blocksize(block)} block",
                    block,
                    state,
                )
            )
        blocks: dict[tuple[str, int], int] = {}
        for ds in sample.datasets:
            if ds.name.split("/", 1)[0] != pool.name:
                continue
            prop, raw = (
                ("recordsize", ds.recordsize)
                if ds.kind == "filesystem"
                else ("volblocksize", ds.volblocksize)
            )
            size = parse_zfs_size(raw or "")
            if size:
                blocks[(prop, size)] = blocks.get((prop, size), 0) + 1
        for (prop, size), count in sorted(blocks.items(), key=lambda item: item[0][1]):
            state = SEV_INFO if block is None else (SEV_WARN if size < block else SEV_OK)
            bars.append(
                LadderBar("Dataset", _rung_label("Dataset", prop, size, count), size, state)
            )
        guests: dict[int, list] = {}
        for ds in sample.datasets:
            if ds.name.split("/", 1)[0] != pool.name or ds.kind != "volume":
                continue
            option = sample.vm_disks.get(ds.name.rsplit("/", 1)[-1])
            if option is None:
                continue
            sector = _guest_sector(option)
            volblock = parse_zfs_size(ds.volblocksize or "")
            entry = guests.setdefault(sector, [0, False])
            entry[0] += 1
            entry[1] = entry[1] or (volblock is not None and sector < volblock)
        for sector, (count, below_volblock) in sorted(guests.items()):
            state = SEV_INFO if below_volblock else SEV_OK
            bars.append(
                LadderBar("VM", _rung_label("VM", "guest sector", sector, count), sector, state)
            )
        ladders.append(
            LadderPool(pool=pool.name, ashift=pool.ashift_effective, block=block, bars=bars)
        )
    return ladders


def arc_readouts(arc, has_l2arc):
    """Return the Memory-tier observation values as {label: value-or-None}.

    Values are fractions (0-1) except "Average L2 hit size" (bytes). The
    GUI renders absent values as "—".
    """
    readouts = {
        "Demand data hit rate": _rate(arc.get("demand_data_hits"), arc.get("demand_data_misses")),
        "Demand metadata hit rate": _rate(
            arc.get("demand_metadata_hits"), arc.get("demand_metadata_misses")
        ),
        "Prefetch data hit rate": _rate(
            arc.get("prefetch_data_hits"), arc.get("prefetch_data_misses")
        ),
    }
    if arc.get("mru_hits") is not None and arc.get("mfu_hits") is not None:
        real = arc.get("mru_hits", 0) + arc.get("mfu_hits", 0)
        ghosts = (arc.get("mru_ghost_hits") or 0) + (arc.get("mfu_ghost_hits") or 0)
        readouts["Ghost hits (share of real)"] = ghosts / real if real > 0 else None
    else:
        readouts["Ghost hits (share of real)"] = None
    evict_total = sum(
        arc.get(key) or 0 for key in ("evict_l2_cached", "evict_l2_ineligible", "evict_l2_eligible")
    )
    readouts["Evictions eligible for L2ARC"] = (
        (arc.get("evict_l2_eligible") or 0) / evict_total if evict_total > 0 else None
    )
    l2_hits = arc.get("l2_hits") or 0
    l2_read = arc.get("l2_read_bytes")
    readouts["Average L2 hit size"] = (
        l2_read / l2_hits if has_l2arc and l2_hits > 0 and l2_read else None
    )
    return readouts

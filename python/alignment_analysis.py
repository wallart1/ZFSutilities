"""Blocksize alignment analysis and tuning recommendations.

Pure logic, no GTK and no subprocess: consumes an AlignmentSample plus the
user's workload survey and emits Finding rows for the Alignment view. The
recommendation basis is deliberately two-sided — observed request-size
histograms and ARC/prefetcher counters on one side, the user-declared
workload survey on the other — and every finding is advisory only: ashift
and volblocksize are creation-only, and recordsize changes happen through
Workload profiles on the Datasets page.

Thresholds are named module constants, a pattern borrowed from Richard
Elling's kstat-analyzer (zfs-linux-tools); the values and rules here are
this project's own.
"""

from dataclasses import dataclass

from alignment_stats import parse_zfs_size

# Severity ladder for findings: OK confirms alignment, info suggests a
# look, WARN marks real misalignment (read-modify-write somewhere).
SEV_OK = "OK"
SEV_INFO = "info"
SEV_WARN = "WARN"

# Minimum since-boot operations before histogram-based advice is trusted.
OBSERVATION_MIN_OPS = 1000

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


@dataclass
class Finding:
    """One advisory row for the Alignment view.

    ``layer`` names the stack level (Device / Pool / Dataset / VM /
    Memory); ``subject`` is the pool, dataset, or host the finding is
    about; ``recommendation`` is advisory text, never an action.
    """

    layer: str
    subject: str
    severity: str
    message: str
    recommendation: str = ""


@dataclass
class WorkloadVerdict:
    """Classification of one pool's observed workload."""

    label: str  # "sequential" | "random-sync" | "mixed" | "insufficient" | "unknown"
    prefetch_rate: float | None = None
    sync_share: float | None = None
    confidence: str = "low"  # "high" when the prefetcher vote is available


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


def _fmt_bytes(size):
    """Render a byte count with binary suffixes, zfs-get style."""
    for suffix, scale in (("M", 1024**2), ("K", 1024)):
        if size >= scale and size % scale == 0:
            return f"{size // scale}{suffix}"
    return str(size)


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
                    f"{_fmt_bytes(block)} blocks){unknown_note}",
                    "device-side alignment not assessed",
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
                    f"ashift {pool.ashift_effective} ({_fmt_bytes(block)}) is below the "
                    f"{_fmt_bytes(max_sector)} physical sector of: {hot_list}{unknown_note}",
                    "every device block write becomes read-modify-write; ashift is "
                    "creation-only — plan a Migrate Pool window with a blocksize of at "
                    "least the physical sector",
                )
            )
        else:
            findings.append(
                Finding(
                    "Pool",
                    pool.name,
                    SEV_OK,
                    f"ashift {pool.ashift_effective} ({_fmt_bytes(block)}) covers the largest "
                    f"member physical sector ({_fmt_bytes(max_sector)}){unknown_note}",
                )
            )
        if max(sectors) != min(sectors):
            findings.append(
                Finding(
                    "Pool",
                    pool.name,
                    SEV_INFO,
                    f"mixed member geometry: physical sectors range "
                    f"{_fmt_bytes(min(sectors))}–{_fmt_bytes(max_sector)}",
                    "future zvols and migrations should assume the largest sector",
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
                        f"({_fmt_bytes(block)})",
                        "every record is padded to the ashift block, wasting space; raise "
                        "recordsize to at least the ashift block",
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
                        f"({_fmt_bytes(block)})",
                        "ZFS pads every volblock to the ashift block; volblocksize is fixed "
                        "at zvol creation",
                    )
                )
    return findings


def _observation_findings(sample):
    """Histogram-driven tuning advice (rules 2-3, observation half)."""
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
            )
        )
        return findings
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
                )
            )
            continue
        if verdict.label == "random-sync":
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
                            f"sync traffic is dominated by {_fmt_bytes(bucket)} requests "
                            f"({share:.0%} of sync ops){confidence}; recordsize on {names}{more} "
                            f"is ≥{RMW_AMPLIFICATION_FACTOR}× that size",
                            "smaller recordsize (or a matching workload profile) reduces "
                            "read-modify-write amplification on random-sync workloads",
                        )
                    )
                hot_vols = _at_least(volumes, "volblocksize", RMW_AMPLIFICATION_FACTOR * bucket)
                if hot_vols:
                    findings.append(
                        Finding(
                            "VM",
                            pool_name,
                            SEV_INFO,
                            f"sync traffic is dominated by {_fmt_bytes(bucket)} requests "
                            f"({share:.0%} of sync ops){confidence}; "
                            f"{len(hot_vols)} zvol(s) use volblocksize "
                            f"{hot_vols[0].volblocksize}",
                            "guest writes smaller than the volblock cause partial-block "
                            "sync writes; volblocksize is fixed at creation — consider the "
                            "observed size for future zvols",
                        )
                    )
        elif verdict.label == "sequential":
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
                            f"sequential traffic aggregates into {_fmt_bytes(bucket)} requests "
                            f"({share:.0%} of ops){confidence}; recordsize on "
                            f"{len(grow)} dataset(s) is smaller",
                            "a larger recordsize improves sequential throughput and "
                            "compression ratio",
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
                    f"uses {_fmt_bytes(volblock)} volblocks",
                    "a 4K-aligned guest filesystem divides evenly, but sub-volblock random "
                    "writes still pay partial-block cost; secs=4096 makes the guest "
                    "geometry explicit",
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
                )
            )
        elif demand_rate >= CACHE_RATIO_GOOD:
            findings.append(
                Finding(
                    "Memory",
                    "(host)",
                    SEV_OK,
                    f"ARC demand-data hit rate {demand_rate:.1%}",
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
            )
        ]
    return [
        Finding(
            "Memory",
            "(host)",
            SEV_INFO,
            message,
            "expected for random workloads; no action required",
        )
    ]


def analyse(sample, survey=None, profiles=None):
    """Return every Finding for the Alignment view, grouped by layer."""
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
            )
        )
    findings.extend(_pool_device_findings(sample))
    findings.extend(_dataset_findings(sample, survey, profiles))
    findings.extend(_observation_findings(sample))
    findings.extend(_vm_findings(sample))
    findings.extend(_memory_findings(sample))
    findings.extend(_prefetch_finding(sample, verdicts))
    return findings


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

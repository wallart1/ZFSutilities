"""ZFS memory-tier statistics — ARC, L2ARC, and SLOG data collection.

Pure data layer with no GTK dependencies so the parsers and rate math can
be unit-tested directly.  Three independent sources are probed on every
sample and degrade individually on hosts that do not expose them
(restricted ``/proc``, older OpenZFS releases, LXC containers):

- ``/proc/spl/kstat/zfs/arcstats`` — ARC + L2ARC counters
- ``/proc/spl/kstat/zfs/zil`` — ZIL/SLOG write counters
- ``zpool iostat -v`` — per-vdev cache/log capacity and traffic (no ``-L``
  so device names match ``zpool status``)

Every kstat field is optional: parsed dicts contain only the fields the
running kernel actually exposes, and the UI renders absent fields as "—".
Rates are computed from cumulative-counter deltas between samples
(arcstat-style), not from interval-blocking commands.
"""

import re
import subprocess
import time
from dataclasses import dataclass, field

from disk_repository import format_bytes

ARCSTATS_PATH = "/proc/spl/kstat/zfs/arcstats"
ZIL_PATH = "/proc/spl/kstat/zfs/zil"

# Subprocess timeout for `zpool iostat -v` (seconds).
IOSTAT_TIMEOUT = 10

# ---------------------------------------------------------------------------
# Regex: ^(\d+(?:\.\d+)?)([KMGTPE]?)$
# Purpose: Parse one `zpool iostat -v` value cell: a plain or decimal number
# with an optional binary size suffix.
# Group 1: The numeric part       e.g. "865", "24.5", "0"
# Group 2: The suffix             e.g. "K", "G", "" (scale 1024**n)
# Examples:
#   "865K" -> ("865", "K")   "24.5G" -> ("24.5", "G")   "32" -> ("32", "")
#   "-"    -> no match (handled by the caller)
# Rationale: zpool iostat renders human-readable sizes in base-1024 with
# single-letter suffixes (verified empirically against `zpool list -Hp`).
_IOSTAT_VALUE_RE = re.compile(r"^(\d+(?:\.\d+)?)([KMGTPE]?)$")

# Suffix scale table for _IOSTAT_VALUE_RE matches.
_SIZE_SUFFIXES = {"": 0, "K": 1, "M": 2, "G": 3, "T": 4, "P": 5, "E": 6}

# Vdev sections of `zpool iostat -v` output that the memory tab tracks.
_TRACKED_SECTIONS = ("logs", "cache")


@dataclass
class VdevSample:
    """One vdev row from `zpool iostat -v` (cumulative since boot)."""

    pool: str
    vdev: str
    section: str  # "logs" | "cache"
    alloc: int | None  # bytes; None when the cell is "-"
    free: int | None
    reads: int  # cumulative operations since boot
    writes: int
    read_bytes: int
    write_bytes: int


@dataclass
class MemorySample:
    """A single collection of all memory-tier counters.

    The ``*_available`` flags record which sources this host exposes; the
    corresponding dicts/lists stay empty when a source is unavailable.
    """

    monotonic: float
    arc: dict[str, int] = field(default_factory=dict)
    zil: dict[str, int] = field(default_factory=dict)
    vdevs: list[VdevSample] = field(default_factory=list)
    arcstats_available: bool = False
    zil_available: bool = False
    iostat_available: bool = False


@dataclass
class VdevRates:
    """Per-interval traffic rates for one vdev."""

    reads_ps: float | None
    writes_ps: float | None
    read_bps: float | None
    write_bps: float | None


@dataclass
class MemoryRates:
    """Per-interval rates derived from two MemorySamples."""

    arc_hits_ps: float | None = None
    arc_misses_ps: float | None = None
    arc_hit_rate: float | None = None  # percent over the interval
    l2_hits_ps: float | None = None
    l2_read_bps: float | None = None
    l2_write_bps: float | None = None
    l2_hit_rate: float | None = None  # percent over the interval
    slog_commits_ps: float | None = None
    slog_writes_ps: float | None = None
    slog_write_bps: float | None = None
    vdevs: dict[tuple[str, str], VdevRates] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# kstat parsers
# ---------------------------------------------------------------------------


def parse_kstats(text):
    """Parse a /proc/spl/kstat/zfs/* body into {name: value}.

    Skips the two header lines (crash record + column header); every
    well-formed data line contributes one entry, so the result contains
    only the fields the running kernel actually exposes.
    """
    stats = {}
    for line in text.splitlines()[2:]:
        parts = line.split()
        if len(parts) != 3:
            continue
        name, _type, data = parts
        try:
            stats[name] = int(data)
        except ValueError:
            continue
    return stats


def parse_arcstats(text):
    """Parse arcstats kstat text into {name: value}."""
    return parse_kstats(text)


def parse_zil_kstats(text):
    """Parse zil kstat text into {name: value}."""
    return parse_kstats(text)


# ---------------------------------------------------------------------------
# zpool iostat -v parser
# ---------------------------------------------------------------------------


def _parse_iostat_cell(cell):
    """Return the byte value of one iostat cell, or None for "-"."""
    match = _IOSTAT_VALUE_RE.match(cell)
    if match is None:
        return None
    number = float(match.group(1))
    scale = 1024 ** _SIZE_SUFFIXES[match.group(2)]
    return int(number * scale)


def parse_zpool_iostat_v(text):
    """Parse `zpool iostat -v` output into VdevSample rows.

    Only vdevs under the tracked infrastructure sections ("logs", "cache")
    are returned.  Rows are matched by structure, not by pool-name lists:
    the column separator between pool blocks is a flush-left all-dash
    name, section headers are flush-left rows whose value cells are all
    dashes, pool rows are flush-left with values, and vdev rows are
    indented — so output from any OpenZFS release parses the same way.
    """
    samples = []
    pool = None
    section = "data"
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) != 7:
            continue
        name, cells = parts[0], parts[1:]
        if set(name) == {"-"}:
            # Column separator between pool blocks.
            section = "data"
            continue
        indented = line[:1].isspace()
        if not indented and all(cell == "-" for cell in cells):
            # Flush-left all-dash row: an infrastructure section header.
            section = name if name in _TRACKED_SECTIONS else "data"
            continue
        alloc = _parse_iostat_cell(cells[0])
        free = _parse_iostat_cell(cells[1])
        tail = []
        for cell in cells[2:]:
            parsed = _parse_iostat_cell(cell)
            if parsed is None:
                tail = None
                break
            tail.append(parsed)
        if tail is None:
            # Column-header line ("pool alloc free read write read write")
            # or an unreadable row; skip it.
            continue
        if not indented:
            # Flush-left with values: a pool row.
            pool = name
            section = "data"
            continue
        if pool is None or section not in _TRACKED_SECTIONS:
            continue
        reads, writes, read_bytes, write_bytes = tail
        samples.append(
            VdevSample(
                pool=pool,
                vdev=name,
                section=section,
                alloc=alloc,
                free=free,
                reads=reads,
                writes=writes,
                read_bytes=read_bytes,
                write_bytes=write_bytes,
            )
        )
    return samples


# ---------------------------------------------------------------------------
# Collection + rate computation
# ---------------------------------------------------------------------------


def collect_memory_sample(
    arcstats_path=ARCSTATS_PATH,
    zil_path=ZIL_PATH,
    timeout=IOSTAT_TIMEOUT,
):
    """Collect one MemorySample, degrading per-source on failure."""
    sample = MemorySample(monotonic=time.monotonic())
    try:
        with open(arcstats_path) as f:
            sample.arc = parse_arcstats(f.read())
        sample.arcstats_available = True
    except OSError:
        pass
    try:
        with open(zil_path) as f:
            sample.zil = parse_zil_kstats(f.read())
        sample.zil_available = True
    except OSError:
        pass
    try:
        result = subprocess.run(
            ["zpool", "iostat", "-v"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode == 0:
            sample.vdevs = parse_zpool_iostat_v(result.stdout)
            sample.iostat_available = True
    except (OSError, subprocess.SubprocessError):
        pass
    return sample


def _delta_rate(prev, cur, elapsed):
    """Return (cur - prev) / elapsed, or None on reset/missing counters."""
    if prev is None or cur is None or cur < prev or elapsed <= 0:
        return None
    return (cur - prev) / elapsed


def _interval_hit_rate(hits_prev, hits_cur, misses_prev, misses_cur):
    """Return interval hit rate in percent, or None when no traffic."""
    hits = hits_cur - hits_prev if (hits_prev is not None and hits_cur is not None) else None
    misses = (
        misses_cur - misses_prev if (misses_prev is not None and misses_cur is not None) else None
    )
    if hits is None or misses is None or hits < 0 or misses < 0:
        return None
    total = hits + misses
    if total == 0:
        return None
    return 100.0 * hits / total


def cumulative_hit_rate(hits, misses):
    """Return since-boot hit rate in percent, or None when counters missing."""
    if hits is None or misses is None:
        return None
    total = hits + misses
    if total == 0:
        return None
    return 100.0 * hits / total


def _get(stats, key):
    """Return stats.get(key) — helper so call sites read as data lookups."""
    return stats.get(key)


def compute_rates(prev, cur):
    """Derive per-interval MemoryRates from two consecutive samples."""
    rates = MemoryRates()
    if prev is None or cur is None:
        return rates
    elapsed = cur.monotonic - prev.monotonic
    if elapsed <= 0:
        return rates

    rates.arc_hits_ps = _delta_rate(_get(prev.arc, "hits"), _get(cur.arc, "hits"), elapsed)
    rates.arc_misses_ps = _delta_rate(_get(prev.arc, "misses"), _get(cur.arc, "misses"), elapsed)
    rates.arc_hit_rate = _interval_hit_rate(
        _get(prev.arc, "hits"),
        _get(cur.arc, "hits"),
        _get(prev.arc, "misses"),
        _get(cur.arc, "misses"),
    )
    rates.l2_hits_ps = _delta_rate(_get(prev.arc, "l2_hits"), _get(cur.arc, "l2_hits"), elapsed)
    rates.l2_read_bps = _delta_rate(
        _get(prev.arc, "l2_read_bytes"), _get(cur.arc, "l2_read_bytes"), elapsed
    )
    rates.l2_write_bps = _delta_rate(
        _get(prev.arc, "l2_write_bytes"), _get(cur.arc, "l2_write_bytes"), elapsed
    )
    rates.l2_hit_rate = _interval_hit_rate(
        _get(prev.arc, "l2_hits"),
        _get(cur.arc, "l2_hits"),
        _get(prev.arc, "l2_misses"),
        _get(cur.arc, "l2_misses"),
    )
    rates.slog_commits_ps = _delta_rate(
        _get(prev.zil, "zil_commit_count"), _get(cur.zil, "zil_commit_count"), elapsed
    )
    rates.slog_writes_ps = _delta_rate(
        _get(prev.zil, "zil_itx_metaslab_slog_count"),
        _get(cur.zil, "zil_itx_metaslab_slog_count"),
        elapsed,
    )
    rates.slog_write_bps = _delta_rate(
        _get(prev.zil, "zil_itx_metaslab_slog_write"),
        _get(cur.zil, "zil_itx_metaslab_slog_write"),
        elapsed,
    )

    prev_vdevs = {(v.pool, v.vdev): v for v in prev.vdevs}
    for cur_vdev in cur.vdevs:
        prev_vdev = prev_vdevs.get((cur_vdev.pool, cur_vdev.vdev))
        if prev_vdev is None:
            continue
        rates.vdevs[(cur_vdev.pool, cur_vdev.vdev)] = VdevRates(
            reads_ps=_delta_rate(prev_vdev.reads, cur_vdev.reads, elapsed),
            writes_ps=_delta_rate(prev_vdev.writes, cur_vdev.writes, elapsed),
            read_bps=_delta_rate(prev_vdev.read_bytes, cur_vdev.read_bytes, elapsed),
            write_bps=_delta_rate(prev_vdev.write_bytes, cur_vdev.write_bytes, elapsed),
        )
    return rates


def format_rate(bps):
    """Format a bytes-per-second rate human-readably; '—' when unknown."""
    if bps is None:
        return "—"
    return f"{format_bytes(bps)}/s"


def format_percent(percent, digits=1):
    """Format a percentage; '—' when unknown."""
    if percent is None:
        return "—"
    return f"{percent:.{digits}f}%"


def format_count(value):
    """Format a raw counter; '—' when unknown."""
    if value is None:
        return "—"
    return f"{value:,}"


def format_per_second(value):
    """Format an events-per-second rate; '—' when unknown."""
    if value is None:
        return "—"
    return f"{value:,.0f}"

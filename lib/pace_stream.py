#!/usr/bin/env python3
"""Rate-limited byte-stream pacer: stdin (or a file) to stdout, capped flat.

Used by lib/archive-engine.sh and lib/transfer-lib.sh wherever a transfer rate
limit is configured. Semantics:

  * The stream never exceeds the configured rate by more than two chunks, ever
    — including right after a slow read or a stalled downstream consumer.
  * Deadline pacing: each chunk owns a budget of chunk/rate seconds; small
    per-chunk overheads are absorbed by the next chunk's sleep, so the
    long-run rate is exact.
  * Forfeit, not catch-up: when the pipeline stalls for longer than two chunk
    budgets (ZFS txg flush, dirty-data throttle, a slow consumer), the missed
    budget is discarded. A stall extends the transfer; it never buys a burst.

This replaces `pv -q -L`, which enforces only a long-run average: after every
downstream stall pv spends its accumulated deficit in bursts far above the cap
(measured: sustained 115-149 MiB/s under a 100M cap, 352 MiB/s after a 4s
stall), defeating the point of pacing a transfer on a small storage host.

Failure containment: a dead downstream consumer kills this process via SIGPIPE
(exit 141) so `set -o pipefail` pipelines fail loudly, exactly as pv did.

Rate grammar (same as archive_valid_rate in lib/archive-engine.sh): digits
plus an optional case-insensitive suffix from k/m/g/t/p/e with optional i and
optional b — 1024-based, e.g. 100M = 100 MiB/s, 500KiB = 500 KiB/s, 4096 = 4096
bytes/s.
"""

import signal
import sys
import time

MULTIPLIERS = {
    "": 1,
    "k": 1024,
    "m": 1024**2,
    "g": 1024**3,
    "t": 1024**4,
    "p": 1024**5,
    "e": 1024**6,
}

MIN_CHUNK = 64 * 1024
MAX_CHUNK = 16 * 1024**2
CHUNKS_PER_SECOND = 25

# Injectable for tests (dependency-injection style used elsewhere in python/).
_monotonic = time.monotonic
_sleep = time.sleep


def parse_rate(text):
    """Parse a rate string into bytes/second. Raises ValueError on garbage."""
    lowered = text.strip().lower()
    i = 0
    while i < len(lowered) and lowered[i].isdigit():
        i += 1
    digits, suffix = lowered[:i], lowered[i:]
    if not digits:
        raise ValueError(f"rate must start with digits: {text!r}")
    if suffix.endswith("ib"):
        suffix = suffix[:-2]
    elif suffix.endswith(("i", "b")):
        suffix = suffix[:-1]
    if suffix not in MULTIPLIERS:
        raise ValueError(f"invalid rate suffix: {text!r}")
    return int(digits) * MULTIPLIERS[suffix]


def chunk_size_for(rate):
    """Chunk big enough to keep syscall counts low, small enough to pace
    smoothly at htop refresh scale: rate/25, clamped to [64KiB, 16MiB]."""
    return max(MIN_CHUNK, min(rate // CHUNKS_PER_SECOND, MAX_CHUNK))


def paced_copy(src, out, rate):
    """Copy src to out, never exceeding rate beyond two chunk budgets."""
    chunk = chunk_size_for(rate)
    budget = chunk / rate
    deadline = _monotonic()
    while True:
        data = src.read(chunk)
        if not data:
            break
        out.write(data)
        out.flush()
        deadline += budget
        now = _monotonic()
        if deadline > now:
            _sleep(deadline - now)
        elif now - deadline > 2 * budget:
            # Forfeit: a stall must not buy a later burst.
            deadline = now


def main(argv):
    args = argv[1:]
    if not args or len(args) > 3:
        print(f"usage: {argv[0]} <rate> [--] [file]", file=sys.stderr)
        return 2
    try:
        rate = parse_rate(args[0])
    except ValueError as exc:
        print(f"pace_stream: {exc}", file=sys.stderr)
        return 2
    path = None
    if len(args) >= 2:
        path = args[1]
        if path == "--":
            path = args[2] if len(args) == 3 else None
        elif len(args) == 3:
            print(f"usage: {argv[0]} <rate> [--] [file]", file=sys.stderr)
            return 2
    if path is not None:
        try:
            with open(path, "rb") as source:
                return _pump(source, rate)
        except OSError as exc:
            print(f"pace_stream: cannot open {path}: {exc}", file=sys.stderr)
            return 1
    return _pump(sys.stdin.buffer, rate)


def _pump(source, rate):
    # Die on EPIPE like a normal filter so pipefail pipelines catch it.
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    try:
        paced_copy(source, sys.stdout.buffer, rate)
    except BrokenPipeError:
        return 141
    except OSError as exc:
        print(f"pace_stream: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

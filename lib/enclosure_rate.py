#!/usr/bin/env python3
"""Per-enclosure transfer-rate resolver — the single min() of rate governance.

CLI contract:

    enclosure_rate.py [--min-with <rate>] <pool-or-dataset>...

  * Each argument names a pool or dataset (pool = first path component; a
    snapshot suffix is ignored). An enclosure caps the transfer when any of
    its member pools is among those pools — an enclosure may hold disks of
    several pools and a pool may span several enclosures.
  * Prints the effective rate: the minimum of --min-with (the per-activity
    rate limit) and every configured cap of every touched enclosure. The
    winner's original string is printed; empty output means unlimited.
  * Exit 0 on success (including empty output), 2 on usage errors, 1 on
    resolver failure (discovery or config) — callers fail open on a nonzero
    exit: run at their own activity limit and log loudly, never blocking a
    transfer on an enclosure-scan hiccup.

Rate grammar (the pacer's, lib/pace_stream.py): digits plus an optional
case-insensitive k/m/g/t/p/e multiplier with optional i/b — 1024-based.
Rates compare numerically via pace_stream.parse_rate so the grammar cannot
drift from the pacer; zfs_repository.valid_rate_limit stays the GUI-side
validator of the same grammar.

Python callers (the GUI via ZfsRepository.effective_transfer_rate) share the
same resolution through effective_rate(), which applies the same fail-open
policy in-process instead of exit codes.

Invoked by the shared transfer engine (lib/transfer-lib.sh's
transfer_resolve_rate), the archive engine's per-zvol rate resolution
(lib/archive-engine.sh), the standalone streaming scripts (zfsreadthru,
zfsrestoresendstream), and the GUI's ZfsRepository.effective_transfer_rate.
"""

import os
import sys

# Import layout: this file lives in lib/ beside the pacer (parse_rate) and
# reaches the python/ layer (enclosure_inventory, feature_config,
# config_core) through the sibling directory — identical in the repository
# and the deployed version tree (bin/, lib/, python/, share/).
_HERE = os.path.dirname(os.path.realpath(__file__))
for _candidate in (_HERE, os.path.join(_HERE, os.pardir, "python")):
    _candidate = os.path.realpath(_candidate)
    if _candidate not in sys.path:
        sys.path.insert(0, _candidate)

# Pacer grammar: imported after the sys.path bootstrap above on purpose.
import pace_stream


def pool_of(target):
    """Return the pool of a pool-or-dataset argument ("tank/ds@snap" -> "tank").

    Empty for arguments that name no pool (leading slash, bare snapshot).
    """
    return target.split("/", 1)[0].split("@", 1)[0]


def min_rate(*rates):
    """Return the smallest non-empty rate string ("" when all are empty).

    The one min() of rate governance: values compare numerically through
    pace_stream.parse_rate (the pacer grammar), and the winner's original
    string is returned so pacer argv keeps the user's units. Raises
    ValueError when a rate is not pacer grammar.
    """
    candidates = [rate for rate in rates if rate]
    if not candidates:
        return ""
    parsed = [(pace_stream.parse_rate(rate), rate) for rate in candidates]
    return min(parsed, key=lambda pair: pair[0])[1]


def caps_for_pools(pools, enclosures, caps):
    """Yield the configured cap strings of enclosures touched by *pools*."""
    wanted = set(pools)
    for enclosure in enclosures:
        if wanted.isdisjoint(enclosure.pools):
            continue
        entry = caps.get(enclosure.id)
        if isinstance(entry, dict) and entry.get("max_rate"):
            yield entry["max_rate"]


def resolve_effective_rate(pools, activity_rate="", enclosures=(), caps=None):
    """Pure resolver: min(activity_rate, every cap of every touched enclosure).

    Returns the winning rate string, "" when nothing constrains the
    transfer. Raises ValueError on a non-grammar rate string; callers own
    the fail-open policy.
    """
    return min_rate(activity_rate, *caps_for_pools(pools, enclosures, caps or {}))


def _resolve_live(pools, activity_rate="", inventory=None, config=None):
    """Resolve against live discovery and config. Raises on any failure.

    *inventory* and *config* are injectable for tests and for callers that
    already hold either object; None means discover / load here.
    """
    if inventory is None:
        from enclosure_inventory import EnclosureInventory

        inventory = EnclosureInventory()
    if config is None:
        from config_core import load_config

        config = load_config()
    from feature_config import get_enclosures_config

    return resolve_effective_rate(
        pools, activity_rate, inventory.discover(), get_enclosures_config(config)
    )


def effective_rate(pools, activity_rate="", inventory=None, config=None):
    """Resolve for Python callers, failing open per campaign policy.

    On any resolver failure — discovery error, unreadable config, a
    non-grammar cap — logs a loud WARN and returns *activity_rate*
    unchanged: a transfer runs at today's activity limit rather than
    blocking on an enclosure-scan hiccup.
    """
    from logging_config import log_msg

    try:
        return _resolve_live(pools, activity_rate, inventory=inventory, config=config)
    except Exception as exc:
        log_msg(f"WARN: enclosure rate resolution failed ({exc}); using the activity limit")
        return activity_rate


def main(argv, inventory=None, config=None):
    """CLI entry; *inventory*/*config* are injectable for tests."""
    usage = "usage: enclosure_rate.py [--min-with <rate>] <pool-or-dataset>..."
    args = argv[1:]
    min_with = ""
    if args and args[0] == "--min-with":
        if len(args) < 2:
            print(usage, file=sys.stderr)
            return 2
        min_with = args[1]
        args = args[2:]
    if not args:
        print(usage, file=sys.stderr)
        return 2
    if min_with:
        try:
            pace_stream.parse_rate(min_with)
        except ValueError as exc:
            print(f"enclosure_rate: {exc}", file=sys.stderr)
            return 2
    pools = []
    for target in args:
        pool = pool_of(target.strip())
        if not pool or pool.startswith("-"):
            print(f"enclosure_rate: invalid target: {target!r}", file=sys.stderr)
            return 2
        if pool not in pools:
            pools.append(pool)
    try:
        rate = _resolve_live(pools, min_with, inventory=inventory, config=config)
    except Exception as exc:
        print(f"enclosure_rate: rate resolution failed: {exc}", file=sys.stderr)
        return 1
    print(rate)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

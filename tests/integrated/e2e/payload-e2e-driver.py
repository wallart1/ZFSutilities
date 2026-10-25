#!/usr/bin/env python3
"""Payload e2e driver — the full GUI-payload scenario matrix, standalone.

Runs inside a privileged context (the ITF j11 guest) where dataset
mutations are permitted.  Unprivileged containers see the pools read-only
(all dataset ioctls need CAP_SYS_ADMIN), so they run only the dry-run and
mechanics layers via pytest; this driver is the full-matrix entry point.

The scenarios and their assertions live in tests/python/e2e_support.py,
shared with the pytest front ends — one matrix, three contexts (container
read-layer, dev-host sudo, ITF guest).

Usage:
    python3 tests/integrated/e2e/payload-e2e-driver.py \
        [--scenarios offsite-,backup-] [--timeout 300] [--list]
"""

from __future__ import annotations

import argparse
import os
import sys

_DRIVER_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.realpath(os.path.join(_DRIVER_DIR, "..", "..", ".."))
for path in (
    os.path.join(_REPO_ROOT, "tests", "python"),
    os.path.join(_REPO_ROOT, "python"),
):
    if path not in sys.path:
        sys.path.insert(0, path)

import e2e_support as e2e


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenarios",
        default="",
        help="comma-separated name prefixes to run (default: all)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="per-step watchdog timeout in seconds (default 300)",
    )
    parser.add_argument("--list", action="store_true", help="list scenarios and exit")
    args = parser.parse_args(argv)

    if args.list:
        for name, _fn, level, engine in e2e.SCENARIOS:
            print(f"{level:8s} {engine:3s} {name}")
        return 0

    prefixes = tuple(p for p in args.scenarios.split(",") if p) or None

    print(f"payload-e2e-driver: repo={_REPO_ROOT} euid={os.geteuid()}")
    if not e2e.read_capable():
        print("FATAL: needs root with zfstest1/2/3 online.", file=sys.stderr)
        return 2
    if not e2e.mutation_capable():
        print(
            "FATAL: dataset mutations are not permitted here (unprivileged "
            "context?); run the full matrix in the ITF guest.",
            file=sys.stderr,
        )
        return 2

    results, failed = e2e.run_matrix(
        lambda engine: e2e.PtyExecutor(timeout=args.timeout, input_hold=(engine == "gui")),
        prefixes=prefixes,
    )

    print()
    print("=" * 60)
    passed = sum(1 for _n, ok, _d in results if ok)
    print(f"payload e2e: {passed} passed, {len(failed)} failed, {len(results)} total")
    if failed:
        print("failed scenarios: " + ", ".join(failed))
    print("=" * 60)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

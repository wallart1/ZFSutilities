r"""Diagnostic script for ZfsRepository / Datasets tab behavior.

Run on a machine with live ZFS pools:

    sudo python3 07\ GTK\ +\ Python/diagnose_zfs_repository.py

It exercises the same repository calls the Datasets tab uses and prints
exact commands, return codes, and result counts.
"""

import os
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from zfs_repository import ZfsRepository


def main():
    repo = ZfsRepository(sudo=True)

    print("=" * 70)
    print("1. list_pools()")
    print("=" * 70)
    try:
        pools = repo.list_pools()
        print(f"Pools found: {len(pools)}")
        for p in pools:
            print(f"  {p.name}")
    except Exception as e:
        print(f"ERROR: {e}")
        return

    if not pools:
        print("No pools to test.")
        return

    pool = pools[0].name
    print()
    print("=" * 70)
    print(f"2. list_datasets(pool={pool!r}, depth=1)")
    print("=" * 70)
    try:
        rows = repo.list_datasets(pool=pool, depth=1)
        print(f"Rows returned: {len(rows)}")
        for r in rows:
            print(f"  {r.ds_type:12} {r.name}")
    except Exception as e:
        print(f"ERROR: {e}")

    # Find a nested dataset to test
    nested = [r for r in rows if r.name != pool and r.ds_type in ("filesystem", "volume")]
    if not nested:
        print("No nested datasets found to test snapshot loading.")
        return

    # Prefer the leafiest dataset that has snapshots
    candidate = None
    for r in reversed(rows):
        if r.ds_type in ("filesystem", "volume") and r.name != pool:
            candidate = r.name
            break

    if not candidate:
        candidate = nested[0].name

    print()
    print("=" * 70)
    print(f"3. list_snapshots(dataset={candidate!r}, depth=0)")
    print("=" * 70)
    try:
        snaps = repo.list_snapshots(candidate, depth=0)
        print(f"Snapshots returned: {len(snaps)}")
        for s in snaps:
            print(f"  {s.name}")
    except Exception as e:
        print(f"ERROR: {e}")

    print()
    print("=" * 70)
    print(f"4. list_datasets(pool={candidate!r}, depth=1)")
    print("=" * 70)
    try:
        children = repo.list_datasets(pool=candidate, depth=1)
        print(f"Children returned: {len(children)}")
        for c in children:
            print(f"  {c.ds_type:12} {c.name}")
    except Exception as e:
        print(f"ERROR: {e}")


if __name__ == "__main__":
    main()

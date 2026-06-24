#!/usr/bin/env python3
"""
zfsinfo.py - Display ZFS pool and dataset information

First Python project for ZFS Utilities. Demonstrates:
- subprocess module for calling zfs/zpool commands
- Parsing command output
- Formatted text output
- Basic error handling

Usage: python3 zfsinfo.py [pool_name]
"""

import subprocess
import sys

from backup_config import log_msg
from zfs_repository import get_default_repository


def get_pools(repo=None):
    """Get list of all ZFS pools with their health status."""
    repo = repo or get_default_repository()
    try:
        return [
            {
                'name': row.name,
                'size': row.size,
                'alloc': row.alloc,
                'free': row.free,
                'health': row.health,
            }
            for row in repo.list_pools()
        ]
    except subprocess.CalledProcessError:
        return []


def get_datasets(pool=None, repo=None):
    """Get list of datasets, optionally filtered by pool."""
    repo = repo or get_default_repository()
    try:
        return repo.list_dataset_info(pool=pool)
    except subprocess.CalledProcessError:
        return []


def get_snapshot_counts(pool=None, repo=None):
    """Get snapshot count per dataset."""
    repo = repo or get_default_repository()
    try:
        snaps = repo.list_all_snapshot_names(pool=pool)
    except subprocess.CalledProcessError:
        return {}

    counts = {}
    for line in snaps:
        if '@' in line:
            dataset = line.split('@')[0]
            counts[dataset] = counts.get(dataset, 0) + 1
    return counts


def print_pools(pools):
    """Display pool information."""
    log_msg("INFO: " + "=" * 70)
    log_msg("INFO: ZFS POOLS")
    log_msg("INFO: " + "=" * 70)

    if not pools:
        log_msg("INFO:   No pools found.")
        return

    # Header
    log_msg(f"INFO: {'NAME':<20} {'SIZE':>8} {'ALLOC':>8} {'FREE':>8} {'HEALTH':<10}")
    log_msg("INFO: " + "-" * 70)

    for pool in pools:
        health = pool['health']
        # Add indicator for non-healthy pools
        if health != 'ONLINE':
            health = f"** {health} **"

        log_msg(f"INFO: {pool['name']:<20} {pool['size']:>8} {pool['alloc']:>8} {pool['free']:>8} {health:<10}")

    log_msg("INFO: ")


def print_datasets(datasets, snapshot_counts):
    """Display datasets in a tree structure with snapshot counts."""
    log_msg("INFO: " + "=" * 70)
    log_msg("INFO: DATASETS")
    log_msg("INFO: " + "=" * 70)

    if not datasets:
        log_msg("INFO:   No datasets found.")
        return

    # Header
    log_msg(f"INFO: {'NAME':<40} {'USED':>8} {'SNAPS':>6}")
    log_msg("INFO: " + "-" * 70)

    for ds in datasets:
        name = ds['name']
        # Calculate indent based on path depth
        depth = name.count('/')
        indent = "  " * depth
        short_name = name.split('/')[-1] if '/' in name else name

        snap_count = snapshot_counts.get(name, 0)
        snap_str = str(snap_count) if snap_count > 0 else "-"

        display_name = f"{indent}{short_name}"
        log_msg(f"INFO: {display_name:<40} {ds['used']:>8} {snap_str:>6}")

    log_msg("INFO: ")


def print_summary(pools, datasets, snapshot_counts):
    """Display summary statistics."""
    log_msg("INFO: " + "=" * 70)
    log_msg("INFO: SUMMARY")
    log_msg("INFO: " + "=" * 70)

    total_snapshots = sum(snapshot_counts.values())
    online_pools = sum(1 for p in pools if p['health'] == 'ONLINE')
    degraded_pools = sum(1 for p in pools if p['health'] != 'ONLINE')

    log_msg(f"INFO:   Pools:     {len(pools)} total ({online_pools} online, {degraded_pools} degraded/offline)")
    log_msg(f"INFO:   Datasets:  {len(datasets)}")
    log_msg(f"INFO:   Snapshots: {total_snapshots}")
    log_msg("INFO: ")


def main():
    """Main entry point."""
    # Optional pool filter from command line
    pool_filter = sys.argv[1] if len(sys.argv) > 1 else None

    if pool_filter:
        log_msg(f"INFO: Filtering by pool: {pool_filter}")

    # Gather information
    pools = get_pools()
    datasets = get_datasets(pool_filter)
    snapshot_counts = get_snapshot_counts(pool_filter)

    # Display
    print_pools(pools)
    print_datasets(datasets, snapshot_counts)
    print_summary(pools, datasets, snapshot_counts)


if __name__ == "__main__":
    main()

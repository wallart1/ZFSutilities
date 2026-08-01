#!/bin/bash
#
# Quick Cache Status Check
# Shows current ARC and L2ARC status in summary format
#

set -euo pipefail

POOL_NAME="${1:-vmpool}"

echo "=== ZFS Cache Status ==="
echo "Pool: $POOL_NAME"
echo "Time: $(date)"
echo ""

# Check if pool exists
if ! zpool list "$POOL_NAME" &>/dev/null; then
    echo "ERROR: Pool '$POOL_NAME' not found"
    exit 1
fi

# System uptime
echo "--- System Status ---"
uptime
echo ""

# Pool health
echo "--- Pool Health ---"
zpool list "$POOL_NAME"
echo ""

# ARC Status
echo "--- ARC Status ---"
arc_summary 2>/dev/null | grep -A 4 "ARC status:" | tail -4
echo ""

# L2ARC Status
echo "--- L2ARC Status ---"
arc_summary 2>/dev/null | grep -A 3 "L2ARC status:" | tail -3
arc_summary 2>/dev/null | grep -A 2 "L2ARC size"
echo ""

# Hit Rates
echo "--- Cache Hit Rates ---"
arc_summary 2>/dev/null | grep "Total hits:" 
arc_summary 2>/dev/null | grep "L2ARC breakdown:" -A 1 | grep "Hit ratio:"
echo ""

# Cache Devices
echo "--- Cache Devices ---"
zpool status -v "$POOL_NAME" | grep -A 20 "cache" | grep -v "errors:" || echo "No cache devices configured"
echo ""

# Recent growth (if progress log exists)
if [[ -f /var/log/zfs-cache-warm-progress.log ]]; then
    echo "--- Recent L2ARC Growth ---"
    tail -5 /var/log/zfs-cache-warm-progress.log
    echo ""
fi

# L2ARC fill rate
echo "--- L2ARC Configuration ---"
current_max=$(cat /sys/module/zfs/parameters/l2arc_write_max)
current_boost=$(cat /sys/module/zfs/parameters/l2arc_write_boost)
echo "Write max:   $(numfmt --to=iec-i --suffix=B/s $current_max)"
echo "Write boost: $(numfmt --to=iec-i --suffix=B/s $current_boost)"
noprefetch=$(cat /sys/module/zfs/parameters/l2arc_noprefetch)
echo "No prefetch: $noprefetch (1=enabled, prefetch data not cached)"
echo ""

# Pool I/O
echo "--- Current Pool I/O (5 second sample) ---"
zpool iostat -v "$POOL_NAME" 5 2 | tail -$(zpool status -v "$POOL_NAME" | wc -l)
echo ""

echo "=== End Status ==="

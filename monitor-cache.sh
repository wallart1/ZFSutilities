#!/bin/bash
#
# Monitor Cache Warming Progress
# Displays real-time L2ARC and ARC statistics
#

set -euo pipefail

INTERVAL="${1:-60}"  # Default: update every 60 seconds
POOL_NAME="${2:-vmpool}"

echo "=== ZFS Cache Warming Monitor ==="
echo "Pool: $POOL_NAME"
echo "Update interval: ${INTERVAL}s"
echo "Press Ctrl+C to exit"
echo ""

# Function to get L2ARC size in bytes
get_l2arc_bytes() {
    local bytes=$(arc_summary 2>/dev/null | grep "L2ARC size" | head -1 | awk '{
        value=$4
        unit=$5
        if (unit ~ /TiB/) printf "%.0f", value * 1024 * 1024 * 1024 * 1024
        else if (unit ~ /GiB/) printf "%.0f", value * 1024 * 1024 * 1024
        else if (unit ~ /MiB/) printf "%.0f", value * 1024 * 1024
        else print 0
    }')
    echo "${bytes:-0}"
}

# Function to format bytes to human readable
format_bytes() {
    local bytes=$1
    numfmt --to=iec-i --suffix=B "$bytes" 2>/dev/null || echo "${bytes}B"
}

# Get initial size
prev_l2arc=$(get_l2arc_bytes)
prev_time=$(date +%s)

echo "Timestamp           | L2ARC Size | Growth Rate | ARC Hit% | L2ARC Hit% | I/O (r/w ops)"
echo "--------------------+------------+-------------+----------+------------+---------------"

while true; do
    # Get current stats
    curr_time=$(date +%s)
    curr_l2arc=$(get_l2arc_bytes)
    
    # Calculate growth
    time_diff=$((curr_time - prev_time))
    l2arc_diff=$((curr_l2arc - prev_l2arc))
    
    if [[ $time_diff -gt 0 ]]; then
        growth_rate=$((l2arc_diff / time_diff))
    else
        growth_rate=0
    fi
    
    # Get hit rates
    arc_hit=$(arc_summary 2>/dev/null | grep "Total hits:" | awk '{print $3}')
    l2arc_hit=$(arc_summary 2>/dev/null | grep "L2ARC breakdown:" -A 1 | grep "Hit ratio:" | awk '{print $3}')
    
    # Get pool I/O (read/write operations per second)
    pool_io=$(zpool iostat "$POOL_NAME" 1 2 2>/dev/null | tail -1 | awk '{print $4 " " $5}')
    
    # Format output
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    l2arc_size=$(format_bytes "$curr_l2arc")
    growth=$(format_bytes "$growth_rate")/s
    
    # Remove % symbols from hit rates
    arc_hit=${arc_hit//%/}
    l2arc_hit=${l2arc_hit//%/}
    
    printf "%s | %10s | %11s | %7s%% | %9s%% | %s\n" \
        "$timestamp" "$l2arc_size" "$growth" "${arc_hit:-0}" "${l2arc_hit:-0}" "$pool_io"
    
    # Update previous values
    prev_l2arc=$curr_l2arc
    prev_time=$curr_time
    
    # Wait for interval
    sleep "$INTERVAL"
done

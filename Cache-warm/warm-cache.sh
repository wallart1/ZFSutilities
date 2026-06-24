#!/bin/bash
#
# ZFS L2ARC Warming Script for Post-Reboot
# Optimized for monthly maintenance reboots
#
# This script accelerates L2ARC population after system reboot by:
# 1. Boosting L2ARC fill rate temporarily
# 2. Starting all VMs (natural workload)
# 3. Reading hot VM disks to populate cache
# 4. Monitoring progress
#
# Author: Created for home lab storage node
# Version: 1.0
#

set -euo pipefail

#==============================================================================
# CONFIGURATION
#==============================================================================

# Pools to warm
POOL_NAME="threeamigos"

# VM dataset path (where your VM zvols live)
VM_DATASET="threeamigos/proxmox"

# Hot VMs - List your most frequently accessed VMs
# Format: "vm-ID-disk-N" (the zvol name)
# These will be read completely to populate cache
# Start with your most important VMs (database, web, docker, etc.)
HOT_VMS=( \
    "vm-201-disk-2" \
    "vm-202-disk-5" \
)

# Start all VMs automatically?
START_ALL_VMS=true

# L2ARC boost settings (bytes per second)
L2ARC_BOOST_RATE=134217728   # 128 MB/s (default is 32 MB/s)
L2ARC_NORMAL_RATE=33554432   # 32 MB/s (restore to default)

# VM boot wait time (seconds)
VM_BOOT_WAIT=300  # 5 minutes for VMs to boot and start services

# Logging
LOG_FILE="/var/log/zfs-cache-warm.log"
PROGRESS_LOG="/var/log/zfs-cache-warm-progress.log"

# Safety check - don't run if L2ARC already substantial
MIN_L2ARC_SIZE_GB=50  # If L2ARC > this, assume cache is already warm

#==============================================================================
# FUNCTIONS
#==============================================================================

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
    echo "$msg" | tee -a "$LOG_FILE"
}

log_progress() {
    local l2arc_size=$(arc_summary 2>/dev/null | grep "L2ARC size" | awk '{print $4, $5}' || echo "Unknown")
    echo "$(date '+%Y-%m-%d %H:%M:%S') - L2ARC: $l2arc_size" >> "$PROGRESS_LOG"
}

get_l2arc_size_bytes() {
    # Parse L2ARC size from arc_summary
    # Returns size in GB as integer (0 if can't determine)
    # grep "L2ARC size" | head -1  —  arc_summary produces many lines; grab the first L2ARC size line.
    local size_line=$(arc_summary 2>/dev/null | grep "L2ARC size" | head -1)
    
    # Regex: ([0-9.]+)[[:space:]]+(GiB|MiB|TiB)
    # Purpose: Extract the numeric size and unit from arc_summary L2ARC output.
    # Group 1: numeric value  e.g. "1.5", "256"
    # Group 2: unit            e.g. "GiB", "MiB", "TiB"
    # Example: "L2ARC size:                     256 GiB" -> match ("256", "GiB")
    if [[ $size_line =~ ([0-9.]+)[[:space:]]+(GiB|MiB|TiB) ]]; then
        local value="${BASH_REMATCH[1]}"
        local unit="${BASH_REMATCH[2]}"
        
        case $unit in
            TiB) echo "scale=0; $value * 1024" | bc | cut -d. -f1 ;;
            GiB) echo "$value" | cut -d. -f1 ;;
            MiB) echo "scale=0; $value / 1024" | bc | cut -d. -f1 ;;
            *) echo 0 ;;
        esac
    else
        echo 0
    fi
}

check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check if running as root
    if [[ $EUID -ne 0 ]]; then
        log "ERROR: This script must be run as root"
        exit 1
    fi
    
    # Check if pool exists
    if ! zpool list "$POOL_NAME" &>/dev/null; then
        log "ERROR: Pool '$POOL_NAME' not found"
        exit 1
    fi
    
    # Check if arc_summary is available
    if ! command -v arc_summary &>/dev/null; then
        log "ERROR: arc_summary command not found"
        exit 1
    fi
    
    # Check current L2ARC size
    local current_l2arc=$(get_l2arc_size_bytes)
    if [[ $current_l2arc -gt $MIN_L2ARC_SIZE_GB ]]; then
        log "INFO: L2ARC already has ${current_l2arc}GB, appears warm. Exiting."
        exit 0
    fi
    
    log "Prerequisites OK. Current L2ARC: ${current_l2arc}GB"
}

boost_l2arc_fill_rate() {
    log "Boosting L2ARC fill rate from $(cat /sys/module/zfs/parameters/l2arc_write_max) to $L2ARC_BOOST_RATE"
    
    echo "$L2ARC_BOOST_RATE" > /sys/module/zfs/parameters/l2arc_write_max
    echo "$L2ARC_BOOST_RATE" > /sys/module/zfs/parameters/l2arc_write_boost
    
    log "L2ARC fill rate boosted to $(numfmt --to=iec-i --suffix=B/s $L2ARC_BOOST_RATE)"
}

restore_l2arc_fill_rate() {
    log "Restoring normal L2ARC fill rate to $L2ARC_NORMAL_RATE"
    
    echo "$L2ARC_NORMAL_RATE" > /sys/module/zfs/parameters/l2arc_write_max
    echo "$L2ARC_NORMAL_RATE" > /sys/module/zfs/parameters/l2arc_write_boost
    
    log "L2ARC fill rate restored to $(numfmt --to=iec-i --suffix=B/s $L2ARC_NORMAL_RATE)"
}

start_vms() {
    if [[ "$START_ALL_VMS" != "true" ]]; then
        log "VM auto-start disabled, skipping..."
        return
    fi
    
    log "Starting all VMs..."
    
    local vm_count=0
    local started_count=0
    
    # Get list of all VMs
    while IFS= read -r vmid; do
        ((vm_count++))
        
        # Check if VM is already running
        if qm status "$vmid" | grep -q "status: running"; then
            log "  VM $vmid already running, skipping"
            continue
        fi
        
        log "  Starting VM $vmid..."
        if qm start "$vmid" &>/dev/null; then
            ((started_count++))
        else
            log "  WARNING: Failed to start VM $vmid"
        fi
    done < <(qm list | awk 'NR>1 {print $1}')
    
    log "Started $started_count of $vm_count VMs"
    
    if [[ $started_count -gt 0 ]]; then
        log "Waiting ${VM_BOOT_WAIT}s for VMs to boot and start services..."
        sleep "$VM_BOOT_WAIT"
        log "VM boot wait complete"
    fi
}

warm_hot_vms() {
    if [[ ${#HOT_VMS[@]} -eq 0 ]]; then
        log "No hot VMs configured, skipping direct warming..."
        return
    fi
    
    log "Warming ${#HOT_VMS[@]} hot VM disk(s)..."
    
    local pids=()
    local warmed=0
    local failed=0
    
    for vm in "${HOT_VMS[@]}"; do
        local zvol_path="/dev/zvol/${VM_DATASET}/${vm}"
        
        if [[ ! -e "$zvol_path" ]]; then
            log "  WARNING: $zvol_path not found, skipping"
            ((failed++))
            continue
        fi
        
        # Get zvol size for progress reporting
        local zvol_size=$(blockdev --getsize64 "$zvol_path" 2>/dev/null || echo "unknown")
        local zvol_size_gb=$(echo "scale=1; $zvol_size / 1024 / 1024 / 1024" | bc 2>/dev/null || echo "?")
        
        log "  Reading $vm (${zvol_size_gb}GB)..."
        
        # Read zvol in background
        dd if="$zvol_path" of=/dev/null bs=1M status=none 2>/dev/null &
        pids+=($!)
        ((warmed++))
    done
    
    if [[ $warmed -gt 0 ]]; then
        log "  Warming $warmed VMs in parallel (PIDs: ${pids[*]})..."
        
        # Wait for all warming processes
        for pid in "${pids[@]}"; do
            if wait "$pid" 2>/dev/null; then
                log "  Process $pid completed successfully"
            else
                log "  WARNING: Process $pid failed or was interrupted"
            fi
        done
        
        log "Direct VM warming complete ($warmed warmed, $failed failed)"
    fi
}

monitor_progress() {
    log "Cache warming initiated. Monitoring progress..."
    log_progress
    
    # Log progress for the next hour (every 5 minutes)
    for i in {1..12}; do
        sleep 300  # 5 minutes
        log_progress
        
        if [[ $i -eq 6 ]]; then
            # After 30 minutes, log current status
            local l2arc_size=$(arc_summary | grep "L2ARC size" | awk '{print $4, $5}')
            log "30-minute checkpoint: L2ARC at $l2arc_size"
        fi
    done
    
    log "Initial 1-hour monitoring complete"
}

show_summary() {
    log "=== Cache Warming Summary ==="
    
    # Show ARC stats
    log "ARC Status:"
    arc_summary | grep -A 3 "ARC status:" | tail -3 | while read line; do
        log "  $line"
    done
    
    # Show L2ARC stats
    log "L2ARC Status:"
    arc_summary | grep -A 5 "L2ARC status:" | tail -5 | while read line; do
        log "  $line"
    done
    
    # Show recent progress
    log "Recent L2ARC growth:"
    tail -5 "$PROGRESS_LOG" 2>/dev/null | while read line; do
        log "  $line"
    done || log "  (no progress log available)"
}

cleanup() {
    log "Performing cleanup..."
    restore_l2arc_fill_rate
    log "Cleanup complete"
}

#==============================================================================
# MAIN EXECUTION
#==============================================================================

main() {
    log "========================================="
    log "ZFS Cache Warming Script Starting"
    log "Pool: $POOL_NAME"
    log "VM Dataset: $VM_DATASET"
    log "Hot VMs: ${#HOT_VMS[@]}"
    log "========================================="
    
    # Set up cleanup trap
    trap cleanup EXIT INT TERM
    
    # Check prerequisites
    check_prerequisites
    
    # Boost L2ARC fill rate
    boost_l2arc_fill_rate
    
    # Start all VMs (natural warming)
    start_vms
    
    # Warm hot VMs directly
    warm_hot_vms
    
    # Monitor progress in background
    monitor_progress &
    local monitor_pid=$!
    
    log "Cache warming in progress (monitor PID: $monitor_pid)"
    log "Check progress: tail -f $PROGRESS_LOG"
    log "Natural cache filling will continue over the next 1-2 weeks"
    
    # Wait for monitoring to complete
    wait "$monitor_pid"
    
    # Show summary
    show_summary
    
    log "========================================="
    log "Cache warming script completed"
    log "========================================="
}

# Run main function
main "$@"

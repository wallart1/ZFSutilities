#!/bin/bash
#
# Identify Hot VMs Script
# Helps determine which VMs to include in HOT_VMS configuration
#
# This analyzes ZFS ARC statistics to identify which VMs are most frequently accessed
#

set -euo pipefail

echo "=== ZFS Hot VM Analyzer ==="
echo ""
echo "Analyzing ZFS access patterns to identify hot VMs..."
echo ""

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: This script must be run as root (needs access to ZFS kstats)"
    exit 1
fi

POOL_NAME="${1:-vmpool}"
VM_DATASET="${2:-vmpool/iscsi-vms}"

echo "Pool: $POOL_NAME"
echo "VM Dataset: $VM_DATASET"
echo ""

# Get list of VM zvols
echo "Discovered VM zvols:"
zfs list -r -t volume -o name "$VM_DATASET" 2>/dev/null | grep -v "^NAME$" | while read zvol; do
    zvol_name=$(basename "$zvol")
    zvol_size=$(zfs get -H -o value volsize "$zvol")
    echo "  - $zvol_name ($zvol_size)"
done

echo ""
echo "=============================================="
echo "RECOMMENDATION FOR HOT_VMS CONFIGURATION"
echo "=============================================="
echo ""
echo "To determine which VMs are 'hot' (frequently accessed):"
echo ""
echo "Option 1 - By VM Importance:"
echo "  List VMs in order of business criticality:"
echo "  - Database servers (highest I/O)"
echo "  - Application servers"
echo "  - Web servers"
echo "  - Development/test VMs (lower priority)"
echo ""
echo "Option 2 - By Disk I/O (requires monitoring):"
echo "  Run this command periodically to see VM disk I/O:"
echo "  # zpool iostat -v $POOL_NAME 5"
echo "  Look for zvols with consistent read activity"
echo ""
echo "Option 3 - By VM Type:"
echo "  Generally high I/O VMs:"
echo "  - Databases (PostgreSQL, MySQL, MongoDB)"
echo "  - Container hosts (Docker, Kubernetes)"
echo "  - Mail servers"
echo "  - File servers with active shares"
echo ""
echo "  Generally low I/O VMs:"
echo "  - Static web servers"
echo "  - Monitoring collectors"
echo "  - Batch processing (bursty, not constant)"
echo ""
echo "Suggested HOT_VMS configuration (customize for your setup):"
echo ""
echo HOT_VMS=( \
      "vm-201-disk-2" \
      "vm-202-disk-5" \
)

# List VMs as examples (commented out)
zfs list -r -t volume -o name "$VM_DATASET" 2>/dev/null | grep -v "^NAME$" | while read zvol; do
    zvol_name=$(basename "$zvol")
    echo "    # \"$zvol_name\"  # TODO: Uncomment if this is a hot VM"
done

echo ')'
echo ""
echo "USAGE:"
echo "1. Edit warm-cache.sh"
echo "2. Find the HOT_VMS=() section"
echo "3. Uncomment and add your 3-5 most active VMs"
echo "4. Start with fewer VMs, expand if cache warming is too slow"
echo ""
echo "Rule of thumb: Include 20-30% of your VMs that handle 70-80% of I/O"

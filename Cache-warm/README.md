# ZFS Cache Warming Toolkit

Accelerates L2ARC population after system reboots for Proxmox VE storage nodes.

## Problem Statement

Without persistent_l2arc support (unavailable in Proxmox VE 9.1), L2ARC is discarded on every reboot. This toolkit reduces the time to rebuild cache from weeks to days.

**Natural fill rate:** ~400GB/day (passive VM activity)  
**With warming:** ~800GB-1.2TB in first day

## Components

1. **warm-cache.sh** - Main cache warming script
2. **identify-hot-vms.sh** - Helper to identify which VMs to prioritize
3. **monitor-cache.sh** - Real-time cache growth monitoring
4. **zfs-cache-warm.service** - Optional systemd service for automatic warming

## Installation

### 1. Install Scripts

```bash
# Copy scripts to system location
sudo cp warm-cache.sh /usr/local/bin/
sudo cp identify-hot-vms.sh /usr/local/bin/
sudo cp monitor-cache.sh /usr/local/bin/

# Make executable
sudo chmod +x /usr/local/bin/warm-cache.sh
sudo chmod +x /usr/local/bin/identify-hot-vms.sh
sudo chmod +x /usr/local/bin/monitor-cache.sh
```

### 2. Configure Hot VMs

```bash
# Identify your hot VMs
sudo /usr/local/bin/identify-hot-vms.sh

# Edit warm-cache.sh to configure
sudo nano /usr/local/bin/warm-cache.sh
```

Find the `HOT_VMS=()` section and add your most active VMs:

```bash
HOT_VMS=(
    "vm-100-disk-0"  # Database server
    "vm-101-disk-0"  # Web application
    "vm-105-disk-0"  # Docker host
)
```

**Tip:** Start with 3-5 VMs that handle most of your I/O.

### 3. Test Configuration

```bash
# Verify pool and dataset names
sudo zpool list vmpool
sudo zfs list -t volume vmpool/iscsi-vms

# Verify hot VMs exist
for vm in vm-100-disk-0 vm-101-disk-0; do
    ls -lh /dev/zvol/vmpool/iscsi-vms/$vm
done
```

### 4. Optional: Enable Automatic Warming on Boot

```bash
# Install systemd service
sudo cp zfs-cache-warm.service /etc/systemd/system/

# Enable service
sudo systemctl daemon-reload
sudo systemctl enable zfs-cache-warm.service

# Check status
sudo systemctl status zfs-cache-warm.service
```

**Note:** Automatic warming starts after each reboot. Disable if you prefer manual control.

## Usage

### Manual Execution (Recommended for First Run)

```bash
# Run cache warming manually
sudo /usr/local/bin/warm-cache.sh

# Monitor in another terminal
sudo /usr/local/bin/monitor-cache.sh
```

Expected output:

```
=========================================
ZFS Cache Warming Script Starting
Pool: vmpool
VM Dataset: vmpool/iscsi-vms
Hot VMs: 3
=========================================
[2026-01-31 09:00:00] Checking prerequisites...
[2026-01-31 09:00:01] Prerequisites OK. Current L2ARC: 5GB
[2026-01-31 09:00:01] Boosting L2ARC fill rate...
[2026-01-31 09:00:02] Starting all VMs...
...
```

### Monitor Progress

```bash
# Real-time monitoring (updates every 60 seconds)
sudo /usr/local/bin/monitor-cache.sh

# Or specify custom interval
sudo /usr/local/bin/monitor-cache.sh 30  # Update every 30 seconds

# View logs
tail -f /var/log/zfs-cache-warm.log
tail -f /var/log/zfs-cache-warm-progress.log
```

### After Reboot Workflow

**Manual approach:**

```bash
# 1. System reboots for monthly maintenance
# 2. After reboot, run warming script
sudo /usr/local/bin/warm-cache.sh

# 3. Monitor progress
sudo /usr/local/bin/monitor-cache.sh

# 4. Check logs after 1 hour
sudo tail /var/log/zfs-cache-warm.log
```

**Automatic approach (if service enabled):**

```bash
# 1. System reboots
# 2. Service runs automatically
# 3. Check status
sudo systemctl status zfs-cache-warm.service

# 4. View logs
sudo journalctl -u zfs-cache-warm.service -f
```

## Configuration Options

Edit `/usr/local/bin/warm-cache.sh` to customize:

### Essential Configuration

```bash
# Pool and dataset names
POOL_NAME="vmpool"
VM_DATASET="vmpool/iscsi-vms"

# Hot VMs to warm directly
HOT_VMS=(
    "vm-100-disk-0"
    "vm-101-disk-0"
)
```

### Advanced Configuration

```bash
# Start all VMs automatically?
START_ALL_VMS=true  # Set to false for manual VM management

# L2ARC boost rate (increase for faster filling)
L2ARC_BOOST_RATE=134217728   # 128 MB/s (default: 32 MB/s)

# VM boot wait time
VM_BOOT_WAIT=300  # Seconds to wait for VMs to fully boot

# Skip warming if L2ARC already > this size
MIN_L2ARC_SIZE_GB=50  # Prevents re-running if cache already warm
```

## Expected Performance

### Without Cache Warming

```
Day 0 (reboot):   0GB L2ARC    - Poor performance
Day 1:            400GB         - Improving
Day 3:            800GB         - Acceptable
Day 7:            1.2TB         - Good
Day 14:           1.6TB         - Very good
Day 21:           1.8TB         - Excellent
```

### With Cache Warming

```
Hour 0 (start):   0GB L2ARC    - Script starts
Hour 1:           200-300GB    - Rapid improvement
Hour 4:           600-800GB    - Good performance restored
Day 1:            1.0-1.2TB    - Very good
Day 7:            1.6TB         - Excellent
Day 14:           1.8-1.9TB    - Peak capacity
```

**Result:** Cache reaches good performance in hours instead of days.

## Monitoring Cache Effectiveness

### Check Current Status

```bash
# Quick status
arc_summary | grep -A 3 "L2ARC size"

# Detailed statistics
arc_summary | grep -A 20 "L2ARC status"

# Pool I/O
zpool iostat -v vmpool 5
```

### Track Long-Term Growth

```bash
# View progress log (created by warm-cache.sh)
cat /var/log/zfs-cache-warm-progress.log

# Create graph data
grep "L2ARC:" /var/log/zfs-cache-warm-progress.log > l2arc-growth.csv
```

### Alert on Slow Growth

```bash
# Check if warming is working
# After 1 hour, should have >100GB
sudo /usr/local/bin/monitor-cache.sh 300 | grep -A 1 "$(date +%H)"
```

## Troubleshooting

### Cache Not Growing

**Check if script is running:**

```bash
ps aux | grep warm-cache
```

**Check logs for errors:**

```bash
tail -100 /var/log/zfs-cache-warm.log
```

**Verify L2ARC devices:**

```bash
zpool status -v vmpool | grep -A 5 cache
```

**Check L2ARC write rate:**

```bash
cat /sys/module/zfs/parameters/l2arc_write_max
# Should show 134217728 while warming
```

### VMs Not Starting

**Check VM configuration:**

```bash
qm list
qm status 100  # Check specific VM
```

**Check start-on-boot setting:**

```bash
qm config 100 | grep onboot
```

**Manual start if needed:**

```bash
qm start 100
```

### Hot VM zvols Not Found

**List available zvols:**

```bash
zfs list -t volume vmpool/iscsi-vms
ls -la /dev/zvol/vmpool/iscsi-vms/
```

**Update HOT_VMS configuration** to match actual zvol names.

### High Disk I/O Impact

**Lower cache warming priority:**

```bash
# Edit warm-cache.sh, change dd command to use ionice:
ionice -c 3 dd if=/dev/zvol/... of=/dev/null bs=1M
```

**Reduce L2ARC boost rate:**

```bash
# In warm-cache.sh configuration:
L2ARC_BOOST_RATE=67108864   # 64 MB/s instead of 128 MB/s
```

## Maintenance

### Monthly Workflow Integration

```bash
# Example monthly maintenance script
#!/bin/bash

# 1. Stop critical services
systemctl stop myapp

# 2. Run ZFS scrub (before reboot)
zpool scrub vmpool

# 3. Wait for scrub to complete
while zpool status vmpool | grep -q "scrub in progress"; do
    sleep 60
done

# 4. Apply updates
apt update && apt upgrade -y

# 5. Reboot
reboot

# After reboot:
# - Cache warming runs automatically (if service enabled)
# - Or run manually: /usr/local/bin/warm-cache.sh
```

### Disable Automatic Warming

```bash
# Disable service
sudo systemctl disable zfs-cache-warm.service
sudo systemctl stop zfs-cache-warm.service

# Run manually when needed
sudo /usr/local/bin/warm-cache.sh
```

### Uninstall

```bash
# Remove service
sudo systemctl disable zfs-cache-warm.service
sudo rm /etc/systemd/system/zfs-cache-warm.service
sudo systemctl daemon-reload

# Remove scripts
sudo rm /usr/local/bin/warm-cache.sh
sudo rm /usr/local/bin/identify-hot-vms.sh
sudo rm /usr/local/bin/monitor-cache.sh

# Remove logs
sudo rm /var/log/zfs-cache-warm*.log
```

## Advanced Tips

### Optimize for Specific Workloads

**Database-heavy (random reads):**

- Include all database VM disks in HOT_VMS
- These benefit most from cache

**Web servers (static content):**

- May not need aggressive warming
- Cache fills naturally from content serving

**Mixed workload:**

- Start with 3-5 most active VMs
- Monitor and expand if needed

### Reduce NVME Wear

**Use selective warming only:**

```bash
# Disable VM auto-start
START_ALL_VMS=false

# Manually start only critical VMs
qm start 100
qm start 101
```

**Lower boost rate:**

```bash
L2ARC_BOOST_RATE=67108864   # 64 MB/s (gentler on NVME)
```

### Integration with ZFSutilities

**Run warming after backup completion:**

```bash
# In your ZFSutilities backup script
# After daily backup succeeds:
if [[ -f /usr/local/bin/warm-cache.sh ]]; then
    /usr/local/bin/warm-cache.sh &
fi
```

## Performance Benchmarks

### Before Warming (Day 0 after reboot)

```
Metric              | Value
--------------------|--------
ARC Hit Rate        | 60%
L2ARC Hit Rate      | 0%
Disk Hits           | 40%
VM Boot Time        | Slow
Database Queries    | Slow
```

### After 1 Hour of Warming

```
Metric              | Value
--------------------|--------
ARC Hit Rate        | 60%
L2ARC Hit Rate      | 10-15%
Disk Hits           | 25-30%
VM Boot Time        | Better
Database Queries    | Improved
```

### After 24 Hours

```
Metric              | Value
--------------------|--------
ARC Hit Rate        | 60%
L2ARC Hit Rate      | 20-25%
Disk Hits           | 15-20%
VM Boot Time        | Normal
Database Queries    | Normal
```

## Safety Notes

- Script uses `nice` priority (low impact on system)
- Automatic restore of normal L2ARC fill rate on exit
- Safety check: skips warming if L2ARC already >50GB
- Can be interrupted with Ctrl+C (cleanup runs automatically)
- Logs all actions for audit trail

## Support

For issues or improvements:

1. Check logs: `/var/log/zfs-cache-warm.log`
2. Verify configuration in `/usr/local/bin/warm-cache.sh`
3. Test with minimal configuration first
4. Monitor with `monitor-cache.sh` during runs

## Version History

- v1.0 (2026-01-31): Initial release
  - Automatic VM start and warming
  - Hot VM selective warming
  - Progress monitoring
  - Systemd integration

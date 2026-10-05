# Phase 0 Report — Integrated Testing Environment

Date: 2026-10-04. All commands in this report were read-only; nothing on the base
systems was modified by the agent. Raw inventory output is saved alongside this
file (`inventory-zfstestvm1.txt`, `inventory-zfstestvm2.txt`).

## 1. Inventory summary

| Item | zfstestvm1 (10.0.0.28) | zfstestvm2 (10.0.0.81) |
|---|---|---|
| PVE / kernel | 9.2.2 / 7.0.2-6-pve | 9.2.21 / 7.0.14-20-pve |
| OS | Debian 13 trixie (13.5) | Debian 13 trixie (13.7) |
| vCPU | 4 (i7-12700 host CPU) | 4 |
| Nested virt | **works** (vmx exposed, kvm_intel loaded) | **works** |
| RAM | 3.8 GiB (2.3 available) | 3.8 GiB |
| Root FS | 23 G (17 G free) | 23 G (16 G free) |
| local-lvm thinpool | 14.7 G free | 14.7 G free |
| `local` dir storage | 23.9 G (17.8 G avail, iso content) | 23.9 G |
| Network | vmbr0 10.0.0.28/16 gw 10.0.0.1 | vmbr0 10.0.0.81/16 |
| Existing VMs / CTs | none / none | none / none |
| Pending updates | 183 packages | 0 |

Dev host: 10.0.0.127/16 on ens18 (same LAN), resolves both VM names.

Key facts driving the request below:

- **Nested virtualization already works on both base VMs** — no host CPU-type
  change is needed.
- **RAM is the hard blocker**: a Debian guest with ZFS (ARC), the GTK/xvfb GUI
  smoke, and the install-time MkDocs docs build wants ~8 GiB; the base PVE uses
  ~1.5 GiB. 3.8 GiB cannot host a guest.
- **Guest-disk space is the second blocker**: `local-lvm` has 14.7 GiB; cycle 1
  needs a 32 G guest system disk plus a ~100 G disk for the documented
  three-RAIDZ1 test-pool recipe (15 × 5 GiB partitions), plus snapshot space.
- Guest OS will be Debian stable (trixie), matching the base generation and the
  "minimal Debian + PVE" decision (PVE guest arrives with the two-node cycle).

## 2. Physical-resource request (applied by you, on the production host that runs the base VMs)

For **zfstestvm1** (cycle-1 target):

1. **RAM: 3.8 GiB → 12 GiB.** Reasoning: guest 8 GiB (ZFS ARC defaults to half
   of guest RAM; GUI smoke under xvfb; MkDocs build during install) + base PVE
   ~1.5 GiB + headroom. 16 GiB if convenient, but 12 suffices.
2. **Add a second virtual disk: 200 GiB** (any bus; virtio-scsi preferred).
   Reasoning: 20 GiB ISO library (Debian netinst ~0.8 GiB, PVE ISO ~2 GiB later,
   headroom) + ~171 GiB thin pool for guest disks (32 G system + 100 G pool-disk
   + snapshot/rollback space; thin-provisioned so overcommitted allocations are
   safe).
3. *(Optional)* **vCPU 4 → 6** — reduces guest install/docs-build cycle time;
   4 remains workable.

For **zfstestvm2**: nothing now. The two-node cycle will request the same
treatment (12 GiB + 200 GiB disk + its own isolated bridge) when it starts.

Ballooning: disable for the base VM (or set balloon 0) so the guest's memory is
guaranteed — the orchestrator pins guest memory too.

## 3. Manual steps (you apply; the orchestrator only verifies)

### 3a. On the production PVE host — resize zfstestvm1

Using the web UI or `qm set <zfstestvm1-vmid> --memory 12288 --balloon 0`
(plus `--cores 6` if adopting the optional CPU bump, and adding the 200 G disk).
Then reboot zfstestvm1 once so the new memory/disk are visible.

### 3b. On zfstestvm1 console, as root

**Optional but recommended first** — catch up on updates (183 packages; aligns
PVE 9.2.2 → current, matching zfstestvm2's 9.2.21):

```bash
apt-get update && apt-get dist-upgrade -y && reboot
```

**Verify the new disk's device name before partitioning** (`lsblk` — expected
`/dev/sdb`, ~200G; adjust below if different):

```bash
lsblk
apt-get install -y parted
parted -s /dev/sdb mklabel gpt
parted -s /dev/sdb mkpart itf-iso 1MiB 20GiB
parted -s /dev/sdb mkpart itf-guests 20GiB 100%
partprobe /dev/sdb
mkfs.ext4 -L itf-iso /dev/sdb1
mkdir -p /mnt/itf-iso
echo 'LABEL=itf-iso /mnt/itf-iso ext4 defaults 0 2' >> /etc/fstab
mount -a
pvcreate /dev/sdb2
vgcreate itfvg /dev/sdb2
lvcreate --type thin-pool -l 95%FREE -n itfthin itfvg
```

**Define the two confined storages** (this is the only /etc/pve write, done by
you; the orchestrator never edits storage.cfg):

```bash
cat >> /etc/pve/storage.cfg <<'EOF'

dir: itfiso
	path /mnt/itf-iso
	content iso

lvmthin: itfguests
	vgname itfvg
	thinpool itfthin
	content rootdir,images
EOF
```

(The two indented lines under each storage use TAB characters, matching PVE's
format.) Verify with `pvesm status` — expect `itfiso` and `itfguests` active.

**Isolated test bridge** (vmbr9, private 10.200.0.0/24, no physical port):

```bash
cat > /etc/network/interfaces.d/itf <<'EOF'
auto vmbr9
iface vmbr9 inet static
	address 10.200.0.1/24
	bridge-ports none
	bridge-stp off
	bridge-fd 0
EOF
ifreload -a
```

**Forwarding + NAT for guests** (guests reach dev/LAN directly; internet via
MASQUERADE), persistent across reboots:

```bash
cat > /etc/sysctl.d/99-itf-forward.conf <<'EOF'
net.ipv4.ip_forward=1
EOF
sysctl --system

cat > /etc/systemd/system/itf-nat.service <<'EOF'
[Unit]
Description=itf guest NAT (isolated test bridge vmbr9)
After=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/sbin/iptables -t nat -A POSTROUTING -s 10.200.0.0/24 ! -d 10.0.0.0/16 -j MASQUERADE
ExecStop=/usr/sbin/iptables -t nat -D POSTROUTING -s 10.200.0.0/24 ! -d 10.0.0.0/16 -j MASQUERADE

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload && systemctl enable --now itf-nat.service
```

**Orchestrator action log** (append-only audit trail of everything itf does on
this base system):

```bash
touch /var/log/itf-actions.log && chmod 644 /var/log/itf-actions.log
```

### 3c. On dev, as root (once)

Route the isolated guest subnet via zfstestvm1:

```bash
ip route add 10.200.0.0/24 via 10.0.0.28
```

To persist across reboots, add the route to the ens18 connection
(NetworkManager: `nmcli connection modify <ens18-conn> +ipv4.routes "10.200.0.0/24 10.0.0.28"`,
then reapply) or the equivalent for dev's network manager.

## 4. Confinement decision (recorded for the site config)

- **VMID range**: 8000–8099 on both base systems (both are empty today).
- **Storages**: guest disks on `itfguests` only; ISOs on `itfiso` only. The
  base's `local` and `local-lvm` are never written by the orchestrator.
- **Base-PVE mutations allowed to the orchestrator** (everything else refused
  by the guard wrapper): `qm` lifecycle commands scoped to VMIDs in range using
  the itf storages; writing `itf-*` files into `/mnt/itf-iso`; appending to
  `/var/log/itf-actions.log`. Never: storage.cfg, interfaces, systemd units,
  apt, or any VMID outside the range.
- **Audit**: every mutating base-PVE command is logged to
  `/var/log/itf-actions.log` with timestamp and full argv.
- **Recovery context**: the base VMs are ZFSutilities-managed guests with daily
  snapshots — the net behind the guardrails, not a substitute for them.

## 5. Next

1. You apply sections 2–3 and confirm; the orchestrator's `preflight` then
   verifies every item (RAM, storages, bridge, NAT, route, log) automatically.
2. Phase 1: build the `itf` orchestrator MVP in the dev repo (independent of
   the above — proceeds in parallel).
3. Phase 2: J01–J03 journeys on the first Debian guest.

## Addendum (2026-10-04, later) — network model corrected per user

The user clarified the intent for vmbr9: it is the **dedicated iSCSI
point-to-point link** for the two-node cycle (test-env equivalent of the
physical storage interconnect used in production), not a general guest
network. All management/preseed/download traffic uses the regular LAN:
guests attach to **vmbr0 and take DHCP from 10.0.0.1**.

Applied corrections on zfstestvm1:

- Removed `itf-nat.service`, `/etc/sysctl.d/99-itf-forward.conf`, and
  IP forwarding (no NAT is needed — guests reach the internet via the
  LAN gateway like any other host).
- vmbr9 demoted to a pure layer-2 bridge (`iface vmbr9 inet manual`,
  no address) — substrate reserved for the cycle-2 iSCSI link.
- The dev-side route from section 3c is **not needed** and was never
  applied.
- Orchestrator guest-IP discovery: DHCP leases mean dynamic addresses;
  the harness will read them via the qemu guest agent
  (`qm guest cmd <vmid> network-get-interfaces`), with the agent
  installed by preseed.

Open design point for the two-node cycle (decide then): a physical
point-to-point cannot run between guests on two different base VMs.
Candidates: a dedicated VLAN on the LAN switch carrying both vmbr9
bridges (closest to a private wire; switch config is user-owned), or
second NICs riding vmbr0's L2 with a private subnet (no switch change,
less faithful).

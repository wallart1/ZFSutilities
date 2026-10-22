#!/usr/bin/env bash
# validate-guestfs-probe — production validation for the Alignment view's
# guest-filesystem blocksize probing.
#
# Run as root ON THE STORAGE HOST of a two-node install (or on the single
# host): the probe reaches the compute node's `qm` over the same read-only
# `ssh root@<compute>` channel the GUI uses. Everything it executes is
# read-only — `qm guest ping`, `lsblk -bJ` and `stat -f` inside guests,
# zpool/zfs property reads, the PVE config fetch — and it writes nothing
# outside its scratch state dir.
#
#   validate-guestfs-probe [--self-check] [<python-dir>]
#
# --self-check  prove the plumbing without touching any host: the probe
#               chain runs against an inline scripted qm runner (no ssh,
#               no zfs, no root needed).
# <python-dir>  the deployment python/ tree to validate. Default: the
#               newest /usr/local/lib/zfsutilities/versions/<v>/python
#               carrying alignment_guestfs.py.
#
# Environment safety: the state migration is disabled and the state dir
# points at a scratch directory removed on exit (the migration-sweep
# hazard recorded in PREEXISTING.md — never run tooling against the live
# state dir by accident).

set -euo pipefail

base=/usr/local/lib/zfsutilities

die() { echo "validate-guestfs-probe: $*" >&2; exit 1; }
usage() {
    sed -n '2,21p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
}

self_check=0
case "${1:-}" in
    --self-check) self_check=1; shift ;;
    -h | --help) usage ;;
esac

if [[ $EUID -ne 0 && $self_check -eq 0 ]]; then
    die "run as root — the qm channel, /proc reads, and zfs need it"
fi

src_dir="${1:-}"
src_note=""
if [[ -z "$src_dir" ]]; then
    for v in $(find "$base/versions" -maxdepth 1 -mindepth 1 -type d -printf '%f\n' 2>/dev/null | sort -V); do
        if [[ -f "$base/versions/$v/python/alignment_guestfs.py" ]]; then
            src_dir="$base/versions/$v/python"
            src_note=" (deployed version $v)"
        fi
    done
    [[ -n "$src_dir" ]] || die "no deployed version carries alignment_guestfs.py; pass <python-dir>"
fi
[[ -f "$src_dir/alignment_guestfs.py" ]] || die "$src_dir has no alignment_guestfs.py"

state_dir="$(mktemp -d)"
trap 'rm -rf "$state_dir"' EXIT
export ZFSUTILITIES_DISABLE_MIGRATION=1
export ZFSUTILITIES_STATE_DIR="$state_dir"

echo "validate-guestfs-probe: source $src_dir$src_note"
python3 - "$src_dir" "$self_check" <<'PY'
import json
import sys
from types import SimpleNamespace

src, self_check = sys.argv[1], sys.argv[2] == "1"
sys.path.insert(0, src)

import alignment_guestfs as agfs  # noqa: E402
import alignment_stats as als  # noqa: E402
import node_config  # noqa: E402


def qm_exec(stdout, exitcode=0):
    payload = json.dumps({"exitcode": exitcode, "out": stdout, "err": ""})
    return SimpleNamespace(returncode=0, stdout=payload, stderr="")


if self_check:
    # One scripted guest: vdb (10G, whole-disk ext4 on /data) matched by
    # its storage-side signature, stat answering 4K — the wire shapes the
    # test-suite fixtures use. No host is touched.
    uuid_c = "73973a54-3a68-4925-98fa-89ae40630cbe"
    lsblk = json.dumps(
        {
            "blockdevices": [
                {
                    "name": "vdb",
                    "type": "disk",
                    "size": 10737418240,
                    "serial": "QM00002",
                    "uuid": uuid_c,
                    "fstype": "ext4",
                    "mountpoint": "/data",
                }
            ]
        }
    )

    def runner(argv, timeout):
        if "ping" in argv:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if "lsblk" in argv:
            return qm_exec(lsblk)
        if "stat" in argv:
            return qm_exec("4096\n")
        raise AssertionError(f"self-check: unexpected argv {argv}")

    config = {
        "mode": "single-node",
        "this_host": "box",
        "storage_host": "box",
        "compute_host": "box",
        "storage_ip": "",
        "pools": set(),
    }
    prober = agfs.GuestFsProber(config=config, runner=runner, ttl=0)
    volumes = [("201", "vm-201-disk-1", "virtio1", 10737418240, None, {uuid_c})]
    probe = prober.probe_volumes(volumes)["vm-201-disk-1"]
    assert probe.match_method == "signature", probe
    assert probe.entries and probe.entries[0].fstype == "ext4", probe
    assert probe.entries[0].blocksize == 4096 and probe.entries[0].mount == "/data", probe
    print("SELF-CHECK PASS: signature-tier match, ext4 4096 on /data")
    sys.exit(0)

# --- live validation -------------------------------------------------------
config = node_config.load_node_config()
print(
    f"node: mode={config.get('mode')} this={config.get('this_host')} "
    f"compute={config.get('compute_host')}"
)
prober = agfs.GuestFsProber(config=config)
sample = als.collect_alignment_sample(guest_prober=prober)
print(
    f"sample: pools={len(sample.pools)} datasets={len(sample.datasets)} "
    f"pve={'ok' if sample.pve_available else 'UNAVAILABLE'}"
)

targets = als._guest_probe_targets(sample.datasets, sample.vm_disks)
volblocks = {
    ds.name.rsplit("/", 1)[-1]: als.parse_zfs_size(ds.volblocksize or "")
    for ds in sample.datasets
    if ds.kind == "volume"
}
print(f"probe targets: {len(targets)}")
for vmid, short, bus, volsize, serial, sigs in sorted(targets, key=lambda t: (t[0], t[1])):
    probe = prober.probe_volumes([(vmid, short, bus, volsize, serial, sigs)]).get(short)
    evidence = []
    if serial:
        evidence.append(f"serial={serial}")
    if sigs:
        evidence.append(f"sigs={len(sigs)}")
    print(f"  vm-{vmid} {short} ({bus}, volsize={volsize}, {' '.join(evidence) or 'no tier-1/2 evidence'})")
    if probe is None:
        print("    no probe result")
        continue
    print(f"    match: {probe.match_method or 'NO MATCH'}")
    if probe.reason:
        print(f"    reason: {probe.reason}")
    vb = volblocks.get(short)
    for entry in probe.entries:
        verdict = ""
        if vb:
            verdict = (
                " WARN: below volblocksize (partial-block writes)"
                if entry.blocksize < vb
                else " ok vs volblocksize"
            )
        print(f"    {entry.fstype} {entry.blocksize} on {entry.mount}{verdict}")

print(f"integrated sample guest_fs: {len(sample.guest_fs)} probed, "
      f"{len(sample.guest_fs_failures)} degraded")
for short, entries in sorted(sample.guest_fs.items()):
    print(f"  {short}: " + ", ".join(f"{e.fstype} {e.blocksize} on {e.mount}" for e in entries))
for short, reason in sorted(sample.guest_fs_failures.items()):
    print(f"  {short}: {reason}")

import alignment_analysis as ana  # noqa: E402

rungs = 0
for ladder in ana.blocksize_ladder(sample):
    for bar in ladder.bars:
        if bar.layer in ("VM", "VM fs"):
            print(f"  ladder {ladder.pool}: {bar.label} [{bar.state}]")
            rungs += 1
print(f"guest-driven ladder rungs: {rungs}")
print("LIVE PASS" if rungs else "LIVE PASS (no guest rungs — check reasons above)")
PY

"""Tests for alignment_guestfs.py — guest-agent probing of VM volumes.

The prober is exercised against a scripted runner (no real ssh/qm): every
guest round-trip is asserted by argv shape, so the tests double as a
record of the wire protocol — ``qm guest ping`` availability, the single
``qm guest exec -- lsblk -bJ`` device-tree round-trip, and the batched
``stat -f`` call. The zvol↔guest-disk match chain (pinned serial →
UUID/PARTUUID signature intersection → size+bus fallback) is proven per
tier, including the clone-ambiguity guard.
"""

import json
import os
import subprocess
import sys
import unittest
from types import SimpleNamespace

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

import alignment_guestfs as agfs

# Guest lsblk -bJ tree: vda (32G) with an ext4 / and an xfs /var partition;
# vdb (10G) with a whole-disk ext4 /data. Serials are QEMU's per-process
# defaults (no serial= pinned in the config unless stated).
UUID_A = "03973a54-3a68-4925-98fa-89ae40630cbd"  # vda1 ext4
PART_A = "9e904afc-e1f2-48e2-a90b-6d91fd8780a5"
UUID_B = "25265b20-b9ca-493e-b44d-b56c6f695933"  # vda2 xfs
PART_B = "1e904afc-e1f2-48e2-a90b-6d91fd8780a6"
UUID_C = "73973a54-3a68-4925-98fa-89ae40630cbe"  # vdb whole-disk ext4
VOLSIZE_VDA = 34359738368
VOLSIZE_VDB = 10737418240

LSBLK_JSON = json.dumps(
    {
        "blockdevices": [
            {
                "name": "vda",
                "type": "disk",
                "size": VOLSIZE_VDA,
                "serial": "QM00001",
                "children": [
                    {
                        "name": "vda1",
                        "type": "part",
                        "size": 511705088,
                        "uuid": UUID_A,
                        "partuuid": PART_A,
                        "fstype": "ext4",
                        "mountpoint": "/",
                    },
                    {
                        "name": "vda2",
                        "type": "part",
                        "size": VOLSIZE_VDA - 511705088 - 1048576,
                        "uuid": UUID_B,
                        "partuuid": PART_B,
                        "fstype": "xfs",
                        "mountpoint": "/var",
                    },
                ],
            },
            {
                "name": "vdb",
                "type": "disk",
                "size": VOLSIZE_VDB,
                "serial": "QM00002",
                "uuid": UUID_C,
                "fstype": "ext4",
                "mountpoint": "/data",
            },
        ]
    }
)

# An LVM guest: one disk, one PV partition, one dm volume with the mount.
PV_UUID = "0RhmWD-V1AT-GAjI-MnZL-nyhJ-2LlY-fXPhL6"
FS_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
LSBLK_LVM_JSON = json.dumps(
    {
        "blockdevices": [
            {
                "name": "sda",
                "type": "disk",
                "size": VOLSIZE_VDA,
                "serial": "QM00001",
                "children": [
                    {
                        "name": "sda2",
                        "type": "part",
                        "uuid": PV_UUID,
                        "partuuid": PART_A,
                        "fstype": "LVM2_member",
                        "children": [
                            {
                                "name": "dm-0",
                                "type": "lvm",
                                "uuid": FS_UUID,
                                "fstype": "ext4",
                                "mountpoint": "/",
                            }
                        ],
                    }
                ],
            }
        ]
    }
)

SIG_DISK0 = {UUID_A, PART_A, UUID_B, PART_B}
SIG_DISK1 = {UUID_C}
SIG_LVM = {PV_UUID, PART_A, FS_UUID}

# stat -f -c %S output paired positionally with the mounts sent.
STAT_VDA = "4096\n4096\n"

TWO_NODE_STORAGE = {
    "mode": "two-node",
    "this_host": "stewie",
    "storage_host": "stewie",
    "compute_host": "tweety",
    "storage_ip": "",
    "pools": set(),
}
TWO_NODE_COMPUTE = dict(TWO_NODE_STORAGE, this_host="tweety")
SINGLE_NODE = {
    "mode": "single-node",
    "this_host": "box",
    "storage_host": "box",
    "compute_host": "box",
    "storage_ip": "",
    "pools": set(),
}


def _qm_exec(stdout, exitcode=0):
    """A successful qm guest exec CompletedProcess with *stdout* inside."""
    payload = json.dumps({"exitcode": exitcode, "out": stdout, "err": ""})
    return SimpleNamespace(returncode=0, stdout=payload, stderr="")


class ScriptedRunner:
    """Runner that answers each call from a queue of results and logs argv."""

    def __init__(self, results):
        self.results = list(results)
        self.argvs = []

    def __call__(self, argv, timeout):
        self.argvs.append(list(argv))
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _ok(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


GUEST_LSBLK_ARGS = [
    "lsblk",
    "-J",
    "-b",
    "-o",
    "NAME,UUID,PARTUUID,FSTYPE,MOUNTPOINT,SIZE,TYPE,SERIAL",
]


class TestParsers(unittest.TestCase):
    def test_parse_qm_exec_output(self):
        self.assertEqual(
            agfs.parse_qm_exec_output('{"exitcode": 0, "out": "hi\\n"}'),
            {"exitcode": 0, "out": "hi\n"},
        )
        self.assertIsNone(agfs.parse_qm_exec_output("not json"))
        self.assertIsNone(agfs.parse_qm_exec_output('["a", "list"]'))

    def test_parse_lsblk_json_builds_the_tree(self):
        disks = agfs.parse_lsblk_json(LSBLK_JSON)
        self.assertEqual([disk.name for disk in disks], ["vda", "vdb"])
        vda = disks[0]
        self.assertEqual(len(vda.children), 2)
        self.assertEqual(vda.signatures, {UUID_A, PART_A, UUID_B, PART_B})
        self.assertEqual(vda.local_mounts(), [("/", "ext4"), ("/var", "xfs")])
        self.assertEqual(disks[1].local_mounts(), [("/data", "ext4")])

    def test_parse_lsblk_json_lvm_attributes_dm_mounts(self):
        disks = agfs.parse_lsblk_json(LSBLK_LVM_JSON)
        disk = disks[0]
        # The PV UUID (tier-2 evidence) and the mounted fs UUID both
        # belong to the disk tree; the mount attributes through the dm
        # child instead of degrading as unattributable.
        self.assertEqual(disk.signatures, SIG_LVM)
        self.assertEqual(disk.local_mounts(), [("/", "ext4")])

    def test_parse_lsblk_json_malformed(self):
        self.assertEqual(agfs.parse_lsblk_json("not json"), [])
        self.assertEqual(agfs.parse_lsblk_json('{"blockdevices": "nope"}'), [])

    def test_parse_lsblk_json_decodes_mount_escapes(self):
        text = json.dumps(
            {
                "blockdevices": [
                    {
                        "name": "vda",
                        "type": "disk",
                        "size": 1,
                        "children": [
                            {
                                "name": "vda1",
                                "type": "part",
                                "fstype": "ext4",
                                "mountpoint": "/media/my\\x20disk",
                            }
                        ],
                    }
                ]
            }
        )
        disks = agfs.parse_lsblk_json(text)
        self.assertEqual(disks[0].local_mounts(), [("/media/my disk", "ext4")])

    def test_collect_zvol_signatures_reads_uuid_tokens(self):
        calls = []

        def runner(argv, timeout=None):
            calls.append(list(argv))
            if "vm-205-disk-3" in argv[-1]:
                return _ok(stdout=f"zd32\nzd32p1 {UUID_A} {PART_A}\n")
            return _ok(stdout=f"zd16 {UUID_C}\n")

        sigs = agfs.collect_zvol_signatures(
            ["/dev/zvol/NVME1/proxmox/vm-201-disk-3", "/dev/zvol/NVME1/proxmox/vm-205-disk-3"],
            runner=runner,
        )
        self.assertEqual(sigs["/dev/zvol/NVME1/proxmox/vm-201-disk-3"], {UUID_C})
        self.assertEqual(sigs["/dev/zvol/NVME1/proxmox/vm-205-disk-3"], {UUID_A, PART_A})
        self.assertEqual(calls[0][:3], ["lsblk", "-nr", "-o"])

    def test_collect_zvol_signatures_blank_and_failed(self):
        # Blank zvol: lsblk succeeds with bare names (no signatures).
        sigs = agfs.collect_zvol_signatures(
            ["/dev/zvol/p/blank"], runner=lambda a, timeout=None: _ok(stdout="zd48\n")
        )
        self.assertEqual(sigs["/dev/zvol/p/blank"], set())
        # Missing node: non-zero lsblk exit.
        sigs = agfs.collect_zvol_signatures(
            ["/dev/zvol/p/gone"], runner=lambda a, timeout=None: _ok(returncode=32)
        )
        self.assertEqual(sigs["/dev/zvol/p/gone"], set())

        def boom(_argv, _timeout=None):
            raise OSError("no lsblk")

        # Subprocess failure: still an entry, still empty.
        sigs = agfs.collect_zvol_signatures(["/dev/zvol/p/x"], runner=boom)
        self.assertEqual(sigs["/dev/zvol/p/x"], set())

    def test_expected_disk_name(self):
        self.assertEqual(agfs.expected_disk_name("virtio0"), "vda")
        self.assertEqual(agfs.expected_disk_name("virtio2"), "vdc")
        self.assertEqual(agfs.expected_disk_name("scsi1"), "sdb")
        self.assertEqual(agfs.expected_disk_name("sata0"), "sda")
        self.assertEqual(agfs.expected_disk_name("ide2"), "sdc")
        self.assertIsNone(agfs.expected_disk_name("usb0"))
        self.assertIsNone(agfs.expected_disk_name("virtio26"))

    def test_classify_agent_failure(self):
        self.assertEqual(agfs.classify_agent_failure("VM 201 not running"), "VM not running")
        self.assertEqual(
            agfs.classify_agent_failure("QEMU guest agent is not running"),
            "guest agent unavailable",
        )
        self.assertEqual(
            agfs.classify_agent_failure(" network unreachable"), "guest agent unreachable"
        )


class TestMatchVolumes(unittest.TestCase):
    """The three-tier zvol↔guest-disk chain (match_volumes)."""

    def setUp(self):
        self.disks = agfs.parse_lsblk_json(LSBLK_JSON)

    def _match(self, volumes):
        return agfs.match_volumes(self.disks, volumes)

    def test_signature_tier_matches_by_uuid_intersection(self):
        result = self._match([("vm-201-disk-0", "scsi0", VOLSIZE_VDA, None, SIG_DISK0)])
        disk, method, reason = result["vm-201-disk-0"]
        self.assertEqual((disk.name, method, reason), ("vda", "signature", None))

    def test_serial_tier_wins_when_pinned(self):
        result = self._match([("vm-201-disk-0", "scsi0", VOLSIZE_VDA, "QM00002", SIG_DISK0)])
        disk, method, _reason = result["vm-201-disk-0"]
        self.assertEqual((disk.name, method), ("vdb", "serial"))

    def test_without_serial_or_signature_size_bus_applies(self):
        # No pinned serial and no signatures: tier 1 is skipped even
        # though devices carry QEMU's per-process serials, and the
        # size+bus tier decides.
        result = self._match([("vm-201-disk-0", "scsi0", VOLSIZE_VDA, None, set())])
        disk, method, _reason = result["vm-201-disk-0"]
        self.assertEqual((disk.name, method), ("vda", "size+bus"))

    def test_clone_signatures_are_not_awarded(self):
        # Two volumes share one signature set (a cloned VM's disks) —
        # neither gets the signature match; sizes then separate them.
        result = self._match(
            [
                ("vm-201-disk-0", "scsi0", VOLSIZE_VDA, None, SIG_DISK0),
                ("vm-202-disk-0", "scsi0", VOLSIZE_VDB, None, SIG_DISK0),
            ]
        )
        disk0, method0, _reason0 = result["vm-201-disk-0"]
        disk1, method1, _reason1 = result["vm-202-disk-0"]
        self.assertEqual((disk0.name, method0), ("vda", "size+bus"))
        self.assertEqual((disk1.name, method1), ("vdb", "size+bus"))

    def test_same_size_clones_stay_ambiguous(self):
        # Identical clones of identical size: the positional tier would
        # have to award one device to both volumes — refused; the
        # ambiguity reason survives.
        result = self._match(
            [
                ("vm-201-disk-0", "scsi0", VOLSIZE_VDA, None, SIG_DISK0),
                ("vm-202-disk-0", "scsi1", VOLSIZE_VDA, None, SIG_DISK0),
            ]
        )
        for short in ("vm-201-disk-0", "vm-202-disk-0"):
            disk, method, reason = result[short]
            self.assertIsNone(disk)
            self.assertIsNone(method)
            self.assertIn("ambiguous", reason)

    def test_blank_zvol_falls_to_size_and_bus(self):
        result = self._match([("vm-201-disk-0", "virtio1", VOLSIZE_VDB, None, set())])
        disk, method, reason = result["vm-201-disk-0"]
        self.assertEqual((disk.name, method, reason), ("vdb", "size+bus", None))

    def test_no_match_reports_reason(self):
        result = self._match([("vm-201-disk-0", "scsi0", 999, None, set())])
        disk, method, reason = result["vm-201-disk-0"]
        self.assertIsNone(disk)
        self.assertIsNone(method)
        self.assertIn("no guest disk matches the volume size", reason)

    def test_unknown_volsize_reports_reason(self):
        result = self._match([("vm-201-disk-0", "scsi0", None, None, set())])
        self.assertIn("volume size unknown", result["vm-201-disk-0"][2])


class TestChannel(unittest.TestCase):
    def test_channel_ssh_for_two_node_storage(self):
        prober = agfs.GuestFsProber(config=TWO_NODE_STORAGE)
        self.assertEqual(prober.channel_argv(), ["ssh", *agfs.SSH_OPTS, "root@tweety"])

    def test_channel_local_on_compute_and_single_node(self):
        self.assertEqual(agfs.GuestFsProber(config=TWO_NODE_COMPUTE).channel_argv(), [])
        self.assertEqual(agfs.GuestFsProber(config=SINGLE_NODE).channel_argv(), [])


class TestProbeVolumes(unittest.TestCase):
    def _prober(self, results, config=SINGLE_NODE, now=None, ttl=agfs.CACHE_TTL):
        runner = ScriptedRunner(results)
        return agfs.GuestFsProber(config=config, runner=runner, now=now, ttl=ttl), runner

    def _volume(self, **overrides):
        fields = {
            "vmid": "201",
            "short": "vm-201-disk-0",
            "bus": "scsi0",
            "volsize": VOLSIZE_VDA,
            "serial": None,
            "signatures": SIG_DISK0,
        }
        fields.update(overrides)
        return (
            fields["vmid"],
            fields["short"],
            fields["bus"],
            fields["volsize"],
            fields["serial"],
            fields["signatures"],
        )

    def test_happy_path_probes_guest_filesystems(self):
        prober, runner = self._prober([_ok(), _qm_exec(LSBLK_JSON), _qm_exec(STAT_VDA)])
        results = prober.probe_volumes([self._volume()])
        probe = results["vm-201-disk-0"]
        self.assertEqual(
            [(e.mount, e.fstype, e.blocksize) for e in probe.entries],
            [("/", "ext4", 4096), ("/var", "xfs", 4096)],
        )
        self.assertIsNone(probe.reason)
        self.assertEqual(probe.match_method, "signature")
        # Wire shape: ping, ONE lsblk round-trip (no /proc/mounts), stat.
        self.assertEqual(len(runner.argvs), 3)
        self.assertEqual(runner.argvs[0], ["qm", "guest", "ping", "201"])
        self.assertEqual(
            runner.argvs[1],
            [
                "qm",
                "guest",
                "exec",
                "201",
                "--timeout",
                str(agfs.EXEC_TIMEOUT),
                "--",
                *GUEST_LSBLK_ARGS,
            ],
        )
        self.assertEqual(runner.argvs[2][-3:], ["%S", "/", "/var"])

    def test_lvm_mounts_attribute_through_dm(self):
        prober, runner = self._prober([_ok(), _qm_exec(LSBLK_LVM_JSON), _qm_exec("4096\n")])
        results = prober.probe_volumes([self._volume(signatures=SIG_LVM)])
        probe = results["vm-201-disk-0"]
        self.assertEqual(probe.match_method, "signature")
        self.assertEqual(
            [(e.mount, e.fstype, e.blocksize) for e in probe.entries],
            [("/", "ext4", 4096)],
        )
        self.assertEqual(runner.argvs[2][-2:], ["%S", "/"])

    def test_ssh_channel_prefixes_every_call(self):
        prober, runner = self._prober(
            [_ok(), _qm_exec(LSBLK_JSON), _qm_exec(STAT_VDA)],
            config=TWO_NODE_STORAGE,
        )
        prober.probe_volumes([self._volume()])
        prefix = ["ssh", *agfs.SSH_OPTS, "root@tweety"]
        self.assertTrue(all(argv[: len(prefix)] == prefix for argv in runner.argvs))

    def test_ping_failure_reasons_per_volume(self):
        prober, runner = self._prober([_ok(returncode=255, stdout="", stderr="VM 201 not running")])
        results = prober.probe_volumes([self._volume()])
        self.assertEqual(results["vm-201-disk-0"].reason, "VM not running")
        self.assertEqual(len(runner.argvs), 1)

    def test_agent_unavailable_reason(self):
        prober, _runner = self._prober(
            [_ok(returncode=255, stdout="", stderr="QEMU guest agent is not running")]
        )
        results = prober.probe_volumes([self._volume()])
        self.assertEqual(results["vm-201-disk-0"].reason, "guest agent unavailable")

    def test_command_failure_reason(self):
        prober, _runner = self._prober([OSError("qm missing")])
        results = prober.probe_volumes([self._volume()])
        self.assertEqual(results["vm-201-disk-0"].reason, "command failed")

    def test_guest_command_failure_reason(self):
        prober, _runner = self._prober([_ok(), _qm_exec("", exitcode=1)])
        results = prober.probe_volumes([self._volume()])
        self.assertEqual(results["vm-201-disk-0"].reason, "guest command failed")

    def test_unexpected_qm_output_reason(self):
        prober, _runner = self._prober([_ok(), _ok(stdout="plain text, not json")])
        results = prober.probe_volumes([self._volume()])
        self.assertEqual(results["vm-201-disk-0"].reason, "unexpected qm output")

    def test_unparsable_lsblk_reason(self):
        prober, _runner = self._prober([_ok(), _qm_exec("{oops")])
        results = prober.probe_volumes([self._volume()])
        self.assertEqual(results["vm-201-disk-0"].reason, "guest reported no block devices")

    def test_no_mounts_on_disk_reason(self):
        bare = json.dumps({"blockdevices": [{"name": "vda", "type": "disk", "size": VOLSIZE_VDA}]})
        prober, _runner = self._prober([_ok(), _qm_exec(bare)])
        results = prober.probe_volumes([self._volume(signatures=set())])
        self.assertIn("no filesystem from this disk is mounted", results["vm-201-disk-0"].reason)
        self.assertEqual(results["vm-201-disk-0"].match_method, "size+bus")

    def test_unsafe_mount_paths_are_skipped(self):
        escaped = json.dumps(
            {
                "blockdevices": [
                    {
                        "name": "vda",
                        "type": "disk",
                        "size": VOLSIZE_VDA,
                        "children": [
                            {
                                "name": "vda1",
                                "type": "part",
                                "fstype": "ext4",
                                "mountpoint": "/a\\x20b",
                            },
                            {
                                "name": "vda2",
                                "type": "part",
                                "fstype": "ext4",
                                "mountpoint": "/safe",
                            },
                        ],
                    }
                ]
            }
        )
        prober, runner = self._prober([_ok(), _qm_exec(escaped), _qm_exec("4096\n")])
        results = prober.probe_volumes([self._volume(signatures=set())])
        self.assertEqual(
            [(e.mount, e.blocksize) for e in results["vm-201-disk-0"].entries],
            [("/safe", 4096)],
        )
        self.assertEqual(runner.argvs[2][-2:], ["%S", "/safe"])

    def test_stat_garbage_degrades(self):
        prober, _runner = self._prober([_ok(), _qm_exec(LSBLK_JSON), _qm_exec("not-a-number\n")])
        results = prober.probe_volumes([self._volume()])
        self.assertEqual(results["vm-201-disk-0"].entries, [])
        self.assertEqual(
            results["vm-201-disk-0"].reason, "guest stat reported no usable block size"
        )

    def test_volumes_of_one_vm_share_round_trips(self):
        """Two disks of one VM: ping/lsblk once, one batched stat."""
        prober, runner = self._prober([_ok(), _qm_exec(LSBLK_JSON), _qm_exec("4096\n4096\n512\n")])
        results = prober.probe_volumes(
            [
                self._volume(),
                self._volume(
                    short="vm-201-disk-1",
                    bus="virtio1",
                    volsize=VOLSIZE_VDB,
                    signatures=SIG_DISK1,
                ),
            ]
        )
        self.assertEqual(len(runner.argvs), 3)
        self.assertEqual(runner.argvs[2][-4:], ["%S", "/", "/var", "/data"])
        self.assertEqual(
            [(e.mount, e.blocksize) for e in results["vm-201-disk-1"].entries],
            [("/data", 512)],
        )
        self.assertEqual(results["vm-201-disk-1"].match_method, "signature")

    def test_ttl_cache_skips_runner_within_window(self):
        clock = {"now": 100.0}
        prober, runner = self._prober(
            [_ok(), _qm_exec(LSBLK_JSON), _qm_exec(STAT_VDA)] * 2,
            now=lambda: clock["now"],
        )
        volume = self._volume()
        prober.probe_volumes([volume])
        self.assertEqual(len(runner.argvs), 3)
        prober.probe_volumes([volume])
        self.assertEqual(len(runner.argvs), 3)  # cached, no new calls
        clock["now"] += agfs.CACHE_TTL + 1
        prober.probe_volumes([volume])
        self.assertEqual(len(runner.argvs), 6)  # stale: re-probed

    def test_cache_keyed_by_volsize_change(self):
        prober, runner = self._prober([_ok(), _qm_exec(LSBLK_JSON), _qm_exec(STAT_VDA)] * 2)
        prober.probe_volumes([self._volume()])
        # A resized zvol is a different key: fresh probe despite the TTL.
        prober.probe_volumes([self._volume(volsize=VOLSIZE_VDA + 1)])
        self.assertEqual(len(runner.argvs), 6)

    def test_timeout_reason(self):
        prober, _runner = self._prober([subprocess.TimeoutExpired(cmd="qm", timeout=25)])
        results = prober.probe_volumes([self._volume()])
        self.assertEqual(results["vm-201-disk-0"].reason, "timeout")


if __name__ == "__main__":
    unittest.main()

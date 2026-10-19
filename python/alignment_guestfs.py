"""Guest filesystem blocksize probing for VM volumes (Alignment view).

A zvol's ``volblocksize`` only pays off when the filesystem the guest
keeps on that volume writes in blocks the volblock can carry whole: a
4 KiB guest filesystem under a 16 KiB volblock pays partial-block work
on every guest block write. That filesystem geometry is invisible from
the storage host — the zvol is just blocks — so this module asks the VM
itself through the QEMU guest agent, and first has to answer: *which*
guest block device is this zvol?

That mapping is resolved by a deterministic chain (see
``match_volumes``, in priority order):

1. **Pinned serial** — a ``serial=`` option on the PVE disk line is
   operator-chosen identity; the guest device reporting that SERIAL
   (lsblk reads it from udev) is the match, with certainty.
2. **Content signature** — UUID/PARTUUID intersection between the two
   ends of the wire. The storage host sees the zvol's own partitions
   through ``lsblk /dev/zvol/<pool>/<ds>`` (sysfs + udev, no device
   I/O, no root); the guest sees its devices' UUID/PARTUUIDs the same
   way. Filesystem UUIDs, GPT partition GUIDs (present even on
   unformatted partitions), LVM PV UUIDs, RAID member UUIDs, and swap
   UUIDs all cross the VM boundary unchanged, so the intersection
   identifies the device regardless of transport — no iSCSI LUNs, no
   bus-letter guessing, single-node and two-node alike. Cloned volumes
   share signatures; when the intersection is not unique the volume
   falls through with an explicit reason instead of guessing.
3. **Size + bus letter** — volsize equality (QEMU presents the zvol at
   exactly its size) with the PVE bus-letter convention
   (``virtio2`` → ``vdc``, ``scsi1``/``sata1`` → ``sdb``) as tiebreak.
   Last resort for signature-less (blank) zvols.

Per VM the probe runs ``qm guest ping`` (availability), one
``qm guest exec -- lsblk -bJ -o …`` (device tree with UUIDs, serials,
mountpoints — children included, so device-mapper/LVM mounts attribute
to their parent disk), and one batched
``qm guest exec -- stat -f -c %S <mount…>`` for the filesystem block
sizes. On two-node installs every ``qm`` invocation is wrapped in
``ssh root@<compute host>`` — the same read-only channel the dashboard
and Proxmox enrollment use. When the GUI host is the compute node the
commands run locally.

The module is pure subprocess with no GTK. Every failure degrades per
volume with a short reason (agent absent, VM stopped, disk not matched,
ambiguous clone signatures, non-Linux guest): probing never fails the
sample that carries it. Results are cached per (vmid, volume, volsize)
with a TTL because guest filesystem geometry is quasi-static — the
1-300 s page refresh must not re-probe every cycle.
"""

import json
import re
import subprocess
import time
from dataclasses import dataclass, field

import node_config

# ssh options for the compute-node channel, matching proxmox_enroll (the
# dashboard/pvesm read-only precedent): BatchMode never prompts, so a
# missing key just fails fast.
SSH_OPTS = ["-o", "ConnectTimeout=5", "-o", "BatchMode=yes"]

# Seconds the guest agent may take per command (``qm guest exec --timeout``)
# and seconds the subprocess wrapper waits for the whole ``qm``/ssh call.
EXEC_TIMEOUT = 15
RUN_TIMEOUT = 25

# Guest filesystem geometry changes about as often as filesystems are
# recreated; probe results are reused within this window (seconds).
CACHE_TTL = 600

# fstype allowlist for mounts whose block size stat -f can report. Pseudo
# and network filesystems are excluded; LVM2_member members carry the PV
# UUID for matching but the mount itself sits on the dm child above them.
LOCAL_FSTYPES = frozenset(
    {"ext2", "ext3", "ext4", "xfs", "btrfs", "f2fs", "zfs", "ntfs", "ntfs3", "exfat", "vfat"}
)

# Timeout for the storage-host lsblk reads of /dev/zvol signatures.
LSBLK_TIMEOUT = 10

# Regex: [\s;&|<>(){}\[\]*?"'`\\$#~]
# Purpose: Match any token the remote shell would re-parse on the ssh path
#          (ssh joins argv with spaces) — a mount path carrying one is
#          refused rather than risk a misquote. lsblk prints blanks as
#          \xNN escapes in JSON, so whitespace is included.
# (character class only; no groups)
_UNSAFE_TOKEN_RE = re.compile(r"""[\s;&|<>(){}\[\]*?"'`\\$#~]""")


@dataclass
class GuestDisk:
    """One device node of the guest's ``lsblk -bJ`` tree."""

    name: str
    dtype: str = ""
    size: int | None = None
    serial: str | None = None
    uuid: str | None = None
    partuuid: str | None = None
    fstype: str | None = None
    mountpoint: str | None = None
    children: list["GuestDisk"] = field(default_factory=list)

    @property
    def signatures(self):
        """UUID/PARTUUID set of this device and everything above it."""
        found = set()
        if self.uuid:
            found.add(self.uuid)
        if self.partuuid:
            found.add(self.partuuid)
        for child in self.children:
            found |= child.signatures
        return found

    def local_mounts(self):
        """``(mountpoint, fstype)`` pairs on local filesystems in this tree
        (the device itself or any descendant — partitions, dm/LVM, crypt)."""
        mounts = []
        if self.fstype in LOCAL_FSTYPES and self.mountpoint:
            mounts.append((self.mountpoint, self.fstype))
        for child in self.children:
            mounts.extend(child.local_mounts())
        return mounts


@dataclass
class GuestFsEntry:
    """One guest filesystem on a probed volume."""

    mount: str
    fstype: str
    blocksize: int


@dataclass
class GuestFsProbe:
    """Probe outcome for one volume: entries, or a reason they are absent.

    ``match_method`` names the chain tier that identified the guest disk:
    ``"serial"``, ``"signature"``, ``"size+bus"`` — or ``None`` when no
    disk was matched at all.
    """

    entries: list[GuestFsEntry] = field(default_factory=list)
    reason: str | None = None
    match_method: str | None = None


def parse_qm_exec_output(text):
    """Parse ``qm guest exec`` stdout into its result dict, or None.

    PVE prints the agent result as one JSON object (``exitcode`` plus
    ``out``/``err`` when the command produced output). None means the
    output was not JSON — an older/plain printer or an error page.
    """
    try:
        parsed = json.loads(text.strip())
    except (ValueError, AttributeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _decode_mount(raw):
    """Decode lsblk's \\xNN / \\uNNN escapes in a mountpoint string."""
    if not raw:
        return raw
    try:
        return bytes(raw, "utf-8").decode("unicode_escape")
    except (UnicodeDecodeError, ValueError):
        return raw


def _disk_from_lsblk(node):
    """Build one GuestDisk (recursively) from an lsblk -J device node."""
    children = [_disk_from_lsblk(child) for child in (node.get("children") or [])]
    size = node.get("size")
    try:
        size = int(size) if size is not None else None
    except (TypeError, ValueError):
        size = None
    mountpoint = node.get("mountpoint")
    # Nested lsblk JSON (mountpoints list form on newer util-linux) is not
    # needed here; take the plain string when present.
    if not isinstance(mountpoint, str):
        mountpoint = None
    return GuestDisk(
        name=str(node.get("name") or ""),
        dtype=str(node.get("type") or ""),
        size=size,
        serial=node.get("serial") if isinstance(node.get("serial"), str) else None,
        uuid=node.get("uuid") if isinstance(node.get("uuid"), str) else None,
        partuuid=node.get("partuuid") if isinstance(node.get("partuuid"), str) else None,
        fstype=node.get("fstype") if isinstance(node.get("fstype"), str) else None,
        mountpoint=_decode_mount(mountpoint),
        children=children,
    )


def parse_lsblk_json(text):
    """Parse ``lsblk -bJ`` output into the top-level ``GuestDisk`` tree.

    Malformed input yields an empty list — the caller degrades per VM.
    """
    try:
        parsed = json.loads(text)
    except (ValueError, AttributeError):
        return []
    devices = parsed.get("blockdevices") if isinstance(parsed, dict) else None
    if not isinstance(devices, list):
        return []
    return [_disk_from_lsblk(node) for node in devices if isinstance(node, dict)]


def collect_zvol_signatures(paths, runner=None, timeout=LSBLK_TIMEOUT):
    """Read each zvol's UUID/PARTUUID signature set on the storage host.

    One ``lsblk -nr -o NAME,UUID,PARTUUID /dev/zvol/<pool>/<ds>`` per path:
    the kernel's partition scan of the zvol plus the udev database answer
    without device I/O and without root, so this is safe against a
    concurrently running VM. Blank zvols (no partition table, no
    filesystem) yield an empty set — tier 3 of the match chain applies.
    Failures (missing node, unreadable) also yield empty sets; the map
    always contains an entry (possibly empty) for every requested path.
    """
    if runner is None:

        def runner(argv, t):
            return subprocess.run(argv, capture_output=True, text=True, timeout=t, check=False)

    signatures = {}
    for path in paths:
        found = set()
        try:
            result = runner(["lsblk", "-nr", "-o", "NAME,UUID,PARTUUID", path], timeout)
        except (OSError, subprocess.SubprocessError):
            signatures[path] = found
            continue
        if result.returncode == 0:
            for line in (result.stdout or "").splitlines():
                for token in line.split()[1:]:
                    if token:
                        found.add(token)
        signatures[path] = found
    return signatures


def expected_disk_name(bus):
    r"""Guest disk name the PVE bus line conventionally maps to, or None.

    ``virtio<n>`` drives appear as ``vd<letter>``; ``scsi<n>``/``sata<n>``
    as ``sd<letter>`` (SCSI via virtio-scsi, SATA via ahci — both sd*).
    ``ide<n>`` disks reach modern guests through libata as ``sd<letter>``
    too. The mapping is positional (n → nth letter), which holds for the
    per-bus families; mixed scsi+sata enumeration order is exactly why
    this is only the tier-3 tiebreak and the signatures decide.

    Regex: ^(virtio|scsi|sata|ide)(\d+)$
    Purpose: Split a PVE bus line into family and index for that mapping.
    Group 1: the bus family    e.g. "virtio", "scsi"
    Group 2: the bus index     e.g. "0", "2"
    """
    match = re.match(r"^(virtio|scsi|sata|ide)(\d+)$", bus or "")
    if match is None:
        return None
    index = int(match.group(2))
    if index > 25:
        return None
    prefix = "vd" if match.group(1) == "virtio" else "sd"
    return f"{prefix}{chr(ord('a') + index)}"


def _match_by_serial(disks, serial):
    """Tier 1: the top-level guest disk whose SERIAL is the pinned one."""
    for disk in disks:
        if disk.serial == serial:
            return disk
    return None


def _match_by_signature(disks, signatures):
    """Tier 2 candidates: devices whose tree signatures intersect."""
    return [disk for disk in disks if disk.signatures & signatures]


def _match_by_size_and_bus(disks, volsize, bus):
    """Tier 3: volsize equality, bus-letter tiebreak (legacy heuristic)."""
    if not volsize:
        return None, "volume size unknown on the storage side"
    candidates = sorted(
        disk.name for disk in disks if disk.dtype == "disk" and disk.size == volsize
    )
    if not candidates:
        return None, "no guest disk matches the volume size"
    if len(candidates) > 1:
        expected = expected_disk_name(bus)
        by_name = {disk.name: disk for disk in disks}
        if expected in candidates:
            return by_name[expected], None
        return None, "several guest disks match the volume size"
    by_name = {disk.name: disk for disk in disks}
    return by_name[candidates[0]], None


def match_volumes(disks, volumes):
    """Resolve the zvol↔guest-disk mapping for one VM's volume batch.

    *volumes* is a list of ``(short_name, bus, volsize, serial,
    signatures)`` tuples (serial may be None; signatures is the
    storage-side UUID/PARTUUID set, possibly empty). Returns
    ``{short_name: (GuestDisk-or-None, method-or-None, reason-or-None)}``
    applying the chain tiers with cross-volume uniqueness: a guest device
    whose signature evidence is shared by two volumes (clones) is not
    awarded to either — both fall through with an ambiguity reason.
    """
    results = {}
    # Tier 1: pinned serials are unique by construction.
    for short, _bus, _volsize, serial, _sigs in volumes:
        if serial:
            disk = _match_by_serial(disks, serial)
            if disk is not None:
                results[short] = (disk, "serial", None)
    # Tier 2: signature intersection with cross-volume uniqueness. A
    # device evidenced by more than one volume (clone-identical
    # signatures) is awarded to neither — the intersection cannot tell
    # the original from the copy, so first-volumes wins would be a coin
    # flip. Volumes with a single-device match on an unshared device
    # claim it; the rest fall through with the ambiguity reason.
    signature_matches: dict[str, list[GuestDisk]] = {}
    for short, _bus, _volsize, _serial, signatures in volumes:
        if short in results or not signatures:
            continue
        signature_matches[short] = _match_by_signature(disks, signatures)
    device_evidence: dict[int, int] = {}
    for devices in signature_matches.values():
        for disk in devices:
            device_evidence[id(disk)] = device_evidence.get(id(disk), 0) + 1
    for short, devices in signature_matches.items():
        if len(devices) == 1 and device_evidence[id(devices[0])] == 1:
            results[short] = (devices[0], "signature", None)
        elif devices:
            results[short] = (
                None,
                None,
                "guest disk ambiguous (clone-identical filesystem signatures?)",
            )
    # Tier 3: size + bus letter for whatever is left (blank zvols, or a
    # signature ambiguity that position may still resolve — the ambiguity
    # reason survives only when position cannot). A device is awarded
    # positionally only when exactly one leftover volume maps to it:
    # same-size clones mapping onto one disk are the same coin flip the
    # signature tier refuses.
    positional: dict[str, tuple] = {}
    device_demand: dict[int, list[str]] = {}
    for short, bus, volsize, _serial, _sigs in volumes:
        if short in results and results[short][1] is not None:
            continue
        disk, reason = _match_by_size_and_bus(disks, volsize, bus)
        positional[short] = (disk, reason)
        if disk is not None:
            device_demand.setdefault(id(disk), []).append(short)
    for short, (disk, reason) in positional.items():
        if disk is not None and device_demand[id(disk)] == [short]:
            results[short] = (disk, "size+bus", None)
        else:
            # Keep a prior ambiguity reason when position cannot resolve
            # either — it explains the situation better than the size
            # miss ("a disk DID match, its signatures were shared").
            prior = results.get(short)
            results[short] = (
                None,
                None,
                (prior[2] if prior else None) or reason or "guest disk ambiguous",
            )
    return results


def classify_agent_failure(stderr):
    """Short reason string for a failed ``qm guest ping``."""
    text = (stderr or "").lower()
    # "agent" first: the agent-down error also says "not running", and
    # the sharper reason wins.
    if "agent" in text or "guest" in text:
        return "guest agent unavailable"
    if "not running" in text or "is not running" in text:
        return "VM not running"
    return "guest agent unreachable"


def _decode_exec(result):
    """Validate one qm guest exec result dict; ``(out, None)`` or reason."""
    if not isinstance(result, dict):
        return None, "unexpected qm output"
    if result.get("exitcode") not in (0, "0"):
        return None, "guest command failed"
    out = result.get("out")
    if not isinstance(out, str):
        return None, "unexpected qm output"
    return out, None


class GuestFsProber:
    """Probe guest filesystem blocksizes for VM volumes, with a TTL cache.

    *config* is a node-config dict (``node_config.load_node_config``
    shape); None loads it here. *runner* executes argv lists —
    ``runner(argv, timeout) -> CompletedProcess`` — and defaults to a
    ``subprocess.run`` wrapper, so tests can script the guest side.
    *now* is the cache clock (``time.monotonic`` by default).
    """

    def __init__(self, config=None, runner=None, now=None, ttl=CACHE_TTL):
        self._config = config
        self._runner = runner or self._subprocess_run
        self._now = now or time.monotonic
        self._ttl = ttl
        self._cache: dict[tuple, tuple[float, GuestFsProbe]] = {}
        self._channel = None

    @staticmethod
    def _subprocess_run(argv, timeout):
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)

    def channel_argv(self):
        """argv prefix reaching ``qm``: ssh to the compute host, or local.

        Same rule as pvesm/pveversion reads: two-node installs reach the
        compute node over ``ssh root@<host>``; when this host *is* the
        compute node (single-node, or the GUI on the compute side) the
        commands run locally.
        """
        if self._channel is None:
            config = self._config if self._config is not None else node_config.load_node_config()
            host = config.get("compute_host") or ""
            if config.get("mode") == "two-node" and host and config.get("this_host") != host:
                self._channel = ["ssh", *SSH_OPTS, f"root@{host}"]
            else:
                self._channel = []
        return list(self._channel)

    def _run(self, argv):
        """Run argv through the channel; ``(stdout, None)`` or reason."""
        try:
            result = self._runner([*self.channel_argv(), *argv], timeout=RUN_TIMEOUT)
        except subprocess.TimeoutExpired:
            return None, "timeout"
        except (OSError, subprocess.SubprocessError):
            return None, "command failed"
        if result.returncode != 0:
            return None, classify_agent_failure(getattr(result, "stderr", "") or "")
        return result.stdout, None

    def _guest_exec(self, vmid, argv):
        """Run one command inside the guest; ``(stdout, None)`` or reason."""
        full = ["qm", "guest", "exec", str(vmid), "--timeout", str(EXEC_TIMEOUT), "--", *argv]
        stdout, reason = self._run(full)
        if reason is not None:
            return None, reason
        out, reason = _decode_exec(parse_qm_exec_output(stdout or ""))
        return out, reason

    def probe_volumes(self, volumes):
        """Probe a batch of volumes: ``{short_name: GuestFsProbe}``.

        *volumes* is an iterable of ``(vmid, short_name, bus, volsize,
        serial, signatures)`` tuples (volsize in bytes or None; serial
        from the PVE disk line or None; signatures the storage-side
        UUID/PARTUUID set, possibly empty). Volumes sharing a vmid share
        that VM's lsblk round-trip and one batched ``stat`` call. Fresh
        results populate the TTL cache; cached ones are reused, so
        steady-state refreshes cost no subprocesses.
        """
        results = {}
        by_vmid: dict[str, list] = {}
        for vmid, short, bus, volsize, serial, signatures in volumes:
            key = (str(vmid), short, volsize)
            cached = self._cache.get(key)
            if cached is not None and self._now() - cached[0] < self._ttl:
                results[short] = cached[1]
                continue
            by_vmid.setdefault(str(vmid), []).append((short, bus, volsize, serial, signatures))
        for vmid, group in by_vmid.items():
            for short, probe in self._probe_vm(vmid, group).items():
                results[short] = probe
                fields = next(v for v in group if v[0] == short)
                self._cache[(vmid, short, fields[2])] = (self._now(), probe)
        return results

    def _probe_vm(self, vmid, group):
        """Probe one VM's volumes: one lsblk round-trip, one batched stat."""
        _stdout, reason = self._run(["qm", "guest", "ping", str(vmid)])
        if reason is not None:
            return {short: GuestFsProbe(reason=reason) for short, *_rest in group}
        out, reason = self._guest_exec(
            vmid,
            ["lsblk", "-J", "-b", "-o", "NAME,UUID,PARTUUID,FSTYPE,MOUNTPOINT,SIZE,TYPE,SERIAL"],
        )
        if reason is not None:
            return {short: GuestFsProbe(reason=reason) for short, *_rest in group}
        disks = parse_lsblk_json(out)
        if not disks:
            return {
                short: GuestFsProbe(reason="guest reported no block devices")
                for short, *_rest in group
            }

        results = {}
        stat_mounts = []  # (short, mount, fstype) — one batched stat call
        matches = match_volumes(disks, group)
        for short, disk, method, reason in (
            (short, match[0], match[1], match[2]) for short, match in matches.items()
        ):
            if disk is None:
                results[short] = GuestFsProbe(reason=reason or "no guest disk matched")
                continue
            mounts = disk.local_mounts()
            if not mounts:
                results[short] = GuestFsProbe(
                    match_method=method,
                    reason="no filesystem from this disk is mounted in the guest",
                )
                continue
            safe = [
                (short, mount, fstype)
                for mount, fstype in mounts
                if not _UNSAFE_TOKEN_RE.search(mount)
            ]
            if not safe:
                results[short] = GuestFsProbe(
                    match_method=method, reason="mount path not probe-safe"
                )
                continue
            stat_mounts.extend(safe)
            results[short] = GuestFsProbe(match_method=method)

        if not stat_mounts:
            return results
        out, reason = self._guest_exec(
            vmid, ["stat", "-f", "-c", "%S", *[m for _s, m, _f in stat_mounts]]
        )
        if reason is not None:
            for short, _mount, _fstype in stat_mounts:
                results[short] = GuestFsProbe(
                    match_method=results[short].match_method, reason=reason
                )
            return results
        sizes = [line.strip() for line in out.splitlines()]
        for (short, mount, fstype), size in zip(stat_mounts, sizes):
            if not size.isdigit() or not 512 <= int(size) <= 1024**3:
                continue
            entry = GuestFsEntry(mount=mount, fstype=fstype, blocksize=int(size))
            results.setdefault(short, GuestFsProbe()).entries.append(entry)
        # Every volume that sent mounts must come back with a verdict —
        # including one whose every stat line was unusable.
        for short, _mount, _fstype in stat_mounts:
            probe = results.setdefault(short, GuestFsProbe())
            if not probe.entries and probe.reason is None:
                probe.reason = "guest stat reported no usable block size"
        return results

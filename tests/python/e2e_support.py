"""e2e_support — shared machinery for GUI-payload end-to-end exercises.

Two frontends drive the same scenario matrix against real ZFS pools:

- ``tests/python/test_offsite_e2e.py`` and ``tests/python/test_backup_payload_e2e.py``
  run scenarios through the REAL BackupRunner (GLib main loop, pty stdin,
  input-hold protocol) — the exact engine the GUI uses.
- ``tests/integrated/e2e/payload-e2e-driver.py`` is a stdlib-only driver run
  inside ITF guests through PtyExecutor, which replicates BackupRunner's
  documented spawn semantics (pty stdin with echo off, merged
  stdout/stderr pipes, ``ZFSUTILITIES_LOG_INHERIT``/``ZFSUTILITIES_INPUT_HOLD``
  environment, marker interception).  Unprivileged containers cannot mutate
  ZFS (all dataset ioctls need CAP_SYS_ADMIN), so the guest is the
  full-matrix context; the container covers the dry-run and mechanics layer.

This module must stay stdlib-only so the guest driver can import it.
The scenario names and their capability level (``none`` / ``read`` /
``mutation``) are the single source of truth for both frontends.

Safety: scenarios only ever create and destroy datasets whose names start
with the per-run ``test-e2e`` prefix inside the allow-listed test pools
(zfstest1/2/3).  Pool structure and every pre-existing dataset are
untouched, and each scenario verifies it left nothing behind.
"""

from __future__ import annotations

import os
import pty
import re
import select
import shlex
import shutil
import signal
import subprocess
import sys
import termios
import time
import uuid as uuidlib
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Repo layout (works from pytest and from the guest driver alike)
# ---------------------------------------------------------------------------

E2E_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.realpath(os.path.join(E2E_DIR, "..", ".."))
PYTHON_DIR = os.path.join(REPO_ROOT, "python")
BIN_DIR = os.path.join(REPO_ROOT, "bin")

if PYTHON_DIR not in sys.path:
    sys.path.insert(0, PYTHON_DIR)

# Repo modules used to build payloads.  The whole import chain of these
# three is stdlib-only, which is what lets the guest driver import them.
import command_builders
import offsite_runner
from command_builders import BashStep

TEST_POOLS = ("zfstest1", "zfstest2", "zfstest3")
DATASET_PREFIX = "test-e2e"

# Signatures that must never appear in a payload run: each is either a
# strict-mode abort, a missing helper, or a bash-level failure that the
# orchestrators are supposed to catch and report as clean FATALs instead.
STRICT_SIGNATURES = (
    "unbound variable",
    "unboundVariable",
    "command not found",
    "syntax error",
    "not found (program not found)",
    "No such file or directory",
)

# Input-hold protocol marker lines emitted by GUI bash payloads when
# ZFSUTILITIES_INPUT_HOLD=Y (see PtyExecutor's docstring): the payload
# prints "ZFSU-INPUT-REQ|<prompt>|[detail]" when it needs input and
# "ZFSU-INPUT-ACK|<prompt>|[detail]" once the reply is consumed.  The
# pattern anchors on the literal "ZFSU-INPUT-" prefix, captures the kind
# (REQ or ACK), then the pipe-delimited prompt id ([^|]+ so the id can
# never swallow a delimiter), then an optional third field (.*, free
# text, possibly empty).  Used with .search(), not .match(): a raw
# `read -rp` prompt prints without a trailing newline, so a marker can
# arrive glued to preceding prompt text on the same line.
_INPUT_MARKER_RE = re.compile(r"ZFSU-INPUT-(REQ|ACK)\|([^|]+)(?:\|(.*))?")


class E2EError(AssertionError):
    """Scenario assertion failure; the message is the report line."""


# ---------------------------------------------------------------------------
# Process helpers (thin subprocess wrappers, always captured)
# ---------------------------------------------------------------------------


def _run(cmd, check=True, timeout=120):
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise E2EError(f"{shlex.join(cmd)} could not run: {exc}") from exc
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise E2EError(f"{shlex.join(cmd)} failed rc={proc.returncode}: {detail[:500]}")
    return proc


def zfs(*args, check=True, timeout=120):
    return _run(["zfs", *args], check=check, timeout=timeout)


def zpool(*args, check=True, timeout=120):
    return _run(["zpool", *args], check=check, timeout=timeout)


# ---------------------------------------------------------------------------
# Capability detection
# ---------------------------------------------------------------------------


def euid_is_root():
    return os.geteuid() == 0


def zfs_tools_available():
    return bool(shutil.which("zfs")) and bool(shutil.which("zpool"))


def pools_online(names=TEST_POOLS):
    if not zfs_tools_available():
        return False
    proc = zpool("list", "-H", "-o", "name", check=False)
    if proc.returncode != 0:
        return False
    online = set(proc.stdout.split())
    return all(name in online for name in names)


_read_capable_cache = None
_mutation_capable_cache = None


def read_capable():
    """Root + zfs + the three test pools online (payload rootcheck needs root)."""
    global _read_capable_cache
    if _read_capable_cache is None:
        _read_capable_cache = euid_is_root() and pools_online()
    return _read_capable_cache


def mutation_capable():
    """True when dataset mutations are permitted (privileged context).

    Probed once by creating and destroying a canmount=off dataset inside
    zfstest1.  In an unprivileged container the create fails cleanly with
    EPERM and nothing is left behind.
    """
    global _mutation_capable_cache
    if _mutation_capable_cache is not None:
        return _mutation_capable_cache
    _mutation_capable_cache = False
    if not read_capable():
        return False
    probe = f"{TEST_POOLS[0]}/{DATASET_PREFIX}-cap-{os.getpid()}-{uuidlib.uuid4().hex[:6]}"
    if zfs("list", "-H", "-o", "name", probe, check=False).returncode == 0:
        return False  # name collision should be impossible; refuse to touch it
    if zfs("create", "-o", "canmount=off", probe, check=False).returncode != 0:
        return False
    _mutation_capable_cache = zfs("destroy", "-r", probe, check=False).returncode == 0
    return _mutation_capable_cache


# ---------------------------------------------------------------------------
# Dataset registry — every dataset a scenario touches is registered here
# ---------------------------------------------------------------------------


class DatasetRegistry:
    """Creates and tracks test datasets; cleanup destroys in reverse order."""

    def __init__(self, run_id=None):
        self.run_id = run_id or "{}-{}-{}".format(
            time.strftime("%Y%m%d%H%M%S"), os.getpid(), uuidlib.uuid4().hex[:6]
        )
        self._created = []  # creation order
        self._destroyed = False

    # -- naming ----------------------------------------------------------

    def name(self, pool, *parts):
        if pool not in TEST_POOLS:
            raise E2EError(f"pool {pool!r} is not in the e2e allow-list {TEST_POOLS}")
        return "/".join((pool, DATASET_PREFIX + "-" + self.run_id, *parts))

    # -- creation ----------------------------------------------------------

    def create(self, pool, *parts):
        """Create pool/test-e2e-<run>/parts with canmount=off (never mounts).

        ``-p`` creates the run's parent dataset too; the property applies
        to every level, so nothing in the fixture ever mounts.
        """
        name = self.name(pool, *parts)
        if zfs("list", "-H", "-o", "name", name, check=False).returncode == 0:
            raise E2EError(f"refusing to create: {name} already exists")
        zfs("create", "-p", "-o", "canmount=off", name)
        self._created.append(name)
        return name

    def create_volume(self, pool, *parts, size="16M"):
        """Create a test zvol (real block device, never needs a mount)."""
        name = self.name(pool, *parts)
        if zfs("list", "-H", "-o", "name", name, check=False).returncode == 0:
            raise E2EError(f"refusing to create: {name} already exists")
        zfs("create", "-p", "-V", size, name)
        self._created.append(name)
        return name

    def register(self, name):
        """Track a dataset the payload itself will create, for cleanup."""
        if name not in self._created:
            self._created.append(name)
        return name

    def snapshot(self, dataset, snap):
        zfs("snapshot", f"{dataset}@{snap.lstrip('@')}")

    def hold(self, snapshot, tag):
        zfs("hold", tag, snapshot)

    # -- teardown ----------------------------------------------------------

    @staticmethod
    def _release_holds(dataset):
        """Release every hold under *dataset* (test datasets only).

        The payloads protect snapshots with offsite-* holds; a plain
        ``zfs destroy -r`` fails with "dataset is busy" while they exist.
        """
        proc = zfs(
            "list",
            "-t",
            "snapshot",
            "-H",
            "-o",
            "name",
            "-r",
            dataset,
            check=False,
        )
        for snap in proc.stdout.split():
            holds = zfs("holds", "-H", snap, check=False)
            if holds.returncode != 0:
                continue
            for line in holds.stdout.splitlines():
                fields = line.split()
                if len(fields) >= 2:
                    zfs("release", fields[1], snap, check=False)

    def cleanup(self):
        if self._destroyed:
            return []
        self._destroyed = True
        leftovers = []

        def _destroy(name):
            """Release holds under *name* and destroy it.

            One retry for transient busy states. Returns an empty string
            when the dataset is gone afterwards (a parent's -r may already
            have taken a registered child — that is success, not failure);
            otherwise a short reason for the report.
            """
            self._release_holds(name)
            proc = zfs("destroy", "-r", name, check=False)
            if proc.returncode != 0 and dataset_exists(name):
                time.sleep(2)
                self._release_holds(name)
                proc = zfs("destroy", "-r", name, check=False)
            if not dataset_exists(name):
                return ""
            return (proc.stderr or proc.stdout or "").strip()[:120]

        for name in reversed(self._created):
            reason = _destroy(name)
            if reason:
                leftovers.append(f"{name} ({reason})")
        # Anything the payload created that the scenario forgot to register
        # still carries the run's unique prefix — find and destroy it too.
        # Deepest first, so parents never fail on surviving children.
        for name in sorted(self.residual_datasets(), key=lambda n: -n.count("/")):
            reason = _destroy(name)
            if reason:
                leftovers.append(f"{name} ({reason})")
        return leftovers

    def residual_datasets(self):
        """All datasets on the test pools carrying this run's prefix."""
        proc = zfs("list", "-H", "-o", "name", "-r", *TEST_POOLS, check=False)
        if proc.returncode != 0:
            return []
        prefix = f"/{DATASET_PREFIX}-{self.run_id}"
        return [line for line in proc.stdout.split() if prefix in line]


def assert_no_residuals(registry):
    residual = registry.residual_datasets()
    if residual:
        raise E2EError(f"datasets left behind: {', '.join(residual)}")


# ---------------------------------------------------------------------------
# ZFS assertions
# ---------------------------------------------------------------------------


def snapshot_exists(snapshot):
    return zfs("list", "-t", "snapshot", "-H", "-o", "name", snapshot, check=False).returncode == 0


def dataset_exists(dataset):
    return zfs("list", "-H", "-o", "name", dataset, check=False).returncode == 0


def holds_of(snapshot):
    proc = zfs("holds", "-H", snapshot, check=False)
    if proc.returncode != 0:
        return []
    return [line.split()[1] for line in proc.stdout.splitlines() if line.strip()]


def guid_of(snapshot):
    proc = zfs("get", "-Hpo", "value", "guid", snapshot, check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def assert_snapshot(snapshot):
    if not snapshot_exists(snapshot):
        raise E2EError(f"expected snapshot {snapshot} does not exist")


def assert_no_snapshot(snapshot):
    if snapshot_exists(snapshot):
        raise E2EError(f"snapshot {snapshot} exists but must not")


def assert_dataset(dataset):
    if not dataset_exists(dataset):
        raise E2EError(f"expected dataset {dataset} does not exist")


def assert_hold(snapshot, tag):
    found = holds_of(snapshot)
    if tag not in found:
        raise E2EError(f"hold {tag!r} missing on {snapshot} (found: {found})")


def assert_no_hold(snapshot, tag):
    found = holds_of(snapshot)
    if tag in found:
        raise E2EError(f"hold {tag!r} unexpectedly present on {snapshot}")


def assert_guid_match(src_ds, dst_ds, snap):
    src_guid = guid_of(f"{src_ds}{snap}")
    dst_guid = guid_of(f"{dst_ds}{snap}")
    if not src_guid or src_guid != dst_guid:
        raise E2EError(f"GUID mismatch for {snap}: src={src_guid} dst={dst_guid}")


# ---------------------------------------------------------------------------
# Strict-signature scanner
# ---------------------------------------------------------------------------


def find_strict_signatures(output):
    found = []
    for signature in STRICT_SIGNATURES:
        if signature in output:
            found.append(signature)
    return found


# ---------------------------------------------------------------------------
# Step execution — StepResult + PtyExecutor
# ---------------------------------------------------------------------------


@dataclass
class StepResult:
    rc: int | None
    output: str
    cancelled: bool = False
    timed_out: bool = False
    prompts: list = field(default_factory=list)
    duration: float = 0.0

    def tail(self, lines=25):
        return "\n".join(self.output.splitlines()[-lines:])


class PtyExecutor:
    """Runs a BashStep with BackupRunner's documented spawn semantics.

    Mirrors ``BackupRunner._spawn_process``: the child is spawned as
    ``Popen(step.command, stdin=pty_slave, stdout=PIPE, stderr=STDOUT)`` with
    echo disabled on the pty and an environment carrying
    ``ZFSUTILITIES_LOG_INHERIT=Y``, ``PYTHONPATH`` plus the repo python dir,
    and — in GUI mode — ``ZFSUTILITIES_INPUT_HOLD=Y``.  ``ZFSU-INPUT-*``
    marker lines are intercepted (never recorded as output); every REQ is
    answered with the configured reply written to the pty master, exactly
    like the GUI's send_input.

    Two engine modes, each production-faithful for its scenario family:

    - ``input_hold=True`` (GUI payloads): the numbered-prompt protocol is
      on, matching the GUI runner.
    - ``input_hold=False`` (CLI orchestrators): the protocol is off, as in
      cron/terminal runs; prompts go to the pty directly and known ones are
      answered via *prefeed*.  A blocking prompt then hits the watchdog —
      the correct failure for an autoproceed flow that should not ask.

    Deviation from the GUI, by design: the child gets its own session so a
    hung step can be killed process-group-wide by the watchdog instead of
    wedging the driver.
    """

    def __init__(self, python_dir=PYTHON_DIR, timeout=300, answer="n", input_hold=True):
        self.python_dir = python_dir
        self.timeout = timeout
        self.answer = answer
        self.input_hold = input_hold

    # -- environment -------------------------------------------------------

    @staticmethod
    def ensure_bashinit():
        """The GUI payloads open with `source ~/bashinit`; make sure it exists."""
        link = os.path.expanduser("~/bashinit")
        if not os.path.exists(link):
            os.symlink(os.path.join(BIN_DIR, "bashinit"), link)

    def _child_env(self):
        env = os.environ.copy()
        env["ZFSUTILITIES_LOG_INHERIT"] = "Y"
        if self.input_hold:
            env["ZFSUTILITIES_INPUT_HOLD"] = "Y"
        else:
            env.pop("ZFSUTILITIES_INPUT_HOLD", None)
        prior = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = os.pathsep.join([self.python_dir, prior]) if prior else self.python_dir
        return env

    # -- execution ---------------------------------------------------------

    def run_step(self, step, timeout=None, prefeed=""):
        self.ensure_bashinit()
        timeout = timeout or self.timeout

        # BackupRunner runs step callbacks around the process; so does the
        # driver (the scrub-pause wrapper depends on them).
        callback_warnings = []
        if getattr(step, "pre_callback", None) is not None:
            try:
                step.pre_callback()
            except Exception as exc:
                callback_warnings.append(f"WARN: Pre-step callback failed: {exc}")

        master_fd, slave_fd = pty.openpty()
        try:
            attrs = termios.tcgetattr(master_fd)
            attrs[3] &= ~termios.ECHO
            termios.tcsetattr(master_fd, termios.TCSANOW, attrs)
        except termios.error:
            pass
        try:
            proc = subprocess.Popen(
                step.command,
                stdin=slave_fd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=self._child_env(),
                start_new_session=True,
            )
        finally:
            os.close(slave_fd)

        if prefeed:
            try:
                os.write(
                    master_fd,
                    prefeed.encode() if prefeed.endswith("\n") else (prefeed + "\n").encode(),
                )
            except OSError:
                pass

        started = time.monotonic()
        deadline = started + timeout
        out_lines = []
        prompts = []
        buf = ""
        timed_out = False
        stdout_fd = proc.stdout.fileno()

        def _consume_line(line):
            # A raw `read -rp` prompt prints without a newline, so a marker
            # can arrive glued to prompt text; search anywhere in the line.
            marker = _INPUT_MARKER_RE.search(line)
            if marker:
                if marker.group(1) == "REQ":
                    prompts.append((marker.group(2), marker.group(3) or ""))
                    try:
                        os.write(master_fd, (self.answer + "\n").encode())
                    except OSError:
                        pass
                prefix = line[: marker.start()]
                if prefix:
                    out_lines.append(prefix)
                return
            out_lines.append(line)

        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    break
                ready, _, _ = select.select([stdout_fd], [], [], min(0.2, remaining))
                if not ready:
                    if proc.poll() is not None:
                        continue  # drain buffered data until EOF below
                    continue
                chunk = os.read(stdout_fd, 8192)
                if not chunk:
                    break
                buf += chunk.decode("utf-8", errors="replace")
                *complete, buf = buf.split("\n")
                for line in complete:
                    _consume_line(line.rstrip("\r"))
            if buf:
                _consume_line(buf.rstrip("\r"))

            if timed_out:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    proc.kill()
            try:
                rc = proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                rc = proc.wait()
        finally:
            try:
                os.close(master_fd)
            except OSError:
                pass
            proc.stdout.close()

        if getattr(step, "post_callback", None) is not None:
            try:
                step.post_callback()
            except Exception as exc:
                callback_warnings.append(f"WARN: Post-step callback failed: {exc}")

        output = "\n".join(out_lines)
        if callback_warnings:
            output = "\n".join(callback_warnings) + "\n" + output
        return StepResult(
            rc=rc,
            output=output,
            timed_out=timed_out,
            prompts=prompts,
            duration=time.monotonic() - started,
        )


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------


def ensure_bashinit():
    PtyExecutor.ensure_bashinit()


def offsite_variables(**overrides):
    """OFFSITE_DEFAULTS variables, exactly as the GUI loads them."""
    from feature_config import OFFSITE_DEFAULTS

    variables = dict(OFFSITE_DEFAULTS["variables"])
    variables.update(overrides)
    return variables


def backup_variables(**overrides):
    """Backup-page variable set for build_send_receive_command."""
    variables = {
        "doincrementals": "Y",
        "dointermediates": "Y",
        "allow_destructive": "N",
        "receive_F_option": "F",
        "releaseholds": "N",
        "releaseholds_tags": "offsite-*",
        "autoresume": "Y",
        "verify_after_transfer": "Y",
        "transfer_rate_limit": "",
        "includes": "",
        "excludes": "",
        "startwith": "",
        "endwith": "",
        "label": "dailybackup",
    }
    variables.update(overrides)
    return variables


_ISSUED_SNAPS = set()


def fresh_snap(label="offsite"):
    """Real GUI snapshot-name generator, leaving the snapfile untouched.

    generate_offsite_snapshot_name() persists the name for the next GUI
    session; the e2e runs must not disturb that file on a dev host, so the
    previous content is saved and restored around the call.  In a fresh
    container the state/lock directories may not exist yet (the first
    payload's bashinit creates them); create them so the real generator —
    not the fallback — runs everywhere.

    The generator is minute-resolution; a scenario that generates several
    names within one minute would collide (the GUI never does — it
    generates once per run).  De-duplicate with a suffix that keeps the
    label prefix intact: commsnap matches by name, retention by label.
    """
    try:
        from paths import get_lock_dir, get_state_dir

        for directory in (get_lock_dir(), get_state_dir()):
            os.makedirs(directory, exist_ok=True)
    except (ImportError, OSError):
        pass
    try:
        from feature_config import OFFSITE_SNAPFILE, generate_offsite_snapshot_name
    except ImportError:
        name = _local_snap_name(label)
    else:
        saved = None
        had_file = os.path.exists(OFFSITE_SNAPFILE)
        if had_file:
            try:
                with open(OFFSITE_SNAPFILE, "rb") as fh:
                    saved = fh.read()
            except OSError:
                saved = None
                had_file = False
        try:
            name = generate_offsite_snapshot_name()
        except OSError:
            name = _local_snap_name(label)
        finally:
            try:
                if had_file and saved is not None:
                    with open(OFFSITE_SNAPFILE, "wb") as fh:
                        fh.write(saved)
                elif not had_file and os.path.exists(OFFSITE_SNAPFILE):
                    os.unlink(OFFSITE_SNAPFILE)
            except OSError:
                pass
    if name in _ISSUED_SNAPS:
        base = name
        n = 2
        while f"{base}-e2e{n}" in _ISSUED_SNAPS:
            n += 1
        name = f"{base}-e2e{n}"
    _ISSUED_SNAPS.add(name)
    return name


def _local_snap_name(label):
    from datetime import datetime, timezone

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    return f"@{label}-{ts}-s"


def build_offsite_step(source, dest, variables, nextsnap, includes="", excludes="", dryrun=False):
    """The exact step object on_offsite_run builds for one GUI step."""
    return offsite_runner.build_offsite_step_command(
        source,
        dest,
        variables,
        BIN_DIR,
        nextsnap,
        includes,
        excludes,
        dryrun=dryrun,
    )


def build_backup_step(source, dest, variables, nextsnap, dryrun=False):
    """The exact step object the Backup page builds for one send/receive step."""
    return command_builders.build_send_receive_command(
        source, dest, variables, BIN_DIR, nextsnap, dryrun=dryrun
    )


def build_prune_step(label, sr_steps, variables, dryrun=False):
    return command_builders.build_backup_prune_command(
        BIN_DIR, label, sr_steps, variables, dryrun=dryrun
    )


def build_rsync_step(source, dest, remote_log_path=None, excludes=None):
    return command_builders.build_rsync_command(
        source, dest, remote_log_path=remote_log_path, excludes=excludes
    )


def _orchestrator_step(script, body, description, source_args=""):
    """Payload shape used for sourceable orchestrators (zfssend &c.).

    The double-quoted ``$mydir`` mirrors the GUI builders' payload text;
    *source_args* is appended to the source line for script-level
    orchestrators (zfsrestore) that parse their overrides from $1.
    """
    bash_script = (
        f'source ~/bashinit; bashinit; mydir="{BIN_DIR}"; '
        f'source "$mydir/{script}"' + (f" {source_args}" if source_args else "") + f"; {body}"
    )
    return BashStep(
        ["bash", "-c", bash_script],
        description,
        is_rsync=False,
        fatal=True,
    )


def dest_path_for(destfs, source_dataset):
    """send-receive's destination mapping (sourcefsremovequalifiers=0)."""
    return f"{destfs}/{source_dataset}"


# ---------------------------------------------------------------------------
# Harness — one per scenario
# ---------------------------------------------------------------------------


class Harness:
    """Bundles executor + registry + the assertion policy every scenario shares."""

    def __init__(self, executor, registry):
        self.executor = executor
        self.registry = registry
        self.last_output = ""

    def run(self, step, expect_rc=0, timeout=None, prefeed="", allow_prompts=False):
        result = self.executor.run_step(step, timeout=timeout, prefeed=prefeed)
        self.last_output = result.output
        if result.timed_out:
            raise E2EError(f"step timed out (watchdog kill); output tail:\n{result.tail()}")
        if result.cancelled:
            raise E2EError(
                f"step ended cancelled (rc=9 lock-abort path); output tail:\n{result.tail()}"
            )
        if result.rc != expect_rc:
            raise E2EError(
                f"step rc={result.rc}, expected {expect_rc}; output tail:\n{result.tail()}"
            )
        signatures = find_strict_signatures(result.output)
        if signatures:
            raise E2EError(
                f"strict-mode signatures in output: {signatures}; output tail:\n{result.tail()}"
            )
        if result.prompts and not allow_prompts:
            raise E2EError(
                f"unexpected interactive prompt(s): {result.prompts}; output tail:\n{result.tail()}"
            )
        return result

    def require_output(self, result, needle):
        if needle not in result.output:
            raise E2EError(f"expected output to contain {needle!r}; output tail:\n{result.tail()}")


# ---------------------------------------------------------------------------
# Scenario registry
# ---------------------------------------------------------------------------

# Entry: (name, function, level, engine)
#   level  — capability the scenario needs: "none" | "read" | "mutation"
#   engine — production-faithful execution mode: "gui" (input-hold protocol
#            on, like the GUI runner) | "cli" (protocol off, like cron/terminal)
SCENARIOS = []


def scenario(name, level="mutation", engine="gui"):
    if level not in ("none", "read", "mutation"):
        raise ValueError(f"bad scenario level: {level}")
    if engine not in ("gui", "cli"):
        raise ValueError(f"bad scenario engine: {engine}")

    def decorator(fn):
        SCENARIOS.append((name, fn, level, engine))
        return fn

    return decorator


def scenarios_matching(prefixes=None, level=None):
    matched = []
    for name, fn, lvl, engine in SCENARIOS:
        if prefixes and not name.startswith(tuple(prefixes)):
            continue
        if level and lvl != level:
            continue
        matched.append((name, fn, lvl, engine))
    return matched


def run_matrix(executor_factory, prefixes=None, levels=("none", "read", "mutation"), log=print):
    """Run the matrix through a fresh executor per scenario (driver entry).

    *executor_factory* is called with the scenario's engine name.
    """
    results = []
    for name, fn, level, engine in scenarios_matching(prefixes):
        if level not in levels:
            log(f"SKIP  {name} (level={level} not selected)")
            continue
        registry = DatasetRegistry()
        started = time.monotonic()
        try:
            fn(Harness(executor_factory(engine), registry))
            leftovers = registry.cleanup()
            if leftovers:
                raise E2EError(f"cleanup could not destroy: {leftovers}")
            assert_no_residuals(registry)
            log(f"PASS  {name} ({time.monotonic() - started:.1f}s)")
            results.append((name, True, ""))
        except E2EError as exc:
            registry.cleanup()
            log(f"FAIL  {name} ({time.monotonic() - started:.1f}s): {exc}")
            results.append((name, False, str(exc)))
        except Exception as exc:  # unexpected harness error — still a failure
            registry.cleanup()
            log(f"FAIL  {name} (harness error {type(exc).__name__}): {exc}")
            results.append((name, False, f"{type(exc).__name__}: {exc}"))
    failed = [name for name, ok, _ in results if not ok]
    return results, failed


# ===========================================================================
# Scenarios — offsite GUI payload (the smoke-test reproduction matrix)
# ===========================================================================


@scenario("offsite-chain-step1-full-copy")
def offsite_chain_step1(h):
    """GUI offsite step 1: full copy with nested datasets and holds applied.

    This is the zfstest1->zfstest2 smoke-test step: nested datasets make the
    holds loop hit parent-and-child duplication (the 2026-10-24 hotfix shape).
    """
    src_parent = h.registry.create("zfstest1", "src")
    src_child = h.registry.create("zfstest1", "src", "child")
    snap = fresh_snap()

    step = build_offsite_step(src_parent, "zfstest2", offsite_variables(), snap)
    h.run(step)

    dst_parent = h.registry.register(dest_path_for("zfstest2", src_parent))
    dst_child = h.registry.register(dest_path_for("zfstest2", src_child))
    for src_ds, dst_ds in ((src_parent, dst_parent), (src_child, dst_child)):
        assert_snapshot(f"{src_ds}{snap}")
        assert_snapshot(f"{dst_ds}{snap}")
        assert_guid_match(src_ds, dst_ds, snap)
        # Payload convention: source snaps are held for the DEST pool,
        # dest snaps for the SOURCE pool.
        assert_hold(f"{src_ds}{snap}", "offsite-zfstest2")
        assert_hold(f"{dst_ds}{snap}", "offsite-zfstest1")


@scenario("offsite-chain-step2-held-source")
def offsite_chain_step2(h):
    """GUI offsite step 2: the zfstest2->zfstest3 chain shape.

    The source datasets are the previous step's DESTINATION, so they already
    carry offsite-* holds when the second step re-holds them for zfstest3 —
    the exact state in which the duplicate-hold hotfix was found.
    """
    src_parent = h.registry.create("zfstest1", "src")
    h.registry.create("zfstest1", "src", "child")
    snap1 = fresh_snap()

    step1 = build_offsite_step(src_parent, "zfstest2", offsite_variables(), snap1)
    h.run(step1)
    step1_dest_root = h.registry.register(dest_path_for("zfstest2", src_parent))

    snap2 = fresh_snap()
    # Step 2 sources the previous step's destination subtree (carries holds).
    step2 = build_offsite_step(step1_dest_root, "zfstest3", offsite_variables(), snap2)
    h.run(step2)

    dst_parent = h.registry.register(dest_path_for("zfstest3", step1_dest_root))
    dst_child = h.registry.register(dest_path_for("zfstest3", step1_dest_root) + "/child")
    for ds in (dst_parent, dst_child):
        assert_snapshot(f"{ds}{snap2}")
    # Step 2's source datasets were step 1's DESTINATION: their snap1
    # snapshots carry step 1's dest-side tag (offsite-zfstest1), and the
    # newly created snap2 gets step 2's source-side tag (offsite-zfstest3);
    # step 2's destination carries offsite-zfstest2.
    assert_hold(f"{step1_dest_root}{snap1}", "offsite-zfstest1")
    assert_hold(f"{step1_dest_root}{snap2}", "offsite-zfstest3")
    assert_hold(f"{dst_parent}{snap2}", "offsite-zfstest2")
    assert_guid_match(step1_dest_root, dst_parent, snap2)


@scenario("offsite-incremental-rerun")
def offsite_incremental(h):
    """Second GUI run with a fresh snapshot: incremental from the common snap."""
    src = h.registry.create("zfstest1", "inc")
    snap1 = fresh_snap()
    h.run(build_offsite_step(src, "zfstest2", offsite_variables(), snap1))
    dst = h.registry.register(dest_path_for("zfstest2", src))

    snap2 = fresh_snap()
    h.run(build_offsite_step(src, "zfstest2", offsite_variables(), snap2))
    assert_snapshot(f"{dst}{snap2}")
    assert_guid_match(src, dst, snap2)


@scenario("offsite-same-nextsnap-rerun")
def offsite_same_nextsnap(h):
    """Re-running a step with the same nextsnap: the skip path must be clean.

    The holds loop still runs and re-applies the same tags — the duplicate
    hold must be an INFO (rc 0), not an abort (the 2026-10-24 hotfix).
    """
    src = h.registry.create("zfstest1", "same")
    snap = fresh_snap()
    step = build_offsite_step(src, "zfstest2", offsite_variables(), snap)
    h.run(step)
    h.registry.register(dest_path_for("zfstest2", src))

    result = h.run(step)
    h.require_output(result, "already exists")
    assert_hold(f"{src}{snap}", "offsite-zfstest2")


def cancel_scrub_if_active(pool):
    """Best-effort scrub cancel so a scenario never leaves one running."""
    status = zpool("status", pool, check=False).stdout
    if "scrub in progress" in status or "scrub paused" in status:
        zpool("scrub", "-c", pool, check=False)


@scenario("offsite-dryrun", level="read")
def offsite_dryrun(h):
    """Dry-run mode against the zfstest1 pool root (read-only context).

    The pool root's snapshot state is whatever the operator's smoke runs
    left behind: with a common snapshot present the engine plans an
    incremental would-send; without one it asks "Should a full copy be done
    instead?" and the executor auto-declines over the input-hold channel.
    Both shapes must run clean with zero pool mutations — and this
    exercises the full sourcing chain under strict mode either way.
    """
    snap = fresh_snap()
    step = build_offsite_step("zfstest1", "zfstest2", offsite_variables(), snap, dryrun=True)
    result = h.run(step, allow_prompts=True)
    h.require_output(result, "Dry-run: Would create snapshot")
    h.require_output(result, "Dry-run: Would apply holds")
    if "Dry-run: Would send" not in result.output and "Skipping zfstest1" not in result.output:
        raise E2EError(
            f"unexpected dry-run shape (neither would-send nor decline-skip); "
            f"output tail:\n{result.tail()}"
        )
    # The prompt count follows however many snapshot-less datasets the
    # pool root happens to contain (operator leftovers included).
    assert_no_snapshot(f"zfstest1{snap}")


@scenario("offsite-rollback-scope-mismatch")
def offsite_rollback(h):
    """Destination ahead of source (scope mismatch): autoproceed rollback path.

    Exercises the rc=16 branch: offsite-* holds on the newer destination
    snapshots must be released, the destination rolled back, and the new
    snapshot transferred.
    """
    src = h.registry.create("zfstest1", "rb")
    snap1 = fresh_snap()
    h.run(build_offsite_step(src, "zfstest2", offsite_variables(), snap1))
    dst = h.registry.register(dest_path_for("zfstest2", src))

    # Destination-only newer snapshot with a foreign label, plus a hold that
    # the rollback must release before destroying it.
    extra = "@dailybackup-2020-01-01T00:00Z-d"
    h.registry.snapshot(dst, extra.lstrip("@"))
    h.registry.hold(f"{dst}{extra}", "offsite-zfstest1")

    snap2 = fresh_snap()
    result = h.run(build_offsite_step(src, "zfstest2", offsite_variables(), snap2))
    h.require_output(result, "rolling back")
    assert_no_snapshot(f"{dst}{extra}")
    assert_snapshot(f"{dst}{snap2}")
    assert_guid_match(src, dst, snap2)


@scenario("offsite-includes-excludes")
def offsite_includes_excludes(h):
    """Per-step dataset selection: only included datasets are copied."""
    root = h.registry.create("zfstest1", "sel")
    keep = h.registry.create("zfstest1", "sel", "keepme")
    drop = h.registry.create("zfstest1", "sel", "skipme")
    snap = fresh_snap()

    step = build_offsite_step(root, "zfstest2", offsite_variables(), snap, includes="keepme")
    h.run(step)

    dst_keep = h.registry.register(dest_path_for("zfstest2", keep))
    dst_drop = dest_path_for("zfstest2", drop)
    assert_snapshot(f"{dst_keep}{snap}")
    assert_no_snapshot(f"{dst_drop}{snap}")


@scenario("offsite-scrub-pause")
def offsite_scrub_pause(h):
    """pause_scrubs wrapper with a live scrub: pause before, resume after."""
    from scrub_manager import attach_step_scrub_callbacks

    src = h.registry.create("zfstest1", "scrub")
    snap = fresh_snap()
    step = build_offsite_step(src, "zfstest2", offsite_variables(), snap)
    messages = []
    attach_step_scrub_callbacks(
        step,
        src,
        "zfstest2",
        enabled=True,
        dry_run=False,
        log_func=lambda msg, **_kw: messages.append(msg),
    )

    zpool("scrub", "zfstest1")
    try:
        h.run(step)
    finally:
        # Never leave a scrub running or paused on the shared pool.
        cancel_scrub_if_active("zfstest1")
    joined = "\n".join(messages)
    if "Pausing scrub on 'zfstest1'" not in joined:
        raise E2EError(f"scrub pause did not run; callback messages: {joined}")
    dst = h.registry.register(dest_path_for("zfstest2", src))
    assert_snapshot(f"{dst}{snap}")
    # The resumed scrub must settle on the tiny pool within the poll budget.
    # A COMPLETED scan line still says "scrub repaired ...", so the exit
    # condition is the absence of in-progress/paused, not of "scrub".
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        scan_line = zpool("status", "zfstest1").stdout.split("scan:", 1)[-1].split("\n", 1)[0]
        if "scrub in progress" not in scan_line and "scrub paused" not in scan_line:
            break
        time.sleep(2)
    else:
        raise E2EError("scrub did not settle after resume within 120s")


@scenario("offsite-scrub-pause-dryrun", level="read")
def offsite_scrub_pause_dryrun(h):
    """Dry-run chain with the scrub-pause wrapper attached (read-only context).

    With no scrub running the callbacks take their not-scanning branch, so
    this proves the wrapper wiring never breaks the step in the same
    configuration the GUI runs it in.
    """
    from scrub_manager import attach_step_scrub_callbacks

    snap = fresh_snap()
    step = build_offsite_step("zfstest1", "zfstest2", offsite_variables(), snap, dryrun=True)
    attach_step_scrub_callbacks(
        step,
        "zfstest1",
        "zfstest2",
        enabled=True,
        dry_run=True,
        log_func=lambda msg, **_kw: None,
    )
    result = h.run(step, allow_prompts=True)
    h.require_output(result, "Dry-run: Would apply holds")


@scenario("offsite-resume-token")
def offsite_resume_token(h):
    """Partial receive leaves a resume token; the payload must resume it.

    The source is a zvol with real allocated blocks: a sparse or empty
    dataset's send stream is only a few hundred bytes, so the truncated
    prefix would land mid-header and fail before creating the destination.
    """
    src = h.registry.create_volume("zfstest1", "resume", size="16M")
    voldev = f"/dev/zvol/{src}"
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not os.path.exists(voldev):
        time.sleep(0.5)
    if not os.path.exists(voldev):
        raise E2EError(f"zvol device {voldev} did not appear")
    _run(["dd", "if=/dev/urandom", f"of={voldev}", "bs=1M", "count=4"])

    base_snap = "@offsite-2020-01-01T00:00Z-s"
    h.registry.snapshot(src, base_snap.lstrip("@"))
    target = fresh_snap()
    h.registry.snapshot(src, target.lstrip("@"))
    dst = h.registry.register(dest_path_for("zfstest2", src))
    # The partial receive creates the leaf dataset; its parents must exist.
    dst_parent = dst.rsplit("/", 1)[0]
    zfs("create", "-p", "-o", "canmount=off", dst_parent)
    h.registry.register(dst_parent)

    # Partial receive: a deliberately truncated stream prefix into a
    # RESUMABLE receive (-s) leaves receive_resume_token on the destination.
    # Shell pipeline (the integration-suite pattern) so the sender dies on
    # SIGPIPE when head closes — no Python-side pipe management to deadlock.
    # The prefix must clear the stream header (a 200-byte cut fails before
    # the dataset is created; 64 KiB is mid-data for the 4 MiB zvol).
    _run(
        [
            "bash",
            "-c",
            "zfs send -cw {snap} | head -c 65536 | zfs receive -s -u {dst}".format(
                snap=shlex.quote(f"{src}{base_snap}"), dst=shlex.quote(dst)
            ),
        ],
        check=False,
    )
    token = zfs("get", "-Hpo", "value", "receive_resume_token", dst).stdout.strip()
    if not token or token == "-":
        raise E2EError("no resume token after partial receive")

    result = h.run(build_offsite_step(src, "zfstest2", offsite_variables(), target))
    h.require_output(result, "resume token")
    assert_snapshot(f"{dst}{target}")
    assert_guid_match(src, dst, target)


@scenario("offsite-negative-control", level="none")
def offsite_negative_control(h):
    """Harness red-proof: a deliberately broken payload must be caught."""
    broken = BashStep(
        ["bash", "-c", 'set -u; echo "value=${E2E_BUG_UNSET_VARIABLE}"'],
        "negative control: unbound variable",
        is_rsync=False,
        fatal=True,
    )
    result = h.executor.run_step(broken)
    if result.rc == 0:
        raise E2EError("negative control unexpectedly succeeded (rc=0)")
    if find_strict_signatures(result.output):
        return  # scanner caught it — the harness works
    raise E2EError(
        f"strict-signature scanner missed the unbound variable; output was:\n{result.tail()}"
    )


# ===========================================================================
# Scenarios — backup GUI payload + prune + rsync + strict-mode leaf scripts
# ===========================================================================


@scenario("backup-full-copy")
def backup_full_copy(h):
    """Backup-page payload: two-step full copy with verify."""
    src = h.registry.create("zfstest1", "bkfull")
    snap = fresh_snap()
    step = build_backup_step(src, "zfstest2", backup_variables(doincrementals="N"), snap)
    h.run(step)
    dst = h.registry.register(dest_path_for("zfstest2", src))
    assert_snapshot(f"{dst}{snap}")
    assert_guid_match(src, dst, snap)


@scenario("backup-incremental")
def backup_incremental(h):
    """Backup-page payload: incremental run off the common snapshot."""
    src = h.registry.create("zfstest1", "bkinc")
    snap1 = fresh_snap()
    h.run(build_backup_step(src, "zfstest2", backup_variables(), snap1))
    dst = h.registry.register(dest_path_for("zfstest2", src))

    snap2 = fresh_snap()
    h.run(build_backup_step(src, "zfstest2", backup_variables(), snap2))
    assert_snapshot(f"{dst}{snap2}")
    assert_guid_match(src, dst, snap2)


@scenario("backup-destructive-hold-preservation")
def backup_destructive(h):
    """allow_destructive full copy vs holds — both designed behaviors.

    1. A USER hold on the destination blocks destructive preparation
       (rc 8, WARN, destination left intact) — user holds are protection.
    2. A system-shaped offsite-* tag is released for the re-copy and then
       REAPPLIED by preserve_target_holds (capture/reapply) afterwards.
    """
    src = h.registry.create("zfstest1", "bkdest")
    snap1 = fresh_snap()
    h.run(build_backup_step(src, "zfstest2", backup_variables(doincrementals="N"), snap1))
    dst = h.registry.register(dest_path_for("zfstest2", src))

    user_tag = "e2e-user-hold"
    h.registry.hold(f"{dst}{snap1}", user_tag)
    snap2 = fresh_snap()
    h.registry.snapshot(src, snap2.lstrip("@"))
    step = build_backup_step(
        src,
        "zfstest2",
        backup_variables(doincrementals="N", allow_destructive="Y"),
        snap2,
    )

    # 1. The user hold must block the destructive re-copy.
    result = h.run(step, expect_rc=8)
    h.require_output(result, "still has holds")
    assert_snapshot(f"{dst}{snap1}")

    # 2. A system-shaped tag rides the capture/reapply path instead.
    zfs("release", user_tag, f"{dst}{snap1}")
    system_tag = "offsite-zfstest9"
    h.registry.hold(f"{dst}{snap1}", system_tag)
    h.run(step)
    assert_snapshot(f"{dst}{snap2}")
    assert_guid_match(src, dst, snap2)
    # The two-step full copy recreates snap1 (oldest as the base), and the
    # preserved tag must be back on it.
    assert_snapshot(f"{dst}{snap1}")
    assert_hold(f"{dst}{snap1}", system_tag)


@scenario("backup-prune")
def backup_prune(h):
    """Prune payload: zfscleanup over the backup's datasets, both sides.

    The checkagainst safety gate prompts before deleting snapshots whose
    pools are not in the (site-specific) checkagainst mapping — the test
    pools are unmapped by design, so the scenario answers "y" and asserts
    the gate actually fired before allowing the removals.
    """
    src = h.registry.create("zfstest1", "prune")
    snap = fresh_snap()
    h.run(build_backup_step(src, "zfstest2", backup_variables(doincrementals="N"), snap))
    dst = h.registry.register(dest_path_for("zfstest2", src))

    dated = [f"dailybackup-2020-01-0{day}T00:00Z-d" for day in (1, 2, 3, 4)]
    for ds in (src, dst):
        for day_snap in dated:
            h.registry.snapshot(ds, day_snap)

    h.executor.answer = "y"
    try:
        step = build_prune_step("dailybackup", [(src, "zfstest2")], backup_variables())
        result = h.run(step, allow_prompts=True)
    finally:
        h.executor.answer = "n"
    h.require_output(result, "retention")
    if not result.prompts:
        raise E2EError(
            "expected the checkagainst removal gate to prompt for the "
            "unmapped test pools; it never asked"
        )
    # With the gate answered, same-day dedup must have removed at least one
    # dated snapshot (they share a creation day) ...
    survivors = [d for d in dated if snapshot_exists(f"{src}@{d}")]
    if len(survivors) == len(dated):
        raise E2EError("no dated snapshot was pruned on the source")
    # ... while the offsite-labeled snapshot is untouched by the
    # dailybackup prune.
    assert_snapshot(f"{src}{snap}")


@scenario("rsync-local-step", level="none")
def rsync_local_step(h, tmp_root=None):
    """rsync step wrapper local->local: log setup, transfer, failure tail."""
    import tempfile

    tmp_root = tmp_root or tempfile.mkdtemp(prefix="e2e-rsync-")
    src_dir = os.path.join(tmp_root, "src")
    dst_dir = os.path.join(tmp_root, "dst")
    log_path = os.path.join(tmp_root, "rsync.log")
    os.makedirs(src_dir)
    os.makedirs(dst_dir)
    with open(os.path.join(src_dir, "marker.txt"), "w") as fh:
        fh.write("e2e-rsync\n")

    step = build_rsync_step(src_dir, dst_dir, remote_log_path=log_path)
    h.run(step)
    # GUI semantics: rsync copies the source directory INTO the destination.
    copied = os.path.join(dst_dir, "src", "marker.txt")
    if not os.path.exists(copied):
        raise E2EError(f"rsync did not copy src/marker.txt into {dst_dir}")
    if not os.path.exists(log_path):
        raise E2EError(f"rsync log was not created at {log_path}")


@scenario("orch-zfssend", engine="cli")
def orch_zfssend(h):
    """zfssend orchestrator live (strict-mode flipped leaf script)."""
    src = h.registry.create("zfstest1", "send")
    overrides = f"sourcefs={src}; destfs=zfstest2; autoproceed='Y'"
    body = f"send {shlex.quote(overrides)}"
    step = _orchestrator_step("zfssend", body, "orchestrator: zfssend")
    # zfssend prompts once with a raw `read -rp` before its overrides apply;
    # exactly one pre-fed newline answers it (stale input would poison the
    # input-hold reads that follow).
    result = h.run(step, prefeed="\n")
    if "Copy completed" not in result.output:
        raise E2EError(f"zfssend did not complete; output tail:\n{result.tail()}")
    # zfssend derives its own nextsnap via zfssnapbuild; assert the newest
    # source snapshot landed on the destination.
    newest = zfs(
        "list", "-t", "snap", "-H", "-o", "name", "-S", "createtxg", "-d", "1", src
    ).stdout.splitlines()[0]
    snap = newest[newest.index("@") :]
    dst = h.registry.register(dest_path_for("zfstest2", src))
    assert_snapshot(f"{dst}{snap}")
    assert_guid_match(src, dst, snap)


@scenario("orch-zfsfullcopy", engine="cli")
def orch_zfsfullcopy(h):
    """zfsfullcopy orchestrator live: two-step full copy restore helper."""
    src = h.registry.create("zfstest1", "fc")
    for day in (1, 2):
        h.registry.snapshot(src, f"offsite-2020-01-0{day}T00:00Z-s")

    overrides = f"restoresourcefs={src}; destfs=zfstest2"
    body = f"zfsfullcopy {shlex.quote(overrides)}"
    step = _orchestrator_step("zfsfullcopy", body, "orchestrator: zfsfullcopy")
    h.run(step)
    # Mapping: destfs + '/' + restoresourcefs (qualifiers default 0).
    dst_mapped = h.registry.register(dest_path_for("zfstest2", src))
    for day in (1, 2):
        assert_snapshot(f"{dst_mapped}@offsite-2020-01-0{day}T00:00Z-s")


@scenario("orch-zfsrestore", engine="cli")
def orch_zfsrestore(h):
    """zfsrestore orchestrator live: full-copy restore with hold release."""
    src = h.registry.create("zfstest1", "restore")
    for day in (1, 2):
        h.registry.snapshot(src, f"offsite-2020-01-0{day}T00:00Z-s")
    # An offsite hold on the source snaps must be released by the restore
    # flow (releaseholds=Y, tags offsite-*).
    h.registry.hold(f"{src}@offsite-2020-01-01T00:00Z-s", "offsite-zfstest1")

    overrides = (
        f"restoresourcefs={src}; sourcefsremovequalifiers='0'; destfs='zfstest3'; autoproceed='Y'"
    )
    # zfsrestore runs at source time (script-level flow), so its overrides
    # travel as the source arguments, not as a separate body.
    step = _orchestrator_step(
        "zfsrestore",
        "",
        "orchestrator: zfsrestore",
        source_args=shlex.quote(overrides),
    )
    h.run(step)
    dst_mapped = h.registry.register(dest_path_for("zfstest3", src))
    assert_snapshot(f"{dst_mapped}@offsite-2020-01-02T00:00Z-s")


@scenario("holds-roundtrip", engine="cli")
def holds_roundtrip(h):
    """zfshold live: duplicate-hold tolerance + holds listing + release."""
    ds = h.registry.create("zfstest1", "holds")
    snap = "@e2e-hold-check"
    h.registry.snapshot(ds, snap.lstrip("@"))
    tag = "offsite-zfstest2"

    body = (
        f"zfshold {shlex.quote(tag)} {shlex.quote(ds)} {shlex.quote(snap)}; "
        f"rc1=$?; zfshold {shlex.quote(tag)} {shlex.quote(ds)} {shlex.quote(snap)}; rc2=$?; "
        f"holds {shlex.quote(ds)} 1; exit $(( rc1 || rc2 ))"
    )
    step = _orchestrator_step("zfshold", "source_helper zfsholds; " + body, "holds roundtrip")
    # NOTE: zfshold must be sourced first (it is a library, not a runner):
    # _orchestrator_step sources "$mydir/zfshold" via the script literal.
    result = h.run(step)
    h.require_output(result, "already present")
    assert_hold(f"{ds}{snap}", tag)
    zfs("release", tag, f"{ds}{snap}")
    assert_no_hold(f"{ds}{snap}", tag)

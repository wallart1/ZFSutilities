"""Shared command builders for backup, offsite, restore, and retention operations."""

import shlex
import socket
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# Common rsync exit-code meanings used to explain a failed step.
# Rsync man page / `rsync --help` exit codes:
#   0  Success
#   1  Syntax or usage error
#   2  Protocol incompatibility
#   3  Errors selecting input/output files, dirs
#   4  Requested action not supported
#   5  Error starting client-server protocol
#   6  Daemon unable to append to log-file
#  10  Error in socket I/O
#  11  Error in file I/O
#  12  Error in rsync protocol data stream
#  13  Errors with program diagnostics
#  14  Error in IPC code
#  20  Received SIGUSR1 or SIGINT
#  21  Some error returned by waitpid()
#  22  Error allocating core memory buffers
#  23  Partial transfer due to error
#  24  Partial transfer due to vanished source files
#  25  The --max-delete limit stopped deletions
#  30  Timeout in data send/receive
#  35  Timeout waiting for daemon connection
_RSYNC_EXIT_CODES = {
    1: "syntax or usage error",
    2: "protocol incompatibility",
    3: "errors selecting input/output files or directories",
    4: "requested action not supported",
    5: "error starting client-server protocol",
    6: "daemon unable to append to log-file",
    10: "error in socket I/O",
    11: "error in file I/O",
    12: "error in rsync protocol data stream",
    13: "errors with program diagnostics",
    14: "error in IPC code",
    20: "received SIGUSR1 or SIGINT",
    21: "error returned by waitpid()",
    22: "error allocating core memory buffers",
    23: "partial transfer due to error",
    24: "partial transfer due to vanished source files",
    25: "the --max-delete limit stopped deletions",
    30: "timeout in data send/receive",
    35: "timeout waiting for daemon connection",
}


def _diagnose_rsync_failure(rc, stderr_lines):
    """Return a human-readable diagnosis for a failed rsync step.

    Args:
        rc: The rsync process return code.
        stderr_lines: Iterable of stripped stderr lines emitted by rsync.

    Returns:
        A short explanatory string, or an empty string if rc is 0.
    """
    if rc == 0:
        return ""

    text = "\n".join(stderr_lines).lower()

    # Network/transport-level failures (SSH failed to connect or talk to rsync).
    if rc in (5, 10, 255) or "ssh:" in text:
        if "connection refused" in text or "no route to host" in text:
            return (
                "SSH connection refused — check that the remote host is "
                "reachable, sshd is running, and the address is correct"
            )
        if "permission denied" in text or "authentication" in text:
            return (
                "Permission denied — verify SSH key access, root login "
                "permissions, and filesystem permissions on the "
                "source/destination"
            )
        if "timeout" in text:
            return "Timeout waiting for data from the remote host"
        if rc == 255:
            return "SSH failed to start — check host reachability and SSH configuration"

    # Destination disk full.
    if "no space left" in text or "disk full" in text:
        return "No space left on destination — free disk space and retry"

    # Rsync-specific transfer outcomes.
    if rc == 24 or "vanished" in text:
        return "Source files vanished during transfer"
    if rc == 23:
        return "Partial transfer due to error"

    # Generic timeout and disk I/O errors.
    if rc == 30:
        return "Timeout in data send/receive"
    if rc == 35:
        return "Timeout waiting for daemon connection"
    if rc == 11:
        return "Error in file I/O"

    return f"rsync exit code {rc}: {_RSYNC_EXIT_CODES.get(rc, 'unknown error')}"


@dataclass
class BashStep:
    """A single bash command step for backup/offsite/restore/retention runners.

    Attributes:
        command: List of command arguments to pass to subprocess.
        description: Human-readable step description for logging and UI.
        is_rsync: True if the step is an rsync transfer (uses rsync log).
        fatal: True if a non-zero return code should abort the run.
        pre_callback: Optional callable to run before the step starts.
        post_callback: Optional callable to run after the step finishes.
        metadata: Optional dict carrying source/dest/label for successful
            send/receive steps (used to auto-seed checkagainst entries).
    """

    command: list[str]
    description: str
    is_rsync: bool = False
    fatal: bool = False
    pre_callback: Callable[[], None] | None = None
    post_callback: Callable[[], None] | None = None
    metadata: dict | None = None


def _dryrun_assignments(dryrun=False):
    """Return bash variable assignments for dry-run overrides."""
    if dryrun:
        return "dryrun='Y'; "
    return ""


def _get_local_hostname():
    return socket.gethostname().split(".")[0]


def _is_local_host(host):
    if not host:
        return True
    return host == _get_local_hostname()


def parse_rsync_endpoint(endpoint):
    """Parse an rsync endpoint into (host_or_None, path)."""
    if ":" in endpoint and not endpoint.startswith("/"):
        host, path = endpoint.split(":", 1)
        if _is_local_host(host):
            return None, path
        return host, path
    return None, endpoint


def _rsync_log_setup_script(log_path):
    """Return a bash snippet that ensures the log dir exists and truncates stale logs.

    The log file is reset when it does not exist or its mtime is not from today.
    """
    log_dir = shlex.quote(str(Path(log_path).parent))
    log_path_quoted = shlex.quote(log_path)
    return (
        f"mkdir -p {log_dir}; "
        f"if [ ! -f {log_path_quoted} ] || "
        f'[ "$(date -r {log_path_quoted} +%Y%m%d 2>/dev/null || echo 0)" != "$(date +%Y%m%d)" ]; then '
        f": > {log_path_quoted}; fi"
    )


# Directories that are commonly unreadable by root because they are owned by
# a user-session FUSE/portal filesystem (e.g. GNOME GVFS, xdg-document-portal).
# Excluding them prevents harmless but noisy "Permission denied" rsync errors.
DEFAULT_RSYNC_EXCLUDES = (
    "**/.gvfs/",
    "**/.cache/doc/",
)


def build_rsync_command(source, dest, remote_log_path=None, excludes=None):
    """Build an rsync command list from source and dest strings.

    Args:
        source: Source endpoint, e.g. "/src", "tweety:/src".
        dest: Destination endpoint, e.g. "/dst", "tweety:/dst".
        remote_log_path: If set and the step is a pull, rsync output is streamed
            to this file on the source host. The file is truncated the first time
            it is used each day and appended to afterwards.
        excludes: Optional iterable of rsync exclude patterns. Each item is
            passed to rsync as ``--exclude=PATTERN``. User-supplied excludes are
            appended after the defaults so they add additional exclusions; the
            defaults are always applied first because they protect unreadable
            system paths.
    """
    src_host, src_path = parse_rsync_endpoint(source)
    dst_host, dst_path = parse_rsync_endpoint(dest)
    rsync_opts = ["rsync", "--delete", "--progress", "-rav"]
    for pattern in DEFAULT_RSYNC_EXCLUDES:
        rsync_opts.append(f"--exclude={pattern}")
    if excludes:
        for pattern in excludes:
            rsync_opts.append(f"--exclude={pattern}")
    local_host = _get_local_hostname()
    if src_host and dst_host:
        remote_cmd = shlex.join(rsync_opts + [src_path, f"root@{dst_host}:{dst_path}"])
        cmd = ["ssh", f"root@{src_host}", remote_cmd]
        desc = f"[{src_host}] rsync {source} -> {dest}"
    elif src_host:
        if remote_log_path:
            setup_cmd = shlex.join(
                ["ssh", "-q", f"root@{src_host}", _rsync_log_setup_script(remote_log_path)]
            )
            rsync_cmd = shlex.join(rsync_opts + [f"root@{src_host}:{src_path}", dst_path])
            host_quoted = shlex.quote(src_host)
            log_quoted = shlex.quote(remote_log_path)
            bash_script = (
                f"_rh={host_quoted}; _rl={log_quoted}; "
                f"{setup_cmd} && "
                f'{rsync_cmd} 2>&1 | ssh -q root@$_rh "cat >> $_rl"; '
                f"exit ${{PIPESTATUS[0]}}"
            )
            cmd = ["bash", "-c", bash_script]
        else:
            cmd = rsync_opts + [f"root@{src_host}:{src_path}", dst_path]
        desc = f"[{local_host}] rsync {source} -> {dest} (pull from {src_host})"
    elif dst_host:
        cmd = rsync_opts + [src_path, f"root@{dst_host}:{dst_path}"]
        desc = f"[{local_host}] rsync {source} -> {dest} (push to {dst_host})"
    else:
        if remote_log_path:
            bash_script = (
                f"{_rsync_log_setup_script(remote_log_path)}; "
                f"{shlex.join(rsync_opts)} "
                f"{shlex.quote(src_path)} {shlex.quote(dst_path)} "
                f">> {shlex.quote(remote_log_path)} 2>&1"
            )
            cmd = ["bash", "-c", bash_script]
        else:
            cmd = rsync_opts + [src_path, dst_path]
        desc = f"[{local_host}] rsync {source} -> {dest}"
    return BashStep(cmd, desc, is_rsync=True, fatal=False)


def build_send_receive_command(source, dest, variables, parent_dir, nextsnap, dryrun=False):
    """Build the bash command string for a zfs send/receive step."""
    v = variables
    var_assignments = (
        f"{_dryrun_assignments(dryrun)}"
        f'sourcefs="{source}"; destfs="{dest}"; nextsnap="{nextsnap}"; '
        f'doincrementals="{v.get("doincrementals", "Y")}"; '
        f'dointermediates="{v.get("dointermediates", "Y")}"; '
        f'autoproceed="Y"; '
        f'allow_destructive="{v.get("allow_destructive", "N")}"; '
        f'receive_F_option="{v.get("receive_F_option", "F")}"; '
        f'releaseholds="{v.get("releaseholds", "N")}"; '
        f'releaseholds_tags=("{v.get("releaseholds_tags", "offsite-*")}"); '
        f'autoresume="{v.get("autoresume", "Y")}"; '
        f'verify_after_transfer="{v.get("verify_after_transfer", "Y")}"; '
        f'pv_rate_limit="{v.get("pv_rate_limit", "")}"; '
    )
    includes = v.get("includes", "").strip()
    excludes = v.get("excludes", "").strip()
    startwith = v.get("startwith", "").strip()
    endwith = v.get("endwith", "").strip()
    if includes:
        items = shlex.split(includes)
        arr = " ".join(f'"{i}"' for i in items)
        var_assignments += f"includes=({arr}); "
    else:
        var_assignments += "includes=(); "
    if excludes:
        items = shlex.split(excludes)
        arr = " ".join(f'"{i}"' for i in items)
        var_assignments += f"excludes=({arr}); "
    else:
        var_assignments += "excludes=(); "
    if startwith:
        var_assignments += f'startwith="{startwith}"; '
    if endwith:
        var_assignments += f'endwith="{endwith}"; '
    bash_script = (
        f'source ~/bashinit; bashinit; mydir="{parent_dir}"; '
        f'source "$mydir/zfs-send-receive"; '
        f"{var_assignments}"
        f"send-receive"
    )
    metadata = {
        "source": source,
        "dest": dest,
        "label": variables.get("label", "dailybackup"),
    }
    return BashStep(
        ["bash", "-c", bash_script],
        f"zfs send/receive: {source} -> {dest}",
        is_rsync=False,
        fatal=True,
        metadata=metadata,
    )


def build_pre_backup_command(script):
    """Build a fatal pre-backup command that runs a user-supplied command."""
    return BashStep(
        ["bash", "-c", script],
        "Pre-backup command",
        is_rsync=False,
        fatal=True,
    )


def build_post_backup_command(script):
    """Build a post-backup command that runs a user-supplied command."""
    return BashStep(
        ["bash", "-c", script],
        "Post-backup command",
        is_rsync=False,
        fatal=False,
    )


def build_retention_command(parent_dir, label, pools=None, dryrun=False, fatal=True):
    """Build the command to run retention/cleanup.

    If *pools* is provided, prune each pool in the given order; otherwise
    let ``zfscleanup`` use the configured pool list.
    """
    label_quoted = shlex.quote(label)
    dryrun_part = _dryrun_assignments(dryrun)
    base_script = (
        f'source ~/bashinit; bashinit; mydir="{parent_dir}"; '
        f'source "$mydir/zfscleanup"; '
        f"{dryrun_part}"
        f'autoproceed="Y"; '
        f'releaseholds="Y"; '
        f'releaseholds_tags=("offsite-*"); '
    )
    if pools:
        pool_list = " ".join(shlex.quote(p) for p in pools)
        bash_script = (
            f"{base_script}"
            f"overall_rc=0; "
            f"for pool in {pool_list}; do "
            f'  cleanup "$pool" "" {label_quoted} || overall_rc=$?; '
            f"done; "
            f"exit $overall_rc"
        )
        desc = f"Prune snapshots ({', '.join(pools)})"
    else:
        bash_script = f'{base_script}cleanup "" "" {label_quoted}'
        desc = "Prune snapshots"
    return BashStep(
        ["bash", "-c", bash_script],
        desc,
        is_rsync=False,
        fatal=fatal,
    )

"""Shared command builders for backup, offsite, restore, and retention operations."""

import os
import shlex
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional


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
    """

    command: List[str]
    description: str
    is_rsync: bool = False
    fatal: bool = False
    pre_callback: Optional[Callable[[], None]] = None
    post_callback: Optional[Callable[[], None]] = None


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
        f'mkdir -p {log_dir}; '
        f'if [ ! -f {log_path_quoted} ] || '
        f'[ "$(date -r {log_path_quoted} +%Y%m%d 2>/dev/null || echo 0)" != "$(date +%Y%m%d)" ]; then '
        f': > {log_path_quoted}; fi'
    )


def _remote_rsync_log_setup_command(host, log_path):
    """Return an SSH command that ensures the remote log dir exists and truncates stale logs."""
    return ["ssh", "-q", f"root@{host}", _rsync_log_setup_script(log_path)]


def build_rsync_command(source, dest, remote_log_path=None):
    """Build an rsync command list from source and dest strings.

    Args:
        source: Source endpoint, e.g. "/src", "tweety:/src".
        dest: Destination endpoint, e.g. "/dst", "tweety:/dst".
        remote_log_path: If set and the step is a pull, rsync output is streamed
            to this file on the source host. The file is truncated the first time
            it is used each day and appended to afterwards.
    """
    src_host, src_path = parse_rsync_endpoint(source)
    dst_host, dst_path = parse_rsync_endpoint(dest)
    rsync_opts = ["rsync", "--delete", "--progress", "-rav"]
    local_host = _get_local_hostname()
    if src_host and dst_host:
        remote_cmd = shlex.join(rsync_opts + [src_path, f"root@{dst_host}:{dst_path}"])
        cmd = ["ssh", f"root@{src_host}", remote_cmd]
        desc = f"[{src_host}] rsync {source} -> {dest}"
    elif src_host:
        if remote_log_path:
            setup_cmd = shlex.join(_remote_rsync_log_setup_command(src_host, remote_log_path))
            rsync_cmd = shlex.join(rsync_opts + [f"root@{src_host}:{src_path}", dst_path])
            host_quoted = shlex.quote(src_host)
            log_quoted = shlex.quote(remote_log_path)
            bash_script = (
                f'_rh={host_quoted}; _rl={log_quoted}; '
                f'{setup_cmd} && '
                f'{rsync_cmd} 2>&1 | ssh -q root@$_rh "cat >> $_rl"; '
                f'exit ${{PIPESTATUS[0]}}'
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
                f'{_rsync_log_setup_script(remote_log_path)}; '
                f'{shlex.join(rsync_opts)} '
                f'{shlex.quote(src_path)} {shlex.quote(dst_path)} '
                f'>> {shlex.quote(remote_log_path)} 2>&1'
            )
            cmd = ["bash", "-c", bash_script]
        else:
            cmd = rsync_opts + [src_path, dst_path]
        desc = f"[{local_host}] rsync {source} -> {dest}"
    return BashStep(cmd, desc, is_rsync=True, fatal=False)


def build_send_receive_command(source, dest, variables, parent_dir, nextsnap,
                               dryrun=False):
    """Build the bash command string for a zfs send/receive step."""
    v = variables
    var_assignments = (
        f'{_dryrun_assignments(dryrun)}'
        f'sourcefs="{source}"; destfs="{dest}"; nextsnap="{nextsnap}"; '
        f'doincrementals="{v.get("doincrementals", "Y")}"; '
        f'dointermediates="{v.get("dointermediates", "Y")}"; '
        f'autoproceed="Y"; '
        f'allow_destructive="{v.get("allow_destructive", "N")}"; '
        f'receive_F_option="{v.get("receive_F_option", "F")}"; '
        f'releaseholds="{v.get("releaseholds", "N")}"; '
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
        var_assignments += f'includes=({arr}); '
    else:
        var_assignments += 'includes=(); '
    if excludes:
        items = shlex.split(excludes)
        arr = " ".join(f'"{i}"' for i in items)
        var_assignments += f'excludes=({arr}); '
    else:
        var_assignments += 'excludes=(); '
    if startwith:
        var_assignments += f'startwith="{startwith}"; '
    if endwith:
        var_assignments += f'endwith="{endwith}"; '
    bash_script = (
        f'source ~/bashinit; bashinit; mydir="{parent_dir}"; '
        f'source "$mydir/zfs-send-receive"; '
        f'{var_assignments}'
        f'send-receive'
    )
    return BashStep(
        ["bash", "-c", bash_script],
        f"zfs send/receive: {source} -> {dest}",
        is_rsync=False,
        fatal=True,
    )


def build_installed_programs_command(host):
    """Build command to run backup-installed-programs on a host."""
    apt_cmd = "cd /root && apt-mark showmanual > installed-programs"
    local_host = _get_local_hostname()
    if host and not _is_local_host(host):
        return BashStep(
            ["ssh", f"root@{host}", apt_cmd],
            f"[{host}] backup-installed-programs",
            is_rsync=False,
            fatal=False,
        )
    return BashStep(
        ["bash", "-c", apt_cmd],
        f"[{local_host}] backup-installed-programs",
        is_rsync=False,
        fatal=False,
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


def build_retention_command(parent_dir, label, pools=None, dryrun=False,
                            fatal=True):
    """Build the command to run retention/cleanup.

    If *pools* is provided, prune each pool in the given order; otherwise
    let ``zfscleanup`` use the configured pool list.
    """
    label_quoted = shlex.quote(label)
    dryrun_part = _dryrun_assignments(dryrun)
    base_script = (
        f'source ~/bashinit; bashinit; mydir="{parent_dir}"; '
        f'source "$mydir/zfscleanup"; '
        f'{dryrun_part}'
        f'autoproceed="Y"; '
        f'releaseholds="Y"; '
    )
    if pools:
        pool_list = " ".join(shlex.quote(p) for p in pools)
        bash_script = (
            f'{base_script}'
            f'overall_rc=0; '
            f'for pool in {pool_list}; do '
            f'  cleanup "$pool" "" {label_quoted} || overall_rc=$?; '
            f'done; '
            f'exit $overall_rc'
        )
        desc = f"Prune snapshots ({', '.join(pools)})"
    else:
        bash_script = (
            f'{base_script}'
            f'cleanup "" "" {label_quoted}'
        )
        desc = "Prune snapshots"
    return BashStep(
        ["bash", "-c", bash_script],
        desc,
        is_rsync=False,
        fatal=fatal,
    )

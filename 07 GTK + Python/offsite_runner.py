"""
Command builders for offsite backup operations.

Offsite backups copy ZFS datasets to an offsite pool via the zfs-send-receive
script, then optionally apply holds to protect the snapshots from accidental
deletion.
"""

import shlex
import subprocess

from backup_config import log_msg
from command_builders import BashStep, _dryrun_assignments


def detect_offsite_pool(candidates):
    """Detect which offsite pool from candidates is currently online.

    Args:
        candidates: list of pool names to look for.

    Returns:
        The first matching online pool name, or None.
    """
    try:
        result = subprocess.run(
            ["zpool", "list", "-H", "-o", "name,health"],
            capture_output=True, text=True, timeout=10, check=True,
        )
        online = {
            p[0] for p in (l.split("\t") for l in result.stdout.strip().split("\n") if l)
            if len(p) >= 2 and p[1] == "ONLINE"
        }
        for pool in candidates:
            if pool in online:
                return pool
    except (subprocess.SubprocessError, OSError):
        pass
    return None


def build_offsite_step_command(source, dest, variables, parent_dir, nextsnap,
                               includes_str, excludes_str,
                               dryrun=False):
    """Build bash command for an offsite send/receive step with optional holds.

    Each step runs send-receive and, if successful and applyholds='Y', applies
    ZFS holds to the source and destination snapshots — matching the behaviour
    of the zfssendoffsite shell script.

    Returns (command_list, description_string).
    """
    v = variables
    var_assignments = (
        f'{_dryrun_assignments(dryrun)}'
        f'sourcefs="{source}"; destfs="{dest}"; nextsnap="{nextsnap}"; '
        f'label="@offsite"; '
        f'doincrementals="{v.get("doincrementals", "Y")}"; '
        f'dointermediates="{v.get("dointermediates", "N")}"; '
        f'autoproceed="Y"; '
        f'allow_destructive="{v.get("allow_destructive", "N")}"; '
        f'receive_F_option="{v.get("receive_F_option", "F")}"; '
        f'verify_after_transfer="{v.get("verify_after_transfer", "Y")}"; '
        f'pv_rate_limit="{v.get("pv_rate_limit", "")}"; '
        f'applyholds="{v.get("applyholds", "Y")}"; '
    )

    startwith = v.get("startwith", "").strip()
    endwith = v.get("endwith", "").strip()

    if startwith:
        var_assignments += f'startwith="{startwith}"; '

    if endwith:
        var_assignments += f'endwith="{endwith}"; '

    # Merge global (from Dataset Selection) and per-step includes/excludes
    global_includes = v.get("includes", "").strip()
    global_excludes = v.get("excludes", "").strip()
    step_includes = includes_str.strip()
    step_excludes = excludes_str.strip()
    includes = f"{global_includes} {step_includes}".strip()
    excludes = f"{global_excludes} {step_excludes}".strip()

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

    # Combined send-receive + hold application in a single bash invocation.
    # After send-receive, $fsarray contains the datasets that were copied —
    # holds are applied to exactly those datasets on both source and dest.
    bash_script = (
        f'source ~/bashinit; bashinit; mydir="{parent_dir}"; '
        f'source "$mydir/zfshold"; '
        f'source "$mydir/zfs-send-receive"; '
        f'{var_assignments}'
        f'send-receive; rc=$?; '
        f'if [[ $rc -eq 0 && $applyholds = "Y" && $dryrun != "Y" ]]; then '
        f'sourcefspool=${{sourcefs%%/*}}; destfspool=${{destfs%%/*}}; '
        f'log_msg "Applying holds to $sourcefspool and $destfspool snapshots."; '
        f'for fs in "${{fsarray[@]}}"; do '
        f'destpath="$destfs/$fs"; '
        f'zfshold "${{label:1}}-$destfspool" "$fs" "$nextsnap"; '
        f'zfshold "${{label:1}}-$sourcefspool" "$destpath" "$nextsnap"; '
        f'done; '
        f'elif [[ $rc -eq 0 && $applyholds = "Y" && $dryrun = "Y" ]]; then '
        f'log_msg "Dry-run: Would apply holds to source and destination snapshots."; '
        f'fi; '
        f'exit $rc'
    )

    cmd = ["bash", "-c", bash_script]
    desc = f"offsite: {source} -> {dest}"
    if includes:
        desc += f" (includes: {includes})"
    if excludes:
        desc += f" (excludes: {excludes})"
    return BashStep(cmd, desc, is_rsync=False, fatal=True)

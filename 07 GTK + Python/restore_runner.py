"""
Command builders for ZFS restore operations.

Restores copy datasets from a backup pool back to the original (or a new)
destination using a two-step process:
  Part 1: Full copy from the oldest snapshot (destructive — destroys dest first)
  Part 2: Incremental copy of remaining snapshots

Both parts run in a single bash script so that the dataset list (fsarray) built
by Part 1 is reused by Part 2, guaranteeing both parts operate on the same
datasets.
"""

import shlex

from backup_config import log_msg
from command_builders import BashStep, _dryrun_assignments


def compute_auto_destination(source, known_pools):
    """Determine a restore destination by stripping leading qualifiers.

    The destination is computed by removing leading path components from the
    source until the first remaining qualifier is a known pool name. This lets
    a backup dataset such as ``backuppool/threeamigos/proxmox/vm-209-disk-0``
    restore back to ``threeamigos/proxmox/vm-209-disk-0`` when ``threeamigos``
    is a registered pool.

    Args:
        source: Fully-qualified source dataset.
        known_pools: Iterable of known pool name strings.

    Returns:
        Fully-qualified destination dataset string.

    Raises:
        ValueError: If no remaining qualifier matches a known pool.
    """
    src_parts = source.strip('/').split('/')
    known = set(known_pools)

    for n in range(1, len(src_parts) + 1):
        tail_parts = src_parts[n:]
        if not tail_parts:
            break
        if tail_parts[0] in known:
            return "/".join(tail_parts)

    raise ValueError(
        f"Cannot auto-determine destination for source '{source}'. "
        f"No remaining qualifier matches a known pool: {sorted(known)}"
    )


def compute_restore_params(source, dest):
    """Compute sourcefsremovequalifiers and destfs for zfs-send-receive.

    zfs-send-receive constructs the destination as:
        destfs + "/" + remove_leading_qualifiers(n, fs)
    where remove_leading_qualifiers strips n leading path components.

    Examples (from zfsremoveleadingqualifiers):
        source="poolA/data", dest="poolB/poolA/data"
        → (0, "poolB")   # strip 0 → "poolA/data", dest = poolB/poolA/data

        source="poolB/poolA/data", dest="poolA/data"
        → (2, "poolA") # strip 2 → "data", dest = poolA/data

        source="poolA/data", dest="poolB/data"
        → (1, "poolB")   # strip 1 → "data", dest = poolB/data

    Args:
        source: Fully-qualified source dataset
        dest: Fully-qualified destination dataset

    Returns:
        (sourcefsremovequalifiers, destfs) tuple.

    Raises:
        ValueError: If source and dest are incompatible.
    """
    src_parts = source.strip('/').split('/')
    dst_parts = dest.strip('/').split('/')
    destfs = dst_parts[0]

    for n in range(len(src_parts) + 1):
        tail_parts = src_parts[n:]
        if tail_parts:
            candidate = destfs + "/" + "/".join(tail_parts)
        else:
            candidate = destfs
        if candidate == dest:
            return n, destfs

    raise ValueError(
        f"Cannot compute restore parameters: "
        f"source '{source}' and dest '{dest}' have no compatible mapping. "
        f"The destination must end with a suffix of the source path."
    )


def build_restore_command(source, removequalifiers, destfs, parent_dir,
                          advanced_vars, do_part1, do_part2,
                          dryrun=False):
    """Build the bash command for a restore operation.

    Both parts are combined into a single bash script. After Part 1, the
    dataset list (fsarray) is saved to a temp file. Part 2 loads it and
    uses exact-match includes to operate on the same datasets.

    Args:
        source: Source dataset
        removequalifiers: Number of leading qualifiers to strip
        destfs: Destination pool/prefix
        parent_dir: Path to the project root directory
        advanced_vars: dict with keys: depth, label, includes, excludes,
                       startwith, endwith (all strings, may be empty)
        do_part1: bool — run Part 1 (full copy)
        do_part2: bool — run Part 2 (incremental)

    Returns:
        (command_list, description_string) tuple.
    """
    v = advanced_vars

    # Build advanced variable assignments
    adv = ""
    depth = v.get("depth", "").strip()
    label = v.get("label", "").strip()
    startwith = v.get("startwith", "").strip()
    endwith = v.get("endwith", "").strip()
    includes = v.get("includes", "").strip()
    excludes = v.get("excludes", "").strip()

    if depth:
        adv += f'depth="{depth}"; '
    if label:
        adv += f'label="{label}"; '
    if startwith:
        adv += f'startwith="{startwith}"; '
    if endwith:
        adv += f'endwith="{endwith}"; '

    if includes:
        items = shlex.split(includes)
        arr = " ".join(f'"{i}"' for i in items)
        adv += f'includes=({arr}); '
    else:
        adv += 'includes=(); '

    if excludes:
        items = shlex.split(excludes)
        arr = " ".join(f'"{i}"' for i in items)
        adv += f'excludes=({arr}); '
    else:
        adv += 'excludes=(); '

    # Preamble — shared by both parts
    # Redirect stdout to stderr so echo output (dataset lists) stays in order
    # with log_msg output and all appears in the GUI log panel.
    preamble = (
        f'exec 1>&2; '
        f'source ~/bashinit; bashinit; mydir="{parent_dir}"; '
        f'source "$mydir/zfssnapbuild"; '
        f'source "$mydir/zfs-send-receive"; '
        f'{_dryrun_assignments(dryrun)}'
        f'sourcefs="{source}"; '
        f'sourcefsremovequalifiers={removequalifiers}; '
        f'destfs="{destfs}"; '
        f'nextsnap="notneeded"; '
        f'{adv}'
        f'fsarray_file="/tmp/zfsrestore_fsarray_$$"; '
    )

    parts = []

    if do_part1:
        parts.append(
            f'log_msg "Part one: Full copy using the oldest available snapshot."; '
            f'force="Y"; releaseholds="Y"; '
            f'doincrementals="N"; dointermediates="N"; '
            f'commsnap_mostrecent="OLDEST"; '
            f'autoproceed="N"; '
            f'send-receive "$sourcefs"; rc=$?; '
            f'if [[ $rc -ne 0 ]]; then rm -f "$fsarray_file"; exit $rc; fi; '
            # Save fsarray for Part 2
            f'printf "%s\\n" "${{fsarray[@]}}" > "$fsarray_file"; '
        )

    if do_part2:
        part2_script = (
            f'log_msg "Part two: Incremental copy of remaining snapshots."; '
            f'force="N"; releaseholds="N"; '
            f'doincrementals="Y"; dointermediates="Y"; '
            f'commsnap_mostrecent=""; '
            f'autoproceed="Y"; '
        )
        if do_part1:
            # Load saved fsarray as exact-match includes
            part2_script += (
                f'if [[ -f "$fsarray_file" ]]; then '
                f'includes=(); '
                f'while IFS= read -r _ds; do includes+=("=$_ds"); done < "$fsarray_file"; '
                f'rm -f "$fsarray_file"; '
                f'fi; '
            )
        part2_script += (
            f'send-receive "$sourcefs"; rc=$?; '
            f'rm -f "$fsarray_file"; '
            f'exit $rc'
        )
        parts.append(part2_script)
    else:
        # Part 1 only — clean up temp file
        parts.append(f'rm -f "$fsarray_file"; exit 0')

    bash_script = preamble + "".join(parts)
    cmd = ["bash", "-c", bash_script]

    which = []
    if do_part1:
        which.append("full copy")
    if do_part2:
        which.append("incremental")
    desc = f"restore: {source} -> {destfs} ({' + '.join(which)})"

    return BashStep(cmd, desc, is_rsync=False, fatal=True)

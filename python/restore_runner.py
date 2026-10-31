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
    src_parts = source.strip("/").split("/")
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
    src_parts = source.strip("/").split("/")
    dst_parts = dest.strip("/").split("/")
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


def build_restore_command(
    source,
    removequalifiers,
    destfs,
    parent_dir,
    advanced_vars,
    dryrun=False,
    recursive=False,
):
    """Build the bash command for a restore operation.

    Both parts are combined into a single bash script. Part 1 does the
    destructive full-copy pass from the oldest snapshot; Part 2 catches the
    remaining snapshots up incrementally, using the dataset list (fsarray)
    Part 1 saved to a temp file as exact-match includes.

    The payload is idempotent when interrupted and re-run: it sets
    restore_resume="Y", so Part 1 skips any destination dataset that already
    holds a GUID-verified snapshot lineage with the source (those are caught
    up by Part 2), and zfs-send-receive honors receive resume tokens on every
    pass — an interrupted resumable receive continues from its token instead
    of being discarded. Only datasets without a verified lineage are
    destroyed and fully re-copied.

    Args:
        source: Source dataset
        removequalifiers: Number of leading qualifiers to strip
        destfs: Destination pool/prefix
        parent_dir: Path to the project root directory
        advanced_vars: dict with keys: depth, label, includes, excludes,
                       startwith, endwith (all strings, may be empty)
        recursive: bool — when True, restore all descendant datasets;
                         when False, restore only the named dataset unless
                         an explicit depth is provided in advanced_vars
        dryrun: bool — when True, append dry-run assignments

    Returns:
        BashStep for the restore operation.
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

    # A non-empty advanced depth overrides the recursive toggle so power users
    # can still set partial recursion (e.g. depth="1").
    if depth:
        adv += f'depth="{depth}"; '
    elif not recursive:
        adv += 'depth="0"; '
    if label:
        adv += f'label="{label}"; '
    if startwith:
        adv += f'startwith="{startwith}"; '
    if endwith:
        adv += f'endwith="{endwith}"; '

    if includes:
        items = shlex.split(includes)
        arr = " ".join(f'"{i}"' for i in items)
        adv += f"includes=({arr}); "
    else:
        adv += "includes=(); "

    if excludes:
        items = shlex.split(excludes)
        arr = " ".join(f'"{i}"' for i in items)
        adv += f"excludes=({arr}); "
    else:
        adv += "excludes=(); "

    verify_after_transfer = v.get("verify_after_transfer", "Y").strip() or "Y"
    transfer_rate_limit = v.get("transfer_rate_limit", "").strip()
    adv += f'verify_after_transfer="{verify_after_transfer}"; '
    adv += f'transfer_rate_limit="{transfer_rate_limit}"; '

    # Post-restore helper: ensure VM disk zvols are exported as iSCSI LUNs.
    ensure_func = (
        "ensure_restored_iscsi() { "
        '[[ "${dryrun:-N}" == "Y" ]] && return 0; '
        "local _fs _dest; local -a _dests=(); "
        'for _fs in "${fsarray[@]}"; do '
        '_dest=$(remove_leading_qualifiers "$sourcefsremovequalifiers" "$_fs"); '
        '[[ "$_dest" != "" && ${_dest:0:1} != "/" ]] && _dest="/$_dest"; '
        '_dests+=("${destfs}${_dest}"); '
        "done; "
        "if [[ ${#_dests[@]} -gt 0 ]]; then "
        'log_msg "INFO: Ensuring iSCSI LUNs for restored VM disks..."; '
        '"$mydir/ensure-restored-vm-iscsi" "${_dests[@]}"; '
        "fi; "
        "}; "
    )

    # Preamble — shared by both parts
    # Redirect stdout to stderr so echo output (dataset lists) stays in order
    # with log_msg output and all appears in the GUI log panel.
    preamble = (
        f"exec 1>&2; "
        f'source ~/bashinit; bashinit; mydir="{parent_dir}"; '
        f'source "$mydir/zfssnapbuild"; '
        f'source "$mydir/zfs-send-receive"; '
        f'source "$mydir/zfsremoveleadingqualifiers"; '
        f"{ensure_func}"
        f"{_dryrun_assignments(dryrun)}"
        f'sourcefs="{source}"; '
        f"sourcefsremovequalifiers={removequalifiers}; "
        f'destfs="{destfs}"; '
        f'nextsnap="notneeded"; '
        f'restore_resume="Y"; '
        f"{adv}"
        f'fsarray_file="/tmp/zfsrestore_fsarray_$$"; '
        # Interrupt hygiene: the fsarray temp file must not survive a failed
        # or cancelled run. append_exit_trap covers every exit path; the TERM
        # trap routes the GUI's cancel signal (SIGTERM to this shell) into an
        # orderly exit so the exit traps run after the current zfs pipeline
        # ends. (Lock-wait SIGINT already flows through zfslockmanager's own
        # INT trap into a normal error exit.)
        f"append_exit_trap 'rm -f \"$fsarray_file\"'; "
        f"trap 'exit 143' TERM; "
    )

    # Part 1: destructive full-copy pass from the oldest snapshot. With
    # restore_resume="Y" this destroys only datasets without a verified
    # lineage; interrupted resumable receives are resumed from their tokens.
    part1_script = (
        'log_msg "Part one: Full copy using the oldest available snapshot."; '
        'force="Y"; releaseholds="Y"; '
        'releaseholds_tags=("offsite-*"); '
        'doincrementals="N"; dointermediates="N"; '
        'commsnap_mostrecent="OLDEST"; '
        'autoproceed="N"; '
        'send-receive "$sourcefs"; rc=$?; '
        "if [[ $rc -ne 0 ]]; then exit $rc; fi; "
        # Save fsarray for Part 2
        'printf "%s\\n" "${fsarray[@]}" > "$fsarray_file"; '
    )

    # Part 2: incremental catch-up of the remaining snapshots, resuming from
    # each dataset's newest common snapshot (and any resume tokens).
    part2_script = (
        'log_msg "Part two: Incremental copy of remaining snapshots."; '
        'force="N"; releaseholds="N"; '
        'doincrementals="Y"; dointermediates="Y"; '
        'commsnap_mostrecent=""; '
        'autoproceed="Y"; '
        # Load Part 1's fsarray as exact-match includes
        'if [[ -f "$fsarray_file" ]]; then '
        "includes=(); "
        'while IFS= read -r _ds; do includes+=("=$_ds"); done < "$fsarray_file"; '
        "fi; "
        'send-receive "$sourcefs"; rc=$?; '
        "if [[ $rc -ne 0 ]]; then exit $rc; fi; "
        "ensure_restored_iscsi; "
        "exit 0"
    )

    bash_script = preamble + part1_script + part2_script
    cmd = ["bash", "-c", bash_script]

    desc = f"restore: {source} -> {destfs} (full copy + incremental)"

    metadata = {
        "source": source,
        "dest": destfs,
        "label": advanced_vars.get("label", ""),
    }
    return BashStep(cmd, desc, is_rsync=False, fatal=True, metadata=metadata)

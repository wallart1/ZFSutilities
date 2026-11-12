"""
Command builders for offsite backup operations.

Offsite backups copy ZFS datasets to an offsite pool via the zfs-send-receive
script, then optionally apply holds to protect the snapshots from accidental
deletion.

Onward legs — steps whose source is itself a backup destination — copy
backup copies, which hold no local properties, so they never capture
property manifests (property_manifest='N') and instead carry the
existing zfsutilities-manifests datasets along as ordinary datasets,
mirroring zfssendoffsite step 4.
"""

import shlex
import subprocess

from command_builders import BashStep, _dryrun_assignments


def _online_pool_names():
    """Return the set of pool names currently reported as ONLINE."""
    try:
        result = subprocess.run(
            ["zpool", "list", "-H", "-o", "name,health"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=10,
            check=True,
        )
        return {
            p[0]
            for p in (l.split("\t") for l in result.stdout.strip().split("\n") if l)
            if len(p) >= 2 and p[1] == "ONLINE"
        }
    except (subprocess.SubprocessError, OSError):
        return set()


def detect_offsite_pool(candidates):
    """Detect which offsite pool from candidates is currently online.

    Args:
        candidates: list of pool names to look for.

    Returns:
        The first matching online pool name, or None.
    """
    online = _online_pool_names()
    for pool in candidates:
        if pool in online:
            return pool
    return None


def detect_offsite_pools(candidates):
    """Return all offsite-candidate pools that are currently online.

    Args:
        candidates: list of pool names to look for.

    Returns:
        List of matching online pool names in the order they appear in
        `candidates`.  Empty list if none are online or zpool cannot be run.
    """
    online = _online_pool_names()
    return [pool for pool in candidates if pool in online]


def is_onward_leg(source, steps, backup_dests=()):
    """Return True when a step's source is itself a backup destination.

    A step is an onward leg when its source equals the destination of
    another configured step, or one of the daily backup's send/receive
    destinations — the chain shape zfssendoffsite step 4 has: it copies
    backup copies onward to the offsite pool.

    Args:
        source: the step's source dataset.
        steps: the offsite config's step dicts (active or not — any step
            writing to the source proves it is a backup destination).
        backup_dests: destination names of the backup config's
            send/receive steps.

    Returns:
        True when the source is a backup destination; False otherwise.
    """
    dests = {s.get("dest", "") for s in steps if isinstance(s, dict) and s.get("dest", "")}
    dests.update(d for d in backup_dests if d)
    return source in dests


def discover_manifest_stores(source):
    """Return the property-manifest datasets that exist under <source>.

    Capture always creates them at depth 2 (<source>/<pool>/
    zfsutilities-manifests), so one bounded listing finds them all.

    Args:
        source: the step's source dataset (the backup root).

    Returns:
        Pool-anchored names relative to source (e.g.
        "tank/zfsutilities-manifests"), in listing order. Empty when the
        listing fails or no store exists.
    """
    try:
        result = subprocess.run(
            ["zfs", "list", "-H", "-t", "filesystem", "-d", "2", "-o", "name", source],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=10,
            check=True,
        )
    except (subprocess.SubprocessError, OSError):
        return []
    stores = []
    prefix = f"{source}/"
    for line in result.stdout.splitlines():
        name = line.split("\t")[0].strip()
        if name.startswith(prefix) and name.endswith("/zfsutilities-manifests"):
            stores.append(name[len(prefix) :])
    return stores


def manifests_include_patterns(includes_str, stores, source):
    """Choose which manifest datasets ride an onward leg.

    Anchored include patterns (containing "/", optionally '='-exact, with
    an optional <source>/ prefix) name their pool directly, so a store
    rides when an include names its pool. Unanchored patterns cannot name
    a pool, so every discovered store rides rather than risk leaving a
    dataset's properties behind — the stores are tiny and prune in
    lockstep. Empty includes add nothing: the stores are children of the
    source and ride as ordinary datasets anyway.

    Args:
        includes_str: the step's includes field (space-separated patterns).
        stores: store names relative to source (discover_manifest_stores).
        source: the step's source dataset.

    Returns:
        The list of stores that should be appended to the step's includes.
    """
    patterns = [p for p in shlex.split(includes_str) if p]
    if not patterns:
        return []
    anchored = set()
    unanchored = False
    for pattern in patterns:
        body = pattern.lstrip("=")
        if body.startswith(f"{source}/"):
            body = body[len(source) + 1 :]
        if "/" in body:
            anchored.add(body.split("/")[0])
        else:
            unanchored = True
    riding = []
    for store in stores:
        pool = store.split("/")[0]
        if pool in anchored or unanchored:
            riding.append(store)
    return riding


def build_offsite_step_command(
    source,
    dest,
    variables,
    parent_dir,
    nextsnap,
    includes_str,
    excludes_str,
    dryrun=False,
    sibling_steps=None,
    backup_dests=(),
):
    """Build bash command for an offsite send/receive step with optional holds.

    Each step runs send-receive and, if successful and applyholds='Y', applies
    ZFS holds to the source and destination snapshots — matching the behaviour
    of the zfssendoffsite shell script.

    When sibling_steps is given, an onward leg (source is itself a backup
    destination, per is_onward_leg) forces property_manifest='N' — copies
    hold no local properties — and appends the manifest datasets that exist
    under the source to the step's includes, so they travel to the offsite
    pool as ordinary datasets (metadata["manifests"] names them).

    Returns (command_list, description_string).
    """
    v = variables
    onward = False
    manifest_stores = []
    if sibling_steps is not None:
        onward = is_onward_leg(source, sibling_steps, backup_dests)
        if onward:
            manifest_stores = manifests_include_patterns(
                includes_str, discover_manifest_stores(source), source
            )
            if manifest_stores:
                includes_str = f"{includes_str} {' '.join(manifest_stores)}".strip()
    manifest_setting = "N" if onward else v.get("property_manifest", "Y")
    var_assignments = (
        f"{_dryrun_assignments(dryrun)}"
        f'sourcefs="{source}"; destfs="{dest}"; nextsnap="{nextsnap}"; '
        f'label="@offsite"; '
        f'doincrementals="{v.get("doincrementals", "Y")}"; '
        f'dointermediates="{v.get("dointermediates", "N")}"; '
        f'autoproceed="Y"; '
        f'allow_destructive="{v.get("allow_destructive", "N")}"; '
        f'receive_F_option="{v.get("receive_F_option", "F")}"; '
        f'verify_after_transfer="{v.get("verify_after_transfer", "Y")}"; '
        f'property_manifest="{manifest_setting}"; '
        f'transfer_rate_limit="{v.get("transfer_rate_limit", "")}"; '
        f'applyholds="{v.get("applyholds", "Y")}"; '
    )

    startwith = v.get("startwith", "").strip()
    endwith = v.get("endwith", "").strip()

    if startwith:
        var_assignments += f'startwith="{startwith}"; '

    if endwith:
        var_assignments += f'endwith="{endwith}"; '

    # The run log names what the derivation decided, so the travel is
    # visible wherever the payload runs (GUI log, e2e, terminal). Dataset
    # names contain no characters that need quoting inside the string.
    onward_log = ""
    if onward:
        if manifest_stores:
            stores = " ".join(manifest_stores)
            onward_log = (
                f'log_msg "INFO: Onward leg {source} -> {dest}: property manifests '
                f'travel via {stores}."; '
            )
        else:
            onward_log = (
                f'log_msg "INFO: Onward leg {source} -> {dest}: property manifest '
                f'capture disabled (copies hold no local properties)."; '
            )

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
        var_assignments += f"includes=({arr}); "
    else:
        var_assignments += "includes=(); "

    if excludes:
        items = shlex.split(excludes)
        arr = " ".join(f'"{i}"' for i in items)
        var_assignments += f"excludes=({arr}); "
    else:
        var_assignments += "excludes=(); "

    # Combined send-receive + hold application in a single bash invocation.
    # After send-receive, $fsarray contains the datasets that were copied —
    # holds are applied to exactly those datasets on both source and dest.
    bash_script = (
        f'source ~/bashinit; bashinit; mydir="{parent_dir}"; '
        f'source "$mydir/zfshold"; '
        f'source "$mydir/zfs-send-receive"; '
        f"{var_assignments}"
        f"{onward_log}"
        f"send-receive; rc=$?; "
        f'if [[ $rc -eq 0 && $applyholds = "Y" && $dryrun != "Y" ]]; then '
        f"sourcefspool=${{sourcefs%%/*}}; destfspool=${{destfs%%/*}}; "
        f'log_msg "Applying holds to $sourcefspool and $destfspool snapshots."; '
        f'for fs in "${{fsarray[@]}}"; do '
        f'destpath="$destfs/$fs"; '
        f'zfshold "${{label:1}}-$destfspool" "$fs" "$nextsnap"; '
        f'zfshold "${{label:1}}-$sourcefspool" "$destpath" "$nextsnap"; '
        f"done; "
        f'elif [[ $rc -eq 0 && $applyholds = "Y" && $dryrun = "Y" ]]; then '
        f'log_msg "Dry-run: Would apply holds to source and destination snapshots."; '
        f"fi; "
        f"exit $rc"
    )

    cmd = ["bash", "-c", bash_script]
    desc = f"offsite: {source} -> {dest}"
    if includes:
        desc += f" (includes: {includes})"
    if excludes:
        desc += f" (excludes: {excludes})"
    metadata = {
        "source": source,
        "dest": dest,
        "label": "offsite",
        "onward": onward,
        "manifests": manifest_stores,
    }
    return BashStep(cmd, desc, is_rsync=False, fatal=True, metadata=metadata)

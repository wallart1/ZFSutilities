"""Scope-alignment validation for backup and offsite jobs.

Backup and offsite jobs that send overlapping filesystem trees to the same
destination pool must agree on which datasets are snapshotted with the
@offsite label. If the destination receives @offsite snapshots for a dataset
that the source does not, the next daily backup must roll that destination
snapshot back before it can receive the @dailybackup snapshot. This module
detects that situation and produces clear warnings.
"""

import fnmatch
import shlex


def _parse_filters(value):
    """Convert a string or list into a list of include/exclude filters.

    Strings are split with shell-like quoting so filters such as
    '=NVME1 proxmox' are handled correctly.
    """
    if isinstance(value, list):
        return list(value)
    if not value or not str(value).strip():
        return []
    return shlex.split(str(value))


def _matches_filter(dataset, pattern):
    """Return True if *dataset* matches a single filter pattern.

    Patterns starting with '=' require an exact match. All other patterns are
    treated as substrings and matched anywhere in the dataset name, mirroring
    the behaviour of zfsbuildfsarray.
    """
    if pattern.startswith("="):
        return dataset == pattern[1:]
    return fnmatch.fnmatch(dataset, f"*{pattern}*")


def _matches_filters(dataset, includes, excludes):
    """Return True if *dataset* is included and not excluded."""
    if includes and not any(
        _matches_filter(dataset, inc) for inc in includes
    ):
        return False
    return not (excludes and any(
        _matches_filter(dataset, exc) for exc in excludes
    ))


def _is_under(dataset, parent):
    """Return True if *dataset* is *parent* or a descendant of *parent*."""
    return dataset == parent or dataset.startswith(parent + "/")


def _destination_dataset(source, destination):
    """Compute the destination dataset for a source/dest send-receive pair.

    This mirrors _compute_destination_root from feature_config.py. If the
    destination already ends with the source path, the destination is used as
    is; otherwise the source path is appended to the destination.
    """
    src_parts = [p for p in str(source).split("/") if p]
    dst_parts = [p for p in str(destination).split("/") if p]

    if not src_parts:
        return destination

    max_suffix = 0
    max_possible = min(len(src_parts), len(dst_parts))
    for length in range(1, max_possible + 1):
        if src_parts[-length] == dst_parts[-length]:
            max_suffix += 1
        else:
            break

    if max_suffix == len(src_parts) or max_suffix == len(dst_parts):
        return destination

    return f"{destination}/{source}" if destination else source


def _extract_steps(cfg, profile_type, profile_name, label):
    """Return a list of effective send/receive steps from a config dict.

    Each step is normalized to a dict with profile metadata and parsed
    includes/excludes. Inactive steps are skipped.
    """
    steps = []
    if profile_type == "backup":
        sr_steps = cfg.get("send_receive_steps", [])
    elif profile_type == "offsite":
        sr_steps = cfg.get("steps", [])
    else:
        return steps

    global_includes = _parse_filters(cfg.get("variables", {}).get("includes", ""))
    global_excludes = _parse_filters(cfg.get("variables", {}).get("excludes", ""))

    for step in sr_steps:
        if not step.get("active", True):
            continue
        step_includes = _parse_filters(step.get("includes", ""))
        step_excludes = _parse_filters(step.get("excludes", ""))
        # Preserve order while deduplicating; the exact semantics of duplicate
        # filters do not matter for overlap detection.
        includes = list(dict.fromkeys(global_includes + step_includes))
        excludes = list(dict.fromkeys(global_excludes + step_excludes))
        steps.append({
            "profile_type": profile_type,
            "profile_name": profile_name,
            "source": str(step.get("source", "")).strip(),
            "dest": str(step.get("dest", "")).strip(),
            "includes": includes,
            "excludes": excludes,
            "active": True,
            "label": label,
        })
    return steps


def _find_offsite_covering_dataset(dataset, offsite_steps):
    """Return the first active offsite step that snapshots *dataset*, or None."""
    for step in offsite_steps:
        if not step["active"]:
            continue
        if not _is_under(dataset, step["source"]):
            continue
        if _matches_filters(dataset, step["includes"], step["excludes"]):
            return step
    return None


def validate_effective_steps(items):
    """Validate a list of effective backup/offsite steps.

    Args:
        items: List of step dicts produced by _extract_steps.

    Returns:
        A list of human-readable warning strings. An empty list means no
        scope misalignment was detected.
    """
    warnings = []
    backup_steps = [
        i for i in items if i.get("profile_type") == "backup"
    ]
    offsite_steps = [
        i for i in items if i.get("profile_type") == "offsite"
    ]

    for bstep in backup_steps:
        source_b = bstep["source"]
        dest_b = bstep["dest"]
        if not source_b or not dest_b:
            continue

        # If the backup step itself would not snapshot the source root, the
        # root cannot be the cause of a rollback.
        if not _matches_filters(
            source_b, bstep["includes"], bstep["excludes"]
        ):
            continue

        dest_dataset = _destination_dataset(source_b, dest_b)
        source_cover = _find_offsite_covering_dataset(source_b, offsite_steps)
        dest_cover = _find_offsite_covering_dataset(dest_dataset, offsite_steps)

        if dest_cover and not source_cover:
            offsite_name = dest_cover["profile_name"]
            warnings.append(
                f"Scope mismatch: backup '{bstep['profile_name']}' sends "
                f"'{source_b}' to '{dest_b}', but no offsite job snapshots "
                f"'{source_b}'. The destination '{dest_dataset}' will receive "
                f"@offsite snapshots from offsite '{offsite_name}' that "
                f"'{source_b}' lacks, causing daily backups to roll back. "
                f"Align the source scopes (for example, change the backup source "
                f"to match the offsite source/includes)."
            )

    return warnings


def validate_gui_settings(backup_cfg, offsite_cfg):
    """Validate current GUI Backup and Offsite settings.

    Args:
        backup_cfg: Dict returned by backup_page.collect_backup_config or
            feature_config.get_backup_config.
        offsite_cfg: Dict returned by offsite_page.collect_offsite_config or
            feature_config.get_offsite_config.

    Returns:
        List of warning strings.
    """
    items = []
    items.extend(_extract_steps(
        backup_cfg, "backup", "current backup settings",
        backup_cfg.get("variables", {}).get("label", "dailybackup")
    ))
    items.extend(_extract_steps(
        offsite_cfg, "offsite", "current offsite settings", "offsite"
    ))
    return validate_effective_steps(items)


def validate_profiles(profiles):
    """Validate saved profiles for scope alignment.

    Args:
        profiles: List of profile dicts as returned by profile_manager.

    Returns:
        List of warning strings.
    """
    items = []
    for profile in profiles:
        tab_type = profile.get("tab_type")
        profile_name = profile.get("profile_name", "unnamed")
        cfg = profile.get("config", {})
        if tab_type == "backup":
            label = cfg.get("variables", {}).get("label", "dailybackup")
        elif tab_type == "offsite":
            label = "offsite"
        else:
            continue
        items.extend(_extract_steps(cfg, tab_type, profile_name, label))
    return validate_effective_steps(items)

"""Pure-logic workload profile helpers.

No GTK and no direct subprocess calls. All ZFS I/O is delegated to callers via
``ZfsRepository``.
"""

from __future__ import annotations

import shlex

LIVE_PROPERTIES = (
    "recordsize",
    "compression",
    "atime",
    "logbias",
    "sync",
    "primarycache",
    "special_small_blocks",
)
CREATION_ONLY_PROPERTIES = ("volblocksize", "ashift")
ALL_KNOWN_PROPERTIES = LIVE_PROPERTIES + CREATION_ONLY_PROPERTIES

# Properties that are safe to request with ``zfs get`` on a filesystem or volume.
# ``ashift`` is intentionally excluded because it is a pool/vdev property.
ZFS_GET_PROPERTIES = LIVE_PROPERTIES + ("volblocksize",)


def properties_for_profile(profile: dict, ds_type: str) -> dict[str, str]:
    """Return profile properties that apply to the given dataset type.

    Filters by ``applies_to`` and drops properties that are meaningless for the
    dataset type (e.g. ``volblocksize`` for filesystems, ``recordsize`` and
    ``atime`` for volumes).
    """
    applies_to = profile.get("applies_to", [])
    if ds_type not in applies_to:
        return {}

    result: dict[str, str] = {}
    for prop, value in profile.get("properties", {}).items():
        if prop not in ALL_KNOWN_PROPERTIES:
            continue
        if ds_type == "filesystem" and prop == "volblocksize":
            continue
        if ds_type == "volume" and prop in ("recordsize", "atime"):
            continue
        result[prop] = str(value)
    return result


def match_profile(profiles: dict[str, dict], ds_type: str, live_props: dict[str, str]) -> str:
    """Return the first profile whose applicable properties match *live_props*.

    Comparison uses literal string equality. Profiles that do not apply to the
    dataset type are skipped. Creation-only properties are not part of the
    match decision because they cannot be changed after creation; they are
    display-only in the apply plan.
    """
    for name, profile in profiles.items():
        applies_to = profile.get("applies_to", [])
        if ds_type not in applies_to:
            continue
        applicable = properties_for_profile(profile, ds_type)
        if not applicable:
            continue
        matches = True
        for prop, target_value in applicable.items():
            if prop in CREATION_ONLY_PROPERTIES:
                continue
            live_value = live_props.get(prop, "-")
            if live_value != target_value:
                matches = False
                break
        if matches:
            return name
    return "custom"


def build_apply_plan(
    profile: dict, dataset: str, ds_type: str, live_props: dict[str, str]
) -> list[dict]:
    """Build a preview plan for applying *profile* to *dataset*.

    Each entry describes one property, whether it will be applied, and why.
    """
    plan: list[dict] = []
    applies_to = profile.get("applies_to", [])
    for prop, target_value in profile.get("properties", {}).items():
        if prop not in ALL_KNOWN_PROPERTIES:
            continue

        live_value = live_props.get(prop)
        target_value = str(target_value)

        if ds_type not in applies_to:
            plan.append(
                {
                    "property": prop,
                    "value": target_value,
                    "live_value": live_value,
                    "dataset": dataset,
                    "explanation": f"{prop} does not apply to {ds_type} datasets; skipped.",
                    "will_apply": False,
                }
            )
            continue

        if ds_type == "filesystem" and prop == "volblocksize":
            plan.append(
                {
                    "property": prop,
                    "value": target_value,
                    "live_value": live_value,
                    "dataset": dataset,
                    "explanation": (f"{prop} does not apply to filesystem datasets; skipped."),
                    "will_apply": False,
                }
            )
            continue

        if ds_type == "volume" and prop in ("recordsize", "atime"):
            plan.append(
                {
                    "property": prop,
                    "value": target_value,
                    "live_value": live_value,
                    "dataset": dataset,
                    "explanation": (f"{prop} does not apply to volume datasets; skipped."),
                    "will_apply": False,
                }
            )
            continue

        if prop in CREATION_ONLY_PROPERTIES:
            plan.append(
                {
                    "property": prop,
                    "value": target_value,
                    "live_value": live_value,
                    "dataset": dataset,
                    "explanation": (f"{prop} is fixed at dataset creation and cannot be changed."),
                    "will_apply": False,
                }
            )
            continue

        if live_value == target_value:
            explanation = f"{prop} is already set to {target_value}."
            will_apply = False
        else:
            from_value = live_value if live_value is not None else "-"
            explanation = (
                f"{prop} will change from {from_value} to {target_value}. "
                "Existing data is unaffected until rewritten."
            )
            will_apply = True

        plan.append(
            {
                "property": prop,
                "value": target_value,
                "live_value": live_value,
                "dataset": dataset,
                "explanation": explanation,
                "will_apply": will_apply,
            }
        )
    return plan


def zfs_set_commands_with_entries(plan: list[dict]) -> list[tuple[str, dict]]:
    """Return ``(command, plan_entry)`` pairs for entries that will apply.

    Callers that need to describe or annotate each command should use this
    instead of re-parsing the command string, which couples them to the exact
    command format.
    """
    pairs: list[tuple[str, dict]] = []
    for entry in plan:
        if not entry.get("will_apply"):
            continue
        prop = entry["property"]
        # Values come from user-editable profiles and are executed via
        # ``bash -c``, so quote defensively; simple tokens pass through
        # unchanged.
        value = shlex.quote(str(entry["value"]))
        dataset = shlex.quote(entry.get("dataset", ""))
        pairs.append((f"zfs set {prop}={value} {dataset}", entry))
    return pairs


def build_zfs_set_commands(plan: list[dict]) -> list[str]:
    """Return the ``zfs set`` command strings for plan entries that will apply."""
    return [cmd for cmd, _entry in zfs_set_commands_with_entries(plan)]


def profile_has_warning(name: str, profile: dict, pool_has_special: bool) -> bool:
    """Return True if applying the profile merits a warning."""
    return name == "scratch" or (name == "small-files" and not pool_has_special)


def warning_text(name: str, profile: dict, pool_has_special: bool) -> str | None:
    """Return a warning string for the profile, or None if no warning applies."""
    if name == "scratch":
        return profile.get("notes")
    if name == "small-files" and not pool_has_special:
        return profile.get("notes")
    return None

"""Pure-logic pool profile helpers.

No GTK and no direct subprocess calls. All ZFS I/O is delegated to callers via
``ZfsRepository``. Pool profiles are the pool-scope counterpart of workload
profiles: named bundles of the settings that shape a pool at creation — the
blocksize (``ashift``, fixed at creation), the live-settable pool properties
written explicitly as ``-o`` so nothing is left to drifting ``zpool create``
defaults, and the filesystem properties applied to the pool root as ``-O`` so
children inherit them. Blocksize changes are why Migrate Pool exists: it is
the only way to rewrite a pool with a different blocksize.
"""

from __future__ import annotations

from workload_profiles import LIVE_PROPERTIES

# Pool-scope, live-settable properties a profile may carry. Everything here is
# written explicitly at pool creation (``zpool create -o prop=value``).
POOL_PROPERTIES = (
    "autotrim",
    "autoexpand",
    "autoreplace",
    "failmode",
    "multihost",
    "listsnapshots",
    "delegation",
)

# Literal values accepted per pool property (values are case-sensitive, as
# zpool itself is). ``dedupditto`` and friends are deliberately absent: they
# are deprecated or not meaningful for small/medium deployments.
POOL_PROPERTY_VALUES = {
    "autotrim": ("on", "off"),
    "autoexpand": ("on", "off"),
    "autoreplace": ("on", "off"),
    "failmode": ("wait", "continue", "panic"),
    "multihost": ("on", "off"),
    "listsnapshots": ("on", "off"),
    "delegation": ("on", "off"),
}

# Blocksize choices stored in a profile. BLOCKSIZE_RECOMMENDED resolves at
# creation time through the disk-probing recommendation engine (starts at
# 4096 bytes and only rises); BLOCKSIZE_AUTO leaves the decision to ZFS.
BLOCKSIZE_RECOMMENDED = "recommended"
BLOCKSIZE_AUTO = "auto"
BLOCKSIZE_CHOICES = (
    BLOCKSIZE_RECOMMENDED,
    BLOCKSIZE_AUTO,
    "512 bytes",
    "4096 bytes",
    "8192 bytes",
)
BLOCKSIZE_BYTES = (512, 4096, 8192)

ASHIFT_BY_LABEL = {"512 bytes": 9, "4096 bytes": 12, "8192 bytes": 13}
LABEL_BY_ASHIFT = {ashift: label for label, ashift in ASHIFT_BY_LABEL.items()}

# Pseudo-profile offered first in Migrate Pool: settings derived from the
# source pool itself. Never saved in the config store.
MATCH_ORIGIN_PROFILE = "Match origin pool"


def pool_properties_for_profile(profile: dict) -> dict[str, str]:
    """Return the profile's pool properties, restricted to the known schema."""
    if not profile:
        return {}
    result: dict[str, str] = {}
    for prop, value in profile.get("pool_properties", {}).items():
        if prop in POOL_PROPERTIES:
            result[prop] = str(value)
    return result


def filesystem_properties_for_profile(profile: dict) -> dict[str, str]:
    """Return the profile's root-filesystem properties (-O set).

    Restricted to dataset-scope live properties (the workload-profile
    vocabulary) so pool profiles cannot smuggle in creation-only or unknown
    dataset properties.
    """
    if not profile:
        return {}
    result: dict[str, str] = {}
    for prop, value in profile.get("filesystem_properties", {}).items():
        if prop in LIVE_PROPERTIES:
            result[prop] = str(value)
    return result


def pool_options_for_profile(profile: dict) -> list[tuple[str, str]]:
    """Return ``(prop, value)`` pairs for ``zpool create -o``, canonical order."""
    props = pool_properties_for_profile(profile)
    return [(prop, props[prop]) for prop in POOL_PROPERTIES if prop in props]


def filesystem_options_for_profile(profile: dict) -> list[tuple[str, str]]:
    """Return ``(prop, value)`` pairs for ``zpool create -O``, canonical order."""
    props = filesystem_properties_for_profile(profile)
    return [(prop, props[prop]) for prop in LIVE_PROPERTIES if prop in props]


def resolve_blocksize(blocksize: str, recommended_ashift: int | None) -> int | None:
    """Resolve a profile blocksize choice to an ashift value.

    ``recommended`` adopts *recommended_ashift* (None falls back to ZFS auto);
    ``auto`` and unknown values map to None (the ``-o ashift`` flag is
    omitted entirely).
    """
    if blocksize == BLOCKSIZE_RECOMMENDED:
        return recommended_ashift
    return ASHIFT_BY_LABEL.get(blocksize)


def blocksize_label_for_ashift(ashift: int | None) -> str:
    """Render an ashift as the GUI blocksize label (``4096 bytes`` style)."""
    if ashift is None:
        return BLOCKSIZE_AUTO
    return LABEL_BY_ASHIFT.get(ashift, f"{1 << ashift} bytes")


def blocksize_below_recommendation(chosen: int | None, recommended: int | None) -> bool:
    """True when a chosen ashift is known and smaller than the recommendation.

    A too-small blocksize permanently hurts modern drives, so the wizards
    warn when the user picks below the recommendation; a larger choice is
    harmless and never warns.
    """
    if chosen is None or recommended is None:
        return False
    return chosen < recommended


def validate_profile(profile: dict) -> list[str]:
    """Return a list of problems with a candidate pool profile (empty = valid)."""
    problems: list[str] = []
    blocksize = profile.get("blocksize", BLOCKSIZE_RECOMMENDED)
    if blocksize not in BLOCKSIZE_CHOICES:
        problems.append(f"unknown blocksize {blocksize!r}")
    for prop, value in profile.get("pool_properties", {}).items():
        if prop not in POOL_PROPERTIES:
            problems.append(f"unknown pool property {prop!r}")
            continue
        if str(value) not in POOL_PROPERTY_VALUES[prop]:
            problems.append(
                f"pool property {prop!r} must be one of "
                f"{'/'.join(POOL_PROPERTY_VALUES[prop])}, got {value!r}"
            )
    for prop in profile.get("filesystem_properties", {}):
        if prop not in LIVE_PROPERTIES:
            problems.append(f"unknown filesystem property {prop!r}")
    return problems


def origin_profile(
    origin_ashift: int | None,
    origin_pool_props: dict[str, str],
    origin_fs_props: dict[str, str],
) -> dict:
    """Build the "Match origin pool" pseudo-profile from source-pool values.

    *origin_pool_props* and *origin_fs_props* are the source pool's current
    values (already restricted by the caller or filtered here). The blocksize
    matches the origin's effective ashift — including None when the origin
    could not be probed, which leaves the choice to ZFS — and every curated
    property is written explicitly, so nothing silently reverts to defaults.
    """
    pool_props = {
        prop: str(origin_pool_props[prop]) for prop in POOL_PROPERTIES if prop in origin_pool_props
    }
    fs_props = {
        prop: str(origin_fs_props[prop]) for prop in LIVE_PROPERTIES if prop in origin_fs_props
    }
    blocksize = blocksize_label_for_ashift(origin_ashift)
    return {
        "description": (
            "Settings derived from the source pool: its blocksize, pool "
            "properties, and root-filesystem properties, carried to the new "
            "pool unchanged."
        ),
        "blocksize": blocksize,
        "pool_properties": pool_props,
        "filesystem_properties": fs_props,
        "notes": (
            "The migration equivalent of a photographed setting: the new "
            "pool starts exactly where the old one was, and you can still "
            "change anything — especially the blocksize, which is fixed "
            "once the pool is created."
        ),
    }


def infra_vdev_classes(topology) -> list[tuple[str, list[str]]]:
    """Return ``(class, leaf_paths)`` pairs for a pool's infra vdevs.

    *topology* is a ``TopologyNode`` tree (duck-typed: ``vdev_type`` and
    ``children``). Classes are ``special``, ``log``, ``cache``, and ``spare``;
    data vdevs are ignored. Leaf paths are the disk entries below each class.
    Used by Migrate Pool to warn that these vdevs are not recreated and must
    be re-added by hand after the cutover.
    """
    infra = ("special", "log", "cache", "spare")

    def _leaves(node) -> list[str]:
        if not getattr(node, "children", None):
            return [node.name]
        leaves: list[str] = []
        for child in node.children:
            leaves.extend(_leaves(child))
        return leaves

    found: list[tuple[str, list[str]]] = []
    for root_child in getattr(topology, "children", []) or []:
        vdev_type = getattr(root_child, "vdev_type", "")
        if vdev_type in infra:
            found.append((vdev_type, _leaves(root_child)))
    return found


# Pool properties captured from the source pool but never replayed on the
# migrated pool. ``feature@…`` rows are pool feature flags (not `zpool set`
# properties at all); the rest are create-only or transient (ashift is fixed
# at creation and already travels via the profile, altroot/cachefile are
# import-time bookkeeping, version is managed by `zpool upgrade`).
_NON_REPLAYABLE_POOL_PROPERTIES = frozenset(
    {
        "ashift",
        "altroot",
        "cachefile",
        "version",
    }
)


def replayable_pool_properties(
    props_with_source: dict[str, tuple[str, str]],
) -> dict[str, str]:
    """Filter ``zpool get all`` results down to the replayable properties.

    *props_with_source* maps property → ``(value, source)`` (the shape
    returned by ``ZfsRepository.pool_properties_with_source``). A property is
    replayable when its SOURCE is ``local`` (the pool owner set it away from
    the default), it is a real settable property (not ``feature@…``, not in
    the create-only/transient set), and it is outside the curated
    ``POOL_PROPERTIES`` set — the curated seven travel through the chosen
    pool profile's ``zpool create -o`` options, so replaying origin values
    for them would clobber a deliberately chosen saved profile. Used by
    Migrate Pool to decide which non-default properties (comment,
    compatibility, dedup_table_quota, …) to reapply with ``zpool set`` after
    the migrated pool is imported under the source pool's name.
    """
    replayable: dict[str, str] = {}
    for prop, (value, source) in props_with_source.items():
        if source != "local":
            continue
        if prop.startswith("feature@"):
            continue
        if prop in _NON_REPLAYABLE_POOL_PROPERTIES or prop in POOL_PROPERTIES:
            continue
        replayable[prop] = value
    return replayable


def data_vdev_leaves(topology) -> list[str]:
    """Return the leaf device paths of a pool's *data* vdevs only.

    Complements ``infra_vdev_classes``: walks the ``TopologyNode`` tree and
    collects disk leaves below root children that are not infrastructure
    classes (special/log/cache/spare), so bare-disk, mirror, and raidz data
    groups are included in tree order while infra-vdev disks are excluded.
    Migrate Pool's holding-mode picker uses this to preselect only true data
    members — a former infra-vdev disk must not silently join the rebuilt
    pool's data vdevs.
    """
    infra = ("special", "log", "cache", "spare")

    def _leaves(node) -> list[str]:
        if getattr(node, "vdev_type", "") == "disk" and node.name:
            return [node.name]
        leaves: list[str] = []
        for child in getattr(node, "children", None) or []:
            leaves.extend(_leaves(child))
        return leaves

    leaves: list[str] = []
    for root_child in getattr(topology, "children", []) or []:
        if getattr(root_child, "vdev_type", "") in infra:
            continue
        leaves.extend(_leaves(root_child))
    return leaves

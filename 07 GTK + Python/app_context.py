"""Application context — cross-cutting, non-GTK state for the GUI.

Pages receive an AppContext alongside the window (`app`) so they can access
config, script paths, version, and the ZFS repository without treating the
window object as a generic state bucket.
"""

from dataclasses import dataclass, field

from zfs_repository import ZfsRepository


@dataclass
class AppContext:
    """Shared operational state used by GUI pages and action handlers.

    Attributes:
        config: The loaded JSON configuration dict (mutated in place by savers).
        script_dir: Directory containing the Python GUI modules.
        parent_dir: Directory containing the bash scripts (repo root or bin).
        version: The deployed/repository version string.
        is_new_install: True when the config file was created fresh this session.
        zfs_repository: Repository for ZFS/zpool I/O.
    """

    config: dict
    script_dir: str
    parent_dir: str
    version: str
    is_new_install: bool = False
    zfs_repository: ZfsRepository = field(
        default_factory=lambda: ZfsRepository(sudo=True)
    )

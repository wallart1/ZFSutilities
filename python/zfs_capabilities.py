"""OpenZFS release-variation capability layer.

The GUI and future pool-modification code must not assume a fixed OpenZFS
release. This module parses the running userland and kernel-module versions
from `zfs version`, exposes a feature-minimum-version table, and lets callers
gate functionality on the kernel module version.
"""

import re
from dataclasses import dataclass

from backup_config import log_msg
from zfs_repository import ZfsRepository


@dataclass
class ZfsVersion:
    """Parsed OpenZFS userland and kernel-module versions."""

    userland: tuple[int, int]
    kmod: tuple[int, int]


# Feature minimum-version table.
# Anything at or below the 2.1 support floor is assumed present and is not
# listed here; read-only Disks views are the baseline.
FEATURE_MIN_VERSION: dict[str, tuple[int, int]] = {
    "draid": (2, 1),
    "json_output": (2, 3),
    "zfs_rewrite": (2, 3),
    "raidz_expansion": (2, 3),
    "fast_dedup": (2, 3),
    "direct_io": (2, 3),
    "ssb_on_zvols": (2, 4),
    "ssb_non_power_of_two": (2, 4),
}


# Regex: (?:zfs|zfs-kmod)[^\d]*(\d+)\.(\d+)
# Purpose: Extract the major.minor OpenZFS version from a `zfs version` line.
# The non-capturing prefix matches either the userland token (`zfs`) or the
# kernel-module token (`zfs-kmod`) so the same pattern works for both lines.
# `[^\d]*` skips any separator characters (hyphens, spaces, etc.) before the
# first digit. Groups 1 and 2 are the major and minor version numbers.
_VERSION_RE = re.compile(r"(?:zfs|zfs-kmod)[^\d]*(\d+)\.(\d+)")


def _parse_version_line(line: str) -> tuple[int, int] | None:
    """Return (major, minor) from a single `zfs version` line, or None."""
    match = _VERSION_RE.search(line)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


class ZfsCapabilities:
    """Runtime OpenZFS capability gating.

    The instance is constructed with an injectable `ZfsRepository` so tests can
    supply a fake `zfs version` response. All feature decisions are gated on
    the kernel-module version; a warning is emitted when userland and kmod
    differ.
    """

    def __init__(self, repository: ZfsRepository):
        self.repository = repository
        self.version = self._load_version()
        if (
            self.version.userland != self.version.kmod
            and self.version.userland != (0, 0)
            and self.version.kmod != (0, 0)
        ):
            log_msg(
                f"WARN: OpenZFS userland {self.version.userland[0]}."
                f"{self.version.userland[1]} differs from kernel module "
                f"{self.version.kmod[0]}.{self.version.kmod[1]}"
            )

    def _load_version(self) -> ZfsVersion:
        """Parse `zfs version` output into userland and kmod tuples."""
        raw = self.repository.version_output()
        if not raw:
            log_msg("WARN: Unable to determine OpenZFS version")
            return ZfsVersion((0, 0), (0, 0))

        userland: tuple[int, int] | None = None
        kmod: tuple[int, int] | None = None
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            parsed = _parse_version_line(stripped)
            if parsed is None:
                continue
            if "kmod" in stripped:
                kmod = parsed
            elif userland is None:
                # First non-kmod match is treated as the userland version.
                userland = parsed

        if userland is None:
            userland = (0, 0)
            log_msg("WARN: Unable to parse OpenZFS userland version")
        if kmod is None:
            # Fall back to userland when the kernel-module line is missing;
            # this is unusual but keeps the object usable.
            kmod = userland
            log_msg(
                "WARN: Unable to parse OpenZFS kernel-module version; "
                "using userland version for feature checks"
            )

        return ZfsVersion(userland, kmod)

    def supports(self, name: str) -> bool:
        """Return True if the running kernel module supports *name*."""
        if name not in FEATURE_MIN_VERSION:
            return False
        required = FEATURE_MIN_VERSION[name]
        return self.version.kmod >= required

    def requires(self, name: str) -> str:
        """Return tooltip text describing the OpenZFS version required.

        Returns an empty string for unknown features.
        """
        if name not in FEATURE_MIN_VERSION:
            return ""
        major, minor = FEATURE_MIN_VERSION[name]
        return f"requires OpenZFS {major}.{minor}+"

    def supports_pool_feature(self, pool: str, feature: str) -> bool:
        """Check whether *pool* has the named feature flag active/enabled.

        This is an optional cross-check for pool-scoped decisions; it consults
        `zpool get all <pool>` for the `feature@<name>` property.
        """
        raw = self.repository.pool_get_all(pool)
        marker = f"feature@{feature}"
        for line in raw.splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            if parts[1] == marker:
                value = parts[2].strip().lower()
                return value in ("active", "enabled")
        return False

"""Parser for legacy bash-style zfsretainpol-* retention policy files."""

import os
import re

# Regex: bktname[N]='<name>'; bktretain[N]=<count>; minage[N]=<days>
# Purpose: Parse legacy bash retention policy files into bucket dicts.
# Group 1: bucket name   e.g. "d", "w", "m"
# Group 2: retain count  e.g. 3
# Group 3: min age days  e.g. 0
# Examples:
#   "bktname[0]='d'; bktretain[0]=3; minage[0]=0"  -> match
#   "bktname[0]='d'"                                 -> no match (missing retain + minage)
_LEGACY_RETENTION_RE = re.compile(
    r"bktname\[\d+\]='(\w+)';\s*bktretain\[\d+\]=(\d+);\s*minage\[\d+\]=(\d+)"
)


def _parse_legacy_retention_file(path):
    """Parse a zfsretainpol-* bash file. Returns bucket list or [] on error."""
    buckets = []
    try:
        with open(path) as fh:
            for line in fh:
                m = _LEGACY_RETENTION_RE.search(line)
                if m:
                    buckets.append({
                        "name": m.group(1),
                        "retain": int(m.group(2)),
                        "minage": int(m.group(3)),
                    })
    except OSError:
        pass
    return buckets


def scan_legacy_retention(parent_dir, retention_dict):
    """Scan parent_dir for zfsretainpol-* files and add missing pools to retention_dict.

    Args:
        parent_dir: directory to scan for zfsretainpol-* files.
        retention_dict: dict mapping pool name -> bucket list (mutated in place).

    Returns:
        List of pool names that were newly imported.
    """
    imported = []
    try:
        for name in os.listdir(parent_dir):
            if not name.startswith("zfsretainpol-"):
                continue
            pool = name[len("zfsretainpol-"):]
            if pool in retention_dict:
                continue
            buckets = _parse_legacy_retention_file(os.path.join(parent_dir, name))
            if buckets:
                retention_dict[pool] = buckets
                imported.append(pool)
    except OSError:
        pass
    return imported

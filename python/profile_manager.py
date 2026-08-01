"""
Profile management — CRUD helpers for scheduled-task profiles.

Profiles are stored as individual JSON files in ~/.config/zfsutilities/profiles/.
"""

import json
import os
import re
from datetime import datetime

from backup_config import get_profiles_dir, log_msg

# Regex: ^[A-Za-z0-9_-]+$
# Purpose: Validate custom profile names for safe filesystem usage.
#          Allows only letters, digits, hyphens, and underscores.
# Example: "daily_backup" -> match
#          "daily backup" -> no match
_VALID_CUSTOM_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def validate_custom_name(name):
    """Raise ValueError if the custom name contains illegal characters."""
    if not name:
        raise ValueError("Profile name cannot be empty")
    if not _VALID_CUSTOM_NAME_RE.match(name):
        raise ValueError(
            "Profile name may only contain letters, digits, hyphens, and underscores"
        )


def build_profile_name(user, tab_type, custom_name):
    """Build a full profile name: <user>-<tab>-<custom_name>.

    Args:
        user: system username (e.g. 'root')
        tab_type: one of 'backup', 'offsite', 'restore', 'retention', 'scrub'
        custom_name: user-supplied suffix

    Returns:
        Full profile name string.
    """
    validate_custom_name(custom_name)
    return f"{user}-{tab_type}-{custom_name}"


def list_profiles():
    """Return a list of all profile dicts, sorted by profile_name."""
    profiles_dir = get_profiles_dir()
    profiles = []
    try:
        for fname in os.listdir(profiles_dir):
            if not fname.endswith(".json"):
                continue
            path = os.path.join(profiles_dir, fname)
            try:
                with open(path) as f:
                    profile = json.load(f)
                profiles.append(profile)
            except (json.JSONDecodeError, OSError) as e:
                log_msg(f"WARN: Could not read profile {fname}: {e}")
    except OSError:
        pass
    profiles.sort(key=lambda p: p.get("profile_name", ""))
    return profiles


def load_profile(name):
    """Load a single profile by name. Returns dict or None."""
    path = os.path.join(get_profiles_dir(), f"{name}.json")
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_profile(profile):
    """Write a profile dict to its JSON file atomically."""
    name = profile["profile_name"]
    path = os.path.join(get_profiles_dir(), f"{name}.json")
    tmp_path = path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(profile, f, indent=2)
    os.replace(tmp_path, path)


def delete_profile(name):
    """Remove a profile file. Returns True if file existed."""
    path = os.path.join(get_profiles_dir(), f"{name}.json")
    try:
        os.remove(path)
        log_msg(f"INFO: Deleted profile: {name}")
        return True
    except OSError:
        return False


def update_profile(tab_type, custom_name, config, dry_run=False):
    """Replace the snapshot config of an existing profile.

    The existing cron schedule and active flag are preserved so the user
    does not have to re-enable or re-schedule the profile after updating it
    from a tab page.

    Args:
        tab_type: 'backup', 'offsite', 'restore', 'retention', or 'scrub'
        custom_name: user-supplied suffix (validated)
        config: tab-specific config dict to snapshot
        dry_run: whether the profile should run in dry-run mode

    Returns:
        The updated profile dict.

    Raises:
        ValueError: if the profile does not exist.
    """
    user = get_user()
    profile_name = build_profile_name(user, tab_type, custom_name)
    profile = load_profile(profile_name)
    if profile is None:
        raise ValueError(f"Profile '{profile_name}' does not exist")

    profile["config"] = config
    profile["dry_run"] = bool(dry_run)
    profile["updated_at"] = datetime.now().isoformat()
    save_profile(profile)
    log_msg(f"INFO: Updated profile: {profile_name}")
    return profile


def profile_exists(name):
    """Return True if a profile with this name already exists."""
    path = os.path.join(get_profiles_dir(), f"{name}.json")
    return os.path.exists(path)


def get_user():
    """Return the current effective username."""
    return os.environ.get("SUDO_USER") or os.environ.get("USER") or "root"


def create_profile(tab_type, custom_name, config, dry_run=False):
    """Create a new profile from the current tab settings.

    Args:
        tab_type: 'backup', 'offsite', 'restore', or 'retention'
        custom_name: user-supplied suffix (validated)
        config: tab-specific config dict to snapshot
        dry_run: whether the profile should run in dry-run mode

    Returns:
        The newly created profile dict.
    """
    user = get_user()
    profile_name = build_profile_name(user, tab_type, custom_name)
    if profile_exists(profile_name):
        raise ValueError(f"Profile '{profile_name}' already exists")

    profile = {
        "profile_name": profile_name,
        "tab_type": tab_type,
        "created_at": datetime.now().isoformat(),
        "config": config,
        "dry_run": bool(dry_run),
        "cron": {
            "minute": "0",
            "hour": "2",
            "day": "*",
            "month": "*",
            "weekday": "*",
        },
        "active": False,
    }
    save_profile(profile)
    log_msg(f"INFO: Created profile: {profile_name}")
    return profile

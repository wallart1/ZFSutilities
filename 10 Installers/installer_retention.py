#!/usr/bin/env python3
"""Initialize the shared JSON config retention policy for installers.

On a new install this ensures only the `default` retention profile exists.
On an existing install it leaves user-created per-pool profiles untouched and
only adds a missing `default` profile.
"""

import argparse
import os
import sys

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))
PYTHON_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

import config_core
from config_core import load_config, save_config
from feature_config import get_all_retention
from logging_config import log_msg


def ensure_default_retention_profile(config_path=None, new_install=False):
    """Load or create the JSON config and enforce the default retention rule.

    Args:
        config_path: Override path to zfsutilities.json. Defaults to
            config_core.CONFIG_PATH.
        new_install: If True, remove all pool-specific retention policies so
            only the `default` policy remains.

    Returns:
        True if the config was modified, False otherwise.
    """
    path = config_path or config_core.CONFIG_PATH

    old_path = config_core.CONFIG_PATH
    config_core.CONFIG_PATH = path
    try:
        config = load_config()

        had_retention = "retention" in config
        had_default = had_retention and "default" in config["retention"]

        retention = get_all_retention(config)
        changed = False

        if new_install:
            cleared = [pool for pool in list(retention.keys()) if pool != "default"]
            for pool in cleared:
                del retention[pool]
                changed = True
            if cleared:
                config["retention"] = retention
                log_msg(
                    "INFO: New install — cleared pool-specific retention policies: "
                    f"{', '.join(cleared)}"
                )

        if not had_retention or not had_default:
            changed = True
            log_msg("INFO: Added default retention policy")

        if changed:
            save_config(config)
        else:
            log_msg("INFO: Retention profiles already initialized")

        return changed
    except OSError as exc:
        log_msg(f"WARN: Could not initialize retention profiles: {exc}")
        raise
    finally:
        config_core.CONFIG_PATH = old_path


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Initialize the default retention profile for ZFSutilities."
    )
    parser.add_argument(
        "--config-path",
        help="Path to zfsutilities.json (default: /root/.config/zfsutilities.json)",
    )
    parser.add_argument(
        "--new-install",
        action="store_true",
        help="Remove pool-specific policies, leaving only the default policy",
    )
    args = parser.parse_args(argv)

    try:
        ensure_default_retention_profile(
            config_path=args.config_path, new_install=args.new_install
        )
    except OSError:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

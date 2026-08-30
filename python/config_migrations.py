"""Config schema migrations. Bump CONFIG_VERSION when JSON structure changes."""

CONFIG_VERSION = 24


def _migrate_1_to_2(config):
    if "archive_path" not in config:
        config["archive_path"] = ""
    config["config_version"] = 2
    return config


def _migrate_2_to_3(config):
    config.pop("project_dir", None)
    config.pop("home_dir", None)
    config["config_version"] = 3
    return config


def _migrate_3_to_4(config):
    if "pre_backup_script_enabled" not in config:
        config["pre_backup_script_enabled"] = False
    if "pre_backup_script" not in config:
        config["pre_backup_script"] = ""
    if "run_installed_programs" not in config:
        config["run_installed_programs"] = True
    config["config_version"] = 4
    return config


def _migrate_4_to_5(config):
    if "log_retention_days" not in config:
        config["log_retention_days"] = 30
    config["config_version"] = 5
    return config


def _migrate_5_to_6(config):
    if "post_backup_script_enabled" not in config:
        config["post_backup_script_enabled"] = False
    if "post_backup_script" not in config:
        config["post_backup_script"] = ""
    config["config_version"] = 6
    return config


def _migrate_6_to_7(config):
    for section in ("backup", "offsite"):
        if (
            section in config
            and "variables" in config[section]
            and "verify_after_transfer" not in config[section]["variables"]
        ):
            config[section]["variables"]["verify_after_transfer"] = "Y"
    config["config_version"] = 7
    return config


def _migrate_7_to_8(config):
    if "history_retention_days" not in config:
        config["history_retention_days"] = 90
    config["config_version"] = 8
    return config


def _migrate_8_to_9(config):
    if "dashboard" not in config:
        config["dashboard"] = {"low_space_threshold": 80}
    config["config_version"] = 9
    return config


def _migrate_9_to_10(config):
    if "scrub_manager" not in config:
        config["scrub_manager"] = {
            "simultaneous": 1,
            "refresh_seconds": 10,
            "system_scrub_weekly": False,
            "system_scrub_monthly": False,
        }
    config["config_version"] = 10
    return config


def _migrate_10_to_11(config):
    backup = config.get("backup", {})
    backup.pop("run_installed_programs", None)
    config["backup"] = backup
    config["config_version"] = 11
    return config


def _migrate_11_to_12(config):
    backup = config.get("backup", {})
    if "pull_steps_active" not in backup:
        backup["pull_steps_active"] = True
    config["backup"] = backup
    config["config_version"] = 12
    return config


def _migrate_12_to_13(config):
    if "prune_label" not in config:
        config["prune_label"] = "dailybackup"
    config["config_version"] = 13
    return config


def _migrate_13_to_14(config):
    pools = config.get("pools")
    if isinstance(pools, list):
        migrated = []
        for pool in pools:
            if isinstance(pool, dict):
                migrated.append(pool)
            else:
                migrated.append({"name": str(pool), "offsite_candidate": False})
        config["pools"] = migrated
    config["config_version"] = 14
    return config


def _migrate_14_to_15(config):
    entries = config.get("checkagainst")
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict) and "comment" not in entry:
                entry["comment"] = ""
    config["config_version"] = 15
    return config


def _migrate_15_to_16(config):
    if "prune_pools_order" not in config:
        config["prune_pools_order"] = []
    config["config_version"] = 16
    return config


def _migrate_16_to_17(config):
    for section in ("backup", "offsite", "restore"):
        if section not in config:
            config[section] = {}
        if "pause_scrubs" not in config[section]:
            config[section]["pause_scrubs"] = False
    config["config_version"] = 17
    return config


def _migrate_17_to_18(config):
    existing = config.get("checkagainst")
    if isinstance(existing, dict):
        nested = existing
    else:
        nested = {}

    defaults = {
        "backup_derived_active": True,
        "offsite_derived_active": True,
        "backup_derived": [],
        "offsite_derived": [],
        "user_entries": [],
    }
    for key, value in defaults.items():
        if key not in nested:
            nested[key] = value

    if isinstance(existing, list):
        for entry in existing:
            if isinstance(entry, dict):
                nested["user_entries"].append(entry)

    config["checkagainst"] = nested
    config["config_version"] = 18
    return config


def _migrate_18_to_19(config):
    """Convert checkagainst rows from strip/prepend to source_root/dest_root."""
    data = config.get("checkagainst")
    if not isinstance(data, dict):
        data = {}
        config["checkagainst"] = data

    sections = ("backup_derived", "offsite_derived", "user_entries")
    for section in sections:
        migrated = []
        for row in data.get(section, []):
            if not isinstance(row, dict):
                continue
            if "source_root" in row and "dest_root" in row:
                migrated.append(row)
                continue
            source_root = str(row.get("dataset", "")).strip()
            quals = int(row.get("quals", "0") or "0")
            counterpart = str(row.get("counterpart", "-") or "-").strip()
            if counterpart == "-":
                counterpart = ""

            parts = [p for p in source_root.split("/") if p]
            stripped = "/".join(parts[quals:]) if quals < len(parts) else ""

            if counterpart and stripped:
                dest_root = f"{counterpart}/{stripped}"
            elif counterpart:
                dest_root = counterpart
            else:
                dest_root = stripped

            new_row = dict(row)
            new_row.pop("dataset", None)
            new_row.pop("quals", None)
            new_row.pop("counterpart", None)
            new_row["source_root"] = source_root
            new_row["dest_root"] = dest_root
            migrated.append(new_row)
        data[section] = migrated

    config["config_version"] = 19
    return config


def _migrate_19_to_20(config):
    """Drop stale offsite_pools now that candidates are resolved at runtime."""
    offsite = config.get("offsite")
    if isinstance(offsite, dict):
        offsite.pop("offsite_pools", None)
    config["config_version"] = 20
    return config


def _migrate_20_to_21(config):
    """Seed the retention VERB message toggle (default off)."""
    if "retention_verb_messages" not in config:
        config["retention_verb_messages"] = False
    config["config_version"] = 21
    return config


def _migrate_21_to_22(config):
    """Add dashboard refresh interval (seconds)."""
    dashboard = config.get("dashboard")
    if not isinstance(dashboard, dict):
        dashboard = {}
        config["dashboard"] = dashboard
    if "refresh_seconds" not in dashboard:
        dashboard["refresh_seconds"] = 30
    config["config_version"] = 22
    return config


def _migrate_22_to_23(config):
    """Add per-rsync-step excludes list to backup pull_steps."""
    backup = config.get("backup")
    if isinstance(backup, dict):
        if "pull_steps" not in backup:
            backup["pull_steps"] = []
        pull_steps = backup.get("pull_steps")
        if isinstance(pull_steps, list):
            migrated = []
            for step in pull_steps:
                if isinstance(step, dict):
                    step = dict(step)
                    if "excludes" not in step:
                        step["excludes"] = []
                migrated.append(step)
            backup["pull_steps"] = migrated
    config["config_version"] = 23
    return config


def _migrate_23_to_24(config):
    """Regenerate checkagainst derived rows from current Backup/Offsite steps.

    Fixes stale rows where a destination of just <offsite> was treated as a
    full suffix match, producing incorrect counterpart paths like
    fivebays/fivebays.
    """
    from feature_config import refresh_checkagainst_derived

    refresh_checkagainst_derived(config)
    config["config_version"] = 24
    return config


MIGRATIONS = [
    _migrate_1_to_2,
    _migrate_2_to_3,
    _migrate_3_to_4,
    _migrate_4_to_5,
    _migrate_5_to_6,
    _migrate_6_to_7,
    _migrate_7_to_8,
    _migrate_8_to_9,
    _migrate_9_to_10,
    _migrate_10_to_11,
    _migrate_11_to_12,
    _migrate_12_to_13,
    _migrate_13_to_14,
    _migrate_14_to_15,
    _migrate_15_to_16,
    _migrate_16_to_17,
    _migrate_17_to_18,
    _migrate_18_to_19,
    _migrate_19_to_20,
    _migrate_20_to_21,
    _migrate_21_to_22,
    _migrate_22_to_23,
    _migrate_23_to_24,
]


def run_migrations(config, save_func=None):
    """Apply all pending migrations to bring config up to CONFIG_VERSION."""
    current = config.get("config_version", 0)
    target = CONFIG_VERSION
    while current < target:
        idx = current - 1
        if idx < 0 or idx >= len(MIGRATIONS):
            raise RuntimeError(f"No migration defined from version {current} to {current + 1}")
        config = MIGRATIONS[idx](config)
        current = config.get("config_version", 0)
        if save_func:
            try:
                save_func(config)
            except OSError:
                pass
    return config

"""Config schema migrations. Bump CONFIG_VERSION when JSON structure changes."""

CONFIG_VERSION = 17


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
        if section in config and "variables" in config[section]:
            if "verify_after_transfer" not in config[section]["variables"]:
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
]


def run_migrations(config, save_func=None):
    """Apply all pending migrations to bring config up to CONFIG_VERSION."""
    current = config.get("config_version", 0)
    target = CONFIG_VERSION
    while current < target:
        idx = current - 1
        if idx < 0 or idx >= len(MIGRATIONS):
            raise RuntimeError(
                f"No migration defined from version {current} to {current + 1}"
            )
        config = MIGRATIONS[idx](config)
        current = config.get("config_version", 0)
        if save_func:
            try:
                save_func(config)
            except OSError:
                pass
    return config

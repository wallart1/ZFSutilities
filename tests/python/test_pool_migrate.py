"""Tests for pool_migrate.py — pure-logic pool-migration helpers.

Also covers the migration argv builders added to zfs_repository.py
(build_recursive_snapshot_command, build_migration_send_receive_command,
build_pool_export_command, build_pool_import_rename_command).
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

import golden
from pool_migrate import (
    MIGRATE_HOLDING_POOL,
    MIGRATE_NEW_DISKS,
    MIGRATION_MODES,
    STEP_COPY,
    STEP_CREATE_POOL,
    STEP_DESTROY_HOLDING,
    STEP_DESTROY_SOURCE,
    STEP_EXPORT_SOURCE,
    STEP_IMPORT_RENAME,
    STEP_SNAPSHOT,
    STEP_VERIFY,
    MigrationStep,
    check_destination_capacity,
    generate_temp_pool_name,
    migration_snapshot_bare_name,
    migration_snapshot_name,
    plan_migration_steps,
    verify_trees_match,
)
from test_support import normalize_repo_root
from zfs_repository import (
    build_migration_send_receive_command,
    build_pool_export_command,
    build_pool_import_rename_command,
    build_recursive_snapshot_command,
)

GB = 1024**3


class TestMigrationSnapshotName(unittest.TestCase):
    def test_format_follows_convention_without_bucket(self):
        when = datetime(2026, 9, 10, 14, 30, tzinfo=timezone(timedelta(hours=-4)))
        name = migration_snapshot_name(when)
        self.assertEqual(name, "@migrate-2026-09-10T14:30-04:00")

    def test_default_is_now(self):
        name = migration_snapshot_name()
        self.assertTrue(name.startswith("@migrate-"), name)
        self.assertFalse(name.rsplit("-", 1)[-1] in ("d", "w", "m", "s", "c"))

    def test_bare_name_strips_at(self):
        self.assertEqual(
            migration_snapshot_bare_name("@migrate-2026-09-10T14:30-04:00"),
            "migrate-2026-09-10T14:30-04:00",
        )

    def test_bare_name_rejects_non_snapshot(self):
        with self.assertRaises(ValueError):
            migration_snapshot_bare_name("pool/ds@migrate-x")


class TestGenerateTempPoolName(unittest.TestCase):
    def test_default_suffix(self):
        self.assertEqual(generate_temp_pool_name("temp", set()), "temp_mig")

    def test_collision_appends_index(self):
        existing = {"temp_mig", "temp_mig2"}
        self.assertEqual(generate_temp_pool_name("temp", existing), "temp_mig3")

    def test_existing_names_not_mutated(self):
        existing = {"temp_mig"}
        before = set(existing)
        generate_temp_pool_name("temp", existing)
        self.assertEqual(existing, before)

    def test_long_source_truncated_to_fit(self):
        source = "a" * 40
        name = generate_temp_pool_name(source, set())
        self.assertLessEqual(len(name), 32)
        self.assertTrue(name.endswith("_mig"))
        self.assertTrue(name.startswith("a"))

    def test_collision_with_max_length_source(self):
        # 32-char source truncates to "a"*28 + suffix (32-char cap).
        source = "a" * 32
        existing = {"a" * 28 + "_mig"}
        name = generate_temp_pool_name(source, existing)
        self.assertTrue(name.endswith("_mig2"))

    def test_empty_source_rejected(self):
        with self.assertRaises(ValueError):
            generate_temp_pool_name("", set())


class TestPlanMigrationSteps(unittest.TestCase):
    def test_new_disks_plan_order(self):
        datasets = ["vm-100-disk-0", "proxmox", "iso"]
        steps = plan_migration_steps("temp", datasets, MIGRATE_NEW_DISKS, "temp_mig")
        self.assertEqual(
            [step.kind for step in steps],
            [
                STEP_SNAPSHOT,
                STEP_COPY,
                STEP_COPY,
                STEP_COPY,
                STEP_VERIFY,
                STEP_EXPORT_SOURCE,
                STEP_IMPORT_RENAME,
            ],
        )
        self.assertEqual(
            [step.dataset for step in steps if step.kind == STEP_COPY],
            datasets,
        )
        for step in steps:
            self.assertTrue(step.description)

    def test_holding_pool_plan_extra_steps(self):
        steps = plan_migration_steps(
            "temp", ["proxmox"], MIGRATE_HOLDING_POOL, "fivebays"
        )
        self.assertEqual(
            [step.kind for step in steps],
            [
                STEP_SNAPSHOT,
                STEP_COPY,
                STEP_VERIFY,
                STEP_EXPORT_SOURCE,
                STEP_DESTROY_SOURCE,
                STEP_CREATE_POOL,
                STEP_COPY,
                STEP_VERIFY,
                STEP_EXPORT_SOURCE,
                STEP_IMPORT_RENAME,
                STEP_DESTROY_HOLDING,
            ],
        )

    def test_mode_constants_distinct(self):
        self.assertEqual(
            set(MIGRATION_MODES), {MIGRATE_NEW_DISKS, MIGRATE_HOLDING_POOL}
        )
        self.assertNotEqual(MIGRATE_NEW_DISKS, MIGRATE_HOLDING_POOL)

    def test_empty_source_rejected(self):
        with self.assertRaises(ValueError):
            plan_migration_steps("", ["proxmox"], MIGRATE_NEW_DISKS, "temp_mig")

    def test_empty_datasets_rejected(self):
        with self.assertRaises(ValueError):
            plan_migration_steps("temp", [], MIGRATE_NEW_DISKS, "temp_mig")

    def test_unknown_mode_rejected(self):
        with self.assertRaises(ValueError):
            plan_migration_steps("temp", ["proxmox"], "sideways", "temp_mig")

    def test_empty_dest_rejected(self):
        with self.assertRaises(ValueError):
            plan_migration_steps("temp", ["proxmox"], MIGRATE_NEW_DISKS, "")

    def test_step_dataclass_defaults(self):
        step = MigrationStep(STEP_VERIFY, "verify things")
        self.assertEqual(step.dataset, "")


class TestCheckDestinationCapacity(unittest.TestCase):
    def test_sufficient_space(self):
        problems, warnings = check_destination_capacity(100 * GB, 200 * GB)
        self.assertEqual(problems, [])
        self.assertEqual(warnings, [])

    def test_insufficient_space_is_a_problem(self):
        problems, warnings = check_destination_capacity(200 * GB, 100 * GB)
        self.assertEqual(warnings, [])
        self.assertEqual(len(problems), 1)
        self.assertIn("insufficient", problems[0])
        self.assertIn("100.00 GiB", problems[0])
        self.assertIn("200.00 GiB", problems[0])

    def test_exact_fit_warns_on_headroom(self):
        problems, warnings = check_destination_capacity(100 * GB, 100 * GB)
        self.assertEqual(problems, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("10% headroom", warnings[0])

    def test_negative_sizes_rejected(self):
        with self.assertRaises(ValueError):
            check_destination_capacity(-1, 100 * GB)
        with self.assertRaises(ValueError):
            check_destination_capacity(100 * GB, -1)


class TestVerifyTreesMatch(unittest.TestCase):
    def test_matching_trees(self):
        source = {"ds": 10 * GB, "ds/child": 5 * GB}
        self.assertEqual(verify_trees_match(source, dict(source)), [])

    def test_small_difference_within_tolerance(self):
        source = {"ds": 10 * GB}
        self.assertEqual(verify_trees_match(source, {"ds": int(10 * GB * 1.005)}), [])

    def test_missing_dataset_reported(self):
        mismatches = verify_trees_match({"ds": 1, "ds/child": 1}, {"ds": 1})
        self.assertEqual(mismatches, ["missing on destination: ds/child"])

    def test_extra_dataset_reported(self):
        mismatches = verify_trees_match({"ds": 1}, {"ds": 1, "stray": 1})
        self.assertEqual(mismatches, ["extra on destination: stray"])

    def test_used_difference_reported(self):
        mismatches = verify_trees_match({"ds": 100 * GB}, {"ds": 90 * GB})
        self.assertEqual(len(mismatches), 1)
        self.assertIn("used bytes differ for ds", mismatches[0])


class TestBuildRecursiveSnapshotCommand(unittest.TestCase):
    def test_pool_root(self):
        golden.check(self, build_recursive_snapshot_command("temp", "migrate-x"))

    def test_dataset(self):
        golden.check(self, build_recursive_snapshot_command("temp/proxmox", "migrate-x"))

    def test_empty_target_rejected(self):
        with self.assertRaises(ValueError):
            build_recursive_snapshot_command("", "migrate-x")

    def test_bad_snap_name_rejected(self):
        for bad in ("", "@migrate-x", "a/b"):
            with self.assertRaises(ValueError):
                build_recursive_snapshot_command("temp", bad)


class TestBuildMigrationSendReceiveCommand(unittest.TestCase):
    def _normalized(self, argv):
        # The sourced script path is resolved from this checkout's absolute
        # location; normalize it (and its quoting) so the golden stays
        # machine-independent.
        return [argv[0], argv[1], normalize_repo_root(argv[2])]

    def test_basic_argv(self):
        argv = build_migration_send_receive_command(
            "temp/proxmox", "temp_mig/proxmox", "migrate-x"
        )
        golden.check(self, self._normalized(argv))

    def test_rate_limit_assignment_emitted(self):
        argv = build_migration_send_receive_command(
            "temp/proxmox", "temp_mig/proxmox", "migrate-x", rate_limit="100m"
        )
        golden.check(self, self._normalized(argv), name="TestBuildMigrationSendReceiveCommand.rate_limit")

    def test_rate_limit_assignment_omitted(self):
        argv = build_migration_send_receive_command(
            "temp/proxmox", "temp_mig/proxmox", "migrate-x"
        )
        golden.check(self, self._normalized(argv), name="TestBuildMigrationSendReceiveCommand.no_rate_limit")
        self.assertNotIn("pv_rate_limit", argv[2])

    def test_invalid_rate_limit_rejected(self):
        for bad in ("abc", "10x", "1.5m", "-5m"):
            with self.assertRaises(ValueError):
                build_migration_send_receive_command(
                    "temp/proxmox", "temp_mig/proxmox", "migrate-x", rate_limit=bad
                )

    def test_names_with_spaces_are_quoted(self):
        argv = build_migration_send_receive_command(
            "my pool/ds", "dest pool/ds", "migrate-x"
        )
        golden.check(self, self._normalized(argv))

    def test_empty_source_rejected(self):
        with self.assertRaises(ValueError):
            build_migration_send_receive_command("", "dest", "migrate-x")

    def test_empty_dest_rejected(self):
        with self.assertRaises(ValueError):
            build_migration_send_receive_command("src", "", "migrate-x")

    def test_bad_snap_name_rejected(self):
        with self.assertRaises(ValueError):
            build_migration_send_receive_command("src", "dest", "a@b")


class TestBuildPoolExportCommand(unittest.TestCase):
    def test_basic_argv(self):
        golden.check(self, build_pool_export_command("temp"))

    def test_empty_name_rejected(self):
        with self.assertRaises(ValueError):
            build_pool_export_command("")


class TestBuildPoolImportRenameCommand(unittest.TestCase):
    def test_basic_argv(self):
        golden.check(self, build_pool_import_rename_command("temp_mig", "temp"))

    def test_empty_names_rejected(self):
        with self.assertRaises(ValueError):
            build_pool_import_rename_command("", "temp")
        with self.assertRaises(ValueError):
            build_pool_import_rename_command("temp_mig", "")

    def test_same_name_rejected(self):
        with self.assertRaises(ValueError):
            build_pool_import_rename_command("temp", "temp")


if __name__ == "__main__":
    unittest.main()

"""Tests for pool_migrate.py — pure-logic pool-migration helpers.

Also covers the migration argv builders added to zfs_repository.py
(build_recursive_snapshot_command, build_migration_send_receive_command,
build_pool_export_command, build_pool_import_rename_command, and the
holds capture/release/apply builders).
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
    STEP_CAPTURE_HOLDS,
    STEP_CATCHUP_COPY,
    STEP_COPY,
    STEP_CREATE_POOL,
    STEP_CUTOVER_SNAPSHOT,
    STEP_DESTROY_HOLDING,
    STEP_DESTROY_SOURCE,
    STEP_EXPORT_SOURCE,
    STEP_IMPORT_RENAME,
    STEP_REAPPLY_HOLDS,
    STEP_REAPPLY_POOL_PROPS,
    STEP_RELEASE_HOLDS,
    STEP_SNAPSHOT,
    STEP_VERIFY,
    MigrationStep,
    check_destination_capacity,
    cutover_snapshot_name,
    generate_temp_pool_name,
    holding_migration_namespace,
    migration_snapshot_bare_name,
    migration_snapshot_name,
    plan_migration_steps,
    verify_trees_match,
    vmids_from_zvols,
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
        # The caller's instant is preserved and rendered canonical UTC+Z.
        when = datetime(2026, 9, 10, 14, 30, tzinfo=timezone(timedelta(hours=-4)))
        name = migration_snapshot_name(when)
        self.assertEqual(name, "@migrate-2026-09-10T18:30Z")

    def test_default_is_now(self):
        name = migration_snapshot_name()
        self.assertTrue(name.startswith("@migrate-"), name)
        self.assertFalse(name.rsplit("-", 1)[-1] in ("d", "w", "m", "s", "c"))
        # "+" is illegal in ZFS names — the canonical Z form must never
        # regress to an embedded UTC offset.
        self.assertNotIn("+", name)

    def test_bare_name_accepts_legacy_offset_form(self):
        self.assertEqual(
            migration_snapshot_bare_name("@migrate-2026-09-10T14:30-04:00"),
            "migrate-2026-09-10T14:30-04:00",
        )

    def test_bare_name_rejects_non_snapshot(self):
        with self.assertRaises(ValueError):
            migration_snapshot_bare_name("pool/ds@migrate-x")


class TestCutoverSnapshotName(unittest.TestCase):
    def test_appends_cutover_suffix(self):
        self.assertEqual(
            cutover_snapshot_name("@migrate-2026-09-10T14:30-04:00"),
            "@migrate-2026-09-10T14:30-04:00-cutover",
        )

    def test_keeps_migrate_label(self):
        # Retention prunes only its own label's buckets, so a cutover
        # snapshot must stay migrate-labelled to be pruning-proof.
        self.assertTrue(
            cutover_snapshot_name("@migrate-2026-09-10T14:30-04:00").startswith("@migrate-")
        )

    def test_rejects_non_migration_snapshot(self):
        for bad in ("", "migrate-x", "pool/ds@migrate-x", "@dailybackup-2026-09-10d", "@snap"):
            with self.assertRaises(ValueError):
                cutover_snapshot_name(bad)

    def test_rejects_dataset_qualified_name(self):
        with self.assertRaises(ValueError):
            cutover_snapshot_name("@migrate-x/sub")

    def test_rejects_already_cutover_name(self):
        with self.assertRaises(ValueError):
            cutover_snapshot_name("@migrate-2026-09-10T14:30-04:00-cutover")


class TestVmidsFromZvols(unittest.TestCase):
    def test_groups_zvols_by_vmid(self):
        names = ["tank/vm-100-disk-0", "tank/vm-207-disk-0", "tank/vm-100-disk-1"]
        self.assertEqual(
            vmids_from_zvols(names),
            {
                "100": ["tank/vm-100-disk-0", "tank/vm-100-disk-1"],
                "207": ["tank/vm-207-disk-0"],
            },
        )

    def test_ignores_non_proxmox_names(self):
        names = [
            "tank/data",
            "tank/vm-100-disk-0",
            "tank/subvol-100-disk-0",
            "tank/vm-abc-disk-0",
        ]
        self.assertEqual(vmids_from_zvols(names), {"100": ["tank/vm-100-disk-0"]})

    def test_requires_full_base_name_match(self):
        self.assertEqual(vmids_from_zvols(["tank/xvm-100-disk-0", "tank/vm-100-disk-0-extra"]), {})

    def test_empty_input(self):
        self.assertEqual(vmids_from_zvols([]), {})


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


class TestHoldingMigrationNamespace(unittest.TestCase):
    def test_namespace_is_source_pool_prefixed(self):
        self.assertEqual(holding_migration_namespace("zfstest2"), "migrate_zfstest2")

    def test_empty_source_rejected(self):
        with self.assertRaises(ValueError):
            holding_migration_namespace("")

    def test_holding_plan_mentions_namespace(self):
        steps = plan_migration_steps("temp", ["proxmox"], MIGRATE_HOLDING_POOL, "fivebays")
        copies = [step.description for step in steps if step.kind == STEP_COPY]
        self.assertIn("fivebays/migrate_temp", copies[0])
        self.assertIn("holding-pool namespace", copies[1])
        destroy = [step.description for step in steps if step.kind == STEP_DESTROY_HOLDING]
        self.assertIn("migration namespace", destroy[0])

    def test_new_disks_plan_mentions_plain_dest(self):
        steps = plan_migration_steps("temp", ["proxmox"], MIGRATE_NEW_DISKS, "temp_mig")
        copies = [step.description for step in steps if step.kind == STEP_COPY]
        self.assertIn("temp_mig", copies[0])
        self.assertNotIn("migrate_temp", copies[0])


class TestPlanMigrationSteps(unittest.TestCase):
    def test_new_disks_plan_order(self):
        datasets = ["vm-100-disk-0", "proxmox", "iso"]
        steps = plan_migration_steps("temp", datasets, MIGRATE_NEW_DISKS, "temp_mig")
        self.assertEqual(
            [step.kind for step in steps],
            [
                STEP_SNAPSHOT,
                STEP_CREATE_POOL,
                STEP_COPY,
                STEP_COPY,
                STEP_COPY,
                STEP_VERIFY,
                STEP_CAPTURE_HOLDS,
                STEP_CUTOVER_SNAPSHOT,
                STEP_CATCHUP_COPY,
                STEP_CATCHUP_COPY,
                STEP_CATCHUP_COPY,
                STEP_EXPORT_SOURCE,
                STEP_IMPORT_RENAME,
                STEP_REAPPLY_HOLDS,
            ],
        )
        self.assertEqual(
            [step.dataset for step in steps if step.kind == STEP_COPY],
            datasets,
        )
        self.assertEqual(
            [step.dataset for step in steps if step.kind == STEP_CATCHUP_COPY],
            datasets,
        )
        for step in steps:
            self.assertTrue(step.description)

    def test_holding_create_step_mentions_disk_count(self):
        steps = plan_migration_steps(
            "temp",
            ["proxmox"],
            MIGRATE_HOLDING_POOL,
            "fivebays",
            rebuild_disk_count=3,
        )
        create = [step for step in steps if step.kind == STEP_CREATE_POOL]
        self.assertEqual(len(create), 1)
        self.assertIn("3 selected disks", create[0].description)
        self.assertNotIn("freed disks", create[0].description)

    def test_rebuild_disk_count_must_be_positive(self):
        with self.assertRaises(ValueError):
            plan_migration_steps(
                "temp",
                ["proxmox"],
                MIGRATE_HOLDING_POOL,
                "fivebays",
                rebuild_disk_count=0,
            )

    def test_holding_pool_plan_extra_steps(self):
        steps = plan_migration_steps("temp", ["proxmox"], MIGRATE_HOLDING_POOL, "fivebays")
        self.assertEqual(
            [step.kind for step in steps],
            [
                STEP_SNAPSHOT,
                STEP_COPY,
                STEP_VERIFY,
                STEP_CAPTURE_HOLDS,
                STEP_CUTOVER_SNAPSHOT,
                STEP_CATCHUP_COPY,
                STEP_EXPORT_SOURCE,
                STEP_RELEASE_HOLDS,
                STEP_DESTROY_SOURCE,
                STEP_CREATE_POOL,
                STEP_COPY,
                STEP_VERIFY,
                STEP_EXPORT_SOURCE,
                STEP_IMPORT_RENAME,
                STEP_REAPPLY_HOLDS,
                STEP_DESTROY_HOLDING,
            ],
        )

    def test_catchup_steps_between_holds_capture_and_export(self):
        for mode, dest in ((MIGRATE_NEW_DISKS, "temp_mig"), (MIGRATE_HOLDING_POOL, "fivebays")):
            steps = plan_migration_steps("temp", ["proxmox"], mode, dest)
            kinds = [step.kind for step in steps]
            self.assertLess(kinds.index(STEP_CAPTURE_HOLDS), kinds.index(STEP_CUTOVER_SNAPSHOT))
            self.assertLess(kinds.index(STEP_CUTOVER_SNAPSHOT), kinds.index(STEP_CATCHUP_COPY))
            self.assertLess(kinds.index(STEP_CATCHUP_COPY), kinds.index(STEP_EXPORT_SOURCE))

    def test_catchup_descriptions_mention_snapshots_and_dest(self):
        steps = plan_migration_steps(
            "temp",
            ["proxmox"],
            MIGRATE_NEW_DISKS,
            "temp_mig",
            migration_snap="@migrate-x",
            cutover_snap="@migrate-x-cutover",
        )
        snapshot = next(step for step in steps if step.kind == STEP_CUTOVER_SNAPSHOT)
        self.assertIn("Take cutover snapshot on 'temp'", snapshot.description)
        catchup = next(step for step in steps if step.kind == STEP_CATCHUP_COPY)
        self.assertIn("'@migrate-x' → '@migrate-x-cutover'", catchup.description)
        self.assertIn("'proxmox'", catchup.description)
        self.assertIn("'temp_mig'", catchup.description)

    def test_holding_catchup_targets_reserved_namespace(self):
        steps = plan_migration_steps(
            "temp",
            ["proxmox"],
            MIGRATE_HOLDING_POOL,
            "fivebays",
            migration_snap="@migrate-x",
            cutover_snap="@migrate-x-cutover",
        )
        catchup = next(step for step in steps if step.kind == STEP_CATCHUP_COPY)
        self.assertIn("'fivebays/migrate_temp'", catchup.description)

    def test_mode_constants_distinct(self):
        self.assertEqual(set(MIGRATION_MODES), {MIGRATE_NEW_DISKS, MIGRATE_HOLDING_POOL})
        self.assertNotEqual(MIGRATE_NEW_DISKS, MIGRATE_HOLDING_POOL)

    def test_replay_props_step_between_import_and_holds(self):
        for mode, dest in ((MIGRATE_NEW_DISKS, "temp_mig"), (MIGRATE_HOLDING_POOL, "fivebays")):
            steps = plan_migration_steps(
                "temp", ["proxmox"], mode, dest, replay_props=("comment", "compatibility")
            )
            kinds = [step.kind for step in steps]
            self.assertIn(STEP_REAPPLY_POOL_PROPS, kinds)
            self.assertLess(kinds.index(STEP_IMPORT_RENAME), kinds.index(STEP_REAPPLY_POOL_PROPS))
            self.assertLess(kinds.index(STEP_REAPPLY_POOL_PROPS), kinds.index(STEP_REAPPLY_HOLDS))

    def test_replay_props_description_names_properties(self):
        steps = plan_migration_steps(
            "temp",
            ["proxmox"],
            MIGRATE_NEW_DISKS,
            "temp_mig",
            replay_props=("comment", "compatibility"),
        )
        replay = next(step for step in steps if step.kind == STEP_REAPPLY_POOL_PROPS)
        self.assertIn("2 non-default pool properties", replay.description)
        self.assertIn("'temp'", replay.description)
        self.assertIn("(comment, compatibility)", replay.description)
        self.assertIn("zpool set", replay.description)

    def test_replay_props_description_singular(self):
        steps = plan_migration_steps(
            "temp",
            ["proxmox"],
            MIGRATE_NEW_DISKS,
            "temp_mig",
            replay_props=("comment",),
        )
        replay = next(step for step in steps if step.kind == STEP_REAPPLY_POOL_PROPS)
        self.assertIn("1 non-default pool property ", replay.description)

    def test_no_replay_props_means_no_step(self):
        for mode, dest in ((MIGRATE_NEW_DISKS, "temp_mig"), (MIGRATE_HOLDING_POOL, "fivebays")):
            steps = plan_migration_steps("temp", ["proxmox"], mode, dest)
            self.assertNotIn(STEP_REAPPLY_POOL_PROPS, [step.kind for step in steps])

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
        argv = build_migration_send_receive_command("temp/proxmox", "temp_mig/proxmox", "migrate-x")
        golden.check(self, self._normalized(argv))

    def test_rate_limit_assignment_emitted(self):
        argv = build_migration_send_receive_command(
            "temp/proxmox", "temp_mig/proxmox", "migrate-x", rate_limit="100m"
        )
        golden.check(
            self, self._normalized(argv), name="TestBuildMigrationSendReceiveCommand.rate_limit"
        )

    def test_rate_limit_assignment_omitted(self):
        argv = build_migration_send_receive_command("temp/proxmox", "temp_mig/proxmox", "migrate-x")
        golden.check(
            self, self._normalized(argv), name="TestBuildMigrationSendReceiveCommand.no_rate_limit"
        )
        self.assertNotIn("pv_rate_limit", argv[2])

    def test_invalid_rate_limit_rejected(self):
        for bad in ("abc", "10x", "1.5m", "-5m"):
            with self.assertRaises(ValueError):
                build_migration_send_receive_command(
                    "temp/proxmox", "temp_mig/proxmox", "migrate-x", rate_limit=bad
                )

    def test_names_with_spaces_are_quoted(self):
        argv = build_migration_send_receive_command("my pool/ds", "dest pool/ds", "migrate-x")
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

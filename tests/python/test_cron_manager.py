"""Tests for cron_manager.py — cron line generation and interpretation."""

import os
import re
import unittest
from unittest.mock import patch

import cron_manager
from config_core import get_paths_config
from logrotate_manager import build_logrotate_content
from profile_manager import list_profiles, save_profile
from test_support import capture_logs, temp_config_dir

CRON_LOG = "/var/log/zfsutilities/cron.log"
# Exact argv fidelity for the sink: the runner's merged output is piped
# through a line-buffered awk timestamp stamper into the configured log.
# Every % is backslash-escaped because cron terminates the command at the
# first unescaped % and feeds the remainder to the job's stdin (crontab(5)).
STAMPED_TAIL = (
    "2>&1 | stdbuf -oL awk '{ print strftime(\"\\%Y-\\%m-\\%d \\%H:\\%M:\\%S\"), $0 }' >> "
    + CRON_LOG
)

# Same rule the cron daemon applies when parsing a job line: a % not preceded
# by a backslash ends the command.
_BARE_PERCENT_RE = re.compile(r"(?<!\\)%")


class TestGenerateCronLine(unittest.TestCase):
    def test_basic(self):
        profile = {
            "profile_name": "root-backup-daily",
            "cron": {"minute": "0", "hour": "2", "day": "*", "month": "*", "weekday": "*"},
        }
        line = cron_manager.generate_cron_line(profile, "/opt/runner.py", CRON_LOG)
        self.assertIn("root-backup-daily", line)
        self.assertIn("0 2 * * *", line)
        self.assertIn("python3 /opt/runner.py", line)
        self.assertIn("mkdir -p", line)
        self.assertIn("/var/log/zfsutilities", line)
        # The generated line mkdirs the configured profile-lock dir; its
        # location follows conftest.py's ZFSUTILITIES_LOCK_DIR redirect.
        self.assertIn(cron_manager.PROFILE_LOCK_DIR, line)
        self.assertTrue(line.rstrip().endswith(STAMPED_TAIL))

    def test_specific_weekday(self):
        profile = {
            "profile_name": "test",
            "cron": {"minute": "30", "hour": "4", "day": "*", "month": "*", "weekday": "0"},
        }
        line = cron_manager.generate_cron_line(profile, "/run.py", CRON_LOG)
        self.assertIn("30 4 * * 0", line)
        self.assertIn("mkdir -p", line)
        self.assertNotIn("flock", line)
        self.assertTrue(line.rstrip().endswith(STAMPED_TAIL))

    def test_profile_name_with_spaces_sanitized(self):
        profile = {
            "profile_name": "Daily Backup #1",
            "cron": {"minute": "0", "hour": "2", "day": "*", "month": "*", "weekday": "*"},
        }
        line = cron_manager.generate_cron_line(profile, "/run.py", CRON_LOG)
        self.assertIn("run 'Daily Backup #1'", line)
        self.assertIn("mkdir -p", line)
        self.assertNotIn("flock", line)
        self.assertTrue(line.rstrip().endswith(STAMPED_TAIL))

    def test_cron_log_path_is_configurable(self):
        profile = {
            "profile_name": "p1",
            "cron": {"minute": "0", "hour": "2", "day": "*", "month": "*", "weekday": "*"},
        }
        custom = "/srv/site-logs/cron-output.log"
        line = cron_manager.generate_cron_line(profile, "/run.py", custom)
        self.assertIn("mkdir -p /srv/site-logs", line)
        self.assertIn(custom, line)
        self.assertNotIn(CRON_LOG, line)
        self.assertTrue(line.rstrip().endswith(">> " + custom))

    def test_from_cron_marker_prefixes_runner(self):
        profile = {
            "profile_name": "root-backup-daily",
            "cron": {"minute": "0", "hour": "2", "day": "*", "month": "*", "weekday": "*"},
        }
        line = cron_manager.generate_cron_line(profile, "/opt/runner.py", CRON_LOG)
        # The marker lets profile_runner silence its own output once its
        # session log exists, so cron.log keeps only pre-log failures.
        self.assertIn("&& ZFSUTILITIES_FROM_CRON=Y python3 /opt/runner.py", line)

    def test_from_cron_marker_in_condition_form(self):
        profile = {
            "profile_name": "root-backup-daily",
            "cron": {
                "minute": "0",
                "hour": "2",
                "day": "*",
                "month": "*",
                "weekday": "*",
                "condition": "[ $(date +%d) -ge 28 ]",
            },
        }
        line = cron_manager.generate_cron_line(profile, "/opt/runner.py", CRON_LOG)
        self.assertIn("&& ZFSUTILITIES_FROM_CRON=Y python3 /opt/runner.py", line)

    def test_condition_is_prepended(self):
        profile = {
            "profile_name": "root-backup-daily",
            "cron": {
                "minute": "0",
                "hour": "2",
                "day": "*",
                "month": "*",
                "weekday": "*",
                "condition": "[ $(date +%d) -ge 28 ]",
            },
        }
        line = cron_manager.generate_cron_line(profile, "/opt/runner.py", CRON_LOG)
        self.assertIn("0 2 * * *", line)
        self.assertIn(r"root [ $(date +\%d) -ge 28 ] && mkdir -p", line)
        self.assertIn("python3 /opt/runner.py", line)
        self.assertTrue(line.rstrip().endswith(STAMPED_TAIL))

    def test_missing_condition_keeps_original_format(self):
        profile = {
            "profile_name": "root-backup-daily",
            "cron": {"minute": "0", "hour": "2", "day": "*", "month": "*", "weekday": "*"},
        }
        line = cron_manager.generate_cron_line(profile, "/opt/runner.py", CRON_LOG)
        self.assertIn("root mkdir -p", line)
        self.assertNotIn("&& mkdir -p &&", line)
        self.assertTrue(line.rstrip().endswith(STAMPED_TAIL))

    def test_empty_condition_keeps_original_format(self):
        profile = {
            "profile_name": "root-backup-daily",
            "cron": {
                "minute": "0",
                "hour": "2",
                "day": "*",
                "month": "*",
                "weekday": "*",
                "condition": "   ",
            },
        }
        line = cron_manager.generate_cron_line(profile, "/opt/runner.py", CRON_LOG)
        self.assertIn("root mkdir -p", line)
        self.assertNotIn("&& mkdir -p &&", line)

    def test_condition_newlines_are_sanitized(self):
        profile = {
            "profile_name": "root-backup-daily",
            "cron": {
                "minute": "0",
                "hour": "2",
                "day": "*",
                "month": "*",
                "weekday": "*",
                "condition": "[ $(date +%d) -ge 28 ]\n[ $(date +%u) -ne 6 ]",
            },
        }
        line = cron_manager.generate_cron_line(profile, "/opt/runner.py", CRON_LOG)
        self.assertNotIn("\n", line)
        self.assertIn(r"[ $(date +\%d) -ge 28 ] [ $(date +\%u) -ne 6 ]", line)


class TestCronPercentEscaping(unittest.TestCase):
    """Cron stops a job's command at the first unescaped % (crontab(5)).

    An unescaped % — from the stamper, a condition, a profile name, or a
    path — silently killed every scheduled run on the production host with
    an unterminated-quote shell error that MAILTO="" discarded.
    """

    def _command_portion(self, line):
        return line.split("root ", 1)[1]

    def test_plain_line_has_no_bare_percent(self):
        profile = {
            "profile_name": "root-backup-daily",
            "cron": {"minute": "0", "hour": "2", "day": "*", "month": "*", "weekday": "*"},
        }
        line = cron_manager.generate_cron_line(profile, "/opt/runner.py", CRON_LOG)
        self.assertIsNone(_BARE_PERCENT_RE.search(self._command_portion(line)))

    def test_condition_line_has_no_bare_percent(self):
        profile = {
            "profile_name": "root-backup-daily",
            "cron": {
                "minute": "0",
                "hour": "2",
                "day": "*",
                "month": "*",
                "weekday": "*",
                "condition": "[ $(date +%d) -ge 28 ]",
            },
        }
        line = cron_manager.generate_cron_line(profile, "/opt/runner.py", CRON_LOG)
        self.assertIsNone(_BARE_PERCENT_RE.search(self._command_portion(line)))

    def test_condition_percent_is_escaped(self):
        profile = {
            "profile_name": "root-backup-daily",
            "cron": {
                "minute": "0",
                "hour": "2",
                "day": "*",
                "month": "*",
                "weekday": "*",
                "condition": "[ $(date +%Y-%m-%d | wc -c) -ge 8 ]",
            },
        }
        line = cron_manager.generate_cron_line(profile, "/opt/runner.py", CRON_LOG)
        self.assertIn(r"date +\%Y-\%m-\%d", line)

    def test_profile_name_percent_is_escaped(self):
        profile = {
            "profile_name": "100% sure",
            "cron": {"minute": "0", "hour": "2", "day": "*", "month": "*", "weekday": "*"},
        }
        line = cron_manager.generate_cron_line(profile, "/run.py", CRON_LOG)
        # The name is single-quoted by shlex; cron strips the backslash
        # before %, so sh still receives the literal name.
        self.assertIn(r"run '100\% sure'", line)
        self.assertIsNone(_BARE_PERCENT_RE.search(self._command_portion(line)))

    def test_already_escaped_percent_is_not_double_escaped(self):
        profile = {
            "profile_name": "root-backup-daily",
            "cron": {
                "minute": "0",
                "hour": "2",
                "day": "*",
                "month": "*",
                "weekday": "*",
                "condition": r"[ $(date +\%d) -ge 28 ]",
            },
        }
        line = cron_manager.generate_cron_line(profile, "/opt/runner.py", CRON_LOG)
        self.assertIn(r"date +\%d", line)
        self.assertNotIn(r"\\%", line)
        self.assertIsNone(_BARE_PERCENT_RE.search(self._command_portion(line)))

    def test_written_file_has_no_bare_percent(self):
        with temp_config_dir():
            profiles = [
                {
                    "profile_name": "p1",
                    "active": True,
                    "cron": {
                        "minute": "0",
                        "hour": "2",
                        "day": "*",
                        "month": "*",
                        "weekday": "*",
                        "condition": "[ $(date +%d) -ge 28 ]",
                    },
                },
            ]
            cron_manager.write_cron_file(profiles, "/runner.py", CRON_LOG)
            with open(cron_manager.CRON_FILE) as f:
                for line in f:
                    if "root " in line:
                        self.assertIsNone(_BARE_PERCENT_RE.search(self._command_portion(line)))


class TestInterpretCron(unittest.TestCase):
    def test_every_minute(self):
        result = cron_manager.interpret_cron("*", "*", "*", "*", "*")
        self.assertIn("Every minute", result)

    def test_every_day_at_time(self):
        result = cron_manager.interpret_cron("0", "2", "*", "*", "*")
        self.assertIn("02:00", result)

    def test_specific_weekday(self):
        result = cron_manager.interpret_cron("0", "2", "*", "*", "1")
        self.assertIn("Monday", result)

    def test_specific_day_of_month(self):
        result = cron_manager.interpret_cron("0", "2", "15", "*", "*")
        self.assertIn("15th", result)

    def test_specific_month(self):
        result = cron_manager.interpret_cron("0", "2", "*", "6", "*")
        self.assertIn("June", result)

    def test_step_minutes(self):
        result = cron_manager.interpret_cron("*/5", "*", "*", "*", "*")
        self.assertIn("Every 5 minutes", result)

    def test_every_hour(self):
        result = cron_manager.interpret_cron("15", "*", "*", "*", "*")
        self.assertIn("15 every hour", result)

    def test_day_and_weekday_specific(self):
        result = cron_manager.interpret_cron("0", "2", "1", "*", "0")
        self.assertIn("1st", result)
        self.assertIn("Sunday", result)

    def test_range_hours(self):
        result = cron_manager.interpret_cron("0", "9-17", "*", "*", "*")
        self.assertIn("during hours 9-17", result)


class TestWriteCronFile(unittest.TestCase):
    def test_writes_file(self):
        with temp_config_dir():
            profiles = [
                {
                    "profile_name": "p1",
                    "active": True,
                    "cron": {"minute": "0", "hour": "2", "day": "*", "month": "*", "weekday": "*"},
                },
                {
                    "profile_name": "p2",
                    "active": False,
                    "cron": {"minute": "0", "hour": "3", "day": "*", "month": "*", "weekday": "*"},
                },
            ]
            cron_manager.write_cron_file(profiles, "/runner.py", CRON_LOG)
            self.assertTrue(os.path.exists(cron_manager.CRON_FILE))
            with open(cron_manager.CRON_FILE) as f:
                content = f.read()
            self.assertIn("run p1", content)
            self.assertNotIn("run p2", content)
            self.assertIn("DO NOT EDIT MANUALLY", content)
            self.assertIn('MAILTO=""', content)
            mode = os.stat(cron_manager.CRON_FILE).st_mode
            self.assertTrue(mode & 0o400)

    def test_written_file_marks_runner_from_cron(self):
        with temp_config_dir():
            profiles = [
                {
                    "profile_name": "p1",
                    "active": True,
                    "cron": {"minute": "0", "hour": "2", "day": "*", "month": "*", "weekday": "*"},
                },
            ]
            cron_manager.write_cron_file(profiles, "/runner.py", CRON_LOG)
            with open(cron_manager.CRON_FILE) as f:
                content = f.read()
            self.assertIn("ZFSUTILITIES_FROM_CRON=Y python3 /runner.py", content)

    def test_mailto_appears_before_cron_lines(self):
        with temp_config_dir():
            profiles = [
                {
                    "profile_name": "p1",
                    "active": True,
                    "cron": {"minute": "0", "hour": "2", "day": "*", "month": "*", "weekday": "*"},
                },
            ]
            cron_manager.write_cron_file(profiles, "/runner.py", CRON_LOG)
            with open(cron_manager.CRON_FILE) as f:
                content = f.read()
            mailto_pos = content.find('MAILTO=""')
            job_pos = content.find("0 2 * * *")
            self.assertGreaterEqual(mailto_pos, 0)
            self.assertGreater(job_pos, mailto_pos)
            self.assertEqual(content.count('MAILTO=""'), 1)
            self.assertIn("mkdir -p", content)
            self.assertIn(STAMPED_TAIL, content)
            self.assertNotIn("flock", content)

    def test_write_cron_file_creates_lock_directory(self):
        with temp_config_dir():
            profiles = [
                {
                    "profile_name": "p1",
                    "active": True,
                    "cron": {"minute": "0", "hour": "2", "day": "*", "month": "*", "weekday": "*"},
                },
            ]
            lock_dir = cron_manager.PROFILE_LOCK_DIR
            self.assertFalse(os.path.exists(lock_dir))
            cron_manager.write_cron_file(profiles, "/runner.py", CRON_LOG)
            self.assertTrue(os.path.isdir(lock_dir))

    def test_write_cron_file_includes_condition(self):
        with temp_config_dir():
            profiles = [
                {
                    "profile_name": "p1",
                    "active": True,
                    "cron": {
                        "minute": "0",
                        "hour": "2",
                        "day": "*",
                        "month": "*",
                        "weekday": "*",
                        "condition": "[ $(date +%d) -ge 28 ]",
                    },
                },
            ]
            cron_manager.write_cron_file(profiles, "/runner.py", CRON_LOG)
            with open(cron_manager.CRON_FILE) as f:
                content = f.read()
            self.assertIn("0 2 * * *", content)
            self.assertIn(r"[ $(date +\%d) -ge 28 ]", content)
            self.assertIn("&& mkdir -p", content)
            self.assertIn("run p1", content)


class TestConvergeSchedulerFiles(unittest.TestCase):
    """Startup convergence of the persisted cron/logrotate drop-ins."""

    # The pre-fence format deployed before 0.125.0: plain redirect, no
    # FROM_CRON marker, no stamper — the layout that flooded cron.log.
    STALE_CONTENT = (
        "# /etc/cron.d/zfsutilities\n"
        'MAILTO=""\n'
        "0 6 * * * root mkdir -p /var/log/zfsutilities && "
        "python3 /usr/local/lib/zfsutilities/current/python/profile_runner.py "
        "run root-backup-daily >> /var/log/zfsutilities/cron.log 2>&1\n"
    )

    def _write_active_profile(self):
        save_profile(
            {
                "profile_name": "root-backup-daily",
                "active": True,
                "cron": {"minute": "0", "hour": "6", "day": "*", "month": "*", "weekday": "*"},
            }
        )

    def _stamped_tail(self):
        cron_log = get_paths_config({}, persist=False)["cron_log"]
        return f"{cron_manager._TIMESTAMP_STAMPER} >> {cron_log}"

    def test_stale_pre_fence_cron_file_is_rewritten(self):
        with temp_config_dir():
            self._write_active_profile()
            with open(cron_manager.CRON_FILE, "w") as f:
                f.write(self.STALE_CONTENT)
            actions = cron_manager.converge_scheduler_files({})
            self.assertEqual(actions, [("cron", "rewritten"), ("logrotate", "rewritten")])
            with open(cron_manager.CRON_FILE) as f:
                content = f.read()
            self.assertIn("ZFSUTILITIES_FROM_CRON=Y", content)
            self.assertIn("0 6 * * *", content)
            self.assertIn(self._stamped_tail(), content)
            self.assertNotIn(">> /var/log/zfsutilities/cron.log 2>&1", content)
            mode = os.stat(cron_manager.CRON_FILE).st_mode & 0o777
            self.assertEqual(mode, 0o644)

    def test_current_files_are_left_untouched(self):
        # A converged host must not churn: identical content means no write,
        # so the mtimes stay pinned where the test put them.  The runner
        # path is pinned because get_profile_runner_path() resolves its
        # caller's directory, which differs between cron_manager and this
        # file in the repo layout.
        with temp_config_dir():
            self._write_active_profile()
            with patch.object(cron_manager, "get_profile_runner_path", return_value="/runner.py"):
                paths_cfg = get_paths_config({}, persist=False)
                cron_manager.write_cron_file(list_profiles(), "/runner.py", paths_cfg["cron_log"])
                cron_manager.write_logrotate_file(paths_cfg)
                os.utime(cron_manager.CRON_FILE, (10**6, 10**6))
                os.utime(paths_cfg["logrotate_file"], (10**6, 10**6))
                actions = cron_manager.converge_scheduler_files({})
            self.assertEqual(actions, [])
            self.assertEqual(os.stat(cron_manager.CRON_FILE).st_mtime, 10**6)
            self.assertEqual(os.stat(paths_cfg["logrotate_file"]).st_mtime, 10**6)

    def test_missing_files_created_with_active_profile(self):
        with temp_config_dir():
            self._write_active_profile()
            paths_cfg = get_paths_config({}, persist=False)
            self.assertFalse(os.path.exists(cron_manager.CRON_FILE))
            self.assertFalse(os.path.exists(paths_cfg["logrotate_file"]))
            actions = cron_manager.converge_scheduler_files({})
            self.assertEqual(actions, [("cron", "rewritten"), ("logrotate", "rewritten")])
            self.assertTrue(os.path.exists(cron_manager.CRON_FILE))
            with open(cron_manager.CRON_FILE) as f:
                self.assertIn("ZFSUTILITIES_FROM_CRON=Y", f.read())
            with open(paths_cfg["logrotate_file"]) as f:
                self.assertEqual(f.read(), build_logrotate_content(paths_cfg))

    def test_missing_files_not_created_without_active_profiles(self):
        # A host with no scheduled profiles (e.g. tweety) gains no drop-ins.
        with temp_config_dir():
            paths_cfg = get_paths_config({}, persist=False)
            actions = cron_manager.converge_scheduler_files({})
            self.assertEqual(actions, [])
            self.assertFalse(os.path.exists(cron_manager.CRON_FILE))
            self.assertFalse(os.path.exists(paths_cfg["logrotate_file"]))

    def test_inactive_profile_does_not_create_drop_ins(self):
        with temp_config_dir():
            save_profile(
                {
                    "profile_name": "paused",
                    "active": False,
                    "cron": {"minute": "0", "hour": "6", "day": "*", "month": "*", "weekday": "*"},
                }
            )
            paths_cfg = get_paths_config({}, persist=False)
            actions = cron_manager.converge_scheduler_files({})
            self.assertEqual(actions, [])
            self.assertFalse(os.path.exists(cron_manager.CRON_FILE))
            self.assertFalse(os.path.exists(paths_cfg["logrotate_file"]))

    def test_unreadable_drop_in_is_skipped_not_clobbered(self):
        # A cron drop-in that cannot be read (here: a directory in its
        # place) is left alone with a WARN; the logrotate drop-in still
        # converges.
        with temp_config_dir():
            self._write_active_profile()
            paths_cfg = get_paths_config({}, persist=False)
            os.mkdir(cron_manager.CRON_FILE)
            with capture_logs() as logs:
                actions = cron_manager.converge_scheduler_files({})
            self.assertEqual(actions, [("logrotate", "rewritten")])
            self.assertTrue(os.path.isdir(cron_manager.CRON_FILE))
            self.assertTrue(
                any(f"Could not read drop-in {cron_manager.CRON_FILE}" in m for m in logs)
            )
            self.assertTrue(os.path.exists(paths_cfg["logrotate_file"]))

    def test_stale_logrotate_content_is_rewritten(self):
        with temp_config_dir():
            self._write_active_profile()
            paths_cfg = get_paths_config({}, persist=False)
            os.makedirs(os.path.dirname(paths_cfg["logrotate_file"]), exist_ok=True)
            with open(paths_cfg["logrotate_file"], "w") as f:
                f.write("# stale hand-written rotation\n/var/log/old.log {\n  monthly\n}\n")
            # Prime the cron file so only the logrotate half changes.  The
            # runner path is pinned to match converge_scheduler_files' view
            # (get_profile_runner_path resolves its caller's directory).
            with patch.object(cron_manager, "get_profile_runner_path", return_value="/runner.py"):
                cron_manager.write_cron_file(list_profiles(), "/runner.py", paths_cfg["cron_log"])
                actions = cron_manager.converge_scheduler_files({})
            self.assertEqual(actions, [("logrotate", "rewritten")])
            with open(paths_cfg["logrotate_file"]) as f:
                self.assertEqual(f.read(), build_logrotate_content(paths_cfg))


class TestNextRunTimes(unittest.TestCase):
    def test_every_minute(self):
        times = cron_manager.next_run_times("*", "*", "*", "*", "*", count=3)
        self.assertEqual(len(times), 3)
        # All should be 1 minute apart
        self.assertEqual((times[1] - times[0]).total_seconds(), 60)

    def test_specific_time(self):
        times = cron_manager.next_run_times("0", "2", "*", "*", "*", count=1)
        self.assertEqual(len(times), 1)
        self.assertEqual(times[0].minute, 0)
        self.assertEqual(times[0].hour, 2)

    def test_no_matches_returns_empty(self):
        times = cron_manager.next_run_times("0", "0", "31", "2", "*", count=1)
        # February 31st doesn't exist
        self.assertEqual(len(times), 0)


class TestFormatNextRuns(unittest.TestCase):
    def test_formats_runs(self):
        text = cron_manager.format_next_runs("0", "2", "*", "*", "*", count=2)
        self.assertIn("Next runs:", text)
        self.assertIn("  •", text)

    def test_no_runs_message(self):
        text = cron_manager.format_next_runs("0", "0", "31", "2", "*", count=1)
        self.assertIn("No upcoming runs", text)


class TestWeekdayOrdinals(unittest.TestCase):
    def test_parse_weekday_no_ordinal(self):
        self.assertEqual(cron_manager._parse_weekday("6"), ("6", []))

    def test_parse_weekday_single_ordinal(self):
        self.assertEqual(cron_manager._parse_weekday("6#1"), ("6", [(1, 1)]))

    def test_parse_weekday_list_and_range(self):
        self.assertEqual(
            cron_manager._parse_weekday("6#1,3-5,L"),
            ("6", [(1, 1), (3, 5), "L"]),
        )

    def test_parse_weekday_invalid_base(self):
        with self.assertRaises(ValueError):
            cron_manager._parse_weekday("*#1")

    def test_format_ordinal_specs_single(self):
        self.assertEqual(cron_manager._format_ordinal_specs([(1, 1)]), "first")

    def test_format_ordinal_specs_range(self):
        self.assertEqual(cron_manager._format_ordinal_specs([(3, 5)]), "third through fifth")

    def test_format_ordinal_specs_list_with_last(self):
        self.assertEqual(
            cron_manager._format_ordinal_specs([(1, 1), (3, 3), "L"]),
            "first, third, and last",
        )

    def test_interpret_first_saturday(self):
        result = cron_manager.interpret_cron("0", "2", "*", "*", "6#1")
        self.assertIn("first Saturday", result)
        self.assertIn("of the month", result)

    def test_interpret_last_saturday(self):
        result = cron_manager.interpret_cron("0", "2", "*", "*", "6#L")
        self.assertIn("last Saturday", result)

    def test_interpret_first_and_third_saturdays(self):
        result = cron_manager.interpret_cron("0", "2", "*", "*", "6#1,3")
        self.assertIn("first and third Saturdays", result)

    def test_interpret_first_through_fifth_saturdays(self):
        result = cron_manager.interpret_cron("0", "2", "*", "*", "6#1,3-5")
        self.assertIn("first and third through fifth Saturdays", result)

    def test_generate_cron_line_strips_ordinal(self):
        profile = {
            "profile_name": "monthly",
            "cron": {"minute": "0", "hour": "2", "day": "*", "month": "*", "weekday": "6#1"},
        }
        line = cron_manager.generate_cron_line(profile, "/run.py", CRON_LOG)
        self.assertIn("0 2 * * 6", line)
        self.assertNotIn("#1", line)
        self.assertIn("mkdir -p", line)
        self.assertTrue(line.rstrip().endswith(STAMPED_TAIL))

    def test_next_run_first_saturday(self):
        times = cron_manager.next_run_times("0", "2", "*", "*", "6#1", count=3)
        self.assertEqual(len(times), 3)
        for t in times:
            self.assertEqual(t.weekday(), 5)  # Saturday
            self.assertLessEqual(t.day, 7)

    def test_next_run_last_saturday(self):
        times = cron_manager.next_run_times("0", "2", "*", "*", "6#L", count=3)
        self.assertEqual(len(times), 3)
        for t in times:
            self.assertEqual(t.weekday(), 5)
            # Adding 7 days should cross into the next month
            from datetime import timedelta

            self.assertNotEqual((t + timedelta(days=7)).month, t.month)

    def test_next_run_fifth_saturday_may_skip_months(self):
        # Find three fifth Saturdays; there may be gaps of several months.
        times = cron_manager.next_run_times("0", "2", "*", "*", "6#5", count=3)
        self.assertEqual(len(times), 3)
        for t in times:
            self.assertEqual(t.weekday(), 5)
            self.assertGreaterEqual(t.day, 29)

    def test_next_run_invalid_ordinal_returns_empty(self):
        times = cron_manager.next_run_times("0", "2", "*", "*", "*#1", count=1)
        self.assertEqual(len(times), 0)


if __name__ == "__main__":
    unittest.main()

"""Tests for cron_manager.py — cron line generation and interpretation."""

import os
import unittest

from test_support import temp_config_dir, capture_logs

import cron_manager


class TestGenerateCronLine(unittest.TestCase):

    def test_basic(self):
        profile = {
            "profile_name": "root-backup-daily",
            "cron": {"minute": "0", "hour": "2", "day": "*", "month": "*", "weekday": "*"},
        }
        line = cron_manager.generate_cron_line(profile, "/opt/runner.py")
        self.assertIn("root-backup-daily", line)
        self.assertIn("0 2 * * *", line)
        self.assertIn("python3 /opt/runner.py", line)
        self.assertIn("flock -n -E 0", line)
        self.assertIn("/run/lock/zfs/profiles/root-backup-daily.lock", line)

    def test_specific_weekday(self):
        profile = {
            "profile_name": "test",
            "cron": {"minute": "30", "hour": "4", "day": "*", "month": "*", "weekday": "0"},
        }
        line = cron_manager.generate_cron_line(profile, "/run.py")
        self.assertIn("30 4 * * 0", line)
        self.assertIn("flock -n -E 0", line)

    def test_profile_name_with_spaces_sanitized(self):
        profile = {
            "profile_name": "Daily Backup #1",
            "cron": {"minute": "0", "hour": "2", "day": "*", "month": "*", "weekday": "*"},
        }
        line = cron_manager.generate_cron_line(profile, "/run.py")
        self.assertIn("/run/lock/zfs/profiles/Daily_Backup__1.lock", line)


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
        with temp_config_dir() as tmpdir:
            profiles = [
                {"profile_name": "p1", "active": True, "cron": {"minute": "0", "hour": "2", "day": "*", "month": "*", "weekday": "*"}},
                {"profile_name": "p2", "active": False, "cron": {"minute": "0", "hour": "3", "day": "*", "month": "*", "weekday": "*"}},
            ]
            cron_manager.write_cron_file(profiles, "/runner.py")
            self.assertTrue(os.path.exists(cron_manager.CRON_FILE))
            with open(cron_manager.CRON_FILE) as f:
                content = f.read()
            self.assertIn("p1", content)
            self.assertNotIn("p2", content)
            self.assertIn("DO NOT EDIT MANUALLY", content)
            self.assertIn('MAILTO=""', content)
            mode = os.stat(cron_manager.CRON_FILE).st_mode
            self.assertTrue(mode & 0o400)

    def test_mailto_appears_before_cron_lines(self):
        with temp_config_dir():
            profiles = [
                {"profile_name": "p1", "active": True, "cron": {"minute": "0", "hour": "2", "day": "*", "month": "*", "weekday": "*"}},
            ]
            cron_manager.write_cron_file(profiles, "/runner.py")
            with open(cron_manager.CRON_FILE) as f:
                content = f.read()
            mailto_pos = content.find('MAILTO=""')
            job_pos = content.find("0 2 * * *")
            self.assertGreaterEqual(mailto_pos, 0)
            self.assertGreater(job_pos, mailto_pos)
            self.assertEqual(content.count('MAILTO=""'), 1)


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
        self.assertEqual(
            cron_manager._format_ordinal_specs([(3, 5)]), "third through fifth"
        )

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
        line = cron_manager.generate_cron_line(profile, "/run.py")
        self.assertIn("0 2 * * 6", line)
        self.assertNotIn("#1", line)

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

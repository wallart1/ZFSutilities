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

    def test_specific_weekday(self):
        profile = {
            "profile_name": "test",
            "cron": {"minute": "30", "hour": "4", "day": "*", "month": "*", "weekday": "0"},
        }
        line = cron_manager.generate_cron_line(profile, "/run.py")
        self.assertIn("30 4 * * 0", line)


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


if __name__ == "__main__":
    unittest.main()

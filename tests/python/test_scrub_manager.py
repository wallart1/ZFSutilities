"""Tests for scrub_manager.py — scrub parsing, queue logic, system timers."""

import json
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import sys

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

import zfs_lock_manager as zlm

from test_support import temp_config_dir, capture_logs

import file_locking

import scrub_manager as sm


class TestScrubControlLocking(unittest.TestCase):
    """Scrub control functions acquire and release pool-level locks."""

    def setUp(self):
        zlm._lock_refcounts.clear()

    def _run_locked(self, func, repo, expected_description):
        with patch.object(sm, "zlm") as zlm_mock:
            zlm_mock.lock.return_value.__enter__ = MagicMock(return_value="lock-id")
            zlm_mock.lock.return_value.__exit__ = MagicMock(return_value=False)
            result = func("tank", repo=repo)
        zlm_mock.lock.assert_called_once_with(
            "tank", "w", expected_description
        )
        zlm_mock.lock.return_value.__exit__.assert_called_once()
        return result

    def test_start_scrub_acquires_pool_lock(self):
        repo = MagicMock()
        repo.start_scrub.return_value = True
        self.assertTrue(
            self._run_locked(sm.start_scrub, repo, "start scrub tank")
        )
        repo.start_scrub.assert_called_once_with("tank", timeout=30)

    def test_start_scrub_releases_lock_on_failure(self):
        repo = MagicMock()
        repo.start_scrub.return_value = False
        self.assertFalse(
            self._run_locked(sm.start_scrub, repo, "start scrub tank")
        )

    def test_pause_scrub_acquires_pool_lock(self):
        repo = MagicMock()
        repo.pause_scrub.return_value = True
        self.assertTrue(
            self._run_locked(sm.pause_scrub, repo, "pause scrub tank")
        )
        repo.pause_scrub.assert_called_once_with("tank", timeout=30)

    def test_resume_scrub_acquires_pool_lock(self):
        repo = MagicMock()
        repo.resume_scrub.return_value = True
        self.assertTrue(
            self._run_locked(sm.resume_scrub, repo, "resume scrub tank")
        )
        repo.resume_scrub.assert_called_once_with("tank", timeout=30)

    def test_stop_scrub_acquires_pool_lock(self):
        repo = MagicMock()
        repo.stop_scrub.return_value = True
        self.assertTrue(
            self._run_locked(sm.stop_scrub, repo, "stop scrub tank")
        )
        repo.stop_scrub.assert_called_once_with("tank", timeout=30)


class TestParseScrubStatus(unittest.TestCase):

    def test_none_requested(self):
        raw = "  scan: none requested\n"
        info = sm.parse_scrub_status(raw)
        self.assertEqual(info.state, sm.ScrubState.NONE)

    def test_in_progress(self):
        raw = (
            "  scan: scrub in progress since Sun May 10 00:24:03 2026\n"
            "    1.23T scanned at 123M/s, 456G issued at 45M/s\n"
            "    0B repaired, 12.34% done, 01:23:45 to go\n"
        )
        info = sm.parse_scrub_status(raw)
        self.assertEqual(info.state, sm.ScrubState.SCANNING)
        self.assertAlmostEqual(info.progress_percent, 12.34)
        self.assertEqual(info.last_scrub, "Sun May 10 00:24:03 2026")

    def test_paused(self):
        raw = (
            "  scan: scrub paused since Sun May 10 00:24:03 2026\n"
            "    1.23T scanned at 123M/s, 456G issued at 45M/s\n"
            "    0B repaired, 50.00% done\n"
        )
        info = sm.parse_scrub_status(raw)
        self.assertEqual(info.state, sm.ScrubState.PAUSED)
        self.assertAlmostEqual(info.progress_percent, 50.0)

    def test_finished(self):
        raw = "  scan: scrub repaired 0B in 00:00:02 with 0 errors on Sun May 10 00:24:03 2026\n"
        info = sm.parse_scrub_status(raw)
        self.assertEqual(info.state, sm.ScrubState.FINISHED)
        self.assertEqual(info.errors, 0)
        self.assertEqual(info.last_scrub, "Sun May 10 00:24:03 2026")

    def test_canceled(self):
        raw = "  scan: scrub canceled on Sun May 10 00:24:03 2026\n"
        info = sm.parse_scrub_status(raw)
        self.assertEqual(info.state, sm.ScrubState.CANCELED)
        self.assertEqual(info.last_scrub, "Sun May 10 00:24:03 2026")

    def test_resilver_treated_as_finished(self):
        raw = "  scan: resilvered 10G in 01:23:45 with 0 errors on Mon Jan  1 12:00:00 2026\n"
        info = sm.parse_scrub_status(raw)
        self.assertEqual(info.state, sm.ScrubState.FINISHED)

    def test_empty_raw(self):
        info = sm.parse_scrub_status("")
        self.assertEqual(info.state, sm.ScrubState.UNKNOWN)

    def test_finished_with_days_duration(self):
        raw = "  scan: scrub repaired 0B in 1 days 01:35:48 with 0 errors on Wed Jun  3 20:50:19 2026\n"
        info = sm.parse_scrub_status(raw)
        self.assertEqual(info.state, sm.ScrubState.FINISHED)
        self.assertEqual(info.errors, 0)
        self.assertEqual(info.last_scrub, "Wed Jun  3 20:50:19 2026")

    def test_in_progress_remaining_seconds(self):
        raw = (
            "  scan: scrub in progress since Sun May 10 00:24:03 2026\n"
            "    1.23T scanned at 123M/s, 456G issued at 45M/s\n"
            "    0B repaired, 12.34% done, 01:23:45 to go\n"
        )
        info = sm.parse_scrub_status(raw)
        self.assertEqual(info.remaining_seconds, 5025)

    def test_in_progress_remaining_seconds_with_days(self):
        raw = (
            "  scan: scrub in progress since Sun May 10 00:24:03 2026\n"
            "    1.23T scanned at 123M/s, 456G issued at 45M/s\n"
            "    0B repaired, 12.34% done, 1 days 01:23:45 to go\n"
        )
        info = sm.parse_scrub_status(raw)
        self.assertEqual(info.remaining_seconds, 86400 + 5025)

    def test_in_progress_no_remaining(self):
        raw = (
            "  scan: scrub in progress since Sun May 10 00:24:03 2026\n"
            "    1.23T scanned at 123M/s, 456G issued at 45M/s\n"
            "    0B repaired, 12.34% done\n"
        )
        info = sm.parse_scrub_status(raw)
        self.assertIsNone(info.remaining_seconds)
        self.assertIsNone(info.eta)

    def test_in_progress_eta_computed(self):
        from datetime import datetime, timedelta
        raw = (
            "  scan: scrub in progress since Sun May 10 00:24:03 2026\n"
            "    1.23T scanned at 123M/s, 456G issued at 45M/s\n"
            "    0B repaired, 12.34% done, 01:23:45 to go\n"
        )
        fixed_now = datetime(2026, 6, 28, 10, 30, 0)
        with patch.object(sm, "datetime") as mock_datetime:
            mock_datetime.now.return_value = fixed_now
            mock_datetime.timedelta = timedelta
            info = sm.parse_scrub_status(raw)
        self.assertEqual(info.eta, fixed_now + timedelta(seconds=5025))


class TestScrubQueue(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.state_path = os.path.join(self.tmpdir.name, "scrub_state.json")
        self._orig_path = sm.SCRUB_STATE_PATH
        self._orig_lock = file_locking.SCRUB_STATE_LOCK_PATH
        sm.SCRUB_STATE_PATH = self.state_path
        file_locking.SCRUB_STATE_LOCK_PATH = os.path.join(
            self.tmpdir.name, ".scrub_state.lock"
        )

    def tearDown(self):
        sm.SCRUB_STATE_PATH = self._orig_path
        file_locking.SCRUB_STATE_LOCK_PATH = self._orig_lock
        self.tmpdir.cleanup()

    def test_add_pending_and_target(self):
        q = sm.ScrubQueue(target=1)
        q.add_pending(["tank"])
        self.assertIn("tank", q.pending)
        self.assertEqual(q.target, 1)

    def test_set_target(self):
        q = sm.ScrubQueue(target=1)
        q.set_target(3)
        self.assertEqual(q.target, 3)

    def test_tick_moves_pending_to_active(self):
        q = sm.ScrubQueue(target=1)
        q.add_pending(["tank"])
        states = {"tank": sm.ScrubInfo(state=sm.ScrubState.NONE)}
        with patch.object(sm, "start_scrub", return_value=True):
            q.tick(states)
        self.assertIn("tank", q.active)
        self.assertNotIn("tank", q.pending)

    def test_tick_starts_scrub_when_pending_state_is_finished(self):
        """A queued scrub must start even if zpool status shows a prior finished scrub."""
        q = sm.ScrubQueue(target=1)
        q.add_pending(["tank"])
        states = {"tank": sm.ScrubInfo(state=sm.ScrubState.FINISHED)}
        with patch.object(sm, "start_scrub", return_value=True) as mock_start:
            q.tick(states)
        mock_start.assert_called_once_with("tank")
        self.assertIn("tank", q.active)
        self.assertNotIn("tank", q.pending)
        self.assertNotIn("tank", q.finished)

    def test_tick_detects_finished(self):
        q = sm.ScrubQueue(target=1)
        q.active.add("tank")
        states = {"tank": sm.ScrubInfo(state=sm.ScrubState.FINISHED)}
        q.tick(states)
        self.assertIn("tank", q.finished)
        self.assertNotIn("tank", q.active)

    def test_tick_detects_external_pause(self):
        q = sm.ScrubQueue(target=1)
        q.active.add("tank")
        states = {"tank": sm.ScrubInfo(state=sm.ScrubState.PAUSED)}
        q.tick(states)
        self.assertIn("tank", q.paused)
        self.assertNotIn("tank", q.active)

    def test_remove_pools(self):
        q = sm.ScrubQueue(target=1)
        q.pending.add("tank")
        q.active.add("data")
        q.remove_pools(["tank", "data"])
        self.assertNotIn("tank", q.pending)
        self.assertNotIn("data", q.active)

    def test_persistence(self):
        q = sm.ScrubQueue(target=2)
        q.add_pending(["tank", "data"])
        q._save()

        q2 = sm.ScrubQueue(target=1)
        self.assertEqual(q2.target, 2)
        self.assertIn("tank", q2.pending)
        self.assertIn("data", q2.pending)

    def test_save_creates_lock_file(self):
        q = sm.ScrubQueue(target=1)
        q.add_pending(["tank"])
        self.assertTrue(os.path.exists(file_locking.SCRUB_STATE_LOCK_PATH))

    def test_resume_pools(self):
        q = sm.ScrubQueue(target=1)
        q.paused.add("tank")
        q.paused_by_user.add("tank")
        q.resume_pools(["tank"])
        self.assertIn("tank", q.pending)
        self.assertNotIn("tank", q.paused)
        self.assertNotIn("tank", q.paused_by_user)

    def test_pause_pools_marks_user_paused(self):
        q = sm.ScrubQueue(target=1)
        q.active.add("tank")
        q.pause_pools(["tank"])
        self.assertIn("tank", q.paused)
        self.assertIn("tank", q.paused_by_user)

    def test_user_paused_pool_not_auto_resumed(self):
        """A pool paused by the user must stay paused when below target."""
        q = sm.ScrubQueue(target=1)
        q.active.add("tank")
        q.pause_pools(["tank"])
        states = {"tank": sm.ScrubInfo(state=sm.ScrubState.PAUSED)}
        with patch.object(sm, "resume_scrub") as mock_resume:
            q.tick(states)
        self.assertIn("tank", q.paused)
        self.assertIn("tank", q.paused_by_user)
        mock_resume.assert_not_called()

    def test_target_paused_pool_auto_resumed_when_target_raised(self):
        """Pools paused by lowering the target resume when target is raised."""
        q = sm.ScrubQueue(target=2)
        q.active.add("tank")
        q.active.add("data")
        states = {
            "tank": sm.ScrubInfo(state=sm.ScrubState.SCANNING),
            "data": sm.ScrubInfo(state=sm.ScrubState.SCANNING),
        }
        q.set_target(1)
        with patch.object(sm, "pause_scrub", return_value=True) as mock_pause:
            q.tick(states)
        self.assertEqual(mock_pause.call_count, 1)
        paused_pool = next(iter(q.paused))
        self.assertNotIn(paused_pool, q.paused_by_user)

        q.set_target(2)
        states[paused_pool] = sm.ScrubInfo(state=sm.ScrubState.PAUSED)
        with patch.object(sm, "resume_scrub", return_value=True) as mock_resume:
            q.tick(states)
        self.assertIn(paused_pool, q.active)
        mock_resume.assert_called_once_with(paused_pool)

    def test_tick_detects_external_scrub(self):
        q = sm.ScrubQueue(target=1)
        states = {"tank": sm.ScrubInfo(state=sm.ScrubState.SCANNING)}
        q.tick(states)
        self.assertIn("tank", q.active)

    def test_tick_grace_period_for_none(self):
        q = sm.ScrubQueue(target=1)
        q.active.add("tank")
        q._start_times["tank"] = sm.time.time()
        states = {"tank": sm.ScrubInfo(state=sm.ScrubState.NONE)}
        q.tick(states)
        self.assertIn("tank", q.active)
        # After grace period expires
        q._start_times["tank"] = sm.time.time() - 60
        q.tick(states)
        self.assertIn("tank", q.finished)
        self.assertNotIn("tank", q.active)

    def test_tick_pending_paused_stays_pending(self):
        """A pending pool that is still live-PAUSED must not be promoted to active."""
        q = sm.ScrubQueue(target=1)
        q.add_pending(["tank"])
        states = {"tank": sm.ScrubInfo(state=sm.ScrubState.PAUSED)}
        with patch.object(sm, "start_scrub") as mock_start:
            q.tick(states)
        self.assertIn("tank", q.pending)
        self.assertNotIn("tank", q.active)
        mock_start.assert_not_called()


class TestParseScrubStatusMixed(unittest.TestCase):

    def test_scan_line_drops_stale_paused_when_scanning(self):
        """A resumed scrub can briefly emit both 'in progress' and 'paused' lines."""
        raw = (
            "  scan: scrub in progress since Sun May 10 00:24:03 2026\n"
            "    scrub paused since Sun May 10 00:24:03 2026\n"
            "    scrub started on Sun May 10 00:00:00 2026\n"
            "    1.23T scanned at 123M/s, 456G issued at 45M/s\n"
            "    0B repaired, 12.34% done, 01:23:45 to go\n"
        )
        info = sm.parse_scrub_status(raw)
        self.assertEqual(info.state, sm.ScrubState.SCANNING)
        self.assertAlmostEqual(info.progress_percent, 12.34)
        self.assertNotIn("scrub paused", info.scan_line)
        self.assertIn("scrub in progress", info.scan_line)
        self.assertIn("12.34% done", info.scan_line)


class TestPoolActionsScrub(unittest.TestCase):

    def test_on_scrub_resume_calls_resume_scrub_for_paused_pools(self):
        """on_scrub_resume issues zpool scrub only for pools that were paused."""
        from test_support import mock_gtk

        with mock_gtk():
            import pool_actions
            import pools_page

        app = MagicMock()
        app.scrub_queue.paused = {"tank"}

        with patch.object(
            pool_actions, "get_selected_pool_names", return_value=["tank", "data"]
        ):
            with patch.object(pool_actions, "resume_scrub") as mock_resume:
                with patch.object(pools_page, "refresh_scrub_table") as mock_refresh:
                    with patch.object(
                        pools_page, "schedule_scrub_refresh_burst"
                    ) as mock_burst:
                        pool_actions.on_scrub_resume(app)

        mock_resume.assert_called_once_with("tank")
        app.scrub_queue.resume_pools.assert_called_once_with(["tank", "data"])
        mock_refresh.assert_called_once_with(app)
        mock_burst.assert_called_once_with(app)

    def test_on_scrub_start_schedules_refresh_burst(self):
        """Start handler adds pools to queue and schedules a refresh burst."""
        from test_support import mock_gtk

        with mock_gtk():
            import pool_actions
            import pools_page

        app = MagicMock()
        with patch.object(
            pool_actions, "get_selected_pool_names", return_value=["tank"]
        ):
            with patch.object(pools_page, "refresh_scrub_table") as mock_refresh:
                with patch.object(
                    pools_page, "schedule_scrub_refresh_burst"
                ) as mock_burst:
                    pool_actions.on_scrub_start(app)

        app.scrub_queue.add_pending.assert_called_once_with(["tank"])
        mock_refresh.assert_called_once_with(app)
        mock_burst.assert_called_once_with(app)

    def test_on_scrub_pause_schedules_refresh_burst(self):
        """Pause handler pauses pools and schedules a refresh burst."""
        from test_support import mock_gtk

        with mock_gtk():
            import pool_actions
            import pools_page

        app = MagicMock()
        with patch.object(
            pool_actions, "get_selected_pool_names", return_value=["tank"]
        ):
            with patch.object(pool_actions, "pause_scrub"):
                with patch.object(pools_page, "refresh_scrub_table") as mock_refresh:
                    with patch.object(
                        pools_page, "schedule_scrub_refresh_burst"
                    ) as mock_burst:
                        pool_actions.on_scrub_pause(app)

        app.scrub_queue.pause_pools.assert_called_once_with(["tank"])
        mock_refresh.assert_called_once_with(app)
        mock_burst.assert_called_once_with(app)

    def test_on_scrub_stop_schedules_refresh_burst(self):
        """Stop handler stops scrubs and schedules a refresh burst."""
        from test_support import mock_gtk

        with mock_gtk():
            import pool_actions
            import pools_page

        app = MagicMock()
        with patch.object(
            pool_actions, "get_selected_pool_names", return_value=["tank"]
        ):
            with patch.object(pool_actions, "stop_scrub"):
                with patch.object(pools_page, "refresh_scrub_table") as mock_refresh:
                    with patch.object(
                        pools_page, "schedule_scrub_refresh_burst"
                    ) as mock_burst:
                        pool_actions.on_scrub_stop(app)

        app.scrub_queue.remove_pools.assert_called_once_with(["tank"])
        mock_refresh.assert_called_once_with(app)
        mock_burst.assert_called_once_with(app)


class TestScheduleScrubRefreshBurst(unittest.TestCase):

    def test_schedules_initial_timeout(self):
        """schedule_scrub_refresh_burst schedules the first timeout."""
        from test_support import mock_gtk

        with mock_gtk():
            import pools_page

        app = MagicMock()
        with patch.object(pools_page.GLib, "timeout_add_seconds") as mock_timeout:
            pools_page.schedule_scrub_refresh_burst(app, count=3, interval=2)

        self.assertEqual(mock_timeout.call_count, 1)
        args, _kwargs = mock_timeout.call_args
        self.assertEqual(args[0], 2)
        self.assertTrue(callable(args[1]))
        self.assertEqual(args[2], 3)


class TestSystemScrubHelpers(unittest.TestCase):

    def test_get_system_scrub_state_parses_enabled(self):
        with patch("subprocess.run") as mock_run:
            def side_effect(cmd, **kwargs):
                result = MagicMock()
                if "weekly" in cmd[-1]:
                    result.returncode = 0
                    result.stdout = "enabled\n"
                else:
                    result.returncode = 1
                    result.stdout = "disabled\n"
                return result
            mock_run.side_effect = side_effect
            state = sm.get_system_scrub_state("tank")
        self.assertTrue(state["weekly"])
        self.assertFalse(state["monthly"])

    def test_set_system_scrub_enabled(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            ok = sm.set_system_scrub_enabled("tank", weekly=True, monthly=False)
        self.assertTrue(ok)
        calls = [c[0][0] for c in mock_run.call_args_list]
        cmd_strs = [" ".join(str(a) for a in c) for c in calls]
        self.assertTrue(any("enable" in s and "weekly" in s for s in cmd_strs))
        self.assertTrue(any("disable" in s and "monthly" in s for s in cmd_strs))


if __name__ == "__main__":
    unittest.main()

"""Tests for logging_config.py — message levels, GUI sink, and session log env."""

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from logging_config import (
    log_msg,
    set_log_sink,
    get_log_sink,
    set_session_log,
    restore_session_log,
    session_log_context,
    MSG_LEVELS,
    parse_msg_level,
    viewer_should_show,
    NONE_LEVEL,
    NONE_PRIORITY,
    _MSG_PRIORITY,
)


class TestSessionLogHelpers(unittest.TestCase):
    """set_session_log / restore_session_log manage environment variables."""

    def setUp(self):
        for key in ("ZFSUTILITIES_LOG_FILE", "ZFSUTILITIES_LOG_INHERIT"):
            if key in os.environ:
                del os.environ[key]

    def tearDown(self):
        for key in ("ZFSUTILITIES_LOG_FILE", "ZFSUTILITIES_LOG_INHERIT"):
            if key in os.environ:
                del os.environ[key]

    def test_set_session_log_sets_both_vars(self):
        previous = set_session_log("/tmp/session.log")
        self.assertEqual(previous, (None, None))
        self.assertEqual(os.environ["ZFSUTILITIES_LOG_FILE"], "/tmp/session.log")
        self.assertEqual(os.environ["ZFSUTILITIES_LOG_INHERIT"], "Y")

    def test_restore_session_log_unsets_when_previously_unset(self):
        set_session_log("/tmp/session.log")
        restore_session_log((None, None))
        self.assertNotIn("ZFSUTILITIES_LOG_FILE", os.environ)
        self.assertNotIn("ZFSUTILITIES_LOG_INHERIT", os.environ)

    def test_restore_session_log_preserves_previous_values(self):
        os.environ["ZFSUTILITIES_LOG_FILE"] = "/tmp/old.log"
        os.environ["ZFSUTILITIES_LOG_INHERIT"] = "N"
        previous = set_session_log("/tmp/new.log")
        self.assertEqual(previous, ("/tmp/old.log", "N"))
        restore_session_log(previous)
        self.assertEqual(os.environ["ZFSUTILITIES_LOG_FILE"], "/tmp/old.log")
        self.assertEqual(os.environ["ZFSUTILITIES_LOG_INHERIT"], "N")

    def test_session_log_context_restores_on_success(self):
        os.environ["ZFSUTILITIES_LOG_FILE"] = "/tmp/prior.log"
        with session_log_context("/tmp/inner.log"):
            self.assertEqual(os.environ["ZFSUTILITIES_LOG_FILE"], "/tmp/inner.log")
            self.assertEqual(os.environ["ZFSUTILITIES_LOG_INHERIT"], "Y")
        self.assertEqual(os.environ["ZFSUTILITIES_LOG_FILE"], "/tmp/prior.log")
        self.assertNotIn("ZFSUTILITIES_LOG_INHERIT", os.environ)

    def test_session_log_context_restores_on_exception(self):
        previous = "/tmp/prior.log"
        os.environ["ZFSUTILITIES_LOG_FILE"] = previous
        with self.assertRaises(RuntimeError):
            with session_log_context("/tmp/inner.log"):
                self.assertEqual(os.environ["ZFSUTILITIES_LOG_FILE"], "/tmp/inner.log")
                raise RuntimeError("boom")
        self.assertEqual(os.environ["ZFSUTILITIES_LOG_FILE"], previous)


class TestLogMsg(unittest.TestCase):
    """log_msg routes to sink, stderr, and file without priority filtering."""

    def tearDown(self):
        set_log_sink(None)
        os.environ.pop("ZFSUTILITIES_LOG_FILE", None)
        os.environ.pop("ZFSUTILITIES_LOG_INHERIT", None)
        os.environ.pop("msg_level", None)

    def test_log_msg_emits_to_sink(self):
        sink = MagicMock()
        set_log_sink(sink)
        log_msg("INFO: hello world")
        self.assertTrue(any("hello world" in m for m in sink.call_args[0]))

    def test_log_msg_delivers_all_levels_to_sink(self):
        sink = MagicMock()
        set_log_sink(sink)
        os.environ["msg_level"] = "WARN"
        log_msg("INFO: hidden before, visible now")
        log_msg("WARN: visible")
        messages = [call[0][0] for call in sink.call_args_list]
        self.assertTrue(any("hidden before" in m for m in messages))
        self.assertTrue(any("visible" in m for m in messages))

    def test_log_msg_writes_to_file(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            path = f.name
        try:
            os.environ["ZFSUTILITIES_LOG_FILE"] = path
            log_msg("INFO: should appear")
            with open(path) as fh:
                content = fh.read()
            self.assertIn("should appear", content)
            self.assertIn("logging_config.py:", content)
        finally:
            os.unlink(path)

    def test_log_msg_writes_all_levels_to_file(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            path = f.name
        try:
            os.environ["ZFSUTILITIES_LOG_FILE"] = path
            os.environ["msg_level"] = "WARN"
            log_msg("DEBUG: low")
            log_msg("INFO: mid")
            log_msg("WARN: high")
            with open(path) as fh:
                content = fh.read()
            self.assertIn("low", content)
            self.assertIn("mid", content)
            self.assertIn("high", content)
        finally:
            os.unlink(path)

    def test_log_msg_writes_to_file_when_inherit_set(self):
        """Python log_msg should write to file even when INHERIT is set."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            path = f.name
        try:
            os.environ["ZFSUTILITIES_LOG_FILE"] = path
            os.environ["ZFSUTILITIES_LOG_INHERIT"] = "Y"
            log_msg("INFO: should appear")
            with open(path) as fh:
                content = fh.read()
            self.assertIn("should appear", content)
        finally:
            os.unlink(path)

    def test_log_msg_returns_full_message(self):
        result = log_msg("INFO: return value")
        self.assertIsNotNone(result)
        self.assertIn("return value", result)

    def test_get_log_sink_returns_current_sink(self):
        sink = MagicMock()
        set_log_sink(sink)
        self.assertIs(get_log_sink(), sink)


class TestParseMsgLevel(unittest.TestCase):

    def test_parses_timestamped_line(self):
        line = "2026-06-21 13:00:00  /path/file:10: WARN: something"
        self.assertEqual(parse_msg_level(line), "WARN")

    def test_parses_non_timestamped_line(self):
        line = "/path/file:10: DEBUG: details"
        self.assertEqual(parse_msg_level(line), "DEBUG")

    def test_returns_none_for_trailer(self):
        line = "# END: rc=0, duration=1.2s"
        self.assertIsNone(parse_msg_level(line))

    def test_returns_none_for_raw_output(self):
        line = "sending incremental stream"
        self.assertIsNone(parse_msg_level(line))

    def test_returns_none_for_empty(self):
        self.assertIsNone(parse_msg_level(""))
        self.assertIsNone(parse_msg_level(None))


class TestViewerShouldShow(unittest.TestCase):

    def test_none_level_always_visible(self):
        for level in MSG_LEVELS:
            self.assertTrue(viewer_should_show(NONE_LEVEL, level))

    def test_level_filtering(self):
        self.assertTrue(viewer_should_show("WARN", "INFO"))
        self.assertFalse(viewer_should_show("INFO", "WARN"))
        self.assertTrue(viewer_should_show("INFO", "INFO"))
        self.assertTrue(viewer_should_show("DEBUG", "DEBUG"))

    def test_invalid_levels_are_visible(self):
        self.assertTrue(viewer_should_show("BOGUS", "INFO"))
        self.assertTrue(viewer_should_show("INFO", "BOGUS"))


if __name__ == "__main__":
    unittest.main()

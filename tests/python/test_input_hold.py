"""Tests for input_hold.py — the python input-hold prompt helpers."""

import io
import os
import sys
import unittest
from unittest.mock import patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

import input_hold as ih


class _StderrCapture(io.StringIO):
    """StringIO that tolerates writes after close during teardown."""

    def write(self, s):
        return 0 if self.closed else super().write(s)


class TestHoldActive(unittest.TestCase):
    """The protocol is armed only by the GUI runner's env var."""

    def test_active_when_env_set(self):
        with patch.dict(os.environ, {"ZFSUTILITIES_INPUT_HOLD": "Y"}):
            self.assertTrue(ih.hold_active())

    def test_inactive_without_env(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(ih.hold_active())


class TestAskYn(unittest.TestCase):
    """ask_yn emits REQ/ACK markers under the protocol and stays silent otherwise."""

    def _ask(self, answers, env):
        stderr = _StderrCapture()
        environ = {"ZFSUTILITIES_INPUT_HOLD": "Y"} if env else {}
        inputs = iter(answers)
        with (
            patch.dict(os.environ, environ, clear=not env),
            patch("sys.stderr", stderr),
            patch("builtins.input", side_effect=lambda _prompt="": next(inputs)),
        ):
            result = ih.ask_yn("Proceed with test?")
        return result, stderr.getvalue()

    def test_hold_mode_yes(self):
        result, stderr = self._ask(["y"], env=True)
        self.assertTrue(result)
        self.assertEqual(stderr.count("ZFSU-INPUT-REQ|"), 1)
        self.assertEqual(stderr.count("ZFSU-INPUT-ACK|"), 1)
        self.assertIn("Proceed with test? [y/N]: ", stderr)
        # REQ and ACK share one uuid: the hold keeps its action number.
        req_id = stderr.split("|")[1]
        ack_id = stderr.split("ZFSU-INPUT-ACK|")[1].split("|")[0].strip()
        self.assertEqual(req_id, ack_id)

    def test_hold_mode_invalid_then_no_reuses_uuid(self):
        result, stderr = self._ask(["x", "n"], env=True)
        self.assertFalse(result)
        self.assertEqual(stderr.count("ZFSU-INPUT-REQ|"), 2)
        self.assertEqual(stderr.count("ZFSU-INPUT-ACK|"), 1)
        self.assertIn("Please answer y or n.", stderr)
        ids = {
            line.split("|", 2)[1]
            for line in stderr.splitlines()
            if line.startswith("ZFSU-INPUT-REQ|")
        }
        self.assertEqual(len(ids), 1)

    def test_terminal_mode_emits_no_markers(self):
        result, stderr = self._ask(["y"], env=False)
        self.assertTrue(result)
        self.assertEqual(stderr, "")

    def test_default_on_empty_answer(self):
        result, _ = self._ask([""], env=True)
        self.assertFalse(result)  # default N


class TestAskLine(unittest.TestCase):
    """ask_line returns the answer verbatim with REQ/ACK around the read."""

    def _ask(self, answer, env, prompt="Enter path:"):
        stderr = _StderrCapture()
        environ = {"ZFSUTILITIES_INPUT_HOLD": "Y"} if env else {}
        with (
            patch.dict(os.environ, environ, clear=not env),
            patch("sys.stderr", stderr),
            patch("builtins.input", side_effect=lambda _prompt="": answer),
        ):
            got = ih.ask_line(prompt)
        return got, stderr.getvalue()

    def test_hold_mode_returns_answer_with_markers(self):
        got, stderr = self._ask("/tank/key", env=True)
        self.assertEqual(got, "/tank/key")
        self.assertIn("ZFSU-INPUT-REQ|", stderr)
        self.assertIn("ZFSU-INPUT-ACK|", stderr)
        self.assertIn("Enter path:", stderr)

    def test_hold_mode_empty_answer_allowed(self):
        got, stderr = self._ask("", env=True)
        self.assertEqual(got, "")
        self.assertEqual(stderr.count("ZFSU-INPUT-ACK|"), 1)

    def test_terminal_mode_no_markers(self):
        got, stderr = self._ask("/tank/key", env=False)
        self.assertEqual(got, "/tank/key")
        self.assertEqual(stderr, "")

    def test_uuids_differ_between_calls(self):
        with patch.dict(os.environ, {"ZFSUTILITIES_INPUT_HOLD": "Y"}):
            stderr = _StderrCapture()
            with patch("sys.stderr", stderr), patch("builtins.input", return_value="x"):
                ih.ask_line("A?")
                ih.ask_line("B?")
        ids = {
            line.split("|", 2)[1]
            for line in stderr.getvalue().splitlines()
            if line.startswith("ZFSU-INPUT-REQ|")
        }
        self.assertEqual(len(ids), 2)


if __name__ == "__main__":
    unittest.main()

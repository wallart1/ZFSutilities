"""Tests for input_requests.py — the numbered input-hold registry."""

import os
import sys
import unittest
from unittest.mock import MagicMock

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from input_requests import (
    InputRequestRegistry,
    parse_user_input,
    sole_live_runner,
)


def _fake_runner(label="Backup", running=False, step_active=False):
    runner = MagicMock()
    runner.label = label
    runner.running = running
    runner.step_active = step_active
    return runner


class TestNumbering(unittest.TestCase):
    """Numbers are monotonic and never reused within a session."""

    def test_numbers_start_at_one_and_increment(self):
        registry = InputRequestRegistry()
        first = registry.register(_fake_runner(), "u1", "First?")
        second = registry.register(_fake_runner(), "u2", "Second?")
        self.assertEqual((first.number, second.number), (1, 2))

    def test_released_number_is_not_reused(self):
        registry = InputRequestRegistry()
        registry.register(_fake_runner(), "u1", "First?")
        second = registry.register(_fake_runner(), "u2", "Second?")
        registry.release_uuid("u1")
        third = registry.register(_fake_runner(), "u3", "Third?")
        self.assertEqual(third.number, 3)
        self.assertEqual(second.number, 2)

    def test_rerequest_same_uuid_updates_in_place(self):
        registry = InputRequestRegistry()
        runner_a = _fake_runner("Restore")
        runner_b = _fake_runner("Restore")
        request = registry.register(runner_a, "u1", "Proceed?")
        again = registry.register(runner_b, "u1", "Proceed? (re-asked)")
        self.assertIs(request, again)
        self.assertEqual(again.number, 1)
        self.assertEqual(again.prompt, "Proceed? (re-asked)")
        self.assertIs(again.runner, runner_b)
        self.assertEqual(registry.outstanding(), [again])


class TestRelease(unittest.TestCase):
    """Releasing removes the request and reports what was released."""

    def test_release_uuid(self):
        registry = InputRequestRegistry()
        request = registry.register(_fake_runner(), "u1", "Proceed?")
        released = registry.release_uuid("u1")
        self.assertIs(released, request)
        self.assertIsNone(registry.by_uuid("u1"))
        self.assertIsNone(registry.by_number(1))

    def test_release_unknown_uuid_is_none(self):
        registry = InputRequestRegistry()
        self.assertIsNone(registry.release_uuid("nope"))

    def test_release_runner_only_touches_that_runner(self):
        registry = InputRequestRegistry()
        runner_a = _fake_runner("Backup")
        runner_b = _fake_runner("Restore")
        registry.register(runner_a, "u1", "One?")
        registry.register(runner_b, "u2", "Two?")
        registry.register(runner_a, "u3", "Three?")
        released = registry.release_runner(runner_a)
        self.assertEqual([r.uuid for r in released], ["u1", "u3"])
        self.assertEqual([r.uuid for r in registry.outstanding()], ["u2"])


class TestSoleOutstanding(unittest.TestCase):
    """sole_outstanding() is exact: one request or nothing."""

    def test_none_when_empty(self):
        self.assertIsNone(InputRequestRegistry().sole_outstanding())

    def test_request_when_exactly_one(self):
        registry = InputRequestRegistry()
        request = registry.register(_fake_runner(), "u1", "Proceed?")
        self.assertIs(registry.sole_outstanding(), request)

    def test_none_when_two_or_more(self):
        registry = InputRequestRegistry()
        registry.register(_fake_runner(), "u1", "One?")
        registry.register(_fake_runner(), "u2", "Two?")
        self.assertIsNone(registry.sole_outstanding())


class TestParseUserInput(unittest.TestCase):
    """Operator syntax: 'N answer' routes to message N."""

    def test_number_with_answer(self):
        self.assertEqual(parse_user_input("3 y"), (3, "y"))

    def test_number_with_multiword_answer(self):
        self.assertEqual(parse_user_input("12 a b c"), (12, "a b c"))

    def test_number_alone_means_empty_answer(self):
        self.assertEqual(parse_user_input("3"), (3, ""))

    def test_number_with_trailing_space_is_empty_answer(self):
        self.assertEqual(parse_user_input("3 "), (3, ""))

    def test_leading_whitespace_tolerated(self):
        self.assertEqual(parse_user_input("  7 yes"), (7, "yes"))

    def test_bare_text(self):
        self.assertEqual(parse_user_input("y"), (None, "y"))

    def test_digits_glued_to_text_are_bare_text(self):
        # "3y" cannot be split reliably; it is treated as bare text.
        self.assertEqual(parse_user_input("3y"), (None, "3y"))


class TestSoleLiveRunner(unittest.TestCase):
    """Bare-text backstop: the single runner with a live step, or nothing."""

    def test_none_when_nothing_live(self):
        runners = [_fake_runner(running=True), _fake_runner(running=True)]
        self.assertIsNone(sole_live_runner(runners))

    def test_runner_when_exactly_one_live(self):
        live = _fake_runner(running=True, step_active=True)
        idle = _fake_runner(running=True)
        self.assertIs(sole_live_runner([idle, live]), live)

    def test_none_when_two_live(self):
        # Two live tasks are ambiguous: never resolve by priority order.
        a = _fake_runner(running=True, step_active=True)
        b = _fake_runner(running=True, step_active=True)
        self.assertIsNone(sole_live_runner([a, b]))

    def test_empty_list(self):
        self.assertIsNone(sole_live_runner([]))


class TestRowText(unittest.TestCase):
    """Held-message rows render number, task label, and prompt."""

    def test_row_text(self):
        registry = InputRequestRegistry()
        request = registry.register(_fake_runner("Restore"), "u1", "Proceed?")
        self.assertEqual(request.row_text(), "1  [Restore]  Proceed?")


if __name__ == "__main__":
    unittest.main()

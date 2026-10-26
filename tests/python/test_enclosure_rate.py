"""Tests for lib/enclosure_rate.py — CLI semantics, min-with, failure exits."""

import contextlib
import io
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
LIB_DIR = os.path.join(REPO_ROOT, "lib")
for _path in (PYTHON_SRC, LIB_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import enclosure_rate
from enclosure_inventory import EnclosureInfo
from test_support import capture_logs


def _enclosure(enclosure_id, pools):
    return EnclosureInfo(
        id=enclosure_id,
        kind="usb",
        location=f"usb2/2-{enclosure_id[:1]}",
        members=[f"sd{enclosure_id[:1]}"],
        pools=list(pools),
    )


class _FakeInventory:
    """Duck-typed EnclosureInventory serving fixed discovery results."""

    def __init__(self, enclosures):
        self._enclosures = enclosures

    def discover(self):
        return list(self._enclosures)


class _ExplodingInventory:
    """Inventory whose discovery fails, for the fail-open paths."""

    def discover(self):
        raise RuntimeError("scan died")


def _run_cli(*args, inventory=None, config=None):
    """Run main() in-process; return (exit code, stdout, stderr)."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = enclosure_rate.main(["enclosure_rate.py", *args], inventory=inventory, config=config)
    return code, stdout.getvalue(), stderr.getvalue()


class TestPoolOf(unittest.TestCase):
    """CLI target reduction: pool = first path component, snapshot ignored."""

    def test_pool_and_dataset_shapes(self):
        self.assertEqual(enclosure_rate.pool_of("tank"), "tank")
        self.assertEqual(enclosure_rate.pool_of("tank/data"), "tank")
        self.assertEqual(enclosure_rate.pool_of("tank/data@snap-1"), "tank")
        self.assertEqual(enclosure_rate.pool_of("tank@snap"), "tank")

    def test_shapes_without_a_pool_are_empty(self):
        self.assertEqual(enclosure_rate.pool_of("/tank"), "")
        self.assertEqual(enclosure_rate.pool_of("@snap"), "")
        self.assertEqual(enclosure_rate.pool_of(""), "")


class TestMinRate(unittest.TestCase):
    """min_rate compares numerically through the pacer grammar."""

    def test_returns_smallest_rate_string_unchanged(self):
        self.assertEqual(enclosure_rate.min_rate("100M", "50m"), "50m")
        self.assertEqual(enclosure_rate.min_rate("50m", "100M"), "50m")
        self.assertEqual(enclosure_rate.min_rate("1G", "500MiB", "1048576"), "1048576")

    def test_numeric_not_lexicographic(self):
        self.assertEqual(enclosure_rate.min_rate("9M", "10M"), "9M")
        self.assertEqual(enclosure_rate.min_rate("1000", "500M"), "1000")

    def test_empty_inputs_are_skipped_and_all_empty_is_unlimited(self):
        self.assertEqual(enclosure_rate.min_rate("", "100M"), "100M")
        self.assertEqual(enclosure_rate.min_rate("", "", ""), "")

    def test_non_grammar_rate_raises(self):
        with self.assertRaises(ValueError):
            enclosure_rate.min_rate("100M", "abc")


class TestResolveEffectiveRate(unittest.TestCase):
    """Pure resolver: min(activity, caps of every touched enclosure)."""

    def test_touching_cap_wins_over_activity(self):
        fivebays = _enclosure("aaa", ["fivebays"])
        caps = {"aaa": {"name": "", "max_rate": "60M"}}
        result = enclosure_rate.resolve_effective_rate(["fivebays"], "100M", [fivebays], caps)
        self.assertEqual(result, "60M")

    def test_lower_cap_wins_across_enclosures(self):
        fivebays = _enclosure("aaa", ["fivebays"])
        threeamigos = _enclosure("bbb", ["fivebays", "offsite"])
        caps = {
            "aaa": {"max_rate": "80M"},
            "bbb": {"max_rate": "30M"},
        }
        result = enclosure_rate.resolve_effective_rate(
            ["fivebays"], "100M", [fivebays, threeamigos], caps
        )
        self.assertEqual(result, "30M")

    def test_untouched_enclosure_is_ignored(self):
        fivebays = _enclosure("aaa", ["fivebays"])
        other = _enclosure("bbb", ["offsite"])
        caps = {"bbb": {"max_rate": "10M"}}
        result = enclosure_rate.resolve_effective_rate(
            ["fivebays"], "100M", [fivebays, other], caps
        )
        self.assertEqual(result, "100M")

    def test_any_pool_of_a_multi_pool_transfer_pulls_in_its_enclosure(self):
        # Destination pool spans another enclosure: its cap applies too.
        fivebays = _enclosure("aaa", ["fivebays"])
        offsite_box = _enclosure("bbb", ["offsite"])
        caps = {"bbb": {"max_rate": "40M"}}
        result = enclosure_rate.resolve_effective_rate(
            ["fivebays", "offsite"], "100M", [fivebays, offsite_box], caps
        )
        self.assertEqual(result, "40M")

    def test_uncapped_or_unconfigured_enclosure_contributes_nothing(self):
        fivebays = _enclosure("aaa", ["fivebays"])
        empty_cap = _enclosure("bbb", ["fivebays"])
        caps = {"aaa": {"max_rate": ""}, "notanid": {"max_rate": "5M"}}
        result = enclosure_rate.resolve_effective_rate(
            ["fivebays"], "100M", [fivebays, empty_cap], caps
        )
        self.assertEqual(result, "100M")

    def test_no_constraints_is_unlimited(self):
        fivebays = _enclosure("aaa", ["fivebays"])
        self.assertEqual(
            enclosure_rate.resolve_effective_rate(["fivebays"], "", [fivebays], {}), ""
        )
        self.assertEqual(
            enclosure_rate.resolve_effective_rate(["x"], "", [], {"a": {"max_rate": "1M"}}), ""
        )

    def test_non_dict_cap_entry_is_ignored(self):
        fivebays = _enclosure("aaa", ["fivebays"])
        result = enclosure_rate.resolve_effective_rate(
            ["fivebays"], "100M", [fivebays], {"aaa": "60M"}
        )
        self.assertEqual(result, "100M")

    def test_non_grammar_cap_raises(self):
        fivebays = _enclosure("aaa", ["fivebays"])
        with self.assertRaises(ValueError):
            enclosure_rate.resolve_effective_rate(
                ["fivebays"], "", [fivebays], {"aaa": {"max_rate": "fast"}}
            )


class TestCliSemantics(unittest.TestCase):
    """main() exit codes and stdout contract with injected fixtures."""

    def _config(self, **by_id):
        return {"enclosures": by_id}

    def test_prints_cap_rate_and_exits_zero(self):
        inventory = _FakeInventory([_enclosure("aaa", ["fivebays"])])
        code, out, err = _run_cli(
            "--min-with",
            "100M",
            "fivebays/vm-disk",
            inventory=inventory,
            config=self._config(aaa={"name": "fivebays", "max_rate": "60M"}),
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, "60M\n")
        self.assertEqual(err, "")

    def test_dataset_and_snapshot_arguments_reduce_to_pools(self):
        inventory = _FakeInventory([_enclosure("aaa", ["fivebays"])])
        code, out, _ = _run_cli(
            "--min-with",
            "100M",
            "fivebays/vm-disk@auto-2026",
            inventory=inventory,
            config=self._config(aaa={"max_rate": "60M"}),
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, "60M\n")

    def test_unlimited_prints_empty_line_and_exits_zero(self):
        code, out, _ = _run_cli("tank", inventory=_FakeInventory([]), config=self._config())
        self.assertEqual(code, 0)
        self.assertEqual(out, "\n")

    def test_min_with_alone_echoes_through(self):
        code, out, _ = _run_cli(
            "--min-with", "100M", "tank", inventory=_FakeInventory([]), config=self._config()
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, "100M\n")

    def test_empty_cap_means_unlimited_not_zero(self):
        inventory = _FakeInventory([_enclosure("aaa", ["tank"])])
        code, out, _ = _run_cli(
            "--min-with",
            "100M",
            "tank",
            inventory=inventory,
            config=self._config(aaa={"max_rate": ""}),
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, "100M\n")

    def test_duplicate_pools_resolve_once(self):
        calls = []
        real = enclosure_rate.resolve_effective_rate

        def recording(*args, **kwargs):
            calls.append(args[0])
            return real(*args, **kwargs)

        inventory = _FakeInventory([])
        with patch.object(enclosure_rate, "resolve_effective_rate", side_effect=recording):
            code, _, _ = _run_cli(
                "tank", "tank/data", "tank@snap", inventory=inventory, config=self._config()
            )
        self.assertEqual(code, 0)
        self.assertEqual(calls, [["tank"]])

    def test_usage_errors_exit_two_without_discovery(self):
        exploding = _ExplodingInventory()  # would fail the test if consulted
        self.assertEqual(_run_cli(inventory=exploding)[0], 2)
        code, _, err = _run_cli("--min-with", inventory=exploding)
        self.assertEqual(code, 2)
        self.assertIn("usage", err)

    def test_non_grammar_min_with_is_a_usage_error(self):
        code, _, err = _run_cli("--min-with", "bogus", "tank", inventory=_ExplodingInventory())
        self.assertEqual(code, 2)
        self.assertIn("rate must start with digits", err)

    def test_unknown_option_is_rejected_as_target(self):
        code, _, err = _run_cli("--frobnicate", "tank", inventory=_FakeInventory([]), config={})
        self.assertEqual(code, 2)
        self.assertIn("invalid target", err)

    def test_resolution_failure_exits_one_with_no_stdout(self):
        code, out, err = _run_cli(
            "--min-with", "100M", "tank", inventory=_ExplodingInventory(), config={}
        )
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("rate resolution failed", err)

    def test_non_grammar_cap_exits_one(self):
        inventory = _FakeInventory([_enclosure("aaa", ["tank"])])
        code, out, err = _run_cli(
            "tank", inventory=inventory, config=self._config(aaa={"max_rate": "60X"})
        )
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("invalid rate suffix", err)


class TestEffectiveRateFailOpen(unittest.TestCase):
    """effective_rate() applies the campaign fail-open policy in-process."""

    def test_returns_activity_rate_and_logs_warn_on_failure(self):
        with capture_logs() as logs:
            result = enclosure_rate.effective_rate(
                ["tank"], "100M", inventory=_ExplodingInventory(), config={}
            )
        self.assertEqual(result, "100M")
        self.assertTrue(any("enclosure rate resolution failed" in msg for msg in logs))

    def test_failure_with_no_activity_limit_is_unlimited(self):
        result = enclosure_rate.effective_rate(
            ["tank"], "", inventory=_ExplodingInventory(), config={}
        )
        self.assertEqual(result, "")

    def test_success_path_resolves_like_the_pure_resolver(self):
        fivebays = _enclosure("aaa", ["fivebays"])
        result = enclosure_rate.effective_rate(
            ["fivebays"],
            "100M",
            inventory=_FakeInventory([fivebays]),
            config={"enclosures": {"aaa": {"max_rate": "60M"}}},
        )
        self.assertEqual(result, "60M")


class TestSubprocessCli(unittest.TestCase):
    """Real-interpreter entrypoint: usage errors need no fixtures."""

    def test_no_args_prints_usage_and_exits_two(self):
        result = subprocess.run(
            [sys.executable, os.path.join(LIB_DIR, "enclosure_rate.py")],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage", result.stderr)

    def test_garbage_min_with_exits_two(self):
        result = subprocess.run(
            [
                sys.executable,
                os.path.join(LIB_DIR, "enclosure_rate.py"),
                "--min-with",
                "not-a-rate",
                "tank",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()

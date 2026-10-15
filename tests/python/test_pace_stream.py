"""Tests for lib/pace_stream.py, the transfer-rate pacer.

Unit tests use injectable clocks (the module's _monotonic/_sleep hooks) so
pacing arithmetic is verified deterministically; CLI tests run the script as
a subprocess with timeouts. Real sleeps are kept at ~0.1s scale, following
the test_log_index timing precedent.
"""

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PACER_PATH = REPO_ROOT / "lib" / "pace_stream.py"


def load_pacer():
    spec = importlib.util.spec_from_file_location("pace_stream", PACER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeClock:
    """Injectable clock: sleep advances time, stalls advance it explicitly."""

    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, duration):
        self.sleeps.append(duration)
        self.now += duration

    def stall(self, seconds):
        self.now += seconds


class ChunkSrc:
    """File-like source yielding fixed chunks, with an optional stall."""

    def __init__(self, sizes, stall_before=None, stall_seconds=5.0):
        self.sizes = list(sizes)
        self.index = 0
        self.stall_before = stall_before
        self.stall_seconds = stall_seconds

    def read(self, _size):
        if self.index >= len(self.sizes):
            return b""
        if self.stall_before is not None and self.index == self.stall_before:
            self.clock.stall(self.stall_seconds)
        data = b"x" * self.sizes[self.index]
        self.index += 1
        return data


class NullSink:
    def __init__(self, clock, write_cost=0.001):
        self.clock = clock
        self.write_cost = write_cost
        self.bytes = 0

    def write(self, data):
        self.clock.now += self.write_cost
        self.bytes += len(data)

    def flush(self):
        pass


class TestParseRate(unittest.TestCase):
    def setUp(self):
        self.pacer = load_pacer()

    def test_valid_values(self):
        cases = {
            "100M": 100 * 1024**2,
            "500KiB": 500 * 1024,
            "4096": 4096,
            "10m": 10 * 1024**2,
            "1Gi": 1024**3,
            "2GB": 2 * 1024**3,
            "3tib": 3 * 1024**4,
            "7K": 7 * 1024,
        }
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(self.pacer.parse_rate(text), want)

    def test_invalid_values(self):
        for text in ("", "M100", "100X", "1.5M", "-5M", "5Q", "100MBx"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    self.pacer.parse_rate(text)

    def test_chunk_size_clamps(self):
        self.assertEqual(self.pacer.chunk_size_for(1024), 64 * 1024)
        self.assertEqual(self.pacer.chunk_size_for(100 * 1024**2), 4 * 1024**2)
        self.assertEqual(self.pacer.chunk_size_for(8 * 1024**3), 16 * 1024**2)


class TestPacedCopy(unittest.TestCase):
    def setUp(self):
        self.pacer = load_pacer()

    def _run(self, sizes, stall_before=None):
        clock = FakeClock()
        module = self.pacer
        module._monotonic = clock.monotonic
        module._sleep = clock.sleep
        rate = 100 * 1024**2  # 100 MiB/s -> 4 MiB chunks, ~0.0419s budget
        chunk = module.chunk_size_for(rate)
        self.assertEqual(sizes, [chunk] * len(sizes))
        src = ChunkSrc(sizes, stall_before=stall_before)
        src.clock = clock
        sink = NullSink(clock)
        module.paced_copy(src, sink, rate)
        return clock, sink

    def test_smooth_stream_sleeps_each_chunk(self):
        clock, sink = self._run([4 * 1024**2] * 3)
        budget = 4 * 1024**2 / (100 * 1024**2)
        self.assertEqual(sink.bytes, 3 * 4 * 1024**2)
        self.assertEqual(len(clock.sleeps), 3)
        for duration in clock.sleeps:
            self.assertGreater(duration, budget * 0.9)

    def test_stall_forfeits_its_budget(self):
        # A 5s stall on chunk 2 must not buy a later burst: the deficit is
        # forfeited, so chunk 3 still sleeps its full budget. Catch-up
        # semantics (the pv -L behavior) would sleep ~0 there.
        clock, sink = self._run([4 * 1024**2] * 3, stall_before=1)
        budget = 4 * 1024**2 / (100 * 1024**2)
        self.assertEqual(sink.bytes, 3 * 4 * 1024**2)
        self.assertEqual(len(clock.sleeps), 2)  # chunk 2 spent 5s: no sleep
        self.assertGreater(clock.sleeps[1], budget * 0.9)


class TestCli(unittest.TestCase):
    def _run_cli(self, args, stdin_data=None, timeout=10):
        return subprocess.run(
            [sys.executable, str(PACER_PATH)] + args,
            input=stdin_data,
            capture_output=True,
            timeout=timeout,
            check=False,
        )

    def test_file_passthrough_is_byte_identical(self):
        data = os.urandom(256 * 1024)
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "src")
            with open(src, "wb") as handle:
                handle.write(data)
            result = self._run_cli(["1G", "--", src])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, data)

    def test_stdin_passthrough_is_byte_identical(self):
        data = os.urandom(128 * 1024)
        result = self._run_cli(["1G"], stdin_data=data)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, data)

    def test_short_final_chunk(self):
        data = os.urandom(100 * 1024 + 123)
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "src")
            with open(src, "wb") as handle:
                handle.write(data)
            result = self._run_cli(["1G", "--", src])
        self.assertEqual(result.stdout, data)

    def test_bad_rate_exits_2(self):
        result = self._run_cli(["wat"])
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"rate", result.stderr)

    def test_missing_file_exits_1(self):
        result = self._run_cli(["100M", "--", "/nonexistent/pace-stream-nope"])
        self.assertEqual(result.returncode, 1)

    def test_rate_bounds_elapsed_time(self):
        # 256 KiB at 2 MiB/s paces to ~0.125s of sleep; keep bounds generous
        # so scheduler noise cannot flake the suite.
        import time as time_module

        data = os.urandom(256 * 1024)
        started = time_module.monotonic()
        result = self._run_cli(["2M"], stdin_data=data, timeout=15)
        elapsed = time_module.monotonic() - started
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, data)
        self.assertGreaterEqual(elapsed, 0.1)
        self.assertLess(elapsed, 5.0)

    def test_sigpipe_exits_141(self):
        script = (
            "set -o pipefail; "
            f"{sys.executable} '{PACER_PATH}' 100M /dev/zero"
            " | head -c 65536 > /dev/null"
        )
        result = subprocess.run(
            ["bash", "-c", script], capture_output=True, timeout=15, check=False
        )
        self.assertEqual(result.returncode, 141)


if __name__ == "__main__":
    unittest.main()

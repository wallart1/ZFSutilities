"""Realized-window check for the Performance page's rolling charts.

Spawns ``rolling_realized_check.py`` as a child process and asserts it
passed.  The child builds the real Performance page (GTK 3) in a realized
window, drives the rolling charts across a wide window and a simulated
sampling stall, and locks the geometry the user judges: the shared
doubled chart height, the shared X-tick grammar under both renderers,
and the post-stall re-baseline.  The child-process boundary keeps the
pytest interpreter's mock-bound GUI module caches and the matplotlib
backend selection untouched for the other suites.

The child needs a display, and it must be one it made itself: the check
starts a private Xvfb and never touches the ambient display (a realized
window flashing on the operator's desktop mid-suite is the leak this
fences), skipping when no private display is possible.  The suite is
listed in tests/requirements.manifest (capability ``gi``).
"""

import os
import subprocess
import sys
import unittest

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))

from test_support import requires_gi

pytestmark = requires_gi

_CHECK_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "rolling_realized_check.py"
)
_SKIP_RC = 3
_TIMEOUT_SECONDS = 120


class TestRollingChartsRealized(unittest.TestCase):
    def _run_check(self, renderer=None):
        env = dict(os.environ)
        if renderer is not None:
            env["REALIZED_CHART_RENDERER"] = renderer
        return subprocess.run(
            [sys.executable, _CHECK_SCRIPT],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            cwd=REPO_ROOT,
            check=False,
            env=env,
        )

    def test_realized_charts_under_both_renderers(self):
        """The rolling-chart locks must hold for the matplotlib renderer
        and the Cairo fallback alike: the shared doubled height realized
        in the page, the shared X-tick grammar (five ticks on a wide
        window, thinned on a narrow one), and the post-stall re-baseline
        (no rate point across the stall, the size gauge continuing)."""
        for renderer in ("default", "cairo"):
            with self.subTest(renderer=renderer):
                proc = self._run_check(renderer=None if renderer == "default" else renderer)
                output = proc.stdout + proc.stderr
                if proc.returncode == _SKIP_RC:
                    self.skipTest(output.strip() or "realized check skipped (no display)")
                self.assertEqual(proc.returncode, 0, f"realized check failed:\n{output}")
                self.assertIn("ROLLING-REALIZED-OK", proc.stdout)
                self.assertIn("REALIZED-RENDERER: ", proc.stdout)
                for pass_line in (
                    "PASS geometry: every chart realizes the shared doubled height",
                    "PASS x ticks: five on a wide window, thinned on a narrow one",
                    "PASS stall: rate point dropped, gauge kept, baseline resumed",
                ):
                    self.assertIn(pass_line, proc.stdout)


if __name__ == "__main__":
    unittest.main()

"""Realized-window scroll check for the Alignment view.

Spawns ``alignment_realized_check.py`` as a child process and asserts it
passed.  The child builds the real Performance page (GTK 3) in a realized
window and drives the GTK main loop — the level at which the
jump-on-refresh defect was measured — while the child-process boundary
keeps the pytest interpreter's mock-bound GUI module caches and the
matplotlib backend selection untouched for the other suites.

The child needs a display, and it must be one it made itself: the check
starts a private Xvfb and never touches the ambient display (a realized
window flashing on the operator's desktop mid-suite is the leak this
fences), skipping when no private display is possible.  The suite is
listed in tests/requirements.manifest (capability ``gi``).
"""

import os
import re
import subprocess
import sys
import unittest

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))

from test_support import requires_gi

pytestmark = requires_gi

_CHECK_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "alignment_realized_check.py"
)
_SKIP_RC = 3
_TIMEOUT_SECONDS = 120


class TestAlignmentScrollRealized(unittest.TestCase):
    def _run_check(self, renderer=None, extra_env=None):
        env = dict(os.environ)
        if renderer is not None:
            env["REALIZED_CHART_RENDERER"] = renderer
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [sys.executable, _CHECK_SCRIPT],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            cwd=REPO_ROOT,
            check=False,
            env=env,
        )

    def test_realized_window_scroll_check(self):
        proc = self._run_check()
        output = proc.stdout + proc.stderr
        if proc.returncode == _SKIP_RC:
            self.skipTest(output.strip() or "realized check skipped (no display)")
        self.assertEqual(proc.returncode, 0, f"realized check failed:\n{output}")
        self.assertIn("ALIGNMENT-REALIZED-OK", proc.stdout)
        self.assertIn("PASS findings change", proc.stdout)
        self.assertIn("PASS per-pool failure", proc.stdout)

    def test_realized_geometry_check_under_both_renderers(self):
        """The Performance-page geometry locks must hold for the matplotlib
        ladder and the Cairo fallback alike: fixed 20-row table windows,
        per-table horizontal scrollbars with the page itself never
        scrolling sideways, honest far-right columns, and the ladder
        keeping its content-derived minimum (the mid-width clamp defect
        was reproduced with the Cairo renderer)."""
        expected = {
            "matplotlib": "REALIZED-RENDERER: MatplotlibBlocksizeLadder",
            "cairo": "REALIZED-RENDERER: BlocksizeLadder",
        }
        for renderer, renderer_line in expected.items():
            with self.subTest(renderer=renderer):
                proc = self._run_check(renderer=renderer)
                output = proc.stdout + proc.stderr
                if proc.returncode == _SKIP_RC:
                    self.skipTest(output.strip() or "realized check skipped (no display)")
                self.assertEqual(proc.returncode, 0, f"realized check failed:\n{output}")
                self.assertIn(renderer_line, proc.stdout)
                for pass_line in (
                    "PASS geometry: 20-row tables",
                    "PASS geometry: ladder keeps its content minimum",
                    "PASS geometry: empty tables keep their 20-row windows",
                ):
                    self.assertIn(pass_line, proc.stdout)

    def test_realized_check_is_immune_to_ambient_font_scaling(self):
        """A private Xvfb fences the display but not the inherited
        environment: GDK scaling variables (and, over the ambient session
        bus, the desktop's text-scaling-factor) change the font metrics
        the geometry findings measure.  The check scrubs those channels
        before Gtk binds, so a hostile environment must not change its
        verdict."""
        proc = self._run_check(extra_env={"GDK_DPI_SCALE": "2"})
        output = proc.stdout + proc.stderr
        if proc.returncode == _SKIP_RC:
            self.skipTest(output.strip() or "realized check skipped (no display)")
        self.assertEqual(proc.returncode, 0, f"realized check failed:\n{output}")
        self.assertIn("ALIGNMENT-REALIZED-OK", proc.stdout)

    def test_realized_check_never_uses_the_ambient_display(self):
        proc = self._run_check()
        output = proc.stdout + proc.stderr
        if proc.returncode == _SKIP_RC:
            self.skipTest(output.strip() or "realized check skipped (no display)")
        self.assertEqual(proc.returncode, 0, f"realized check failed:\n{output}")
        # The check must name the display it drove, and that display must
        # be a private one: when an ambient DISPLAY is inherited, the
        # realized window may never land on it.
        match = re.search(r"^REALIZED-DISPLAY: (\S+)", proc.stdout, re.MULTILINE)
        self.assertIsNotNone(match, f"check did not name its display:\n{output}")
        used = match.group(1)
        self.assertTrue(used.startswith(":"), f"not a display name: {used}")
        ambient = os.environ.get("DISPLAY", "")
        if ambient:
            self.assertNotEqual(
                used,
                ambient,
                f"realized check drew on the ambient display ({ambient}) instead of a private Xvfb",
            )


if __name__ == "__main__":
    unittest.main()

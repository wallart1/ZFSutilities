"""Realized-window scroll check for the Alignment view.

Spawns ``alignment_realized_check.py`` as a child process and asserts it
passed.  The child builds the real Performance page (GTK 3) in a
realized window and drives the GTK main loop — the level at which the
jump-on-refresh defect was measured — while the child-process boundary
keeps the pytest interpreter's mock-bound GUI module caches and the
matplotlib backend selection untouched for the other suites.

The child needs a display: it starts a private Xvfb first (so no window
flashes on the operator's desktop) and falls back to the ambient display
when Xvfb cannot start, skipping when neither is possible.
The suite is listed in tests/requirements.manifest (capability ``gi``).
"""

import os
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
    def test_realized_window_scroll_check(self):
        proc = subprocess.run(
            [sys.executable, _CHECK_SCRIPT],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            cwd=REPO_ROOT,
            check=False,
        )
        output = proc.stdout + proc.stderr
        if proc.returncode == _SKIP_RC:
            self.skipTest(output.strip() or "realized check skipped (no display)")
        self.assertEqual(proc.returncode, 0, f"realized check failed:\n{output}")
        self.assertIn("ALIGNMENT-REALIZED-OK", proc.stdout)
        # Names which display was used (private Xvfb vs ambient fallback).
        self.assertIn("REALIZED-DISPLAY:", proc.stdout)
        self.assertIn("PASS findings change", proc.stdout)
        self.assertIn("PASS per-pool failure", proc.stdout)


if __name__ == "__main__":
    unittest.main()

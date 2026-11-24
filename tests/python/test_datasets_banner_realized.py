"""Realized-window check for the Datasets page mount-order warning banner.

Spawns ``datasets_banner_realized_check.py`` as a child process and asserts
it passed.  The child builds the real Datasets page (GTK 3) inside a
realized window and drives the banner contract end to end — hidden through
``show_all``, hidden when the unreachable-mount detector is clean, visible
with the affected count and the Dashboard pointer when it finds mounts,
and hidden again once the detector is clean — while the child-process
boundary keeps the pytest interpreter's mock-bound GUI module caches
untouched for the other suites.

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
    os.path.dirname(os.path.abspath(__file__)), "datasets_banner_realized_check.py"
)
_SKIP_RC = 3
_TIMEOUT_SECONDS = 120


class TestDatasetsBannerRealized(unittest.TestCase):
    def _run_check(self, extra_env=None):
        env = dict(os.environ)
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

    def test_realized_banner_check(self):
        proc = self._run_check()
        output = proc.stdout + proc.stderr
        if proc.returncode == _SKIP_RC:
            self.skipTest(output.strip() or "realized check skipped (no display)")
        self.assertEqual(proc.returncode, 0, f"realized check failed:\n{output}")
        self.assertIn("DATASETS-BANNER-REALIZED-OK", proc.stdout)
        self.assertIn("PASS banner: hidden when clean", proc.stdout)
        self.assertIn("PASS banner: hides again", proc.stdout)

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

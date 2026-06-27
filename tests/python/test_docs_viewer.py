"""Tests for docs_viewer.py — standalone documentation viewer launcher."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

from test_support import mock_gtk, REPO_ROOT


PYTHON_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")


class _ExecvpCalled(Exception):
    """Raised by the mocked os.execvp to stop execution in pkexec tests."""

    def __init__(self, program, args):
        self.program = program
        self.exec_args = args
        super().__init__(f"os.execvp called: {program} {args}")


class TestDocsViewerMain(unittest.TestCase):
    """Verify docs_viewer.main() launches the documentation viewer window."""

    def test_main_creates_window_and_starts_gtk_main(self):
        with mock_gtk() as gtk_mock:
            # DocsViewerWindow is imported at module load time, so reload after
            # mock_gtk has installed the fake GTK modules.
            if "docs_viewer" in sys.modules:
                del sys.modules["docs_viewer"]
            import docs_viewer as dv

            window = MagicMock()
            with patch.object(dv, "DocsViewerWindow", return_value=window) as mock_win, \
                 patch.object(dv.os, "geteuid", return_value=0):
                dv.main()

            mock_win.assert_called_once_with(PYTHON_SRC)
            window.connect.assert_called_once_with("destroy", gtk_mock.main_quit)
            window.show_all.assert_called_once()
            gtk_mock.main.assert_called_once()

    def test_main_pkexec_when_non_root(self):
        with mock_gtk():
            if "docs_viewer" in sys.modules:
                del sys.modules["docs_viewer"]
            import docs_viewer as dv

            def fake_execvp(program, args):
                raise _ExecvpCalled(program, args)

            test_env = {
                "DISPLAY": ":1",
                "XAUTHORITY": "/home/test/.Xauthority",
                "WAYLAND_DISPLAY": "wayland-0",
            }
            with patch.object(dv.os, "geteuid", return_value=1000), \
                 patch.object(dv.os, "execvp", side_effect=fake_execvp) as mock_execvp, \
                 patch.dict(dv.os.environ, test_env, clear=False):
                with self.assertRaises(_ExecvpCalled) as ctx:
                    dv.main()

            mock_execvp.assert_called_once()
            self.assertEqual(ctx.exception.program, "pkexec")
            args = ctx.exception.exec_args
            self.assertEqual(args[0], "pkexec")
            self.assertEqual(args[1], "env")
            self.assertIn("DISPLAY=:1", args)
            self.assertIn("XAUTHORITY=/home/test/.Xauthority", args)
            self.assertIn("WAYLAND_DISPLAY=wayland-0", args)
            self.assertIn(sys.executable, args)
            self.assertIn(sys.argv[0], args)

    def test_main_pkexec_omits_optional_env_vars(self):
        with mock_gtk():
            if "docs_viewer" in sys.modules:
                del sys.modules["docs_viewer"]
            import docs_viewer as dv

            def fake_execvp(program, args):
                raise _ExecvpCalled(program, args)

            with patch.object(dv.os, "geteuid", return_value=1000), \
                 patch.object(dv.os, "execvp", side_effect=fake_execvp), \
                 patch.dict(dv.os.environ, {"DISPLAY": ":0"}, clear=True):
                with self.assertRaises(_ExecvpCalled) as ctx:
                    dv.main()

            args = ctx.exception.exec_args
            self.assertIn("DISPLAY=:0", args)
            xauth_args = [a for a in args if a.startswith("XAUTHORITY=")]
            wayland_args = [a for a in args if a.startswith("WAYLAND_DISPLAY=")]
            self.assertEqual(xauth_args, [])
            self.assertEqual(wayland_args, [])


if __name__ == "__main__":
    unittest.main()

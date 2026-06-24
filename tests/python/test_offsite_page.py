"""Tests for offsite_page.py — offsite pool detection and config helpers."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import mock_gtk, mock_subprocess, temp_config_dir


class _FakeComboBoxText:
    def __getattr__(self, _name):
        return lambda *args, **kwargs: None


def _import_offsite_page():
    """Import offsite_page under a fresh mocked GTK context."""
    sys.modules.pop("offsite_page", None)
    with mock_gtk():
        import offsite_page
        return offsite_page


class TestDoDetectOffsitePool(unittest.TestCase):
    """do_detect_offsite_pool reads candidates from the pool registry."""

    def _make_app(self, pools):
        app = MagicMock()
        app.ctx = MagicMock()
        app.ctx.config = {"pools": pools}
        app.offsite_detected_label = MagicMock()
        return app

    def test_no_candidates_configured(self):
        op = _import_offsite_page()
        app = self._make_app([])

        result = op.do_detect_offsite_pool(app)

        self.assertIsNone(result)
        app.offsite_detected_label.set_text.assert_called_once_with(
            "(no candidates configured)"
        )

    def test_detects_online_candidate(self):
        op = _import_offsite_page()
        app = self._make_app([
            {"name": "z40tb", "offsite_candidate": True},
            {"name": "z22tb", "offsite_candidate": True},
        ])
        with mock_subprocess() as m:
            m.add_zpool_list([
                {"name": "z40tb", "health": "ONLINE"},
                {"name": "z22tb", "health": "OFFLINE"},
            ])
            result = op.do_detect_offsite_pool(app)

        self.assertEqual(result, "z40tb")
        app.offsite_detected_label.set_markup.assert_called_once()
        args = app.offsite_detected_label.set_markup.call_args[0]
        self.assertIn("z40tb", args[0])

    def test_all_candidates_offline(self):
        op = _import_offsite_page()
        app = self._make_app([
            {"name": "z40tb", "offsite_candidate": True},
        ])
        with mock_subprocess() as m:
            m.add_zpool_list([
                {"name": "z40tb", "health": "OFFLINE"},
            ])
            result = op.do_detect_offsite_pool(app)

        self.assertIsNone(result)
        app.offsite_detected_label.set_text.assert_called_once()
        args = app.offsite_detected_label.set_text.call_args[0]
        self.assertIn("none online", args[0])
        self.assertIn("z40tb", args[0])

    def test_refreshes_after_config_changes(self):
        """Detection reflects a pool registry that changed after page creation."""
        op = _import_offsite_page()
        app = self._make_app([])

        result = op.do_detect_offsite_pool(app)
        self.assertIsNone(result)
        app.offsite_detected_label.set_text.assert_called_once_with(
            "(no candidates configured)"
        )

        app.offsite_detected_label.reset_mock()
        app.ctx.config["pools"] = [
            {"name": "z40tb", "offsite_candidate": True},
        ]

        with mock_subprocess() as m:
            m.add_zpool_list([{"name": "z40tb", "health": "ONLINE"}])
            result = op.do_detect_offsite_pool(app)

        self.assertEqual(result, "z40tb")
        app.offsite_detected_label.set_markup.assert_called_once()
        args = app.offsite_detected_label.set_markup.call_args[0]
        self.assertIn("z40tb", args[0])


class TestCollectOffsiteConfig(unittest.TestCase):
    """collect_offsite_config uses candidates from the pool registry."""

    def _make_app(self, pools):
        app = MagicMock()
        app.ctx = MagicMock()
        app.ctx.config = {"pools": pools}
        app.offsite_var_widgets = {
            "applyholds": MagicMock(get_text=MagicMock(return_value="Y")),
            "doincrementals": MagicMock(get_text=MagicMock(return_value="N")),
        }
        store = MagicMock()
        store.__iter__ = lambda _s: iter([
            [True, "tank/src", "<offsite>/dst", "", ""],
        ])
        app.offsite_step_store = store
        return app

    def test_candidates_from_pool_registry(self):
        op = _import_offsite_page()
        op.Gtk.ComboBoxText = _FakeComboBoxText
        app = self._make_app([
            {"name": "tank", "offsite_candidate": False},
            {"name": "z40tb", "offsite_candidate": True},
            {"name": "z22tb", "offsite_candidate": True},
        ])

        cfg = op.collect_offsite_config(app)

        self.assertEqual(cfg["offsite_pools"], ["z40tb", "z22tb"])

    def test_no_candidates_empty_list(self):
        op = _import_offsite_page()
        op.Gtk.ComboBoxText = _FakeComboBoxText
        app = self._make_app([
            {"name": "tank", "offsite_candidate": False},
        ])

        cfg = op.collect_offsite_config(app)

        self.assertEqual(cfg["offsite_pools"], [])

    def test_steps_collected(self):
        op = _import_offsite_page()
        op.Gtk.ComboBoxText = _FakeComboBoxText
        app = self._make_app([])

        cfg = op.collect_offsite_config(app)

        self.assertEqual(len(cfg["steps"]), 1)
        self.assertEqual(cfg["steps"][0]["source"], "tank/src")
        self.assertEqual(cfg["steps"][0]["dest"], "<offsite>/dst")


class TestLoadOffsiteConfig(unittest.TestCase):
    """load_offsite_config refreshes detection from the pool registry."""

    def _make_app(self, pools):
        app = MagicMock()
        app.ctx = MagicMock()
        app.ctx.config = {"pools": pools}
        app.offsite_var_widgets = {
            "applyholds": MagicMock(),
        }
        store = MagicMock()
        store.__iter__ = lambda _s: iter([])
        app.offsite_step_store = store
        app.offsite_detected_label = MagicMock()
        return app

    def test_refreshes_detection_no_entry(self):
        op = _import_offsite_page()
        op.Gtk.ComboBoxText = _FakeComboBoxText
        app = self._make_app([])

        op.load_offsite_config(app, {"variables": {}, "steps": []})

        app.offsite_detected_label.set_text.assert_called_once_with(
            "(no candidates configured)"
        )

    def test_does_not_use_offsite_pools_entry(self):
        op = _import_offsite_page()
        op.Gtk.ComboBoxText = _FakeComboBoxText
        app = self._make_app([
            {"name": "z40tb", "offsite_candidate": True},
        ])

        with mock_subprocess() as m:
            m.add_zpool_list([
                {"name": "z40tb", "health": "ONLINE"},
            ])
            op.load_offsite_config(
                app,
                {
                    "variables": {},
                    "offsite_pools": ["z22tb"],
                    "steps": [],
                },
            )

        app.offsite_detected_label.set_markup.assert_called_once()
        args = app.offsite_detected_label.set_markup.call_args[0]
        self.assertIn("z40tb", args[0])


class TestOffsitePageFrames(unittest.TestCase):
    """Tests for Offsite page layout helpers."""

    @patch("offsite_page._do_generate_snap")
    @patch("offsite_page.do_detect_offsite_pool")
    def test_frames_use_bold_label_widgets(self, _mock_detect, _mock_gen):
        op = _import_offsite_page()
        op.Gtk.ComboBoxText = _FakeComboBoxText

        frames = [MagicMock() for _ in range(4)]
        expanders = [MagicMock() for _ in range(1)]
        op.Gtk.Frame.side_effect = frames
        op.Gtk.Expander.side_effect = expanders

        app = MagicMock()
        app.ctx = MagicMock()
        app.ctx.config = {"pools": []}
        app.config = {"pools": []}

        op.create_offsite_page(app, app.ctx)

        for frame in frames:
            frame.set_label.assert_not_called()
            frame.set_label_widget.assert_called_once()

        for expander in expanders:
            expander.set_label.assert_not_called()
            expander.set_label_widget.assert_called_once()

    @patch("offsite_page._do_generate_snap")
    @patch("offsite_page.do_detect_offsite_pool")
    def test_snapshot_frame_above_send_receive_steps(
        self, _mock_detect, _mock_gen
    ):
        """Snapshot frame is packed after Advanced and before Send/Receive Steps."""
        op = _import_offsite_page()
        op.Gtk.ComboBoxText = _FakeComboBoxText

        frames = [MagicMock() for _ in range(4)]
        expanders = [MagicMock() for _ in range(1)]
        op.Gtk.Frame.side_effect = frames
        op.Gtk.Expander.side_effect = expanders

        boxes = []
        op.Gtk.Box.side_effect = lambda *a, **k: (
            boxes.append(MagicMock()) or boxes[-1]
        )

        app = MagicMock()
        app.ctx = MagicMock()
        app.ctx.config = {"pools": []}
        app.config = {"pools": []}

        op.create_offsite_page(app, app.ctx)

        # The first Box created is the outer vertical container.
        outer_box = boxes[0]

        # Frame creation order: Offsite Pool, Dataset Selection, Snapshot,
        # Send/Receive Steps.
        pool_frame, _, snap_frame, sr_frame = frames
        adv_expander = expanders[0]

        packed = [call[0][0] for call in outer_box.pack_start.call_args_list]
        self.assertEqual(
            packed,
            [op.Gtk.Label.return_value, op.Gtk.Separator.return_value,
             pool_frame, adv_expander, snap_frame, sr_frame],
        )


class TestOffsiteRunDialog(unittest.TestCase):
    """Tests for the offsite run confirmation dialog."""

    def _make_app(self):
        app = MagicMock()
        app.backup_runner = MagicMock()
        app.backup_runner.running = False
        app.offsite_runner = MagicMock()
        app.offsite_runner.running = False
        app.restore_runner = MagicMock()
        app.restore_runner.running = False
        app._dry_run_active = False
        app.offsite_nextsnap_entry.get_text.return_value = "@offsite-2026-06-11T12:00-s"
        app.offsite_step_store = MagicMock(__iter__=lambda _s: iter([]))
        return app

    def test_generate_button_regenerates_snapshot_then_runs(self):
        op = _import_offsite_page()
        op.Gtk.ComboBoxText = _FakeComboBoxText

        dialog_mock = MagicMock()
        dialog_mock.run.side_effect = [
            op.Gtk.ResponseType.APPLY,
            op.Gtk.ResponseType.OK,
        ]

        app = self._make_app()
        with patch.object(op.Gtk, "MessageDialog", return_value=dialog_mock), \
             patch.object(op, "do_detect_offsite_pool", return_value="z40tb"), \
             patch.object(op, "_do_generate_snap") as mock_generate, \
             patch.object(op, "collect_offsite_config", return_value={
                 "steps": [],
                 "variables": {},
             }):
            op.on_offsite_run(app, app.ctx)

        mock_generate.assert_called_once_with(app)
        app.offsite_runner.prepare_session_log.assert_called_once()

    def test_cancel_button_does_not_start_runner(self):
        op = _import_offsite_page()
        op.Gtk.ComboBoxText = _FakeComboBoxText

        dialog_mock = MagicMock()
        dialog_mock.run.side_effect = [
            op.Gtk.ResponseType.CANCEL,
        ]

        app = self._make_app()
        with patch.object(op.Gtk, "MessageDialog", return_value=dialog_mock), \
             patch.object(op, "do_detect_offsite_pool", return_value="z40tb"), \
             patch.object(op, "_do_generate_snap") as mock_generate:
            op.on_offsite_run(app, app.ctx)

        mock_generate.assert_not_called()
        app.offsite_runner.prepare_session_log.assert_not_called()


if __name__ == "__main__":
    unittest.main()

"""Modal-dialog dimming: run_dialog/dimmed_modal state machine.

While a modal dialog is on screen every other toplevel window is dimmed to
``gui_helpers.MODAL_DIM_OPACITY`` and restored to its previous opacity when
the dialog closes (see test_modal_dim_wiring.py for the sweep that routes
every dialog display through these helpers). These tests drive the helpers
under ``mock_gtk`` with fake toplevel windows so the opacity traffic is
observable without a display or compositor.
"""

import os
import sys
from contextlib import contextmanager

import pytest

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import import_gui_fresh, mock_gtk


class _FakeWindow:
    """Toplevel/dialog stand-in recording opacity traffic and run() calls.

    Real dialogs are toplevels too, so one class plays both roles; windows
    that never run() simply keep ``run_calls`` at zero.
    """

    def __init__(self, opacity=1.0, response=-6):
        self.opacity = opacity
        self.set_calls = []
        self.run_calls = 0
        self.response = response

    def get_opacity(self):
        return self.opacity

    def set_opacity(self, value):
        self.set_calls.append(value)
        self.opacity = value

    def broken_set_opacity(self, value):
        raise RuntimeError("window destroyed while dimmed")

    def run(self):
        self.run_calls += 1
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@contextmanager
def _helper_with_toplevels(windows):
    """Yield gui_helpers bound to a mock_gtk listing *windows* as toplevels."""
    with mock_gtk(fresh=True) as gtk_mock:
        gtk_mock.Window.list_toplevels = staticmethod(lambda: list(windows))
        yield import_gui_fresh("gui_helpers")


def test_run_dialog_dims_and_restores_sibling_windows():
    main, docs, dialog = _FakeWindow(), _FakeWindow(), _FakeWindow(response=1)
    with _helper_with_toplevels([main, docs, dialog]) as gh:
        assert gh.run_dialog(dialog) == 1
        assert dialog.run_calls == 1
        assert main.set_calls == [gh.MODAL_DIM_OPACITY, 1.0]
        assert docs.set_calls == [gh.MODAL_DIM_OPACITY, 1.0]
        assert main.opacity == 1.0 and docs.opacity == 1.0


def test_dim_uses_the_constant_and_restores_prior_opacity():
    faded, dialog = _FakeWindow(opacity=0.8), _FakeWindow()
    with _helper_with_toplevels([faded, dialog]) as gh:
        assert gh.MODAL_DIM_OPACITY == 0.6
        gh.run_dialog(dialog)
        # Dimmed to the constant, restored to the window's OWN prior value.
        assert faded.set_calls == [0.6, 0.8]


def test_running_dialog_is_never_dimmed():
    dialog = _FakeWindow()
    with _helper_with_toplevels([dialog]) as gh:
        gh.run_dialog(dialog)
        assert dialog.set_calls == []


def test_nested_dialogs_restore_in_stack_order():
    main, d1, d2 = _FakeWindow(), _FakeWindow(), _FakeWindow()
    with _helper_with_toplevels([main, d1, d2]) as gh:
        gh._push_modal_dim(d1)
        assert main.set_calls == [gh.MODAL_DIM_OPACITY]
        assert d1.set_calls == []

        gh._push_modal_dim(d2)
        # The parent dialog is just another disabled window now.
        assert d1.set_calls == [gh.MODAL_DIM_OPACITY]
        assert main.set_calls == [gh.MODAL_DIM_OPACITY]  # prior kept, not re-set

        gh._pop_modal_dim(d2)
        assert d1.set_calls == [gh.MODAL_DIM_OPACITY, 1.0]
        assert main.opacity == gh.MODAL_DIM_OPACITY  # outer modal still open

        gh._pop_modal_dim(d1)
        assert main.set_calls == [gh.MODAL_DIM_OPACITY, 1.0]
        assert gh._modal_dim_stack == [] and gh._dim_priors == {}


def test_run_exception_still_restores_windows():
    main = _FakeWindow()
    dialog = _FakeWindow(response=RuntimeError("run exploded"))
    with _helper_with_toplevels([main, dialog]) as gh:
        with pytest.raises(RuntimeError):
            gh.run_dialog(dialog)
        assert main.opacity == 1.0
        assert gh._modal_dim_stack == [] and gh._dim_priors == {}


def test_dimmed_modal_context_restores_on_block_exit_and_error():
    main, dialog = _FakeWindow(), _FakeWindow()
    with _helper_with_toplevels([main, dialog]) as gh:
        with gh.dimmed_modal(dialog):
            assert main.opacity == gh.MODAL_DIM_OPACITY
        assert main.opacity == 1.0

        with pytest.raises(ValueError):
            with gh.dimmed_modal(dialog):
                raise ValueError("boom")
        assert main.opacity == 1.0
        assert gh._modal_dim_stack == [] and gh._dim_priors == {}


def test_unlistable_toplevels_degrade_to_passthrough():
    dialog = _FakeWindow(response=1)
    with mock_gtk(fresh=True) as gtk_mock:
        gh = import_gui_fresh("gui_helpers")
        # Stock mock: Gtk.Window has no list_toplevels class attribute, so
        # enumeration raises and the display path must pass through cleanly.
        assert not hasattr(type(gtk_mock.Window), "list_toplevels")
        assert gh.run_dialog(dialog) == 1
        assert gh._modal_dim_stack == [] and gh._dim_priors == {}


def test_destroyed_window_cannot_break_the_restore():
    healthy, doomed, dialog = _FakeWindow(), _FakeWindow(), _FakeWindow()
    doomed.set_opacity = doomed.broken_set_opacity
    with _helper_with_toplevels([healthy, doomed, dialog]) as gh:
        # _dim_window also fails on the doomed window, so only the healthy
        # one is recorded; the restore must complete either way.
        gh.run_dialog(dialog)
        assert healthy.opacity == 1.0
        assert doomed not in gh._dim_priors


def test_pop_of_unknown_dialog_is_a_noop():
    main, d1 = _FakeWindow(), _FakeWindow()
    with _helper_with_toplevels([main, d1]) as gh:
        gh._push_modal_dim(d1)
        gh._pop_modal_dim(_FakeWindow())  # stray pop must not undim early
        assert main.opacity == gh.MODAL_DIM_OPACITY
        gh._pop_modal_dim(d1)
        assert main.opacity == 1.0

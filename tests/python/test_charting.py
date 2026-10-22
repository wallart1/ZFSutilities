"""Tests for charting.py — shared vocabulary, backend probe, and renderers."""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import mock_gtk


def _charting():
    """Import charting bound to a fresh mock context (GUI-module rules)."""
    with mock_gtk(fresh=True):
        import charting

    return charting


def _fake_backend():
    """Build a matplotlib stand-in wired for per-artist assertions.

    Every artist creation goes through a side effect so each line/fill is a
    distinct object (a bare MagicMock return value cannot be unpacked as
    ``(line,) = ax.plot(...)``), and the FuncFormatter fake records the
    formatting callbacks so tick-label text can be asserted directly.
    """
    fig = MagicMock()
    ax = MagicMock()
    fig.add_subplot.return_value = ax
    lines = []
    fills = []
    canvas = MagicMock()

    def _plot(*args, **kwargs):
        line = MagicMock()
        lines.append(line)
        return [line]

    def _fill(*args, **kwargs):
        poly = MagicMock()
        fills.append(poly)
        return [poly]

    def _func_formatter(func):
        holder = SimpleNamespace(func=func)
        formatters.append(holder)
        return holder

    ax.plot.side_effect = _plot
    ax.fill.side_effect = _fill
    formatters = []
    backend = SimpleNamespace(
        Figure=MagicMock(return_value=fig),
        FigureCanvas=MagicMock(return_value=canvas),
        FuncFormatter=_func_formatter,
        Patch=MagicMock(),
    )
    return backend, fig, ax, canvas, lines, fills, formatters


class _FakeStyleContext:
    """Style context answering lookup_color with fixed theme colours."""

    def __init__(self, bg, fg):
        self._colors = {"theme_bg_color": bg, "theme_fg_color": fg}

    def lookup_color(self, name):
        if name not in self._colors:
            return False, None
        return True, SimpleNamespace(**dict(zip(("red", "green", "blue"), self._colors[name])))


class _FakeThemeWidget:
    def __init__(self, bg, fg):
        self._context = _FakeStyleContext(bg, fg)

    def get_style_context(self):
        return self._context


class TestThemePalette(unittest.TestCase):
    """The theme-following palette every renderer resolves."""

    DARK_BG = (0.16, 0.16, 0.18)
    DARK_FG = (0.88, 0.88, 0.88)

    def test_light_palette_matches_the_classic_vocabulary(self):
        charting = _charting()
        light = charting.LIGHT_PALETTE
        self.assertEqual(light.background, (1.0, 1.0, 1.0))
        self.assertEqual(light.series, tuple(charting.SERIES_COLORS))
        self.assertEqual(light.states["OK"], charting.LADDER_STATE_COLORS["OK"])

    def test_dark_theme_resolves_dark_palette(self):
        charting = _charting()
        widget = _FakeThemeWidget(self.DARK_BG, self.DARK_FG)
        palette = charting.chart_palette(widget)
        self.assertEqual(palette.background, self.DARK_BG)
        self.assertEqual(palette.foreground, self.DARK_FG)
        # Series colours are the bright variants, and every structural
        # colour is a blend between fg and bg (visible on the background).
        self.assertNotEqual(palette.series, charting.LIGHT_PALETTE.series)
        for color in (palette.grid, palette.spine, palette.reference, palette.muted):
            for channel, fg, bg in zip(color, self.DARK_FG, self.DARK_BG):
                self.assertGreaterEqual(channel, min(fg, bg))
                self.assertLessEqual(channel, max(fg, bg))
        # Ladder states keep OK/WARN on the two series colours.
        self.assertEqual(palette.states["OK"], palette.series[0])
        self.assertEqual(palette.states["WARN"], palette.series[1])

    def test_light_theme_keeps_light_series(self):
        charting = _charting()
        widget = _FakeThemeWidget((0.98, 0.98, 0.98), (0.1, 0.1, 0.1))
        palette = charting.chart_palette(widget)
        self.assertEqual(palette.background, (1.0, 1.0, 1.0))
        self.assertEqual(palette.series, charting.LIGHT_PALETTE.series)
        self.assertEqual(palette.foreground, (0.1, 0.1, 0.1))

    def test_unresolvable_theme_falls_back_to_light(self):
        charting = _charting()
        # A MagicMock context: lookup_color answers a non-unpackable mock.
        widget = MagicMock()
        self.assertIs(charting.chart_palette(widget), charting.LIGHT_PALETTE)
        # Missing colour names answer found=False.
        widget = SimpleNamespace(
            get_style_context=lambda: SimpleNamespace(lookup_color=lambda name: (False, None))
        )
        self.assertIs(charting.chart_palette(widget), charting.LIGHT_PALETTE)


class _FakeFontWidget:
    """Widget whose style context reports a fixed theme font size."""

    def __init__(self, pt):
        desc = SimpleNamespace(get_size=lambda: int(pt * 1024))
        self._context = SimpleNamespace(get_font=lambda _flags: desc)

    def get_style_context(self):
        return self._context


class TestChartFontScale(unittest.TestCase):
    """The GUI-base-font scale every renderer resolves for its text."""

    def test_base_font_sizes_scale_chart_text(self):
        charting = _charting()
        self.assertAlmostEqual(charting.chart_font_scale(_FakeFontWidget(10.0)), 1.0)
        self.assertAlmostEqual(charting.chart_font_scale(_FakeFontWidget(12.5)), 1.25)
        self.assertAlmostEqual(charting.chart_font_scale(_FakeFontWidget(5.0)), 0.5)

    def test_unresolvable_font_degrades_to_one(self):
        charting = _charting()
        # No style context at all.
        self.assertEqual(charting.chart_font_scale(object()), 1.0)
        # Mocked GTK: every call answers, but no real size comes back.
        self.assertEqual(charting.chart_font_scale(MagicMock()), 1.0)
        # A context that answers None.
        self.assertEqual(
            charting.chart_font_scale(SimpleNamespace(get_style_context=lambda: None)), 1.0
        )
        # A font whose size is not a number.
        garbage = SimpleNamespace(
            get_style_context=lambda: SimpleNamespace(
                get_font=lambda _f: SimpleNamespace(get_size=lambda: "huge")
            )
        )
        self.assertEqual(charting.chart_font_scale(garbage), 1.0)


class TestSharedVocabulary(unittest.TestCase):
    """The rolling-chart vocabulary both renderers share."""

    def test_nice_ceiling_ladder(self):
        charting = _charting()
        self.assertEqual(charting.nice_ceiling(0), 1.0)
        self.assertEqual(charting.nice_ceiling(1), 1.0)
        self.assertEqual(charting.nice_ceiling(3), 5.0)
        self.assertEqual(charting.nice_ceiling(7), 10.0)
        self.assertEqual(charting.nice_ceiling(80), 100.0)
        self.assertEqual(charting.nice_ceiling(900), 1000.0)

    def test_format_age(self):
        charting = _charting()
        self.assertEqual(charting.format_age(45), "45s")
        self.assertEqual(charting.format_age(299), "4m 59s")
        self.assertEqual(charting.format_age(3661), "1h 01m")


class TestBackendProbe(unittest.TestCase):
    def test_backend_unavailable_under_mocks(self):
        """Under mock_gtk the probe never runs, so the backend is unavailable.

        The mock-aware fence is structural: with a mocked ``Gtk`` binding
        the probe returns None without even attempting the import — on
        GTK-equipped hosts the import used to "succeed" against the fake
        gi and cache a canvas class mixed from mocks.
        """
        with mock_gtk(fresh=True):
            import charting

            self.assertIsNone(charting.matplotlib_backend())
            # No cache was written either — the next call re-checks rather
            # than trusting a probe that ran under a fake binding.
            self.assertIsNone(charting.matplotlib_backend())

    def test_probe_does_not_cache_under_mock_binding(self):
        """A mocked Gtk binding must leave the probe cache untouched."""
        with mock_gtk(fresh=True):
            import charting

            self.assertIsNone(charting.matplotlib_backend())
            self.assertIs(charting._backend, charting._UNPROBED)

    def test_real_cache_hidden_under_mock_binding(self):
        """A cache from a real probe is never served to a mocked binding.

        The poisoning trap: a module binding whose ``Gtk`` became a stale
        mock (a fresh mock import surviving its context) consuming a
        backend cached by an earlier real probe — mixed real/mock canvas
        construction dies with a PyGObject SystemError.
        """
        charting = _charting()
        real_cache = SimpleNamespace(Figure=MagicMock(), FigureCanvas=MagicMock())
        with patch.object(charting, "_backend", real_cache):
            # Real binding: the cache is served.
            with patch.object(charting, "Gtk", object()):
                self.assertIs(charting.matplotlib_backend(), real_cache)
            # Mocked binding: the cache is hidden.
            with patch.object(charting, "Gtk", MagicMock()):
                self.assertIsNone(charting.matplotlib_backend())

    def test_real_binding_is_not_mistaken_for_mock(self):
        """Ordinary modules (and their absence) never trip the fence."""
        charting = _charting()
        with patch.object(charting, "Gtk", None):
            self.assertFalse(charting._gtk_binding_is_mock())
        import types

        with patch.object(charting, "Gtk", types.ModuleType("Gtk")):
            self.assertFalse(charting._gtk_binding_is_mock())
        with patch.object(charting, "Gtk", MagicMock()):
            self.assertTrue(charting._gtk_binding_is_mock())


class TestFactory(unittest.TestCase):
    def test_factory_falls_back_to_cairo_when_unavailable(self):
        with mock_gtk(fresh=True):
            import charting
            from memory_page import RollingChart

            chart = charting.create_rolling_chart("ARC size", ["size"])
            self.assertIsInstance(chart, RollingChart)
            self.assertEqual(chart.title, "ARC size")
            self.assertEqual(chart.series_names, ["size"])

    def test_factory_prefers_matplotlib_when_available(self):
        charting = _charting()
        backend = _fake_backend()[0]
        with patch.object(charting, "matplotlib_backend", return_value=backend):
            chart = charting.create_rolling_chart("L2ARC traffic", ["read", "write"])
        self.assertIsInstance(chart, charting.MatplotlibRollingChart)
        self.assertEqual(chart.series_names, ["read", "write"])


class TestMatplotlibRollingChart(unittest.TestCase):
    def _built(self, **kwargs):
        """Build a chart against the fake backend; return everything mocked."""
        charting = _charting()
        backend, fig, ax, canvas, lines, fills, formatters = _fake_backend()
        patcher = patch.object(charting, "matplotlib_backend", return_value=backend)
        patcher.start()
        self.addCleanup(patcher.stop)
        chart = charting.MatplotlibRollingChart("traffic", ["read", "write"], **kwargs)
        return chart, ax, canvas, lines, fills, formatters, fig

    def test_construction_styles_canvas_and_axes(self):
        _chart, ax, canvas, lines, fills, _formatters, fig = self._built()
        # Height behavior from the pack layer: a fixed height request on
        # the packed widget, exactly like the Cairo fallback.
        canvas.set_size_request.assert_called_once_with(-1, 110)
        # One artist pair per series, translucent fill under each line.
        self.assertEqual(len(lines), 2)
        self.assertEqual(len(fills), 2)
        # Left-aligned title, initial legend with the series names, and a
        # single build-time layout pass (never constrained_layout).
        ax.set_title.assert_called_once()
        self.assertEqual(ax.set_title.call_args.args[0], "traffic")
        self.assertEqual(ax.set_title.call_args.kwargs.get("loc"), "left")
        self.assertEqual(ax.legend.call_args.args[1], ["read", "write"])
        fig.tight_layout.assert_called_once()

    def test_build_applies_light_palette_under_mocks(self):
        """Under the fake backend the theme cannot resolve, so the chart
        paints with the light palette — the matplotlib analogue of the
        Cairo fallback's own palette resolution."""
        _chart, _ax, _canvas, _lines, _fills, _formatters, fig = self._built()
        fig.patch.set_facecolor.assert_called_with((1.0, 1.0, 1.0))

    def test_style_updated_reapplies_palette(self):
        chart, _ax, canvas, _lines, _fills, _formatters, fig = self._built()
        fig.patch.set_facecolor.reset_mock()
        canvas.draw_idle.reset_mock()
        chart._on_style_updated()
        self.assertEqual(fig.patch.set_facecolor.call_count, 1)
        canvas.draw_idle.assert_called_once()

    def test_style_updated_rebuilds_legend_with_new_label_colour(self):
        """A mid-session theme change recolours the legend text immediately:
        the legend is rebuilt from its stashed labels with the freshly
        resolved palette's foreground instead of staying stale until the
        next data append."""
        chart, ax, _canvas, _lines, _fills, _formatters, _fig = self._built()
        chart.append(100.0, [10, 5])
        chart.append(105.0, [20, 8])
        ax.legend.reset_mock()
        # Flip the canvas onto a dark theme and fire the style change.
        dark = _FakeThemeWidget((0.16, 0.16, 0.18), (0.88, 0.88, 0.88))
        chart.widget = SimpleNamespace(
            get_style_context=dark.get_style_context,
            draw_idle=lambda: None,
        )
        chart._on_style_updated()
        ax.legend.assert_called_once()
        self.assertEqual(ax.legend.call_args.args[1], chart._legend_labels)
        self.assertEqual(ax.legend.call_args.kwargs.get("labelcolor"), (0.88, 0.88, 0.88))

    def test_text_sizes_follow_the_gui_base_font(self):
        """Chart text scales with the widget-resolved GUI base font (the
        tuned sizes are per a 10pt default); the mocked canvas resolves no
        font, so an unscaled build keeps them, and style-updated re-resolves."""
        charting = _charting()
        _chart, ax, _canvas, _lines, _fills, _formatters, _fig = self._built()
        self.assertEqual(ax.set_title.call_args.kwargs.get("fontsize"), 9)
        self.assertEqual(ax.tick_params.call_args.kwargs.get("labelsize"), 7.5)
        self.assertEqual(ax.legend.call_args.kwargs.get("fontsize"), 8)
        self.assertEqual(ax.text.call_args_list[0].kwargs.get("fontsize"), 8.5)

        backend, _fig2, ax2, _canvas2, _l, _f, _fmt = _fake_backend()
        with (
            patch.object(charting, "matplotlib_backend", return_value=backend),
            patch.object(charting, "chart_font_scale", return_value=1.25),
        ):
            scaled = charting.MatplotlibRollingChart("traffic", ["read"])
        self.assertEqual(ax2.set_title.call_args.kwargs.get("fontsize"), 11.25)
        self.assertEqual(ax2.tick_params.call_args.kwargs.get("labelsize"), 9.375)
        self.assertEqual(ax2.legend.call_args.kwargs.get("fontsize"), 10.0)
        self.assertEqual(ax2.text.call_args_list[0].kwargs.get("fontsize"), 10.625)

        # The style-updated path re-resolves the scale with the palette.
        with patch.object(charting, "chart_font_scale", return_value=1.0):
            scaled._on_style_updated()
        self.assertEqual(ax2.set_title.call_args.kwargs.get("fontsize"), 9)

    def test_collecting_state_until_two_points(self):
        chart, _ax, _canvas, _lines, _fills, _formatters, _fig = self._built()
        chart._collecting.set_visible.reset_mock()
        chart.append(100.0, [10, None])
        chart._collecting.set_visible.assert_called_once_with(True)
        chart.append(105.0, [20, 5])
        chart._collecting.set_visible.assert_called_with(False)

    def test_append_updates_artists_and_scales(self):
        chart, ax, canvas, lines, fills, _formatters, _fig = self._built()
        chart.append(100.0, [10, None])
        chart.append(105.0, [20, 5])
        chart.append(110.0, [30, 8])

        # One idle redraw per append (the refresh-tick cadence).
        self.assertEqual(canvas.draw_idle.call_count, 3)
        # Window and Y ceiling: peak 30 -> nice ceiling 50 over quarters.
        ax.set_xlim.assert_called_with(100.0, 110.0)
        ax.set_ylim.assert_called_with(0.0, 50.0)
        ax.set_yticks.assert_called_with([0.0, 12.5, 25.0, 37.5, 50.0])
        # A 10 s window keeps two ticks (more once the span allows it).
        ax.set_xticks.assert_called_with([100.0, 110.0])

        # Series data: None values drop out of the polyline, and the fill
        # polygon closes down to the zero baseline.
        lines[0].set_data.assert_called_with([100.0, 105.0, 110.0], [10, 20, 30])
        lines[1].set_data.assert_called_with([105.0, 110.0], [5, 8])
        self.assertEqual(
            fills[1].xy,
            [(105.0, 0.0), (105.0, 5), (110.0, 8), (110.0, 0.0)],
        )
        fills[0].set_visible.assert_called_with(True)

        # Legend rebuilt with the newest value per series (fallback text).
        self.assertEqual(
            ax.legend.call_args.args[1],
            ["read 30 B", "write 8 B"],
        )

    def test_percent_chart_formats_axis_and_legend(self):
        charting = _charting()
        backend, _fig, ax, _canvas, _lines, _fills, formatters = _fake_backend()
        with patch.object(charting, "matplotlib_backend", return_value=backend):
            chart = charting.MatplotlibRollingChart("ARC hit rate", ["hit rate"], percent=True)
        chart.append(100.0, [50])
        chart.append(105.0, [80])
        ax.set_ylim.assert_called_with(0.0, 100.0)
        ax.set_yticks.assert_called_with([0.0, 25.0, 50.0, 75.0, 100.0])
        # Y tick labels are percent form regardless of the chart formatter.
        self.assertEqual(formatters[0].func(50, 0), "50%")
        # Legend uses format_percent for the latest value.
        self.assertEqual(ax.legend.call_args.args[1], ["hit rate 80.0%"])

    def test_x_axis_labels_age_behind_newest_sample(self):
        chart, _ax, _canvas, _lines, _fills, formatters, _fig = self._built()
        chart.append(100.0, [1, 1])
        chart.append(125.0, [2, 2])  # 25 s window -> 3 ticks
        x_format = formatters[1].func
        self.assertEqual(x_format(125.0, 0), "now")
        self.assertEqual(x_format(100.0, 0), "-25s")
        self.assertEqual(x_format(112.5, 0), "-12s")

    def test_reference_line_overlay_and_clear(self):
        chart, ax, _canvas, _lines, _fills, _formatters, _fig = self._built()
        chart.append(100.0, [10, 5])
        chart.append(105.0, [20, 8])
        chart.set_reference(40.0, "c_max 40 B")
        # The reference raises the ceiling: peak becomes 40 -> ceiling 50.
        ax.set_ylim.assert_called_with(0.0, 50.0)
        ax.axhline.assert_called_once()
        self.assertEqual(ax.axhline.call_args.args[0], 40.0)
        self.assertEqual(ax.axhline.call_args.kwargs.get("linestyle"), (0, (4, 4)))
        ax.annotate.assert_called_once()
        self.assertEqual(ax.annotate.call_args.args[0], "c_max 40 B")

        ax.axhline.reset_mock()
        chart.set_reference(None, "")
        self.assertEqual(ax.axhline.call_count, 0)

    def test_window_trims_to_max_samples(self):
        charting = _charting()
        backend = _fake_backend()[0]
        with patch.object(charting, "matplotlib_backend", return_value=backend):
            chart = charting.MatplotlibRollingChart("t", ["a"], max_samples=3)
        for i in range(5):
            chart.append(float(i), [i])
        self.assertEqual(len(chart.points), 3)
        self.assertEqual(chart.points[0][0], 2.0)

    def test_layout_runs_once_after_first_rendered_sample(self):
        chart, _ax, _canvas, _lines, _fills, _formatters, fig = self._built()
        fig.tight_layout.reset_mock()
        chart.append(100.0, [1, 1])
        chart.append(105.0, [2, 2])
        fig.tight_layout.assert_called_once()
        chart.append(110.0, [3, 3])
        chart.append(115.0, [4, 4])
        self.assertEqual(fig.tight_layout.call_count, 1)


def _rung(layer, label, size, state="OK"):
    return SimpleNamespace(layer=layer, label=label, size=size, state=state)


def _ladder_pool(name, block, rungs, ashift=None):
    """LadderPool stand-in: the ladder code touches only these attributes."""
    return SimpleNamespace(pool=name, ashift=ashift, block=block, bars=list(rungs))


def _two_pool_ladder():
    return [
        _ladder_pool(
            "tank",
            4096,
            [
                _rung("Device", "device · physical sector 4K (2 devices)", 4096),
                _rung("Pool", "pool · ashift 12 · 4K block", 4096),
                _rung("Dataset", "dataset · volblocksize 16K", 16384),
                _rung("VM", "vm · guest sector 512", 512, state="info"),
            ],
            ashift=12,
        ),
        _ladder_pool(
            "old", 512, [_rung("Device", "device · physical sector 4K", 4096, state="WARN")]
        ),
    ]


class TestLadderVocabulary(unittest.TestCase):
    """Shared ladder geometry and axis grammar (both renderers use these)."""

    def test_pixel_height_follows_row_set(self):
        charting = _charting()
        self.assertEqual(
            charting.ladder_pixel_height([]),
            charting.LADDER_MARGIN_TOP + charting.LADDER_MARGIN_BOTTOM,
        )
        pools = _two_pool_ladder()
        rows = sum(1 + len(pool.bars) for pool in pools)
        self.assertEqual(
            charting.ladder_pixel_height(pools),
            charting.LADDER_MARGIN_TOP
            + rows * charting.LADDER_ROW_HEIGHT
            + charting.LADDER_MARGIN_BOTTOM,
        )

    def test_axis_range_powers_of_two_with_headroom(self):
        charting = _charting()
        x_min, x_max, ticks = charting.ladder_axis_range(_two_pool_ladder())
        self.assertEqual(x_min, 256)  # one power below the smallest size (512)
        self.assertEqual(x_max, 32768)  # one power past the largest size
        self.assertEqual(ticks, (256, 512, 1024, 2048, 4096, 8192, 16384, 32768))

    def test_minimum_width_covers_labels_plot_and_legend(self):
        """The horizontal-scrollbar floor: zero when empty, wider for
        longer labels, always at least the plot floor plus legend."""
        charting = _charting()
        self.assertEqual(charting.ladder_minimum_width([]), 0)
        pools = _two_pool_ladder()
        base = charting.ladder_minimum_width(pools)
        legend_chars = sum(len(text) for _state, text in charting.LADDER_LEGEND)
        self.assertGreaterEqual(
            base, charting.LADDER_PLOT_MIN_WIDTH + legend_chars * charting.LADDER_CHAR_WIDTH_PX
        )
        longer = [
            _ladder_pool(
                "tank",
                4096,
                [_rung("Dataset", "dataset · recordsize 128K (very long label)", 131072)],
            )
        ]
        self.assertGreater(charting.ladder_minimum_width(longer), base)

    def test_minimum_width_scales_with_the_gui_base_font(self):
        """A larger GUI base font widens the gutter and legend estimate, so
        the horizontal-scrollbar floor grows with the ladder's text."""
        charting = _charting()
        pools = _two_pool_ladder()
        base = charting.ladder_minimum_width(pools)
        self.assertEqual(charting.ladder_minimum_width(pools, 1.0), base)
        self.assertGreater(charting.ladder_minimum_width(pools, 1.25), base)
        self.assertEqual(charting.ladder_minimum_width([], 1.25), 0)

    def test_axis_range_defaults_without_data(self):
        charting = _charting()
        x_min, x_max, ticks = charting.ladder_axis_range([])
        self.assertEqual((x_min, x_max), (256, 8192))
        self.assertEqual(ticks[0], 256)

    def test_axis_range_thins_ticks_on_wide_spans(self):
        charting = _charting()
        pools = [
            _ladder_pool(
                "big",
                4096,
                [
                    _rung("VM", "vm · guest sector 512", 512, state="info"),
                    _rung("Dataset", "dataset · recordsize 256M", 256 * 1024**2),
                ],
            )
        ]
        _x_min, _x_max, ticks = charting.ladder_axis_range(pools)
        # 256..512M spans 21 powers — too many for per-tick labels, so the
        # grid thins to every other power.
        self.assertGreater(len(ticks), 4)
        steps = {ticks[i + 1] // ticks[i] for i in range(len(ticks) - 1)}
        self.assertEqual(steps, {2**2})

    def test_ladder_build_applies_light_palette_under_mocks(self):
        """Theme resolution fails under the fake backend, so the ladder
        paints with the light palette (the white-background look)."""
        charting = _charting()
        backend, fig, _ax, _canvas = _fake_backend()[:4]
        with patch.object(charting, "matplotlib_backend", return_value=backend):
            charting.MatplotlibBlocksizeLadder("Blocksize ladder")
        fig.patch.set_facecolor.assert_called_with((1.0, 1.0, 1.0))

    def test_state_colour_key_covers_severity_ladder(self):
        charting = _charting()
        self.assertEqual(set(charting.LADDER_STATE_COLORS), {"OK", "WARN", "info"})
        self.assertEqual(
            {state for state, _text in charting.LADDER_LEGEND}, set(charting.LADDER_STATE_COLORS)
        )

    def test_factory_falls_back_to_cairo_ladder(self):
        with mock_gtk(fresh=True):
            import charting
            from alignment_page import BlocksizeLadder

            ladder = charting.create_blocksize_ladder()
        self.assertIsInstance(ladder, BlocksizeLadder)

    def test_factory_prefers_matplotlib_ladder(self):
        charting = _charting()
        backend = _fake_backend()[0]
        with patch.object(charting, "matplotlib_backend", return_value=backend):
            ladder = charting.create_blocksize_ladder("Blocksize ladder")
        self.assertIsInstance(ladder, charting.MatplotlibBlocksizeLadder)


class TestMatplotlibBlocksizeLadder(unittest.TestCase):
    def _built(self):
        charting = _charting()
        backend, fig, ax, canvas, _lines, _fills, _formatters = _fake_backend()
        patcher = patch.object(charting, "matplotlib_backend", return_value=backend)
        patcher.start()
        self.addCleanup(patcher.stop)
        ladder = charting.MatplotlibBlocksizeLadder("Blocksize ladder")
        return ladder, ax, canvas, fig, backend

    def test_construction_sizes_empty_widget_and_styles_title(self):
        _ladder, ax, canvas, _fig, _backend = self._built()
        canvas.set_size_request.assert_called_once_with(-1, _charting().LADDER_EMPTY_HEIGHT)
        ax.set_title.assert_called_once()
        self.assertEqual(ax.set_title.call_args.args[0], "Blocksize ladder")
        self.assertEqual(ax.set_title.call_args.kwargs.get("loc"), "left")

    def test_update_draws_one_bar_per_rung_with_state_colours(self):
        ladder, ax, _canvas, _fig, _backend = self._built()
        pools = [_ladder_pool("tank", 4096, _two_pool_ladder()[0].bars, ashift=12)]
        ladder.update(pools)
        ax.barh.assert_called_once()
        positions, widths = ax.barh.call_args.args[0], ax.barh.call_args.args[1]
        self.assertEqual(positions, [1, 2, 3, 4])  # rungs below the header row
        self.assertEqual(widths, [4096 - 256, 4096 - 256, 16384 - 256, 512 - 256])
        colors = ax.barh.call_args.kwargs["color"]
        self.assertEqual(
            colors,
            [
                _built_state_color("OK"),
                _built_state_color("OK"),
                _built_state_color("OK"),
                _built_state_color("info"),
            ],
        )
        self.assertEqual(ax.barh.call_args.kwargs["left"], 256)

    def test_reference_lines_one_per_pool_with_known_block(self):
        ladder, ax, _canvas, _fig, _backend = self._built()
        ladder.update(_two_pool_ladder())
        blocks = sorted(call.args[0] for call in ax.vlines.call_args_list)
        self.assertEqual(blocks, [512, 4096])
        for call in ax.vlines.call_args_list:
            self.assertEqual(call.kwargs.get("linestyle"), (0, (4, 4)))

    def test_axis_is_log2_with_pow2_tick_labels(self):
        ladder, ax, _canvas, _fig, _backend = self._built()
        ladder.update(_two_pool_ladder())
        ax.set_xscale.assert_called_with("log", base=2)
        ax.set_xlim.assert_called_with(256, 32768)
        ax.set_xticks.assert_called_with([256, 512, 1024, 2048, 4096, 8192, 16384, 32768])
        ax.set_xticklabels.assert_called_with(["256", "512", "1K", "2K", "4K", "8K", "16K", "32K"])

    def test_row_labels_with_bold_pool_headers(self):
        ladder, ax, _canvas, _fig, _backend = self._built()
        pools = [_ladder_pool("tank", 4096, [_rung("Pool", "pool · ashift 12 · 4K block", 4096)])]
        tick_labels = [MagicMock(), MagicMock()]
        ax.get_yticklabels = MagicMock(return_value=tick_labels)
        ladder.update(pools)
        labels = ax.set_yticklabels.call_args.args[0]
        self.assertEqual(labels, ["tank", "pool · ashift 12 · 4K block"])
        tick_labels[0].set_fontweight.assert_called_once_with("bold")
        tick_labels[1].set_fontweight.assert_not_called()

    def test_legend_patches_per_state(self):
        ladder, ax, _canvas, _fig, backend = self._built()
        ladder.update(_two_pool_ladder())
        handles = ax.legend.call_args.kwargs["handles"]
        self.assertEqual(len(handles), 3)
        facecolors = [call.kwargs["facecolor"] for call in backend.Patch.call_args_list]
        self.assertEqual(
            facecolors,
            [
                _built_state_color("OK"),
                _built_state_color("WARN"),
                _built_state_color("info"),
            ],
        )

    def test_height_and_layout_follow_row_set_only(self):
        ladder, _ax, canvas, fig, _backend = self._built()
        pools = _two_pool_ladder()
        ladder.update(pools)
        charting = _charting()
        canvas.set_size_request.assert_called_with(
            charting.ladder_minimum_width(pools), charting.ladder_pixel_height(pools)
        )
        fig.tight_layout.reset_mock()
        canvas.set_size_request.reset_mock()

        # Same row set: no re-layout, no size churn.
        ladder.update(_two_pool_ladder())
        fig.tight_layout.assert_not_called()
        canvas.set_size_request.assert_not_called()

        # A new pool changes the row set: one fresh layout and height.
        grown = pools + [
            _ladder_pool("new", 4096, [_rung("Pool", "pool · ashift 12 · 4K block", 4096)])
        ]
        ladder.update(grown)
        fig.tight_layout.assert_called_once()
        canvas.set_size_request.assert_called_with(
            charting.ladder_minimum_width(grown), charting.ladder_pixel_height(grown)
        )

    def test_canvas_request_is_content_minimum_only(self):
        """The width request is the content minimum — there is no followed
        page width. The viewport stretches the canvas to the full page
        width whenever the page is wider, so the request doubles as the
        horizontal-scrollbar floor (the window's max_content_width is
        floored at the same value by alignment_page)."""
        ladder, _ax, canvas, _fig, _backend = self._built()
        pools = _two_pool_ladder()
        ladder.update(pools)
        charting = _charting()
        canvas.set_size_request.assert_called_with(
            charting.ladder_minimum_width(pools), charting.ladder_pixel_height(pools)
        )
        # The retired followed-width API must stay retired: the half-share
        # contract fed a max_content_width below this request, which made
        # GTK clamp the canvas and drop the horizontal scrollbar.
        self.assertFalse(hasattr(ladder, "set_draw_width"))
        self.assertFalse(hasattr(ladder, "draw_width"))

    def test_ladder_text_sizes(self):
        """The ladder's text sits a notch larger than the rolling charts'
        vocabulary (user-visible sizing; the Cairo fallback's 13px font
        matches this scale)."""
        ladder, ax, _canvas, _fig, _backend = self._built()
        self.assertEqual(ax.set_title.call_args.kwargs.get("fontsize"), 11.5)
        ladder.update(_two_pool_ladder())
        self.assertEqual(ax.set_yticklabels.call_args.kwargs.get("fontsize"), 11)
        self.assertEqual(ax.legend.call_args.kwargs.get("fontsize"), 10.5)
        self.assertEqual(ax.tick_params.call_args.kwargs.get("labelsize"), 10.5)

    def test_ladder_text_sizes_and_width_follow_the_gui_base_font(self):
        """A 12.5pt GUI base font scales every ladder font site by 1.25 and
        widens the canvas's content-minimum width request with it; the
        mocked canvas resolves no font, so the unscaled build above keeps
        the tuned sizes. The backend patch lives for the whole test — an
        unpatched update() would run the real backend probe outside any
        mock and cache the real GTK canvas for every later suite."""
        charting = _charting()
        backend, _fig, ax, canvas, _lines, _fills, _formatters = _fake_backend()
        backend_patcher = patch.object(charting, "matplotlib_backend", return_value=backend)
        scale_patcher = patch.object(charting, "chart_font_scale", return_value=1.25)
        backend_patcher.start()
        scale_patcher.start()
        self.addCleanup(scale_patcher.stop)
        self.addCleanup(backend_patcher.stop)
        ladder = charting.MatplotlibBlocksizeLadder("Blocksize ladder")
        self.assertEqual(ax.set_title.call_args.kwargs.get("fontsize"), 14.375)
        pools = _two_pool_ladder()
        ladder.update(pools)
        self.assertEqual(ax.set_yticklabels.call_args.kwargs.get("fontsize"), 13.75)
        self.assertEqual(ax.legend.call_args.kwargs.get("fontsize"), 13.125)
        self.assertEqual(ax.tick_params.call_args.kwargs.get("labelsize"), 13.125)
        canvas.set_size_request.assert_called_with(
            charting.ladder_minimum_width(pools, 1.25), charting.ladder_pixel_height(pools)
        )
        self.assertGreater(
            charting.ladder_minimum_width(pools, 1.25), charting.ladder_minimum_width(pools)
        )

    def test_empty_update_keeps_placeholder_height(self):
        ladder, _ax, canvas, _fig, _backend = self._built()
        ladder.update([])
        canvas.set_size_request.assert_called_with(-1, _charting().LADDER_EMPTY_HEIGHT)
        ladder.update([], unavailable=True)
        # The unavailable variant renders the same empty height.
        canvas.set_size_request.assert_called_with(-1, _charting().LADDER_EMPTY_HEIGHT)

    def test_empty_messages_distinguish_unavailable_from_no_pools(self):
        ladder, ax, _canvas, _fig, _backend = self._built()
        ladder.update([])
        texts = [call.args[2] for call in ax.text.call_args_list]
        self.assertTrue(any("no pools found" in text for text in texts))
        ax.text.reset_mock()
        ladder.update([], unavailable=True)
        texts = [call.args[2] for call in ax.text.call_args_list]
        self.assertTrue(any("unavailable" in text for text in texts))


def _built_state_color(state):
    charting = _charting()
    return charting.LADDER_STATE_COLORS[state]


if __name__ == "__main__":
    unittest.main()

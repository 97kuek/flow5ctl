"""Chart rendering.

The charts exist for MCP clients, where the reader cannot open a file. These tests
check the things that would quietly make a chart wrong or unreadable rather than
throw: that both themes are *selected* rather than flipped, that the palette is used
in its validated order, that a form which cannot be read is refused, and that a real
PNG comes out.
"""
from __future__ import annotations

import pytest

pytest.importorskip("matplotlib", reason="charts need the `plot` extra")

from flow5ctl.errors import DesignError
from flow5ctl.flow5.results import parse_polar
from flow5ctl.viz import charts, palette

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@pytest.fixture
def result(fixtures):
    """A stored-result shape, built from a real polar fixture."""
    polar = parse_polar(fixtures / "polar_t1_rectwing.csv")
    return {
        "design": "RectWing", "polar": "cruise", "flow5_version": "7.57",
        "conditions": {"speed": 15.0, "viscous_method": "interpolated",
                       "ground_height": None},
        "summary": {"best_LD": {"value": 184.7, "alpha": 2.0, "cl": 0.171,
                                "cd": 0.00093}},
        "columns": polar.columns, "rows": polar.rows,
    }


class TestPalette:
    def test_both_themes_exist_and_differ(self):
        assert palette.LIGHT.surface != palette.DARK.surface
        assert palette.LIGHT.series[0] != palette.DARK.series[0]

    def test_the_categorical_order_is_the_validated_one(self):
        """The order is the colour-vision safety mechanism, not decoration — the first
        three slots are the ones validated for all-pairs use."""
        assert palette.SERIES_LIGHT[:3] == ("#2a78d6", "#eb6834", "#1baf7a")
        assert palette.SERIES_DARK[:3] == ("#3987e5", "#d95926", "#199e70")

    def test_both_themes_offer_the_same_number_of_slots(self):
        assert len(palette.SERIES_LIGHT) == len(palette.SERIES_DARK) == palette.MAX_SERIES

    def test_an_unknown_theme_says_what_is_valid(self):
        with pytest.raises(ValueError, match="light.*dark"):
            palette.theme("neon")

    def test_colours_do_not_cycle_within_the_slot_range(self):
        th = palette.LIGHT
        assert len({th.colour(i) for i in range(palette.MAX_SERIES)}) == palette.MAX_SERIES


class TestRendering:
    @pytest.mark.parametrize("kind", ["polar", "cl_alpha", "cm_alpha", "drag_breakdown"])
    @pytest.mark.parametrize("theme", ["light", "dark"])
    def test_every_kind_renders_in_both_themes(self, result, kind, theme):
        data = charts.render([result], kind, theme_name=theme)
        assert data[:8] == PNG_MAGIC
        assert len(data) > 5_000

    def test_the_two_themes_produce_different_images(self, result):
        light = charts.render([result], "polar", theme_name="light")
        dark = charts.render([result], "polar", theme_name="dark")
        assert light != dark

    def test_several_polars_render_on_one_chart(self, result):
        second = {**result, "polar": "slow"}
        data = charts.render([result, second], "cl_alpha")
        assert data[:8] == PNG_MAGIC

    def test_an_unknown_kind_lists_the_real_ones(self, result):
        with pytest.raises(DesignError, match="spanwise_lift"):
            charts.render([result], "isometric")

    def test_nothing_to_plot_is_refused(self):
        with pytest.raises(DesignError, match="nothing to plot"):
            charts.render([], "polar")

    def test_more_series_than_distinguishable_colours_is_refused(self, result):
        """A ninth hue would be indistinguishable under colour-vision deficiency, so
        it is refused rather than generated."""
        with pytest.raises(DesignError, match="distinguishable"):
            charts.render([result] * (palette.MAX_SERIES + 1), "polar")

    def test_a_drag_breakdown_refuses_to_stack_two_aircraft(self, result):
        with pytest.raises(DesignError, match="one analysis at a time"):
            charts.render([result, result], "drag_breakdown")

    def test_a_missing_column_is_named(self, result):
        broken = {**result, "columns": ["Ctrl"], "rows": [[0.0]]}
        with pytest.raises(DesignError, match="column"):
            charts.render([broken], "polar")


class TestSpanwise:
    def strips(self, n: int = 20) -> dict:
        import math
        half = 1.0
        ys = [-half + 2 * half * i / (n - 1) for i in range(n)]
        cls = [0.7 * math.sqrt(max(0.0, 1 - (y / half) ** 2)) for y in ys]
        return {"Main Wing": {"y": ys, "cl": cls, "source": "op.csv"}}

    def test_renders_with_the_elliptic_reference(self, result):
        data = charts.render([result], "spanwise_lift", strips=self.strips())
        assert data[:8] == PNG_MAGIC

    def test_without_strip_data_it_says_to_re_run(self, result):
        with pytest.raises(DesignError, match="spanwise data"):
            charts.render([result], "spanwise_lift", strips=None)

    def test_an_empty_strip_table_is_refused(self, result):
        with pytest.raises(DesignError, match="no usable rows"):
            charts.render([result], "spanwise_lift",
                          strips={"Main Wing": {"y": [], "cl": []}})


class TestEllipticReference:
    """Elliptic means the LOADING is elliptic, not the local Cl.

    Loading is Cl x chord, so on a tapered wing the local Cl that produces an
    elliptic load rises towards the tip rather than falling like sqrt(1 - eta^2).
    The chart drew sqrt(1 - eta^2) against local Cl, which compares two different
    quantities: on the 34 m example at taper 0.45 it made a wing whose loading is
    close to elliptic look far below it.
    """

    N = 41

    def _span(self):
        return [-1.0 + 2.0 * i / (self.N - 1) for i in range(self.N)]

    def _shape(self, ys):
        import math
        return [math.sqrt(max(0.0, 1.0 - y * y)) for y in ys]

    def _spread(self, a, b):
        r = [a[i] / b[i] for i in range(len(a)) if b[i] > 1e-6]
        return max(r) - min(r)

    def test_a_rectangular_wing_is_unchanged(self):
        """With a constant chord the two readings coincide, so nothing moves."""
        ys = self._span()
        cls = [1.0 - 0.3 * y * y for y in ys]
        ref = charts._elliptic_reference(ys, cls, [1.0] * self.N, 1.0)
        assert self._spread(ref.y, self._shape(ys)) < 1e-12

    def test_on_a_tapered_wing_the_loading_is_elliptic_and_the_cl_is_not(self):
        ys = self._span()
        cls = [1.0 - 0.3 * y * y for y in ys]
        chord = [1.0 - 0.55 * abs(y) for y in ys]          # taper 0.45
        ref = charts._elliptic_reference(ys, cls, chord, 1.0)
        shape = self._shape(ys)
        loading = [ref.y[i] * chord[i] for i in range(self.N)]
        assert self._spread(loading, shape) < 1e-12         # the load is elliptic
        assert self._spread(ref.y, shape) > 0.5             # the Cl curve is not

    def test_it_carries_the_same_total_lift_as_the_measured_curve(self):
        """The old scaling matched the sum of Cl, which is the lift only when the
        chord and the strip widths are constant. Neither is, on a tapered wing with
        cosine spacing."""
        ys = self._span()
        cls = [1.0 - 0.3 * y * y for y in ys]
        chord = [1.0 - 0.55 * abs(y) for y in ys]
        ref = charts._elliptic_reference(ys, cls, chord, 1.0)
        measured = charts._integrate(ys, [cls[i] * chord[i] for i in range(self.N)])
        drawn = charts._integrate(ys, [ref.y[i] * chord[i] for i in range(self.N)])
        assert drawn == pytest.approx(measured, rel=1e-9)

    def test_without_a_chord_it_says_the_reference_is_approximate(self):
        ys = self._span()
        cls = [1.0 - 0.3 * y * y for y in ys]
        assert charts._elliptic_reference(ys, cls, None, 1.0).label.endswith("(approximate)")
        assert charts._elliptic_reference(ys, cls, chord=[1.0] * self.N,
                                          half=1.0).label == "elliptic loading (same lift)"

    def test_the_chord_comes_from_the_strip_reynolds_numbers(self):
        """flow5's strip table has no chord column, but within one operating point
        the freestream is uniform so Re is exactly proportional to the local chord.
        Measured on the 34 m example at taper 0.45: Re ratio 2.21, taper ratio 2.22.
        """
        table = {"re": [200.0, 300.0, 400.0]}
        assert charts._relative_chord(table, [0, 1, 2]) == pytest.approx([0.5, 0.75, 1.0])

    def test_a_result_stored_without_re_falls_back_rather_than_guessing(self):
        assert charts._relative_chord({}, [0, 1]) is None
        assert charts._relative_chord({"re": [0.0, 1.0]}, [0, 1]) is None


class TestTheSubtitleDescribesEveryCurve:
    """A comparison chart took its caption from the first result alone.

    Plotting a 12 m/s run against an 8 m/s one was captioned "12 m/s", so the second
    curve was silently attributed a speed it was not run at - on a chart whose whole
    purpose is comparison.
    """

    def _r(self, speed=None, method="interpolated", ground=None, version="7.57"):
        return {"conditions": {"speed": speed, "viscous_method": method,
                               "ground_height": ground},
                "flow5_version": version}

    def test_one_polar_reads_as_before(self):
        assert charts._subtitle([self._r(speed=12.0)]) == \
            "12 m/s · interpolated · flow5 7.57"

    def test_two_speeds_are_shown_as_a_range(self):
        s = charts._subtitle([self._r(speed=12.0), self._r(speed=8.0)])
        assert "8 m/s–12 m/s" in s
        assert s.count("m/s") == 2          # not "12 m/s" alone

    def test_a_shared_speed_is_not_turned_into_a_range(self):
        s = charts._subtitle([self._r(speed=12.0), self._r(speed=12.0)])
        assert "12 m/s ·" in s and "–" not in s

    def test_mixed_methods_are_both_named(self):
        """Mixing them invents a fifth of the drag; the caption must not hide it."""
        s = charts._subtitle([self._r(speed=12.0, method="interpolated"),
                              self._r(speed=12.0, method="on-the-fly")])
        assert "interpolated / on-the-fly" in s

    def test_ground_effect_on_one_run_only_shows_up(self):
        s = charts._subtitle([self._r(speed=8.0), self._r(speed=8.0, ground=2.0)])
        assert "ground 2 m" in s

    def test_a_missing_speed_is_omitted_not_guessed(self):
        s = charts._subtitle([self._r(speed=None), self._r(speed=None)])
        assert "m/s" not in s
        assert "interpolated" in s


class TestChartsThatCannotShowTwoRuns:
    """Two of the five kinds are single-analysis by construction.

    `drag_breakdown` already refused. `spanwise_lift` did not: the strip table is
    read from the first result, so a second polar was silently dropped while the
    subtitle went on naming both runs' conditions. A chart showing one aircraft's
    loading, captioned as if it covered two, is worse than no chart.
    """

    def _r(self, name):
        return {"design": "D", "polar": name, "columns": ["Ctrl", "α (°)", "CL", "CD"],
                "rows": [[0, 0.0, 0.1, 0.01], [0, 2.0, 0.3, 0.012]],
                "conditions": {"speed": 12.0, "viscous_method": "interpolated"},
                "flow5_version": "7.57", "summary": {}}

    def test_spanwise_lift_refuses_two(self):
        with pytest.raises(DesignError, match="one analysis at a time"):
            charts.render([self._r("a"), self._r("b")], "spanwise_lift",
                          strips={"Main": {"y": [-1.0, 0.0, 1.0], "cl": [0.2, 0.5, 0.2],
                                           "re": [1e5, 2e5, 1e5]}})

    def test_it_says_what_to_do_instead(self):
        with pytest.raises(DesignError, match="Plot them separately"):
            charts.render([self._r("a"), self._r("b")], "spanwise_lift", strips=None)

    def test_drag_breakdown_still_refuses_two(self):
        with pytest.raises(DesignError, match="one analysis at a time"):
            charts.render([self._r("a"), self._r("b")], "drag_breakdown")

    def test_one_analysis_is_fine(self):
        data = charts.render([self._r("a")], "spanwise_lift",
                             strips={"Main": {"y": [-1.0, 0.0, 1.0],
                                              "cl": [0.2, 0.5, 0.2],
                                              "re": [1e5, 2e5, 1e5]}})
        assert data[:8] == b"\x89PNG\r\n\x1a\n"

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

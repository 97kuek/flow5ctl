"""The refusals. Each one exists because flow5 answers the question wrongly instead
of declining it."""
from __future__ import annotations

import pytest

from flow5ctl.advisor import dragbudget, guardrails, structure
from flow5ctl.errors import DesignError, UnsupportedByFlow5
from flow5ctl.flow5 import markers
from flow5ctl.geometry import derived as geometry
from flow5ctl.model import presets
from flow5ctl.model.design import Design


@pytest.fixture
def rect(rect_design):
    return geometry.solve(Design.model_validate(rect_design))


class TestPolarTypeRefusals:
    def test_stability_from_a_t1_polar_is_refused(self):
        with pytest.raises(DesignError, match="1e51|T7"):
            guardrails.check_polar_type("T1", wants_stability=True)

    def test_stability_from_a_t7_polar_is_allowed(self):
        guardrails.check_polar_type("T7", wants_stability=True, derivatives=True)

    def test_derivatives_outside_t7_are_refused(self):
        with pytest.raises(DesignError, match="T7"):
            guardrails.check_polar_type("T2", derivatives=True)

    def test_t6_control_polars_say_why_they_are_impossible(self):
        with pytest.raises(UnsupportedByFlow5, match="hinge"):
            guardrails.check_polar_type("T6")

    def test_static_margin_from_t1_is_not_refused(self):
        """It is the dynamic modes that need T7, not the neutral point."""
        guardrails.check_polar_type("T1")


class TestAnalysisChecks:
    def check(self, rect, **kw):
        opts = {"polar_type": "T1", "alpha": (-2.0, 8.0, 1.0), "viscous": True,
                "on_the_fly": False, "ground_height": None}
        opts.update(kw)
        return guardrails.check_analysis(rect, presets.load("rc-glider"), **opts)

    def test_inviscid_runs_are_labelled_loudly(self, rect):
        c = self.check(rect, viscous=False)
        assert any("INVISCID" in w for w in c.warnings)
        assert any("93" in w for w in c.warnings)

    def test_viscous_method_is_always_recorded(self, rect):
        assert any("interpolated" in n for n in self.check(rect).notes)
        assert any("on-the-fly" in n for n in self.check(rect, on_the_fly=True).notes)

    def test_alpha_beyond_stall_warns(self, rect):
        c = self.check(rect, alpha=(-2.0, 30.0, 1.0))
        assert any("fiction" in w for w in c.warnings)

    def test_a_negative_alpha_step_is_refused(self, rect):
        with pytest.raises(DesignError, match="positive"):
            self.check(rect, alpha=(0.0, 8.0, -1.0))

    def test_too_many_panels_is_refused_with_the_count(self, rect_design):
        raw = {**rect_design}
        raw["wing"] = {**raw["wing"], "panels": {"chordwise": 30, "spanwise": 120}}
        d = geometry.solve(Design.model_validate(raw))
        with pytest.raises(DesignError, match="panels"):
            self.check(d)

    def test_fixed_lift_polars_are_told_about_the_reynolds_range(self, rect):
        assert any("Reynolds" in n for n in self.check(rect, polar_type="T2").notes)

    def test_ground_effect_asks_for_the_out_of_ground_case_too(self, rect):
        assert any("out-of-ground" in n or "out of ground" in n
                   for n in self.check(rect, ground_height=0.3).notes)


class TestGeometryChecks:
    def test_degenerate_roll_inertia_warns_with_the_physical_reason(self, rect):
        c = guardrails.check_geometry(rect, presets.load("rc-glider"))
        assert any("radius of gyration" in w for w in c.warnings)

    def test_a_realistic_mass_distribution_does_not_warn(self, rect_design):
        raw = {**rect_design, "mass": {"components": [
            {"tag": "L", "mass": 0.5, "at": [0.05, -0.35, 0.0]},
            {"tag": "R", "mass": 0.5, "at": [0.05, 0.35, 0.0]},
        ]}}
        d = geometry.solve(Design.model_validate(raw))
        c = guardrails.check_geometry(d, presets.load("rc-glider"))
        assert not any("radius of gyration" in w for w in c.warnings)

    def test_out_of_band_aspect_ratio_warns(self, rect_design):
        raw = {**rect_design, "preset": "hpa"}
        d = geometry.solve(Design.model_validate(raw))
        c = guardrails.check_geometry(d, presets.load("hpa"))
        assert any("aspect ratio" in w for w in c.warnings)

    def test_the_custom_preset_has_no_thresholds(self, rect):
        c = guardrails.check_geometry(rect, presets.load("custom"))
        assert not any("outside the" in w for w in c.warnings)

    def test_mass_given_as_a_total_says_inertia_is_unknown(self, rect_design):
        raw = {**rect_design, "mass": {"total": 1.0, "cg": [0.05, 0.0, 0.0]}}
        d = geometry.solve(Design.model_validate(raw))
        c = guardrails.check_geometry(d, presets.load("rc-glider"))
        assert any("inertia is unknown" in n for n in c.notes)


class TestFixedLiftPolarGuardrail:
    def test_a_t2_sweep_starting_at_zero_lift_warns(self, rect):
        c = guardrails.check_analysis(
            rect, presets.load("rc-glider"), polar_type="T2",
            alpha=(0.0, 8.0, 2.0), viscous=True, on_the_fly=False, ground_height=None)
        assert any("no solution" in w for w in c.warnings)

    def test_a_positive_t2_sweep_does_not_warn(self, rect):
        c = guardrails.check_analysis(
            rect, presets.load("rc-glider"), polar_type="T2",
            alpha=(2.0, 8.0, 2.0), viscous=True, on_the_fly=False, ground_height=None)
        assert not any("no solution" in w for w in c.warnings)


class TestInterpolationFailureExplanation:
    def test_a_diverging_fixed_lift_point_is_not_blamed_on_the_mesh(self):
        from flow5ctl.flow5.markers import explain_interpolation_failure
        log = ("...Viscous interpolation failures:\n"
               "  Span position     -0.97 m,  Re =  59043819,  Cl =    0.00\n"
               "  Span position     -0.93 m,  Re =  59043819,  Cl =    0.00\n")
        msg = explain_interpolation_failure(log, 50_000, 600_000)
        assert "zero-lift angle" in msg
        assert "mesh" in msg

    def test_a_genuinely_narrow_mesh_says_so(self):
        from flow5ctl.flow5.markers import explain_interpolation_failure
        log = ("...Viscous interpolation failures:\n"
               "  Span position     -0.97 m,  Re =  38000,  Cl =    0.62\n")
        msg = explain_interpolation_failure(log, 50_000, 600_000)
        assert "Widen" in msg

    def test_no_failures_means_no_explanation(self):
        from flow5ctl.flow5.markers import explain_interpolation_failure
        assert explain_interpolation_failure("all good", 1e5, 1e6) is None


class TestCoincidentSurfaces:
    """flow5 answers with a -104 degree flow angle instead of an error."""

    def design(self, fin_z: float) -> dict:
        return {
            "name": "Tail", "preset": "custom",
            "requirements": {"cruise_speed": 8.0},
            "mass": {"components": [
                {"tag": "p", "mass": 60.0, "at": [0.55, 0.0, -0.5]},
                {"tag": "wl", "mass": 10.0, "at": [0.6, -7.0, 0.15]},
                {"tag": "wr", "mass": 10.0, "at": [0.6, 7.0, 0.15]},
            ]},
            "airfoils": [{"name": "W", "source": "naca:4412"},
                         {"name": "T", "source": "naca:0010"}],
            "wing": {"airfoil": "W",
                     "planform": {"span": 34.0, "root_chord": 1.15, "taper": 0.45},
                     "panels": {"chordwise": 13, "spanwise": 40}},
            "tail": {"type": "conventional",
                     "elevator": {"position": [6.0, 0.0, 0.5], "airfoil": "T",
                                  "planform": {"span": 3.4, "root_chord": 0.75},
                                  "panels": {"chordwise": 7, "spanwise": 10}},
                     "fin": {"position": [6.0, 0.0, fin_z], "airfoil": "T",
                             "planform": {"span": 1.2, "root_chord": 0.8},
                             "panels": {"chordwise": 7, "spanwise": 8}}},
        }

    def test_a_fin_root_on_the_elevator_warns(self):
        d = geometry.solve(Design.model_validate(self.design(0.5)))
        c = guardrails.check_geometry(d, presets.load("hpa"))
        assert any("Coincident surfaces" in w for w in c.warnings)

    def test_an_offset_fin_does_not_warn(self):
        d = geometry.solve(Design.model_validate(self.design(0.62)))
        c = guardrails.check_geometry(d, presets.load("hpa"))
        assert not any("Coincident" in w for w in c.warnings)


class TestAoaFailureExplanation:
    def test_a_nonsensical_flow_angle_points_at_overlapping_surfaces(self):
        from flow5ctl.flow5.markers import explain_interpolation_failure
        log = ("...Viscous interpolation failures:\n"
               "  Span position     -0.02 m,  Re =    398385,  AoA_effective = -103.90\n")
        msg = explain_interpolation_failure(log, 100_000, 2_000_000)
        assert "same space" in msg or "degenerate" in msg
        assert "fin" in msg

    def test_a_merely_large_flow_angle_points_at_the_polar_alpha_range(self):
        from flow5ctl.flow5.markers import explain_interpolation_failure
        log = ("...Viscous interpolation failures:\n"
               "  Span position     -0.72 m,  Re =    344198,  AoA_effective = -18.5\n")
        msg = explain_interpolation_failure(log, 100_000, 2_000_000)
        assert "alpha sweep" in msg


class TestInterpolationDiagnostic:
    """flow5 prints the failure header with nothing under it.

    Measured on a real run: the log ends at `...Viscous interpolation failures:`
    with no strip, Reynolds or Cl beneath it, so the detailed explainer found
    nothing and a static message took over. That static message named the Reynolds
    range as the cause and talked about fixed-lift polars - on a T1 run whose actual
    fix was widening the alpha sweep. It sent a real investigation the wrong way.
    """

    LOG = (
        "       Calculating plane\n"
        "          Adding interpolated viscous drag...\n"
        "             Processing Main\n"
        "                ...Viscous interpolation failures:\n"
        "\nPanel analysis completed ... Errors encountered\n"
    )

    def test_the_surface_is_named_from_the_log(self):
        assert markers.failing_surface(self.LOG) == "Main"

    def test_a_later_surface_does_not_steal_the_name(self):
        log = self.LOG + "             Processing Elevator\n"
        assert markers.failing_surface(log) == "Main"

    def test_no_failure_means_no_surface(self):
        assert markers.failing_surface("Calculating plane\n Processing Main\n") is None

    def test_the_message_reports_both_ranges_and_picks_no_cause(self):
        text = markers.explain_interpolation_failure(
            self.LOG, 100_000, 1_500_000, cl_cover=(-0.88, 1.67))
        assert text is not None
        assert "Main" in text
        assert "100,000" in text and "1,500,000" in text
        assert "-0.88" in text and "1.67" in text
        # it must not assert an axis it cannot know
        assert "Either could be the cause" in text

    def test_a_lift_range_short_of_the_wing_is_called_out(self):
        text = markers.explain_interpolation_failure(
            self.LOG, 100_000, 1_500_000, cl_cover=(-0.5, 1.20), cl_wanted=1.55)
        assert "1.55" in text and "alpha" in text

    def test_the_static_remedy_no_longer_names_one_axis(self):
        d = markers.diagnose(
            "Viscous interpolation failures\n", 0)
        assert "fixed-lift polar" not in d.hint
        assert "Either the Reynolds range or the lift range" in d.hint


class TestDragBudget:
    """A VLM run of a wing and a tail returns the drag of a wing and a tail.

    On a human-powered aircraft the rigging, the fairing and the pilot are a fifth
    to two fifths of the aeroplane again, and flow5 cannot model them through this
    interface. Quoting the modelled L/D as if it were the aircraft's is the mistake
    this exists to prevent.
    """

    def test_an_hpa_gets_a_band_below_the_modelled_figure(self):
        b = dragbudget.budget("hpa", 27.0)
        assert b is not None
        assert b["realistic_best_LD"]["high"] < 27.0
        assert b["realistic_best_LD"]["low"] < b["realistic_best_LD"]["high"]

    def test_rigging_is_named_for_an_hpa_and_not_for_a_glider(self):
        hpa = [i.name for i in dragbudget.items_for("hpa")]
        glider = [i.name for i in dragbudget.items_for("rc-glider")]
        assert "rigging wires" in hpa
        assert "rigging wires" not in glider
        assert "fuselage" in glider

    def test_the_total_is_not_the_sum_of_the_per_item_highs(self):
        """Summing them assumes every item is at its worst at once."""
        items = dragbudget.items_for("hpa")
        summed = sum(i.high for i in items)
        b = dragbudget.budget("hpa", 27.0)
        assert b["missing_fraction"]["high"] < summed

    def test_custom_gets_no_budget_because_it_assumes_no_airframe(self):
        assert dragbudget.items_for("custom") == ()
        assert dragbudget.budget("custom", 27.0) is None

    def test_no_l_over_d_means_no_claim(self):
        assert dragbudget.budget("hpa", None) is None
        assert dragbudget.warning("hpa", 0.0) is None

    def test_the_warning_says_it_is_an_estimate_not_a_measurement(self):
        text = dragbudget.warning("hpa", 27.0)
        assert "not in the model" in text
        assert "Published estimates" in text


class TestRootBendingMoment:
    """The strip table already carries the number a spar is sized from.

    It was being discarded with the rest of the columns. This does not size a spar -
    that needs the section, the material and a safety factor - but it surfaces the
    aerodynamic load and checks it against the closed form, so a figure that is wrong
    by a factor is caught before it reaches a laminate schedule.
    """

    def _strips(self, moments: list[float], ys: list[float]) -> dict:
        return {"alpha": 0.0,
                "surfaces": {"Main": {"y(m)": ys, "Bending.mom": moments}}}

    def test_the_peak_and_where_it_is(self):
        s = self._strips([0.0, 1500.0, 2804.0, 1500.0, 0.0],
                         [-16.0, -8.0, 0.1, 8.0, 16.0])
        out = structure.root_load(s, mass_kg=89.0, semi_span_m=16.0)
        assert out["root_bending_moment_Nm"] == pytest.approx(2804.0)
        assert out["at_y_m"] == pytest.approx(0.1)

    def test_it_agrees_with_the_elliptic_estimate_on_a_real_aircraft(self):
        """Measured: 2804 N.m from flow5 against 2961 from the closed form."""
        s = self._strips([0.0, 2804.0, 0.0], [-16.0, 0.0, 16.0])
        out = structure.root_load(s, mass_kg=89.0, semi_span_m=16.0)
        assert out["elliptic_estimate_Nm"] == pytest.approx(2961.0, abs=5.0)
        assert out["ratio_to_estimate"] == pytest.approx(0.947, abs=0.01)
        assert "disagreement" not in out

    def test_a_load_that_cannot_be_the_same_aircraft_is_called_out(self):
        s = self._strips([0.0, 12000.0, 0.0], [-16.0, 0.0, 16.0])
        out = structure.root_load(s, mass_kg=89.0, semi_span_m=16.0)
        assert "disagreement" in out
        assert structure.warning(out) is not None

    def test_no_strips_or_no_column_means_no_claim(self):
        assert structure.root_load(None, mass_kg=89.0, semi_span_m=16.0) is None
        assert structure.root_load({"surfaces": {}}, mass_kg=89.0,
                                   semi_span_m=16.0) is None
        bare = {"surfaces": {"Main": {"y(m)": [0.0], "Cl": [1.0]}}}
        assert structure.root_load(bare, mass_kg=89.0, semi_span_m=16.0) is None

    def test_without_a_mass_the_load_is_reported_but_not_checked(self):
        s = self._strips([0.0, 2804.0, 0.0], [-16.0, 0.0, 16.0])
        out = structure.root_load(s, mass_kg=None, semi_span_m=16.0)
        assert out["root_bending_moment_Nm"] == pytest.approx(2804.0)
        assert "elliptic_estimate_Nm" not in out
        assert structure.warning(out) is None

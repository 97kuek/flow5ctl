"""The refusals. Each one exists because flow5 answers the question wrongly instead
of declining it."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from flow5ctl.advisor import dragbudget, guardrails, stability, structure
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


class TestUnsupportedPolarTypes:
    """flow5 offers T4 and T8 and neither of them works through this interface.

    They were listed as "known" polar types in the error message a user sees when
    they mistype one, and both were marked untested in FLOW5-INTERFACE.md. Running
    them settled it.
    """

    def test_t8_returns_nonsense_so_it_is_refused(self):
        """Measured: alpha 2 to 8 step 2 gave ONE point, at 2.0 m/s that nothing
        asked for, reporting L/D 68.6 for a 3 m glider."""
        with pytest.raises(UnsupportedByFlow5, match="returns nonsense"):
            guardrails.check_polar_type("T8")

    def test_t4_needs_a_speed_sweep_we_cannot_express(self):
        with pytest.raises(UnsupportedByFlow5, match="sweeps the speed"):
            guardrails.check_polar_type("T4")

    def test_t4_points_at_the_way_that_does_work(self):
        with pytest.raises(UnsupportedByFlow5, match="`sweep` on the `speed`"):
            guardrails.check_polar_type("T4")

    def test_the_types_that_do_work_are_not_refused(self):
        for pt in ("T1", "T2", "T3", "T5", "T7"):
            guardrails.check_polar_type(pt)


class TestAnalysisChecks:
    def check(self, rect, **kw):
        opts = {"polar_type": "T1", "alpha": (-2.0, 8.0, 1.0), "viscous": True,
                "on_the_fly": False, "ground_height": None}
        opts.update(kw)
        return guardrails.check_analysis(rect, presets.load("rc-glider"), **opts)

    def test_inviscid_runs_are_labelled_loudly(self, rect):
        """The figure has to be one a reader can re-run, not a remembered one.

        It used to say 93 % "at Re 2e5", from a wing nobody reading has. Measured on
        the shipped 3 m glider at alpha 0 with the current defaults: CD 0.000345
        inviscid against 0.018006 viscous, so 98 % is left out.
        """
        c = self.check(rect, viscous=False)
        assert any("INVISCID" in w for w in c.warnings)
        assert any("98 % of the drag" in w for w in c.warnings)
        assert any("shipped 3 m glider" in w for w in c.warnings)

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

    The check compares the strips against the lift at the operating point, not
    against the weight. A fixed-speed polar does not fly the aeroplane, so most of
    its points are out of balance and a weight comparison there measures the load
    factor rather than the strip table.
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
        assert structure.notes(out)

    def test_no_strips_or_no_column_means_no_claim(self):
        assert structure.root_load(None, mass_kg=89.0, semi_span_m=16.0) is None
        assert structure.root_load({"surfaces": {}}, mass_kg=89.0,
                                   semi_span_m=16.0) is None
        bare = {"surfaces": {"Main": {"y(m)": [0.0], "Cl": [1.0]}}}
        assert structure.root_load(bare, mass_kg=89.0, semi_span_m=16.0) is None

    def test_without_a_mass_or_a_lift_the_load_is_reported_but_not_checked(self):
        s = self._strips([0.0, 2804.0, 0.0], [-16.0, 0.0, 16.0])
        out = structure.root_load(s, mass_kg=None, semi_span_m=16.0)
        assert out["root_bending_moment_Nm"] == pytest.approx(2804.0)
        assert "elliptic_estimate_Nm" not in out
        assert structure.notes(out) == []

    def test_the_estimate_uses_the_lift_at_the_point_not_the_weight(self):
        """The shipped 3 m glider, measured.

        Best L/D on its fixed-speed polar sits at CL 0.7132 and 12 m/s over
        0.5551 m2, which is 34.9 N of lift against 7.8 N of weight. flow5's strips
        give 10.8 N.m there. Against the weight that is 4.3x the estimate and reads
        like a broken parser; against the lift it is 3 % - nothing is wrong.
        """
        s = self._strips([0.0, 10.8, 0.0], [-1.5, 0.006, 1.5])
        out = structure.root_load(s, mass_kg=0.8, semi_span_m=1.5, lift_N=34.9)
        assert out["elliptic_estimate_Nm"] == pytest.approx(11.1, abs=0.1)
        assert out["ratio_to_estimate"] == pytest.approx(0.97, abs=0.02)
        assert "disagreement" not in out

    def test_a_point_that_is_not_level_flight_says_so(self):
        """The same run: the load factor is the finding, not a parser fault."""
        s = self._strips([0.0, 10.8, 0.0], [-1.5, 0.006, 1.5])
        out = structure.root_load(s, mass_kg=0.8, semi_span_m=1.5, lift_N=34.9)
        assert out["load_factor"] == pytest.approx(4.45, abs=0.05)
        text = out["not_level_flight"]
        assert "4.45x the aircraft's weight" in text
        assert "not the 1 g level-flight one" in text
        # and it does not then claim that IS what a spar is sized from
        assert "not the load a spar is sized from either" in text
        assert structure.notes(out) == [text]

    def test_a_fixed_lift_polar_comes_out_at_exactly_one(self):
        """Measured end to end on the 34 m HPA example, T2, at best L/D.

        A fixed-lift polar solves the speed at every alpha so that lift equals
        weight, so the load factor has to be 1.00 by construction. It came out at
        1020.2 N of lift against 104 kg - 1020.2 N of weight, which checks the whole
        chain at once: the polar's speed column, CL, the reference area and the
        density all agreeing.
        """
        s = self._strips([0.0, 3492.4, 0.0], [-17.0, 0.033, 17.0])
        out = structure.root_load(s, mass_kg=104.0, semi_span_m=17.0, lift_N=1020.2)
        assert out["load_factor"] == pytest.approx(1.0, abs=0.005)
        assert out["estimate_from"] == "lift at this operating point"
        assert structure.notes(out) == []

    def test_the_estimate_says_the_wing_does_not_carry_quite_all_of_it(self):
        """A second reviewer's objection, measured rather than argued.

        The estimate uses the aircraft's total lift, so on a tailed layout it is
        high by the tail's share. Integrating each surface's own strips on the two
        shipped examples: the elevator carries 3.5 % on the 3 m glider at alpha 6
        and 3.2 % on the 34 m HPA at alpha 7. That is an eighth of the threshold at
        which a disagreement is reported, so it raises no false alarm - but the
        printed ratio is biased by about that much and now says so.

        It is not corrected, because splitting the total by the strips' own shares
        would check the strip table against itself and the whole value of the
        comparison is that the two sides come from different places.
        """
        s = self._strips([0.0, 2804.0, 0.0], [-16.0, 0.0, 16.0])
        out = structure.root_load(s, mass_kg=89.0, semi_span_m=16.0, lift_N=873.0)
        assert "the wing carries all of that lift" in out["estimate_assumes"]
        assert "3.2-3.5 %" in out["estimate_assumes"]
        assert "canard" in out["estimate_assumes"]

    def test_the_assumption_is_not_stated_when_no_estimate_is_made(self):
        s = self._strips([0.0, 2804.0, 0.0], [-16.0, 0.0, 16.0])
        out = structure.root_load(s, mass_kg=None, semi_span_m=16.0)
        assert "estimate_assumes" not in out

    def test_level_flight_is_silent(self):
        s = self._strips([0.0, 2804.0, 0.0], [-16.0, 0.0, 16.0])
        lift = 89.0 * 9.81
        out = structure.root_load(s, mass_kg=89.0, semi_span_m=16.0, lift_N=lift)
        assert out["load_factor"] == pytest.approx(1.0)
        assert structure.notes(out) == []

    def test_both_findings_can_be_reported_at_once(self):
        s = self._strips([0.0, 12000.0, 0.0], [-16.0, 0.0, 16.0])
        out = structure.root_load(s, mass_kg=89.0, semi_span_m=16.0, lift_N=400.0)
        assert len(structure.notes(out)) == 2


class TestStaticMarginIsChecked:
    """A negative static margin used to be reported in silence.

    The shipped HPA example analysed at -10.1 % MAC against its own declared
    requirement of 5-15 %, printed beside a lift-to-drag figure of 50.6, and nothing
    in the report said the aircraft was unflyable. `requirements.static_margin` and
    the preset bands both existed and neither was ever compared against a result.
    """

    class _S:
        def __init__(self, sm, stiffness=None):
            self.static_margin = sm
            self.pitch_stiffness_margin = stiffness

    def test_a_negative_margin_is_called_unflyable(self):
        out = stability.notes(self._S(-0.101), required=(0.05, 0.15), design="Albatross")
        assert len(out) == 1
        assert "CG is behind the neutral point" in out[0]
        assert "Albatross diverges in pitch" in out[0]
        assert "not flyable" in out[0]
        assert "--target static-margin" in out[0]

    def test_the_cg_height_term_does_not_rescue_a_negative_margin(self):
        """The HPA case exactly: classical -10.1 %, pitch stiffness +3.4 %."""
        out = stability.notes(self._S(-0.101, 0.034), required=(0.05, 0.15))
        assert "not flyable" in out[0]
        assert "+3.4%" in out[0]
        assert "not a substitute" in out[0]

    def test_a_margin_inside_the_band_says_nothing(self):
        assert stability.notes(self._S(0.10), required=(0.05, 0.15)) == []

    def test_below_the_band_is_reported_against_the_design_s_own_requirement(self):
        out = stability.notes(self._S(0.02), required=(0.05, 0.15),
                              preset_band=(0.05, 0.12))
        assert "this design asks for 5%-15%" in out[0]
        assert "It is stable, but" in out[0]

    def test_without_a_requirement_the_preset_band_is_used_and_named(self):
        out = stability.notes(self._S(0.02), preset_band=(0.05, 0.12))
        assert "the preset for this class expects 5%-12%" in out[0]

    def test_over_stable_is_worth_saying_too(self):
        out = stability.notes(self._S(0.30), required=(0.05, 0.15))
        assert "Over-stable costs trim drag" in out[0]

    def test_no_margin_means_no_claim(self):
        assert stability.notes(self._S(None), required=(0.05, 0.15)) == []

    def test_no_band_anywhere_still_catches_instability(self):
        assert stability.notes(self._S(-0.01)) != []
        assert stability.notes(self._S(0.30)) == []


class TestSpanwiseMesh:
    """Induced drag is set by the span, and a coarse span makes it optimistic.

    A rectangular wing came back with a span efficiency of 1.008-1.012, which is
    impossible for a planar wing, and that was recorded in the design guide as
    evidence that induced drag was only good to +-5 %. It was the mesh. Refining the
    span makes it fall monotonically below 1, at AR 10 and at AR 40 alike, and
    chordwise panels make no difference at all.
    """

    def _design(self, spanwise: int) -> Design:
        return Design.model_validate({
            "name": "M", "preset": "custom",
            "requirements": {"cruise_speed": 15.0},
            "mass": {"components": [{"tag": "b", "mass": 1.0, "at": [0.05, 0.0, 0.0]}]},
            "airfoils": [{"name": "NACA0012", "source": "naca:0012"}],
            "wing": {"airfoil": "NACA0012",
                     "planform": {"span": 2.0, "root_chord": 0.2},
                     "panels": {"chordwise": 13, "spanwise": spanwise}},
        })

    def _notes(self, spanwise: int) -> list[str]:
        d = geometry.solve(self._design(spanwise))
        return guardrails.check_geometry(d, presets.load("custom")).notes

    def test_a_coarse_span_is_called_out(self):
        text = " ".join(self._notes(20))
        assert "20 spanwise panels per semi-span" in text
        assert "impossible" in text
        assert "Chordwise panels do not help" in text

    def test_an_adequate_span_says_nothing_about_the_mesh(self):
        assert not any("spanwise panels" in n for n in self._notes(40))

    def test_the_default_is_no_longer_the_coarse_one(self):
        """20 was the default and 20 is measurably wrong, so the default moved."""
        d = Design.model_validate({
            "name": "M", "preset": "custom",
            "requirements": {"cruise_speed": 15.0},
            "mass": {"components": [{"tag": "b", "mass": 1.0, "at": [0.05, 0.0, 0.0]}]},
            "airfoils": [{"name": "NACA0012", "source": "naca:0012"}],
            "wing": {"airfoil": "NACA0012",
                     "planform": {"span": 2.0, "root_chord": 0.2}},
        })
        assert d.wing.panels.spanwise == 40
        assert d.wing.panels.spanwise >= guardrails.MIN_SPANWISE


class TestMoreThanThreeSurfaces:
    """A tandem, a biplane and a canard-plus-tail need a fourth lifting surface.

    The schema was fixed at wing, elevator and fin, so none of them could be
    expressed. flow5 has no such cap - its plane reader calls addWing() once per
    <wing> element and dispatches on nothing else - and the twin-fin work already
    proved extra surfaces solve correctly.
    """

    def _tandem(self, **extra) -> dict:
        surface = {"name": "Rear Wing", "airfoil": "NACA0012",
                   "position": [1.3, 0.0, 0.1],
                   "planform": {"span": 1.8, "root_chord": 0.18}}
        surface.update(extra)
        return {
            "name": "T", "preset": "custom", "requirements": {"cruise_speed": 15.0},
            "mass": {"components": [{"tag": "b", "mass": 1.0, "at": [0.4, 0.0, 0.0]}]},
            "airfoils": [{"name": "NACA0012", "source": "naca:0012"}],
            "wing": {"name": "Front Wing", "airfoil": "NACA0012",
                     "planform": {"span": 2.0, "root_chord": 0.2}},
            "extra_surfaces": [surface],
        }

    def test_a_fourth_surface_is_accepted_and_carried_through(self):
        d = Design.model_validate(self._tandem())
        assert [w.name for w in d.surfaces()] == ["Front Wing", "Rear Wing"]
        assert d.extra_surfaces[0].role == "other"
        assert d.extra_surfaces[0].symmetric is True

    def test_it_reaches_the_geometry_and_the_panel_count(self):
        d = geometry.solve(Design.model_validate(self._tandem()))
        assert len(d.surfaces) == 2
        assert d.panel_count == sum(s.geom.panel_count for s in d.surfaces)
        # coefficients stay referenced to the main wing, as flow5 does
        assert d.reference_span == pytest.approx(2.0)

    def test_an_unnamed_surface_is_refused(self):
        raw = self._tandem()
        del raw["extra_surfaces"][0]["name"]
        with pytest.raises(ValidationError, match="needs a `name`"):
            Design.model_validate(raw)

    def test_a_duplicate_name_is_refused(self):
        raw = self._tandem()
        raw["extra_surfaces"][0]["name"] = "Front Wing"
        with pytest.raises(ValidationError, match="both called"):
            Design.model_validate(raw)

    def test_a_pair_on_the_centreline_is_refused(self):
        raw = self._tandem(count=2)
        with pytest.raises(ValidationError, match="half-spacing"):
            Design.model_validate(raw)

    def test_tail_volume_is_flagged_as_the_wrong_measure(self):
        raw = self._tandem()
        raw["tail"] = {"type": "conventional", "fin": {
            "name": "Fin", "airfoil": "NACA0012", "position": [1.45, 0.0, 0.12],
            "planform": {"span": 0.25, "root_chord": 0.15}}}
        d = geometry.solve(Design.model_validate(raw))
        text = " ".join(guardrails.check_geometry(d, presets.load("custom")).notes)
        assert "Rear Wing" in text
        assert "one wing and one tail" in text

    def test_the_elliptic_cross_check_is_withheld_when_lift_is_shared(self):
        """Measured on the tandem: the check reported 1.49x and nothing was wrong.

        The closed form assumes the wing carries all the lift. On a tandem it
        carries an unknown share of it, so the estimate is against the wrong number.
        """
        s = {"alpha": 0.0, "surfaces": {"Main": {"y(m)": [-1.0, 0.0, 1.0],
                                                 "Bending.mom": [0.0, 1.0, 0.0]}}}
        out = structure.root_load(s, mass_kg=4.0, semi_span_m=1.0, lift_N=3.2,
                                  shared_lift=True)
        assert out["root_bending_moment_Nm"] == pytest.approx(1.0)
        assert "elliptic_estimate_Nm" not in out
        assert "ratio_to_estimate" not in out
        assert "more than one lifting wing" in out["cross_check"]
        # the load factor is still a real finding and is still reported
        assert out["load_factor"] == pytest.approx(0.08, abs=0.01)


class TestTheWakeIsSetInSpans:
    """flow5's default wake is 30 x MAC, which is 30/AR spans - short on a slender
    wing, and the induced drag comes out low as a result.

    This was published as "flow5's induced drag is low, increasingly with aspect
    ratio" in 0.1.0. It was not: the error depends on the wake length in spans and
    not on aspect ratio at all. Measured on elliptic wings, where the exact answer
    is a span efficiency of 1.0 and no planar wing can beat it:

    | wake (spans) | AR 10 | AR 20 | AR 30 | AR 40 | AR 50 |
    |---|---|---|---|---|---|
    | 0.75 | 1.2238 | 1.2154 | 1.2126 | 1.2103 | 1.2095 |
    | 3    | 1.0240 | 1.0238 | 1.0229 | 1.0217 | 1.0214 |
    | 10   | 1.0039 | 1.0038 | 1.0030 | 1.0019 | 1.0016 |
    | 30   | 1.0020 | 1.0019 | 1.0011 | 1.0000 | 0.9997 |
    """

    def _xml(self, span: float, chord: float, wake_spans: float | None = None) -> str:
        from flow5ctl.flow5 import xmlgen
        d = geometry.solve(Design.model_validate({
            "name": "W", "preset": "custom", "requirements": {"cruise_speed": 10.0},
            "mass": {"components": [{"tag": "b", "mass": 1.0, "at": [0.1, 0.0, 0.0]}]},
            "airfoils": [{"name": "N", "source": "naca:0012"}],
            "wing": {"airfoil": "N", "planform": {"span": span, "root_chord": chord}},
        }))
        kw = {} if wake_spans is None else {"wake_spans": wake_spans}
        spec = xmlgen.AnalysisSpec(name="p", speed=10.0, **kw)
        return xmlgen.polar_xml(spec, "W", d)

    def _length_factor(self, xml: str) -> float:
        import re
        return float(re.search(r"<LengthFactor>([\d.]+)</LengthFactor>", xml).group(1))

    def test_a_wake_block_is_emitted_at_all(self):
        """flow5 defaults to 30 x MAC if we say nothing, which is the trap."""
        xml = self._xml(34.0, 0.85)
        assert "<Wake>" in xml and "<FlatPanelWake>true</FlatPanelWake>" in xml

    def test_the_length_scales_with_aspect_ratio(self):
        """LengthFactor is in MAC units, so spans x AR keeps the physical wake fixed."""
        assert self._length_factor(self._xml(34.0, 0.85)) == pytest.approx(20 * 40, rel=1e-3)
        assert self._length_factor(self._xml(2.0, 0.2)) == pytest.approx(20 * 10, rel=1e-3)

    def test_it_is_never_shorter_than_flow5_s_own_default(self):
        """A stubby wing must not end up with less wake than doing nothing gave."""
        assert self._length_factor(self._xml(1.0, 1.0)) >= 30.0

    def test_the_caller_can_ask_for_more(self):
        assert self._length_factor(self._xml(34.0, 0.85, wake_spans=30.0)) == \
            pytest.approx(30 * 40, rel=1e-3)


class TestWakePlane:
    """A tail level with the wing sits in its trailing vortex sheet.

    The wing's trailing vortices leave at its own height and run downstream; a
    horizontal tail at exactly that height has its control points on the sheet,
    which is singular. flow5 does not complain - it returns a number, and the number
    is out by a factor of two in the optimistic direction.

    Measured on an AR 12 wing of 0.25 m chord with a 0.9 x 0.15 m tail 1.2 m behind,
    inviscid at alpha 6, moving only the tail's z: induced drag 0.00483 at z = 0
    (span efficiency 1.93, which is impossible), 0.00977 at z = 0.02, which then
    matches AVL within 3 %. Two centimetres doubled it.
    """

    def _design(self, tail_z: float, tail_x: float = 1.2) -> Design:
        return Design.model_validate({
            "name": "W", "preset": "custom", "requirements": {"cruise_speed": 15.0},
            "mass": {"components": [{"tag": "b", "mass": 1.0, "at": [0.05, 0.0, 0.0]},
                                    {"tag": "l", "mass": 0.2, "at": [0.05, -1.0, 0.0]},
                                    {"tag": "r", "mass": 0.2, "at": [0.05, 1.0, 0.0]}]},
            "airfoils": [{"name": "N", "source": "naca:0012"}],
            "wing": {"airfoil": "N", "planform": {"span": 3.0, "root_chord": 0.25}},
            "tail": {"type": "conventional", "elevator": {
                "airfoil": "N", "position": [tail_x, 0.0, tail_z],
                "planform": {"span": 0.9, "root_chord": 0.15}}},
        })

    def _warnings(self, **kw) -> str:
        d = geometry.solve(self._design(**kw))
        return " ".join(guardrails.check_geometry(d, presets.load("custom")).warnings)

    def test_a_tail_level_with_the_wing_is_called_out(self):
        text = self._warnings(tail_z=0.0)
        assert "trailing vortex sheet" in text
        assert "impossible" in text

    def test_an_offset_of_a_tenth_of_the_mac_is_enough(self):
        # MAC is 0.25, so 0.03 is 12 % - past the measured convergence at 8 %
        assert "trailing vortex sheet" not in self._warnings(tail_z=0.03)

    def test_a_hair_off_the_plane_is_still_called_out(self):
        """0.005 m is 2 % of chord, where the span efficiency still read 0.996."""
        assert "trailing vortex sheet" in self._warnings(tail_z=0.005)

    def test_a_surface_ahead_of_the_wing_is_not_in_its_wake(self):
        assert "trailing vortex sheet" not in self._warnings(tail_z=0.0, tail_x=-0.6)

    def test_a_fin_is_vertical_and_has_no_such_plane(self):
        d = geometry.solve(Design.model_validate({
            "name": "W", "preset": "custom", "requirements": {"cruise_speed": 15.0},
            "mass": {"components": [{"tag": "b", "mass": 1.0, "at": [0.05, 0.0, 0.0]},
                                    {"tag": "l", "mass": 0.2, "at": [0.05, -1.0, 0.0]},
                                    {"tag": "r", "mass": 0.2, "at": [0.05, 1.0, 0.0]}]},
            "airfoils": [{"name": "N", "source": "naca:0012"}],
            "wing": {"airfoil": "N", "planform": {"span": 3.0, "root_chord": 0.25}},
            "tail": {"type": "conventional", "fin": {
                "airfoil": "N", "position": [1.2, 0.0, 0.0],
                "planform": {"span": 0.3, "root_chord": 0.18}}},
        }))
        text = " ".join(guardrails.check_geometry(d, presets.load("custom")).warnings)
        assert "trailing vortex sheet" not in text

    def test_the_shipped_examples_are_clear_of_it(self):
        import pathlib

        import yaml
        root = pathlib.Path(__file__).resolve().parent.parent / "examples"
        for name in ("rc-glider.yaml", "hpa.yaml"):
            raw = yaml.safe_load((root / name).read_text(encoding="utf-8"))
            raw["name"] = name
            d = geometry.solve(Design.model_validate(raw))
            text = " ".join(guardrails.check_geometry(d, presets.load(d_preset := raw.get("preset", "custom"))).warnings)
            assert "trailing vortex sheet" not in text, f"{name} ({d_preset})"

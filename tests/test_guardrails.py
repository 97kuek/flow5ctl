"""The refusals. Each one exists because flow5 answers the question wrongly instead
of declining it."""
from __future__ import annotations

import pytest

from flow5ctl.advisor import guardrails
from flow5ctl.errors import DesignError, UnsupportedByFlow5
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

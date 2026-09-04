"""Trim solving and parameter sweeps.

The pure-maths parts are tested without flow5; the solver paths are marked.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import ClassVar

import pytest

from flow5ctl.errors import DesignError, SolverError
from flow5ctl.model.design import Design
from flow5ctl.project.store import Project
from flow5ctl.usecases import analyze, define, ground
from flow5ctl.usecases import sweep as sweep_uc
from flow5ctl.usecases import trim as trim_uc


@pytest.fixture(autouse=True)
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("FLOW5CTL_WORKSPACE", str(tmp_path / "ws"))


@pytest.fixture
def project(rect_design):
    define.create("Rect", rect_design)
    return Project.resolve("Rect")


class TestInterpolation:
    def test_solves_for_x_at_a_target_y(self):
        assert trim_uc._interpolate([0.0, 2.0, 4.0], [0.0, 0.2, 0.4], 0.1) == pytest.approx(1.0)

    def test_evaluates_y_at_a_given_x(self):
        assert trim_uc._interp_at([0.0, 2.0, 4.0], [0.0, 0.2, 0.4], 1.0) == pytest.approx(0.1)

    def test_never_extrapolates(self):
        assert trim_uc._interp_at([0.0, 2.0], [0.0, 0.2], 5.0) is None
        assert trim_uc._interpolate([0.0, 2.0], [0.0, 0.2], 0.1) == pytest.approx(1.0)
        assert trim_uc._interpolate([0.0, 2.0], [0.0, 0.2], 0.9) is None

    def test_ignores_non_finite_points(self):
        xs = [0.0, 1.0, 2.0]
        ys = [0.0, math.inf, 0.2]
        assert trim_uc._interp_at(xs, ys, 1.5) is not None


class TestRequiredCl:
    def test_matches_the_lift_equation(self):
        cl = trim_uc.required_cl(mass=1.0, density=1.225, area=0.4, speed=15.0)
        expected = 1.0 * 9.80665 / (0.5 * 1.225 * 15.0**2 * 0.4)
        assert cl == pytest.approx(expected)

    def test_halving_the_speed_quadruples_the_required_cl(self):
        a = trim_uc.required_cl(1.0, 1.225, 0.4, 20.0)
        b = trim_uc.required_cl(1.0, 1.225, 0.4, 10.0)
        assert b / a == pytest.approx(4.0)

    def test_zero_speed_is_refused(self):
        with pytest.raises(DesignError, match="zero speed"):
            trim_uc.required_cl(1.0, 1.225, 0.4, 0.0)


class TestTrimValidation:
    def test_cl_target_needs_a_value(self, project):
        with pytest.raises(DesignError, match="--value"):
            trim_uc.trim(project, trim_uc.TrimRequest(target="cl", speed=15.0))

    def test_speed_target_needs_an_alpha(self, project):
        with pytest.raises(DesignError, match="--alpha"):
            trim_uc.trim(project, trim_uc.TrimRequest(target="speed"))

    def test_pitch_trim_needs_an_elevator(self, project):
        with pytest.raises(DesignError, match="no elevator"):
            trim_uc.trim(project, trim_uc.TrimRequest(target="pitch", speed=15.0))

    def test_an_unknown_target_is_refused(self, project):
        with pytest.raises(DesignError, match="unknown trim target"):
            trim_uc.trim(project, trim_uc.TrimRequest(target="banana"))  # type: ignore[arg-type]


class TestSweepValues:
    @pytest.mark.parametrize("spec,expected", [
        ("0.3,0.4,0.5", [0.3, 0.4, 0.5]),
        ("0.3, 0.4", [0.3, 0.4]),
        ("0:1:3", [0.0, 0.5, 1.0]),
        ("-4:0:5", [-4.0, -3.0, -2.0, -1.0, 0.0]),
    ])
    def test_parsing(self, spec, expected):
        assert sweep_uc.parse_values(spec) == pytest.approx(expected)

    def test_a_single_value_is_not_a_sweep(self):
        with pytest.raises(DesignError, match="at least two"):
            sweep_uc.parse_values("0.5")

    def test_a_malformed_range_says_the_shape(self):
        with pytest.raises(DesignError, match="from:to:steps"):
            sweep_uc.parse_values("0:1")


class TestSweepPaths:
    @pytest.fixture
    def data(self, rect_design):
        """What `sweep` actually operates on: a full dump, so schema fields the user
        never wrote are still present with their defaults and can be varied."""
        from flow5ctl.model.design import Design
        return Design.model_validate(rect_design).model_dump(
            mode="json", by_alias=True, exclude_none=True)

    def test_setting_an_existing_path(self, data):
        out = sweep_uc._set_path(data, "wing.planform.span", 4.0)
        assert out["wing"]["planform"]["span"] == 4.0
        assert data["wing"]["planform"]["span"] == 2.0            # input untouched

    def test_a_defaulted_field_the_user_never_wrote_can_still_be_varied(self, data,
                                                                       rect_design):
        assert "taper" not in rect_design["wing"]["planform"]
        out = sweep_uc._set_path(data, "wing.planform.taper", 0.5)
        assert out["wing"]["planform"]["taper"] == 0.5

    def test_a_missing_path_is_refused(self, data):
        with pytest.raises(DesignError, match="does not exist"):
            sweep_uc._set_path(data, "wing.planform.nope", 1.0)

    def test_a_list_index_works(self, data):
        out = sweep_uc._set_path(data, "mass.components.0.mass", 2.0)
        assert out["mass"]["components"][0]["mass"] == 2.0

    def test_analysis_parameters_are_recognised(self):
        assert "cg_x" in sweep_uc.ANALYSIS_PARAMS
        assert "wing.planform.taper" not in sweep_uc.ANALYSIS_PARAMS


class TestSweepMetrics:
    SUMMARY: ClassVar[dict] = {
        "best_LD": {"value": 20.0, "alpha": 4.0}, "static_margin": 0.1,
        "min_sink": {"value": 0.3, "speed": 8.0}, "ld_at_trim": 15.0,
    }

    @pytest.mark.parametrize("metric,expected", [
        ("best_LD", 20.0), ("best_LD_alpha", 4.0), ("static_margin", 0.1),
        ("min_sink", 0.3), ("min_sink_speed", 8.0), ("ld_at_trim", 15.0),
    ])
    def test_reading(self, metric, expected):
        assert sweep_uc._metric(self.SUMMARY, metric) == pytest.approx(expected)

    def test_a_missing_metric_is_none_not_an_error(self):
        assert sweep_uc._metric(self.SUMMARY, "trim_alpha") is None

    def test_an_unknown_metric_lists_the_available_ones(self):
        with pytest.raises(DesignError, match="Available"):
            sweep_uc._metric(self.SUMMARY, "vibes")

    def test_cg_sweeps_know_which_metrics_are_blind_to_cg(self):
        blind = sweep_uc.INSENSITIVE["cg_x"]
        assert "best_LD" in blind
        assert "ld_at_trim" not in blind
        assert "static_margin" not in blind

    def test_washout_carries_a_tradeoff_note(self):
        assert "tip-stall" in sweep_uc.TRADEOFF_NOTES["washout"]


class TestStudyFiles:
    def test_loading_a_study(self, tmp_path):
        path = tmp_path / "cg.yaml"
        path.write_text(
            "name: cg-sweep\n"
            "vary:\n  parameter: cg_x\n  from: 0.03\n  to: 0.09\n  steps: 4\n"
            "analysis:\n  type: T1\n  speed: 12.0\n  alpha: [-2, 8, 2]\n"
            "report:\n  metrics: [static_margin, ld_at_trim]\n",
            encoding="utf-8")
        req = sweep_uc.load_study(path)
        assert req.name == "cg-sweep"
        assert req.parameter == "cg_x"
        assert req.values == pytest.approx([0.03, 0.05, 0.07, 0.09])
        assert req.analysis.speed == pytest.approx(12.0)
        assert req.analysis.alpha == (-2, 8, 2)
        assert req.metrics == ("static_margin", "ld_at_trim")

    def test_explicit_values_also_work(self, tmp_path):
        path = tmp_path / "s.yaml"
        path.write_text("vary:\n  parameter: cg_x\n  values: [0.04, 0.06]\n", encoding="utf-8")
        assert sweep_uc.load_study(path).values == pytest.approx([0.04, 0.06])

    def test_a_study_without_values_is_refused(self, tmp_path):
        path = tmp_path / "s.yaml"
        path.write_text("vary:\n  parameter: cg_x\n", encoding="utf-8")
        with pytest.raises(DesignError, match="values"):
            sweep_uc.load_study(path)


# --------------------------------------------------------------------- with flow5

@pytest.mark.needs_flow5
class TestTrimAgainstFlow5:
    @pytest.fixture(autouse=True)
    def _flow5(self):
        from flow5ctl.errors import SolverNotFound
        from flow5ctl.flow5 import probe as probe_mod
        try:
            probe_mod.probe()
        except SolverNotFound as exc:
            pytest.skip(str(exc))

    def test_level_flight_alpha_produces_the_required_lift(self, project):
        out = trim_uc.trim(project, trim_uc.TrimRequest(
            target="level", speed=15.0, alpha_range=(0.0, 8.0, 2.0), viscous=False))
        solved = out["solved"]
        expected_cl = trim_uc.required_cl(1.0, 1.225, 0.4, 15.0)
        assert solved["cl"] == pytest.approx(expected_cl, rel=1e-3)
        assert 0.0 < solved["alpha"] < 8.0
        # the refine pass returns the solver's own values, not an interpolation
        assert out["values_are_exact"] is True
        assert abs(out["cl_residual"]) < 0.02

    def test_a_target_cl_outside_the_sweep_says_so(self, project):
        with pytest.raises(SolverError, match="not reached"):
            trim_uc.trim(project, trim_uc.TrimRequest(
                target="cl", value=3.0, speed=15.0,
                alpha_range=(0.0, 4.0, 2.0), viscous=False))

    def test_the_cg_for_a_target_static_margin_is_solved_in_two_runs(self, project):
        out = trim_uc.trim(project, trim_uc.TrimRequest(
            target="static_margin", value=0.10, speed=15.0,
            alpha_range=(0.0, 8.0, 2.0), viscous=False))
        assert out["solver_runs"] == 2
        assert out["solved"]["static_margin"] == pytest.approx(0.10, abs=0.01)
        # the neutral point does not depend on the CG, which is what makes this exact
        np_x = out["solved"]["neutral_point_x"]
        cg = out["solved"]["cg_x"]
        assert cg == pytest.approx(np_x - 0.10 * 0.2, abs=1e-3)

    def test_speed_for_level_flight_at_an_angle(self, project):
        out = trim_uc.trim(project, trim_uc.TrimRequest(
            target="speed", alpha=4.0, speed=15.0,
            alpha_range=(0.0, 8.0, 2.0), viscous=False))
        v = out["solved"]["speed"]
        cl = out["solved"]["cl"]
        # L = W at the solved speed
        lift = 0.5 * 1.225 * v * v * 0.4 * cl
        assert lift == pytest.approx(1.0 * 9.80665, rel=1e-3)


@pytest.mark.needs_flow5
class TestSweepAgainstFlow5:
    @pytest.fixture(autouse=True)
    def _flow5(self):
        from flow5ctl.errors import SolverNotFound
        from flow5ctl.flow5 import probe as probe_mod
        try:
            probe_mod.probe()
        except SolverNotFound as exc:
            pytest.skip(str(exc))

    def test_a_cg_sweep_moves_the_static_margin_linearly(self, project):
        from flow5ctl.usecases.analyze import Request
        out = sweep_uc.sweep(project, sweep_uc.SweepRequest(
            parameter="cg_x", values=[0.03, 0.05, 0.07], name="cg",
            analysis=Request(polar_type="T1", speed=15.0, alpha=(0.0, 8.0, 2.0),
                             viscous=False),
            metrics=("static_margin", "ld_at_trim")))
        margins = [r["static_margin"] for r in out["rows"]]
        assert len(margins) == 3
        assert margins[0] > margins[1] > margins[2]
        # linear in CG, with slope -1/MAC
        slope = (margins[2] - margins[0]) / (0.07 - 0.03)
        assert slope == pytest.approx(-1 / 0.2, rel=0.05)

    def test_a_cg_sweep_warns_that_best_ld_is_blind_to_cg(self, project):
        from flow5ctl.usecases.analyze import Request
        out = sweep_uc.sweep(project, sweep_uc.SweepRequest(
            parameter="cg_x", values=[0.04, 0.06], name="cg2",
            analysis=Request(polar_type="T1", speed=15.0, alpha=(0.0, 8.0, 2.0),
                             viscous=False),
            metrics=("best_LD", "static_margin")))
        assert any("do not respond to cg_x" in w for w in out["warnings"])

    def test_a_design_sweep_does_not_touch_design_yaml(self, project):
        from flow5ctl.usecases.analyze import Request
        original = project.design_path.read_text(encoding="utf-8")
        sweep_uc.sweep(project, sweep_uc.SweepRequest(
            parameter="wing.planform.taper", values=[0.6, 0.8], name="taper",
            analysis=Request(polar_type="T1", speed=15.0, alpha=(0.0, 6.0, 3.0),
                             viscous=False),
            metrics=("best_LD",)))
        assert project.design_path.read_text(encoding="utf-8") == original

    def test_a_taper_sweep_changes_the_geometry_and_the_result(self, project):
        from flow5ctl.usecases.analyze import Request
        out = sweep_uc.sweep(project, sweep_uc.SweepRequest(
            parameter="wing.planform.taper", values=[0.4, 1.0], name="taper2",
            analysis=Request(polar_type="T1", speed=15.0, alpha=(0.0, 6.0, 3.0),
                             viscous=False),
            metrics=("cl_alpha", "best_LD")))
        assert out["rows"][0]["cl_alpha"] != out["rows"][1]["cl_alpha"]
        assert (project.results / "study-taper2.json").is_file()

    def test_results_are_written_for_later_reference(self, project):
        from flow5ctl.usecases.analyze import Request
        out = sweep_uc.sweep(project, sweep_uc.SweepRequest(
            parameter="cg_x", values=[0.04, 0.06], name="stored",
            analysis=Request(polar_type="T1", speed=15.0, alpha=(0.0, 6.0, 3.0),
                             viscous=False),
            metrics=("static_margin",)))
        assert (project.root / out["data"]).is_file()


class TestStripOperatingPoint:
    """A spanwise distribution has to be read at the angle the report is about.

    flow5 pads the angle in an operating-point filename with a space, so a sweep of
    -2..8 sorts as ' 0_00', ' 2_00', ' 4_00', ' 6_00', ' 8_00', '-2_00' - every
    negative angle after every positive one. Taking the middle FILE therefore took
    6.0 degrees out of that sweep, six degrees from where best L/D fell, and nothing
    in the output said which angle had been used.
    """

    def test_the_angle_is_read_out_of_the_filename(self):
        for name, want in ((" 0_00°_ 7_60m_s.csv", 0.0),
                           (" 6_00°_ 7_60m_s.csv", 6.0),
                           ("-2_00°_ 7_60m_s.csv", -2.0),
                           ("-2_50°_ 8_00m_s.csv", -2.5)):
            assert analyze._oppoint_alpha(Path(name)) == pytest.approx(want)

    def test_an_unparseable_name_is_not_guessed_at(self):
        assert analyze._oppoint_alpha(Path("summary.csv")) is None

    def test_a_filename_sort_puts_the_negative_angles_last(self):
        """The bug in one line - this ordering is why the middle file was 6 degrees."""
        names = sorted([" 0_00°_x.csv", " 2_00°_x.csv", " 4_00°_x.csv",
                        " 6_00°_x.csv", " 8_00°_x.csv", "-2_00°_x.csv"])
        assert names[len(names) // 2] == " 6_00°_x.csv"
        by_angle = sorted(analyze._oppoint_alpha(Path(n)) for n in names)
        assert by_angle[len(by_angle) // 2] == 4.0   # the middle ANGLE


class TestGroundEffectComparison:
    """Free-air and in-ground-effect from one call.

    Doing it by hand means running the same analysis twice and changing exactly one
    flag. Getting that wrong is silent: two runs at the same height report no
    difference, which reads like "ground effect does not matter here" rather than
    like a mistake. On a Birdman Rally aircraft it matters a great deal - measured
    on a reconstructed 32 m machine at h = 2 m, best L/D went 28.83 to 31.43.
    """

    def test_only_the_ground_settings_and_the_name_change(self):
        req = analyze.Request(name="cruise", polar_type="T1", speed=7.2,
                              alpha=(-2.0, 8.0, 2.0), mass=89.0)
        free = ground.replace_ground(req, effect=False, height=None, suffix="__free")
        near = ground.replace_ground(req, effect=True, height=2.0, suffix=None)
        assert free.ground_effect is False and free.ground_height is None
        assert near.ground_effect is True and near.ground_height == 2.0
        assert free.name == "cruise__free" and near.name == "cruise"
        for field in ("polar_type", "speed", "alpha", "mass"):
            assert getattr(free, field) == getattr(near, field) == getattr(req, field)

    def test_the_percentage_is_signed_from_free_air(self):
        assert ground._pct(28.83, 31.43) == pytest.approx(9.0, abs=0.1)
        assert ground._pct(0.2394, 0.2142) == pytest.approx(-10.5, abs=0.1)

    def test_a_missing_or_zero_baseline_gives_no_percentage(self):
        assert ground._pct(None, 31.4) is None
        assert ground._pct(28.8, None) is None

    def _design(self, rect_design, preset="custom", height=None) -> Design:
        raw = dict(rect_design)
        raw["preset"] = preset
        raw["requirements"] = dict(raw.get("requirements") or {})
        if height is not None:
            raw["requirements"]["ground_effect_height"] = height
        return Design.model_validate(raw)

    def test_the_design_s_own_height_is_found(self, rect_design):
        """The bug: this was never consulted, so the feature built for HPAs refused
        to run on an HPA and blamed the preset the design was already using."""
        d = self._design(rect_design, height=2.0)
        assert ground.resolve_height(d, analyze.Request()) == pytest.approx(2.0)

    def test_the_hpa_preset_supplies_one_when_the_design_does_not(self, rect_design):
        d = self._design(rect_design, preset="hpa")
        assert ground.resolve_height(d, analyze.Request()) == pytest.approx(1.5)

    def test_an_explicit_height_wins_over_both(self, rect_design):
        d = self._design(rect_design, preset="hpa", height=2.0)
        assert ground.resolve_height(d, analyze.Request(), 0.8) == pytest.approx(0.8)

    def test_the_request_wins_over_the_design(self, rect_design):
        d = self._design(rect_design, height=2.0)
        req = analyze.Request(ground_height=3.0)
        assert ground.resolve_height(d, req) == pytest.approx(3.0)

    def test_with_nowhere_to_get_one_it_says_where_to_put_it(self, rect_design):
        d = self._design(rect_design)
        with pytest.raises(DesignError, match="requirements.ground_effect_height"):
            ground.resolve_height(d, analyze.Request())

    def test_a_height_at_or_below_the_surface_is_refused(self, rect_design):
        d = self._design(rect_design)
        with pytest.raises(DesignError, match="must be positive"):
            ground.resolve_height(d, analyze.Request(), 0.0)
        assert ground._pct(0.0, 31.4) is None


class TestTrimmedSweeps:
    """A fixed-speed sweep reports numbers from a condition the aircraft never flies.

    It holds the speed and sweeps alpha, so at almost every point the lift does not
    equal the weight and the pitching moment is not zero. Best L/D off such a polar
    is the best point of a flight condition that does not exist. A trimmed sweep
    runs each point as a fixed-lift polar, so the speed is solved to carry the
    weight, and reads the metrics where Cm crosses zero.
    """

    def _tailed(self, rect_design) -> Design:
        raw = dict(rect_design)
        raw["tail"] = {"type": "conventional", "elevator": {
            "airfoil": "NACA0012", "position": [0.6, 0.0, 0.05],
            "planform": {"span": 0.5, "root_chord": 0.1}}}
        return Design.model_validate(raw)

    def test_it_switches_the_polar_and_the_metrics_together(self, rect_design):
        req = sweep_uc.SweepRequest(parameter="cg_x", values=[0.04, 0.06],
                                    analysis=analyze.Request(polar_type="T1"),
                                    trimmed=True)
        note = sweep_uc._apply_trimmed(req, self._tailed(rect_design))
        assert req.analysis.polar_type == "T2"
        assert req.metrics == sweep_uc.TRIMMED_METRICS
        assert "best_LD" not in req.metrics
        assert "fixed-lift" in note and "Cm crosses zero" in note

    def test_metrics_the_caller_chose_are_left_alone(self, rect_design):
        req = sweep_uc.SweepRequest(parameter="cg_x", values=[0.04, 0.06],
                                    metrics=("static_margin",), trimmed=True)
        sweep_uc._apply_trimmed(req, self._tailed(rect_design))
        assert req.metrics == ("static_margin",)

    def test_without_an_elevator_there_is_nothing_to_trim_against(self, rect_design):
        req = sweep_uc.SweepRequest(parameter="cg_x", values=[0.04, 0.06], trimmed=True)
        with pytest.raises(DesignError, match="no elevator"):
            sweep_uc._apply_trimmed(req, Design.model_validate(rect_design))

    def test_an_untrimmed_sweep_is_untouched(self, rect_design):
        req = sweep_uc.SweepRequest(parameter="cg_x", values=[0.04, 0.06],
                                    analysis=analyze.Request(polar_type="T1"))
        assert sweep_uc._apply_trimmed(req, Design.model_validate(rect_design)) is None
        assert req.analysis.polar_type == "T1"
        assert req.metrics == sweep_uc.DEFAULT_METRICS

    def test_the_note_says_what_it_is_not(self, rect_design):
        """A second reviewer: "level, trimmed numbers" was stronger than the logic.

        It is an estimate of the trimmed condition, not a solve of it - the elevator
        sits where the design puts it, the Cm crossing is interpolated between the
        alpha points asked for, and the mass is held while the geometry changes.
        """
        req = sweep_uc.SweepRequest(parameter="cg_x", values=[0.04, 0.06],
                                    trimmed=True)
        note = sweep_uc._apply_trimmed(req, self._tailed(rect_design))
        assert "nothing solves for the incidence" in note
        assert "interpolated between the alpha points" in note
        assert "mass is held fixed" in note
        assert "trim --target pitch" in note

    def test_the_caller_s_request_is_not_rewritten(self, project):
        """`_apply_trimmed` changes the polar type and the metrics in place.

        No caller here reuses its request, but one that did would find T2 and the
        trimmed metrics still set after turning `trimmed` off. `sweep` copies.
        """
        req = sweep_uc.SweepRequest(parameter="cg_x", values=[0.04, 0.06],
                                    analysis=analyze.Request(polar_type="T1"),
                                    trimmed=True)
        import contextlib
        # the solver may be absent or refuse; the copy is what is being checked
        with contextlib.suppress(Exception):
            sweep_uc.sweep(project, req)
        assert req.analysis.polar_type == "T1"
        assert req.metrics == sweep_uc.DEFAULT_METRICS

    def test_a_study_file_can_ask_for_it(self, tmp_path):
        path = tmp_path / "t.yaml"
        path.write_text("name: t\nvary:\n  parameter: cg_x\n  values: [0.04, 0.06]\n"
                        "analysis:\n  trimmed: true\n", encoding="utf-8")
        assert sweep_uc.load_study(path).trimmed is True


class TestRepeatedWarningsAreCollapsed:
    """Every point of a sweep runs a full analysis and warns about the same things.

    A four-point CG sweep came back with the CG-height explanation four times, each
    carrying a different percentage, so exact-match de-duplication could not see
    they were one finding and the reader had to diff them by eye.
    """

    def test_warnings_differing_only_in_their_numbers_share_a_shape(self):
        a = "the CG sits 0.74 MAC below the wing, adding +15.8% to pitch stiffness"
        b = "the CG sits 0.31 MAC below the wing, adding +9.2% to pitch stiffness"
        assert sweep_uc._shape(a) == sweep_uc._shape(b)

    def test_genuinely_different_warnings_do_not(self):
        a = "the static margin is +16.1% MAC and this design asks for 5%-15%"
        b = "this L/D of 49.84 is for the lifting surfaces only"
        assert sweep_uc._shape(a) != sweep_uc._shape(b)

    def test_a_signed_number_is_not_mistaken_for_a_word(self):
        assert sweep_uc._shape("margin -10.1%") == sweep_uc._shape("margin +8.7%")

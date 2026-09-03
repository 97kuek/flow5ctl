"""The numbers an agent is actually given."""
from __future__ import annotations

import pytest

from flow5ctl.flow5.results import parse_polar
from flow5ctl.flow5.summary import parse_modes, summarise
from flow5ctl.units import static_margin_from_flow5


class TestRectangularWing:
    @pytest.fixture
    def s(self, fixtures):
        return summarise(parse_polar(fixtures / "polar_t1_rectwing.csv"),
                         mac=0.2, cg_x=0.05)

    def test_lift_curve_slope_is_physical(self, s):
        """AR 10 straight wing: Helmbold gives 5.15 /rad = 0.0899 /deg."""
        import math
        per_rad = s.cl_alpha_per_deg * 180 / math.pi
        helmbold = 2 * math.pi * 10 / (2 + math.sqrt(10**2 + 4))
        assert abs(per_rad / helmbold - 1) < 0.10

    def test_static_margin_agrees_with_flow5_once_units_are_fixed(self, s, fixtures):
        reported = parse_polar(fixtures / "polar_t1_rectwing.csv").header_float("Static margin")
        assert s.static_margin == pytest.approx(static_margin_from_flow5(reported), rel=0.02)

    def test_neutral_point_comes_from_the_header_when_the_column_is_zero(self, s):
        assert s.neutral_point_x == pytest.approx(0.05)

    def test_best_ld_reports_where_it_occurs(self, s):
        assert s.best_ld is not None
        assert s.best_ld.alpha == pytest.approx(2.0)
        assert s.best_ld.cl == pytest.approx(0.17146, rel=1e-3)

    def test_no_spurious_warnings(self, s):
        assert s.warnings == []


class TestStabilityPolar:
    @pytest.fixture
    def polar(self, fixtures):
        return parse_polar(fixtures / "polar_t7_inf.csv")

    def test_non_finite_columns_produce_a_warning(self, polar):
        s = summarise(polar, mac=0.1935, cg_x=0.05125)
        assert any("Roll Damping" in w for w in s.warnings)

    def test_a_vertically_offset_cg_suppresses_the_cross_check(self, polar):
        """flow5's header and −dCm/dCL are different quantities when the CG is low.

        flow5 reports the classical static margin. −dCm/dCL about a CG below the wing
        additionally carries the force-tilt term, so cross-checking one against the
        other produces a false alarm — which is exactly what flow5ctl used to do, and
        it wrongly documented flow5 as inconsistent for it.
        """
        s = summarise(polar, mac=0.1935, cg_x=0.05125, cg_height_offset_mac=-1.0)
        assert not any("flow5 reports a static margin" in w for w in s.warnings)

    def test_with_the_cg_at_wing_height_the_cross_check_runs(self, polar):
        s = summarise(polar, mac=0.1935, cg_x=0.05125, cg_height_offset_mac=0.0)
        assert any("flow5 reports a static margin" in w for w in s.warnings)

    def test_neutral_point_prefers_the_column_over_the_wrong_header(self, polar):
        assert polar.header_float("XNP") == pytest.approx(0.0)
        s = summarise(polar, mac=0.1935, cg_x=0.05125)
        assert s.neutral_point_x == pytest.approx(0.10883, rel=1e-3)


class TestModeParsing:
    LOG = """
      ___Longitudinal modes___

      Eigenvalue:     -100.7 +         0i   |      -25.78 +         0i   |    -0.04435 +   -0.4199i   |    -0.04435 +    0.4199i
                    ______________________________________
      Eigenvector:         1 +         0i

      ___Lateral modes___

      Eigenvalue:    -0.01397 +         0i   |           0 +         0i   |       101.2 +         0i   |      -1.5 +    0.5i
    """

    def test_longitudinal_eigenvalues_are_recovered(self):
        lon, _ = parse_modes(self.LOG)
        assert len(lon) == 4
        assert lon[0].real == pytest.approx(-100.7)
        assert lon[3].imag == pytest.approx(0.4199)

    def test_the_phugoid_frequency_matches_flow5s_own_figure(self):
        """flow5 reported `Phugoid Freq. = 0.067084 Hz` for this run.

        Its printed eigenvalues carry four significant figures, and its summary
        column sits between the damped (0.06683) and undamped natural (0.06720)
        frequency, so both are reported and both are checked loosely.
        """
        lon, _ = parse_modes(self.LOG)
        phugoid = lon[3]
        assert phugoid.frequency_hz == pytest.approx(0.067084, rel=0.01)
        assert phugoid.natural_frequency_hz == pytest.approx(0.067084, rel=0.01)
        assert phugoid.damping_ratio == pytest.approx(0.105, rel=0.02)
        assert phugoid.period_s == pytest.approx(14.96, rel=0.01)
        assert phugoid.stable

    def test_an_unstable_mode_is_marked(self):
        _, lat = parse_modes(self.LOG)
        assert any(not m.stable for m in lat)

    def test_no_block_means_no_modes(self):
        assert parse_modes("nothing here") == ([], [])


class TestEmptyPolar:
    def test_a_polar_with_no_points_says_so_rather_than_inventing_numbers(self, fixtures,
                                                                          tmp_path):
        text = (fixtures / "polar_t7_inf.csv").read_text(encoding="utf-8")
        head = text.split("\n")
        i = next(k for k, ln in enumerate(head) if "Ctrl" in ln and "CL" in ln)
        # keep the labels, drop every data field, and say there are no points
        labels = head[i][: len(head[i]) - 741]
        rebuilt = [ln.replace("= 3", "= 0") if "Nbr. of data points" in ln else ln
                   for ln in head[:i]] + [labels]
        target = tmp_path / "empty_polar.csv"
        target.write_text("\n".join(rebuilt) + "\n", encoding="utf-8")
        s = summarise(parse_polar(target))
        assert s.points == 0
        assert s.cl_alpha_per_deg is None
        assert any("no operating points" in w for w in s.warnings)


class TestStaticMarginCrossCheck:
    """flow5's own figure and −dCm/dCL agree when the CG is at the wing's height.

    They diverge when it is not, by as much as 29 percentage points on a
    human-powered aircraft, and the divergence is physics rather than a flow5 defect.
    flow5ctl reported the divergence as a flow5 inconsistency until a real aircraft
    showed otherwise; these tests keep that mistake from coming back.
    """

    def _polar(self, tmp_path, fixtures, static_margin: float):
        text = (fixtures / "polar_t1_rectwing.csv").read_text(encoding="utf-8")
        text = text.replace("Static margin       = -0.590317",
                            f"Static margin       = {static_margin}")
        target = tmp_path / "sm.csv"
        target.write_text(text, encoding="utf-8")
        from flow5ctl.flow5.results import parse_polar
        return parse_polar(target)

    def test_agreement_produces_no_warning(self, tmp_path, fixtures):
        s = summarise(self._polar(tmp_path, fixtures, -0.590317), mac=0.2, cg_x=0.05,
                      cg_height_offset_mac=0.0)
        assert s.warnings == []

    def test_disagreement_at_wing_height_points_at_the_geometry(self, tmp_path,
                                                                fixtures):
        s = summarise(self._polar(tmp_path, fixtures, 8.0), mac=0.2, cg_x=0.05,
                      cg_height_offset_mac=0.0)
        assert any("check the geometry" in w for w in s.warnings)
        # and it no longer blames flow5
        assert not any("inconsistently" in w for w in s.warnings)

    def test_the_two_margins_are_separate_fields(self, fixtures):
        from flow5ctl.flow5.results import parse_polar
        s = summarise(parse_polar(fixtures / "polar_t1_rectwing.csv"), mac=0.2,
                      cg_x=0.05)
        assert "static_margin" in s.as_dict()
        assert "pitch_stiffness_margin" in s.as_dict()

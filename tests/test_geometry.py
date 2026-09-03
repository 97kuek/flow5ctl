"""Golden geometry values, computed by hand.

These are the numbers everything downstream depends on: they become flow5's
reference area, span and chord, and getting them wrong makes every coefficient wrong
without any error appearing. Changing a value here means proving the old one wrong.

The rectangular case is cross-validated against flow5 itself: flow5 reported
`Counted 520 elements` for this mesh, and every strip reported `Re = 200000`
(= 0.2 m x 15 m/s / 1.5e-5), matching `panel_count` and `reynolds_at_mac` below.
"""
from __future__ import annotations

import math

import pytest

from flow5ctl.geometry import derived as geometry
from flow5ctl.geometry.planform import allocate_spanwise_panels
from flow5ctl.model.design import Design


def solve(raw: dict) -> geometry.Derived:
    return geometry.solve(Design.model_validate(raw))


def test_rectangular_wing_matches_hand_calculation(rect_design):
    d = solve(rect_design)
    assert d.reference_area == pytest.approx(0.4)
    assert d.reference_span == pytest.approx(2.0)
    assert d.reference_chord == pytest.approx(0.2)
    assert d.aspect_ratio == pytest.approx(10.0)
    assert d.main.geom.mac_y == pytest.approx(0.5)
    assert d.main.geom.taper_ratio == pytest.approx(1.0)
    # flow5 counted 520 elements for this mesh
    assert d.panel_count == 520
    # flow5's strip table reported Re = 200000 for every strip
    assert d.reynolds_at_mac == pytest.approx(200_000)
    assert d.wing_loading == pytest.approx(2.5)


def test_simple_taper_matches_the_closed_form(rect_design):
    """For a single trapezoid the classic formulas apply, so they pin the integrals."""
    raw = {**rect_design}
    raw["wing"] = {**raw["wing"], "planform": {"span": 2.0, "root_chord": 0.2, "taper": 0.5}}
    d = solve(raw)
    cr, lam, semi = 0.2, 0.5, 1.0
    assert d.reference_area == pytest.approx(2 * semi * cr * (1 + lam) / 2)
    assert d.reference_chord == pytest.approx(2 / 3 * cr * (1 + lam + lam**2) / (1 + lam))
    assert d.main.geom.mac_y == pytest.approx(semi / 3 * (1 + 2 * lam) / (1 + lam))


def test_multi_break_planform_needs_the_integral_not_the_formula(rect_design):
    """A wing with a break is where the two-parameter taper formula goes wrong."""
    raw = {**rect_design}
    raw["wing"] = {
        "airfoil": "NACA0012",
        "sections": [
            {"y": 0.0, "chord": 0.20, "spanwise": 10, "chordwise": 13},
            {"y": 0.5, "chord": 0.16, "spanwise": 10, "chordwise": 13},
            {"y": 1.0, "chord": 0.10, "spanwise": 1, "chordwise": 13},
        ],
    }
    d = solve(raw)
    # hand-computed: int c dy = 0.5*(0.20+0.16)/2 + 0.5*(0.16+0.10)/2 = 0.155
    assert d.reference_area == pytest.approx(0.31)
    # int c^2 dy = 0.5*(0.04+0.032+0.0256)/3 + 0.5*(0.0256+0.016+0.01)/3
    int_c2 = 0.5 * (0.04 + 0.032 + 0.0256) / 3 + 0.5 * (0.0256 + 0.016 + 0.01) / 3
    assert d.reference_chord == pytest.approx(int_c2 / 0.155)
    # the naive taper formula would give a different answer
    naive = 2 / 3 * 0.20 * (1 + 0.5 + 0.25) / 1.5
    assert abs(d.reference_chord - naive) > 1e-3


def test_dihedral_reduces_projected_span_but_not_planform_span(rect_design):
    """Verified against flow5: a section's y is the station ALONG the wing, so the
    planform span is unchanged and only the projected quantities shrink by cos(dihedral)."""
    raw = {**rect_design}
    raw["wing"] = {**raw["wing"],
                   "planform": {"span": 2.0, "root_chord": 0.2, "dihedral": 30.0}}
    d = solve(raw)
    assert d.reference_span == pytest.approx(2.0)
    assert d.main.geom.projected_span == pytest.approx(2.0 * math.cos(math.radians(30)))
    assert d.main.geom.planform_area == pytest.approx(0.4)
    assert d.main.geom.projected_area == pytest.approx(0.4 * math.cos(math.radians(30)))


def test_sweep_moves_the_mac_leading_edge(rect_design):
    raw = {**rect_design}
    raw["wing"] = {**raw["wing"],
                   "planform": {"span": 2.0, "root_chord": 0.2, "sweep_le": 10.0}}
    d = solve(raw)
    # constant chord, so the MAC sits at mid semi-span
    assert d.main.geom.mac_le_x == pytest.approx(0.5 * math.tan(math.radians(10.0)))


def test_units_are_converted_once(rect_design):
    raw = {**rect_design, "units": {"length": "mm", "mass": "g", "speed": "m/s"}}
    raw["mass"] = {"components": [{"tag": "b", "mass": 1000.0, "at": [50.0, 0.0, 0.0]}]}
    raw["wing"] = {**raw["wing"], "planform": {"span": 2000.0, "root_chord": 200.0}}
    d = solve(raw)
    assert d.reference_area == pytest.approx(0.4)
    assert d.mass.total == pytest.approx(1.0)
    assert d.mass.cg[0] == pytest.approx(0.05)


class TestMassProperties:
    def test_cg_is_the_mass_weighted_mean(self, rect_design):
        raw = {**rect_design, "mass": {"components": [
            {"tag": "a", "mass": 1.0, "at": [0.0, 0.0, 0.0]},
            {"tag": "b", "mass": 3.0, "at": [0.4, 0.0, 0.0]},
        ]}}
        d = solve(raw)
        assert d.mass.total == pytest.approx(4.0)
        assert d.mass.cg[0] == pytest.approx(0.3)

    def test_centreline_masses_give_no_roll_inertia(self, rect_design):
        d = solve(rect_design)
        assert d.mass.ixx == pytest.approx(0.0)
        assert d.mass.lateral_inertia_is_degenerate(d.reference_span / 2)

    def test_spanwise_masses_give_a_plausible_roll_radius(self, rect_design):
        raw = {**rect_design, "mass": {"components": [
            {"tag": "L", "mass": 0.5, "at": [0.05, -0.6, 0.0]},
            {"tag": "R", "mass": 0.5, "at": [0.05, 0.6, 0.0]},
        ]}}
        d = solve(raw)
        assert d.mass.ixx == pytest.approx(0.36)
        assert d.mass.roll_radius_of_gyration == pytest.approx(0.6)
        assert not d.mass.lateral_inertia_is_degenerate(d.reference_span / 2)

    def test_total_only_leaves_inertia_unknown(self, rect_design):
        raw = {**rect_design, "mass": {"total": 1.0, "cg": [0.05, 0.0, 0.0]}}
        d = solve(raw)
        assert not d.mass.from_components
        assert d.mass.ixx == 0.0


class TestPanelAllocation:
    def make(self, ys: list[float]):
        from flow5ctl.model.design import Section
        return [Section(y=y, chord=0.2, airfoil="x") for y in ys]

    def test_totals_are_exact_and_the_tip_gets_one(self):
        counts = allocate_spanwise_panels(self.make([0.0, 0.5, 1.0]), 20)
        assert counts[-1] == 1
        assert sum(counts[:-1]) == 20

    def test_proportional_to_segment_length(self):
        counts = allocate_spanwise_panels(self.make([0.0, 0.8, 1.0]), 20)
        assert counts[0] > counts[1]

    def test_never_allocates_zero_to_a_segment(self):
        counts = allocate_spanwise_panels(self.make([0.0, 0.01, 0.02, 1.0]), 4)
        assert all(c >= 1 for c in counts)


class TestReynoldsEnvelope:
    def test_brackets_the_low_speed_end(self, rect_design):
        d = solve(rect_design)
        lo, hi = d.reynolds_envelope(cl_max=1.2)
        assert lo < d.reynolds_at_mac < hi
        # the stall-speed end must be below cruise Reynolds, or a T2 polar fails
        assert lo < d.reynolds(d.main.geom.tip_chord, d.stall_speed(1.2))

    def test_uses_the_smallest_chord(self, rect_design):
        raw = {**rect_design}
        raw["wing"] = {**raw["wing"],
                       "planform": {"span": 2.0, "root_chord": 0.2, "taper": 0.3}}
        d = solve(raw)
        lo, _ = d.reynolds_envelope()
        assert lo <= d.reynolds(0.06, d.stall_speed() or 1.0)


class TestValidation:
    def test_unknown_airfoil_is_refused(self, rect_design):
        raw = {**rect_design}
        raw["wing"] = {**raw["wing"], "airfoil": "NotDeclared"}
        with pytest.raises(Exception, match="not.*declared|discards"):
            solve(raw)

    def test_sections_must_increase(self, rect_design):
        raw = {**rect_design}
        raw["wing"] = {"airfoil": "NACA0012", "sections": [
            {"y": 0.0, "chord": 0.2}, {"y": 0.0, "chord": 0.1}]}
        with pytest.raises(Exception, match="increasing"):
            solve(raw)

    def test_planform_and_sections_are_mutually_exclusive(self, rect_design):
        raw = {**rect_design}
        raw["wing"] = {
            "airfoil": "NACA0012",
            "planform": {"span": 2.0, "root_chord": 0.2},
            "sections": [{"y": 0.0, "chord": 0.2}, {"y": 1.0, "chord": 0.2}],
        }
        with pytest.raises(Exception, match="exactly one"):
            solve(raw)

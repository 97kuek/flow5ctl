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

from flow5ctl.errors import DesignError
from flow5ctl.flow5 import airfoils
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

    def test_the_total_carries_no_binary_noise(self, rect_design):
        """0.40 + 0.10 + 0.10 + 0.10 came back as 0.7000000000000001 kg.

        It was reported that way, and a number that looks broken makes a careful
        reader doubt every other number beside it.
        """
        raw = dict(rect_design)
        raw["mass"] = {"components": [
            {"tag": "a", "mass": 0.40, "at": [0.1, 0.0, 0.0]},
            {"tag": "b", "mass": 0.10, "at": [0.1, -0.5, 0.0]},
            {"tag": "c", "mass": 0.10, "at": [0.1, 0.5, 0.0]},
            {"tag": "d", "mass": 0.10, "at": [0.2, 0.0, 0.0]},
        ]}
        total = geometry.solve(Design.model_validate(raw)).mass.total
        assert total == 0.7
        assert repr(total) == "0.7"

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


class TestReferenceHeight:
    """The height the pitching moment must be referenced to.

    Taking dCm/dCL about a CG offset from it in z adds a force-tilt term that is not
    part of the classical static margin. Measured on a real human-powered aircraft:
    29 percentage points. Getting this wrong made flow5ctl report a 47 % static margin
    where the classical figure was 18 %, and made it wrongly document flow5 as
    inconsistent.
    """

    def test_a_flat_wing_sits_at_its_own_position(self, rect_design):
        d = solve(rect_design)
        assert d.reference_height == pytest.approx(0.0)

    def test_dihedral_raises_the_mean_height(self, rect_design):
        raw = {**rect_design}
        raw["wing"] = {**raw["wing"],
                       "planform": {"span": 2.0, "root_chord": 0.2, "dihedral": 30.0}}
        d = solve(raw)
        # a constant-chord wing's mean height is half the tip rise
        expected = 0.5 * 1.0 * math.tan(math.radians(30.0))
        assert d.reference_height == pytest.approx(expected, rel=1e-6)

    def test_taper_weights_the_mean_height_inboard(self, rect_design):
        """Area weighting pulls the mean height down when the tip chord is smaller."""
        raw = {**rect_design}
        raw["wing"] = {**raw["wing"], "planform": {
            "span": 2.0, "root_chord": 0.2, "taper": 0.4, "dihedral": 30.0}}
        tapered = solve(raw).reference_height
        raw["wing"] = {**raw["wing"], "planform": {
            "span": 2.0, "root_chord": 0.2, "taper": 1.0, "dihedral": 30.0}}
        rectangular = solve(raw).reference_height
        assert tapered < rectangular

    def test_the_wings_own_z_position_shifts_it(self, rect_design):
        raw = {**rect_design}
        raw["wing"] = {**raw["wing"], "position": [0.0, 0.0, 0.5]}
        assert solve(raw).reference_height == pytest.approx(0.5)

    def test_the_offset_is_reported_in_mac(self, rect_design):
        raw = {**rect_design, "mass": {"components": [
            {"tag": "pilot", "mass": 1.0, "at": [0.05, 0.0, -0.4]}]}}
        d = solve(raw)
        assert d.cg_height_offset_mac == pytest.approx(-0.4 / 0.2)

    def test_a_human_powered_layout_reaches_a_full_mac(self, rect_design):
        """The case that matters: pilot slung low under a wing with dihedral."""
        raw = {**rect_design, "mass": {"components": [
            {"tag": "pilot", "mass": 68.0, "at": [0.4, 0.0, -0.55]},
            {"tag": "wl", "mass": 11.0, "at": [0.4, -7.0, 0.1]},
            {"tag": "wr", "mass": 11.0, "at": [0.4, 7.0, 0.1]}]}}
        raw["wing"] = {"airfoil": "NACA0012", "planform": {
            "span": 30.0, "root_chord": 1.15, "taper": 0.45, "dihedral": 6.0}}
        d = solve(raw)
        assert d.cg_height_offset_mac < -0.8
        assert d.reference_height > 0.5


# --- airfoil coordinate files ------------------------------------------------
#
# Two formats are in the wild and flow5ctl has to read both. Naive parsing of a
# Lednicer file produced a shape that jumped from the upper trailing edge back to
# the leading edge; flow5 rejected it with "the trailing edge is open by 57.3
# chord" (the point-count line was also read as a coordinate at x = 42). Every
# airfoil on the UIUC database is served in that format.

_SELIG = """DAE-31 AIRFOIL
  1.000000  0.000000
  0.500000  0.060000
  0.000000  0.000000
  0.500000 -0.020000
  1.000000  0.000000
"""

_LEDNICER = """DAE-11 AIRFOIL
       3.0       3.0

 0.0000000 0.0000000
 0.5000000 0.0600000
 1.0000000 0.0000000

 0.0000000 0.0000000
 0.5000000 -.0200000
 1.0000000 0.0000000
"""


def test_selig_coordinates_are_read_as_one_contour():
    pts = airfoils._parse_dat(_SELIG, "dae31")
    assert pts[0] == (1.0, 0.0)
    assert pts[2] == (0.0, 0.0)  # leading edge in the middle
    assert pts[-1] == (1.0, 0.0)


def test_lednicer_surfaces_are_reassembled_into_a_closed_contour():
    """Both surfaces run LE->TE, so the upper one has to be reversed."""
    pts = airfoils._parse_dat(_LEDNICER, "dae11")
    assert pts[0] == (1.0, 0.0)  # starts at the trailing edge, not at x = 3
    assert pts[2] == (0.0, 0.0)  # leading edge in the middle
    assert pts[-1] == (1.0, 0.0)  # and closes there
    assert len(pts) == 5  # the shared leading edge is not duplicated
    assert max(x for x, _ in pts) == 1.0  # the point-count line is gone


def test_lednicer_falls_back_to_the_blank_line_when_the_counts_are_wrong():
    text = _LEDNICER.replace("       3.0       3.0", "      99.0      99.0")
    pts = airfoils._parse_dat(text, "dae11")
    assert pts[0] == (1.0, 0.0)
    assert len(pts) == 5


def test_a_file_that_is_not_coordinates_is_refused():
    with pytest.raises(DesignError, match="declares|normalised coordinates|no coordinates"):
        airfoils._parse_dat("1200 340\n1300 350\n1400 360\n", "junk")

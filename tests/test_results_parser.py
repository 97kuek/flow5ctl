"""Pin the parser against real flow5 output.

Each test names the trap it defends. flow5's output has at least seven ways of
producing a plausible wrong number rather than an error, so a "simplification" of
the parser is nearly always a regression — see ADR-0010.
"""
from __future__ import annotations

import math

import pytest

from flow5ctl.errors import ParseError
from flow5ctl.flow5.results import (
    owning_polar,
    parse_foil_polar,
    parse_polar,
    parse_strips,
)


class TestTrapsInThePolarFile:
    def test_the_table_in_a_csv_file_contains_no_commas(self, fixtures):
        """Trap 1: `polar_text_output_format=csv` is whitespace-aligned text.

        Commas do appear in the prose header (`CoG = (0.050, 0.000, 0.000)m`), which
        is exactly why a CSV reader on this file returns nonsense rather than failing.
        """
        lines = (fixtures / "polar_t1_rectwing.csv").read_text(encoding="utf-8").split("\n")
        header_i = next(i for i, ln in enumerate(lines) if "Ctrl" in ln and "CL" in ln)
        for line in lines[header_i:]:
            assert "," not in line

    def test_row_count_matches_the_files_own_declared_count(self, fixtures):
        """Trap 2: the first row is welded onto the header line."""
        p = parse_polar(fixtures / "polar_t1_rectwing.csv")
        assert p.header["Nbr. of data points"] == "5"
        assert len(p.rows) == 5
        # the recovered row is the FIRST alpha, the one a naive reader loses
        assert p.column("α")[0] == pytest.approx(0.0)

    def test_columns_with_unit_tokens_and_internal_spaces_resolve(self, fixtures):
        """Trap 3: labels are variable width, separated by 2+ spaces."""
        p = parse_polar(fixtures / "polar_t1_rectwing.csv")
        assert len(p.columns) == 57
        assert "α (°)" in p.columns
        assert "Short Period Damping Ratio" in p.columns
        assert p.index("α") == p.columns.index("α (°)")
        assert p.index("CL") != p.index("CD")

    def test_single_point_polar_has_no_standalone_data_line(self, fixtures):
        """Trap 4: the only row lives inside the header line."""
        p = parse_polar(fixtures / "polar_t2_single_point.csv")
        assert p.header["Nbr. of data points"] == "1"
        assert len(p.rows) == 1
        assert p.column("V")[0] == pytest.approx(11.322, rel=1e-4)

    def test_non_finite_cells_are_kept_and_reported(self, fixtures):
        """Trap 5: `inf` in Roll Damping silently drops rows from a strict parser."""
        p = parse_polar(fixtures / "polar_t7_inf.csv")
        assert len(p.rows) == 3 == int(p.header["Nbr. of data points"])
        assert p.nonfinite
        assert {c for _, c in p.nonfinite} == {"Roll Damping"}
        assert any(not math.isfinite(v) for v in p.column("Roll Damping"))

    def test_operating_point_file_names_its_real_owner(self, fixtures):
        """Trap 6: op-point files are duplicated across every polar's directory."""
        assert owning_polar(fixtures / "oppoint_strips.csv") == "t1"

    def test_static_margin_in_the_header_is_a_percentage(self, fixtures):
        """Trap 7: -0.59 means -0.59 %, not -59 %."""
        from flow5ctl.units import static_margin_from_flow5
        p = parse_polar(fixtures / "polar_t1_rectwing.csv")
        reported = p.header_float("Static margin")
        assert reported == pytest.approx(-0.590317)
        assert static_margin_from_flow5(reported) == pytest.approx(-0.00590317)

    def test_header_value_after_an_expression_is_still_found(self, fixtures):
        """flow5 writes `XNP = d(XCp.Cl)/dCl =     0.05 m`."""
        p = parse_polar(fixtures / "polar_t1_rectwing.csv")
        assert p.header_float("XNP") == pytest.approx(0.05)


class TestAcrossPolarTypes:
    @pytest.mark.parametrize("name", [
        "polar_t1_rectwing.csv",
        "polar_t2_single_point.csv",
        "polar_t5_beta.csv",
        "polar_t7_inf.csv",
    ])
    def test_every_fixture_self_validates(self, fixtures, name):
        p = parse_polar(fixtures / name)
        assert len(p.rows) == int(p.header["Nbr. of data points"])
        assert len(p.columns) == 57

    def test_beta_polar_varies_beta_not_alpha(self, fixtures):
        p = parse_polar(fixtures / "polar_t5_beta.csv")
        assert len(set(p.column("α"))) == 1
        assert sorted(p.column("β")) == [-8.0, -4.0, 0.0, 4.0, 8.0]

    def test_a_truncated_file_raises_rather_than_reporting_a_partial_polar(
            self, fixtures, tmp_path):
        text = (fixtures / "polar_t1_rectwing.csv").read_text(encoding="utf-8")
        truncated = "\n".join(text.split("\n")[:-2])
        target = tmp_path / "truncated.csv"
        target.write_text(truncated, encoding="utf-8")
        with pytest.raises(ParseError, match="declares"):
            parse_polar(target)

    def test_a_file_with_no_table_raises(self, tmp_path):
        target = tmp_path / "empty.csv"
        target.write_text("nothing here\n", encoding="utf-8")
        with pytest.raises(ParseError, match="no polar table"):
            parse_polar(target)


class TestStrips:
    def test_strip_table_recovers_the_geometry_flow5_used(self, fixtures):
        """`Re = c.V/nu` and the y column together cross-check our own geometry."""
        tables = parse_strips(fixtures / "oppoint_strips.csv")
        assert "Main Wing" in tables
        t = tables["Main Wing"]
        ys = t.column("y(m)")
        # 20 uniform panels per semi-span over 1.0 m: strip centres 0.05 apart
        assert len(ys) == 40
        assert max(ys) == pytest.approx(0.975)
        assert min(ys) == pytest.approx(-0.975)
        assert ys[1] - ys[0] == pytest.approx(0.05)
        # every strip is at Re = 0.2 m x 15 m/s / 1.5e-5 = 200000
        assert set(t.column("Re")) == {200000.0}
        # so the chord flow5 used is exactly the one we asked for
        chord = 200000.0 * 1.5e-5 / 15.0
        assert chord == pytest.approx(0.2)

    def test_bending_moment_is_available_for_spar_sizing(self, fixtures):
        t = parse_strips(fixtures / "oppoint_strips.csv")["Main Wing"]
        assert "Bending.mom" in t.columns


class TestFoilPolars:
    def test_comma_separated_form(self, fixtures):
        fp = parse_foil_polar(fixtures / "foilpolar_csv.csv")
        assert fp.foil == "AG35ish"
        assert fp.reynolds == pytest.approx(200_000)
        assert fp.ncrit == pytest.approx(9.0)
        assert len(fp.alpha) == len(fp.cl) == len(fp.cd) > 20

    def test_xfoil_text_form(self, fixtures):
        fp = parse_foil_polar(fixtures / "foilpolar_xfoil.txt")
        assert fp.reynolds == pytest.approx(100_000)
        assert len(fp.alpha) > 20

    def test_drag_falls_and_lift_rises_with_reynolds(self, fixtures):
        """A physical sanity check on the fixtures themselves."""
        lo = parse_foil_polar(fixtures / "foilpolar_xfoil.txt")     # Re 1e5
        hi = parse_foil_polar(fixtures / "foilpolar_csv.csv")       # Re 2e5
        assert min(hi.cd) < min(lo.cd)
        assert max(hi.cl) > max(lo.cl)

    def test_an_empty_polar_explains_the_batch_range_trap(self, tmp_path):
        target = tmp_path / "empty.csv"
        target.write_text(" Calculated polar for: X\n\nalpha,CL,CD,CDp,Cm\n", encoding="utf-8")
        with pytest.raises(ParseError, match="OpPoint_Range"):
            parse_foil_polar(target)

"""Pin the parser against real flow5 output.

Each test names the trap it defends. flow5's output has at least seven ways of
producing a plausible wrong number rather than an error, so a "simplification" of
the parser is nearly always a regression — see ADR-0010.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from flow5ctl.errors import ParseError
from flow5ctl.flow5 import foilpolar
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


class TestFoilPolarCoverage:
    """XFoil drops the points it cannot converge, and flow5 reports no error.

    Measured on DAE-31 at Re 450,000, asking for alpha -4..12 in half-degree steps:
    29 of 33 points came back, with alpha +0.5 to +3.0 missing. That gap is where
    upper-surface transition jumps to the leading edge and drag steps up 44%, so
    interpolating the 3D viscous drag across it is interpolating across a
    discontinuity. flow5ctl checked only that some polars existed.
    """

    def _polar(self, tmp_path, alphas: list[float]) -> Path:
        rows = "\n".join(
            f"  {a:6.3f}   0.5000   0.01000   0.00300  -0.1000  0.7000  0.0000"
            for a in alphas
        )
        p = tmp_path / "T1-Re0.450-N9.0.txt"
        p.write_text(
            "flow5 v7.57\n\n Calculated polar for: DAE31\n\n"
            " 1 1 Reynolds number fixed          Mach number fixed\n\n"
            "  alpha     CL        CD       CDp       Cm    Top Xtr Bot Xtr\n"
            " ------- -------- --------- --------- -------- ------- -------\n"
            + rows + "\n"
        )
        return p

    def test_the_header_line_starting_with_a_number_is_not_a_data_row(self, tmp_path):
        """`1 1 Reynolds number fixed` parses as alpha 1.0 if rows are found naively."""
        p = self._polar(tmp_path, [-1.0, -0.5, 0.0, 0.5])
        assert foilpolar.read_alphas(p) == [-1.0, -0.5, 0.0, 0.5]

    def test_a_converged_sweep_reports_no_gap(self, tmp_path):
        self._polar(tmp_path, [-1.0, -0.5, 0.0, 0.5, 1.0])
        assert foilpolar.find_gaps(tmp_path, 0.5) == []

    def test_a_single_dropped_point_is_tolerated(self, tmp_path):
        """One missing point is noise; the interpolation across it is harmless."""
        self._polar(tmp_path, [0.0, 0.5, 1.5, 2.0])
        assert foilpolar.find_gaps(tmp_path, 0.5) == []

    def test_the_measured_hole_is_reported(self, tmp_path):
        """The real DAE-31 gap: nothing between +0.5 and +3.0."""
        self._polar(tmp_path, [-1.0, -0.5, 0.0, 0.5, 3.0, 3.5, 4.0])
        gaps = foilpolar.find_gaps(tmp_path, 0.5)
        assert len(gaps) == 1
        assert (gaps[0].lo, gaps[0].hi) == (0.5, 3.0)
        assert gaps[0].width == pytest.approx(2.5)

    def test_the_warning_names_the_gap_and_says_what_it_costs(self, tmp_path):
        self._polar(tmp_path, [0.0, 0.5, 3.0, 3.5])
        text = foilpolar.describe(foilpolar.find_gaps(tmp_path, 0.5))
        assert "+0.5" in text and "+3.0" in text
        assert "interpolated" in text

    def test_a_polar_with_one_point_is_not_a_gap(self, tmp_path):
        """No polar at all is a different failure, caught by the caller."""
        self._polar(tmp_path, [0.0])
        assert foilpolar.find_gaps(tmp_path, 0.5) == []


class TestTheParserDoesNotDropRowsInSilence:
    """ADR-0010 exists because flow5's output produces plausible wrong numbers.

    A reviewer found two ways a row could vanish with nothing noticing: the wrong
    field count, or a non-numeric field. Both were caught only if the file's declared
    point count happened to disagree with the total - and when flow5 declares no
    count, or an unparsable one, nothing noticed at all.

    Built by mutating the real fixture rather than a synthetic header, because the
    label widths and the welded first row are the parts that matter.
    """

    def _mutate(self, fixtures, tmp_path, *, corrupt_last, count=None):
        import re

        text = (fixtures / "polar_t1_rectwing.csv").read_text(encoding="utf-8")
        lines = text.split("\n")
        # the last line that parses as a full numeric row
        idx = max(i for i, ln in enumerate(lines)
                  if ln.split() and all(_is_number(f) for f in ln.split()))
        if corrupt_last == "short":
            lines[idx] = " ".join(lines[idx].split()[:-1])
        else:
            lines[idx] = " ".join([*lines[idx].split()[:-1], "oops"])
        out = "\n".join(lines)
        if count is not None:
            out = re.sub(r"(Nbr\. of data points\s*=\s*)\S+", rf"\g<1>{count}", out)
        p = tmp_path / "p.csv"
        p.write_text(out, encoding="utf-8")
        return p

    def test_a_dropped_row_with_no_declared_count_raises(self, fixtures, tmp_path):
        p = self._mutate(fixtures, tmp_path, corrupt_last="short", count="unknown")
        with pytest.raises(ParseError, match="no way to tell whether"):
            parse_polar(p)

    def test_a_non_numeric_field_is_the_same_case(self, fixtures, tmp_path):
        p = self._mutate(fixtures, tmp_path, corrupt_last="bad", count="unknown")
        with pytest.raises(ParseError, match="could not be read as"):
            parse_polar(p)

    def test_a_declared_count_still_catches_the_loss(self, fixtures, tmp_path):
        p = self._mutate(fixtures, tmp_path, corrupt_last="short")
        with pytest.raises(ParseError, match="Points were dropped"):
            parse_polar(p)

    def test_the_untouched_fixture_still_parses(self, fixtures):
        assert len(parse_polar(fixtures / "polar_t1_rectwing.csv").rows) == 5


def _is_number(token: str) -> bool:
    try:
        float(token)
    except ValueError:
        return False
    return True


class TestAnAmbiguousHeaderKeyIsRefused:
    """`header_float` fell back to `startswith` and took whichever came first.

    The header genuinely has keys that share a prefix - `XNP` beside
    `XNP = d(XCp.Cl)/dCl` - so the fallback is needed; what it must not do is pick
    one of several by dictionary order.
    """

    def _polar(self, header):
        import pathlib as _p

        from flow5ctl.flow5.results import Polar
        return Polar(name="p", header=header, columns=["CL"], rows=[[0.1]],
                     path=_p.Path("p.csv"))

    def test_an_exact_key_wins(self):
        p = self._polar({"XNP": "0.05 m", "XNP = d(XCp.Cl)/dCl": "0.09 m"})
        assert p.header_float("XNP") == pytest.approx(0.05)

    def test_two_prefix_matches_and_no_exact_one_is_an_error(self):
        p = self._polar({"XNPa": "0.05 m", "XNPb": "0.09 m"})
        with pytest.raises(ParseError, match="matches 2 header keys"):
            p.header_float("XNP")

    def test_a_single_prefix_match_is_still_used(self):
        p = self._polar({"XNP = d(XCp.Cl)/dCl": "0.09 m"})
        assert p.header_float("XNP") == pytest.approx(0.09)

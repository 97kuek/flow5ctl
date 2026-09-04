"""Field edits, airfoils, shorthand expansion, export."""
from __future__ import annotations

import pytest

from flow5ctl.errors import DesignError
from flow5ctl.geometry import derived as geometry
from flow5ctl.project.store import Project
from flow5ctl.usecases import define, edit


@pytest.fixture(autouse=True)
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("FLOW5CTL_WORKSPACE", str(tmp_path / "ws"))


@pytest.fixture
def project(rect_design):
    define.create("Rect", rect_design)
    return Project.resolve("Rect")


class TestSet:
    def test_a_single_field_changes_and_nothing_else(self, project):
        out = edit.set_fields(project, ["wing.planform.taper=0.5"])
        design = project.load()
        assert design.wing.planform.taper == pytest.approx(0.5)
        assert design.wing.planform.span == pytest.approx(2.0)
        assert out["changed"] == ["wing.planform.taper"]
        assert out["geometry"]["taper_ratio"] == pytest.approx(0.5)

    def test_several_assignments_apply_together(self, project):
        edit.set_fields(project, ["wing.planform.taper=0.6",
                                  "wing.planform.washout=-2.5",
                                  "requirements.cruise_speed=20"])
        design = project.load()
        assert design.wing.planform.washout == pytest.approx(-2.5)
        assert design.requirements.cruise_speed == pytest.approx(20)

    @pytest.mark.parametrize("text,expected", [
        ("wing.symmetric=false", False),
        ("wing.panels.chordwise=9", 9),
        ("wing.panels.span_distribution=SINE", "SINE"),
    ])
    def test_yaml_scalar_rules_apply(self, project, text, expected):
        edit.set_fields(project, [text])
        path = text.split("=")[0].split(".")
        node = project.load().model_dump(mode="json", by_alias=True)
        for k in path:
            node = node[k]
        assert node == expected

    def test_a_nonexistent_path_is_refused(self, project):
        with pytest.raises(DesignError, match="does not exist"):
            edit.set_fields(project, ["wing.planform.nope=1"])

    def test_new_fields_are_never_created_by_assignment(self, project):
        """A typo that silently added a field flow5 ignores would be worse than an error."""
        with pytest.raises(DesignError, match="will not create new fields"):
            edit.set_fields(project, ["wing.wingspan=3.0"])

    def test_an_invalid_value_is_rejected_before_writing(self, project):
        """A rejected edit is a normal event, so it reads as a sentence.

        This used to surface Pydantic's own ValidationError, docs URL and all.
        """
        original = project.design_path.read_text(encoding="utf-8")
        with pytest.raises(DesignError) as e:
            edit.set_fields(project, ["wing.planform.taper=5.0"])   # taper must be <= 1
        assert "would not leave a valid design" in str(e.value)
        assert "pydantic" not in str(e.value).lower()
        assert project.design_path.read_text(encoding="utf-8") == original

    def test_a_malformed_assignment_is_refused(self, project):
        with pytest.raises(DesignError, match="path=value"):
            edit.set_fields(project, ["wing.planform.taper 0.5"])


class TestAirfoils:
    def test_add_writes_a_dat_whose_first_line_is_the_name(self, project):
        out = edit.add_airfoil(project, "NACA2412", "naca:2412")
        dat = project.airfoils / "NACA2412.dat"
        assert dat.is_file()
        assert dat.read_text(encoding="utf-8").splitlines()[0] == "NACA2412"
        assert out["airfoil"]["points"] > 100
        assert out["airfoil"]["max_thickness_fraction"] == pytest.approx(0.12, abs=0.01)

    def test_the_stored_source_points_at_the_file_not_the_generator(self, project):
        edit.add_airfoil(project, "NACA2412", "naca:2412")
        entry = next(a for a in project.load().airfoils if a.name == "NACA2412")
        assert entry.source == "file:airfoils/NACA2412.dat"

    def test_adding_a_duplicate_needs_replace(self, project):
        with pytest.raises(DesignError, match="already declared"):
            edit.add_airfoil(project, "NACA0012", "naca:2412")
        edit.add_airfoil(project, "NACA0012", "naca:2412", replace=True)
        assert len(project.load().airfoils) == 1

    def test_a_polar_specification_is_stored(self, project):
        edit.add_airfoil(project, "AG35", "naca:2409",
                         reynolds=[50_000, 150_000], ncrit=11.0, alpha=(-8.0, 14.0, 0.5))
        entry = next(a for a in project.load().airfoils if a.name == "AG35")
        assert entry.polars.reynolds == [50_000, 150_000]
        assert entry.polars.ncrit == pytest.approx(11.0)

    def test_an_unknown_source_scheme_says_what_is_valid(self, project):
        with pytest.raises(DesignError, match="naca:"):
            edit.add_airfoil(project, "X", "magic:1234")

    def test_a_missing_file_is_reported(self, project):
        with pytest.raises(DesignError, match="not found"):
            edit.add_airfoil(project, "X", "file:nope.dat")

    def test_open_trailing_edge_coordinates_are_rejected(self, project, tmp_path):
        bad = project.root / "bad.dat"
        bad.write_text("BAD\n1.0 0.20\n0.0 0.0\n1.0 -0.20\n" + "\n".join(
            f"{i / 40:.4f} {0.05:.4f}" for i in range(40)), encoding="utf-8")
        with pytest.raises(DesignError, match="trailing edge"):
            edit.add_airfoil(project, "Bad", "file:bad.dat")

    def test_list_reports_which_surfaces_use_each_airfoil(self, project):
        rows = edit.list_airfoils(project)["airfoils"]
        assert rows[0]["name"] == "NACA0012"
        assert rows[0]["used_by"] == ["main"]


class TestExpand:
    def test_expansion_preserves_the_geometry_exactly(self, project, rect_design):
        """The shorthand and its expansion must be the same aircraft, or the
        convenience form silently means something different."""
        before = geometry.solve(project.load()).as_dict()
        edit.expand(project)
        after = geometry.solve(project.load()).as_dict()
        assert before == after

    def test_expansion_replaces_the_planform_with_sections(self, project):
        edit.expand(project)
        wing = project.load().wing
        assert wing.planform is None
        assert wing.sections is not None
        assert len(wing.sections) == 2
        assert wing.sections[-1].spanwise == 1

    def test_a_multi_break_planform_expands_to_every_station(self, project):
        edit.set_fields(project, ["wing.planform.breaks=[0.4, 0.75]"])
        out = edit.expand(project)
        assert project.load().wing.sections is not None
        assert len(project.load().wing.sections) == 4
        assert "4 sections" in out["expanded"][0]

    def test_expanding_twice_is_a_no_op(self, project):
        edit.expand(project)
        out = edit.expand(project)
        assert out["expanded"] == []

    def test_dry_run_does_not_write(self, project):
        original = project.design_path.read_text(encoding="utf-8")
        edit.expand(project, write=False)
        assert project.design_path.read_text(encoding="utf-8") == original


class TestExport:
    def test_exporting_before_any_analysis_says_so(self, project):
        with pytest.raises(DesignError, match="nothing has been analysed"):
            edit.export(project, "fl5")

    def test_an_unknown_format_lists_the_valid_ones(self, project):
        (project.build / "out" / "x").mkdir(parents=True)
        with pytest.raises(DesignError, match="fl5, stl, csv or xml"):
            edit.export(project, "dxf")

    def _run(self, project, name: str) -> None:
        """A build directory shaped like one flow5 leaves behind."""
        d = project.build / "out" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_bytes(b"fl5")

    def test_the_default_skips_our_own_by_products(self, project):
        """The reference-height pass is usually the most recent thing on disk.

        It holds the CG at wing height so the CG-height term can be separated out,
        so exporting it hands the user a different aircraft than the one they asked
        about, under a name close enough to be missed.
        """
        self._run(project, "cruise")
        self._run(project, "cruise__zref")
        out = edit.export(project, "fl5")
        assert out["from_analysis"] == "cruise"

    def test_a_free_air_copy_is_not_defaulted_to_either(self, project):
        self._run(project, "cruise")
        self._run(project, "cruise__free")
        assert edit.export(project, "fl5")["from_analysis"] == "cruise"

    def test_naming_one_explicitly_works_and_says_what_it_is(self, project):
        self._run(project, "cruise")
        self._run(project, "cruise__zref")
        out = edit.export(project, "fl5", polar="cruise__zref")
        assert out["from_analysis"] == "cruise__zref"
        assert any("internal by-product" in n for n in out["notes"])

    def test_when_only_by_products_exist_it_says_so_rather_than_picking_one(self, project):
        self._run(project, "cruise__zref")
        with pytest.raises(DesignError, match="internal by-products"):
            edit.export(project, "fl5")

    def test_an_unknown_name_does_not_offer_the_by_products(self, project):
        self._run(project, "cruise")
        self._run(project, "cruise__zref")
        with pytest.raises(DesignError) as exc:
            edit.export(project, "fl5", polar="nope")
        assert "cruise" in str(exc.value)
        assert "__zref" not in str(exc.value)


def test_a_twin_fin_edit_that_would_overlap_is_refused(rect_design):
    """count: 2 with the fin on the centreline would build two coincident surfaces."""
    d = dict(rect_design)
    d["tail"] = {"fin": {"airfoil": d["wing"]["airfoil"],
                         "position": [3.0, 0.8, 0.2],
                         "planform": {"span": 0.4, "root_chord": 0.2}}}
    define.create("Twin", d)
    project = Project.resolve("Twin")

    edit.set_fields(project, ["tail.fin.count=2"])
    assert project.load().tail.fin.count == 2

    with pytest.raises(DesignError, match="half-spacing"):
        edit.set_fields(project, ["tail.fin.position=[3.0, 0.0, 0.2]"])
    assert project.load().tail.fin.position[1] == pytest.approx(0.8)


class TestSetTakesTheDesignPositionally:
    """Every other verb takes the design name first, so people write it that way.

    `flow5ctl set Glider wing.planform.taper=0.6` used to read as three assignments,
    none containing an `=`, and the error that surfaced was "no design.yaml in the
    current directory" — which is about the wrong thing entirely.
    """

    def _args(self, assignment: list[str]):
        import argparse
        return argparse.Namespace(assignment=assignment, design=None, json=True)

    def test_a_leading_bare_name_is_the_design(self, project, capsys):
        from flow5ctl.cli import cmd_set
        assert cmd_set(self._args(["Rect", "wing.planform.taper=0.5"])) == 0
        assert project.load().wing.planform.taper == pytest.approx(0.5)

    def test_an_assignment_without_an_equals_says_what_is_wrong(self, project):
        from flow5ctl.cli import cmd_set
        from flow5ctl.errors import Flow5ctlError
        with pytest.raises(Flow5ctlError, match="not a `path=value` assignment"):
            cmd_set(self._args(["Rect", "taper", "0.6"]))

    def test_a_design_name_alone_is_not_an_edit(self, project):
        from flow5ctl.cli import cmd_set
        from flow5ctl.errors import Flow5ctlError
        with pytest.raises(Flow5ctlError, match="nothing to set"):
            cmd_set(self._args(["Rect"]))

    def test_the_design_flag_still_works(self, project):
        import argparse

        from flow5ctl.cli import cmd_set
        args = argparse.Namespace(assignment=["wing.planform.taper=0.4"],
                                  design="Rect", json=True)
        assert cmd_set(args) == 0
        assert project.load().wing.planform.taper == pytest.approx(0.4)

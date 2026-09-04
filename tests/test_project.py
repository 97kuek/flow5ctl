"""A design is a directory (ADR-0003)."""
from __future__ import annotations

import pathlib

import pytest

from flow5ctl.errors import DesignError, Flow5ctlError
from flow5ctl.project.store import Project, list_designs
from flow5ctl.usecases import define


@pytest.fixture(autouse=True)
def workspace(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    monkeypatch.setenv("FLOW5CTL_WORKSPACE", str(ws))
    return ws


def test_create_then_reopen_round_trips(rect_design, workspace):
    payload = define.create("Rect", rect_design)
    assert payload["geometry"]["planform_area"] == pytest.approx(0.4)
    project = Project.resolve("Rect")
    assert project.load().name == "Rect"
    assert (project.root / ".gitignore").exists()
    assert [n for n, _ in list_designs()] == ["Rect"]


def test_design_yaml_is_the_source_of_truth(rect_design, workspace):
    define.create("Rect", rect_design)
    project = Project.resolve("Rect")
    text = project.design_path.read_text(encoding="utf-8")
    assert "schema: flow5ctl/design/1" in text
    assert "root_chord: 0.2" in text


def test_generated_artifacts_are_gitignored(rect_design, workspace):
    define.create("Rect", rect_design)
    ignore = (Project.resolve("Rect").root / ".gitignore").read_text(encoding="utf-8")
    assert "build/" in ignore


def test_creating_twice_is_refused_unless_forced(rect_design, workspace):
    define.create("Rect", rect_design)
    with pytest.raises(DesignError, match="already exists"):
        define.create("Rect", rect_design)
    define.create("Rect", rect_design, exist_ok=True)


def test_unknown_design_lists_what_exists(rect_design, workspace):
    define.create("Rect", rect_design)
    with pytest.raises(DesignError, match="Rect"):
        Project.resolve("Nope")


def test_partial_update_keeps_everything_else(rect_design, workspace):
    define.create("Rect", rect_design)
    project = Project.resolve("Rect")
    out = define.update(project, {"wing": {"planform": {"taper": 0.5}}})
    design = project.load()
    assert design.wing.planform.taper == pytest.approx(0.5)
    assert design.wing.planform.span == pytest.approx(2.0)   # untouched
    assert design.mass.components[0].tag == "ballast"
    assert any("taper" in c for c in out["changed"])


def test_update_reports_the_new_geometry(rect_design, workspace):
    define.create("Rect", rect_design)
    project = Project.resolve("Rect")
    out = define.update(project, {"wing": {"planform": {"root_chord": 0.4}}})
    assert out["geometry"]["planform_area"] == pytest.approx(0.8)


def test_presets_fill_in_defaults_and_say_which(rect_design, workspace):
    raw = {**rect_design, "preset": "rc-glider"}
    raw.pop("requirements")
    out = define.create("Glider", raw)
    assert any("objective" in d for d in out["defaults_applied"])
    assert Project.resolve("Glider").load().requirements.objective == "min_sink"


def test_a_design_needs_an_airfoil(rect_design, workspace):
    raw = {**rect_design, "airfoils": []}
    with pytest.raises(DesignError, match="airfoil"):
        define.create("Bad", raw)


def test_the_lock_serialises_runs(rect_design, workspace):
    """Two runs against one project would share `build/`, so the second must wait."""
    define.create("Rect", rect_design)
    project = Project.resolve("Rect")
    with project.lock():
        second = project.lock(timeout=0.2)
        with pytest.raises(Flow5ctlError, match="another flow5ctl run"):
            second.__enter__()
    # the lock is released again afterwards
    with project.lock(timeout=1.0):
        pass


def test_state_records_what_produced_a_result(rect_design, workspace):
    define.create("Rect", rect_design)
    project = Project.resolve("Rect")
    project.update_state(flow5_version="7.57", last_analysis="cruise")
    assert project.state()["flow5_version"] == "7.57"
    assert define.describe(project)["flow5_version_last_used"] == "7.57"


class TestInvalidDesignFile:
    """design.yaml is meant to be hand-edited, so a bad one is a normal event.

    Before this, every failure came out as a Pydantic `ValidationError` traceback
    with a docs URL - reproduced by copying `examples/hpa.yaml`, which is a template
    and deliberately has no `name`.
    """

    def _project(self, tmp_path, text: str):
        (tmp_path / "design.yaml").write_text(text)
        return Project.open(tmp_path)

    def test_a_missing_field_is_named(self, tmp_path):
        p = self._project(tmp_path, "description: no name here\n")
        with pytest.raises(DesignError) as e:
            p.load()
        assert "name is required but missing" in str(e.value)
        assert "pydantic" not in str(e.value).lower()

    def test_a_misspelled_field_says_so(self, tmp_path):
        p = self._project(tmp_path, "name: X\nwing:\n  plamform: {span: 10}\n")
        with pytest.raises(DesignError) as e:
            p.load()
        assert "wing.plamform is not a field flow5ctl knows" in str(e.value)

    def test_broken_yaml_reports_the_line(self, tmp_path):
        p = self._project(tmp_path, "name: X\nwing: [oops\n")
        with pytest.raises(DesignError) as e:
            p.load()
        assert "not valid YAML" in str(e.value) and "line" in str(e.value)

    def test_a_file_that_is_not_a_mapping_is_refused(self, tmp_path):
        p = self._project(tmp_path, "- just\n- a list\n")
        with pytest.raises(DesignError, match="should hold a mapping"):
            p.load()


class TestTheVersionHasOneSource:
    """The version was written in two places and they drifted the moment one moved.

    `pyproject.toml` was bumped to 0.1.0 and `__init__.py` still said 0.1.0.dev0, so
    the wheel was built correctly while `flow5ctl --version`, `doctor` and the
    `flow5://status` resource all reported a pre-release to anyone who installed it.
    It is now read back from the installed distribution, so there is nothing to keep
    in step - and this test says so if that ever changes.
    """

    def _declared(self) -> str:
        import tomllib
        root = pathlib.Path(__file__).resolve().parent.parent
        data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        return data["project"]["version"]

    def test_the_package_reports_what_pyproject_declares(self):
        import flow5ctl
        assert flow5ctl.__version__ == self._declared()

    def test_the_cli_reports_the_same(self, capsys):
        import flow5ctl
        from flow5ctl.cli import main
        with pytest.raises(SystemExit):
            main(["--version"])
        assert flow5ctl.__version__ in capsys.readouterr().out

    def test_it_is_not_hard_coded_in_the_source(self):
        """A literal here is exactly how the two drifted."""
        root = pathlib.Path(__file__).resolve().parent.parent
        text = (root / "src" / "flow5ctl" / "__init__.py").read_text(encoding="utf-8")
        assert '__version__ = "' not in text


class TestTheBundledExamples:
    """The README's first command must work for someone who installed, not cloned.

    It said `init --file examples/rc-glider.yaml`, a path that exists only in a
    checkout, so the documentation's opening line failed for every user who ran
    `pip install flow5ctl`.
    """

    def test_they_are_force_included_into_the_wheel(self):
        import tomllib
        root = pathlib.Path(__file__).resolve().parent.parent
        cfg = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        inc = cfg["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
        for name in ("rc-glider", "hpa", "cg-sweep"):
            assert inc[f"examples/{name}.yaml"] == f"flow5ctl/examples/{name}.yaml"

    def test_one_can_be_found_by_name(self):
        from flow5ctl.cli import example_path
        p = example_path("rc-glider")
        assert p.is_file()
        assert "3 m F5J-style glider" in p.read_text(encoding="utf-8")

    def test_the_yaml_suffix_is_optional(self):
        from flow5ctl.cli import example_path
        assert example_path("rc-glider.yaml") == example_path("rc-glider")

    def test_an_unknown_name_lists_what_there_is(self):
        from flow5ctl.cli import example_path
        from flow5ctl.errors import Flow5ctlError
        with pytest.raises(Flow5ctlError, match="rc-glider"):
            example_path("nope")

    def test_every_shipped_example_is_a_valid_design_or_study(self):
        """A broken example is documentation that fails on first contact."""
        import yaml

        from flow5ctl.cli import example_path, examples
        from flow5ctl.model.design import Design
        names = examples()
        assert {"rc-glider", "hpa", "cg-sweep"} <= set(names)
        for name in names:
            raw = yaml.safe_load(example_path(name).read_text(encoding="utf-8"))
            if raw.get("schema", "").startswith("flow5ctl/study"):
                assert raw.get("vary", {}).get("parameter"), name
            else:
                raw["name"] = name
                Design.model_validate(raw)

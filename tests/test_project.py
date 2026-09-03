"""A design is a directory (ADR-0003)."""
from __future__ import annotations

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

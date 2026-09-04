"""Real flow5 runs. Skipped when flow5 is not installed.

These reproduce measured values from the PoC verification round, so they are the
regression net for anything that touches the solver path.
"""
from __future__ import annotations

import math

import pytest

from flow5ctl.errors import SolverNotFound
from flow5ctl.flow5 import probe as probe_mod
from flow5ctl.project.store import Project
from flow5ctl.usecases import analyze as analyze_uc
from flow5ctl.usecases import define

pytestmark = pytest.mark.needs_flow5


@pytest.fixture(scope="session")
def install():
    try:
        return probe_mod.probe()
    except SolverNotFound as exc:
        pytest.skip(str(exc))


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("FLOW5CTL_WORKSPACE", str(tmp_path / "ws"))
    return tmp_path


def test_probe_reads_the_version_from_the_program(install):
    """Never from the macOS bundle, which reported 7.70 for a 7.57 install."""
    assert install.version
    assert len(install.version.split(".")) == 2


def test_inviscid_rectangular_wing_reproduces_the_poc(install, rect_design, workspace):
    """PoC case A: CL_alpha 0.08525 /deg, static margin -0.59 % MAC, 520 panels.

    CL_alpha is 0.08516 here rather than the PoC's 0.08525 - 0.1 % - because the
    wake is now carried 20 spans downstream instead of flow5's default 30 chords.
    That the lift barely moves while the induced drag changes by tens of percent is
    the same split seen everywhere else in the wake investigation, and it is why the
    PoC's lift figure still stands as a cross-check.
    """
    define.create("Rect", rect_design)
    project = Project.resolve("Rect")
    out = analyze_uc.analyze(project, analyze_uc.Request(
        name="t1", polar_type="T1", speed=15.0, alpha=(0.0, 8.0, 2.0), viscous=False,
    ))
    assert out["status"] == "ok"
    assert out["points"] == 5
    assert out["panels"] == 520

    s = out["summary"]
    assert s["cl_alpha_per_deg"] == pytest.approx(0.08516, rel=1e-3)
    assert s["neutral_point_x"] == pytest.approx(0.05, abs=1e-3)
    assert s["static_margin"] == pytest.approx(-0.0059, abs=5e-4)

    # lifting-line theory for AR 10
    per_rad = s["cl_alpha_per_deg"] * 180 / math.pi
    helmbold = 2 * math.pi * 10 / (2 + math.sqrt(104))
    assert abs(per_rad / helmbold - 1) < 0.10

    assert any("INVISCID" in w for w in out["warnings"])
    assert (project.root / out["data"]).is_file()


def test_viscous_analysis_computes_and_then_caches_2d_polars(install, rect_design,
                                                             workspace):
    define.create("Rect", rect_design)
    project = Project.resolve("Rect")
    req = analyze_uc.Request(name="v1", polar_type="T1", speed=15.0,
                             alpha=(0.0, 6.0, 3.0), viscous=True)
    first = analyze_uc.analyze(project, req)
    assert first["airfoil_polars"]["computed"] is True
    assert first["airfoil_polars"]["count"] > 0
    # viscous drag must dominate at this Reynolds number
    assert first["summary"]["best_LD"]["value"] < 60

    second = analyze_uc.analyze(project, analyze_uc.Request(
        name="v2", polar_type="T1", speed=15.0, alpha=(0.0, 6.0, 3.0), viscous=True))
    assert second["airfoil_polars"]["cached"] is True
    assert second["runtime_s"] < first["runtime_s"] + 1.0


def test_the_reynolds_envelope_makes_a_fixed_lift_polar_converge(install, rect_design,
                                                                 workspace):
    """A mesh covering only cruise gave 1 of 6 points in the PoC; the derived
    envelope must give all of them.

    The sweep starts above zero lift because a fixed-lift polar has no solution where
    the aircraft produces none — see the test below.
    """
    define.create("Rect", rect_design)
    project = Project.resolve("Rect")
    out = analyze_uc.analyze(project, analyze_uc.Request(
        name="t2", polar_type="T2", alpha=(2.0, 8.0, 2.0), viscous=True))
    assert out["points"] == 4
    assert out["summary"]["min_sink"] is not None
    assert out["summary"]["min_sink"]["speed"] is not None


def test_a_fixed_lift_polar_at_zero_lift_is_diagnosed_precisely(install, rect_design,
                                                                workspace):
    """The failure looks like a Reynolds-range problem and is not one.

    flow5 reports a "viscous interpolation failure" at Re around 6e7 with Cl = 0.
    Telling the user to widen the polar mesh would send them the wrong way.
    """
    from flow5ctl.errors import SolverError
    define.create("Rect", rect_design)
    project = Project.resolve("Rect")
    with pytest.raises(SolverError, match="zero-lift angle"):
        analyze_uc.analyze(project, analyze_uc.Request(
            name="t2bad", polar_type="T2", alpha=(0.0, 8.0, 2.0), viscous=True))


def test_ground_effect_improves_lift_over_drag(install, rect_design, workspace):
    define.create("Rect", rect_design)
    project = Project.resolve("Rect")
    free = analyze_uc.analyze(project, analyze_uc.Request(
        name="free", polar_type="T1", speed=15.0, alpha=(4.0, 8.0, 4.0), viscous=True))
    ige = analyze_uc.analyze(project, analyze_uc.Request(
        name="ige", polar_type="T1", speed=15.0, alpha=(4.0, 8.0, 4.0), viscous=True,
        ground_effect=True, ground_height=0.3))
    assert ige["summary"]["best_LD"]["value"] > free["summary"]["best_LD"]["value"]


def test_stability_polar_returns_eigenvalues_not_nonsense(install, workspace):
    """A T1 polar would return eigenvalues of order 1e51; T7 must not."""
    raw = {
        "name": "Stab", "preset": "custom",
        "requirements": {"cruise_speed": 12.0},
        "mass": {"components": [
            {"tag": "fuse", "mass": 0.4, "at": [0.12, 0.0, 0.0]},
            {"tag": "nose", "mass": 0.2, "at": [-0.10, 0.0, 0.0]},
            {"tag": "wl", "mass": 0.1, "at": [0.05, -0.75, 0.02]},
            {"tag": "wr", "mass": 0.1, "at": [0.05, 0.75, 0.02]},
        ]},
        "airfoils": [{"name": "W", "source": "naca:2409"},
                     {"name": "T", "source": "naca:0009"}],
        "wing": {"airfoil": "W",
                 "planform": {"span": 3.0, "root_chord": 0.24, "taper": 0.55,
                              "dihedral": 3.0, "washout": -1.5},
                 "panels": {"chordwise": 11, "spanwise": 16}},
        "tail": {
            "type": "conventional",
            "elevator": {"position": [0.85, 0.0, 0.03], "incidence": -1.5, "airfoil": "T",
                         "planform": {"span": 0.48, "root_chord": 0.13, "taper": 0.7},
                         "panels": {"chordwise": 7, "spanwise": 6}},
            "fin": {"position": [0.85, 0.0, 0.05], "airfoil": "T",
                    "planform": {"span": 0.22, "root_chord": 0.16, "taper": 0.6},
                    "panels": {"chordwise": 7, "spanwise": 5}},
        },
    }
    define.create("Stab", raw)
    project = Project.resolve("Stab")
    out = analyze_uc.analyze(project, analyze_uc.Request(
        name="stab", polar_type="T7", speed=12.0, alpha=(0.0, 1.0, 1.0),
        viscous=True, stability=True))
    modes = out["summary"].get("longitudinal_modes")
    assert modes, "no longitudinal modes were parsed"
    assert all(abs(m["eigenvalue"][0]) < 1e4 for m in modes), "eigenvalues are nonsense"
    assert any(m["frequency_hz"] > 0 for m in modes), "no oscillatory mode found"
    assert out["summary"]["static_margin"] is not None


def test_a_design_referencing_a_missing_airfoil_never_reaches_flow5(install, rect_design,
                                                                    workspace):
    from flow5ctl.errors import DesignError
    raw = {**rect_design}
    raw["wing"] = {**raw["wing"], "airfoil": "Missing"}
    with pytest.raises(DesignError, match="not.*declared"):
        define.create("Bad", raw)



@pytest.mark.needs_flow5
class TestCgHeightSeparation:
    """The classical static margin and the pitch stiffness must be told apart.

    A CG below the wing's mean height adds a force-tilt term to −dCm/dCL. On a real
    human-powered aircraft that term was 29 percentage points, and reporting the sum
    as "static margin" put a perfectly conventional design 30 points outside its own
    preset's band.
    """

    @pytest.fixture
    def slung(self, rect_design):
        """The rectangular test wing with the mass hung well below it."""
        raw = {**rect_design, "mass": {"components": [
            {"tag": "low", "mass": 1.0, "at": [0.05, 0.0, -0.30]}]}}
        return raw

    def test_the_two_margins_differ_when_the_cg_is_low(self, install, slung, workspace):
        define.create("Slung", slung)
        out = analyze_uc.analyze(Project.resolve("Slung"), analyze_uc.Request(
            name="t", polar_type="T1", speed=15.0, alpha=(0.0, 8.0, 2.0), viscous=False))
        s = out["summary"]
        assert s["static_margin"] is not None
        assert s["pitch_stiffness_margin"] is not None
        assert s["pitch_stiffness_margin"] > s["static_margin"] + 0.02
        assert any("pitch stiffness" in w for w in out["warnings"])

    def test_the_classical_margin_does_not_move_with_cg_height(self, install,
                                                               rect_design, workspace):
        """It is a property of the aerodynamics and the CG's x, nothing else."""
        margins = []
        for i, z in enumerate((0.0, -0.20, -0.40)):
            raw = {**rect_design, "mass": {"components": [
                {"tag": "m", "mass": 1.0, "at": [0.05, 0.0, z]}]}}
            define.create(f"Z{i}", raw)
            out = analyze_uc.analyze(Project.resolve(f"Z{i}"), analyze_uc.Request(
                name="t", polar_type="T1", speed=15.0, alpha=(0.0, 8.0, 2.0),
                viscous=False))
            margins.append(out["summary"]["static_margin"])
        assert max(margins) - min(margins) < 0.02, \
            f"the classical margin moved with CG height: {margins}"

    def test_pitch_stiffness_does_move_with_cg_height(self, install, rect_design,
                                                      workspace):
        stiffness = []
        for i, z in enumerate((0.0, -0.40)):
            raw = {**rect_design, "mass": {"components": [
                {"tag": "m", "mass": 1.0, "at": [0.05, 0.0, z]}]}}
            define.create(f"S{i}", raw)
            out = analyze_uc.analyze(Project.resolve(f"S{i}"), analyze_uc.Request(
                name="t", polar_type="T1", speed=15.0, alpha=(0.0, 8.0, 2.0),
                viscous=False))
            stiffness.append(out["summary"]["pitch_stiffness_margin"])
        assert stiffness[1] > stiffness[0] + 0.05

    def test_no_second_pass_when_the_cg_is_at_wing_height(self, install, rect_design,
                                                          workspace):
        """The extra solver pass only happens when it changes the answer."""
        raw = {**rect_design, "mass": {"components": [
            {"tag": "m", "mass": 1.0, "at": [0.05, 0.0, 0.0]}]}}
        define.create("Level", raw)
        project = Project.resolve("Level")
        out = analyze_uc.analyze(project, analyze_uc.Request(
            name="t", polar_type="T1", speed=15.0, alpha=(0.0, 8.0, 2.0), viscous=False))
        s = out["summary"]
        assert s["pitch_stiffness_margin"] == pytest.approx(s["static_margin"])
        assert not (project.build / "out" / "t__zref").exists()


def test_a_sideslip_polar_reports_no_root_bending_moment(install, rect_design, workspace):
    """Alpha is held and beta swept, so there is no longitudinal operating point.

    It used to report one anyway - 1,186 N.m against a 3,680 N.m estimate on an HPA,
    the strips being read at whichever beta sorted to the middle. That reads as a
    structural finding and is not one, and the summary already refuses to report
    anything else longitudinal from a T5 run.
    """
    raw = dict(rect_design)
    raw["tail"] = {"type": "conventional", "fin": {
        "name": "Fin", "airfoil": "NACA0012", "position": [0.7, 0.0, 0.03],
        "planform": {"span": 0.2, "root_chord": 0.1}}}
    define.create("Side", raw)
    out = analyze_uc.analyze(Project.resolve("Side"), analyze_uc.Request(
        name="t5", polar_type="T5", speed=15.0, alpha=(-4.0, 4.0, 2.0), viscous=False,
    ))
    assert out["summary"]["sideslip_sweep"] is True
    assert out["structure"] is None
    assert any("no root bending moment from a sideslip polar" in n
               for n in out["notes"])


def test_no_stability_verdict_without_a_classical_margin(install, rect_design,
                                                         workspace, monkeypatch):
    """When the reference-height pass yields no polar, do not judge the number.

    `static_margin` still holds the pitch stiffness there, and on an aircraft whose
    CG hangs below the wing that is worth tens of points. Checking it against a
    static-margin band would read an unstable aircraft as stable, which is the one
    direction this guardrail must not fail in.
    """
    raw = dict(rect_design)
    raw["mass"] = {"components": [
        {"tag": "pilot", "mass": 5.0, "at": [0.05, 0.0, -0.6]},
        {"tag": "l", "mass": 0.5, "at": [0.05, -0.8, 0.0]},
        {"tag": "r", "mass": 0.5, "at": [0.05, 0.8, 0.0]},
    ]}
    raw["tail"] = {"type": "conventional", "elevator": {
        "airfoil": "NACA0012", "position": [0.8, 0.0, 0.05],
        "planform": {"span": 0.5, "root_chord": 0.1}}}
    define.create("LowCG", raw)
    project = Project.resolve("LowCG")

    # the case the branch exists for: the reference-height pass produced no polar
    monkeypatch.setattr(analyze_uc, "reference_polar", lambda *a, **k: None)

    out = analyze_uc.analyze(project, analyze_uc.Request(
        name="t1", polar_type="T1", speed=15.0, alpha=(0.0, 6.0, 2.0), viscous=False))
    text = " ".join(out["warnings"])
    assert "no stability verdict is given" in text
    assert "Treat it as pitch stiffness" in text
    # and none of stability.py's verdicts appear
    assert "diverges in pitch" not in text
    assert "asks for" not in text


def test_a_wing_alone_puts_its_neutral_point_at_the_quarter_chord(install, rect_design,
                                                                  workspace):
    """The physics check a tailless design makes available for free.

    For a wing on its own the neutral point is its aerodynamic centre, which thin
    aerofoil theory puts at the quarter chord. Measured on the shipped 3 m glider
    with the tail removed: x_np = 0.04747 m against a quarter chord of 0.04763 -
    0.3 %. It is also why the "wing only" note says the static margin is still
    meaningful and only the trim point is not.
    """
    import pathlib as _p

    import yaml

    from flow5ctl.usecases import trim as trim_uc
    root = _p.Path(__file__).resolve().parent.parent
    raw = yaml.safe_load((root / "examples" / "rc-glider.yaml").read_text())
    raw.pop("tail", None)
    define.create("WingAlone", raw)
    project = Project.resolve("WingAlone")

    out = trim_uc.trim(project, trim_uc.TrimRequest(
        target="static_margin", value=0.10, speed=12.0, alpha=(-4.0, 10.0, 1.0)))
    mac = out["geometry"]["reference_chord"] if "reference_chord" in out.get(
        "geometry", {}) else 0.1905
    np_x = out["solved"]["neutral_point_x"]
    assert np_x == pytest.approx(mac / 4.0, rel=0.02)
    assert any("neutral point and static margin are still" in n
               for n in out.get("notes", []))


def test_expanding_a_planform_changes_no_result(install, workspace):
    """DOMAIN-MODEL says shorthand never silently diverges from the truth.

    `expand` rewrites `planform` into explicit `sections`, and that expansion is the
    only way sections ever appear. If the two described different aeroplanes, a
    designer who expanded in order to hand-tune would find their numbers had moved
    before they touched anything. Checked on the shipped glider, all three surfaces.
    """
    import pathlib as _p

    import yaml

    from flow5ctl.usecases import edit as edit_uc
    root = _p.Path(__file__).resolve().parent.parent
    raw = yaml.safe_load((root / "examples" / "rc-glider.yaml").read_text())
    define.create("Expanded", raw)
    project = Project.resolve("Expanded")
    req = analyze_uc.Request(name="p", polar_type="T1", speed=12.0,
                             alpha=(0.0, 8.0, 2.0), viscous=False)

    before = analyze_uc.analyze(project, req, store=False)
    edit_uc.expand(project)
    after = analyze_uc.analyze(project, req, store=False)

    design = project.load()
    assert design.wing.sections is not None and design.wing.planform is None
    assert after["panels"] == before["panels"]
    assert after["summary"]["best_LD"]["value"] == \
        pytest.approx(before["summary"]["best_LD"]["value"])
    assert after["summary"]["cl_alpha_per_deg"] == \
        pytest.approx(before["summary"]["cl_alpha_per_deg"])


@pytest.mark.parametrize("polar_type", ["T1", "T2", "T5"])
def test_strip_reynolds_stays_proportional_to_chord(install, workspace, polar_type):
    """The spanwise chart recovers the chord from the strip Reynolds numbers.

    A reviewer said that inference was assumed rather than established, and listed
    the cases that might break it: a fixed-lift polar where the speed is solved per
    point, ground effect, sideslip. Measured on the shipped 34 m example, which has
    ground effect on by default and a taper ratio of 2.222:

    | polar | root Re | tip Re | ratio |
    |---|---|---|---|
    | T1 | 612,685 | 276,957 | 2.212 |
    | T2 | 561,166 | 253,668 | 2.212 |
    | T5 | 612,685 | 276,957 | 2.212 |

    The absolute values move - T2 solves a lower speed - but the ratio does not, and
    `_relative_chord` normalises by the maximum so only the ratio is used. Under
    sideslip the left and right Re are identical to the digit. The 2.212 against a
    taper of 2.222 is the outermost strip's centroid sitting inboard of the tip.
    """
    import pathlib as _p

    import yaml
    root = _p.Path(__file__).resolve().parent.parent
    raw = yaml.safe_load((root / "examples" / "hpa.yaml").read_text())
    define.create(f"Re{polar_type}", raw)
    project = Project.resolve(f"Re{polar_type}")
    alpha = (3.0, 7.0, 2.0) if polar_type != "T5" else (-6.0, 6.0, 3.0)
    out = analyze_uc.analyze(project, analyze_uc.Request(
        name="p", polar_type=polar_type, speed=8.0, alpha=alpha, viscous=False))

    # the strip table is written into the stored result, not the returned payload
    import json
    stored = json.loads((project.root / out["data"]).read_text(encoding="utf-8"))
    strips = (stored.get("strips") or {}).get("surfaces", {}).get("Main")
    assert strips, "no strip table"
    re = [v for v in strips["Re"] if v]
    assert max(re) / min(re) == pytest.approx(2.212, abs=0.01)


def test_the_two_margins_do_not_contradict_each_other(install, workspace):
    """Static margin is -dCm/dCL, so the two have to come from the same pass.

    `dcm_dcl` was kept from the first pass while `static_margin` was replaced by the
    reference-height pass's, so one payload reported a static margin of +8.7 % beside
    a dcm_dcl of -0.2222. A reader computing -dCm/dCL got 0.2222 - two and a half
    times the number printed next to it.

    The about-the-real-CG value is not lost. It is `pitch_stiffness_margin`, which is
    what it is, and `trim_alpha` stays from the first pass because the aircraft trims
    where Cm about its *real* CG is zero: moving the reference height moves the
    crossing from 3.601 deg to 6.003 deg, and the second is a condition it never
    reaches.
    """
    import pathlib as _p

    import yaml
    root = _p.Path(__file__).resolve().parent.parent
    raw = yaml.safe_load((root / "examples" / "hpa.yaml").read_text())
    define.create("Margins", raw)
    out = analyze_uc.analyze(Project.resolve("Margins"), analyze_uc.Request(
        name="m", polar_type="T1", alpha=(0.0, 8.0, 2.0), viscous=False))

    s = out["summary"]
    # both identities hold, and the payload rounds, so compare at what it prints
    assert s["static_margin"] == pytest.approx(-s["dcm_dcl"], abs=1e-3)
    assert s["pitch_stiffness_margin"] == pytest.approx(-s["dcm_dcl_about_cg"], abs=1e-3)
    # and the two margins are genuinely different on this aircraft
    assert s["pitch_stiffness_margin"] > s["static_margin"] + 0.05

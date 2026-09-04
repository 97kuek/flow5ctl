"""Run one analysis, end to end.

Two flow5 invocations, always: 2D airfoil polars first, then the plane analysis.
A single script containing both segfaults flow5 (ADR-0009). The 2D polars are the
expensive half (~15 s against ~1 s for the 3D run), so they are cached on the
airfoil set and Reynolds range and reused until one of those changes.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..advisor import guardrails
from ..errors import InternalError, SolverError
from ..flow5 import airfoils as foil_io
from ..flow5 import foilpolar, xmlgen
from ..flow5 import probe as probe_mod
from ..flow5.markers import explain_interpolation_failure
from ..flow5.results import owning_polar, parse_polar, parse_strips
from ..flow5.runner import DEFAULT_TIMEOUT, Workspace, run_script
from ..flow5.summary import summarise
from ..geometry import derived as geometry
from ..geometry.derived import Derived
from ..model import presets
from ..model.design import Design
from ..project.store import Project

MANIFEST = ".manifest.json"


@dataclass(slots=True)
class Request:
    """What to analyse. SI units; `None` means "take it from the preset or design"."""

    name: str = "cruise"
    polar_type: str = "T1"
    method: str | None = None
    speed: float | None = None
    alpha: tuple[float, float, float] | None = None
    fixed_alpha: float | None = None
    viscous: bool | None = None
    on_the_fly: bool | None = None
    ncrit: float | None = None
    ground_effect: bool | None = None
    ground_height: float | None = None
    mass: float | None = None
    cg_x: float | None = None
    cg_z: float | None = None
    stability: bool = False
    export_stl: bool = False
    export_cp: bool = False
    timeout: float = DEFAULT_TIMEOUT
    recompute_polars: bool = False
    extra_notes: list[str] = field(default_factory=list)


def _polar_key(design: Design, reynolds: list[float], alpha: tuple[float, float, float],
               ncrit: float, coords: dict[str, list[tuple[float, float]]]) -> str:
    """Cache key: the airfoil geometry plus the mesh actually requested."""
    h = hashlib.sha256()
    for name in sorted(coords):
        h.update(name.encode())
        for x, y in coords[name]:
            h.update(f"{x:.6f},{y:.6f};".encode())
    h.update(json.dumps({
        "reynolds": [round(r) for r in reynolds],
        "alpha": [round(v, 4) for v in alpha],
        "ncrit": round(ncrit, 3),
    }, sort_keys=True).encode())
    return h.hexdigest()[:16]


def _write_foils(ws: Workspace, design: Design, project_root: Path
                 ) -> tuple[list[str], dict[str, list[tuple[float, float]]]]:
    names, coords = [], {}
    for a in design.airfoils:
        pts = foil_io.resolve(a.name, a.source, project_root)
        coords[a.name] = pts
        path = foil_io.write_dat(ws.foils / f"{a.name}.dat", a.name, pts)
        names.append(path.name)
    return names, coords


def _ensure_foil_polars(ws: Workspace, install: probe_mod.Flow5Install, design: Design,
                        derived: Derived, preset: presets.Preset, req: Request,
                        foil_files: list[str],
                        coords: dict[str, list[tuple[float, float]]]) -> dict[str, Any]:
    """Pass 1. Returns a report; skips the run when the cache is still valid."""
    declared = [a.polars.reynolds for a in design.airfoils if a.polars.reynolds]
    if declared:
        reynolds = sorted({r for group in declared for r in group})
    else:
        cl_max = float(preset.analysis.get("cl_max_estimate", 1.2))
        lo, hi = derived.reynolds_envelope(cl_max)
        reynolds = _log_ladder(lo, hi)

    ncrit = req.ncrit if req.ncrit is not None else float(preset.analysis.get("ncrit", 9.0))
    alpha_spec = design.airfoils[0].polars.alpha if design.airfoils else (-10.0, 16.0, 0.5)

    key = _polar_key(design, reynolds, alpha_spec, ncrit, coords)
    manifest = ws.xfoil_polars / MANIFEST
    cached = None
    if manifest.exists():
        try:
            cached = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            cached = None

    if (not req.recompute_polars and cached and cached.get("key") == key
            and ws.cached_polar_count() > 0):
        return {
            "computed": False,
            "cached": True,
            "count": ws.cached_polar_count(),
            "reynolds": reynolds,
            "ncrit": ncrit,
            "gaps": cached.get("gaps", []),
            "gap_warning": cached.get("gap_warning"),
        }

    shutil.rmtree(ws.xfoil_polars, ignore_errors=True)
    ws.xfoil_polars.mkdir(parents=True, exist_ok=True)

    pass1_out = ws.root / "foil_out"
    shutil.rmtree(pass1_out, ignore_errors=True)
    pass1_out.mkdir(parents=True, exist_ok=True)

    script = ws.root / "foil_script.xml"
    script.write_text(
        xmlgen.foil_script(
            project="foils",
            dirs=xmlgen.Dirs(output=pass1_out, foils=ws.foils),
            foil_files=foil_files,
            reynolds=reynolds,
            alpha=alpha_spec,
            ncrit=ncrit,
        ),
        encoding="utf-8",
    )
    result = run_script(install.path, script, timeout=req.timeout)
    if result.diagnosis.outcome.name == "CRASHED":
        result.raise_for_status()

    staged = ws.stage_foil_polars(pass1_out)
    if staged == 0:
        raise SolverError(
            "flow5 produced no 2D airfoil polars. Nothing can be interpolated, so the "
            "viscous analysis would fail.\n"
            f"flow5 said:\n{result.stdout[-1200:]}"
        )
    # `staged > 0` only says polars exist, not that they cover the range asked for.
    # XFoil drops the points it cannot converge and flow5 reports no error, so a
    # polar with a hole in the middle of the operating range looks like a success.
    gaps = foilpolar.find_gaps(ws.xfoil_polars, alpha_spec[2])
    gap_warning = foilpolar.describe(gaps) if gaps else None

    manifest.write_text(json.dumps({
        "key": key, "reynolds": reynolds, "ncrit": ncrit,
        "alpha": list(alpha_spec), "count": staged,
        "gaps": [g.as_dict() for g in gaps], "gap_warning": gap_warning,
        "flow5_version": install.version,
    }, indent=2), encoding="utf-8")
    return {
        "computed": True,
        "cached": False,
        "count": staged,
        "reynolds": reynolds,
        "ncrit": ncrit,
        "gaps": [g.as_dict() for g in gaps],
        "gap_warning": gap_warning,
        "seconds": round(result.elapsed, 1),
    }


def _log_ladder(lo: float, hi: float, per_decade: int = 3) -> list[float]:
    """A Reynolds ladder that BRACKETS [lo, hi], on values a human recognises.

    The endpoints are rounded outwards, never inwards. A mesh that stops just short
    of the Reynolds number the wing actually reaches is the difference between five
    converged operating points and one — measured, see ADR-0009.
    """
    import math

    def snap(v: float, up: bool) -> float:
        mag = 10 ** math.floor(math.log10(v))
        step = mag / 2.0
        return (math.ceil(v / step) if up else math.floor(v / step)) * step

    lo = snap(max(lo, 5.0e3), up=False)
    hi = snap(max(hi, lo * 2), up=True)
    n = max(3, round(per_decade * math.log10(hi / lo)) + 1)
    out = {lo, hi}
    for i in range(1, n - 1):
        v = lo * (hi / lo) ** (i / (n - 1))
        mag = 10 ** math.floor(math.log10(v))
        out.add(round(v / mag * 2) / 2 * mag)
    return sorted(v for v in out if lo <= v <= hi)


def _ranges_for(polar_type: str, alpha: tuple[float, float, float]) -> xmlgen.PlaneRanges:
    pt = polar_type.upper()
    if pt in {"T1", "T2"}:
        return xmlgen.PlaneRanges(t12=alpha)
    if pt == "T3":
        return xmlgen.PlaneRanges(t3=alpha)
    if pt == "T5":
        return xmlgen.PlaneRanges(t5=alpha)
    if pt == "T7":
        return xmlgen.PlaneRanges(t7=alpha)
    return xmlgen.PlaneRanges(extra={f"{pt}_Range": alpha})


def analyze(project: Project, req: Request, *, flow5: str | None = None,
            design: Design | None = None, store: bool = True) -> dict[str, Any]:
    """Run one analysis and return a summary, never the table (ADR-0004).

    `design` overrides what is on disk without writing to it, which is how `sweep`
    varies a geometric parameter without mutating the user's design.yaml.
    `store=False` skips writing a result file, for the throwaway runs a solver
    iteration makes.
    """
    install = probe_mod.probe(flow5)
    design = design if design is not None else project.load()
    preset = presets.load(design.preset)
    derived = geometry.solve(design)

    method = (req.method or preset.analysis.get("method", "VLM2")).upper()
    viscous = req.viscous if req.viscous is not None else bool(preset.analysis.get("viscous", True))
    on_the_fly = (req.on_the_fly if req.on_the_fly is not None
                  else bool(preset.analysis.get("on_the_fly", False)))
    ncrit = req.ncrit if req.ncrit is not None else float(preset.analysis.get("ncrit", 9.0))
    alpha = tuple(req.alpha or preset.analysis.get("alpha", (-2.0, 10.0, 1.0)))  # type: ignore[arg-type]

    ground = req.ground_height
    want_ground = (req.ground_effect if req.ground_effect is not None
                   else bool(preset.analysis.get("ground_effect", False)))
    if ground is None and want_ground:
        ground = design.requirements.ground_effect_height
    if not want_ground:
        ground = None

    speed = req.speed
    if speed is None and req.polar_type.upper() in {"T1", "T5", "T7"}:
        speed = derived.cruise_speed
        if speed is None:
            raise SolverError(
                f"a {req.polar_type} polar needs a speed. Give `speed`, or set "
                "`requirements.cruise_speed` in the design."
            )

    # ---- guardrails, before anything is written ----
    guardrails.check_polar_type(
        req.polar_type, wants_stability=req.stability, derivatives=req.stability
    )
    geo_check = guardrails.check_geometry(derived, preset)
    an_check = guardrails.check_analysis(
        derived, preset, polar_type=req.polar_type, alpha=alpha,
        viscous=viscous, on_the_fly=on_the_fly, ground_height=ground,
    )

    warnings = [*geo_check.warnings, *an_check.warnings]
    notes = [*geo_check.notes, *an_check.notes, *req.extra_notes]
    if not install.verified:
        warnings.insert(0, install.note)

    with project.lock():
        ws = Workspace(project.build).prepare(keep_polars=not req.recompute_polars)
        foil_files, coords = _write_foils(ws, design, project.root)

        polars_report: dict[str, Any] = {"computed": False, "cached": False, "count": 0}
        if viscous and not on_the_fly:
            polars_report = _ensure_foil_polars(
                ws, install, design, derived, preset, req, foil_files, coords
            )
            if polars_report["computed"]:
                notes.append(
                    f"2D polars for {len(coords)} airfoil(s) were computed automatically: "
                    f"{polars_report['count']} polars over Re "
                    f"{polars_report['reynolds'][0]:,.0f}–{polars_report['reynolds'][-1]:,.0f} "
                    f"in {polars_report['seconds']} s."
                )
            else:
                notes.append(f"reused {polars_report['count']} cached 2D polars.")
            if polars_report.get("gap_warning"):
                warnings.append(polars_report["gap_warning"])

        # ---- pass 2 ----
        (ws.planes / "plane.xml").write_text(xmlgen.plane_xml(design, derived), encoding="utf-8")
        cg_actual = (
            req.cg_x if req.cg_x is not None else derived.mass.cg[0],
            derived.mass.cg[1],
            req.cg_z if req.cg_z is not None else derived.mass.cg[2],
        )

        def one_pass(polar_name: str, cg: tuple[float, float, float]) -> Any:
            spec = xmlgen.AnalysisSpec(
                name=polar_name, polar_type=req.polar_type, method=method, speed=speed,
                alpha_deg=req.fixed_alpha, viscous=viscous, on_the_fly=on_the_fly,
                ncrit=ncrit, ground_height=ground, mass=req.mass, cg=cg,
            )
            (ws.analyses / f"{polar_name}.xml").write_text(
                xmlgen.polar_xml(spec, design.name, derived), encoding="utf-8"
            )
            script = ws.root / f"plane_script_{polar_name}.xml"
            script.write_text(
                xmlgen.plane_script(
                    project=polar_name,
                    dirs=xmlgen.Dirs(
                        output=ws.out, foils=ws.foils, planes=ws.planes,
                        analyses=ws.analyses,
                        xfoil_polars=ws.xfoil_polars if (viscous and not on_the_fly) else None,
                    ),
                    foil_files=foil_files,
                    ranges=_ranges_for(req.polar_type, alpha),
                    outputs=xmlgen.PlaneOutputs(
                        cp=req.export_cp, stl=req.export_stl, derivatives=req.stability
                    ),
                ),
                encoding="utf-8",
            )
            r = run_script(install.path, script, timeout=req.timeout)
            if not r.ok:
                _explain_failure(r, ws, req, polars_report)
                r.raise_for_status()
            return r

        # Only the requested analysis is kept; the reference-height pass below exists
        # solely to separate the classical static margin from the pitch stiffness.
        for stale in ws.analyses.glob("*.xml"):
            if stale.stem != req.name:
                stale.unlink()
        run = one_pass(req.name, cg_actual)

        reference_run = None
        z_offset = (cg_actual[2] - derived.reference_height) / derived.reference_chord
        if abs(z_offset) > 0.05:
            # dCm/dCL about a vertically offset CG is not the classical static margin:
            # as alpha rises the force vector tilts, and its line of action moves
            # relative to the CG. Re-running with the moment referenced to the wing's
            # own mean height separates the two exactly, and costs one 3D pass because
            # the expensive 2D polars are already cached.
            ref_name = f"{req.name}__zref"
            for stale in ws.analyses.glob("*.xml"):
                stale.unlink()
            reference_run = one_pass(
                ref_name, (cg_actual[0], cg_actual[1], derived.reference_height)
            )

    # ---- read the results ----
    polar_csv = ws.project_dir(req.name) / design.name / f"{req.name}.csv"
    if not polar_csv.is_file():
        candidates = sorted(ws.project_dir(req.name).rglob("*.csv"))
        raise InternalError(
            f"flow5 reported success but wrote no polar at {polar_csv}. "
            f"Found instead: {[str(c.name) for c in candidates[:6]]}"
        )
    polar = parse_polar(polar_csv)
    log = run.stdout
    log_file = ws.project_dir(req.name) / f"{req.name}.log"
    if log_file.is_file():
        log += "\n" + log_file.read_text(encoding="utf-8", errors="replace")

    summary = summarise(
        polar, mac=derived.reference_chord, cg_x=cg_actual[0], log=log,
        cg_height_offset_mac=z_offset,
    )
    warnings.extend(summary.warnings)

    # Separate the classical static margin from the pitch stiffness about the real CG.
    summary.pitch_stiffness_margin = summary.static_margin
    if reference_run is not None:
        ref_csv = (ws.project_dir(f"{req.name}__zref") / design.name
                   / f"{req.name}__zref.csv")
        if ref_csv.is_file():
            ref = summarise(parse_polar(ref_csv), mac=derived.reference_chord,
                            cg_x=cg_actual[0], cg_height_offset_mac=0.0)
            warnings.extend(w for w in ref.warnings if w not in warnings)
            summary.static_margin = ref.static_margin
            summary.neutral_point_x = ref.neutral_point_x or summary.neutral_point_x
            if (summary.static_margin is not None
                    and summary.pitch_stiffness_margin is not None):
                gap = summary.pitch_stiffness_margin - summary.static_margin
                if abs(gap) > 0.02:
                    warnings.append(
                        f"the CG sits {abs(z_offset):.2f} MAC "
                        f"{'below' if z_offset < 0 else 'above'} the wing's mean height, "
                        f"which adds {gap:+.1%} to the pitch stiffness that is NOT part "
                        "of the classical static margin. Reported: static margin "
                        f"{summary.static_margin:+.1%} (the number tail-sizing rules and "
                        "published CG bands refer to), pitch stiffness "
                        f"{summary.pitch_stiffness_margin:+.1%} (what the aircraft "
                        "actually resists a disturbance with). Do not compare the "
                        "second against a textbook band."
                    )
        else:
            warnings.append(
                "the reference-height pass produced no polar, so the reported static "
                "margin still includes the CG-height term. Treat it as pitch stiffness."
            )

    if run.discarded:
        warnings.append(
            f"{run.discarded} operating point(s) failed to converge and were discarded "
            "by flow5. The polar is incomplete."
        )
    if req.stability and not summary.longitudinal_modes:
        warnings.append(
            "no eigenvalue block was found in flow5's log, so dynamic modes are "
            "unavailable even though a stability polar was requested."
        )

    payload: dict[str, Any] = {
        "status": "ok",
        "design": design.name,
        "polar": req.name,
        "polar_type": req.polar_type.upper(),
        "conditions": {
            "method": method,
            "speed": speed,
            "alpha_range": list(alpha),
            "viscous": viscous,
            "viscous_method": None if not viscous else ("on-the-fly" if on_the_fly else "interpolated"),
            "ncrit": ncrit if viscous else None,
            "ground_height": ground,
            "mass": req.mass or derived.mass.total,
            "cg_x": req.cg_x or derived.mass.cg[0],
        },
        "points": summary.points,
        "runtime_s": round(run.elapsed, 2),
        "panels": run.panels or derived.panel_count,
        "flow5_version": install.version,
        "summary": summary.as_dict(),
        "geometry": derived.as_dict(),
        "airfoil_polars": polars_report,
        "warnings": warnings,
        "notes": notes,
        "data": None,
        "flow5_output": str(polar_csv),
    }
    if store:
        stored = project.write_result(req.name, {
            **payload,
            "columns": polar.columns,
            "rows": polar.rows,
            "strips": _strip_data(ws, req.name, design.name,
                                  at_alpha=summary.best_ld.alpha if summary.best_ld
                                  else summary.trim_alpha),
        })
        payload["data"] = str(stored.relative_to(project.root))
        project.update_state(
            flow5_version=install.version,
            last_analysis=req.name,
            last_polar_type=req.polar_type.upper(),
        )
    payload["_polar_columns"] = polar.columns
    payload["_polar_rows"] = polar.rows
    return payload


def _explain_failure(run, ws: Workspace, req: Request,
                     polars_report: dict[str, Any]) -> None:
    """Replace a generic solver message with the specific cause, where we can find it.

    flow5 writes the useful detail into the run log rather than stdout, and the same
    marker covers two unrelated causes — see `explain_interpolation_failure`.
    """
    log = run.stdout
    log_file = ws.project_dir(req.name) / f"{req.name}.log"
    if log_file.is_file():
        log += "\n" + log_file.read_text(encoding="utf-8", errors="replace")

    reynolds = polars_report.get("reynolds") or []
    if reynolds:
        cover = foilpolar.cl_coverage(ws.xfoil_polars)
        cl_cover = ((min(lo for lo, _ in cover.values()),
                     max(hi for _, hi in cover.values())) if cover else None)
        detail = explain_interpolation_failure(
            log, min(reynolds), max(reynolds), cl_cover=cl_cover)
        if detail:
            from ..errors import SolverError
            raise SolverError(detail)


#: Strip columns worth keeping. `Cl` drives the spanwise loading plot and
#: `Bending.mom` is what an HPA spar is sized from; the rest of the ~19 columns are
#: not worth carrying in every result file.
_STRIP_COLUMNS = ("y(m)", "Re", "Cl", "Cd_i", "Cd_v", "Bending.mom")


#: `-2_00°_ 7_60m_s.csv` — flow5 pads the angle with a space, so a filename sort puts
#: every negative angle AFTER every positive one ('-' is 0x2D, ' ' is 0x20).
_OPPOINT_ALPHA = re.compile(r"^\s*(-?\d+)_(\d+)°")


def _oppoint_alpha(path: Path) -> float | None:
    m = _OPPOINT_ALPHA.match(path.name)
    if not m:
        return None
    whole, frac = m.group(1), m.group(2)
    value = float(f"{whole}.{frac}")
    return value


def _strip_data(ws: Workspace, polar_name: str, plane: str,
                at_alpha: float | None = None) -> dict[str, Any] | None:
    """Copy the spanwise strip table into the durable result.

    `build/` is cleared by the next analysis, so anything a chart needs later has to
    live in `results/`. Only the columns a plot or a spar calculation uses are kept.

    The operating-point file is matched on the polar name written INSIDE it: flow5
    duplicates these files into every polar's directory and fills them with another
    polar's contents (FLOW5-INTERFACE.md section 5.1).

    **Which operating point matters.** A spanwise lift distribution and a spar load
    are read at one angle of attack, and it has to be the one the rest of the report
    is about - `at_alpha` is normally where best L/D falls. This used to take the
    middle file by filename, which is not the middle angle: flow5 pads the angle with
    a space, so a sweep of -2..8 sorts as 0, 2, 4, 6, 8, -2 and the "middle" was 6°.
    Every spanwise plot was drawn at an angle nobody chose, six degrees from the
    operating point on that example, with nothing in the output saying so.
    """
    root = ws.project_dir(polar_name) / plane / polar_name
    if not root.is_dir():
        return None
    files = [p for p in sorted(root.glob("*.csv")) if owning_polar(p) == polar_name]
    if not files:
        return None

    alphas = [(_oppoint_alpha(f), f) for f in files]
    known = [(a, f) for a, f in alphas if a is not None]
    if known and at_alpha is not None:
        chosen = min(known, key=lambda af: abs(af[0] - at_alpha))[1]
    elif known:
        known.sort()
        chosen = known[len(known) // 2][1]    # the middle ANGLE, not the middle name
    else:
        chosen = files[len(files) // 2]
    out: dict[str, Any] = {"source": chosen.name,
                           "alpha": _oppoint_alpha(chosen),
                           "surfaces": {}}
    for wing, table in parse_strips(chosen).items():
        keep = {c: table.columns.index(c) for c in _STRIP_COLUMNS if c in table.columns}
        if "y(m)" not in keep or "Cl" not in keep:
            continue
        out["surfaces"][wing] = {c: [r[i] for r in table.rows] for c, i in keep.items()}
    return out if out["surfaces"] else None

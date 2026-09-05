"""Solve for a condition instead of sweeping towards it.

These are the questions designers actually ask — "what angle of attack holds level
flight at 8 m/s?", "where does the CG have to be for 10 % static margin?" — and doing
them inside the tool stops an agent burning ten tool calls on a bisection it will
get slightly wrong.

Two of the four need no iteration at all:

* Lift is linear in alpha over the usable range, so one polar plus interpolation
  answers any CL or level-flight question.
* The neutral point does not move with the CG. Verified: for one aircraft, XNP came
  out at 0.0941 m from CG positions of 0.030, 0.060 and 0.090 m, with the static
  margin varying linearly at exactly 1/MAC. So a target static margin is a closed-form
  solve, and the second run is only there to confirm it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise
from typing import Any, Literal

from ..errors import DesignError, SolverError
from ..geometry import derived as geometry
from ..project.store import Project
from ..units import GRAVITY
from .analyze import Request, analyze

Target = Literal["cl", "level", "speed", "static_margin", "pitch"]

MAX_ITERATIONS = 8


@dataclass(slots=True)
class TrimRequest:
    target: Target
    value: float | None = None
    speed: float | None = None
    alpha: float | None = None
    mass: float | None = None
    alpha_range: tuple[float, float, float] | None = None
    tolerance: float = 1e-3
    viscous: bool | None = None
    ground_effect: bool | None = None
    timeout: float = 900.0


def _interpolate(xs: list[float], ys: list[float], want: float) -> float | None:
    """x at which y = want, by linear interpolation between bracketing points."""
    pairs = sorted(
        ((x, y) for x, y in zip(xs, ys, strict=True)
         if math.isfinite(x) and math.isfinite(y)),
        key=lambda p: p[0],
    )
    for (x0, y0), (x1, y1) in pairwise(pairs):
        if (y0 - want) == 0.0:
            return x0
        if (y0 - want < 0) != (y1 - want < 0):
            return x0 + (x1 - x0) * (want - y0) / (y1 - y0)
    return None


def _column(result: dict[str, Any], label: str) -> list[float]:
    columns: list[str] = result["_polar_columns"]
    rows: list[list[float]] = result["_polar_rows"]
    idx = None
    if label in columns:
        idx = columns.index(label)
    else:
        for i, name in enumerate(columns):
            if name.split(" (")[0].strip() == label:
                idx = i
                break
    if idx is None:
        raise SolverError(f"the polar has no {label!r} column")
    return [r[idx] for r in rows]


def _base_request(name: str, req: TrimRequest, speed: float | None) -> Request:
    return Request(
        name=name,
        polar_type="T1",
        speed=speed,
        alpha=req.alpha_range or (-4.0, 10.0, 1.0),
        viscous=req.viscous,
        ground_effect=req.ground_effect,
        mass=req.mass,
        timeout=req.timeout,
    )


def required_cl(mass: float, density: float, area: float, speed: float) -> float:
    """CL for level flight: L = W."""
    q = 0.5 * density * speed * speed * area
    if q <= 0:
        raise DesignError("cannot compute required CL at zero speed")
    return mass * GRAVITY / q


def trim(project: Project, req: TrimRequest, *, flow5: str | None = None) -> dict[str, Any]:
    design = project.load()
    d = geometry.solve(design)
    mass = req.mass if req.mass is not None else d.mass.total

    if req.target in {"cl", "level", "pitch"}:
        speed = req.speed if req.speed is not None else d.cruise_speed
        if speed is None:
            raise DesignError(
                "give --speed, or set requirements.cruise_speed in the design"
            )
    else:
        speed = req.speed if req.speed is not None else d.cruise_speed

    runs: list[dict[str, Any]] = []

    def run(name: str, **kw: Any) -> dict[str, Any]:
        r = _base_request(name, req, speed)
        for k, v in kw.items():
            setattr(r, k, v)
        out = analyze(project, r, flow5=flow5, store=False,
                      design=kw.pop("_design", None) or design)
        runs.append(out)
        return out

    # ---------------- alpha for a target CL, or for level flight ----------------
    if req.target in {"cl", "level"}:
        if req.target == "level":
            want = required_cl(mass, d.density, d.reference_area, speed)
        else:
            if req.value is None:
                raise DesignError("--value is required for target 'cl'")
            want = req.value

        out = run("trim_cl")
        alpha = _column(out, "α")
        cl = _column(out, "CL")
        solved = _interpolate(alpha, cl, want)
        if solved is None:
            raise SolverError(
                f"CL = {want:.4f} is not reached within the alpha range "
                f"{min(alpha):g}..{max(alpha):g}° (CL spans {min(cl):.3f} to "
                f"{max(cl):.3f}). Widen --alpha-range, or reduce the mass or wing loading."
            )
        # Refine: the first sweep locates alpha on a coarse grid, which is fine for a
        # quantity as linear as CL but not for L/D. A second run centred on the solved
        # angle gives the drag and moment at the condition itself rather than
        # interpolated between grid points, and costs well under a second.
        refined = run("trim_cl_refine", alpha=(solved - 0.5, solved + 0.5, 0.5))
        r_alpha = _column(refined, "α")
        exact = _closest(r_alpha, solved)
        if exact is not None and abs(r_alpha[exact] - solved) < 0.05:
            cl_x = _column(refined, "CL")[exact]
            cd = _column(refined, "CD")[exact]
            ld = _column(refined, "CL/CD")[exact]
            cm = _column(refined, "Cm")[exact]
            residual = cl_x - want
        else:
            ld = _interp_at(cl, _column(out, "CL/CD"), want)
            cd = _interp_at(cl, _column(out, "CD"), want)
            cm = _interp_at(cl, _column(out, "Cm"), want)
            residual = None
        return _payload(
            req, design.name, speed, mass, runs,
            solved={"alpha": round(solved, 4), "cl": round(want, 5),
                    "cd": None if cd is None else round(cd, 6),
                    "L_over_D": None if ld is None else round(ld, 3),
                    "cm": None if cm is None else round(cm, 6)},
            note=("Level flight at this speed needs CL = "
                  f"{want:.4f}, reached at alpha = {solved:.2f}°."
                  if req.target == "level" else
                  f"CL = {want:.4f} is reached at alpha = {solved:.2f}°."),
            extra={
                "trimmed_at_zero_moment": abs(cm) < 5e-3 if cm is not None else None,
                "cl_residual": None if residual is None else round(residual, 6),
                "values_are_exact": residual is not None,
            },
        )

    # ---------------- speed for level flight at a given alpha ----------------
    if req.target == "speed":
        if req.alpha is None:
            raise DesignError("--alpha is required for target 'speed'")
        probe_speed = speed or 10.0
        out = run("trim_speed", speed=probe_speed)
        cl_at_alpha = _interp_at(_column(out, "α"), _column(out, "CL"), req.alpha)
        if cl_at_alpha is None or cl_at_alpha <= 0:
            raise SolverError(
                f"CL at alpha = {req.alpha:g}° is "
                f"{'unavailable' if cl_at_alpha is None else f'{cl_at_alpha:.4f}'}; "
                "level flight needs positive lift."
            )
        v = math.sqrt(2 * mass * GRAVITY / (d.density * d.reference_area * cl_at_alpha))
        return _payload(
            req, design.name, probe_speed, mass, runs,
            solved={"speed": round(v, 4), "alpha": req.alpha,
                    "cl": round(cl_at_alpha, 5)},
            note=(f"At alpha = {req.alpha:g}° the aircraft holds level flight at "
                  f"{v:.2f} m/s."),
            extra={"note_on_viscosity":
                   "Drag was evaluated at the probe speed, so quote the speed, not the L/D."},
        )

    # ---------------- CG for a target static margin ----------------
    if req.target == "static_margin":
        if req.value is None:
            raise DesignError("--value is required for target 'static_margin'")
        want = req.value
        mac = d.reference_chord
        first = run("trim_sm_probe")
        sm0 = first["summary"].get("static_margin")
        cg0 = first["conditions"]["cg_x"]
        if sm0 is None:
            raise SolverError(
                "the probe run produced no static margin, so the CG cannot be solved. "
                "The alpha range may be too narrow to fit a moment slope."
            )
        # the neutral point does not move with the CG, so this is exact
        x_np = cg0 + sm0 * mac
        cg_target = x_np - want * mac

        check = run("trim_sm_check", cg_x=cg_target)
        achieved = check["summary"].get("static_margin")
        warnings = list(check["warnings"])
        if achieved is not None and abs(achieved - want) > max(0.005, abs(want) * 0.05):
            warnings.append(
                f"the confirming run gave a static margin of {achieved:+.3f} rather than "
                f"the requested {want:+.3f}. The moment slope is not perfectly linear; "
                "treat the CG as approximate and check it directly."
            )
        return _payload(
            req, design.name, speed, mass, runs,
            solved={"cg_x": round(cg_target, 5),
                    "static_margin": None if achieved is None else round(achieved, 4),
                    "neutral_point_x": round(x_np, 5),
                    "cg_percent_mac": round((cg_target - d.main.geom.mac_le_x) / mac, 4),
                    "shift_from_current": round(cg_target - d.mass.cg[0], 5)},
            note=(f"A static margin of {want:+.1%} needs the CG at x = {cg_target:.4f} m "
                  f"({(cg_target - d.main.geom.mac_le_x) / mac * 100:.1f} % MAC), which is "
                  f"{abs(cg_target - d.mass.cg[0]) * 1000:.0f} mm "
                  f"{'forward of' if cg_target < d.mass.cg[0] else 'aft of'} the current CG. "
                  "The neutral point is at "
                  f"x = {x_np:.4f} m."),
            warnings=warnings,
        )

    # ---------------- elevator incidence for zero pitching moment ----------------
    if req.target == "pitch":
        if design.tail.elevator is None:
            raise DesignError(
                "there is no elevator to trim. Add tail.elevator, or use "
                "target 'static_margin' to place the CG instead."
            )
        alpha_at = req.alpha
        if alpha_at is None:
            if req.value is not None:
                alpha_at = None  # solve for the alpha that also gives CL = value
            else:
                want_cl = required_cl(mass, d.density, d.reference_area, speed)
                probe = run("trim_pitch_probe")
                alpha_at = _interpolate(_column(probe, "α"), _column(probe, "CL"), want_cl)
                if alpha_at is None:
                    raise SolverError(
                        "level flight is not reachable within the alpha range, so there "
                        "is no condition to trim at."
                    )

        history: list[tuple[float, float]] = []
        incidence = design.tail.elevator.incidence
        for step in range(MAX_ITERATIONS):
            variant = design.model_copy(deep=True)
            variant.tail.elevator.incidence = incidence
            out = analyze(
                project,
                _base_request(f"trim_pitch_{step}", req, speed),
                flow5=flow5, store=False, design=variant,
            )
            runs.append(out)
            cm = _interp_at(_column(out, "α"), _column(out, "Cm"), alpha_at)
            if cm is None:
                raise SolverError(
                    f"Cm is unavailable at alpha = {alpha_at:g}°; widen --alpha-range."
                )
            history.append((incidence, cm))
            if abs(cm) < req.tolerance:
                break
            if len(history) == 1:
                # An elevator's pitching moment falls as its incidence rises, so to
                # raise Cm towards zero the incidence must come DOWN. Measured on a
                # 3 m glider: incidence -1.5 deg gave Cm -0.0231 and -0.5 deg gave
                # -0.0453. Stepping the wrong way costs an extra solver run.
                incidence += math.copysign(1.0, cm)
            else:
                (i0, c0), (i1, c1) = history[-2], history[-1]
                if c1 == c0:
                    break
                incidence = i1 - c1 * (i1 - i0) / (c1 - c0)
                incidence = max(-15.0, min(15.0, incidence))

        # The secant iteration is not monotone, so the last step is not necessarily
        # the best one. Reporting `history[-1]` while telling the reader it was "the
        # closest found" was simply untrue whenever the iteration overshot.
        final_i, final_cm = min(history, key=lambda h: abs(h[1]))
        converged = abs(final_cm) < req.tolerance
        warnings = []
        if not converged:
            warnings.append(
                f"the iteration stopped at Cm = {final_cm:+.5f} after "
                f"{len(history)} runs without reaching the tolerance of "
                f"{req.tolerance:g}. This is the closest of the {len(history)} "
                "attempts, not a trimmed condition: the aircraft is not in "
                "equilibrium at this elevator setting."
            )
        return _payload(
            req, design.name, speed, mass, runs,
            # `converged` is here because `status` is "ok" for every use case in this
            # package and so carries no information. A caller reading only the
            # structured output — which is every MCP client — has no other way to
            # tell a solved trim from an abandoned one, and the difference is whether
            # the aeroplane flies.
            solved={"incidence": round(final_i, 4), "alpha": round(alpha_at, 4),
                    "cm": round(final_cm, 6), "iterations": len(history),
                    "converged": converged},
            note=(f"An elevator incidence of {final_i:+.2f}° gives Cm = {final_cm:+.5f} "
                  f"at alpha = {alpha_at:.2f}°."
                  if converged else
                  f"No trimmed condition was found. The closest of {len(history)} "
                  f"attempts was an elevator incidence of {final_i:+.2f}°, leaving "
                  f"Cm = {final_cm:+.5f} at alpha = {alpha_at:.2f}°."),
            warnings=warnings,
            extra={"history": [{"incidence": round(i, 4), "cm": round(c, 6)}
                               for i, c in history]},
        )

    raise DesignError(f"unknown trim target {req.target!r}")


def _interp_at(xs: list[float], ys: list[float], x: float) -> float | None:
    """y at a given x, by linear interpolation, without extrapolating."""
    pairs = sorted(
        ((a, b) for a, b in zip(xs, ys, strict=True)
         if math.isfinite(a) and math.isfinite(b)),
        key=lambda p: p[0],
    )
    if not pairs:
        return None
    if x <= pairs[0][0]:
        return pairs[0][1] if math.isclose(x, pairs[0][0], abs_tol=1e-9) else None
    for (x0, y0), (x1, y1) in pairwise(pairs):
        if x0 <= x <= x1:
            if x1 == x0:
                return y0
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return None


def _closest(xs: list[float], target: float) -> int | None:
    finite = [i for i, x in enumerate(xs) if math.isfinite(x)]
    if not finite:
        return None
    return min(finite, key=lambda i: abs(xs[i] - target))


def _payload(req: TrimRequest, design_name: str, speed: float | None, mass: float,
             runs: list[dict[str, Any]], *, solved: dict[str, Any], note: str,
             warnings: list[str] | None = None,
             extra: dict[str, Any] | None = None) -> dict[str, Any]:
    collected: list[str] = list(warnings or [])
    for r in runs:
        for w in r["warnings"]:
            if w not in collected:
                collected.append(w)
    return {
        "status": "ok",
        "design": design_name,
        "target": req.target,
        "requested": req.value,
        "conditions": {"speed": speed, "mass": mass,
                       "alpha_range": list(req.alpha_range or (-4.0, 10.0, 1.0))},
        "solved": solved,
        "explanation": note,
        "solver_runs": len(runs),
        "runtime_s": round(sum(r["runtime_s"] for r in runs), 2),
        "warnings": collected,
        "notes": [n for r in runs for n in r["notes"]][:6],
        **(extra or {}),
    }

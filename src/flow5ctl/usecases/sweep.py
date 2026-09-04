"""Run a named, re-runnable question across a range of one parameter.

A comparison table between designs run identically is worth more than any single
absolute number, and it is what a potential-flow solver is actually good at. This is
the unit of work most designers want, which is why it is a first-class operation
rather than something an agent loops by hand.

A geometric parameter is varied in memory: `design.yaml` is never written to, so a
sweep cannot leave the design in an intermediate state if it is interrupted.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..errors import DesignError, SolverError
from ..model.design import Design
from ..project.store import Project
from .analyze import Request, analyze

#: Parameters that override the analysis request rather than the design.
ANALYSIS_PARAMS = {"cg_x", "speed", "mass", "ground_height"}

#: Metrics available from an analysis summary, with how to read them.
METRICS: dict[str, tuple[str, ...]] = {
    "cl_alpha": ("cl_alpha_per_deg",),
    "alpha_zero_lift": ("alpha_zero_lift",),
    "best_LD": ("best_LD", "value"),
    "best_LD_alpha": ("best_LD", "alpha"),
    "best_LD_cl": ("best_LD", "cl"),
    "min_sink": ("min_sink", "value"),
    "min_sink_speed": ("min_sink", "speed"),
    "static_margin": ("static_margin",),
    "neutral_point_x": ("neutral_point_x",),
    "trim_alpha": ("trim_alpha",),
    "cl_at_trim": ("cl_at_trim",),
    "ld_at_trim": ("ld_at_trim",),
    "cm_alpha": ("cm_alpha_per_deg",),
    "dcm_dcl": ("dcm_dcl",),
}

#: Which metric a design objective is trying to maximise, and in which direction.
OBJECTIVE_METRIC = {
    "max_range": ("best_LD", "max"),
    "min_sink": ("min_sink", "min"),
    "max_speed": ("best_LD", "max"),
}

DEFAULT_METRICS = ("best_LD", "best_LD_alpha", "min_sink", "static_margin", "trim_alpha")

#: What a trimmed sweep reports instead. Best L/D is deliberately absent: it is the
#: best point on a polar the aircraft is not flying, and quoting it beside trimmed
#: numbers invites the reader to compare the two.
TRIMMED_METRICS = ("ld_at_trim", "trim_alpha", "cl_at_trim", "min_sink", "static_margin")

#: Costs a potential-flow sweep cannot see, keyed by the parameter being varied.
#: Without these, a sweep reliably "discovers" that washout should be zero and span
#: should be infinite — true for induced drag alone, and wrong for an aircraft.
TRADEOFF_NOTES: dict[str, str] = {
    "washout": (
        "washout costs induced drag, so a drag-only sweep will always favour zero. What "
        "it buys — tip-stall margin, roll damping, and on a high-aspect-ratio wing an "
        "unloaded tip where the structure is lightest — is invisible to a potential-flow "
        "solver, which has no separation model. Do not remove washout on this evidence."
    ),
    "taper": (
        "reducing taper drops the tip Reynolds number, where the airfoil is already "
        "worst behaved, and the 2D polar mesh must still cover it. Structural mass also "
        "rises as the tip chord shrinks."
    ),
    "span": (
        "induced drag falls with span, so a drag-only sweep will always favour more of "
        "it. Structural mass and root bending moment rise faster; the strip table's "
        "bending-moment column is the place to check that."
    ),
    "root_chord": (
        "changing the root chord changes both area and Reynolds number, so the result "
        "mixes two effects. Fix the area and vary taper instead if you want the "
        "planform effect alone."
    ),
}

#: Metrics that do not respond to a given parameter, so comparing on them misleads.
INSENSITIVE: dict[str, tuple[str, ...]] = {
    "cg_x": ("best_LD", "best_LD_alpha", "best_LD_cl", "min_sink", "min_sink_speed",
             "cl_alpha", "alpha_zero_lift", "neutral_point_x"),
}


@dataclass(slots=True)
class SweepRequest:
    parameter: str
    """A dotted path into design.yaml, or one of `cg_x`, `speed`, `mass`,
    `ground_height`, which override the analysis instead."""
    values: list[float]
    name: str = "sweep"
    analysis: Request = field(default_factory=Request)
    metrics: tuple[str, ...] = DEFAULT_METRICS
    stop_on_error: bool = False
    trimmed: bool = False
    """Solve the flight condition at every point instead of reporting a polar.

    A fixed-speed sweep holds the speed and sweeps alpha, so almost every point on
    it is out of balance in both senses: the lift does not equal the weight, and the
    pitching moment is not zero. The numbers that come off it — best L/D above all —
    belong to a condition the aircraft never flies.

    With this set, each point runs as a **fixed-lift (T2) polar**, which solves the
    speed at every alpha so that lift equals weight, and the reported metrics are
    read at the alpha where Cm crosses zero. That row is the aircraft actually
    flying: level, trimmed, at its own weight.
    """


def _set_path(data: dict, path: str, value: Any) -> dict:
    out = copy.deepcopy(data)
    node: Any = out
    parts = path.split(".")
    for key in parts[:-1]:
        if isinstance(node, dict):
            if key not in node or not isinstance(node[key], dict | list):
                raise DesignError(
                    f"{path!r} does not exist in this design (stopped at {key!r}). "
                    "Use `flow5ctl show --json` to see the fields you can vary."
                )
            node = node[key]
        elif isinstance(node, list):
            try:
                node = node[int(key)]
            except (ValueError, IndexError):
                raise DesignError(f"{path!r}: {key!r} is not a valid list index") from None
        else:
            raise DesignError(f"{path!r} is not a settable path")
    leaf = parts[-1]
    if isinstance(node, dict):
        if leaf not in node:
            raise DesignError(
                f"{path!r} does not exist in this design. Use `flow5ctl show --json` to "
                "see the fields you can vary."
            )
        node[leaf] = value
    elif isinstance(node, list):
        node[int(leaf)] = value
    return out


def _metric(summary: dict[str, Any], name: str) -> float | None:
    try:
        keys = METRICS[name]
    except KeyError:
        raise DesignError(
            f"unknown metric {name!r}. Available: {', '.join(sorted(METRICS))}"
        ) from None
    node: Any = summary
    for k in keys:
        if not isinstance(node, dict) or k not in node:
            return None
        node = node[k]
    return node if isinstance(node, int | float) else None


def parse_values(spec: str | list[float]) -> list[float]:
    """Accept `0.3,0.35,0.4` or `0.30:0.40:5` (from:to:steps)."""
    if isinstance(spec, list):
        return [float(v) for v in spec]
    text = spec.strip()
    if ":" in text:
        parts = text.split(":")
        if len(parts) != 3:
            raise DesignError("a range is `from:to:steps`, e.g. 0.30:0.40:5")
        lo, hi, steps = float(parts[0]), float(parts[1]), int(parts[2])
        if steps < 2:
            raise DesignError("a range needs at least 2 steps")
        return [lo + (hi - lo) * i / (steps - 1) for i in range(steps)]
    values = [float(v) for v in text.replace(" ", "").split(",") if v]
    if len(values) < 2:
        raise DesignError("a sweep needs at least two values")
    return values


def load_study(path: Path) -> SweepRequest:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    vary = data.get("vary") or {}
    values = vary.get("values")
    if values is None and {"from", "to", "steps"} <= set(vary):
        values = parse_values(f"{vary['from']}:{vary['to']}:{vary['steps']}")
    if not values:
        raise DesignError(f"{path}: `vary.values` (or from/to/steps) is required")
    a = data.get("analysis") or {}
    alpha = a.get("alpha")
    return SweepRequest(
        parameter=vary.get("parameter") or _required(path, "vary.parameter"),
        values=parse_values(values),
        name=data.get("name") or Path(path).stem,
        analysis=Request(
            name="sweep",
            polar_type=a.get("type", "T1"),
            speed=a.get("speed"),
            alpha=tuple(alpha) if alpha else None,
            viscous=a.get("viscous"),
            ground_effect=a.get("ground_effect"),
            mass=a.get("mass"),
        ),
        metrics=tuple((data.get("report") or {}).get("metrics") or DEFAULT_METRICS),
        trimmed=bool(a.get("trimmed") or data.get("trimmed")),
    )


def _shape(text: str) -> str:
    """A warning with the numbers taken out, for collapsing a sweep's repeats.

    Every point of a sweep runs a full analysis and every analysis warns about the
    same things, so a four-point CG sweep returned the CG-height explanation four
    times with four different percentages. Exact-match de-duplication cannot see
    that they are one finding, and the reader has to diff them by eye to find out.
    """
    return re.sub(r"[-+]?\d[\d,._]*", "#", text)


def _apply_trimmed(req: SweepRequest, design: Design) -> str | None:
    """Turn a trimmed sweep into the analysis that can actually answer it.

    Two things have to change together, which is why this is one function rather
    than two flags a caller has to remember to set. The polar becomes fixed-lift, so
    that every alpha is flown at the aircraft's own weight; and the metrics become
    the ones read at Cm = 0, because on a trimmed sweep the best point of the polar
    is not the point being asked about.
    """
    if not req.trimmed:
        return None
    if design.tail.elevator is None:
        raise DesignError(
            "a trimmed sweep needs something to trim against, and this design has no "
            "elevator. Without one there is no Cm = 0 crossing to solve for. Run the "
            "sweep without --trimmed, or add a tail."
        )
    req.analysis.polar_type = "T2"
    if req.metrics == DEFAULT_METRICS:
        req.metrics = TRIMMED_METRICS
    return (
        "trimmed sweep: every point is a fixed-lift (T2) polar, so the speed is "
        "solved at each alpha to carry the aircraft's weight, and the metrics are "
        "read where Cm crosses zero. These are level, trimmed numbers and they are "
        "not comparable with a fixed-speed sweep's best L/D, which is the best point "
        "of a polar the aircraft is not flying."
    )


def _required(path: Path, field_name: str) -> str:
    raise DesignError(f"{path}: `{field_name}` is required")


def sweep(project: Project, req: SweepRequest, *,
          flow5: str | None = None) -> dict[str, Any]:
    design = project.load()
    base_raw = design.model_dump(mode="json", by_alias=True, exclude_none=True)
    is_analysis_param = req.parameter in ANALYSIS_PARAMS
    trimmed_note = _apply_trimmed(req, design)

    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    seen: dict[str, tuple[str, int]] = {}

    for i, value in enumerate(req.values):
        run = _clone_request(req.analysis, f"{req.name}_{i:02d}")
        variant: Design | None = None
        if is_analysis_param:
            setattr(run, req.parameter, value)
        else:
            variant = Design.model_validate(_set_path(base_raw, req.parameter, value))

        try:
            out = analyze(project, run, flow5=flow5, design=variant, store=False)
        except (SolverError, DesignError) as exc:
            failures.append({"value": value, "error": str(exc)})
            if req.stop_on_error:
                raise
            continue

        row: dict[str, Any] = {req.parameter: value, "points": out["points"],
                               "runtime_s": out["runtime_s"]}
        for m in req.metrics:
            row[m] = _metric(out["summary"], m)
        rows.append(row)
        for w in out["warnings"]:
            key = _shape(w)
            first, n = seen.get(key, (w, 0))
            seen[key] = (first, n + 1)

    warnings = [
        first if n < 2 else
        f"{first}  (the same warning came back from {n} of the {len(rows)} points, "
        "with different numbers; this is the first)"
        for first, n in seen.values()
    ]

    if not rows:
        raise SolverError(
            f"every point of the sweep failed. First error:\n{failures[0]['error']}"
            if failures else "the sweep produced no results"
        )

    objective = design.requirements.objective
    best = None
    if objective in OBJECTIVE_METRIC:
        metric, direction = OBJECTIVE_METRIC[objective]
        if metric in req.metrics:
            usable = [r for r in rows if isinstance(r.get(metric), int | float)]
            if usable:
                best = (max if direction == "max" else min)(usable, key=lambda r: r[metric])

    if trimmed_note:
        warnings.insert(0, trimmed_note)

    leaf = req.parameter.rsplit(".", 1)[-1]
    if leaf in TRADEOFF_NOTES:
        warnings.append(TRADEOFF_NOTES[leaf])

    blind = INSENSITIVE.get(req.parameter, ())
    used_blind = [m for m in req.metrics if m in blind]
    if used_blind:
        warnings.insert(0, (
            f"{', '.join(used_blind)} do not respond to {req.parameter} — the drag polar "
            "is unchanged, only the trim point moves. Compare on `ld_at_trim` and "
            "`cl_at_trim` instead, which are the numbers that actually differ."
        ))

    # A column of dashes is not self-explanatory; say why the value is absent.
    for m in req.metrics:
        missing = [r[req.parameter] for r in rows if r.get(m) is None]
        if not missing or len(missing) == len(rows):
            continue
        reason = (
            "the trimmed condition falls outside the alpha sweep"
            if m in {"trim_alpha", "cl_at_trim", "ld_at_trim"}
            else "flow5 did not report it"
        )
        warnings.append(
            f"{m} is missing for {len(missing)} of {len(rows)} values "
            f"({', '.join(f'{v:g}' for v in missing)}) because {reason}. "
            + ("Widen the alpha range to cover them."
               if m in {"trim_alpha", "cl_at_trim", "ld_at_trim"} else "")
        )

    band = design.requirements.static_margin
    if band and "static_margin" in req.metrics:
        inside = [r for r in rows
                  if isinstance(r.get("static_margin"), int | float)
                  and band[0] <= r["static_margin"] <= band[1]]
        if not inside:
            warnings.append(
                f"no point in this sweep sits inside the target static margin band "
                f"{band[0]:+.0%} to {band[1]:+.0%}."
            )

    payload = {
        "status": "ok",
        "design": design.name,
        "study": req.name,
        "parameter": req.parameter,
        "parameter_kind": "analysis" if is_analysis_param else "design",
        "values": req.values,
        "metrics": list(req.metrics),
        "rows": rows,
        "best": best,
        "best_by": objective,
        "failed": failures,
        "solver_runs": len(rows) + len(failures),
        "runtime_s": round(sum(r["runtime_s"] for r in rows), 2),
        "warnings": warnings,
    }
    stored = project.write_result(f"study-{req.name}", payload)
    payload["data"] = str(stored.relative_to(project.root))
    return payload


def _clone_request(req: Request, name: str) -> Request:
    new = copy.deepcopy(req)
    new.name = name
    return new

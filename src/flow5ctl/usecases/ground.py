"""Ground effect, in and out, from one call.

A Birdman Rally aircraft launches from a platform and flies a few metres above
water for its whole flight. Ground effect is not a correction to its performance,
it is a large part of it — measured on a reconstructed 30 m aircraft at h = 2.0 m,
best lift-to-drag went 38.7 to 47.6 (**+23 %**) and minimum sink 0.172 to 0.133 m/s.

Comparing the two used to mean running `analyze` twice by hand, remembering to
change only the one flag, and doing the arithmetic. Getting that wrong is easy and
silent: run both at the same height by accident and the difference is zero, which
reads like "ground effect does not matter here" rather than like a mistake.
"""
from __future__ import annotations

from typing import Any

from ..errors import DesignError
from ..project.store import Project
from . import analyze as analyze_uc


def _pct(free: float | None, near: float | None) -> float | None:
    if free is None or near is None or free == 0:
        return None
    return round((near - free) / abs(free) * 100.0, 1)


def compare(project: Project, req: analyze_uc.Request, *, height: float | None = None,
            flow5: str | None = None) -> dict[str, Any]:
    """Run the same analysis free-air and in ground effect, and report both.

    The stored result is the in-ground-effect run, because for this class of
    aircraft that is the flying condition; the free-air numbers ride alongside it
    for reference. Only `ground_effect` and `ground_height` differ between the two
    runs — everything else, including the polar name, comes from one Request.
    """
    design = project.load()
    height = resolve_height(design, req, height)

    free_req = replace_ground(req, effect=False, height=None, suffix="__free")
    near_req = replace_ground(req, effect=True, height=height, suffix=None)

    free = analyze_uc.analyze(project, free_req, flow5=flow5, store=False)
    near = analyze_uc.analyze(project, near_req, flow5=flow5, store=True)

    fs, ns = free.get("summary", {}), near.get("summary", {})
    fld = (fs.get("best_LD") or {}).get("value")
    nld = (ns.get("best_LD") or {}).get("value")
    fsink = (fs.get("min_sink") or {}).get("value")
    nsink = (ns.get("min_sink") or {}).get("value")

    return {
        "status": "ok",
        "design": design.name,
        "polar": req.name,
        "ground_height": height,
        "free_air": {"best_LD": fld, "min_sink": fsink,
                     "cl_alpha_per_deg": fs.get("cl_alpha_per_deg")},
        "in_ground_effect": {"best_LD": nld, "min_sink": nsink,
                             "cl_alpha_per_deg": ns.get("cl_alpha_per_deg")},
        "change_pct": {
            "best_LD": _pct(fld, nld),
            "min_sink": _pct(fsink, nsink),
            "cl_alpha_per_deg": _pct(fs.get("cl_alpha_per_deg"),
                                 ns.get("cl_alpha_per_deg")),
        },
        "warnings": near.get("warnings", []),
        "notes": [
            # The single-run guardrail tells an HPA to report the other case as well.
            # This IS the other case, so keeping it would tell the reader to do what
            # they have just done.
            *[n for n in near.get("notes", []) if "out-of-ground-effect" not in n],
            f"free-air and in-ground-effect at h = {height} m, same geometry, mass "
            "and alpha range. The stored result is the in-ground-effect run.",
        ],
        "data": near.get("data"),
    }


def resolve_height(design: Any, req: analyze_uc.Request,
                   height: float | None = None) -> float:
    """Where the ground height comes from — the same places `analyze` looks.

    This used to check only the preset's `analysis` block, and no preset has ever
    put a ground height there: they put it in `defaults.requirements`, from which it
    lands on the design as `requirements.ground_effect_height`. So the one feature
    built for human-powered aircraft refused to run on a human-powered aircraft, and
    told the user to "use a preset that sets one (hpa does)" about a design that was
    already using exactly that preset.
    """
    from ..model import presets

    if height is None:
        height = req.ground_height
    if height is None:
        height = design.requirements.ground_effect_height
    if height is None:
        preset = presets.load(design.preset)
        height = (preset.analysis.get("ground_height")
                  or (preset.defaults.get("requirements") or {}).get("ground_effect_height"))
    if height is None:
        raise DesignError(
            "no ground height to compare against. Pass --ground-height, or set "
            "`requirements.ground_effect_height` in the design (the hpa preset does "
            "it for you)."
        )
    if height <= 0:
        raise DesignError(f"ground height must be positive, not {height}")
    return float(height)


def replace_ground(req: analyze_uc.Request, *, effect: bool, height: float | None,
                   suffix: str | None) -> analyze_uc.Request:
    """A copy of the request with only the ground settings and name changed."""
    import dataclasses

    changes: dict[str, Any] = {"ground_effect": effect, "ground_height": height}
    if suffix:
        changes["name"] = req.name + suffix
    return dataclasses.replace(req, **changes)

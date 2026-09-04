"""The one structural number an aerodynamic run already contains.

flow5's strip table carries a `Bending.mom` column, and its value at the root is
what a human-powered aircraft's main spar is sized from. It is right there in every
analysis and was being thrown away.

This does not size a spar — that needs the spar's own section, material and safety
factor, none of which this project knows. What it does is surface the aerodynamic
load and check it against a closed-form estimate, so a number that is wrong by a
factor is caught rather than carried into a laminate schedule.

**The cross-check.** For a wing carrying half the aircraft's weight on each side,
the root bending moment is that half-weight times the spanwise centroid of the
load. An elliptic distribution puts the centroid at 4s/(3π) ≈ 0.424 s. So

    M_root ≈ (W / 2) · 0.424 · s

Measured on a reconstructed 32 m aircraft at 89 kg: the estimate gives 2961 N·m
and flow5's strip table gives 2804 N·m, 5 % apart — the real loading is slightly
more inboard than elliptic, which is what a wing with a constant-chord inner panel
and washout should do. A disagreement much larger than that means the strips and
the weight are not describing the same aeroplane.
"""
from __future__ import annotations

import math
from typing import Any

#: Spanwise centroid of an elliptic lift distribution, as a fraction of semi-span.
ELLIPTIC_CENTROID = 4.0 / (3.0 * math.pi)

#: Past this, the strip table and the mass are not describing the same aircraft.
_DISAGREEMENT = 0.35


def _finite(values: list[float]) -> list[float]:
    return [v for v in values if isinstance(v, (int, float)) and math.isfinite(v)]


def root_load(strips: dict[str, Any] | None, *, mass_kg: float | None,
              semi_span_m: float | None, g: float = 9.81) -> dict[str, Any] | None:
    """Root bending moment from the strip table, with a sanity estimate beside it.

    Returns None when there is nothing to say — no strips, no bending column, or no
    mass to check against. Saying nothing is better than reporting a load whose
    provenance cannot be stated.
    """
    if not strips or not strips.get("surfaces"):
        return None
    main = strips["surfaces"].get("Main") or next(iter(strips["surfaces"].values()), None)
    if not main:
        return None
    moments = _finite(main.get("Bending.mom") or [])
    ys = _finite(main.get("y(m)") or [])
    if not moments or not ys:
        return None

    peak = max(moments)
    at_y = ys[main["Bending.mom"].index(peak)] if peak in main["Bending.mom"] else 0.0
    out: dict[str, Any] = {
        "root_bending_moment_Nm": round(peak, 1),
        "at_y_m": round(at_y, 3),
        "alpha": strips.get("alpha"),
        "note": ("aerodynamic load only, at the operating point the rest of this "
                 "report is about. Not a spar sizing — that needs the section, the "
                 "material and a safety factor."),
    }

    if mass_kg and semi_span_m and semi_span_m > 0:
        estimate = (mass_kg * g / 2.0) * ELLIPTIC_CENTROID * semi_span_m
        out["elliptic_estimate_Nm"] = round(estimate, 1)
        if estimate > 0:
            ratio = peak / estimate
            out["ratio_to_estimate"] = round(ratio, 3)
            if abs(ratio - 1.0) > _DISAGREEMENT:
                out["disagreement"] = (
                    f"the strip table's root bending moment is {ratio:.2f}x the "
                    f"elliptic estimate for {mass_kg:g} kg over a {semi_span_m:g} m "
                    "semi-span. Those two should agree within a few tens of percent; "
                    "check that the mass and the analysis are describing the same "
                    "aircraft, and that this operating point is level flight."
                )
    return out


def warning(load: dict[str, Any] | None) -> str | None:
    """A sentence only when the cross-check actually failed."""
    return load.get("disagreement") if load else None

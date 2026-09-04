"""The one structural number an aerodynamic run already contains.

flow5's strip table carries a `Bending.mom` column, and its value at the root is
what a human-powered aircraft's main spar is sized from. It is right there in every
analysis and was being thrown away.

This does not size a spar — that needs the spar's own section, material and safety
factor, none of which this project knows. What it does is surface the aerodynamic
load and check it against a closed-form estimate, so a number that is wrong by a
factor is caught rather than carried into a laminate schedule.

**The cross-check.** For a wing carrying lift L, the root bending moment on each
side is half that lift times the spanwise centroid of the load. An elliptic
distribution puts the centroid at 4s/(3π) ≈ 0.424 s. So

    M_root ≈ (L / 2) · 0.424 · s

**The lift is the operating point's, not the weight.** This is the whole trap. A
fixed-speed (T1) polar does not fly the aeroplane — it holds the speed and sweeps
alpha, so almost every point on it is out of balance. Measured on the shipped 3 m
glider example at its best-L/D point: the strip table gives 10.8 N·m, and checking
against the 0.8 kg weight gives an estimate of 2.5 N·m — 4.3x apart, which reads
like a broken parser. Checking against the lift the polar itself reports at that
point (CL 0.7132 at 12 m/s over 0.5551 m² = 34.9 N) gives 11.1 N·m: **3 % apart.**
Nothing was wrong with the strips. The point simply carried 4.4 times the
aircraft's weight, and that is worth saying on its own.

So there are two separate statements, and conflating them is what produced the
misleading warning:

| Question | Compare | Fires when |
|---|---|---|
| Do the strips and the polar agree? | strip peak vs elliptic estimate **from lift** | the parser or the geometry is wrong |
| Is this the load a spar sees? | lift at the point vs weight | the point is not level flight |

Measured on a reconstructed 32 m aircraft at 89 kg in near-level flight: the
estimate gives 2961 N·m and flow5's strip table gives 2804 N·m, 5 % apart — the
real loading is slightly more inboard than elliptic, which is what a wing with a
constant-chord inner panel and washout should do.
"""
from __future__ import annotations

import math
from typing import Any

#: Spanwise centroid of an elliptic lift distribution, as a fraction of semi-span.
ELLIPTIC_CENTROID = 4.0 / (3.0 * math.pi)

#: Past this, the strip table and the lift it was computed from disagree.
_DISAGREEMENT = 0.35

#: A load factor further than this from 1 is not level flight, and the bending
#: moment is not the one a spar is sized from.
_LEVEL = 0.15


def _finite(values: list[float]) -> list[float]:
    return [v for v in values if isinstance(v, (int, float)) and math.isfinite(v)]


def root_load(strips: dict[str, Any] | None, *, mass_kg: float | None,
              semi_span_m: float | None, lift_N: float | None = None,
              g: float = 9.81) -> dict[str, Any] | None:
    """Root bending moment from the strip table, with a sanity estimate beside it.

    `lift_N` is the lift the polar reports at this operating point. Pass it whenever
    it can be computed — it makes the cross-check a real test of the strip table.
    Without it the estimate falls back to the weight, which is only the right
    comparison if the point happens to be level flight.

    Returns None when there is nothing to say — no strips, no bending column, or
    nothing to check against. Saying nothing is better than reporting a load whose
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

    weight = mass_kg * g if mass_kg else None
    if lift_N is not None:
        out["lift_at_point_N"] = round(lift_N, 1)
    if lift_N is not None and weight:
        factor = lift_N / weight
        out["load_factor"] = round(factor, 2)
        if abs(factor - 1.0) > _LEVEL:
            out["not_level_flight"] = (
                f"this operating point carries {factor:.2f}x the aircraft's weight "
                f"({lift_N:.1f} N of lift against {weight:.1f} N), so the root bending "
                f"moment of {peak:.1f} N·m is the load there, not the level-flight "
                "load a spar is sized from. Trim it first (`flow5ctl trim`), or run a "
                "fixed-lift (T2) polar, which flies every point at the aircraft's own "
                "weight."
            )

    reference = lift_N if lift_N is not None else weight
    if reference and semi_span_m and semi_span_m > 0:
        estimate = (reference / 2.0) * ELLIPTIC_CENTROID * semi_span_m
        out["elliptic_estimate_Nm"] = round(estimate, 1)
        out["estimate_from"] = ("lift at this operating point" if lift_N is not None
                                else "the aircraft's weight, assuming level flight")
        if estimate > 0:
            ratio = peak / estimate
            out["ratio_to_estimate"] = round(ratio, 3)
            if abs(ratio - 1.0) > _DISAGREEMENT:
                against = (f"{reference:.1f} N of lift" if lift_N is not None
                           else f"{mass_kg:g} kg of weight")
                out["disagreement"] = (
                    f"the strip table's root bending moment is {ratio:.2f}x the "
                    f"elliptic estimate for {against} over a {semi_span_m:g} m "
                    "semi-span. Those two should agree within a few tens of percent; "
                    "check that the mass and the analysis are describing the same "
                    "aircraft."
                )
    return out


def notes(load: dict[str, Any] | None) -> list[str]:
    """Only the sentences the numbers actually earned.

    Two independent things can be worth saying, and they are not the same thing:
    that the point is not level flight, and that the strips disagree with the lift
    they came from.
    """
    if not load:
        return []
    return [load[k] for k in ("not_level_flight", "disagreement") if k in load]

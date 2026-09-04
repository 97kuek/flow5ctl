"""What the drag figure does NOT include.

A VLM analysis of a wing and a tail returns the drag of a wing and a tail. On a
human-powered aircraft that is roughly two thirds of the aeroplane: the rigging
wires, the fairing, the pilot's body, the wheel and every joint between components
are simply not in the model, and flow5 has no way to put them there through this
interface (`<body>` exists but is a lifting-surface fuselage, not a drag bookkeeping
device).

Leaving the reader to remember that is how a number gets quoted as if it were the
aeroplane's. This module names the missing pieces and puts a size on them, so the
gap between "what was modelled" and "what will fly" is on the page next to the L/D.

**These are published estimates, not measurements by this project.** They are deliberately given as ranges: an HPA's rigging
drag depends on wire diameter, count, length and whether the wires are faired, and
a design that has not chosen those yet cannot be given a single number.

The estimates are expressed as a fraction of the *modelled* total drag at the best
lift-to-drag point, because that is the number a designer is looking at when they
need the warning. The per-item ranges are not added together to reach the total -
see `_TOTAL`.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Missing:
    """One thing the aerodynamic model does not contain."""

    name: str
    low: float
    high: float
    """Fraction of the modelled drag, low and high estimate."""
    note: str

    def as_dict(self) -> dict:
        return {"item": self.name, "low": self.low, "high": self.high, "note": self.note}


#: Human-powered aircraft. Ranges from the Daedalus and Monarch project reports and
#: from Birdman Rally teams' own published drag budgets; see docs/DESIGN-GUIDE.md.
#: An HPA carries a lot of wire and very little else, which is why rigging dominates.
_HPA: tuple[Missing, ...] = (
    Missing("rigging wires", 0.10, 0.30,
            "bare wire runs at a section drag coefficient near 1.0. A 32 m aircraft "
            "carries tens of metres of it. Faired wire cuts this by roughly half."),
    Missing("pilot and fairing", 0.08, 0.20,
            "the pilot is a bluff body. A good fairing is worth a lot here and a bad "
            "one is worse than none, because it separates."),
    Missing("interference at joints", 0.03, 0.08,
            "wing-to-fuselage, tail-to-boom, and every strut end."),
    Missing("surface finish and rib stitching", 0.02, 0.06,
            "film over ribs is not the smooth aerofoil the 2D polar assumes."),
    Missing("undercarriage", 0.01, 0.04,
            "small if retracted or dropped, not small if left hanging."),
)

#: RC gliders and UAVs. No rigging, a much smaller fuselage relative to the wing,
#: and usually a moulded surface - so the budget is dominated by the fuselage itself.
_SMALL: tuple[Missing, ...] = (
    Missing("fuselage", 0.06, 0.15, "not modelled as a drag source by this analysis."),
    Missing("interference at joints", 0.02, 0.06, "wing root and tail junctions."),
    Missing("surface finish", 0.01, 0.04, "a moulded surface is close to the 2D "
                                          "assumption; a built-up one is not."),
    Missing("control gaps and linkages", 0.01, 0.03, "hinge lines and horns."),
)

#: The total, taken from published whole-aircraft drag budgets rather than by summing
#: the per-item highs above. Summing them assumes every item is simultaneously at its
#: worst, which no flying aircraft is: for a Daedalus-class HPA the lifting surfaces
#: are roughly three quarters of the total drag, putting everything else near 25-35 %
#: of the modelled figure. The per-item ranges say where that total comes from and
#: which choices move it; they are not meant to be added up.
_TOTAL: dict[str, tuple[float, float]] = {
    "hpa": (0.20, 0.40),
    "rc-glider": (0.08, 0.20),
    "uav": (0.08, 0.20),
}

_BY_PRESET: dict[str, tuple[Missing, ...]] = {
    "hpa": _HPA,
    "rc-glider": _SMALL,
    "uav": _SMALL,
}


def items_for(preset_name: str) -> tuple[Missing, ...]:
    """The missing-drag list for a preset, or nothing for `custom`.

    `custom` gets nothing on purpose: the whole point of that preset is that no
    assumptions are made about what kind of aircraft it is, and a drag budget IS an
    assumption about the airframe.
    """
    return _BY_PRESET.get(preset_name, ())


def budget(preset_name: str, modelled_ld: float | None) -> dict | None:
    """A drag budget for what is not in the model, or None when nothing is known.

    `modelled_ld` is the best lift-to-drag ratio the analysis produced. The realistic
    band is that figure divided by (1 + missing fraction), because adding drag at
    constant lift divides the ratio.
    """
    items = items_for(preset_name)
    if not items or not modelled_ld or modelled_ld <= 0:
        return None
    low, high = _TOTAL.get(preset_name, (0.0, 0.0))
    if high <= 0:
        return None
    return {
        "modelled_best_LD": round(modelled_ld, 2),
        "missing_fraction": {"low": round(low, 3), "high": round(high, 3)},
        "realistic_best_LD": {
            "low": round(modelled_ld / (1 + high), 2),
            "high": round(modelled_ld / (1 + low), 2),
        },
        "items": [i.as_dict() for i in items],
        "basis": ("published estimates for this class of aircraft, not measurements "
                  "by this project"),
    }


def warning(preset_name: str, modelled_ld: float | None) -> str | None:
    """One sentence for the analysis output, or None when there is nothing to say."""
    b = budget(preset_name, modelled_ld)
    if b is None:
        return None
    lo, hi = b["realistic_best_LD"]["low"], b["realistic_best_LD"]["high"]
    frac = b["missing_fraction"]
    names = ", ".join(i["item"] for i in b["items"][:3])
    return (
        f"this L/D of {b['modelled_best_LD']} is for the lifting surfaces only. "
        f"{names} and the rest are not in the model and flow5 cannot put them there. "
        f"Published estimates for this class put them at {frac['low']:.0%}-{frac['high']:.0%} "
        f"of the modelled drag, which would give a realistic {lo}-{hi}. Compare a "
        "published aircraft's figure against that band, not against the number above."
    )

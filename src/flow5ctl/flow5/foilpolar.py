"""Coverage of the 2D airfoil polars the 3D viscous drag is interpolated from.

flow5ctl asks flow5's XFoil for a polar over an alpha range and then interpolates
every wing strip's viscous drag out of the result. XFoil does not always converge
across that range, and flow5 reports no error when it does not - it simply writes a
polar with fewer points than were asked for. The 3D run then interpolates straight
across the hole and reports a drag figure with no indication that it did.

Measured on DAE-31 at Re 450,000, asking for alpha -4..12 in half-degree steps:
29 of 33 points came back, with **alpha +0.5 to +3.0 missing entirely**. That gap
is not incidental - it is exactly where upper-surface transition jumps from x/c 0.72
to the leading edge, and drag steps from 0.01050 to 0.01513, up 44 %. Interpolating
across it is interpolating across a discontinuity.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Gap:
    """A stretch of the requested alpha range that XFoil did not converge in."""
    polar: str
    lo: float
    hi: float

    @property
    def width(self) -> float:
        return self.hi - self.lo

    def as_dict(self) -> dict:
        return {"polar": self.polar, "from": self.lo, "to": self.hi,
                "width": round(self.width, 2)}


def read_alphas(path: Path) -> list[float]:
    """Alpha column of an XFoil-format polar.

    The header carries a line reading `1 1 Reynolds number fixed ...`, which parses
    as a data row if rows are recognised only by starting with a number - so rows are
    taken only after the `alpha  CL  CD` header and only when they have the full
    column count.
    """
    alphas: list[float] = []
    seen_header = False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not seen_header:
            seen_header = "alpha" in line and "CL" in line and "CD" in line
            continue
        parts = line.split()
        if len(parts) < 7:
            continue
        try:
            alphas.append(float(parts[0]))
        except ValueError:
            continue
    return sorted(alphas)


def find_gaps(directory: Path, step: float, *, slack: float = 2.5) -> list[Gap]:
    """Stretches of missing alpha in every polar in `directory`.

    A gap is reported when consecutive converged points are further apart than
    `slack` times the requested step, so a single dropped point is tolerated and a
    real hole is not. Polars with fewer than two points are skipped - "no polar at
    all" is a different failure and is already caught by the caller.
    """
    if step <= 0:
        return []
    limit = step * slack
    gaps: list[Gap] = []
    for path in sorted(directory.glob("*.txt")):
        alphas = read_alphas(path)
        for a, b in pairwise(alphas):
            if b - a > limit:
                gaps.append(Gap(path.stem, round(a, 3), round(b, 3)))
    return gaps


def describe(gaps: list[Gap]) -> str:
    """One warning sentence, naming the worst offender rather than listing all."""
    worst = max(gaps, key=lambda g: g.width)
    others = len(gaps) - 1
    tail = f" ({others} other gap{'s' if others > 1 else ''} as well)" if others else ""
    return (
        f"XFoil did not converge across part of the requested alpha range: "
        f"{worst.polar} has no points between {worst.lo:+.1f}° and {worst.hi:+.1f}° "
        f"({worst.width:.1f}° wide){tail}. Viscous drag is interpolated straight "
        "across that, and these gaps sit where transition moves, so drag either side "
        "of one can differ by tens of percent. Treat the drag from this run as "
        "uncertain, and try a different alpha step or ncrit."
    )


def cl_coverage(directory: Path) -> dict[str, tuple[float, float]]:
    """Lift-coefficient range each staged 2D polar actually covers.

    The alpha sweep asked for is not the same thing: XFoil stops where it stops, so
    a sweep to 16 degrees may only deliver Cl up to 1.3 while the wing wants 1.5.
    Reading it back is the only way to know.
    """
    out: dict[str, tuple[float, float]] = {}
    for path in sorted(directory.glob("*.txt")):
        cls: list[float] = []
        seen_header = False
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not seen_header:
                seen_header = "alpha" in line and "CL" in line and "CD" in line
                continue
            parts = line.split()
            if len(parts) < 7:
                continue
            try:
                cls.append(float(parts[1]))
            except ValueError:
                continue
        if cls:
            out[path.stem] = (min(cls), max(cls))
    return out

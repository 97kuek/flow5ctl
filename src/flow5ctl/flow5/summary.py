"""Turn a polar into the handful of numbers a designer actually asked for.

An agent receives this, never the 57-column table (ADR-0004).

Where flow5's own reported value and a value computed from the data columns disagree,
the computed one wins and the discrepancy becomes a warning. That is not distrust for
its own sake: flow5 7.57's T7 header reports a static margin that contradicts its own
columns and contradicts the T1 run on the same aircraft.
See docs/FLOW5-INTERFACE.md section 5.3.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from itertools import pairwise

from ..units import static_margin_from_flow5
from .results import Polar


def _fit(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    """Least-squares slope and intercept, ignoring non-finite points."""
    pts = [(x, y) for x, y in zip(xs, ys, strict=True)
           if math.isfinite(x) and math.isfinite(y)]
    if len(pts) < 2:
        return None
    n = len(pts)
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    den = sum((p[0] - mx) ** 2 for p in pts)
    if den == 0:
        return None
    slope = sum((p[0] - mx) * (p[1] - my) for p in pts) / den
    return slope, my - slope * mx


def _zero_crossing(xs: list[float], ys: list[float]) -> float | None:
    """First linear interpolation of y = 0, for trim angle."""
    for (x0, y0), (x1, y1) in pairwise(list(zip(xs, ys, strict=True))):
        if not (math.isfinite(y0) and math.isfinite(y1)):
            continue
        if y0 == 0.0:
            return x0
        if (y0 < 0) != (y1 < 0):
            return x0 + (x1 - x0) * (-y0) / (y1 - y0)
    return None


@dataclass(slots=True)
class Extremum:
    value: float
    alpha: float
    cl: float | None = None
    cd: float | None = None
    speed: float | None = None

    def as_dict(self) -> dict:
        d = {"value": round(self.value, 4), "alpha": round(self.alpha, 3)}
        if self.cl is not None:
            d["cl"] = round(self.cl, 4)
        if self.cd is not None:
            d["cd"] = round(self.cd, 6)
        if self.speed is not None:
            d["speed"] = round(self.speed, 3)
        return d


@dataclass(slots=True)
class Mode:
    """One eigenvalue of a stability analysis."""

    real: float
    imag: float

    @property
    def frequency_hz(self) -> float:
        """Damped frequency — the rate the motion is actually observed at."""
        return abs(self.imag) / (2 * math.pi)

    @property
    def natural_frequency_hz(self) -> float:
        """Undamped natural frequency, |lambda| / 2*pi.

        Both are reported because flow5's own summary column sits between the two and
        its printed eigenvalues carry only four significant figures, so the pair
        differ by a fraction of a percent and it is not worth guessing which one a
        given flow5 version meant.
        """
        return math.hypot(self.real, self.imag) / (2 * math.pi)

    @property
    def damping_ratio(self) -> float | None:
        mag = math.hypot(self.real, self.imag)
        return None if mag == 0 else -self.real / mag

    @property
    def period_s(self) -> float | None:
        f = self.frequency_hz
        return None if f == 0 else 1.0 / f

    @property
    def stable(self) -> bool:
        return self.real < 0

    def as_dict(self) -> dict:
        return {
            "eigenvalue": [round(self.real, 6), round(self.imag, 6)],
            "frequency_hz": round(self.frequency_hz, 5),
            "natural_frequency_hz": round(self.natural_frequency_hz, 5),
            "period_s": None if self.period_s is None else round(self.period_s, 3),
            "damping_ratio": None if self.damping_ratio is None else round(self.damping_ratio, 4),
            "stable": self.stable,
        }


@dataclass(slots=True)
class Summary:
    points: int
    cl_alpha_per_deg: float | None = None
    alpha_zero_lift: float | None = None
    best_ld: Extremum | None = None
    min_sink: Extremum | None = None
    cm_alpha_per_deg: float | None = None
    dcm_dcl: float | None = None
    neutral_point_x: float | None = None
    static_margin: float | None = None
    trim_alpha: float | None = None
    longitudinal_modes: list[Mode] = field(default_factory=list)
    lateral_modes: list[Mode] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        def r(v: float | None, n: int = 5) -> float | None:
            return None if v is None or not math.isfinite(v) else round(v, n)

        d: dict = {
            "points": self.points,
            "cl_alpha_per_deg": r(self.cl_alpha_per_deg),
            "alpha_zero_lift": r(self.alpha_zero_lift, 3),
            "cm_alpha_per_deg": r(self.cm_alpha_per_deg),
            "dcm_dcl": r(self.dcm_dcl),
            "neutral_point_x": r(self.neutral_point_x),
            "static_margin": r(self.static_margin, 4),
            "trim_alpha": r(self.trim_alpha, 3),
        }
        if self.best_ld:
            d["best_LD"] = self.best_ld.as_dict()
        if self.min_sink:
            d["min_sink"] = self.min_sink.as_dict()
        if self.longitudinal_modes:
            d["longitudinal_modes"] = [m.as_dict() for m in self.longitudinal_modes]
        if self.lateral_modes:
            d["lateral_modes"] = [m.as_dict() for m in self.lateral_modes]
        return d


_EIGEN = re.compile(r"([-+]?[\d.eE+-]+)\s*\+\s*([-+]?[\d.eE+-]+)i")


def parse_modes(log: str) -> tuple[list[Mode], list[Mode]]:
    """Read the eigenvalue blocks flow5 prints for a stability polar.

    Parsed from the log rather than the summary columns because in 7.57 the
    `Dutch Roll Freq.` column returns 56 Hz or 0.0 for a 3 m glider, `Short Period
    Freq.` reads 0.0 whenever the mode is overdamped, and `Roll Damping` is `inf`
    whenever Ixx is 0. The eigenvalues themselves are correct.
    """
    def block(marker: str) -> list[Mode]:
        modes: list[Mode] = []
        idx = log.find(marker)
        while idx != -1:
            segment = log[idx: idx + 2000]
            for line in segment.splitlines():
                if "Eigenvalue" in line:
                    modes = [Mode(float(a), float(b)) for a, b in _EIGEN.findall(line)]
                    break
            break
        return modes

    return block("___Longitudinal modes___"), block("___Lateral modes___")


def summarise(polar: Polar, *, mac: float | None = None, cg_x: float | None = None,
              log: str = "") -> Summary:
    if not polar.rows:
        return Summary(points=0, warnings=[
            "flow5 produced no operating points for this analysis. "
            "Nothing can be concluded from it."
        ])

    s = Summary(points=len(polar.rows))
    alpha = polar.column("α")
    cl = polar.column("CL")
    cd = polar.column("CD")

    if fit := _fit(alpha, cl):
        s.cl_alpha_per_deg = fit[0]
        if fit[0] != 0:
            s.alpha_zero_lift = -fit[1] / fit[0]

    if polar.has("Cm"):
        cm = polar.column("Cm")
        if fit := _fit(alpha, cm):
            s.cm_alpha_per_deg = fit[0]
        cl_spread = max(cl) - min(cl) if cl else 0.0
        if cl_spread > 0.05 and (fit := _fit(cl, cm)):
            s.dcm_dcl = fit[0]
            # Cm is non-dimensionalised by the reference chord, so -dCm/dCL is
            # already the static margin as a fraction of that chord.
            s.static_margin = -fit[0]
        s.trim_alpha = _zero_crossing(alpha, cm)

    if polar.has("CL/CD"):
        ld = polar.column("CL/CD")
        best = max(
            (i for i in range(len(ld)) if math.isfinite(ld[i]) and cl[i] > 1e-4),
            key=lambda i: ld[i], default=None,
        )
        if best is not None:
            s.best_ld = Extremum(ld[best], alpha[best], cl[best], cd[best])

    if polar.has("Vz"):
        vz = polar.column("Vz")
        speeds = polar.column("V") if polar.has("V") else [None] * len(vz)
        sinking = [
            i for i in range(len(vz))
            if math.isfinite(vz[i]) and vz[i] > 0 and cl[i] > 1e-4
        ]
        if sinking:
            i = min(sinking, key=lambda i: vz[i])
            s.min_sink = Extremum(vz[i], alpha[i], cl[i], cd[i], speeds[i])

    # neutral point: prefer the data column, fall back to the header
    if polar.has("XNP"):
        xnp = [v for v in polar.column("XNP") if math.isfinite(v) and v != 0.0]
        if xnp:
            s.neutral_point_x = sum(xnp) / len(xnp)
    if s.neutral_point_x is None:
        s.neutral_point_x = polar.header_float("XNP")

    # Fall back to the geometric definition when there is not enough spread in CL to
    # fit dCm/dCL — a stability polar sweeps a control parameter, not alpha.
    if s.static_margin is None and mac and cg_x is not None and s.neutral_point_x:
        s.static_margin = (s.neutral_point_x - cg_x) / mac

    # Cross-check against flow5's own figure, which is a PERCENTAGE of the reference
    # chord. Ours wins on disagreement; see the module docstring.
    reported = polar.header_float("Static margin")
    if reported is not None and s.static_margin is not None:
        theirs = static_margin_from_flow5(reported)
        if abs(theirs - s.static_margin) > max(0.01, abs(s.static_margin) * 0.25):
            s.warnings.append(
                f"flow5 reports a static margin of {theirs:+.3f} but the data columns "
                f"give {s.static_margin:+.3f}. Using the computed value. flow5 7.57 is "
                "known to report this inconsistently, especially for stability polars."
            )

    s.longitudinal_modes, s.lateral_modes = parse_modes(log)

    if polar.nonfinite:
        cols = sorted({c for _, c in polar.nonfinite})
        s.warnings.append(
            f"flow5 wrote non-finite values in: {', '.join(cols)}. Those columns are "
            "not reported. This usually means an inertia term was zero."
        )
    return s

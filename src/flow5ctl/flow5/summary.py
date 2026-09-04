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


def _at(xs: list[float], ys: list[float], x: float) -> float | None:
    """y at a given x by linear interpolation, without extrapolating."""
    pairs = sorted(
        ((a, b) for a, b in zip(xs, ys, strict=True)
         if math.isfinite(a) and math.isfinite(b)),
        key=lambda p: p[0],
    )
    for (x0, y0), (x1, y1) in pairwise(pairs):
        if x0 <= x <= x1:
            return y0 if x1 == x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return None


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
    """Classical stick-fixed static margin, (X_np − X_cg)/MAC.

    This is what tail-sizing rules and published CG bands mean by the term. When the
    CG is offset vertically it is NOT what dCm/dCL about that CG gives — see
    `pitch_stiffness_margin`."""
    pitch_stiffness_margin: float | None = None
    """−dCm/dCL about the actual CG, including the term a vertical CG offset adds.

    Physically this is the stiffness the aircraft resists a pitch disturbance with,
    and on a human-powered aircraft it can exceed the classical static margin by 10-25
    percentage points because the pilot hangs a metre below the wing's mean height.
    Never compare it against a textbook static-margin band."""
    trim_alpha: float | None = None
    cl_at_trim: float | None = None
    ld_at_trim: float | None = None
    """Lift-to-drag at the trimmed condition.

    This is the number to compare when moving the CG. Best L/D does not change with
    CG at all — the drag polar is the same, only the trim point moves — so a CG study
    reported on best L/D looks like it makes no difference when it does."""
    sideslip_sweep: bool = False
    """True when the polar varies sideslip at fixed alpha (a T5 run).

    Every longitudinal number is meaningless on such a polar and is left unset.
    flow5 itself still prints an `XNP` and a `Static margin` in the header - on the
    reference HPA it printed 5.77 m and 593%, because it divides a moment slope by a
    lift slope that is zero by construction. Passing those through as results was a
    bug: they read as authoritative and are noise."""

    cn_beta_per_deg: float | None = None
    """Directional (weathercock) stability. Positive is stable.

    Reported in the textbook sign convention, which is NOT the one flow5 writes.
    See `_LATERAL_SIGN` for how that was established."""

    cl_beta_per_deg: float | None = None
    """Dihedral effect - roll response to sideslip. Negative is stable.

    Textbook convention, negated from flow5's. See `_LATERAL_SIGN`."""

    cy_beta_per_deg: float | None = None
    """Side-force slope. Negative for any conventional aircraft.

    flow5 already writes this in the textbook convention, so it is not negated."""

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
            "pitch_stiffness_margin": r(self.pitch_stiffness_margin, 4),
            "trim_alpha": r(self.trim_alpha, 3),
            "cl_at_trim": r(self.cl_at_trim, 5),
            "ld_at_trim": r(self.ld_at_trim, 3),
        }
        if self.sideslip_sweep:
            d = {"points": self.points, "sideslip_sweep": True}
            d["cn_beta_per_deg"] = r(self.cn_beta_per_deg, 6)
            d["cl_beta_per_deg"] = r(self.cl_beta_per_deg, 6)
            d["cy_beta_per_deg"] = r(self.cy_beta_per_deg, 6)
            d["sign_convention"] = (
                "textbook: Cn_beta > 0 stable, Cl_beta < 0 stable"
            )
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


#: flow5 7.57 writes the two lateral moment coefficients with the opposite sign to
#: the convention every stability text uses. Established by control experiment, not
#: by reading flow5's source - three configurations of one HPA, T5, beta -6..6:
#:
#:   fin 6.0 m aft of the CG   dCY/dbeta -0.006333   dCn/dbeta -0.000991
#:   no fin at all             dCY/dbeta -0.000105   dCn/dbeta +0.000038
#:   fin 1.5 m AHEAD of the CG dCY/dbeta -0.006235   dCn/dbeta +0.000381
#:
#: Moving the same fin from behind the CG to in front leaves the side force almost
#: unchanged and flips dCn/dbeta. Only a moment-arm sign change does that, so the
#: aft-fin case - which is stable by construction - is the NEGATIVE one. Likewise
#: for roll, with the fin removed so only the wing contributes:
#:
#:   dihedral +6 deg   dCl/dbeta +0.002089      dihedral +2 deg   +0.000609
#:   dihedral -6 deg   dCl/dbeta -0.002323
#:
#: Monotone in dihedral and flipped by anhedral, which is roll-unstable. So flow5's
#: stable sign is POSITIVE for dCl/dbeta.
#:
#: dCY/dbeta is negative in every case, matching the textbook, and Cm is not
#: affected either - the static margin built on it validates against three
#: published aircraft. Only Cn and Cl are inverted.
_LATERAL_SIGN = -1.0

#: Below this, an alpha column is not being swept and longitudinal slopes are noise.
_SWEPT_DEG = 0.5


def _summarise_sideslip(polar: Polar, s: Summary) -> Summary:
    """Reduce a sideslip polar to the three derivatives it exists to measure.

    Converted into the textbook sign convention on the way out, so that the usual
    rule - Cn_beta > 0 stable, Cl_beta < 0 stable - reads correctly. flow5's raw
    output has both of them the other way round (`_LATERAL_SIGN`), which is a trap:
    applied naively, a strongly weathercock-stable aircraft reads as unstable.
    """
    s.sideslip_sweep = True
    beta = polar.column("β")
    for attr, col, sign in (("cy_beta_per_deg", "CY", 1.0),
                            ("cn_beta_per_deg", "Cn", _LATERAL_SIGN),
                            ("cl_beta_per_deg", "Cl", _LATERAL_SIGN)):
        if polar.has(col) and (fit := _fit(beta, polar.column(col))):
            setattr(s, attr, sign * fit[0])

    if s.cn_beta_per_deg is not None and s.cn_beta_per_deg <= 0:
        s.warnings.append(
            f"directionally UNSTABLE: Cn_beta is {s.cn_beta_per_deg:+.5f} /deg and "
            "has to be positive. The aircraft will diverge in yaw rather than "
            "weathercock back into the wind. Enlarge the fin or move it further aft."
        )
    if s.cl_beta_per_deg is not None and s.cl_beta_per_deg >= 0:
        s.warnings.append(
            f"the dihedral effect is UNSTABLE: Cl_beta is {s.cl_beta_per_deg:+.5f} "
            "/deg and has to be negative. In a sideslip the aircraft rolls further "
            "into it. Add dihedral, or raise the fin."
        )
    return s


def summarise(polar: Polar, *, mac: float | None = None, cg_x: float | None = None,
              log: str = "", cg_height_offset_mac: float | None = None) -> Summary:
    """Reduce a polar to the numbers a designer asked for.

    `cg_height_offset_mac` matters for one reason: −dCm/dCL about a vertically offset
    CG is not the classical static margin, so flow5's own reported figure and this
    one legitimately differ and must not be cross-checked against each other. Pass it
    and the check is skipped; leave it None and the check runs as before.
    """
    if not polar.rows:
        return Summary(points=0, warnings=[
            "flow5 produced no operating points for this analysis. "
            "Nothing can be concluded from it."
        ])

    s = Summary(points=len(polar.rows))
    alpha = polar.column("α")
    cl = polar.column("CL")
    cd = polar.column("CD")

    # A T5 polar holds alpha fixed and sweeps beta. Fitting anything against alpha
    # then divides by zero spread, and flow5's own header figures are noise too, so
    # this leaves before any longitudinal number is computed.
    if polar.has("β"):
        beta = polar.column("β")
        swept = max(beta) - min(beta) if beta else 0.0
        held = max(alpha) - min(alpha) if alpha else 0.0
        if swept > _SWEPT_DEG and held < _SWEPT_DEG:
            return _summarise_sideslip(polar, s)

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
        if s.trim_alpha is not None:
            s.cl_at_trim = _at(alpha, cl, s.trim_alpha)
            if polar.has("CL/CD"):
                s.ld_at_trim = _at(alpha, polar.column("CL/CD"), s.trim_alpha)

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
    # chord. Skipped when the CG is offset vertically, because the two quantities are
    # then different things — flow5 reports the classical margin, −dCm/dCL about a
    # low CG additionally carries the force-tilt term.
    reported = polar.header_float("Static margin")
    offset_matters = (cg_height_offset_mac is not None
                      and abs(cg_height_offset_mac) > 0.05)
    if reported is not None and s.static_margin is not None and not offset_matters:
        theirs = static_margin_from_flow5(reported)
        if abs(theirs - s.static_margin) > max(0.01, abs(s.static_margin) * 0.25):
            s.warnings.append(
                f"flow5 reports a static margin of {theirs:+.3f} while its own lift and "
                f"moment columns give {s.static_margin:+.3f}. Using the computed value. "
                "With the CG at the wing's own height these should agree, so treat this "
                "as a reason to check the geometry rather than as a result."
            )

    s.longitudinal_modes, s.lateral_modes = parse_modes(log)

    if polar.nonfinite:
        cols = sorted({c for _, c in polar.nonfinite})
        s.warnings.append(
            f"flow5 wrote non-finite values in: {', '.join(cols)}. Those columns are "
            "not reported. This usually means an inertia term was zero."
        )
    return s

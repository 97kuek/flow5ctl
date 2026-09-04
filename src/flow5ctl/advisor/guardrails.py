"""Make the wrong thing hard.

flow5 will accept a stability request on a fixed-speed polar and answer with an
eigenvalue of 5.995e+51. It will accept an alpha sweep well past the airfoil's stall
and extrapolate a straight lift line through it. It will accept an inviscid run and
report an L/D three times too high. None of these raise an error.

So the guardrails live here, ahead of the solver, and they refuse rather than warn
when the result would be meaningless.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..errors import DesignError, UnsupportedByFlow5
from ..geometry.derived import Derived
from ..model.presets import Preset

STABILITY_TYPES = {"T7"}
DERIVATIVE_TYPES = {"T7"}


@dataclass(slots=True)
class Check:
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def note(self, message: str) -> None:
        self.notes.append(message)


def check_polar_type(polar_type: str, *, wants_stability: bool = False,
                     derivatives: bool = False) -> None:
    """Refuse combinations flow5 answers wrongly."""
    pt = polar_type.upper()

    if pt in {"T6"}:
        raise UnsupportedByFlow5(
            "T6 control polars need flap or control-surface definitions, and flow5's "
            "plane XML has no hinge elements — a flap belongs to flow5's Foil object, "
            "which a .dat file cannot carry. Planes loaded from a GUI-made project "
            "cannot be paired with new analyses either, so there is no way in. "
            "See docs/FLOW5-INTERFACE.md section 3.3."
        )

    if wants_stability and pt not in STABILITY_TYPES:
        raise DesignError(
            f"A {pt} polar cannot answer a stability question. flow5 will return "
            "eigenvalues of order 1e51 from a non-T7 polar rather than refusing. "
            "Use polar_type='T7' (STABILITYPOLAR) instead.\n"
            "Static margin and neutral point ARE available from a T1 polar; it is the "
            "dynamic modes that require T7."
        )

    if derivatives and pt not in DERIVATIVE_TYPES:
        raise DesignError(
            f"Compute_derivatives is only meaningful on a T7 polar; on a {pt} polar "
            "flow5 fills the derivative columns with zeros and the eigenvalues with "
            "nonsense. Use polar_type='T7'."
        )


def check_analysis(derived: Derived, preset: Preset, *, polar_type: str,
                   alpha: tuple[float, float, float] | None, viscous: bool,
                   on_the_fly: bool, ground_height: float | None) -> Check:
    c = Check()
    limits = preset.limits

    panels = derived.panel_count
    max_panels = int(limits.get("max_panels", 6000))
    if panels > max_panels:
        raise DesignError(
            f"the mesh has {panels} panels, above the {preset.name} preset's ceiling of "
            f"{max_panels}. Reduce wing.panels.spanwise or chordwise. Measured on a 34 m "
            "high-aspect-ratio wing, results were already converged at 544 panels, so a "
            "finer mesh usually buys nothing."
        )

    if alpha is not None:
        max_alpha = float(limits.get("max_alpha", 14.0))
        if max(abs(alpha[0]), abs(alpha[1])) > max_alpha:
            c.warn(
                f"the alpha sweep reaches {max(abs(alpha[0]), abs(alpha[1])):g}°, beyond "
                f"{max_alpha:g}° where a potential-flow result is fiction — there is no "
                "separation model, so CL keeps rising past the real CL_max. Treat the "
                "top of this polar as unusable."
            )
        if alpha[2] <= 0:
            raise DesignError("the alpha step must be positive")

    if not viscous:
        c.warn(
            "this is an INVISCID run. Measured at Re 2e5, an inviscid analysis omitted "
            "93 % of the drag. Do not quote an L/D from it."
        )
    elif on_the_fly:
        if len(derived.surfaces) > 1:
            c.warn(
                "on-the-fly XFoil is unreliable on multi-surface aircraft — measured on "
                "a 3-surface glider it failed to converge on the elevator and discarded "
                "every operating point. The interpolated method is the default for a "
                "reason."
            )
        c.note("viscous drag from on-the-fly XFoil; do not compare against interpolated runs.")
    else:
        c.note("viscous drag interpolated from a 2D polar mesh.")

    if ground_height is not None:
        span = derived.reference_span
        if span and ground_height > span:
            c.warn(
                f"ground height {ground_height:g} m exceeds the span {span:g} m; ground "
                "effect will be negligible at that height."
            )
        c.note(
            "ground effect is on. Report the out-of-ground-effect case too — measured "
            "differences were +18 to +20 % in L/D."
        )
    elif preset.analysis.get("ground_effect"):
        c.warn(
            f"the {preset.name} preset expects ground effect to matter, but this "
            "analysis has none. For an aircraft flown a few metres above water that "
            "omits a large part of the performance."
        )

    if polar_type.upper() in {"T2", "T3"}:
        c.note(
            "a fixed-lift or glide polar flies slower at high CL, so the local Reynolds "
            "number drops well below cruise. The 2D polar mesh must cover that."
        )
        if alpha is not None and alpha[0] <= 0.0:
            c.warn(
                f"this {polar_type.upper()} polar starts at α = {alpha[0]:g}°. A "
                "fixed-lift or glide polar has no solution where the aircraft produces "
                "no lift — the required speed diverges, and flow5 solves an enormous "
                "speed rather than refusing. Start the sweep above the zero-lift angle "
                "(α > 0 for a symmetric section)."
            )
    return c


def check_geometry(derived: Derived, preset: Preset) -> Check:
    """Sanity thresholds, plus the checks flow5 will never do for you."""
    c = Check()

    def band(key: str, value: float | None, label: str, fmt: str = "{:.3g}") -> None:
        b = preset.band(key)
        if b is None or value is None:
            return
        lo, hi = b
        if value < lo or value > hi:
            c.warn(
                f"{label} is {fmt.format(value)}, outside the {lo:g}–{hi:g} range typical "
                f"for {preset.label.lower()}. Check the design, or use preset='custom' if "
                "this is deliberate."
            )

    band("aspect_ratio", derived.aspect_ratio, "aspect ratio", "{:.1f}")
    band("wing_loading", derived.wing_loading, "wing loading (kg/m²)")
    band("reynolds_at_mac", derived.reynolds_at_mac, "Reynolds number at the MAC", "{:.3g}")
    band("tail_volume_h", derived.tail_volume_h, "horizontal tail volume")
    band("tail_volume_v", derived.tail_volume_v, "vertical tail volume", "{:.4g}")

    fin = next((x for x in derived.surfaces if x.wing.role == "fin"), None)
    if fin is not None and fin.wing.count == 2 and preset.band("tail_volume_v"):
        lo, hi = preset.band("tail_volume_v")
        if derived.tail_volume_v is not None and not (lo <= derived.tail_volume_v <= hi):
            # The band was fitted to single-fin aircraft. A twin fin needs more total
            # area for the same effect - each one sits in a worse part of the flow -
            # and one published human-powered aircraft flies at 0.0264 with two.
            # Rather than invent a second band from one data point, say so.
            c.note(
                "that band was set from aircraft with one fin. This design has two, "
                "which normally need more total area for the same effect, so the "
                "figure above may be reasonable — compare it against twin-fin "
                "aircraft rather than against the band."
            )

    if derived.tail_volume_h is None and len(derived.surfaces) == 1:
        c.note("wing only — no tail, so pitch trim and stability cannot be assessed.")

    _check_coincident_surfaces(derived, c)

    semi_span = derived.reference_span / 2.0
    if derived.mass.from_components and derived.mass.lateral_inertia_is_degenerate(semi_span):
        kx = derived.mass.roll_radius_of_gyration
        c.warn(
            f"the roll radius of gyration is {kx:.3g} m, only "
            f"{kx / semi_span * 100:.1f} % of the semi-span (Ixx = {derived.mass.ixx:.3g} "
            "kg·m²). The mass model has essentially no spanwise content, so "
            "lateral-directional results will be meaningless — flow5 returns `inf` for "
            "roll damping in this situation. Give the wing structure mass spanwise "
            "positions; real aircraft sit around 15-35 % of semi-span."
        )
    if not derived.mass.from_components:
        c.note(
            "mass was given as a total, so inertia is unknown and lateral-directional "
            "results will not be meaningful. Use mass.components to get inertia."
        )

    if derived.cg_percent_mac is not None:
        c.note(f"CG is at {derived.cg_percent_mac * 100:.1f} % MAC.")
    return c


def _check_coincident_surfaces(derived: Derived, c: Check) -> None:
    """Two surfaces in the same place make flow5 produce nonsense, not an error.

    Observed: a fin whose root sat exactly on the elevator gave an effective angle of
    attack of -104 degrees at the elevator centre and failed the whole analysis. flow5
    does not check for this, so we do.
    """
    tol = 0.02
    for i, a in enumerate(derived.surfaces):
        for b in derived.surfaces[i + 1:]:
            same_x = abs(a.position_m[0] - b.position_m[0]) < tol
            same_z = abs(a.position_m[2] - b.position_m[2]) < tol
            if not (same_x and same_z):
                continue
            roles = {a.wing.role, b.wing.role}
            if roles == {"elevator", "fin"}:
                c.warn(
                    f"the fin root and the elevator are both at x = "
                    f"{a.position_m[0]:.3g} m, z = {a.position_m[2]:.3g} m. Coincident "
                    "surfaces make flow5 compute nonsensical local flow angles and fail "
                    "the analysis. Offset the fin root a few centimetres above the "
                    "elevator."
                )
            else:
                c.warn(
                    f"{a.wing.name or a.wing.role!r} and {b.wing.name or b.wing.role!r} "
                    f"are at the same position (x = {a.position_m[0]:.3g} m, "
                    f"z = {a.position_m[2]:.3g} m). Overlapping panels give unreliable "
                    "results."
                )

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

    if pt == "T8":
        raise UnsupportedByFlow5(
            "flow5 accepts a T8 polar and returns nonsense from it rather than "
            "refusing. Measured on a 3 m glider asked for alpha 2 to 8 in steps of "
            "2: one point came back, at a speed of 2.0 m/s that nothing in the "
            "request mentioned, reporting a lift-to-drag ratio of 68.6. Whatever "
            "T8POLAR is for, it is not an alpha sweep, and flow5's own "
            "documentation does not say. Use T1, T2, T3, T5 or T7."
        )

    if pt == "T4":
        raise UnsupportedByFlow5(
            "a T4 polar holds the angle of attack and sweeps the speed, and this "
            "tool has no way to express a speed range — `alpha` is the only sweep "
            "there is. flow5 rejects the analysis we generate for it outright "
            "(\"matched no plane with any analysis\"), which used to be reported as "
            "a bug in flow5ctl. To vary speed at a fixed attitude, use `sweep` on "
            "the `speed` parameter with a T1 polar, which is the same question "
            "asked in a way that works."
        )

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
            "this is an INVISCID run. On the shipped 3 m glider at alpha 0 the drag "
            "came to 0.000345 inviscid against 0.018006 viscous — the inviscid run left out "
            "98 % of the drag. Do not quote an L/D from it."
        )
    elif on_the_fly:
        if len(derived.surfaces) > 1:
            c.warn(
                "on-the-fly XFoil can fail outright on a multi-surface aircraft: on one "
                "3-surface glider it reported Cl = 3.23 on the elevator, discarded every "
                "operating point, and had not finished after two minutes. It does not "
                "always — the shipped 3 m glider runs all five points — but it is 8x "
                "slower there (6.5 s against 0.8 s) and gives 19-28 % less viscous drag "
                "than the interpolated method, so the two must never be mixed inside one "
                "comparison. Check that every operating point you asked for came back."
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
            "on the shipped examples with the current defaults, +17.2 % on best L/D "
            "for the 3 m glider at h = 0.30 m and +22.5 % for the 34 m HPA at "
            "h = 2.0 m. `--compare-ground` gives both from one call."
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

    _check_wake_plane(derived, c)
    _check_spanwise_mesh(derived, c)
    _check_extra_surfaces(derived, c)

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


#: Below this many spanwise panels per semi-span, induced drag is measurably
#: optimistic. See docs/log/2026-09-04-induced-drag-and-the-mesh.md.
MIN_SPANWISE = 25


#: A downstream surface closer than this to the wing's own plane, as a fraction of
#: the wing's MAC, sits in its trailing vortex sheet and the induced drag is wrong.
WAKE_PLANE_MAC = 0.10


def _check_wake_plane(derived: Derived, c: Check) -> None:
    """A tail level with the wing sits in its wake sheet, and the drag halves.

    The wing's trailing vortices leave at its own height and run downstream. Put a
    horizontal tail at exactly that height and its control points sit on the sheet,
    which is singular; flow5 does not complain, it returns a number.

    Measured on an AR 12 wing of 0.25 m chord with a 0.9 x 0.15 m tail 1.2 m behind,
    inviscid, at alpha 6, moving only the tail's z:

    | tail z | as a fraction of chord | induced drag | span efficiency |
    |---|---|---|---|
    | 0.000 | 0 | 0.00483 | **1.93 — impossible** |
    | 0.001 | 0.4 % | 0.00734 | 1.27 — impossible |
    | 0.005 | 2 % | 0.00935 | 0.996 |
    | 0.010 | 4 % | 0.00964 | 0.966 |
    | 0.020 | 8 % | 0.00977 | 0.953 |

    Two centimetres of offset **doubles** the induced drag, to a value that then
    matches AVL within 3 %. So this is not a small sensitivity to a modelling
    choice: at zero offset the answer is out by a factor of two, in the optimistic
    direction, with nothing in the output to say so.

    Real aircraft rarely sit exactly there, but a design.yaml written as
    `position: [1.2, 0, 0]` does, and that is an easy thing to type.
    """
    main = derived.main
    if main is None:
        return
    mac = derived.reference_chord
    if not mac:
        return
    # The sheet leaves the wing at the height its lift is centred on, not at the
    # root. Dihedral lifts that by a useful amount on a 34 m wing - `mac_z` is the
    # chord-weighted mean height and is what the CG-height separation already uses -
    # so comparing the two roots would miss a tail level with a dihedral wing's root
    # and flag one level with its mean height.
    z_wing = main.position_m[2] + main.geom.mac_z
    for s in derived.surfaces:
        if s is main or s.wing.role == "fin":
            continue                      # a fin is vertical; it has no such plane
        if s.position_m[0] <= main.position_m[0]:
            continue                      # a canard is upstream of the sheet
        gap = abs(s.position_m[2] + s.geom.mac_z - z_wing)
        if gap >= WAKE_PLANE_MAC * mac:
            continue
        name = s.wing.name or s.wing.role
        c.warn(
            f"{name} sits {gap:.3g} m from the wing's own height, which is "
            f"{gap / mac:.0%} of the MAC, and it is behind the wing. That puts it in "
            "the wing's trailing vortex sheet, where the induced drag comes out "
            "wrong and flow5 says nothing. Measured on a comparable layout: at zero "
            "offset the induced drag was half its converged value and the span "
            "efficiency read 1.93, which is impossible; moving the tail 2 cm — 8 % "
            f"of chord — doubled it and brought it within 3 % of AVL. Offset {name} "
            "vertically by at least a tenth of the MAC, or model the height it "
            "actually has."
        )


def _check_extra_surfaces(derived: Derived, c: Check) -> None:
    """Tail volume is a two-surface idea, and a fourth surface breaks it.

    Both tail volume coefficients are area x lever arm over the main wing's area and
    a reference length, and every published band for them was fitted to aircraft
    with one lifting wing and one tail. On a tandem or a canard the lift is shared
    between two surfaces and the bands are simply not about that aircraft, so the
    number is still computed - it is what flow5's geometry gives - but it is not
    something to size against.
    """
    extra = [s for s in derived.surfaces if s.wing.role == "other"]
    if not extra:
        return
    names = ", ".join(s.wing.name or "unnamed" for s in extra)
    if derived.tail_volume_h is not None or derived.tail_volume_v is not None:
        c.note(
            f"this design has a lifting surface beyond the wing, elevator and fin "
            f"({names}). The tail volumes above are still computed from the elevator "
            "and fin alone, and the bands they are compared against were fitted to "
            "aircraft with one wing and one tail. On a tandem or a canard they are "
            "not the right measure of pitch or yaw authority — check the trimmed "
            "condition and the static margin instead."
        )


def _check_spanwise_mesh(derived: Derived, c: Check) -> None:
    """Induced drag is set by the span, and a coarse span makes it optimistic.

    Measured on rectangular wings at AR 10 and AR 40, inviscid, varying only the
    spanwise panel count. Span efficiency comes out **above 1** on a coarse mesh —
    impossible for a planar wing — and falls monotonically, linearly in 1/N:

    | spanwise per semi-span | how optimistic the induced drag is |
    |---|---|
    | 20 | about 3 % |
    | 40 | about 1.5 % |
    | 80 | about 0.7 % |

    Chordwise panels make no difference to this at all: 7, 13 and 21 chordwise agree
    to four decimal places. So the fix is always to spend the panels on the span.
    """
    main = derived.main
    if main is None:
        return
    spanwise = getattr(main.wing.panels, "spanwise", None)
    if not spanwise or spanwise >= MIN_SPANWISE:
        return
    c.note(
        f"the wing has {spanwise} spanwise panels per semi-span. Induced drag is set "
        "by the span, and below about 25 it is optimistic — measured 3 % at 20 "
        "panels, with the span efficiency coming out above 1, which is impossible "
        "for a planar wing. Chordwise panels do not help this; 40 spanwise brings it "
        "inside 1.5 %."
    )


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

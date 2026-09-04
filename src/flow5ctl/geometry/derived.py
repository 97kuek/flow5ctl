"""Everything flow5ctl computes from a design and hands back to the agent.

Two of these are load-bearing rather than informational:

* `reference_area`, `reference_span`, `reference_chord` are written into every polar
  as `CUSTOM`, because flow5's `PLANFORM` and `PROJECTED` modes silently produce
  zeros in script mode (ADR-0005).
* `reynolds_min` / `reynolds_max` set the 2D polar mesh range. A mesh covering only
  cruise silently fails at high CL (ADR-0009).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..errors import DesignError
from ..model.design import Design, Section, Wing
from ..units import GRAVITY, to_si_length, to_si_speed
from .massprops import MassProperties, solve_mass
from .planform import SurfaceGeometry, resolve_sections, surface_geometry


@dataclass(frozen=True, slots=True)
class Surface:
    wing: Wing
    sections: list[Section]
    geom: SurfaceGeometry
    position_m: tuple[float, float, float]


@dataclass(slots=True)
class Derived:
    """SI units throughout."""

    surfaces: list[Surface]
    mass: MassProperties
    cruise_speed: float | None
    density: float
    kinematic_viscosity: float
    warnings: list[str] = field(default_factory=list)

    # ---- the main wing is the reference for everything ----
    @property
    def main(self) -> Surface:
        return self.surfaces[0]

    @property
    def reference_area(self) -> float:
        return self.main.geom.planform_area

    @property
    def reference_span(self) -> float:
        return self.main.geom.span

    @property
    def reference_chord(self) -> float:
        return self.main.geom.mac

    @property
    def aspect_ratio(self) -> float:
        return self.main.geom.aspect_ratio

    @property
    def wing_loading(self) -> float:
        """kg/m^2 — the number model-aircraft designers actually quote."""
        return self.mass.total / self.reference_area

    @property
    def panel_count(self) -> int:
        # a twin fin is emitted as two `<wing>` elements, so it costs twice the panels
        return sum(s.geom.panel_count * s.wing.count for s in self.surfaces)

    @property
    def cg_percent_mac(self) -> float | None:
        """CG position as a fraction of MAC aft of the MAC leading edge."""
        mac = self.reference_chord
        if not mac:
            return None
        return (self.mass.cg[0] - self.main.geom.mac_le_x) / mac

    @property
    def reference_height(self) -> float:
        """The height the pitching moment should be referenced to.

        Chord-weighted mean height of the main wing, which dihedral raises well above
        the root. Taking the moment about a CG offset from this in z adds a term to
        dCm/dCL that is not part of the classical static margin.

        **This is an approximation, and it is worth knowing its size.** The term
        vanishes exactly at the height where the resultant aerodynamic force acts,
        which is the *load*-weighted mean height over every lifting surface, not the
        chord-weighted mean height of the wing alone. The two differ because lift is
        not proportional to chord and because the tail carries load at its own height.

        Measured on a 32 m human-powered aircraft, from the spanwise strip table of
        the run itself: chord-weighted 0.5536 m, load-weighted over wing and tail
        0.5218 m, a difference of 0.037 MAC. At the measured sensitivity of 22.0
        points of margin per MAC of height offset, that leaves **0.8 points** of
        residual on a +23.4 %MAC static margin - 3.5 % of it, and one twenty-eighth
        of the 22.8-point error this reference removed.

        Using the load-weighted height instead is possible - the strips are already
        parsed from the first pass - but it would make the static margin depend on
        strip parsing succeeding, and the loading changes with alpha so there is no
        single height anyway. Documented rather than chased.
        """
        return self.main.geom.mac_z

    @property
    def cg_height_offset_mac(self) -> float:
        """(CG height − reference height) in MAC, negative for a CG below the wing.

        On a human-powered aircraft the pilot hangs half a metre below the root and
        dihedral lifts the wing's mean height further still, so this routinely reaches
        −1 MAC — enough to move the reported pitch stiffness by 25 percentage points.
        """
        mac = self.reference_chord
        if not mac:
            return 0.0
        return (self.mass.cg[2] - self.reference_height) / mac

    # ---- Reynolds ----
    def reynolds(self, chord: float, speed: float) -> float:
        return chord * speed / self.kinematic_viscosity

    @property
    def reynolds_at_mac(self) -> float | None:
        if self.cruise_speed is None:
            return None
        return self.reynolds(self.reference_chord, self.cruise_speed)

    def stall_speed(self, cl_max: float = 1.2) -> float | None:
        """Rough minimum flight speed, used to bound the 2D polar mesh."""
        q = 0.5 * self.density * self.reference_area * cl_max
        if q <= 0:
            return None
        return math.sqrt(self.mass.total * GRAVITY / q)

    def reynolds_envelope(self, cl_max: float = 1.2, margin: float = 1.5
                          ) -> tuple[float, float]:
        """(min, max) local Reynolds number over the whole flight envelope.

        The minimum comes from the *smallest* chord at the *lowest* speed, which is
        the case that actually bites: a fixed-lift polar solves a lower speed at high
        CL, and the wing tip is already the low-Re end. Measured consequence of
        getting this wrong: 1 of 6 operating points instead of 6.
        """
        chords = [
            c
            for s in self.surfaces
            for c in (s.geom.tip_chord, s.geom.root_chord)
            if c > 0
        ]
        c_min, c_max = min(chords), max(chords)
        v_lo = self.stall_speed(cl_max) or (self.cruise_speed or 10.0)
        v_hi = max(self.cruise_speed or v_lo, v_lo) * 2.0
        lo = self.reynolds(c_min, v_lo) / margin
        hi = self.reynolds(c_max, v_hi) * margin
        return max(lo, 5.0e3), hi

    # ---- tail volumes: the sanity check flow5 will not do for you ----
    def _tail(self, role: str) -> Surface | None:
        return next((s for s in self.surfaces if s.wing.role == role), None)

    @property
    def tail_volume_h(self) -> float | None:
        t = self._tail("elevator")
        if t is None or not self.reference_chord:
            return None
        arm = (t.geom.mac_le_x + 0.25 * t.geom.mac) - (
            self.main.geom.mac_le_x + 0.25 * self.main.geom.mac
        )
        return t.geom.planform_area * arm / (self.reference_area * self.reference_chord)

    @property
    def tail_volume_v(self) -> float | None:
        t = self._tail("fin")
        if t is None or not self.reference_span:
            return None
        arm = (t.geom.mac_le_x + 0.25 * t.geom.mac) - (
            self.main.geom.mac_le_x + 0.25 * self.main.geom.mac
        )
        # a twin fin contributes both areas; `count` is 1 for every other surface
        area = t.geom.planform_area * t.wing.count
        return area * arm / (self.reference_area * self.reference_span)

    def as_dict(self) -> dict:
        """The payload returned to an agent. Rounded for legibility, SI throughout."""

        def r(v: float | None, n: int = 4) -> float | None:
            return None if v is None else round(v, n)

        g = self.main.geom
        return {
            "planform_area": r(g.planform_area),
            "projected_area": r(g.projected_area),
            "span": r(g.span),
            "projected_span": r(g.projected_span),
            "mac": r(g.mac),
            "mac_y": r(g.mac_y),
            "mac_le_x": r(g.mac_le_x),
            "aspect_ratio": r(g.aspect_ratio, 2),
            "taper_ratio": r(g.taper_ratio, 3),
            "root_chord": r(g.root_chord),
            "tip_chord": r(g.tip_chord),
            "total_mass": r(self.mass.total, 3),
            "cg": [r(v) for v in self.mass.cg],
            "cg_percent_mac": r(self.cg_percent_mac, 4),
            "reference_height": r(self.reference_height),
            "cg_height_offset_mac": r(self.cg_height_offset_mac, 3),
            "inertia": {
                "ixx": r(self.mass.ixx, 6), "iyy": r(self.mass.iyy, 6),
                "izz": r(self.mass.izz, 6), "ixz": r(self.mass.ixz, 6),
            },
            "wing_loading": r(self.wing_loading, 3),
            "reynolds_at_mac": None if self.reynolds_at_mac is None else round(self.reynolds_at_mac),
            "panel_count": self.panel_count,
            "tail_volume_h": r(self.tail_volume_h, 3),
            "tail_volume_v": r(self.tail_volume_v, 4),
            "surfaces": [
                {
                    "name": s.wing.name or s.wing.role,
                    "role": s.wing.role,
                    "area": r(s.geom.planform_area),
                    "span": r(s.geom.span),
                    "mac": r(s.geom.mac),
                    "aspect_ratio": r(s.geom.aspect_ratio, 2),
                    "panels": s.geom.panel_count,
                }
                for s in self.surfaces
            ],
        }


def solve(design: Design) -> Derived:
    """Compute everything derivable from a design. No flow5 involved."""
    lu, mu, su = design.units.length, design.units.mass, design.units.speed
    to_m = to_si_length(1.0, lu)

    surfaces: list[Surface] = []
    for wing in design.surfaces():
        sections = resolve_sections(wing, to_m)
        surfaces.append(
            Surface(
                wing=wing,
                sections=sections,
                geom=surface_geometry(wing, sections, to_m),
                position_m=tuple(to_si_length(v, lu) for v in wing.position),  # type: ignore[arg-type]
            )
        )
    if not surfaces:
        raise DesignError("a design needs at least a main wing")

    mass = solve_mass(design.mass, lu, mu)
    cruise = design.requirements.cruise_speed
    d = Derived(
        surfaces=surfaces,
        mass=mass,
        cruise_speed=None if cruise is None else to_si_speed(cruise, su),
        density=design.atmosphere.density,
        kinematic_viscosity=design.atmosphere.kinematic_viscosity,
    )

    # airfoil references must resolve, or flow5 discards the plane without an error
    known = design.airfoil_names()
    for s in surfaces:
        for sec in s.sections:
            for nm in (sec.airfoil, sec.airfoil_left, sec.airfoil_right):
                if nm and nm not in known:
                    raise DesignError(
                        f"section at y={sec.y:g} references airfoil {nm!r}, which is not "
                        f"declared in `airfoils`. Known: {sorted(known) or 'none'}. "
                        "flow5 silently discards a plane whose foils cannot be resolved."
                    )
            if not (sec.airfoil or (sec.airfoil_left and sec.airfoil_right)):
                raise DesignError(
                    f"section at y={sec.y:g} on {s.wing.name or s.wing.role!r} has no airfoil"
                )
    return d

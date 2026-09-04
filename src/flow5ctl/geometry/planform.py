"""Planform geometry: shorthand expansion, areas, span, mean aerodynamic chord.

Conventions, verified against flow5 7.57 (see docs/FLOW5-INTERFACE.md section 3 and
the dihedral experiment in docs/log/2026-09-03-poc-verification.md):

* A section's `y` is the span station measured **along the wing**. Dihedral tilts the
  panel outboard of that section without shortening its y extent, so
  `span` (also called planform or developed span) is `2 * y_tip` for a symmetric
  surface, while `projected_span` accumulates `dy * cos(dihedral)`.
* `dihedral`, `twist` and the spanwise panel count on a section describe the panel
  **outboard** of it. The tip section's values for those are ignored.

All integrals below are exact for the linear (trapezoidal) panels flow5 uses; nothing
here approximates, so a wing with breaks is handled correctly. That matters because
the two-parameter taper formula for MAC is wrong for any wing with more than two
sections — which is most real ones.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise

from ..errors import DesignError
from ..model.design import Panels, Planform, Section, Wing


@dataclass(frozen=True, slots=True)
class Panel:
    """One trapezoidal segment between two sections, in SI units."""

    y0: float
    y1: float
    c0: float
    c1: float
    x0: float
    x1: float
    dihedral_deg: float

    @property
    def dy(self) -> float:
        return self.y1 - self.y0

    def integral_c(self) -> float:
        """∫ c dy over the panel — its area."""
        return self.dy * (self.c0 + self.c1) / 2.0

    def integral_c2(self) -> float:
        """∫ c² dy — the numerator of the mean aerodynamic chord."""
        return self.dy * (self.c0 * self.c0 + self.c0 * self.c1 + self.c1 * self.c1) / 3.0

    def integral_cy(self) -> float:
        """∫ c·y dy — locates the MAC spanwise."""
        dc, dyy = self.c1 - self.c0, self.y1 - self.y0
        return self.dy * (self.c0 * self.y0 + (self.c0 * dyy + self.y0 * dc) / 2.0 + dc * dyy / 3.0)

    def integral_cx(self) -> float:
        """∫ c·x_le dy — locates the MAC leading edge in x."""
        dc, dxx = self.c1 - self.c0, self.x1 - self.x0
        return self.dy * (self.c0 * self.x0 + (self.c0 * dxx + self.x0 * dc) / 2.0 + dc * dxx / 3.0)

    def integral_cz(self, z0: float, z1: float) -> float:
        """∫ c·z dy — locates the surface's mean height, which dihedral raises."""
        dc, dzz = self.c1 - self.c0, z1 - z0
        return self.dy * (self.c0 * z0 + (self.c0 * dzz + z0 * dc) / 2.0 + dc * dzz / 3.0)


@dataclass(frozen=True, slots=True)
class SurfaceGeometry:
    """Derived geometry for one lifting surface, SI units."""

    planform_area: float
    projected_area: float
    span: float
    projected_span: float
    mac: float
    mac_y: float
    mac_le_x: float
    mac_z: float
    """Area-weighted mean height of the surface, raised by dihedral.

    This is the height the aerodynamic force acts at, and it is the reference the
    pitching moment should be taken about. A CG offset from it in z changes dCm/dCL
    by a term that is not part of the classical static margin — see
    docs/FLOW5-INTERFACE.md section 5.3."""
    root_chord: float
    tip_chord: float
    aspect_ratio: float
    taper_ratio: float
    panel_count: int

    @property
    def mean_chord(self) -> float:
        return self.planform_area / self.span if self.span else 0.0


def expand_planform(pf: Planform, panels: Panels, airfoil: str | None,
                    symmetric: bool) -> list[Section]:
    """Turn planform shorthand into explicit sections.

    This is the only way sections come into existence from shorthand, so the two can
    never silently diverge — `flow5ctl expand` writes the result back into the design
    when a user wants to hand-tune it.
    """
    semi = pf.span / 2.0 if symmetric else pf.span
    stations = sorted({0.0, *(f * semi for f in pf.breaks), semi})
    tip_chord = pf.root_chord * pf.taper
    sweep = math.tan(math.radians(pf.sweep_le))

    out: list[Section] = []
    for i, y in enumerate(stations):
        f = y / semi if semi else 0.0
        out.append(
            Section(
                y=y,
                chord=pf.root_chord + (tip_chord - pf.root_chord) * f,
                offset=y * sweep,
                dihedral=pf.dihedral,
                twist=pf.washout * f,
                airfoil=airfoil,
                chordwise=panels.chordwise,
                spanwise=None,  # allocated by allocate_spanwise_panels
            )
        )
        if i == len(stations) - 1:
            out[-1] = out[-1].model_copy(update={"spanwise": 1})
    return out


def allocate_spanwise_panels(sections: list[Section], total: int) -> list[int]:
    """Distribute `total` spanwise panels over the segments, proportional to length.

    Returns one count per section; the tip section always gets 1, which is what flow5
    expects for the section that terminates the wing.
    """
    lengths = [b.y - a.y for a, b in pairwise(sections)]
    span = sum(lengths)
    if span <= 0:
        raise DesignError("wing has zero span")
    n_seg = len(lengths)
    total = max(total, n_seg)

    raw = [total * L / span for L in lengths]
    counts = [max(1, round(r)) for r in raw]

    # correct rounding drift against the largest segments so the total is exact
    while sum(counts) != total:
        diff = total - sum(counts)
        order = sorted(range(n_seg), key=lambda i: raw[i], reverse=diff > 0)
        for i in order:
            if diff > 0:
                counts[i] += 1
                diff -= 1
            elif counts[i] > 1:
                counts[i] -= 1
                diff += 1
            if diff == 0:
                break
        else:
            break  # cannot go lower; every segment is at 1

    return [*counts, 1]


def resolve_sections(wing: Wing, length_to_m: float) -> list[Section]:
    """Explicit sections for a wing, in SI units, with panel counts filled in."""
    if wing.sections is not None:
        sections = [s.model_copy() for s in wing.sections]
    else:
        assert wing.planform is not None
        sections = expand_planform(
            wing.planform, wing.panels, wing.airfoil, bool(wing.symmetric)
        )

    # the wing-level airfoil cascades into any section that does not name one
    sections = [
        s.model_copy(update={
            "y": s.y * length_to_m,
            "chord": s.chord * length_to_m,
            "offset": s.offset * length_to_m,
            "chordwise": s.chordwise or wing.panels.chordwise,
            "airfoil": s.airfoil or wing.airfoil,
        })
        for s in sections
    ]

    if any(s.spanwise is None for s in sections[:-1]):
        counts = allocate_spanwise_panels(sections, wing.panels.spanwise)
        sections = [
            s.model_copy(update={"spanwise": s.spanwise or c})
            for s, c in zip(sections, counts, strict=True)
        ]
    sections[-1] = sections[-1].model_copy(update={"spanwise": 1})
    return sections


def panels_of(sections: list[Section], position_x_m: float) -> list[Panel]:
    return [
        Panel(
            y0=a.y, y1=b.y,
            c0=a.chord, c1=b.chord,
            x0=position_x_m + a.offset, x1=position_x_m + b.offset,
            dihedral_deg=a.dihedral,
        )
        for a, b in pairwise(sections)
    ]


def surface_geometry(wing: Wing, sections: list[Section], length_to_m: float) -> SurfaceGeometry:
    """Areas, span and MAC for one surface. `sections` must already be SI."""
    position_z_m = wing.position[2] * length_to_m
    panels = panels_of(sections, wing.position[0] * length_to_m)
    if not panels:
        raise DesignError(f"wing {wing.name or wing.role!r} has no panels")

    mirror = 2.0 if wing.symmetric else 1.0

    semi_area = sum(p.integral_c() for p in panels)
    semi_proj_area = sum(p.integral_c() * math.cos(math.radians(p.dihedral_deg)) for p in panels)
    semi_span = sections[-1].y - sections[0].y
    semi_proj_span = sum(p.dy * math.cos(math.radians(p.dihedral_deg)) for p in panels)

    int_c = semi_area
    mac = sum(p.integral_c2() for p in panels) / int_c
    mac_y = sum(p.integral_cy() for p in panels) / int_c
    mac_le_x = sum(p.integral_cx() for p in panels) / int_c

    # height of each section, accumulated through the dihedral of the panel inboard
    z = position_z_m
    heights = [z]
    for p in panels:
        z += p.dy * math.tan(math.radians(p.dihedral_deg))
        heights.append(z)
    mac_z = sum(p.integral_cz(heights[i], heights[i + 1])
                for i, p in enumerate(panels)) / int_c

    area = semi_area * mirror
    span = semi_span * mirror
    return SurfaceGeometry(
        planform_area=area,
        projected_area=semi_proj_area * mirror,
        span=span,
        projected_span=semi_proj_span * mirror,
        mac=mac,
        mac_y=mac_y,
        mac_le_x=mac_le_x,
        mac_z=mac_z,
        root_chord=sections[0].chord,
        tip_chord=sections[-1].chord,
        aspect_ratio=span * span / area if area else 0.0,
        taper_ratio=sections[-1].chord / sections[0].chord if sections[0].chord else 0.0,
        # Two, always - not `int(mirror)`. flow5's own element count doubles every
        # surface, a fin included, and ours only doubled the mirrored ones. Measured
        # on a 34 m aircraft, varying only the fin's spanwise count: our total was
        # short by exactly the fin's panels every time (56 -> 56, 112 -> 112,
        # 168 -> 168), so flow5 allocates a mirrored half for a fin that
        # `<symmetric>false</symmetric>` says it should not have. Whether it then
        # uses that half is not visible from here; the side force behaves as one fin
        # (two fins of double the area gave 1.92x, not 3.8x), so it probably does
        # not. What matters for this number is the matrix flow5 actually builds,
        # because that is what the panel budget is protecting and what the
        # documented cross-check compares against.
        panel_count=sum((s.chordwise or 0) * (s.spanwise or 0) for s in sections[:-1])
        * 2,
    )

"""Mass properties: total mass, centre of gravity, moments of inertia.

Inertia is not decoration. flow5 with `Use_plane_inertia=true` derives inertia from
the plane's masses and *discards* whatever you wrote in the analysis XML; if every
mass sits on the centreline, `Ixx` comes out 0 and every lateral-directional result
becomes `inf` — silently, with no error.

So flow5ctl computes inertia here and writes it explicitly with
`Use_plane_inertia=false`. See docs/FLOW5-INTERFACE.md section 4.4.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..errors import DesignError
from ..model.design import Mass
from ..units import to_si_length, to_si_mass


@dataclass(frozen=True, slots=True)
class MassProperties:
    """SI units. Moments of inertia are about the CG."""

    total: float
    cg: tuple[float, float, float]
    ixx: float
    iyy: float
    izz: float
    ixz: float
    from_components: bool

    @property
    def roll_radius_of_gyration(self) -> float:
        """k_x = sqrt(Ixx / m), in metres."""
        return math.sqrt(self.ixx / self.total) if self.total > 0 else 0.0

    def lateral_inertia_is_degenerate(self, semi_span: float) -> bool:
        """True when Ixx is too small for lateral results to mean anything.

        Testing `Ixx > 0` is not enough: a design whose masses all sit on the
        centreline still gets a non-zero Ixx from their z offsets, while being wildly
        wrong for a 17 m semi-span wing whose structure is spread along it.

        The physical test is the roll radius of gyration as a fraction of the
        semi-span. Real aircraft sit around 0.15-0.35; below 0.05 the mass model has
        no spanwise content at all.
        """
        if self.ixx <= 1e-12 or semi_span <= 0:
            return True
        return self.roll_radius_of_gyration < 0.05 * semi_span


def solve_mass(mass: Mass, length_unit: str, mass_unit: str) -> MassProperties:
    if mass.components:
        items = [
            (to_si_mass(c.mass, mass_unit),
             tuple(to_si_length(v, length_unit) for v in c.at))
            for c in mass.components
        ]
        # Rounded because summing masses a designer typed in decimal produces
        # binary representation noise: 0.40 + 0.10 + 0.10 + 0.10 came back as
        # 0.7000000000000001 kg and was reported that way. At 1e-12 kg this is far
        # below anything meaningful, and a number that looks broken makes a careful
        # reader doubt every other number in the report.
        total = round(sum(m for m, _ in items), 12)
        if total <= 0:
            raise DesignError("total mass is zero")
        cg = tuple(sum(m * p[i] for m, p in items) / total for i in range(3))

        ixx = iyy = izz = ixz = 0.0
        for m, p in items:
            dx, dy, dz = p[0] - cg[0], p[1] - cg[1], p[2] - cg[2]
            ixx += m * (dy * dy + dz * dz)
            iyy += m * (dx * dx + dz * dz)
            izz += m * (dx * dx + dy * dy)
            ixz += m * dx * dz
        return MassProperties(total, cg, ixx, iyy, izz, ixz, from_components=True)  # type: ignore[arg-type]

    if mass.total is None or mass.cg is None:
        raise DesignError("give mass.components, or mass.total with mass.cg")
    return MassProperties(
        total=to_si_mass(mass.total, mass_unit),
        cg=tuple(to_si_length(v, length_unit) for v in mass.cg),  # type: ignore[arg-type]
        ixx=0.0, iyy=0.0, izz=0.0, ixz=0.0,
        from_components=False,
    )

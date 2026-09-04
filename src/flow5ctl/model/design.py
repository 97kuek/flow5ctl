"""The `design.yaml` schema — the source of truth for an aircraft.

Shaped so a language model can fill it in from a sentence and a human can read it in
a diff: flat where possible, explicit units, no magic numbers. See
docs/DOMAIN-MODEL.md.

Values here are in the design's declared units. `geometry.solve()` converts to SI.
"""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA = "flow5ctl/design/1"

Distribution = Literal["UNIFORM", "COSINE", "SINE", "INV_SINE", "TANH", "INV_EXP"]
WingRole = Literal["main", "elevator", "fin", "other"]


class Base(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Units(Base):
    length: Literal["m", "cm", "mm", "in", "ft"] = "m"
    mass: Literal["kg", "g", "lb", "oz"] = "kg"
    speed: Literal["m/s", "km/h", "mph", "kt", "ft/s"] = "m/s"
    angle: Literal["deg"] = "deg"


class Atmosphere(Base):
    density: Annotated[float, Field(gt=0)] = 1.225
    kinematic_viscosity: Annotated[float, Field(gt=0)] = 1.5e-5


class Requirements(Base):
    """Design intent. Never sent to flow5 — used to choose analyses, sanity-check
    results, and tell the agent when it is done."""

    cruise_speed: Annotated[float, Field(gt=0)] | None = None
    total_mass: Annotated[float, Field(gt=0)] | None = None
    static_margin: tuple[float, float] | None = None
    """Acceptable band as a fraction of MAC, e.g. [0.05, 0.15]."""
    ground_effect_height: Annotated[float, Field(gt=0)] | None = None
    objective: Literal["max_range", "min_sink", "max_speed", "custom"] = "max_range"

    @model_validator(mode="after")
    def _band_ordered(self) -> Requirements:
        if self.static_margin and self.static_margin[0] >= self.static_margin[1]:
            raise ValueError("static_margin must be [low, high] with low < high")
        return self


class MassComponent(Base):
    tag: str
    mass: Annotated[float, Field(gt=0)]
    at: tuple[float, float, float]
    """(x, y, z) in design length units. y != 0 matters: mass on the centreline
    gives Ixx = 0 and makes every lateral stability result meaningless."""


class Mass(Base):
    components: list[MassComponent] = Field(default_factory=list)
    total: Annotated[float, Field(gt=0)] | None = None
    cg: tuple[float, float, float] | None = None

    @model_validator(mode="after")
    def _one_or_the_other(self) -> Mass:
        if not self.components and self.total is None:
            raise ValueError("give mass.components, or mass.total with mass.cg")
        if self.total is not None and self.cg is None and not self.components:
            raise ValueError("mass.total needs mass.cg")
        return self


class FoilPolarSpec(Base):
    """The 2D polar mesh to compute for this airfoil.

    Leave `reynolds` unset and flow5ctl derives it from the flight envelope — which
    is the safer choice, because a mesh that only covers cruise silently fails at
    high CL. See docs/FLOW5-INTERFACE.md section 4.3.
    """

    reynolds: list[Annotated[float, Field(gt=0)]] | None = None
    ncrit: Annotated[float, Field(gt=0)] = 9.0
    alpha: tuple[float, float, float] = (-10.0, 16.0, 0.5)


class Airfoil(Base):
    name: str
    """The name sections refer to. Also written as line 1 of the .dat file, because
    that — not the filename — is how flow5 identifies a foil."""
    source: str
    """`naca:2412`, `file:airfoils/ag35.dat`, or `url:https://…`"""
    polars: FoilPolarSpec = Field(default_factory=FoilPolarSpec)


class Panels(Base):
    chordwise: Annotated[int, Field(ge=2, le=40)] = 13
    spanwise: Annotated[int, Field(ge=1, le=120)] = 20
    """Total panels across the semi-span, distributed over the sections."""
    chord_distribution: Distribution = "COSINE"
    span_distribution: Distribution = "COSINE"


class Section(Base):
    y: Annotated[float, Field(ge=0)]
    """Span station, measured ALONG the wing. Dihedral tilts the panel outboard of
    this section without shortening its y extent — verified, see
    docs/FLOW5-INTERFACE.md section 3."""
    chord: Annotated[float, Field(gt=0)]
    offset: float = 0.0
    dihedral: float = 0.0
    twist: float = 0.0
    airfoil: str | None = None
    airfoil_left: str | None = None
    airfoil_right: str | None = None
    chordwise: int | None = None
    spanwise: int | None = None


class Planform(Base):
    """Shorthand, expanded into sections. Convenience only — sections are the truth."""

    span: Annotated[float, Field(gt=0)]
    """Full span, tip to tip, for a symmetric surface; root to tip for a fin."""
    root_chord: Annotated[float, Field(gt=0)]
    taper: Annotated[float, Field(gt=0, le=1)] = 1.0
    sweep_le: float = 0.0
    dihedral: float = 0.0
    washout: float = 0.0
    """Twist at the tip, degrees, linear from the root. Negative unloads the tip."""
    breaks: list[Annotated[float, Field(gt=0, lt=1)]] = Field(default_factory=list)
    """Extra section stations, as fractions of the semi-span."""


class Wing(Base):
    name: str | None = None
    role: WingRole = "main"
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    incidence: float = 0.0
    airfoil: str | None = None
    planform: Planform | None = None
    sections: list[Section] | None = None
    panels: Panels = Field(default_factory=Panels)
    symmetric: bool | None = None
    count: Annotated[int, Field(ge=1, le=2)] = 1
    """How many of this surface there are. Only a fin may have two.

    Twin fins are ordinary on human-powered aircraft and on twin-boom layouts, and
    flow5 handles them natively - a plane is a list of `<wing>` elements with no cap,
    so two fins are two entries, each stood up by its own `Rx_angle`. Measured: two
    fins of exactly double the area gave 1.92x the side force and 1.96x the yaw
    moment of one, the shortfall being tip loss. Modelling them as one equivalent
    fin of the combined area is the workaround this replaces; it gets the yaw
    stiffness about right but puts all of it on the centreline.

    With `count: 2` the y in `position` is the half-spacing: the fins are placed at
    +y and -y. `tail_volume_v` counts both."""

    @model_validator(mode="after")
    def _exactly_one_geometry(self) -> Wing:
        if (self.planform is None) == (self.sections is None):
            raise ValueError("a wing needs exactly one of `planform` or `sections`")
        if self.sections is not None:
            if len(self.sections) < 2:
                raise ValueError("a wing needs at least two sections")
            ys = [s.y for s in self.sections]
            if ys != sorted(ys) or len(set(ys)) != len(ys):
                raise ValueError("section `y` must be strictly increasing")
            if ys[0] != 0.0:
                raise ValueError("the first section must be at y = 0")
        return self


class Tail(Base):
    type: Literal["conventional", "t-tail", "v-tail", "canard", "none"] = "conventional"
    elevator: Wing | None = None
    fin: Wing | None = None

    @model_validator(mode="after")
    def _roles(self) -> Tail:
        if self.elevator is not None:
            self.elevator.role = "elevator"
            if self.elevator.count != 1:
                raise ValueError("only a fin may have count: 2")
        if self.fin is not None:
            self.fin.role = "fin"
            if self.fin.symmetric is None:
                self.fin.symmetric = False
            if self.fin.count == 2 and self.fin.position[1] == 0.0:
                raise ValueError(
                    "two fins need a half-spacing: set the y in the fin's `position` "
                    "to where one of them sits, and the pair is placed at ±y"
                )
        return self


class Fuselage(Base):
    type: Literal["none", "pod", "frames"] = "none"
    frames: list[dict] | None = None


class Design(Base):
    schema_: Literal["flow5ctl/design/1"] = Field(default=SCHEMA, alias="schema")
    name: str
    description: str = ""
    preset: str = "custom"
    units: Units = Field(default_factory=Units)
    atmosphere: Atmosphere = Field(default_factory=Atmosphere)
    requirements: Requirements = Field(default_factory=Requirements)
    mass: Mass
    airfoils: list[Airfoil] = Field(default_factory=list)
    wing: Wing
    tail: Tail = Field(default_factory=Tail)
    fuselage: Fuselage = Field(default_factory=Fuselage)

    @model_validator(mode="after")
    def _wing_is_main(self) -> Design:
        self.wing.role = "main"
        if self.wing.symmetric is None:
            self.wing.symmetric = True
        for w in (self.tail.elevator, self.tail.fin):
            if w is not None and w.symmetric is None:
                w.symmetric = w.role != "fin"
        return self

    def surfaces(self) -> list[Wing]:
        """Every lifting surface, main wing first."""
        return [w for w in (self.wing, self.tail.elevator, self.tail.fin) if w is not None]

    def airfoil_names(self) -> set[str]:
        return {a.name for a in self.airfoils}

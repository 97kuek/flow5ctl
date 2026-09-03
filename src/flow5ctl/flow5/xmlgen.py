"""Generate the XML flow5 reads. The only module that writes flow5's dialect.

Two rules are structural rather than advisory:

* **There is no function that can emit both a `<foil_analysis>` and a
  `<Plane_analysis>` section.** A script with both segfaults flow5 (verified,
  reproducibly, with no output at all). `foil_script` and `plane_script` are separate
  entry points and neither can produce the other's section. See ADR-0009.
* **Reference dimensions are always `CUSTOM` with explicit values.** flow5's
  `PLANFORM` and `PROJECTED` modes silently yield zeros in script mode. See ADR-0005.

Field names are matched case-insensitively by flow5, and unknown elements are
silently skipped — so a typo here is not an error, it is a wrong analysis. Everything
written below is taken from docs/FLOW5-INTERFACE.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

from ..errors import InternalError
from ..geometry.derived import Derived, Surface
from ..model.design import Design, Section

_HEAD = '<?xml version="1.0" encoding="UTF-8"?>'

VALID_METHODS = ("LLT", "VLM1", "VLM2", "QUADS", "TRIUNIFORM", "TRILINEAR")
POLAR_TYPES = {
    "T1": "FIXEDSPEEDPOLAR",
    "T2": "FIXEDLIFTPOLAR",
    "T3": "GLIDEPOLAR",
    "T4": "FIXEDAOAPOLAR",
    "T5": "BETAPOLAR",
    "T6": "CONTROLPOLAR",
    "T7": "STABILITYPOLAR",
    "T8": "T8POLAR",
}
_WING_TYPE = {"main": "MAINWING", "elevator": "ELEVATOR", "fin": "FIN", "other": "OTHERWING"}


def _e(v: object) -> str:
    return escape(str(v))


def _tag(name: str, value: object, indent: int) -> str:
    return f"{' ' * indent}<{name}>{_e(value)}</{name}>"


def _units_block(indent: int) -> str:
    """flow5ctl always writes SI, so every conversion factor is 1."""
    pad = " " * indent
    return (
        f"{pad}<Units>\n"
        f"{pad}  <meter_to_length_unit>1.0</meter_to_length_unit>\n"
        f"{pad}  <kg_to_mass_unit>1.0</kg_to_mass_unit>\n"
        f"{pad}  <ms_to_speed_unit>1.0</ms_to_speed_unit>\n"
        f"{pad}  <m2_to_area_unit>1.0</m2_to_area_unit>\n"
        f"{pad}  <kgm2_to_inertia_unit>1.0</kgm2_to_inertia_unit>\n"
        f"{pad}</Units>"
    )


# ------------------------------------------------------------------ plane definition

def _section_xml(sec: Section, wing_airfoil: str | None, chord_dist: str,
                 span_dist: str, indent: int) -> str:
    left = sec.airfoil_left or sec.airfoil or wing_airfoil
    right = sec.airfoil_right or sec.airfoil or wing_airfoil
    if not left or not right:
        raise InternalError(f"section at y={sec.y:g} reached XML generation with no airfoil")
    pad = " " * indent
    rows = [
        _tag("y_position", f"{sec.y:.6g}", indent + 2),
        _tag("Chord", f"{sec.chord:.6g}", indent + 2),
        _tag("xOffset", f"{sec.offset:.6g}", indent + 2),
        _tag("Dihedral", f"{sec.dihedral:.6g}", indent + 2),
        _tag("Twist", f"{sec.twist:.6g}", indent + 2),
        _tag("x_number_of_panels", sec.chordwise, indent + 2),
        _tag("x_panel_distribution", chord_dist, indent + 2),
        _tag("y_number_of_panels", sec.spanwise, indent + 2),
        _tag("y_panel_distribution", span_dist, indent + 2),
        _tag("Left_Side_FoilName", left, indent + 2),
        _tag("Right_Side_FoilName", right, indent + 2),
    ]
    return f"{pad}<Section>\n" + "\n".join(rows) + f"\n{pad}</Section>"


#: Roll angle that stands a surface up vertically.
#:
#: `Type=FIN` alone does NOT orient a fin — flow5 builds the sections along y like any
#: other wing, so a fin written with Rx_angle 0 becomes a second HORIZONTAL tail. The
#: upstream API example is explicit about it: `setRxAngle(&fin, -90.0)`
#: (API_examples/PlaneRun1/PlaneRun1.cpp:316).
#:
#: Found by reconstructing a real aircraft: a phantom horizontal surface moved the
#: neutral point 35 % MAC aft, and made every sideslip result meaningless because
#: flow5 never saw a vertical surface at all.
FIN_ROLL_ANGLE = -90.0


def _wing_xml(surface: Surface, indent: int, *, has_fuselage: bool = False) -> str:
    w = surface.wing
    pad = " " * indent
    px, py, pz = surface.position_m
    sections = "\n".join(
        _section_xml(s, w.airfoil, w.panels.chord_distribution,
                     w.panels.span_distribution, indent + 4)
        for s in surface.sections
    )
    is_fin = w.role == "fin"
    rx = FIN_ROLL_ANGLE if is_fin else 0.0
    rows = [
        _tag("Name", w.name or w.role.title(), indent + 2),
        _tag("Type", _WING_TYPE[w.role], indent + 2),
        _tag("Position", f"{px:.6g}, {py:.6g}, {pz:.6g}", indent + 2),
        _tag("Rx_angle", f"{rx:.6g}", indent + 2),
        _tag("Ry_angle", f"{w.incidence:.6g}", indent + 2),
        _tag("symmetric", "true" if w.symmetric else "false", indent + 2),
    ]
    if is_fin and not has_fuselage:
        # a fin that is not attached to a fuselage has to close its own root, or the
        # root panels leak — the upstream example calls this out too
        rows.append(_tag("Closed_Inner_Side", "true", indent + 2))
    return (
        f"{pad}<wing>\n" + "\n".join(rows) + "\n"
        + f"{pad}  <Sections>\n{sections}\n{pad}  </Sections>\n"
        + f"{pad}</wing>"
    )


def plane_xml(design: Design, derived: Derived) -> str:
    """`xflplane` v1.0. The root version must be exactly "1.0"."""
    masses = ""
    if design.mass.components:
        from ..units import to_si_length, to_si_mass
        lu, mu = design.units.length, design.units.mass
        rows = "\n".join(
            "      <Point_Mass>\n"
            + _tag("Tag", c.tag, 8) + "\n"
            + _tag("Mass", f"{to_si_mass(c.mass, mu):.6g}", 8) + "\n"
            + _tag("coordinates",
                   ", ".join(f"{to_si_length(v, lu):.6g}" for v in c.at), 8) + "\n"
            + "      </Point_Mass>"
            for c in design.mass.components
        )
        masses = f"    <Inertia>\n{rows}\n    </Inertia>\n"

    has_fuselage = design.fuselage.type != "none"
    wings = "\n".join(_wing_xml(s, 4, has_fuselage=has_fuselage)
                      for s in derived.surfaces)
    return (
        f"{_HEAD}\n<!DOCTYPE flow5>\n<xflplane version=\"1.0\">\n"
        + _units_block(2) + "\n"
        + "  <Plane>\n"
        + _tag("Name", design.name, 4) + "\n"
        + _tag("Description", design.description, 4) + "\n"
        + masses
        + wings + "\n"
        + "  </Plane>\n</xflplane>\n"
    )


# ------------------------------------------------------------------------- analysis

@dataclass(slots=True)
class AnalysisSpec:
    """One flow5 polar request, in SI units."""

    name: str
    polar_type: str = "T1"
    method: str = "VLM2"
    speed: float | None = None
    alpha_deg: float | None = None
    viscous: bool = True
    on_the_fly: bool = False
    ncrit: float = 9.0
    ground_height: float | None = None
    mass: float | None = None
    cg: tuple[float, float, float] | None = None
    inertia: tuple[float, float, float, float] | None = None
    """(Ixx, Iyy, Izz, Ixz). Written with Use_plane_inertia=false so flow5 honours it."""
    thin_surfaces: bool = True

    def flow5_type(self) -> str:
        try:
            return POLAR_TYPES[self.polar_type.upper()]
        except KeyError:
            raise InternalError(
                f"unknown polar type {self.polar_type!r}; known: {sorted(POLAR_TYPES)}"
            ) from None


def polar_xml(spec: AnalysisSpec, plane_name: str, derived: Derived) -> str:
    """`xflPlanePolar` v1.0."""
    if spec.method.upper() not in VALID_METHODS:
        # flow5 silently falls back to VLM2 for anything it does not recognise
        raise InternalError(
            f"unknown analysis method {spec.method!r}; flow5 would silently use VLM2. "
            f"Known: {', '.join(VALID_METHODS)}"
        )

    mass = spec.mass if spec.mass is not None else derived.mass.total
    cg = spec.cg if spec.cg is not None else derived.mass.cg
    inertia = spec.inertia
    if inertia is None:
        m = derived.mass
        inertia = (m.ixx, m.iyy, m.izz, m.ixz)

    body = [
        _tag("Polar_Name", spec.name, 4),
        _tag("Plane_Name", plane_name, 4),
        _tag("Type", spec.flow5_type(), 4),
        _tag("Method", spec.method.upper(), 4),
        _tag("Thin_Surfaces", "true" if spec.thin_surfaces else "false", 4),
        "    <Reference_Dimensions>",
        # ADR-0005: never PLANFORM or PROJECTED — they yield zeros in script mode
        _tag("Reference_Dimensions", "CUSTOM", 6),
        _tag("Reference_Area", f"{derived.reference_area:.8g}", 6),
        _tag("Reference_Span_Length", f"{derived.reference_span:.8g}", 6),
        _tag("Reference_Chord_Length", f"{derived.reference_chord:.8g}", 6),
        _tag("Include_Other_Wing_Area", "false", 6),
        "    </Reference_Dimensions>",
        "    <Viscous_Analysis>",
        _tag("Is_Viscous_Analysis", "true" if spec.viscous else "false", 6),
        _tag("XFoil_OnTheFly", "true" if spec.on_the_fly else "false", 6),
        _tag("From_CL", "false", 6),
        _tag("NCrit", f"{spec.ncrit:g}", 6),
        "    </Viscous_Analysis>",
    ]
    if spec.ground_height is not None:
        body += [
            _tag("Ground_Effect", "true", 4),
            _tag("Ground_Height", f"{spec.ground_height:.6g}", 4),
        ]
    # ADR / section 4.4: with Use_plane_inertia=true flow5 discards these values and
    # derives its own, which gives Ixx = 0 for centreline masses and inf lateral modes.
    body.append(_tag("Use_plane_inertia", "false", 4))
    if spec.speed is not None:
        body.append(_tag("Fixed_Velocity", f"{spec.speed:.6g}", 4))
    if spec.alpha_deg is not None:
        body.append(_tag("Fixed_AOA", f"{spec.alpha_deg:.6g}", 4))
    body += [
        "    <Inertia>",
        _tag("Mass", f"{mass:.8g}", 6),
        _tag("CoG", ", ".join(f"{v:.6g}" for v in cg), 6),
        _tag("CoG_Ixx", f"{inertia[0]:.8g}", 6),
        _tag("CoG_Iyy", f"{inertia[1]:.8g}", 6),
        _tag("CoG_Izz", f"{inertia[2]:.8g}", 6),
        _tag("CoG_Ixz", f"{inertia[3]:.8g}", 6),
        "    </Inertia>",
    ]
    return (
        f"{_HEAD}\n<!DOCTYPE flow5>\n<xflPlanePolar version=\"1.0\">\n"
        + _units_block(2) + "\n  <Polar>\n"
        + "\n".join(body)
        + "\n  </Polar>\n</xflPlanePolar>\n"
    )


# --------------------------------------------------------------------------- scripts

@dataclass(slots=True)
class Dirs:
    output: Path
    foils: Path | None = None
    planes: Path | None = None
    analyses: Path | None = None
    xfoil_polars: Path | None = None

    def xml(self, indent: int) -> str:
        pad = " " * indent
        rows = [_tag("output_dir", self.output, indent + 2)]
        for key, val in (
            ("foil_files_dir", self.foils),
            ("plane_definition_xml_dir", self.planes),
            ("plane_analysis_xml_dir", self.analyses),
            ("xfoil_polars_dir", self.xfoil_polars),
        ):
            if val is not None:
                rows.append(_tag(key, val, indent + 2))
        return f"{pad}<Directories>\n" + "\n".join(rows) + f"\n{pad}</Directories>"


def _metadata(project: str, dirs: Dirs, threads: int, csv: bool) -> str:
    """`make_project_file` + `project_file_name` are mandatory here: without them
    flow5 writes into a timestamped directory whose name we would have to discover."""
    rows = [
        _tag("make_project_file", "true", 4),
        _tag("project_file_name", project, 4),
    ]
    if csv:
        rows.append(_tag("polar_text_output_format", "csv", 4))
    rows += [
        "    <MultiThreading>",
        _tag("Allow_Multithreading", "true", 6),
        _tag("max_threads", max(1, threads), 6),
        "    </MultiThreading>",
        dirs.xml(4),
    ]
    return "  <Metadata>\n" + "\n".join(rows) + "\n  </Metadata>"


def foil_script(project: str, dirs: Dirs, foil_files: list[str], reynolds: list[float],
                alpha: tuple[float, float, float], ncrit: float = 9.0,
                panels: int = 160, max_iter: int = 120, threads: int = 8) -> str:
    """Pass 1: 2D polars only. Never contains a plane analysis — see ADR-0009.

    Output is deliberately NOT csv, because the default text format is genuine XFoil
    polar format and can be re-imported through `xfoil_polars_dir` for pass 2.

    The alpha sweep goes in `OpPoint_Range`. flow5 parses `Batch_Range/Alpha` and then
    ignores it, producing empty polars and reporting success.
    """
    if not reynolds:
        raise InternalError("foil_script called with no Reynolds numbers")
    files = "\n".join(_tag("Foil_File_Name", f, 6) for f in foil_files)
    re_list = ", ".join(f"{r:.0f}" for r in reynolds)
    return (
        f"{_HEAD}\n<!DOCTYPE xflscript>\n<xflscript version=\"1.0\">\n"
        + _metadata(project, dirs, threads, csv=False) + "\n"
        + "  <foil_analysis>\n"
        + f"    <Foil_Files>\n{files}\n    </Foil_Files>\n"
        + "    <Batch_Analysis_Data>\n"
        + _tag("Polar_Type", "FIXEDSPEEDPOLAR", 6) + "\n"
        + f"      <Batch_Range>\n{_tag('Reynolds', re_list, 8)}\n"
        + f"{_tag('NCrit', ', '.join(f'{ncrit:g}' for _ in reynolds), 8)}\n"
        + "      </Batch_Range>\n"
        + "    </Batch_Analysis_Data>\n"
        + "    <OpPoint_Range>\n"
        + _tag("Alpha", f"{alpha[0]:g}, {alpha[1]:g}, {alpha[2]:g}", 6) + "\n"
        + _tag("Spec_Alpha", "true", 6) + "\n"
        + _tag("From_Zero", "true", 6) + "\n"
        + "    </OpPoint_Range>\n"
        + "    <Options>\n"
        + _tag("Max_XFoil_Iterations", max_iter, 6) + "\n"
        + _tag("Repanel_Foils", "true", 6) + "\n"
        + _tag("Foil_Panels", panels, 6) + "\n"
        + "    </Options>\n"
        + "    <Output>\n"
        + _tag("make_polars_text_file", "true", 6) + "\n"
        + "    </Output>\n"
        + "  </foil_analysis>\n</xflscript>\n"
    )


@dataclass(slots=True)
class PlaneOutputs:
    polars: bool = True
    oppoints: bool = True
    oppoint_text: bool = True
    cp: bool = False
    stl: bool = False
    derivatives: bool = False
    """Only meaningful for a T7 polar. On a T1 flow5 returns eigenvalues of ~1e51."""


@dataclass(slots=True)
class PlaneRanges:
    t12: tuple[float, float, float] | None = None
    t3: tuple[float, float, float] | None = None
    t5: tuple[float, float, float] | None = None
    t7: tuple[float, float, float] | None = None
    extra: dict[str, tuple[float, float, float]] = field(default_factory=dict)

    def xml(self, indent: int) -> str:
        pad = " " * indent
        rows = []
        for key, val in (("T12_Range", self.t12), ("T3_Range", self.t3),
                         ("T5_Range", self.t5), ("T7_Range", self.t7),
                         *self.extra.items()):
            if val is not None:
                # flat text, not a container: children abort the whole script
                rows.append(_tag(key, f"{val[0]:g}, {val[1]:g}, {val[2]:g}", indent + 2))
        if not rows:
            raise InternalError("plane_script called with no analysis range")
        return f"{pad}<Plane_Analysis_Data>\n" + "\n".join(rows) + f"\n{pad}</Plane_Analysis_Data>"


def plane_script(project: str, dirs: Dirs, foil_files: list[str], ranges: PlaneRanges,
                 outputs: PlaneOutputs | None = None, threads: int = 8) -> str:
    """Pass 2: a plane analysis only. Never contains a foil analysis — see ADR-0009."""
    out = outputs or PlaneOutputs()
    files = "\n".join(_tag("Foil_File_Name", f, 6) for f in foil_files)
    flags = [
        _tag("make_polars_text_file", str(out.polars).lower(), 6),
        _tag("make_oppoints", str(out.oppoints).lower(), 6),
        _tag("make_oppoints_text_file", str(out.oppoint_text).lower(), 6),
        _tag("export_oppoint_Cp", str(out.cp).lower(), 6),
        _tag("export_stl_mesh", str(out.stl).lower(), 6),
        _tag("Compute_derivatives", str(out.derivatives).lower(), 6),
    ]
    return (
        f"{_HEAD}\n<!DOCTYPE xflscript>\n<xflscript version=\"1.0\">\n"
        + _metadata(project, dirs, threads, csv=True) + "\n"
        + "  <Plane_analysis>\n"
        + "    <Plane_Analysis_Output>\n" + "\n".join(flags) + "\n    </Plane_Analysis_Output>\n"
        + f"    <Foil_Dat_Files>\n{files}\n    </Foil_Dat_Files>\n"
        + "    <Plane_Definition_Files>\n"
        + _tag("Process_All_Files", "true", 6) + "\n"
        + "    </Plane_Definition_Files>\n"
        + "    <Plane_Analysis_Files>\n"
        + _tag("Process_All_Files", "true", 6) + "\n"
        + "    </Plane_Analysis_Files>\n"
        + ranges.xml(4) + "\n"
        + "  </Plane_analysis>\n</xflscript>\n"
    )

"""MCP server — the reason this project is general rather than personal.

Claude Desktop has no shell and no filesystem, so MCP is the only way flow5ctl reaches
the people who are not in a terminal, which is most flow5 users. This module is a thin
adapter over the same use cases the CLI calls (ADR-0002); it contains no domain logic
and no knowledge of flow5.

Three things it does that the CLI does not have to:

* **It owns a workspace.** Designs are addressed by name, never by path, and a name
  that is not a plain name is rejected rather than resolved. The server never reads or
  writes outside `FLOW5CTL_WORKSPACE` (default `~/flow5ctl`).
* **It runs blocking work off the event loop.** A first viscous analysis takes about
  twelve seconds and a sweep can take minutes; those go to a worker thread so the
  server stays responsive and can report progress.
* **It returns pictures.** For a reader who cannot open a file, a curve says in one
  glance what twenty numbers do not.
"""
from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
from typing import Annotated, Any, Literal

import anyio
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ResourceError, ToolError
from mcp.server.mcpserver.utilities.types import Image
from pydantic import Field

from . import __version__
from .errors import Flow5ctlError
from .flow5 import probe as probe_mod
from .model import presets
from .project.store import list_designs, resolve_in_workspace, workspace_root
from .usecases import analyze as analyze_uc
from .usecases import define as define_uc
from .usecases import edit as edit_uc
from .usecases import gui as gui_uc
from .usecases import plot as plot_uc
from .usecases import sweep as sweep_uc
from .usecases import trim as trim_uc

INSTRUCTIONS = """\
flow5ctl designs low-Reynolds-number aircraft — human-powered aircraft, RC gliders,
small UAVs — by driving the flow5 potential-flow solver.

Start with `doctor`. Then `create_design` (or `get_design` for an existing one) and
`analyze`. Designs live in a workspace and are addressed by name.

Read `flow5://guide/design` before drawing conclusions from a result. It is short, and
it is the difference between a number and an answer: this solver has no separation
model, so it returns confident values past stall; it needs a T7 polar for stability
because a T1 polar answers with eigenvalues of order 1e51; and its absolute drag is
optimistic because interference and surface finish are not modelled.

Every tool returns `warnings` and `notes`. They are not decoration — they are where
the tool tells you which of its numbers you may not trust. Pass them on to the user
rather than reporting the summary alone.

No aircraft that carries a person should be committed to build on the basis of a
potential-flow analysis alone. Say so when it applies.
"""

server = MCPServer(
    name="flow5ctl",
    title="flow5ctl — aircraft design with flow5",
    version=__version__,
    instructions=INSTRUCTIONS,
    website_url="https://github.com/97kuek/flow5ctl",
)

DesignName = Annotated[str, Field(description="the design's name in the workspace")]
PolarType = Literal["T1", "T2", "T3", "T5", "T7"]


async def _run(fn, *args, **kwargs):
    """Run blocking work in a thread so the event loop stays free."""
    def call():
        return fn(*args, **kwargs)
    try:
        return await anyio.to_thread.run_sync(call)
    except Flow5ctlError as exc:
        raise ToolError(str(exc)) from exc


async def _progress(ctx: Context | None, done: float, total: float, message: str) -> None:
    """Report progress when the client asked for it, and never fail because it did not.

    A sweep can take minutes. Progress is worth reporting, but a client that did not
    send a progress token must not turn a working analysis into an error — and the
    logging capability that would otherwise carry status messages was deprecated in
    the protocol (SEP-2577), so warnings live in the response payload instead.
    """
    if ctx is None:
        return
    # progress is best-effort by definition
    with contextlib.suppress(Exception):
        await ctx.report_progress(done, total, message)


def _project(name: str):
    try:
        return resolve_in_workspace(name)
    except Flow5ctlError as exc:
        raise ToolError(str(exc)) from exc


def _trim(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop the raw table from a response. The agent gets the summary; the numbers
    live in a file it can read if it genuinely needs one (ADR-0004)."""
    return {k: v for k, v in payload.items() if not k.startswith("_")}


# ------------------------------------------------------------------------- tools

@server.tool(
    description="Check the environment: where flow5 is, its version, whether that "
                "version is verified, and where designs are kept. Call this first.",
)
async def doctor() -> dict[str, Any]:
    def check() -> dict[str, Any]:
        ws = workspace_root()
        try:
            install = probe_mod.probe()
        except Flow5ctlError as exc:
            return {
                "flow5ctl_version": __version__,
                "flow5_found": False,
                "problem": str(exc),
                "workspace": str(ws),
            }
        writable = True
        try:
            ws.mkdir(parents=True, exist_ok=True)
            (ws / ".write-test").write_text("", encoding="utf-8")
            (ws / ".write-test").unlink()
        except OSError:
            writable = False
        return {
            "flow5ctl_version": __version__,
            "flow5_found": True,
            "flow5_path": str(install.path),
            "flow5_version": install.version,
            "verified": install.verified,
            "warnings": [install.note] if install.note else [],
            "workspace": str(ws),
            "workspace_writable": writable,
            "presets": presets.available(),
            "designs": [n for n, _ in list_designs()],
            "notes": [
                "flow5ctl is verified on macOS with flow5 7.57 only. On another "
                "platform, results are unconfirmed.",
                "Read flow5://guide/design before interpreting any result.",
            ],
        }
    return await _run(check)


@server.tool(
    description="List the designs in the workspace, with each one's span, mass, "
                "preset and the analyses already stored against it.",
)
async def list_workspace() -> dict[str, Any]:
    def run() -> dict[str, Any]:
        rows = []
        for name, path in list_designs():
            try:
                d = define_uc.describe(resolve_in_workspace(name))
                g = d["geometry"]
                rows.append({"name": name, "preset": d["preset"],
                             "description": d["description"],
                             "span": g["span"], "mass": g["total_mass"],
                             "polars": d["polars"]})
            except Flow5ctlError:
                rows.append({"name": name, "path": str(path), "error": "unreadable"})
        return {"workspace": str(workspace_root()), "designs": rows}
    return await _run(run)


@server.tool(
    description="Create a design. `design` is the design.yaml content as an object — "
                "see flow5://schema/design for the fields, and flow5://presets/{name} "
                "for what a preset fills in. Returns the derived geometry and any "
                "warnings about it.",
)
async def create_design(
    name: DesignName,
    design: Annotated[dict[str, Any], Field(description="design.yaml content")],
    preset: Annotated[str, Field(description="hpa, rc-glider, uav or custom")] = "custom",
    overwrite: bool = False,
) -> dict[str, Any]:
    from .project.store import safe_name
    def run() -> dict[str, Any]:
        raw = {**design, "preset": design.get("preset", preset)}
        return define_uc.create(safe_name(name), raw, exist_ok=overwrite)
    return await _run(run)


@server.tool(
    description="Get a design, everything derivable from it (area, span, MAC, aspect "
                "ratio, CG, inertia, Reynolds number, tail volumes), and warnings.",
)
async def get_design(name: DesignName) -> dict[str, Any]:
    return await _run(lambda: define_uc.describe(_project(name)))


@server.tool(
    description="Change part of a design. `patch` is merged into it, so you only send "
                "what changes — restating the whole aircraft risks losing a field.",
)
async def update_design(
    name: DesignName,
    patch: Annotated[dict[str, Any], Field(description="partial design, deep-merged")],
) -> dict[str, Any]:
    return await _run(lambda: define_uc.update(_project(name), patch))


@server.tool(
    description="Add an airfoil. `source` is `naca:2412`, `url:https://...`, or "
                "`file:<path relative to the design>`. Coordinates are validated and "
                "stored; polars are computed later, on demand.",
)
async def add_airfoil(
    name: DesignName,
    airfoil: Annotated[str, Field(description="the name sections will refer to")],
    source: Annotated[str, Field(description="naca:NNNN | url:... | file:...")],
    reynolds: Annotated[list[float] | None,
                        Field(description="2D polar Reynolds numbers; omit to derive "
                                          "them from the flight envelope")] = None,
    ncrit: float | None = None,
    replace: bool = False,
) -> dict[str, Any]:
    return await _run(lambda: edit_uc.add_airfoil(
        _project(name), airfoil, source, reynolds=reynolds, ncrit=ncrit,
        replace=replace))


@server.tool(
    description="Rewrite planform shorthand as explicit sections, so individual "
                "stations can be hand-tuned. The geometry is unchanged.",
)
async def expand_planform(name: DesignName) -> dict[str, Any]:
    return await _run(lambda: edit_uc.expand(_project(name)))


@server.tool(
    description="Run an analysis. T1 fixed speed, T2 fixed lift, T3 glide, T5 "
                "sideslip, T7 stability. Returns a summary — lift-curve slope, best "
                "L/D and where it occurs, minimum sink, neutral point, static margin, "
                "trim angle, and for T7 the dynamic modes — never the raw table. "
                "2D airfoil polars are computed automatically the first time (about "
                "twelve seconds) and cached afterwards.",
)
async def analyze(
    name: DesignName,
    polar: Annotated[str, Field(description="a name for this analysis")] = "cruise",
    type: PolarType = "T1",
    speed: Annotated[float | None, Field(description="m/s; required for T1/T5/T7 "
                                                     "unless the design has a cruise "
                                                     "speed")] = None,
    alpha: Annotated[list[float] | None,
                     Field(description="[min, max, step] in degrees. On a T5 polar "
                                       "this is the SIDESLIP range, not incidence — "
                                       "alpha is held at 0 and beta is swept.")] = None,
    viscous: bool | None = None,
    ground_effect: bool | None = None,
    ground_height: Annotated[float | None,
                             Field(description="height of the CG above the surface, m")] = None,
    mass: float | None = None,
    cg_x: Annotated[float | None, Field(description="override the CG x position, m")] = None,
    export_stl: bool = False,
) -> dict[str, Any]:
    project = _project(name)
    req = analyze_uc.Request(
        name=polar, polar_type=type, speed=speed,
        alpha=tuple(alpha) if alpha else None, viscous=viscous,
        ground_effect=ground_effect, ground_height=ground_height,
        mass=mass, cg_x=cg_x, stability=(type == "T7"), export_stl=export_stl,
    )
    out = await _run(analyze_uc.analyze, project, req)
    return _trim(out)


@server.tool(
    description="Solve for a condition rather than sweeping towards it. Targets: "
                "`level` (the angle of attack that holds level flight at a speed), "
                "`cl` (the angle for a given CL), `speed` (the speed at a given "
                "angle), `static_margin` (the CG that achieves a target margin — a "
                "closed-form solve, because the neutral point does not move with the "
                "CG), `pitch` (the elevator incidence giving Cm = 0).",
)
async def trim(
    name: DesignName,
    target: Literal["level", "cl", "speed", "static_margin", "pitch"],
    value: Annotated[float | None,
                     Field(description="the target value: a CL, or a static margin as "
                                       "a fraction of MAC")] = None,
    speed: float | None = None,
    alpha: Annotated[float | None,
                     Field(description="a single angle, for target speed or pitch")] = None,
    alpha_range: Annotated[list[float] | None,
                           Field(description="[min, max, step] for the search sweep")] = None,
    mass: float | None = None,
) -> dict[str, Any]:
    project = _project(name)
    req = trim_uc.TrimRequest(
        target=target, value=value, speed=speed, alpha=alpha,
        alpha_range=tuple(alpha_range) if alpha_range else None, mass=mass,
    )
    return await _run(trim_uc.trim, project, req)


@server.tool(
    description="Vary one parameter and compare. `parameter` is a dotted path into the "
                "design (wing.planform.taper) or one of cg_x, speed, mass, "
                "ground_height. Returns a table, the best row by the design's "
                "objective, and — importantly — a warning when a requested metric does "
                "not respond to the parameter you varied. Best L/D does not respond to "
                "CG at all; compare CG positions on ld_at_trim.",
)
async def sweep(
    name: DesignName,
    parameter: str,
    values: Annotated[list[float], Field(description="at least two values")],
    metrics: Annotated[list[str] | None,
                       Field(description="from: best_LD, best_LD_alpha, min_sink, "
                                         "static_margin, trim_alpha, cl_at_trim, "
                                         "ld_at_trim, cl_alpha, neutral_point_x")] = None,
    type: PolarType = "T1",
    speed: float | None = None,
    alpha: Annotated[list[float] | None, Field(description="[min, max, step]")] = None,
    study: Annotated[str | None,
                     Field(description="a name for the study, so it can be re-run")] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    project = _project(name)
    if len(values) < 2:
        raise ToolError("a sweep needs at least two values")
    await _progress(ctx, 0, len(values), f"starting the {parameter} sweep")
    req = sweep_uc.SweepRequest(
        parameter=parameter, values=[float(v) for v in values],
        name=study or parameter.replace(".", "-"),
        analysis=analyze_uc.Request(polar_type=type, speed=speed,
                                    alpha=tuple(alpha) if alpha else None),
        metrics=tuple(metrics) if metrics else sweep_uc.DEFAULT_METRICS,
    )
    out = await _run(sweep_uc.sweep, project, req)
    await _progress(ctx, len(values), len(values), "sweep complete")
    return out


@server.tool(
    description="Draw a chart of a stored analysis, as a PNG. Kinds: `polar` (CL "
                "against CD, with best L/D marked), `cl_alpha`, `cm_alpha` (with the "
                "trim point), `drag_breakdown` (induced and viscous, stacked), "
                "`spanwise_lift` (local Cl along the span against the elliptic "
                "distribution). Pass several polars to compare them on one chart.",
)
async def plot(
    name: DesignName,
    kind: Literal["polar", "cl_alpha", "cm_alpha", "drag_breakdown",
                  "spanwise_lift"] = "polar",
    polars: Annotated[list[str] | None,
                      Field(description="which analyses to draw; the most recent by "
                                        "default")] = None,
    theme: Literal["light", "dark"] = "light",
) -> list[Any]:
    project = _project(name)
    payload, data = await _run(plot_uc.plot, project, kind=kind, polars=polars,
                               theme=theme)
    return [
        Image(data=data, format="png").to_image_content(),
        json.dumps(payload, indent=2),
    ]


@server.tool(
    description="Export a build artifact: `fl5` (a flow5 project the GUI can open), "
                "`stl` (the mesh), `csv` (the polar), `xml` (the generated plane).",
)
async def export(
    name: DesignName,
    format: Literal["fl5", "stl", "csv", "xml"] = "fl5",
    polar: Annotated[str | None, Field(description="which analysis; the most recent "
                                                   "by default")] = None,
) -> dict[str, Any]:
    return await _run(lambda: edit_uc.export(_project(name), format, polar=polar))


@server.tool(
    description="Open the design in the flow5 GUI, so a human can look at the "
                "aircraft themselves. Only works when flow5ctl is running on the "
                "user's own machine.",
)
async def open_in_flow5(
    name: DesignName,
    polar: str | None = None,
    launch: Annotated[bool, Field(description="set false to export and return the "
                                             "command without launching")] = True,
) -> dict[str, Any]:
    return await _run(lambda: gui_uc.open_in_flow5(_project(name), polar=polar,
                                                   launch=launch))


# --------------------------------------------------------------------- resources

@server.resource("flow5://status", mime_type="application/json",
                 description="The same content as `doctor`, readable without a tool call.")
async def status_resource() -> str:
    return json.dumps(await doctor(), indent=2)


@server.resource("flow5://guide/design", mime_type="text/markdown",
                 description="Aerodynamic guardrails. Read this before drawing "
                             "conclusions from any result.")
def design_guide() -> str:
    path = Path(__file__).parent.parent.parent / "docs" / "DESIGN-GUIDE.md"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return (
        "# Design guide\n\n"
        "The full guide ships with the source tree at docs/DESIGN-GUIDE.md and is "
        "not bundled in this installation. The essentials:\n\n"
        "- flow5 is a potential-flow solver with 2D viscous data layered on. It has "
        "no separation model, so results at or past stall are fiction. Keep alpha "
        "sweeps inside roughly ±10°.\n"
        "- Stability modes require a T7 polar. A T1 polar returns eigenvalues of "
        "order 1e51 rather than refusing.\n"
        "- Absolute drag is optimistic: interference, surface finish, rigging and a "
        "pilot's body are not modelled. Treat absolute L/D as an upper bound; "
        "comparisons between designs run identically are far more reliable.\n"
        "- Viscous analysis is not optional at these Reynolds numbers. An inviscid "
        "run omitted 93 % of the drag at Re 2e5.\n"
        "- Ground effect is a design driver for human-powered aircraft, worth 15-20 % "
        "in L/D a few metres above water.\n"
        "- No aircraft carrying a person should be committed to build on a "
        "potential-flow analysis alone.\n"
    )


@server.resource("flow5://presets/{name}", mime_type="application/json",
                 description="A preset's defaults, analysis policy and sanity thresholds.")
def preset_resource(name: str) -> str:
    try:
        p = presets.load(name)
    except Flow5ctlError as exc:
        # A listing is more useful to a client than a failure, and the protocol's
        # wrapper would otherwise reduce the message to "error creating resource".
        return json.dumps({"error": str(exc), "available": presets.available()}, indent=2)
    return json.dumps({
        "name": p.name, "label": p.label, "description": p.description,
        "defaults": p.defaults, "analysis": p.analysis, "limits": p.limits,
        "thresholds": p.thresholds,
    }, indent=2)


@server.resource("flow5://design/{name}", mime_type="text/yaml",
                 description="A design's design.yaml, as written.")
def design_resource(name: str) -> str:
    try:
        return resolve_in_workspace(name).design_path.read_text(encoding="utf-8")
    except Flow5ctlError as exc:
        raise ResourceError(str(exc)) from exc


@server.resource("flow5://results/{name}/{polar}", mime_type="application/json",
                 description="The full operating-point table for one analysis — every "
                             "column flow5 produced. Read this only when the summary "
                             "genuinely cannot answer the question.")
def results_resource(name: str, polar: str) -> str:
    try:
        project = resolve_in_workspace(name)
    except Flow5ctlError as exc:
        raise ResourceError(str(exc)) from exc
    path = project.results / f"{polar}.json"
    if not path.is_file():
        raise ResourceError(
            f"no stored result called {polar!r} for {name!r}. Available: "
            f"{', '.join(plot_uc.available(project)) or 'none'}"
        )
    return path.read_text(encoding="utf-8")


@server.resource("flow5://schema/design", mime_type="application/json",
                 description="JSON Schema for design.yaml — the exact fields "
                             "create_design and update_design accept.")
def design_schema() -> str:
    from .model.design import Design
    return json.dumps(Design.model_json_schema(by_alias=True), indent=2)


# ----------------------------------------------------------------------- prompts

@server.prompt(description="Design a new aircraft from scratch, in the right order.")
def new_aircraft(
    kind: Annotated[str, Field(description="human-powered aircraft, RC glider, or UAV")],
    goal: Annotated[str, Field(description="what it has to do")] = "",
) -> str:
    return f"""\
Design a {kind}{f' for: {goal}' if goal else ''} with flow5ctl.

Work in this order, and stop at each step to show me what you found:

1. `doctor`, then read `flow5://guide/design`.
2. Choose a preset and read `flow5://presets/{{name}}` so you know what it will
   default. State the requirements you are designing to — cruise speed, mass,
   static margin band — before choosing any geometry.
3. `create_design` with a first planform. Read the derived geometry back: aspect
   ratio, wing loading, Reynolds number at the MAC, tail volumes. Tell me if any of
   them look wrong for this class before running the solver.
4. `analyze` a T1 polar at cruise. Report best L/D and where it occurs, the static
   margin, and every warning the tool returned.
5. `trim` for the CG that gives a static margin inside the preset's band.
6. `plot` the drag polar and the spanwise lift distribution.

Mass components must have spanwise positions for the wing structure. Mass that all
sits on the centreline gives zero roll inertia, and every lateral result becomes
meaningless without flow5 complaining.
"""


@server.prompt(description="Diagnose where the drag is going and test a change.")
def improve_glide(name: str) -> str:
    return f"""\
Improve the glide performance of {name}.

1. `get_design` and `analyze` a T2 (fixed-lift) polar — that is the one that gives a
   glide polar and a minimum sink rate. Start the alpha sweep above the zero-lift
   angle, or the required speed diverges.
2. `plot` the drag breakdown. Say which of induced and viscous dominates at the
   condition that matters, because that decides what is worth changing.
3. `plot` the spanwise lift distribution against elliptic.
4. Propose one change, `sweep` it, and show the table.

When the sweep picks an optimum, say what the optimum costs that this solver cannot
see. A washout sweep will always favour zero washout; what washout buys — tip-stall
margin, roll damping, an unloaded tip — is invisible to a solver with no separation
model.
"""


@server.prompt(description="Assess longitudinal and lateral stability honestly.")
def check_stability(name: str) -> str:
    return f"""\
Assess the stability of {name}.

1. `analyze` a T1 polar and report the neutral point and static margin against the
   preset's band.
2. `trim` for the CG that puts the static margin in the middle of that band, and say
   how far it is from the current CG.
3. `analyze` a T7 stability polar. Report the longitudinal eigenvalues, the phugoid
   frequency and damping, and whether every mode is damped.
4. `plot` the pitching moment curve.

Two cautions to apply rather than mention:

- Do not report Dutch-roll or short-period figures from flow5 7.57. They come back as
  0.0 or as implausible values. The eigenvalues are correct; the summary columns for
  those two modes are not.
- If the tool warns that the static margin is ambiguous — the two definitions
  disagreeing in sign — do not pick one. That happens near neutral stability, and the
  answer is a CG sweep, not a choice.
"""


@server.prompt(description="Compare two or more designs on the same metrics.")
def compare_designs(names: Annotated[str, Field(description="comma-separated names")]) -> str:
    return f"""\
Compare these designs: {names}.

Run the same analysis on each — same polar type, same speed, same alpha range, same
viscous method — and put the results in one table. A comparison between designs run
identically is the most reliable thing this solver produces; an absolute figure is
the least.

Then `plot` their polars on one chart.

State explicitly what was held constant and what differs. If the designs have
different wing areas, say which reference area each coefficient is normalised by,
because otherwise the CL columns are not comparable.
"""


def main(argv: list[str] | None = None) -> int:
    """Entry point for `flow5ctl mcp`."""
    if os.environ.get("FLOW5CTL_MCP_SELFTEST"):
        # A cheap import-and-registration check, so packaging problems surface without
        # needing an MCP client.
        print(f"flow5ctl {__version__} MCP server ready", flush=True)
        return 0
    server.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

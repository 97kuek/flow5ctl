"""Command line interface.

Phase 1 exposes only what is needed to drive and verify the core. Phase 2 fleshes
this out and adds `--json` to every command; the MCP server (Phase 3) is a second
adapter over the same use cases, never a reimplementation. See ADR-0002.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .errors import Flow5ctlError
from .flow5 import probe as probe_mod
from .model import presets
from .project.store import Project, list_designs, workspace_root
from .usecases import analyze as analyze_uc
from .usecases import define as define_uc
from .usecases import edit as edit_uc
from .usecases import gui as gui_uc
from .usecases import sweep as sweep_uc
from .usecases import trim as trim_uc


def _emit(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return
    _pretty(payload)


def _pretty(p: dict[str, Any]) -> None:
    def line(label: str, value: Any) -> None:
        if value is not None:
            print(f"  {label:<24}{value}")

    if "geometry" in p and "summary" not in p:
        g = p["geometry"]
        print(f"\n{p['name']}   [{p['preset']}]  {p.get('description','')}")
        print(f"  {p['path']}")
        print("\nGeometry")
        line("area", f"{g['planform_area']} m²  (projected {g['projected_area']})")
        line("span", f"{g['span']} m  (projected {g['projected_span']})")
        line("MAC", f"{g['mac']} m at y = {g['mac_y']} m")
        line("aspect ratio", g["aspect_ratio"])
        line("taper", g["taper_ratio"])
        line("mass", f"{g['total_mass']} kg   CG {g['cg']}")
        if g.get("cg_percent_mac") is not None:
            line("CG", f"{g['cg_percent_mac'] * 100:.1f} % MAC")
        line("wing loading", f"{g['wing_loading']} kg/m²")
        line("Re at MAC", f"{g['reynolds_at_mac']:,}" if g.get("reynolds_at_mac") else None)
        line("panels", g["panel_count"])
        line("tail volume h/v", f"{g.get('tail_volume_h')} / {g.get('tail_volume_v')}")
    if "summary" in p:
        s = p["summary"]
        c = p["conditions"]
        print(f"\n{p['design']} / {p['polar']}   {p['polar_type']}  {c['method']}")
        visc = c["viscous_method"] or "inviscid"
        print(f"  {c['speed'] or '—'} m/s, α {c['alpha_range']}, {visc}"
              + (f", ground {c['ground_height']} m" if c.get("ground_height") else ""))
        print(f"  {p['points']} points, {p['panels']} panels, {p['runtime_s']} s, "
              f"flow5 {p['flow5_version']}")
        print("\nResults")
        line("CL_alpha", f"{s['cl_alpha_per_deg']} /deg" if s.get("cl_alpha_per_deg") else None)
        line("alpha at CL=0", s.get("alpha_zero_lift"))
        if s.get("best_LD"):
            b = s["best_LD"]
            line("best L/D", f"{b['value']} at α {b['alpha']}° (CL {b['cl']})")
        if s.get("min_sink"):
            m = s["min_sink"]
            line("min sink", f"{m['value']} m/s at α {m['alpha']}°"
                             + (f", {m['speed']} m/s" if m.get("speed") else ""))
        line("dCm/dCL", s.get("dcm_dcl"))
        line("neutral point x", s.get("neutral_point_x"))
        if s.get("static_margin") is not None:
            line("static margin", f"{s['static_margin'] * 100:.2f} % MAC")
        line("trim alpha", s.get("trim_alpha"))
        for key, label in (("longitudinal_modes", "Longitudinal"), ("lateral_modes", "Lateral")):
            if s.get(key):
                print(f"\n{label} modes")
                for m in s[key]:
                    ev = m["eigenvalue"]
                    mark = "stable" if m["stable"] else "UNSTABLE"
                    period = f"T={m['period_s']:.1f}s  " if m.get("period_s") else ""
                    print(f"    {ev[0]:>12.5g} {ev[1]:+.5g}i   f={m['frequency_hz']:.4f} Hz  "
                          f"{period}ζ={m['damping_ratio']}  {mark}")
        if p.get("data"):
            print(f"\n  full data: {p['data']}")
    if "solved" in p:
        print(f"\n{p['design']}   trim: {p['target']}"
              + (f" = {p['requested']}" if p.get("requested") is not None else ""))
        c = p["conditions"]
        print(f"  {c['speed'] or '—'} m/s, {c['mass']} kg, α {c['alpha_range']}")
        print(f"  {p['solver_runs']} solver run(s), {p['runtime_s']} s")
        print("\nSolved")
        for k, v in p["solved"].items():
            line(k, v)
        print(f"\n  {p['explanation']}")
        if p.get("history"):
            print("\n  iterations:")
            for h in p["history"]:
                print(f"    incidence {h['incidence']:+7.3f}°   Cm {h['cm']:+.6f}")
    if "rows" in p and "parameter" in p:
        print(f"\n{p['design']}   study: {p['study']}")
        print(f"  varying {p['parameter']} ({p['parameter_kind']}) over "
              f"{len(p['values'])} values")
        print(f"  {p['solver_runs']} solver run(s), {p['runtime_s']} s\n")
        cols = [p["parameter"], *p["metrics"]]
        widths = [max(len(c), 11) for c in cols]
        print("  " + "  ".join(c.rjust(w) for c, w in zip(cols, widths, strict=True)))
        print("  " + "  ".join("-" * w for w in widths))
        for row in p["rows"]:
            cells = []
            for c, w in zip(cols, widths, strict=True):
                v = row.get(c)
                cells.append(("—" if v is None else f"{v:.5g}").rjust(w))
            marker = " ←best" if p.get("best") is not None and row is p["best"] else ""
            print("  " + "  ".join(cells) + marker)
        if p.get("best"):
            print(f"\n  best by {p['best_by']}: {p['parameter']} = "
                  f"{p['best'][p['parameter']]:.5g}")
        for f in p.get("failed", []):
            print(f"\n  ✗ {p['parameter']} = {f['value']:.5g} failed: "
                  f"{f['error'].splitlines()[0]}")
    if p.get("applied"):
        print(f"\nApplied to {p.get('name', 'the design')}")
        for a in p["applied"]:
            print(f"  · {a}")
    if p.get("expanded"):
        print("\nExpanded")
        for e in p["expanded"]:
            print(f"  · {e}")
    if p.get("airfoil"):
        a = p["airfoil"]
        print(f"\nAirfoil {a['name']}")
        line("source", a["requested_source"])
        line("stored at", a["stored_at"])
        line("points", a["points"])
        line("max thickness", f"{a['max_thickness_fraction'] * 100:.1f} % chord")
    if p.get("airfoils") is not None and "geometry" not in p:
        print(f"\n{p['design']} airfoils")
        for a in p["airfoils"]:
            used = ", ".join(a["used_by"]) or "unused"
            re_ = "auto" if not a["reynolds"] else ", ".join(f"{r:,.0f}" for r in a["reynolds"])
            print(f"  {a['name']:<16} {a['source']:<34} Re {re_}   [{used}]")
    if p.get("format"):
        print(f"\nExported {p['format']} from analysis {p['from_analysis']}")
        print(f"  {p['path']}")
        if p.get("launched"):
            print(f"  opened in flow5 {p['flow5_version']}")
    for w in p.get("warnings", []):
        print(f"\n  ⚠ {w}")
    for n in p.get("notes", []):
        print(f"  · {n}")
    if p.get("defaults_applied"):
        print("\nDefaults applied")
        for d in p["defaults_applied"]:
            print(f"  · {d}")
    print()


# ------------------------------------------------------------------------ commands

def cmd_doctor(args: argparse.Namespace) -> int:
    try:
        install = probe_mod.probe(args.flow5)
    except Flow5ctlError as exc:
        print(f"flow5: NOT FOUND\n\n{exc}")
        return 1
    ws = workspace_root()
    payload = {
        "flow5ctl_version": __version__,
        "flow5_path": str(install.path),
        "flow5_version": install.version,
        "verified": install.verified,
        "note": install.note,
        "workspace": str(ws),
        "workspace_writable": _writable(ws),
        "presets": presets.available(),
        "designs": [n for n, _ in list_designs()],
    }
    if args.json:
        _emit(payload, True)
    else:
        print(f"flow5ctl      {__version__}")
        print(f"flow5         {install.version}  {install.path}")
        print(f"              {'verified' if install.verified else 'NOT verified'}")
        if install.note:
            print(f"              {install.note}")
        print(f"workspace     {ws}  ({'writable' if payload['workspace_writable'] else 'NOT writable'})")
        print(f"presets       {', '.join(payload['presets'])}")
        print(f"designs       {', '.join(payload['designs']) or '(none)'}")
    return 0


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".flow5ctl-write-test"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def cmd_init(args: argparse.Namespace) -> int:
    import yaml
    raw = yaml.safe_load(Path(args.file).read_text(encoding="utf-8")) if args.file else {}
    raw = raw or {}
    if args.preset:
        raw["preset"] = args.preset
    root = Path(args.path) if args.path else None
    payload = define_uc.create(args.name, raw, root=root, exist_ok=args.force)
    _emit(payload, args.json)
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    project = Project.resolve(args.design)
    _emit(define_uc.describe(project), args.json)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    rows = list_designs()
    if args.json:
        _emit({"workspace": str(workspace_root()),
               "designs": [{"name": n, "path": str(p)} for n, p in rows]}, True)
        return 0
    if not rows:
        print(f"no designs in {workspace_root()}")
        return 0
    for name, path in rows:
        print(f"{name:24s} {path}")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    project = Project.resolve(args.design)
    alpha = None
    if args.alpha:
        parts = [float(v) for v in args.alpha.replace(":", ",").split(",")]
        if len(parts) != 3:
            raise Flow5ctlError("--alpha takes three values: min,max,step")
        alpha = (parts[0], parts[1], parts[2])
    req = analyze_uc.Request(
        name=args.name,
        polar_type=args.type,
        method=args.method,
        speed=args.speed,
        alpha=alpha,
        viscous=None if args.viscous is None else args.viscous,
        on_the_fly=args.on_the_fly,
        ground_effect=args.ground_effect,
        ground_height=args.ground_height,
        mass=args.mass,
        cg_x=args.cg,
        stability=args.type.upper() == "T7",
        export_stl=args.stl,
        export_cp=args.cp,
        timeout=args.timeout,
        recompute_polars=args.recompute_polars,
    )
    _emit(analyze_uc.analyze(project, req, flow5=args.flow5), args.json)
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    project = Project.resolve(args.design)
    _emit(edit_uc.set_fields(project, args.assignment), args.json)
    return 0


def cmd_expand(args: argparse.Namespace) -> int:
    project = Project.resolve(args.design)
    _emit(edit_uc.expand(project), args.json)
    return 0


def cmd_airfoil(args: argparse.Namespace) -> int:
    project = Project.resolve(args.design)
    if args.airfoil_command == "list":
        _emit(edit_uc.list_airfoils(project), args.json)
        return 0
    source = args.source
    if args.naca:
        source = f"naca:{args.naca}"
    elif args.file:
        source = f"file:{args.file}"
    elif args.url:
        source = f"url:{args.url}"
    if not source:
        raise Flow5ctlError("give a source: --naca, --file, --url, or a source string")
    reynolds = None
    if args.reynolds:
        reynolds = [float(v) for v in args.reynolds.replace(" ", "").split(",") if v]
    alpha = None
    if args.polar_alpha:
        parts = [float(v) for v in args.polar_alpha.replace(":", ",").split(",")]
        if len(parts) != 3:
            raise Flow5ctlError("--polar-alpha takes three values: min,max,step")
        alpha = (parts[0], parts[1], parts[2])
    _emit(edit_uc.add_airfoil(project, args.name, source, reynolds=reynolds,
                              ncrit=args.ncrit, alpha=alpha, replace=args.replace),
          args.json)
    return 0


def cmd_trim(args: argparse.Namespace) -> int:
    project = Project.resolve(args.design)
    alpha_range = None
    if args.alpha_range:
        parts = [float(v) for v in args.alpha_range.replace(":", ",").split(",")]
        if len(parts) != 3:
            raise Flow5ctlError("--alpha-range takes three values: min,max,step")
        alpha_range = (parts[0], parts[1], parts[2])
    req = trim_uc.TrimRequest(
        target=args.target.replace("-", "_"),
        value=args.value,
        speed=args.speed,
        alpha=args.alpha,
        mass=args.mass,
        alpha_range=alpha_range,
        viscous=args.viscous,
        ground_effect=args.ground_effect,
        timeout=args.timeout,
    )
    _emit(trim_uc.trim(project, req, flow5=args.flow5), args.json)
    return 0


def cmd_sweep(args: argparse.Namespace) -> int:
    project = Project.resolve(args.design)
    if args.study:
        req = sweep_uc.load_study(Path(args.study))
    else:
        if not args.parameter or not args.values:
            raise Flow5ctlError(
                "give a study file, or both --parameter and --values"
            )
        alpha = None
        if args.alpha:
            parts = [float(v) for v in args.alpha.replace(":", ",").split(",")]
            if len(parts) != 3:
                raise Flow5ctlError("--alpha takes three values: min,max,step")
            alpha = (parts[0], parts[1], parts[2])
        req = sweep_uc.SweepRequest(
            parameter=args.parameter,
            values=sweep_uc.parse_values(args.values),
            name=args.name or args.parameter.replace(".", "-"),
            analysis=analyze_uc.Request(
                name="sweep", polar_type=args.type, speed=args.speed, alpha=alpha,
                viscous=args.viscous, ground_effect=args.ground_effect,
                mass=args.mass, timeout=args.timeout),
        )
    if args.metrics:
        req.metrics = tuple(m.strip() for m in args.metrics.split(",") if m.strip())
    _emit(sweep_uc.sweep(project, req, flow5=args.flow5), args.json)
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    project = Project.resolve(args.design)
    _emit(edit_uc.export(project, args.format, polar=args.polar,
                         out_dir=Path(args.out) if args.out else None), args.json)
    return 0


def cmd_open(args: argparse.Namespace) -> int:
    project = Project.resolve(args.design)
    _emit(gui_uc.open_in_flow5(project, polar=args.polar, flow5=args.flow5,
                               launch=not args.no_launch), args.json)
    return 0


def cmd_presets(args: argparse.Namespace) -> int:
    rows = [presets.load(n) for n in presets.available()]
    if args.json:
        _emit({"presets": [
            {"name": p.name, "label": p.label, "description": p.description}
            for p in rows]}, True)
        return 0
    for p in rows:
        print(f"{p.name:12s} {p.label:28s} {p.description}")
    return 0


# --------------------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="flow5ctl",
        description="AI-driven aircraft design with flow5.",
    )
    ap.add_argument("--version", action="version", version=f"flow5ctl {__version__}")
    ap.add_argument("--flow5", metavar="PATH", help="path to the flow5 executable")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    sub = ap.add_subparsers(dest="command", required=True)

    def add(name: str, **kw) -> argparse.ArgumentParser:
        """Every subcommand also accepts --json after the verb, which is where anyone
        driving this from a script or an agent will naturally put it."""
        p = sub.add_parser(name, **kw)
        p.add_argument("--json", action="store_true", default=None,
                       help=argparse.SUPPRESS)
        p.add_argument("--flow5", metavar="PATH", default=None, help=argparse.SUPPRESS)
        return p

    p = add("doctor", help="check the environment")
    p.set_defaults(func=cmd_doctor)

    p = add("presets", help="list available presets")
    p.set_defaults(func=cmd_presets)

    p = add("list", help="list designs in the workspace")
    p.set_defaults(func=cmd_list)

    p = add("init", help="create a design")
    p.add_argument("name")
    p.add_argument("--preset", choices=presets.available())
    p.add_argument("--file", metavar="YAML", help="design fields to start from")
    p.add_argument("--path", metavar="DIR", help="create here instead of the workspace")
    p.add_argument("--force", action="store_true", help="overwrite an existing design")
    p.set_defaults(func=cmd_init)

    p = add("show", help="show a design and its derived geometry")
    p.add_argument("design", nargs="?")
    p.set_defaults(func=cmd_show)

    p = add("set", help="change fields in a design")
    p.add_argument("assignment", nargs="+", metavar="PATH=VALUE",
                   help="e.g. wing.planform.washout=-2.5")
    p.add_argument("--design")
    p.set_defaults(func=cmd_set)

    p = add("expand", help="rewrite planform shorthand as explicit sections")
    p.add_argument("design", nargs="?")
    p.set_defaults(func=cmd_expand)

    p = add("airfoil", help="add or list airfoils")
    apsub = p.add_subparsers(dest="airfoil_command", required=True)
    ap_add = apsub.add_parser("add", help="add an airfoil to the design")
    ap_add.add_argument("name")
    ap_add.add_argument("source", nargs="?", help="naca:2412 / file:foo.dat / url:...")
    ap_add.add_argument("--naca", metavar="NNNN")
    ap_add.add_argument("--file", metavar="PATH")
    ap_add.add_argument("--url", metavar="URL")
    ap_add.add_argument("--reynolds", metavar="LIST",
                        help="2D polar Reynolds numbers; omitted means derive them")
    ap_add.add_argument("--ncrit", type=float)
    ap_add.add_argument("--polar-alpha", dest="polar_alpha", metavar="MIN,MAX,STEP")
    ap_add.add_argument("--replace", action="store_true")
    ap_add.add_argument("--design")
    ap_list = apsub.add_parser("list", help="list the design's airfoils")
    ap_list.add_argument("design", nargs="?")
    p.set_defaults(func=cmd_airfoil)

    p = add("analyze", help="run an analysis")
    p.add_argument("design", nargs="?")
    p.add_argument("--name", default="cruise", help="name for this polar")
    p.add_argument("--type", default="T1",
                   help="T1 fixed speed, T2 fixed lift, T3 glide, T5 sideslip, T7 stability")
    p.add_argument("--method", help="LLT, VLM1, VLM2, QUADS, TRIUNIFORM, TRILINEAR")
    p.add_argument("--speed", type=float)
    p.add_argument("--alpha", help="min,max,step in degrees")
    p.add_argument("--viscous", dest="viscous", action="store_true", default=None)
    p.add_argument("--inviscid", dest="viscous", action="store_false")
    p.add_argument("--on-the-fly", dest="on_the_fly", action="store_true", default=None,
                   help="XFoil on the fly instead of interpolating a 2D polar mesh")
    p.add_argument("--ground-effect", dest="ground_effect", action="store_true", default=None)
    p.add_argument("--no-ground-effect", dest="ground_effect", action="store_false")
    p.add_argument("--ground-height", dest="ground_height", type=float)
    p.add_argument("--mass", type=float)
    p.add_argument("--cg", type=float, metavar="X", help="override the CG x position")
    p.add_argument("--stl", action="store_true", help="export an STL mesh")
    p.add_argument("--cp", action="store_true", help="export Cp per operating point")
    p.add_argument("--recompute-polars", dest="recompute_polars", action="store_true",
                   help="rebuild the 2D airfoil polar cache")
    p.add_argument("--timeout", type=float, default=900.0)
    p.set_defaults(func=cmd_analyze)

    p = add("trim", help="solve for a condition instead of sweeping to it")
    p.add_argument("design", nargs="?")
    p.add_argument("--target", required=True,
                   choices=["cl", "level", "speed", "static-margin", "pitch"],
                   help="cl: alpha for a CL | level: alpha for level flight | "
                        "speed: speed at an alpha | static-margin: CG for a margin | "
                        "pitch: elevator incidence for Cm = 0")
    p.add_argument("--value", type=float, help="the target value")
    p.add_argument("--speed", type=float)
    p.add_argument("--alpha", type=float, help="a single angle, for --target speed/pitch")
    p.add_argument("--alpha-range", dest="alpha_range", metavar="MIN,MAX,STEP")
    p.add_argument("--mass", type=float)
    p.add_argument("--viscous", dest="viscous", action="store_true", default=None)
    p.add_argument("--inviscid", dest="viscous", action="store_false")
    p.add_argument("--ground-effect", dest="ground_effect", action="store_true", default=None)
    p.add_argument("--no-ground-effect", dest="ground_effect", action="store_false")
    p.add_argument("--timeout", type=float, default=900.0)
    p.set_defaults(func=cmd_trim)

    p = add("sweep", help="vary one parameter and compare")
    p.add_argument("design", nargs="?")
    p.add_argument("--study", metavar="YAML", help="a saved study file")
    p.add_argument("--parameter", metavar="PATH",
                   help="a design path (wing.planform.taper) or cg_x / speed / mass")
    p.add_argument("--values", metavar="SPEC", help="0.3,0.4,0.5 or from:to:steps")
    p.add_argument("--metrics", metavar="LIST")
    p.add_argument("--name")
    p.add_argument("--type", default="T1")
    p.add_argument("--speed", type=float)
    p.add_argument("--alpha", metavar="MIN,MAX,STEP")
    p.add_argument("--mass", type=float)
    p.add_argument("--viscous", dest="viscous", action="store_true", default=None)
    p.add_argument("--inviscid", dest="viscous", action="store_false")
    p.add_argument("--ground-effect", dest="ground_effect", action="store_true", default=None)
    p.add_argument("--no-ground-effect", dest="ground_effect", action="store_false")
    p.add_argument("--timeout", type=float, default=900.0)
    p.set_defaults(func=cmd_sweep)

    p = add("export", help="copy a build artifact out")
    p.add_argument("design", nargs="?")
    p.add_argument("--format", default="fl5", choices=["fl5", "stl", "csv", "xml"])
    p.add_argument("--polar", help="which analysis to export (default: the most recent)")
    p.add_argument("--out", metavar="DIR")
    p.set_defaults(func=cmd_export)

    p = add("open", help="open the design in the flow5 GUI")
    p.add_argument("design", nargs="?")
    p.add_argument("--polar")
    p.add_argument("--no-launch", dest="no_launch", action="store_true",
                   help="export and print the command without launching")
    p.set_defaults(func=cmd_open)

    return ap


_VALUE_OPTS = (
    "--alpha", "--alpha-range", "--polar-alpha", "--speed", "--cg", "--mass",
    "--ground-height", "--timeout", "--value", "--values", "--ncrit",
)


def _glue_negative_values(argv: list[str]) -> list[str]:
    """Let `--alpha -2,8,2` work as well as `--alpha=-2,8,2`.

    argparse treats any token starting with `-` as an option unless it looks like a
    plain negative number, and `-2,8,2` does not. Since an alpha sweep almost always
    starts negative, this would otherwise be a papercut on nearly every call.
    """
    out: list[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok in _VALUE_OPTS and i + 1 < len(argv) and argv[i + 1].startswith("-"):
            nxt = argv[i + 1]
            if all(c in "-+.,:0123456789eE" for c in nxt):
                out.append(f"{tok}={nxt}")
                i += 2
                continue
        out.append(tok)
        i += 1
    return out


def main(argv: list[str] | None = None) -> int:
    raw = _glue_negative_values(list(sys.argv[1:] if argv is None else argv))
    ap = build_parser()
    # A subcommand-level --json defaults to None so that `flow5ctl --json show` still
    # works; resolve the two into one boolean.
    pre, _ = ap.parse_known_args([a for a in raw if a != "--json"])
    args = ap.parse_args(raw)
    if getattr(args, "json", None) is None:
        args.json = "--json" in raw
    if getattr(args, "flow5", None) is None:
        args.flow5 = getattr(pre, "flow5", None)
    try:
        return int(args.func(args) or 0)
    except Flow5ctlError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

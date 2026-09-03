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

    p = sub.add_parser("doctor", help="check the environment")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("presets", help="list available presets")
    p.set_defaults(func=cmd_presets)

    p = sub.add_parser("list", help="list designs in the workspace")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("init", help="create a design")
    p.add_argument("name")
    p.add_argument("--preset", choices=presets.available())
    p.add_argument("--file", metavar="YAML", help="design fields to start from")
    p.add_argument("--path", metavar="DIR", help="create here instead of the workspace")
    p.add_argument("--force", action="store_true", help="overwrite an existing design")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("show", help="show a design and its derived geometry")
    p.add_argument("design", nargs="?")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("analyze", help="run an analysis")
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

    return ap


_VALUE_OPTS = ("--alpha", "--speed", "--cg", "--mass", "--ground-height", "--timeout")


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
    ap = build_parser()
    args = ap.parse_args(_glue_negative_values(list(sys.argv[1:] if argv is None else argv)))
    try:
        return int(args.func(args) or 0)
    except Flow5ctlError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

"""Field-level edits, airfoils, and shorthand expansion.

`set` exists because an agent adjusting washout should not have to restate the whole
aircraft, and a restated aircraft is a chance to lose a field.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from ..errors import DesignError
from ..flow5 import airfoils as foil_io
from ..geometry.planform import resolve_sections
from ..model.design import Airfoil, Design
from ..project.store import Project, explain_validation
from ..units import to_si_length
from .define import describe


def _parse_scalar(text: str) -> Any:
    """YAML scalar rules, so `true`, `3`, `0.45`, `[1, 2]` and `COSINE` all work."""
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        return text


def set_fields(project: Project, assignments: list[str]) -> dict[str, Any]:
    """Apply `path=value` assignments to design.yaml."""
    design = project.load()
    data = design.model_dump(mode="json", by_alias=True, exclude_none=True)
    before = copy.deepcopy(data)
    applied: list[str] = []

    for raw in assignments:
        if "=" not in raw:
            raise DesignError(f"{raw!r} is not a `path=value` assignment")
        path, _, text = raw.partition("=")
        path, value = path.strip(), _parse_scalar(text.strip())
        node: Any = data
        parts = path.split(".")
        for key in parts[:-1]:
            if isinstance(node, list):
                try:
                    node = node[int(key)]
                    continue
                except (ValueError, IndexError):
                    raise DesignError(f"{path!r}: {key!r} is not a valid list index") from None
            if not isinstance(node, dict) or key not in node:
                raise DesignError(
                    f"{path!r} does not exist (stopped at {key!r}). "
                    "Run `flow5ctl show --json` to see the available fields."
                )
            node = node[key]
        leaf = parts[-1]
        if isinstance(node, list):
            node[int(leaf)] = value
        elif isinstance(node, dict):
            if leaf not in node:
                raise DesignError(
                    f"{path!r} does not exist. flow5ctl will not create new fields by "
                    "assignment, because a typo would silently add a field flow5 ignores."
                )
            node[leaf] = value
        else:
            raise DesignError(f"{path!r} is not a settable path")
        applied.append(f"{path} = {value!r}")

    # validation happens here, before anything is written. A rejected edit is a
    # normal event - the same explainer the loader uses turns it into a sentence
    # rather than a Pydantic traceback.
    try:
        updated = Design.model_validate(data)
    except ValidationError as exc:
        raise DesignError(explain_validation(
            exc, project.design_path,
            lead="that edit would not leave a valid design, so nothing was written:",
        )) from exc
    project.save(updated)
    out = describe(project)
    out["applied"] = applied
    out["changed"] = sorted(_changed(before, data))
    return out


def _changed(before: dict, after: dict, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    for key in set(before) | set(after):
        p = f"{prefix}{key}"
        b, a = before.get(key), after.get(key)
        if isinstance(b, dict) and isinstance(a, dict):
            paths |= _changed(b, a, f"{p}.")
        elif b != a:
            paths.add(p)
    return paths


def add_airfoil(project: Project, name: str, source: str, *,
                reynolds: list[float] | None = None, ncrit: float | None = None,
                alpha: tuple[float, float, float] | None = None,
                replace: bool = False) -> dict[str, Any]:
    """Validate the coordinates, store the .dat, and register the airfoil."""
    design = project.load()
    existing = {a.name for a in design.airfoils}
    if name in existing and not replace:
        raise DesignError(
            f"airfoil {name!r} is already declared. Pass --replace to overwrite it."
        )

    points = foil_io.resolve(name, source, project.root)
    dat = foil_io.write_dat(project.airfoils / f"{name}.dat", name, points)
    stored_source = f"file:{dat.relative_to(project.root).as_posix()}"

    polars: dict[str, Any] = {}
    if reynolds:
        polars["reynolds"] = reynolds
    if ncrit is not None:
        polars["ncrit"] = ncrit
    if alpha is not None:
        polars["alpha"] = list(alpha)

    entry = Airfoil.model_validate(
        {"name": name, "source": stored_source, **({"polars": polars} if polars else {})}
    )
    design.airfoils = [a for a in design.airfoils if a.name != name] + [entry]
    project.save(design)

    thickness = max(p[1] for p in points) - min(p[1] for p in points)
    out = describe(project)
    out["airfoil"] = {
        "name": name,
        "requested_source": source,
        "stored_at": str(dat.relative_to(project.root)),
        "points": len(points),
        "max_thickness_fraction": round(thickness, 4),
    }
    out["notes"] = [
        *out.get("notes", []),
        f"the .dat file's first line is {name!r} — that string, not the filename, is how "
        "flow5 identifies the section.",
    ]
    return out


def list_airfoils(project: Project) -> dict[str, Any]:
    design = project.load()
    rows = []
    for a in design.airfoils:
        used_by = [
            surface.name or surface.role
            for surface in design.surfaces()
            if surface.airfoil == a.name or any(
                a.name in (s.airfoil, s.airfoil_left, s.airfoil_right)
                for s in (surface.sections or [])
            )
        ]
        rows.append({
            "name": a.name,
            "source": a.source,
            "reynolds": a.polars.reynolds,
            "ncrit": a.polars.ncrit,
            "alpha": list(a.polars.alpha),
            "used_by": used_by,
        })
    return {"design": design.name, "airfoils": rows}


def expand(project: Project, *, write: bool = True) -> dict[str, Any]:
    """Rewrite planform shorthand as explicit sections, in place.

    This is the only way sections come into existence from shorthand, so the two can
    never drift apart. Once expanded, a designer can hand-tune individual stations.
    """
    design = project.load()
    to_m = to_si_length(1.0, design.units.length)
    expanded: list[str] = []

    for surface in design.surfaces():
        if surface.sections is not None:
            continue
        sections = resolve_sections(surface, to_m)
        surface.sections = [
            s.model_copy(update={
                "y": round(s.y / to_m, 6),
                "chord": round(s.chord / to_m, 6),
                "offset": round(s.offset / to_m, 6),
            })
            for s in sections
        ]
        surface.planform = None
        expanded.append(f"{surface.name or surface.role} → {len(sections)} sections")

    if not expanded:
        return {**describe(project), "expanded": [],
                "notes": ["every surface already uses explicit sections."]}
    if write:
        project.save(design)
    out = describe(project)
    out["expanded"] = expanded
    return out


#: Suffixes this tool appends to a polar name for its own runs. A user never asks
#: for one of these by name, and neither should a default.
INTERNAL_SUFFIXES = ("__zref", "__free")


def _is_internal(name: str) -> bool:
    return name.endswith(INTERNAL_SUFFIXES)


def _missing(polar: str, runs: list[Path], asked_for: set[str]) -> str:
    """Why a named analysis cannot be exported — which is rarely that it never ran.

    `build/` is overwritten by every solver invocation, so a `trim` or a `sweep` run
    afterwards leaves the earlier analysis' artifacts gone while its results JSON
    stays. The old message — "no analysis called 'cruise'. Available: cg_x_02" —
    named a sweep point the user never asked for and implied their own analysis had
    never happened.
    """
    if polar in asked_for:
        return (
            f"{polar!r} was analysed and its results are still here, but the solver "
            "output it would be exported from has been overwritten: `build/` holds "
            "the last run only, and a `trim` or a `sweep` since then has replaced "
            f"it. Re-run it (`analyze --name {polar}`) and export straight after."
        )
    offered = [p.name for p in runs if not _is_internal(p.name)]
    return (f"no analysis called {polar!r}. "
            f"Exportable right now: {', '.join(offered) or 'none'}")


def export(project: Project, fmt: str, *, polar: str | None = None,
           out_dir: Path | None = None) -> dict[str, Any]:
    """Copy a build artifact out of `build/` under a predictable name."""
    import shutil

    design = project.load()
    target_dir = Path(out_dir) if out_dir else project.root / "export"
    target_dir.mkdir(parents=True, exist_ok=True)
    build_out = project.build / "out"
    if not build_out.is_dir():
        raise DesignError("nothing has been analysed yet, so there is nothing to export.")

    runs = sorted((p for p in build_out.iterdir() if p.is_dir()),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    # `build/` holds the last solver invocation only - every run overwrites it - so
    # what can be exported is a much smaller set than what has been analysed. An
    # analysis the user named and read is in `results/`; a run that is in `build/`
    # but not in `results/` is one nobody asked for by name: a sweep point, a trim's
    # internal pass, a ground comparison's free-air copy.
    asked_for = {q.stem for q in project.results.glob("*.json")}
    if polar is not None:
        chosen = next((p for p in runs if p.name == polar), None)
        if chosen is None:
            raise DesignError(_missing(polar, runs, asked_for))
    else:
        chosen = (next((p for p in runs if p.name in asked_for), None)
                  or next((p for p in runs if not _is_internal(p.name)), None))
        if chosen is None:
            raise DesignError(
                "the only solver output on disk is an internal by-product of `trim` "
                "or `analyze --compare-ground`, not a run you asked for. Run "
                "`analyze` and export straight after it."
            )

    notes: list[str] = []
    from_analysis: str | None = chosen.name

    # Build output can be older than the design: an edit since the analysis leaves
    # the two describing different aeroplanes, and nothing in the exported file says
    # which one it is.
    if project.design_path.is_file():
        try:
            if project.design_path.stat().st_mtime > chosen.stat().st_mtime:
                notes.append(
                    f"the design has been edited since {chosen.name} was run, so this "
                    "is the geometry as it was then, not as it is now. Re-run the "
                    "analysis if you want the current shape."
                )
        except OSError:
            pass

    fmt = fmt.lower()
    if fmt == "fl5":
        # flow5 writes the project with no extension; the GUI wants one.
        src = chosen / chosen.name
        if not src.is_file():
            raise DesignError(f"no flow5 project file in {chosen}")
        dst = target_dir / f"{design.name}-{chosen.name}.fl5"
        shutil.copyfile(src, dst)
    elif fmt == "stl":
        candidates = sorted((chosen / "STL").glob("*.stl")) if (chosen / "STL").is_dir() else []
        if not candidates:
            raise DesignError(
                "no STL mesh was exported. Re-run the analysis with --stl."
            )
        dst = target_dir / f"{design.name}.stl"
        shutil.copyfile(candidates[0], dst)
    elif fmt in {"csv", "polar"}:
        where = chosen / design.name
        candidates = sorted(where.glob("*.csv")) if where.is_dir() else []
        if not candidates:
            raise DesignError(f"no polar file found in {where}")
        # The polar's own file, not whichever sorts first. Taking candidates[0]
        # alphabetically is a silent choice when there is more than one.
        named = [c for c in candidates if c.stem == chosen.name]
        pick = named[0] if named else candidates[0]
        if not named and len(candidates) > 1:
            notes.append(
                f"{where} holds {len(candidates)} polar files and none is named "
                f"{chosen.name!r}; took {pick.name} because it sorts first. The "
                "others are: " + ", ".join(c.name for c in candidates if c is not pick)
            )
        dst = target_dir / f"{design.name}-{pick.name}"
        shutil.copyfile(pick, dst)
    elif fmt == "xml":
        dst = target_dir / f"{design.name}-plane.xml"
        src = project.build / "planes" / "plane.xml"
        if not src.is_file():
            raise DesignError("no generated plane XML found; run an analysis first.")
        shutil.copyfile(src, dst)
        # This one is not the selected run's. `plane.xml` sits outside `build/out/`
        # and every analysis overwrites it, so it is whatever ran last - and the
        # payload used to report `from_analysis` beside it, which read as a claim
        # that the geometry came from the polar named there.
        from_analysis = None
        notes.append(
            "this is the plane XML from the most recent solver run, whichever that "
            "was. It is not tied to a polar: flow5ctl writes one `plane.xml` per "
            "project and every analysis overwrites it, so if you have run anything "
            "since the analysis you have in mind, this is the geometry of that "
            "later run."
        )
    else:
        raise DesignError(f"unknown export format {fmt!r}. Use fl5, stl, csv or xml.")

    return {
        "status": "ok",
        "design": design.name,
        "format": fmt,
        "from_analysis": from_analysis,
        "path": str(dst),
        "notes": notes
                 + (["Open it in the flow5 GUI with `flow5ctl open`."] if fmt == "fl5" else [])
                 + ([f"{chosen.name} is an internal by-product, not an analysis you "
                     "asked for: a reference-height pass holds the CG at wing height, "
                     "and a ground comparison's free-air copy has ground effect off. "
                     "You named it, so it was used."] if _is_internal(chosen.name) else [])
                 + ([f"{chosen.name} is simply the last thing the solver ran — a sweep "
                     "point or an intermediate step — not an analysis you named. "
                     "`build/` keeps only the most recent run, so if you wanted a "
                     "particular analysis, re-run it and export straight after."]
                    if not _is_internal(chosen.name) and chosen.name not in asked_for
                    else []),
    }

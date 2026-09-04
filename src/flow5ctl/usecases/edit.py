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
    if polar is not None:
        chosen = next((p for p in runs if p.name == polar), None)
    else:
        # Never default to one of our own by-products. The reference-height pass
        # runs the aircraft with the CG at wing height so the CG-height term can be
        # separated out, and the ground comparison runs a free-air copy; both land
        # in build/out and both are usually the most recent thing there. Exporting
        # one of them hands the user a different aircraft than the one they asked
        # about, under a name that looks close enough to be missed.
        chosen = next((p for p in runs if not _is_internal(p.name)), None)
    if chosen is None:
        offered = [p.name for p in runs if not _is_internal(p.name)]
        raise DesignError(
            f"no analysis called {polar!r}. Available: {', '.join(offered) or 'none'}"
            if polar is not None else
            "the only analyses on disk are internal by-products of `trim` and "
            "`analyze --compare-ground`, not runs you asked for. Run `analyze` first."
        )

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
        candidates = sorted((chosen / design.name).glob("*.csv")) \
            if (chosen / design.name).is_dir() else []
        if not candidates:
            raise DesignError(f"no polar file found in {chosen / design.name}")
        dst = target_dir / f"{design.name}-{candidates[0].name}"
        shutil.copyfile(candidates[0], dst)
    elif fmt == "xml":
        dst = target_dir / f"{design.name}-plane.xml"
        src = project.build / "planes" / "plane.xml"
        if not src.is_file():
            raise DesignError("no generated plane XML found; run an analysis first.")
        shutil.copyfile(src, dst)
    else:
        raise DesignError(f"unknown export format {fmt!r}. Use fl5, stl, csv or xml.")

    return {
        "status": "ok",
        "design": design.name,
        "format": fmt,
        "from_analysis": chosen.name,
        "path": str(dst),
        "notes": (["Open it in the flow5 GUI with `flow5ctl open`."] if fmt == "fl5" else [])
                 + ([f"{chosen.name} is an internal by-product, not an analysis you "
                     "asked for: a reference-height pass holds the CG at wing height, "
                     "and a ground comparison's free-air copy has ground effect off. "
                     "You named it, so it was used."] if _is_internal(chosen.name) else []),
    }

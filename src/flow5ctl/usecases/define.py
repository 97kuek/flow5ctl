"""Create and update a design, and report everything derivable from it.

Every applied preset default is named in the response. Silent defaults are how
designs go wrong.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from ..advisor import guardrails
from ..errors import DesignError
from ..geometry import derived as geometry
from ..model import presets
from ..model.design import Design
from ..project.store import Project, workspace_root


def _deep_merge(base: dict, patch: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def apply_preset(raw: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Fill in preset defaults, returning the design data and what was applied."""
    preset = presets.load(raw.get("preset", "custom"))
    applied: list[str] = []
    out = copy.deepcopy(raw)

    for key in ("atmosphere", "requirements"):
        want = preset.defaults.get(key) or {}
        have = out.setdefault(key, {}) or {}
        for field, value in want.items():
            if field not in have:
                have[field] = value
                applied.append(f"{key}.{field} = {value!r} ({preset.name} preset)")
        out[key] = have

    def panels_for(wing: dict | None, which: str) -> None:
        if wing is None:
            return
        want = preset.defaults.get(which) or {}
        have = wing.setdefault("panels", {}) or {}
        for field, value in want.items():
            if field not in have:
                have[field] = value
                applied.append(f"panels.{field} = {value!r} ({preset.name} preset)")
        wing["panels"] = have

    panels_for(out.get("wing"), "wing_panels")
    tail = out.get("tail") or {}
    panels_for(tail.get("elevator"), "tail_panels")
    panels_for(tail.get("fin"), "tail_panels")

    if not out.get("airfoils"):
        raise DesignError(
            "a design needs at least one airfoil in `airfoils`. Use "
            "`{name: NACA2412, source: 'naca:2412'}` to start from a NACA section."
        )
    return out, applied


def describe(project: Project) -> dict[str, Any]:
    """The `get_design` payload: the design, all derived geometry, and warnings."""
    design = project.load()
    preset = presets.load(design.preset)
    d = geometry.solve(design)
    checks = guardrails.check_geometry(d, preset)
    state = project.state()
    return {
        "name": design.name,
        "path": str(project.root),
        "preset": design.preset,
        "description": design.description,
        "geometry": d.as_dict(),
        "airfoils": [{"name": a.name, "source": a.source} for a in design.airfoils],
        "requirements": design.requirements.model_dump(exclude_none=True),
        "warnings": checks.warnings,
        "notes": checks.notes,
        "flow5_version_last_used": state.get("flow5_version"),
        "polars": sorted(p.stem for p in project.results.glob("*.json"))
        if project.results.is_dir() else [],
    }


def create(name: str, raw: dict[str, Any], *, root: Path | None = None,
           exist_ok: bool = False) -> dict[str, Any]:
    data, applied = apply_preset({**raw, "name": name})
    design = Design.model_validate(data)
    target = Path(root) if root else workspace_root() / name
    project = Project.create(target, design, exist_ok=exist_ok)
    out = describe(project)
    out["defaults_applied"] = applied
    return out


def update(project: Project, patch: dict[str, Any]) -> dict[str, Any]:
    current = project.load().model_dump(mode="json", by_alias=True, exclude_none=True)
    merged = _deep_merge(current, patch)
    data, applied = apply_preset(merged)
    design = Design.model_validate(data)
    project.save(design)
    out = describe(project)
    out["defaults_applied"] = applied
    out["changed"] = sorted(_changed_paths(current, data))
    return out


def _changed_paths(before: dict, after: dict, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    for key in set(before) | set(after):
        p = f"{prefix}{key}"
        b, a = before.get(key), after.get(key)
        if isinstance(b, dict) and isinstance(a, dict):
            paths |= _changed_paths(b, a, f"{p}.")
        elif b != a:
            paths.add(p)
    return paths

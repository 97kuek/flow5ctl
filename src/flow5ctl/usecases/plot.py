"""Render a stored analysis as a PNG.

Reads `results/<polar>.json` rather than re-running the solver, so a chart costs
nothing and can be redrawn in either theme without touching flow5.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from ..errors import DesignError
from ..project.store import Project
from ..viz import charts


def available(project: Project) -> list[str]:
    if not project.results.is_dir():
        return []
    return sorted(p.stem for p in project.results.glob("*.json")
                  if not p.stem.startswith("study-"))


def _load(project: Project, name: str) -> dict[str, Any]:
    path = project.results / f"{name}.json"
    if not path.is_file():
        raise DesignError(
            f"no stored result called {name!r}. Available: "
            f"{', '.join(available(project)) or 'none — run an analysis first'}"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    if "columns" not in data or "rows" not in data:
        raise DesignError(
            f"{name!r} was stored without its data table, so it cannot be plotted. "
            "Re-run the analysis."
        )
    return data


def _strip_table(result: dict[str, Any]) -> dict[str, Any] | None:
    """The spanwise strip table, taken from the stored result.

    It is stored at analysis time rather than read from `build/`, because `build/` is
    cleared by the next analysis and a chart must not depend on that surviving.
    """
    stored = result.get("strips")
    if not stored or not stored.get("surfaces"):
        return None
    for wing, cols in stored["surfaces"].items():
        ys, cls = cols.get("y(m)"), cols.get("Cl")
        if not ys or not cls:
            continue
        if any(math.isfinite(v) and v != 0.0 for v in cls):
            return {wing: {"y": ys, "cl": cls,
                           "source": stored.get("source", ""),
                           "alpha": stored.get("alpha")}}
    return None


def plot(project: Project, *, kind: str = "polar", polars: list[str] | None = None,
         theme: str = "light", out: Path | None = None) -> tuple[dict[str, Any], bytes]:
    """-> (payload, png bytes). The caller decides whether to write or return them."""
    names = polars or available(project)[-1:]
    if not names:
        raise DesignError("nothing has been analysed yet, so there is nothing to plot.")
    results = [_load(project, n) for n in names]
    design = results[0].get("design", project.name)

    strips = _strip_table(results[0]) if kind == "spanwise_lift" else None
    data = charts.render(results, kind, theme_name=theme, strips=strips)

    payload: dict[str, Any] = {
        "status": "ok",
        "design": design,
        "kind": kind,
        "description": charts.KINDS[kind],
        "polars": names,
        "theme": theme,
        "bytes": len(data),
        "mime_type": "image/png",
    }
    if strips:
        first = next(iter(strips.values()))
        payload["strip_source"] = first["source"]
        payload["strip_alpha"] = first.get("alpha")
    if out is not None:
        payload["path"] = str(charts.write(Path(out), data))
    return payload, data

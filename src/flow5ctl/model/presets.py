"""Presets: defaults, analysis policy and sanity thresholds per class of aircraft.

Deliberately data, not code (`src/flow5ctl/presets/*.yaml`), so the community can
contribute a preset for F3F or an HPA distance ship without touching the solver layer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from ..errors import DesignError

_DIR = "flow5ctl.presets"


@dataclass(slots=True)
class Preset:
    name: str
    label: str
    description: str
    defaults: dict[str, Any] = field(default_factory=dict)
    analysis: dict[str, Any] = field(default_factory=dict)
    limits: dict[str, Any] = field(default_factory=dict)
    thresholds: dict[str, list[float]] = field(default_factory=dict)

    def band(self, key: str) -> tuple[float, float] | None:
        v = self.thresholds.get(key)
        return (float(v[0]), float(v[1])) if v else None


def available() -> list[str]:
    return sorted(
        p.name.removesuffix(".yaml")
        for p in resources.files(_DIR).iterdir()
        if p.name.endswith(".yaml")
    )


def load(name: str) -> Preset:
    name = (name or "custom").strip()
    try:
        text = (resources.files(_DIR) / f"{name}.yaml").read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        raise DesignError(
            f"unknown preset {name!r}. Available: {', '.join(available())}"
        ) from None
    data = yaml.safe_load(text) or {}
    return Preset(
        name=data.get("name", name),
        label=data.get("label", name),
        description=data.get("description", ""),
        defaults=data.get("defaults") or {},
        analysis=data.get("analysis") or {},
        limits=data.get("limits") or {},
        thresholds=data.get("thresholds") or {},
    )


def load_file(path: Path) -> Preset:
    """A project-local preset, for a class we do not ship."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return Preset(
        name=data.get("name", Path(path).stem),
        label=data.get("label", Path(path).stem),
        description=data.get("description", ""),
        defaults=data.get("defaults") or {},
        analysis=data.get("analysis") or {},
        limits=data.get("limits") or {},
        thresholds=data.get("thresholds") or {},
    )

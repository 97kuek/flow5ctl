"""Resolve an airfoil source into a `.dat` file flow5 can load.

The name written on line 1 matters: flow5 identifies a foil by that string, not by
the filename, and silently discards any plane whose foils it cannot resolve.
"""
from __future__ import annotations

import math
import re
import urllib.error
import urllib.request
from pathlib import Path

from ..errors import DesignError

_NACA4 = re.compile(r"^naca:(\d{4})$", re.IGNORECASE)
_FILE = re.compile(r"^file:(.+)$", re.IGNORECASE)
_URL = re.compile(r"^url:(https?://.+)$", re.IGNORECASE)


def naca4_coordinates(code: str, n: int = 80) -> list[tuple[float, float]]:
    """NACA 4-digit section, cosine-spaced, in Selig order (TE → upper → LE → lower → TE)."""
    m, p, t = int(code[0]) / 100.0, int(code[1]) / 10.0, int(code[2:]) / 100.0

    def camber(x: float) -> tuple[float, float]:
        if p == 0.0:
            return 0.0, 0.0
        if x < p:
            return m / p**2 * (2 * p * x - x * x), 2 * m / p**2 * (p - x)
        return (m / (1 - p) ** 2 * ((1 - 2 * p) + 2 * p * x - x * x),
                2 * m / (1 - p) ** 2 * (p - x))

    def thickness(x: float) -> float:
        return 5 * t * (0.2969 * math.sqrt(x) - 0.1260 * x - 0.3516 * x**2
                        + 0.2843 * x**3 - 0.1036 * x**4)

    xs = [(1 - math.cos(i * math.pi / n)) / 2 for i in range(n + 1)]
    upper, lower = [], []
    for x in xs:
        yc, dy = camber(x)
        th, ang = thickness(x), math.atan(dy)
        upper.append((x - th * math.sin(ang), yc + th * math.cos(ang)))
        lower.append((x + th * math.sin(ang), yc - th * math.cos(ang)))
    return list(reversed(upper)) + lower[1:]


def _validate(points: list[tuple[float, float]], name: str) -> None:
    if len(points) < 20:
        raise DesignError(f"airfoil {name!r}: only {len(points)} points; need at least 20")
    xs = [p[0] for p in points]
    if max(xs) - min(xs) < 0.5:
        raise DesignError(
            f"airfoil {name!r}: x range {min(xs):.3g}..{max(xs):.3g} — coordinates should "
            "be normalised to a unit chord"
        )
    gap = math.hypot(points[0][0] - points[-1][0], points[0][1] - points[-1][1])
    if gap > 0.05:
        raise DesignError(
            f"airfoil {name!r}: the trailing edge is open by {gap:.3g} chord. flow5 "
            "needs a closed or nearly closed trailing edge."
        )


def _parse_dat(text: str, name: str) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for line in text.splitlines():
        parts = line.replace(",", " ").split()
        if len(parts) < 2:
            continue
        try:
            x, y = float(parts[0]), float(parts[1])
        except ValueError:
            continue  # a header or comment line
        if abs(x) > 1e3 or abs(y) > 1e3:
            continue  # Lednicer-style point counts, not coordinates
        points.append((x, y))
    if not points:
        raise DesignError(f"airfoil {name!r}: no coordinates found in the source")
    return points


def resolve(name: str, source: str, project_root: Path) -> list[tuple[float, float]]:
    if m := _NACA4.match(source.strip()):
        return naca4_coordinates(m.group(1))
    if m := _FILE.match(source.strip()):
        path = (project_root / m.group(1)).resolve()
        if not path.is_file():
            raise DesignError(f"airfoil {name!r}: file not found: {path}")
        return _parse_dat(path.read_text(encoding="utf-8", errors="replace"), name)
    if m := _URL.match(source.strip()):
        try:
            with urllib.request.urlopen(m.group(1), timeout=30) as r:
                body = r.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError) as exc:
            raise DesignError(f"airfoil {name!r}: could not fetch {m.group(1)}: {exc}") from exc
        return _parse_dat(body, name)
    raise DesignError(
        f"airfoil {name!r}: unrecognised source {source!r}. Use `naca:2412`, "
        "`file:airfoils/foo.dat`, or `url:https://…`"
    )


def write_dat(path: Path, name: str, points: list[tuple[float, float]]) -> Path:
    """Write a `.dat` whose first line is the foil name flow5 will use."""
    _validate(points, name)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [name, *(f"{x:11.7f} {y:11.7f}" for x, y in points)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path

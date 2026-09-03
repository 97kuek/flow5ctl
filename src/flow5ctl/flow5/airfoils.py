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


#: A normalised airfoil coordinate lives in this box. Anything outside it is a point
#: count, a scale factor, or a comment that happened to parse as two numbers.
_X_RANGE = (-0.10, 1.10)
_Y_RANGE = (-0.60, 0.60)


def _numeric_blocks(text: str) -> list[list[tuple[float, float]]]:
    """Coordinate pairs, split into blocks at blank or non-numeric lines."""
    blocks: list[list[tuple[float, float]]] = [[]]
    for line in text.splitlines():
        parts = line.replace(",", " ").split()
        if len(parts) < 2:
            if blocks[-1]:
                blocks.append([])
            continue
        try:
            pair = (float(parts[0]), float(parts[1]))
        except ValueError:
            if blocks[-1]:
                blocks.append([])
            continue
        blocks[-1].append(pair)
    return [b for b in blocks if b]


def _parse_dat(text: str, name: str) -> list[tuple[float, float]]:
    """Read an airfoil coordinate file in either of the two formats in the wild.

    **Selig** — one contour, trailing edge → upper → leading edge → lower → trailing
    edge. This is what flow5 wants and what airfoiltools serves.

    **Lednicer** — a line of two point counts, then the upper surface leading edge →
    trailing edge, then the lower surface the same way. This is what the UIUC database
    serves, and it is not a contour: read naively it produces a shape that jumps from
    the upper trailing edge back to the leading edge, which flow5 rejects as an open
    trailing edge (measured: "open by 57.3 chord", because the point-count line was
    also being read as a coordinate at x = 42).

    Lednicer is detected by its count line and reassembled into Selig order.
    """
    blocks = _numeric_blocks(text)
    if not blocks:
        raise DesignError(f"airfoil {name!r}: no coordinates found in the source")

    first = blocks[0][0]
    is_lednicer = first[0] > 1.5 and first[1] > 1.5

    if is_lednicer:
        counts = (round(first[0]), round(first[1]))
        rest = blocks[0][1:] + [p for b in blocks[1:] for p in b]
        n_up, n_lo = counts
        if len(rest) >= n_up + n_lo:
            upper, lower = rest[:n_up], rest[n_up:n_up + n_lo]
        elif len(blocks) >= 3:
            # the counts did not fit; trust the blank-line split instead
            upper, lower = blocks[1], blocks[2]
        else:
            raise DesignError(
                f"airfoil {name!r}: the file declares {n_up}+{n_lo} points but only "
                f"{len(rest)} were found, and the surfaces are not separated by a "
                "blank line. Re-download it, or convert it to Selig format."
            )
        # both surfaces run leading edge → trailing edge; a contour runs
        # trailing edge → upper → leading edge → lower → trailing edge
        points = list(reversed(upper)) + lower[1:]
    else:
        points = [p for b in blocks for p in b]

    good = [
        (x, y) for x, y in points
        if _X_RANGE[0] <= x <= _X_RANGE[1] and _Y_RANGE[0] <= y <= _Y_RANGE[1]
    ]
    if len(good) < len(points) and len(good) < 20:
        raise DesignError(
            f"airfoil {name!r}: only {len(good)} of {len(points)} values look like "
            "normalised coordinates. The file may be in a format flow5ctl does not "
            "read, or the coordinates may not be scaled to a unit chord."
        )
    if not good:
        raise DesignError(f"airfoil {name!r}: no coordinates found in the source")
    return good


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

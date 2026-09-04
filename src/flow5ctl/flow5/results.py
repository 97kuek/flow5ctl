"""Read flow5's output files.

Written as if parsing untrusted input, because in practice it is. Every trap below
was hit for real while verifying flow5 7.57, and every one of them produces a
plausible wrong number rather than an error:

1. `polar_text_output_format=csv` writes plane polars as WHITESPACE-ALIGNED
   fixed-width text with **zero commas**, despite the `.csv` extension.
   (Foil polars are different — with `csv` they really are comma-separated, and
   without it they are genuine XFoil format.)
2. The FIRST data row is concatenated onto the header line with no newline. A naive
   line reader silently drops one operating point.
3. Data cells are fixed 13-character fields, but header LABELS are variable width and
   contain internal single spaces (`α (°)`, `Short Period Damping Ratio`). Labels are
   separated by runs of 2+ spaces. Take the column *count* from a data row, never
   from the label text.
4. A single-point polar has no standalone data line at all.
5. Cells may be `inf` or `nan` — `Roll Damping` was `inf` in every row of a T7 polar.
6. Operating-point files are duplicated into every polar's directory and carry
   ANOTHER polar's contents. The directory does not identify the polar.
7. `Static margin` is a PERCENTAGE of the reference chord, not a fraction.

The parser therefore validates itself: the number of rows recovered must equal the
file's own `Nbr. of data points`, or it raises. See
docs/adr/0010-treat-solver-output-as-hostile.md.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..errors import ParseError

_NUM = re.compile(
    r"^[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?$"   # ordinary numbers
    r"|^[-+]?(?:inf|nan)$",                            # trap 5
    re.IGNORECASE,
)
_LABEL_SPLIT = re.compile(r"\s{2,}")                   # trap 3
_POINT_COUNT = "Nbr. of data points"


def _is_num(token: str) -> bool:
    return bool(_NUM.match(token))


def _read(path: Path) -> list[str]:
    # trap: labels carry Unicode (α β φ ° ² ³ ∞ ρ ν); decode explicitly
    return path.read_text(encoding="utf-8", errors="replace").split("\n")


@dataclass(slots=True)
class Polar:
    """One parsed plane polar."""

    name: str
    header: dict[str, str]
    columns: list[str]
    rows: list[list[float]]
    path: Path
    nonfinite: list[tuple[int, str]] = field(default_factory=list)

    def index(self, label: str) -> int:
        """Column index by exact label, or by label with its unit token stripped."""
        if label in self.columns:
            return self.columns.index(label)
        for i, name in enumerate(self.columns):
            if name.split(" (")[0].strip() == label:
                return i
        raise ParseError(
            f"column {label!r} not present in {self.path.name}; "
            f"available: {', '.join(self.columns[:12])}…"
        )

    def column(self, label: str) -> list[float]:
        i = self.index(label)
        return [r[i] for r in self.rows]

    def has(self, label: str) -> bool:
        try:
            self.index(label)
        except ParseError:
            return False
        return True

    def header_float(self, key: str) -> float | None:
        """A numeric value from the prose header block.

        The value is not always the first token: flow5 writes
        `XNP = d(XCp.Cl)/dCl =     0.05 m`, whose "value" after the first `=` still
        contains an expression. The last numeric token is taken instead.
        """
        # Exact first. `startswith` alone could take a different key that happens
        # to begin with the same text, silently, and the header has keys like
        # `XNP` beside `XNP = d(XCp.Cl)/dCl`.
        def last_number(value: str) -> float | None:
            for token in reversed(value.replace(",", " ").split()):
                if _is_num(token):
                    return float(token)
            return None

        for k, v in self.header.items():
            if k.strip() == key:
                return last_number(v)
        # Only then a prefix, which is how `XNP` finds
        # `XNP = d(XCp.Cl)/dCl`. Ambiguity here is worth naming rather than
        # resolving by dictionary order.
        matches = [(k, v) for k, v in self.header.items() if k.startswith(key)]
        if len(matches) > 1:
            raise ParseError(
                f"{key!r} matches {len(matches)} header keys "
                f"({', '.join(repr(k) for k, _ in matches)}); which one is meant "
                "cannot be decided by order. flow5's header labels may have changed."
            )
        return last_number(matches[0][1]) if matches else None


def parse_polar(path: Path) -> Polar:
    path = Path(path)
    lines = _read(path)

    head_i = next(
        (i for i, ln in enumerate(lines) if "Ctrl" in ln and "CL" in ln and "CD" in ln),
        None,
    )
    if head_i is None:
        raise ParseError(f"{path.name}: no polar table header found")
    head = lines[head_i]

    header: dict[str, str] = {}
    for ln in lines[:head_i]:
        if "=" in ln:
            k, _, v = ln.partition("=")
            header[k.strip()] = v.strip()

    # column count comes from a DATA row, never from the label text (trap 3)
    ncol = data_len = None
    for ln in lines[head_i + 1:]:
        fields = ln.split()
        if fields and all(_is_num(f) for f in fields):
            ncol, data_len = len(fields), len(ln)
            break

    rows: list[list[float]] = []
    if ncol is not None and data_len is not None and len(head) > data_len:
        # trap 2: the first row is welded onto the header line
        embedded = head[len(head) - data_len:].split()
        if len(embedded) == ncol and all(_is_num(f) for f in embedded):
            rows.append([float(f) for f in embedded])
        label_region = head[: len(head) - data_len]
    else:
        # trap 4: single-point polar — no standalone data line exists
        fields = head.split()
        first_num = next((i for i, f in enumerate(fields) if _is_num(f)), len(fields))
        pos = 0
        for tok in fields[:first_num]:
            pos = head.index(tok, pos) + len(tok)
        label_region = head[:pos]
        tail = fields[first_num:]
        columns_guess = [c for c in _LABEL_SPLIT.split(label_region.strip()) if c]
        if tail and len(tail) == len(columns_guess):
            rows.append([float(f) for f in tail])
        ncol = len(columns_guess)

    columns = [c for c in _LABEL_SPLIT.split(label_region.strip()) if c]

    # Skipped lines are counted, not merely skipped. A row of the wrong width, or
    # one carrying a non-numeric field, used to vanish - caught only if the declared
    # point count happened to notice. When flow5 declares no count, or an
    # unparsable one, nothing noticed at all and the polar came back short.
    skipped: list[str] = []
    for ln in lines[head_i + 1:]:
        fields = ln.split()
        if not fields:
            continue
        if len(fields) != ncol or not all(_is_num(f) for f in fields):
            if any(_is_num(f) for f in fields):
                skipped.append(ln.strip()[:80])
            continue
        rows.append([float(f) for f in fields])

    if len(columns) != ncol:
        raise ParseError(
            f"{path.name}: recovered {len(columns)} column labels but rows have {ncol} "
            "fields. flow5's label formatting may have changed; see "
            "https://github.com/97kuek/flow5ctl/blob/main/docs/FLOW5-INTERFACE.md section 5.2."
        )

    # self-check: flow5 states how many points it wrote. Trust that over our parsing.
    claimed = header.get(_POINT_COUNT)
    want: int | None = None
    if claimed is not None:
        try:
            want = int(claimed)
        except ValueError:
            want = None
    if want is None and skipped:
        raise ParseError(
            f"{path.name}: {len(skipped)} line(s) after the header carry numbers but "
            f"could not be read as {ncol} numeric fields, and the file declares no "
            "usable point count to check the total against — so there is no way to "
            "tell whether operating points were lost. First: "
            f"{skipped[0]!r}. See "
            "https://github.com/97kuek/flow5ctl/blob/main/docs/FLOW5-INTERFACE.md "
            "section 5.2."
        )
    if want is not None and want != len(rows):
        raise ParseError(
                f"{path.name}: recovered {len(rows)} operating points but the file "
                f"declares {want}. Points were dropped — refusing to report a partial "
                "polar. See https://github.com/97kuek/flow5ctl/blob/main/docs/adr/0010-treat-solver-output-as-hostile.md."
            )

    nonfinite = [
        (i, columns[j] if j < len(columns) else f"col{j}")
        for i, row in enumerate(rows)
        for j, v in enumerate(row)
        if not math.isfinite(v)
    ]

    return Polar(
        name=path.stem,
        header=header,
        columns=columns,
        rows=rows,
        path=path,
        nonfinite=nonfinite,
    )


# --------------------------------------------------------------------------- strips

@dataclass(slots=True)
class StripTable:
    """The spanwise strip table for one surface at one operating point.

    The source for spanwise-loading plots, transition location and bending moment.
    Also a geometry cross-check: `Re = c·V/ν` recovers flow5's local chord.
    """

    surface: str
    columns: list[str]
    rows: list[list[float]]

    def column(self, label: str) -> list[float]:
        if label not in self.columns:
            raise ParseError(f"strip column {label!r} not present: {self.columns}")
        i = self.columns.index(label)
        return [r[i] for r in self.rows]


def parse_strips(path: Path) -> dict[str, StripTable]:
    lines = _read(Path(path))
    out: dict[str, StripTable] = {}
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("y(m)"):
            surface = next(
                (lines[j].strip() for j in range(i - 1, max(-1, i - 6), -1) if lines[j].strip()),
                "?",
            )
            columns = lines[i].split()
            rows: list[list[float]] = []
            k = i + 1
            while k < len(lines):
                fields = lines[k].split()
                if len(fields) != len(columns) or not all(_is_num(f) for f in fields):
                    break
                rows.append([float(f) for f in fields])
                k += 1
            out[surface] = StripTable(surface, columns, rows)
            i = k
        else:
            i += 1
    return out


def owning_polar(path: Path) -> str | None:
    """Which polar an operating-point file actually belongs to (trap 6).

    flow5 duplicates op-point files into every polar's directory, so the directory
    name lies. Line 2 of the file names the polar; that is the only reliable source.
    """
    lines = _read(Path(path))
    return lines[1].strip() if len(lines) > 1 and lines[1].strip() else None


# ----------------------------------------------------------------------- foil polars

@dataclass(slots=True)
class FoilPolar:
    foil: str
    reynolds: float
    ncrit: float
    alpha: list[float]
    cl: list[float]
    cd: list[float]
    cm: list[float]


def parse_foil_polar(path: Path) -> FoilPolar:
    """Parse a foil polar in either of the two shapes flow5 writes.

    With `polar_text_output_format=csv` it is genuinely comma separated; without it,
    it is XFoil-format whitespace text with a dashed rule under the header.
    """
    path = Path(path)
    lines = _read(path)
    foil, reynolds, ncrit = path.stem, 0.0, 9.0
    for ln in lines[:14]:
        if "Calculated polar for:" in ln:
            foil = ln.split(":", 1)[1].strip()
        if "Re =" in ln:
            m = re.search(r"Re\s*=\s*([0-9.]+)\s*e\s*([0-9]+)", ln)
            if m:
                reynolds = float(m.group(1)) * 10 ** float(m.group(2))
            m = re.search(r"Ncrit\s*=\s*([0-9.]+)", ln)
            if m:
                ncrit = float(m.group(1))

    head_i = next((i for i, ln in enumerate(lines) if ln.strip().lower().startswith("alpha")), None)
    if head_i is None:
        raise ParseError(f"{path.name}: no foil polar table found")
    sep = "," if "," in lines[head_i] else None

    a, cl, cd, cm = [], [], [], []
    for ln in lines[head_i + 1:]:
        if not ln.strip() or set(ln.strip()) <= {"-", " "}:
            continue
        fields = ln.split(sep) if sep else ln.split()
        if len(fields) < 5 or not all(_is_num(f.strip()) for f in fields[:5]):
            continue
        a.append(float(fields[0]))
        cl.append(float(fields[1]))
        cd.append(float(fields[2]))
        cm.append(float(fields[4]))
    if not a:
        raise ParseError(
            f"{path.name}: foil polar has no converged points. If this came from a "
            "batch run, check that the alpha sweep was given in OpPoint_Range, not "
            "Batch_Range — flow5 ignores the latter."
        )
    return FoilPolar(foil, reynolds, ncrit, a, cl, cd, cm)

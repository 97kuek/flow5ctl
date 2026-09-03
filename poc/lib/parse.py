"""Robust parser for flow5 polar / operating-point files. Verified vs flow5 7.57.

Traps handled — every one of these was hit for real:
  1. `polar_text_output_format=csv` writes WHITESPACE-ALIGNED fixed-width text,
     NOT comma-separated values, despite the .csv extension. Zero commas appear.
  2. The FIRST data row is concatenated onto the header line with no newline.
     A naive line reader silently drops one operating point.
  3. Data cells are fixed 13-char fields, but header LABELS are variable width
     and contain internal single spaces: `α (°)`, `Short Period Damping Ratio`,
     `Fx_FF_wind (N)`. Labels are separated by runs of 2+ spaces.
  4. Labels carry Unicode: α β φ ° ² ³ ∞ ρ ν. Read as UTF-8 explicitly.
  5. Numeric cells may be `inf` or `nan`. Accept them, then report them:
     `nonfinite()` lists (row, column) so a caller can warn instead of
     presenting a broken number as a result.
"""
import pathlib
import re

# flow5 emits non-finite values in numeric columns (verified: `inf` in the
# "Roll Damping" column of a T7 polar). A strict numeric pattern silently
# rejects the whole row, dropping operating points without warning.
_NUM = re.compile(r"^[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?$|^[-+]?(?:inf|nan)$",
                  re.IGNORECASE)
_SPLIT = re.compile(r"\s{2,}")

def _is_num(t): return bool(_NUM.match(t))

def polar_table(path):
    """-> (header_dict, colnames, rows). Rows include the one hidden in the header."""
    txt = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    lines = txt.split("\n")
    hi = next((i for i, l in enumerate(lines)
               if "Ctrl" in l and "CL" in l and "CD" in l), None)
    if hi is None:
        return {}, [], []
    head = lines[hi]

    # column count comes from a DATA row, never from the label text
    ncol, dlen = None, None
    for ln in lines[hi + 1:]:
        f = ln.split()
        if f and all(_is_num(x) for x in f):
            ncol, dlen = len(f), len(ln); break
    if ncol is None:
        # Single-point polar: there is no standalone data line, because the only
        # row is the one embedded in the header. Fall back to finding where the
        # label tokens stop and the numeric tail begins. Safe because no flow5
        # column label is a bare number ('CL^(3/2)/CD', '1/sqrt(CL)' are not).
        f = head.split()
        k = next((i for i, t in enumerate(f) if _is_num(t)), len(f))
        nnum = len(f) - k
        labels = _SPLIT.split(head.strip())
        # rebuild by measuring the character position of the first numeric field
        pos, cnt = 0, 0
        for tok in f:
            if cnt == k: break
            pos = head.index(tok, pos) + len(tok); cnt += 1
        label_region = head[:pos]
        names = [n for n in _SPLIT.split(label_region.strip()) if n]
        rows = []
        if nnum == len(names):
            rows.append([float(x) for x in f[k:]])
        hdr = {}
        for ln in lines[:hi]:
            if "=" in ln:
                a, _, b = ln.partition("=")
                hdr[a.strip()] = b.strip()
        return hdr, names, rows

    rows = []
    if ncol and dlen and len(head) > dlen:            # trap 2
        embedded = head[len(head) - dlen:]
        f = embedded.split()
        if len(f) == ncol and all(_is_num(x) for x in f):
            rows.append([float(x) for x in f])
        label_region = head[:len(head) - dlen]
    else:
        label_region = head

    names = [n for n in _SPLIT.split(label_region.strip()) if n]   # trap 3
    for ln in lines[hi + 1:]:
        f = ln.split()
        if len(f) != ncol or not all(_is_num(x) for x in f):
            continue
        rows.append([float(x) for x in f])
    hdr = {}
    for ln in lines[:hi]:
        if "=" in ln:
            k, _, v = ln.partition("=")
            hdr[k.strip()] = v.strip()
    return hdr, names, rows

def col(names, want):
    """Index by exact label, or by label with the unit token stripped."""
    if want in names: return names.index(want)
    for i, n in enumerate(names):
        if n.split(" (")[0].strip() == want: return i
    raise KeyError(f"{want!r} not found; have {names[:10]}")

def strips(path):
    """Spanwise strip tables from an operating-point file -> {wing: (names, rows)}."""
    lines = pathlib.Path(path).read_text(encoding="utf-8", errors="replace").split("\n")
    out, i = {}, 0
    while i < len(lines):
        if lines[i].strip().startswith("y(m)"):
            wing = next((lines[j].strip() for j in range(i - 1, max(-1, i - 6), -1)
                         if lines[j].strip()), "?")
            names = lines[i].split()
            rows, k = [], i + 1
            while k < len(lines):
                f = lines[k].split()
                if len(f) != len(names) or not all(_is_num(x) for x in f): break
                rows.append([float(x) for x in f]); k += 1
            out[wing] = (names, rows); i = k
        else:
            i += 1
    return out


def nonfinite(names, rows):
    """-> [(row_index, column_name)] for every non-finite cell."""
    import math
    out = []
    for i, r in enumerate(rows):
        for j, v in enumerate(r):
            if not math.isfinite(v):
                out.append((i, names[j] if j < len(names) else f"col{j}"))
    return out

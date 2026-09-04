"""Render an analysis as a PNG.

This exists for MCP clients, where the reader cannot open a file and a curve says in
one glance what twenty numbers do not. The CLI writes the same image to disk.

Chart rules followed here, and worth not undoing:

* **One axis, always.** No chart plots two quantities of different scale against two
  y-scales; the alignment would be arbitrary and would invent a correlation. The drag
  breakdown stacks CD components, which share units.
* **Thin marks, hairline solid grid, generous padding.** No dashed gridlines. The one
  dashed line in here is the Cm = 0 trim threshold, which is a threshold and reads
  correctly as one.
* **Identity never rests on colour.** Two or more series get a legend; four or fewer
  are also labelled at their endpoint.
* **Labels are selective.** The extreme that matters is annotated; the axis carries
  the rest. A number on every point goes unread.
* matplotlib is imported lazily, so the MCP server starts without paying for it.
"""
from __future__ import annotations

import io
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ..errors import DesignError
from .palette import MAX_SERIES, Theme
from .palette import theme as get_theme

Kind = Literal["cl_alpha", "cm_alpha", "polar", "drag_breakdown", "spanwise_lift"]

KINDS: dict[str, str] = {
    "cl_alpha": "lift coefficient against angle of attack",
    "cm_alpha": "pitching moment against angle of attack, with the trim point",
    "polar": "the drag polar — CL against CD, with best L/D marked",
    "drag_breakdown": "induced and viscous drag against angle of attack",
    "spanwise_lift": "local lift coefficient along the span, against elliptic",
}

_FONT = ["system-ui", "-apple-system", "Segoe UI", "Helvetica Neue", "DejaVu Sans"]


@dataclass(slots=True)
class Series:
    """One curve. `label` is what the legend and the direct label say."""

    label: str
    x: list[float]
    y: list[float]


def _rc(th: Theme) -> dict[str, Any]:
    return {
        "figure.facecolor": th.surface,
        "axes.facecolor": th.surface,
        "savefig.facecolor": th.surface,
        "font.family": "sans-serif",
        "font.sans-serif": _FONT,
        "font.size": 9,
        "text.color": th.ink,
        "axes.edgecolor": th.axis,
        "axes.labelcolor": th.ink_secondary,
        "axes.linewidth": 0.8,
        "axes.grid": True,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "grid.color": th.grid,
        "grid.linewidth": 0.6,
        "grid.linestyle": "-",          # never dashed
        "xtick.color": th.ink_muted,
        "ytick.color": th.ink_muted,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "legend.frameon": False,
        "legend.fontsize": 8,
        "legend.labelcolor": th.ink_secondary,
        "lines.linewidth": 2.0,
        "lines.markersize": 4.0,
        "lines.solid_capstyle": "round",
    }


def _draw(series: list[Series], *, title: str, subtitle: str, xlabel: str, ylabel: str,
          th: Theme, annotate: tuple[float, float, str] | None = None,
          zero_line: bool = False, stacked: bool = False,
          reference: Series | None = None, width: float = 7.2,
          height: float = 4.4) -> bytes:
    try:
        import matplotlib
    except ImportError as exc:
        raise DesignError(
            "charts need matplotlib, which is an optional dependency.\n"
            "  pip install 'flow5ctl[plot]'\n"
            "or, if you run flow5ctl with uvx:\n"
            "  uvx --from 'flow5ctl[plot]' flow5ctl mcp\n"
            "Everything else works without it — only `plot` needs it."
        ) from exc
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    with plt.rc_context(_rc(th)):
        fig, ax = plt.subplots(figsize=(width, height), dpi=160)

        if stacked:
            base = [0.0] * len(series[0].x)
            for i, s in enumerate(series):
                top = [b + v for b, v in zip(base, s.y, strict=True)]
                # a large area is not a small mark: fills stay light, so the chart
                # reads as data rather than as two saturated blocks
                ax.fill_between(s.x, base, top, color=th.colour(i), alpha=0.5,
                                linewidth=0, label=s.label)
                # a surface gap between fills, not a border around them
                ax.plot(s.x, top, color=th.surface, linewidth=1.6, zorder=3)
                base = top
        else:
            if reference is not None:
                ax.plot(reference.x, reference.y, color=th.ink_muted, linewidth=1.4,
                        linestyle=(0, (4, 3)), label=reference.label, zorder=2)
            for i, s in enumerate(series):
                # markers identify individual operating points; on a 40-strip spanwise
                # curve they turn the line into noise, so they drop out
                marker = "o" if len(s.x) <= 25 else None
                ax.plot(s.x, s.y, color=th.colour(i), marker=marker, markersize=5.0,
                        markeredgecolor=th.surface, markeredgewidth=1.0,
                        label=s.label, zorder=4 + i)

        if zero_line:
            ax.axhline(0.0, color=th.ink_muted, linewidth=1.0,
                       linestyle=(0, (4, 3)), zorder=1)
            ax.annotate("trim (Cm = 0)", xy=(0.995, 0.0), xycoords=("axes fraction", "data"),
                        ha="right", va="bottom", fontsize=7.5, color=th.ink_muted)

        if annotate is not None:
            x, y, text = annotate
            ax.plot([x], [y], marker="o", markersize=9, color=th.colour(0),
                    markeredgecolor=th.surface, markeredgewidth=1.8, zorder=10)
            # offset down and right, clear of a curve that rises to the right
            ax.annotate(text, xy=(x, y), xytext=(12, -16), textcoords="offset points",
                        fontsize=8, color=th.ink, zorder=11,
                        bbox={"facecolor": th.surface, "edgecolor": "none",
                              "alpha": 0.85, "pad": 2})

        entries = len(series) + (1 if reference is not None else 0)
        if entries >= 2:
            # identity never rests on colour: a legend is present whenever more than
            # one thing is drawn
            ax.legend(loc="best")
        # Direct labels are a second channel, not a repeat of the legend: they only
        # earn their space when several data series must be told apart at a glance.
        if 2 <= len(series) <= 4 and not stacked:
            ax.margins(x=0.12)
            for i, s in enumerate(series):
                if not s.x:
                    continue
                ax.annotate(s.label, xy=(s.x[-1], s.y[-1]), xytext=(6, 0),
                            textcoords="offset points", fontsize=7.5,
                            color=th.colour(i), va="center")

        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_title(title, color=th.ink, fontsize=11, loc="left", pad=14,
                     fontweight="medium")
        if subtitle:
            ax.annotate(subtitle, xy=(0, 1.02), xycoords="axes fraction",
                        fontsize=8, color=th.ink_secondary, va="bottom")
        ax.tick_params(length=3, width=0.8)
        fig.tight_layout(pad=1.4)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.22)
        plt.close(fig)
    return buf.getvalue()


def _column(result: dict[str, Any], label: str) -> list[float]:
    columns: list[str] = result["columns"]
    rows: list[list[float]] = result["rows"]
    idx = columns.index(label) if label in columns else next(
        (i for i, c in enumerate(columns) if c.split(" (")[0].strip() == label), None)
    if idx is None:
        raise DesignError(f"the stored polar has no {label!r} column")
    return [r[idx] for r in rows]


def _finite(*columns: list[float]) -> list[int]:
    n = len(columns[0])
    return [i for i in range(n) if all(math.isfinite(c[i]) for c in columns)]


def render(results: list[dict[str, Any]], kind: str, *, theme_name: str = "light",
           strips: dict[str, Any] | None = None) -> bytes:
    """Render one chart from one or more stored analysis results."""
    if kind not in KINDS:
        raise DesignError(
            f"unknown chart kind {kind!r}. Available: "
            + ", ".join(f"{k} ({v})" for k, v in KINDS.items())
        )
    if not results:
        raise DesignError("nothing to plot")
    if len(results) > MAX_SERIES:
        raise DesignError(
            f"{len(results)} polars is more than the {MAX_SERIES} distinguishable "
            "colours available. Plot fewer, or split them across charts — a ninth "
            "colour would be indistinguishable from an existing one under colour-vision "
            "deficiency."
        )
    th = get_theme(theme_name)
    first = results[0]
    design = first.get("design", "")
    subtitle = _subtitle(results)

    if kind == "spanwise_lift":
        if len(results) > 1:
            # The strips come from one result, so a second polar was silently
            # dropped while the subtitle went on naming both runs' conditions -
            # a chart showing one aircraft's loading captioned as if it covered
            # two. Refusing is what `drag_breakdown` already does.
            raise DesignError(
                "a spanwise loading chart shows one analysis at a time. The strip "
                "table it is drawn from belongs to a single operating point, and the "
                "elliptic reference is computed for that aircraft's own planform, so "
                "two of them in one frame would share neither. Plot them separately "
                "and compare the two images."
            )
        return _spanwise(design, strips, th, subtitle)

    if kind == "drag_breakdown":
        if len(results) > 1:
            raise DesignError(
                "a drag breakdown shows one analysis at a time — stacking two "
                "aircraft's components in one chart cannot be read. Plot them separately."
            )
        alpha = _column(first, "α")
        induced = _column(first, "CD_induced")
        viscous = _column(first, "CD_viscous")
        keep = _finite(alpha, induced, viscous)
        return _draw(
            [Series("induced", [alpha[i] for i in keep], [induced[i] for i in keep]),
             Series("viscous", [alpha[i] for i in keep], [viscous[i] for i in keep])],
            title=f"{design} — drag breakdown",
            subtitle=subtitle,
            xlabel="angle of attack  α (°)", ylabel="CD",
            th=th, stacked=True,
        )

    series: list[Series] = []
    annotate = None
    for n, res in enumerate(results):
        label = res.get("polar", f"polar {n + 1}")
        if kind == "cl_alpha":
            xs, ys = _column(res, "α"), _column(res, "CL")
            xlabel, ylabel, title = "angle of attack  α (°)", "CL", "lift curve"
        elif kind == "cm_alpha":
            xs, ys = _column(res, "α"), _column(res, "Cm")
            xlabel, ylabel, title = "angle of attack  α (°)", "Cm", "pitching moment"
        else:  # polar
            xs, ys = _column(res, "CD"), _column(res, "CL")
            xlabel, ylabel, title = "CD", "CL", "drag polar"
        keep = _finite(xs, ys)
        series.append(Series(label, [xs[i] for i in keep], [ys[i] for i in keep]))

        if kind == "polar" and n == 0:
            best = (res.get("summary") or {}).get("best_LD")
            if best and best.get("cl") is not None and best.get("cd") is not None:
                annotate = (best["cd"], best["cl"],
                            f"best L/D {best['value']:.1f} at α {best['alpha']:g}°")

    return _draw(series, title=f"{design} — {title}", subtitle=subtitle,
                 xlabel=xlabel, ylabel=ylabel, th=th, annotate=annotate,
                 zero_line=(kind == "cm_alpha"))


def _subtitle(results: list[dict[str, Any]]) -> str:
    """The conditions, but only the ones every polar on the chart shares.

    A comparison chart used to take its subtitle from the first result alone, so
    plotting a 12 m/s run against an 8 m/s one was labelled "12 m/s" and the second
    curve was silently attributed a speed it was not run at. On a chart whose entire
    purpose is comparison, that is the caption undoing the comparison.

    Where the runs differ the value is shown as a range, and where the difference is
    the thing being compared that is exactly what the reader needs to see.
    """
    def values(key: str) -> list[Any]:
        seen = []
        for r in results:
            v = (r.get("conditions") or {}).get(key)
            if v is not None and v not in seen:
                seen.append(v)
        return seen

    def span(key: str, fmt: str) -> str | None:
        vs = [v for v in values(key) if isinstance(v, (int, float))]
        if not vs:
            return None
        return fmt.format(min(vs)) if len(vs) == 1 else \
            f"{fmt.format(min(vs))}–{fmt.format(max(vs))}"

    methods = values("viscous_method") or ["inviscid"]
    versions = [v for v in (r.get("flow5_version") for r in results) if v]
    parts = [
        span("speed", "{:g} m/s"),
        " / ".join(str(m) for m in methods),
        (lambda g: f"ground {g}" if g else None)(span("ground_height", "{:g} m")),
        f"flow5 {'/'.join(dict.fromkeys(versions))}" if versions else None,
    ]
    return " · ".join(p for p in parts if p)


def _spanwise(design: str, strips: dict[str, Any] | None, th: Theme,
              subtitle: str) -> bytes:
    """Local lift against span, with the elliptic distribution for comparison.

    The elliptic curve is the reference because it is the minimum-induced-drag
    loading for a planar wing. It is drawn as a muted dashed line, not a series: it
    is a target, not a measurement.
    """
    if not strips:
        raise DesignError(
            "this analysis has no spanwise data stored. Re-run it — operating points "
            "are on by default, and the strip table is saved with the result."
        )
    wing, table = next(iter(strips.items()))
    ys = table["y"]
    cls = table["cl"]
    keep = _finite(ys, cls)
    ys = [ys[i] for i in keep]
    cls = [cls[i] for i in keep]
    if not ys:
        raise DesignError("the strip table has no usable rows")

    half = table.get("semi_span") or max(abs(y) for y in ys)
    chord = _relative_chord(table, keep)
    elliptic = _elliptic_reference(ys, cls, chord, half)

    # A lift distribution is read at one angle of attack and is a different curve at
    # every other one, so the angle belongs on the chart. It used to be absent, while
    # the strips themselves came from whichever operating-point file sorted to the
    # middle of the directory.
    alpha = table.get("alpha")
    if alpha is not None:
        subtitle = " · ".join(filter(None, [subtitle, f"at α {alpha:g}°"]))

    return _draw(
        [Series(f"{wing} — local Cl", ys, cls)],
        title=f"{design} — spanwise lift distribution",
        subtitle=subtitle,
        xlabel="span position  y (m)", ylabel="local Cl",
        th=th, reference=elliptic, width=7.6, height=4.2,
    )


def _relative_chord(table: dict[str, Any], keep: list[int]) -> list[float] | None:
    """The chord distribution, up to a constant, from the strip Reynolds numbers.

    flow5's strip table has no chord column, but within one operating point the
    freestream is uniform, so Re is exactly proportional to the local chord.

    A reviewer said that was assumed rather than established, and named the cases
    that might break it. Measured on the shipped 34 m example, which has ground
    effect on and a taper ratio of 2.222:

    | polar | root Re | tip Re | ratio |
    |---|---|---|---|
    | T1 fixed speed | 612,685 | 276,957 | 2.212 |
    | T2 fixed lift — speed solved per point | 561,166 | 253,668 | **2.212** |
    | T5 sideslip | 612,685 | 276,957 | 2.212 |

    The absolute values move, T2 solving a lower speed, but the ratio does not — and
    this normalises by the maximum, so only the ratio is used. Under sideslip the
    left and right values are identical to the digit. The 2.212 against a taper of
    2.222 is the outermost strip's centroid sitting inboard of the tip.
    """
    re = table.get("re")
    if not re:
        return None
    vals = [re[i] for i in keep]
    if len(vals) != len(keep) or not all(isinstance(v, (int, float)) for v in vals):
        return None
    hi = max(vals)
    if hi <= 0 or min(vals) <= 0:
        return None
    return [v / hi for v in vals]


def _integrate(ys: list[float], vs: list[float], half: float | None = None) -> float:
    """Trapezoid over the strip centroids, closed to zero at the tips.

    The centroids stop short of the tip, so integrating only between them leaves
    the outermost interval out of both totals. Closing each end at zero load on the
    physical tip is the right closure and keeps the two sides comparable.
    """
    xs, ws = list(ys), list(vs)
    if half:
        if xs[0] > -half:
            xs.insert(0, -half)
            ws.insert(0, 0.0)
        if xs[-1] < half:
            xs.append(half)
            ws.append(0.0)
    return sum((ws[i] + ws[i - 1]) / 2.0 * (xs[i] - xs[i - 1]) for i in range(1, len(xs)))


def _elliptic_reference(ys: list[float], cls: list[float],
                        chord: list[float] | None, half: float) -> Series:
    """The elliptic comparison, drawn in the same quantity as the measured curve.

    **Elliptic means the loading is elliptic, not the local Cl.** Loading is Cl·c, so
    on a tapered wing the local Cl that produces an elliptic load *rises* towards the
    tip rather than falling like sqrt(1 - eta^2). Drawing sqrt(1 - eta^2) against
    local Cl compares two different quantities, and on the 34 m example — taper 0.45
    — it made a wing whose loading is close to elliptic look far below it. The scale
    used to be fitted on the sum of Cl, which is the total lift only if the chord and
    the strip widths are constant; neither is true on a tapered wing with cosine
    spacing.

    With no chord available (a result stored before Re was kept) this falls back to
    the old shape, and says so in the label rather than pretending.
    """
    shape = [math.sqrt(max(0.0, 1.0 - (y / half) ** 2)) for y in ys]
    if chord is None:
        total = sum(shape)
        scale = (sum(cls) / total) if total else 1.0
        return Series("elliptic (approximate)", ys, [v * scale for v in shape])

    lift = _integrate(ys, [cls[i] * chord[i] for i in range(len(ys))], half)
    ref = _integrate(ys, shape, half)
    scale = (lift / ref) if ref else 1.0
    return Series("elliptic loading (same lift)", ys,
                  [scale * shape[i] / chord[i] for i in range(len(ys))])


def write(path: Path, data: bytes) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path

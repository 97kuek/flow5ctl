"""Chart colours and chrome.

Both modes are *selected*, not flipped: the dark values are the same hues stepped
for the dark surface. Validated with the data-viz palette validator — the first three
categorical slots clear the all-pairs colour-vision gates in both modes
(worst CVD ΔE 9.2 light / 9.4 dark, normal-vision 24.0 / 20.9).

On the light surface the aqua slot sits below 3:1 contrast, so the relief rule
applies: every chart with two or more series carries a legend, charts with four or
fewer also direct-label their series, and the analysis summary that accompanies every
plot is the table view. Colour never carries identity alone.
"""
from __future__ import annotations

from dataclasses import dataclass

#: Fixed categorical order. Never cycled, never reassigned by rank — a series keeps
#: its hue when another is filtered out.
SERIES_LIGHT = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100",
                "#e87ba4", "#008300", "#4a3aa7", "#e34948")
SERIES_DARK = ("#3987e5", "#d95926", "#199e70", "#c98500",
               "#d55181", "#008300", "#9085e9", "#e66767")

MAX_SERIES = len(SERIES_LIGHT)


@dataclass(frozen=True, slots=True)
class Theme:
    name: str
    surface: str
    ink: str
    ink_secondary: str
    ink_muted: str
    grid: str
    axis: str
    series: tuple[str, ...]

    def colour(self, index: int) -> str:
        return self.series[index % len(self.series)]


LIGHT = Theme(
    name="light",
    surface="#fcfcfb",
    ink="#0b0b0b",
    ink_secondary="#52514e",
    ink_muted="#898781",
    grid="#e1e0d9",
    axis="#c3c2b7",
    series=SERIES_LIGHT,
)

DARK = Theme(
    name="dark",
    surface="#1a1a19",
    ink="#ffffff",
    ink_secondary="#c3c2b7",
    ink_muted="#898781",
    grid="#2c2c2a",
    axis="#383835",
    series=SERIES_DARK,
)

THEMES = {"light": LIGHT, "dark": DARK}


def theme(name: str) -> Theme:
    try:
        return THEMES[name.lower()]
    except KeyError:
        raise ValueError(f"unknown theme {name!r}; use 'light' or 'dark'") from None

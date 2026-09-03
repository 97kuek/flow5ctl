"""Unit handling.

SI internally, always. Conversion happens here and nowhere else.
Angles are degrees in `design.yaml` and in every user-facing value, radians inside
geometry code — hence the `_deg` / `_rad` naming convention used throughout.
"""
from __future__ import annotations

LENGTH_TO_M: dict[str, float] = {
    "m": 1.0, "cm": 0.01, "mm": 0.001,
    "in": 0.0254, "ft": 0.3048,
}
MASS_TO_KG: dict[str, float] = {
    "kg": 1.0, "g": 0.001, "lb": 0.45359237, "oz": 0.028349523125,
}
SPEED_TO_MS: dict[str, float] = {
    "m/s": 1.0, "km/h": 1 / 3.6, "mph": 0.44704, "kt": 0.5144444444444445,
    "ft/s": 0.3048,
}

GRAVITY = 9.80665
"""Standard gravity, m/s^2."""


def to_si_length(value: float, unit: str) -> float:
    try:
        return value * LENGTH_TO_M[unit]
    except KeyError:
        raise ValueError(f"unknown length unit {unit!r}; known: {sorted(LENGTH_TO_M)}") from None


def to_si_mass(value: float, unit: str) -> float:
    try:
        return value * MASS_TO_KG[unit]
    except KeyError:
        raise ValueError(f"unknown mass unit {unit!r}; known: {sorted(MASS_TO_KG)}") from None


def to_si_speed(value: float, unit: str) -> float:
    try:
        return value * SPEED_TO_MS[unit]
    except KeyError:
        raise ValueError(f"unknown speed unit {unit!r}; known: {sorted(SPEED_TO_MS)}") from None


def static_margin_from_flow5(percent: float) -> float:
    """flow5 reports static margin as a PERCENTAGE of the reference chord.

    A reported -0.59 means -0.59 %, i.e. marginally unstable — not -59 %.
    Verified in docs/FLOW5-INTERFACE.md section 5.3. Normalised to a fraction here,
    once, at the boundary.
    """
    return percent / 100.0

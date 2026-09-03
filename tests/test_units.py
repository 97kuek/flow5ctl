from __future__ import annotations

import pytest

from flow5ctl import units


@pytest.mark.parametrize("value,unit,expected", [
    (1.0, "m", 1.0), (100.0, "cm", 1.0), (1000.0, "mm", 1.0),
    (1.0, "in", 0.0254), (1.0, "ft", 0.3048),
])
def test_length(value, unit, expected):
    assert units.to_si_length(value, unit) == pytest.approx(expected)


@pytest.mark.parametrize("value,unit,expected", [
    (1.0, "kg", 1.0), (1000.0, "g", 1.0), (1.0, "lb", 0.45359237),
])
def test_mass(value, unit, expected):
    assert units.to_si_mass(value, unit) == pytest.approx(expected)


@pytest.mark.parametrize("value,unit,expected", [
    (1.0, "m/s", 1.0), (3.6, "km/h", 1.0), (1.0, "kt", 0.5144444),
])
def test_speed(value, unit, expected):
    assert units.to_si_speed(value, unit) == pytest.approx(expected, rel=1e-6)


def test_unknown_unit_lists_what_is_known():
    with pytest.raises(ValueError, match="known"):
        units.to_si_length(1.0, "furlong")


def test_static_margin_is_converted_from_percent():
    """flow5's -0.590317 means -0.59 %, not -59 %."""
    assert units.static_margin_from_flow5(-0.590317) == pytest.approx(-0.00590317)
    assert units.static_margin_from_flow5(29.8478) == pytest.approx(0.298478)

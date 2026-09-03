from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture
def rect_design() -> dict:
    """The rectangular wing from PoC case A: S = 0.4 m², b = 2 m, MAC = 0.2 m, AR = 10."""
    return {
        "name": "RectWing",
        "preset": "custom",
        "requirements": {"cruise_speed": 15.0},
        "mass": {"components": [{"tag": "ballast", "mass": 1.0, "at": [0.05, 0.0, 0.0]}]},
        "airfoils": [{"name": "NACA0012", "source": "naca:0012"}],
        "wing": {
            "airfoil": "NACA0012",
            "planform": {"span": 2.0, "root_chord": 0.2},
            "panels": {"chordwise": 13, "spanwise": 20, "span_distribution": "UNIFORM"},
        },
    }

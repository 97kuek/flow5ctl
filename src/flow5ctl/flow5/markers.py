"""What flow5 prints, and what it means.

flow5's exit code is not a success signal: it exits 0 for a script it rejected
outright and for a run in which every operating point failed. A NON-zero code means
it crashed. So success is read from stdout, and the exit code is checked separately
for crashes. Both are required.

Verified against flow5 7.57 — docs/FLOW5-INTERFACE.md section 6.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Outcome(Enum):
    OK = "ok"
    SCRIPT_REJECTED = "script_rejected"
    NO_PAIRS = "no_pairs"
    SOLVER_ERROR = "solver_error"
    CRASHED = "crashed"
    UNKNOWN = "unknown"


SUCCESS = (
    "Panel analysis completed successfully",
    "LLT analysis completed successfully",
    "_____Foil analysis completed_____",
)

FAILURE = (
    "Panel analysis completed ... Errors encountered",
    "LLT analysis completed ... Errors encountered",
)

SCRIPT_REJECTED = (
    "Error reading script...aborting",
    "The file is not an xml readable script",
    "Expected character data.",
    "Error making directories ...aborting",
)

# Scoped to "(plane, polar)" deliberately: flow5 emits
# `Made 0 valid analysis pairs (boat, polar) to run` on EVERY run for the unused sail
# module, so an unscoped match reports failure on every success.
NO_PLANE_PAIRS = "Made 0 valid analysis pairs (plane, polar) to run"

SCRIPT_ACCEPTED = "Script imported, no parsing error"


@dataclass(frozen=True, slots=True)
class Diagnosis:
    outcome: Outcome
    message: str
    hint: str = ""
    internal: bool = False
    """True when this is a flow5ctl bug rather than a problem with the design."""


_DIAGNOSTICS: tuple[tuple[str, Diagnosis], ...] = (
    ("foils not found ...discarding this plane", Diagnosis(
        Outcome.SOLVER_ERROR,
        "flow5 discarded the plane because an airfoil could not be resolved.",
        "A section references an airfoil name flow5 did not load. Remember that a "
        "foil's name is the first line of its .dat file, not the filename.",
        internal=True,
    )),
    ("error: reference", Diagnosis(
        Outcome.SOLVER_ERROR,
        "The analysis had no reference dimensions.",
        "flow5ctl should always emit CUSTOM reference dimensions.",
        internal=True,
    )),
    ("Viscous interpolation failures", Diagnosis(
        Outcome.SOLVER_ERROR,
        "The 2D airfoil polar mesh does not cover the conditions this analysis reached.",
        # Deliberately does not pick an axis. flow5 usually prints this header with no
        # detail lines under it, so nothing here knows whether Reynolds or lift ran
        # off the mesh - `explain_interpolation_failure` replaces this text whenever
        # it can work it out, and naming a cause here sent at least one real
        # investigation the wrong way.
        "Either the Reynolds range or the lift range of the 2D polars is too narrow. "
        "Widening the airfoil polar alpha sweep extends the lift range; widening its "
        "Reynolds range covers a tip that flies slower than the cruise point.",
    )),
    ("OTF failures:", Diagnosis(
        Outcome.SOLVER_ERROR,
        "On-the-fly XFoil did not converge at one or more wing strips.",
        "Use the interpolated viscous method instead. On-the-fly XFoil is unreliable "
        "on small tail surfaces.",
    )),
    ("Error generating the operating point", Diagnosis(
        Outcome.SOLVER_ERROR,
        "One or more operating points failed to converge.",
        "Narrow the alpha range, or widen the airfoil polar Reynolds range.",
    )),
)


def diagnose(stdout: str, returncode: int) -> Diagnosis:
    if returncode != 0:
        return Diagnosis(
            Outcome.CRASHED,
            f"flow5 terminated abnormally (exit {returncode}) without completing.",
            "flow5 segfaults when one script contains both a foil analysis and a "
            "plane analysis; flow5ctl runs them separately, so this should not happen.",
            internal=True,
        )

    for marker in SCRIPT_REJECTED:
        if marker in stdout:
            return Diagnosis(
                Outcome.SCRIPT_REJECTED,
                f"flow5 rejected the generated script ({marker!r}).",
                "The XML flow5ctl produced is invalid.",
                internal=True,
            )

    if NO_PLANE_PAIRS in stdout:
        return Diagnosis(
            Outcome.NO_PAIRS,
            "flow5 matched no plane with any analysis.",
            "The polar's Plane_Name must equal the plane's Name exactly.",
            internal=True,
        )

    if any(m in stdout for m in FAILURE):
        for marker, diag in _DIAGNOSTICS:
            if marker in stdout:
                return diag
        return Diagnosis(
            Outcome.SOLVER_ERROR,
            "flow5 ran but reported errors.",
            "Check the run log for the failing operating points.",
        )

    for marker, diag in _DIAGNOSTICS:
        if marker in stdout and not any(m in stdout for m in SUCCESS):
            return diag

    if any(m in stdout for m in SUCCESS):
        return Diagnosis(Outcome.OK, "flow5 completed successfully.")

    return Diagnosis(
        Outcome.UNKNOWN,
        "flow5 produced no recognisable completion marker.",
        "This may be a flow5 version whose output differs from the one flow5ctl was "
        "verified against.",
    )


def panel_count(stdout: str) -> int | None:
    """flow5 reports its own element count — useful for a mesh budget."""
    for line in stdout.splitlines():
        s = line.strip()
        if s.startswith("Counted ") and s.endswith(" elements"):
            try:
                return int(s.split()[1])
            except (ValueError, IndexError):
                return None
    return None


def discarded_points(stdout: str) -> int:
    return stdout.count("Error generating the operating point")


# flow5 prints the failing strip in one of two shapes, depending on which quantity
# it could not interpolate on.
_FAILED_CL = re.compile(
    r"Span position\s+([-\d.]+)\s*m,\s*Re\s*=\s*([\d.]+),\s*Cl\s*=\s*([-\d.]+)"
)
_FAILED_AOA = re.compile(
    r"Span position\s+([-\d.]+)\s*m,\s*Re\s*=\s*([\d.]+),\s*AoA_effective\s*=\s*([-\d.]+)"
)


def interpolation_failures(log: str) -> list[tuple[float, float, float]]:
    """(span position, Reynolds, Cl) for each strip where 2D interpolation failed."""
    return [(float(a), float(b), float(c)) for a, b, c in _FAILED_CL.findall(log)]


def aoa_failures(log: str) -> list[tuple[float, float, float]]:
    """(span position, Reynolds, effective AoA in degrees) for the other shape."""
    return [(float(a), float(b), float(c)) for a, b, c in _FAILED_AOA.findall(log)]


#: flow5 names the surface it is working on just before it gives up on it.
_PROCESSING = re.compile(r"^\s*(?:\.\.\.)?Processing\s+(.+?)\s*$", re.MULTILINE)


def failing_surface(log: str) -> str | None:
    """The surface flow5 was processing when interpolation failed.

    flow5 prints `...Viscous interpolation failures:` with no detail lines beneath
    it, so this is often the only fact available about where the failure was.
    """
    idx = log.find("Viscous interpolation failures")
    if idx == -1:
        return None
    names = _PROCESSING.findall(log[:idx])
    return names[-1].strip() if names else None


def explain_interpolation_failure(log: str, mesh_lo: float, mesh_hi: float,
                                  cl_cover: tuple[float, float] | None = None,
                                  cl_wanted: float | None = None) -> str | None:
    """Say which of the two very different causes actually applies.

    A "viscous interpolation failure" can mean the 2D polar mesh is too narrow, or it
    can mean the operating point itself is unphysical. A fixed-lift polar asked for an
    angle of attack where CL is about zero has no finite solution: flow5 solves an
    enormous speed instead of refusing, and the interpolation then fails at a Reynolds
    number hundreds of times too high. Blaming the mesh in that case sends the user
    the wrong way.
    """
    aoa = aoa_failures(log)
    if aoa:
        worst = max(aoa, key=lambda f: abs(f[2]))
        if abs(worst[2]) > 30.0:
            return (
                f"The solver computed an effective angle of attack of {worst[2]:.0f}° at "
                f"span position {worst[0]:+.2f} m. That is not a physical flow angle — it "
                "means the panelling is degenerate there, almost always because two "
                "surfaces occupy the same space.\n"
                "The usual cause is a fin whose root sits exactly on the elevator, or two "
                "surfaces at an identical position. Offset one of them by a few "
                "centimetres in z."
            )
        return (
            f"The effective angle of attack reached {worst[2]:.1f}° at span position "
            f"{worst[0]:+.2f} m, outside the range the 2D polars cover. Widen the airfoil "
            "polar alpha sweep, or reduce the incidence of that surface."
        )

    failures = interpolation_failures(log)
    if not failures:
        if "Viscous interpolation failures" not in log:
            return None          # nothing went wrong; there is nothing to explain
        # flow5 usually prints the header with nothing under it. Say what is known
        # rather than guessing an axis, and name the surface if the log gives one.
        where = failing_surface(log)
        parts = ["flow5 could not interpolate 2D drag"]
        parts.append(f" for {where}" if where else "")
        parts.append(", and printed no detail about which strip or condition.\n")
        parts.append(
            f"The 2D polars cover Reynolds {mesh_lo:,.0f} to {mesh_hi:,.0f}"
        )
        if cl_cover:
            parts.append(f" and lift coefficients {cl_cover[0]:.2f} to {cl_cover[1]:.2f}")
        parts.append(".\n")
        if cl_cover and cl_wanted is not None and cl_wanted > cl_cover[1]:
            parts.append(
                f"The wing reaches a local Cl of about {cl_wanted:.2f}, above what "
                "those polars carry, so the alpha sweep in `airfoils[].polars.alpha` "
                "is the thing to widen."
            )
        else:
            parts.append(
                "Either could be the cause and flow5 does not say which. Widening the "
                "alpha sweep in `airfoils[].polars.alpha` is the cheaper thing to try "
                "- it costs one more 2D pass, not a whole ladder of Reynolds numbers "
                "- and it did resolve this on a 32 m aircraft whose polars ran to 16 "
                "degrees. Widen the Reynolds range if that does not help."
            )
        return "".join(parts)
    res = [re_ for _, re_, _ in failures]
    cls = [cl for _, _, cl in failures]
    lo, hi = min(res), max(res)

    if hi > mesh_hi * 10 and max(abs(c) for c in cls) < 0.05:
        return (
            f"The analysis reached a Reynolds number of {hi:,.0f} with a local lift "
            "coefficient of about zero. That is not a mesh problem — it is a fixed-lift "
            "or glide polar being asked for an angle of attack that produces no lift, "
            "where the required speed diverges.\n"
            "Start the alpha range above the zero-lift angle. For a symmetric section "
            "that means alpha > 0; for a cambered one, a degree or two above its own "
            "zero-lift angle."
        )
    if lo < mesh_lo or hi > mesh_hi:
        return (
            f"Local Reynolds numbers between {lo:,.0f} and {hi:,.0f} were reached, "
            f"outside the 2D polar mesh which covers {mesh_lo:,.0f} to {mesh_hi:,.0f}. "
            "Widen the airfoil polar Reynolds range, or narrow the alpha sweep."
        )
    return (
        f"Interpolation failed at {len(failures)} strip(s) inside the mesh range "
        f"({mesh_lo:,.0f} to {mesh_hi:,.0f}), at Cl values from {min(cls):.2f} to "
        f"{max(cls):.2f}. The 2D polars may not cover that lift range — widen the "
        "airfoil polar alpha sweep."
    )

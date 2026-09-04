"""Whether the aircraft that came back is one that can be flown.

Every design may declare the static margin it wants — `requirements.static_margin`
— and every preset carries a band for its class. Until this module existed, neither
was ever compared against the result. An analysis could report a **negative** static
margin, meaning the CG sits behind the neutral point and the aircraft diverges in
pitch instead of returning to trim, and the report would say nothing about it.

That is the exact failure this project is built to prevent. The shipped HPA example
was in that state and nothing caught it: −10.1 % MAC against a declared requirement
of 5–15 %, reported beside a lift-to-drag figure of 50.6 that reads like success.

**The CG-height term is not a rescue.** When the CG hangs well below the wing — a
human-powered aircraft, where the pilot is most of the mass and sits under it — the
pitch stiffness includes a force-tilt term the classical static margin does not, and
it can be positive while the classical margin is negative. Those are two different
quantities. Tail-sizing rules and every published CG band refer to the classical
one, so a negative classical margin is reported as the finding it is, and the
stiffness number is mentioned only so the reader is not confused by seeing both.
"""
from __future__ import annotations

from typing import Any

#: Below this the two margins are the same number and saying both is noise.
_DIFFERS = 0.005


def _fmt(band: tuple[float, float]) -> str:
    return f"{band[0]:.0%}-{band[1]:.0%}"


def notes(summary: Any, *, required: tuple[float, float] | None = None,
          preset_band: tuple[float, float] | None = None,
          design: str = "this design") -> list[str]:
    """What is worth saying about the static margin that came back.

    `required` is the design's own `requirements.static_margin`; `preset_band` is
    the class default. The design's own statement wins, and the message says which
    one it is being held to — being told a number is "out of band" without being
    told whose band is not actionable.
    """
    sm = getattr(summary, "static_margin", None)
    if sm is None:
        return []

    out: list[str] = []
    stiffness = getattr(summary, "pitch_stiffness_margin", None)
    also = ""
    if stiffness is not None and abs(stiffness - sm) > _DIFFERS:
        also = (f" Including the CG-height term the pitch stiffness is "
                f"{stiffness:+.1%}, which is a different quantity and not a "
                "substitute for this one.")

    if sm <= 0:
        out.append(
            f"the static margin is {sm:+.1%} MAC: the CG is behind the neutral "
            f"point, so {design} diverges in pitch rather than returning to trim. "
            f"It is not flyable as it stands.{also} Move the CG forward — "
            "`flow5ctl trim <design> --target static-margin --value 0.10` solves "
            "for the position that gives a 10 % margin."
        )
        return out

    band, whose = ((required, "this design asks for") if required
                   else (preset_band, "the preset for this class expects"))
    if band:
        low, high = band
        if sm < low:
            out.append(
                f"the static margin is {sm:+.1%} MAC and {whose} {_fmt(band)}. "
                "It is stable, but with less margin than intended: build tolerance, "
                "pilot movement and a wet wing all eat into it."
            )
        elif sm > high:
            out.append(
                f"the static margin is {sm:+.1%} MAC and {whose} {_fmt(band)}. "
                "Over-stable costs trim drag and makes the aircraft slow to respond; "
                "check the elevator can still trim the speed range you want."
            )
    return out
